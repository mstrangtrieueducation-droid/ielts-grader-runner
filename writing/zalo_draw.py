"""Zalo pictures (Cô 11/11) — v3, the centre's look: warm white paper, navy ink, a touch of gold,
Inter only (Cô 11/11: plain, not fussy), hairlines instead of boxes, quiet status colours.

draw(data) / draw_inclass(data) → [PNG bytes]: page 1 = summary, then the per-pupil table on even pages.

draw data: cls, title, deadline (datetime), made (datetime), total, kind,
  pupils: [{name, sub: "on"|"late"|"none", nb: "Đạt"|"Cần bổ sung"|"Không đạt"|None, band: float|None}]
  crit: {"TR","CC","LR","GRA": avg}, show_band, notebook_only
draw_inclass data: cls, title, date (str), made, pupils [{name, has, band, level, done}], crit, scored, unknown
"""
import io
from pathlib import Path

FONTS = Path(__file__).parent / "fonts"
W, P = 1080, 76
PAPER, CARD = (251, 250, 247), (255, 255, 255)
INK, MUTED, FAINT, LINE = (28, 32, 51), (108, 112, 128), (160, 162, 172), (230, 226, 216)
NAVY, GOLD, GOLD_TEXT, GOLD_SOFT = (11, 17, 53), (201, 151, 26), (160, 116, 10), (246, 236, 207)
GREEN, AMBER, ROSE, TRACK = (63, 125, 92), (192, 138, 43), (180, 83, 74), (236, 232, 223)
SUB = {"on": ("Đúng hạn", GREEN), "late": ("Muộn", AMBER), "none": ("Chưa nộp", ROSE)}
NB = {"Đạt": ("Đạt", GREEN), "Cần bổ sung": ("Cần bổ sung", AMBER), "Không đạt": ("Chưa đạt", ROSE),
      "Chưa đủ dữ liệu để kết luận": ("Chụp lại", MUTED)}
CRIT = (("TR", "Trả lời đúng đề"), ("CC", "Mạch lạc, liên kết"), ("LR", "Từ vựng"), ("GRA", "Ngữ pháp"))
ROW = 64
ROWS_PER_PAGE = 16


def F(name, size):
    from PIL import ImageFont
    return ImageFont.truetype(str(FONTS / name), size)


def serif(size, w="Bold"):
    """Cô 11/11 'hơi điệu': titles in the same plain sans as the text."""
    return F("Inter-SemiBold.otf" if w == "Bold" else "Inter-Medium.otf", size)


def sans(size, w="Regular"):
    return F(f"Inter-{w}.otf", size)


def tw(d, t, f):
    return d.textlength(t, font=f)


def spaced(d, x, y, text, f, fill, gap=0):
    """Plain label (no letter spacing)."""
    d.text((x, y), text, font=f, fill=fill)
    return x + tw(d, text, f)


def dot(d, x, y, c, r=7):
    d.ellipse((x, y - r, x + 2 * r, y + r), fill=c)


def logo_tile(img, x, y, h):
    """Cô's whole logo image (not cropped), scaled down sharply."""
    from PIL import Image, ImageFilter
    lg = Image.open(FONTS / "logo.png").convert("RGB").resize((h, h), Image.LANCZOS)
    lg = lg.filter(ImageFilter.UnsharpMask(radius=1, percent=60, threshold=2))
    img.paste(lg, (x, y))
    return lg.width


def header(img, d, kind, cls, title, meta):
    """Navy band (the logo's own background), white title, gold rule."""
    d.rectangle((0, 0, W, 400), fill=NAVY)
    logo_tile(img, P - 10, 34, 132)
    d.text((P + 140, 64), kind, font=sans(27, "SemiBold"), fill=GOLD)
    d.text((P + 140, 102), "Ms. Trang Trieu Education", font=sans(22), fill=(190, 196, 220))
    d.text((P, 192), cls, font=sans(74, "SemiBold"), fill=(255, 255, 255))
    d.text((P, 280), title, font=sans(40, "Medium"), fill=(228, 231, 242))
    d.text((P, 342), meta, font=sans(23), fill=(170, 176, 205))
    d.rectangle((0, 396, W, 400), fill=GOLD)
    return 440


