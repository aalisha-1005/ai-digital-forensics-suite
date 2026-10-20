"""Timeline construction: normalise to UTC, keep provenance, flag conflicts and gaps."""
from datetime import datetime, timezone


def to_utc(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip()
        # PDF style D:YYYYMMDDHHmmSS
        if s.startswith("D:") and len(s) >= 16 and s[2:16].isdigit():
            s = f"{s[2:6]}-{s[6:8]}-{s[8:10]}T{s[10:12]}:{s[12:14]}:{s[14:16]}"
        elif len(s) >= 19 and s[4] == ":" and s[7] == ":":  # EXIF "YYYY:MM:DD HH:MM:SS"
            s = s[:4] + "-" + s[5:7] + "-" + s[8:10] + "T" + s[11:19]
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


TIME_KEYS = {"modified_time": "File modified", "changed_time": "File metadata changed", "created": "Document created",
             "modified": "Document modified", "creationdate": "PDF created", "moddate": "PDF modified",
             "datetimeoriginal": "Photo taken (EXIF)", "datetime": "Image datetime (EXIF)",
             "datetimedigitized": "Image digitized (EXIF)"}


def events_from_metadata(fields: list[dict]) -> list[dict]:
    out = []
    for f in fields:
        label = TIME_KEYS.get(f["key"].lower())
        if not label:
            continue
        dt = to_utc(f["value"])
        if dt:
            out.append({"timestamp": dt, "title": label, "source": f"metadata:{f['source']}",
                        "provenance": "automated extraction (self-reported, alterable)"})
    return out


def detect_conflicts(events: list[dict]) -> list[str]:
    notes = []
    by = {e["title"]: e["timestamp"] for e in events if e.get("timestamp")}
    now = datetime.now(timezone.utc)
    if "Document created" in by and "Document modified" in by and by["Document modified"] < by["Document created"]:
        notes.append("Document modified time precedes its created time.")
    if "PDF created" in by and "PDF modified" in by and by["PDF modified"] < by["PDF created"]:
        notes.append("PDF modification date precedes its creation date.")
    for e in events:
        if e.get("timestamp") and e["timestamp"] > now:
            notes.append(f"'{e['title']}' is in the future ({e['timestamp'].isoformat()}).")
    return notes
