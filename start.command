#!/bin/zsh
set -eu
cd "${0:A:h}"
if command -v curl >/dev/null && curl -fsS --max-time 1 http://127.0.0.1:8766/list >/dev/null 2>&1; then
  open http://127.0.0.1:8766
  exit 0
fi
if [[ -d ../ollama-runtime/models ]]; then
  zsh scripts/ensure_ollama.zsh || print "Ollama 未启动；仍可在连接设置里使用 API。"
fi
( for i in {1..40}; do
    if curl -fsS --max-time 1 http://127.0.0.1:8766/list >/dev/null 2>&1; then open http://127.0.0.1:8766; break; fi
    sleep .25
  done ) &
exec python3 app.py
