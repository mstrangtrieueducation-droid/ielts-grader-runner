"""Picture for the class Zalo group: who handed in the writing homework on time, late, or not yet.

Cô 11/11: one picture per class and week, made at the first report after the deadline and attached to her
report e-mail, so she can forward it to the class group. Cô chose: submission + notebook verdict + band of
each pupil, class averages per criterion, praise list (drawing in zalo_draw.py).

The PNG never touches the public repo: it is stored (base64, split over cells) in a hidden tab of the class's
own tracker (which already holds these names and statuses); the public report only says which classes have
a new picture, and Cô's mail script opens those trackers, attaches the pictures and marks the rows as sent.
"""
import base64
import json
import math
import datetime as dt
import io
import re
import unicodedata
from pathlib import Path

VN = dt.timezone(dt.timedelta(hours=7))
TAB = "Ảnh Zalo"
HEAD = ["id", "lớp", "tiêu đề", "tạo lúc", "đã gửi"] + [f"phần {i}" for i in range(1, 11)]
CHUNK = 45000
WINDOW = dt.timedelta(days=8)          # the lesson day is within a week of the deadline
FONTS = Path(__file__).parent / "fonts"


def nice(name):
    """'NGUYỄN THÀNH AN' → 'Nguyễn Thành An' (name as written in the class list)."""
    return " ".join(w[:1].upper() + w[1:].lower() for w in name.split())


def key_of(name):
    s = unicodedata.normalize("NFC", re.sub(r"\s+", " ", name.strip().upper()))
    return s


def parse_vn(s):
    for f in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return dt.datetime.strptime(s.strip(), f).replace(tzinfo=VN)
        except Exception:
            pass
    return None


def roster(runner, cls):
    """Pupils on the class list, in list order: rows whose column A is a number and column B a name."""
    tr = runner.tracker(cls)
    vals = runner.g.values(tr.id, f"'{tr.tab}'!A1:B200") or []
    out = []
    for r in vals[1:]:
        if len(r) >= 2 and str(r[0]).strip().isdigit() and r[1].strip():
            out.append(r[1].strip().split("\n")[0])
    return out


def band_of(sub):
    """Overall band of the corrected essay(s): mean of the four criteria, to the nearest half band."""
    er = sub.get("essayResult")
    if isinstance(er, str):
        try:
            er = json.loads(er)
        except Exception:
            er = None
    crit, overall = {}, []
    for e in (er or {}).get("essays") or []:
        c = {("TR" if k in ("TA_TR", "TA", "TR") else k): (v or {}).get("band") for k, v in (e.get("criteria") or {}).items()}
        c = {k: v for k, v in c.items() if isinstance(v, (int, float))}
        if len(c) == 4:
            overall.append(sum(c.values()) / 4)
            for k, v in c.items():
                crit.setdefault(k, []).append(v)
    if not overall:
        return None, {}
    return math.floor(sum(overall) / len(overall) * 2 + 0.5) / 2, {k: sum(v) / len(v) for k, v in crit.items()}


def collect(runner, cls, code, deadline):
    """Pupils on the class list (list order) with: submission status, notebook verdict, essay band."""
    best = {}
    for s in runner.state.get("subs", {}).values():
        if s.get("className") != cls or s.get("assignment") != code:
            continue
        k = key_of(s.get("student", ""))
        t = parse_vn(s.get("firstAt") or s.get("submittedAt") or "")
        b = best.setdefault(k, {"t": None, "nb": None, "band": None, "crit": {}})
        if t and (b["t"] is None or t < b["t"]):
            b["t"] = t
        if s.get("status") == "published":
            b["nb"] = s.get("verdict") or b["nb"]
            band, crit = band_of(s)
            if band is not None:
                b["band"], b["crit"] = band, crit
    bare = lambda x: "".join(c for c in unicodedata.normalize("NFD", x) if not unicodedata.combining(c)).replace("Đ", "D")
    by_bare = {}
    for k, v in best.items():
        by_bare.setdefault(bare(k), []).append(v)
    pupils, crit = [], {}
    for n in roster(runner, cls):
        k = key_of(n)
        b = best.get(k) or (by_bare[bare(k)][0] if len(by_bare.get(bare(k), [])) == 1 else None)
        if not b or not b["t"]:
            pupils.append({"name": nice(n), "sub": "none", "nb": None, "band": None})
            continue
        sub = "on" if b["t"] <= deadline else "late"
        pupils.append({"name": nice(n), "sub": sub, "nb": b["nb"], "band": b["band"]})
        for c, v in b["crit"].items():
            crit.setdefault(c, []).append(v)
    return pupils, {c: sum(v) / len(v) for c, v in crit.items()}


