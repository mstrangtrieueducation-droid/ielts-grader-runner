"""Zalo pictures (Cô 11/11) — v6 "phiếu báo cáo": a white report sheet laid on the centre's navy, the logo
above it on its own navy, one gold seal with the class's key number. Plain Inter type, sentence case,
quiet colours; status colours only in the per-pupil table.

draw(data) / draw_inclass(data) → [PNG bytes]: page 1 = summary sheet, then the per-pupil table sheets.

draw data: cls, title, deadline (datetime), made (datetime), total, kind,
  pupils: [{name, sub: "on"|"late"|"none", nb: "Đạt"|"Cần bổ sung"|"Không đạt"|None, band: float|None}]
  crit: {"TR","CC","LR","GRA": avg}, show_band, notebook_only
draw_inclass data: cls, title, date (str), made, pupils [{name, has, band, level, done}], crit, scored, unknown
"""
import io
from pathlib import Path

FONTS = Path(__file__).parent / "fonts"
W = 1080                     # picture width
M = 56                       # navy margin around the sheet
SW = W - 2 * M               # sheet width
P = 56                       # padding inside the sheet
NAVY, SHEET = (11, 17, 53), (255, 255, 255)
INK, MUTED, LINE, TRACK = (27, 33, 64), (110, 115, 135), (231, 227, 214), (238, 235, 227)
GOLD, GOLD_DEEP, GOLD_SOFT = (212, 162, 42), (150, 108, 14), (250, 243, 224)
GREEN, AMBER, ROSE = (62, 123, 90), (183, 131, 42), (176, 80, 63)
SUB = {"on": ("Đúng hạn", GREEN), "late": ("Muộn", AMBER), "none": ("Chưa nộp", ROSE)}
NB = {"Đạt": ("Đạt", GREEN), "Cần bổ sung": ("Cần bổ sung", AMBER), "Không đạt": ("Chưa đạt", ROSE),
      "Chưa đủ dữ liệu để kết luận": ("Chụp lại", MUTED)}
CRIT = (("TR", "Trả lời đúng đề"), ("CC", "Mạch lạc, liên kết"), ("LR", "Từ vựng"), ("GRA", "Ngữ pháp"))
ROW = 62
ROWS_PER_PAGE = 15


def F(name, size):
    from PIL import ImageFont
    return ImageFont.truetype(str(FONTS / name), size)


def sans(size, w="Regular"):
    return F(f"Inter-{w}.otf", size)


def tw(d, t, f):
    return d.textlength(t, font=f)


def png(img):
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def sheet_canvas(h):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (SW, h), SHEET)
    return img, ImageDraw.Draw(img)


def compose(sheet, top_logo=True, footer=True):
    """Lay the white sheet on the navy page: logo above (blends into the navy), small name below."""
    from PIL import Image, ImageDraw
    logo_h = 170 if top_logo else 0
    H = M + logo_h + sheet.height + (96 if footer else M)
    page = Image.new("RGB", (W, H), NAVY)
    if top_logo:
        lg = Image.open(FONTS / "logo.png").convert("RGB").resize((logo_h + 40, logo_h + 40), Image.LANCZOS)
        page.paste(lg, ((W - lg.width) // 2, M - 40))
    mask = Image.new("L", sheet.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, sheet.width - 1, sheet.height - 1), radius=28, fill=255)
    page.paste(sheet, (M, M + logo_h), mask)
    if footer:
        d = ImageDraw.Draw(page)
        t = "Ms. Trang Trieu Education"
        f = sans(22, "Medium")
        d.text(((W - tw(d, t, f)) / 2, H - 66), t, font=f, fill=GOLD)
    return page


def heading(d, kind, cls, title, meta):
    d.text((P, 52), f"{kind} – {title}", font=sans(26, "Medium"), fill=MUTED)
    d.text((P, 92), cls, font=sans(76, "SemiBold"), fill=NAVY)
    d.text((P, 190), meta, font=sans(23), fill=MUTED)
    return 252


def seal(d, cx, cy, big, small):
    """The one gold element: the class's key number in a medal-like ring."""
    r = 112
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GOLD_SOFT, outline=GOLD, width=6)
    d.ellipse((cx - r + 16, cy - r + 16, cx + r - 16, cy + r - 16), outline=GOLD, width=2)
    fb, fs = sans(70, "SemiBold"), sans(21, "Medium")
    d.text((cx - tw(d, big, fb) / 2, cy - 58), big, font=fb, fill=GOLD_DEEP)
    d.text((cx - tw(d, small, fs) / 2, cy + 30), small, font=fs, fill=GOLD_DEEP)


