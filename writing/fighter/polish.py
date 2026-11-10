"""One-off: tighten Cô's correction explanations ("đủ và cần") in the Reading 1/2 correction docs.

Runs in GitHub Actions (polish_docs.yml), never on its own schedule.
  MODE=survey  → per doc: tabs and explanation tables, counts only (no content in the public log)
  MODE=apply   → rewrite every explanation cell in place (bold kept on the key word), originals saved
                 in the encrypted state for rollback; stray vocabulary notes moved to "Từ vựng thêm" at the end.
  MODE=restore → put the saved originals back.
DOCS env: comma-separated codes (RI2-C06,…) or "all".
"""
from __future__ import annotations

import json
import os
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import claude_worker as cw  # noqa: E402
import gapi  # noqa: E402

READING = json.loads((HERE / "reading.json").read_text(encoding="utf-8"))
STATE = Path(os.environ["FIGHTER_STATE"]).with_name("polish-docs.json")
MODEL = "claude-sonnet-5-5"
ALLOWED = {v["doc"] for v in READING.values()}


class Docs(gapi.Google):
    """Service account with edit rights on Cô's correction docs only."""

    def token(self):
        old = gapi.SCOPES
        gapi.SCOPES = "https://www.googleapis.com/auth/documents"
        try:
            return super().token()
        finally:
            gapi.SCOPES = old

    def call(self, doc, method="GET", data=None, suffix=""):
        if doc not in ALLOWED:
            raise ValueError("DOC_NOT_ALLOWED")
        import urllib.error
        import urllib.request
        url = f"https://docs.googleapis.com/v1/documents/{doc}{suffix}"
        body = None if data is None else json.dumps(data, ensure_ascii=False).encode()
        req = urllib.request.Request(url, data=body, method=method, headers={
            "Authorization": "Bearer " + self.token(), "Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=300) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"DOCS_HTTP_{e.code}") from None

    def get(self, doc):
        return self.call(doc, suffix="?includeTabsContent=true")


def tabs(d):
    out = []

    def walk(ts):
        for t in ts or []:
            out.append(t)
            walk(t.get("childTabs"))
    walk(d.get("tabs"))
    return out


def cell_text(cell):
    s = ""
    for p in cell.get("content", []):
        for e in p.get("paragraph", {}).get("elements", []):
            s += e.get("textRun", {}).get("content", "")
    return s


def cell_marked(cell):
    """Cell text with **bold** markers (what the model sees and returns)."""
    s = ""
    for p in cell.get("content", []):
        for e in p.get("paragraph", {}).get("elements", []):
            tr = e.get("textRun")
            if not tr:
                continue
            t = tr["content"]
            if tr.get("textStyle", {}).get("bold") and t.strip():
                lead, core, tail = re.match(r"(\s*)(.*?)(\s*)$", t, re.S).groups()
                s += f"{lead}**{core}**{tail}"
            else:
                s += t
    return re.sub(r"\*\*\s*\*\*", "", s).strip()


def expl_tables(d):
    """(tabId, cell) for every explanation cell: tables whose header row has 'Giải thích'."""
    found = []
    for t in tabs(d):
        tid = t["tabProperties"]["tabId"]
        for el in t.get("documentTab", {}).get("body", {}).get("content", []):
            tb = el.get("table")
            if not tb:
                continue
            rows = tb.get("tableRows", [])
            if not rows:
                continue
            head = [cell_text(c).strip().lower() for c in rows[0].get("tableCells", [])]
            col = next((i for i, h in enumerate(head) if "giải thích" in h), None)
            if col is None:
                continue
            for r in rows[1:]:
                cs = r.get("tableCells", [])
                if col < len(cs) and cell_text(cs[col]).strip():
                    ans = cell_text(cs[col - 1]).strip() if col else ""
                    found.append({"tab": tid, "tabTitle": t["tabProperties"].get("title", ""), "cell": cs[col], "answer": ans})
    return found


PROMPT = """Bạn là trợ lí của Cô Trang, giáo viên tiếng Anh. Học sinh phải CHÉP TAY phần giải thích dưới đây vào vở chữa bài, mà các con còn học nhiều môn,
nên Cô muốn giải thích "đủ và cần": giữ đúng ý, đúng bằng chứng, bỏ chữ thừa.

Quy tắc viết lại từng ô:
1. Nghĩa từ (dạng "**Word (loại từ):** nghĩa dài") → "**Word (loại từ):** nghĩa ngắn" (nghĩa ≤ 8 chữ, giữ nghĩa chính).
2. Câu đọc hiểu: BỎ phần nhắc lại câu hỏi và các nhãn "Trích dẫn:", "Giải thích:". Viết một dòng:
   "trích dẫn tiếng Anh ngắn (giữ nguyên chữ, rút bằng …)" → lí do ngắn bằng tiếng Việt. Hoặc dạng "X = Y" cho câu từ đồng nghĩa / đại từ.
   Tối đa khoảng 20 chữ. Trích dẫn phải là chữ có trong bản gốc, không bịa.
3. Câu ngữ pháp / điền từ: nêu đúng quy tắc quyết định đáp án, ≤ 15 chữ.
4. Ô đã ngắn (≤ 12 chữ) và rõ: giữ nguyên.
5. Ghi chú từ vựng lạc chỗ, không liên quan trực tiếp tới câu đó: chuyển nguyên văn sang trường "extra", không đưa vào "text".
6. Dùng **…** để in đậm từ khoá như bản gốc (từ vựng chính, đáp án). Không thêm emoji, không xuống dòng.
7. Không đổi đáp án, không thêm kiến thức mới.

Ví dụ Cô đã duyệt:
- "**Stun (v):** Làm choáng váng, kinh ngạc đến mức không kịp phản ứng." → "**Stun (v):** làm choáng váng"
- "**Khía cạnh nào của cuộc sống gia đình… được thảo luận chính?** • **Trích dẫn:** Nội dung thảo luận về lò sưởi, lug poles, lò nướng và nồi sắt. • **Giải thích:** Chủ đề xuyên suốt là các phương thức nấu ăn quanh lò sưởi…"
  → "Bài tả lò sưởi, lug pole, lò nướng, nồi → chủ đề: nấu ăn quanh lò sưởi"
- "**Từ \\"it\\" ám chỉ cái gì?** • **Trích dẫn:** \\"A heavy timber called the **mantel tree**… **it** was far enough…\\" • **Giải thích:** Đại từ \\"it\\" thay thế cho…" → "**it** = **the mantel tree** (danh từ ngay trước)"
- "**Từ \\"obtain\\" gần nghĩa nhất với từ nào?** • **Giải thích:** **Obtain (v)**: đạt được, thu được = **acquire**." → "**obtain** = **acquire**"

Các ô cần viết lại (JSON, mỗi ô có id, đáp án, nội dung gốc):
{items}

Trả về bằng công cụ record: mỗi ô một mục {{"id", "text", "extra"}} (extra = "" nếu không có)."""

SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {
    "type": "object", "properties": {"id": {"type": "integer"}, "text": {"type": "string"}, "extra": {"type": "string"}},
    "required": ["id", "text", "extra"]}}}, "required": ["items"]}


