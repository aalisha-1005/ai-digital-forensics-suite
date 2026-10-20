"""File-signature (magic number) detection. Pure inspection, never executes content."""
from pathlib import Path

# (offset, magic, type, mime, family)
SIGNATURES = [
    (0, b"\x89PNG\r\n\x1a\n", "png", "image/png", "image"),
    (0, b"\xff\xd8\xff", "jpg", "image/jpeg", "image"),
    (0, b"GIF87a", "gif", "image/gif", "image"),
    (0, b"GIF89a", "gif", "image/gif", "image"),
    (0, b"BM", "bmp", "image/bmp", "image"),
    (0, b"II*\x00", "tiff", "image/tiff", "image"),
    (0, b"MM\x00*", "tiff", "image/tiff", "image"),
    (0, b"%PDF-", "pdf", "application/pdf", "pdf"),
    (0, b"MZ", "exe", "application/vnd.microsoft.portable-executable", "executable"),
    (0, b"\x7fELF", "elf", "application/x-elf", "executable"),
    (0, b"\xcf\xfa\xed\xfe", "macho", "application/x-mach-binary", "executable"),
    (0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "ole", "application/x-ole-storage", "office-legacy"),
    (0, b"PK\x03\x04", "zip", "application/zip", "archive"),
    (0, b"\x1f\x8b", "gz", "application/gzip", "archive"),
    (0, b"#!", "script", "text/x-script", "script"),
]

OOXML = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}

TEXT_EXT = {"txt", "log", "csv", "json", "md", "xml", "html", "htm", "ini", "cfg", "eml"}
SCRIPT_EXT = {"sh", "bat", "cmd", "ps1", "vbs", "js", "py", "wsf"}
EXECUTABLE_EXT = {"exe", "dll", "scr", "com", "msi", "elf", "bin"}


def _is_text(sample: bytes) -> bool:
    if not sample:
        return True
    if b"\x00" in sample:
        return False
    printable = sum(1 for b in sample if b in (9, 10, 13) or 32 <= b < 127 or b >= 128)
    return printable / len(sample) > 0.95


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")


def detect(path, filename: str) -> dict:
    """Return detected type from content, claimed type from extension and mismatch flag."""
    with open(path, "rb") as fh:
        head = fh.read(4096)
    detected, mime, family = "unknown", "application/octet-stream", "unknown"
    for off, magic, t, m, fam in SIGNATURES:
        if head[off:off + len(magic)] == magic:
            detected, mime, family = t, m, fam
            break
    if detected == "zip":
        import zipfile
        try:
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
            for ext in OOXML:
                if any(n.startswith(("word/", "xl/", "ppt/")[("docx", "xlsx", "pptx").index(ext)]) for n in names):
                    detected, mime, family = ext, OOXML[ext], "office"
                    break
        except Exception:
            pass
    if detected == "unknown" and _is_text(head):
        detected, mime, family = "text", "text/plain", "text"
    ext = extension_of(filename)
    acceptable = {detected}
    if detected == "jpg":
        acceptable.add("jpeg")
    if detected == "tiff":
        acceptable.add("tif")
    if detected == "ole":
        acceptable |= {"doc", "xls", "ppt", "msg"}
    if detected == "text":
        acceptable |= TEXT_EXT | SCRIPT_EXT
    if detected == "script":
        acceptable |= SCRIPT_EXT | {"txt"}
    if detected == "exe":
        acceptable |= EXECUTABLE_EXT
    if detected == "zip":
        acceptable |= {"zip", "jar", "apk"}
    mismatch = bool(ext) and ext not in acceptable
    return {"detected_type": detected, "detected_mime": mime, "family": family,
            "claimed_extension": ext, "extension_mismatch": mismatch}
