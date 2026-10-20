import json
from .models import iso


def user_out(u):
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role.name,
            "is_active": u.is_active, "created_at": iso(u.created_at)}


def case_out(c, evidence_count=0, pending=0):
    return {"id": c.id, "case_id": c.case_id, "title": c.title, "description": c.description,
            "investigator_id": c.investigator_id, "investigator": c.investigator.full_name if c.investigator else None,
            "priority": c.priority, "status": c.status, "is_synthetic": c.is_synthetic,
            "created_at": iso(c.created_at), "updated_at": iso(c.updated_at), "closed_at": iso(c.closed_at),
            "evidence_count": evidence_count, "pending_reviews": pending}


def evidence_out(e):
    return {"id": e.id, "evidence_id": e.evidence_id, "case_id": e.case.case_id, "original_filename": e.original_filename,
            "size_bytes": e.size_bytes, "mime_type": e.mime_type, "declared_mime": e.declared_mime,
            "detected_type": e.detected_type, "source_description": e.source_description,
            "uploader": e.uploader.username, "acquired_at": iso(e.acquired_at), "sha256": e.sha256,
            "integrity_status": e.integrity_status, "is_synthetic": e.is_synthetic}


def finding_out(f, evidence_ref, case_ref, reviewer=None):
    return {"id": f.id, "case_id": case_ref, "evidence_id": evidence_ref, "category": f.category, "title": f.title,
            "description": f.description, "origin": f.origin, "confidence": f.confidence,
            "details": json.loads(f.details_json or "{}"), "review_status": f.review_status,
            "analyst_interpretation": f.analyst_interpretation, "reviewed_by": reviewer,
            "reviewed_at": iso(f.reviewed_at), "created_at": iso(f.created_at)}


def ledger_out(r, ref_attr=None):
    d = {"seq": r.seq, "timestamp_utc": iso(r.timestamp), "actor": r.actor, "action": r.action,
         "details": json.loads(r.details or "{}"), "prev_hash": r.prev_hash, "entry_hash": r.entry_hash}
    if ref_attr:
        d["evidence_id"] = getattr(r, ref_attr)
    return d
