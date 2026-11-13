"""Cô 12/11 'ok sửa': one-shot correction of results already published, so word count, deduction, band and comment
agree. Machine-only: no new grading. A tracker cell is rewritten only while it still holds exactly what the machine wrote.
IELTS 49 KT lần 1 and IELTS 45 KT lần 3 (graded in the old system) are left alone."""
import json
import re

SKIP_TESTS = {("IELTS 49", 1), ("IELTS 45", 3)}
RANGE = re.compile(r"(?:khoảng|tầm|gần|ước|chỉ khoảng|chỉ)?\s*~?\s*(?<![\d.,])(\d{2,3})\s*[-–]\s*(\d{2,3})\s*từ(?![ \t]*\d)")
ONE = re.compile(r"(?:(chỉ)\s+)?(?:(?:khoảng|tầm|gần|ước|chừng|đủ khoảng|có khoảng)\s+)?~?\s*(?<![\d.,])(\d{2,3})\s*từ(?![ \t]*\d)")
SHORT_CLAIM = re.compile(r"(?i)(chưa|không)\s+(thật\s+sự\s+)?đủ\s+(\d+\s+)?từ|chưa\s+đủ\s+(150|250)|dưới\s+(150|250)\s+từ|"
                         r"thiếu\s+số\s+từ|thiếu\s+\d+\s+từ|ngắn\s+hơn\s+yêu\s+cầu|chưa\s+đạt\s+(độ\s+dài|số\s+từ)|chưa\s+đủ\s+độ\s+dài")


def fix_text(text, w, minimum, fighter=False):
    """Word-count guesses written by the model → the machine count; claims of 'too short' removed when it is not."""
    if not text or not w:
        return text
    mins = {minimum, 140, 160, 170} if fighter else {minimum, 150, 250}

    def rng(m):
        return f"{w} từ"

    def one(m):
        n = int(m.group(2))
        if n in mins or abs(n - w) > 150:
            return m.group(0)
        lead = "chỉ " if (m.group(1) and minimum and w < minimum) else ""
        return f"{lead}{w} từ"
    out = RANGE.sub(rng, text)
    out = ONE.sub(one, out)
    if minimum and w >= minimum and not fighter:
        parts = re.split(r"(?<=[.!?;])\s+", out)
        kept = [p for p in parts if not SHORT_CLAIM.search(p)]
        if kept and len(kept) < len(parts):
            out = re.sub(r"[;,]\s*$", ".", " ".join(kept))
    return out


def fix_ielts_task(t, w, minimum):
    """Model text of one IELTS task / homework essay."""
    ch = 0
    for k in ("overall",):
        new = fix_text(t.get(k), w, minimum)
        if new != t.get(k):
            t[k], ch = new, ch + 1
    for c in (t.get("criteria") or {}).values():
        for k in ("reason", "whyNotHigher"):
            new = fix_text(c.get(k), w, minimum)
            if new != c.get(k):
                c[k], ch = new, ch + 1
    return ch


def _cells(sc, rec, s, tr, grid):
    """{task: (a1, text)} where this pupil's result sits, or {} when it can't be found."""
    from run_writing import col_letter
    spec = sc_mod().pack_for(rec["meta"])
    if spec.get("inclass"):
        c = sc.inclass_column(tr, grid, rec["meta"], create=False)
        cols = {} if c is None else {(spec.get("tasks") or [0])[0] if spec["schema"] == "ielts" else 0: c}
    else:
        cols = sc.find_columns(grid, rec["meta"], spec.get("tasks") or [])
    row = tr.row_of(s["name"])
    if not row:
        return {}
    return {task: f"{col_letter(c)}{row}" for task, c in cols.items()}


def sc_mod():
    import scans
    return scans


