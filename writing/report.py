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

    return letter(since, until, nb, tests, dash, waiting)


THU = ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật"]
WAIT_VI = {
    "đang chấm / chờ lượt sau": "bài đang chấm, sẽ có kết quả ở lượt sau",
    "bài kiểm tra đang tạm dừng (chờ Cô quyết)": "bài kiểm tra cũ đang tạm dừng, chờ Cô quyết định có chấm không",
    "bài kiểm tra đang chấm": "bài kiểm tra đang chấm",
    "file scan sai tên (không đọc được lớp/buổi)": "file scan đặt tên sai, máy không biết của lớp/buổi nào — Cô xem lại tên file giúp em",
    "bài kiểm tra chưa có barem": "bài kiểm tra chưa có đáp án/barem để chấm",
}


def letter(since, until, nb, tests, dash, waiting):
    """Plain Vietnamese e-mail: subject, text and simple HTML (counts only, no pupil names)."""
    f = lambda t: t.astimezone(VN).strftime("%H:%M ngày %d/%m")
    u = until.astimezone(VN)
    subject = f"Báo cáo chấm bài viết – {u:%H:%M} {THU[u.weekday()]} {u:%d/%m}"
    blocks = []   # (title, [lines])
    if nb:
        lines = []
        for (cls, w), c in sorted(nb.items()):
            bits = [f"kiểm tra {c['vở']} vở"]
            v = [f"{c[k]} {lab}" for k, lab in (("Đạt", "đạt"), ("Cần bổ sung", "cần bổ sung"), ("Không đạt", "không đạt"),
                                                 ("Chưa đủ dữ liệu để kết luận", "chưa đủ ảnh để kết luận")) if c[k]]
            if v:
                bits[0] += " (" + ", ".join(v) + ")"
            if c["bài chữa"]:
                bits.append(f"chữa {c['bài chữa']} bài viết")
            if c["muộn"]:
                bits.append(f"{c['muộn']} em nộp muộn nên chỉ kiểm tra vở")
            lines.append(f"{cls} – bài {w}: " + "; ".join(bits) + ".")
        blocks.append((f"BÀI TẬP VỀ NHÀ: đã trả kết quả cho {sum(c['vở'] for c in nb.values())} học sinh", lines))
    if tests:
        blocks.append((f"BÀI KIỂM TRA TRÊN GIẤY: đã ghi điểm {sum(tests.values())} bài",
                       [f"{t}: {n} bài." for t, n in sorted(tests.items())]))
    if dash:
        blocks.append((f"ĐÃ LÊN DASH PHỤ HUYNH: {sum(dash.values())} học sinh",
                       [", ".join(f"{c}: {n} em" for c, n in sorted(dash.items())) + "."]))
    if waiting:
        blocks.append(("VIỆC ĐANG CHỜ", [f"{n} {WAIT_VI.get(k, k)}." for k, n in waiting.most_common()]))
    intro = f"Từ {f(since)} đến {f(until)}, máy chấm đã làm xong những việc sau:" if (nb or tests or dash) else \
        f"Từ {f(since)} đến {f(until)}, chưa có bài mới nào được chấm."
    outro = "Máy tự gửi thư này 2 lần mỗi ngày (khoảng 12 giờ trưa và 10 giờ 30 tối). Thư chỉ ghi số lượng; Cô xem chi tiết từng em trên file theo dõi của lớp."
    text = "\n".join(["Chào Cô Trang,", "", intro, ""] +
                     sum(([t] + ["  • " + x for x in ls] + [""] for t, ls in blocks), []) + [outro])
    esc = lambda x: x.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = ['<div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.6;color:#222">',
            "<p>Chào Cô Trang,</p>", f"<p>{esc(intro)}</p>"]
    for t, ls in blocks:
        html.append(f'<p style="margin:16px 0 4px"><b>{esc(t)}</b></p><ul style="margin:0">')
        html += [f"<li>{esc(x)}</li>" for x in ls]
        html.append("</ul>")
    html.append(f'<p style="color:#777;font-size:13px;margin-top:20px">{esc(outro)}</p></div>')
    return {"subject": subject, "text": text, "html": "".join(html)}


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


def save_reports(reports):
    """Public file read by Cô's Gmail script (Apps Script) which sends each new report from her own mailbox."""
    d = os.environ.get("RUNTIME_DIR")
    if d:
        p = os.path.join(d, "state", "reports.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"reports": reports}, fh, ensure_ascii=False)


def zalo_mail(runner, made, now, seq=0):
    """Own mail for the class pictures (Cô 11/11): sent as soon as a class is complete, 08:00–20:00.
    Public file carries class names only; Cô's mail script fetches the pictures from each class tracker."""
    classes = sorted({c for c, _ in made})
    names = ", ".join(f"{c} – {t}" for c, t in made)
    text = ("Chào Cô Trang,\n\nẢnh tổng kết để gửi nhóm Zalo lớp: " + names + ".\n"
            "Ảnh trang 1 là tổng quan, các trang sau là bảng từng bạn (đánh số theo thứ tự).\n\nMáy chấm bài viết")
    html = ("<p>Chào Cô Trang,</p><p>Ảnh tổng kết để gửi nhóm Zalo lớp: <b>" + names + "</b>.</p>"
            "<p>Ảnh trang 1 là tổng quan, các trang sau là bảng từng bạn (đánh số theo thứ tự).</p><p>Máy chấm bài viết</p>")
    reports = runner.state.setdefault("reports", [])
    reports.append({"id": now.isoformat(timespec="seconds") + f"z{seq:02d}", "subject": "Ảnh Zalo " + names,
                    "text": text, "html": html, "zalo": classes})
    del reports[:-30]
    save_reports(reports)


def maybe_send(runner, scans, force=False):
    state = runner.state
    now = dt.datetime.now(VN)
    tag = due(state, now)
    if not (tag or force):
        return False
    since = _t(state.get("lastReportAt") or "") or now.replace(hour=0, minute=0, second=0, microsecond=0)
    mail = build(state, scans, since, now)
    reports = state.setdefault("reports", [])
    reports.append({"id": now.isoformat(timespec="seconds"), **mail})
    del reports[:-30]
    save_reports(reports)
    state["lastReportAt"] = now.isoformat()
    sent = state.setdefault("reportsSent", [])
    if tag:
        sent.append(tag)
    del sent[:-20]
    runner.tick("report_sent")
    return True
