# AI-Based Digital Forensics Investigation Suite (DFIS)

An offline, defensive digital-forensics workstation for **authorized, lawfully obtained** evidence in a controlled
environment. No API keys, no cloud AI, no external auth. Evidence and model processing never leave the machine.

> **Status honesty.** Pure-Python forensic services (hashing, signatures, metadata, rules, ML, timeline, ledger,
> PDF/CSV) have unit tests that pass (`backend/tests/test_services.py`). The FastAPI/SQLAlchemy layer, API
> integration tests (`tests/test_api.py`) and the React frontend were written in a network-less sandbox and have
> **not been executed yet**. Expect to fix small issues on first run; see *Troubleshooting* and *Known limitations*.

## Prerequisites
Python 3.11+, Node 20+ and npm. Optional: libmagic (`python-magic`), Docker.

## Install (online once, then fully offline)
```bash
cd backend && python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd ../frontend && npm install
```
**Offline setup:** on a connected machine run `pip download -r backend/requirements.txt -d wheels` and
`npm ci` (copy `node_modules`), transfer to the air-gapped host, then `pip install --no-index --find-links wheels -r requirements.txt`.

## Database initialisation, demo login and model training
```bash
cd backend
python -m scripts.init_db --admin-user admin --seed-demo
```
* Prompts for the administrator password (12+ chars, mixed case + digit); nothing is hard-coded. For automation set
  `DFIS_ADMIN_PASSWORD` for that one command.
* `--seed-demo` adds clearly labelled **SYNTHETIC** cases/evidence and a `demo_investigator` user whose random
  password is printed once.
* Trains the local model automatically (synthetic data). Retrain: `python -m scripts.train_model`.
* Migrations run automatically at API start (`app/migrations.py`, tracked in `schema_migrations`).

## Run
```bash
cd backend && uvicorn app.main:app --reload --port 8000      # API docs: http://localhost:8000/docs
cd frontend && npm run dev                                   # UI: http://localhost:5173 (proxies /api)
```

## Tests
```bash
cd backend
python -m unittest tests.test_services     # service tests, no web deps
pytest                                     # + API integration tests (needs requirements.txt)
cd ../frontend && npm run build            # type-checks and builds
```

## Docker (optional)
`DFIS_ADMIN_PASSWORD='<strong password>' docker compose up --build` → UI at http://localhost:8080. Add `--seed-demo`
by editing the backend `CMD`. Data lives in the `dfis-data` volume.

## Architecture
See `docs/ARCHITECTURE.md`.

## API (interactive docs at `/docs`)
| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` |
| Cases | `GET/POST /api/cases`, `GET/PATCH /api/cases/{id}`, notes `GET/POST /api/cases/{id}/notes` |
| Evidence | `POST /api/cases/{id}/evidence`, `GET /api/evidence`, `GET /api/evidence/{id}`, `/metadata`, `POST /verify`, `/analyze`, `/transfer`, `/dispose` (admin) |
| Findings | `GET /api/findings`, `POST /api/findings/{id}/review` |
| Timeline | `GET/POST /api/cases/{id}/timeline` |
| Ledgers | `GET /api/custody`, `GET /api/custody/verify`, `GET /api/audit`, `GET /api/audit/verify` (admin) |
| Dashboard | `GET /api/dashboard` (live DB aggregates) |
| Reports | `POST /api/cases/{id}/reports` `{format: pdf|csv}`, `GET /api/reports`, `GET /api/reports/{id}/download` |
| Admin | `GET/PUT /api/settings`, `GET/POST/PATCH /api/users`, `GET /api/model`, `POST /api/model/train`, `GET /api/notifications` |

## Security considerations
* Passwords: scrypt (stdlib) with per-user salt; min 12 chars. Login rate-limited (in-memory, per IP+username).
* Sessions: random token, only its SHA-256 stored; `HttpOnly`, `SameSite=Strict` cookie (`DFIS_COOKIE_SECURE=true` behind HTTPS);
  CSRF via per-session token in `X-CSRF-Token` on all unsafe methods.
* RBAC: administrator vs investigator; investigators only access cases assigned to them.
* Uploads: extension allow-list, size cap (streamed), empty-file rejection, content-signature detection, server-generated storage
  names (user filename is display-only, sanitised), path confinement check, originals `chmod 0444`, analysis on a `0600` copy that is
  deleted afterwards. Uploaded content is **never executed**, macros never run, PDFs never rendered by an active engine.
* Parameterised SQL through SQLAlchemy; OOXML metadata parsed with regex after rejecting DTD/entity declarations; CSV export
  neutralises spreadsheet-formula injection; generic 500 errors; security headers set.
* The model file is a pickle-based joblib artifact: only load models you trained locally.
* `.env`, databases, evidence, exports and model artifacts are git-ignored.

## Evidence and AI limitations
* Metadata is self-reported and alterable; filesystem times of the stored copy reflect upload, not the original device.
* AI classification is a logistic-regression triage aid trained on **synthetic** data; it is not proof of wrongdoing and every
  result requires investigator review. Only accepted findings with a written interpretation appear as analyst conclusions.
* The custody/audit ledgers are hash-linked and tamper-*evident*, not tamper-proof: someone with database access could rewrite
  the whole chain. They provide no independent trusted timestamping and do not replace legally mandated procedures.

## Known limitations (documented, not hidden)
* Not yet run end-to-end in the authoring environment (see status note). Alembic is not used; a small built-in runner is.
* Rate limiter and sessions are single-process; use a reverse proxy/shared store for multi-worker deployments.
* Metadata supports images (Pillow), PDF (PyMuPDF, regex fallback), OOXML and text; legacy `.doc/.xls` get signature + filesystem data only.
* Disposal removes stored content but keeps hashes, findings and ledger entries (preservation); there is no hard-delete of cases.
* No bundled font files: UI uses system fallbacks so it works fully offline.

## Troubleshooting
* `ModuleNotFoundError: app` → run commands from `backend/` (`python -m scripts.init_db`).
* 401/403 after login in dev → use the Vite dev server (proxy keeps cookies same-origin) and keep `DFIS_CORS_ORIGINS` correct.
* `database is locked` → run a single API worker with SQLite.
* PyMuPDF missing → PDF metadata falls back to a regex scan (noted in the output).
