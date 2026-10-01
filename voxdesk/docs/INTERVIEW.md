# Explain the project, don't just list its tools

## 60-second walkthrough

“VoxDesk answers spoken questions and reads its answers back. I built separate transcription, reasoning and speech adapters so I can tell which stage failed and switch between cloud and local models. The web app supports microphone capture, notes, conversation history and playback. Knowledge mode combines BM25 and semantic retrieval, then LangGraph generates a structured answer and checks citation IDs. PostgreSQL keeps history, vectors and generated audio together. Database leases prevent overlapping writes, and request IDs make network retries safe. I tested ownership, corrupt/silent audio, provider timeouts, citation failures and browser recording. The local pipeline is measurable without paying for an API.”

## Decisions you should be able to defend

| Question | Short answer |
|---|---|
| Why three models? | Each modality has a distinct job. Separate stages make quality, latency and failures easier to diagnose. |
| Why not just a ChatGPT call? | Audio normalization, retrieval, typed output, citation validation, persistence and speech recovery surround the model call. |
| Why PostgreSQL instead of MongoDB? | The data has clear ownership and relationships. Transactions, constraints and pgvector fit those needs in one database. |
| Why not Qdrant too? | The corpus is capped at 200 chunks per workspace. Another service would add operations without a measured benefit. |
| Why LangGraph? | It makes retrieve, generate and validate explicit. The problem needs a bounded workflow, not a swarm of agents. |
| Why sessions instead of JWT? | It is an anonymous browser workspace. An opaque server-issued cookie avoids unnecessary token lifecycle complexity. |
| Why Redis? | Shared counters keep the request budget consistent when there are multiple API replicas. |
| Why not cache answers? | Answers depend on private notes and conversation history. Caching adds privacy and invalidation risks here. |
| Why complete turns instead of streaming? | It is easier to validate and persist a short complete answer. Realtime streaming would require different cancellation and commit rules. |
| What does structured output solve? | It gives a stable answer/citation/abstention contract. It does not prove the answer is true. |
| How do retries work? | The client keeps a request UUID. Identical retries return a saved turn; a different payload with that ID is rejected. |
| Why a leased database lock? | It serializes turns across processes and recovers after a crashed worker. An in-memory mutex would only protect one process. |
| What happens if TTS fails? | The text answer is saved with a warning. Retry voice regenerates only the missing speech. |
| Does cancellation stop inference? | It stops browser waiting. A server turn can finish, and native local transcription stays serialized until its thread exits. |
| Are all cited answers correct? | Citation IDs are verified against retrieved passages. Entailment and relevance still need live evaluation and review. |
| Is this production experience? | It is a personal project with production-oriented controls. I would not claim production traffic or uptime from it. |

## Skills this project demonstrates

Directly implemented: multimodal AI; STT/TTS integration; audio preprocessing; MediaRecorder; async FastAPI; typed structured outputs; LangGraph workflows; hybrid RAG; PostgreSQL/pgvector; migrations; Redis rate limits; concurrency and idempotency; provider adapters; guardrails; Prometheus observability; Docker; CI; Python and TypeScript testing; mobile/browser lifecycle handling.

The local STT engine uses CTranslate2; the local LLM is served by Ollama. Integrating those tools is not evidence that you trained a foundation model. Do not claim fine-tuning, production Kubernetes, Azure/GCP deployment, OCR, image understanding, realtime speech streaming, function-calling agents or millions of users from this project. Your existing professional experience can be discussed separately and accurately.

## Truthful CV bullets after reviewing the code yourself

- Built VoxDesk, a multimodal voice assistant chaining speech transcription, structured LLM answers and speech synthesis, with local and OpenAI provider adapters.
- Implemented private hybrid RAG using BM25, semantic embeddings and PostgreSQL/pgvector, coordinated through a LangGraph workflow with citation validation and abstention.
- Added conversation lock leases, request replay, recoverable TTS failures, Redis rate limits, Prometheus metrics, Docker deployment and automated API/browser checks.

Use measured test results from `docs/VERIFICATION.md` if you mention a number. Do not turn a synthetic speech smoke test into a claim of accuracy on natural noisy audio.

## Read the code in this order

1. `docs/DESIGN.md`: problem, scope, diagram, data model and API contract.
2. `backend/voxdesk/audio.py`: preprocessing boundaries and silence/duration checks.
3. `backend/voxdesk/providers.py`: cloud/local contracts, normalized PCM and structured output.
4. `backend/voxdesk/retrieval.py` and `workflow.py`: indexing, hybrid ranking and citation checks.
5. `backend/voxdesk/main.py`: ownership, transaction lifecycle, lease acquisition, replay and speech recovery.
6. `frontend/src/useRecorder.ts` and `App.tsx`: browser state, permissions, recording cleanup, aborts and playback.
7. Tests and evaluation scripts: what is verified, and where model judgment is still involved.

Official implementation references: [OpenAI transcription](https://developers.openai.com/api/docs/guides/speech-to-text), [speech synthesis](https://developers.openai.com/api/docs/guides/text-to-speech), [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md), [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview), [pgvector](https://github.com/pgvector/pgvector).
