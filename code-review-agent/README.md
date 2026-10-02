# Reviewline

An evidence-checked code review agent for Python. It returns specific, physical line comments from deterministic AST checks and an optional LLM pass. It can review a local file, emit JSON or SARIF for tooling, write GitHub Actions annotations, and post inline comments on changed pull request lines.

## Quick start

Requires Python 3.11 or newer. The default reviewer has no runtime dependencies.

```bash
python -m pip install -e .
reviewline examples/unsafe.py
reviewline examples/unsafe.py --format json
python -m unittest discover -s tests -v
```

Example output:

```text
examples/unsafe.py:6: MEDIUM PY005 HTTP request has no timeout.
  Set a finite connect/read timeout to avoid hanging indefinitely.
examples/unsafe.py:7: HIGH PY002 Subprocess runs through a shell.
  Pass an argument list with shell=False; validate untrusted arguments.
```

The CLI returns 0 for no findings at the selected threshold, 1 for findings, and 2 for input or configuration errors. The default threshold is medium; use `--fail-on low` or `--fail-on high` to change it. `-` reads stdin.

## Optional AI review

The static checks always run. To request additional contextual findings:

```bash
export REVIEWLINE_API_KEY="your-provider-key"
export REVIEWLINE_LLM_MODEL="gpt-4o-mini"
reviewline my_file.py --ai --format json
```

By default, this calls an OpenAI-compatible chat completions endpoint at `https://api.openai.com/v1/chat/completions`. Set `REVIEWLINE_LLM_URL` to a compatible HTTPS endpoint or a loopback HTTP endpoint. The provider must support `response_format: {"type": "json_object"}`. The model name is configurable; availability and billing depend on the provider.

`--ai` sends the source to the configured provider. The agent refuses this stage when the hardcoded credential rule triggers. That heuristic cannot identify every secret, so only opt in for code approved for external processing. Source comments are treated as untrusted data, and the model gets no tools. Candidate comments are discarded unless their quoted evidence appears on the exact claimed line. Model failures become warnings; static findings remain available.

## Rules

| ID | Severity | Detection |
| --- | --- | --- |
| PY001 | High | `eval` or `exec` calls |
| PY002 | High | `subprocess` call with literal `shell=True` |
| PY003 | High | `pickle.load` or `loads` |
| PY004 | High | `yaml.load` without a recognized safe loader |
| PY005 | Medium | `requests` call without a timeout keyword |
| PY006 | Medium | Bare `except` |
| PY007 | Medium | Mutable function default |
| PY008 | High | Dynamically interpolated SQL passed to `execute` |
| PY009 | High | Possible hardcoded credential assigned to a sensitive name |
| PY010 | Low | Line beyond configured length |
| PY011 | Medium | Broad exception silently ignored |
| PY012 | High | Python syntax error |
| AI001 | Model supplied | Contextual issue with validated line evidence |

Rules are intentionally narrow. Aliased imports, data flow through variables, and all possible credentials are not fully resolved. Review a finding before changing security-sensitive code.

## Policy and output

Use `--policy reviewline.toml` to set `ignore`, `max_line_length`, `max_file_bytes`, `llm_max_lines`, and `llm_max_findings`. Unknown options and rule IDs fail fast. Output formats: `text`, `json`, `sarif`, and `github`.

```bash
reviewline app.py --policy reviewline.toml --format sarif > review.sarif
reviewline app.py --format github
```

## Pull request comments

The included workflow reviews changed Python files on pull requests. Its privileged job runs code from the repository's base branch and reads submitted files through GitHub's API as data. It posts only on added diff lines, skips deleted or oversized files, and uses a revision fingerprint to avoid duplicate reviews. A repository's Actions policy must permit `pull_request_target`; the workflow needs `pull-requests: write`.

For manual publishing from a checkout:

```bash
export GITHUB_REPOSITORY="owner/repo"
export REVIEWLINE_PR_NUMBER="123"
export GITHUB_TOKEN="a-token-with-pull-request-write-access"
reviewline relative/path/in/repo.py --publish-pr
```

Only findings on added lines in that pull request are published. GitHub API/network errors surface as operational errors; the token is never included in output.

## Design and evaluation

See [architecture](docs/architecture.md) for problem framing, data flow, trust boundaries, data model, and tradeoffs. The repository's unit tests exercise every static rule, syntax errors, suppressions, model evidence validation and failure isolation, format serialization, diff line mapping, and the installed CLI. There is deliberately no database, cache, or web server: a single-file review has no state to store and does not need authentication.

## Portfolio description

Built a Python code review agent with AST-based security/style checks, opt-in evidence-validated LLM comments, SARIF/JSON output, and secure GitHub pull request inline reviews. This is a project implementation; it is not a claim of production deployment or measured model accuracy.

