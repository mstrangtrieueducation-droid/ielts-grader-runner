"""Paper tests / in-class writing scanned into the Drive scan folder → split by student → graded in a batch.

File names: "<IELTS|FIGHTER> <n>_<DD-MM-YYYY>_Viết [task 1|2] kiểm tra lần <N>" (one PDF per class and paper).
Results are kept (encrypted with the runner state) for the teacher's review; nothing is written to trackers here.
Grading uses the lean packs approved 09/11/2026: Sonnet without the reasoning pass, only the fields students see.
"""
import base64, io, json, re, unicodedata
from pathlib import Path

import claude_worker as cw
from run_writing import BUNDLE, STATE_DIR, WORK, col_letter, h, load_json, norm, now, save_json

SCANS = STATE_DIR / "scans.json"
MODEL = "claude-sonnet-5-5"
NAME_RE = re.compile(r"^\s*(IELTS|FIGHTER)\s*0*(\d+)\s*_\s*(\d{1,2})\s*-\s*(\d{1,2})\s*-\s*(\d{4})\s*_\s*(.*?)(?:\.pdf)?\s*$", re.I)
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[’'\-][A-Za-z0-9]+)*%?")
BANNED_FIGHTER = re.compile(r"\b(so|because|like|you|your|but|and so on)\b|\.\.\.|\b\w+n't\b|\b(it's|that's|there's)\b", re.I)
BANNED_IELTS = re.compile(r"\b\w+n't\b|\b(it's|that's|there's|I'm|they're)\b|&", re.I)

S, B, N = {"type": "string"}, {"type": "boolean"}, {"type": "number"}


def obj(props, req=None):
    return {"type": "object", "properties": props, "required": req or list(props), "additionalProperties": False}


ARR = lambda it: {"type": "array", "items": it}

SEGMENT_SCHEMA = obj({"pages": ARR(obj({"page": {"type": "integer"}, "header": B, "nameRead": S,
                                         "rosterName": S, "sure": B}))})
FIGHTER_SCHEMA = obj({
    "transcript": S, "transcriptionNote": S, "taskSeen": S,
    "errors": ARR(obj({"quote": S, "group": {"type": "string", "enum": ["vocab", "grammar", "coherence"]}, "code": S,
                       "severity": {"type": "string", "enum": ["S1", "S2", "S3"]}, "replacement": S, "explanation": S})),
    "overall": S, "revision": S,
    "score": {"anyOf": [{"type": "null"}, obj({"tieuChi": ARR(obj({"ten": S, "diem": N, "bangChung": S})), "tong": N})]},
    "doubts": ARR(S)})
IELTS_TASK = obj({
    "task": {"type": "integer"}, "transcript": S, "transcriptionNote": S, "taskSeen": S,
    "criteria": obj({k: obj({"band": {"type": "integer"}, "reason": S, "whyNotHigher": S}) for k in ("TA_TR", "CC", "LR", "GRA")}),
    "annotations": ARR(obj({"group": {"type": "string", "enum": ["vocab", "grammar", "coherence"]},
                            "kind": {"type": "string", "enum": ["error", "practice", "suggestion"]},
                            "label": S, "quote": S, "replacement": S, "explanation": S})),
    "overall": S, "revisedText": S})
IELTS_SCHEMA = obj({"tasks": ARR(IELTS_TASK), "doubts": ARR(S)})


def words(t):
    return len(WORD_RE.findall(re.sub(r"\[không rõ:[^\]]*\]", " x ", t or "")))


def _bracket(m):
    """Transcriber's notes in a handwritten paper: crossed-out words and notes don't count, inserted words do,
    an unreadable word counts as one."""
    inner = m.group(1)
    low = inner.lower()
    if "không rõ" in low:
        return " x "
    tag = r"chèn|thêm|insert|added"
    if re.search(tag, low):
        if ":" in inner:
            a, _, b = inner.partition(":")
            return " " + (b if re.search(tag, a.lower()) else a) + " "
        return " " + re.sub(rf"\(?[^()]*\b(?:{tag})\b[^()]*\)?\s*$", " ", inner) + " "   # 'words (chèn trên dòng)'
    return " "


NO_COUNT = (" Không chép tên học sinh vào `transcript`. Chữ em gạch bỏ ghi [gạch bỏ: …], chữ em chèn thêm ghi [chèn: …]. "
            "Không tự đếm hay ước lượng số từ, không khẳng định bài thiếu hay đủ số từ trong nhận xét và tiêu chí: máy đếm "
            "chính xác rồi tự ghi số từ và phần trừ điểm vào kết quả.")


def paper_words(t):
    """Cô 12/11: word count of a handwritten paper = what the pupil left as the essay. Not the [gạch bỏ …] parts,
    not the transcriber's notes, not the name or heading line at the top."""
    t = re.sub(r"\[([^\]]*)\]", _bracket, t or "")
    lines = [ln for ln in t.splitlines() if ln.strip()]
    if len(lines) > 1:
        first = lines[0].strip().rstrip(".")
        toks = first.split()
        if len(toks) <= 5 and not re.search(r"\d", first) and all(w[:1].isupper() for w in toks):
            lines = lines[1:]   # 'Pham Viet Anh.', 'Khải Huyền', 'Task 1' …
    return len(WORD_RE.findall("\n".join(lines)))


def parse_name(title):
    m = NAME_RE.match(unicodedata.normalize("NFC", title))
    if not m:
        return None
    prog, n, d, mo, y, rest = m.groups()
    t = rest.lower()
    lan = re.search(r"lần\s*(\d+)", t)
    task = re.search(r"task\s*([12])", t)
    kind = "test" if lan else ("inclass" if "trên lớp" in t or "buổi" in t else None)
    out = {"cls": f"{prog.upper()} {int(n)}", "date": f"{int(d):02d}/{int(mo):02d}/{y}", "kind": kind,
           "n": int(lan.group(1)) if lan else None, "task": int(task.group(1)) if task else None}
    if kind == "inclass":   # Cô 11/11: in-class writing graded automatically too
        b = re.search(r"buổi\s*0*(\d+)", t)
        w = re.search(r"(?:bài|tuần|\bw)\s*0*(\d+)", t)
        out["buoi"] = int(b.group(1)) if b else None
        out["week"] = int(w.group(1)) if w else None
        if out["cls"].startswith("IELTS") and out["week"] is None:   # IELTS 'Buổi N' = lesson N = week WN
            out["week"], out["buoi"] = out["buoi"], None
    return out


def label(meta):
    """Human name of the paper: 'Kiểm tra lần 2', 'Viết trên lớp Buổi 5', 'Viết trên lớp bài 28'."""
    if meta.get("kind") == "inclass":
        return f"Viết trên lớp Buổi {meta.get('buoi') or meta.get('week')}"
    return f"Kiểm tra lần {meta.get('n')}"


def pack_for(meta):
    """Which approved pack grades this paper (None = not prepared yet → reported, not graded)."""
    if meta["kind"] == "inclass":
        if meta["cls"].startswith("FIGHTER"):
            b = meta.get("buoi")
            if not b:
                return None
            # rulebook v4 §1: Buổi 2–15 guided, no score; from Buổi 16 the /1 scale
            return {"pack": "TEST-FIGHTER", "item": f"B{b:02d}", "mode": "khong-diem" if b <= 15 else "1-diem",
                    "schema": "fighter", "inclass": True}
        w = meta.get("week")
        if not w or not (BUNDLE / "packs" / f"ESSAY-W{w:02d}" / "head.md").exists():
            return None
        task = json.loads((BUNDLE / "packs" / f"ESSAY-W{w:02d}" / "meta.json").read_text(encoding="utf-8")).get("task") or 2
        return {"pack": f"ESSAY-W{w:02d}", "item": None, "mode": "ielts", "schema": "ielts", "tasks": [task], "inclass": True}
    if meta["kind"] != "test":
        return None
    if meta["cls"].startswith("FIGHTER"):
        return {"pack": "TEST-FIGHTER", "item": f"KT{meta['n']:02d}", "mode": "1-diem", "schema": "fighter"}
    if meta["n"] == 1 and meta["task"] in (None, 1):
        return {"pack": "TEST-IELTS-L1", "item": None, "mode": "ielts", "schema": "ielts", "tasks": [1]}
    if meta["n"] in (3, 4):   # full tests: one PDF with both tasks, or one PDF per task
        return {"pack": f"TEST-IELTS-L{meta['n']}", "item": None, "mode": "ielts", "schema": "ielts",
                "tasks": [meta["task"]] if meta["task"] else [1, 2]}
    return None   # lần 2 (Mix + Map) waits for its pack


def jpeg(page, side, clip=None):
    from PIL import Image
    pix = page.get_pixmap(dpi=200, clip=clip)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    im.thumbnail((side, side))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85)
    return base64.b64encode(out.getvalue()).decode()