def facts(d, x, y, items):
    """Plain sentences with the number in bold: '25/25 bạn đã nộp bài'."""
    fb, fr = sans(34, "SemiBold"), sans(28)
    for num, rest in items:
        d.text((x, y), num, font=fb, fill=NAVY)
        d.text((x + tw(d, num, fb) + 12, y + 5), rest, font=fr, fill=INK)
        y += 60
    return y


def rule(d, y):
    d.line((P, y, SW - P, y), fill=LINE, width=2)
    return y + 36


def label(d, y, text):
    d.text((P, y), text, font=sans(27, "SemiBold"), fill=NAVY)
    return y + 54


def praise(d, y, people, with_band):
    f, fb = sans(28), sans(25, "SemiBold")
    half = (len(people) + 1) // 2
    colw = (SW - 2 * P) // 2
    for i, p in enumerate(people):
        col, row = (0, i) if i < half else (1, i - half)
        x, yy = P + col * colw, y + row * 54
        d.text((x, yy - 2), "★", font=sans(26), fill=GOLD)
        d.text((x + 36, yy), p["name"], font=f, fill=INK)
        if with_band and p.get("band"):
            d.text((x + 36 + tw(d, p["name"], f) + 12, yy + 2), f"{p['band']:.1f}", font=fb, fill=GOLD_DEEP)
    return y + half * 54 + 14


def criteria(d, y, crit):
    f, fv = sans(26), sans(26, "SemiBold")
    x0 = P + 290
    bw = SW - P - x0 - 70
    for k, lab in CRIT:
        v = crit.get(k)
        if v is None:
            continue
        d.text((P, y), lab, font=f, fill=INK)
        d.rounded_rectangle((x0, y + 13, x0 + bw, y + 23), radius=5, fill=TRACK)
        d.rounded_rectangle((x0, y + 13, x0 + max(10, bw * v / 9), y + 23), radius=5, fill=NAVY)
        d.text((x0 + bw + 20, y), f"{v:.1f}", font=fv, fill=NAVY)
        y += 52
    return y + 8


def note(d, y, lines):
    f = sans(23)
    for j, ln in enumerate(lines):
        d.text((P, y + 34 * j), ln, font=f, fill=MUTED)
    return y + 34 * len(lines) + 10


