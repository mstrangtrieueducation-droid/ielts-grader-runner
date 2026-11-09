"""IELTS/Fighter Writing runner (cloud) — Claude API, Batch first.

One cycle = collect finished batches → scan Form tabs for new/changed submissions → submit one batch
→ publish approved results to the class tracker → print counts only.

Rules carried over from the teacher's pipeline:
  * notebook first; essays only for timely submissions whose notebook passed (essay packs optional)
  * several submissions of the same student for one assignment are combined into one job
  * late (after the "Hạn" in the tracker header) = notebook check only
  * never overwrite the system status prefix; never write over a teacher comment we did not write
  * cells whose prefix is "⛔ QUÁ HẠN — CHƯA GHI NHẬN" are held for the teacher
  * public logs show counts only — no names, no feedback

Env: ANTHROPIC_API_KEY, GOOGLE_SERVICE_ACCOUNT_JSON, WRITING_BUNDLE_KEY,
     MODE=cycle|audit|publish, APPROVE=all|key1,key2 (optional), STATE_DIR, BUNDLE_DIR.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import claude_worker as cw  # noqa: E402

VN = dt.timezone(dt.timedelta(hours=7))
RUNTIME = Path(os.environ.get("RUNTIME_DIR", HERE.parent / ".runtime" / "writing"))
BUNDLE = Path(os.environ.get("BUNDLE_DIR", RUNTIME / "bundle"))
STATE_DIR = Path(os.environ.get("STATE_DIR", RUNTIME / "state"))
WORK = RUNTIME / "work"
MARK = "— NHẬN XÉT GV —"
DONE = ("published", "held", "late_essay", "skipped", "no_tracker_column")


# ---------------------------------------------------------------- helpers
def now():
    return dt.datetime.now(VN)


def norm(name: str) -> str:
    s = unicodedata.normalize("NFC", str(name or "")).upper()
    return re.sub(r"\s+", " ", s).strip()


def h(s: str, n=16) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:n]


def parse_vn_time(s):
    s = str(s or "").strip()
    for f in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(s, f).replace(tzinfo=VN)
        except ValueError:
            pass
    return None


def to_jpeg(data: bytes) -> bytes:
    """Any photo format the form accepts (JPEG, PNG, HEIC/HEIF, WebP…) → JPEG bytes."""
    if data[:3] == b"\xff\xd8\xff":
        return data
    import io
    from PIL import Image, ImageOps
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    out = io.BytesIO()
    im.save(out, "JPEG", quality=90)
    return out.getvalue()


def file_id(url):
    m = re.search(r"(?:id=|/d/)([A-Za-z0-9_-]{20,})", str(url or ""))
    return m.group(1) if m else None


def col_letter(i: int) -> str:  # 0-based
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def load_json(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(p, data):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(p) + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


# ---------------------------------------------------------------- tracker
class Tracker:
    def __init__(self, g, sheet_id, tab):
        self.g, self.id, self.tab = g, sheet_id, tab
        self._hdr = None
        self._names = None

    def header(self):
        if self._hdr is None:
            self._hdr = (self.g.values(self.id, f"'{self.tab}'!A4:ZZ4") or [[]])[0]
        return self._hdr

    def column(self, code):
        for i, v in enumerate(self.header()):
            if re.search(r"Mã:\s*" + re.escape(code) + r"\b", str(v)):
                m = re.search(r"Hạn:[^\n]*?(\d{2}/\d{2}/\d{4})", str(v))
                deadline = parse_vn_time(m.group(1) + " 23:59:59") if m else None
                return col_letter(i), deadline
        return None, None

    def rows(self):
        if self._names is None:
            vals = self.g.values(self.id, f"'{self.tab}'!B1:B200")
            # the name is the first line; staff sometimes add notes below it ("new 31/10/2026")
            self._names = {norm(r[0].strip().split("\n")[0]): n + 1 for n, r in enumerate(vals) if r and r[0].strip()}
        return self._names

    def row_of(self, name):
        """Exact name first; otherwise a unique match ignoring diacritics (form typos like CỒNG ↔ CÔNG)."""
        rows = self.rows()
        if name in rows:
            return rows[name]
        bare = lambda s: "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c)).replace("Đ", "D")
        hits = [r for n, r in rows.items() if bare(n) == bare(name)]
        return hits[0] if len(hits) == 1 else None

    def cell(self, a1):  # live read: used only right before / after a write
        v = self.g.values(self.id, f"'{self.tab}'!{a1}")
        return v[0][0] if v and v[0] else ""

    def cached(self, col, row):
        """One read of the whole tab per run for scanning (avoids per-cell reads hitting the Sheets quota)."""
        if getattr(self, "_grid", None) is None:
            self._grid = self.g.values(self.id, f"'{self.tab}'!A1:ZZ200")
        idx = 0
        for ch in col:
            idx = idx * 26 + (ord(ch) - 64)
        r = self._grid[row - 1] if row - 1 < len(self._grid) else []
        return r[idx - 1] if idx - 1 < len(r) else ""

    def write(self, a1, text):
        self.g.set_cell(self.id, f"'{self.tab}'!{a1}", text)


# ---------------------------------------------------------------- runner
class Runner:
    def __init__(self, g, cfg, state):
        self.g, self.cfg, self.state = g, cfg, state
        self.trackers = {}
        self.counts = {}
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        WORK.mkdir(parents=True, exist_ok=True)
        cw.LEDGER = STATE_DIR / "ledger.jsonl"
        cw.HERE = WORK  # batch bookkeeping files stay in the ephemeral work dir

    def tick(self, k, n=1):
        self.counts[k] = self.counts.get(k, 0) + n

    def tracker(self, cls):
        if cls not in self.trackers:
            self.trackers[cls] = Tracker(self.g, self.cfg["classes"][cls], self.cfg.get("trackerTab", "THEO DÕI TOÀN DIỆN"))
        return self.trackers[cls]

    # ---------------- discovery
    def discover_classes(self):
        """Every tracker named 'IELTS N_THEO DÕI TOÀN DIỆN' / 'FIGHTER N_…' shared with the service account
        becomes a class automatically (new classes need no configuration)."""
        try:
            files = self.g.search("name contains 'THEO DÕI TOÀN DIỆN' and "
                                  "mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false")
        except Exception:
            self.tick("class_discovery_failed")
            return
        found = 0
        for f in files:
            m = re.match(r"\s*(IELTS|FIGHTER)\s*(\d+)\s*_\s*THEO DÕI TOÀN DIỆN\s*$", unicodedata.normalize("NFC", f["name"]), re.I)
            if m:
                name = f"{m.group(1).upper()} {int(m.group(2))}"
                if name not in self.cfg["classes"]:
                    self.cfg["classes"][name] = f["id"]
                    found += 1
        if found:
            self.tick("classes_discovered", found)

    def closed(self, a):
        """A week is skipped once every class's deadline is more than 14 days in the past (late work after the
        next writing day is not graded anyway), so the scan stays light as weeks accumulate."""
        closed = self.state.setdefault("closedWeeks", {})
        if a["code"] in closed:
            return True
        last = self.state.setdefault("lastDeadline", {}).get(a["code"])
        if last and now() > dt.datetime.fromisoformat(last) + dt.timedelta(days=14):
            closed[a["code"]] = now().isoformat()
            return True
        return False

    def note_deadline(self, code, deadline):
        if deadline:
            ld = self.state.setdefault("lastDeadline", {})
            if not ld.get(code) or dt.datetime.fromisoformat(ld[code]) < deadline:
                ld[code] = deadline.isoformat()

    def scan(self):
        subs = self.state.setdefault("subs", {})
        self.discover_classes()
        for a in self.cfg["assignments"]:
            if not a.get("enabled", True) or self.closed(a):
                continue
            rows = self.g.values(self.cfg["formSheet"], f"'{a['formTab']}'!A2:G2000")
            grouped = {}
            for n, r in enumerate(rows, start=2):
                r = r + [""] * (7 - len(r))
                cls, name = r[2].strip(), norm(r[1])
                if not name or cls not in self.cfg["classes"] or (a["classes"] != "*" and cls not in a["classes"]):
                    continue
                fid = file_id(r[5]) or file_id(r[3])
                if not fid:
                    continue
                grouped.setdefault((cls, name), []).append({"row": n, "time": r[0], "fileId": fid,
                                                            "extra": [x for x in (file_id(u) for u in re.split(r",\s*", r[4])) if x]})
            for (cls, name), items in grouped.items():
                items.sort(key=lambda x: parse_vn_time(x["time"]) or now())
                key = f"{a['code']}|{cls}|{h(name, 10)}"
                files = []
                for it in items:
                    for f in [it["fileId"]] + it["extra"]:
                        if f not in files:
                            files.append(f)
                sig = h("|".join(files))
                old = subs.get(key)
                if old and old.get("sig") == sig and not (old.get("status") == "no_tracker_column"
                                                          and self.tracker(cls).column(a["code"])[0]):
                    continue
                if old and old.get("status") == "published":
                    self.tick("changed_after_publish")
                status = "new"
                if not self.tracker(cls).column(a["code"])[0]:
                    status = "no_tracker_column"   # class tracker has no column for this week: nothing to write to
                elif not old and not self.state.get("baselined", {}).get(a["code"]):
                    # first sight of this assignment: work already commented by the old pipeline is not regraded
                    if self.too_old(cls, a["code"]) or self.existing_comment(cls, a["code"], name):
                        status = "skipped"
                subs[key] = {"assignment": a["code"], "className": cls, "student": name, "files": files,
                             "rows": [i["row"] for i in items], "submittedAt": items[-1]["time"],
                             "firstAt": items[0]["time"], "sig": sig, "status": status, "at": now().isoformat()}
                self.tick(status)
            self.state.setdefault("baselined", {})[a["code"]] = True
        self.unconfigured()

    def existing_comment(self, cls, code, name):
        tr = self.tracker(cls)
        col, _ = tr.column(code)
        row = tr.row_of(name)
        if not col or not row:
            return False
        cur = tr.cached(col, row)
        return MARK in cur and bool(cur.split(MARK, 1)[1].strip())

    def too_old(self, cls, code):
        """Weeks whose deadline passed more than 14 days ago are history: never graded on first sight."""
        _, deadline = self.tracker(cls).column(code)
        if deadline:
            self.note_deadline(code, deadline)
        return bool(deadline and now() > deadline + dt.timedelta(days=14))

    def unconfigured(self):
        # Form tabs for weeks that have no pack yet are reported (count only) so a pack can be prepared.
        try:
            from_tabs = self.g.sheet_titles(self.cfg["formSheet"])
        except Exception:
            return
        known = {a["formTab"] for a in self.cfg["assignments"]}
        recent = sorted(t for t in from_tabs if re.match(r"IELTS WRITING - W\d+$", t) and t not in known)[-3:]
        self.state["unconfiguredTabs"] = recent
        if recent:
            self.tick("weeks_without_pack", len(recent))

    # ---------------- job preparation (idempotent; also used when collecting a batch)
    def assignment(self, code):
        return next(a for a in self.cfg["assignments"] if a["code"] == code)

    def prepare(self, key, sub, step="notebook"):
        import pymupdf as fitz
        a = self.assignment(sub["assignment"])
        pack = BUNDLE / "packs" / (a["pack"] if step == "notebook" else a["essayPack"])
        d = WORK / h(key + step, 20)
        d.mkdir(parents=True, exist_ok=True)
        paths, pages = [], 0
        for i, f in enumerate(sub["files"], 1):
            p = d / f"file-{i:02d}.pdf"
            if not p.exists():
                data = self.g.download(f)
                if data[:4] != b"%PDF":  # Form uploads may be images (iPhone photos arrive as HEIC)
                    p = d / f"file-{i:02d}.jpg"
                    data = to_jpeg(data)
                p.write_bytes(data)
            paths.append(p)
            pages += fitz.open(p).page_count if p.suffix == ".pdf" else 1
        tr = self.tracker(sub["className"])
        _, deadline = tr.column(sub["assignment"])
        self.note_deadline(sub["assignment"], deadline)
        sub_time = parse_vn_time(sub["submittedAt"])
        job = {"className": sub["className"], "assignmentCode": sub["assignment"], "studentName": sub["student"],
               "sourceRows": sub["rows"], "submittedAt": sub["submittedAt"],
               "submittedDateVN": sub_time.strftime("%d/%m/%Y") if sub_time else "",
               "deadline": deadline.strftime("%d/%m/%Y") if deadline else None,
               "afterDeadline": bool(deadline and sub_time and sub_time > deadline),
               "totalPages": pages, "submissionCount": len(sub["rows"])}
        (d / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
        head = (pack / "head.md").read_text(encoding="utf-8")
        head = head.replace("{{CLASS}}", sub["className"]).replace("{{PACK}}", str(pack))
        listing = "\n".join(f"- {p}" for p in paths)
        many = f" (gộp {len(sub['rows'])} lượt nộp, xem cả hai)" if len(sub["rows"]) > 1 else ""
        wi = (head.rstrip() + "\n\n## JOB — DỮ LIỆU\n\n"
              + f"Học sinh: {sub['student']} · {sub['className']} · nộp {sub['submittedAt']} · {pages} trang{many}.\n"
              + "Tệp bài (xem MỌI trang):\n" + listing + "\n")
        (d / "worker-input.md").write_text(wi, encoding="utf-8")
        spec = {"workerInput": str(d / "worker-input.md"), "output": str(d / "result.json"), "job": str(d / "job.json"),
                "schema": str(pack / "schema.json"), "media": [str(p) for p in paths],
                "validator": f"cmd:{sys.executable} {pack / 'validate.py'} {{draft}} {{job}}",
                "kind": "notebook" if step == "notebook" else "essay",
                "category": f"{sub['className']} · {'Kiểm tra vở' if step == 'notebook' else a.get('essayLabel', 'Bài viết')} · "
                            + sub["assignment"].split("-")[-1]}
        if step != "notebook" and deadline:
            spec["deadline"] = deadline.strftime("%d/%m/%Y %H:%M:%S")
        return spec, job

    # ---------------- batch submit / collect
    def submit(self):
        for s in self.state.get("subs", {}).values():  # retry download/convert failures a few times
            if s["status"] == "error" and str(s.get("error", "")).startswith("prepare:") and s.get("tries", 0) < 3:
                s["tries"] = s.get("tries", 0) + 1
                s["status"] = s.get("errStep") == "essay" and "essay_new" or "new"
        todo = [(k, s) for k, s in self.state.get("subs", {}).items() if s["status"] in ("new", "essay_new")]
        if not todo:
            return
        reqs, mapping = [], {}
        model = self.cfg.get("model", cw.DEFAULT_MODEL)
        for k, s in todo:
            step = "essay" if s["status"] == "essay_new" else "notebook"
            try:
                spec, _ = self.prepare(k, s, step)
                params, _ = cw.build_params(spec, model, 24000, 0)
            except Exception as e:
                s.update(status="error", error=f"prepare:{type(e).__name__}"[:120], errStep=step)
                self.tick("error")
                continue
            cid = h(k + step + s["sig"], 40)
            reqs.append({"custom_id": cid, "params": params})
            mapping[cid] = {"key": k, "step": step}
        if not reqs:
            return
        b = cw.client().messages.batches.create(requests=reqs)
        self.state.setdefault("batches", {})[b.id] = {"at": now().isoformat(), "map": mapping, "model": model}
        for m in mapping.values():
            self.state["subs"][m["key"]]["status"] = "submitted" if m["step"] == "notebook" else "essay_submitted"
        self.tick("submitted", len(reqs))

    def collect(self):
        batches = self.state.get("batches", {})
        if not batches:
            return
        cl = cw.client()
        for bid in list(batches):
            info = batches[bid]
            b = cl.messages.batches.retrieve(bid)
            if b.processing_status != "ended":
                self.tick("batch_pending")
                continue
            for item in cl.messages.batches.results(bid):
                m = info["map"].get(item.custom_id)
                if not m:
                    continue
                k, s = m["key"], self.state["subs"][m["key"]]
                if item.result.type != "succeeded":
                    s.update(status="new" if m["step"] == "notebook" else "essay_new")  # resubmit next cycle
                    self.tick("batch_retry")
                    continue
                resp = item.result.message.model_dump()
                c = cw.cost_usd(info["model"], resp["usage"], batch=True)
                spec, job = self.prepare(k, s, m["step"])
                cw.ledger({"at": cw.now_iso(), "category": spec["category"], "step": "grade-batch",
                           "model": info["model"], "usage": resp["usage"], "usd": c, "vnd": round(c * cw.USD_VND)})
                r = cw.process(spec, info["model"], 24000, 0, 1, cl=cl, raw_override=resp, batch=True)
                self.finish(k, s, m["step"], r, spec, job)
            del batches[bid]

    def finish(self, k, s, step, r, spec, job):
        if r.get("state") not in ("written", "written_after_full_recheck"):
            s.update(status="held", hold=r.get("state", "unknown"))
            self.tick("held")
            return
        res = json.loads(Path(spec["output"]).read_text(encoding="utf-8"))
        if step == "notebook":
            s.update(verdict=res.get("verdict"), comment=res.get("overall", "").strip(),
                     afterDeadline=job["afterDeadline"], status="graded")
            a = self.assignment(s["assignment"])
            if a.get("essayPack") and res.get("verdict") == "Đạt" and not job["afterDeadline"]:
                s["status"] = "essay_new"  # notebook passed on time → grade the essay next cycle
            self.tick("graded")
        else:
            s.update(essayResult=res, status="graded_essay")
            self.tick("graded_essay")

    # ---------------- publish
    def auto_publish(self):
        """autoPublish, or autoPublishFrom (DD/MM/YYYY, Vietnam time) once that day has come."""
        if self.cfg.get("autoPublish"):
            return True
        start = parse_vn_time(self.cfg.get("autoPublishFrom", "") + " 00:00:00") if self.cfg.get("autoPublishFrom") else None
        return bool(start and now() >= start)

    def publish(self, approve):
        for k, s in self.state.get("subs", {}).items():
            retry = (s["status"] == "held" and (s.get("approved") or approve == "all" or k in approve)
                     and s.get("hold") in ("tracker_cell_not_found", "status_prefix_not_ready"))
            if s["status"] != "graded" and not retry:
                continue
            if not (retry or self.auto_publish() or approve == "all" or k in approve):
                self.tick("awaiting_review")
                continue
            s["approved"] = True  # approval sticks: a held item is retried each cycle until its cell is ready
            tr = self.tracker(s["className"])
            col, _ = tr.column(s["assignment"])
            row = tr.row_of(s["student"])
            if not col or not row:
                s.update(status="held", hold="tracker_cell_not_found")
                self.tick("held")
                continue
            a1 = f"{col}{row}"
            cur = tr.cell(a1)
            if cur.startswith("⛔") or MARK not in cur:
                s.update(status="held", hold="status_prefix_not_ready", cell=a1)
                self.tick("held")
                continue
            prefix, existing = cur.split(MARK, 1)
            existing = existing.strip()
            if existing and existing != s.get("publishedComment"):
                s.update(status="held", hold="teacher_comment_exists", cell=a1)
                self.tick("held")
                continue
            new = prefix.rstrip() + "\n\n" + MARK + "\n" + s["comment"]
            tr.write(a1, new)
            if tr.cell(a1) != new:
                s.update(status="held", hold="readback_mismatch", cell=a1)
                self.tick("held")
                continue
            s.update(status="published", cell=a1, publishedComment=s["comment"], publishedAt=now().isoformat())
            self.tick("published")

    # ---------------- review list (encrypted with the state; read by the teacher's session)
    def review(self):
        items = [{"key": k, **{f: s.get(f) for f in ("assignment", "className", "student", "submittedAt", "verdict",
                                                        "comment", "afterDeadline", "status", "hold", "cell")}}
                 for k, s in self.state.get("subs", {}).items() if s["status"] in ("graded", "held", "graded_essay")]
        save_json(STATE_DIR / "review.json", {"at": now().isoformat(), "items": items})


def main():
    from gapi import Google
    mode = os.environ.get("MODE", "cycle")
    cfg = load_json(BUNDLE / "config.json", None)
    if not cfg:
        raise SystemExit("bundle config missing")
    state = load_json(STATE_DIR / "state.json", {"subs": {}, "batches": {}})
    g = Google(json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]))
    run = Runner(g, cfg, state)
    approve = os.environ.get("APPROVE", "").strip()
    approve = "all" if approve == "all" else {x.strip() for x in approve.split(",") if x.strip()}
    try:
        if mode in ("cycle",):
            run.collect()
            run.scan()
            run.submit()
        if mode in ("cycle", "publish"):
            run.publish(approve)
        if mode == "audit":
            run.scan()
    finally:
        save_json(STATE_DIR / "state.json", state)
        run.review()
        line = " · ".join(f"{k}={v}" for k, v in sorted(run.counts.items())) or "no changes"
        print("WRITING:", line)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
                f.write(f"Writing runner ({mode}): {line}\n")


if __name__ == "__main__":
    main()
