# VoxDesk operating notes

## Database
VoxDesk uses PostgreSQL because ACID transactions, foreign key constraints and pgvector semantic search belong in one transactional system. PostgreSQL serializes turn writes with a conversation lock lease. SQLite is a portable development option for small workspaces.

## Audio privacy
Microphone recordings are transient. VoxDesk decodes and transcribes them, then discards the recording. Generated answer audio stays with the conversation until that conversation is deleted. Cloud mode sends recordings, questions and relevant note passages to OpenAI. Local mode runs speech and language models on the host.

## Deployment
The local Docker Compose setup runs FastAPI, PostgreSQL, Redis and Ollama. Model initialization downloads qwen2.5:3b, nomic-embed-text and faster-whisper base before the API starts. Production requires HTTPS, secure cookies, PostgreSQL, Redis and a unique database password. Redis stores request rate limits, not private answers.

## Failure recovery
When speech synthesis fails, the text answer is saved and Retry voice can regenerate audio. Request IDs prevent duplicate saved turns for retries. Knowledge mode must cite retrieved passage IDs or abstain. General mode can answer without documents.
