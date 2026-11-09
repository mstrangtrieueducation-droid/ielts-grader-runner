"""Fighter — sổ từ vựng (VF1, VF2, Reading 1/2 – từ vựng): checked by Haiku, scored by code, written to the tracker.

Cô's decisions (10/11/2026):
  * Haiku only (regular homework, keep it cheap); fully automatic, nothing waits for Cô.
  * Haiku only READS the notebook (which numbered words are there, which of the 7 columns are filled).
    Code compares with the unit's word list from the lesson site and decides the result → same standard for everyone.
  * Result = "Mức hoàn thành N%" + exact numbers of missing words / empty columns; < 90 % → "con làm lại/bổ sung".
  * Not accepted (⛔): printed / screenshot instead of handwriting, photos reused from another submission, wrong unit.
  * Video trả từ: only "has a video" + "length reasonable for the number of words" (Drive metadata, no AI).
  * From the 3rd incomplete notebook: "Đây là lần thứ N con nộp sổ chưa đầy đủ (…)" (count from our own results).
  * Only submissions from Sunday 08/11/2026 00:00 on; older work is left to the staff.
  * Results within ~1 hour: direct calls (no batch), every 25-minute cycle.
  * Unclear handwriting is never counted as missing; unreadable photos → "chụp lại rõ".
"""
from __future__ import annotations

import base64
import concurrent.futures as cf
import datetime as dt
import difflib
import io
import json
import os
import re
import unicodedata
from pathlib import Path

import claude_worker as cw
from run_writing import MARK, STATE_DIR, VN, col_letter, file_id, h, load_json, norm, now, parse_vn_time, save_json, to_jpeg

HERE = Path(__file__).resolve().parent
VOCAB = json.loads((HERE / "vocab.json").read_text(encoding="utf-8"))
SAMPLE = HERE / "notebook-sample.png"
STATE = Path(os.environ.get("FIGHTER_STATE") or (STATE_DIR / "fighter-notebook.json"))
FORM = "1l02Y7llw4b6QZtcSgbH2bQ0LHARxa74iLwybVGQ_D68"          # sheet "Chấm bài FIGHTER"
TABS = {"VOCABULARY FOUNDATION 1": "VF1", "VOCABULARY FOUNDATION 2": "VF2",
        "READING 1": "RI1", "READING 2 - TỪ VỰNG": "RI2",
        "GRAMMAR FOUNDATION": "GF", "ĐOẠN VĂN HỌC THUẬT": "AP"}
COPY = {"GF": json.loads((HERE / "grammar.json").read_text(encoding="utf-8")),      # vở chép lí thuyết ngữ pháp
        "AP": json.loads((HERE / "paragraph.json").read_text(encoding="utf-8"))}    # vở chép bài giảng đoạn văn (Buổi 1–15)
KIND_NAME = {"GF": "vở chép lí thuyết", "AP": "vở chép bài giảng"}
START = dt.datetime(2026, 11, 8, 0, 0, tzinfo=VN)
MODEL = "claude-haiku-5-5"
SIDE = 1568
MAX_PAGES = 14
PASS = 90
VERSION = 4              # raise when the scoring changes: our own published results are regraded once and replaced
GROUP_MINUTES = 30          # rows of one student/unit sent within 30 min = one submission (photos split over rows)
STATUS_WAIT_MIN = 40        # the status system normally marks the cell first; after this we write the status line ourselves
FIELDS = [("type", "Từ loại"), ("ipa", "Phiên âm"), ("vi", "Nghĩa tiếng Việt"), ("en", "Nghĩa tiếng Anh"), ("example", "Ví dụ")]
PROGRAM_HEAD = {"VF1": r"Vocabulary Foundation 1", "VF2": r"Vocabulary Foundation 2",
                "RI1": r"READING 1\s*-\s*TỪ VỰNG", "RI2": r"READING 2\s*-\s*TỪ VỰNG",
                "GF": r"Grammar Foundation", "AP": r"ĐOẠN VĂN HỌC THUẬT"}

S, I = {"type": "string"}, {"type": "integer"}
CELL = {"type": "string", "enum": ["filled", "empty", "unclear"]}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["pages", "entries", "otherTerms", "meaningCheck"],
          "properties": {
              "pages": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                    "required": ["page", "kind", "readable", "neat"],
                                                    "properties": {"page": I,
                                                                   "kind": {"type": "string", "enum": ["handwritten", "printed_or_screen", "not_a_notebook"]},
                                                                   "readable": {"type": "string", "enum": ["yes", "partly", "no"]},
                                                                   "neat": {"type": "string", "enum": ["neat", "acceptable", "messy"]}}}},
              "entries": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                      "required": ["n", "term"] + [f for f, _ in FIELDS],
                                                      "properties": dict({"n": I, "term": S}, **{f: CELL for f, _ in FIELDS})}},
              "otherTerms": I,
              "meaningCheck": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                           "required": ["n", "match"],
                                                           "properties": {"n": I, "match": {"type": "string", "enum": ["yes", "no", "unclear"]}}}}}}

