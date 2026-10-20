"""Read-only metadata extraction. Every field carries a provenance label and the
caller should always display LIMITATIONS: metadata is easily altered or stripped."""
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

LIMITATIONS = (
    "Metadata is self-reported by the file or the filesystem and can be edited, stripped or "
    "forged. Filesystem timestamps of a re-uploaded copy describe the working environment, "
    "not the original device. Treat all values as leads for corroboration, not proof."
)


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _field(source, key, value):
    return {"source": source, "key": key, "value": str(value)[:500]}


def filesystem(path) -> list[dict]:
    st = Path(path).stat()
    return [_field("filesystem", "size_bytes", st.st_size),
            _field("filesystem", "modified_time", _iso(st.st_mtime)),
            _field("filesystem", "changed_time", _iso(st.st_ctime))]


def image(path) -> list[dict]:
    out = []
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        with Image.open(path) as im:
            out += [_field("image", "format", im.format), _field("image", "dimensions", f"{im.width}x{im.height}"),
                    _field("image", "mode", im.mode)]
            exif = im.getexif()
            for tag_id, val in exif.items():
                name = TAGS.get(tag_id, f"tag_{tag_id}")
                if isinstance(val, bytes):
                    val = val[:40].hex()
                out.append(_field("exif", name, val))
            if not len(exif):
                out.append(_field("exif", "note", "No EXIF data present (may be stripped or never recorded)"))
    except Exception as exc:
        out.append(_field("image", "error", f"Could not parse image: {type(exc).__name__}"))
    return out


_PDF_KEYS = ("Title", "Author", "Creator", "Producer", "CreationDate", "ModDate", "Subject")


def pdf(path) -> list[dict]:
    out = []
    try:
        import fitz  # PyMuPDF
        with fitz.open(path) as doc:
            out.append(_field("pdf", "page_count", doc.page_count))
            for k, v in (doc.metadata or {}).items():
                if v:
                    out.append(_field("pdf", k, v))
        return out
    except ImportError:
        pass
    except Exception as exc:
        return [_field("pdf", "error", f"PyMuPDF failed: {type(exc).__name__}")]
    # Fallback: shallow regex scan of the Info dictionary (no parsing of active content)
    data = Path(path).read_bytes()[:2_000_000]
    out.append(_field("pdf", "parser", "fallback regex scan (PyMuPDF not installed)"))
    for k in _PDF_KEYS:
        m = re.search(rb"/" + k.encode() + rb"\s*\(([^)]{0,200})\)", data)
        if m:
            out.append(_field("pdf", k, m.group(1).decode("latin-1")))
    out.append(_field("pdf", "page_count", len(re.findall(rb"/Type\s*/Page[^s]", data))))
    return out


_OOXML_MAP = {"dc:title": "title", "dc:creator": "creator", "cp:lastModifiedBy": "last_modified_by",
              "dcterms:created": "created", "dcterms:modified": "modified", "cp:revision": "revision"}


def ooxml(path) -> list[dict]:
    out = []
    try:
        with zipfile.ZipFile(path) as z:
            if "docProps/core.xml" not in z.namelist():
                return [_field("ooxml", "note", "docProps/core.xml missing")]
            info = z.getinfo("docProps/core.xml")
            if info.file_size > 1_000_000:
                return [_field("ooxml", "error", "core.xml unreasonably large; skipped")]
            xml = z.read("docProps/core.xml").decode("utf-8", "replace")
        if "<!DOCTYPE" in xml or "<!ENTITY" in xml:  # XML entity expansion defence
            return [_field("ooxml", "error", "DTD/entity declarations rejected")]
        for tag, name in _OOXML_MAP.items():
            m = re.search(rf"<{re.escape(tag)}[^>]*>([^<]*)</{re.escape(tag)}>", xml)
            if m:
                out.append(_field("ooxml", name, m.group(1)))
    except zipfile.BadZipFile:
        out.append(_field("ooxml", "error", "Invalid ZIP container"))
    return out


def text(path) -> list[dict]:
    data = Path(path).read_bytes()[:1_000_000]
    s = data.decode("utf-8", "replace")
    return [_field("text", "line_count", s.count("\n") + 1), _field("text", "char_count", len(s))]


def extract(path, detected_type: str) -> list[dict]:
    fields = filesystem(path)
    if detected_type in ("jpg", "png", "gif", "bmp", "tiff"):
        fields += image(path)
    elif detected_type == "pdf":
        fields += pdf(path)
    elif detected_type in ("docx", "xlsx", "pptx"):
        fields += ooxml(path)
    elif detected_type in ("text", "script"):
        fields += text(path)
    return fields


def text_excerpt(path, detected_type: str, limit: int = 2000) -> str:
    if detected_type not in ("text", "script"):
        return ""
    s = Path(path).read_bytes()[:limit].decode("utf-8", "replace")
    return "".join(c if c.isprintable() or c in "\n\t" else "?" for c in s)
