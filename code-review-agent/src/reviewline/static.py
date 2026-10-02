"""Small, explainable AST checks. This is not a general taint analyzer."""

import ast
import re

from .models import Finding
from .policy import Policy

SECRET_NAME = re.compile(
    r"(?:secret|password|passwd|api[_-]?key|access[_-]?token|private[_-]?key)", re.I
)
PLACEHOLDER = re.compile(r"^(?:test|example|sample|dummy|changeme|your[_-]|<|\$|x+$)", re.I)
SQL_VERB = re.compile(r"\b(?:select|insert|update|delete|drop|alter)\b", re.I)


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def static_review(source: str, path: str, policy: Policy) -> list[Finding]:
    lines = source.splitlines()
    findings: list[Finding] = []

    def add(rule: str, severity: str, node: ast.AST, message: str, suggestion: str) -> None:
        if rule in policy.ignore:
            return
        line = max(1, min(getattr(node, "lineno", 1), max(len(lines), 1)))
        end = max(line, min(getattr(node, "end_lineno", None) or line, max(len(lines), 1)))
        evidence = lines[line - 1].strip()[:200] if lines else ""
        findings.append(Finding(path, line, end, rule, severity, message, suggestion, evidence))

    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as error:
        node = ast.Pass()
        node.lineno = error.lineno or 1
        add("PY012", "high", node, f"Python syntax error: {error.msg}",
            "Fix the syntax error before running the reviewer again.")
        return findings

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = dotted(node.func)
            keywords = {k.arg: k.value for k in node.keywords if k.arg is not None}
            if name in {"eval", "exec", "builtins.eval", "builtins.exec"}:
                add("PY001", "high", node, f"Dynamic code execution through {name}.",
                    "Use an explicit parser or dispatch table for expected inputs.")
            if name in {"subprocess.run", "subprocess.Popen", "subprocess.call",
                        "subprocess.check_call", "subprocess.check_output"}:
                if (isinstance(keywords.get("shell"), ast.Constant)
                        and keywords["shell"].value is True):
                    add("PY002", "high", node, "Subprocess runs through a shell.",
                        "Pass an argument list with shell=False; validate untrusted arguments.")
            if name in {"pickle.load", "pickle.loads", "cPickle.load", "cPickle.loads"}:
                add("PY003", "high", node, "Pickle deserialization can execute code.",
                    "Use a safe format such as JSON for untrusted input.")
            if name == "yaml.load":
                loader = keywords.get("Loader")
                if loader is None and len(node.args) > 1:
                    loader = node.args[1]
                if dotted(loader) not in {"yaml.SafeLoader", "SafeLoader"}:
                    add("PY004", "high", node, "YAML load has no verified safe loader.",
                        "Use yaml.safe_load or explicitly supply yaml.SafeLoader.")
            requests_calls = {"requests.get", "requests.post", "requests.put",
                              "requests.delete", "requests.patch", "requests.head",
                              "requests.request"}
            if name in requests_calls and "timeout" not in keywords:
                add("PY005", "medium", node, "HTTP request has no timeout.",
                    "Set a finite connect/read timeout to avoid hanging indefinitely.")
            if name.split(".")[-1] in {"execute", "executemany"} and node.args:
                query = node.args[0]
                dynamic = isinstance(query, ast.JoinedStr) or (
                    isinstance(query, ast.BinOp) and isinstance(query.op, (ast.Add, ast.Mod))
                ) or (isinstance(query, ast.Call) and dotted(query.func).endswith(".format"))
                if dynamic and SQL_VERB.search(ast.unparse(query)):
                    add("PY008", "high", node, "SQL query appears to interpolate values.",
                        "Use database parameter binding for values and allowlist identifiers.")
        elif isinstance(node, ast.ExceptHandler):
            if node.type is None:
                add("PY006", "medium", node, "Bare except catches system-exiting exceptions.",
                    "Catch the specific expected exception and handle or re-raise it.")
            elif dotted(node.type) in {"Exception", "BaseException"} and node.body and all(
                isinstance(item, ast.Pass) for item in node.body
            ):
                add("PY011", "medium", node, "Broad exception is silently ignored.",
                    "Handle the failure explicitly or log it and re-raise.")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = (*node.args.defaults,
                        *(x for x in node.args.kw_defaults if x is not None))
            for default in defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)) or (
                    isinstance(default, ast.Call)
                    and dotted(default.func) in {"list", "dict", "set"}
                ):
                    add("PY007", "medium", default, "Mutable default is shared between calls.",
                        "Default to None, then create a fresh value inside the function.")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                secret = value.value.strip()
                if len(secret) >= 8 and not PLACEHOLDER.match(secret):
                    if any(SECRET_NAME.search(dotted(target)) for target in targets):
                        add("PY009", "high", node, "Possible hardcoded credential.",
                            "Read the credential from a secret manager or environment variable.")

    if "PY010" not in policy.ignore:
        for index, line in enumerate(lines, 1):
            if len(line) > policy.max_line_length:
                findings.append(Finding(path, index, index, "PY010", "low",
                    f"Line has {len(line)} characters; limit is {policy.max_line_length}.",
                    "Wrap the expression or split it into named parts.", line.strip()[:200]))
    return findings