PROMPT = """Bạn đọc ảnh SỔ TỪ VỰNG viết tay của một học sinh. Bạn KHÔNG chấm, KHÔNG nhận xét; chỉ ghi lại đúng những gì nhìn thấy.

Mẫu sổ (ảnh đầu tiên) có 7 cột: STT · Từ/cụm từ · Từ loại · Phiên âm · Giải nghĩa tiếng Việt · Giải nghĩa tiếng Anh · Ví dụ minh họa.
Bài này là {code} ({title}), gồm các mục số {first}–{last}:
{listing}

Việc cần làm:
1. pages: với MỖI ảnh bài làm (không tính ảnh mẫu), theo thứ tự 1, 2, 3…: kind = handwritten (chữ viết tay trên sổ/giấy),
   printed_or_screen (bản in, ảnh chụp màn hình/web, chữ đánh máy), not_a_notebook (ảnh khác); readable = yes / partly / no;
   neat = neat (chữ rõ, sạch) / acceptable (bình thường) / messy (chữ quá cẩu thả, nguệch ngoạc, gạch xoá bôi bẩn nhiều,
   viết lệch dòng lộn xộn — chỉ chọn messy khi thật sự rõ ràng; ảnh mờ do chụp KHÔNG phải messy).
2. entries: mỗi mục từ em ĐÃ VIẾT trong sổ, một dòng: n = số thứ tự em ghi (nếu em không ghi số, lấy số của từ tương ứng
   trong danh sách trên; nhiều em tự đánh số lại từ 1 — vẫn ghi số em viết), term = từ/cụm từ tiếng Anh em viết (chép nguyên văn). Với từng cột type, ipa, vi, en, example:
   filled = có viết nội dung; empty = để trống; unclear = không nhìn rõ (ảnh mờ, bị cắt, che khuất).
   Ví dụ dài xuống dòng vẫn là filled. KHÔNG liệt kê mục em không viết. Không đoán: không chắc thì unclear.
3. otherTerms = số mục em viết mà KHÔNG có trong danh sách trên (từ của bài khác).
4. meaningCheck: với các số {spot}: nghĩa tiếng Việt em viết có cùng nghĩa với nghĩa tham khảo không
   (yes / no / unclear; sai chính tả, diễn đạt khác mà cùng nghĩa vẫn là yes; không thấy mục đó thì bỏ qua).

Trả kết quả DUY NHẤT qua công cụ record."""


PAGE = {"type": "object", "additionalProperties": False, "required": ["page", "kind", "readable", "neat"],
        "properties": {"page": I, "kind": {"type": "string", "enum": ["handwritten", "printed_or_screen", "not_a_notebook"]},
                       "readable": {"type": "string", "enum": ["yes", "partly", "no"]},
                       "neat": {"type": "string", "enum": ["neat", "acceptable", "messy"]}}}
OUTLINE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["parts"],
                  "properties": {"parts": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                                       "required": ["name", "starts"],
                                                                       "properties": {"name": S, "starts": S}}}}}
COPY_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["pages", "parts", "otherLesson"],
               "properties": {"pages": {"type": "array", "items": PAGE},
                              "parts": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                                    "required": ["id", "status"],
                                                                    "properties": {"id": I, "status": {"type": "string", "enum": ["full", "partly", "missing", "unclear"]}}}},
                              "otherLesson": {"type": "boolean"}}}
OUTLINE_PROMPT = """Dưới đây là TÀI LIỆU BÀI GIẢNG mà học sinh phải chép tay vào vở. Hãy chia tài liệu thành các PHẦN CHÍNH (4–12 phần)
theo đúng thứ tự trong tài liệu, để giáo viên kiểm tra học sinh đã chép đủ chưa. Dùng các đề mục có sẵn (I, II, 1, 2…, Outline,
Bài mẫu, Từ vựng…); phần nào quá ngắn thì gộp với phần bên cạnh. name = tên phần ngắn gọn (≤ 60 ký tự, giữ ngôn ngữ của tài liệu);
starts = vài chữ đầu của phần đó. Trả kết quả qua công cụ record.

TÀI LIỆU:
{doc}"""
COPY_PROMPT = """Bạn đọc ảnh VỞ CHÉP BÀI GIẢNG viết tay của một học sinh. Bạn KHÔNG chấm, KHÔNG nhận xét; chỉ ghi lại đúng những gì nhìn thấy.
Học sinh phải chép tay đầy đủ tài liệu bài giảng ({title}) dưới đây vào vở. Tài liệu gồm các phần:
{parts}

1. pages: với MỖI ảnh, theo thứ tự 1, 2, 3…: kind = handwritten / printed_or_screen (bản in, ảnh chụp màn hình, chữ đánh máy,
   dán tài liệu in) / not_a_notebook; readable = yes / partly / no; neat = neat / acceptable / messy (chữ quá cẩu thả, nguệch ngoạc,
   gạch xoá bôi bẩn nhiều, lộn xộn — chỉ chọn messy khi thật sự rõ ràng; ảnh mờ do chụp KHÔNG phải messy).
2. parts: với MỖI phần ở trên (id theo số thứ tự): full = đã chép đủ nội dung chính của phần đó; partly = chỉ chép một phần
   (thiếu rõ ràng nhiều ý/ví dụ); missing = không thấy phần đó trong vở; unclear = không nhìn rõ để kết luận.
   Đối chiếu với nội dung tài liệu bên dưới; không đòi chép giống từng chữ, không bắt lỗi chính tả.
3. otherLesson = true nếu vở chủ yếu là nội dung của một bài khác (không phải tài liệu này).

TÀI LIỆU BÀI GIẢNG:
{doc}

Trả kết quả DUY NHẤT qua công cụ record."""
STATUS_RANK = {"missing": 0, "partly": 1, "unclear": 2, "full": 3}


