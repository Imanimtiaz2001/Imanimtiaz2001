import json

from .models import ReviewResult
from .policy import RULES

LEVELS = {"high": "error", "medium": "warning", "low": "note"}


def render(result: ReviewResult, kind: str) -> str:
    if kind == "json":
        return json.dumps(result.as_dict(), indent=2)
    if kind == "sarif":
        data = {
            "version": "2.1.0",
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [{
                "tool": {"driver": {"name": "Reviewline",
                                     "rules": [{"id": rule} for rule in sorted(RULES)]}},
                "results": [{
                    "ruleId": f.rule_id, "level": LEVELS[f.severity],
                    "message": {"text": f"{f.message} {f.suggestion}"},
                    "locations": [{"physicalLocation": {
                        "artifactLocation": {"uri": f.path},
                        "region": {"startLine": f.line, "endLine": f.end_line},
                    }}],
                } for f in result.findings],
            }],
        }
        return json.dumps(data, indent=2)
    if kind == "github":
        def escape(value: str) -> str:
            return (value.replace("%", "%25").replace("\r", "%0D")
                    .replace("\n", "%0A").replace(":", "%3A"))
        return "\n".join(
            f"::{LEVELS[f.severity]} file={escape(f.path)},line={f.line},"
            f"endLine={f.end_line},title={f.rule_id}::{escape(f.message)} {escape(f.suggestion)}"
            for f in result.findings
        )
    return "\n".join(
        f"{f.path}:{f.line}: {f.severity.upper()} {f.rule_id} {f.message}\n"
        f"  {f.suggestion}" for f in result.findings
    ) or "No findings."
