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
MAX_TRIES = 2           # attempts per submission (download/convert or grading) before the fallback message
GRACE_HOURS = 3         # how long the status system gets to mark a submission before the runner writes the status
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


def form_columns(header):
    """Form tabs differ per week: find notebook photo/PDF columns, the merged PDF and typed essays by header text."""
    H = [unicodedata.normalize("NFC", str(x or "")).upper() for x in header]
    merged = next((i for i, x in enumerate(H) if "PDF ĐÃ GHÉP" in x), None)
    status = next((i for i, x in enumerate(H) if "TRẠNG THÁI GHÉP" in x), None)
    photos = [i for i, x in enumerate(H) if i > 2 and i != merged and "TRẠNG THÁI" not in x and "BÀI VIẾT" not in x
              and any(k in x for k in ("ẢNH", "FILE SCAN", "PDF", "VỞ", "DÀN Ý"))]
    essays = [i for i, x in enumerate(H) if x.startswith("BÀI VIẾT")]
    return {"merged": merged, "status": status, "photos": photos, "essays": essays,
            "essayNames": {i: str(header[i]).strip() for i in essays}}


def form_files(row, cols):
    """All notebook files of one form row. The auto-merged PDF is used only when it holds every uploaded image."""
    singles = []
    for i in cols["photos"]:
        for u in re.split(r"[,\s]+", row[i] if i < len(row) else ""):
            f = file_id(u)
            if f and f not in singles:
                singles.append(f)
    m = cols["merged"]
    merged = file_id(row[m]) if m is not None and m < len(row) else None
    st = row[cols["status"]] if cols["status"] is not None and cols["status"] < len(row) else ""
    k = re.search(r"(\d+)\s*ẢNH", unicodedata.normalize("NFC", str(st)).upper())
    if merged and "HOÀN TẤT" in unicodedata.normalize("NFC", str(st)).upper() and k and int(k.group(1)) >= len(singles):
        return [merged]
    return singles or ([merged] if merged else [])


