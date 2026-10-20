from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .models import utcnow
from .security import token_digest

COOKIE = "dfis_session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def current_session(request: Request, db: Session = Depends(get_db)) -> models.UserSession:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Not authenticated")
    s = db.query(models.UserSession).filter_by(token_digest=token_digest(token)).first()
    if not s or s.expires_at < utcnow():
        raise HTTPException(401, "Session expired")
    if request.method not in SAFE_METHODS and request.headers.get("x-csrf-token") != s.csrf_token:
        raise HTTPException(403, "CSRF token missing or invalid")
    return s


def current_user(s: models.UserSession = Depends(current_session), db: Session = Depends(get_db)) -> models.User:
    u = db.get(models.User, s.user_id)
    if not u or not u.is_active:
        raise HTTPException(401, "Account disabled")
    return u


def require_admin(u: models.User = Depends(current_user)) -> models.User:
    if u.role.name != "administrator":
        raise HTTPException(403, "Administrator role required")
    return u


def is_admin(u) -> bool:
    return u.role.name == "administrator"


def get_case_or_404(db, case_pk_or_id, user, write=False) -> models.Case:
    q = db.query(models.Case)
    case = q.filter_by(id=case_pk_or_id).first() if isinstance(case_pk_or_id, int) else q.filter_by(case_id=case_pk_or_id).first()
    if not case:
        raise HTTPException(404, "Case not found")
    if not is_admin(user) and case.investigator_id != user.id:
        raise HTTPException(403, "You are not assigned to this case")
    if write and case.status == "closed":
        raise HTTPException(409, "Case is closed; an administrator must reopen it")
    return case


def get_evidence_or_404(db, evidence_id: str, user, write=False) -> models.Evidence:
    ev = db.query(models.Evidence).filter_by(evidence_id=evidence_id).first()
    if not ev:
        raise HTTPException(404, "Evidence not found")
    get_case_or_404(db, ev.case_id, user, write=write)
    return ev


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""