def img(b64):
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}}


def text_of(resp):
    return "".join(b.get("text", "") for b in resp["content"] if b.get("type") == "text")


class Scans:
    def __init__(self, runner):
        self.r, self.g = runner, runner.g
        self.st = load_json(SCANS, {"files": {}, "batches": {}})
        self.cl = cw.client()

    def save(self):
        save_json(SCANS, self.st)

    def tick(self, k, n=1):
        self.r.tick("scan_" + k, n)

    # ------------------------------------------------------------ discovery
    def discover(self):
        folder = self.r.cfg.get("scanFolder")
        if not folder:
            return
        for f in self.g.list_folder(folder):
            if f.get("mimeType") != "application/pdf":
                continue
            old = self.st["files"].get(f["id"])
            if old and old.get("modified") == f.get("modifiedTime"):
                if old["status"] == "no_pack" and old.get("meta") and pack_for(old["meta"]):
                    old["status"] = "new"   # its pack has been added since
                    self.tick("new")
                continue
            meta = parse_name(f["name"])
            cut = self.r.cfg.get("scanBaselineBefore")
            if not old and cut and (f.get("modifiedTime") or "") < cut:   # uploaded before go-live: already handled
                self.st["files"][f["id"]] = {"title": f["name"], "modified": f.get("modifiedTime"), "meta": meta,
                                             "students": {}, "status": "baseline", "at": now().isoformat()}
                continue
            rec = {"title": f["name"], "modified": f.get("modifiedTime"), "meta": meta, "students": {},
                   "status": "new", "at": now().isoformat()}
            if not meta or meta["cls"] not in self.r.cfg["classes"]:
                rec["status"] = "unrecognised_name"
            elif not pack_for(meta):
                rec["status"] = "no_pack"
            elif old and old.get("baseline"):
                rec["baseline"] = True
            self.st["files"][f["id"]] = rec
            self.tick(rec["status"])

    # ------------------------------------------------------------ one PDF → students → batch requests
    def segment(self, doc, roster):
        """Read the name box on every page once (cheap crops); pages without a header continue the previous paper."""
        content, pages = [], []
        for i, page in enumerate(doc, 1):
            r = page.rect
            clip = type(r)(r.x0, r.y0, r.x1, r.y0 + r.height * 0.33)
            content += [{"type": "text", "text": f"Trang {i}:"}, img(jpeg(page, 900, clip))]
        content.append({"type": "text", "text":
            "Mỗi ảnh là phần đầu một trang bài viết tay. Với từng trang: header = có ô tên học sinh/Candidate Name đã ghi "
            "(trang đầu một bài); nameRead = tên đọc được (rỗng nếu không có); rosterName = tên khớp DUY NHẤT trong danh sách "
            "lớp dưới đây (chép đúng như danh sách), rỗng nếu không chắc; sure = true chỉ khi chắc chắn.\n"
            "Danh sách lớp:\n" + "\n".join(roster)})
        resp = cw.call_api(self.cl, {"model": MODEL, "max_tokens": 16000, "thinking": {"type": "between_tools"},
                                     "output_config": {"format": {"type": "json_schema", "schema": SEGMENT_SCHEMA}},
                                     "messages": [{"role": "user", "content": content}]})
        resp = resp if isinstance(resp, dict) else resp.model_dump()
        c = cw.cost_usd(MODEL, resp["usage"])
        cw.ledger({"at": cw.now_iso(), "category": "Tách bài scan", "step": "segment", "model": MODEL,
                   "usage": resp["usage"], "usd": c, "vnd": round(c * cw.USD_VND)})
        return json.loads(text_of(resp))["pages"]

    def roster_aliases(self, cls):
        """{roster name: [English/short names]} from column C of the tracker (e.g. 'PHẠM THÁI HÀ' → ['Sophia'])."""
        tr = self.r.tracker(cls)
        out = {}
        for row in self.g.values(tr.id, f"'{tr.tab}'!B1:C200"):
            if row and row[0].strip():
                nm = norm(row[0].strip().split("\n")[0])
                al = [x.strip() for x in re.split(r"[\n/,]", row[1]) if x.strip()] if len(row) > 1 else []
                out[nm] = al
        return out

    @staticmethod
    def resolve(read, aliases):
        """A name read on the paper → the ONE roster name it can only mean, else None. Tries: full name, English name
        (column C, also inside brackets), then every written word found in exactly one roster name."""
        if not read:
            return None
        bare = lambda x: "".join(c for c in unicodedata.normalize("NFD", x) if not unicodedata.combining(c)).replace("Đ", "D").replace("đ", "d").upper()
        words = lambda x: re.findall(r"[A-Z0-9]+", bare(x))
        names = list(aliases)
        full = [n for n in names if words(n) == words(read)]
        if len(full) == 1:
            return full[0]
        tokens = set(words(read))
        eng = [n for n in names if any(set(words(a)) and set(words(a)) <= tokens for a in aliases[n])]
        if len(eng) == 1:
            return eng[0]
        w = words(read)   # Vietnamese order: the given name is the LAST word → a short name matches the end of the full name
        tail = [n for n in names if w and words(n)[-len(w):] == w]
        if len(tail) == 1:
            return tail[0]
        part = [n for n in names if tokens and tokens <= set(words(n)) and words(n)[-1] in tokens]
        return part[0] if len(part) == 1 else None

    def build(self, fid, rec, pdf_bytes, only=None):
        import pymupdf as fitz
        meta, spec = rec["meta"], pack_for(rec["meta"])
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        tr = self.r.tracker(meta["cls"])
        roster_rows = tr.rows()
        roster = [n for n in roster_rows if n and not n.startswith(("HỌ TÊN", "HỌ VÀ TÊN", "STT"))]
        aliases = {n: a for n, a in self.roster_aliases(meta["cls"]).items() if n in roster_rows}
        if only is not None:   # rescue pass: papers already split, names now resolvable
            groups = only
        else:
            listing = [n + (f" ({', '.join(aliases[n])})" if aliases.get(n) else "") for n in roster]
            pages = self.segment(doc, listing)
            groups, cur = [], None
            for p in sorted(pages, key=lambda x: x["page"]):
                if p["header"] or cur is None:
                    pick = norm(re.sub(r"\s*\(.*$", "", p["rosterName"] or ""))
                    cur = {"pages": [p["page"]], "nameRead": p["nameRead"],
                           "name": pick if p["sure"] and pick in roster_rows else self.resolve(p["nameRead"], aliases)}
                    groups.append(cur)
                else:
                    cur["pages"].append(p["page"])
        head = (BUNDLE / "packs" / spec["pack"] / "head.md").read_text(encoding="utf-8")
        system = [{"type": "text", "text": head, "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
        task_text = self.task_text(spec)
        reqs, seen = [], {x["name"] for x in rec["students"].values() if x.get("name")} if only is not None else set()
        for g in groups:
            if not g["name"] or g["name"] in seen:   # unreadable / duplicate / not on the list → not graded
                if only is not None:
                    continue
                key = f"?{g['pages'][0]}"
                rec["students"][key] = {"name": None, "nameRead": g["nameRead"], "pages": g["pages"], "status": "unidentified"}
                self.tick("unidentified")
                continue
            seen.add(g["name"])
            key = h(g["name"], 10)
            content = self.reference_blocks(spec) + [img(jpeg(doc[i - 1], 1568)) for i in g["pages"]]
            content.append({"type": "text", "text":
                f"Lớp {meta['cls']} · học sinh {g['name']} (đã đối chiếu danh sách lớp) · {label(meta)} · ngày {meta['date']} · "
                f"{len(g['pages'])} trang ảnh theo thứ tự trên.\n{task_text}\nChép bài, chấm và chữa theo hướng dẫn."})
            schema = FIGHTER_SCHEMA if spec["schema"] == "fighter" else IELTS_SCHEMA
            cid = h(fid + key + rec["modified"], 40)
            reqs.append({"custom_id": cid, "params": {
                "model": MODEL, "max_tokens": 12000, "thinking": {"type": "between_tools"}, "system": system,
                "output_config": {"format": {"type": "json_schema", "schema": schema}},
                "messages": [{"role": "user", "content": content}]}})
            rec["students"].pop(f"?{g['pages'][0]}", None)
            rec["students"][key] = {"name": g["name"], "nameRead": g["nameRead"], "pages": g["pages"],
                                    "status": "submitted", "cid": cid}
        return reqs

    def rescue(self):
        """Papers left unidentified (English or short name on the paper): match them again with column C names.
        Cô can also name a page herself (cfg scanNames: {file id: {page: "FULL NAME"}})."""
        reqs, mapping = [], {}
        for fid, fix in (self.r.cfg.get("scanNames") or {}).items():
            rec = self.st["files"].get(fid)
            if not rec or rec["status"] not in ("graded", "submitted"):
                continue
            groups = []
            for x in rec["students"].values():
                name = fix.get(str((x.get("pages") or [None])[0]))
                if x["status"] == "unidentified" and name:
                    groups.append({"pages": x["pages"], "nameRead": x.get("nameRead"), "name": norm(name)})
                    x["status"] = "renamed"
            if not groups:
                continue
            try:
                rq = self.build(fid, rec, self.g.download(fid), only=groups)
            except Exception:
                self.tick("rename_error")
                continue
            for q in rq:
                mapping[q["custom_id"]] = fid
            reqs += rq
            if rq:
                rec["status"] = "submitted"
                self.tick("renamed", len(rq))
        for fid, rec in self.st["files"].items():
            if rec.get("rescued") == 2 or rec["status"] not in ("graded", "submitted") or not rec.get("meta"):
                continue
            unk = [x for x in rec["students"].values() if x["status"] == "unidentified"]
            rec["rescued"] = 2
            if not unk:
                continue
            aliases = self.roster_aliases(rec["meta"]["cls"])
            groups = [{"pages": x["pages"], "nameRead": x.get("nameRead"), "name": self.resolve(x.get("nameRead"), aliases)}
                      for x in unk]
            groups = [g for g in groups if g["name"]]
            if not groups:
                continue
            try:
                rq = self.build(fid, rec, self.g.download(fid), only=groups)
            except Exception:
                self.tick("rescue_error")
                continue
            for q in rq:
                mapping[q["custom_id"]] = fid
            reqs += rq
            if rq:
                rec["status"] = "submitted"
                self.tick("rescued", len(rq))
        if reqs:
            b = self.cl.messages.batches.create(requests=reqs)
            self.st["batches"][b.id] = {"at": now().isoformat(), "map": mapping}

    def task_text(self, spec, meta=None):
        if spec.get("inclass") and spec["schema"] == "fighter":
            b = int(spec["item"][1:])
            length = {12: "Buổi 12: tối thiểu 140 từ, không giới hạn trên.", 13: "Buổi 13: không giới hạn độ dài."}.get(
                b, "Độ dài: 140–160 từ; 161–170 chấp nhận; dưới 140 cần phát triển; trên 170 cần rút gọn.")
            mode = ("Chế độ: KHÔNG ĐIỂM (mục 1: viết trên lớp có hướng dẫn) — `score` = null; chỉ chữa lỗi, nhận xét, bản sửa."
                    if spec["mode"] == "khong-diem" else "Chế độ: 1-điểm (mục 13) — từ Buổi 16.")
            src = f"Nguồn đúng buổi: mục 'NGUỒN BUỔI {b}' trong tài liệu." if b <= 15 else "Buổi này chưa có nguồn riêng: không bắt em phải có ý của bài mẫu."
            return (f"Bài viết đoạn văn TRÊN LỚP — Buổi {b}. {mode}\n{src} Đề: đọc trên ảnh bài làm; nếu ảnh không có đề, "
                    f"dùng đề của buổi trong nguồn.\n{length}")
        if spec.get("inclass"):
            return (f"Bài viết TRÊN LỚP (viết tay), cùng chủ đề {spec['pack'].replace('ESSAY-', 'bài ')} trong tài liệu. "
                    "Chấm như bài viết của tuần đó nhưng là bài viết tay trên lớp, không chấm phần vở. "
                    f"Chấm Task {spec['tasks'][0]} (một mục trong `tasks`). Nếu đề trên giấy khác đề trong tài liệu, chấm theo đề "
                    "trên giấy và ghi rõ ở `doubts`. Task 1 tối thiểu 150 từ, Task 2 tối thiểu 250 từ."
                    + NO_COUNT)
        if spec["pack"] == "TEST-FIGHTER":
            kt = json.loads((BUNDLE / "packs/TEST-FIGHTER/kt.json").read_text(encoding="utf-8"))[spec["item"]]
            return (f"Bài kiểm tra tự viết {spec['item']} — chủ đề {kt['topic']}. Chế độ: 1-điểm (mục 13).\n"
                    f"Đề: {kt['prompt']}\nĐộ dài: 140–160 từ; 161–170 chấp nhận; dưới 140 cần phát triển; trên 170 cần rút gọn.\n"
                    "Outline/bài mẫu riêng của đề này chưa có trong nguồn: không bắt em phải có ý của bài mẫu.")
        n = spec["pack"][-1]
        which = " và ".join(f"Task {t}" for t in spec["tasks"])
        return (f"Kiểm tra Writing lần {n}. Chấm {which} có trong ảnh bài làm (mỗi Task một mục trong `tasks`). "
                "Ảnh đầu tiên là đề và biểu đồ Task 1. Task 1 tối thiểu 150 từ, Task 2 tối thiểu 250 từ." + NO_COUNT)

    def reference_blocks(self, spec):
        if not spec["pack"].startswith("TEST-IELTS"):
            return []
        q = base64.b64encode((BUNDLE / "packs" / spec["pack"] / "question.png").read_bytes()).decode()
        return [{"type": "text", "text": "ĐỀ VÀ BIỂU ĐỒ:"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": q},
                 "cache_control": {"type": "ephemeral", "ttl": "1h"}}]

    def submit(self, limit_files=None):
        reqs, mapping = [], {}
        todo = [(fid, rec) for fid, rec in self.st["files"].items() if rec["status"] == "new" and not rec.get("baseline")]
        for fid, rec in todo[:limit_files or len(todo)]:
            try:
                rq = self.build(fid, rec, self.g.download(fid))
            except Exception as e:
                rec.update(status="error", error=f"{type(e).__name__}"[:80])
                self.tick("error")
                continue
            for q in rq:
                mapping[q["custom_id"]] = fid
            reqs += rq
            rec["status"] = "submitted"
        if reqs:
            b = self.cl.messages.batches.create(requests=reqs)
            self.st["batches"][b.id] = {"at": now().isoformat(), "map": mapping}
            self.tick("graded_requests", len(reqs))

    # ------------------------------------------------------------ results
    def collect(self):
        for bid in list(self.st["batches"]):
            b = self.cl.messages.batches.retrieve(bid)
            if b.processing_status != "ended":
                self.tick("batch_pending")
                continue
            for item in self.cl.messages.batches.results(bid):
                fid = self.st["batches"][bid]["map"].get(item.custom_id)
                rec = self.st["files"].get(fid or "")
                if not rec:
                    continue
                stu = next((s for s in rec["students"].values() if s.get("cid") == item.custom_id), None)
                if not stu:
                    continue
                if item.result.type != "succeeded":
                    stu["status"] = "retry"
                    continue
                resp = item.result.message.model_dump()
                c = cw.cost_usd(MODEL, resp["usage"], batch=True)
                cw.ledger({"at": cw.now_iso(), "category": f"{rec['meta']['cls']} · {label(rec['meta'])}",
                           "step": "grade-batch", "model": MODEL, "usage": resp["usage"], "usd": c,
                           "vnd": round(c * cw.USD_VND)})
                try:
                    res = json.loads(text_of(resp))
                except ValueError:
                    stu["status"] = "retry"
                    continue
                res = self.checks(rec, res)
                sp = pack_for(rec["meta"]) or {}
                free_len = sp.get("item") in ("B12", "B13")   # rulebook: Buổi 12 no upper limit, Buổi 13 no limit
                if res.get("_qa") and (res["_qa"].get("bannedInRevision") or
                                       (not free_len and not 140 <= res["_qa"]["revisionWords"] <= 170)):
                    res = self.fix_revision(rec, res, free_len)
                stu.update(result=res, status="graded", vnd=round(c * cw.USD_VND))
                self.tick("graded")
            del self.st["batches"][bid]
        for rec in self.st["files"].values():
            if rec["status"] == "submitted" and all(s["status"] in ("graded", "unidentified") for s in rec["students"].values()):
                rec["status"] = "graded"

    def fix_revision(self, rec, res, free_len=False):
        """Fighter rule-breaks left in the suggested revision (banned linkers, length) are fixed by a small cheap call."""
        q = res["_qa"]
        prompt = ("Sửa ĐOẠN VĂN tiếng Anh dưới đây (bản sửa gợi ý cho học sinh) theo đúng các yêu cầu, giữ nguyên ý, ví dụ và "
                  "cách diễn đạt còn lại; chỉ trả đoạn văn đã sửa, một đoạn, không lời dẫn.\n"
                  + ("- Giữ nguyên độ dài hiện có.\n" if free_len else f"- Độ dài 140–160 từ (hiện {q['revisionWords']} từ).\n")
                  + "- Không dùng: so, because, because of, but (đối lập), like (nêu ví dụ), you, your, and so on, '...', "
                  "viết tắt. Thay bằng cách nối học thuật đúng nghĩa: as a result, thereby, owing to, whereas, however, such as.\n\n"
                  + res["revision"])
        try:
            r = self.cl.messages.create(model="claude-haiku-5-5", max_tokens=1200, thinking={"type": "disabled"},
                                        messages=[{"role": "user", "content": prompt}])
            u = r.usage.model_dump()
            c = cw.cost_usd("claude-haiku-5-5", u)
            cw.ledger({"at": cw.now_iso(), "category": "Sửa bản sửa (quy ước lớp)", "step": "revision-fix",
                       "model": "claude-haiku-5-5", "usage": u, "usd": c, "vnd": round(c * cw.USD_VND)})
            new = "".join(b.text for b in r.content if b.type == "text").strip()
            allowed = re.sub(r"(?i)not only\b.*?\bbut also|last but not least|but also", " ", new)
            if new and "\n" not in new and not BANNED_FIGHTER.search(allowed) and (free_len or 135 <= words(new) <= 175):
                res["_qa"]["revisionBefore"] = res["revision"]
                res["revision"] = new
                res["_qa"].update(revisionWords=words(new), bannedInRevision=[], revisionFixed=True)
        except Exception:
            res["_qa"]["revisionFixFailed"] = True
        return res

    def checks(self, rec, res):
        """Free checks done by code: word counts, quotes really in the transcript, banned forms, class score."""
        spec = pack_for(rec["meta"])
        if spec["schema"] == "ielts":
            import calculate_class_score as ccs
            for t in res.get("tasks", []):
                qa = {"words": paper_words(t["transcript"]), "revisionWords": words(t.get("revisedText", ""))}
                qa["quotesNotFound"] = [x["quote"] for x in t["annotations"] if x["quote"] not in t["transcript"]]
                qa["bannedInRevision"] = sorted({m.group(0) for m in BANNED_IELTS.finditer(t.get("revisedText", ""))})
                op = [" ".join(x["explanation"].split()[:4]).lower() for x in t["annotations"]]
                qa["repeatedOpenings"] = sorted({o for o in op if op.count(o) > 2})
                bands = [t["criteria"][k]["band"] for k in ("TA_TR", "CC", "LR", "GRA")]
                qa["classScore"] = ccs.calculate(t["task"] if t["task"] in (1, 2) else 1, qa["words"], bands)
                t["_qa"] = qa
            sc = {t["task"]: t["_qa"]["classScore"]["classAssessment"]["overallBand"] for t in res.get("tasks", [])}
            if 1 in sc and 2 in sc:   # full test: Task 2 counts double (rounded to the nearest half band)
                res["_overall"] = round(((sc[1] + 2 * sc[2]) / 3) * 2 + 1e-9) / 2
            return res
        t = res.get("transcript", "")
        qa = {"words": paper_words(t)}
        items = res.get("errors") or []
        qa["quotesNotFound"] = [x["quote"] for x in items if x["quote"] not in t]
        rev = res.get("revision") or ""
        qa["revisionWords"] = words(rev)
        allowed = re.sub(r"(?i)not only\b.*?\bbut also|last but not least|but also", " ", rev)
        qa["bannedInRevision"] = sorted({m.group(0).lower() for m in BANNED_FIGHTER.finditer(allowed)})
        openings = [" ".join(x["explanation"].split()[:4]).lower() for x in items]
        qa["repeatedOpenings"] = sorted({o for o in openings if openings.count(o) > 2})
        s2 = sum(1 for e in items if e["severity"] == "S2")
        s3 = sum(1 for e in items if e["severity"] == "S3")
        level = 3 if s2 >= 6 or s3 >= 2 else 2 if s2 >= 3 or s3 == 1 else 1
        qa["level"] = level
        harsh = "Bài làm rất ẩu. Em chưa kiểm tra và tự sửa bài cẩn thận."
        ov = res.get("overall", "")
        if level == 3 and "Bài làm rất ẩu" not in ov:      # Mức is decided by the error counts (rulebook §11)
            res["overall"] = harsh + " " + ov
            qa["levelAdjusted"] = "added"
        elif level < 3 and "Bài làm rất ẩu" in ov:
            res["overall"] = re.sub(r"Bài làm rất ẩu\.\s*(Em chưa kiểm tra và tự sửa bài cẩn thận\.\s*)?(Cô không chấp nhận[^.]*\.\s*)?", "", ov).strip()
            qa["levelAdjusted"] = "removed"
        if res.get("score"):
            qa["scoreSumOK"] = abs(sum(c["diem"] for c in res["score"]["tieuChi"]) - res["score"]["tong"]) < 1e-6
        res["_qa"] = qa
        return res


    # ------------------------------------------------------------ publish to the class tracker
    @staticmethod
    def find_columns(grid, meta, tasks):
        """Tracker columns for this paper test.
        FIGHTER: row 2 'KT 0N' with row 3 'Điểm /1 …'.
        IELTS: the block whose row-2 title says 'KIỂM TRA … LẦN N' (and mentions VIẾT); inside it the row-4 cell
        'VIẾT (TASK t)'. A block with a single plain 'VIẾT' column takes every task. Returns {task|0: column index}."""
        row = lambda r: grid[r] if r < len(grid) else []
        cell = lambda r, c: str(row(r)[c]) if c < len(row(r)) else ""
        width = max((len(x) for x in grid[:4]), default=0)
        if meta["cls"].startswith("FIGHTER"):
            for c in range(width):
                if re.fullmatch(rf"\s*KT\s*0*{meta['n']}\s*", cell(1, c)) and "Điểm /1" in cell(2, c):
                    return {0: c}
            return {}
        for c in range(width):
            t = unicodedata.normalize("NFC", cell(1, c)).upper()
            if "KIỂM TRA" in t and "VIẾT" in t and re.search(rf"LẦN\s*0*{meta['n']}\b", t):
                end = next((x for x in range(c + 1, width) if cell(1, x).strip()), width)
                out, plain, in_viet = {}, [], False
                for x in range(c, end):
                    top = unicodedata.normalize("NFC", " ".join(cell(r, x) for r in (2, 3))).upper()
                    if top.strip():   # a new row-3/4 label starts a new group (ĐỌC, NGHE, VIẾT …); blank = merged
                        in_viet = bool(re.search(r"\bVIẾT\b", top))
                    lab = top + " " + unicodedata.normalize("NFC", cell(4, x)).upper()
                    m = re.search(r"TASK\s*([12])", lab)
                    if in_viet and m:
                        out[int(m.group(1))] = x
                    elif in_viet and re.search(r"\bVIẾT\b", top):
                        plain.append(x)
                if not out and len(plain) == 1:
                    out = {0: plain[0]}
                return out
        return {}

    def add_fighter_column(self, tr, grid, n):
        """Insert 'KT 0n' right after the last existing KT column, same format, headers as KT 01. Only Fighter, only
        when a KT 01-style column exists to copy (never guesses a place in an unfamiliar tracker)."""
        row = lambda r: grid[r] if r < len(grid) else []
        kts = [c for c, v in enumerate(row(1)) if re.fullmatch(r"\s*KT\s*0*\d+\s*", str(v)) and "Điểm /1" in str(row(2)[c] if c < len(row(2)) else "")]
        if not kts:
            return False
        at = max(kts) + 1
        meta = self.g._req(f"https://sheets.googleapis.com/v4/spreadsheets/{tr.id}?fields=sheets.properties(sheetId,title)")
        gid = next((x["properties"]["sheetId"] for x in meta["sheets"] if x["properties"]["title"] == tr.tab), None)
        if gid is None:
            return False
        self.g._req(f"https://sheets.googleapis.com/v4/spreadsheets/{tr.id}:batchUpdate", "POST", {"requests": [
            {"insertDimension": {"range": {"sheetId": gid, "dimension": "COLUMNS", "startIndex": at, "endIndex": at + 1},
                                 "inheritFromBefore": True}},
            {"copyPaste": {"source": {"sheetId": gid, "startColumnIndex": max(kts), "endColumnIndex": max(kts) + 1},
                           "destination": {"sheetId": gid, "startColumnIndex": at, "endColumnIndex": at + 1},
                           "pasteType": "PASTE_FORMAT"}}]})
        self.g.set_cell(tr.id, f"'{tr.tab}'!{col_letter(at)}2", f"KT {n:02d}")
        self.g.set_cell(tr.id, f"'{tr.tab}'!{col_letter(at)}3", str(row(2)[max(kts)]))
        tr._hdr = None   # columns moved: every cached column position of this tracker is stale
        self.tick("kt_column_added")
        return True

    @staticmethod
    def inclass_key(meta):
        return label(meta).replace("Viết trên lớp ", "") + (f" · Task {meta['task']}" if meta.get("task") else "")

    def inclass_column(self, tr, grid, meta, create=True):
        """In-class writing: its own column, row 2 'VIẾT TRÊN LỚP', row 3 '<Buổi N | bài N> · dd/mm/yyyy'.
        Created at the first empty column after the tracker's used area (no merged header is touched)."""
        row = lambda r: grid[r] if r < len(grid) else []
        key = self.inclass_key(meta)
        width = max((len(x) for x in grid), default=0)
        for c in range(width):
            top = unicodedata.normalize("NFC", str(row(1)[c]) if c < len(row(1)) else "").upper()
            sub = unicodedata.normalize("NFC", str(row(2)[c]) if c < len(row(2)) else "")
            if "VIẾT TRÊN LỚP" in top and sub.split("\n")[0].strip() == key and meta["date"] in sub:
                return c
        if not create:
            return None
        info = self.g._req(f"https://sheets.googleapis.com/v4/spreadsheets/{tr.id}?fields=sheets.properties(sheetId,title,gridProperties)")
        p = next((x["properties"] for x in info["sheets"] if x["properties"]["title"] == tr.tab), None)
        if p is None:
            return None
        gid, cols = p["sheetId"], p.get("gridProperties", {}).get("columnCount", 0)
        reqs = []
        if width >= cols:
            reqs.append({"appendDimension": {"sheetId": gid, "dimension": "COLUMNS", "length": 1}})
        if reqs:
            self.g._req(f"https://sheets.googleapis.com/v4/spreadsheets/{tr.id}:batchUpdate", "POST", {"requests": reqs})
        if width > 0:   # format of the pupils' rows only: the header rows may be merged (copying them fails with 400)
            try:
                self.g._req(f"https://sheets.googleapis.com/v4/spreadsheets/{tr.id}:batchUpdate", "POST", {"requests": [
                    {"copyPaste": {"source": {"sheetId": gid, "startRowIndex": 4, "endRowIndex": 200,
                                              "startColumnIndex": width - 1, "endColumnIndex": width},
                                   "destination": {"sheetId": gid, "startRowIndex": 4, "endRowIndex": 200,
                                                   "startColumnIndex": width, "endColumnIndex": width + 1},
                                   "pasteType": "PASTE_FORMAT"}},
                    {"repeatCell": {"range": {"sheetId": gid, "startRowIndex": 1, "endRowIndex": 3,
                                              "startColumnIndex": width, "endColumnIndex": width + 1},
                                    "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "wrapStrategy": "WRAP",
                                                                   "horizontalAlignment": "CENTER"}},
                                    "fields": "userEnteredFormat(textFormat.bold,wrapStrategy,horizontalAlignment)"}}]})
            except Exception:
                self.tick("inclass_column_format_skipped")
        self.g.set_cell(tr.id, f"'{tr.tab}'!{col_letter(width)}2", "VIẾT TRÊN LỚP")
        self.g.set_cell(tr.id, f"'{tr.tab}'!{col_letter(width)}3", f"{key}\n{meta['date']}")
        tr._hdr = None
        self.tick("inclass_column_added")
        return width

    @staticmethod
    def fmt(x):
        return f"{x:.2f}".replace(".", ",") if abs(x * 10 - round(x * 10)) > 1e-9 else f"{x:.1f}".replace(".", ",")

    def cell_text(self, rec, res, task=None):
        if rec["meta"]["cls"].startswith("FIGHTER"):
            sc = res.get("score") or {}
            if not sc and rec["meta"].get("kind") == "inclass":   # Buổi 2–15: corrected, no score (rulebook §1)
                return f"Đã chữa: {label(rec['meta'])}\n{res['overall'].strip()}\nSố từ: {res['_qa']['words']}"
            if not sc:
                return None
            return f"{self.fmt(sc['tong'])}/1\n{res['overall'].strip()}\nSố từ: {res['_qa']['words']}"
        lines = []
        for t in res.get("tasks", []):
            if task and t["task"] != task:
                continue
            cs = t["_qa"]["classScore"]
            cr = cs["classAssessment"]["criteria"]
            ta = cr.get("TA", cr.get("TR"))
            band = cs["classAssessment"]["overallBand"]
            head = f"{band:.1f}" if task else f"Task {t['task']}: {band:.1f}"
            note = f"Số từ: {cs['wordCount']}/{cs['minimum']}"
            if cs["shortfall"] > 0:
                note += f"; thiếu {cs['shortfallPercent']:g}%"
                if cs["deductionPerLanguageCriterion"]:
                    note += f"; đã trừ {cs['deductionPerLanguageCriterion']:g} ở mỗi CC, LR, GRA theo quy tắc lớp"
            lines.append(f"{head}\n{'TA' if t['task'] == 1 else 'TR'}: {ta:g} | CC: {cr['CC']:g} | LR: {cr['LR']:g} | "
                         f"GRA: {cr['GRA']:g}\n{t['overall'].strip()}\n{note}.")
        if not lines:
            return None
        if not task and res.get("_overall") is not None:
            lines.insert(0, f"Overall: {res['_overall']:.1f}")
        return "\n\n".join(lines)

    def publish(self):
        """Graded paper tests → the class tracker. A cell that already has anything is never touched (the result was
        given before); a test without its tracker column waits until the column exists."""
        cut = self.r.cfg.get("scanBaselineBefore") or ""
        for fid, rec in sorted(self.st["files"].items(), key=lambda kv: ((kv[1].get("meta") or {}).get("cls", ""), (kv[1].get("meta") or {}).get("n") or 0)):
            if (rec.get("modified") or "") < cut and not rec.get("approvedOld"):   # pre-go-live trials stay unpublished
                continue
            todo = [s for s in rec["students"].values() if s["status"] in ("graded", "held") and s.get("name")]
            if not todo:
                continue
            try:   # one file's trouble must not stop the others; the reason is kept for checking
                self.publish_file(rec, todo)
                rec.pop("publishError", None)
            except Exception as e:
                rec["publishError"] = f"{type(e).__name__}: {str(e)[:300]}"
                self.tick("publish_error")

    def publish_file(self, rec, todo):
        if True:
            tr = self.r.tracker(rec["meta"]["cls"])
            tr._grid = None
            tr.cached("A", 1)
            grid = tr._grid
            spec = pack_for(rec["meta"])
            if spec.get("inclass"):
                c = self.inclass_column(tr, grid, rec["meta"])
                if c is not None:
                    tr._grid = None
                    tr.cached("A", 1)
                    grid = tr._grid
                cols = {} if c is None else {(spec.get("tasks") or [0])[0] if spec["schema"] == "ielts" else 0: c}
            else:
                cols = self.find_columns(grid, rec["meta"], spec.get("tasks") or [])
            if not cols and not spec.get("inclass") and rec["meta"]["cls"].startswith("FIGHTER"):
                if self.add_fighter_column(tr, grid, rec["meta"]["n"]):   # Cô 10/11: open the KT column automatically
                    tr._grid = None
                    tr.cached("A", 1)
                    grid = tr._grid
                    cols = self.find_columns(grid, rec["meta"], spec.get("tasks") or [])
            if not cols:
                for s in todo:
                    s.update(status="held", hold="no_tracker_column")
                self.tick("held_no_column", len(todo))
                return
            for s in todo:
                row = tr.row_of(s["name"])
                if not row:
                    s.update(status="dropped", hold="not_in_roster")   # Cô 10/11: not on the class list → dropped
                    self.tick("dropped_not_in_roster")
                    continue
                done = True
                for task, c in cols.items():
                    text = self.cell_text(rec, s["result"], task or None)
                    if text is None:
                        continue
                    a1 = f"{col_letter(c)}{row}"
                    cur = tr.cell(a1)
                    if cur.strip():
                        if cur.strip() != text.strip():
                            s.setdefault("skippedCells", []).append(a1)   # result already given there
                        continue
                    tr.write(a1, text)
                    if tr.cell(a1).strip() != text.strip():
                        done = False
                        s["hold"] = "readback_mismatch"
                if done:
                    s.update(status="published", at=now().isoformat())
                    self.tick("published")
                else:
                    s["status"] = "held"

    def review(self):
        out = []
        for fid, rec in self.st["files"].items():
            for k, s in rec["students"].items():
                out.append({"file": rec["title"], "status": s["status"], "name": s.get("name"), "nameRead": s.get("nameRead"),
                            "pages": s["pages"], "vnd": s.get("vnd"), "result": s.get("result")})
        save_json(STATE_DIR / "scan-review.json", {"at": now().isoformat(), "files": {f: {"title": r["title"], "status": r["status"]}
                                                                                       for f, r in self.st["files"].items()},
                                                   "students": out})


