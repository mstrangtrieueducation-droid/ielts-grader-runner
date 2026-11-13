"""In-class writing (scanned papers) → the parent dashboard's 'Nhận xét bài viết trên lớp' (Cô 13/11: Buổi 8 was
missing on the dash). Same store and format as the earlier Codex classwork flow, so the class page's existing
classwork viewer shows it under the lesson card:

  _WRITING_CLASSWORK_V1   schema | class | identity | review_key | part | title | lesson_date | state | sha256 |
                          chunk_index | chunk_count | encoding | payload
  identity = sha256("<class>|<NAME>")   part = core (the review) / source (photos of the paper)
  payload  = gzip + base64 of the JSON, cut in 40 000-character chunks; sha256 = of the JSON bytes.

Only papers already published to the tracker are sent, each once (student["dash"]). IELTS classes whose page carries
the classwork viewer only (cfg classworkClasses)."""
from __future__ import annotations

import base64
import datetime as dt
import gzip
import hashlib
import io
import json
import re

TAB = "_WRITING_CLASSWORK_V1"
HEAD = ["schema", "class", "identity", "review_key", "part", "title", "lesson_date", "state", "sha256",
        "chunk_index", "chunk_count", "encoding", "payload"]
CHUNK = 40000
GROUP = {"grammar": "grammar", "vocab": "vocabulary", "vocabulary": "vocabulary", "coherence": "coherence"}
CRIT = {"TA_TR": ("TA", "Hoàn thành yêu cầu đề"), "TA": ("TA", "Hoàn thành yêu cầu đề"), "TR": ("TR", "Trả lời đúng đề"),
        "CC": ("CC", "Mạch lạc và liên kết"), "LR": ("LR", "Từ vựng"), "GRA": ("GRA", "Ngữ pháp")}
CROSSED = re.compile(r"gạch|crossed|erased|tẩy|xoá|xóa|strike")
INSERTED = re.compile(r"chèn|thêm|insert|added")


def _note(m):
    inner = m.group(1)
    low = inner.lower()
    if low.startswith("unclear:"):
        return m.group(0)   # the viewer shows '[unclear: …]' as uncertain text
    if "không rõ" in low or low.strip() in ("unclear", "?"):
        return "[?]"
    if INSERTED.search(low) and ":" in inner:
        a, _, b = inner.partition(":")
        return b.strip() if INSERTED.search(a.lower()) else a.strip()
    return ""   # crossed-out words, erasures and transcriber notes are not the pupil's text


def paragraphs_of(transcript, name):
    """The pupil's paragraphs: transcriber notes out, the name/heading line(s) at the top out."""
    t = re.sub(r"~~[^~\n]*~~", "", transcript or "")   # struck-through words
    t = re.sub(r"\[([^\]]*)\]", _note, t)
    lines = [re.sub(r"[ \t]{2,}", " ", ln).strip(" \t") for ln in t.splitlines()]
    lines = [ln for ln in lines if ln and not (ln.endswith(":") and len(ln.split()) <= 4)]
    bare = lambda s: re.sub(r"\W+", "", s).lower()
    while len(lines) > 1:
        first = lines[0].rstrip(".")
        toks = first.split()
        if (bare(name) and bare(name) in bare(first)) or (len(toks) <= 5 and not re.search(r"\d", first)
                                                          and all(w[:1].isupper() for w in toks)):
            lines = lines[1:]
            continue
        break
    return lines


def locate(paragraphs, quote):
    """(paragraph, start, end) of the quote: exact first, then ignoring spacing/quote-mark differences. Offsets are
    sent, so a quote that stands twice is bound to its first place."""
    for i, p in enumerate(paragraphs):
        k = p.find(quote)
        if k >= 0:
            return i, k, k + len(quote)
    pat = re.escape(re.sub(r"\s+", " ", quote.strip()))
    pat = pat.replace("\\ ", r"\s+")
    for a, b in (("’", "['’]"), ("'", "['’]"), ("“", "[\"“”]"), ("”", "[\"“”]")):
        pat = pat.replace(re.escape(a), b)
    for i, p in enumerate(paragraphs):
        m = re.search(pat, p)
        if m:
            return i, m.start(), m.end()
    return None


def status_of(band):
    if not isinstance(band, (int, float)):
        return "needs_practice"
    return "met" if band >= 6 else ("needs_practice" if band >= 5 else "needs_correction")


def chunks(obj):
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sha = hashlib.sha256(data).hexdigest()
    b64 = base64.b64encode(gzip.compress(data, mtime=0)).decode()
    parts = [b64[i:i + CHUNK] for i in range(0, len(b64), CHUNK)]
    return sha, parts


def page_webp(page, side=1600):
    from PIL import Image
    pix = page.get_pixmap(dpi=170)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    im.thumbnail((side, side))
    out = io.BytesIO()
    im.save(out, "WEBP", quality=62, method=4)
    return "data:image/webp;base64," + base64.b64encode(out.getvalue()).decode()


