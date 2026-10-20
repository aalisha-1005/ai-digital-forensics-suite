import json
import uuid
from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import config, models
from ..database import get_db
from ..deps import client_ip, current_user, get_case_or_404, is_admin, require_admin
from ..models import iso, utcnow
from ..security import hash_password, validate_password_strength
from ..serializers import ledger_out, user_out
from ..services import hashing, ml, records, reports, settings_store
from .cases import scoped_cases

router = APIRouter(prefix="/api", tags=["system"])


# ---------- dashboard (real DB values only) ----------
@router.get("/dashboard")
def dashboard(user=Depends(current_user), db: Session = Depends(get_db)):
    cases = scoped_cases(db, user).all()
    cids = [c.id for c in cases]
    ev = db.query(models.Evidence).filter(models.Evidence.case_id.in_(cids)).all() if cids else []
    fnd = db.query(models.Finding).filter(models.Finding.case_id.in_(cids)).all() if cids else []
    refs = {e.evidence_id for e in ev}
    since = utcnow() - timedelta(days=14)
    cust = db.query(models.CustodyEvent).filter(models.CustodyEvent.evidence_ref.in_(refs), models.CustodyEvent.timestamp >= since).all() if refs else []
    activity = Counter(c.timestamp.strftime("%Y-%m-%d") for c in cust)
    days = [(since + timedelta(days=i + 1)).strftime("%Y-%m-%d") for i in range(14)]
    recent = db.query(models.CustodyEvent).filter(models.CustodyEvent.evidence_ref.in_(refs)).order_by(models.CustodyEvent.seq.desc()).limit(8).all() if refs else []
    return {
        "totals": {"cases": len(cases), "evidence": len(ev),
                   "verified": sum(e.integrity_status == "verified" for e in ev),
                   "mismatches": sum(e.integrity_status == "mismatch" for e in ev),
                   "pending_reviews": sum(f.review_status == "pending" for f in fnd)},
        "case_status": dict(Counter(c.status for c in cases)),
        "evidence_categories": dict(Counter(e.detected_type for e in ev)),
        "activity": [{"date": d, "events": activity.get(d, 0)} for d in days],
        "flagged_findings": dict(Counter(f.category for f in fnd)),
        "recent_activity": [ledger_out(r, "evidence_ref") for r in recent],
    }


# ---------- custody & audit ----------
@router.get("/custody")
def custody(evidence_id: str = "", action: str = "", user=Depends(current_user), db: Session = Depends(get_db)):
    ids = [c.id for c in scoped_cases(db, user).all()]
    refs = [e.evidence_id for e in db.query(models.Evidence).filter(models.Evidence.case_id.in_(ids))] if ids else []
    q = db.query(models.CustodyEvent).filter(models.CustodyEvent.evidence_ref.in_(refs))
    if evidence_id:
        q = q.filter(models.CustodyEvent.evidence_ref == evidence_id)
    if action:
        q = q.filter(models.CustodyEvent.action == action)
    return [ledger_out(r, "evidence_ref") for r in q.order_by(models.CustodyEvent.seq.desc()).limit(500).all()]


@router.get("/custody/verify")
def custody_verify(user=Depends(current_user), db: Session = Depends(get_db)):
    res = records.verify_custody(db)
    records.audit(db, user.username, "custody.verify", {"valid": res["valid"]})
    db.commit()
    return res


@router.get("/audit")
def audit_log(action: str = "", actor: str = "", limit: int = 300, user=Depends(require_admin), db: Session = Depends(get_db)):
    q = db.query(models.AuditLog)
    if action:
        q = q.filter(models.AuditLog.action.ilike(f"%{action[:50]}%"))
    if actor:
        q = q.filter(models.AuditLog.actor == actor)
    return [{**ledger_out(r), "ip": r.ip} for r in q.order_by(models.AuditLog.seq.desc()).limit(min(limit, 1000)).all()]


@router.get("/audit/verify")
def audit_verify(user=Depends(require_admin), db: Session = Depends(get_db)):
    res = records.verify_audit(db)
    records.audit(db, user.username, "audit.verify", {"valid": res["valid"]})
    db.commit()
    return res


# ---------- notifications ----------
@router.get("/notifications")
def notifications(unread_only: bool = False, user=Depends(current_user), db: Session = Depends(get_db)):
    ids = {c.id for c in scoped_cases(db, user).all()}
    q = db.query(models.Notification).order_by(models.Notification.created_at.desc()).limit(100)
    rows = [n for n in q.all() if n.case_id is None or n.case_id in ids]
    if unread_only:
        rows = [n for n in rows if not n.is_read]
    return [{"id": n.id, "kind": n.kind, "message": n.message, "evidence_id": n.evidence_ref, "is_read": n.is_read,
             "created_at": iso(n.created_at)} for n in rows]