def run(runner, only=None, limit_files=None):
    sc = Scans(runner)
    try:
        sc.collect()
        if runner.auto_publish():
            sc.publish()
        sc.discover()
        for rec in sc.st["files"].values():   # a long scan could overflow the page-reading answer: retry once
            if rec["status"] == "error" and rec.get("error") == "JSONDecodeError" and not rec.get("retried"):
                rec.update(status="new", retried=True, students={})
        for fid in runner.cfg.get("scanDone") or []:   # Cô already graded these in the old system: leave them alone
            rec = sc.st["files"].get(fid)
            if rec and rec["status"] != "teacher_done":
                rec.update(status="teacher_done", rescued=2, retried=True)
        for fid in runner.cfg.get("scanApprovedOld") or []:   # papers from before go-live that Cô asked to grade
            rec = sc.st["files"].get(fid)
            if rec and not rec.get("approvedOld") and rec.get("meta") and rec["meta"].get("cls") in runner.cfg["classes"]:
                rec.update(status="new" if pack_for(rec["meta"]) else "no_pack", students={}, approvedOld=True)
                rec.pop("baseline", None)
                sc.tick("approved_old")
        for fid in (only or []):   # trial re-run of a named file
            rec = sc.st["files"].get(fid)
            if (rec and rec["status"] == "graded" and runner.cfg.get("scanRegrade") == fid
                    and fid not in sc.st.setdefault("regradeDone", [])):   # one re-run only, never a loop
                rec.update(status="new", students={})
                sc.st["regradeDone"].append(fid)
        if only:  # trial: grade only the named file(s); everything else waits
            for fid, rec in sc.st["files"].items():
                if rec["status"] == "new" and fid not in only:
                    rec["status"] = "waiting"
        sc.submit(limit_files)
        sc.rescue()
    finally:
        sc.save()
        sc.review()
