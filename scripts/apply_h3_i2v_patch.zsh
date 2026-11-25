#!/bin/zsh
set -eu
PROJECT="${0:A:h:h}"
RUNTIME="${H3_RUNTIME:-${PROJECT:h}/h3-runtime}"
for patch_name in h3-low-memory-i2v h3-reference-image-processor; do
  patch_file="$PROJECT/patches/$patch_name.patch"
  if git -C "$RUNTIME" apply --reverse --check "$patch_file" 2>/dev/null; then
    print "已安装 $patch_name"
  elif git -C "$RUNTIME" apply --check "$patch_file"; then
    git -C "$RUNTIME" apply "$patch_file"
    print "已应用 $patch_name"
  else
    print -u2 "$patch_name 与当前 H3 源码不匹配，请检查运行时版本。"
    exit 1
  fi
done
