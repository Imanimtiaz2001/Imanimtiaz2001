"""Publish one idempotent GitHub PR review with comments only on added lines."""

import hashlib
import json
import urllib.parse
import urllib.request

from .models import ReviewResult

MARKER = "<!-- reviewline-agent:"


def added_lines(patch: str) -> set[int]:
    import re
    current = 0
    added: set[int] = set()
    in_hunk = False
    for line in patch.splitlines():
        match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if match:
            current = int(match.group(1))
            in_hunk = True
        elif in_hunk and line.startswith("+"):
            added.add(current)
            current += 1
        elif in_hunk and line.startswith(" "):
            current += 1
    return added


def publish(result: ReviewResult, *, repository: str, number: int, token: str,
            api_base: str = "https://api.github.com", expected_head: str | None = None) -> dict:
    if not repository or "/" not in repository or number < 1 or not token:
        raise ValueError("repository, positive PR number, and token are required")
    if not api_base.startswith("https://"):
        raise ValueError("GitHub API base must use HTTPS")
    repo = "/".join(urllib.parse.quote(part, safe="") for part in repository.split("/"))
    root = f"{api_base}/repos/{repo}/pulls/{number}"

    def call(url: str, payload: dict | None = None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(url, data=data, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        }, method="POST" if data is not None else "GET")
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)

    pr = call(root)
    head = pr["head"]["sha"]
    if expected_head is not None and head != expected_head:
        raise ValueError("Pull request head changed during review; rerun on the new revision")
    if pr["state"] != "open":
        raise ValueError("Pull request is not open")
    allowed: dict[str, set[int]] = {}
    page = 1
    while True:
        files = call(f"{root}/files?per_page=100&page={page}")
        for item in files:
            if item.get("status") != "removed" and "patch" in item:
                allowed[item["filename"]] = added_lines(item["patch"])
        if len(files) < 100:
            break
        page += 1
    comments = [{
        "path": f.path, "line": f.line, "side": "RIGHT",
        "body": f"**{f.rule_id} · {f.severity}** — {f.message}\n\n"
                f"Suggestion: {f.suggestion}\n\nEvidence: `{f.evidence.replace('`', chr(39))}`",
    } for f in result.findings if f.line in allowed.get(f.path, set())]
    if not comments:
        return {"status": "no_changed_line_findings", "posted": 0}
    fingerprint = hashlib.sha256(json.dumps(
        {"head": head, "comments": comments}, sort_keys=True
    ).encode()).hexdigest()[:20]
    marker = f"{MARKER}{fingerprint}"
    existing = set()
    page = 1
    while True:
        reviews = call(f"{root}/reviews?per_page=100&page={page}")
        for review in reviews:
            body = review.get("body") or ""
            if marker in body:
                existing.add(body)
        if len(reviews) < 100:
            break
        page += 1
    posted = 0
    for index in range(0, len(comments), 100):
        batch = index // 100 + 1
        label = f"{marker}:{batch} -->"
        if any(label in body for body in existing):
            continue
        # GitHub rejects a review against a head that has moved; it is safe to rerun.
        chunk = comments[index:index + 100]
        call(f"{root}/reviews", {"commit_id": head, "event": "COMMENT",
                                "body": f"Reviewline findings for this revision. {label}",
                                "comments": chunk})
        posted += len(chunk)
    return {"status": "posted" if posted else "already_posted", "posted": posted}
