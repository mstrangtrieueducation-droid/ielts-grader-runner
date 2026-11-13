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
    week = meta.get("lesson") or meta.get("week") or meta.get("buoi")   # lesson: the lesson of the paper's day
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


# Cô 13/11 (IELTS 50, Thanh Hoa): a classmate's paper scanned right after a pupil's was read as part of her paper —
# the transcriber's English note and "em chép bài của bạn" reached the dash. Such pages are another pupil's paper:
# never shown, never counted, never mentioned to this pupil.
PAGE_HDR = re.compile(r"^\s*\[?Pages?\s*(\d+)(?:\s*[-–]\s*(\d+))?\s*\(([^)]*)\)[^\n]*", re.M)
FOREIGN = re.compile(r"not the (?:student|pupil)|classmate|another (?:student|pupil)|someone else|bài của bạn|"
                     r"không phải bài của em", re.I)
NOTE_PAGES = re.compile(r"(?:ảnh|trang)\s*(\d+)(?:\s*(?:và|–|-|,|đến)\s*(\d+))?[^.]{0,80}?"
                        r"(?:không phải bài của em|bài của bạn)", re.I)
ABOUT_OTHER = re.compile(r"[^.!?\n]*(?:bài của bạn|chép (?:lại )?bài|của bạn [A-ZĐ])[^.!?\n]*[.!?]?\s*")


def scrub(t):
    """(pages to drop, 1-based within the pupil's pages; the task without the other pupil's paper) or None."""
    import scans
    tr, drop, out = t.get("transcript") or "", set(), []
    for part in re.split(r"(?m)^(?=\s*\[?Pages?\s*\d)", tr):
        m = PAGE_HDR.match(part)
        if m and FOREIGN.search(m.group(3) + m.group(0)):
            drop |= set(range(int(m.group(1)), int(m.group(2) or m.group(1)) + 1))
            continue
        out.append(part)
    for m in NOTE_PAGES.finditer(t.get("transcriptionNote") or ""):
        drop |= set(range(int(m.group(1)), int(m.group(2) or m.group(1)) + 1))
    if not drop:
        return None
    new = json.loads(json.dumps(t))
    new["transcript"] = "".join(out).rstrip() + "\n"
    new["overall"] = ABOUT_OTHER.sub("", t.get("overall") or "").strip()
    new["transcriptionNote"] = ""
    cs = (new.get("_qa") or {}).get("classScore")
    if cs:
        w = scans.paper_words(new["transcript"])
        cs["wordCount"] = new["_qa"]["words"] = w
        cs["shortfall"] = max(0, cs["minimum"] - w)
        cs["shortfallPercent"] = round(100 * cs["shortfall"] / cs["minimum"], 1)
    return drop, new


def scrub_published(scans_obj, cache):
    """Papers already out with another pupil's pages: the tracker cell (only if it is still exactly ours), the dash
    card (withdrawn and sent again with the pupil's own photos) — once each."""
    runner = scans_obj.r
    for fid, rec in scans_obj.st["files"].items():
        meta = rec.get("meta") or {}
        cls = meta.get("cls") or ""
        if meta.get("kind") != "inclass" or not cls.startswith("IELTS") or cls not in runner.cfg["classes"]:
            continue
        for s in rec.get("students", {}).values():
            if s.get("scrubbed") or s.get("status") != "published" or not s.get("result"):
                continue
            tasks = s["result"].get("tasks") or []
            r = scrub(tasks[0]) if tasks else None
            if not r:
                continue
            drop, new = r
            try:
                old_text = scans_obj.cell_text(rec, s["result"])
                res = json.loads(json.dumps(s["result"]))
                res["tasks"][0] = new
                new_text = scans_obj.cell_text(rec, res)
                tr = runner.tracker(cls)
                row = tr.row_of(s["name"])
                cell = None
                if row and old_text:
                    tr._grid = None
                    vals = (runner.g.values(tr.id, f"'{tr.tab}'!A{row}:ZZ{row}") or [[]])[0]
                    hits = [i for i, v in enumerate(vals) if str(v).strip() == old_text.strip()]
                    if len(hits) == 1:
                        from run_writing import col_letter
                        cell = f"{col_letter(hits[0])}{row}"   # 0-based
                        tr.write(cell, new_text)
                        if tr.cell(cell).strip() != new_text.strip():
                            raise RuntimeError("readback")
                if s.get("dash"):
                    week = meta.get("lesson") or meta.get("week") or meta.get("buoi")
                    iso = dt.datetime.strptime(meta["date"], "%d/%m/%Y").date().isoformat()
                    withdraw(runner, cls, f"classwork-b{week:02d}-viet-tren-lop", iso, [s["name"]])
                    s.pop("dash", None)
                pages = list(s.get("pages") or [])
                s.update(resultBeforeScrub=s["result"], result=res, pagesAll=pages, scrubbedCell=cell or "not_found",
                         pages=[p for i, p in enumerate(pages, 1) if i not in drop], scrubbed=True)
                scans_obj.tick("classwork_scrubbed")
            except Exception as e:
                s["scrubError"] = f"{type(e).__name__}: {str(e)[:200]}"
                scans_obj.tick("classwork_scrub_error")


