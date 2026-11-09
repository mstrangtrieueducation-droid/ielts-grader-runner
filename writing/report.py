"""Grading digest for Cô: what was graded since the last report.

Posted as a comment on one GitHub issue in this repo, mentioning the owner, so GitHub e-mails it to her inbox
(free, no mail quota, nothing to set up). The repo is public, so the digest carries COUNTS ONLY: class, week,
test name, numbers. No pupil names, comments or scores.
"""
import collections
import datetime as dt
import json
import os
import urllib.request

VN = dt.timezone(dt.timedelta(hours=7))
OWNER = "mstrangtrieueducation-droid"
TITLE = "📋 Báo cáo chấm Writing (tự động)"
SLOTS = ("12:00", "22:30")   # Vietnam time; the first cycle after each slot sends the report

HOLD_VI = {
    "no_tracker_column": "chưa có cột trên tracker",
    "not_in_roster": "tên không có trong danh sách lớp",
    "readback_mismatch": "ghi tracker chưa khớp, sẽ thử lại",
    "result_already_given": "ô đã có kết quả từ trước (không chấm lại)",
    "status_prefix_not_ready": "chờ hệ thống ghi trạng thái nộp bài",
}


def _t(x):
    try:
        t = dt.datetime.fromisoformat(x)
        return t if t.tzinfo else t.replace(tzinfo=VN)
    except Exception:
        return None


def _in(x, a, b):
    t = _t(x) if isinstance(x, str) else None
    return bool(t and a < t <= b)


def week(code):
    return (code or "").replace("IELTS-WRITING-", "").replace("FIGHTER-WRITING-", "") or "?"


def build(state, scans, since, until):
    subs = state.get("subs", {})
    nb = collections.defaultdict(collections.Counter)   # (class, week) → counts
    dash = collections.Counter()
    for s in subs.values():
        key = (s.get("className", "?"), week(s.get("assignment")))
        if s.get("status") == "published" and _in(s.get("publishedAt"), since, until):
            c = nb[key]
            c["vở"] += 1
            c[s.get("verdict") or "khác"] += 1
            if s.get("essayResult"):
                c["bài chữa"] += 1
            if s.get("afterDeadline"):
                c["muộn"] += 1
        if _in(s.get("dash"), since, until):
            dash[s.get("className", "?")] += 1

    tests = collections.Counter()
    for rec in (scans or {}).get("files", {}).values():
        for stu in rec.get("students", {}).values():
            if stu.get("status") == "published" and _in(stu.get("at"), since, until):
                tests[(rec.get("title") or "?").rsplit(".", 1)[0].replace("_", " · ")] += 1

    waiting = collections.Counter()
    for s in subs.values():
        st = s.get("status")
        if st in ("new", "submitted", "graded", "essay_new", "essay_submitted"):
            waiting["đang chấm / chờ lượt sau"] += 1
        elif st == "held":
            waiting[HOLD_VI.get(s.get("hold"), s.get("hold") or "cần xem")] += 1
    for rec in (scans or {}).get("files", {}).values():
        if rec.get("status") == "unrecognised_name":
            waiting["file scan sai tên (không đọc được lớp/buổi)"] += 1
        elif rec.get("status") == "waiting":
            waiting["bài kiểm tra đang tạm dừng (chờ Cô quyết)"] += 1
        elif rec.get("status") == "submitted":
            waiting["bài kiểm tra đang chấm"] += 1
        elif rec.get("status") == "no_pack":
            waiting["bài kiểm tra chưa có barem"] += 1
        for stu in rec.get("students", {}).values():
            if stu.get("status") == "held":
                waiting["bài kiểm tra: " + HOLD_VI.get(stu.get("hold"), stu.get("hold") or "cần xem")] += 1
            elif stu.get("status") == "unidentified":
                waiting["bài kiểm tra: chưa nhận ra tên học sinh"] += 1

    f = lambda t: t.astimezone(VN).strftime("%H:%M %d/%m")
    out = [f"@{OWNER} Báo cáo chấm Writing **{f(since)} → {f(until)}**", ""]
    if nb:
        out.append(f"### ✅ Bài tập về nhà đã trả: {sum(c['vở'] for c in nb.values())} học sinh")
        for (cls, w), c in sorted(nb.items()):
            parts = [f"{c['vở']} vở"]
            verdicts = [f"{c[v]} {v}" for v in ("Đạt", "Cần bổ sung", "Không đạt", "Chưa đủ dữ liệu để kết luận") if c[v]]
            if verdicts:
                parts.append("(" + ", ".join(verdicts) + ")")
            if c["bài chữa"]:
                parts.append(f"· {c['bài chữa']} bài chữa")
            if c["muộn"]:
                parts.append(f"· {c['muộn']} nộp muộn (chỉ kiểm tra vở)")
            out.append(f"- **{cls}** · {w}: " + " ".join(parts))
        out.append("")
    if tests:
        out.append(f"### 📝 Bài kiểm tra giấy đã ghi điểm: {sum(tests.values())} bài")
        out += [f"- {t}: {n} bài" for t, n in sorted(tests.items())]
        out.append("")
    if dash:
        out.append(f"### 🌐 Lên dashboard phụ huynh: {sum(dash.values())} học sinh")
        out.append("- " + " · ".join(f"{c}: {n}" for c, n in sorted(dash.items())))
        out.append("")
    if not (nb or tests or dash):
        out += ["Không có bài mới được chấm trong khoảng này.", ""]
    if waiting:
        out.append("### ⏳ Đang chờ / cần Cô xem")
        out += [f"- {k}: {n}" for k, n in waiting.most_common()]
        out.append("")
    out.append("_Máy chấm tự gửi sau mỗi buổi (khoảng 12:00 và 22:30). Chỉ có số lượng, không có tên học sinh._")
    return "\n".join(out)


def _api(path, data=None, method=None):
    repo = os.environ.get("GITHUB_REPOSITORY", f"{OWNER}/ielts-grader-runner")
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/{path}",
                                 data=json.dumps(data).encode() if data is not None else None,
                                 method=method or ("POST" if data is not None else "GET"),
                                 headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                                          "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"null")


def post(state, body):
    num = state.get("reportIssue")
    if num:
        try:
            if _api(f"issues/{num}").get("state") != "open":
                num = None
        except Exception:
            num = None
    if not num:
        num = _api("issues", {"title": TITLE, "body": "Mỗi bình luận dưới đây là một báo cáo chấm bài (chỉ số lượng)."})["number"]
        state["reportIssue"] = num
    _api(f"issues/{num}/comments", {"body": body})
    return num


def due(state, now):
    """The slot that is due now and not yet reported, or None."""
    sent = state.setdefault("reportsSent", [])
    for slot in SLOTS:
        hh, mm = map(int, slot.split(":"))
        at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        tag = at.strftime("%Y-%m-%d ") + slot
        if now >= at and tag not in sent:
            return tag
    return None


def maybe_send(runner, scans, force=False):
    state = runner.state
    now = dt.datetime.now(VN)
    tag = due(state, now)
    if not (tag or force) or not os.environ.get("GH_TOKEN"):
        return False
    since = _t(state.get("lastReportAt") or "") or now.replace(hour=0, minute=0, second=0, microsecond=0)
    body = build(state, scans, since, now)
    post(state, body)
    state["lastReportAt"] = now.isoformat()
    sent = state.setdefault("reportsSent", [])
    if tag:
        sent.append(tag)
    del sent[:-20]
    runner.tick("report_sent")
    return True
