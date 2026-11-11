"""Zalo picture, version 2 (Cô 11/11: more about the quality of the work, more visual).

draw(data) → PNG bytes. `data`:
  cls, title, deadline (datetime), made (datetime), total (pupils on the list)
  pupils: [{name, sub: "on"|"late"|"none", nb: "Đạt"|"Cần bổ sung"|"Không đạt"|None, band: float|None}]
  crit: {"TR": avg, "CC": avg, "LR": avg, "GRA": avg} over the essays corrected (may be empty)
  notes: [3 short lines: what the whole class should fix]
  show_band: bool — per-pupil band in the table
"""
import io
from pathlib import Path

FONTS = Path(__file__).parent / "fonts"
W, P = 1080, 56
INK, MUTED, LINE, BG, CARD = (17, 24, 39), (100, 110, 125), (226, 230, 236), (246, 247, 251), (255, 255, 255)
NAVY = (30, 58, 138)
GREEN, GREEN_BG = (21, 128, 61), (220, 252, 231)
AMBER, AMBER_BG = (180, 83, 9), (254, 243, 199)
RED, RED_BG = (185, 28, 28), (254, 226, 226)
GREY, GREY_BG = (75, 85, 99), (229, 231, 235)
BLUE = (37, 99, 235)
SUB = {"on": ("Đúng hạn", GREEN, GREEN_BG), "late": ("Muộn", AMBER, AMBER_BG), "none": ("Chưa nộp", RED, RED_BG)}
NB = {"Đạt": ("Đạt", GREEN, GREEN_BG), "Cần bổ sung": ("Cần bổ sung", AMBER, AMBER_BG),
      "Không đạt": ("Chưa đạt", RED, RED_BG), "Chưa đủ dữ liệu để kết luận": ("Chụp lại", GREY, GREY_BG)}
CRIT = (("TR", "Trả lời đúng đề (TR)"), ("CC", "Mạch lạc, liên kết (CC)"), ("LR", "Từ vựng (LR)"), ("GRA", "Ngữ pháp (GRA)"))


def F(w, s):
    from PIL import ImageFont
    return ImageFont.truetype(str(FONTS / f"Carlito-{w}.ttf"), s)


def tw(d, t, f):
    return d.textlength(t, font=f)


