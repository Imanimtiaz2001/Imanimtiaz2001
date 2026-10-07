import React, { useCallback, useEffect, useRef, useState } from "react";
import ReactDOM from "react-dom/client";
import {
  ArrowDownToLine,
  ArrowUpRight,
  Check,
  ChevronRight,
  FileCheck2,
  FileText,
  LoaderCircle,
  LockKeyhole,
  ScanLine,
  ShieldCheck,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import type { Config, Fact, HistoryItem, MatchReport, RankingReport, RecordResult } from "./types";
import "./style.css";

const examples = [
  "standard",
  "sidebar",
  "scanned",
  "unicode",
  "year-only",
  "sparse",
];

const FactButton = ({
  fact,
  label,
  activeFact,
  onSelect,
}: {
  fact: Fact | null;
  label?: string;
  activeFact: Fact | null;
  onSelect: (fact: Fact) => void;
}) =>
  fact ? (
    <button
      className={`fact ${activeFact === fact ? "selected" : ""}`}
      title="Show source evidence"
      onClick={() => onSelect(fact)}
    >
      {label && <small>{label}</small>}
      <span>{fact.value}</span>
      <ArrowUpRight size={13} />
    </button>
  ) : (
    <span className="unknown">{label ? `${label}: ` : ""}Not found</span>
  );

function App() {
  const [mobileHistory, setMobileHistory] = useState(false);
  const [config, setConfig] = useState<Config | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [locked, setLocked] = useState(false);
  const [keyInput, setKeyInput] = useState("");
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [offset, setOffset] = useState(0);
  const [record, setRecord] = useState<RecordResult | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState("");
  const [activeFact, setActiveFact] = useState<Fact | null>(null);
  const [tab, setTab] = useState<"fields" | "json">("fields");
  const [consent, setConsent] = useState(false);
  const [workspace, setWorkspace] = useState<"parser" | "match" | "rank">("parser");
  const [jobDescription, setJobDescription] = useState("");
  const [matchReport, setMatchReport] = useState<MatchReport | null>(null);
  const [matchBusy, setMatchBusy] = useState(false);
  const [selectedCandidates, setSelectedCandidates] = useState<string[]>([]);
  const [ranking, setRanking] = useState<RankingReport | null>(null);
  const [dragging, setDragging] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const request = useCallback(
    async (path: string, options: RequestInit = {}) => {
      const headers = new Headers(options.headers);
      if (apiKey) headers.set("X-API-Key", apiKey);
      const response = await fetch(path, { ...options, headers });
      if (!response.ok) {
        if (response.status === 401) {
          setLocked(true);
          setRecord(null);
          setHistory([]);
        }
        const body = await response.json().catch(() => null);
        throw new Error(
          body?.error?.message ?? `Request failed (${response.status}).`,
        );
      }
      return response;
    },
    [apiKey],
  );

  const loadHistory = useCallback(
    async (page = 0) => {
      const response = await request(`/api/resumes?limit=8&offset=${page}`);
      const body = await response.json();
      setHistory(body.items);
      setOffset(page);
    },
    [request],
  );

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const response = await request("/api/config");
        const data = await response.json();
        if (!alive) return;
        setConfig(data);
        setLocked(false);
        setError("");
        await loadHistory();
      } catch (err) {
        if (alive) setError((err as Error).message);
      }
    })();
    return () => {
      alive = false;
    };
  }, [request, loadHistory]);

  useEffect(() => {
    if (!activeFact) return;
    document
      .getElementById(activeFact.line_ids[0])
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [activeFact]);

  function choose(selected: File | undefined) {
    if (!selected) return;
    setError("");
    if (!selected.name.toLowerCase().endsWith(".pdf")) {
      setError("Choose a PDF file.");
      return;
    }
    if (config && selected.size > config.max_upload_bytes) {
      setError("This PDF exceeds the upload limit.");
      return;
    }
    if (!selected.size) {
      setError("This file is empty.");
      return;
    }
    setFile(selected);
    setRecord(null);
    setActiveFact(null);
    setDeleteConfirm(false);
  }

  async function parse() {
    if (!file || busy) return;
    setBusy(true);
    setError("");
    setActiveFact(null);
    setDeleteConfirm(false);
    const body = new FormData();
    body.append("file", file);
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 180000);
    try {
      const response = await request(`/api/resumes?consent=${consent}`, {
        method: "POST",
        body,
        signal: controller.signal,
      });
      const result = await response.json();
      setRecord(result);
      setTab("fields");
      await loadHistory();
    } catch (err) {
      setError(
        (err as Error).name === "AbortError"
          ? "The request timed out. Refresh history before retrying; extraction may have completed."
          : (err as Error).message,
      );
    } finally {
      window.clearTimeout(timeout);
      setBusy(false);
    }
  }

  async function demo(caseName: string) {
    setActionBusy(true);
    setError("");
    try {
      const response = await request(`/api/examples/${caseName}`);
      choose(
        new File([await response.blob()], `${caseName}.pdf`, {
          type: "application/pdf",
        }),
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setActionBusy(false);
    }
  }

  async function open(id: string) {
    setActionBusy(true);
    setError("");
    try {
      const response = await request(`/api/resumes/${id}`);
      setRecord(await response.json());
      setMobileHistory(false);
      setActiveFact(null);
      setDeleteConfirm(false);
      setTab("fields");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setActionBusy(false);
    }
  }

  async function runMatch() {
    if (!record || !jobDescription.trim() || matchBusy) return;
    setMatchBusy(true);
    setError("");
    try {
      const params = new URLSearchParams({ job_description: jobDescription });
      const response = await request(`/api/matches/${record.id}?${params}`, {
        method: "POST",
      });
      setMatchReport(await response.json());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setMatchBusy(false);
    }
  }

  async function runRanking() {
    if (!selectedCandidates.length || !jobDescription.trim() || matchBusy) return;
    setMatchBusy(true);
    setError("");
    try {
      const response = await request("/api/rankings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resume_ids: selectedCandidates,
          job_description: jobDescription,
        }),
      });
      setRanking(await response.json());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setMatchBusy(false);
    }
  }

  function exportMatchReport() {
    if (!matchReport || !record) return;
    const blob = new Blob([JSON.stringify(matchReport, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `match-${record.id}.json`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function exportRanking() {
    if (!ranking) return;
    const rows = [
      ["rank", "candidate", "resume_id", "overall", "skills", "experience", "requirements"],
      ...ranking.candidates.map((item) => [
        item.rank,
        item.candidate_name ?? "",
        item.resume_id,
        item.report.overall_score,
        item.report.breakdown.skills,
        item.report.breakdown.experience,
        item.report.breakdown.requirements,
      ]),
    ];
    const csv = rows
      .map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(","))
      .join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "candidate-ranking.csv";
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function exportFile(format: string) {
    if (!record) return;
    setActionBusy(true);
    setError("");
    try {
      const response = await request(
        `/api/resumes/${record.id}/export?format=${format}`,
      );
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `resume-${record.id}.${format}`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setActionBusy(false);
    }
  }

  async function remove() {
    if (!record) return;
    setActionBusy(true);
    setError("");
    try {
      await request(`/api/resumes/${record.id}`, { method: "DELETE" });
      setRecord(null);
      setActiveFact(null);
      setDeleteConfirm(false);
      await loadHistory();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setActionBusy(false);
    }
  }

  const result = record?.result;
  const years = result
    ? result.experience.lower_years === result.experience.upper_years
      ? `${result.experience.lower_years}`
      : `${result.experience.lower_years}–${result.experience.upper_years}`
    : "—";

  return (
    <div className="app">
      <aside className={`sidebar ${mobileHistory ? "mobile-open" : ""}`}>
        <a className="brand" href="/" aria-label="ClearCV home">
          <div className="brand-icon">
            <ScanLine size={22} />
          </div>
          <span>
            ClearCV<small>RESUME INTELLIGENCE</small>
          </span>
        </a>
        <button
          className="mobile-history-toggle"
          aria-expanded={mobileHistory}
          onClick={() => setMobileHistory(!mobileHistory)}
        >
          Recent documents
        </button>
        <div className="nav-label">WORKSPACE</div>
        <button className={`nav-active ${workspace === "parser" ? "" : "nav-secondary"}`} onClick={() => setWorkspace("parser")}>
          <FileCheck2 size={18} /> Resume parser <span>01</span>
        </button>
        <button className={`nav-active ${workspace === "match" ? "" : "nav-secondary"}`} onClick={() => setWorkspace("match")}>
          <ScanLine size={18} /> CV ↔ JD Match <span>02</span>
        </button>
        <button className={`nav-active ${workspace === "rank" ? "" : "nav-secondary"}`} onClick={() => setWorkspace("rank")}>
          <FileText size={18} /> Rank candidates <span>03</span>
        </button>
        <div className="history-title">
          <span>RECENT DOCUMENTS</span>
          <button
            disabled={busy || actionBusy || locked}
            onClick={() => {
              setError("");
              loadHistory(offset).catch((err) => setError(err.message));
            }}
            aria-label="Refresh history"
          >
            ↻
          </button>
        </div>
        <div className="history">
          {history.length ? (
            history.map((item) => (
              <button
                key={item.id}
                disabled={busy || actionBusy}
                className={`history-item ${record?.id === item.id ? "active" : ""}`}
                onClick={() => open(item.id)}
              >
                <FileText size={16} />
                <span>
                  {item.name ?? "Unknown name"}
                  <small>
                    {new Date(item.created_at).toLocaleDateString()} ·{" "}
                    {item.provider}
                  </small>
                </span>
                <ChevronRight size={14} />
              </button>
            ))
          ) : (
            <p className="history-empty">
              Your parsed documents
              <br />
              will appear here.
            </p>
          )}
        </div>
        <div className="pages">
          <button
            disabled={offset === 0 || busy || actionBusy || locked}
            onClick={() =>
              loadHistory(Math.max(0, offset - 8)).catch((err) =>
                setError(err.message),
              )
            }
          >
            Previous
          </button>
          <button
            disabled={history.length < 8 || busy || actionBusy || locked}
            onClick={() =>
              loadHistory(offset + 8).catch((err) => setError(err.message))
            }
          >
            Next
          </button>
        </div>
        <div className="sidebar-note">
          <ShieldCheck size={21} />
          <strong>Evidence before assumptions.</strong>
          <p>Every extracted field links back to the document it came from.</p>
        </div>
        <div className="profile">
          <div className="avatar">CV</div>
          <span>
            Recruiting workspace<small>Single team · schema v1.0</small>
          </span>
        </div>
      </aside>

      <main>
        <header>
          <span>
            Workspace <ChevronRight size={13} /> <strong>{workspace === "parser" ? "Resume parser" : workspace === "match" ? "CV ↔ JD Match" : "Candidate ranking"}</strong>
          </span>
          <div className="mode">
            <i />
            {config?.provider === "openai"
              ? "AI extraction"
              : "Offline extraction"}
            <LockKeyhole size={14} />
          </div>
        </header>
        <section className="heading">
          <div className="eyebrow">DOCUMENTS → DECISIONS</div>
          <h1>
            Good data starts
            <br className="mobile-break" /> with a clear resume.
          </h1>
          <p>
            Turn a PDF into structured fields. Trace every detail to its source.
          </p>
          <div className="step-row">
            <span>
              <b>1</b> Upload a resume
            </span>
            <ChevronRight size={13} />
            <span>
              <b>2</b> Check the evidence
            </span>
            <ChevronRight size={13} />
            <span>
              <b>3</b> Export your data
            </span>
          </div>
        </section>

        {workspace === "match" && (
          <section className="match-workspace">
            <div className="eyebrow">MATCH INTELLIGENCE</div>
            <h2>Compare this CV with a job description</h2>
            <p>ClearCV compares requirements against evidence in the parsed resume. The score is decision support, not a hiring decision.</p>
            {!record ? (
              <div className="match-empty">Parse or open a resume from Recent Documents first.</div>
            ) : (
              <>
                <textarea
                  aria-label="Job description"
                  placeholder="Paste the complete job description here…"
                  value={jobDescription}
                  maxLength={30000}
                  onChange={(e) => {
                    setJobDescription(e.target.value);
                    setMatchReport(null);
                  }}
                />
                <button className="primary-button" disabled={!jobDescription.trim() || matchBusy} onClick={runMatch}>
                  {matchBusy ? <LoaderCircle className="spin" size={17} /> : <ScanLine size={17} />}
                  {matchBusy ? "Comparing…" : "Analyze match"}
                </button>
                {matchReport && (
                  <div className="match-report">
                    <div className="score-card"><strong>{matchReport.overall_score}%</strong><span>Overall alignment</span></div>
                    <div className="score-card"><strong>{matchReport.breakdown.skills}%</strong><span>Skills</span></div>
                    <div className="score-card"><strong>{matchReport.breakdown.experience}%</strong><span>Experience</span></div>
                    <div className="score-card"><strong>{matchReport.breakdown.responsibilities}%</strong><span>Responsibilities</span></div>
                    <div className="score-card"><strong>{matchReport.breakdown.education}%</strong><span>Education</span></div>
                    <div className="score-card"><strong>{matchReport.breakdown.requirements}%</strong><span>Required items</span></div>
                    <div className="match-column">
                      <h3>Matched requirements</h3>
                      {matchReport.matched.map((item, i) => <div className="match-item good" key={`m-${i}`}><Check size={15}/><span><b>{item.requirement}</b><small>{item.explanation} · Evidence: {item.cv_evidence}</small></span></div>)}
                    </div>
                    <div className="match-column">
                      <h3>Missing / gap areas</h3>
                      {matchReport.missing.map((item, i) => <div className="match-item gap" key={`g-${i}`}><X size={15}/><span><b>{item.requirement}</b><small>{item.explanation} · JD: {item.jd_evidence}</small></span></div>)}
                    </div>
                    <div className="match-suggestions">
                      <h3>Improvement guidance</h3>
                      <p><b>{matchReport.summary}</b></p>
                      {matchReport.suggestions.map((item, i) => <p key={i}>{item}</p>)}
                      <button className="secondary" onClick={exportMatchReport}>Export match JSON</button>
                    </div>
                  </div>
                )}
              </>
            )}
          </section>
        )}

        {workspace === "rank" && (
          <section className="match-workspace recruiter-workspace">
            <div className="eyebrow">RECRUITER INTELLIGENCE</div>
            <h2>Rank candidates against one job description</h2>
            <p>Select up to 50 parsed resumes. Ranking uses the same evidence-backed scoring and always requires human review.</p>
            <textarea
              aria-label="Recruiter job description"
              placeholder="Paste the job description used for all candidates…"
              value={jobDescription}
              maxLength={30000}
              onChange={(e) => { setJobDescription(e.target.value); setRanking(null); }}
            />
            <div className="candidate-picker">
              {history.map((item) => (
                <label key={item.id}>
                  <input
                    type="checkbox"
                    checked={selectedCandidates.includes(item.id)}
                    onChange={(e) => setSelectedCandidates((current) =>
                      e.target.checked
                        ? [...current, item.id].slice(0, 50)
                        : current.filter((id) => id !== item.id)
                    )}
                  />
                  <span>{item.name ?? "Unknown name"}<small>{item.id}</small></span>
                </label>
              ))}
            </div>
            <button className="primary-button" disabled={!selectedCandidates.length || !jobDescription.trim() || matchBusy} onClick={runRanking}>
              {matchBusy ? <LoaderCircle className="spin" size={17} /> : <ScanLine size={17} />}
              {matchBusy ? "Ranking…" : `Rank ${selectedCandidates.length} candidate(s)`}
            </button>
            {ranking && (
              <div className="ranking-results">
                <div className="ranking-header"><h3>Candidate ranking</h3><button className="secondary" onClick={exportRanking}>Export CSV</button></div>
                {ranking.candidates.map((candidate) => (
                  <div className="ranking-row" key={candidate.resume_id}>
                    <strong>#{candidate.rank}</strong>
                    <span>{candidate.candidate_name ?? "Unknown candidate"}<small>{candidate.report.summary}</small></span>
                    <b>{candidate.report.overall_score}%</b>
                    <button className="secondary" onClick={() => { open(candidate.resume_id); setWorkspace("match"); setMatchReport(candidate.report); }}>Review evidence</button>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {locked && (
          <form
            className="key-form"
            onSubmit={(e) => {
              e.preventDefault();
              setApiKey(keyInput);
            }}
          >
            <LockKeyhole size={18} />
            <label htmlFor="operator-key">Operator API key</label>
            <input
              id="operator-key"
              type="password"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              autoComplete="off"
              required
            />
            <button type="submit">Unlock workspace</button>
            <small>Kept in memory for this browser tab only.</small>
          </form>
        )}
        {error && (
          <div className="error" role="alert">
            <span>{error}</span>
            <button aria-label="Dismiss error" onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}

        <section className="upload-card">
          <div className="card-title">
            <h2>
              <Upload size={17} /> Add a document
            </h2>
            <span>PDF ONLY</span>
          </div>
          <div
            className={`dropzone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              if (!busy && !actionBusy) setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              if (!busy && !actionBusy && !locked)
                choose(e.dataTransfer.files[0]);
            }}
          >
            <div className="upload-symbol">
              {file ? <FileText size={25} /> : <Upload size={25} />}
            </div>
            <div>
              <strong>{file ? file.name : "Drop your resume here"}</strong>
              <p>
                {file
                  ? `${(file.size / 1024).toFixed(1)} KB · ready to extract`
                  : `Text or scanned PDF · up to ${config ? Math.round(config.max_upload_bytes / 1048576) : 10} MB, ${config?.max_pages ?? 10} pages`}
              </p>
            </div>
            <input
              ref={input}
              aria-label="Upload resume PDF"
              type="file"
              accept=".pdf,application/pdf"
              hidden
              onChange={(e) => {
                choose(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
            <button
              className="secondary"
              disabled={busy || actionBusy || locked || !config}
              onClick={() => input.current?.click()}
            >
              {file ? "Change file" : "Browse files"}
            </button>
          </div>
          <div className="upload-footer">
            <div>
              <span className="demo-label">Try a synthetic resume</span>
              <div className="demo-buttons">
                {examples.map((name) => (
                  <button
                    key={name}
                    disabled={busy || actionBusy || locked || !config}
                    onClick={() => demo(name)}
                  >
                    {name}
                  </button>
                ))}
              </div>
            </div>
            <button
              className="primary"
              disabled={
                !file ||
                busy ||
                actionBusy ||
                locked ||
                !config ||
                (config.provider === "openai" && !consent)
              }
              onClick={parse}
            >
              {busy ? (
                <>
                  <LoaderCircle className="spin" size={17} /> Extracting…
                </>
              ) : (
                <>
                  Extract resume <ArrowUpRight size={17} />
                </>
              )}
            </button>
          </div>
          {config?.provider === "openai" && (
            <label className="consent">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />{" "}
              I have permission to send this resume’s extracted text to OpenAI
              for processing.
            </label>
          )}
          <p className="privacy">
            <LockKeyhole size={12} /> Original PDFs are discarded after
            extraction. Text and results expire after{" "}
            {config?.retention_hours ?? 24} hours.
          </p>
        </section>

        {busy && (
          <div className="working" role="status">
            <LoaderCircle className="spin" size={18} /> Reading pages,
            extracting fields, and checking source evidence. Scanned PDFs may
            take longer.
          </div>
        )}

        {record && result ? (
          <>
            <section className="summary-grid">
              <div>
                <span>DOCUMENT NAME</span>
                <strong>{result.fields.name?.value ?? "Name not found"}</strong>
                <small>
                  <Check size={12} /> Schema validated · review required
                </small>
              </div>
              <div>
                <span>DATED EXPERIENCE</span>
                <strong>
                  {years} <em>years</em>
                </strong>
                <small>
                  {result.experience.dated_roles} dated roles · overlaps merged
                </small>
              </div>
              <div>
                <span>EXTRACTION</span>
                <strong>
                  {result.document.page_count}{" "}
                  <em>{result.document.page_count === 1 ? "page" : "pages"}</em>
                </strong>
                <small>
                  {result.provider === "local" ? "Offline rules" : result.model}{" "}
                  · {(result.timings_ms.total / 1000).toFixed(1)}s
                </small>
              </div>
            </section>
            <div className="results-grid">
              <section className="fields-card">
                <div className="result-header">
                  <div className="tabs">
                    <button
                      className={tab === "fields" ? "active" : ""}
                      onClick={() => setTab("fields")}
                    >
                      Structured fields
                    </button>
                    <button
                      className={tab === "json" ? "active" : ""}
                      onClick={() => setTab("json")}
                    >
                      JSON
                    </button>
                  </div>
                  <span className="validated">
                    <Check size={12} /> Validated
                  </span>
                </div>
                {tab === "json" ? (
                  <pre className="json">{JSON.stringify(result, null, 2)}</pre>
                ) : (
                  <div className="field-content">
                    <div className="field-section">
                      <h3>
                        01 <span>Candidate</span>
                      </h3>
                      <FactButton
                        activeFact={activeFact}
                        onSelect={setActiveFact}
                        fact={result.fields.name}
                        label="Name"
                      />
                    </div>
                    <div className="field-section">
                      <h3>
                        02 <span>Technical skills</span>
                        <small>{result.fields.skills.length} found</small>
                      </h3>
                      <div className="skill-list">
                        {result.fields.skills.map((skill, i) => (
                          <FactButton
                            activeFact={activeFact}
                            onSelect={setActiveFact}
                            key={i}
                            fact={skill}
                          />
                        ))}
                        {!result.fields.skills.length && (
                          <span className="unknown">No skills found</span>
                        )}
                      </div>
                    </div>
                    <div className="field-section">
                      <h3>
                        03 <span>Experience</span>
                      </h3>
                      {result.fields.employment.length ? (
                        result.fields.employment.map((job, i) => (
                          <div className="entry" key={i}>
                            <FactButton
                              activeFact={activeFact}
                              onSelect={setActiveFact}
                              fact={job.role}
                              label="Role"
                            />
                            <FactButton
                              activeFact={activeFact}
                              onSelect={setActiveFact}
                              fact={job.employer}
                              label="Employer"
                            />
                            <div className="dates">
                              <FactButton
                                activeFact={activeFact}
                                onSelect={setActiveFact}
                                fact={job.start}
                                label="From"
                              />
                              <FactButton
                                activeFact={activeFact}
                                onSelect={setActiveFact}
                                fact={job.end}
                                label="To"
                              />
                            </div>
                          </div>
                        ))
                      ) : (
                        <span className="unknown">
                          No employment entries found
                        </span>
                      )}
                      <p className="experience-policy">
                        {result.experience.policy} Calculated as of{" "}
                        {result.experience.as_of}.
                      </p>
                    </div>
                    <div className="field-section">
                      <h3>
                        04 <span>Education</span>
                      </h3>
                      {result.fields.education.length ? (
                        result.fields.education.map((item, i) => (
                          <div className="entry" key={i}>
                            <FactButton
                              activeFact={activeFact}
                              onSelect={setActiveFact}
                              fact={item.degree}
                              label="Degree"
                            />
                            <FactButton
                              activeFact={activeFact}
                              onSelect={setActiveFact}
                              fact={item.institution}
                              label="Institution"
                            />
                            <FactButton
                              activeFact={activeFact}
                              onSelect={setActiveFact}
                              fact={item.graduation}
                              label="Graduation"
                            />
                          </div>
                        ))
                      ) : (
                        <span className="unknown">
                          No education entries found
                        </span>
                      )}
                    </div>
                  </div>
                )}
                <div className="export-bar">
                  <span>
                    <ShieldCheck size={14} /> Fixed schema · v
                    {result.schema_version}
                  </span>
                  <button
                    disabled={actionBusy || busy}
                    onClick={() => exportFile("json")}
                  >
                    <ArrowDownToLine size={14} /> JSON
                  </button>
                  <button
                    disabled={actionBusy || busy}
                    onClick={() => exportFile("csv")}
                  >
                    <ArrowDownToLine size={14} /> CSV
                  </button>
                </div>
              </section>
              <section className="source-card">
                <div className="card-title">
                  <h2>
                    <ScanLine size={17} /> Source evidence
                  </h2>
                  <span>
                    {result.document.ocr_pages.length
                      ? "OCR + TEXT"
                      : "PDF TEXT"}
                  </span>
                </div>
                <p className="source-hint">
                  Click any extracted field to highlight its source.
                </p>
                {activeFact && (
                  <div className="quote">
                    <small>EXACT SOURCE QUOTE</small>
                    <p>“{activeFact.quote}”</p>
                    <span>{activeFact.line_ids.join(" · ")}</span>
                  </div>
                )}
                <div
                  className="source-lines"
                  tabIndex={0}
                  aria-label="Extracted source text"
                >
                  {result.document.lines.map((line, i, all) => (
                    <React.Fragment key={line.id}>
                      {(i === 0 || all[i - 1].page !== line.page) && (
                        <div className="page-label">PAGE {line.page}</div>
                      )}
                      <div
                        id={line.id}
                        className={`source-line ${activeFact?.line_ids.includes(line.id) ? "highlight" : ""}`}
                      >
                        <span>{line.id.split("-")[1]}</span>
                        <p>{line.text}</p>
                      </div>
                    </React.Fragment>
                  ))}
                </div>
              </section>
            </div>
            <section className="review">
              <div>
                <ShieldCheck size={18} />
                <h3>
                  Review notes <span>{result.warnings.length}</span>
                </h3>
              </div>
              <ul>
                {result.warnings.map((warning, i) => (
                  <li key={i}>{warning}</li>
                ))}
              </ul>
            </section>
            <div className="record-footer">
              <span>
                Expires {new Date(record.expires_at).toLocaleString()}
              </span>
              {deleteConfirm ? (
                <div className="confirm">
                  Delete this record and its text?
                  <button disabled={actionBusy || busy} onClick={remove}>
                    Delete now
                  </button>
                  <button onClick={() => setDeleteConfirm(false)}>
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  disabled={actionBusy || busy}
                  onClick={() => setDeleteConfirm(true)}
                >
                  <Trash2 size={14} /> Delete record
                </button>
              )}
            </div>
          </>
        ) : (
          !busy && (
            <section className="empty-state">
              <div className="empty-icon">
                <FileCheck2 size={27} />
              </div>
              <h2>A resume, with a little more clarity.</h2>
              <p>
                Upload a document to see its name, skills, experience,
                <br />
                and education — each connected to source evidence.
              </p>
              <div>
                <span>
                  <Check size={13} /> Schema validation
                </span>
                <span>
                  <Check size={13} /> Overlap-aware dates
                </span>
                <span>
                  <Check size={13} /> OCR support
                </span>
              </div>
            </section>
          )
        )}
        <footer>
          <span>ClearCV</span>
          <p>Built for careful extraction. Human review comes first.</p>
          <a href="/docs" target="_blank" rel="noreferrer">
            API reference <ArrowUpRight size={12} />
          </a>
        </footer>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
