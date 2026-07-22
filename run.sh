#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if ! curl -sf http://127.0.0.1:11434 >/dev/null 2>&1; then
  echo "Starting Ollama..."
  if command -v systemctl >/dev/null && systemctl --user list-unit-files ollama.service >/dev/null 2>&1; then
    systemctl --user start ollama.service
  else
    nohup "$HOME/.local/ollama/bin/ollama" serve >/dev/null 2>&1 &
    disown
  fi

  for _ in $(seq 1 30); do
    curl -sf http://127.0.0.1:11434 >/dev/null 2>&1 && break
    sleep 1
  done
fi

exec python3 main.py "$@"
