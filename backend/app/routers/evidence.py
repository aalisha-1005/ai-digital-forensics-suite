import json
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import config, models
from ..database import get_db
from ..deps import client_ip, current_user, get_case_or_404, get_evidence_or_404, is_admin, require_admin
from ..models import iso, utcnow
from ..serializers import evidence_out
from ..services import evidence_ops as ops
from ..services import metadata, records, settings_store
from .cases import scoped_cases

router = APIRouter(prefix="/api", tags=["evidence"])
CHUNK = 1024 * 1024


def _commit_and_raise(db, exc: ops.EvidenceError):
    db.commit()  # keep the audit/custody trail of the failed attempt
    raise HTTPException(exc.status, str(exc))


@router.post("/cases/{case_id}/evidence", status_code=201)
async def upload(case_id: str, request: Request, file: UploadFile = File(...), source_description: str = Form("", max_length=2000),
                 user=Depends(current_user), db: Session = Depends(get_db)):
    case = get_case_or_404(db, case_id, user, write=True)
    limit = int(settings_store.get_all(db)["max_upload_mb"]) * 1024 * 1024
    tmp = config.DATA_DIR / f"upload_{uuid.uuid4().hex}.part"
    total = 0
    try:
        with open(tmp, "wb") as out:
            while chunk := await file.read(CHUNK):
                total += len(chunk)
                if total > limit:
                    raise HTTPException(413, f"File exceeds the configured limit of {limit // (1024 * 1024)} MB")
                out.write(chunk)
        ev = ops.ingest(db, case, user, tmp, file.filename or "unnamed", file.content_type or "", source_description,
                        ip=client_ip(request))
        db.commit()
        db.refresh(ev)
        return evidence_out(ev)
    except ops.EvidenceError as exc:
        raise HTTPException(exc.status, str(exc))
    finally:
        tmp.unlink(missing_ok=True)


@router.get("/evidence")
def list_evidence(q: str = "", case_id: str = "", file_type: str = "", integrity: str = "", date_from: str = "",
                  date_to: str = "", investigator_id: int | None = None, user=Depends(current_user),
                  db: Session = Depends(get_db)):
    ids = [c.id for c in scoped_cases(db, user).all()]
    query = db.query(models.Evidence).join(models.Case).filter(models.Evidence.case_id.in_(ids))
    if q:
        like = f"%{q.strip()[:100]}%"
        query = query.filter(models.Evidence.evidence_id.ilike(like) | models.Evidence.original_filename.ilike(like)
                             | models.Evidence.sha256.ilike(like))
    if case_id:
        query = query.filter(models.Case.case_id == case_id)
    if file_type:
        query = query.filter(models.Evidence.detected_type == file_type)
    if integrity:
        query = query.filter(models.Evidence.integrity_status == integrity)
    if date_from:
        query = query.filter(models.Evidence.acquired_at >= date_from)
    if date_to:
        query = query.filter(models.Evidence.acquired_at <= date_to + "T23:59:59")
    if investigator_id:
        query = query.filter(models.Case.investigator_id == investigator_id)
    return [evidence_out(e) for e in query.order_by(models.Evidence.acquired_at.desc()).all()]


@router.get("/evidence/{evidence_id}")
def get_evidence(evidence_id: str, user=Depends(current_user), db: Session = Depends(get_db)):
    ev = get_evidence_or_404(db, evidence_id, user)
    hashes = db.query(models.EvidenceHash).filter_by(evidence_id=ev.id).order_by(models.EvidenceHash.computed_at).all()
    job = db.query(models.AnalysisJob).filter_by(evidence_id=ev.id, status="completed").order_by(models.AnalysisJob.id.desc()).first()
    out = evidence_out(ev)
    out["hash_history"] = [{"value": h.value, "context": h.context, "matches_original": h.matches_original,
                            "computed_at": iso(h.computed_at)} for h in hashes]
    out["last_analysis"] = json.loads(job.result_json) if job else None
    out["last_analysis_at"] = iso(job.finished_at) if job else None
    return out


