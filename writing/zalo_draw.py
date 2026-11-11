"""Zalo pictures (Cô 11/11) — v3, the centre's look: warm white paper, navy ink, a touch of gold,
Lora for titles and Inter for text, hairlines instead of boxes, quiet status colours.

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
    return F(f"Lora-{w}.ttf", size)


def sans(size, w="Regular"):
    return F(f"Inter-{w}.otf", size)


def tw(d, t, f):
    return d.textlength(t, font=f)


def spaced(d, x, y, text, f, fill, gap=3):
    """Small caps label with letter spacing."""
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += tw(d, ch, f) + gap
    return x


def dot(d, x, y, c, r=7):
    d.ellipse((x, y - r, x + 2 * r, y + r), fill=c)


def logo_tile(img, x, y, h):
    """Logo on its own navy rounded tile (the logo artwork is navy-backed)."""
    from PIL import Image, ImageDraw
    lg = Image.open(FONTS / "logo-header.png").convert("RGB")
    lg = lg.resize((int(lg.width * h / lg.height), h), Image.LANCZOS)
    mask = Image.new("L", lg.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, lg.width - 1, lg.height - 1), radius=h // 5, fill=255)
    img.paste(lg, (x, y), mask)
    return lg.width


def header(img, d, kind, cls, title, meta):
    lw = logo_tile(img, P, 56, 78)
    spaced(d, P + lw + 26, 66, kind.upper(), sans(21, "SemiBold"), GOLD_TEXT, 3)
    d.text((P + lw + 26, 98), "Ms. Trang Trieu Education", font=sans(22), fill=MUTED)
    d.text((P, 168), cls, font=serif(68), fill=NAVY)
    d.text((P, 252), title, font=serif(40, "Medium"), fill=INK)
    d.text((P, 316), meta, font=sans(24), fill=MUTED)
    d.rectangle((P, 368, P + 96, 371), fill=GOLD)
    return 410


def section(d, y, label):
    spaced(d, P, y, label.upper(), sans(20, "SemiBold"), GOLD_TEXT, 3)
    return y + 48


def stats(d, y, items):
    """Big numbers in a row, hairline separators, no boxes."""
    n = len(items)
    cw = (W - 2 * P) / n
    for i, (big, lab) in enumerate(items):
        x = P + i * cw
        if i:
            d.line((x, y + 8, x, y + 118), fill=LINE, width=2)
        x0 = x + (24 if i else 0)
        d.text((x0, y), big, font=serif(58), fill=NAVY)
        d.text((x0, y + 82), lab, font=sans(22), fill=MUTED)
    return y + 150


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
    f = F("Lora-Italic.ttf", 25)
    h = 34 * len(lines) + 40
    d.rectangle((P, y, P + 4, y + h), fill=GOLD)
    for j, ln in enumerate(lines):
        d.text((P + 28, y + 20 + 34 * j), ln, font=f, fill=INK)
    return y + h + 44


def praise(d, y, people, with_band):
    f, fb = serif(30, "Medium"), sans(22, "SemiBold")
    half = (len(people) + 1) // 2
    colw = (W - 2 * P) // 2
    for i, p in enumerate(people):
        col, row = (0, i) if i < half else (1, i - half)
        x, yy = P + col * colw, y + row * 58
        d.text((x, yy), p["name"], font=f, fill=NAVY)
        if with_band and p.get("band"):
            d.text((x + tw(d, p["name"], f) + 16, yy + 8), f"{p['band']:.1f}", font=fb, fill=GOLD_TEXT)
    return y + half * 58 + 30


def png(img):
    out = io.BytesIO()
    img.quantize(colors=256, method=2).save(out, "PNG", optimize=True)
    return out.getvalue()


def table_pages(data, cols, rows_draw, n, foot):
    """Per-pupil table split over pages with a small header; footer on the last page."""
    from PIL import Image, ImageDraw
    pages = []
    per = -(-n // max(1, -(-n // ROWS_PER_PAGE))) if n else 1
    chunks = [list(range(i, min(i + per, n))) for i in range(0, n, per)] or [[]]
    for k, idx in enumerate(chunks):
        last = k == len(chunks) - 1
        H = 220 + 60 + len(idx) * ROW + (60 + 36 * len(foot) if last else 40)
        img = Image.new("RGB", (W, H), PAPER)
        d = ImageDraw.Draw(img)
        lw = logo_tile(img, P, 44, 56)
        d.text((P + lw + 22, 46), f"{data['cls']} · {data['title']}", font=serif(34), fill=NAVY)
        d.text((P + lw + 22, 92), ("Từng bạn" + (f"  ·  trang {k + 1}/{len(chunks)}" if len(chunks) > 1 else "")),
               font=sans(22), fill=MUTED)
        d.rectangle((P, 150, P + 96, 153), fill=GOLD)
        y = 196
        for lab, x in cols:
            spaced(d, x, y, lab.upper(), sans(19, "SemiBold"), FAINT, 2)
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
    items = [(f"{len(handed)}/{data['total']}", "đã nộp bài"), (f"{len(on)}", "nộp đúng hạn"),
             (f"{len(ok)}/{len(handed)}", "vở đạt yêu cầu")]
    if not nb_only:
        items.append((f"{sum(bands) / len(bands):.1f}" if bands else "—", f"band TB · {len(bands)} bài"))
    y = stats(d, y + 10, items)
    y = section(d, y + 20, "Nộp bài")
    y = bar(d, y, [("Đúng hạn", len(on), GREEN), ("Muộn", len(handed) - len(on), AMBER),
                   ("Chưa nộp", data["total"] - len(handed), ROSE)], data["total"])
    y = section(d, y + 16, "Vở ghi")
    y = bar(d, y, [("Đạt", len(ok), GREEN), ("Cần bổ sung", sum(1 for p in handed if p.get("nb") == "Cần bổ sung"), AMBER),
                   ("Chưa đạt", sum(1 for p in handed if p.get("nb") == "Không đạt"), ROSE)], len(handed))
    if crit:
        y = section(d, y + 16, f"Chất lượng bài viết · trung bình {len(bands)} bài được chữa")
        y = criteria(d, y + 4, crit)
    if bands:
        y = note(d, y + 10, ["Band ở đây là chất lượng bài viết của bài tập về nhà này, không phải",
                             "trình độ hay band thi thật: bài làm ở nhà, không giới hạn thời gian,",
                             "được xem tài liệu và dàn ý. Đi thi sẽ khác."])
    elif nb_only:
        y = note(d, y + 10, ["Tuần này chỉ kiểm tra vở chép bài giảng, không có bài viết."])
    if stars:
        y = section(d, y, "Tuyên dương · bài tốt nhất, nộp đúng hạn")
        y = praise(d, y + 6, stars, True)
    pages = [png(img.crop((0, 0, W, y + 30)))]

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
            d.text((X_ES, y + 20), "không chữa · muộn", font=F("Lora-Italic.ttf", 21), fill=FAINT)
        elif p.get("nb") and p["nb"] != "Đạt":
            d.text((X_ES, y + 20), "không chữa · vở", font=F("Lora-Italic.ttf", 21), fill=FAINT)

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
    items = [(f"{len(has)}/{len(pupils)}", "có bài viết"), (f"{len(pupils) - len(has)}", "không có bài")]
    items.append((f"{sum(bands) / len(bands):.1f}" if bands else "—", "band TB lớp") if scored
                 else (f"{sum(1 for p in has if p.get('done'))}", "bài đã chữa"))
    y = stats(d, y + 10, items)
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