def lesson_of(runner, cls, date_vn, cache):
    """The class's lesson number on that day: the writing week whose closure day (policy cutoffDate = the next writing
    lesson) it is, plus one. IELTS 47: W28 closes 11/11 → the 11/11 paper is Buổi 29 (Cô 13/11). None if unknown."""
    try:
        iso = dt.datetime.strptime(date_vn, "%d/%m/%Y").date().isoformat()
    except (TypeError, ValueError):
        return None
    if cls not in cache:
        sid = runner.cfg["classes"][cls]
        found = {}
        if "_WRITING_POLICIES_V1" in runner.g.sheet_titles(sid):
            for r in runner.g.values(sid, "'_WRITING_POLICIES_V1'!A1:C300")[1:]:
                try:
                    pol = json.loads(r[2]) if len(r) > 2 and r[0] == cls else None
                except ValueError:
                    pol = None
                m = re.search(r"W0*(\d+)$", r[1]) if pol and pol.get("cutoffDate") else None
                if m:
                    found.setdefault(pol["cutoffDate"], set()).add(int(m.group(1)) + 1)
        cache[cls] = {d: n.pop() for d, n in found.items() if len(n) == 1}
    return cache[cls].get(iso)


def withdraw(runner, cls, key, iso, names):
    """Our rows of one session under a wrong lesson key: state → withdrawn (the viewer reads 'published' only)."""
    sid = runner.cfg["classes"][cls]
    rows = runner.g.values(sid, f"'{TAB}'!A1:H5000")
    idents = {hashlib.sha256(f"{cls}|{n}".encode("utf-8")).hexdigest() for n in names}
    hit = [i + 1 for i, r in enumerate(rows) if i and len(r) > 7 and r[1] == cls and r[3] == key and r[6] == iso
           and r[2] in idents and r[7] == "published"]
    runs = []
    for n in hit:
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    for a, b in runs:
        runner.g.set_block(sid, f"'{TAB}'!H{a}:H{b}", [["withdrawn"]] * (b - a + 1))
    return len(hit)


