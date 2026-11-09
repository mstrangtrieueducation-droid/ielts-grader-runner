"""Homework essays typed into the form (Task 1 / Task 2), graded only when the notebook passed on time.
Lean output approved 09/11/2026: bands, annotations, short overall, revision. No transcription needed (typed text)."""
import base64, json, re
import claude_worker as cw
from run_writing import BUNDLE, h, parse_vn_time
import scans

ESSAY = scans.obj({
    "de": {"type": "integer"},
    "criteria": scans.obj({k: scans.obj({"band": {"type": "integer"}, "reason": scans.S, "whyNotHigher": scans.S})
                           for k in ("TA_TR", "CC", "LR", "GRA")}),
    "annotations": scans.ARR(scans.obj({"group": {"type": "string", "enum": ["vocab", "grammar", "coherence"]},
                                        "kind": {"type": "string", "enum": ["error", "practice", "suggestion"]},
                                        "label": scans.S, "quote": scans.S, "replacement": scans.S, "explanation": scans.S})),
    "overall": scans.S, "revisedText": scans.S})
SCHEMA = scans.obj({"essays": scans.ARR(ESSAY), "doubts": scans.ARR(scans.S)})
MODEL = "claude-sonnet-5-5"


def de_number(label, i):
    m = re.search(r"Đề\s*(\d+)", label)
    return int(m.group(1)) if m else i + 1


def request(a, s):
    pack = BUNDLE / "packs" / a["essayPack"]
    meta = json.loads((pack / "meta.json").read_text(encoding="utf-8"))
    head = (pack / "head.md").read_text(encoding="utf-8")
    content = []
    for i, f in enumerate(meta["images"]):
        content.append({"type": "text", "text": f"ẢNH ĐỀ {i + 1}:"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                     "data": base64.b64encode((pack / f).read_bytes()).decode()}})
    if content:
        content[-1] = {**content[-1], "cache_control": {"type": "ephemeral", "ttl": "1h"}}
    texts = []
    for i, (label, txt) in enumerate(sorted(s.get("essays", {}).items())):
        n = de_number(label, i)
        if str(n) not in meta["labels"]:   # only the essays this lesson asked for
            continue
        texts.append(f"=== ĐỀ {n} ({meta['labels'].get(str(n), label)}) — bài em đánh máy ===\n{txt}")
    content.append({"type": "text", "text": f"Học sinh {s['student']} · lớp {s['className']}. Chấm và chữa các bài sau "
                                            f"(mỗi bài tối thiểu {meta['minWords']} từ):\n\n" + "\n\n".join(texts)})
    return {"model": MODEL, "max_tokens": 12000, "thinking": {"type": "between_tools"},
            "system": [{"type": "text", "text": head, "cache_control": {"type": "ephemeral", "ttl": "1h"}}],
            "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
            "messages": [{"role": "user", "content": content}]}


def checks(a, s, res):
    import calculate_class_score as ccs
    meta = json.loads((BUNDLE / "packs" / a["essayPack"] / "meta.json").read_text(encoding="utf-8"))
    by_de = {de_number(lbl, i): txt for i, (lbl, txt) in enumerate(sorted(s.get("essays", {}).items()))
             if str(de_number(lbl, i)) in meta["labels"]}
    for e in res.get("essays", []):
        txt = by_de.get(e["de"], "")
        qa = {"words": scans.words(txt), "revisionWords": scans.words(e.get("revisedText", ""))}
        qa["quotesNotFound"] = [x["quote"] for x in e["annotations"] if x["quote"] not in txt]
        qa["bannedInRevision"] = sorted({m.group(0) for m in scans.BANNED_IELTS.finditer(e.get("revisedText", ""))})
        bands = [e["criteria"][k]["band"] for k in ("TA_TR", "CC", "LR", "GRA")]
        qa["band"] = ccs.calculate(meta.get("task", 1), qa["words"], bands)["classAssessment"]["overallBand"]
        e["_qa"] = qa
    res["_labels"] = meta["labels"]
    return res


def summary(res):
    """Short text for the tracker cell: one line per essay + its overall comment (details go to the dashboard)."""
    out = []
    for e in sorted(res.get("essays", []), key=lambda x: x["de"]):
        lbl = res.get("_labels", {}).get(str(e["de"]), f"Đề {e['de']}")
        out.append(f"【{lbl} · band {e['_qa']['band']:.1f}】\n{e['overall'].strip()}")
    return "\n\n".join(out)
