#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v ollama >/dev/null || { echo 'Install Ollama from https://ollama.com/download first, or use Docker Compose local mode.'; exit 1; }
command -v espeak-ng >/dev/null || { echo 'Install espeak-ng first (Linux: sudo apt-get install espeak-ng).'; exit 1; }
command -v ffmpeg >/dev/null || { echo 'Install ffmpeg first.'; exit 1; }
uv sync --frozen --extra local --extra dev
voxdesk_chat_model=$(uv run --no-sync python -c 'from voxdesk.config import Settings; print(Settings().local_chat_model)')
voxdesk_embedding_model=$(uv run --no-sync python -c 'from voxdesk.config import Settings; print(Settings().local_embedding_model)')
ollama pull "$voxdesk_chat_model"
ollama pull "$voxdesk_embedding_model"
uv run --no-sync python -c "from voxdesk.config import Settings; from faster_whisper import WhisperModel; cfg=Settings(); WhisperModel(cfg.whisper_model, device=cfg.whisper_device, compute_type='int8'); print('Local speech model is ready.')"