# ---------------------------------------------------------------- run
def store(runner, cls, key, title, pages, now):
    """One row per page in the class tracker's hidden tab; file names sort in page order."""
    sid = runner.cfg["classes"][cls]
    ensure_tab(runner.g, sid)
    rows = []
    for k, png in enumerate(pages, 1):
        b64 = base64.b64encode(png).decode()
        parts = [b64[i:i + CHUNK] for i in range(0, len(b64), CHUNK)][:10]
        name = title + (f" ({k}-{len(pages)})" if len(pages) > 1 else "")
        rows.append([f"{key}|{now:%Y%m%d%H%M}|{k}", cls, name, now.strftime("%d/%m/%Y %H:%M"), ""] + parts)
    runner.g.append_rows(sid, TAB, rows)


def ensure_tab(g, sid):
    if TAB not in g.sheet_titles(sid):
        g.add_hidden_sheet(sid, TAB, HEAD)


PENDING = ("new", "submitted", "graded", "essay_new", "essay_submitted")


SCHEDULE = "1NHZ6N2fp-ptJ9p7_HN65fFSs-A_lohiGVTwndm3ud6Q"   # "* SCHEDULE updated 7/2026" (weekly tabs)
TAB_RE = re.compile(r"^\s*(\d{2})\.(\d{2})\.(\d{4})\s*-\s*(\d{2})\.(\d{2})\.(\d{4})\s*$")


def lessons(runner):
    """{class: sorted [dates]} of Cô Trang's own lessons that take place ('Học'), from the centre's weekly
    schedule tabs (DAY | TIME | … | CLASS | TEACHER | … | CLASS STATUS). Read once per run."""
    if getattr(runner, "_lessons", None) is not None:
        return runner._lessons
    out = {}
    sid = runner.cfg.get("scheduleSheet") or SCHEDULE
    try:
        tabs = runner.g.sheet_titles(sid)
        today = dt.datetime.now(VN).date()
        for t in tabs:
            m = TAB_RE.match(t)
            if not m:
                continue
            a = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if not (today - dt.timedelta(days=21) <= a <= today + dt.timedelta(days=14)):
                continue
            rows = runner.g.values(sid, f"'{t}'!A1:M400") or []
            head = next((i for i, r in enumerate(rows) if len(r) > 4 and str(r[0]).strip().upper() == "DAY"
                         and str(r[3]).strip().upper() == "CLASS"), None)
            if head is None:
                continue
            day = None
            for r in rows[head + 1:]:
                r = list(r) + [""] * (13 - len(r))
                dm = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", str(r[0]))
                if dm:
                    day = dt.date(int(dm.group(3)), int(dm.group(2)), int(dm.group(1)))
                cls = runner.class_of(r[3]) if hasattr(runner, "class_of") else str(r[3]).strip()
                if (day and re.fullmatch(r"(IELTS|FIGHTER) \d+", cls) and "TRANG TRIEU" in str(r[4]).upper()
                        and str(r[12]).strip().lower() == "học" and not re.search(r"\d+\.\d+", str(r[3]))):
                    out.setdefault(cls, set()).add(day)
    except Exception:
        runner.tick("schedule_read_failed")
    runner._lessons = {k: sorted(v) for k, v in out.items()}
    return runner._lessons


def class_day(runner, cls, deadline):
    """Cô 11/11: the homework picture goes out on the day Cô teaches that class (centre schedule), the first
    such lesson after the deadline. Without schedule data: cfg 'classDays' (weekday numbers, Monday = 0),
    else the day after the deadline."""
    after = deadline.astimezone(VN).date()
    for d in lessons(runner).get(cls, []):
        if d > after:
            return d
    days = (runner.cfg.get("classDays") or {}).get(cls)
    d = after + dt.timedelta(days=1)
    if days:
        while d.weekday() not in days:
            d += dt.timedelta(days=1)
    return d


def ready(runner, cls, code, deadline, now):
    """From the lesson day on (Cô 11/11): only once EVERY piece handed in has its result — never a picture
    with work still being graded. Given up 2 days after the lesson day."""
    day = class_day(runner, cls, deadline)
    if not (day <= now.astimezone(VN).date() <= day + dt.timedelta(days=2)):
        return False
    return not any(s.get("className") == cls and s.get("assignment") == code and s.get("status") in PENDING
                   for s in runner.state.get("subs", {}).values())


