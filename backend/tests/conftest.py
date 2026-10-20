import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="dfis-test-")
os.environ["DFIS_DATA_DIR"] = _tmp
os.environ["DFIS_LOGIN_MAX_ATTEMPTS"] = "3"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app import migrations  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from scripts.init_db import create_user, ensure_roles  # noqa: E402

PW = "Test-Password-123"


@pytest.fixture(scope="session", autouse=True)
def _init():
    migrations.run()
    db = SessionLocal()
    ensure_roles(db)
    create_user(db, "adm", "Admin", PW, "administrator")
    create_user(db, "inv1", "Investigator One", PW, "investigator")
    create_user(db, "inv2", "Investigator Two", PW, "investigator")
    db.close()


def login(username):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": username, "password": PW})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return c


@pytest.fixture()
def admin():
    return login("adm")


@pytest.fixture()
def inv1():
    return login("inv1")


@pytest.fixture()
def inv2():
    return login("inv2")
