"""Evidence ingestion, integrity verification and read-only analysis workflow."""
import json
import os
import shutil
import uuid
from pathlib import Path

from sqlalchemy import func, select

from .. import config, models
from ..models import iso, utcnow
from ..security import safe_display_name
from . import hashing, metadata, ml, records, reports, rules, settings_store, signatures, timeline


class EvidenceError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def next_id(db, model, column, prefix: str) -> str:
    n = db.execute(select(func.coalesce(func.max(model.id), 0))).scalar_one() + 1
    return f"{prefix}-{n:04d}"


def stored_file(ev) -> Path:
    """Resolve and confine the stored path to ORIGINALS_DIR (path traversal guard)."""
    p = (config.ORIGINALS_DIR / ev.stored_path).resolve()
    if config.ORIGINALS_DIR.resolve() not in p.parents:
        raise EvidenceError("Invalid stored path", 500)
    return p


def ingest(db, case, user, tmp_path: Path, original_filename: str, declared_mime: str, source: str,
           is_synthetic=False, ip="") -> models.Evidence:
    settings = settings_store.get_all(db)
    name = safe_display_name(original_filename)
    ext = signatures.extension_of(name)
    allowed = {e.strip().lower() for e in settings["allowed_formats"].split(",") if e.strip()}
    size = tmp_path.stat().st_size
    if size == 0:
        raise EvidenceError("Empty files cannot be registered as evidence.")
    if size > int(settings["max_upload_mb"]) * 1024 * 1024:
        raise EvidenceError(f"File exceeds the configured limit of {settings['max_upload_mb']} MB.", 413)
    if ext not in allowed:
        raise EvidenceError(f"File extension '.{ext}' is not in the supported formats list.", 415)
    sig = signatures.detect(tmp_path, name)
    ev_id = next_id(db, models.Evidence, None, "EV")
    folder = config.ORIGINALS_DIR / ev_id
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{uuid.uuid4().hex}.bin"  # server-generated name: user input never touches the path
    shutil.move(str(tmp_path), dest)
    os.chmod(dest, 0o444)  # preserve original read-only
    digest = hashing.sha256_file(dest)
    ev = models.Evidence(evidence_id=ev_id, case_id=case.id, original_filename=name, stored_path=f"{ev_id}/{dest.name}",
                         size_bytes=size, mime_type=sig["detected_mime"], declared_mime=(declared_mime or "")[:128],
                         detected_type=sig["detected_type"], source_description=source[:2000], uploader_id=user.id,
                         acquired_at=utcnow().replace(microsecond=0), sha256=digest, integrity_status="verified",
                         is_synthetic=is_synthetic)
    db.add(ev)
    db.flush()
    db.add(models.EvidenceHash(evidence_id=ev.id, value=digest, context="acquisition", matches_original=True,
                               computed_by=user.id))
    db.add(models.TimelineEvent(case_id=case.id, evidence_id=ev.id, timestamp=ev.acquired_at, title="Evidence acquired",
                                source="case_activity", provenance="recorded by system at acquisition", created_by=user.id))
    records.custody(db, user.username, "registered", ev_id, {"sha256": digest, "filename": name, "size": size,
                                                            "source": source[:200], "signature_mismatch": sig["extension_mismatch"]})
    records.audit(db, user.username, "evidence.upload", {"evidence_id": ev_id, "case": case.case_id}, ip)
    records.notify(db, "evidence_uploaded", f"{ev_id} ({name}) registered in {case.case_id}", case.id, ev_id)
    return ev


def verify(db, ev, user, context="manual", ip="") -> dict:
    if ev.integrity_status == "disposed":
        raise EvidenceError("Evidence content was disposed under the retention workflow.", 409)
    ok, actual = hashing.verify_file(stored_file(ev), ev.sha256)
    db.add(models.EvidenceHash(evidence_id=ev.id, value=actual, context=context, matches_original=ok, computed_by=user.id))
    ev.integrity_status = "verified" if ok else "mismatch"
    records.custody(db, user.username, "hash_verified" if ok else "hash_MISMATCH", ev.evidence_id,
                    {"context": context, "expected": ev.sha256, "actual": actual})
    if not ok:
        records.notify(db, "integrity_mismatch", f"INTEGRITY MISMATCH on {ev.evidence_id}: stored copy differs from acquisition hash",
                       ev.case_id, ev.evidence_id)
        records.audit(db, user.username, "evidence.integrity_mismatch", {"evidence_id": ev.evidence_id}, ip)
    return {"evidence_id": ev.evidence_id, "match": ok, "expected": ev.sha256, "actual": actual, "context": context,
            "verified_at": iso(utcnow())}


