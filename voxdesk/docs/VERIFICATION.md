# Verification evidence

The checked-in reports distinguish real model execution from deterministic tests. No OpenAI API key was available during this build, so OpenAI calls were verified against request/response contracts with a mocked HTTP transport rather than billed live inference.

## Completed local checks

- Backend: 48 passing tests with 2 infrastructure tests reserved for real PostgreSQL/Redis services.
- Frontend: 6 component tests pass; TypeScript and production Vite build pass.
- Browser: 4 Playwright tests pass across desktop and mobile Chromium. They exercise text submission, note indexing, sources, audio playback, history, export and actual MediaRecorder capture through the real FFmpeg decoder. AI adapters are explicitly fixtures in these browser tests.
- Database: initial Alembic migration and metadata drift check pass against SQLite.
- Offline retrieval regression: 8 cases pass. Vectors are deterministic token hashes; this is not a semantic model benchmark. See [offline report](offline-evaluation.json).
- Live local voice: faster-whisper base, Qwen2.5 3B, nomic embeddings and eSpeak NG completed a real speech → answer → speech run with a grounded citation and playable WAV. The input was synthetic English speech; this is not an accent/noise accuracy measurement. See [live smoke report](live-smoke.json).
- Live local answer evaluation: all 8 sample cases pass retrieval, citation, abstention and lexical key-concept gates. See [live report](live-evaluation.json) for exact outputs and pass flags. The lexical key-concept gate tolerates ordinary word inflections; it is not a semantic entailment judge.

## Bugs caught during validation

A real run exposed faster-whisper/PyAV decode API incompatibility. The local adapter now consumes the already-normalized PCM samples directly, avoiding a second media decode. A cancellation regression test confirms that a running native transcription retains its model lock. Browser testing caught the mobile settings button losing its accessible name when its visible label was hidden. That button now has a persistent ARIA label. The live model evaluation identified history contamination and a misanswered retry question; the prompt now gives the current question last, treats earlier answers as non-authoritative, and requires concise answers from current passages. Independent golden cases now use fresh conversations.

A retrieved passage is allowed to be relevant to a topic without being enough to answer it. The injection test can retrieve a passage mentioning a database password; the final answer must still abstain instead of inventing a secret. Out-of-domain retrieval uses a conservative semantic threshold. These sample results are regressions, not universal claims about all questions.

## Infrastructure gate

GitHub Actions additionally checks the PostgreSQL/pgvector distance path and shared Redis budget, validates both Compose profiles, and builds the container. The corresponding service tests require those real services rather than pretending SQLite is PostgreSQL. Local Docker execution was unavailable in the build environment. The initial repository run is checked before merging.

## Reproduce

Use the commands in the README. Run `scripts/live_smoke.py` and `scripts/evaluate.py --live` with an actual configured local or cloud provider. Live cloud calls can incur charges. Repeat speech evaluation on representative human recordings before making accuracy claims; no such benchmark is asserted here.