def scans_text(resp):
    return "".join(b.get("text", "") for b in resp["content"] if b.get("type") == "text")


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
        m = re.match(r"(.*-)W?0*(\d+)$", code)
        pat = (r"Mã:\s*" + re.escape(m.group(1)) + r"W?0*" + m.group(2) + r"\b") if m else (r"Mã:\s*" + re.escape(code) + r"\b")
        for i, v in enumerate(self.header()):
            if re.search(pat, str(v)):
                m = re.search(r"Hạn:[^\n]*?(\d{2}/\d{2}/\d{4})", str(v))
                deadline = parse_vn_time(m.group(1) + " 23:59:59") if m else None
                return col_letter(i), deadline
        return None, None

    def rows(self):
        if self._names is None:
            vals = self.g.values(self.id, f"'{self.tab}'!B1:B200")
            # the name is the first line; staff sometimes add notes below it ("new 31/10/2026")
            self._names, self._dups = {}, set()
            for n, r in enumerate(vals):
                if r and r[0].strip():
                    k = norm(r[0].strip().split("\n")[0])
                    if k in self._names:
                        self._dups.add(k)
                    self._names[k] = n + 1
        return self._names

    def row_of(self, name):
        """Exact name first; otherwise a unique match ignoring diacritics (form typos like CỒNG ↔ CÔNG)."""
        rows = self.rows()
        if name in self._dups:
            return None  # two students with the same name: never guess
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

    def drop_excluded(self):
        """Classes the teacher took off the list (finished / closed) are never read, graded or written."""
        for c in self.cfg.get("excludeClasses", []):
            self.cfg["classes"].pop(c, None)

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
                if name not in self.cfg["classes"] and name not in self.cfg.get("excludeClasses", []):
                    self.cfg["classes"][name] = f["id"]
                    found += 1
        if found:
            self.tick("classes_discovered", found)

    def class_of(self, raw):
        """'IELTS 50', 'ielts50', 'Lớp IELTS 50 ' … → the configured class key."""
        m = re.search(r"(IELTS|FIGHTER)\s*0*(\d+)", unicodedata.normalize("NFC", str(raw or "")).upper())
        return f"{m.group(1)} {int(m.group(2))}" if m else str(raw or "").strip()

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
        done = self.state.setdefault("resetDone", [])
        for code in self.cfg.get("resetGraded", []):   # pack corrected → unpublished results of that week are regraded once
            if code in done:
                continue
            for s in subs.values():
                if s["assignment"] == code and s["status"] in ("graded", "held"):
                    s.update(status="new", verdict=None, comment=None, tries=0)
                    self.tick("reset_for_new_pack")
            done.append(code)
        for key in self.cfg.get("resetKeys", []):   # our own failure (not a resubmission): grade that work properly once
            sub = subs.get(key)
            if sub and key not in done:
                sub.update(status="new", tries=0, fallback=None, verdict=None)
                done.append(key)
                self.tick("reset_after_system_fix")
        for a in self.cfg["assignments"]:
            if not a.get("enabled", True):  # every week stays open: late work must still get its notebook check
                continue
            table = self.g.values(self.cfg["formSheet"], f"'{a['formTab']}'!A1:Z2000")
            if not table:
                continue
            cols = form_columns(table[0])
            grouped = {}
            for n, r in enumerate(table[1:], start=2):
                r = r + [""] * (len(table[0]) + 2 - len(r))
                cls, name = self.class_of(r[2]), norm(r[1])
                if not name or cls not in self.cfg["classes"] or (a["classes"] != "*" and cls not in a["classes"]):
                    continue
                files = form_files(r, cols)
                if not files:
                    continue
                grouped.setdefault((cls, name), []).append({"row": n, "time": r[0], "fileId": files[0], "extra": files[1:],
                                                            "essays": {cols["essayNames"][i]: r[i].strip() for i in cols["essays"]
                                                                       if r[i].strip()}})
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
                waiting = old and old.get("status") in ("no_tracker_column", "not_in_roster", "ambiguous_name")
                essays = {}
                for it in items:          # latest typed essay of each task wins
                    essays.update(it.get("essays") or {})
                if old and old.get("status") == "skipped":   # history stays history, even if its file list is re-read
                    old.update(sig=sig, files=files, essays=essays)
                    continue
                if (old and old.get("sig") != sig and old.get("status") in ("published", "graded", "held")
                        and not self.cfg.get("rereadFix", {}).get(key)):
                    # Cô 09/11: once a result is given, a later resubmission is NOT graded again
                    old["resubmittedAfterResult"] = items[-1]["time"]
                    self.tick("resubmission_not_regraded")
                    continue
                if old and old.get("sig") == sig and not waiting:
                    if essays and not old.get("essays"):
                        old["essays"] = essays
                    continue
                if old and old.get("status") == "published":
                    self.tick("changed_after_publish")
                status = "new"
                tr = self.tracker(cls)
                first = not old or waiting
                if not tr.column(a["code"])[0]:
                    status = "no_tracker_column"   # class tracker has no column for this week: nothing to write to
                elif tr.row_of(name) is None:
                    # removed from the class list (moved class / left): not graded, no API call (Cô's rule)
                    status = "ambiguous_name" if name in tr._dups else "not_in_roster"
                elif first and not self.state.get("baselined", {}).get(a["code"]) or (waiting and old.get("sig") == sig):
                    # first sight: work already commented by the old pipeline, or weeks long past, are history
                    if self.too_old(cls, a["code"]) or self.existing_comment(cls, a["code"], name):
                        status = "skipped"
                if waiting and old.get("status") == status:
                    continue
                subs[key] = {"assignment": a["code"], "className": cls, "student": name, "files": files, "essays": essays,
                             "rows": [i["row"] for i in items], "submittedAt": items[-1]["time"],
                             "firstAt": items[0]["time"], "sig": sig, "status": status, "at": now().isoformat()}
                self.tick(status)
            self.state.setdefault("baselined", {})[a["code"]] = True
        for s in subs.values():   # notebook passed on time before this week's essay pack existed → grade its essays now
            a = next((x for x in self.cfg["assignments"] if x["code"] == s["assignment"]), {})
            if (a.get("essayPack") and s["status"] in ("graded", "published") and s.get("verdict") == "Đạt"
                    and s.get("afterDeadline") is False and s.get("essays") and not s.get("essayResult")
                    and not s.get("essayTried")):
                s.update(status="essay_new", essayTried=True)
                self.tick("essay_new")
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
        d = WORK / h(key + step + str(sub.get("tries", 0)), 20)
        d.mkdir(parents=True, exist_ok=True)
        paths, pages, seen = [], 0, set()
        for i, f in enumerate(sub["files"], 1):
            done = sorted(d.glob(f"file-{i:02d}*"))
            if not done:
                data = self.g.download(f)
                digest = h(hashlib.sha256(data).hexdigest())
                if digest in seen:          # the same file uploaded into two form boxes
                    continue
                seen.add(digest)
                if data[:4] != b"%PDF":     # Form uploads may be images (iPhone photos arrive as HEIC)
                    (d / f"file-{i:02d}.jpg").write_bytes(to_jpeg(data))
                elif len(data) > 12_000_000:   # very large scans: send readable page images instead of the raw PDF
                    doc = fitz.open(stream=data, filetype="pdf")
                    for j, pg in enumerate(doc, 1):
                        pix = pg.get_pixmap(dpi=110)
                        (d / f"file-{i:02d}-p{j:03d}.jpg").write_bytes(to_jpeg(pix.tobytes("png")))
                else:
                    (d / f"file-{i:02d}.pdf").write_bytes(data)
                done = sorted(d.glob(f"file-{i:02d}*"))
            for p in done:
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
        # sharp recheck of doubtful notebooks goes through the next BATCH (half price), never an immediate full-price call
        spec["autoEscalate"] = False
        if sub.get("sharp") == "yes":
            spec.update(profile="full", escalatedFrom="lite")
        elif sub.get("sharp") == "done":
            spec["acceptDoubts"] = True
        if step != "notebook" and deadline:
            spec["deadline"] = deadline.strftime("%d/%m/%Y %H:%M:%S")
        return spec, job

    # ---------------- batch submit / collect
    def submit(self):
        for s in self.state.get("subs", {}).values():  # retry download/convert failures a few times
            if s["status"] == "error" and str(s.get("error", "")).startswith("prepare:"):
                if s.get("tries", 0) < MAX_TRIES - 1:
                    s["tries"] = s.get("tries", 0) + 1
                    s["status"] = s.get("errStep") == "essay" and "essay_new" or "new"
                elif s.get("errStep") != "essay":
                    self.fallback(s, "file")
        todo = [(k, s) for k, s in self.state.get("subs", {}).items() if s["status"] in ("new", "essay_new")]
        if not todo:
            return
        reqs, mapping = [], {}
        base = self.cfg.get("model", cw.DEFAULT_MODEL)
        for k, s in todo:
            step = "essay" if s["status"] == "essay_new" else "notebook"
            if step == "essay":
                import essays
                if not s.get("essays"):   # nothing typed: the notebook result alone is published
                    s["status"] = "graded"
                    continue
                cid = h(k + step + s["sig"] + str(s.get("tries", 0)), 40)
                reqs.append({"custom_id": cid, "params": essays.request(self.assignment(s["assignment"]), s)})
                mapping[cid] = {"key": k, "step": step, "model": essays.MODEL}
                continue
            # last attempt after repeated failures goes to the stronger model (rare, so cost stays low)
            model = (self.cfg.get("escalationModel") or base) if s.get("tries", 0) >= MAX_TRIES - 1 else base
            try:
                spec, _ = self.prepare(k, s, step)
                try:
                    params, _ = cw.build_params(spec, model, 24000, 0)
                except RuntimeError as e:
                    if "TOO_LARGE" not in str(e) or s.get("sharp") != "yes":
                        raise
                    s["sharp"] = "done"          # too many pages for a sharp request: accept the readable result
                    spec, _ = self.prepare(k, s, step)
                    params, _ = cw.build_params(spec, model, 24000, 0)
                if s.get("sharp") == "yes":
                    s["sharp"] = "done"
            except Exception as e:
                s.update(status="error", error=f"prepare:{type(e).__name__}"[:120], errStep=step)
                self.tick("error")
                continue
            cid = h(k + step + s["sig"], 40)
            reqs.append({"custom_id": cid, "params": params})
            mapping[cid] = {"key": k, "step": step, "model": model}
        if not reqs:
            return
        b = cw.client().messages.batches.create(requests=reqs)
        self.state.setdefault("batches", {})[b.id] = {"at": now().isoformat(), "map": mapping, "model": base}
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
                if m["step"] == "notebook" and item.custom_id != h(k + "notebook" + s["sig"], 40):
                    self.tick("stale_result_ignored")   # files changed after submission: the newer files are graded instead
                    continue
                if item.result.type != "succeeded":
                    s.update(status="new" if m["step"] == "notebook" else "essay_new")  # resubmit next cycle
                    self.tick("batch_retry")
                    continue
                resp = item.result.message.model_dump()
                mdl = m.get("model", info["model"])
                c = cw.cost_usd(mdl, resp["usage"], batch=True)
                if m["step"] == "essay":
                    import essays
                    cw.ledger({"at": cw.now_iso(), "category": f"{s['className']} · Bài viết · {s['assignment'].split('-')[-1]}",
                               "step": "essay-batch", "model": mdl, "usage": resp["usage"], "usd": c, "vnd": round(c * cw.USD_VND)})
                    try:
                        res = json.loads(scans_text(resp))
                        s.update(essayResult=essays.checks(self.assignment(s["assignment"]), s, res), status="graded")
                        self.tick("graded_essay")
                    except Exception:
                        s["tries"] = s.get("tries", 0) + 1
                        s["status"] = "essay_new" if s["tries"] < MAX_TRIES else "graded"   # never block the notebook result
                        self.tick("essay_retry")
                    continue
                spec, job = self.prepare(k, s, m["step"])
                cw.ledger({"at": cw.now_iso(), "category": spec["category"], "step": "grade-batch",
                           "model": mdl, "usage": resp["usage"], "usd": c, "vnd": round(c * cw.USD_VND)})
                try:
                    r = cw.process(spec, mdl, 24000, 0, 1, cl=cl, raw_override=resp, batch=True)
                except Exception as e:   # one bad item never stops the class run
                    r = {"state": f"error:{type(e).__name__}"}
                self.finish(k, s, m["step"], r, spec, job)
            del batches[bid]

    def finish(self, k, s, step, r, spec, job):
        if r.get("state") == "needs_full_recheck" and step == "notebook" and not s.get("sharp"):
            s.update(status="new", sharp="yes")     # regraded once at full sharpness in the next batch
            self.tick("sharp_recheck_next_batch")
            return
        if r.get("state") not in ("written", "written_after_full_recheck"):
            if s.get("tries", 0) < MAX_TRIES - 1:   # regrade next cycle (last try on the stronger model)
                s.update(tries=s.get("tries", 0) + 1, status="essay_new" if step == "essay" else "new",
                         lastFail=r.get("state", "unknown"))
                self.tick("retry")
            elif step == "notebook":
                self.fallback(s, "unclear")
            else:
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

    def fallback(self, s, why):
        """Every submitting student gets a result: when the file cannot be opened or the pages cannot be read after
        all retries, the student is told exactly what to resend (reported in the review list)."""
        t = parse_vn_time(s["submittedAt"])
        d = t.strftime("%d/%m/%Y") if t else ""
        s["comment"] = (f"Cô chưa mở được file em nộp ngày {d}. Em chụp lại vở rõ nét (ảnh JPG hoặc PDF), đủ các trang "
                        f"và nộp lại giúp Cô nhé." if why == "file" else
                        f"Cô đã nhận vở em nộp ngày {d} nhưng ảnh một số trang chưa đủ rõ để Cô kiểm tra hết. "
                        f"Em chụp lại rõ nét, đủ trang và nộp lại giúp Cô nhé.")
        _, deadline = self.tracker(s["className"]).column(s["assignment"])
        s.update(status="graded", verdict="Chưa đủ dữ liệu để kết luận", fallback=why,
                 afterDeadline=bool(t and deadline and t > deadline))
        self.tick("fallback")

    # ---------------- publish
    def auto_publish(self):
        """autoPublish, or autoPublishFrom (DD/MM/YYYY, Vietnam time) once that day has come."""
        if self.cfg.get("autoPublish"):
            return True
        start = parse_vn_time(self.cfg.get("autoPublishFrom", "") + " 00:00:00") if self.cfg.get("autoPublishFrom") else None
        return bool(start and now() >= start)

    def publish(self, approve):
        for tr in self.trackers.values():   # columns move when new weeks are inserted: never write with an old header
            tr._hdr = None
            tr._grid = None
        self.revert_appended()
        for k, s in self.state.get("subs", {}).items():
            retry = (s["status"] == "held" and (s.get("approved") or approve == "all" or k in approve or self.auto_publish())
                     and s.get("hold") in ("tracker_cell_not_found", "status_prefix_not_ready", "readback_mismatch"))
            if s["status"] != "graded" and not retry:
                continue
            manual = f"{s['className']}|{s['assignment']}" in self.cfg.get("manualReview", [])
            if not (retry or (self.auto_publish() and not manual) or approve == "all" or k in approve):
                self.tick("awaiting_review")
                continue
            s["approved"] = True  # approval sticks: a held item is retried each cycle until its cell is ready
            tr = self.tracker(s["className"])
            col, _ = tr.column(s["assignment"])
            row = tr.row_of(s["student"])
            if not row:   # no longer on the class list (moved class / left): not published, Cô's rule
                s.update(status="not_in_roster", hold=None)
                self.tick("not_in_roster")
                continue
            if not col:
                s.update(status="held", hold="tracker_cell_not_found")
                self.tick("held")
                continue
            a1 = f"{col}{row}"
            if not re.search(r"Mã:\s*IELTS-WRITING-W?0*" + s["assignment"].split("W")[-1].lstrip("0") + r"\b",
                             tr.cell(f"{col}4")):
                s.update(status="held", hold="readback_mismatch")   # header moved: retried next cycle
                self.tick("held")
                continue
            cur = tr.cell(a1)
            sub_t = parse_vn_time(s["submittedAt"])
            if cur.startswith("⛔") or MARK not in cur:
                if not sub_t or now() < sub_t + dt.timedelta(hours=GRACE_HOURS):
                    s.update(status="held", hold="status_prefix_not_ready", cell=a1)
                    self.tick("held")
                    continue
                # the status system never marked this submission: write the status line in its own format
                _, deadline = tr.column(s["assignment"])
                late = bool(deadline and sub_t > deadline)
                prefix = ("⚠️ ĐÃ NỘP MUỘN" if late else "✅ ĐÃ NỘP") + "\n" + sub_t.strftime("%d/%m/%Y %H:%M")
                if MARK in cur:
                    existing = cur.split(MARK, 1)[1].strip()
                else:  # a note typed without the marker is kept as a teacher comment
                    existing = "" if cur.startswith("⛔") else cur.strip()
                self.tick("status_written")
            else:
                prefix, existing = cur.split(MARK, 1)
                existing = existing.strip()
            comment, prev = s["comment"], s.get("publishedBlock") or s.get("publishedComment")
            if s.get("essayResult"):
                import essays
                comment = comment.rstrip() + "\n\n" + essays.summary(s["essayResult"])
            tag = f"【Lần nộp {sub_t.strftime('%d/%m/%Y') if sub_t else ''}】\n"
            if not existing or existing == prev:
                body = blk = comment
            elif prev and prev in existing:   # regrade of a resubmission: replace only our own earlier result
                blk = (tag + comment) if prev.startswith("【") else comment
                body = existing.replace(prev, blk)
            else:   # a result was already given here (Cô 09/11: no second grading) → leave the cell as it is
                s.update(status="skipped", hold="result_already_given", cell=a1)
                self.tick("result_already_given")
                continue
            new = prefix.rstrip() + "\n\n" + MARK + "\n" + body
            tr.write(a1, new)
            if tr.cell(a1) != new:
                s.update(status="held", hold="readback_mismatch", cell=a1)
                self.tick("held")
                continue
            s.update(status="published", cell=a1, publishedComment=comment, publishedBlock=blk,
                     publishedAt=now().isoformat(), hold=None)
            self.tick("published")

    def revert_appended(self):
        if self.state.get("revertAppendedDone"):
            return
        for k, s in self.state.get("subs", {}).items():
            blk = s.get("publishedBlock") or ""
            if s["status"] != "published" or not blk.startswith("【Lần nộp"):
                continue
            tr = self.tracker(s["className"])
            cur = tr.cell(s["cell"])
            if blk in cur:
                new = cur.replace("\n\n" + blk, "").replace(blk, "").rstrip()
                tr.write(s["cell"], new)
                self.tick("reverted_duplicate")
            s.update(status="skipped", hold="result_already_given")
        self.state["revertAppendedDone"] = True

    # ---------------- shadow comparison (no tracker writes, no status changes)
    def shadow(self, model, think="off", limit=120):
        """Regrade notebooks already graded by the main model with a cheaper setting and record agreement."""
        import concurrent.futures as cf
        sh = self.state.setdefault("shadow", {})
        todo = [(k, s) for k, s in self.state.get("subs", {}).items()
                if s["status"] in ("graded", "published") and s.get("verdict") in ("Đạt", "Cần bổ sung")
                and not s.get("fallback") and f"{k}|{model}|{think}" not in sh][:limit]
        cl = cw.client()

        def one(item):
            k, s = item
            spec, _ = self.prepare(k, s, "notebook")
            spec["output"] = str(Path(spec["output"]).with_name(f"shadow-{h(model + think, 6)}.json"))
            spec["category"] = "THỬ SO SÁNH · " + spec["category"]
            r = cw.process(spec, model, 8000, think, 1, cl=cl)
            if r.get("state") not in ("written", "written_after_full_recheck"):
                return k, {"verdict": None, "state": r.get("state")}
            res = json.loads(Path(spec["output"]).read_text(encoding="utf-8"))
            return k, {"verdict": res.get("verdict"), "overall": res.get("overall", "")}

        with cf.ThreadPoolExecutor(6) as ex:
            for k, res in ex.map(one, todo):
                s = self.state["subs"][k]
                sh[f"{k}|{model}|{think}"] = {**res, "main": s.get("verdict"), "at": now().isoformat()}
                self.tick("shadow_same" if res.get("verdict") == s.get("verdict") else "shadow_diff")

    # ---------------- review list (encrypted with the state; read by the teacher's session)
    def review(self):
        items = [{"key": k, **{f: s.get(f) for f in ("assignment", "className", "student", "submittedAt", "verdict", "fallback",
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
    run.drop_excluded()
    approve = os.environ.get("APPROVE", "").strip()
    approve = "all" if approve == "all" else {x.strip() for x in approve.split(",") if x.strip()}
    try:
        if mode in ("cycle",):
            run.collect()
            run.scan()
            run.submit()
            try:   # paper tests in the scan folder (new uploads only)
                import scans
                scans.run(run)
            except Exception as e:
                run.tick(f"scan_failed_{type(e).__name__}")
        if mode == "fighter":   # own workflow (fighter_notebooks.yml, every 20 min) with its own state branch
            try:   # Fighter vocabulary notebooks (Haiku reads, code scores, written straight to the tracker)
                from fighter import notebook as fnb
                run.discover_classes()
                fnb.run(run)
            except Exception as e:
                run.tick(f"fighter_nb_failed_{type(e).__name__}")
        if mode in ("cycle", "publish"):
            run.publish(approve)
            if run.auto_publish():
                try:   # parent dashboard: bài chữa + kết quả vở (only what is already on the tracker)
                    import dashboard
                    dashboard.Dashboard(run).run()
                except Exception as e:
                    run.tick(f"dash_failed_{type(e).__name__}")
        if mode == "cycle" and run.auto_publish():
            try:   # Cô 11/11: Zalo picture per class & week as soon as the class is complete (08:00–20:00)
                import zalo
                zalo.make(run)
            except Exception as e:
                run.tick(f"zalo_failed_{type(e).__name__}")
        if mode in ("cycle", "report"):
            try:   # digest for Cô (counts only) as a GitHub issue comment → e-mail
                import report
                report.maybe_send(run, load_json(STATE_DIR / "scans.json", {}), force=(mode == "report"))
            except Exception as e:
                run.tick(f"report_failed_{type(e).__name__}")
        if mode == "audit":
            run.scan()
        if mode == "scan":   # paper tests from the scan folder (trial: APPROVE = file IDs to grade now)
            import scans
            run.discover_classes()
            only = {x.strip() for x in os.environ.get("APPROVE", "").split(",") if x.strip()} or None
            scans.run(run, only=only)
        if mode == "shadow":
            run.shadow(os.environ.get("SHADOW_MODEL") or "claude-haiku-5-5", os.environ.get("SHADOW_THINK") or "off")
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
