import io
import os
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app import config, models
from app.database import SessionLocal
from app.main import app
from tests.conftest import PW, login


def mk_case(c, title="Test case title"):
    r = c.post("/api/cases", json={"title": title, "description": "d", "priority": "high"})
    assert r.status_code == 201, r.text
    return r.json()["case_id"]


def upload(c, case_id, name="note.txt", data=b"hello evidence\n"):
    return c.post(f"/api/cases/{case_id}/evidence", files={"file": (name, io.BytesIO(data), "text/plain")},
                  data={"source_description": "synthetic test"})


def png_bytes():
    b = io.BytesIO()
    im = Image.new("RGB", (4, 4))
    ex = im.getexif(); ex[306] = "2024:01:02 03:04:05"
    im.save(b, "PNG", exif=ex)
    return b.getvalue()


# ---- authentication & authorization ----
def test_login_failure_and_rate_limit():
    c = TestClient(app)
    for _ in range(3):
        assert c.post("/api/auth/login", json={"username": "ratelimited", "password": "x"}).status_code == 401
    assert c.post("/api/auth/login", json={"username": "ratelimited", "password": "x"}).status_code == 429


def test_requires_session_and_csrf(inv1):
    assert TestClient(app).get("/api/cases").status_code == 401
    bad = TestClient(app)
    r = bad.post("/api/auth/login", json={"username": "inv1", "password": PW})
    assert r.status_code == 200
    assert bad.post("/api/cases", json={"title": "No csrf header"}).status_code == 403  # missing X-CSRF-Token


def test_cookie_flags():
    r = TestClient(app).post("/api/auth/login", json={"username": "inv1", "password": PW})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_role_isolation(inv1, inv2, admin):
    cid = mk_case(inv1)
    assert inv2.get(f"/api/cases/{cid}").status_code == 403
    assert inv2.get("/api/audit").status_code == 403
    assert inv1.post("/api/users", json={"username": "x1x1", "full_name": "x", "password": PW, "role": "investigator"}).status_code == 403
    assert admin.get(f"/api/cases/{cid}").status_code == 200
    assert admin.get("/api/audit").status_code == 200


def test_weak_password_rejected(admin):
    r = admin.post("/api/users", json={"username": "weakpw", "full_name": "w", "password": "short", "role": "investigator"})
    assert r.status_code == 422


# ---- uploads, hashing, integrity ----
def test_upload_hash_readonly_and_sanitised_name(inv1):
    cid = mk_case(inv1)
    r = upload(inv1, cid, name="../../etc/passwd.txt", data=b"abc")
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["sha256"] == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert "/" not in j["original_filename"] and ".." not in j["original_filename"]
    db = SessionLocal()
    ev = db.query(models.Evidence).filter_by(evidence_id=j["evidence_id"]).one()
    p = config.ORIGINALS_DIR / ev.stored_path
    assert p.exists() and (os.name == "nt" or not os.access(p, os.X_OK)) and (p.stat().st_mode & 0o222) == 0
    db.close()


def test_upload_validation(inv1, admin):
    cid = mk_case(inv1)
    assert upload(inv1, cid, name="a.xyz").status_code == 415
    assert upload(inv1, cid, name="empty.txt", data=b"").status_code == 400
    assert admin.put("/api/settings", json={"max_upload_mb": 1}).status_code == 200
    assert upload(inv1, cid, name="big.txt", data=b"a" * (1024 * 1024 + 10)).status_code == 413
    admin.put("/api/settings", json={"max_upload_mb": 25})


def test_extension_mismatch_recorded(inv1):
    cid = mk_case(inv1)
    r = upload(inv1, cid, name="photo.pdf", data=png_bytes())
    assert r.status_code == 201 and r.json()["detected_type"] == "png"


def test_tamper_detected_and_analysis_aborted(inv1):
    cid = mk_case(inv1)
    ev = upload(inv1, cid).json()
    assert inv1.post(f"/api/evidence/{ev['evidence_id']}/verify").json()["match"] is True
    db = SessionLocal()
    row = db.query(models.Evidence).filter_by(evidence_id=ev["evidence_id"]).one()
    p = config.ORIGINALS_DIR / row.stored_path
    p.chmod(0o600); p.write_bytes(b"tampered"); db.close()
    assert inv1.post(f"/api/evidence/{ev['evidence_id']}/verify").json()["match"] is False
    assert inv1.get(f"/api/evidence/{ev['evidence_id']}").json()["integrity_status"] == "mismatch"
    assert inv1.post(f"/api/evidence/{ev['evidence_id']}/analyze").status_code == 409
    notes = inv1.get("/api/notifications").json()
    assert any(n["kind"] == "integrity_mismatch" and n["evidence_id"] == ev["evidence_id"] for n in notes)