def run(runner):
    if not runner.cfg.get("recount1112") or runner.state.get("recount1112Done"):
        return
    import calculate_class_score as ccs
    import essays
    import zalo
    from run_writing import MARK, now
    scans = sc_mod()
    stamp = now().isoformat()

    # ---- homework essays (typed): fix the model's word guesses, add the machine count, rewrite our own block
    for k, s in runner.state.get("subs", {}).items():
        if s.get("status") != "published" or not s.get("essayResult"):
            continue
        er = s["essayResult"]
        was_str = isinstance(er, str)
        er = json.loads(er) if was_str else er
        mn = zalo.min_words(s.get("assignment"))
        task = 1 if mn == 150 else 2
        er["_task"] = task
        for e in er.get("essays") or []:
            qa = e.setdefault("_qa", {})
            try:
                bands = [int(e["criteria"][x]["band"]) for x in ("TA_TR", "CC", "LR", "GRA")]
                qa["classScore"] = ccs.calculate(task, int(qa["words"]), bands)
            except Exception:
                continue
            if fix_ielts_task(e, qa["words"], mn):
                runner.tick("recount_hw_text_fixed")
        old_comment, old_blk = s.get("publishedComment"), s.get("publishedBlock") or s.get("publishedComment")
        new_comment = s["comment"].rstrip() + "\n\n" + essays.summary(er)
        s["essayResult"] = json.dumps(er, ensure_ascii=False) if was_str else er
        s["correctedAt"], s["dashEssay"] = stamp, None   # the dashboard gets the corrected bài chữa (newer time wins)
        if not old_comment or not s.get("cell") or new_comment == old_comment:
            continue
        new_blk = old_blk.replace(old_comment, new_comment) if old_comment in old_blk else new_comment
        try:
            tr = runner.tracker(s["className"])
            cur = tr.cell(s["cell"])
            if MARK not in cur or old_blk not in cur.split(MARK, 1)[1]:
                runner.tick("recount_hw_cell_changed_by_teacher")
                continue
            new = cur.replace(old_blk, new_blk)
            tr.write(s["cell"], new)
            if tr.cell(s["cell"]) == new:
                s.update(publishedComment=new_comment, publishedBlock=new_blk)
                runner.tick("recount_hw_cell_rewritten")
        except Exception as ex:
            runner.tick(f"recount_hw_failed_{type(ex).__name__}")

    # ---- handwritten papers: count again without crossed-out words / notes / name; band follows the class rule
    sc = scans.Scans(runner)
    for fid, rec in sc.st.get("files", {}).items():
        meta = rec.get("meta") or {}
        if meta.get("kind") not in ("inclass", "test"):
            continue
        if meta.get("kind") == "test" and (meta.get("cls"), meta.get("n")) in SKIP_TESTS:
            continue
        fighter = str(meta.get("cls", "")).startswith("FIGHTER")
        pupils = [s for s in rec.get("students", {}).values() if s.get("status") == "published" and s.get("result")]
        if not pupils:
            continue
        try:
            tr = runner.tracker(meta["cls"])
            tr._grid = None
            tr.cached("A", 1)
            grid = tr._grid
        except Exception as ex:
            runner.tick(f"recount_paper_failed_{type(ex).__name__}")
            continue
        for s in pupils:
            res = s["result"]
            spec = scans.pack_for(meta) or {}
            tasks = [t.get("task") for t in res.get("tasks") or []] if spec.get("schema") == "ielts" else [None]
            old = {t: sc.cell_text(rec, res, t) for t in tasks}
            if spec.get("schema") == "ielts":
                for t in res.get("tasks") or []:
                    w = scans.paper_words(t.get("transcript"))
                    mn = 150 if t.get("task") == 1 else 250
                    fix_ielts_task(t, w, mn)
                    t["_qa"]["words"] = w
                    bands = [int(t["criteria"][x]["band"]) for x in ("TA_TR", "CC", "LR", "GRA")]
                    t["_qa"]["classScore"] = ccs.calculate(t["task"] if t["task"] in (1, 2) else 1, w, bands)
                sc_ = {t["task"]: t["_qa"]["classScore"]["classAssessment"]["overallBand"] for t in res.get("tasks", [])}
                if 1 in sc_ and 2 in sc_:
                    res["_overall"] = round(((sc_[1] + 2 * sc_[2]) / 3) * 2 + 1e-9) / 2
            else:
                w = scans.paper_words(res.get("transcript"))
                res["overall"] = fix_text(res.get("overall"), w, 140, fighter=True)
                res.setdefault("_qa", {})["words"] = w
            new = {t: sc.cell_text(rec, res, t) for t in tasks}
            if new == old:
                continue
            runner.tick("recount_paper_changed")
            try:
                where = _cells(sc, rec, s, tr, grid)
            except Exception:
                where = {}
            for t in tasks:
                key = t if t in where else (0 if 0 in where else (t or 0))
                a1 = where.get(key) or (where.get(next(iter(where))) if len(where) == 1 else None)
                if not a1 or not new.get(t) or new[t] == old[t]:
                    continue
                cur = tr.cell(a1)
                if cur.strip() != (old[t] or "").strip():
                    runner.tick("recount_paper_cell_changed_by_teacher")
                    continue
                tr.write(a1, new[t])
                runner.tick("recount_paper_cell_rewritten" if tr.cell(a1).strip() == new[t].strip() else "recount_paper_readback")
            s["recountedAt"] = stamp
    sc.save()
    runner.state["recount1112Done"] = stamp


def run_cells(runner):
    """Pass 2 (12/11 evening): the first pass could not find some cells (columns moved, a merged header). Each
    correction is now located by its exact old text in the pupil's row and rewritten only if that text is still there."""
    if not runner.cfg.get("recount1112b") or runner.state.get("recount1112bDone"):
        return
    from run_writing import BUNDLE, MARK, col_letter, norm
    path = BUNDLE / "recount_cells.json"
    if not path.exists():
        return
    items = json.loads(path.read_text(encoding="utf-8"))
    apply_cells(runner, items, "recount2")
    runner.state["recount1112bDone"] = True


