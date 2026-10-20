import json
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import client_ip, current_user, get_case_or_404, get_evidence_or_404
from ..models import iso, utcnow
from ..serializers import finding_out, ledger_out
from ..services import records, timeline as tl
from .cases import scoped_cases

router = APIRouter(prefix="/api", tags=["workspace"])
CATS = "^(benign|needs_review|suspicious)$"


@router.get("/findings")
def list_findings(case_id: str = "", evidence_id: str = "", category: str = "", review_status: str = "", origin: str = "",
                  user=Depends(current_user), db: Session = Depends(get_db)):
    ids = [c.id for c in scoped_cases(db, user).all()]
    q = db.query(models.Finding).filter(models.Finding.case_id.in_(ids))
    if case_id:
        q = q.join(models.Case, models.Case.id == models.Finding.case_id).filter(models.Case.case_id == case_id)
    if evidence_id:
        q = q.join(models.Evidence, models.Evidence.id == models.Finding.evidence_id).filter(models.Evidence.evidence_id == evidence_id)
    for col, val in ((models.Finding.category, category), (models.Finding.review_status, review_status), (models.Finding.origin, origin)):
        if val:
            q = q.filter(col == val)
    out = []
    for f in q.order_by(models.Finding.created_at.desc()).all():
        ev, case = db.get(models.Evidence, f.evidence_id), db.get(models.Case, f.case_id)
        rev = db.get(models.User, f.reviewed_by).username if f.reviewed_by else None
        out.append(finding_out(f, ev.evidence_id, case.case_id, rev))
    return out


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^(accepted|rejected)$")
    analyst_interpretation: str = Field(default="", max_length=3000)


