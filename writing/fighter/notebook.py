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
        "GRAMMAR FOUNDATION": "GF", "ĐOẠN VĂN HỌC THUẬT": "AP",
        "READING 2 - VỞ CHỮA": "RC2", "READING 1 - VỞ CHỮA": "RC1"}
PT_FORM = "111wsgqFHovbArNS-KuZaxTHh1nOQzZewcWWjWRNU8Wo"   # "LUYỆN ĐỀ - NỘP SỔ LUYỆN ĐỀ & SỔ TỪ VỰNG"
SOURCES = [(FORM, tab, prog) for tab, prog in TABS.items()] + [(PT_FORM, "Câu trả lời biểu mẫu 1", "PT")]
PRACTICE = json.loads((HERE / "practice.json").read_text(encoding="utf-8"))   # PTn → lesson-site pages (answer key, words)
READING = json.loads((HERE / "reading.json").read_text(encoding="utf-8"))   # code → lesson-site pages (test answers, correction words)
SITE = "https://mstrangtrieueducation-droid.github.io/vocabulary-reading-web/"
COPY = {"GF": json.loads((HERE / "grammar.json").read_text(encoding="utf-8")),      # vở chép lí thuyết ngữ pháp
        "AP": json.loads((HERE / "paragraph.json").read_text(encoding="utf-8"))}    # vở chép bài giảng đoạn văn (Buổi 1–15)
KIND_NAME = {"GF": "vở chép lí thuyết", "AP": "vở chép bài giảng", "RC1": "vở chữa Reading", "RC2": "vở chữa Reading",
             "PT": "sổ luyện đề"}
START = dt.datetime(2026, 11, 8, 0, 0, tzinfo=VN)
MODEL = "claude-haiku-5-5"
VERIFY_MODEL = "claude-sonnet-5-5"
LEAN_MODEL = "claude-sonnet-5-5"     # Cô 11/11: lecture-copy notebooks (GF, AP) read ONCE by Sonnet, sent as a batch (half price)
LEAN_PROGS = {"GF", "AP"}
LEAN_SIDE = 1200                     # photo size for that read: enough to see the handwriting, a third of the image cost
LEAN_ALL = True                      # Cô 11/11 ("Sonnet chấm đúng hết"): every notebook — vocab books and reading books too
LEAN_TABLE_SIDE = 1400               # vocab tables have 7 narrow columns: a little sharper
SIDE = 1568
MAX_PAGES = 14
PASS = 90
VERSION = 27              # raise when the scoring changes: our own published results are regraded once and replaced
GROUP_MINUTES = 30          # rows of one student/unit sent within 30 min = one submission (photos split over rows)
STATUS_WAIT_MIN = 0         # Cô 10/11: grade as soon as a notebook is submitted; we write the receipt line ourselves if the sync has not
FIELDS = [("type", "Từ loại"), ("ipa", "Phiên âm"), ("vi", "Nghĩa tiếng Việt"), ("en", "Nghĩa tiếng Anh"), ("example", "Ví dụ")]
PROGRAM_HEAD = {"VF1": r"Vocabulary Foundation 1", "VF2": r"Vocabulary Foundation 2",
                "RI1": r"READING 1\s*-\s*TỪ VỰNG", "RI2": r"READING 2\s*-\s*TỪ VỰNG",
                "GF": r"Grammar Foundation", "AP": r"ĐOẠN VĂN HỌC THUẬT",
                "RC2": r"READING 2\s*-\s*VỞ CHỮA", "RC1": r"READING 1\s*-\s*VỞ CHỮA", "PT": r"LUYỆN ĐỀ"}

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
   neat = neat / acceptable / messy. CHỈ chọn messy khi trang thật sự ẩu: nét chữ nguệch ngoạc khó đọc, gạch xoá hoặc bôi
   bẩn nhiều chỗ, trang lem nhem, viết tràn lộn xộn không theo cột/dòng. Chữ nghiêng, chữ nối, chữ nhỏ, chữ không đẹp nhưng
   đọc được đều là acceptable. Ảnh mờ/tối do chụp KHÔNG phải messy. Phân vân thì chọn acceptable.
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
                                                                    "required": ["id", "status", "lacking"],
                                                                    "properties": {"id": I, "status": {"type": "string", "enum": ["full", "partly", "missing", "unclear"]},
                                                                                   "lacking": S}}},
                              "otherLesson": {"type": "boolean"}}}
OUTLINE_PROMPT = """Dưới đây là TÀI LIỆU BÀI GIẢNG mà học sinh phải chép tay vào vở. Hãy chia tài liệu thành các PHẦN CHÍNH (4–12 phần) — CHỈ các phần nội dung học sinh phải chép (lí thuyết, ví dụ, bảng, bài mẫu, từ vựng); BỎ tiêu đề, lời dặn/hướng dẫn cách học, chú thích màu, quy trình học
theo đúng thứ tự trong tài liệu, để giáo viên kiểm tra học sinh đã chép đủ chưa. Dùng các đề mục có sẵn (I, II, 1, 2…, Outline,
Bài mẫu, Từ vựng…); phần nào quá ngắn thì gộp với phần bên cạnh. name = tên phần ngắn gọn (≤ 60 ký tự, giữ ngôn ngữ của tài liệu);
starts = vài chữ đầu của phần đó. Trả kết quả qua công cụ record.

TÀI LIỆU:
{doc}"""
AP_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["pages", "outline", "model", "vocab", "revised", "otherLesson"],
             "properties": {"pages": {"type": "array", "items": PAGE},
                            "revised": {"type": "object", "additionalProperties": False, "required": ["present", "words"],
                                        "properties": {"present": {"type": "string", "enum": ["yes", "no", "unclear"]}, "words": I}},
                            "outline": {"type": "object", "additionalProperties": False, "required": ["status", "lacking"],
                                        "properties": {"status": {"type": "string", "enum": ["full", "partly", "missing", "unclear"]},
                                                       "lacking": S}},
                            "model": {"type": "object", "additionalProperties": False, "required": ["present", "lastSentence"],
                                      "properties": {"present": {"type": "string", "enum": ["yes", "no", "unclear"]}, "lastSentence": I}},
                            "vocab": {"type": "array", "items": S}, "otherLesson": {"type": "boolean"}}}
AP_PROMPT = """Bạn đọc ảnh VỞ ĐOẠN VĂN HỌC THUẬT viết tay của một học sinh ({title}). Bạn KHÔNG chấm, KHÔNG nhận xét; chỉ ghi lại đúng
những gì nhìn thấy. Học sinh phải có: đoạn REVISED VERSION tự viết lại sau khi được chữa, sơ đồ OUTLINE của bài, BÀI MẪU (thường ở ô BÀI MẪU THAM KHẢO) và các từ/cụm từ (có thể ghi ở lề,
đầu trang hoặc cuối trang, viết nhỏ, nghiêng) — nhìn kỹ cả lề, đầu/cuối trang và các trang sau.

1. pages: với MỖI ảnh, theo thứ tự 1, 2, 3…: kind = handwritten / printed_or_screen / not_a_notebook; readable = yes / partly / no;
   neat = neat / acceptable / messy (CHỈ messy khi nét chữ nguệch ngoạc khó đọc, gạch xoá/bôi bẩn nhiều; phân vân → acceptable).
2. outline: học sinh đã chép SƠ ĐỒ OUTLINE (luận điểm, ý chính – ý phụ) của bài chưa, so với ẢNH OUTLINE MẪU (nếu có):
   status = full (đủ các nhánh chính) / partly (thiếu rõ ràng một số nhánh/ý) / missing (không có) / unclear;
   lacking: CHỈ khi partly — ghi ngắn (≤ 15 chữ) nhánh/ý còn thiếu; còn lại "".
2b. revised: present = yes nếu có đoạn REVISED VERSION — đoạn văn học sinh TỰ VIẾT LẠI sau khi được cô chữa (thường ở ô
   REVISED VERSION, cùng đề bài, khác bài mẫu); words = số chữ ước lượng (0 nếu không có).
3. model: present = yes nếu có chép bài mẫu; lastSentence = SỐ THỨ TỰ câu cuối cùng của bài mẫu (đánh số bên dưới) mà học sinh
   đã chép tới (đọc hết ô Bài mẫu tham khảo, kể cả dòng cuối trang và trang sau). Chép hết → số câu cuối cùng; không chép → 0.
4. vocab: danh sách các từ/cụm từ tiếng Anh học sinh đã ghi (mục từ vựng ở bất kỳ chỗ nào trên trang), mỗi mục một chuỗi, nguyên văn.
5. otherLesson = true nếu vở chủ yếu là bài của một buổi khác (đề bài khác).

BÀI MẪU (để đối chiếu, đã đánh số câu):
{model}

TỪ VỰNG CỦA BÀI:
{vocab}

Trả kết quả DUY NHẤT qua công cụ record."""


def docs_api_text(g, doc):
    """(text, outline picture) of a Google Doc through the Docs API (service account, documents.readonly)."""
    import urllib.request
    try:
        old = gapi_scopes = None
        import gapi
        old = gapi.SCOPES
        gapi.SCOPES = "https://www.googleapis.com/auth/documents.readonly https://www.googleapis.com/auth/drive.readonly"
        tok = gapi.Google(g.account).token()
        gapi.SCOPES = old
        req = urllib.request.Request(f"https://docs.googleapis.com/v1/documents/{doc}?includeTabsContent=true",
                                     headers={"Authorization": "Bearer " + tok})
        d = json.loads(urllib.request.urlopen(req, timeout=120).read())
    except Exception:
        if old:
            import gapi
            gapi.SCOPES = old
        return None, None
    out, pics = [], []

    def para(p):
        return "".join(e.get("textRun", {}).get("content", "") for e in p.get("elements", []))

    def walk(content):
        for el in content or []:
            if "paragraph" in el:
                out.append(para(el["paragraph"]))
            elif "table" in el:
                for row in el["table"].get("tableRows", []):
                    cells = []
                    for c in row.get("tableCells", []):
                        cells.append("\n".join(para(x["paragraph"]) for x in c.get("content", []) if "paragraph" in x))
                    out.append(" | ".join(cells) + "\n")

    def tabs(ts):
        for t in ts or []:
            dt_ = t.get("documentTab", {})
            walk(dt_.get("body", {}).get("content"))
            for o in (dt_.get("inlineObjects") or {}).values():
                emb = o.get("inlineObjectProperties", {}).get("embeddedObject", {})
                uri = emb.get("imageProperties", {}).get("contentUri")
                size = emb.get("size", {})
                if uri:
                    area = (size.get("width", {}).get("magnitude", 0) or 0) * (size.get("height", {}).get("magnitude", 0) or 0)
                    pics.append((area, uri))
            tabs(t.get("childTabs"))
    tabs(d.get("tabs"))
    figure = None
    for _, uri in sorted(pics, reverse=True)[:1]:
        try:
            raw = urllib.request.urlopen(urllib.request.Request(uri, headers={"Authorization": "Bearer " + tok}), timeout=60).read()
            figure = img_block(to_jpeg(raw))["source"]["data"]
        except Exception:
            figure = None
    return "".join(out), figure


