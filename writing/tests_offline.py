"""Offline safety tests for the Writing runner: fake Google + fake Claude batch, synthetic data, no network."""
import re
import json, os, sys, tempfile, types
from pathlib import Path

T = Path(tempfile.mkdtemp())
pack = T / "bundle/packs/P1"; pack.mkdir(parents=True)
(pack / "head.md").write_text("# KIỂM TRA VỞ — {{CLASS}}\nPrompt thử.\n", encoding="utf-8")
(pack / "schema.json").write_text(json.dumps({"type": "object", "properties": {"verdict": {"type": "string"}, "overall": {"type": "string"}}, "required": ["verdict", "overall"]}))
(pack / "validate.py").write_text("import json,sys\nr=json.load(open(sys.argv[1]));assert r['verdict'] in ('Đạt','Cần bổ sung')\n", encoding="utf-8")
cfg = {"formSheet": "F", "classes": {"L 1": "TR"}, "autoPublish": False,
       "assignments": [{"code": "IELTS-WRITING-W01", "formTab": "IELTS WRITING - W01", "pack": "P1", "classes": "*"}]}
(T / "bundle/config.json").write_text(json.dumps(cfg))
os.environ.update(RUNTIME_DIR=str(T / "rt"), BUNDLE_DIR=str(T / "bundle"), STATE_DIR=str(T / "rt/state"))
sys.path.insert(0, str(Path(__file__).parent))
import pymupdf, run_writing as rw, claude_worker as cw

doc = pymupdf.open(); doc.new_page(); PDF = doc.tobytes()
import datetime as _d0
DUE = (_d0.datetime.now() + _d0.timedelta(days=3)).strftime("%d/%m/%Y")
ROW = lambda name, t, f: [t, name, "L 1", "", "", f"https://drive.google.com/file/d/{f*24}/view", ""]

class G:
    def __init__(s):
        s.cells = {"C7": "✅ ĐÃ NỘP\n01/01/2026\n\n— NHẬN XÉT GV —\n", "C8": "✅ ĐÃ NỘP\n\n— NHẬN XÉT GV —\nCô đã chấm.",
                   "C9": "⛔ QUÁ HẠN\n— CHƯA GHI NHẬN\n\n— NHẬN XÉT GV —"}
        s.rows = [ROW("an", "01/01/2026 10:00:00", "A"), ROW("BÌNH", "01/01/2026 10:00:00", "B"), ROW("an", "01/01/2026 11:00:00", "D"),
                  ROW("CHI", "01/01/2026 12:00:00", "C"), ROW("DŨNG", "01/01/2026 12:00:00", "E")]
        s.writes = []
    def values(s, sid, rng):
        if "W01" in rng: return s.rows
        if "A4:ZZ4" in rng: return [["", "", "Mã: IELTS-WRITING-W01\nHạn: Thứ Bảy, " + DUE]]
        if "B1:B200" in rng: return [[]] * 6 + [["AN"], ["BÌNH"], ["CHI"]]
        if "A1:ZZ200" in rng:
            s.grid_reads = getattr(s, "grid_reads", 0) + 1
            g = [[""] * 10 for _ in range(12)]
            for a1, v in s.cells.items():
                m = re.match(r"([A-Z]+)(\d+)$", a1); g[int(m.group(2)) - 1][ord(m.group(1)) - 65] = v
            return g
        return [[s.cells.get(rng.split("!")[1], "")]]
    def set_cell(s, sid, rng, text): s.cells[rng.split("!")[1]] = text; s.writes.append(rng)
    def download(s, f): return PDF
    def sheet_titles(s, sid): return ["IELTS WRITING - W01"]
    def search(s, q): return [{"id": "T53", "name": "IELTS 53_THEO DÕI TOÀN DIỆN"}, {"id": "F10", "name": "FIGHTER 10_THEO DÕI TOÀN DIỆN"}, {"id": "X", "name": "MẪU - THEO DÕI TOÀN DIỆN - LỚP MỚI"}]

