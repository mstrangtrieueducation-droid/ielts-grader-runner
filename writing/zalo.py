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
    """On the lesson day: every piece handed in has its result, or it is 17:00 (send what there is)."""
    day = class_day(runner, cls, deadline)
    if not (day <= now.astimezone(VN).date() <= day + dt.timedelta(days=1)):   # missed by > 1 day: not sent late
        return False
    if now.astimezone(VN).hour >= 17 or now.astimezone(VN).date() > class_day(runner, cls, deadline):
        return True
    return not any(s.get("className") == cls and s.get("assignment") == code and s.get("status") in PENDING
                   for s in runner.state.get("subs", {}).values())


def make(runner, now=None):
    """Each cycle (Cô 11/11): a class's homework picture goes out on its lesson day (the day after the deadline),
    08:00–20:00, once the class has its results (17:00 at the latest), in its own mail. A week without homework
    has no deadline, so nothing is sent. Returns [(class, title)] made this time."""
    now = now or dt.datetime.now(VN)
    if not (8 <= now.astimezone(VN).hour < 20):
        return []
    done = runner.state.setdefault("zaloDone", [])
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
            if not col or not deadline or not (deadline < now <= deadline + WINDOW):
                continue
            if not ready(runner, cls, code, deadline, now):
                continue
            pupils, crit = collect(runner, cls, code, deadline)
            if not pupils:
                continue
            title = "Bài viết " + code.rsplit("-", 1)[-1]
            import zalo_draw   # Cô 11/11: quality + charts, per-pupil band shown, no class-wide notes
            png = zalo_draw.draw({"cls": cls, "title": title, "deadline": deadline, "made": now, "total": len(pupils),
                                  "pupils": pupils, "crit": crit, "notes": [], "show_band": True,
                                  "kind": "BÀI TẬP VỀ NHÀ"})
            b64 = base64.b64encode(png).decode()
            parts = [b64[i:i + CHUNK] for i in range(0, len(b64), CHUNK)][:10]
            sid = runner.cfg["classes"][cls]
            ensure_tab(runner.g, sid)
            runner.g.append_rows(sid, TAB, [[key + "|" + now.strftime("%Y%m%d%H%M"), cls, f"{cls} – {title}",
                                             now.strftime("%d/%m/%Y %H:%M"), ""] + parts])
            done.append(key)
            del done[:-400]
            made.append((cls, title))
            runner.tick("zalo_picture")
    if made:
        import report
        report.zalo_mail(runner, made, now)
    return made


FINAL = ("published", "dropped", "unidentified")


def make_inclass(runner, scans_state, now=None):
    """In-class writing (Cô 11/11): one picture per scanned in-class file once every paper in it has its result,
    08:00–20:00, own mail. Returns [(class, title)]."""
    import scans as sc
    now = now or dt.datetime.now(VN)
    if not (8 <= now.astimezone(VN).hour < 20):
        return []
    done = runner.state.setdefault("zaloDone", [])
    made = []
    for fid, rec in (scans_state or {}).get("files", {}).items():
        meta = rec.get("meta") or {}
        if meta.get("kind") != "inclass" or rec.get("status") != "graded" or f"scan|{fid}" in done:
            continue
        studs = [s for s in rec.get("students", {}).values()]
        if not studs or any(s.get("status") not in FINAL for s in studs):
            continue
        cls = meta["cls"]
        if cls not in runner.cfg["classes"]:
            continue
        try:   # Cô 11/11: in-class picture the day after the lesson
            lesson = dt.datetime.strptime(meta["date"], "%d/%m/%Y").date()
        except Exception:
            continue
        if now.astimezone(VN).date() < lesson + dt.timedelta(days=1):
            continue
        spec = sc.pack_for(meta) or {}
        scored = spec.get("schema") == "ielts"
        got = {key_of(s["name"]): s for s in studs if s.get("name") and s.get("status") == "published"}
        pupils, crit = [], {}
        for n in roster(runner, cls):
            s = got.get(key_of(n))
            p = {"name": nice(n), "has": bool(s), "band": None, "level": None, "done": bool(s)}
            if s:
                res = s.get("result") or {}
                if scored:
                    for t in res.get("tasks", []):
                        ca = ((t.get("_qa") or {}).get("classScore") or {}).get("classAssessment") or {}
                        if ca.get("overallBand") is not None:
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
        title = (f"Đoạn văn Buổi {meta['buoi']}" if meta.get("buoi") else f"Bài viết W{meta.get('week')}")
        if meta.get("task"):
            title += f" · Task {meta['task']}"
        import zalo_draw
        png = zalo_draw.draw_inclass({"cls": cls, "title": title, "date": meta["date"], "made": now, "pupils": pupils,
                                      "crit": {k: sum(v) / len(v) for k, v in crit.items()}, "scored": scored,
                                      "unknown": sum(1 for s in studs if s.get("status") == "unidentified")})
        b64 = base64.b64encode(png).decode()
        parts = [b64[i:i + CHUNK] for i in range(0, len(b64), CHUNK)][:10]
        sid = runner.cfg["classes"][cls]
        ensure_tab(runner.g, sid)
        runner.g.append_rows(sid, TAB, [[f"scan|{fid}|" + now.strftime("%Y%m%d%H%M"), cls, f"{cls} – {title}",
                                         now.strftime("%d/%m/%Y %H:%M"), ""] + parts])
        done.append(f"scan|{fid}")
        del done[:-400]
        made.append((cls, title))
        runner.tick("zalo_picture_inclass")
    if made:
        import report
        report.zalo_mail(runner, made, now)
    return made
