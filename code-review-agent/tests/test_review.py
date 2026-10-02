import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from io import BytesIO

from reviewline import Policy, review_source
from reviewline.github import added_lines, publish
from reviewline.output import render


class ReviewTests(unittest.TestCase):
    def test_static_rules_and_physical_lines(self):
        code = (
            "import subprocess, pickle, requests, yaml\n"
            "def f(items=[]):\n"
            "    try:\n"
            "        eval('1')\n"
            "    except:\n"
            "        pass\n"
            "    subprocess.run('ls', shell=True)\n"
            "    pickle.loads(b'x')\n"
            "    yaml.load('x')\n"
            "    requests.get('https://example.org')\n"
            "    cursor.execute(f'SELECT * FROM users WHERE id={user_id}')\n"
            "api_key = 'real-looking-key-123'\n"
        )
        result = review_source(code, "sample.py")
        rules = {(f.rule_id, f.line) for f in result.findings}
        self.assertEqual(rules, {
            ("PY007", 2), ("PY001", 4), ("PY006", 5), ("PY002", 7),
            ("PY003", 8), ("PY004", 9), ("PY005", 10), ("PY008", 11), ("PY009", 12),
        })
        self.assertEqual(result.findings[0].path, "sample.py")

    def test_syntax_and_suppression(self):
        result = review_source("def f(:\n", "bad.py")
        self.assertEqual(result.findings[0].rule_id, "PY012")
        self.assertEqual(review_source("eval('x')", policy=Policy(ignore=frozenset({"PY001"}))).findings, [])
        self.assertEqual(review_source("requests.get('x', timeout=5)").findings, [])
        self.assertEqual(review_source("yaml.load(data, Loader=yaml.SafeLoader)").findings, [])

    def test_ai_evidence_and_bounds(self):
        source = "def total(values):\n    return sum(values)\n"
        def mock(_chunk, _limit):
            return {"findings": [
                {"line": 2, "severity": "medium", "message": "Empty input returns zero.",
                 "suggestion": "Check whether empty values are valid.", "evidence": "return sum(values)"},
                {"line": 1, "severity": "high", "message": "Invented.",
                 "suggestion": "Ignore.", "evidence": "this is not present"},
                {"line": 999, "severity": "high", "message": "Out of bounds.",
                 "suggestion": "Ignore.", "evidence": "return sum(values)"},
            ]}
        result = review_source(source, ai=True, request_fn=mock)
        self.assertEqual([(f.rule_id, f.line) for f in result.findings], [("AI001", 2)])
        self.assertEqual(result.warnings, [])

    def test_ai_failure_retains_static_and_secret_guard(self):
        def broken(_chunk, _limit):
            raise ValueError("bad provider")
        result = review_source("eval('x')", ai=True, request_fn=broken)
        self.assertEqual(result.findings[0].rule_id, "PY001")
        self.assertIn("skipped", result.warnings[0])
        result = review_source("api_key = 'actual-secret-123'", ai=True, request_fn=broken)
        self.assertEqual(result.findings[0].rule_id, "PY009")
        self.assertIn("credential", result.warnings[0])
        result = review_source("api_key = 'actual-secret-123'", policy=Policy(
            ignore=frozenset({"PY009"})), ai=True, request_fn=broken)
        self.assertEqual(result.findings, [])
        self.assertIn("credential", result.warnings[0])

    def test_size_policy_and_renderers(self):
        with self.assertRaises(ValueError):
            review_source("x" * 20, policy=Policy(max_file_bytes=10))
        result = review_source("eval('1')", "x.py")
        self.assertEqual(json.loads(render(result, "json"))["findings"][0]["line"], 1)
        self.assertEqual(json.loads(render(result, "sarif"))["runs"][0]["results"][0]["ruleId"], "PY001")
        self.assertIn("file=x.py,line=1", render(result, "github"))

    def test_patch_lines(self):
        patch = "@@ -4,2 +4,3 @@\n context\n-old\n+new\n+++valid_code\n"
        self.assertEqual(added_lines(patch), {5, 6})

    def test_publisher_filters_diff_lines_and_deduplicates(self):
        calls = []
        responses = [
            {"head": {"sha": "a" * 40}, "state": "open"},
            [{"filename": "x.py", "status": "modified",
              "patch": "@@ -1,1 +1,2 @@\n old\n+eval('1')\n"}],
            [],
            {"id": 12},
        ]
        class Reply(BytesIO):
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
        def urlopen(request, timeout):
            calls.append((request.full_url, request.data))
            return Reply(json.dumps(responses.pop(0)).encode())
        result = review_source("old\neval('1')\neval('2')\n", "x.py")
        with patch("reviewline.github.urllib.request.urlopen", urlopen):
            outcome = publish(result, repository="owner/repo", number=7, token="token",
                              expected_head="a" * 40)
        self.assertEqual(outcome["posted"], 1)
        posted = json.loads(calls[-1][1])
        self.assertEqual([(c["path"], c["line"]) for c in posted["comments"]], [("x.py", 2)])
        self.assertEqual(posted["event"], "COMMENT")

    def test_cli_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.py"
            path.write_text("eval('1')\n", encoding="utf-8")
            command = [sys.executable, "-m", "reviewline.cli", str(path), "--format", "json"]
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 1, run.stderr)
            self.assertEqual(json.loads(run.stdout)["findings"][0]["rule_id"], "PY001")
            path.write_text("answer = 42\n", encoding="utf-8")
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == "__main__":
    unittest.main()