def make(runner, now=None):
    """Each cycle (Cô 11/11): a class's homework picture goes out on its lesson day (the day after the deadline),
    08:00–20:00, once EVERY piece handed in has its result, in its own mail. A week without homework
    has no deadline, so nothing is sent. Returns [(class, title)] made this time."""
    now = now or dt.datetime.now(VN)
    force = set(runner.cfg.get("zaloForce") or [])   # Cô asks for a picture now: "IELTS 47|IELTS-WRITING-W28"
    done = runner.state.setdefault("zaloDone", [])
    redone = runner.state.setdefault("zaloRedone", [])
    for k in runner.cfg.get("zaloRedo") or []:   # a picture sent wrongly: make it again, once
        if k in done and k not in redone:
            done.remove(k)
            redone.append(k)
    if not (8 <= now.astimezone(VN).hour < 20) and not (force - set(done)):
        return []
    made = []
    for cls in sorted(runner.cfg["classes"]):
        for a in runner.cfg["assignments"]:
            code = a["code"]
            if a.get("classes", "*") != "*" and cls not in a["classes"]:
                continue
            key = f"{cls}|{code}"
            if key in done:
                continue
            try:
                col, deadline = runner.tracker(cls).column(code)
            except Exception:
                continue
            if not col or not deadline:
                continue
            if key not in force:
                if not (8 <= now.astimezone(VN).hour < 20) or not (deadline < now <= deadline + WINDOW):
                    continue
                if not ready(runner, cls, code, deadline, now):
                    continue
            pupils, crit = collect(runner, cls, code, deadline)
            if not pupils:
                continue
            nb_only = a.get("mode") == "notebook_only"   # weeks with only the lecture notebook, no essay
            title = ("Vở chép bài giảng " if nb_only else "Bài viết ") + code.rsplit("-", 1)[-1]
            import zalo_draw   # Cô 11/11: quality + charts, per-pupil band shown, no class-wide notes
            png = zalo_draw.draw({"cls": cls, "title": title, "deadline": deadline, "made": now, "total": len(pupils),
                                  "pupils": pupils, "crit": {} if nb_only else crit, "notes": [],
                                  "show_band": not nb_only, "notebook_only": nb_only,
                                  "kind": "BÀI TẬP VỀ NHÀ"})
            store(runner, cls, key, f"{cls} – {title}", png, now)
            done.append(key)
            del done[:-400]
            made.append((cls, title))
            runner.tick("zalo_picture")
    if made:
        import report
        for i, item in enumerate(made):   # Cô 11/11: one mail per class, so all its pages save in one go
            report.zalo_mail(runner, [item], now, i)
    return made


FINAL = ("published", "dropped", "unidentified", "renamed")
GROUPS = ("vocab", "grammar", "coherence")


def code_names():
    """Fighter error codes → short Vietnamese names, read from the rulebook table in the (decrypted) pack."""
    try:
        from run_writing import BUNDLE
        head = (BUNDLE / "packs" / "TEST-FIGHTER" / "head.md").read_text(encoding="utf-8")
    except Exception:
        return {}
    out = {}
    for m in re.finditer(r"^\|\s*((?:QL|VOC|GRA|COH)-[A-Z]+)\s*\|\s*([^|]+)\|", head, re.M):
        name = re.sub(r"\s*\(.*?\)", "", m.group(2)).replace("**", "").split(";")[0].strip().rstrip(",.")
        out[m.group(1)] = name[:1].upper() + name[1:]
    return out


SEVERITY = {"S1": 1, "S2": 2, "S3": 4}


def quality_pct(errors, words, free_length=False):
    """Cô 12/11: '% chất lượng' of an unscored Fighter paragraph, computed by code from the corrections:
    100 − 2.5 × (S1 + 2·S2 + 4·S3 per 150 words), scaled down when shorter than 140 words. Fitted on 124 graded
    Fighter tests against Cô's /1 rubric (mean gap ≈ 10 points)."""
    w = words or 0
    pen = sum(SEVERITY.get(e.get("severity"), 1) for e in errors or [])
    pct = 100 - 2.5 * pen * 150 / max(w, 100)
    if not free_length and w < 140:
        pct *= w / 140
    return max(15, min(100, round(pct)))   # floor: a written paragraph never shows as 0%


