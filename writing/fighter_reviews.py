"""Fighter in-class paragraph reviews on the parent dashboard (Cô 14/11/2026: "chấm xong phải lên dash").

The Fighter dashboard shows a lesson's in-class review (bài chữa) from the class Apps Script reader
fighterParagraphReadV1_. That reader now also reads the tracker tab _FIGHTER_PARAGRAPH_REVIEWS_V1, one row per
review:   A reviewId | B studentName | C lessonDate (yyyy-mm-dd) | D state | E… the review JSON in chunks.
Only rows in state "published" are shown. The review JSON has the shape the dashboard panel
(dashboard-ui/fighter-paragraph-review-v1.js) reads: originalEssay, corrections[{quote, correction, explanation,
category}], suggestedRevision, overall, … and assignmentCode = the lesson's DVHT-S<n>-<ddmmyyyy> id.
"""
import hashlib
import json
import re

TAB = "_FIGHTER_PARAGRAPH_REVIEWS_V1"
WIDTH = 24
HEAD = ["reviewId", "studentName", "lessonDate", "state"] + [f"json{i}" for i in range(1, WIDTH - 3)]
CHUNK = 45000
CATEGORY = {"grammar": "grammar", "vocab": "vocabulary", "vocabulary": "vocabulary", "coherence": "coherence"}


def _plain(text):
    """Tracker comments mark words as *word*; the dashboard shows text as typed, so quote marks instead."""
    return re.sub(r"\*([^*\n]+)\*", r"“\1”", (text or "").strip())


def _words(text):
    return len(re.findall(r"[A-Za-z0-9’']+", text or ""))


def review_of(meta, stu):
    """Dashboard review for one graded in-class paragraph (scans state record + pupil), or None."""
    import classwork
    res = stu.get("result") or {}
    if not res.get("transcript") or not stu.get("name"):
        return None
    d, m, y = meta["date"].split("/")
    test = meta.get("kind") == "test"
    buoi = int((meta.get("n") if test else meta.get("buoi")) or 0)
    paras = classwork.paragraphs_of(res["transcript"], stu.get("nameRead") or stu["name"])
    essay = "\n\n".join(paras)
    corrections = []
    for e in res.get("errors") or []:
        quote = (e.get("quote") or "").strip()
        at = classwork.locate([essay], quote) if quote else None
        if at:
            quote = essay[at[1]:at[2]]
        expl = (e.get("explanation") or "").strip().split("\n")[0].strip()   # first paragraph: the real explanation
        corrections.append({"index": len(corrections) + 1, "category": CATEGORY.get(e.get("group"), "grammar"),
                            "quote": quote, "correction": (e.get("replacement") or "").strip(), "explanation": _plain(expl)})
    revision = (res.get("revision") or "").strip()
    tag = f"kt{buoi:02d}" if test else f"s{buoi}"
    rid = f"{meta['cls'].lower().replace(' ', '')}-dvht-{tag}-{y}{m}{d}-" + hashlib.sha1(stu["name"].encode()).hexdigest()[:8]
    sc = res.get("score") if isinstance(res.get("score"), dict) else None
    extra = {}
    if test:   # KT card on the dashboard: score /1 with the four criteria (0,25 each)
        if not sc or not isinstance(sc.get("tong"), (int, float)):
            return None
        extra = {"assessmentNumber": buoi, "assessmentDate": f"{y}-{m}-{d}", "score": sc["tong"],
                 "scoreBreakdown": [{"criterion": c.get("ten", ""), "score": c.get("diem", 0), "maxScore": 0.25,
                                     "rationale": _plain(c.get("bangChung"))} for c in sc.get("tieuChi") or []]}
    return dict({
        "reviewId": rid, "className": meta["cls"], "studentName": stu["name"], "lessonNumber": buoi,
        "lessonDate": f"{y}-{m}-{d}", "assignmentCode": f"DVHT-{'KT%02d' % buoi if test else 'S%d' % buoi}-{d}{m}{y}",
        "scored": bool(test), "score": None, "sourcePages": stu.get("pages") or [],
        "originalEssay": essay, "originalWordCount": (res.get("_qa") or {}).get("words") or _words(essay),
        "transcriptionNotes": "", "overall": _plain(res.get("overall")),
        "corrections": corrections, "suggestedRevision": revision, "suggestedRevisionWordCount": _words(revision),
        "revisionNotes": f"Bản sửa {_words(revision)} từ; giữ ý của em và sửa những lỗi đã chữa.", "revisionAnalysis": [],
        "learningTransfer": [],
    }, **extra)


def _row(r, state="published"):
    data = json.dumps(r, ensure_ascii=False, separators=(",", ":"))
    row = [r["reviewId"], r["studentName"], r["lessonDate"], state] + [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)]
    if len(row) > WIDTH:
        raise ValueError("REVIEW_TOO_LARGE")
    return row + [""] * (WIDTH - len(row))   # blanks clear the chunks of a longer earlier version


def publish(g, sid, reviews):
    """Add or replace the given reviews (by reviewId) in the class tracker's store tab. Returns the count written."""
    if not reviews:
        return 0
    if TAB not in g.sheet_titles(sid):
        g.add_hidden_sheet(sid, TAB, HEAD)
    have = g.values(sid, f"'{TAB}'!A1:A2000")
    at = {row[0]: i + 1 for i, row in enumerate(have) if row}
    new = []
    for r in reviews:
        row = _row(r)
        if r["reviewId"] in at:
            n = at[r["reviewId"]]
            g.set_row(sid, f"'{TAB}'!A{n}", row)
        else:
            new.append(row)
    if new:
        g.append_rows(sid, TAB, new)
    return len(reviews)