@router.post("/findings/{finding_id}/review")
def review(finding_id: int, body: ReviewIn, request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    f = db.get(models.Finding, finding_id)
    if not f:
        raise HTTPException(404, "Finding not found")
    get_case_or_404(db, f.case_id, user, write=True)
    if body.decision == "accepted" and not body.analyst_interpretation.strip():
        raise HTTPException(422, "An analyst interpretation is required to accept a finding as a conclusion")
    f.review_status, f.analyst_interpretation = body.decision, body.analyst_interpretation.strip()
    f.reviewed_by, f.reviewed_at = user.id, utcnow()
    ev = db.get(models.Evidence, f.evidence_id)
    records.custody(db, user.username, "finding_reviewed", ev.evidence_id, {"finding_id": f.id, "decision": body.decision})
    records.audit(db, user.username, "finding.review", {"finding_id": f.id, "decision": body.decision}, client_ip(request))
    db.commit()
    return finding_out(f, ev.evidence_id, db.get(models.Case, f.case_id).case_id, user.username)


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    method: str = Field(default="", max_length=200)
    evidence_id: str | None = None
    finding_id: int | None = None


@router.get("/cases/{case_id}/notes")
def list_notes(case_id: str, user=Depends(current_user), db: Session = Depends(get_db)):
    case = get_case_or_404(db, case_id, user)
    rows = db.query(models.Note).filter_by(case_id=case.id).order_by(models.Note.created_at.desc()).all()
    refs = {e.id: e.evidence_id for e in db.query(models.Evidence).filter_by(case_id=case.id)}
    return [{"id": n.id, "author": n.author.username, "method": n.method, "body": n.body, "created_at": iso(n.created_at),
             "evidence_id": refs.get(n.evidence_id), "finding_id": n.finding_id} for n in rows]


@router.post("/cases/{case_id}/notes", status_code=201)
def add_note(case_id: str, body: NoteIn, request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    case = get_case_or_404(db, case_id, user, write=True)
    ev = get_evidence_or_404(db, body.evidence_id, user) if body.evidence_id else None
    if ev and ev.case_id != case.id:
        raise HTTPException(422, "Evidence belongs to a different case")
    if body.finding_id:
        f = db.get(models.Finding, body.finding_id)
        if not f or f.case_id != case.id:
            raise HTTPException(422, "Finding belongs to a different case")
    n = models.Note(case_id=case.id, evidence_id=ev.id if ev else None, finding_id=body.finding_id, author_id=user.id,
                    method=body.method, body=body.body)
    db.add(n)
    records.audit(db, user.username, "note.add", {"case": case.case_id}, client_ip(request))
    db.commit()
    return {"id": n.id}


@router.get("/cases/{case_id}/timeline")
def get_timeline(case_id: str, q: str = "", evidence_id: str = "", date_from: str = "", date_to: str = "",
                 user=Depends(current_user), db: Session = Depends(get_db)):
    case = get_case_or_404(db, case_id, user)
    evs = {e.id: e.evidence_id for e in db.query(models.Evidence).filter_by(case_id=case.id)}
    items = [{"timestamp_utc": iso(t.timestamp), "title": t.title, "source": t.source, "provenance": t.provenance,
              "evidence_id": evs.get(t.evidence_id), "id": f"t{t.id}"}
             for t in db.query(models.TimelineEvent).filter_by(case_id=case.id)]
    for c in db.query(models.CustodyEvent).filter(models.CustodyEvent.evidence_ref.in_(list(evs.values()))):
        items.append({"timestamp_utc": iso(c.timestamp), "title": f"Custody: {c.action}", "source": "case_activity",
                      "provenance": f"ledger entry #{c.seq} by {c.actor}", "evidence_id": c.evidence_ref, "id": f"c{c.id}"})
    items.append({"timestamp_utc": iso(case.created_at), "title": "Case created", "source": "case_activity",
                  "provenance": "recorded by system", "evidence_id": None, "id": "case"})
    if q:
        ql = q.lower()
        items = [i for i in items if ql in i["title"].lower() or ql in i["source"].lower() or ql in i["provenance"].lower()]
    if evidence_id:
        items = [i for i in items if i["evidence_id"] == evidence_id]
    if date_from:
        items = [i for i in items if i["timestamp_utc"] >= date_from]
    if date_to:
        items = [i for i in items if i["timestamp_utc"] <= date_to + "T23:59:59Z"]
    items.sort(key=lambda i: i["timestamp_utc"])
    parsed = [{"title": i["title"], "timestamp": tl.to_utc(i["timestamp_utc"])} for i in items if i["source"].startswith("metadata")]
    notes = tl.detect_conflicts(parsed)
    for e in db.query(models.Evidence).filter_by(case_id=case.id):
        if e.integrity_status != "disposed" and not any(i["evidence_id"] == e.evidence_id and i["source"].startswith("metadata") for i in items):
            notes.append(f"{e.evidence_id}: no embedded or filesystem timestamps available (analysis not run or metadata stripped).")
    return {"events": items, "notes": notes,
            "note": "All times are stored in UTC. Metadata-derived events are self-reported and may be altered."}


class EventIn(BaseModel):
    timestamp: str
    title: str = Field(min_length=3, max_length=200)
    evidence_id: str | None = None


@router.post("/cases/{case_id}/timeline", status_code=201)
def add_event(case_id: str, body: EventIn, request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    case = get_case_or_404(db, case_id, user, write=True)
    dt = tl.to_utc(body.timestamp)
    if not dt:
        raise HTTPException(422, "Unparseable timestamp; use ISO 8601 e.g. 2026-01-31T14:05:00Z")
    ev = get_evidence_or_404(db, body.evidence_id, user) if body.evidence_id else None
    db.add(models.TimelineEvent(case_id=case.id, evidence_id=ev.id if ev else None, timestamp=dt.replace(tzinfo=None),
                                title=body.title, source="analyst", provenance=f"entered by {user.username}", created_by=user.id))
    records.audit(db, user.username, "timeline.add", {"case": case.case_id}, client_ip(request))
    db.commit()
    return {"ok": True}
