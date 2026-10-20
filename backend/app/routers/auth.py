from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import config, models
from ..database import get_db
from ..deps import COOKIE, client_ip, current_session, current_user
from ..models import utcnow
from ..security import login_limiter, new_token, token_digest, verify_password
from ..serializers import user_out
from ..services import records

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    key = f"{client_ip(request)}|{body.username.lower()}"
    if login_limiter.blocked(key):
        records.audit(db, body.username[:64], "auth.login_blocked", {}, client_ip(request))
        db.commit()
        raise HTTPException(429, "Too many failed attempts. Try again later.")
    user = db.query(models.User).filter_by(username=body.username).first()
    # always run a verification to keep timing similar for unknown users
    ok = verify_password(body.password, user.password_hash if user else "scrypt$16384$8$1$00$00")
    if not (user and ok and user.is_active):
        login_limiter.record_failure(key)
        records.audit(db, body.username[:64], "auth.login_failed", {}, client_ip(request))
        db.commit()
        raise HTTPException(401, "Invalid credentials")
    login_limiter.reset(key)
    token, csrf = new_token(), new_token()
    db.add(models.UserSession(token_digest=token_digest(token), csrf_token=csrf, user_id=user.id,
                              expires_at=utcnow() + timedelta(hours=config.SESSION_HOURS)))
    records.audit(db, user.username, "auth.login", {}, client_ip(request))
    db.commit()
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=config.COOKIE_SECURE,
                        max_age=config.SESSION_HOURS * 3600, path="/")
    return {"user": user_out(user), "csrf_token": csrf}


@router.post("/logout")
def logout(request: Request, response: Response, s=Depends(current_session), db: Session = Depends(get_db),
           user=Depends(current_user)):
    db.delete(s)
    records.audit(db, user.username, "auth.logout", {}, client_ip(request))
    db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user=Depends(current_user), s=Depends(current_session)):
    return {"user": user_out(user), "csrf_token": s.csrf_token}
