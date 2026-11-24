#!/bin/zsh
set -eu
PROJECT="${0:A:h:h}"
RUNTIME="${PROJECT:h}/ollama-runtime"
export STORY_MODEL="${STORY_MODEL:-qwen3.5:4b}"
export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
if curl --fail --silent --max-time 3 "$OLLAMA_HOST/api/tags" >/dev/null; then
  exit 0
fi
OLLAMA_BIN="$(command -v ollama || true)"
if [[ -z "$OLLAMA_BIN" ]]; then
  for candidate in /opt/homebrew/bin/ollama /usr/local/bin/ollama /Applications/Ollama.app/Contents/Resources/ollama; do
    if [[ -x "$candidate" ]]; then OLLAMA_BIN="$candidate"; break; fi
  done
fi
if [[ -z "$OLLAMA_BIN" ]]; then
  print -u2 '尚未安装 Ollama，请先安装 Ollama 并拉取所选 Qwen 模型'
  exit 1
fi
# Do not launch a local daemon for an explicitly configured remote endpoint.
if [[ "$OLLAMA_HOST" != 'http://127.0.0.1:11434' && "$OLLAMA_HOST" != 'http://localhost:11434' ]]; then
  print -u2 "Ollama 服务未连接：$OLLAMA_HOST"
  exit 1
fi
mkdir -p "$RUNTIME/models"
export OLLAMA_MODELS="$RUNTIME/models"
export OLLAMA_KEEP_ALIVE=0
export OLLAMA_NUM_PARALLEL=1
nohup "$OLLAMA_BIN" serve >"$RUNTIME/server.log" 2>&1 &
for attempt in {1..30}; do
  if curl --fail --silent --max-time 1 "$OLLAMA_HOST/api/tags" >/dev/null; then
    print "Ollama 已启动，日志：$RUNTIME/server.log"
    exit 0
  fi
  sleep 1
done
print -u2 "Ollama 启动失败，请检查 $RUNTIME/server.log"
exit 1