def status(d, x, y, text, c):
    d.ellipse((x, y + ROW // 2 - 6, x + 12, y + ROW // 2 + 6), fill=c)
    d.text((x + 22, y + 16), text, font=sans(24, "Medium"), fill=c)


def table_pages(data, cols, rows_draw, n, foot):
    pages = []
    per = -(-n // max(1, -(-n // ROWS_PER_PAGE))) if n else 1
    chunks = [list(range(i, min(i + per, n))) for i in range(0, n, per)] or [[]]
    for k, idx in enumerate(chunks):
        last = k == len(chunks) - 1
        h = 150 + 56 + len(idx) * ROW + (40 + 34 * len(foot) + 40 if last else 40)
        img, d = sheet_canvas(h)
        d.text((P, 46), f"{data['cls']} – {data['title']}", font=sans(36, "SemiBold"), fill=NAVY)
        d.text((P, 96), "Từng bạn" + (f", trang {k + 1}/{len(chunks)}" if len(chunks) > 1 else ""),
               font=sans(23), fill=MUTED)
        y = 150
        for lab, x in cols:
            d.text((x, y), lab, font=sans(22, "SemiBold"), fill=MUTED)
        y += 44
        d.line((P, y, SW - P, y), fill=LINE, width=2)
        for i in idx:
            rows_draw(d, i, y)
            y += ROW
            d.line((P, y, SW - P, y), fill=LINE, width=1)
        if last:
            y += 34
            for j, ln in enumerate(foot):
                d.text((P, y + 34 * j), ln, font=sans(22, "Medium" if j == 0 else "Regular"),
                       fill=INK if j == 0 else MUTED)
        pages.append(png(compose(img, top_logo=False)))
    return pages


def draw(data):
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

    img, d = sheet_canvas(2200)
    y = heading(d, data.get("kind") or "Bài tập về nhà", data["cls"], data["title"],
                f"Hạn nộp {data['deadline']:%d/%m/%Y}, tổng kết lúc {data['made']:%H:%M} ngày {data['made']:%d/%m/%Y}")
    y = rule(d, y)
    if bands and not nb_only:
        seal(d, P + 112, y + 126, f"{sum(bands) / len(bands):.1f}", "band TB lớp")
    else:
        seal(d, P + 112, y + 126, f"{len(ok)}/{len(handed)}", "vở đạt")
    fl = [(f"{len(handed)}/{data['total']}", "bạn đã nộp bài"), (f"{len(on)}", "bạn nộp đúng hạn"),
          (f"{len(ok)}/{len(handed)}", "vở đạt yêu cầu")]
    if bands and not nb_only:
        fl.append((f"{len(bands)}", "bài viết được chữa"))
    facts(d, P + 280, y + (2 if len(fl) > 3 else 22), fl)
    y += 270
    if stars:
        y = rule(d, y)
        y = label(d, y, "Tuyên dương: bài tốt nhất, nộp đúng hạn")
        y = praise(d, y, stars, True)
    if crit:
        y = rule(d, y + 10)
        y = label(d, y, f"Chất lượng {len(bands)} bài viết được chữa (trung bình)")
        y = criteria(d, y, crit)
    y = rule(d, y + 10)
    if nb_only:
        y = note(d, y, ["Tuần này chỉ kiểm tra vở chép bài giảng, không có bài viết."])
    else:
        y = note(d, y, ["Band là chất lượng bài viết về nhà (làm ở nhà, không giới hạn thời gian,",
                        "được xem tài liệu và dàn ý), không phải band thi thật của các con.",
                        "Bài viết chỉ được chữa khi con nộp đúng hạn và vở đạt."])
    pages = [png(compose(img.crop((0, 0, SW, y + 40))))]

    X_SUB, X_NB, X_ES = 380, 540, 728
    cols = [("Họ tên", P), ("Nộp bài", X_SUB), ("Vở ghi", X_NB)] + ([] if nb_only else [("Bài viết", X_ES)])

    def rows(d, i, y):
        p = pupils[i]
        d.text((P, y + 16), p["name"], font=sans(26), fill=INK)
        status(d, X_SUB, y, *SUB[p["sub"]])
        if p.get("nb") in NB:
            status(d, X_NB, y, *NB[p["nb"]])
        if nb_only:
            return
        if p.get("band") and show_band:
            d.text((X_ES, y + 12), f"{p['band']:.1f}", font=sans(30, "SemiBold"), fill=NAVY)
        elif p["sub"] == "late":
            d.text((X_ES, y + 19), "không chữa (muộn)", font=sans(20), fill=MUTED)
        elif p.get("nb") and p["nb"] != "Đạt":
            d.text((X_ES, y + 19), "không chữa (vở)", font=sans(20), fill=MUTED)

    if nb_only:
        foot = ["Tuần này chỉ kiểm tra vở chép bài giảng, không có bài viết.",
                "Vở “Cần bổ sung”: con bổ sung và nộp lại.",
                "Nhận xét chi tiết của từng bạn: xem trên dashboard phụ huynh."]
    else:
        foot = ["Bài viết chỉ được chữa và cho band khi con nộp đúng hạn và vở đạt.",
                "Nộp muộn hoặc vở cần bổ sung: chỉ kiểm tra vở, không chữa bài viết.",
                "Nhận xét chi tiết của từng bạn: xem trên dashboard phụ huynh."]
    return pages + table_pages(data, cols, rows, len(pupils), foot)


def draw_inclass(data):
    pupils, crit, scored = data["pupils"], data.get("crit") or {}, data.get("scored")
    has = [p for p in pupils if p["has"]]
    bands = [p["band"] for p in has if p.get("band")]
    if scored:
        stars = sorted([p for p in has if p.get("band")], key=lambda p: -p["band"])
        stars = [p for p in stars if p["band"] >= stars[0]["band"] - 0.5][:6] if stars else []
        caution = ["Band là chất lượng bài viết trên lớp này (chủ đề đã học, có hướng dẫn",
                   "của Cô), chưa phải trình độ hay band thi thật của các con."]
    else:
        stars = [p for p in has if p.get("level") == 1][:8]
        caution = ["Viết đoạn văn trên lớp có hướng dẫn: Cô không chấm điểm, chỉ chữa lỗi",
                   "chi tiết và gợi ý bản sửa để các con rút kinh nghiệm."]
    img, d = sheet_canvas(2000)
    y = heading(d, "Bài viết trên lớp", data["cls"], data["title"],
                f"Ngày học {data['date']}, tổng kết lúc {data['made']:%H:%M} ngày {data['made']:%d/%m/%Y}")
    y = rule(d, y)
    if scored and bands:
        seal(d, P + 112, y + 126, f"{sum(bands) / len(bands):.1f}", "band TB lớp")
    else:
        seal(d, P + 112, y + 126, f"{len(has)}/{len(pupils)}", "có bài viết")
    facts(d, P + 280, y + 40, [(f"{len(has)}/{len(pupils)}", "bạn có bài viết"),
                               (f"{sum(1 for p in has if p.get('done'))}", "bài đã chữa")])
    y += 270
    if stars:
        y = rule(d, y)
        y = label(d, y, "Tuyên dương: " + ("bài tốt nhất" if scored else "bài viết cẩn thận, ít lỗi"))
        y = praise(d, y, stars, scored)
    if crit:
        y = rule(d, y + 10)
        y = label(d, y, f"Chất lượng {len(bands)} bài viết (trung bình)")
        y = criteria(d, y, crit)
    y = rule(d, y + 10)
    y = note(d, y, caution)
    pages = [png(compose(img.crop((0, 0, SW, y + 40))))]
    X_HAS, X_RES = 520, 770
    cols = [("Họ tên", P), ("Bài viết", X_HAS), ("Kết quả", X_RES)]

    def rows(d, i, y):
        p = pupils[i]
        d.text((P, y + 16), p["name"], font=sans(26), fill=INK)
        if not p["has"]:
            status(d, X_HAS, y, "Không có bài", ROSE)
            return
        status(d, X_HAS, y, "Có bài", GREEN)
        if scored and p.get("band"):
            d.text((X_RES, y + 12), f"{p['band']:.1f}", font=sans(30, "SemiBold"), fill=NAVY)
        elif p.get("done"):
            status(d, X_RES, y, "Đã chữa", NAVY)

    foot = ["“Không có bài”: máy không thấy bài của con trong tập scan của buổi này.",
            "Bài chữa chi tiết của từng bạn: xem trên dashboard phụ huynh."]
    if data.get("unknown"):
        foot.insert(1, f"Có {data['unknown']} tờ chưa đọc được tên học sinh nên chưa ghi vào bảng.")
    return pages + table_pages(data, cols, rows, len(pupils), foot)