def section(d, y, label):
    spaced(d, P, y, label, sans(26, "SemiBold"), NAVY)
    return y + 52


TINTS = {"navy": ((236, 239, 248), NAVY), "green": ((233, 243, 237), GREEN), "amber": ((251, 242, 226), (150, 100, 20)),
         "rose": ((248, 233, 231), ROSE), "gold": ((250, 244, 226), GOLD_TEXT)}


def stats(d, y, items):
    """Tinted cards: (big, label, tint)."""
    n, gap = len(items), 18
    cw = (W - 2 * P - gap * (n - 1)) / n
    for i, it in enumerate(items):
        big, lab = it[0], it[1]
        bg, fg = TINTS[it[2] if len(it) > 2 else "navy"]
        x = P + i * (cw + gap)
        d.rounded_rectangle((x, y, x + cw, y + 150), radius=20, fill=bg)
        d.text((x + 22, y + 20), big, font=sans(52, "SemiBold"), fill=fg)
        d.text((x + 22, y + 96), lab, font=sans(21), fill=(80, 84, 100))
    return y + 180


def wrap(d, text, f, width):
    lines, cur = [], ""
    for w in text.split(" "):
        t = (cur + " " + w).strip()
        if cur and tw(d, t, f) > width:
            lines.append(cur)
            cur = w
        else:
            cur = t
    return lines + ([cur] if cur else [])


def attention(d, y, groups):
    """Cô 11/11: the important part stands out — who needs a reminder, by name, in tinted cards."""
    f_t, f_n = sans(26, "SemiBold"), sans(25)
    for label, names, tint in groups:
        if not names:
            continue
        bg, fg = TINTS[tint]
        lines, cur = [], ""   # break between names, never inside one
        for nm in names:
            t = (cur + "  ·  " + nm) if cur else nm
            if cur and tw(d, t, f_n) > W - 2 * P - 56:
                lines.append(cur)
                cur = nm
            else:
                cur = t
        lines += [cur] if cur else []
        h = 62 + 36 * len(lines) + 22
        d.rounded_rectangle((P, y, W - P, y + h), radius=18, fill=bg)
        d.rectangle((P, y + 18, P + 5, y + h - 18), fill=fg)
        d.text((P + 28, y + 18), f"{label} · {len(names)} bạn", font=f_t, fill=fg)
        for j, ln in enumerate(lines):
            d.text((P + 28, y + 62 + 36 * j), ln, font=f_n, fill=INK)
        y += h + 16
    return y + 20


def bar(d, y, parts, total):
    x, w, h = P, W - 2 * P, 12
    d.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=TRACK)
    cx = x
    for _, n, c in parts:
        if not n:
            continue
        seg = w * n / max(total, 1)
        d.rounded_rectangle((cx, y, cx + seg, y + h), radius=h // 2, fill=c)
        cx += seg
    lx, ly, f = P, y + 34, sans(23)
    for lab, n, c in parts:
        dot(d, lx, ly + 14, c, 6)
        t = f"{lab}  {n}"
        d.text((lx + 20, ly), t, font=f, fill=INK)
        lx += 20 + tw(d, t, f) + 40
    return y + 96


def criteria(d, y, crit):
    f, fv = sans(25), sans(25, "SemiBold")
    x0, bw = P + 300, W - 2 * P - 300 - 70
    for k, lab in CRIT:
        v = crit.get(k)
        if v is None:
            continue
        d.text((P, y), lab, font=f, fill=INK)
        d.rounded_rectangle((x0, y + 12, x0 + bw, y + 22), radius=5, fill=TRACK)
        d.rounded_rectangle((x0, y + 12, x0 + max(10, bw * v / 9), y + 22), radius=5, fill=NAVY)
        d.text((x0 + bw + 22, y), f"{v:.1f}", font=fv, fill=NAVY)
        y += 52
    return y + 16


def note(d, y, lines):
    f = sans(24)
    h = 34 * len(lines) + 40
    d.rounded_rectangle((P, y, W - P, y + h), radius=12, fill=(243, 241, 235))
    for j, ln in enumerate(lines):
        d.text((P + 28, y + 20 + 34 * j), ln, font=f, fill=INK)
    return y + h + 44


def praise(d, y, people, with_band):
    half = (len(people) + 1) // 2
    h = half * 58 + 44
    d.rounded_rectangle((P, y, W - P, y + h), radius=18, fill=TINTS["gold"][0])
    f, fb, colw = sans(28), sans(24, "SemiBold"), (W - 2 * P) // 2
    for i, p in enumerate(people):
        col, row = (0, i) if i < half else (1, i - half)
        x, yy = P + 28 + col * colw, y + 22 + row * 58
        d.text((x, yy), "★", font=sans(26), fill=GOLD)
        d.text((x + 34, yy), p["name"], font=f, fill=NAVY)
        if with_band and p.get("band"):
            d.text((x + 34 + tw(d, p["name"], f) + 14, yy + 2), f"{p['band']:.1f}", font=fb, fill=GOLD_TEXT)
    return y + h + 36


def png(img):
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)   # full colour: the logo stays crisp
    return out.getvalue()