@router.post("/notifications/read-all")
def read_all(user=Depends(current_user), db: Session = Depends(get_db)):
    db.query(models.Notification).update({"is_read": True})
    db.commit()
    return {"ok": True}


# ---------- settings & users ----------
@router.get("/settings")
def get_settings(user=Depends(current_user), db: Session = Depends(get_db)):
    return settings_store.get_all(db)


class SettingsIn(BaseModel):
    max_upload_mb: int | None = Field(default=None, ge=1, le=500)
    allowed_formats: str | None = Field(default=None, max_length=300, pattern=r"^[a-z0-9, ]+$")
    retention_days: int | None = Field(default=None, ge=0, le=3650)


@router.put("/settings")
def put_settings(body: SettingsIn, request: Request, user=Depends(require_admin), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_none=True)
    for k, v in data.items():
        settings_store.set_value(db, k, str(v).lower() if k == "allowed_formats" else str(v))
    records.audit(db, user.username, "settings.update", data, client_ip(request))
    db.commit()
    return settings_store.get_all(db)


@router.get("/users")
def list_users(user=Depends(current_user), db: Session = Depends(get_db)):
    users = db.query(models.User).order_by(models.User.username).all()
    return [user_out(u) for u in users] if is_admin(user) else [{"id": u.id, "username": u.username, "full_name": u.full_name} for u in users if u.is_active]


class UserIn(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,64}$")
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(max_length=256)
    role: str = Field(pattern="^(administrator|investigator)$")


@router.post("/users", status_code=201)
def create_user(body: UserIn, request: Request, user=Depends(require_admin), db: Session = Depends(get_db)):
    err = validate_password_strength(body.password)
    if err:
        raise HTTPException(422, err)
    if db.query(models.User).filter_by(username=body.username).first():
        raise HTTPException(409, "Username already exists")
    role = db.query(models.Role).filter_by(name=body.role).one()
    u = models.User(username=body.username, full_name=body.full_name, password_hash=hash_password(body.password), role_id=role.id)
    db.add(u)
    records.audit(db, user.username, "user.create", {"username": body.username, "role": body.role}, client_ip(request))
    db.commit()
    db.refresh(u)
    return user_out(u)


class UserPatch(BaseModel):
    role: str | None = Field(default=None, pattern="^(administrator|investigator)$")
    is_active: bool | None = None
    password: str | None = Field(default=None, max_length=256)


