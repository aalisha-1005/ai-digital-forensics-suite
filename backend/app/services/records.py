"""DB-backed hash-linked ledgers: audit log and chain of custody."""
import json
import threading

from sqlalchemy import select

from .. import models
from ..models import AuditLog, CustodyEvent, iso, utcnow
from . import ledger

_lock = threading.Lock()


def _payload(row, extra: dict) -> dict:
    return {"seq": row.seq, "timestamp": iso(row.timestamp), "actor": row.actor, "action": row.action,
            "details": row.details, **extra}


def _append(db, model, actor: str, action: str, details: dict, extra: dict):
    with _lock:
        last = db.execute(select(model).order_by(model.seq.desc()).limit(1)).scalar_one_or_none()
        row = model(seq=(last.seq + 1) if last else 1, timestamp=utcnow().replace(microsecond=0), actor=actor,
                    action=action, details=json.dumps(details, sort_keys=True, default=str),
                    prev_hash=last.entry_hash if last else ledger.GENESIS, entry_hash="", **extra)
        row.entry_hash = ledger.compute_hash(row.prev_hash, _payload(row, extra))
        db.add(row)
        db.flush()
        return row


def audit(db, actor: str, action: str, details: dict | None = None, ip: str = ""):
    return _append(db, AuditLog, actor, action, details or {}, {"ip": ip})


def custody(db, actor: str, action: str, evidence_ref: str, details: dict | None = None):
    return _append(db, CustodyEvent, actor, action, details or {}, {"evidence_ref": evidence_ref})


def _verify(db, model, extra_keys: list[str]) -> dict:
    rows = db.execute(select(model).order_by(model.seq)).scalars().all()
    entries = [{"seq": r.seq, "prev_hash": r.prev_hash, "entry_hash": r.entry_hash,
                "payload": _payload(r, {k: getattr(r, k) for k in extra_keys})} for r in rows]
    res = ledger.verify_chain(entries)
    res["disclaimer"] = ledger.DISCLAIMER
    res["total_entries"] = len(entries)
    return res


def verify_audit(db):
    return _verify(db, AuditLog, ["ip"])


def verify_custody(db):
    return _verify(db, CustodyEvent, ["evidence_ref"])


def notify(db, kind: str, message: str, case_id: int | None = None, evidence_ref: str | None = None):
    db.add(models.Notification(kind=kind, message=message[:300], case_id=case_id, evidence_ref=evidence_ref))
