import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DFIS_DATA_DIR", BASE_DIR / "data")).resolve()
ORIGINALS_DIR = DATA_DIR / "evidence" / "originals"
WORKING_DIR = DATA_DIR / "evidence" / "working"
EXPORT_DIR = DATA_DIR / "exports"
MODEL_DIR = DATA_DIR / "models"
DATABASE_URL = os.getenv("DFIS_DATABASE_URL", f"sqlite:///{DATA_DIR / 'dfis.db'}")
SESSION_HOURS = int(os.getenv("DFIS_SESSION_HOURS", "8"))
COOKIE_SECURE = os.getenv("DFIS_COOKIE_SECURE", "false").lower() == "true"  # set true behind HTTPS
CORS_ORIGINS = [o for o in os.getenv("DFIS_CORS_ORIGINS", "http://localhost:5173").split(",") if o]
DEFAULT_MAX_UPLOAD_MB = int(os.getenv("DFIS_MAX_UPLOAD_MB", "25"))
LOGIN_MAX_ATTEMPTS = int(os.getenv("DFIS_LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_WINDOW_SECONDS = int(os.getenv("DFIS_LOGIN_WINDOW_SECONDS", "300"))
DEFAULT_FORMATS = "txt,log,csv,json,md,pdf,png,jpg,jpeg,gif,bmp,tiff,docx,xlsx,pptx,eml,zip,exe,bin"
DEFAULT_RETENTION_DAYS = 365

for d in (ORIGINALS_DIR, WORKING_DIR, EXPORT_DIR, MODEL_DIR):
    d.mkdir(parents=True, exist_ok=True)