def build(rec, stu, pct, cls, pages_src):
    """Core and source payloads for one pupil."""
    meta = rec["meta"]
    week = meta.get("week") or meta.get("buoi")
    res = stu["result"]
    t = (res.get("tasks") or [{}])[0]
    task = t.get("task") or 1
    name = stu["name"]
    key = f"classwork-b{week:02d}-viet-tren-lop"
    ident = hashlib.sha256(f"{cls}|{name}".encode("utf-8")).hexdigest()
    paras = paragraphs_of(t.get("transcript"), stu.get("nameRead") or name)
    notes = []
    for a in t.get("annotations") or []:
        cat = GROUP.get(a.get("group"))
        q = (a.get("quote") or "").strip()
        hit = locate(paras, q) if q and cat else None
        if not hit:
            continue
        i, s0, s1 = hit
        notes.append({"id": f"a{len(notes) + 1}", "paragraphIndex": i, "quote": paras[i][s0:s1], "occurrence": 1, "category": cat,
                      "kind": a.get("kind") if a.get("kind") in ("error", "practice", "suggestion") else "suggestion",
                      "errorTypeLabel": a.get("label") or "", "title": a.get("label") or "",
                      "explanation": a.get("explanation") or "", "replacement": a.get("replacement") or "",
                      "start": s0, "end": s1})
    crits = []
    for k, v in (t.get("criteria") or {}).items():
        if k not in CRIT or not isinstance(v, dict):
            continue
        cid, label = CRIT[k]
        crits.append({"id": cid, "label": label, "status": status_of(v.get("band")), "evidence": [],
                      "comment": v.get("reason") or "", "action": v.get("whyNotHigher") or ""})
    revision = [p.strip() for p in re.split(r"\n\s*\n|\n", t.get("revisedText") or "") if p.strip()]
    qa = t.get("_qa") or {}
    words = (qa.get("classScore") or {}).get("wordCount") or qa.get("words")
    mn = (qa.get("classScore") or {}).get("minimum") or (150 if task == 1 else 250)
    overall = (t.get("overall") or "").strip()
    if pct.get("note"):
        overall = pct["note"]
    label = f"Buổi {week:02d} · Task {task} · Bài viết trên lớp"
    core = {
        "schemaVersion": 1,
        "student": {"name": name, "className": cls},
        "title": "Nhận xét bài viết trên lớp",
        "assignmentLabel": label,
        "promptVersion": "claude-scan/inclass-v1",
        "wordCount": words,
        "paragraphs": paras,
        "completion": {"status": "complete" if (words or 0) >= mn else "short", "missingParts": []},
        "overall": overall,
        "learningVerdict": f"{pct['pct']}% chất lượng",
        "learningCriteria": crits,
        "annotations": notes,
        "revision": {"paragraphs": revision, "paragraphSourceIndices": list(range(len(revision))),
                     "addedSections": [], "notes": []},
        "nextSteps": [],
        "transcriptionNote": (f"Số từ: {words}/{mn}." if words else ""),
        "className": cls, "parentStudentName": name, "studentIdentity": ident, "reviewKey": key, "part": "core",
        "task": {"text": f"Đề bài viết trên lớp Buổi {week} (Task {task}).", "images": []},
        "source": {"documentName": rec.get("title") or "", "pages": [{"deferred": True, "alt": f"Ảnh bài gốc {i + 1}"}
                                                                   for i in range(len(pages_src))]},
    }
    source = {"className": cls, "parentStudentName": name, "studentIdentity": ident, "reviewKey": key, "part": "source",
              "documentName": rec.get("title") or "",
              "pages": [{"src": src, "alt": f"Ảnh bài viết gốc {i + 1}/{len(pages_src)}"} for i, src in enumerate(pages_src)]}
    date = dt.datetime.strptime(meta["date"], "%d/%m/%Y").strftime("%Y-%m-%d")
    rows = []
    for part, obj in (("core", core), ("source", source)):
        sha, parts = chunks(obj)
        for i, p in enumerate(parts):
            rows.append([1, cls, ident, key, part, label, date, "published", sha, i, len(parts), "gzip-base64", p])
    return rows


def manual_override(runner, cls, meta, name):
    """Cô's hand re-grade (cfg manualInclass, override) wins over the machine's figure."""
    from zalo import key_of
    for m in runner.cfg.get("manualInclass") or []:
        if (m.get("override") and m.get("cls") == cls and str(m.get("date")) == meta.get("date")
                and key_of(m["name"]) == key_of(name) and m.get("week") == meta.get("week")):
            return m
    return None


def publish(scans_obj):
    """Send every published in-class IELTS paper not sent yet. Errors are kept per file, never fatal."""
    import scans
    runner = scans_obj.r
    allowed = set(runner.cfg.get("classworkClasses") or [])
    for fid, rec in scans_obj.st["files"].items():
        meta = rec.get("meta") or {}
        cls = meta.get("cls")
        if meta.get("kind") != "inclass" or cls not in allowed or not cls.startswith("IELTS"):
            continue
        todo = [s for s in rec.get("students", {}).values()
                if s.get("status") == "published" and s.get("result") and s.get("name") and not s.get("dash")]
        if not todo:
            continue
        try:
            import pymupdf as fitz
            doc = fitz.open(stream=scans_obj.g.download(fid), filetype="pdf")
            sid = runner.cfg["classes"][cls]
            if TAB not in runner.g.sheet_titles(sid):
                runner.g.add_hidden_sheet(sid, TAB, HEAD)
            for s in todo:
                t = (s["result"].get("tasks") or [{}])[0]
                m = manual_override(runner, cls, meta, s["name"])
                pct = {"pct": m["pct"], "note": m.get("note")} if m else {"pct": scans.ielts_pct(t)}
                srcs = [page_webp(doc[p - 1]) for p in s.get("pages") or [] if 0 < p <= len(doc)]
                rows = build(rec, s, pct, cls, srcs)
                runner.g.append_rows(sid, TAB, rows)
                s["dash"] = rows[0][8]
                scans_obj.tick("classwork_dash")
            rec.pop("dashError", None)
        except Exception as e:
            rec["dashError"] = f"{type(e).__name__}: {str(e)[:300]}"
            scans_obj.tick("classwork_dash_error")