def ap_reference(text):
    """Model paragraph and word list of an Academic Paragraph lesson doc; None when the doc has another layout (Buổi 1)."""
    t = unicodedata.normalize("NFC", re.sub(r"\\([*\[\]_#\\])", r"\1", str(text or "")))
    low = t.lower()
    j = low.find("từ vựng và cụm từ")
    i = low.rfind("bài mẫu", 0, j) if j > 0 else -1
    if i < 0 or j < 0 or j < i or t.find("PHÂN TÍCH") > 0 or t.find("KỸ THUẬT") > 0:
        return None
    model = re.sub(r"\s+([,.;:!?])", r"\1", re.sub(r"\s+", " ", re.sub(r"\*+|\|", " ", t[i + len("Bài mẫu"):j]))).strip()
    tail = t[j + len("từ vựng và cụm từ"):]
    vocab = []   # "term (TT): nghĩa — ví dụ." items, separated by new lines, <br> or a full stop
    for m in re.finditer(r"(?:^|[.\n>|])\s*[-•]?\s*([A-Za-z][^\n():|.<>]{1,60}?)\s*\(([^)]{1,14})\)\s*:", re.sub(r"\*+", "", tail)):
        vocab.append(re.sub(r"\s+", " ", m.group(1)).strip(" .:"))
    if len(model.split()) < 60 or len(vocab) < 3:
        return None
    return {"model": model, "vocab": vocab}


def sentences(text):
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+(?=[A-Z])", str(text or "").strip()) if x.strip()]


def model_reach(model, last):
    """Share of the model paragraph copied, from the last words the pupil wrote (0–1)."""
    mw = [core(w) for w in model.split()]
    lw = [core(w) for w in str(last or "").split() if core(w)]
    if not lw or not mw:
        return 0.0
    k = len(lw)
    best, at = 0.0, 0
    for e in range(k, len(mw) + 1):
        r = difflib.SequenceMatcher(None, mw[e - k:e], lw).ratio()
        if r >= best:
            best, at = r, e
    return at / len(mw) if best >= 0.5 else 0.0


class Pending(Exception):
    """The read was queued in a Message Batch; the submission is graded when the answer is back."""


def judge_messy(read):
    """Sonnet's read agrees the handwriting is messy on at least two thirds of the pages."""
    pg = read.get("pages", [])
    return bool(pg) and sum(p.get("neat") == "messy" for p in pg) * 3 >= len(pg) * 2


def lean_copy_result(read, parts, imgs, hashes, reused):
    """One Sonnet read of a lecture-copy notebook: copied / missing / unreadable per part (unreadable → re-photograph)."""
    n = len(parts)
    st = {x["id"]: x["status"] for x in read.get("parts", []) if 1 <= x["id"] <= n}
    status = {i: st.get(i, "missing") for i in range(1, n + 1)}
    pg = [{"kind": p["kind"], "readable": p["readable"], "messy": p.get("neat") == "messy"} for p in read.get("pages", [])]
    pct = round(100 * sum(v != "missing" for v in status.values()) / n) if n else 0
    out = {"type": "copy", "kind": "scored", "pct": pct, "pages": len(imgs), "hashes": hashes, "lean": True,
           "missing": [parts[i - 1]["name"] for i, v in status.items() if v == "missing"], "partly": [],
           "blurry": [parts[i - 1]["name"] for i, v in status.items() if v == "unreadable"], "total": n,
           "messy": bool(pg) and sum(p["messy"] for p in pg) * 3 >= len(pg) * 2}
    if pg and sum(p["kind"] == "printed_or_screen" for p in pg) * 2 > len(pg):
        out["kind"] = "printed"
    elif reused and len(reused) * 2 >= len(imgs):
        out.update(kind="reused", reusedFrom=reused[0])
    elif read.get("otherLesson") and pct < 50:
        out["kind"] = "wrong_unit"
    elif pg and all(p["readable"] == "no" for p in pg):
        out["kind"] = "unreadable"
    return out


def copy_passes(out):
    return out["kind"] == "scored" and out["pct"] >= PASS and not out["messy"] and not out.get("blurry")


def copy_clean(out):
    """Nothing to say against the notebook: no second opinion needed."""
    return copy_passes(out) and out["pct"] >= 100


def copy_result(reads, parts, imgs, hashes, reused, judge=None):
    """Lecture-copy notebook. Without a judge: Haiku reads merged in the pupil's favour. With a judge (Sonnet): its
    status decides each part; where it could not see a part (unclear) a Haiku "full" still counts. A part nobody could
    see clearly is listed as blurry: the pupil re-photographs those pages, nothing has to be copied again."""
    n = len(parts)
    best, lack = {}, {}
    for x in [p for r in reads for p in r.get("parts", [])]:
        if 1 <= x["id"] <= n and STATUS_RANK[x["status"]] >= STATUS_RANK.get(best.get(x["id"]), -1):
            if STATUS_RANK[x["status"]] > STATUS_RANK.get(best.get(x["id"]), -1) or not lack.get(x["id"]):
                lack[x["id"]] = str(x.get("lacking") or "").strip().rstrip(".")
            best[x["id"]] = x["status"]
    status = {i: best.get(i, "missing") for i in range(1, n + 1)}
    blurry = []
    if judge is not None:
        jv = {x["id"]: x for x in judge.get("parts", []) if 1 <= x["id"] <= n}
        for i in range(1, n + 1):
            j = jv.get(i, {}).get("status", "missing")
            if j == "unclear":
                if status[i] != "full":
                    blurry.append(i)
                    status[i] = "unclear"
                else:
                    status[i] = "full"
            else:
                status[i] = j
                lack[i] = str(jv[i].get("lacking") or "").strip().rstrip(".") if i in jv else ""
    pct = round(100 * sum({"full": 1, "unclear": 1, "partly": 0.5}.get(v, 0) for v in status.values()) / n) if n else 0
    a = reads[0]
    pb = {p["page"]: p for p in (reads[1] if len(reads) > 1 else a).get("pages", [])}
    pg = []
    for p in a.get("pages", []):
        q = pb.get(p["page"], p)
        pg.append({"kind": p["kind"] if p["kind"] == q["kind"] else "handwritten",
                   "readable": p["readable"] if p["readable"] == q["readable"] else "partly",
                   "messy": p.get("neat") == q.get("neat") == "messy"})
    messy = bool(pg) and sum(p["messy"] for p in pg) * 3 >= len(pg) * 2 and (judge is None or judge_messy(judge))
    out = {"type": "copy", "kind": "scored", "pct": pct, "pages": len(imgs), "hashes": hashes,
           "missing": [parts[i - 1]["name"] for i, v in status.items() if v == "missing"],
           "partly": [parts[i - 1]["name"] + (f" ({lack[i]})" if lack.get(i) else "") for i, v in status.items() if v == "partly"],
           "blurry": [parts[i - 1]["name"] for i in blurry], "total": n, "messy": messy, "verified": judge is not None}
    other = all(r.get("otherLesson") for r in reads) and (judge is None or judge.get("otherLesson"))
    if pg and sum(p["kind"] == "printed_or_screen" for p in pg) * 2 > len(pg):
        out["kind"] = "printed"
    elif reused and len(reused) * 2 >= len(imgs):
        out.update(kind="reused", reusedFrom=reused[0])
    elif other and pct < 50:
        out["kind"] = "wrong_unit"
    elif pg and all(p["readable"] == "no" for p in pg) and (judge is None or all(p.get("readable") == "no" for p in judge.get("pages", []))):
        out["kind"] = "unreadable"
    return out


LEAN_COPY_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["pages", "parts", "otherLesson"],
                    "properties": {"pages": {"type": "array", "items": PAGE},
                                   "parts": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                                         "required": ["id", "status"],
                                                                         "properties": {"id": I, "status": {"type": "string",
                                                                                        "enum": ["copied", "missing", "unreadable"]}}}},
                                   "otherLesson": {"type": "boolean"}}}
LEAN_COPY_PROMPT = """Ảnh trên là VỞ CHÉP BÀI GIẢNG viết tay của một học sinh. Bài giảng phải chép: {title}. Bài giảng gồm các phần:
{parts}

Chỉ ghi lại những gì nhìn thấy, không chấm, không nhận xét.
1. pages — với MỖI ảnh theo thứ tự 1, 2, 3…: kind = handwritten / printed_or_screen (bản in, ảnh màn hình, chữ đánh máy) /
   not_a_notebook; readable = yes / partly / no; neat = neat / acceptable / messy (CHỈ messy khi chữ nguệch ngoạc khó đọc,
   gạch xoá, bôi bẩn nhiều; chữ xấu mà đọc được là acceptable; ảnh mờ do chụp KHÔNG phải messy).
2. parts — với MỖI phần ở trên (id theo số thứ tự):
   copied = trong vở CÓ chép phần này (thấy đề mục hoặc nội dung chính của phần; chép gọn, tóm tắt, thiếu vài ví dụ vẫn là copied);
   missing = ảnh đọc được nhưng KHÔNG có phần này (không có đề mục, không có nội dung của phần), kể cả trang để trống;
   unreadable = ảnh quá mờ / tối / bị cắt nên không nhìn được trang có phần này.
   Không bắt bẻ chi tiết nhỏ. Phân vân giữa copied và missing thì nhìn lại đề mục; vẫn không chắc thì chọn copied.
3. otherLesson = true nếu vở rõ ràng là nội dung của một bài giảng KHÁC (các đề mục không khớp danh sách trên)."""


