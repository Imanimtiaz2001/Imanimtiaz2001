export type Mode = 'general' | 'knowledge';
export type Source = {
  id: string;
  document_id: string;
  name: string;
  excerpt: string;
  score: number;
};
export type Turn = {
  id: string;
  request_id: string;
  transcript: string;
  answer: { text: string; sources: Source[]; abstained: boolean };
  timings: Record<string, number>;
  audio_url: string | null;
  warning: string | null;
  mode: Mode;
  created_at: string;
};
export type Conversation = { id: string; title: string; created_at?: string };
export type Note = { id: string; name: string; chunks: number; embedding_model: string };
export type Config = {
  provider: string;
  ready: boolean;
  voices: string[];
  languages: string[];
  max_audio_seconds: number;
  max_audio_bytes: number;
  setup_hint: string;
  voice_disclosure: string;
  prompt_version: string;
  embedding_identity: string;
};
export type Submission = {
  text?: string;
  audio?: File;
  requestId: string;
  mode: Mode;
  language: string;
  voice: string;
};