def rewrite(cl, items):
    out = {}
    for k in range(0, len(items), 40):
        chunk = items[k:k + 40]
        r = cl.messages.create(model=MODEL, max_tokens=16000,
                               tools=[{"name": "record", "description": "Ghi kết quả", "input_schema": SCHEMA}],
                               tool_choice={"type": "tool", "name": "record"},
                               messages=[{"role": "user", "content": PROMPT.format(items=json.dumps(chunk, ensure_ascii=False))}])
        if r.stop_reason == "max_tokens":
            raise RuntimeError("REWRITE_TRUNCATED")
        u = r.usage.model_dump()
        c = cw.cost_usd(MODEL, u)
        cw.ledger({"at": cw.now_iso(), "category": "Fighter · Chuốt giải thích", "step": "polish-docs", "model": MODEL,
                   "usage": u, "usd": c, "vnd": round(c * cw.USD_VND)})
        print(f"  model call: {len(chunk)} cells, ~{round(c * cw.USD_VND)}đ")
        for it in next(b.input for b in r.content if b.type == "tool_use")["items"]:
            out[int(it["id"])] = it
    missing = {i["id"] for i in items} - set(out)
    if missing:
        raise RuntimeError(f"REWRITE_MISSING_{len(missing)}")
    return out


def plain(marked):
    """'a **b** c' → ('a b c', [(start, end) bold ranges in UTF-16 units])."""
    text, bold, pos = "", [], 0
    for i, part in enumerate(re.split(r"\*\*", marked)):
        n = len(part.encode("utf-16-le")) // 2
        if i % 2 and part:
            bold.append((pos, pos + n))
        text += part
        pos += n
    return text, bold


def cell_range(cell):
    ps = cell["content"]
    return ps[0]["startIndex"], ps[-1]["endIndex"] - 1   # keep the cell's final newline


