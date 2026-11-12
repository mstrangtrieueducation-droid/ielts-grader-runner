"""Parent dashboard publication: graded notebooks and essays → the class tracker's private store tabs, which the class
Apps Script backend serves to the parent page (same tables and checks as the earlier Codex flow).

  _WRITING_NOTEBOOK_ASSIGNMENTS_V1  one config row per class + week (added only if the week has none)
  _WRITING_NOTEBOOKS_V1             one published notebook review per submission
  _WRITING_FEEDBACK_V1              one published essay review (bài chữa) per essay

Only results already published to the tracker are sent, each once (sub["dash"]). Nothing is regraded. The list of
weeks/tasks per class is also written to dashboard-assignments.json (public metadata only: class, week, task titles)
so the parent page can list weeks that are not in its built-in list."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import unicodedata

from run_writing import BUNDLE, STATE_DIR, h, load_json, now, parse_vn_time, save_json

NB_CONFIG = "_WRITING_NOTEBOOK_ASSIGNMENTS_V1"
NB_STORE = "_WRITING_NOTEBOOKS_V1"
FEEDBACK = "_WRITING_FEEDBACK_V1"
NB_CONFIG_HEADERS = ['class', 'assignment', 'lesson', 'homework_mode', 'source_spreadsheet_id', 'source_sheet_name',
                     'timestamp_column', 'name_column', 'class_column', 'notebook_column', 'notebook_header', 'config_json',
                     'config_sha256', 'enabled']
NB_STORE_HEADERS = ['record_id', 'student_key', 'class', 'assignment', 'submitted_at', 'notebook_job_id', 'state',
                    'result_json', 'published_at', 'result_sha256', 'receipt_id', 'publication']
FEEDBACK_HEADERS = ['receipt_id', 'student_key', 'class', 'assignment', 'task', 'submitted_at', 'source_sha256',
                    'prompt_sha256', 'publication', 'result_json', 'published_at', 'result_sha256']
WS = "\u0009-\u000d\u001c- \u0085   -     　"
MANIFEST = STATE_DIR / "dashboard-assignments.json"


def sha(v):
    return hashlib.sha256(v.encode("utf-8") if isinstance(v, str) else v).hexdigest()


def canonical(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def student_key(name):
    """Same key as the class backend (ieltsWritingNameKey_): no diacritics, đ→d, lower case, single spaces."""
    raw = re.sub(f"^[{WS}]+|[{WS}]+$", "", str(name or ""))
    lines = [x for x in (re.sub(f"^[{WS}]+|[{WS}]+$", "", l) for l in re.split(r"\r\n|[\n\r\v\f\u001c-\u001e\u0085  ]", raw)) if x]
    note = re.compile(r"^(?:writing[ \t]+only(?:[ \t]*,[ \t]*new[ \t]+\d{1,2}/\d{1,2}/\d{4})?|new[ \t]+\d{1,2}/\d{1,2}/\d{4})$", re.I)
    if len(lines) > 1 and all(note.match(l) for l in lines[1:]):
        raw = lines[0]
    t = "".join(c for c in unicodedata.normalize("NFD", raw) if not unicodedata.combining(c))
    t = re.sub("[đĐ]", "d", t).lower()
    return re.sub(f"[{WS}]+", " ", t).strip(" ")


def iso_vn(text):
    t = parse_vn_time(text)
    return t.astimezone(dt.timezone(dt.timedelta(hours=7))).strftime("%Y-%m-%dT%H:%M:%S+07:00") if t else ""


def utc_now():
    """Publication time as the class backend compares it: plain string order, so always Vietnam time like earlier rows."""
    return now().isoformat(timespec="microseconds")


def js_json(d):
    """JSON.stringify of a plain object (insertion order, no spaces, non-ASCII kept)."""
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


def link_ids(cell):
    out = []
    for u in re.findall(r"https://[^\s,]+", str(cell or "")):
        m = re.search(r"/d/([A-Za-z0-9_-]+)", u) or re.search(r"[?&]id=([A-Za-z0-9_-]+)", u)
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def supplement_columns(header, notebook_col, merged_col):
    out = []
    for i, v in enumerate(header):
        t = re.sub(r"\s+", " ", re.sub("[\u0300-\u036f]", "", unicodedata.normalize("NFD", str(v))).lower()).strip()
        if i not in (notebook_col, merged_col) and re.match(r"^(?:anh bo sung|anh (?:chup )?vo(?:\s|$)|supplement(?:al|ary)? (?:notebook )?(?:images?|photos?|files?))", t):
            out.append(i)
    return out


def latest_receipt(grid, cls, roster_name, code, sheet, spreadsheet, nb_col):
    """The class backend's view of the newest notebook receipt (ieltsNotebookLatest_): time, receipt id, file ids."""
    head = grid[0]
    merged = next((i for i, v in enumerate(head) if "PDF ĐÃ GHÉP TỰ ĐỘNG" in str(v)), -1)
    sup = supplement_columns(head, nb_col, merged)
    key, ck = student_key(roster_name), student_key(cls)
    rows = []
    for r in grid[1:]:
        r = list(r) + [""] * (len(head) + 1 - len(r))
        if student_key(r[2]) != ck or student_key(r[1]) != key:
            continue
        t = iso_vn(r[0])
        if not t:
            return None
        ids = set(link_ids(r[nb_col]))
        if merged >= 0:
            ids |= set(link_ids(r[merged]))
        for c in sup:
            ids |= set(link_ids(r[c]))
        rows.append((t, sorted(ids)))
    if not rows:
        return None
    t = max(x[0] for x in rows)
    latest = [x for x in rows if x[0] == t]
    if len({json.dumps(x[1]) for x in latest}) > 1 or not latest[0][1]:
        return None
    ident = {"assignmentCode": code, "className": cls, "component": "notebook", "sheetName": sheet,
             "spreadsheetId": spreadsheet, "studentKey": key, "submittedAt": t}
    return {"submittedAt": t, "receiptId": sha(js_json(ident)), "fileIds": latest[0][1]}