def relabel(scans_obj, cache):
    """Sessions sent under a lesson number that is not the lesson of that day are withdrawn and sent again."""
    runner = scans_obj.r
    allowed = set(runner.cfg.get("classworkClasses") or [])
    for fid, rec in scans_obj.st["files"].items():
        meta = rec.get("meta") or {}
        cls = meta.get("cls")
        if meta.get("kind") != "inclass" or cls not in allowed or not cls.startswith("IELTS"):
            continue
        lesson = lesson_of(runner, cls, meta.get("date"), cache)
        week = meta.get("lesson") or meta.get("week") or meta.get("buoi")   # the lesson it was sent under
        if not lesson or lesson == week:
            continue
        sent = [s for s in rec.get("students", {}).values() if s.get("dash")]
        try:
            iso = dt.datetime.strptime(meta["date"], "%d/%m/%Y").date().isoformat()
            if sent:
                n = withdraw(runner, cls, f"classwork-b{week:02d}-viet-tren-lop", iso, [s["name"] for s in sent])
                scans_obj.tick("classwork_relabel_withdrawn", n)
            meta["lesson"] = lesson   # meta week stays (Zalo picture and hand re-grades are keyed on it)
            for s in sent:
                s.pop("dash", None)
            scans_obj.tick("classwork_relabelled")
        except Exception as e:
            rec["dashError"] = f"relabel {type(e).__name__}: {str(e)[:200]}"
    done = scans_obj.st.setdefault("manualDash", [])
    from run_writing import BUNDLE
    path = BUNDLE / "classwork-manual" / "manual.json"
    for it in (json.loads(path.read_text(encoding="utf-8")) if path.exists() else []):
        k = f"{it['cls']}|{it['date']}|{it['name']}"
        if k not in done or it["cls"] not in runner.cfg["classes"]:
            continue
        lesson = lesson_of(runner, it["cls"], it["date"], cache)
        sent = scans_obj.st.setdefault("manualDashWeek", {}).get(k, it["week"])
        if lesson and lesson != sent:
            try:
                iso = dt.datetime.strptime(it["date"], "%d/%m/%Y").date().isoformat()
                withdraw(runner, it["cls"], f"classwork-b{sent:02d}-viet-tren-lop", iso, [it["name"]])
                done.remove(k)
                scans_obj.tick("classwork_relabelled_manual")
            except Exception as e:
                scans_obj.st.setdefault("manualDashError", {})[k] = f"relabel {type(e).__name__}: {str(e)[:200]}"


def manual_cell(scans_obj, it):
    """A paper Cô sent for hand grading → its tracker cell in the session's in-class column, in the class's % format,
    only while that cell is empty (Cô's own result is never overwritten)."""
    runner = scans_obj.r
    meta = {"cls": it["cls"], "date": it["date"], "week": it["week"], "kind": "inclass", "buoi": None, "n": None, "task": None}
    tr = runner.tracker(it["cls"])
    tr._grid = None
    tr.cached("A", 1)
    c = scans_obj.inclass_column(tr, tr._grid, meta, create=True)   # a session Cô sent as photos has no column yet
    row = tr.row_of(it["name"])
    if c is None or not row:
        scans_obj.st.setdefault("manualCell", {})[f"{it['cls']}|{it['date']}|{it['name']}"] = "no_column_or_row"
        return
    from run_writing import col_letter
    a1 = f"{col_letter(c)}{row}"
    if tr.cell(a1).strip():
        scans_obj.st.setdefault("manualCell", {})[f"{it['cls']}|{it['date']}|{it['name']}"] = "kept:" + a1
        return
    t = it["result"]["tasks"][0]
    g = {k: sum(1 for a in t.get("annotations") or [] if a.get("kind") == "error" and a.get("group") == k)
         for k in ("grammar", "vocab", "coherence")}
    cs = t["_qa"]["classScore"]
    text = (f"{it['pct']}% chất lượng\nĐã chữa: {g['grammar']} lỗi ngữ pháp, {g['vocab']} lỗi từ vựng, "
            f"{g['coherence']} lỗi mạch lạc/liên kết\n{t['overall'].strip()}\nSố từ: {cs['wordCount']}/{cs['minimum']}.")
    tr.write(a1, text)
    scans_obj.st.setdefault("manualCell", {})[f"{it['cls']}|{it['date']}|{it['name']}"] = a1
    scans_obj.tick("classwork_manual_cell")