def bare(s):
    s = unicodedata.normalize("NFD", str(s or "")).replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def core(t):
    return re.sub(r"\s+", " ", re.sub(r"\(.*?\)|[^a-z ]", " ", bare(t))).strip()


def sim(listed, written):
    """How well a written headword matches a listed entry ('achieve' ↔ 'achieve · achievement', 'clever = smart' ↔ 'clever ~ smart')."""
    w = core(written)
    if not w:
        return 0.0
    best = 0.0
    for alt in re.split(r"~|·|=|><|/|,|;", bare(listed)):
        a = core(alt)
        if not a:
            continue
        if a == w or a.startswith(w + " ") or w.startswith(a + " "):
            return 1.0
        if a.split(" ")[0] == w.split(" ")[0] and len(w.split(" ")[0]) > 2:
            best = max(best, 0.85)
        best = max(best, difflib.SequenceMatcher(None, a, w).ratio())
    return best


def ranges(nums):
    nums = sorted(set(nums))
    out, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if i == j else f"{nums[i]}–{nums[j]}")
        i = j + 1
    return ", ".join(out)


def unit_code(prog, raw):
    raw = str(raw or "").strip()
    if prog == "GF":   # GF1-U04.1-LT, "Unit 4.1"
        m = re.search(r"U(?:nit)?\s*0*(\d+)(?:\.(\d))?", raw, re.I) or re.search(r"(\d+)(?:\.(\d))?", raw)
        return f"GF1-U{int(m.group(1)):02d}{'.' + m.group(2) if m.group(2) else ''}-LT" if m else None
    if prog == "AP":   # AP-B07, "Buổi 05"
        m = re.search(r"(\d+)", raw)
        return f"AP-B{int(m.group(1)):02d}" if m else None
    m = re.search(r"(\d+)\s*$", raw) or re.search(r"U\s*0*(\d+)", raw, re.I)
    return f"{prog}-U{int(m.group(1)):02d}" if m else None


def unit_label(code):
    """Text used in the tracker header and in the comment: 'Unit 14', 'Unit 4.1', 'Buổi 7'."""
    if code.startswith("AP-B"):
        return "Buổi", str(int(code[4:]))
    m = re.search(r"U0*(\d+(?:\.\d)?)", code)
    return "Unit", m.group(1)


def known(prog, code):
    return code in (COPY[prog] if prog in COPY else VOCAB)


def dhash(jpeg: bytes) -> str:
    from PIL import Image
    from PIL import ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(jpeg))).convert("L").resize((33, 32))
    px = list(im.getdata())
    bits = "".join("1" if px[r * 33 + c] > px[r * 33 + c + 1] else "0" for r in range(32) for c in range(32))
    return f"{int(bits, 2):0256x}"


def ham(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def img_block(jpeg: bytes):
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(jpeg))).convert("RGB")
    im.thumbnail((SIDE, SIDE))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}}


def score(unit, res):
    """Code decides: % = (word present + 5 columns filled) / (6 × words); unclear counts as filled."""
    want = {e["n"]: e for e in unit["entries"]}
    seen = {}
    for e in res.get("entries", []):
        # the headword decides which listed word this is (pupils often number from 1); the number only breaks ties
        best = max(want.values(), key=lambda w: (sim(w["term"], e.get("term")), w["n"] == e.get("n")))
        bs = sim(best["term"], e.get("term"))
        if bs >= 0.75:
            n = best["n"]
        elif e.get("n") in want and bs >= 0.4 and sim(want[e["n"]]["term"], e.get("term")) >= 0.4:
            n = e["n"]
        else:
            continue
        old = seen.get(n)
        seen[n] = dict(e) if old is None else dict(old, **{f: ("empty" if old[f] == e[f] == "empty" else "filled") for f, _ in FIELDS})
    missing = [n for n in want if n not in seen]
    empty = {f: [n for n, e in seen.items() if e[f] == "empty"] for f, _ in FIELDS}
    pts = sum(1 + sum(e[f] != "empty" for f, _ in FIELDS) for e in seen.values())
    pct = round(100 * pts / (6 * len(want))) if want else 0
    termok = len(seen)
    return {"pct": pct, "missing": missing, "empty": empty, "seen": len(seen), "total": len(want), "termOk": termok,
            "written": len(res.get("entries", []))}


