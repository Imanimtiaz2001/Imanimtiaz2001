"""Trusted base-branch GitHub Action entrypoint; pull request files are data."""

import base64
import json
import os
import urllib.parse
import urllib.request

from .engine import review_source
from .github import publish
from .models import ReviewResult
from .policy import Policy


def run() -> dict:
    repo = os.environ["GITHUB_REPOSITORY"]
    number = int(os.environ["REVIEWLINE_PR_NUMBER"])
    sha = os.environ["REVIEWLINE_HEAD_SHA"]
    token = os.environ["GITHUB_TOKEN"]
    if not all(c in "0123456789abcdef" for c in sha.lower()) or len(sha) != 40:
        raise ValueError("Invalid pull request head SHA")
    root = f"https://api.github.com/repos/{repo}"
    headers = {"Authorization": f"Bearer {token}",
               "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}

    def get(url):
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
            return json.load(r)

    result = ReviewResult("")
    policy = Policy()
    page = 1
    while True:
        files = get(f"{root}/pulls/{number}/files?per_page=100&page={page}")
        for item in files:
            name = item["filename"]
            if not name.endswith(".py") or item.get("status") == "removed":
                continue
            path = urllib.parse.quote(name, safe="/")
            data = get(f"{root}/contents/{path}?ref={sha}")
            if (data.get("type") != "file"
                    or data.get("size", policy.max_file_bytes + 1) > policy.max_file_bytes):
                continue
            source = base64.b64decode(data["content"], validate=False).decode("utf-8")
            result.findings.extend(review_source(source, name, policy).findings)
        if len(files) < 100:
            break
        page += 1
    return publish(result, repository=repo, number=number, token=token, expected_head=sha)


if __name__ == "__main__":
    print(json.dumps(run()))
