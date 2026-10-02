from dataclasses import dataclass
from pathlib import Path
import tomllib

RULES = frozenset({
    "PY001", "PY002", "PY003", "PY004", "PY005", "PY006", "PY007",
    "PY008", "PY009", "PY010", "PY011", "PY012", "AI001",
})


@dataclass(frozen=True)
class Policy:
    ignore: frozenset[str] = frozenset()
    max_line_length: int = 100
    max_file_bytes: int = 200_000
    llm_max_lines: int = 100
    llm_max_findings: int = 12

    @classmethod
    def load(cls, path: str | Path | None) -> "Policy":
        if path is None:
            return cls()
        with open(path, "rb") as stream:
            data = tomllib.load(stream)
        if set(data) != {"review"} or not isinstance(data["review"], dict):
            raise ValueError("Policy must contain only a [review] table")
        values = data["review"]
        allowed = set(cls.__dataclass_fields__)
        if set(values) - allowed:
            raise ValueError(f"Unknown policy options: {', '.join(sorted(set(values) - allowed))}")
        ignored = values.get("ignore", [])
        if not isinstance(ignored, list) or any(not isinstance(x, str) for x in ignored):
            raise ValueError("review.ignore must be a list of rule IDs")
        if set(ignored) - RULES:
            raise ValueError(f"Unknown rule IDs: {', '.join(sorted(set(ignored) - RULES))}")
        for key in allowed - {"ignore"}:
            if key in values and (type(values[key]) is not int or values[key] < 1):
                raise ValueError(f"review.{key} must be a positive integer")
        return cls(**{**values, "ignore": frozenset(ignored)})