def apply_cells(runner, items, tag):
    """Rewrite each {cls, name, old, new, mode} where the old text still stands in the pupil's row."""
    from run_writing import MARK, col_letter, norm
    by_cls = {}
    for it in items:
        by_cls.setdefault(it["cls"], []).append(it)
    for cls, its in by_cls.items():
        try:
            tr = runner.tracker(cls)
            tr._grid = None
            tr.cached("A", 1)
            grid = tr._grid
        except Exception as ex:
            runner.tick(f"{tag}_tracker_failed_{type(ex).__name__}")
            continue
        for it in its:
            row = tr.row_of(norm(it["name"]))
            if not row:
                runner.tick(f"{tag}_no_row")
                continue
            cells = grid[row - 1] if row - 1 < len(grid) else []
            old = it["old"].strip()
            hits = [c for c, v in enumerate(cells) if (str(v).strip() == old if it["mode"] == "exact"
                                                       else (MARK in str(v) and it["old"] in str(v)))]
            if len(hits) != 1:
                done = any(str(v).strip() == it["new"].strip() or (it["mode"] != "exact" and it["new"] in str(v)) for v in cells)
                runner.tick(f"{tag}_already" if done else (f"{tag}_not_found" if not hits else f"{tag}_ambiguous"))
                continue
            a1 = f"{col_letter(hits[0])}{row}"
            cur = tr.cell(a1)   # live read right before the write
            if it["mode"] == "exact":
                if cur.strip() != old:
                    runner.tick(f"{tag}_changed_meanwhile")
                    continue
                new = it["new"]
            else:
                if it["old"] not in cur:
                    runner.tick(f"{tag}_changed_meanwhile")
                    continue
                new = cur.replace(it["old"], it["new"])
            tr.write(a1, new)
            ok = tr.cell(a1).strip() == new.strip()
            runner.tick(f"{tag}_rewritten" if ok else f"{tag}_readback")
            if ok and it.get("sub") in runner.state.get("subs", {}):
                runner.state["subs"][it["sub"]].update(publishedComment=it["comment"], publishedBlock=it["new"], cell=a1)


def run_pct(runner):
    """Cô 12/11 tối: in-class IELTS writing already published with a band → the same cell with '% chất lượng'."""
    if runner.state.get("inclassPct1112Done"):
        return
    scans = sc_mod()
    sc = scans.Scans(runner)
    items = []
    for rec in sc.st.get("files", {}).values():
        meta = rec.get("meta") or {}
        if meta.get("kind") != "inclass" or not str(meta.get("cls", "")).startswith("IELTS"):
            continue
        for s in rec.get("students", {}).values():
            if s.get("status") != "published" or not s.get("result"):
                continue
            olds = {t.get("task"): sc.cell_text(rec, s["result"], t.get("task"), legacy=True) for t in s["result"].get("tasks") or []}
            import calculate_class_score as ccs
            for t in s["result"].get("tasks") or []:   # 12/11 tối: label lines ('Full essay:') no longer counted
                try:
                    w = scans.paper_words(t.get("transcript"))
                    t["_qa"]["words"] = w
                    t["_qa"]["classScore"] = ccs.calculate(t["task"] if t["task"] in (1, 2) else 1, w,
                                                           [int(t["criteria"][x]["band"]) for x in ("TA_TR", "CC", "LR", "GRA")])
                except Exception:
                    pass
            for t, old in olds.items():
                new = sc.cell_text(rec, s["result"], t)
                if old and new and old != new:
                    items.append({"cls": meta["cls"], "name": s["name"], "old": old, "new": new, "mode": "exact"})
    apply_cells(runner, items, "inclass_pct")
    sc.save()
    runner.state["inclassPct1112Done"] = True


def run_words3(runner):
    """13/11: label lines ('Full essay:') left out of the count — papers converted before that rule got their
    count, % and cell refreshed once (only where the cell still holds the machine's text)."""
    if runner.state.get("recount1113Done"):
        return
    import calculate_class_score as ccs
    scans = sc_mod()
    sc = scans.Scans(runner)
    items = []
    for rec in sc.st.get("files", {}).values():
        meta = rec.get("meta") or {}
        if meta.get("kind") != "inclass" or not str(meta.get("cls", "")).startswith("IELTS"):
            continue
        for s in rec.get("students", {}).values():
            if s.get("status") != "published" or not s.get("result"):
                continue
            tasks = s["result"].get("tasks") or []
            if all(scans.paper_words(t.get("transcript")) == (t.get("_qa") or {}).get("words") for t in tasks):
                continue
            olds = {t.get("task"): sc.cell_text(rec, s["result"], t.get("task")) for t in tasks}
            for t in tasks:
                w = scans.paper_words(t.get("transcript"))
                t["_qa"]["words"] = w
                t["_qa"]["classScore"] = ccs.calculate(t["task"] if t["task"] in (1, 2) else 1, w,
                                                       [int(t["criteria"][x]["band"]) for x in ("TA_TR", "CC", "LR", "GRA")])
            for k, old in olds.items():
                new = sc.cell_text(rec, s["result"], k)
                if old and new and old != new:
                    items.append({"cls": meta["cls"], "name": s["name"], "old": old, "new": new, "mode": "exact"})
    apply_cells(runner, items, "recount3")
    sc.save()
    runner.state["recount1113Done"] = True