def publish_manual(scans_obj, cache=None):
    """Papers Cô had graded by hand (not in a scan file): bundle classwork-manual/manual.json + their photos."""
    from run_writing import BUNDLE
    runner = scans_obj.r
    path = BUNDLE / "classwork-manual" / "manual.json"
    if not path.exists():
        return
    done = scans_obj.st.setdefault("manualDash", [])
    for it in json.loads(path.read_text(encoding="utf-8")):
        k = f"{it['cls']}|{it['date']}|{it['name']}"
        if k in done or it["cls"] not in runner.cfg["classes"]:
            continue
        try:
            sid = runner.cfg["classes"][it["cls"]]
            if TAB not in runner.g.sheet_titles(sid):
                runner.g.add_hidden_sheet(sid, TAB, HEAD)
            srcs = ["data:image/webp;base64," + base64.b64encode((path.parent / p).read_bytes()).decode() for p in it["pages"]]
            week = lesson_of(runner, it["cls"], it["date"], cache if cache is not None else {}) or it["week"]
            rec = {"meta": {"cls": it["cls"], "date": it["date"], "week": week, "kind": "inclass"}, "title": it["title"]}
            stu = {"name": it["name"], "result": it["result"]}
            rows = build(rec, stu, {"pct": it["pct"]}, it["cls"], srcs)
            withdraw(runner, it["cls"], rows[0][3], rows[0][6], [it["name"]])   # one card per paper
            runner.g.append_rows(sid, TAB, rows)
            done.append(k)
            scans_obj.st.setdefault("manualDashWeek", {})[k] = week
            try:
                if runner.cfg.get("manualCellWrite"):   # off: the in-class column was picked wrongly (IELTS 46, 13/11)
                    manual_cell(scans_obj, it)
            except Exception as e:
                scans_obj.st.setdefault("manualCellError", {})[k] = f"{type(e).__name__}: {str(e)[:200]}"
            scans_obj.tick("classwork_dash_manual")
        except Exception as e:
            scans_obj.st.setdefault("manualDashError", {})[k] = f"{type(e).__name__}: {str(e)[:200]}"


def publish(scans_obj):
    """Send every published in-class IELTS paper not sent yet. Errors are kept per file, never fatal."""
    import scans
    runner = scans_obj.r
    cache = {}
    try:   # another pupil's pages out of a paper first (Cô 13/11)
        scrub_published(scans_obj, cache)
    except Exception as e:
        scans_obj.tick(f"classwork_scrub_failed_{type(e).__name__}")
    try:   # the card goes on the lesson of the paper's day (Cô 13/11: the 11/11 paper is Buổi 29)
        relabel(scans_obj, cache)
    except Exception as e:
        scans_obj.tick(f"classwork_relabel_error_{type(e).__name__}")
    try:
        publish_manual(scans_obj, cache)
    except Exception:
        scans_obj.tick("classwork_dash_manual_error")
    allowed = set(runner.cfg.get("classworkClasses") or [])
    for fid, rec in scans_obj.st["files"].items():
        meta = rec.get("meta") or {}
        cls = meta.get("cls")
        if meta.get("kind") != "inclass" or cls not in allowed or not cls.startswith("IELTS"):
            continue
        todo = []
        for s in rec.get("students", {}).values():
            if s.get("status") != "published" or not s.get("result") or not s.get("name") or s.get("dash"):
                continue
            if s.get("skippedCells"):   # a re-read of a file already out: the tracker keeps the earlier result,
                s["dash"] = "kept_earlier"   # and so does the dash (never two cards for one paper)
                scans_obj.tick("classwork_kept_earlier")
                continue
            todo.append(s)
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
                pct = {"pct": m["pct"], "note": m.get("note")} if m else {"pct": scans.ielts_pct(t, cls)}
                srcs = [page_webp(doc[p - 1]) for p in s.get("pages") or [] if 0 < p <= len(doc)]
                rows = build(rec, s, pct, cls, srcs)
                # one card per paper: an earlier card of the same lesson for this pupil is withdrawn first
                withdraw(runner, cls, rows[0][3], rows[0][6], [s["name"]])
                runner.g.append_rows(sid, TAB, rows)
                s["dash"] = rows[0][8]
                scans_obj.tick("classwork_dash")
            rec.pop("dashError", None)
        except Exception as e:
            rec["dashError"] = f"{type(e).__name__}: {str(e)[:300]}"
            scans_obj.tick("classwork_dash_error")