def paper_stats(res, fighter, free_length=False):
    """Per pupil, counted from the graded result (free): words and errors per group (+ class conventions)."""
    st = {"words": None, "vocab": 0, "grammar": 0, "coherence": 0, "ql": 0, "codes": [], "pct": None}
    if fighter:
        st["words"] = (res.get("_qa") or {}).get("words")
        st["pct"] = quality_pct(res.get("errors"), st["words"], free_length)
        for e in res.get("errors") or []:
            code = str(e.get("code") or "")
            if code.startswith("QL"):
                st["ql"] += 1
            elif e.get("group") in GROUPS:
                st[e["group"]] += 1
            st["codes"].append(code)
    else:
        w = 0
        for t in res.get("tasks") or []:
            w += ((t.get("_qa") or {}).get("classScore") or {}).get("wordCount") or 0
            for a in t.get("annotations") or []:
                if a.get("kind") == "error" and a.get("group") in GROUPS:
                    st[a["group"]] += 1
                    st["codes"].append(str(a.get("label") or "").strip().lower())
        st["words"] = w or None
    return st


def class_notes(runner, cls, title, fighter, comments, top):
    """Short class-level comment written by Haiku from the comments already given (no names)."""
    if not comments:
        return ""
    try:
        import claude_worker as cw
        text = "\n".join(f"Bài {i + 1}: {c.strip()[:900]}" for i, c in enumerate(comments))
        common = "; ".join(f"{n} ({k} bài)" for n, k in top)
        prompt = (f"Nhận xét đã chấm cho từng bài viết trên lớp ({'đoạn văn học thuật' if fighter else 'bài viết IELTS'}, {title}). "
                  f"Lỗi gặp nhiều nhất (máy đếm): {common}.\n\n{text}\n\n"
                  "Tóm tắt cho phụ huynh đúng 3 dòng, mỗi dòng một câu ngắn (tối đa 28 từ), viết như giáo viên ghi sổ: "
                  "thẳng, cụ thể, nêu đúng cấu trúc/lỗi có trong nhận xét.\n"
                  "Làm tốt: …\nCần sửa: …\nBuổi sau: …\n"
                  "Không xưng 'Cô', không dùng 'các con lớp …', không 'mong', không 'hãy', không tính từ khen chung chung "
                  "(tốt, khá tốt, ấn tượng…) trừ khi kèm ví dụ cụ thể, không nêu tên học sinh, không cho điểm, không bịa. "
                  "Chỉ trả về 3 dòng đó.")
        r = cw.client().messages.create(model="claude-haiku-5-5", max_tokens=500, thinking={"type": "disabled"},
                                        messages=[{"role": "user", "content": prompt}])
        u = r.usage.model_dump()
        c = cw.cost_usd("claude-haiku-5-5", u)
        cw.ledger({"at": cw.now_iso(), "category": f"{cls} · Nhận xét chung ảnh Zalo", "step": "zalo-notes",
                   "model": "claude-haiku-5-5", "usage": u, "usd": c, "vnd": round(c * cw.USD_VND)})
        out = " ".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip()
        return re.sub(r"[*_#`]+", "", out)   # plain text on the picture
    except Exception as e:
        runner.tick(f"zalo_notes_failed_{type(e).__name__}")
        return ""
ZALO_SINCE = dt.date(2026, 11, 9)   # papers before the pictures existed get none


