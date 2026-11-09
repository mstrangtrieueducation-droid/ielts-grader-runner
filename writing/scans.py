"""Paper tests / in-class writing scanned into the Drive scan folder → split by student → graded in a batch.

File names: "<IELTS|FIGHTER> <n>_<DD-MM-YYYY>_Viết [task 1|2] kiểm tra lần <N>" (one PDF per class and paper).
Results are kept (encrypted with the runner state) for the teacher's review; nothing is written to trackers here.
Grading uses the lean packs approved 09/11/2026: Sonnet without the reasoning pass, only the fields students see.
"""
import base64, io, json, re, unicodedata
from pathlib import Path

import claude_worker as cw
from run_writing import BUNDLE, STATE_DIR, WORK, h, load_json, norm, now, save_json

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


def parse_name(title):
    m = NAME_RE.match(unicodedata.normalize("NFC", title))
    if not m:
        return None
    prog, n, d, mo, y, rest = m.groups()
    t = rest.lower()
    lan = re.search(r"lần\s*(\d+)", t)
    task = re.search(r"task\s*([12])", t)
    kind = "test" if lan else ("inclass" if "trên lớp" in t or "buổi" in t else None)
    return {"cls": f"{prog.upper()} {int(n)}", "date": f"{int(d):02d}/{int(mo):02d}/{y}", "kind": kind,
            "n": int(lan.group(1)) if lan else None, "task": int(task.group(1)) if task else None}


def pack_for(meta):
    """Which approved pack grades this paper (None = not prepared yet → reported, not graded)."""
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
        resp = cw.call_api(self.cl, {"model": MODEL, "max_tokens": 4000, "thinking": {"type": "between_tools"},
                                     "output_config": {"format": {"type": "json_schema", "schema": SEGMENT_SCHEMA}},
                                     "messages": [{"role": "user", "content": content}]})
        resp = resp if isinstance(resp, dict) else resp.model_dump()
        c = cw.cost_usd(MODEL, resp["usage"])
        cw.ledger({"at": cw.now_iso(), "category": "Tách bài scan", "step": "segment", "model": MODEL,
                   "usage": resp["usage"], "usd": c, "vnd": round(c * cw.USD_VND)})
        return json.loads(text_of(resp))["pages"]

    def build(self, fid, rec, pdf_bytes):
        import pymupdf as fitz
        meta, spec = rec["meta"], pack_for(rec["meta"])
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        tr = self.r.tracker(meta["cls"])
        roster_rows = tr.rows()
        roster = [n for n in roster_rows if n and not n.startswith(("HỌ TÊN", "HỌ VÀ TÊN", "STT"))]
        pages = self.segment(doc, roster)
        groups, cur = [], None
        for p in sorted(pages, key=lambda x: x["page"]):
            if p["header"] or cur is None:
                cur = {"pages": [p["page"]], "nameRead": p["nameRead"],
                       "name": norm(p["rosterName"]) if p["sure"] and norm(p["rosterName"]) in roster_rows else None}
                groups.append(cur)
            else:
                cur["pages"].append(p["page"])
        head = (BUNDLE / "packs" / spec["pack"] / "head.md").read_text(encoding="utf-8")
        system = [{"type": "text", "text": head, "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
        task_text = self.task_text(spec)
        reqs, seen = [], set()
        for g in groups:
            if not g["name"] or g["name"] in seen:   # unreadable / duplicate name → the teacher assigns it
                key = f"?{g['pages'][0]}"
                rec["students"][key] = {"name": None, "nameRead": g["nameRead"], "pages": g["pages"], "status": "unidentified"}
                self.tick("unidentified")
                continue
            seen.add(g["name"])
            key = h(g["name"], 10)
            content = self.reference_blocks(spec) + [img(jpeg(doc[i - 1], 1568)) for i in g["pages"]]
            content.append({"type": "text", "text":
                f"Lớp {meta['cls']} · học sinh {g['name']} (đã đối chiếu danh sách lớp) · ngày kiểm tra {meta['date']} · "
                f"{len(g['pages'])} trang ảnh theo thứ tự trên.\n{task_text}\nChép bài, chấm và chữa theo hướng dẫn."})
            schema = FIGHTER_SCHEMA if spec["schema"] == "fighter" else IELTS_SCHEMA
            cid = h(fid + key + rec["modified"], 40)
            reqs.append({"custom_id": cid, "params": {
                "model": MODEL, "max_tokens": 12000, "thinking": {"type": "between_tools"}, "system": system,
                "output_config": {"format": {"type": "json_schema", "schema": schema}},
                "messages": [{"role": "user", "content": content}]}})
            rec["students"][key] = {"name": g["name"], "nameRead": g["nameRead"], "pages": g["pages"],
                                    "status": "submitted", "cid": cid}
        return reqs

    def task_text(self, spec):
        if spec["pack"] == "TEST-FIGHTER":
            kt = json.loads((BUNDLE / "packs/TEST-FIGHTER/kt.json").read_text(encoding="utf-8"))[spec["item"]]
            return (f"Bài kiểm tra tự viết {spec['item']} — chủ đề {kt['topic']}. Chế độ: 1-điểm (mục 13).\n"
                    f"Đề: {kt['prompt']}\nĐộ dài: 140–160 từ; 161–170 chấp nhận; dưới 140 cần phát triển; trên 170 cần rút gọn.\n"
                    "Outline/bài mẫu riêng của đề này chưa có trong nguồn: không bắt em phải có ý của bài mẫu.")
        n = spec["pack"][-1]
        which = " và ".join(f"Task {t}" for t in spec["tasks"])
        return (f"Kiểm tra Writing lần {n}. Chấm {which} có trong ảnh bài làm (mỗi Task một mục trong `tasks`). "
                "Ảnh đầu tiên là đề và biểu đồ Task 1. Task 1 tối thiểu 150 từ, Task 2 tối thiểu 250 từ.")

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
                cw.ledger({"at": cw.now_iso(), "category": f"{rec['meta']['cls']} · Kiểm tra lần {rec['meta']['n']}",
                           "step": "grade-batch", "model": MODEL, "usage": resp["usage"], "usd": c,
                           "vnd": round(c * cw.USD_VND)})
                try:
                    res = json.loads(text_of(resp))
                except ValueError:
                    stu["status"] = "retry"
                    continue
                stu.update(result=self.checks(rec, res), status="graded", vnd=round(c * cw.USD_VND))
                self.tick("graded")
            del self.st["batches"][bid]
        for rec in self.st["files"].values():
            if rec["status"] == "submitted" and all(s["status"] in ("graded", "unidentified") for s in rec["students"].values()):
                rec["status"] = "graded"

    def checks(self, rec, res):
        """Free checks done by code: word counts, quotes really in the transcript, banned forms, class score."""
        spec = pack_for(rec["meta"])
        if spec["schema"] == "ielts":
            import calculate_class_score as ccs
            for t in res.get("tasks", []):
                qa = {"words": words(t["transcript"]), "revisionWords": words(t.get("revisedText", ""))}
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
        qa = {"words": words(t)}
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
        sc.discover()
        for fid in (only or []):   # trial re-run of a named file
            rec = sc.st["files"].get(fid)
            if rec and rec["status"] == "graded" and runner.cfg.get("scanRegrade") == fid:
                rec.update(status="new", students={})
        if only:  # trial: grade only the named file(s); everything else waits
            for fid, rec in sc.st["files"].items():
                if rec["status"] == "new" and fid not in only:
                    rec["status"] = "waiting"
        sc.submit(limit_files)
    finally:
        sc.save()
        sc.review()