SEVERITY_CATEGORY = {"high": "suspicious", "medium": "needs_review", "low": "needs_review"}


def analyze(db, ev, user, ip="") -> dict:
    """1) verify original  2) copy to working area  3) inspect copy (never execute)  4) re-verify original."""
    pre = verify(db, ev, user, "pre_analysis", ip)
    job = models.AnalysisJob(evidence_id=ev.id, requested_by=user.id, tool_versions=json.dumps(reports.tool_versions()))
    db.add(job)
    db.flush()
    if not pre["match"]:
        job.status, job.finished_at = "aborted", utcnow()
        job.result_json = json.dumps({"reason": "pre-analysis integrity mismatch"})
        raise EvidenceError("Analysis aborted: integrity mismatch detected before analysis.", 409)
    work_dir = config.WORKING_DIR / ev.evidence_id
    work_dir.mkdir(parents=True, exist_ok=True)
    work = work_dir / f"job{job.id}.work"
    shutil.copyfile(stored_file(ev), work)
    os.chmod(work, 0o600)  # never executable
    try:
        sig = signatures.detect(work, ev.original_filename)
        fields = metadata.extract(work, sig["detected_type"])
        res = rules.analyze(work, ev.original_filename, sig, fields)
        pred = ml.predict(config.MODEL_DIR, res["features"])
        excerpt = metadata.text_excerpt(work, sig["detected_type"])
    finally:
        work.unlink(missing_ok=True)
    post = verify(db, ev, user, "post_analysis", ip)

    # persist: metadata (latest set), timeline, findings
    db.query(models.MetadataRecord).filter_by(evidence_id=ev.id).delete()
    for f in fields:
        db.add(models.MetadataRecord(evidence_id=ev.id, job_id=job.id, source=f["source"], key=f["key"], value=f["value"]))
    existing = {(t.timestamp, t.title, t.source) for t in db.query(models.TimelineEvent).filter_by(evidence_id=ev.id)}
    for e in timeline.events_from_metadata(fields):
        src = e["source"]
        prov = ("server filesystem time of the stored copy; reflects upload, not the original device"
                if src == "metadata:filesystem" else e["provenance"])
        key = (e["timestamp"].replace(tzinfo=None), e["title"], src)
        if key not in existing:
            db.add(models.TimelineEvent(case_id=ev.case_id, evidence_id=ev.id, timestamp=key[0], title=e["title"],
                                        source=src, provenance=prov, created_by=user.id))
    db.query(models.Finding).filter(models.Finding.evidence_id == ev.id, models.Finding.review_status == "pending",
                                    models.Finding.origin != "analyst").delete()
    db.add(models.Finding(case_id=ev.case_id, evidence_id=ev.id, category=pred["label"], origin="ai_model",
                          title=f"AI triage: {pred['label'].replace('_', ' ')}", confidence=pred["confidence"],
                          description="Local model classification from static features. Triage aid only; requires human review.",
                          details_json=json.dumps({"top_features": pred["top_features"], "probabilities": pred["probabilities"],
                                                   "model_version": pred["model_version"], "limitations": pred["limitations"]})))
    for i in res["indicators"]:
        db.add(models.Finding(case_id=ev.case_id, evidence_id=ev.id, category=SEVERITY_CATEGORY[i["severity"]],
                              origin="automated_rule", title=i["code"], description=i["reason"],
                              details_json=json.dumps({"severity": i["severity"]})))
    job.status, job.finished_at = "completed", utcnow()
    job.result_json = json.dumps({"signature": sig, "indicators": res["indicators"], "features": res["features"],
                                  "prediction": pred, "text_excerpt": excerpt, "post_integrity_match": post["match"],
                                  "metadata_limitations": metadata.LIMITATIONS})
    records.custody(db, user.username, "analyzed", ev.evidence_id, {"job_id": job.id, "indicators": len(res["indicators"]),
                                                                  "ai_label": pred["label"]})
    records.audit(db, user.username, "evidence.analyze", {"evidence_id": ev.evidence_id, "job": job.id}, ip)
    records.notify(db, "pending_review", f"{ev.evidence_id}: {len(res['indicators']) + 1} automated finding(s) await review",
                   ev.case_id, ev.evidence_id)
    if not post["match"]:
        raise EvidenceError("Integrity mismatch detected AFTER analysis; results flagged.", 409)
    return {"job_id": job.id, "signature": sig, "indicators": res["indicators"], "prediction": pred,
            "pre_integrity": pre, "post_integrity": post, "text_excerpt": excerpt}
