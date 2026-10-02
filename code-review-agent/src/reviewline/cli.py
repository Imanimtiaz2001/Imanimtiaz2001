import argparse
import json
import os
from pathlib import Path
import sys

from .engine import review_source
from .github import publish
from .output import render
from .policy import Policy

RANK = {"low": 1, "medium": 2, "high": 3}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evidence-checked Python code reviewer")
    parser.add_argument("path", help="Python file or - for UTF-8 stdin")
    parser.add_argument("--policy", help="TOML review policy")
    parser.add_argument("--ai", action="store_true", help="Opt in to external LLM review")
    parser.add_argument("--format", choices=("text", "json", "sarif", "github"), default="text")
    parser.add_argument("--fail-on", choices=("low", "medium", "high"), default="medium")
    parser.add_argument("--publish-pr", action="store_true",
                        help="Post changed-line PR review comments")
    args = parser.parse_args(argv)
    try:
        policy = Policy.load(args.policy)
        if args.path == "-":
            source = sys.stdin.read(policy.max_file_bytes + 1)
        else:
            path = Path(args.path)
            if path.stat().st_size > policy.max_file_bytes:
                raise ValueError(f"File exceeds {policy.max_file_bytes} byte limit")
            source = path.read_text(encoding="utf-8")
        result = review_source(source, args.path, policy, ai=args.ai)
        print(render(result, args.format))
        for warning in result.warnings:
            print(f"warning: {warning}", file=sys.stderr)
        if args.publish_pr:
            repo = os.environ.get("GITHUB_REPOSITORY", "")
            number = int(os.environ.get("REVIEWLINE_PR_NUMBER", "0"))
            token = os.environ.get("GITHUB_TOKEN", "")
            outcome = publish(result, repository=repo, number=number, token=token)
            print(json.dumps(outcome), file=sys.stderr)
        return int(any(RANK[f.severity] >= RANK[args.fail_on] for f in result.findings))
    except (OSError, UnicodeError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"reviewline: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
