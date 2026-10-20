"""Transparent rule-based indicators + feature extraction. Static, read-only inspection:
nothing is ever executed, opened with an interpreter or rendered by an office suite."""
import math
import re
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from . import signatures

SCRIPT_PATTERNS = [rb"powershell", rb"cmd\.exe", rb"eval\(", rb"base64 -d", rb"wscript\.shell",
                   rb"invoke-expression", rb"/bin/sh", rb"chmod \+x", rb"curl .*\| *sh"]


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in Counter(data).values())


def _read_sample(path, limit=1_000_000) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(limit)


def pdf_active_markers(data: bytes) -> list[str]:
    return [m.decode() for m in (b"/JavaScript", b"/JS", b"/OpenAction", b"/Launch", b"/EmbeddedFile")
            if m in data]


def office_macro(path) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            return any("vbaProject" in n for n in z.namelist())
    except Exception:
        return False


def analyze(path, filename: str, sig: dict, meta_fields: list[dict]) -> dict:
    """Return {indicators: [...], features: {...}}. Each indicator is an automated flag
    with a plain-language reason; none is proof of wrongdoing."""
    data = _read_sample(path)
    size = Path(path).stat().st_size
    entropy = shannon_entropy(data)
    printable = (sum(1 for b in data[:65536] if b in (9, 10, 13) or 32 <= b < 127) / max(1, len(data[:65536])))
    name = filename.lower()
    parts = name.split(".")
    double_ext = len(parts) > 2 and parts[-1] in (signatures.EXECUTABLE_EXT | signatures.SCRIPT_EXT) \
        and parts[-2] in (signatures.TEXT_EXT | {"pdf", "doc", "docx", "jpg", "png", "xls", "xlsx"})
    exec_sig = sig["family"] == "executable"
    macro = sig["detected_type"] in ("docx", "xlsx", "pptx") and office_macro(path)
    pdf_markers = pdf_active_markers(data) if sig["detected_type"] == "pdf" else []
    script_hits = sum(len(re.findall(p, data, re.I)) for p in SCRIPT_PATTERNS) \
        if sig["family"] in ("text", "script") else 0
    keys = {f["key"].lower() for f in meta_fields if f["source"] not in ("filesystem",)}
    metadata_missing = int(sig["family"] in ("image", "pdf", "office") and len(keys) <= 1)
    ts = _timestamp_conflicts(meta_fields)

    ind = []

    def flag(code, severity, reason):
        ind.append({"code": code, "severity": severity, "reason": reason})

    if sig["extension_mismatch"]:
        flag("EXT_MISMATCH", "medium", f"Extension '.{sig['claimed_extension']}' does not match detected "
             f"content type '{sig['detected_type']}'.")
    if double_ext:
        flag("DOUBLE_EXT", "medium", "Filename uses a document-like name followed by an executable/script extension.")
    if exec_sig:
        flag("EXEC_SIGNATURE", "high", "File content carries an executable signature. It was NOT executed.")
    if macro:
        flag("OFFICE_MACRO", "high", "Office container includes a VBA project part. Macros were NOT run.")
    if pdf_markers:
        flag("PDF_ACTIVE_CONTENT", "medium", "PDF contains active-content markers: " + ", ".join(pdf_markers))
    if script_hits:
        flag("SCRIPT_KEYWORDS", "medium", f"{script_hits} command-execution keyword(s) found in text content.")
    if entropy > 7.5 and sig["family"] not in ("image", "archive", "pdf", "office"):
        flag("HIGH_ENTROPY", "low", f"High byte entropy ({entropy:.2f}) may indicate packed or encrypted data.")
    if metadata_missing:
        flag("METADATA_MISSING", "low", "Expected metadata fields are absent (stripped or never recorded).")
    for c in ts:
        flag("TIMESTAMP_ANOMALY", "low", c)

    features = {"log_size": math.log10(size + 1), "entropy": entropy, "printable_ratio": printable,
                "ext_mismatch": int(sig["extension_mismatch"]), "double_ext": int(double_ext),
                "exec_sig": int(exec_sig), "macro": int(macro), "pdf_active": len(pdf_markers),
                "script_hits": min(script_hits, 20), "metadata_missing": metadata_missing,
                "ts_anomaly": len(ts)}
    return {"indicators": ind, "features": features}


def _parse(v):
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _timestamp_conflicts(meta_fields) -> list[str]:
    vals = {f["key"].lower(): _parse(f["value"]) for f in meta_fields}
    out = []
    created, modified = vals.get("created"), vals.get("modified")
    if created and modified and modified < created:
        out.append("Embedded modified time is earlier than created time.")
    now = datetime.now(timezone.utc)
    for k, v in vals.items():
        if v and v > now and k in ("created", "modified", "modified_time"):
            out.append(f"Timestamp '{k}' lies in the future.")
    return out
