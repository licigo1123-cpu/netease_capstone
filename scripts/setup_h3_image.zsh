#!/bin/zsh
set -eu
PROJECT="${0:A:h:h}"
IMAGE_RUNTIME="${H3_IMAGE_RUNTIME:-${PROJECT:h}/h3-image-runtime}"
PY="${PROJECT:h}/h3-runtime/.venv/bin/python"
mkdir -p "$IMAGE_RUNTIME"
[[ -x "$IMAGE_RUNTIME/.venv/bin/python" ]] || "$PY" -m venv "$IMAGE_RUNTIME/.venv"
"$IMAGE_RUNTIME/.venv/bin/python" -m pip install 'h3-image-mlx==0.1.0a10' 'httpx[socks]'
print 'H3 Image 是独立模型，约需额外 49.30 GB。请阅读模型许可：'
print 'https://huggingface.co/MiniMaxAI/MiniMax-H3-Image/blob/main/LICENSE'
read 'answer?阅读并接受许可后，输入 YES 开始下载：'
[[ "$answer" == YES ]] || exit 0
"$IMAGE_RUNTIME/.venv/bin/h3-image-mlx" fetch --models "$IMAGE_RUNTIME/models" --source huggingface
"$IMAGE_RUNTIME/.venv/bin/h3-image-mlx" verify --models "$IMAGE_RUNTIME/models"
print 'H3 Image 已就绪，重启漫剧工作台即可生成角色三视图。'
