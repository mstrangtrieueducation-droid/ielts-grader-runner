"""Offline checks for the Fighter notebook step (no network)."""
import datetime as dt, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os; os.environ.setdefault("STATE_DIR", "/tmp/fnb-test-state")
from fighter import notebook as nb

u = nb.VOCAB["VF2-U14"]; ns = [e["n"] for e in u["entries"]]
full = {"entries": [dict(n=n, term=e["term"], **{f: "filled" for f, _ in nb.FIELDS}) for n, e in zip(ns, u["entries"])], "otherTerms": 0}
r = nb.score(u, full); assert r["pct"] == 100 and not r["missing"], r
part = {"entries": [dict(e, en="empty") if i < 3 else e for i, e in enumerate(full["entries"][:-4])]}
r = nb.score(u, part); assert r["missing"] == ns[-4:] and r["empty"]["en"] == ns[:3] and r["pct"] < 90, r
unclear = {"entries": [dict(e, example="unclear") for e in full["entries"]]}
assert nb.score(u, unclear)["pct"] == 100, "unclear handwriting never counts as missing"
nonum = {"entries": [dict(e, n=0) for e in full["entries"]]}
assert nb.score(u, nonum)["seen"] == len(ns), "missing numbers are mapped by the term"
u2 = nb.VOCAB["VF1-U02"]
vu = ["achieve", "brain", "clever = smart", "concentrate", "consider", "course", "degree", "experience", "expert", "fail",
      "guess", "hesitate", "instruction", "make progress", "make sure", "mark"]
r = nb.score(u2, {"entries": [dict(n=i + 1, term=t, **{f: "filled" for f, _ in nb.FIELDS}) for i, t in enumerate(vu)]})
assert r["seen"] == 10, ("pupil numbering from 1 is matched by the headword", r)
print("VF1-U02 renumbered notebook:", r["seen"], "/", r["total"], r["pct"], "%")
assert nb.ranges([1, 2, 3, 5, 7, 8]) == "1–3, 5, 7–8"
assert nb.unit_code("VF2", "VF2-U14") == "VF2-U14" and nb.unit_code("RI2", "UNIT 7") == "RI2-U07"

class R:  # minimal runner
    cfg = {"classes": {"FIGHTER 5": "F5"}}
    counts = {}
    def tick(s, k, n=1): s.counts[k] = s.counts.get(k, 0) + n
    def class_of(s, raw): return "FIGHTER 5"
class TR:
    id, tab = "F5", "T"
    def row_of(s, name): return {"NGUYỄN KIM NGÂN": 7, "LƯU GIA BẢO": 9}.get(name)
r1 = [""] * 70; r1[60] = "Theo dõi\nBài tập về nhà"
r2 = [""] * 70; r3 = [""] * 70
r2[10] = "Vocabulary Foundation 2\nUnit 14"; r3[10] = "Tổng: 45 câu hỏi"            # score area: ignored
r2[62] = "Vocabulary Foundation 2 \nTừ vựng nền tảng cấp độ 2\nUnit 14"; r3[62] = "* làm lại trên web\nhạn: Thứ 2"
r3[63] = "Hạn: Thứ HAI, 12/10/2026\n🔗 MỞ BÀI CẢ LỚP"; r3[64] = "tra cứu trước"
r2[65] = "READING 2 - TỪ VỰNG\nUnit 4"; r3[65] = "Hạn 28/10/2026"
class G:
    def values(s, sid, rng): return [r1, r2, r3]
run = R(); f = nb.FighterNotebooks.__new__(nb.FighterNotebooks); f.r, f.g = run, G()
tr = TR(); run.tracker = lambda c: tr
a1, dl, why = f.cell_for({"cls": "FIGHTER 5", "student": "Nguyễn Kim Ngân- Jane", "code": "VF2-U14", "prog": "VF2"})
assert (a1, why) == ("BL7", None) and dl.day == 12, (a1, dl, why)
a1, dl, why = f.cell_for({"cls": "FIGHTER 5", "student": "LƯU GIA BẢO (Legacy)", "code": "RI2-U04", "prog": "RI2"})
assert a1 == "BN9", a1
assert f.cell_for({"cls": "FIGHTER 5", "student": "X Y", "code": "VF2-U14", "prog": "VF2"})[2] == "not_in_roster"

