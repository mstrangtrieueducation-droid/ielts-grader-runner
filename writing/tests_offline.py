"""Offline safety tests for the Writing runner: fake Google + fake Claude batch, synthetic data, no network."""
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
        s.rows = [ROW("an", "01/01/2026 10:00:00", "A"), ROW("BÌNH", "01/01/2026 10:00:00", "B"), ROW("an", "01/01/2026 11:00:00", "D")]
        s.writes = []
    def values(s, sid, rng):
        if "W01" in rng: return s.rows
        if "A4:ZZ4" in rng: return [["", "", "Mã: IELTS-WRITING-W01\nHạn: Thứ Bảy, " + DUE]]
        if "B1:B200" in rng: return [[]] * 6 + [["AN"], ["BÌNH"], ["CHI"]]
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
r.submit(); assert len(B.reqs) == 2
r.collect(); assert all(s["status"] == "graded" for s in st["subs"].values())
r.publish(set()); assert not g.writes, "nothing is written before approval"
r.publish("all")
assert g.cells["C7"].endswith("— NHẬN XÉT GV —\nĐã ghi nhận vở — Đạt yêu cầu.") and g.cells["C7"].startswith("✅ ĐÃ NỘP"), "prefix kept"
assert g.cells["C8"].endswith("Cô đã chấm."), "teacher comment is never overwritten"
assert next(s for s in st["subs"].values() if s["student"] == "BÌNH")["hold"] == "teacher_comment_exists"
r.counts = {}; r.scan(); assert "new" not in r.counts, "unchanged work is not regraded"
g.rows.append(ROW("BÌNH", "02/01/2026 09:00:00", "E")); r.scan(); assert r.counts.get("new") == 1, "resubmission is regraded"
# baseline: first sight of an assignment skips work already commented by the old pipeline
st2 = {"subs": {}, "batches": {}}; g2 = G(); r2 = rw.Runner(g2, cfg, st2); r2.scan()
assert sorted(s["status"] for s in st2["subs"].values()) == ["new", "skipped"]
assert cfg["classes"].get("IELTS 53") == "T53" and cfg["classes"].get("FIGHTER 10") == "F10" and len(cfg["classes"]) == 3, "new classes discovered, template ignored"
import datetime as _dt
st2["lastDeadline"] = {"IELTS-WRITING-W01": (rw.now() - _dt.timedelta(days=20)).isoformat()}
r2.counts = {}; r2.scan(); assert "IELTS-WRITING-W01" in st2["closedWeeks"], "old week closed"
print("writing offline tests OK")