def table_pages(data, cols, rows_draw, n, foot):
    """Per-pupil table split over pages with a small header; footer on the last page."""
    from PIL import Image, ImageDraw
    pages = []
    per = -(-n // max(1, -(-n // ROWS_PER_PAGE))) if n else 1
    chunks = [list(range(i, min(i + per, n))) for i in range(0, n, per)] or [[]]
    for k, idx in enumerate(chunks):
        last = k == len(chunks) - 1
        H = 230 + 60 + len(idx) * ROW + (60 + 36 * len(foot) if last else 40)
        img = Image.new("RGB", (W, H), PAPER)
        d = ImageDraw.Draw(img)
        lw = logo_tile(img, P, 30, 104)
        d.text((P + lw + 24, 46), f"{data['cls']} · {data['title']}", font=serif(34), fill=NAVY)
        d.text((P + lw + 24, 92), ("Từng bạn" + (f"  ·  trang {k + 1}/{len(chunks)}" if len(chunks) > 1 else "")),
               font=sans(22), fill=MUTED)
        d.rectangle((P, 158, P + 96, 161), fill=GOLD)
        y = 200
        for lab, x in cols:
            spaced(d, x, y, lab, sans(22, "SemiBold"), MUTED)
        y += 44
        d.line((P, y, W - P, y), fill=LINE, width=2)
        for i in idx:
            rows_draw(d, i, y)
            y += ROW
            d.line((P, y, W - P, y), fill=LINE, width=1)
        if last:
            y += 36
            for j, ln in enumerate(foot):
                d.text((P, y + 36 * j), ln, font=sans(22, "Medium" if j == 0 else "Regular"),
                       fill=INK if j == 0 else MUTED)
        pages.append(png(img))
    return pages


def status(d, x, y, label, c):
    dot(d, x, y + ROW // 2, c, 6)
    d.text((x + 20, y + 18), label, font=sans(24, "Medium"), fill=c)


def draw(data):
    from PIL import Image, ImageDraw
    pupils = data["pupils"]
    nb_only = data.get("notebook_only")
    show_band = data.get("show_band") and not nb_only and any(p.get("band") for p in pupils)
    crit = {} if nb_only else (data.get("crit") or {})
    handed = [p for p in pupils if p["sub"] != "none"]
    on = [p for p in pupils if p["sub"] == "on"]
    ok = [p for p in handed if p.get("nb") == "Đạt"]
    bands = [p["band"] for p in pupils if p.get("band")]
    stars = sorted([p for p in pupils if p.get("band") and p["sub"] == "on" and p.get("nb") == "Đạt"],
                   key=lambda p: -p["band"])
    stars = [p for p in stars if p["band"] >= stars[0]["band"] - 0.5][:6] if stars else []

    img = Image.new("RGB", (W, 2600), PAPER)
    d = ImageDraw.Draw(img)
    y = header(img, d, data.get("kind") or "Bài tập về nhà", data["cls"], data["title"],
               f"Hạn nộp {data['deadline']:%d/%m/%Y}   ·   Tổng kết {data['made']:%H:%M, %d/%m/%Y}")
    items = [(f"{len(handed)}/{data['total']}", "đã nộp bài", "navy"),
             (f"{len(on)}", "nộp đúng hạn", "green" if len(on) * 2 >= max(len(handed), 1) else "amber"),
             (f"{len(ok)}/{len(handed)}", "vở đạt yêu cầu", "green" if len(ok) * 2 >= max(len(handed), 1) else "amber")]
    if not nb_only:
        items.append((f"{sum(bands) / len(bands):.1f}" if bands else "—", f"band TB · {len(bands)} bài", "gold"))
    y = stats(d, y + 10, items)
    if stars:
        y = section(d, y + 10, "Tuyên dương · bài tốt nhất, nộp đúng hạn")
        y = praise(d, y + 4, stars, True)
    late = [p["name"] for p in pupils if p["sub"] == "late"]
    missing = [p["name"] for p in pupils if p["sub"] == "none"]
    redo = [p["name"] for p in handed if p.get("nb") in ("Cần bổ sung", "Không đạt")]
    if late or missing or redo:
        y = section(d, y + 10, "Cần nhắc")
        y = attention(d, y + 4, [("Chưa nộp", missing, "rose"), ("Vở cần bổ sung, nộp lại", redo, "amber"),
                                 ("Nộp muộn" + ("" if nb_only else " · không được chữa bài viết"), late, "amber")])
    pages = []
    if crit and y > 1150:   # keep each picture phone-sized: quality on its own page
        pages.append(png(img.crop((0, 0, W, y + 10))))
        img = Image.new("RGB", (W, 1400), PAPER)
        d = ImageDraw.Draw(img)
        lw = logo_tile(img, P, 30, 104)
        d.text((P + lw + 24, 46), f"{data['cls']} · {data['title']}", font=sans(34, "SemiBold"), fill=NAVY)
        d.text((P + lw + 24, 92), "Chất lượng bài viết", font=sans(22), fill=MUTED)
        d.rectangle((P, 158, P + 96, 161), fill=GOLD)
        y = 200
    if crit:
        y = section(d, y, f"Chất lượng bài viết · trung bình {len(bands)} bài được chữa")
        y = criteria(d, y + 4, crit)
    if bands:
        y = note(d, y + 10, ["Band ở đây là chất lượng bài viết của bài tập về nhà này, không phải",
                             "trình độ hay band thi thật: bài làm ở nhà, không giới hạn thời gian,",
                             "được xem tài liệu và dàn ý. Đi thi sẽ khác."])
    elif nb_only:
        y = note(d, y + 10, ["Tuần này chỉ kiểm tra vở chép bài giảng, không có bài viết."])
    pages.append(png(img.crop((0, 0, W, y + 30))))

    X_SUB, X_NB, X_ES = 440, 625, 822
    cols = [("Họ tên", P), ("Nộp bài", X_SUB), ("Vở ghi", X_NB)] + ([] if nb_only else [("Bài viết", X_ES)])

    def rows(d, i, y):
        p = pupils[i]
        d.text((P, y + 17), p["name"], font=sans(26), fill=INK)
        status(d, X_SUB, y, *SUB[p["sub"]])
        if p.get("nb") in NB:
            status(d, X_NB, y, *NB[p["nb"]])
        if nb_only:
            return
        if p.get("band") and show_band:
            d.text((X_ES, y + 14), f"{p['band']:.1f}", font=serif(30), fill=NAVY)
        elif p["sub"] == "late":
            d.text((X_ES, y + 20), "không chữa · muộn", font=sans(21), fill=FAINT)
        elif p.get("nb") and p["nb"] != "Đạt":
            d.text((X_ES, y + 20), "không chữa · vở", font=sans(21), fill=FAINT)

    if nb_only:
        foot = ["Tuần này chỉ kiểm tra vở chép bài giảng, không có bài viết.",
                "Vở “Cần bổ sung”: con bổ sung và nộp lại.",
                "Nhận xét chi tiết của từng bạn: xem trên dashboard phụ huynh."]
    else:
        foot = ["Bài viết chỉ được chữa và cho band khi con nộp đúng hạn và vở đạt.",
                "Nộp muộn hoặc vở cần bổ sung: chỉ kiểm tra vở, không chữa bài viết.",
                "Band là chất lượng bài viết về nhà, không phải band thi thật.",
                "Nhận xét chi tiết của từng bạn: xem trên dashboard phụ huynh."]
    return pages + table_pages(data, cols, rows, len(pupils), foot)


def draw_inclass(data):
    from PIL import Image, ImageDraw
    pupils, crit, scored = data["pupils"], data.get("crit") or {}, data.get("scored")
    has = [p for p in pupils if p["has"]]
    bands = [p["band"] for p in has if p.get("band")]
    if scored:
        stars = sorted([p for p in has if p.get("band")], key=lambda p: -p["band"])
        stars = [p for p in stars if p["band"] >= stars[0]["band"] - 0.5][:6] if stars else []
        caution = ["Band ở đây là chất lượng bài viết trên lớp này (chủ đề đã học, có",
                   "hướng dẫn của Cô), chưa phải trình độ hay band thi thật của các con."]
    else:
        stars = [p for p in has if p.get("level") == 1][:8]
        caution = ["Viết đoạn văn trên lớp có hướng dẫn: Cô không chấm điểm, chỉ chữa lỗi",
                   "chi tiết và gợi ý bản sửa để các con rút kinh nghiệm."]
    img = Image.new("RGB", (W, 2400), PAPER)
    d = ImageDraw.Draw(img)
    y = header(img, d, "Bài viết trên lớp", data["cls"], data["title"],
               f"Ngày học {data['date']}   ·   Tổng kết {data['made']:%H:%M, %d/%m/%Y}")
    items = [(f"{len(has)}/{len(pupils)}", "có bài viết", "navy"), (f"{len(pupils) - len(has)}", "không có bài", "rose")]
    items.append((f"{sum(bands) / len(bands):.1f}" if bands else "—", "band TB lớp", "gold") if scored
                 else (f"{sum(1 for p in has if p.get('done'))}", "bài đã chữa", "green"))
    y = stats(d, y + 10, items)
    if stars:
        y = section(d, y + 10, "Tuyên dương · " + ("bài tốt nhất" if scored else "bài viết cẩn thận, ít lỗi"))
        y = praise(d, y + 4, stars, scored)
        stars = []
    absent = [p["name"] for p in pupils if not p["has"]]
    if absent:
        y = section(d, y + 10, "Cần nhắc")
        y = attention(d, y + 4, [("Không có bài trong tập scan", absent, "rose")])
    if crit:
        y = section(d, y + 20, f"Chất lượng bài viết · trung bình {len(bands)} bài")
        y = criteria(d, y + 4, crit)
    y = note(d, y + 10, caution)
    if stars:
        y = section(d, y, "Tuyên dương · " + ("bài tốt nhất" if scored else "bài viết cẩn thận, ít lỗi"))
        y = praise(d, y + 6, stars, scored)
    pages = [png(img.crop((0, 0, W, y + 30)))]
    X_HAS, X_RES = 560, 820
    cols = [("Họ tên", P), ("Bài viết", X_HAS), ("Kết quả", X_RES)]

    def rows(d, i, y):
        p = pupils[i]
        d.text((P, y + 17), p["name"], font=sans(26), fill=INK)
        if not p["has"]:
            status(d, X_HAS, y, "Không có bài", ROSE)
            return
        status(d, X_HAS, y, "Có bài", GREEN)
        if scored and p.get("band"):
            d.text((X_RES, y + 14), f"{p['band']:.1f}", font=serif(30), fill=NAVY)
        elif p.get("done"):
            status(d, X_RES, y, "Đã chữa", NAVY)

    foot = ["“Không có bài”: máy không thấy bài của con trong tập scan của buổi này.",
            "Bài chữa chi tiết của từng bạn: xem trên dashboard / file theo dõi của lớp."]
    if data.get("unknown"):
        foot.insert(1, f"Có {data['unknown']} tờ chưa đọc được tên học sinh nên chưa ghi vào bảng.")
    return pages + table_pages(data, cols, rows, len(pupils), foot)