s = {"code": "VF2-U14", "prog": "VF2"}
res = dict(nb.score(u, part), kind="scored", video="ok", videoSecs=60, meaningOff=False)
txt, ok, _pct = f.comment(s, res, 0); assert not ok and "Thiếu 4 từ" in txt and "Nghĩa tiếng Anh" in txt, txt
print(txt); print("---")
txt, ok, _pct = f.comment(s, dict(nb.score(u, full), kind="scored", video="ok", videoSecs=60, meaningOff=False), 0); assert ok; print(txt); print("---")
txt, ok, _pct = f.comment(s, dict(nb.score(u, full), kind="scored", video="ok", videoSecs=60, meaningOff=False, messy=True), 0)
assert not ok and "cẩu thả" in txt, txt
print(f.comment(s, {"kind": "reused", "reusedFrom": {"code": "VF2-U13"}}, 0)[0])
assert nb.unit_code("GF", "GF1-U04.1-LT") == "GF1-U04.1-LT" and nb.unit_code("GF", "Unit 10") == "GF1-U10-LT"
assert nb.unit_code("AP", "AP-B07") == "AP-B07" and nb.unit_code("AP", "Buổi 05") == "AP-B05"
assert nb.unit_label("GF1-U04.1-LT") == ("Unit", "4.1") and nb.unit_label("AP-B07") == ("Buổi", "7")
r2[66] = "Grammar Foundation \nNgữ pháp nền tảng\nUnit 4.1"; r3[66] = "* làm lại trên web"; r3[67] = "Hạn: Thứ 2, 05/10/2026"
r2[68] = "Grammar Foundation \nNgữ pháp nền tảng\nUnit 4"; r3[68] = "Hạn: Thứ 2, 28/09/2026"
r2[69] = "ĐOẠN VĂN HỌC THUẬT\nBuổi 07"; r3[69] = "Hạn:\nThứ tư, 07/10/2026"
assert f.cell_for({"cls": "FIGHTER 5", "student": "Nguyễn Kim Ngân", "code": "GF1-U04.1-LT", "prog": "GF"})[0] == "BP7"
assert f.cell_for({"cls": "FIGHTER 5", "student": "Nguyễn Kim Ngân", "code": "GF1-U04-LT", "prog": "GF"})[0] == "BQ7", "Unit 4 ≠ Unit 4.1"
assert f.cell_for({"cls": "FIGHTER 5", "student": "Nguyễn Kim Ngân", "code": "AP-B07", "prog": "AP"})[0] == "BR7"
g = {"code": "GF1-U10-LT", "prog": "GF"}
txt, ok, _pct = f.comment(g, {"type": "copy", "kind": "scored", "pct": 70, "total": 5, "missing": ["IV. Countable – Uncountable Nouns"],
                        "partly": ["VI. Articles"], "messy": True}, 0)
assert not ok and "Chưa chép phần: IV." in txt and "cẩu thả" in txt; print(txt); print("---")
print(f.comment({"code": "AP-B07", "prog": "AP"}, {"kind": "printed"}, 0)[0])
assert nb.unit_code("RC2", "Test 11") == "RI2-C11" and nb.unit_code("RC2", "RI2-C07") == "RI2-C07"
assert nb.unit_label("RI2-C07") == ("Unit", "7") and nb.known("RC2", "RI2-C07")
r2[60] = "READING 2 - VỞ CHỮA\nUnit 4"; r3[60] = "Hạn 04/11/2026"
assert f.cell_for({"cls": "FIGHTER 5", "student": "Nguyễn Kim Ngân", "code": "RI2-C04", "prog": "RC2"})[0] == "BI7"
res = {"type": "reading", "kind": "scored", "vocab": dict(nb.score(u, part)), "total": 64, "work": 80, "notAnswered": [60, 61, 62, 63, 64],
       "notExplained": [1, 2, 3], "wrong": [7], "messy": False}