def edit_requests(cells, new, extras_at):
    """Requests from the highest index down, so earlier positions stay valid."""
    reqs = []
    jobs = sorted(((c["tab"], *cell_range(c["cell"]), i) for i, c in enumerate(cells)), key=lambda x: -x[1])
    if extras_at:
        tab, idx, lines = extras_at
        text = "\nTừ vựng thêm\n" + "\n".join(lines)
        reqs += [{"insertText": {"location": {"index": idx, "tabId": tab}, "text": text}},
                 {"updateTextStyle": {"range": {"startIndex": idx, "endIndex": idx + len(text.encode("utf-16-le")) // 2, "tabId": tab},
                                      "textStyle": {"bold": False}, "fields": "bold"}},
                 {"updateTextStyle": {"range": {"startIndex": idx + 1, "endIndex": idx + 1 + len("Từ vựng thêm"), "tabId": tab},
                                      "textStyle": {"bold": True}, "fields": "bold"}}]
    for tab, a, b, i in jobs:
        text, bold = plain(new[i])
        if b > a:
            reqs.append({"deleteContentRange": {"range": {"startIndex": a, "endIndex": b, "tabId": tab}}})
        if not text:
            continue
        n = len(text.encode("utf-16-le")) // 2
        reqs.append({"insertText": {"location": {"index": a, "tabId": tab}, "text": text}})
        reqs.append({"updateTextStyle": {"range": {"startIndex": a, "endIndex": a + n, "tabId": tab},
                                         "textStyle": {"bold": False}, "fields": "bold"}})
        for s, e in bold:
            reqs.append({"updateTextStyle": {"range": {"startIndex": a + s, "endIndex": a + e, "tabId": tab},
                                             "textStyle": {"bold": True}, "fields": "bold"}})
    return reqs


def words(s):
    return len(re.sub(r"\*\*", "", s).split())


def main():
    g = Docs(json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]))
    mode = os.environ.get("POLISH_MODE", "survey")
    sel = os.environ.get("DOCS", "all")
    codes = list(READING) if sel == "all" else [c.strip() for c in sel.split(",") if c.strip()]
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    cl = cw.client() if mode == "apply" else None
    bad = 0
    for code in codes:
        doc = READING[code]["doc"]
        try:
            d = g.get(doc)
        except Exception as e:
            print(f"{code}: {e}")
            bad += 1
            continue
        cells = expl_tables(d)
        tl = [t["tabProperties"].get("title", "") for t in tabs(d)]
        w = [words(cell_marked(c["cell"])) for c in cells]
        print(f"{code}: tabs={len(tl)} {tl} · explanation cells={len(cells)} · words median={statistics.median(w) if w else 0} max={max(w) if w else 0}")
        if mode == "survey" or not cells:
            continue
        if mode == "restore":
            old = st.get(code)
            if not old:
                print("  nothing saved")
                continue
            if len(old["cells"]) != len(cells):
                print("  cell count changed since polish: restore by hand from version history")
                bad += 1
                continue
            reqs = edit_requests(cells, old["cells"], None)
            g.call(doc, "POST", {"requests": reqs, "writeControl": {"requiredRevisionId": d["revisionId"]}}, ":batchUpdate")
            print("  restored")
            continue
        if code in st:
            print("  already polished (restore first to redo)")
            continue
        items = [{"id": i, "answer": c["answer"], "text": cell_marked(c["cell"])} for i, c in enumerate(cells)]
        res = rewrite(cl, items)
        new = [res[i]["text"].strip() or items[i]["text"] for i in range(len(items))]
        extra = [res[i]["extra"].strip() for i in range(len(items)) if res[i]["extra"].strip()]
        nw = [words(t) for t in new]
        print(f"  → words median={statistics.median(nw)} max={max(nw)} · extra notes moved={len(extra)}")
        extras_at = None
        if extra:
            t0 = next(t for t in tabs(d) if t["tabProperties"]["tabId"] == cells[-1]["tab"])
            end = t0["documentTab"]["body"]["content"][-1]["endIndex"] - 1
            extras_at = (cells[-1]["tab"], end, [re.sub(r"\*\*", "", x) for x in extra])
        reqs = edit_requests(cells, new, extras_at)
        st[code] = {"doc": doc, "cells": [it["text"] for it in items], "new": new, "extra": extra}
        g.call(doc, "POST", {"requests": reqs, "writeControl": {"requiredRevisionId": d["revisionId"]}}, ":batchUpdate")
        STATE.write_text(json.dumps(st, ensure_ascii=False))
        print("  written")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
