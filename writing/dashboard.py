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
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


NB_STATE = {
    "Đạt": ("notebook_complete", "Đạt yêu cầu"),
    "Cần bổ sung": ("awaiting_notebook_completion", "Cần bổ sung vở"),
}


def notebook_record(cls, s, roster_name, mode, pack_sha, ref_sha):
    verdict = s.get("verdict") or ""
    state, title = NB_STATE.get(verdict, ("needs_readable_copy", "Cần ảnh rõ hơn"))
    submitted = iso_vn(s.get("submittedAt", ""))
    receipt = sha(canonical({"component": "notebook", "className": cls, "assignmentCode": s["assignment"],
                             "studentKey": student_key(roster_name), "submittedAt": submitted}))
    overall = (s.get("comment") or "").strip()
    locked = state == "awaiting_notebook_completion" and mode == "notebook_and_writing"
    rec = {"schemaVersion": 1, "kind": "review", "className": cls, "assignmentCode": s["assignment"],
           "studentName": roster_name, "submittedAt": submitted, "checkedAt": s.get("publishedAt") or s.get("at") or "",
           "state": state, "displayTitle": title,
           "reason": overall if state != "notebook_complete" else overall,
           "overall": overall, "nextSteps": [], "issues": [],
           "handwriting": {"legibility": "readable" if state != "needs_readable_copy" else "unclear",
                           "captureQuality": "clear" if state != "needs_readable_copy" else "unclear", "evidence": []},
           "binding": {"receiptId": receipt, "notebookJobId": sha(receipt + "|" + s.get("sig", "")),
                       "files": [{"fileId": f} for f in s.get("files", [])],
                       "promptSha256": pack_sha, "referenceSha256": ref_sha},
           "essayGradingLocked": locked, "reviewMode": "quick_check", "sourceUrls": []}
    if locked:
        rec["reason"] = overall
    return rec


def essay_records(cls, s, roster_name, a):
    """One bài chữa per graded essay, in the parent page's review format."""
    res = s.get("essayResult") or {}
    meta = json.loads((BUNDLE / "packs" / a["essayPack"] / "meta.json").read_text(encoding="utf-8"))
    head_sha = sha((BUNDLE / "packs" / a["essayPack"] / "head.md").read_bytes())
    import essays as E
    by_de = {E.de_number(lbl, i): txt for i, (lbl, txt) in enumerate(sorted(s.get("essays", {}).items()))
             if str(E.de_number(lbl, i)) in meta["labels"]}
    submitted = iso_vn(s.get("submittedAt", ""))
    published = s.get("publishedAt") or utc_now()
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
        grid = " · ".join(f"{k} {c[x]['band']}" for k, x in crit)
        detail = "\n\n".join(f"**{k} {c[x]['band']}** — {c[x]['reason'].strip()}\n**Để lên band cao hơn:** {c[x]['whyNotHigher'].strip()}"
                             for k, x in crit)
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", e["revisedText"].strip()) if p.strip()]
        identity = {"assignmentCode": a["code"], "className": cls, "studentKey": student_key(roster_name),
                    "submittedAt": submitted, "taskNumber": e["de"]}
        receipt = sha(json.dumps(identity, ensure_ascii=False, separators=(",", ":")))
        source_sha = sha(original)
        rec = {"schemaVersion": 1, "resultId": "claude-" + h(receipt + head_sha, 24),
               "className": cls, "studentName": roster_name, "assignmentCode": a["code"], "taskNumber": e["de"],
               "originalEssay": original, "originalWordCount": e.get("_qa", {}).get("words") or len(original.split()),
               "overall": e["overall"].strip() + (f"\n\n**Band {band:.1f}** ({grid})" if band is not None else ""),
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
                    "published", raw, published, sha(raw)])
    return out