NB_STATE = {
    "Đạt": ("notebook_complete", "Đạt yêu cầu"),
    "Cần bổ sung": ("awaiting_notebook_completion", "Cần bổ sung vở"),
}


def notebook_record(cls, s, roster_name, mode, pack_sha, ref_sha, receipt=None, files=None):
    verdict = s.get("verdict") or ""
    state, title = NB_STATE.get(verdict, ("needs_readable_copy", "Cần ảnh rõ hơn"))
    submitted = receipt["submittedAt"] if receipt else iso_vn(s.get("submittedAt", ""))
    receipt_id = receipt["receiptId"] if receipt else sha(canonical({"component": "notebook", "className": cls,
                 "assignmentCode": s["assignment"], "studentKey": student_key(roster_name), "submittedAt": submitted}))
    overall = (s.get("comment") or "").strip()
    locked = state == "awaiting_notebook_completion" and mode == "notebook_and_writing"
    rec = {"schemaVersion": 1, "kind": "review", "className": cls, "assignmentCode": s["assignment"],
           "studentName": roster_name, "submittedAt": submitted, "checkedAt": s.get("publishedAt") or s.get("at") or "",
           "state": state, "displayTitle": title,
           "reason": overall if state != "notebook_complete" else overall,
           "overall": overall, "nextSteps": [], "issues": [],
           "handwriting": {"legibility": "readable" if state != "needs_readable_copy" else "unclear",
                           "captureQuality": "clear" if state != "needs_readable_copy" else "unclear", "evidence": []},
           "binding": {"receiptId": receipt_id, "notebookJobId": sha(receipt_id + "|" + s.get("sig", "")),
                       "files": files if files is not None else [{"fileId": f} for f in s.get("files", [])],
                       "promptSha256": pack_sha, "referenceSha256": ref_sha},
           "essayGradingLocked": locked, "reviewMode": "quick_check", "sourceUrls": []}
    if locked:
        rec["reason"] = overall
    return rec


