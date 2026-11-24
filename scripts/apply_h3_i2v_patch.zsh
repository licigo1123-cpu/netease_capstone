#!/bin/zsh
set -eu
PROJECT="${0:A:h:h}"
RUNTIME="${H3_RUNTIME:-${PROJECT:h}/h3-runtime}"
PATCH="$PROJECT/patches/h3-low-memory-i2v.patch"
if git -C "$RUNTIME" apply --reverse --check "$PATCH" 2>/dev/null; then
  print 'H3 低内存图生视频补丁已安装。'
elif git -C "$RUNTIME" apply --check "$PATCH"; then
  git -C "$RUNTIME" apply "$PATCH"
  print 'H3 低内存图生视频补丁安装完成。'
else
  print 'H3 版本与补丁不匹配，请保留当前代码并检查版本。'
  exit 1
fi