class B:
    reqs = []
    def create(s, requests): B.reqs = requests; return types.SimpleNamespace(id="b1")
    def retrieve(s, i): return types.SimpleNamespace(processing_status="ended")
    def results(s, i):
        for r in B.reqs:
            body = {"content": [{"type": "text", "text": json.dumps({"verdict": "Đạt", "overall": "Đã ghi nhận vở — Đạt yêu cầu."}, ensure_ascii=False)}],
                    "usage": {"input_tokens": 10, "output_tokens": 5}, "stop_reason": "end_turn"}
            yield types.SimpleNamespace(custom_id=r["custom_id"], result=types.SimpleNamespace(type="succeeded", message=types.SimpleNamespace(model_dump=lambda b=body: b)))
cw.client = lambda: types.SimpleNamespace(messages=types.SimpleNamespace(batches=B()))

g, st = G(), {"subs": {}, "batches": {}}
st["baselined"] = {"IELTS-WRITING-W01": True}
r = rw.Runner(g, cfg, st)
r.scan()
an = next(s for s in st["subs"].values() if s["student"] == "AN")
assert an["files"] == ["A" * 24, "D" * 24] and an["rows"] == [2, 4], "two submissions of one student are combined"
assert next(s for s in st["subs"].values() if s["student"] == "DŨNG")["status"] == "not_in_roster", "not on the class list → not graded"
r.submit(); assert len(B.reqs) == 3, "students off the class list cost nothing"
r.collect(); assert all(s["status"] == "graded" for s in st["subs"].values() if s["student"] != "DŨNG")
r.publish(set()); assert not g.writes, "nothing is written before approval"
r.publish("all")
assert g.cells["C7"].endswith("— NHẬN XÉT GV —\nĐã ghi nhận vở — Đạt yêu cầu.") and g.cells["C7"].startswith("✅ ĐÃ NỘP"), "prefix kept"
assert "Cô đã chấm.\n\n【Lần nộp 01/01/2026】\nĐã ghi nhận vở — Đạt yêu cầu." in g.cells["C8"], "teacher comment kept, new result added below"
assert g.cells["C9"].startswith("✅ ĐÃ NỘP\n01/01/2026 12:00\n\n— NHẬN XÉT GV —\nĐã ghi nhận"), "unmarked submission gets its status + result"
assert next(s for s in st["subs"].values() if s["student"] == "DŨNG")["status"] == "not_in_roster"
r.counts = {}; r.scan(); assert "new" not in r.counts, "unchanged work is not regraded"
g.rows.append(ROW("BÌNH", "02/01/2026 09:00:00", "E")); r.scan(); assert r.counts.get("new") == 1, "resubmission is regraded"
# baseline: first sight of an assignment skips work already commented by the old pipeline
st2 = {"subs": {}, "batches": {}}; g2 = G(); r2 = rw.Runner(g2, cfg, st2); r2.scan()
assert sorted(s["status"] for s in st2["subs"].values()) == ["new", "new", "not_in_roster", "skipped"]
assert cfg["classes"].get("IELTS 53") == "T53" and cfg["classes"].get("FIGHTER 10") == "F10" and len(cfg["classes"]) == 3, "new classes discovered, template ignored"
# failures: one regrade, then a clear message instead of no result
fk, fs = next((k, s) for k, s in st2["subs"].items() if s["status"] == "new")
r2.finish(fk, fs, "notebook", {"state": "validation_failed"}, None, None); assert fs["status"] == "new" and fs["tries"] == 1
r2.finish(fk, fs, "notebook", {"state": "validation_failed"}, None, None)
assert fs["status"] == "graded" and fs["fallback"] == "unclear" and "nộp lại" in fs["comment"], "every student gets a result"
# header codes written without W / class names typed loosely
class H(G):
    def values(s, sid, rng): return [["", "Mã: IELTS-WRITING-25\nHạn: Thứ Hai, 12/10/2026"]] if "A4" in rng else G.values(s, sid, rng)
assert rw.Tracker(H(), "x", "t").column("IELTS-WRITING-W25")[0] == "B" and rw.Tracker(H(), "x", "t").column("IELTS-WRITING-W02")[0] is None
assert r2.class_of(" ielts50 ") == "IELTS 50" and r2.class_of("Lớp FIGHTER 09") == "FIGHTER 9"
# duplicate names on one list are never guessed
class Dup(G):
    def values(s, sid, rng): return [[]] * 6 + [["AN"], ["AN"]] if "B1:B200" in rng else G.values(s, sid, rng)
assert rw.Tracker(Dup(), "x", "t").row_of("AN") is None
print("writing offline tests OK")