@router.get("/evidence/{evidence_id}/metadata")
def get_metadata(evidence_id: str, user=Depends(current_user), db: Session = Depends(get_db)):
    ev = get_evidence_or_404(db, evidence_id, user)
    rows = db.query(models.MetadataRecord).filter_by(evidence_id=ev.id).order_by(models.MetadataRecord.id).all()
    records.custody(db, user.username, "accessed", ev.evidence_id, {"view": "metadata"})
    db.commit()
    return {"evidence_id": ev.evidence_id, "limitations": metadata.LIMITATIONS,
            "fields": [{"source": r.source, "key": r.key, "value": r.value} for r in rows]}


@router.post("/evidence/{evidence_id}/verify")
def verify(evidence_id: str, request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    ev = get_evidence_or_404(db, evidence_id, user)
    try:
        res = ops.verify(db, ev, user, "manual", client_ip(request))
    except ops.EvidenceError as exc:
        raise HTTPException(exc.status, str(exc))
    db.commit()
    return res


@router.post("/evidence/{evidence_id}/analyze")
def analyze(evidence_id: str, request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    ev = get_evidence_or_404(db, evidence_id, user, write=True)
    try:
        res = ops.analyze(db, ev, user, client_ip(request))
    except ops.EvidenceError as exc:
        _commit_and_raise(db, exc)
    db.commit()
    return res


class TransferIn(BaseModel):
    to_username: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=3, max_length=500)


@router.post("/evidence/{evidence_id}/transfer")
def transfer(evidence_id: str, body: TransferIn, request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    ev = get_evidence_or_404(db, evidence_id, user, write=True)
    target = db.query(models.User).filter_by(username=body.to_username, is_active=True).first()
    if not target:
        raise HTTPException(422, "Unknown or inactive recipient")
    records.custody(db, user.username, "transferred", ev.evidence_id, {"from": user.username, "to": target.username, "reason": body.reason})
    records.audit(db, user.username, "evidence.transfer", {"evidence_id": ev.evidence_id, "to": target.username}, client_ip(request))
    db.commit()
    return {"ok": True}


class DisposeIn(BaseModel):
    reason: str = Field(min_length=10, max_length=500)
    confirm_evidence_id: str


@router.post("/evidence/{evidence_id}/dispose")
def dispose(evidence_id: str, body: DisposeIn, request: Request, user=Depends(require_admin), db: Session = Depends(get_db)):
    """Retention workflow: removes stored content only when the case is closed and the retention
    period has elapsed. Hashes, findings and the custody ledger are preserved."""
    ev = db.query(models.Evidence).filter_by(evidence_id=evidence_id).first()
    if not ev:
        raise HTTPException(404, "Evidence not found")
    if body.confirm_evidence_id != ev.evidence_id:
        raise HTTPException(422, "Confirmation ID does not match")
    case = ev.case
    days = int(settings_store.get_all(db)["retention_days"])
    if case.status != "closed" or not case.closed_at:
        raise HTTPException(409, "Case must be closed before evidence can be disposed")
    if utcnow() < case.closed_at + timedelta(days=days):
        raise HTTPException(409, f"Retention period of {days} days has not elapsed (until {iso(case.closed_at + timedelta(days=days))})")
    if ev.integrity_status == "disposed":
        raise HTTPException(409, "Already disposed")
    path = ops.stored_file(ev)
    try:
        path.chmod(0o600)
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise HTTPException(500, f"Could not remove file: {exc.__class__.__name__}")
    ev.integrity_status = "disposed"
    records.custody(db, user.username, "disposed", ev.evidence_id, {"reason": body.reason, "sha256_retained": ev.sha256})
    records.audit(db, user.username, "evidence.dispose", {"evidence_id": ev.evidence_id, "reason": body.reason}, client_ip(request))
    db.commit()
    return {"ok": True, "evidence_id": ev.evidence_id, "status": "disposed"}