def chip(d, x, y, text, fg, bg, f, h=40):
    w = tw(d, text, f) + 28
    d.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=bg)
    d.text((x + 14, y + (h - f.size) // 2 - 2), text, font=f, fill=fg)
    return w


def stacked(d, x, y, w, parts, total, f):
    """Horizontal bar split by counts, with a legend underneath."""
    h = 34
    d.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=GREY_BG)
    cx = x
    shown = [(n, c) for _, n, c in parts if n]
    for i, (n, c) in enumerate(shown):
        seg = w * n / max(total, 1)
        r = (cx, y, cx + seg, y + h)
        d.rounded_rectangle(r, radius=h // 2, fill=c)
        if i:   # square the joint with the previous segment
            d.rectangle((cx, y, cx + min(h // 2, seg), y + h), fill=c)
        cx += seg
    lx = x
    for lab, n, c in parts:
        d.ellipse((lx, y + h + 18, lx + 18, y + h + 36), fill=c)
        t = f"{lab}: {n}"
        d.text((lx + 26, y + h + 12), t, font=f, fill=INK)
        lx += 26 + tw(d, t, f) + 36
    return h + 50


def draw(data):
    from PIL import Image, ImageDraw
    pupils = data["pupils"]
    show_band = data.get("show_band") and any(p.get("band") for p in pupils)
    f_t, f_s = F("Bold", 50), F("Regular", 30)
    f_big, f_lab = F("Bold", 56), F("Regular", 26)
    f_h, f_b, f_sm, f_chip = F("Bold", 36), F("Regular", 31), F("Regular", 26), F("Bold", 25)
    crit = data.get("crit") or {}
    notes = data.get("notes") or []
    stars = sorted([p for p in pupils if p.get("band") and p["sub"] == "on" and p.get("nb") == "Đạt"],
                   key=lambda p: -p["band"])
    stars = [p for p in stars if p["band"] >= (stars[0]["band"] - 0.5 if stars else 0)][:6]

    # ---- layout pass (heights)
    H = 256 + 210 + 2 * 150 + 40
    caution = data.get("caution") or [
        "Band ở đây là điểm CHẤT LƯỢNG BÀI VIẾT của bài tập về nhà này,",
        "không phải trình độ hay band thi thật của các con: bài làm ở nhà, không giới hạn",
        "thời gian, được xem tài liệu, dàn ý. Đi thi sẽ khác (áp lực thời gian, không tài liệu).",
    ]
    if any(p.get("band") for p in pupils):
        H += 40 * len(caution) + 70
    if crit:
        H += 90 + len(CRIT) * 62 + 20
    if notes:
        H += 90 + len(notes) * 124 + 10
    if stars:
        H += 90 + ((len(stars) + 1) // 2) * 60 + 10
    H += 90 + 56 + len(pupils) * 58 + 30 + 150
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # ---- header
    kind = data.get("kind") or "BÀI TẬP VỀ NHÀ"
    d.rectangle((0, 0, W, 236), fill=NAVY)
    chip(d, P, 30, kind, NAVY, (255, 255, 255), F("Bold", 26), h=42)
    d.text((P, 86), f"{data['cls']} · {data['title']}", font=f_t, fill=(255, 255, 255))
    d.text((P, 158), f"Hạn nộp {data['deadline']:%d/%m/%Y}  ·  Tổng kết lúc {data['made']:%H:%M %d/%m}",
           font=f_s, fill=(199, 210, 254))
    y = 256

    # ---- KPI tiles
    total = data["total"]
    handed = [p for p in pupils if p["sub"] != "none"]
    on = [p for p in pupils if p["sub"] == "on"]
    ok = [p for p in pupils if p.get("nb") == "Đạt"]
    bands = [p["band"] for p in pupils if p.get("band")]
    tiles = [(f"{len(handed)}/{total}", "đã nộp bài", NAVY),
             (f"{len(on)}", "nộp đúng hạn", GREEN),
             (f"{len(ok)}/{len(handed)}", "vở đạt yêu cầu", GREEN if len(ok) * 2 >= max(len(handed), 1) else AMBER),
             ((f"{sum(bands) / len(bands):.1f}" if bands else "—"), f"band bài viết TB ({len(bands)} bài)", BLUE)]
    tw_ = (W - 2 * P - 3 * 20) // 4
    for i, (big, lab, c) in enumerate(tiles):
        x = P + i * (tw_ + 20)
        d.rounded_rectangle((x, y, x + tw_, y + 180), radius=22, fill=CARD, outline=LINE, width=2)
        d.text((x + (tw_ - tw(d, big, f_big)) / 2, y + 34), big, font=f_big, fill=c)
        d.text((x + (tw_ - tw(d, lab, f_lab)) / 2, y + 114), lab, font=f_lab, fill=MUTED)
    y += 210

    def section(title):
        nonlocal y
        d.text((P, y + 20), title, font=f_h, fill=INK)
        y += 80

    # ---- bars
    section("Nộp bài")
    y += stacked(d, P, y, W - 2 * P, [("Đúng hạn", len(on), GREEN), ("Muộn", len(handed) - len(on), AMBER),
                                      ("Chưa nộp", total - len(handed), RED)], total, f_sm)
    y -= 10
    section("Vở ghi")
    nbc = {k: sum(1 for p in handed if p.get("nb") == k) for k in NB}
    y += stacked(d, P, y, W - 2 * P, [("Đạt", nbc["Đạt"], GREEN), ("Cần bổ sung", nbc["Cần bổ sung"], AMBER),
                                      ("Chưa đạt", nbc["Không đạt"], RED)], len(handed), f_sm)
    y += 30

    # ---- criteria
    if crit:
        section(f"Chất lượng bài viết được chữa – trung bình từng tiêu chí ({len(bands)} bài)")
        bw = W - 2 * P - 330 - 80
        for k, lab in CRIT:
            v = crit.get(k)
            if v is None:
                continue
            d.text((P, y + 4), lab, font=f_sm, fill=INK)
            x0 = P + 330
            d.rounded_rectangle((x0, y + 6, x0 + bw, y + 36), radius=15, fill=GREY_BG)
            d.rounded_rectangle((x0, y + 6, x0 + max(30, bw * v / 9), y + 36), radius=15, fill=BLUE)
            d.text((x0 + bw + 16, y + 2), f"{v:.1f}", font=F("Bold", 30), fill=BLUE)
            y += 62
        y += 20

    # ---- caution about what the band means (Cô 11/11)
    if bands:
        bh = 36 * len(caution) + 36
        d.rounded_rectangle((P, y, W - P, y + bh), radius=16, fill=(255, 251, 235), outline=(253, 230, 138), width=2)
        d.text((P + 24, y + 16), "Lưu ý", font=F("Bold", 27), fill=AMBER)
        for j, ln in enumerate(caution):
            d.text((P + 120, y + 16 + 36 * j), ln, font=F("Regular", 25), fill=INK)
        y += bh + 34

    # ---- notes
    if notes:
        section("Cả lớp cần chú ý")
        for i, n in enumerate(notes):
            lines, cur = [], ""
            for word in n.split():
                t = (cur + " " + word).strip()
                if tw(d, t, f_sm) > W - 2 * P - 100 and cur:
                    lines.append(cur)
                    cur = word
                else:
                    cur = t
            lines = (lines + [cur])[:2]
            bh = 38 + 36 * len(lines)
            d.rounded_rectangle((P, y, W - P, y + bh), radius=16, fill=CARD, outline=LINE, width=2)
            d.ellipse((P + 18, y + 19, P + 54, y + 55), fill=AMBER_BG)
            d.text((P + 29, y + 20), str(i + 1), font=F("Bold", 28), fill=AMBER)
            for j, ln in enumerate(lines):
                d.text((P + 72, y + 19 + 36 * j), ln, font=f_sm, fill=INK)
            y += bh + 12
        y += 10

    # ---- praise
    if stars:
        section("⭐ Tuyên dương: bài tốt nhất, nộp đúng hạn".replace("⭐ ", ""))
        half = (len(stars) + 1) // 2
        for i, p in enumerate(stars):
            col, row = (0, i) if i < half else (1, i - half)
            x = P + col * ((W - 2 * P) // 2)
            d.text((x, y + row * 60), p["name"], font=f_b, fill=INK)
            chip(d, x + tw(d, p["name"], f_b) + 14, y + row * 60, f"band {p['band']:.1f}".replace(".0", ".0"), BLUE,
                 (219, 234, 254), f_chip)
        y += half * 60 + 10

    # ---- per pupil
    section("Từng bạn")
    cols = [("Họ tên", P + 20), ("Nộp bài", 560), ("Vở ghi", 760)] + ([("Band bài*", 925)] if show_band else [])
    d.rounded_rectangle((P, y, W - P, y + 50), radius=12, fill=GREY_BG)
    for lab, x in cols:
        d.text((x, y + 9), lab, font=F("Bold", 27), fill=GREY)
    y += 56
    for i, p in enumerate(pupils):
        if i % 2:
            d.rectangle((P, y, W - P, y + 58), fill=(239, 241, 246))
        d.text((P + 20, y + 11), p["name"], font=f_sm, fill=INK)
        lab, fg, bg = SUB[p["sub"]]
        chip(d, 560, y + 9, lab, fg, bg, f_chip)
        if p.get("nb") in NB:
            lab, fg, bg = NB[p["nb"]]
            chip(d, 760, y + 9, lab, fg, bg, f_chip)
        elif p["sub"] != "none":
            d.text((760, y + 11), "đang chấm", font=f_sm, fill=MUTED)
        if show_band:
            d.text((960, y + 11), f"{p['band']:.1f}" if p.get("band") else "—", font=F("Bold", 28),
                   fill=BLUE if p.get("band") else MUTED)
        y += 58
    y += 30
    d.line((P, y, W - P, y), fill=LINE, width=2)
    d.text((P, y + 18), "Nộp muộn: chỉ kiểm tra vở, không chữa bài viết. Vở \"Cần bổ sung\": con bổ sung và nộp lại.",
           font=f_sm, fill=MUTED)
    d.text((P, y + 54), "Nhận xét chi tiết của từng bạn: xem trên dashboard phụ huynh.", font=f_sm, fill=MUTED)
    if show_band:
        d.text((P, y + 90), "* Band chất lượng bài viết về nhà, không phải band thi thật.", font=f_sm, fill=MUTED)
        y += 36
    img = img.crop((0, 0, W, y + 110))
    out = io.BytesIO()
    img.quantize(colors=128).save(out, "PNG", optimize=True)
    return out.getvalue()
