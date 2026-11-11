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
WINDOW = dt.timedelta(days=3)          # deadlines further back are history: no picture
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
    for r in vals[5:]:
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


def ready(runner, cls, code, deadline, now):
    """Every piece handed in for that class & week has its result (or 36 h passed since the deadline)."""
    if now > deadline + dt.timedelta(hours=36):
        return True
    return not any(s.get("className") == cls and s.get("assignment") == code and s.get("status") in PENDING
                   for s in runner.state.get("subs", {}).values())


def make(runner, now=None):
    """Each cycle (Cô 11/11): a class's picture is made as soon as the whole class has its results, between
    08:00 and 20:00 only, and sent to Cô in its own mail. Returns [(class, title)] made this time."""
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
