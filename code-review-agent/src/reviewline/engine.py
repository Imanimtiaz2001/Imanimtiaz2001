import ast
from dataclasses import replace

from .llm import llm_review
from .models import ReviewResult
from .policy import Policy
from .static import static_review


def review_source(source: str, path: str = "<stdin>", policy: Policy | None = None,
                  *, ai: bool = False, request_fn=None) -> ReviewResult:
    policy = policy or Policy()
    if len(source.encode("utf-8")) > policy.max_file_bytes:
        raise ValueError(f"File exceeds {policy.max_file_bytes} byte limit")
    result = ReviewResult(path)
    result.findings = static_review(source, path, policy)
    try:
        ast.parse(source, filename=path)
        syntax_error = False
    except SyntaxError:
        syntax_error = True
    # Suppressing the visible credential rule must not bypass the provider guard.
    secret_policy = replace(policy, ignore=policy.ignore - {"PY009"})
    secret = any(f.rule_id == "PY009" for f in static_review(source, path, secret_policy))
    if ai and not syntax_error and "AI001" not in policy.ignore:
        if secret:
            result.warnings.append("AI review skipped: possible hardcoded credential in source")
        else:
            extra, warnings = llm_review(source, path, policy, request_fn)
            result.findings.extend(extra)
            result.warnings.extend(warnings)
    seen = set()
    ordered = []
    for finding in sorted(result.findings, key=lambda f: (f.line, f.rule_id, f.message)):
        key = (finding.line, finding.rule_id, finding.message)
        if key not in seen:
            seen.add(key)
            ordered.append(finding)
    result.findings = ordered
    return result