COPY_PROMPT = """Bạn đọc ảnh VỞ CHÉP BÀI GIẢNG viết tay của một học sinh. Bạn KHÔNG chấm, KHÔNG nhận xét; chỉ ghi lại đúng những gì nhìn thấy.
Học sinh phải chép tay đầy đủ tài liệu bài giảng ({title}) dưới đây vào vở. Tài liệu gồm các phần:
{parts}

1. pages: với MỖI ảnh, theo thứ tự 1, 2, 3…: kind = handwritten / printed_or_screen (bản in, ảnh chụp màn hình, chữ đánh máy,
   dán tài liệu in) / not_a_notebook; readable = yes / partly / no; neat = neat / acceptable / messy (CHỈ messy khi nét chữ
   nguệch ngoạc khó đọc, gạch xoá/bôi bẩn nhiều, trang lem nhem lộn xộn; chữ không đẹp nhưng đọc được là acceptable;
   ảnh mờ do chụp KHÔNG phải messy; phân vân thì chọn acceptable).
2. parts: với MỖI phần ở trên (id theo số thứ tự): full = phần đó CÓ trong vở với các ý chính (định nghĩa / cách dùng /
   bảng / ví dụ chính) — học sinh viết gọn, tóm tắt, thiếu vài ví dụ phụ hay chi tiết nhỏ VẪN là full; partly = chỉ khi thiếu hẳn
   một mục lớn của phần (vd cả bảng, cả mục "cách hình thành", hơn một nửa nội dung); missing = không thấy phần đó trong vở;
   unclear = không nhìn rõ để kết luận. KHÔNG bắt bẻ chi tiết nhỏ. Ảnh mờ, chụp nghiêng hay bị cắt mép mà vẫn thấy phần đó
   có trong vở → full hoặc unclear, KHÔNG phải partly (không phạt học sinh vì ảnh chụp).
   lacking: CHỈ khi partly — ghi cụ thể, ngắn (≤ 20 chữ) phần còn thiếu so với tài liệu, gọi theo tên/ý trong tài liệu
   (vd "thiếu ý 2 và 3 của thân đoạn", "bài mẫu mới chép đến câu 4/9", "thiếu 3 cụm cuối: …"); các trường hợp khác để "".
   Đối chiếu với nội dung tài liệu bên dưới; không đòi chép giống từng chữ, không bắt lỗi chính tả.
3. otherLesson = true nếu vở chủ yếu là nội dung của một bài khác (không phải tài liệu này).

TÀI LIỆU BÀI GIẢNG:
{doc}

Trả kết quả DUY NHẤT qua công cụ record."""
ANS = {"type": "object", "additionalProperties": False, "required": ["n", "answer", "explained"],
       "properties": {"n": I, "answer": S, "explained": {"type": "string", "enum": ["yes", "no", "unclear"]}}}
READING_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["pages", "entries", "answers"],
                  "properties": {"pages": {"type": "array", "items": PAGE}, "entries": SCHEMA["properties"]["entries"],
                                 "answers": {"type": "array", "items": ANS}}}
READING_PROMPT = """Bạn đọc ảnh bài nộp của một học sinh cho bài chữa {title}. Bạn KHÔNG chấm, KHÔNG nhận xét; chỉ ghi lại đúng những gì nhìn thấy.
Bài nộp gồm 2 phần: (A) SỔ TỪ VỰNG các từ cô in đỏ — mỗi từ 7 cột: STT · Từ/cụm từ · Từ loại · Phiên âm · Nghĩa tiếng Việt ·
Nghĩa tiếng Anh · Ví dụ; (B) {book} — học sinh làm lại {total} câu của đề vào vở và viết giải thích cho từng câu.

Các từ của phần A:
{listing}

1. pages: với MỖI ảnh, theo thứ tự 1, 2, 3…: kind = handwritten / printed_or_screen (bản in, ảnh chụp màn hình, chữ đánh máy) /
   not_a_notebook; readable = yes / partly / no; neat = neat / acceptable / messy (CHỈ messy khi nét chữ nguệch ngoạc khó đọc,
   gạch xoá/bôi bẩn nhiều, trang lem nhem lộn xộn; chữ không đẹp nhưng đọc được là acceptable; phân vân thì chọn acceptable).
2. entries (phần A): mỗi mục từ em ĐÃ VIẾT trong sổ: n = số của từ đó trong danh sách trên, term = từ em viết (nguyên văn);
   type, ipa, vi, en, example = filled / empty / unclear. KHÔNG liệt kê từ em không viết; không chắc thì unclear.
3. answers (phần B): mỗi câu em ĐÃ LÀM LẠI trong vở: n = số câu, answer = đáp án em viết (nguyên văn, ngắn), explained = yes
   (có viết giải thích/lí do cho câu đó) / no / unclear. KHÔNG liệt kê câu em không làm.

Trả kết quả DUY NHẤT qua công cụ record."""
DOCS_VERSION = 1            # lecture split + reference picture; kept stable so a notebook is judged the same way each time
PAINT_VERSION = 3           # raise when only the cell colours/sizes change: published cells are repainted, not re-read
BODY_SIZE = 9               # comment text size (Cô 10/11: keep 9, make the row twice as tall instead)
ROW_FACTOR = 2              # rows holding our comments: twice the class sheet's own row height
REGRADE = {"GF", "AP"}
REGRADE_FAILED_ONLY = True  # on a VERSION bump only notebooks below 100% are read again (a clean pass stays)      # programmes whose reading rules changed in this VERSION; others are only re-styled
FLAG = "LỖI: ❌ CẦN NỘP LẠI"   # cell note prefix of our own "redo" mark
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
    if prog == "PT":   # "PRACTICE TEST 4"
        m = re.search(r"(\d+)", raw)
        return f"PT{int(m.group(1))}" if m else None
    if prog in ("RC1", "RC2"):   # RI2-C07, "Test 11"
        m = re.search(r"(\d+)\s*$", raw) or re.search(r"(\d+)", raw)
        return f"RI{prog[-1]}-C{int(m.group(1)):02d}" if m else None
    if prog == "AP":   # AP-B07, "Buổi 05"
        m = re.search(r"(\d+)", raw)
        return f"AP-B{int(m.group(1)):02d}" if m else None
    m = re.search(r"(\d+)\s*$", raw) or re.search(r"U\s*0*(\d+)", raw, re.I)
    return f"{prog}-U{int(m.group(1)):02d}" if m else None


def unit_label(code):
    """Text used in the tracker header and in the comment: 'Unit 14', 'Unit 4.1', 'Buổi 7'."""
    if code.startswith("AP-B"):
        return "Buổi", str(int(code[4:]))
    if code.startswith("PT"):
        return "Practice Test", code[2:]
    m = re.search(r"[UC]0*(\d+(?:\.\d)?)", code)
    return "Unit", m.group(1)


def family(prog):
    return "vocab" if prog in ("VF1", "VF2", "RI1", "RI2") else prog


def known(prog, code):
    if prog == "PT":
        return {"test", "words"} <= set(PRACTICE.get(code, {}))
    if prog in ("RC1", "RC2"):
        return {"test", "correction"} <= set(READING.get(code, {}))
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


def img_block(jpeg: bytes, side=SIDE):
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(jpeg))).convert("RGB")
    im.thumbnail((side, side))
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


def test_section(text, n):
    marks = [(int(m.group(1)), m.start()) for m in re.finditer(r"(?m)^[#\s*\\]*TEST\s*(\d+)\b", text)]
    for i, (k, at) in enumerate(marks):
        if k == n:
            return text[at:marks[i + 1][1] if i + 1 < len(marks) else len(text)]
    return ""


