import json, os, struct, tempfile, unittest, zipfile
from pathlib import Path
from PIL import Image
from app.services import hashing, signatures, metadata, rules, ml, ledger, timeline, reports


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def write(self, name, data: bytes):
        p = self.tmp / name
        p.write_bytes(data)
        return p


class TestHashing(Base):
    def test_known_vector(self):
        p = self.write("a.txt", b"abc")
        self.assertEqual(hashing.sha256_file(p), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_verify_detects_modification_and_missing(self):
        p = self.write("a.txt", b"abc")
        h = hashing.sha256_file(p)
        self.assertTrue(hashing.verify_file(p, h)[0])
        p.write_bytes(b"abd")
        ok, actual = hashing.verify_file(p, h)
        self.assertFalse(ok); self.assertNotEqual(actual, h)
        self.assertEqual(hashing.verify_file(self.tmp / "nope", h), (False, "MISSING"))


class TestSignatures(Base):
    def test_png_disguised_as_pdf(self):
        p = self.tmp / "x.png"; Image.new("RGB", (4, 4)).save(p)
        r = signatures.detect(p, "report.pdf")
        self.assertEqual(r["detected_type"], "png"); self.assertTrue(r["extension_mismatch"])

    def test_clean_text(self):
        r = signatures.detect(self.write("n.txt", b"hello world\n"), "n.txt")
        self.assertEqual(r["detected_type"], "text"); self.assertFalse(r["extension_mismatch"])

    def test_exe_signature(self):
        r = signatures.detect(self.write("a.txt", b"MZ" + b"\x00" * 100), "a.txt")
        self.assertEqual(r["family"], "executable"); self.assertTrue(r["extension_mismatch"])


class TestMetadataAndRules(Base):
    def test_image_exif(self):
        p = self.tmp / "p.jpg"
        im = Image.new("RGB", (8, 8)); ex = im.getexif(); ex[306] = "2024:01:02 03:04:05"; im.save(p, exif=ex)
        sig = signatures.detect(p, "p.jpg")
        f = metadata.extract(p, sig["detected_type"])
        self.assertTrue(any(x["key"] == "DateTime" and x["value"].startswith("2024") for x in f))
        ev = timeline.events_from_metadata(f)
        self.assertTrue(any(e["title"].startswith("Image datetime") for e in ev))

    def test_ooxml_core_and_macro_flag(self):
        p = self.tmp / "d.docx"
        core = '<cp:coreProperties xmlns:cp="x" xmlns:dc="y" xmlns:dcterms="z"><dc:creator>Synthetic Author</dc:creator>' \
               '<dcterms:created>2024-05-02T10:00:00Z</dcterms:created><dcterms:modified>2024-05-01T10:00:00Z</dcterms:modified></cp:coreProperties>'
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("word/document.xml", "<w/>"); z.writestr("docProps/core.xml", core); z.writestr("word/vbaProject.bin", b"x")
        sig = signatures.detect(p, "d.docx"); self.assertEqual(sig["detected_type"], "docx")
        f = metadata.extract(p, "docx")
        res = rules.analyze(p, "d.docx", sig, f)
        codes = {i["code"] for i in res["indicators"]}
        self.assertIn("OFFICE_MACRO", codes); self.assertIn("TIMESTAMP_ANOMALY", codes)

    def test_xml_entity_rejected(self):
        p = self.tmp / "e.docx"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("word/document.xml", "<w/>"); z.writestr("docProps/core.xml", '<!DOCTYPE x [<!ENTITY a "b">]><x/>')
        self.assertEqual(metadata.extract(p, "docx")[-1]["key"], "error")

    def test_pdf_active_content(self):
        p = self.write("a.pdf", b"%PDF-1.4\n/Title (Demo)\n/OpenAction <</S /JavaScript /JS (x)>>\n%%EOF")
        sig = signatures.detect(p, "a.pdf"); f = metadata.extract(p, "pdf")
        self.assertIn("PDF_ACTIVE_CONTENT", {i["code"] for i in rules.analyze(p, "a.pdf", sig, f)["indicators"]})

    def test_double_extension(self):
        p = self.write("invoice.pdf.exe", b"MZ" + b"\x00" * 50)
        sig = signatures.detect(p, "invoice.pdf.exe")
        codes = {i["code"] for i in rules.analyze(p, "invoice.pdf.exe", sig, metadata.extract(p, sig["detected_type"]))["indicators"]}
        self.assertIn("DOUBLE_EXT", codes); self.assertIn("EXEC_SIGNATURE", codes)


class TestML(Base):
    def test_train_and_predict(self):
        card = ml.train(self.tmp, n=1500)
        self.assertGreater(card["holdout_accuracy"], 0.7)
        benign = ml.predict(self.tmp, {"log_size": 4, "entropy": 4.0, "printable_ratio": 0.95})
        bad = ml.predict(self.tmp, {"log_size": 5, "entropy": 7.4, "printable_ratio": 0.3, "exec_sig": 1, "double_ext": 1,
                                    "ext_mismatch": 1, "script_hits": 6})
        self.assertEqual(benign["label"], "benign"); self.assertEqual(bad["label"], "suspicious")
        self.assertTrue(bad["requires_human_review"]); self.assertTrue(bad["top_features"]); self.assertTrue(bad["limitations"])


class TestLedger(unittest.TestCase):
    def make(self, n=4):
        prev, out = ledger.GENESIS, []
        for i in range(1, n + 1):
            payload = {"seq": i, "action": f"a{i}", "actor": "u"}
            h = ledger.compute_hash(prev, payload)
            out.append({"seq": i, "payload": payload, "prev_hash": prev, "entry_hash": h}); prev = h
        return out

    def test_valid(self):
        self.assertTrue(ledger.verify_chain(self.make())["valid"])

    def test_modification_detected(self):
        e = self.make(); e[1]["payload"]["action"] = "tampered"
        r = ledger.verify_chain(e); self.assertFalse(r["valid"]); self.assertEqual(r["first_broken_seq"], 2)

    def test_deletion_detected(self):
        e = self.make(); del e[1]
        self.assertFalse(ledger.verify_chain(e)["valid"])


class TestTimeline(unittest.TestCase):
    def test_normalisation(self):
        self.assertEqual(timeline.to_utc("2024:01:02 03:04:05").isoformat(), "2024-01-02T03:04:05+00:00")
        self.assertEqual(timeline.to_utc("D:20240102030405").year, 2024)
        self.assertEqual(timeline.to_utc("2024-01-02T05:30:00+05:30").hour, 0)
        self.assertIsNone(timeline.to_utc("garbage"))

    def test_conflicts(self):
        ev = [{"title": "PDF created", "timestamp": timeline.to_utc("2024-02-01T00:00:00Z")},
              {"title": "PDF modified", "timestamp": timeline.to_utc("2024-01-01T00:00:00Z")},
              {"title": "File modified", "timestamp": timeline.to_utc("2999-01-01T00:00:00Z")}]
        self.assertEqual(len(timeline.detect_conflicts(ev)), 2)


class TestReports(unittest.TestCase):
    def data(self):
        return {"generated_by": "tester", "case": {"case_id": "CASE-0001", "title": "Synthetic <demo>", "description": "d",
                "status": "open", "priority": "high"},
                "evidence": [{"evidence_id": "EV-0001", "original_filename": "a.txt", "size_bytes": 3, "acquired_at": "2024-01-01T00:00:00Z",
                              "sha256": "ba78" * 16, "integrity_status": "verified", "verifications": [{"timestamp_utc": "t", "result": "match"}],
                              "metadata": [{"source": "filesystem", "key": "size_bytes", "value": "3"}]}],
                "findings": [{"evidence_id": "EV-0001", "category": "needs_review", "title": "=cmd()", "description": "x", "review_status": "pending", "confidence": 0.8},
                             {"evidence_id": "EV-0001", "category": "benign", "title": "ok", "description": "y", "review_status": "accepted",
                              "analyst_interpretation": "Looks fine", "reviewed_by": "inv1"}],
                "timeline": [{"timestamp_utc": "2024-01-01T00:00:00Z", "title": "File modified", "provenance": "auto", "evidence_id": "EV-0001"}],
                "timeline_notes": ["n"], "notes": [{"created_at": "t", "author": "inv1", "method": "m", "body": "b"}],
                "custody": [{"timestamp_utc": "t", "evidence_id": "EV-0001", "action": "registered", "actor": "inv1", "details": "{}"}],
                "custody_verification": "Chain intact"}

    def test_pdf(self):
        pdf = reports.build_pdf(self.data())
        self.assertTrue(pdf.startswith(b"%PDF")); self.assertGreater(len(pdf), 2000)

    def test_csv_sections_and_formula_guard(self):
        csv = reports.build_csv(self.data()).decode()
        for s in ("observed", "automated", "analyst", "custody", "timeline"):
            self.assertIn(s, csv)
        self.assertIn("'=cmd()", csv)


if __name__ == "__main__":
    unittest.main()
