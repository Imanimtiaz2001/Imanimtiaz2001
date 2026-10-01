import { useEffect, useRef, useState } from 'react';
import {
  ArrowDownToLine,
  ArrowUp,
  AudioLines,
  BookOpen,
  Check,
  ChevronRight,
  FileText,
  Headphones,
  Menu,
  Mic,
  Pencil,
  Plus,
  RotateCcw,
  Settings2,
  Square,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { api, ApiError } from './api';
import { useRecorder } from './useRecorder';
import type { Config, Conversation, Mode, Note, Submission, Turn } from './types';

const suggestions = [
  ['Understand an idea', 'Why would I choose PostgreSQL over MongoDB?'],
  ['Think it through', 'Explain how speech-to-text models work in simple terms.'],
  ['Ask your notes', 'What do my notes say about deployment?'],
];
const duration = (ms: number) =>
  ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;

export default function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);
  const [mode, setMode] = useState<Mode>('general');
  const [language, setLanguage] = useState('auto');
  const [voice, setVoice] = useState('coral');
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [trace, setTrace] = useState('');
  const [sidebar, setSidebar] = useState(false);
  const [panel, setPanel] = useState(false);
  const [autoPlay, setAutoPlay] = useState(true);
  const [pending, setPending] = useState<Submission | null>(null);
  const [activeAudio, setActiveAudio] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const questionRef = useRef<HTMLTextAreaElement | null>(null);
  const audioUploadRef = useRef<HTMLInputElement | null>(null);
  const noteUploadRef = useRef<HTMLInputElement | null>(null);
  const busyRef = useRef(false);
  const operation = useRef(0);
  const report = (err: unknown) => {
    if (err instanceof Error && err.name === 'AbortError') return;
    setError(err instanceof Error ? err.message : 'Something went wrong. Please retry.');
    setTrace(err instanceof ApiError ? err.traceId || '' : '');
  };
  const refreshLists = async () => {
    const [items, documents] = await Promise.all([
      api<Conversation[]>('/conversations'),
      api<Note[]>('/documents'),
    ]);
    setConversations(items);
    setNotes(documents);
  };
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const cfg = await api<Config>('/config');
        if (!alive) return;
        setConfig(cfg);
        setVoice(cfg.voices[0]);
        await refreshLists();
      } catch (err) {
        if (alive) report(err);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
      abortRef.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (turns.length || busy) bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turns, busy]);
  const stopAudio = () => {
    audioRef.current?.pause();
    audioRef.current = null;
    setActiveAudio(null);
  };
  const play = async (turn: Turn) => {
    stopAudio();
    if (!turn.audio_url) return;
    const audio = new Audio(turn.audio_url);
    audioRef.current = audio;
    audio.onended = () => setActiveAudio(null);
    audio.onerror = () => {
      setActiveAudio(null);
      setError('Speech could not be played. Try replaying or refresh the conversation.');
    };
    try {
      await audio.play();
      setActiveAudio(turn.id);
    } catch {
      setActiveAudio(null);
      setError('Automatic playback was blocked. Press Listen on the answer to play it.');
    }
  };
  const newConversation = () => {
    stopAudio();
    setCurrent(null);
    setTurns([]);
    setDraft('');
    setError('');
    setPending(null);
    setSidebar(false);
  };
  const openConversation = async (id: string) => {
    try {
      stopAudio();
      const value = await api<{ turns: Turn[] }>(`/conversations/${id}`);
      setCurrent(id);
      setTurns(value.turns);
      setError('');
      setPending(null);
      setSidebar(false);
    } catch (err) {
      report(err);
    }
  };
  const send = async (input: Submission) => {
    if (busyRef.current) return;
    if (!config?.ready) {
      setError(config?.setup_hint || 'The server is still connecting. Please wait.');
      return;
    }
    if (input.audio && input.audio.size > config.max_audio_bytes) {
      setError('Audio files must be 10 MB or smaller.');
      return;
    }
    busyRef.current = true;
    setBusy(true);
    setError('');
    setTrace('');
    setPending(input);
    stopAudio();
    const sequence = ++operation.current;
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      let id = current;
      if (!id) {
        const conversation = await api<Conversation>('/conversations', {
          method: 'POST',
          signal: controller.signal,
        });
        id = conversation.id;
        setCurrent(id);
      }
      const body = new FormData();
      body.set('request_id', input.requestId);
      body.set('mode', input.mode);
      body.set('language', input.language);
      body.set('voice', input.voice);
      if (input.audio) body.set('audio', input.audio);
      else body.set('text', input.text || '');
      const turn = await api<Turn>(`/conversations/${id}/turns`, {
        method: 'POST',
        body,
        signal: controller.signal,
      });
      if (sequence !== operation.current) return;
      setTurns((previous) => [...previous.filter((item) => item.id !== turn.id), turn]);
      setDraft('');
      setPending(null);
      await refreshLists();
      if (autoPlay && turn.audio_url) await play(turn);
    } catch (err) {
      if (sequence === operation.current) report(err);
    } finally {
      if (sequence === operation.current) {
        busyRef.current = false;
        setBusy(false);
        abortRef.current = null;
      }
    }
  };
  const submitText = (text = draft) => {
    if (text.trim())
      void send({ text: text.trim(), requestId: crypto.randomUUID(), mode, language, voice });
  };
  const recorder = useRecorder(
    (file) => {
      void send({ audio: file, requestId: crypto.randomUUID(), mode, language, voice });
    },
    setError,
    config?.max_audio_seconds || 60,
  );
  const cancel = () => {
    abortRef.current?.abort();
    operation.current++;
    busyRef.current = false;
    setBusy(false);
    setError(
      'Request cancelled in this browser. The server may finish the turn; reopen this conversation to recover it.',
    );
  };
  const uploadNote = async (file: File) => {
    setUploading(true);
    setError('');
    try {
      const body = new FormData();
      body.set('file', file);
      await api('/documents', { method: 'POST', body });
      await refreshLists();
      setPanel(true);
      setMode('knowledge');
    } catch (err) {
      report(err);
    } finally {
      setUploading(false);
    }
  };
  const removeNote = async (id: string) => {
    try {
      await api(`/documents/${id}`, { method: 'DELETE' });
      await refreshLists();
    } catch (err) {
      report(err);
    }
  };
  const removeConversation = async (id: string) => {
    if (!window.confirm('Delete this conversation and its generated audio?')) return;
    try {
      await api(`/conversations/${id}`, { method: 'DELETE' });
      if (current === id) newConversation();
      await refreshLists();
    } catch (err) {
      report(err);
    }
  };
  const exportHistory = async () => {
    if (!current) return;
    try {
      const data = await api(`/conversations/${current}/export`);
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
      );
      const link = document.createElement('a');
      link.href = url;
      link.download = 'voxdesk-conversation.json';
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      report(err);
    }
  };
  const retryVoice = async (turn: Turn) => {
    try {
      const body = new FormData();
      body.set('voice', voice);
      body.set('language', language);
      const refreshed = await api<Turn>(`/turns/${turn.id}/speech`, { method: 'POST', body });
      setTurns((previous) => previous.map((item) => (item.id === turn.id ? refreshed : item)));
      await play(refreshed);
    } catch (err) {
      report(err);
    }
  };
  const locked = busy || recorder.recording || recorder.starting;
  return (
    <div className="app-shell">
      {(sidebar || panel) && (
        <button
          className="scrim"
          aria-label="Close drawer"
          onClick={() => {
            setSidebar(false);
            setPanel(false);
          }}
        />
      )}
      <aside className={`sidebar ${sidebar ? 'open' : ''}`} aria-label="Conversation history">
        <a className="brand" href="/" aria-label="VoxDesk home">
          <span className="brand-icon">
            <AudioLines size={23} />
          </span>
          voxdesk<span className="brand-dot">.</span>
        </a>
        <p className="brand-caption">A little less typing.</p>
        <button className="new-button" disabled={locked} onClick={newConversation}>
          <Plus size={17} />
          New conversation
        </button>
        <div className="section-label">
          YOUR CONVERSATIONS <span>{conversations.length}</span>
        </div>
        <div className="history-list">
          {conversations.length === 0 ? (
            <p className="muted small history-empty">Your conversations will appear here.</p>
          ) : (
            conversations.map((item) => (
              <div key={item.id} className={`history-row ${current === item.id ? 'selected' : ''}`}>
                <button disabled={locked} onClick={() => void openConversation(item.id)}>
                  <AudioLines size={16} />
                  <span>{item.title}</span>
                </button>
                <button
                  disabled={locked}
                  className="icon-button history-delete"
                  aria-label={`Delete ${item.title}`}
                  onClick={() => void removeConversation(item.id)}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))
          )}
        </div>
        <div className="sidebar-bottom">
          <span className="avatar">VI</span>
          <div>
            <strong>Voice workspace</strong>
            <span>Private to this browser</span>
          </div>
          <Check size={15} />
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="icon-button mobile-menu"
              aria-label="Open history"
              onClick={() => setSidebar(true)}
            >
              <Menu size={20} />
            </button>
            <span className="top-title">Your voice, understood.</span>
            <span className={`status-pill ${config?.ready ? 'ready' : ''}`}>
              <i />
              {loading
                ? 'Connecting'
                : config?.provider === 'fixture'
                  ? 'Test fixtures'
                  : config?.ready
                    ? 'Ready to listen'
                    : 'Setup needed'}
            </span>
          </div>
          <div className="top-actions">
            <button
              className="text-button"
              aria-label="Knowledge & settings"
              onClick={() => setPanel(!panel)}
            >
              <BookOpen size={16} />
              <span>Knowledge & settings</span>
            </button>
            {current && (
              <button
                className="icon-button"
                title="Export conversation"
                aria-label="Export conversation"
                onClick={() => void exportHistory()}
              >
                <ArrowDownToLine size={18} />
              </button>
            )}
          </div>
        </header>
        {config && !config.ready && (
          <div className="setup-notice" role="status">
            <Settings2 size={18} />
            <div>
              <strong>Your voice provider needs setup.</strong>
              <span>{config.setup_hint} See the README for the exact command.</span>
            </div>
          </div>
        )}
        {config?.provider === 'fixture' && (
          <div className="setup-notice">
            Automated test mode. Responses and audio are deterministic fixtures, not live AI.
          </div>
        )}
        <div className="conversation-scroll">
          {turns.length === 0 ? (
            <section className="welcome">
              <div className="eyebrow">
                <span />
                SPACE TO THINK, OUT LOUD
              </div>
              <h1>
                Good ideas start
                <br />
                with a conversation<span>.</span>
              </h1>
              <p>
                Ask a question. Talk through an idea. Find an answer in your notes.
                <br className="desktop-break" /> Just speak — we’ll take it from here.
              </p>
              <div className="welcome-visual" aria-hidden="true">
                <div className="visual-orbit orbit-one" />
                <div className="visual-orbit orbit-two" />
                <div className="visual-orbit orbit-three" />
                <div className="voice-core">
                  <AudioLines size={36} />
                </div>
                <span className="visual-label">
                  <i />
                  Say what’s on your mind
                </span>
              </div>
              <div className="suggestions">
                {suggestions.map(([title, text], i) => (
                  <button
                    key={title}
                    disabled={locked}
                    onClick={() => {
                      setMode(i === 2 ? 'knowledge' : 'general');
                      setDraft(text);
                    }}
                  >
                    {i === 0 ? (
                      <BookOpen size={19} />
                    ) : i === 1 ? (
                      <AudioLines size={19} />
                    ) : (
                      <FileText size={19} />
                    )}
                    <strong>{title}</strong>
                    <span>{text}</span>
                    <ChevronRight className="suggestion-arrow" size={15} />
                  </button>
                ))}
              </div>
            </section>
          ) : (
            <div className="thread">
              {turns.map((turn) => (
                <article key={turn.id} className="turn">
                  <div className="user-message">
                    <span className="speaker-label">YOU</span>
                    <p>{turn.transcript}</p>
                    <button
                      className="transcript-edit"
                      disabled={locked}
                      onClick={() => {
                        setDraft(turn.transcript);
                        setPending(null);
                        questionRef.current?.focus();
                      }}
                    >
                      <Pencil size={11} />
                      Edit question
                    </button>
                  </div>
                  <div className="assistant-message">
                    <span className="assistant-avatar">
                      <AudioLines size={19} />
                    </span>
                    <div className="answer-body">
                      <div className="answer-heading">
                        <strong>VoxDesk</strong>
                        <span>
                          {turn.answer.abstained
                            ? 'Needs more context'
                            : turn.mode === 'knowledge'
                              ? 'Grounded in your notes'
                              : 'General answer'}
                        </span>
                      </div>
                      <p dir="auto">{turn.answer.text}</p>
                      {turn.answer.sources.length > 0 && (
                        <div className="sources">
                          {turn.answer.sources.map((source) => (
                            <details key={source.id}>
                              <summary>
                                <FileText size={13} />
                                {source.name}
                                <ChevronRight size={12} />
                              </summary>
                              <p>{source.excerpt}</p>
                            </details>
                          ))}
                        </div>
                      )}
                      {turn.warning && <p className="voice-warning">{turn.warning}</p>}
                      <div className="answer-actions">
                        {turn.audio_url ? (
                          <button
                            onClick={() =>
                              activeAudio === turn.id ? stopAudio() : void play(turn)
                            }
                          >
                            {activeAudio === turn.id ? (
                              <Square size={13} />
                            ) : (
                              <Headphones size={13} />
                            )}{' '}
                            {activeAudio === turn.id ? 'Stop' : 'Listen'}
                          </button>
                        ) : (
                          <button onClick={() => void retryVoice(turn)}>
                            <RotateCcw size={13} />
                            Retry voice
                          </button>
                        )}
                        <details className="timings">
                          <summary>
                            {duration(turn.timings.total_ms || 0)} <Settings2 size={12} />
                          </summary>
                          <div>
                            {Object.entries(turn.timings).map(([key, value]) => (
                              <span key={key}>
                                {key.replace('_ms', '').replace('_', ' ')} <b>{duration(value)}</b>
                              </span>
                            ))}
                          </div>
                        </details>
                      </div>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
          {busy && (
            <div className="processing" role="status">
              <span className="processing-dots">
                <i />
                <i />
                <i />
              </span>
              <div>
                <strong>
                  {pending?.audio
                    ? 'Listening, thinking, then speaking…'
                    : 'Finding a clear answer…'}
                </strong>
                <p>A short answer is on its way.</p>
              </div>
              <button className="text-button" onClick={cancel}>
                <X size={14} />
                Cancel
              </button>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
        <footer className="composer-area">
          {error && (
            <div className="error-box" role="alert">
              <div>
                {error}
                {trace && <small>Request: {trace}</small>}
              </div>
              {pending && !busy && (
                <button className="text-button" onClick={() => void send(pending)}>
                  <RotateCcw size={14} />
                  Retry
                </button>
              )}
              <button
                className="icon-button"
                aria-label="Dismiss error"
                onClick={() => setError('')}
              >
                <X size={15} />
              </button>
            </div>
          )}
          <div className="composer-meta">
            <div className="mode-switch" aria-label="Answer mode">
              <button
                className={mode === 'general' ? 'active' : ''}
                disabled={locked}
                onClick={() => setMode('general')}
              >
                General
              </button>
              <button
                className={mode === 'knowledge' ? 'active' : ''}
                disabled={locked}
                onClick={() => setMode('knowledge')}
              >
                <BookOpen size={12} />
                My notes <span>{notes.length}</span>
              </button>
            </div>
            <span className="keyboard-hint">
              {recorder.recording
                ? `Recording · ${recorder.seconds}s / ${config?.max_audio_seconds || 60}s`
                : mode === 'knowledge'
                  ? 'Answers grounded in your uploaded notes'
                  : 'Speak naturally. Or type below.'}
            </span>
          </div>
          <form
            className={`composer ${recorder.recording ? 'is-recording' : ''}`}
            onSubmit={(event) => {
              event.preventDefault();
              submitText();
            }}
          >
            <button
              type="button"
              className={`mic-button ${recorder.recording ? 'recording' : ''}`}
              disabled={busy || recorder.starting || loading}
              aria-label={recorder.recording ? 'Stop recording and send' : 'Start recording'}
              onClick={() => {
                stopAudio();
                recorder.recording ? recorder.stop() : void recorder.start();
              }}
            >
              {recorder.recording ? <Square size={19} fill="currentColor" /> : <Mic size={21} />}
            </button>
            {recorder.recording ? (
              <div className="recording-field">
                <span className="recording-wave" aria-hidden="true">
                  {Array.from({ length: 22 }, (_, i) => (
                    <i key={i} />
                  ))}
                </span>
                <span>Listening to you…</span>
                <button type="button" className="text-button" onClick={() => recorder.stop(true)}>
                  Discard
                </button>
              </div>
            ) : (
              <textarea
                ref={questionRef}
                aria-label="Your question"
                dir="auto"
                placeholder="Ask anything, or tap the mic…"
                maxLength={4000}
                rows={1}
                value={draft}
                disabled={busy || recorder.starting}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                    event.preventDefault();
                    submitText();
                  }
                }}
              />
            )}
            <button
              type="button"
              className="icon-button upload-audio"
              disabled={locked || loading}
              title="Upload recording"
              aria-label="Upload audio"
              onClick={() => audioUploadRef.current?.click()}
            >
              <Upload size={18} />
            </button>
            <button
              className="send-button"
              aria-label="Send question"
              disabled={!draft.trim() || locked || loading}
            >
              <ArrowUp size={19} />
            </button>
          </form>
          <input
            ref={audioUploadRef}
            type="file"
            className="hidden"
            accept="audio/*,.webm,.m4a"
            aria-label="Audio file"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file)
                void send({ audio: file, requestId: crypto.randomUUID(), mode, language, voice });
              event.target.value = '';
            }}
          />
          <div className="composer-footnote">
            <span>
              <AudioLines size={12} />
              Speak. Think. Keep going.
            </span>
            <span>AI-generated answers & voice · Verify important details.</span>
          </div>
        </footer>
      </main>
      <aside
        className={`knowledge-panel ${panel ? 'open' : ''}`}
        aria-label="Knowledge and settings"
      >
        <div className="panel-heading">
          <div>
            <span className="section-label">YOUR WORKSPACE</span>
            <h2>A little context helps.</h2>
          </div>
          <button
            className="icon-button"
            aria-label="Close settings"
            onClick={() => setPanel(false)}
          >
            <X size={18} />
          </button>
        </div>
        <p className="muted">Add notes to make answers specific to what you know.</p>
        <button
          className="upload-note"
          disabled={uploading || locked || loading}
          onClick={() => noteUploadRef.current?.click()}
        >
          <Upload size={21} />
          <strong>{uploading ? 'Indexing your note…' : 'Add a note'}</strong>
          <span>Text or Markdown · up to 256 KB</span>
        </button>
        <input
          className="hidden"
          ref={noteUploadRef}
          type="file"
          accept=".txt,.md"
          aria-label="Note file"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void uploadNote(file);
            event.target.value = '';
          }}
        />
        <div className="notes-list">
          {notes.map((note) => (
            <div className="note" key={note.id}>
              <FileText size={19} />
              <div>
                <strong>{note.name}</strong>
                <span>
                  {config?.embedding_identity && note.embedding_model !== config.embedding_identity
                    ? 'Provider changed · delete & re-upload'
                    : `${note.chunks} passages`}
                </span>
              </div>
              <button
                className="icon-button"
                aria-label={`Delete note ${note.name}`}
                disabled={locked}
                onClick={() => void removeNote(note.id)}
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
        <div className="settings-block">
          <span className="section-label">MAKE IT YOURS</span>
          <label>
            Spoken language
            <select
              aria-label="Spoken language"
              disabled={locked}
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
            >
              <option value="auto">Detect automatically</option>
              <option value="en">English</option>
              <option value="ur">Urdu</option>
            </select>
          </label>
          <label>
            Voice
            <select
              aria-label="Voice"
              disabled={locked}
              value={voice}
              onChange={(event) => setVoice(event.target.value)}
            >
              {(config?.voices || ['coral']).map((item) => (
                <option key={item} value={item}>
                  {item === 'local'
                    ? 'Local · eSpeak NG'
                    : item.charAt(0).toUpperCase() + item.slice(1)}
                </option>
              ))}
            </select>
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={autoPlay}
              onChange={(event) => setAutoPlay(event.target.checked)}
            />
            Play answers automatically
          </label>
        </div>
        <div className="privacy-note">
          <BookOpen size={17} />
          <strong>Your notes stay in your workspace.</strong>
          <p>
            Microphone input is processed, then discarded. History and generated speech stay until
            you delete the conversation. In cloud mode, audio, questions and relevant passages are
            sent to the AI provider.
          </p>
        </div>
        <span className="version-label">VoxDesk 1.0 · {config?.provider || 'connecting'}</span>
      </aside>
    </div>
  );
}
