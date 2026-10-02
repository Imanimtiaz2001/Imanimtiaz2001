from dataclasses import dataclass, field


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    end_line: int
    rule_id: str
    severity: str
    message: str
    suggestion: str
    evidence: str
    origin: str = "static"

    def as_dict(self) -> dict:
        return {
            "path": self.path, "line": self.line, "end_line": self.end_line,
            "rule_id": self.rule_id, "severity": self.severity,
            "message": self.message, "suggestion": self.suggestion,
            "evidence": self.evidence, "origin": self.origin,
        }


@dataclass
class ReviewResult:
    path: str
    findings: list[Finding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"path": self.path, "findings": [f.as_dict() for f in self.findings],
                "warnings": self.warnings}