class FighterNotebooks:
    def __init__(self, runner):
        self.r, self.g = runner, runner.g
        self.st = load_json(STATE, {"subs": {}, "hashes": {}})
        self._cl = None

    def tick(self, k, n=1):
        self.r.tick("fnb_" + k, n)

    @property
    def cl(self):
        if self._cl is None:
            self._cl = cw.client()
        return self._cl

    # ------------------------------------------------------------ scan the form
    def scan(self):
        rows = []
        for tab, prog in TABS.items():
            try:
                table = self.g.values(FORM, f"'{tab}'!A1:J3000")
            except Exception:
                self.tick("form_read_failed")
                continue
            if not table:
                continue
            hdr = [unicodedata.normalize("NFC", str(x or "")).upper() for x in table[0]]
            col = lambda *keys: next((i for i, x in enumerate(hdr) if any(k in x for k in keys)), None)
            vid, merged, status = col("VIDEO"), col("PDF ĐÃ GHÉP"), col("TRẠNG THÁI GHÉP")
            c_code, c_name, c_cls = col("MÃ BÀI"), col("HỌ VÀ TÊN", "HỌ TÊN"), col("LỚP")
            if None in (c_code, c_name, c_cls):
                self.tick("form_columns_unknown")
                continue
            photos = [i for i, x in enumerate(hdr) if i not in (0, c_code, c_name, c_cls, vid, merged, status)
                      and any(k in x for k in ("ẢNH", "FILE", "PDF"))]
            for k, row in enumerate(table[1:], 2):
                t = parse_vn_time(row[0] if row else "")
                if not t or t < START or len(row) <= max(c_code, c_name, c_cls):
                    continue
                code = unit_code(prog, row[c_code])
                if not code or not known(prog, code):
                    self.tick("unit_without_word_list")
                    continue
                files = []
                for i in photos:
                    for u in re.split(r"[,\s]+", row[i] if i < len(row) else ""):
                        f = file_id(u)
                        if f and f not in files:
                            files.append(f)
                mid = file_id(row[merged]) if merged is not None and merged < len(row) else None
                st_txt = unicodedata.normalize("NFC", row[status]).upper() if status is not None and status < len(row) else ""
                m = re.search(r"(\d+)\s*ẢNH", st_txt)
                if mid and "HOÀN TẤT" in st_txt and (("PDF GỐC" in st_txt) or (m and int(m.group(1)) >= len(files))):
                    files = [mid]
                video = file_id(row[vid]) if vid is not None and vid < len(row) else None
                rows.append({"tab": tab, "prog": prog, "row": k, "time": t, "code": code, "rawName": row[c_name].strip(),
                             "cls": self.r.class_of(row[c_cls]), "files": files, "video": video})
        # one submission = rows of the same student / unit sent within GROUP_MINUTES of each other
        rows.sort(key=lambda x: x["time"])
        groups = []
        for x in rows:
            key = (x["cls"], bare(norm(x["rawName"])), x["code"])
            g = next((g for g in reversed(groups) if g["key"] == key and x["time"] - g["last"] <= dt.timedelta(minutes=GROUP_MINUTES)), None)
            if g:
                g["rows"].append(x["row"]); g["last"] = x["time"]
                g["files"] += [f for f in x["files"] if f not in g["files"]]
                g["video"] = x["video"] or g["video"]
            else:
                groups.append({"key": key, "first": x["time"], "last": x["time"], "rows": [x["row"]], "files": list(x["files"]),
                               "video": x["video"], **{k: x[k] for k in ("tab", "prog", "code", "rawName", "cls")}})
        subs = self.st["subs"]
        for g in groups:
            sid = h(f"{g['tab']}|{g['rows'][0]}|{g['rawName']}")
            if sid in subs:
                if len(g["rows"]) > len(subs[sid]["rows"]) and subs[sid]["status"] == "new":
                    subs[sid].update(rows=g["rows"], files=g["files"], video=g["video"])
                continue
            subs[sid] = {"cls": g["cls"], "student": g["rawName"], "code": g["code"], "prog": g["prog"], "tab": g["tab"],
                         "rows": g["rows"], "files": g["files"], "video": g["video"],
                         "submittedAt": g["last"].strftime("%d/%m/%Y %H:%M:%S"), "status": "new", "tries": 0}
            self.tick("new")

    # ------------------------------------------------------------ tracker cell
    def cell_for(self, s):
        if s["cls"] not in self.r.cfg["classes"]:
            return None, None, "class_unknown"
        tr = self.r.tracker(s["cls"])
        row = tr.row_of(norm(s["student"]))
        if not row:   # "LƯU GIA BẢO (Legacy)", "Nguyễn Kim Ngân- Jane" … → name without the nickname
            alt = re.sub(r"\(.*?\)", " ", s["student"])
            alt = re.split(r"\s+-\s*|\s*-\s+|-(?=[A-Za-z]+\s*$)", alt)[0]
            row = tr.row_of(norm(alt))
        if not row:
            return None, None, "not_in_roster"
        grid = getattr(tr, "_fgrid", None)
        if grid is None:
            grid = tr._fgrid = self.g.values(tr.id, f"'{tr.tab}'!A1:ZZ3")
        r1, r2, r3 = (grid + [[], [], []])[:3]
        start = next((i for i, v in enumerate(r1) if "BÀI TẬP VỀ NHÀ" in unicodedata.normalize("NFC", str(v)).upper()), None)
        if start is None:
            return None, None, "no_homework_area"
        label, unit = unit_label(s["code"])
        unit_re = rf"\b{label}\s*0*{re.escape(unit)}(?![.\d]*\d)"
        hits, group = [], ""
        for i in range(start, max(len(r2), len(r3))):
            v2 = str(r2[i]) if i < len(r2) else ""
            if v2.strip():
                group = v2
            v3 = str(r3[i]) if i < len(r3) else ""
            if (re.search(PROGRAM_HEAD[s["prog"]], group, re.I) and re.search(unit_re, group, re.I)
                    and re.match(r"\s*Hạn", v3, re.I)):
                hits.append(i)
        if len(hits) != 1:
            return None, None, "tracker_column_" + ("missing" if not hits else "ambiguous")
        i = hits[0]
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(r3[i]))
        deadline = dt.datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), 23, 59, 59, tzinfo=VN) if m else None
        return f"{col_letter(i)}{row}", deadline, None

    # ------------------------------------------------------------ grading
    def pages(self, s):
        import pymupdf as fitz
        out = []
        for f in s["files"]:
            data = self.g.download(f)
            if data[:4] == b"%PDF":
                doc = fitz.open(stream=data, filetype="pdf")
                for pg in doc:
                    z = SIDE / max(pg.rect.width, pg.rect.height)
                    out.append(pg.get_pixmap(matrix=fitz.Matrix(z, z), colorspace=fitz.csRGB).tobytes("jpeg", jpg_quality=82))
            else:
                out.append(to_jpeg(data))
            if len(out) >= MAX_PAGES:
                break
        return out[:MAX_PAGES]

    def reused_pages(self, sid, s, hashes):
        reused = []
        for hx in hashes:
            for other, owner in self.st["hashes"].items():
                if owner["sid"] != sid and (owner["student"] != bare(s["student"]) or owner["code"] != s["code"]) and ham(hx, other) <= 60:
                    reused.append(owner)
                    break
        return reused

    def grade_copy(self, sid, s):
        les = self.lesson(COPY[s["prog"]][s["code"]]["doc"])
        imgs = self.pages(s)
        if not imgs:
            return {"kind": "no_photos", "type": "copy"}
        hashes = [dhash(b) for b in imgs]
        reused = self.reused_pages(sid, s, hashes)
        parts = "\n".join(f"{i}. {p['name']} (bắt đầu: {p['starts'][:60]})" for i, p in enumerate(les["parts"], 1))
        content = [{"type": "text", "text": f"Vở của học sinh ({len(imgs)} ảnh):"}] + [img_block(b) for b in imgs]
        content.append({"type": "text", "text": COPY_PROMPT.format(title=COPY[s["prog"]][s["code"]].get("title") or s["code"],
                                                                   parts=parts, doc=les["text"])})
        cat = f"{s['cls']} · {KIND_NAME[s['prog']].capitalize()} · {s['code']}"
        with cf.ThreadPoolExecutor(2) as ex:
            a, b = ex.map(lambda _: self.call(content, COPY_SCHEMA, cat), range(2))
        # merged in the pupil's favour: a part is missing only if both reads say so
        best = {}
        for x in a.get("parts", []) + b.get("parts", []):
            if 1 <= x["id"] <= len(les["parts"]) and STATUS_RANK[x["status"]] >= STATUS_RANK.get(best.get(x["id"]), -1):
                best[x["id"]] = x["status"]
        n = len(les["parts"])
        status = {i: best.get(i, "missing") for i in range(1, n + 1)}
        pct = round(100 * sum({"full": 1, "unclear": 1, "partly": 0.5}.get(v, 0) for v in status.values()) / n) if n else 0
        pb = {p["page"]: p for p in b.get("pages", [])}
        pg = []
        for p in a.get("pages", []):
            q = pb.get(p["page"], p)
            pg.append({"kind": p["kind"] if p["kind"] == q["kind"] else "handwritten",
                       "readable": p["readable"] if p["readable"] == q["readable"] else "partly",
                       "messy": p.get("neat") == q.get("neat") == "messy"})
        out = {"type": "copy", "kind": "scored", "pct": pct, "pages": len(imgs), "hashes": hashes,
               "missing": [les["parts"][i - 1]["name"] for i, v in status.items() if v == "missing"],
               "partly": [les["parts"][i - 1]["name"] for i, v in status.items() if v == "partly"], "total": n,
               "messy": bool(pg) and sum(p["messy"] for p in pg) * 2 >= len(pg)}
        if pg and sum(p["kind"] == "printed_or_screen" for p in pg) * 2 > len(pg):
            out["kind"] = "printed"
        elif reused and len(reused) * 2 >= len(imgs):
            out.update(kind="reused", reusedFrom=reused[0])
        elif a.get("otherLesson") and b.get("otherLesson") and pct < 50:
            out["kind"] = "wrong_unit"
        elif pg and all(p["readable"] == "no" for p in pg):
            out["kind"] = "unreadable"
        return out

    def video_seconds(self, fid):
        try:
            m = self.g._req(f"https://www.googleapis.com/drive/v3/files/{fid}?supportsAllDrives=true"
                            "&fields=mimeType,size,videoMediaMetadata(durationMillis)")
        except Exception:
            return "unreadable"
        d = (m.get("videoMediaMetadata") or {}).get("durationMillis")
        return round(int(d) / 1000) if d else None

    def call(self, content, schema, category, max_tokens=6000):
        r = self.cl.messages.create(model=MODEL, max_tokens=max_tokens, thinking={"type": "disabled"},
                                    tools=[{"name": "record", "description": "Ghi lại kết quả", "input_schema": schema}],
                                    tool_choice={"type": "tool", "name": "record"},
                                    messages=[{"role": "user", "content": content}])
        u = r.usage.model_dump()
        c = cw.cost_usd(MODEL, u)
        cw.ledger({"at": cw.now_iso(), "category": category, "step": "fighter-notebook", "model": MODEL,
                   "usage": u, "usd": c, "vnd": round(c * cw.USD_VND)})
        self.r.tick("fnb_cost_vnd", round(c * cw.USD_VND))
        return json.loads(json.dumps(next(b.input for b in r.content if b.type == "tool_use")))

    def lesson(self, doc):
        """Lecture text (Drive export, cached with the encrypted state) and its fixed list of parts (one Haiku call per lecture)."""
        docs = self.st.setdefault("docs", {})
        if doc not in docs:
            text = None
            for mime in ("text/markdown", "text/plain"):
                try:
                    text = self.g._req(f"https://www.googleapis.com/drive/v3/files/{doc}/export?mimeType={mime}", raw=True).decode("utf-8", "replace")
                    break
                except Exception:
                    continue
            if not text:
                raise RuntimeError("LECTURE_NOT_READABLE")
            text = re.sub(r"\\([*\[\]_#])", r"\1", text)[:14000]
            parts = self.call([{"type": "text", "text": OUTLINE_PROMPT.format(doc=text)}], OUTLINE_SCHEMA, "Fighter · Chia phần bài giảng", 2000)["parts"]
            docs[doc] = {"text": text, "parts": parts[:12]}
        return docs[doc]

    def grade(self, sid, s):
        if s["prog"] in COPY:
            return self.grade_copy(sid, s)
        unit = VOCAB[s["code"]]
        imgs = self.pages(s)
        if not imgs:
            return {"kind": "no_photos"}
        hashes = [dhash(b) for b in imgs]
        reused = self.reused_pages(sid, s, hashes)   # 1024-bit hash: different pages differ by ~350, a re-saved photo by <50
        ents = unit["entries"]
        step = max(1, len(ents) // 5)
        spot = [e["n"] for e in ents[::step]][:5]
        listing = "\n".join(f"{e['n']}. {e['term']} — {e['vi']}" for e in ents)
        content = [{"type": "text", "text": "Ảnh mẫu sổ 7 cột:"}, img_block(SAMPLE.read_bytes()),
                   {"type": "text", "text": f"Bài làm của học sinh ({len(imgs)} ảnh):"}]
        content += [img_block(b) for b in imgs]
        content.append({"type": "text", "text": PROMPT.format(code=s["code"], title=unit["title"], first=ents[0]["n"],
                                                              last=ents[-1]["n"], listing=listing, spot=", ".join(map(str, spot)))})
        def read():
            r = self.cl.messages.create(model=MODEL, max_tokens=6000, thinking={"type": "disabled"},
                                        tools=[{"name": "record", "description": "Ghi lại những gì đọc được", "input_schema": SCHEMA}],
                                        tool_choice={"type": "tool", "name": "record"},
                                        messages=[{"role": "user", "content": content}])
            u = r.usage.model_dump()
            c = cw.cost_usd(MODEL, u)
            cw.ledger({"at": cw.now_iso(), "category": f"{s['cls']} · Sổ từ vựng · {s['code']}", "step": "fighter-notebook",
                       "model": MODEL, "usage": u, "usd": c, "vnd": round(c * cw.USD_VND)})
            return json.loads(json.dumps(next(b.input for b in r.content if b.type == "tool_use"))), c
        # two independent reads, merged in the pupil's favour: a word/column counts as missing only if BOTH reads miss it
        with cf.ThreadPoolExecutor(2) as ex:
            (a, ca), (b, cb) = ex.map(lambda _: read(), range(2))
        c = ca + cb
        pb = {p["page"]: p for p in b.get("pages", [])}
        for p in a.get("pages", []):
            q = pb.get(p["page"])
            if q and q["kind"] != p["kind"]:
                p["kind"] = "handwritten"
            if q and "no" in (p["readable"], q["readable"]) and p["readable"] != q["readable"]:
                p["readable"] = "partly"
            p["neat"] = "messy" if (q and p.get("neat") == q.get("neat") == "messy") else "ok"   # both reads must agree
        res = {"pages": a.get("pages", []), "entries": a.get("entries", []) + b.get("entries", []),
               "otherTerms": min(a.get("otherTerms", 0), b.get("otherTerms", 0)),
               "meaningCheck": [m for m in a.get("meaningCheck", [])
                                if any(x["n"] == m["n"] and x["match"] == m["match"] for x in b.get("meaningCheck", []))]}
        self.r.tick("fnb_cost_vnd", round(c * cw.USD_VND))
        sc = score(unit, res)
        pg = res.get("pages", [])
        out = {"kind": "scored", **sc, "pages": len(imgs), "hashes": hashes, "costVnd": round(c * cw.USD_VND)}
        if pg and sum(p["kind"] == "printed_or_screen" for p in pg) * 2 > len(pg):
            out["kind"] = "printed"
        elif reused and len(reused) * 2 >= len(imgs):
            out.update(kind="reused", reusedFrom=reused[0])
        elif sc["written"] >= 16 and res.get("otherTerms", 0) >= 8 and sc["seen"] * 20 < sc["written"] * 3:   # entries of two reads
            out["kind"] = "wrong_unit"
        elif pg and all(p["readable"] == "no" for p in pg):
            out["kind"] = "unreadable"
        out["messy"] = bool(pg) and sum(p.get("neat") == "messy" for p in pg) * 2 >= len(pg)
        mc = [m for m in res.get("meaningCheck", []) if m["match"] != "unclear"]
        out["meaningOff"] = sum(m["match"] == "no" for m in mc) >= 4
        secs = self.video_seconds(s["video"]) if s.get("video") else "none"
        need = max(20, round(1.2 * sc["total"]))
        out["video"] = ("none" if secs == "none" else "short" if isinstance(secs, int) and secs < need else "ok")
        out["videoSecs"], out["videoNeed"] = (secs if isinstance(secs, int) else None), need
        return out

    # ------------------------------------------------------------ feedback text
    def comment(self, s, res, count_incomplete):
        label, unit = unit_label(s["code"])
        what = "SỔ TỪ VỰNG" if s["prog"] not in COPY else KIND_NAME[s["prog"]].upper()
        book = "sổ" if s["prog"] not in COPY else "vở"
        if res["kind"] == "no_photos":
            return f"⛔ CHƯA GHI NHẬN {what}\n• Không mở được ảnh/tệp {book} con gửi.\n→ Con chụp rõ, đủ các trang {book} và nộp lại nhé.", False
        if res["kind"] == "unreadable":
            return (f"⛔ CHƯA GHI NHẬN {what}\n• Ảnh {book} quá mờ/bị cắt nên không đọc được.\n"
                    "→ Con chụp lại rõ nét, đủ sáng, đủ các trang và nộp lại nhé."), False
        if res["kind"] in ("printed", "reused", "wrong_unit"):
            prev = res.get("reusedFrom", {}).get("code")
            why = {"printed": f"{book.capitalize()} nộp là bản in/ảnh chụp màn hình, không phải chép tay.",
                   "reused": f"Ảnh {book} trùng với bài đã nộp trước đó" + (f" ({' '.join(unit_label(prev))})" if prev else "") + ".",
                   "wrong_unit": (f"Các từ trong sổ không phải từ của {label} {unit}." if s["prog"] not in COPY
                                  else f"Nội dung trong vở không phải bài giảng của {label} {unit}.")}[res["kind"]]
            return f"⛔ KHÔNG ĐƯỢC GHI NHẬN\n• {why}\n→ Con chép tay đúng {label} {unit} vào {book} và nộp lại.", False
        if res.get("type") == "copy":
            lines = [f"Mức hoàn thành {KIND_NAME[s['prog']]}: {res['pct']}% "
                     f"({res['total'] - len(res['missing']) - len(res['partly'])}/{res['total']} phần chép đủ)."]
            if res["missing"]:
                lines.append("• Chưa chép: " + "; ".join(res["missing"]) + ".")
            if res["partly"]:
                lines.append("• Chép thiếu nội dung: " + "; ".join(res["partly"]) + ".")
            if res.get("messy"):
                lines.append("• Chữ viết cẩu thả, bẩn, khó đọc. Con viết lại cẩn thận, rõ ràng, sạch sẽ.")
            ok = res["pct"] >= PASS and not res.get("messy")
            if not ok:
                lines.append("→ Con chép bổ sung đầy đủ các phần còn thiếu, chụp nộp lại trước buổi học tới." if res["pct"] < PASS
                             else "→ Con chép lại cẩn thận và nộp lại trước buổi học tới.")
            return "\n".join(lines), ok
        lines = [f"Mức hoàn thành sổ từ vựng: {res['pct']}% ({res['total'] - len(res['missing'])}/{res['total']} từ"
                 + (", đủ 7 cột)." if res["pct"] >= 100 else ").")]
        if res["missing"]:
            lines.append(f"• Thiếu {len(res['missing'])} từ: số {ranges(res['missing'])}.")
        for f, label in FIELDS:
            if res["empty"][f]:
                lines.append(f"• Trống cột {label} ở {len(res['empty'][f])} từ: số {ranges(res['empty'][f])}.")
        if res.get("messy"):
            lines.append("• Chữ viết cẩu thả, bẩn, khó đọc. Con viết lại cẩn thận, rõ ràng, sạch sẽ, bám sát dòng kẻ.")
        if res.get("meaningOff"):
            lines.append("• Nhiều nghĩa tiếng Việt chép không khớp với từ; con đối chiếu lại với web học.")
        if res["video"] == "none":
            lines.append("• Chưa có video trả từ.")
        elif res["video"] == "short":
            lines.append(f"• Video trả từ quá ngắn ({res['videoSecs']} giây) so với {res['total']} từ; con quay lại đủ các từ.")
        else:
            lines.append("• Video trả từ: đã có.")
        ok = res["pct"] >= PASS and res["video"] != "none" and not res.get("messy")
        if not ok:
            lines.append("→ Con bổ sung đủ các từ và các cột còn thiếu, chụp nộp lại trước buổi học tới." if res["pct"] < PASS
                         else "→ Con viết lại sổ cẩn thận và nộp lại trước buổi học tới." if res.get("messy")
                         else "→ Con quay video trả từ và nộp bổ sung trước buổi học tới.")
        return "\n".join(lines), ok

    # ------------------------------------------------------------ main step
    def write(self, s, a1, deadline, text):
        tr = self.r.tracker(s["cls"])
        cur = tr.cell(a1)
        sub_t = parse_vn_time(s["submittedAt"])
        marked = cur.strip() and not cur.startswith("⛔") and "CHƯA GHI NHẬN" not in cur.split("\n")[0]
        if not marked:
            if now() < sub_t + dt.timedelta(minutes=STATUS_WAIT_MIN):
                return "wait"
            prefix = ("⚠️ ĐÃ NỘP MUỘN" if deadline and sub_t > deadline else "✅ ĐÃ NỘP") + "\n" + sub_t.strftime("%d/%m/%Y %H:%M")
            existing = ""
        elif MARK in cur:
            prefix, existing = cur.split(MARK, 1)
            existing = existing.strip()
        else:
            prefix, existing = cur, ""
        prev = s.get("published")
        if "GHI CHÚ GV" in prefix.upper() or (existing and existing != prev and not (prev and prev in existing)):
            return "teacher_comment"   # a note Cô/staff wrote is never overwritten
        body = existing.replace(prev, text) if prev and prev in existing else text
        new = prefix.rstrip() + "\n\n" + MARK + "\n" + body
        tr.write(a1, new)
        return "ok" if tr.cell(a1) == new else "readback_mismatch"

    def run(self):
        self.scan()
        subs = self.st["subs"]
        for s in subs.values():
            if s["status"] == "published" and s.get("ver", 1) < VERSION:
                s.update(status="new", tries=0, regrade=True)
                self.tick("regrade_new_rules")
        todo = []
        for sid, s in subs.items():
            if s["status"] in ("published", "skipped", "not_in_roster", "held_error"):
                continue
            if s["status"] == "graded":
                continue
            a1, deadline, why = self.cell_for(s)
            if why:
                s.update(status="not_in_roster" if why == "not_in_roster" else "new", hold=why)
                self.tick(why)
                continue
            # a later notebook of the same unit replaces an earlier one only if that one was incomplete
            done = [x for x in subs.values() if x is not s and x["cls"] == s["cls"] and bare(norm(x["student"])) == bare(norm(s["student"]))
                    and x["code"] == s["code"] and x["status"] == "published"]
            if any(x.get("ok") for x in done):
                s.update(status="skipped", hold="already_complete")
                continue
            s["cell"], s["deadline"] = a1, deadline.isoformat() if deadline else None
            todo.append((sid, s))
        with cf.ThreadPoolExecutor(6) as ex:
            futs = {ex.submit(self.grade, sid, s): (sid, s) for sid, s in todo}
            for fu in cf.as_completed(futs):
                sid, s = futs[fu]
                try:
                    s["result"] = fu.result()
                    s["status"] = "graded"
                    self.tick("graded")
                except Exception as e:
                    s["tries"] = s.get("tries", 0) + 1
                    s["error"] = type(e).__name__
                    self.tick("error_" + type(e).__name__)
                    if s["tries"] >= 6:   # our side failing (Drive access, API): never blame the pupil, keep it for a fix
                        s["status"] = "held_error"
        for sid, s in subs.items():   # publish (graded earlier or just now)
            if s["status"] != "graded":
                continue
            res = s["result"]
            key = (s["cls"], bare(norm(s["student"])))
            earlier = sorted({x["code"] for x in subs.values() if (x["cls"], bare(norm(x["student"]))) == key
                              and x["status"] == "published" and not x.get("ok") and x["code"] != s["code"]
                              and (x["prog"] in COPY) == (s["prog"] in COPY) and (x["prog"] == s["prog"] or s["prog"] not in COPY)})
            text, ok = self.comment(s, res, len(earlier))
            if not ok and len(earlier) >= 2:
                label = unit_label(s["code"])[0]
                units = ", ".join(unit_label(c)[1] for c in earlier + [s["code"]])
                book = "sổ từ vựng" if s["prog"] not in COPY else KIND_NAME[s["prog"]]
                text += f"\n• Đây là lần thứ {len(earlier) + 1} con nộp {book} chưa đầy đủ ({label} {units})."
            dl = dt.datetime.fromisoformat(s["deadline"]) if s.get("deadline") else None
            w = self.write(s, s["cell"], dl, text)
            if w == "wait":
                self.tick("waiting_status_line")
                continue
            if w != "ok":
                s.update(status="skipped" if w == "teacher_comment" else "graded", hold=w)
                self.tick(w)
                continue
            s.update(status="published", published=text, ok=ok, publishedAt=now().isoformat(), ver=VERSION)
            for hx in res.get("hashes", []):
                self.st["hashes"][hx] = {"sid": sid, "student": bare(s["student"]), "code": s["code"]}
            self.tick("published")

    def save(self):
        save_json(STATE, self.st)


def run(runner):
    if os.environ.get("FIGHTER_STATE"):
        cw.LEDGER = STATE.parent / "ledger.jsonl"   # cost ledger kept with the Fighter state
    STATE.parent.mkdir(parents=True, exist_ok=True)
    fn = FighterNotebooks(runner)
    try:
        fn.run()
    finally:
        fn.save()
