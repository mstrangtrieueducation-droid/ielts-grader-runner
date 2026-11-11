"""Picture for the class Zalo group: who handed in the writing homework on time, late, or not yet.

Cô 11/11: one picture per class and week, made at the first report after the deadline and attached to her
report e-mail, so she can forward it to the class group. Submission status only — no scores or comments,
since every parent in the group sees it.

The PNG never touches the public repo: it is stored (base64, split over cells) in a hidden tab of the class's
own tracker (which already holds these names and statuses); the public report only says which classes have
a new picture, and Cô's mail script opens those trackers, attaches the pictures and marks the rows as sent.
"""
import base64
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


def status(runner, cls, code, deadline):
    on, late = [], []
    handed = {}
    for s in runner.state.get("subs", {}).values():
        if s.get("className") != cls or s.get("assignment") != code:
            continue
        t = parse_vn(s.get("firstAt") or s.get("submittedAt") or "")
        k = key_of(s.get("student", ""))
        if t and (k not in handed or t < handed[k]):
            handed[k] = t
    names = roster(runner, cls)
    bare = lambda x: "".join(c for c in unicodedata.normalize("NFD", x) if not unicodedata.combining(c)).replace("Đ", "D")
    by_bare = {}
    for k, t in handed.items():
        by_bare.setdefault(bare(k), []).append(t)
    missing = []
    for n in names:
        k = key_of(n)
        t = handed.get(k)
        if t is None and len(by_bare.get(bare(k), [])) == 1:   # form typo in the diacritics
            t = by_bare[bare(k)][0]
        if t is None:
            missing.append(nice(n))
        elif t <= deadline:
            on.append(nice(n))
        else:
            late.append(nice(n))
    return names, on, late, missing


# ---------------------------------------------------------------- drawing
W, PAD = 1080, 64
INK, MUTED, LINE, BG = (31, 41, 55), (107, 114, 128), (229, 231, 235), (255, 255, 255)
SECTIONS = (("Nộp đúng hạn", (22, 128, 61), (220, 252, 231)),
            ("Nộp muộn", (180, 83, 9), (254, 243, 199)),
            ("Chưa nộp", (185, 28, 28), (254, 226, 226)))


def font(weight, size):
    from PIL import ImageFont
    return ImageFont.truetype(str(FONTS / f"Carlito-{weight}.ttf"), size)   # Carlito: full Vietnamese, OFL


def draw(cls, title, deadline, total, groups):
    from PIL import Image, ImageDraw
    f_title, f_sub = font("Bold", 58), font("Regular", 34)
    f_head, f_name, f_foot = font("Bold", 36), font("Regular", 34), font("Regular", 28)
    col_w = (W - 2 * PAD - 32) // 2
    row_h = 50
    # height
    h = PAD + 70 + 50 + 40
    for _, names in groups:
        rows = (len(names) + 1) // 2
        h += 76 + max(rows, 1) * row_h + 28
    h += 60 + PAD
    img = Image.new("RGB", (W, h), BG)
    d = ImageDraw.Draw(img)
    y = PAD
    d.text((PAD, y), f"{cls} · {title}", font=f_title, fill=INK)
    y += 76
    handed = len(groups[0][1]) + len(groups[1][1])
    d.text((PAD, y), f"Hạn nộp: {deadline:%d/%m/%Y}   ·   Đã nộp {handed}/{total} bạn", font=f_sub, fill=MUTED)
    y += 50
    d.line((PAD, y + 10, W - PAD, y + 10), fill=LINE, width=2)
    y += 40
    for (label, fg, bgc), (_, names) in zip(SECTIONS, groups):
        d.rounded_rectangle((PAD, y, W - PAD, y + 56), radius=14, fill=bgc)
        d.text((PAD + 24, y + 9), f"{label} ({len(names)})", font=f_head, fill=fg)
        y += 76
        if not names:
            d.text((PAD + 24, y), "Không có bạn nào", font=f_name, fill=MUTED)
            y += row_h
        half = (len(names) + 1) // 2
        for i, n in enumerate(names):
            col, row = (0, i) if i < half else (1, i - half)
            x = PAD + 24 + col * (col_w + 32)
            d.text((x, y + row * row_h), f"• {n}", font=f_name, fill=INK)
        y += half * row_h + 28
    d.line((PAD, y, W - PAD, y), fill=LINE, width=2)
    d.text((PAD, y + 18), "Nhận xét và kết quả chấm chi tiết của từng bạn: xem trên dashboard phụ huynh.",
           font=f_foot, fill=MUTED)
    out = io.BytesIO()
    img.quantize(colors=64).save(out, "PNG", optimize=True)
    return out.getvalue()


# ---------------------------------------------------------------- run
def ensure_tab(g, sid):
    if TAB not in g.sheet_titles(sid):
        g.add_hidden_sheet(sid, TAB, HEAD)


def make(runner, now=None):
    """Called when the report is sent. Returns the classes that got a new picture."""
    now = now or dt.datetime.now(VN)
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
            names, on, late, missing = status(runner, cls, code, deadline)
            if not names:
                continue
            title = "Bài viết " + code.rsplit("-", 1)[-1]
            png = draw(cls, title, deadline, len(names), [(None, on), (None, late), (None, missing)])
            b64 = base64.b64encode(png).decode()
            parts = [b64[i:i + CHUNK] for i in range(0, len(b64), CHUNK)][:10]
            sid = runner.cfg["classes"][cls]
            ensure_tab(runner.g, sid)
            runner.g.append_rows(sid, TAB, [[key + "|" + now.strftime("%Y%m%d%H%M"), cls, f"{cls} – {title}",
                                             now.strftime("%d/%m/%Y %H:%M"), ""] + parts])
            done.append(key)
            del done[:-400]
            if cls not in made:
                made.append(cls)
            runner.tick("zalo_picture")
    return made