def essay_source(grid, cls, roster_name, label, sheet, spreadsheet, code, task):
    """The class backend's view of the newest typed essay (ieltsWritingLatestSource_): receipt id + checksum."""
    if not grid:
        return None
    head = [str(x).strip() for x in grid[0]]
    if label not in head:
        return None
    col = head.index(label)
    key, ck = student_key(roster_name), student_key(cls)
    rows = []
    for r in grid[1:]:
        r = list(r) + [""] * (len(head) + 1 - len(r))
        if student_key(r[2]) == ck and student_key(r[1]) == key:
            t = iso_vn(r[0])
            if not t:
                return None
            rows.append((t, str(r[col])))
    if not rows:
        return None
    t = max(x[0] for x in rows)
    latest = {sha(x[1]) for x in rows if x[0] == t}
    if len(latest) != 1:
        return None
    ident = {"assignmentCode": code, "className": cls, "sheetName": sheet, "spreadsheetId": spreadsheet,
             "studentKey": key, "submittedAt": t, "taskNumber": task}
    return {"submittedAt": t, "receiptId": sha(js_json(ident)), "sourceSha256": latest.pop(), "column": col,
            "numbered": bool(re.search(rf"Đề\s+{task}(?![0-9])", grid[0][col]))}


def essay_records(cls, s, roster_name, a, grid=None, spreadsheet=""):
    """One bài chữa per graded essay, in the parent page's review format."""
    res = s.get("essayResult") or {}
    meta = json.loads((BUNDLE / "packs" / a["essayPack"] / "meta.json").read_text(encoding="utf-8"))
    head_sha = sha((BUNDLE / "packs" / a["essayPack"] / "head.md").read_bytes())
    import essays as E
    by_de = {E.de_number(lbl, i): txt for i, (lbl, txt) in enumerate(sorted(s.get("essays", {}).items()))
             if str(E.de_number(lbl, i)) in meta["labels"]}
    submitted = iso_vn(s.get("submittedAt", ""))
    published = s.get("correctedAt") or s.get("publishedAt") or utc_now()   # Cô 12/11: a corrected bài chữa wins
    task1 = meta.get("task", 1) == 1
    names = {"vocab": "Từ vựng", "grammar": "Ngữ pháp", "coherence": "Mạch lạc"}
    out = []
    for e in res.get("essays", []):
        original = by_de.get(e["de"], "")
        if not original or not e.get("revisedText"):
            continue
        notes = []
        for n in e.get("annotations", []):
            at, anchors = original.find(n["quote"]), []
            if n["quote"] and at >= 0:
                anchors.append({"start": at, "end": at + len(n["quote"]), "quote": n["quote"]})
            body = n["explanation"].strip()
            if n.get("replacement"):
                body += "\n\n**Cách sửa:** " + n["replacement"].strip()
            notes.append({"label": names.get(n["group"], "Ghi chú") + (" · cần sửa" if n["kind"] == "error" else " · gợi ý"),
                          "title": n["label"], "severity": "serious" if n["kind"] == "error" else "minor",
                          "bodyMarkdown": body, "anchors": anchors})
        c = e["criteria"]
        band = e.get("_qa", {}).get("band")
        crit = [("TA" if task1 else "TR", "TA_TR"), ("CC", "CC"), ("LR", "LR"), ("GRA", "GRA")]
        bands = " · ".join(f"{k} {c[x]['band']}" for k, x in crit)
        detail = "\n\n".join(f"**{k} {c[x]['band']}** — {c[x]['reason'].strip()}\n**Để lên band cao hơn:** {c[x]['whyNotHigher'].strip()}"
                             for k, x in crit)
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", e["revisedText"].strip()) if p.strip()]
        label = next((lbl for i, lbl in enumerate(sorted(s.get("essays", {}))) if E.de_number(lbl, i) == e["de"]), "")
        src = essay_source(grid, cls, roster_name, label, a["formTab"], spreadsheet, a["code"], e["de"])
        if src:
            receipt, source_sha, submitted = src["receiptId"], src["sourceSha256"], src["submittedAt"]
        else:
            identity = {"assignmentCode": a["code"], "className": cls, "studentKey": student_key(roster_name),
                        "submittedAt": submitted, "taskNumber": e["de"]}
            receipt = sha(json.dumps(identity, ensure_ascii=False, separators=(",", ":")))
            source_sha = sha(original)
        rec = {"schemaVersion": 1, "resultId": "claude-" + h(receipt + head_sha, 24),
               "className": cls, "studentName": roster_name, "assignmentCode": a["code"], "taskNumber": e["de"],
               "originalEssay": original, "originalWordCount": e.get("_qa", {}).get("words") or len(original.split()),
               "overall": e["overall"].strip() + (f"\n\n**Band {band:.1f}** ({'điểm gốc theo tiêu chí: ' if (e.get('_qa', {}).get('words') or 0) < (150 if task1 else 250) else ''}{bands})\n{E.length_note(e, task1)}"
                                                  if band is not None else ""),
               "learningVerdict": f"Band {band:.1f}" if band is not None else "Đã chữa",
               "submittedAt": submitted,
               "publication": {"state": "published", "status": "published", "publishedAt": published, "autoReturn": True,
                               "teacherReviewRequired": False},
               "annotations": notes,
               "suggestedRevision": "\n\n".join(paragraphs), "suggestedRevisionParagraphs": paragraphs,
               "suggestedRevisionWordCount": len(" ".join(paragraphs).split()),
               "savedModelResult": True, "dataGrouping": detail, "appliedKnowledge": [], "nextSteps": [],
               "receiptId": receipt, "sourceSha256": source_sha, "promptSha256": head_sha,
               "provenance": {"promptSha256": head_sha, "contextSha256": head_sha, "grader": "claude-sonnet-5-5"}}
        raw = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
        out.append([receipt, student_key(roster_name), cls, a["code"], str(e["de"]), submitted, source_sha, head_sha,
                    "published", raw, utc_now(), sha(raw)])
        if src and src["numbered"]:
            CONFIG_CANDIDATES.append([cls, a["code"], str(e["de"]), spreadsheet, a["formTab"], "0", "1", "2",
                                      str(src["column"]), head_sha, head_sha, "TRUE"])
    return out


