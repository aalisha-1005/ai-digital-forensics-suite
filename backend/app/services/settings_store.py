from .. import config, models


def defaults() -> dict:
    return {"max_upload_mb": str(config.DEFAULT_MAX_UPLOAD_MB), "allowed_formats": config.DEFAULT_FORMATS,
            "retention_days": str(config.DEFAULT_RETENTION_DAYS)}


def get_all(db) -> dict:
    out = defaults()
    for s in db.query(models.AppSetting).all():
        out[s.key] = s.value
    return out


def set_value(db, key: str, value: str):
    if key not in defaults():
        raise KeyError(key)
    row = db.get(models.AppSetting, key)
    if row:
        row.value = value
    else:
        db.add(models.AppSetting(key=key, value=value))