txt, ok, _pct = f.comment({"code": "RI2-C04", "prog": "RC2"}, res, 0); assert not ok and "Chưa làm lại câu: 60–64" in txt; print(txt)
assert nb.unit_code("PT", "PRACTICE TEST 4") == "PT4" and nb.unit_label("PT4") == ("Practice Test", "4") and nb.known("PT", "PT4")
r2[61] = "LUYỆN ĐỀ\nPractice Test 4"; r3[61] = "* sổ luyện đề & sổ từ vựng\nHạn: Chủ nhật, 15/11/2026"
assert f.cell_for({"cls": "FIGHTER 5", "student": "Nguyễn Kim Ngân", "code": "PT4", "prog": "PT"})[0] == "BJ7"
print("fighter notebook offline checks: OK")

# correction-doc table → which answers need an explanation
from notebook import parse_doc_why
_t = "| **Câu** | **Đáp án** | **Giải thích** |\n| :- | :- | :- |\n|  | **Q** | **Stun (v):** x |\n|  | **state ** |  |\n|  | **D** |  |\n|  | **B** | **Khía** |\n"
assert parse_doc_why(_t, 4) == [True, False, False, True]
assert parse_doc_why(_t, 5) is None
print("doc_why ok")

from notebook import test_section
_d = "# **CHỮA ĐỀ**\n# **TEST 1**\n| a |\n# **TEST 2**\n| b |\n"
assert "| b |" in test_section(_d, 2) and "| a |" not in test_section(_d, 2) and test_section(_d, 3) == ""
print("test_section ok")

# status line: not ok → "❌ CẦN NỘP LẠI · N% · time" (dashboard/web app count it as owed); ok again → a receipt line
class _T:
    def __init__(self, v): self.v = v
    def cell(self, a1): return self.v
    def write(self, a1, t): self.v = t
_t = _T("✅ ĐÃ NỘP\n09/11/2026 23:51")
_f = nb.FighterNotebooks.__new__(nb.FighterNotebooks)
_f.r = type("R", (), {"tracker": lambda self, c: _t})()
_s = {"cls": "FIGHTER 5", "submittedAt": "09/11/2026 23:51:00"}
assert _f.write(_s, "BQ4", None, "Chất lượng: đạt 17% — CHƯA ĐẠT", False, 17) == "ok"
assert _t.v.startswith("❌ CẦN NỘP LẠI · 17% · 09/11/2026 23:51\n\n" + nb.MARK), _t.v
_s["published"] = "Chất lượng: đạt 17% — CHƯA ĐẠT"
_s2 = {"cls": "FIGHTER 5", "submittedAt": "10/11/2026 20:00:00", "published": _s["published"]}
assert _f.write(_s2, "BQ4", None, "Chất lượng: đạt 95% — Đạt yêu cầu.", True, 95) == "ok"
assert _t.v.startswith("✅ ĐÃ NỘP\n10/11/2026 20:00\n\n" + nb.MARK + "\nChất lượng: đạt 95%"), _t.v
print("status line ok")

# Academic Paragraph: model paragraph + word list from the lesson doc, coverage from the last words copied
_doc = "x **Bài mẫu**" + " ".join(f"w{i}" for i in range(100)) + " end of model. **Từ vựng và cụm từ****alpha** (TT): a.**beta gamma** (cụm DT): b.**delta** (ĐT): c."
_r = nb.ap_reference(_doc); assert _r and _r["vocab"] == ["alpha", "beta gamma", "delta"], _r
assert nb.model_reach(_r["model"], "w97 w98 w99 end of model.") == 1.0 and 0.4 < nb.model_reach(_r["model"], "w45 w46 w47 w48 w49") < 0.6
assert nb.ap_reference("**Bài mẫu** short **Từ vựng và cụm từ**") is None
print("academic paragraph ok")