# ---- analysis, metadata, AI, review ----
def test_analysis_metadata_ai_and_review(inv1):
    cid = mk_case(inv1)
    ev = upload(inv1, cid, name="p.png", data=png_bytes()).json()
    r = inv1.post(f"/api/evidence/{ev['evidence_id']}/analyze")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["pre_integrity"]["match"] and j["post_integrity"]["match"]
    assert j["prediction"]["requires_human_review"] is True
    md = inv1.get(f"/api/evidence/{ev['evidence_id']}/metadata").json()
    assert any(f["key"] == "DateTime" for f in md["fields"]) and md["limitations"]
    tl = inv1.get(f"/api/cases/{cid}/timeline").json()
    assert any("Image datetime" in e["title"] for e in tl["events"])
    fs = inv1.get(f"/api/findings?case_id={cid}").json()
    assert fs and all(f["review_status"] == "pending" for f in fs)
    assert inv1.post(f"/api/cases/{cid}/notes", json={"body": "x"}).status_code == 201
    # cannot close with pending findings
    assert inv1.patch(f"/api/cases/{cid}", json={"status": "closed"}).status_code == 409
    fid = fs[0]["id"]
    assert inv1.post(f"/api/findings/{fid}/review", json={"decision": "accepted"}).status_code == 422
    for f in fs:
        assert inv1.post(f"/api/findings/{f['id']}/review", json={"decision": "accepted", "analyst_interpretation": "Reviewed; consistent."}).status_code == 200
    assert inv1.patch(f"/api/cases/{cid}", json={"status": "closed"}).status_code == 200
    assert upload(inv1, cid).status_code == 409  # closed case rejects new evidence


def test_suspicious_sample_flagged(inv1):
    cid = mk_case(inv1)
    ev = upload(inv1, cid, name="invoice.pdf.exe", data=b"MZ" + b"\0" * 300).json()
    j = inv1.post(f"/api/evidence/{ev['evidence_id']}/analyze").json()
    codes = {i["code"] for i in j["indicators"]}
    assert {"EXEC_SIGNATURE", "DOUBLE_EXT"} <= codes
    assert j["prediction"]["label"] in ("suspicious", "needs_review")


# ---- ledgers ----
def test_custody_and_audit_chain_and_tamper(admin, inv1):
    cid = mk_case(inv1)
    upload(inv1, cid)
    assert inv1.get("/api/custody/verify").json()["valid"] is True
    assert admin.get("/api/audit/verify").json()["valid"] is True
    db = SessionLocal()
    row = db.query(models.CustodyEvent).order_by(models.CustodyEvent.seq).first()
    row.actor = "forged"; db.commit(); db.close()
    res = inv1.get("/api/custody/verify").json()
    assert res["valid"] is False and res["first_broken_seq"] == 1


# ---- reports, dashboard, retention ----
def test_reports_and_dashboard(inv1):
    cid = mk_case(inv1)
    upload(inv1, cid, name="n.txt")
    pdf = inv1.post(f"/api/cases/{cid}/reports", json={"format": "pdf"})
    assert pdf.status_code == 201
    dl = inv1.get(f"/api/reports/{pdf.json()['id']}/download")
    assert dl.status_code == 200 and dl.content.startswith(b"%PDF")
    csv = inv1.post(f"/api/cases/{cid}/reports", json={"format": "csv"}).json()
    assert b"observed" in inv1.get(f"/api/reports/{csv['id']}/download").content
    d = inv1.get("/api/dashboard").json()
    assert d["totals"]["cases"] >= 1 and d["totals"]["evidence"] >= 1


def test_dispose_blocked_until_closed_and_retained(admin, inv1):
    cid = mk_case(inv1)
    ev = upload(inv1, cid).json()
    r = admin.post(f"/api/evidence/{ev['evidence_id']}/dispose", json={"reason": "cleanup after trial", "confirm_evidence_id": ev["evidence_id"]})
    assert r.status_code == 409
    assert inv1.post(f"/api/evidence/{ev['evidence_id']}/dispose", json={"reason": "cleanup after trial", "confirm_evidence_id": ev["evidence_id"]}).status_code == 403
