"""PDF (ReportLab) and CSV (Pandas) report builders. Input is plain dicts so the
builders are independent of the web layer. Observed facts, automated flags and analyst
interpretations are kept in clearly separate sections."""
import io
import platform
import sys
from datetime import datetime, timezone

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

LIMITS = [
    "Metadata may be altered, stripped or forged; timestamps are not independently verified.",
    "Automated flags and AI classifications are triage aids, not proof of wrongdoing.",
    "Only findings marked 'accepted' by an investigator are treated as analyst conclusions.",
    "The custody ledger is tamper-evident but is not trusted timestamping and does not replace legal procedure.",
]


def tool_versions() -> dict:
    import reportlab, sklearn
    return {"python": sys.version.split()[0], "platform": platform.system(), "reportlab": reportlab.Version,
            "scikit-learn": sklearn.__version__, "pandas": pd.__version__}


def build_csv(data: dict) -> bytes:
    """Flat CSV with a 'section' column: observed / automated / analyst / custody / timeline."""
    rows = []
    for e in data["evidence"]:
        rows.append({"section": "observed", "evidence_id": e["evidence_id"], "item": "sha256", "value": e["sha256"],
                     "detail": f"{e['original_filename']} | {e['size_bytes']} bytes | integrity={e['integrity_status']}"})
        for m in e.get("metadata", []):
            rows.append({"section": "observed", "evidence_id": e["evidence_id"], "item": f"{m['source']}.{m['key']}",
                         "value": m["value"], "detail": "extracted metadata (alterable)"})
    for f in data["findings"]:
        sec = "analyst" if f["review_status"] == "accepted" else "automated"
        rows.append({"section": sec, "evidence_id": f["evidence_id"], "item": f["category"],
                     "value": f["title"], "detail": f"{f['description']} | review={f['review_status']}"
                     + (f" | interpretation={f['analyst_interpretation']}" if f.get("analyst_interpretation") else "")})
    for t in data["timeline"]:
        rows.append({"section": "timeline", "evidence_id": t.get("evidence_id", ""), "item": t["title"],
                     "value": t["timestamp_utc"], "detail": t["provenance"]})
    for c in data["custody"]:
        rows.append({"section": "custody", "evidence_id": c["evidence_id"], "item": c["action"],
                     "value": c["timestamp_utc"], "detail": f"actor={c['actor']} | {c['details']}"})
    cols = ["section", "evidence_id", "item", "value", "detail"]
    df = pd.DataFrame(rows, columns=cols)
    # neutralise spreadsheet formula injection
    df = df.map(lambda v: "'" + v if isinstance(v, str) and v[:1] in "=+-@" else v)
    return df.to_csv(index=False).encode("utf-8")


def _tbl(rows, widths=None, header=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    st = [("FONTSIZE", (0, 0), (-1, -1), 7.5), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#9aa7b5"))]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0e3a5c")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
    t.setStyle(TableStyle(st))
    return t


def build_pdf(data: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm,
                            bottomMargin=15 * mm, title=f"Forensic Report {data['case']['case_id']}")
    ss = getSampleStyleSheet()
    P = lambda s, st="BodyText": Paragraph(_esc(str(s)), ss[st])
    c = data["case"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    story = [P("Digital Forensics Investigation Report", "Title"),
             P(f"Case {c['case_id']}: {c['title']}", "Heading2"),
             P(f"Generated {now} by {data['generated_by']} | Status: {c['status']} | Priority: {c['priority']}"),
             P(f"Description: {c['description']}"), Spacer(1, 6),
             P("Data notice: records may be synthetic demonstration data.", "Italic"), Spacer(1, 6),
             P("1. Limitations", "Heading3")] + [P("- " + l) for l in LIMITS]

    story += [P("2. Evidence inventory and integrity (observed facts)", "Heading3")]
    rows = [["Evidence ID", "File", "Size", "Acquired (UTC)", "Integrity"]]
    for e in data["evidence"]:
        rows.append([P(e["evidence_id"]), P(e["original_filename"]), e["size_bytes"], e["acquired_at"],
                     P(e["integrity_status"].upper())])
    story += [_tbl(rows, [28 * mm, 55 * mm, 18 * mm, 40 * mm, 30 * mm]), Spacer(1, 4)]
    for e in data["evidence"]:
        story.append(P(f"SHA-256 {e['evidence_id']}: {e['sha256']}"))
        if e.get("verifications"):
            story.append(P("Verifications: " + "; ".join(f"{v['timestamp_utc']} {v['result']}" for v in e["verifications"][-5:])))

    story += [P("3. Extracted metadata (observed, alterable)", "Heading3")]
    for e in data["evidence"]:
        mrows = [["Source", "Key", "Value"]] + [[m["source"], m["key"], P(m["value"])] for m in e.get("metadata", [])]
        story += [P(e["evidence_id"], "Heading4"), _tbl(mrows if len(mrows) > 1 else [["No metadata extracted", "", ""]],
                                                         [25 * mm, 40 * mm, 100 * mm])]

    auto = [f for f in data["findings"] if f["review_status"] != "accepted"]
    acc = [f for f in data["findings"] if f["review_status"] == "accepted"]
    story += [P("4. Automated flags (NOT conclusions; pending or rejected review)", "Heading3")]
    story += [_tbl([["Evidence", "Category", "Title", "Confidence", "Review"]] +
                   [[f["evidence_id"], f["category"], P(f["title"]), f.get("confidence", ""), f["review_status"]] for f in auto]
                   if auto else [["None"]])]
    story += [P("5. Analyst interpretations (accepted by an investigator)", "Heading3")]
    if acc:
        for f in acc:
            story.append(P(f"{f['evidence_id']} | {f['title']} | reviewed by {f.get('reviewed_by', '?')}: "
                           f"{f.get('analyst_interpretation') or 'no interpretation recorded'}"))
    else:
        story.append(P("No findings have been accepted by an investigator."))

    story += [P("6. Timeline (UTC)", "Heading3")]
    trows = [["UTC", "Event", "Provenance"]] + [[t["timestamp_utc"], P(t["title"]), P(t["provenance"])] for t in data["timeline"]]
    story += [_tbl(trows if len(trows) > 1 else [["No events", "", ""]], [42 * mm, 60 * mm, 63 * mm])]
    for n in data.get("timeline_notes", []):
        story.append(P("Timeline note: " + n))

    story += [P("7. Investigator notes", "Heading3")] + \
             ([P(f"[{n['created_at']}] {n['author']} ({n['method'] or 'no method recorded'}): {n['body']}") for n in data["notes"]]
              or [P("No notes recorded.")])
    story += [P("8. Chain of custody", "Heading3"), P(data["custody_verification"])]
    crow = [["UTC", "Evidence", "Action", "Actor"]] + [[x["timestamp_utc"], x["evidence_id"], x["action"], x["actor"]] for x in data["custody"]]
    story += [_tbl(crow if len(crow) > 1 else [["No events"]], [42 * mm, 30 * mm, 50 * mm, 40 * mm])]
    story += [P("9. Tool versions", "Heading3"), P(", ".join(f"{k} {v}" for k, v in tool_versions().items()))]
    doc.build(story)
    return buf.getvalue()


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