CONFIG_CANDIDATES = []
ESSAY_CONFIG = "_WRITING_ASSIGNMENTS_V1"
ESSAY_CONFIG_HEADERS = ['class', 'assignment', 'task', 'source_spreadsheet_id', 'source_sheet_name', 'timestamp_column',
                        'name_column', 'class_column', 'essay_column', 'criteria_sha256', 'context_sha256', 'enabled']
ESSAY_VERSION = "v3"   # v2 rows lost to v1 on publication-time order
NB_VERSION = "v3"   # v3: merged-PDF link read from the cell hyperlink   # v1 rows (09/11 evening) were bound to the wrong receipt; v2 republishes them once


class Dashboard:
    def __init__(self, runner):
        self.r, self.g = runner, runner.g
        self.tabs, self.forms, self.metas, self.known_versions = {}, {}, {}, {}

    def table(self, sid, tab, headers, create=True):
        """The store tab's rows; created hidden with its headers if missing. A header mismatch → never write."""
        key = (sid, tab)
        if key not in self.tabs:
            if tab not in self.g.sheet_titles(sid):
                if not create:
                    raise RuntimeError("STORE_ABSENT")
                self.g.add_hidden_sheet(sid, tab, headers)
            vals = self.g.values(sid, f"'{tab}'!A1:{chr(64 + len(headers))}3000")
            if not vals or [str(x) for x in vals[0][:len(headers)]] != headers:
                raise RuntimeError("STORE_SCHEMA_MISMATCH")
            self.tabs[key] = vals
        return self.tabs[key]

    def roster_name(self, tr, name):
        row = tr.row_of(name)
        if not row:
            return None
        v = self.g.values(tr.id, f"'{tr.tab}'!B{row}")
        return str(v[0][0]).split("\n")[0].strip() if v and v[0] else None

    def run(self):
        subs = self.r.state.get("subs", {})
        assignments = {a["code"]: a for a in self.r.cfg["assignments"]}
        todo = {}
        for k, s in subs.items():
            if s.get("status") != "published" or s.get("className") not in self.r.cfg["classes"]:
                continue
            if s.get("dashNb") in (NB_VERSION, "no_roster_name") and (s.get("dashEssay") == ESSAY_VERSION or not s.get("essayResult")):
                continue
            if s["assignment"] not in assignments or s.get("fallback"):
                continue
            todo.setdefault(s["className"], []).append((k, s))
        manifest = load_json(MANIFEST, {"schemaVersion": 1, "entries": []})
        if todo:
            self.scan_configs()
        seen = {(e["className"], e["assignmentCode"]) for e in manifest["entries"]}
        for cls, items in todo.items():
            try:
                self.publish_class(cls, items, assignments, manifest, seen)
            except Exception as e:  # one class never blocks the others
                self.r.tick("dash_class_failed")
                print("dashboard:", cls, type(e).__name__, str(e)[:80])
        # keep the lesson version of every published week current (a later edit of the lesson doc must not hide results)
        weeks = {(v["className"], v["assignment"]) for v in subs.values()
                 if v.get("dashNb") in (NB_VERSION, "v2") and v.get("className") in self.r.cfg["classes"] and v["assignment"] in assignments}
        if weeks and not self.known_versions:
            self.scan_configs()
        for cls, code in sorted(weeks):
            try:
                a = assignments[code]
                n = int(re.search(r"W0*(\d+)$", code).group(1))
                pack = BUNDLE / "packs" / a["pack"]
                pack_sha = sha((pack / "head.md").read_bytes())
                ref_sha = sha((pack / "meta.json").read_bytes()) if (pack / "meta.json").exists() else sha(code + pack_sha)
                self.config_for(cls, self.r.cfg["classes"][cls], a, n, pack_sha, ref_sha)
            except Exception:
                self.r.tick("dash_config_check_failed")
        save_json(MANIFEST, manifest)

    def form(self, tab):
        """Form tab display values; the merged-PDF column's hyperlinks are added as URLs (its cells only show a label)."""
        if tab not in self.forms:
            grid = self.g.values(self.r.cfg["formSheet"], f"'{tab}'!A1:Z2000")
            col = next((i for i, v in enumerate(grid[0] if grid else []) if "PDF ĐÃ GHÉP TỰ ĐỘNG" in str(v)), -1)
            if col >= 0:
                letter = chr(65 + col)
                try:
                    links = self.g.links(self.r.cfg["formSheet"], f"'{tab}'!{letter}1:{letter}2000")
                    for i, cells in enumerate(links):
                        if i and i < len(grid) and cells and cells[0]:
                            row = grid[i] + [""] * (col + 1 - len(grid[i]))
                            row[col] = (str(row[col]) + " " + " ".join(cells[0])).strip()
                            grid[i] = row
                except Exception:
                    self.r.tick("dash_form_links_failed")
            self.forms[tab] = grid
        return self.forms[tab]

    def file_meta(self, fid):
        if fid not in self.metas:
            try:
                m = self.g.meta(fid)
                self.metas[fid] = {"fileId": fid, "mimeType": m.get("mimeType", ""), "modifiedTime": m.get("modifiedTime", ""),
                                   "size": str(m.get("size", ""))}
            except Exception:
                self.metas[fid] = None
        return self.metas[fid]

    def source_versions(self, code):
        """The lesson document version the class backend checks: reuse a week's existing config from any class,
        else the lesson doc from the bundle (its current modifiedTime)."""
        doc = self.r.cfg.get("lessonDocs", {}).get(code)
        m = self.file_meta(doc) if doc else None
        if m and m["modifiedTime"]:
            return [{"fileId": doc, "modifiedTime": m["modifiedTime"]}]
        return self.refresh_versions(self.known_versions.get(code))

    def refresh_versions(self, versions):
        """Same lesson files, their current modifiedTime (the backend hides results when a lesson doc was edited later)."""
        if not versions:
            return None
        out = []
        for v in versions:
            m = self.file_meta(v.get("fileId", ""))
            if not m or not m["modifiedTime"]:
                return None
            out.append({"fileId": v["fileId"], "modifiedTime": m["modifiedTime"]})
        return out

    def scan_configs(self):
        """Existing notebook configs of every class: lesson versions per week (shared lessons)."""
        for cls, sid in self.r.cfg["classes"].items():
            try:
                rows = self.table(sid, NB_CONFIG, NB_CONFIG_HEADERS, create=False)
            except Exception:
                continue
            for r in rows[1:]:
                if len(r) < 14 or r[13] != "TRUE":
                    continue
                try:
                    d = json.loads(r[11])
                except ValueError:
                    continue
                sv = d.get("sourceVersions") or []
                if sv and not any(str(x.get("fileId", "")).startswith("claude-pack-") for x in sv) and r[1] not in self.known_versions:
                    if not d.get("claudeRunner"):
                        self.known_versions[r[1]] = sv

    def config_for(self, cls, sid, a, n, pack_sha, ref_sha):
        """This class's notebook config row for the week (created if missing; our own rows kept current)."""
        rows = self.table(sid, NB_CONFIG, NB_CONFIG_HEADERS)
        idx = next((i for i, r in enumerate(rows) if i and len(r) > 1 and r[0] == cls and r[1] == a["code"]), None)
        grid = self.form(a["formTab"])
        nb_col = 3
        header = str(grid[0][nb_col]).strip() if grid and len(grid[0]) > nb_col else ""
        if idx is not None:
            r = rows[idx] + [""] * (14 - len(rows[idx]))
            d = json.loads(r[11])
            sv = d.get("sourceVersions") or []
            ours = d.get("claudeRunner") or any(str(x.get("fileId", "")).startswith("claude-pack-") for x in sv)
            fresh = self.source_versions(a["code"]) if ours else self.refresh_versions(sv)
            if fresh and (fresh != sv or (ours and r[10] != header[:60])):
                d["sourceVersions"] = fresh
                if ours:
                    d["claudeRunner"] = True
                raw = canonical(d)
                r = r[:10] + [header[:60] if ours else r[10], raw, sha(raw), "TRUE"]
                self.g.set_row(sid, f"'{NB_CONFIG}'!A{idx + 1}:N{idx + 1}", r)
                rows[idx] = r
            return {"notebookColumn": int(r[9] or 3), "sheet": r[5], "spreadsheet": r[4],
                    "promptSha256": d.get("promptSha256"), "referenceSha256": d.get("referenceSha256")}
        sv = self.source_versions(a["code"]) or [{"fileId": "claude-pack-" + pack_sha[:16], "modifiedTime": "2026-11-09T00:00:00Z"}]
        d = {"claudeRunner": True, "notebookSourceResolveHyperlinks": True, "notebookSubmissionFormats": ["pdf", "image"],
             "preferredNotebookHeader": "PDF ĐÃ GHÉP TỰ ĐỘNG", "promptSha256": pack_sha, "referenceSha256": ref_sha,
             "schemaVersion": 1, "sourceUrls": [], "sourceVersions": sv}
        raw = canonical(d)
        row = [cls, a["code"], str(n), a.get("mode", "notebook_only"), self.r.cfg["formSheet"], a["formTab"],
               "0", "1", "2", str(nb_col), header[:60], raw, sha(raw), "TRUE"]
        self.g.append_rows(sid, NB_CONFIG, [row])
        rows.append(row)
        return {"notebookColumn": nb_col, "sheet": a["formTab"], "spreadsheet": self.r.cfg["formSheet"],
                "promptSha256": pack_sha, "referenceSha256": ref_sha}

    def publish_class(self, cls, items, assignments, manifest, seen):
        tr = self.r.tracker(cls)
        sid = tr.id
        self.table(sid, NB_STORE, NB_STORE_HEADERS)
        self.table(sid, FEEDBACK, FEEDBACK_HEADERS)
        nb_rows, fb_rows, done = [], [], []
        for k, s in items:
            a = assignments[s["assignment"]]
            n = int(re.search(r"W0*(\d+)$", a["code"]).group(1))
            pack = BUNDLE / "packs" / a["pack"]
            pack_sha = sha((pack / "head.md").read_bytes())
            ref_sha = sha((pack / "meta.json").read_bytes()) if (pack / "meta.json").exists() else sha(a["code"] + pack_sha)
            mode = a.get("mode", "notebook_only")
            name = self.roster_name(tr, s["student"])
            if not name:
                s["dashNb"] = "no_roster_name"
                continue
            if s.get("dashNb") != NB_VERSION:
                c = self.config_for(cls, sid, a, n, pack_sha, ref_sha)
                rc = latest_receipt(self.form(c["sheet"]), cls, name, a["code"], c["sheet"], c["spreadsheet"], c["notebookColumn"])
                files = [self.file_meta(f) for f in rc["fileIds"]] if rc else None
                if files and any(f is None for f in files):
                    files = None
                rec = notebook_record(cls, s, name, mode, c["promptSha256"], c["referenceSha256"],
                                      receipt=rc if files else None, files=files)
                raw = canonical(rec)
                nb_rows.append([sha(raw), student_key(name), cls, a["code"], rec["submittedAt"], rec["binding"]["notebookJobId"],
                                rec["state"], raw, utc_now(), sha(raw), rec["binding"]["receiptId"], "published"])
                s["dashNb"] = NB_VERSION
                self.r.tick("dash_nb_bound" if files else "dash_nb_unbound")
            tasks = []
            if s.get("essayResult") and a.get("essayPack") and s.get("dashEssay") != ESSAY_VERSION:
                rows = essay_records(cls, s, name, a, self.form(a["formTab"]), self.r.cfg["formSheet"])
                fb_rows += rows
                tasks = sorted({int(r[4]) for r in rows})
            done.append(s)
            if (cls, a["code"]) not in seen or tasks:
                self.add_manifest(manifest, seen, cls, a, n, tasks)
        if nb_rows:
            self.g.append_rows(sid, NB_STORE, nb_rows)
        if fb_rows:
            self.g.append_rows(sid, FEEDBACK, fb_rows)
        if CONFIG_CANDIDATES:   # freshness config per class/week/task, only where none exists (never a duplicate)
            rows = self.table(sid, ESSAY_CONFIG, ESSAY_CONFIG_HEADERS)
            have = {(r[0], r[1], r[2]) for r in rows[1:] if len(r) > 2}
            add = []
            for c in CONFIG_CANDIDATES:
                if c[0] == cls and (c[0], c[1], c[2]) not in have:
                    have.add((c[0], c[1], c[2]))
                    add.append(c)
            if add:
                self.g.append_rows(sid, ESSAY_CONFIG, add)
                rows += add
            CONFIG_CANDIDATES.clear()
        for s in done:
            if s.get("essayResult"):
                s["dashEssay"] = ESSAY_VERSION
        self.r.tick("dash_notebooks", len(nb_rows))
        self.r.tick("dash_essays", len(fb_rows))

    def add_manifest(self, manifest, seen, cls, a, n, tasks):
        meta = {}
        if a.get("essayPack"):
            meta = json.loads((BUNDLE / "packs" / a["essayPack"] / "meta.json").read_text(encoding="utf-8"))
        entry = next((e for e in manifest["entries"] if e["className"] == cls and e["assignmentCode"] == a["code"]), None)
        if not entry:
            entry = {"className": cls, "assignmentCode": a["code"], "session": n, "tasks": []}
            manifest["entries"].append(entry)
            seen.add((cls, a["code"]))
        have = {t["taskNumber"] for t in entry["tasks"]}
        for t in tasks:
            if t not in have:
                label = meta.get("labels", {}).get(str(t), f"Đề {t}")
                title = re.sub(r"^Đề\s*\d+\s*·\s*", "", label)
                entry["tasks"].append({"taskNumber": t, "title": ("Task 1 · " if meta.get("task") == 1 else "Task 2 · ") + title})
        entry["tasks"].sort(key=lambda x: x["taskNumber"])