def parse_doc_why(text, total):
    rows = []
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or set("".join(cells)) <= set(":- ") or "Đáp án" in cells[1]:
            continue
        if not re.sub(r"[*\\\s]", "", cells[1]):
            continue
        rows.append(bool(re.sub(r"[*\\\s]", "", "|".join(cells[2:]))))
    return rows if len(rows) == total else None


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
        for sheet, tab, prog in SOURCES:
            try:
                table = self.g.values(sheet, f"'{tab}'!A1:J3000")
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
                    and ((re.search(r"sổ luyện đề\s*&\s*sổ từ vựng", v3, re.I) if s["prog"] == "PT" else re.match(r"\s*Hạn", v3, re.I))
                         or (re.search(r"VỞ CHỮA|TỪ VỰNG", group, re.I) and v2.strip() and "làm lại" not in v3.lower()))):
                hits.append(i)
        if len(hits) != 1:
            return None, None, "tracker_column_" + ("missing" if not hits else "ambiguous")
        i = hits[0]
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(r3[i]))
        deadline = dt.datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), 23, 59, 59, tzinfo=VN) if m else None
        return f"{col_letter(i)}{row}", deadline, None

    # ------------------------------------------------------------ grading
    def pages(self, s, limit=MAX_PAGES):
        import pymupdf as fitz
        out = []
        failed = 0
        for f in s["files"]:
            try:
                data = self.g.download(f)
            except RuntimeError as e:   # never grade on part of the pages: a missing page would read as "not done"
                failed += 1
                self.tick(f"file_unreadable_{str(e)[:20]}[{s['code']}]")
                raise RuntimeError("FILE_UNREADABLE")
            if data[:4] == b"%PDF":
                doc = fitz.open(stream=data, filetype="pdf")
                for pg in doc:
                    z = SIDE / max(pg.rect.width, pg.rect.height)
                    out.append(pg.get_pixmap(matrix=fitz.Matrix(z, z), colorspace=fitz.csRGB).tobytes("jpeg", jpg_quality=82))
            else:
                out.append(to_jpeg(data))
            if len(out) >= limit:
                break
        return out[:limit]

    def reused_pages(self, sid, s, hashes):
        reused = []
        for hx in hashes:
            for other, owner in self.st["hashes"].items():
                src = self.st["subs"].get(owner["sid"], {})
                if (src.get("result") or {}).get("kind") == "wrong_unit":   # pupil sent this notebook under the wrong unit first
                    continue
                if src.get("submittedAt") and parse_vn_time(src["submittedAt"]) >= parse_vn_time(s["submittedAt"]):
                    continue   # only an EARLIER submission can have been reused
                if owner["sid"] != sid and (owner["student"] != bare(s["student"]) or owner["code"] != s["code"]) and ham(hx, other) <= 60:
                    reused.append(owner)
                    break
        return reused

    def grade_ap(self, sid, s, ref):
        imgs = self.pages(s)
        if not imgs:
            return {"kind": "no_photos", "type": "ap"}
        hashes = [dhash(b) for b in imgs]
        reused = self.reused_pages(sid, s, hashes)
        lean = s["prog"] in LEAN_PROGS
        content = [{"type": "text", "text": f"Vở của học sinh ({len(imgs)} ảnh):"}] + [img_block(b, LEAN_SIDE if lean else SIDE) for b in imgs]
        if ref.get("figure"):
            content += [{"type": "text", "text": "ẢNH OUTLINE MẪU của bài (để đối chiếu):"},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": ref["figure"]}}]
        content.append({"type": "text", "text": AP_PROMPT.format(title=COPY[s["prog"]][s["code"]].get("title") or s["code"],
                                                                 model="\n".join(f"[{k}] {x}" for k, x in enumerate(sentences(ref["model"]), 1)),
                                                                 vocab="\n".join(ref["vocab"]))})
        cat = f"{s['cls']} · {KIND_NAME[s['prog']].capitalize()} · {s['code']}"
        if lean:
            return self.ap_score([self.call(content, AP_SCHEMA, cat, model=LEAN_MODEL, batch=True)], ref, imgs, hashes, reused)
        with cf.ThreadPoolExecutor(2) as ex:
            reads = list(ex.map(lambda _: self.call(content, AP_SCHEMA, cat), range(2)))
        first = self.ap_score(reads, ref, imgs, hashes, reused)
        if first["kind"] not in ("scored", "wrong_unit") or (first["kind"] == "scored" and first["pct"] >= 100 and not first["messy"]):
            return first
        try:   # Haiku alone never fails a pupil: one Sonnet read joins the merge
            reads.append(self.call(content, AP_SCHEMA, cat, model=VERIFY_MODEL))
            self.tick("ap_verified")
        except Exception as e:
            self.tick("verify_error_" + type(e).__name__)
            return first
        return self.ap_score(reads, ref, imgs, hashes, reused, verified=len(reads) > 2)

    def ap_score(self, reads, ref, imgs, hashes, reused, verified=False):
        # merged in the pupil's favour
        best = max(reads, key=lambda r: STATUS_RANK[r["outline"]["status"]])
        outline = {"full": 1.0, "unclear": 1.0, "partly": 0.5}.get(best["outline"]["status"], 0.0)
        outline_lack = str(best["outline"].get("lacking") or "").strip().rstrip(".") if best["outline"]["status"] == "partly" else ""
        sents = sentences(ref["model"])
        got = 0
        for r in reads:
            k = max(0, min(len(sents), int(r["model"]["lastSentence"] or 0))) if r["model"]["present"] != "no" else 0
            if r["model"]["present"] in ("yes", "unclear") and not k:   # seen but not placed: benefit of the doubt
                k = len(sents)
            got = max(got, k)
        reach = got / len(sents) if sents else 0.0
        seen = [w for r in reads for w in r.get("vocab", [])]
        have = [v for v in ref["vocab"] if any(sim(v, w) >= 0.8 for w in seen)]
        lack = [v for v in ref["vocab"] if v not in have]
        model_full = got >= len(sents)
        revised = any(r["revised"]["present"] in ("yes", "unclear") and (r["revised"]["words"] >= 60 or r["revised"]["present"] == "unclear")
                      for r in reads)
        pct = round(100 * ((1 if revised else 0) + outline + (1 if model_full else reach) + len(have) / len(ref["vocab"])) / 4)
        pg = []
        pb = {p["page"]: p for p in reads[-1].get("pages", [])}
        for p in reads[0].get("pages", []):
            q = pb.get(p["page"], p)
            pg.append({"kind": p["kind"] if p["kind"] == q["kind"] else "handwritten",
                       "readable": p["readable"] if p["readable"] == q["readable"] else "partly",
                       "messy": p.get("neat") == q.get("neat") == "messy"})
        out = {"type": "ap", "kind": "scored", "pct": pct, "pages": len(imgs), "hashes": hashes, "revised": revised, "outline": outline, "outlineLack": outline_lack,
               "modelFull": model_full, "modelGot": got, "modelTotal": len(sents),
               "modelNext": " ".join(sents[got].split()[:6]) if not model_full and got < len(sents) else "", "vocabHave": len(have), "vocabTotal": len(ref["vocab"]), "vocabLack": lack,
               "messy": bool(pg) and sum(p["messy"] for p in pg) * 3 >= len(pg) * 2 and (not verified or judge_messy(reads[-1]))}
        if pg and sum(p["kind"] == "printed_or_screen" for p in pg) * 2 > len(pg):
            out["kind"] = "printed"
        elif reused and len(reused) * 2 >= len(imgs):
            out.update(kind="reused", reusedFrom=reused[0])
        elif all(r.get("otherLesson") for r in reads) and pct < 50:
            out["kind"] = "wrong_unit"
        elif pg and all(p["readable"] == "no" for p in pg):
            out["kind"] = "unreadable"
        return out

    def grade_copy(self, sid, s):
        les = self.lesson(COPY[s["prog"]][s["code"]]["doc"])
        if s["prog"] == "AP":
            ref = ap_reference(les["text"])
            if ref:
                ref["figure"] = les.get("figure")
                return self.grade_ap(sid, s, ref)
            self.tick(f"ap_layout_other[{s['code']}]")
        imgs = self.pages(s)
        if not imgs:
            return {"kind": "no_photos", "type": "copy"}
        hashes = [dhash(b) for b in imgs]
        reused = self.reused_pages(sid, s, hashes)
        parts = "\n".join(f"{i}. {p['name']} (bắt đầu: {p['starts'][:60]})" for i, p in enumerate(les["parts"], 1))
        if s["prog"] in LEAN_PROGS:
            content = [{"type": "text", "text": f"Vở của học sinh ({len(imgs)} ảnh):"}] + [img_block(b, LEAN_SIDE) for b in imgs]
            content.append({"type": "text", "text": LEAN_COPY_PROMPT.format(
                title=COPY[s["prog"]][s["code"]].get("title") or s["code"], parts=parts)})
            cat = f"{s['cls']} · {KIND_NAME[s['prog']].capitalize()} · {s['code']}"
            read = self.call(content, LEAN_COPY_SCHEMA, cat, model=LEAN_MODEL, batch=True)
            return lean_copy_result(read, les["parts"], imgs, hashes, reused)
        content = [{"type": "text", "text": f"Vở của học sinh ({len(imgs)} ảnh):"}] + [img_block(b) for b in imgs]
        content.append({"type": "text", "text": COPY_PROMPT.format(title=COPY[s["prog"]][s["code"]].get("title") or s["code"],
                                                                   parts=parts, doc=les["text"])})
        cat = f"{s['cls']} · {KIND_NAME[s['prog']].capitalize()} · {s['code']}"
        with cf.ThreadPoolExecutor(2) as ex:
            reads = list(ex.map(lambda _: self.call(content, COPY_SCHEMA, cat), range(2)))
        out = copy_result(reads, les["parts"], imgs, hashes, reused)
        if out["kind"] in ("scored", "wrong_unit", "unreadable") and not copy_clean(out):
            # Haiku alone never fails a pupil: Sonnet reads the notebook once more and its reading decides
            try:
                v = self.call(content, COPY_SCHEMA, cat, model=VERIFY_MODEL)
                out = copy_result(reads, les["parts"], imgs, hashes, reused, judge=v)
                self.tick("copy_verified")
            except Exception as e:
                self.tick("verify_error_" + type(e).__name__)
        return out

    def site(self, d):
        """Lesson-site page (public), cached in the encrypted state."""
        pages = self.st.setdefault("site", {})
        if d not in pages:
            import urllib.request
            req = urllib.request.Request(SITE + d + "/", headers={"User-Agent": "fighter-notebook-checker"})
            pages[d] = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        return pages[d]

    def practice_ref(self, code):
        dec = json.JSONDecoder()
        pg = PRACTICE[code]
        page = self.site(pg["test"])
        i = page.find("const APP = ")
        test = dec.raw_decode(page[i + len("const APP = "):])[0]["test"]
        words = None
        for x in re.findall(r"<script[^>]*>(\{\"(?:test|title)\".*?)</script>", self.site(pg["words"]), re.S):
            d = json.loads(x)
            if d.get("words"):
                words = d["words"]
        if not words or not test.get("answers"):
            raise RuntimeError("PRACTICE_REFERENCE_INCOMPLETE")
        qs = [{"n": int(a["globalNumber"]), "answer": str(a.get("displayAnswer") or (a.get("acceptedAnswers") or [""])[0]),
               "choices": bool(re.fullmatch(r"[A-Da-d]", str(a.get("displayAnswer") or "").strip())),
               "needsWhy": bool(str(a.get("explanation") or "").strip())} for a in test["answers"]]
        return {"title": test.get("title") or f"Practice Test {code[2:]}", "total": int(test.get("total") or len(qs)),
                "words": [{"n": k, "term": w.get("term", ""), "type": w.get("meta", ""), "vi": w.get("meaning", "")}
                          for k, w in enumerate(words, 1)], "questions": qs}

    def reading_ref(self, code):
        if self.st.get("refsVersion") != VERSION:
            self.st["readingRefs"], self.st["refsVersion"] = {}, VERSION
        ref = self.st.setdefault("readingRefs", {})
        if code not in ref and code.startswith("PT"):
            ref[code] = self.practice_ref(code)
        if code not in ref:
            import html as H
            pg = READING[code]
            test = None
            for x in re.findall(r"<script[^>]*>(\{\"unit\".*?)</script>", self.site(pg["test"]), re.S):
                d = json.loads(x)
                if d.get("testCode"):
                    test = d
            corr = self.site(pg["correction"])
            words = []
            for i, card in enumerate(re.findall(r'<article class="word-card">(.*?)</article>', corr, re.S), 1):
                meta = re.search(r'class="word-meta">(.*?)</p>', card, re.S)
                term = re.search(r"<h3>(.*?)</h3>", card, re.S)
                vi = re.search(r'NGHĨA TIẾNG VIỆT</p><p>(.*?)</p>', card, re.S)
                words.append({"n": i, "term": H.unescape(re.sub(r"<[^>]+>", "", term.group(1))).strip() if term else "",
                              "type": H.unescape(meta.group(1)).strip() if meta else "",
                              "vi": H.unescape(re.sub(r"<[^>]+>", "", vi.group(1))).strip() if vi else ""})
            qs = []
            for sec in (test or {}).get("sections", []):
                qlist = sec["questions"] if isinstance(sec["questions"], list) else []
                for q in qlist:
                    qs.append({"n": int(q["number"]), "answer": str(q.get("answer", "")), "choices": bool(sec.get("choices")),
                               "needsWhy": bool(str(q.get("explanation") or "").strip())})
            if not words or not qs:
                raise RuntimeError("READING_REFERENCE_INCOMPLETE")
            why = self.doc_why(pg.get("whyDoc") or pg.get("doc"), len(qs), pg.get("whyPart"))
            if why:   # Cô's correction doc decides which answers need a written explanation
                for q, w in zip(sorted(qs, key=lambda q: q["n"]), why):
                    q["needsWhy"] = w
            ref[code] = {"title": (test or {}).get("title", code), "total": int((test or {}).get("total") or len(qs)),
                         "words": words, "questions": qs}
        return ref[code]

    def doc_why(self, doc, total, part=None):
        """One flag per answer row of the correction doc's table: True when Cô wrote an explanation there."""
        if not doc:
            return None
        try:
            text = self.g._req(f"https://www.googleapis.com/drive/v3/files/{doc}/export?mimeType=text/markdown", raw=True).decode("utf-8", "replace")
        except Exception:
            return None
        if part:   # one doc holding every test: keep the "TEST n" section only
            text = test_section(text, part)
        return parse_doc_why(text, total) if text else None

    def grade_reading(self, sid, s):
        ref = self.reading_ref(s["code"])
        imgs = self.pages(s, limit=24)
        if not imgs:
            return {"kind": "no_photos", "type": "reading"}
        hashes = [dhash(b) for b in imgs]
        reused = self.reused_pages(sid, s, hashes)
        listing = "\n".join(f"{w['n']}. {w['term']} ({w['type']}) — {w['vi']}" for w in ref["words"])
        lean = LEAN_ALL
        content = [{"type": "text", "text": f"Bài nộp ({len(imgs)} ảnh):"}] + [img_block(b, LEAN_TABLE_SIDE if lean else SIDE) for b in imgs]
        content.append({"type": "text", "text": READING_PROMPT.format(title=ref["title"], total=ref["total"], listing=listing,
                                                                     book="SỔ LUYỆN ĐỀ" if s["prog"] == "PT" else "VỞ CHỮA BÀI")})
        cat = f"{s['cls']} · {KIND_NAME[s['prog']].capitalize()} · {s['code']}"
        if lean:   # one Sonnet read (Message Batch)
            a = self.call(content, READING_SCHEMA, cat, 20000, model=LEAN_MODEL, batch=True)
            b = a
        else:
            with cf.ThreadPoolExecutor(2) as ex:
                a, b = ex.map(lambda _: self.call(content, READING_SCHEMA, cat, 20000), range(2))
        reads = [a] if b is a else [a, b]
        vocab = score({"entries": ref["words"]}, {"entries": [e for r in reads for e in r.get("entries", [])]})
        key = {q["n"]: q for q in ref["questions"]}
        ans = {}
        for x in [y for r in reads for y in r.get("answers", [])]:
            if x["n"] in key:
                ans.setdefault(x["n"], []).append(x)
        answered = sorted(ans)
        # Cô's rule: every question that has an explanation in the correction must be explained (more is fine)
        need_why = {n for n, q in key.items() if q.get("needsWhy", True)} or set(key)
        explained = sorted(n for n, xs in ans.items() if n not in need_why or any(x["explained"] != "no" for x in xs))
        norm_a = lambda v: re.sub(r"[^a-z0-9]", "", bare(v))
        wrong = sorted(n for n, xs in ans.items()   # only clear single-letter answers, both reads agreeing
                       if key[n]["choices"] and re.fullmatch(r"[A-Za-z]", key[n]["answer"].strip()) and len(xs) == len(reads)
                       and norm_a(xs[0]["answer"]) == norm_a(xs[-1]["answer"]) and re.fullmatch(r"[a-z]", norm_a(xs[0]["answer"]) or "")
                       and norm_a(xs[0]["answer"]) != norm_a(key[n]["answer"]))
        total = ref["total"]
        work = round(100 * (len(answered) + len(explained)) / (2 * total)) if total else 0
        explained = [n for n in explained if n in need_why]
        pb = {p["page"]: p for p in b.get("pages", [])}
        pg = []
        for p in a.get("pages", []):
            q = pb.get(p["page"], p)
            pg.append({"kind": p["kind"] if p["kind"] == q["kind"] else "handwritten",
                       "readable": p["readable"] if p["readable"] == q["readable"] else "partly",
                       "messy": p.get("neat") == q.get("neat") == "messy"})
        out = {"type": "reading", "kind": "scored", "pages": len(imgs), "hashes": hashes, "vocab": vocab, "total": total,
               "work": work, "notAnswered": [n for n in key if n not in ans],
               "notExplained": [n for n in answered if n in need_why and n not in explained], "needWhy": len(need_why),
               "wrong": wrong, "messy": bool(pg) and sum(p["messy"] for p in pg) * 3 >= len(pg) * 2}
        out["pct"] = min(vocab["pct"], work)
        if pg and sum(p["kind"] == "printed_or_screen" for p in pg) * 2 > len(pg):
            out["kind"] = "printed"
        elif reused and len(reused) * 2 >= len(imgs):
            out.update(kind="reused", reusedFrom=reused[0])
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

    def call(self, content, schema, category, max_tokens=12000, model=MODEL, batch=False):
        if batch:   # answered by a Message Batch (half price): queued now, the answer is picked up by a later cycle
            key = h(json.dumps([model, schema, content], ensure_ascii=False, sort_keys=True), 40)
            got = self.st.setdefault("batchRes", {}).pop(key, None)
            if got is not None:
                if "_error" in got:
                    raise RuntimeError("BATCH_" + got["_error"])
                return got["out"]
            if key not in self.st.setdefault("batchPending", {}):
                self.queue[key] = {"cat": category, "params": {
                    "model": model, "max_tokens": max_tokens, "thinking": {"type": "between_tools"},
                    "output_config": {"format": {"type": "json_schema", "schema": schema}},
                    "messages": [{"role": "user", "content": content}]}}
            raise Pending()
        if model == MODEL:
            r = self.cl.messages.create(model=model, max_tokens=max_tokens, thinking={"type": "disabled"},
                                        tools=[{"name": "record", "description": "Ghi lại kết quả", "input_schema": schema}],
                                        tool_choice={"type": "tool", "name": "record"},
                                        messages=[{"role": "user", "content": content}])
        else:   # Sonnet: forced tool choice is refused with its default thinking, so ask for the tool and check it came
            for _ in range(3):
                r = self.cl.messages.create(model=model, max_tokens=max_tokens + 8000,
                                            tools=[{"name": "record", "description": "Ghi lại kết quả", "input_schema": schema}],
                                            tool_choice={"type": "auto"},
                                            messages=[{"role": "user", "content": content + [{"type": "text", "text":
                                                      "Bắt buộc gọi công cụ record đúng một lần để ghi kết quả."}]}])
                if any(b.type == "tool_use" for b in r.content):
                    break
            else:
                raise RuntimeError("VERIFY_NO_TOOL")
        u = r.usage.model_dump()
        c = cw.cost_usd(model, u)
        if r.stop_reason == "max_tokens":   # a cut-off read would look like "nothing written": never publish it
            self.r.tick("fnb_cost_vnd", round(c * cw.USD_VND))
            raise RuntimeError("READ_TRUNCATED")
        cw.ledger({"at": cw.now_iso(), "category": category, "step": "fighter-notebook", "model": model,
                   "usage": u, "usd": c, "vnd": round(c * cw.USD_VND)})
        self.r.tick("fnb_cost_vnd", round(c * cw.USD_VND))
        return json.loads(json.dumps(next(b.input for b in r.content if b.type == "tool_use")))

    def lesson(self, doc):
        """Lecture text (Drive export, cached with the encrypted state) and its fixed list of parts (one Haiku call per lecture)."""
        if self.st.get("docsVersion") != DOCS_VERSION:   # split the lectures again only when the split rules change
            self.st["docs"], self.st["docsVersion"] = {}, DOCS_VERSION
        docs = self.st.setdefault("docs", {})
        if doc not in docs:
            text = None
            for mime in ("text/markdown", "text/plain"):
                try:
                    text = self.g._req(f"https://www.googleapis.com/drive/v3/files/{doc}/export?mimeType={mime}", raw=True).decode("utf-8", "replace")
                    break
                except Exception:
                    continue
            figure = None
            if not text:   # export blocked (viewers may not download): read it through the Docs API instead
                text, figure = docs_api_text(self.g, doc)
            if not text:
                raise RuntimeError("LECTURE_NOT_READABLE")
            imgs = sorted(re.findall(r"data:image/[a-z+]+;base64,([A-Za-z0-9+/=]+)", text), key=len, reverse=True)
            if imgs and 20000 < len(imgs[0]) < 6000000:   # the outline diagram of the lesson (largest picture)
                try:
                    figure = img_block(to_jpeg(base64.b64decode(imgs[0])))["source"]["data"]
                except Exception:
                    figure = None
            text = re.sub(r"!\[[^\]]*\]\(data:[^)]*\)|^\[[^\]]+\]:\s*<?data:\S+", "", text, flags=re.M)   # inline images (base64)
            text = re.sub(r"\\([*\[\]_#])", r"\1", text)[:14000]
            parts = self.call([{"type": "text", "text": OUTLINE_PROMPT.format(doc=text)}], OUTLINE_SCHEMA, "Fighter · Chia phần bài giảng", 2000)["parts"]
            docs[doc] = {"text": text, "parts": parts[:12], "figure": figure}
        return docs[doc]

    def grade(self, sid, s):
        if s["prog"] in ("RC1", "RC2", "PT"):
            return self.grade_reading(sid, s)
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
        lean = LEAN_ALL
        side = LEAN_TABLE_SIDE if lean else SIDE
        content = [{"type": "text", "text": "Ảnh mẫu sổ 7 cột:"}, img_block(SAMPLE.read_bytes(), side),
                   {"type": "text", "text": f"Bài làm của học sinh ({len(imgs)} ảnh):"}]
        content += [img_block(b, side) for b in imgs]
        content.append({"type": "text", "text": PROMPT.format(code=s["code"], title=unit["title"], first=ents[0]["n"],
                                                              last=ents[-1]["n"], listing=listing, spot=", ".join(map(str, spot)))})
        def read():
            r = self.cl.messages.create(model=MODEL, max_tokens=12000, thinking={"type": "disabled"},
                                        tools=[{"name": "record", "description": "Ghi lại những gì đọc được", "input_schema": SCHEMA}],
                                        tool_choice={"type": "tool", "name": "record"},
                                        messages=[{"role": "user", "content": content}])
            u = r.usage.model_dump()
            c = cw.cost_usd(MODEL, u)
            if r.stop_reason == "max_tokens":
                raise RuntimeError("READ_TRUNCATED")
            cw.ledger({"at": cw.now_iso(), "category": f"{s['cls']} · Sổ từ vựng · {s['code']}", "step": "fighter-notebook",
                       "model": MODEL, "usage": u, "usd": c, "vnd": round(c * cw.USD_VND)})
            return json.loads(json.dumps(next(b.input for b in r.content if b.type == "tool_use"))), c
        if lean:   # one Sonnet read (Message Batch); the merge below then sees the same read twice
            a = self.call(content, SCHEMA, f"{s['cls']} · Sổ từ vựng · {s['code']}", model=LEAN_MODEL, batch=True)
            b, c = a, 0.0
        else:      # two independent Haiku reads, merged in the pupil's favour
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
        res = {"pages": a.get("pages", []), "entries": a.get("entries", []) + (b.get("entries", []) if b is not a else []),
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
        elif sc["written"] >= (8 if b is a else 16) and res.get("otherTerms", 0) >= 8 and sc["seen"] * 20 < sc["written"] * 3:
            out["kind"] = "wrong_unit"
        elif pg and all(p["readable"] == "no" for p in pg):
            out["kind"] = "unreadable"
        out["messy"] = bool(pg) and sum(p.get("neat") == "messy" for p in pg) * 3 >= len(pg) * 2
        mc = [m for m in res.get("meaningCheck", []) if m["match"] != "unclear"]
        out["meaningOff"] = sum(m["match"] == "no" for m in mc) >= 4
        secs = self.video_seconds(s["video"]) if s.get("video") else "none"
        need = max(20, round(1.2 * sc["total"]))
        out["video"] = ("none" if secs == "none" else "short" if isinstance(secs, int) and secs < need else "ok")
        out["videoSecs"], out["videoNeed"] = (secs if isinstance(secs, int) else None), need
        return out

    # ------------------------------------------------------------ feedback text
    def comment(self, s, res, count_incomplete):
        """(text, ok, pct). Same look as KIDS: a quality line the dashboard reads ("Chất lượng: đạt N%"), the reasons,
        then a firm request. Not ok → the cell's status line becomes "❌ CẦN NỘP LẠI", so the dashboard and the class
        web app count it as homework still owed until a good notebook comes in."""
        label, unit = unit_label(s["code"])
        what = KIND_NAME.get(s["prog"], "sổ từ vựng")
        book = "vở" if s["prog"] in KIND_NAME else "sổ"
        OWED = "⚠ Bài chưa đạt nên vẫn tính là CHƯA NỘP BÀI cho tới khi con nộp lại đạt yêu cầu."
        def refuse(why, ask):
            return (f"❌ Chất lượng: Chưa đạt (Yêu cầu nộp lại).\n• Lý do yêu cầu nộp lại: {why}\n{OWED}\n→ Yêu cầu: {ask}"), False, None

        def head(pct, ok):
            return (f"{'✅' if ok else '❌'} Chất lượng: đạt {pct}% — {'Đạt yêu cầu.' if ok else f'Chưa đạt (Yêu cầu nộp lại, cần từ {PASS}%).'}")

        def ending(ok, ask, pct=None):
            return [] if ok else [OWED, "→ Yêu cầu: " + ask]

        if res["kind"] == "no_photos":
            return refuse(f"cô không mở được ảnh/tệp {book} con gửi.", f"con chụp rõ, đủ các trang {book} và NỘP LẠI ngay.")
        if res["kind"] == "unreadable":
            return refuse(f"ảnh {book} quá mờ hoặc bị cắt, cô không đọc được.", "con chụp lại rõ nét, đủ sáng, đủ các trang và NỘP LẠI ngay.")
        if res["kind"] == "wrong_unit" and s.get("hadEarlier"):
            when = parse_vn_time(s["submittedAt"]).strftime("%d/%m %H:%M")
            return (f"ℹ️ Lần nộp {when} là vở của một bài khác, không phải {label} {unit}, nên cô không tính lần nộp này; "
                    f"bài {label} {unit} con nộp lần trước vẫn được ghi nhận.\n→ Nếu đây là bài của buổi khác, con nộp lại đúng mục bài đó nhé."), True, None
        if res["kind"] in ("printed", "reused", "wrong_unit"):
            prev = res.get("reusedFrom", {}).get("code")
            why = {"printed": f"{book} nộp là bản in/ảnh chụp màn hình, không phải chép tay — cô không chấp nhận.",
                   "reused": f"ảnh {book} trùng với bài đã nộp trước đó" + (f" ({' '.join(unit_label(prev))})" if prev else "")
                             + " — mỗi bài phải là ảnh chụp mới của chính bài đó.",
                   "wrong_unit": (f"các từ trong sổ không phải từ của {label} {unit}." if s["prog"] not in COPY
                                  else f"nội dung trong vở không phải bài giảng của {label} {unit}.")}[res["kind"]]
            return refuse(why, f"con chép tay đúng {label} {unit} vào {book} và NỘP LẠI trước buổi học tới.")
        messy = "• Chữ viết cẩu thả, bẩn, khó đọc — cô không chấp nhận cách trình bày này; con viết lại rõ ràng, sạch sẽ."
        if res.get("type") == "reading":
            v = res["vocab"]
            name = "Sổ luyện đề" if s["prog"] == "PT" else "Vở chữa bài"
            pct = min(v["pct"], res["work"])
            ok = v["pct"] >= PASS and res["work"] >= PASS and not res.get("messy")
            need = res.get("needWhy", res["total"])
            lines = [head(pct, ok),
                     f"• Sổ từ vựng (từ cô in đỏ): {v['pct']}% — có {v['total'] - len(v['missing'])}/{v['total']} từ.",
                     f"• {name}: {res['work']}% — làm lại {res['total'] - len(res['notAnswered'])}/{res['total']} câu, "
                     f"giải thích {need - len(res['notAnswered']) - len(res['notExplained'])}/{need} câu cần giải thích."]
            if v["missing"]:
                lines.append(f"• Thiếu {len(v['missing'])} từ: số {ranges(v['missing'])}.")
            for f, lab in FIELDS:
                if v["empty"][f]:
                    lines.append(f"• Bỏ trống cột {lab} ở {len(v['empty'][f])} từ: số {ranges(v['empty'][f])}.")
            if res["notAnswered"]:
                lines.append(f"• Chưa làm lại câu: {ranges(res['notAnswered'])}.")
            if res["notExplained"]:
                lines.append(f"• Chưa chép giải thích câu: {ranges(res['notExplained'])}.")
            if res["wrong"]:
                lines.append(f"• Đáp án làm lại vẫn sai ở câu: {ranges(res['wrong'])} — con đối chiếu lại phần chữa đề.")
            if res.get("messy"):
                lines.append(messy)
            lines += ending(ok, pct=pct, ask=f"con bổ sung đủ các mục trên vào sổ từ vựng và {name.lower()}, chụp lại toàn bộ và NỘP LẠI trước buổi học tới.")
            return "\n".join(lines), ok, pct
        if res.get("type") == "ap":
            pct = res["pct"]
            ok = pct >= PASS and not res.get("messy")
            lines = [head(pct, ok)]
            lines.append("• Revised version (đoạn văn con viết lại sau khi chữa): " + ("đã có." if res["revised"] else "CHƯA CÓ."))
            lines.append("• Outline: " + ("đã chép đủ." if res["outline"] >= 1 else
                                          f"chép thiếu — {res['outlineLack']}." if res["outline"] and res["outlineLack"] else
                                          "chép thiếu." if res["outline"] else "CHƯA CHÉP."))
            if res["modelFull"]:
                lines.append("• Bài mẫu: đã chép đủ.")
            elif res["modelGot"]:
                lines.append(f"• Bài mẫu: mới chép {res['modelGot']}/{res['modelTotal']} câu"
                             + (f" — còn thiếu từ câu \"{res['modelNext']}…\" đến hết." if res["modelNext"] else "."))
            else:
                lines.append("• Bài mẫu: CHƯA CHÉP.")
            lines.append(f"• Từ vựng và cụm từ: có {res['vocabHave']}/{res['vocabTotal']}"
                         + (" — thiếu: " + "; ".join(res["vocabLack"]) + "." if res["vocabLack"] else "."))
            if res.get("messy"):
                lines.append(messy)
            lines += ending(ok, pct=pct, ask="con bổ sung ĐỦ các mục còn thiếu ở trên vào vở, chụp lại toàn bộ và NỘP LẠI trước buổi học tới.")
            return "\n".join(lines), ok, pct
        if res.get("type") == "copy":
            pct = res["pct"]
            blurry = res.get("blurry") or []
            ok = pct >= PASS and not res.get("messy") and not blurry
            full = res["total"] - len(res["missing"]) - len(res["partly"]) - len(blurry)
            lines = [head(pct, ok), f"• {what.capitalize()}: {'đã' if full >= res['total'] else 'mới'} chép đủ {full}/{res['total']} phần của bài giảng."]
            if res["missing"]:
                lines.append("• Chưa chép phần: " + "; ".join(res["missing"]) + ".")
            if res["partly"]:
                lines.append("• Chép thiếu: " + "; ".join(res["partly"]) + ".")
            if blurry:
                lines.append("• Ảnh chụp mờ / bị cắt, cô chưa đọc được phần: " + "; ".join(blurry)
                             + " — con KHÔNG phải chép lại, chỉ cần chụp lại rõ nét các trang đó.")
            if res.get("messy"):
                lines.append(messy)
            lines += ending(ok, pct=pct, ask=("con chép bổ sung ĐỦ các phần trên theo bài giảng trên web, chụp lại toàn bộ và NỘP LẠI trước buổi học tới."
                                 if pct < PASS or res["missing"] or res["partly"] else
                                 "con chụp lại rõ nét, đủ sáng, thẳng trang (mỗi ảnh 1–2 trang) và NỘP LẠI ngay." if blurry
                                 else "con chép lại cẩn thận và NỘP LẠI trước buổi học tới."))
            return "\n".join(lines), ok, pct
        pct = res["pct"]
        ok = pct >= PASS and res["video"] != "none" and not res.get("messy")
        lines = [head(pct, ok), f"• Sổ từ vựng: có {res['total'] - len(res['missing'])}/{res['total']} từ"
                 + (", đủ 7 cột." if pct >= 100 else ".")]
        if res["missing"]:
            lines.append(f"• Thiếu {len(res['missing'])} từ: số {ranges(res['missing'])}.")
        for f, lab in FIELDS:
            if res["empty"][f]:
                lines.append(f"• Bỏ trống cột {lab} ở {len(res['empty'][f])} từ: số {ranges(res['empty'][f])}.")
        if res.get("messy"):
            lines.append(messy)
        if res.get("meaningOff"):
            lines.append("• Nhiều nghĩa tiếng Việt chép không khớp với từ — con đối chiếu lại với web học.")
        if res["video"] == "none":
            lines.append("• Chưa có video trả từ.")
        elif res["video"] == "short":
            lines.append(f"• Video trả từ quá ngắn ({res['videoSecs']} giây) so với {res['total']} từ — con quay lại đủ các từ.")
        else:
            lines.append("• Video trả từ: đã có.")
        lines += ending(ok, pct=pct, ask=("con bổ sung đủ các từ và các cột còn thiếu, chụp lại và NỘP LẠI trước buổi học tới." if pct < PASS
                             else "con viết lại sổ cẩn thận và NỘP LẠI trước buổi học tới." if res.get("messy")
                             else "con quay video trả từ và NỘP LẠI trước buổi học tới."))
        return "\n".join(lines), ok, pct

    # ------------------------------------------------------------ main step
    def write(self, s, a1, deadline, text, ok=True, pct=None):
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
        receipt = ("⚠️ ĐÃ NỘP MUỘN" if deadline and sub_t > deadline else "✅ ĐÃ NỘP") + "\n" + sub_t.strftime("%d/%m/%Y %H:%M")
        if prefix.strip().startswith("❌ CẦN NỘP LẠI"):   # our own line for an earlier notebook: back to a receipt
            prefix = receipt
        prev = s.get("published")
        existing = re.sub(r"\n*💬?\s*GHI CHÚ GV:\s*\n?" + re.escape(FLAG) + r"[^\n]*", "", existing).strip()
        if FLAG in prefix:   # the class sync shows our own note in the status block: drop it, it is set again below
            prefix = re.sub(r"\n*💬?\s*GHI CHÚ GV:\s*\n?" + re.escape(FLAG) + r"[^\n]*", "", prefix)
        if "GHI CHÚ GV" in prefix.upper() or (existing and existing != prev and not (prev and prev in existing)):
            return "teacher_comment"   # a note Cô/staff wrote is never overwritten
        body = existing.replace(prev, text) if prev and prev in existing else text
        new = prefix.rstrip() + "\n\n" + MARK + "\n" + body
        tr.write(a1, new)
        if tr.cell(a1) != new:
            return "readback_mismatch"
        self.set_flag(tr, a1, None)   # Cô 10/11: no cell notes — the comment itself says CẦN NỘP LẠI; clear our old ones
        self.paint(tr, a1, new, ok)
        return "ok"

    def restyle(self, s):
        try:
            txt, ok = s.get("published") or "", bool(s.get("ok"))
            m = re.search(r"đạt (\d+)%", txt)
            pct = int(m.group(1)) if m else None
            first, sep, rest = txt.partition("\n")
            if first.startswith("Chất lượng:"):
                first = ("✅ " if ok else "❌ ") + first
            elif first.startswith(("❌", "✅")):
                pass
            first = re.sub(r"CHƯA ĐẠT(?:, CẦN NỘP LẠI)? \(yêu cầu từ (\d+)%\)\.", r"Chưa đạt (Yêu cầu nộp lại, cần từ \1%).", first)
            rest = rest.replace("⛔ Bài chưa đạt", "⚠ Bài chưa đạt")
            rest = re.sub(r"mới chép đủ (\d+)/\1 phần", r"đã chép đủ \1/\1 phần", rest)
            new = first + sep + rest
            dl = dt.datetime.fromisoformat(s["deadline"]) if s.get("deadline") else None
            w = self.write(s, s["cell"], dl, new, ok, pct)
            if w == "ok":
                s.update(published=new, ver=VERSION, paintVer=PAINT_VERSION)
                self.tick("restyled")
            else:
                self.tick("restyle_" + w)
        except Exception as e:
            self.tick("restyle_error_" + type(e).__name__)

    def paint(self, tr, a1, text, ok):
        """Same colours as the class sync: status block green/orange, the marker blue; our verdict green when passed,
        red (cell background red too) when the notebook must be redone, so staff see it at a glance."""
        try:
            sid, row, col = self.cell_ref(tr, a1)
            u = lambda t: len(t.encode("utf-16-le")) // 2
            rgb = lambda h: {"red": int(h[1:3], 16) / 255, "green": int(h[3:5], 16) / 255, "blue": int(h[5:7], 16) / 255}
            fmt = lambda h, b=True, size=None: {"foregroundColor": rgb(h), "bold": b, **({"fontSize": size} if size else {})}
            at = text.find(MARK)
            head = text[:at]
            runs = [{"startIndex": 0, "format": fmt("#b45f06" if "MUỘN" in head.split("\n")[0] else "#274e13", True, 8)},
                    {"startIndex": u(text[:at]), "format": fmt("#1c4587", True, 10)}]
            pos = at + len(MARK)
            for line in text[pos:].split("\n"):   # KIDS colours: praise green, correction pink, attention red
                if line.strip():
                    strong = line.startswith(("❌", "✅", "⚠", "⛔", "→", "• ĐÂY LÀ"))
                    if line.startswith("✅"):
                        color = "#1B5E20"
                    elif strong:
                        color = "#B71C1C"
                    elif re.search(r"CHƯA|[Tt]hiếu|Bỏ trống|[Cc]hưa|sai|quá ngắn|cẩu thả|không khớp", line):
                        color = "#C2185B"
                    else:
                        color = "#1B5E20"
                    runs.append({"startIndex": u(text[:pos]), "format": fmt(color, strong, BODY_SIZE)})
                pos += len(line) + 1
            cell = {"textFormatRuns": runs}
            fields = "textFormatRuns"
            if not ok:
                cell["userEnteredFormat"] = {"backgroundColor": rgb("#f4cccc")}
                fields += ",userEnteredFormat.backgroundColor"
            reqs = [{"updateCells": {
                "range": {"sheetId": sid, "startRowIndex": row - 1, "endRowIndex": row, "startColumnIndex": col - 1, "endColumnIndex": col},
                "rows": [{"values": [cell]}], "fields": fields}}]
            h = self.row_height(tr, sid, row)
            if h:
                reqs.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "ROWS", "startIndex": row - 1, "endIndex": row},
                                                           "properties": {"pixelSize": h}, "fields": "pixelSize"}})
            self.g._req(f"https://sheets.googleapis.com/v4/spreadsheets/{tr.id}:batchUpdate", "POST", {"requests": reqs})
        except Exception as e:
            self.tick("paint_error_" + type(e).__name__)

    def row_height(self, tr, sid, row):
        """Height to set for this row (ROW_FACTOR x the row's own height, remembered the first time), or None if already tall enough."""
        try:
            import urllib.parse
            key = f"{tr.id}|{tr.tab}|{row}"
            base = self.st.setdefault("rowBase", {})
            rng = urllib.parse.quote(f"'{tr.tab}'!A{row}")
            meta = self.g._req(f"https://sheets.googleapis.com/v4/spreadsheets/{tr.id}?ranges={rng}&includeGridData=true"
                               "&fields=sheets.data.rowMetadata.pixelSize")
            cur = meta["sheets"][0]["data"][0]["rowMetadata"][0].get("pixelSize", 21)
            if key not in base:
                base[key] = cur
            want = base[key] * ROW_FACTOR
            return want if cur < want else None
        except Exception as e:
            self.tick("row_height_error_" + type(e).__name__)
            return None

    def cell_ref(self, tr, a1):
        m = re.match(r"([A-Z]+)(\d+)$", a1)
        col = 0
        for ch in m.group(1):
            col = col * 26 + ord(ch) - 64
        sid = self.st.setdefault("sheetIds", {}).get(f"{tr.id}|{tr.tab}")
        if sid is None:
            meta = self.g._req(f"https://sheets.googleapis.com/v4/spreadsheets/{tr.id}?fields=sheets.properties(sheetId,title)")
            sid = next(x["properties"]["sheetId"] for x in meta["sheets"] if x["properties"]["title"] == tr.tab)
            self.st["sheetIds"][f"{tr.id}|{tr.tab}"] = sid
        return sid, int(m.group(2)), col

    def set_flag(self, tr, a1, text):
        """Cell note, the staff's own way to mark homework to redo ("LỖI: …"): the class sync shows it in red in the cell,
        the dashboard files the homework under "Cần bổ sung" with "Cô nhắn". Only our own note is changed or cleared."""
        try:
            import urllib.parse
            m = re.match(r"([A-Z]+)(\d+)$", a1)
            col = 0
            for ch in m.group(1):
                col = col * 26 + ord(ch) - 64
            row = int(m.group(2))
            sid = self.st.setdefault("sheetIds", {}).get(f"{tr.id}|{tr.tab}")
            if sid is None:
                meta = self.g._req(f"https://sheets.googleapis.com/v4/spreadsheets/{tr.id}?fields=sheets.properties(sheetId,title)")
                sid = next(x["properties"]["sheetId"] for x in meta["sheets"] if x["properties"]["title"] == tr.tab)
                self.st["sheetIds"][f"{tr.id}|{tr.tab}"] = sid
            rng = urllib.parse.quote(f"'{tr.tab}'!{a1}", safe="")
            got = self.g._req(f"https://sheets.googleapis.com/v4/spreadsheets/{tr.id}?ranges={rng}&fields=sheets.data.rowData.values.note")
            cur = (((got.get("sheets") or [{}])[0].get("data") or [{}])[0].get("rowData") or [{}])[0].get("values", [{}])[0].get("note", "")
            if cur and not cur.startswith(FLAG):
                self.tick("flag_kept_staff_note")
                return
            want = text or ""
            if cur == want:
                return
            self.g._req(f"https://sheets.googleapis.com/v4/spreadsheets/{tr.id}:batchUpdate", "POST", {"requests": [{"updateCells": {
                "range": {"sheetId": sid, "startRowIndex": row - 1, "endRowIndex": row, "startColumnIndex": col - 1, "endColumnIndex": col},
                "rows": [{"values": [{"note": want}]}], "fields": "note"}}]})
            self.tick("flag_set" if want else "flag_cleared")
        except Exception as e:
            self.tick("flag_error_" + type(e).__name__)

    def unpublish(self, s):
        prev = s.pop("published", None)
        if not prev or not s.get("cell"):
            return
        tr = self.r.tracker(s["cls"])
        cur = tr.cell(s["cell"])
        if MARK in cur:
            prefix, body = cur.split(MARK, 1)
            if body.strip() == prev.strip():
                tr.write(s["cell"], prefix.rstrip())
                self.tick("unpublished_partial_read")

    def collect_batches(self):
        pend, res = self.st.setdefault("batchPending", {}), self.st.setdefault("batchRes", {})
        for bid, info in list(self.st.setdefault("batches", {}).items()):
            try:
                b = self.cl.messages.batches.retrieve(bid)
            except Exception as e:
                self.tick("batch_retrieve_error_" + type(e).__name__)
                continue
            if b.processing_status != "ended":
                if now() - dt.datetime.fromisoformat(info["at"]) < dt.timedelta(hours=26):
                    self.tick("batch_pending")
                    continue
            else:
                for item in self.cl.messages.batches.results(bid):
                    key = item.custom_id
                    cat = (pend.get(key) or {}).get("cat", "Fighter")
                    if item.result.type != "succeeded":
                        res[key] = {"_error": item.result.type}
                        self.tick("batch_item_" + item.result.type)
                        continue
                    m = item.result.message.model_dump()
                    c = cw.cost_usd(m["model"], m["usage"], batch=True)
                    cw.ledger({"at": cw.now_iso(), "category": cat, "step": "fighter-notebook-batch", "model": m["model"],
                               "usage": m["usage"], "usd": c, "vnd": round(c * cw.USD_VND)})
                    self.r.tick("fnb_cost_vnd", round(c * cw.USD_VND))
                    self.tick("batch_reads")
                    self.tick("batch_read_vnd", round(c * cw.USD_VND))
                    txt = "".join(x.get("text") or "" for x in m["content"] if x.get("type") == "text")
                    try:
                        res[key] = {"out": json.loads(txt)}
                    except ValueError:
                        res[key] = {"_error": "truncated" if m.get("stop_reason") == "max_tokens" else "bad_json"}
            for key in info["keys"]:
                pend.pop(key, None)
            del self.st["batches"][bid]

    def submit_batch(self):
        if not self.queue:
            return
        reqs = [{"custom_id": k, "params": v["params"]} for k, v in self.queue.items()]
        try:
            b = self.cl.messages.batches.create(requests=reqs)
        except Exception as e:
            self.tick("batch_submit_error_" + type(e).__name__)
            self.queue = {}
            return
        self.st.setdefault("batches", {})[b.id] = {"at": now().isoformat(), "keys": list(self.queue)}
        for k, v in self.queue.items():
            self.st.setdefault("batchPending", {})[k] = {"bid": b.id, "cat": v["cat"]}
        self.tick("batch_submitted", len(reqs))
        self.queue = {}

    def run(self):
        self.queue = {}
        self.collect_batches()
        self.scan()
        subs = self.st["subs"]
        for s in subs.values():   # "reused" against a later submission (the pupil sent it under another unit first): read again
            src = (s.get("result") or {}).get("reusedFrom") or {}
            o = subs.get(src.get("sid"), {})
            if s["status"] == "published" and (s.get("result") or {}).get("kind") == "reused" and o.get("submittedAt") \
                    and parse_vn_time(o["submittedAt"]) >= parse_vn_time(s["submittedAt"]):
                s.update(status="new", tries=0, regrade=True)
                self.tick("regrade_reuse_order")
        for s in subs.values():
            if s["status"] == "published" and s.get("ver", 1) < VERSION:
                m = re.search(r"đạt (\d+)%", s.get("published") or "")
                clean = s.get("ok") and m and int(m.group(1)) >= 100
                if s["prog"] in REGRADE and not (REGRADE_FAILED_ONLY and clean):
                    s.update(status="new", tries=0, regrade=True)
                    self.tick("regrade_new_rules")
                else:   # same result, today's wording/colours: no new reading
                    self.restyle(s)
            elif s["status"] == "published" and s.get("paintVer", 1) < PAINT_VERSION:
                try:
                    tr = self.r.tracker(s["cls"])
                    cur = tr.cell(s["cell"])
                    if MARK in cur and (s.get("published") or "") in cur:
                        self.paint(tr, s["cell"], cur, bool(s.get("ok")))
                        self.tick("repainted")
                    s["paintVer"] = PAINT_VERSION
                except Exception as e:
                    self.tick("repaint_error_" + type(e).__name__)
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
                if why.startswith("tracker_column"):   # counts only (no names): which class / lesson has no column
                    self.tick(f"{why}[{s['cls']}|{s['code']}]")
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
                except Pending:
                    self.tick("waiting_batch")
                except Exception as e:
                    if str(e) == "FILE_UNREADABLE":   # our access problem: take back any result shown, wait for access
                        self.unpublish(s)
                        s.update(status="new", hold="file_unreadable")
                        continue
                    s["tries"] = s.get("tries", 0) + 1
                    s["error"] = type(e).__name__
                    self.tick("error_" + type(e).__name__ + (f"_{str(e)[:40]}[{s['code']}]" if isinstance(e, RuntimeError) else ""))
                    if s["tries"] >= 6:   # our side failing (Drive access, API): never blame the pupil, keep it for a fix
                        s["status"] = "held_error"
        self.submit_batch()   # reads queued this cycle go out as one Message Batch
        for sid, s in subs.items():   # publish (graded earlier or just now)
            if s["status"] != "graded":
                continue
            res = s["result"]
            key = (s["cls"], bare(norm(s["student"])))
            earlier = sorted({x["code"] for x in subs.values() if (x["cls"], bare(norm(x["student"]))) == key
                              and x["status"] == "published" and not x.get("ok") and x["code"] != s["code"]
                              and family(x["prog"]) == family(s["prog"])})
            if res.get("kind") == "wrong_unit":   # sent under the wrong unit: an earlier submission of this unit is kept
                try:
                    first = self.r.tracker(s["cls"]).cell(s["cell"]).split("\n")[0]
                except Exception:
                    first = ""
                s["hadEarlier"] = first.startswith("🔁") or any(
                    x is not s and (x["cls"], bare(norm(x["student"])), x["code"]) == (s["cls"], bare(norm(s["student"])), s["code"])
                    and parse_vn_time(x["submittedAt"]) < parse_vn_time(s["submittedAt"]) for x in subs.values())
            text, ok, pct = self.comment(s, res, len(earlier))
            if not ok and len(earlier) >= 2:
                label = unit_label(s["code"])[0]
                units = ", ".join(unit_label(c)[1] for c in earlier + [s["code"]])
                book = KIND_NAME.get(s["prog"], "sổ từ vựng")
                rep = f"• ĐÂY LÀ LẦN THỨ {len(earlier) + 1} con nộp {book} chưa đạt ({label} {units}) — con cần nghiêm túc hơn."
                text += "\n" + rep
            dl = dt.datetime.fromisoformat(s["deadline"]) if s.get("deadline") else None
            w = self.write(s, s["cell"], dl, text, ok, pct)
            if w == "wait":
                self.tick("waiting_status_line")
                continue
            if w != "ok":
                s.update(status="skipped" if w == "teacher_comment" else "graded", hold=w)
                self.tick(w)
                continue
            s.update(status="published", published=text, ok=ok, publishedAt=now().isoformat(), ver=VERSION, paintVer=PAINT_VERSION)
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