class Dashboard:
    def __init__(self, runner):
        self.r, self.g = runner, runner.g
        self.tabs = {}

    def table(self, sid, tab, headers):
        """The store tab's rows; created hidden with its headers if missing. A header mismatch → never write."""
        key = (sid, tab)
        if key not in self.tabs:
            if tab not in self.g.sheet_titles(sid):
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
            if s.get("dash") and (s.get("dashEssay") or not s.get("essayResult")):
                continue
            if s["assignment"] not in assignments or s.get("fallback"):
                continue
            todo.setdefault(s["className"], []).append((k, s))
        manifest = load_json(MANIFEST, {"schemaVersion": 1, "entries": []})
        seen = {(e["className"], e["assignmentCode"]) for e in manifest["entries"]}
        for cls, items in todo.items():
            try:
                self.publish_class(cls, items, assignments, manifest, seen)
            except Exception as e:  # one class never blocks the others
                self.r.tick("dash_class_failed")
                print("dashboard:", cls, type(e).__name__, str(e)[:80])
        save_json(MANIFEST, manifest)

    def publish_class(self, cls, items, assignments, manifest, seen):
        tr = self.r.tracker(cls)
        sid = tr.id
        cfg_rows = self.table(sid, NB_CONFIG, NB_CONFIG_HEADERS)
        have_cfg = {r[1] for r in cfg_rows[1:] if len(r) > 1 and r[0] == cls}
        self.table(sid, NB_STORE, NB_STORE_HEADERS)
        self.table(sid, FEEDBACK, FEEDBACK_HEADERS)
        new_cfg, nb_rows, fb_rows, done = [], [], [], []
        for k, s in items:
            a = assignments[s["assignment"]]
            n = int(re.search(r"W0*(\d+)$", a["code"]).group(1))
            pack = BUNDLE / "packs" / a["pack"]
            pack_sha = sha((pack / "head.md").read_bytes())
            ref_sha = sha((pack / "meta.json").read_bytes()) if (pack / "meta.json").exists() else sha(a["code"] + pack_sha)
            mode = a.get("mode", "notebook_only")
            if a["code"] not in have_cfg:
                details = {"notebookSourceResolveHyperlinks": True, "notebookSubmissionFormats": ["pdf", "image"],
                           "preferredNotebookHeader": "PDF ĐÃ GHÉP TỰ ĐỘNG", "promptSha256": pack_sha,
                           "referenceSha256": ref_sha, "schemaVersion": 1, "sourceUrls": [],
                           "sourceVersions": [{"fileId": "claude-pack-" + pack_sha[:16], "modifiedTime": "2026-11-09T00:00:00Z"}]}
                raw = canonical(details)
                new_cfg.append([cls, a["code"], str(n), mode, self.r.cfg["formSheet"], a["formTab"], "0", "1", "2", "3",
                                "Ảnh / File scan vở chép", raw, sha(raw), "TRUE"])
                have_cfg.add(a["code"])
            name = self.roster_name(tr, s["student"])
            if not name:
                s["dash"] = "no_roster_name"
                continue
            if not s.get("dash"):
                rec = notebook_record(cls, s, name, mode, pack_sha, ref_sha)
                raw = canonical(rec)
                nb_rows.append([sha(raw), student_key(name), cls, a["code"], rec["submittedAt"], rec["binding"]["notebookJobId"],
                                rec["state"], raw, s.get("publishedAt") or utc_now(), sha(raw), rec["binding"]["receiptId"], "published"])
            tasks = []
            if s.get("essayResult") and a.get("essayPack") and not s.get("dashEssay"):
                rows = essay_records(cls, s, name, a)
                fb_rows += rows
                tasks = sorted({int(r[4]) for r in rows})
            done.append(s)
            if (cls, a["code"]) not in seen or tasks:
                self.add_manifest(manifest, seen, cls, a, n, tasks)
        if new_cfg:
            self.g.append_rows(sid, NB_CONFIG, new_cfg)
        if nb_rows:
            self.g.append_rows(sid, NB_STORE, nb_rows)
        if fb_rows:
            self.g.append_rows(sid, FEEDBACK, fb_rows)
        for s in done:
            s["dash"] = s.get("dash") or now().isoformat()
            if s.get("essayResult"):
                s["dashEssay"] = now().isoformat()
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
