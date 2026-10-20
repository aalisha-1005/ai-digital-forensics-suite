from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import client_ip, current_user, get_case_or_404, is_admin
from ..models import utcnow
from ..serializers import case_out
from ..services import records
from ..services.evidence_ops import next_id

router = APIRouter(prefix="/api/cases", tags=["cases"])
PRIORITIES = "^(low|medium|high|critical)$"
STATUSES = "^(open|in_review|closed)$"


class CaseIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=5000)
    priority: str = Field(default="medium", pattern=PRIORITIES)
    investigator_id: int | None = None


class CasePatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    priority: str | None = Field(default=None, pattern=PRIORITIES)
    status: str | None = Field(default=None, pattern=STATUSES)
    investigator_id: int | None = None


def _counts(db, c):
    ev = db.query(func.count(models.Evidence.id)).filter_by(case_id=c.id).scalar()
    pend = db.query(func.count(models.Finding.id)).filter_by(case_id=c.id, review_status="pending").scalar()
    return case_out(c, ev, pend)


def scoped_cases(db, user):
    q = db.query(models.Case)
    return q if is_admin(user) else q.filter(models.Case.investigator_id == user.id)


@router.get("")
def list_cases(q: str = "", status: str = "", priority: str = "", investigator_id: int | None = None,
               date_from: str = "", date_to: str = "", user=Depends(current_user), db: Session = Depends(get_db)):
    query = scoped_cases(db, user)
    if q:
        like = f"%{q.strip()[:100]}%"
        query = query.filter(or_(models.Case.case_id.ilike(like), models.Case.title.ilike(like), models.Case.description.ilike(like)))
    if status:
        query = query.filter(models.Case.status == status)
    if priority:
        query = query.filter(models.Case.priority == priority)
    if investigator_id:
        query = query.filter(models.Case.investigator_id == investigator_id)
    if date_from:
        query = query.filter(models.Case.created_at >= date_from)
    if date_to:
        query = query.filter(models.Case.created_at <= date_to + "T23:59:59")
    return [_counts(db, c) for c in query.order_by(models.Case.created_at.desc()).all()]


@router.post("", status_code=201)
def create_case(body: CaseIn, request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    inv = body.investigator_id if (is_admin(user) and body.investigator_id) else user.id
    if not db.get(models.User, inv):
        raise HTTPException(422, "Unknown investigator")
    c = models.Case(case_id=next_id(db, models.Case, None, "CASE"), title=body.title, description=body.description,
                    priority=body.priority, investigator_id=inv)
    db.add(c)
    db.flush()
    records.audit(db, user.username, "case.create", {"case": c.case_id}, client_ip(request))
    records.notify(db, "case_update", f"Case {c.case_id} created", c.id)
    db.commit()
    db.refresh(c)
    return _counts(db, c)


@router.get("/{case_id}")
def get_case(case_id: str, user=Depends(current_user), db: Session = Depends(get_db)):
    return _counts(db, get_case_or_404(db, case_id, user))


@router.patch("/{case_id}")
def update_case(case_id: str, body: CasePatch, request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    c = get_case_or_404(db, case_id, user)
    data = body.model_dump(exclude_unset=True)
    if c.status == "closed" and not (is_admin(user) and data.get("status") in ("open", "in_review")):
        raise HTTPException(409, "Closed cases can only be reopened by an administrator")
    if "investigator_id" in data:
        if not is_admin(user):
            raise HTTPException(403, "Only administrators can assign cases")
        if data["investigator_id"] and not db.get(models.User, data["investigator_id"]):
            raise HTTPException(422, "Unknown investigator")
    if data.get("status") == "closed":
        pending = db.query(models.Finding).filter_by(case_id=c.id, review_status="pending").count()
        if pending:
            raise HTTPException(409, f"{pending} finding(s) still await investigator review; review them before closing")
        c.closed_at = utcnow()
    elif data.get("status"):
        c.closed_at = None
    for k, v in data.items():
        setattr(c, k, v)
    records.audit(db, user.username, "case.update", {"case": c.case_id, "fields": list(data)}, client_ip(request))
    records.notify(db, "case_update", f"Case {c.case_id} updated ({', '.join(data)})", c.id)
    db.commit()
    db.refresh(c)
    return _counts(db, c)
