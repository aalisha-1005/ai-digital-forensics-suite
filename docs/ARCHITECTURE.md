# Architecture

```
 Browser (React + Vite + TS + Tailwind + Recharts)
        |  JSON over HTTPS/HTTP, HttpOnly session cookie + X-CSRF-Token
        v
 FastAPI (app/main.py)  ── routers: auth · cases · evidence · workspace · system
        |                    deps.py: session, CSRF, RBAC, per-case access checks
        v
 services/ (framework-free, unit-tested)
   hashing · signatures · metadata · rules · ml · timeline · ledger · reports
   evidence_ops (ingest / verify / analyze) · records (audit + custody ledgers)
        |
        +--> SQLite via SQLAlchemy (models.py, migrations.py)
        +--> data/evidence/originals/<EV-id>/<uuid>.bin   (chmod 0444, never modified)
        +--> data/evidence/working/<EV-id>/job<N>.work     (0600, deleted after analysis)
        +--> data/models/model.joblib + model_card.json    (local, synthetic training)
        +--> data/exports/*.pdf|csv
```

Analysis flow: verify original hash → copy to working area → static inspection of the copy → local model inference →
re-verify original hash → persist metadata/timeline/findings → append custody + audit entries → delete working copy.