@router.patch("/users/{user_id}")
def patch_user(user_id: int, body: UserPatch, request: Request, admin=Depends(require_admin), db: Session = Depends(get_db)):
    u = db.get(models.User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id and (body.is_active is False or (body.role and body.role != "administrator")):
        raise HTTPException(409, "You cannot disable or demote your own account")
    if body.password:
        err = validate_password_strength(body.password)
        if err:
            raise HTTPException(422, err)
        u.password_hash = hash_password(body.password)
        db.query(models.UserSession).filter_by(user_id=u.id).delete()
    if body.role:
        u.role_id = db.query(models.Role).filter_by(name=body.role).one().id
    if body.is_active is not None:
        u.is_active = body.is_active
        if not body.is_active:
            db.query(models.UserSession).filter_by(user_id=u.id).delete()
    records.audit(db, admin.username, "user.update", {"username": u.username, "fields": [k for k, v in body.model_dump().items() if v is not None and k != "password"] + (["password"] if body.password else [])}, client_ip(request))
    db.commit()
    db.refresh(u)
    return user_out(u)


# ---------- reports ----------
class ReportIn(BaseModel):
    format: str = Field(pattern="^(pdf|csv)$")


def _report_data(db, case, user) -> dict:
    evs = db.query(models.Evidence).filter_by(case_id=case.id).all()
    refs = [e.evidence_id for e in evs]
    emap = {e.id: e.evidence_id for e in evs}
    ev_out = []
    for e in evs:
        hs = db.query(models.EvidenceHash).filter_by(evidence_id=e.id).order_by(models.EvidenceHash.computed_at).all()
        md = db.query(models.MetadataRecord).filter_by(evidence_id=e.id).all()
        ev_out.append({"evidence_id": e.evidence_id, "original_filename": e.original_filename, "size_bytes": e.size_bytes,
                       "acquired_at": iso(e.acquired_at), "sha256": e.sha256, "integrity_status": e.integrity_status,
                       "verifications": [{"timestamp_utc": iso(h.computed_at), "result": f"{h.context}: {'match' if h.matches_original else 'MISMATCH'}"} for h in hs],
                       "metadata": [{"source": m.source, "key": m.key, "value": m.value} for m in md]})
    findings = []
    for f in db.query(models.Finding).filter_by(case_id=case.id).all():
        findings.append({"evidence_id": emap.get(f.evidence_id, ""), "category": f.category, "title": f.title, "description": f.description,
                         "confidence": f.confidence, "review_status": f.review_status, "analyst_interpretation": f.analyst_interpretation,
                         "reviewed_by": db.get(models.User, f.reviewed_by).username if f.reviewed_by else None})
    tlines = sorted([{"timestamp_utc": iso(t.timestamp), "title": t.title, "provenance": f"{t.source}; {t.provenance}",
                      "evidence_id": emap.get(t.evidence_id, "")} for t in db.query(models.TimelineEvent).filter_by(case_id=case.id)],
                    key=lambda x: x["timestamp_utc"])
    from ..services import timeline as tl
    notes = tl.detect_conflicts([{"title": t["title"], "timestamp": tl.to_utc(t["timestamp_utc"])} for t in tlines if t["provenance"].startswith("metadata")])
    cust = db.query(models.CustodyEvent).filter(models.CustodyEvent.evidence_ref.in_(refs)).order_by(models.CustodyEvent.seq).all() if refs else []
    ver = records.verify_custody(db)
    return {"generated_by": user.username,
            "case": {"case_id": case.case_id, "title": case.title, "description": case.description, "status": case.status, "priority": case.priority},
            "evidence": ev_out, "findings": findings, "timeline": tlines, "timeline_notes": notes,
            "notes": [{"created_at": iso(n.created_at), "author": n.author.username, "method": n.method, "body": n.body}
                      for n in db.query(models.Note).filter_by(case_id=case.id).order_by(models.Note.created_at)],
            "custody": [{"timestamp_utc": iso(c.timestamp), "evidence_id": c.evidence_ref, "action": c.action, "actor": c.actor, "details": c.details} for c in cust],
            "custody_verification": f"Ledger verification at generation: {ver['reason']} ({ver['total_entries']} entries). {ver['disclaimer']}"}


@router.post("/cases/{case_id}/reports", status_code=201)
def make_report(case_id: str, body: ReportIn, request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    case = get_case_or_404(db, case_id, user)
    data = _report_data(db, case, user)
    blob = reports.build_pdf(data) if body.format == "pdf" else reports.build_csv(data)
    name = f"{case.case_id}_{utcnow().strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:6]}.{body.format}"
    (config.EXPORT_DIR / name).write_bytes(blob)
    r = models.ReportExport(case_id=case.id, format=body.format, filename=name, sha256=hashing.sha256_bytes(blob), generated_by=user.id)
    db.add(r)
    for e in data["evidence"]:
        records.custody(db, user.username, "exported", e["evidence_id"], {"report": name, "format": body.format})
    records.audit(db, user.username, "report.generate", {"case": case.case_id, "format": body.format}, client_ip(request))
    db.commit()
    return {"id": r.id, "filename": name, "format": body.format, "sha256": r.sha256, "generated_at": iso(r.generated_at)}


@router.get("/reports")
def list_reports(user=Depends(current_user), db: Session = Depends(get_db)):
    ids = {c.id: c.case_id for c in scoped_cases(db, user).all()}
    rows = db.query(models.ReportExport).filter(models.ReportExport.case_id.in_(list(ids))).order_by(models.ReportExport.generated_at.desc()).all() if ids else []
    return [{"id": r.id, "case_id": ids[r.case_id], "format": r.format, "filename": r.filename, "sha256": r.sha256,
             "generated_at": iso(r.generated_at)} for r in rows]


@router.get("/reports/{report_id}/download")
def download_report(report_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(models.ReportExport, report_id)
    if not r:
        raise HTTPException(404, "Report not found")
    get_case_or_404(db, r.case_id, user)
    path = (config.EXPORT_DIR / r.filename).resolve()
    if config.EXPORT_DIR.resolve() not in path.parents or not path.exists():
        raise HTTPException(404, "Report file missing")
    return FileResponse(path, filename=r.filename, media_type="application/pdf" if r.format == "pdf" else "text/csv")


# ---------- model ----------
@router.get("/model")
def model_info(user=Depends(current_user)):
    return ml.load_card(config.MODEL_DIR) or {"version": None, "note": "Model not trained yet. An administrator can train it locally."}


@router.post("/model/train")
def model_train(request: Request, user=Depends(require_admin), db: Session = Depends(get_db)):
    card = ml.train(config.MODEL_DIR)
    records.audit(db, user.username, "model.train", {"accuracy": card["holdout_accuracy"]}, client_ip(request))
    db.commit()
    return card