def make_inclass(runner, scans_state, now=None):
    """In-class writing (Cô 11/11): one picture per scanned in-class file once every paper in it has its result,
    08:00–20:00, own mail. Returns [(class, title)]."""
    import scans as sc
    now = now or dt.datetime.now(VN)
    if not (8 <= now.astimezone(VN).hour < 20) or runner.cfg.get("zaloInclassHold"):   # hold: Cô checks a sample first
        return []
    done = runner.state.setdefault("zaloDone", [])
    made = []
    # Cô 12/11: a supplementary scan ("… bổ sung") of the same session joins the same picture
    sessions = {}
    for fid, rec in (scans_state or {}).get("files", {}).items():
        meta = rec.get("meta") or {}
        if meta.get("kind") not in ("inclass", "test"):
            continue
        skey = "|".join(str(meta.get(k)) for k in ("cls", "kind", "date", "n", "buoi", "week", "task"))
        sessions.setdefault(skey, []).append((fid, rec))
    for skey, files in sessions.items():
        fid, rec = files[0]
        meta = rec.get("meta") or {}
        if (f"scan|{skey}" in done or any(f"scan|{f}" in done for f, _ in files)
                or any(r.get("status") not in ("graded", "teacher_done") for _, r in files)):
            continue   # Cô 11/11: every graded paper (in-class writing and paper tests) gets its picture
        if any(r.get("status") == "teacher_done" for _, r in files):
            continue
        studs = [s for _, r in files for s in r.get("students", {}).values()]
        if not studs or any(s.get("status") not in FINAL for s in studs):
            continue
        cls = meta["cls"]
        if cls not in runner.cfg["classes"]:
            continue
        try:   # Cô 11/11: in-class picture the day after the lesson
            lesson = dt.datetime.strptime(meta["date"], "%d/%m/%Y").date()
        except Exception:
            continue
        if now.astimezone(VN).date() < lesson + dt.timedelta(days=1) or lesson < ZALO_SINCE:
            continue
        spec = sc.pack_for(meta) or {}
        test = meta["kind"] == "test"
        fighter = cls.startswith("FIGHTER")
        scored = spec.get("schema") == "ielts" or (test and fighter)
        unit = "/1" if fighter else "band"
        got = {key_of(s["name"]): s for s in studs if s.get("name") and s.get("status") == "published"}
        pupils, crit, comments = [], {}, []
        for n in roster(runner, cls):
            s = got.get(key_of(n))
            p = {"name": nice(n), "has": bool(s), "band": None, "level": None, "done": bool(s)}
            if s:
                res = s.get("result") or {}
                p["stats"] = paper_stats(res, fighter, meta.get("buoi") == 13)
                if not test:
                    comments.append(res.get("overall") or " ".join(t.get("overall", "") for t in res.get("tasks") or []))
                if scored and fighter:
                    tong = (res.get("score") or {}).get("tong")
                    p["band"] = float(tong) if isinstance(tong, (int, float)) else None
                elif scored:
                    if res.get("_overall") is not None:
                        p["band"] = float(res["_overall"])
                    for t in res.get("tasks", []):
                        ca = ((t.get("_qa") or {}).get("classScore") or {}).get("classAssessment") or {}
                        if ca.get("overallBand") is not None and res.get("_overall") is None:
                            p["band"] = float(ca["overallBand"])
                        for k, v in (ca.get("criteria") or {}).items():
                            k = "TR" if k in ("TA", "TR") else k
                            if isinstance(v, (int, float)):
                                crit.setdefault(k, []).append(v)
                else:
                    p["level"] = (res.get("_qa") or {}).get("level")
            pupils.append(p)
        if not pupils:
            continue
        if test:
            title = f"Kiểm tra lần {meta['n']}"
        else:
            title = (f"Đoạn văn Buổi {meta['buoi']}" if fighter else f"Bài viết Buổi {meta.get('week')}")
        if meta.get("task"):
            title += f" · Task {meta['task']}"
        summary = {}
        if not test:   # Cô 12/11: in-class writing — class stats (free) + a short class comment (Haiku) + per-pupil stats
            names = code_names() if fighter else {}
            per_code = {}
            for p in pupils:
                for c in set((p.get("stats") or {}).get("codes") or []):
                    if c:
                        per_code[c] = per_code.get(c, 0) + 1
            top = sorted(per_code.items(), key=lambda kv: -kv[1])[:4]
            top = [((names.get(c) or c) if fighter else c[:1].upper() + c[1:], k) for c, k in top]
            done_n = sum(1 for p in pupils if p["has"])
            tot = {g: sum((p.get("stats") or {}).get(g, 0) for p in pupils) for g in GROUPS + ("ql",)}
            ws = [p["stats"]["words"] for p in pupils if p.get("stats") and p["stats"].get("words")]
            summary = {"top": top, "n": done_n, "totals": tot, "words": ws, "fighter": fighter,
                       "note": class_notes(runner, cls, title, fighter, comments, top)}
        import zalo_draw
        png = zalo_draw.draw_inclass({"summary": summary,"cls": cls, "title": title, "date": meta["date"], "made": now, "pupils": pupils,
                                      "crit": {k: sum(v) / len(v) for k, v in crit.items()}, "scored": scored,
                                      "kind": "Bài kiểm tra" if test else "Bài viết trên lớp", "unit": unit,
                                      "unknown": sum(1 for s in studs if s.get("status") == "unidentified")})
        store(runner, cls, f"scan|{skey}", f"{cls} – {title}", png, now)
        done.append(f"scan|{skey}")
        del done[:-400]
        made.append((cls, title))
        runner.tick("zalo_picture_inclass")
    if made:
        import report
        for i, item in enumerate(made):   # Cô 11/11: one mail per class, so all its pages save in one go
            report.zalo_mail(runner, [item], now, i)
    return made
