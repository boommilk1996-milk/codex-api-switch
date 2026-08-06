#!/usr/bin/env sh
# 一键发布：推送 GitHub（origin）+ Gitee（gitee）
# 用法：在仓库根目录执行 ./push-all.sh
set -e

echo "==> GitHub (origin)"
git push origin main

echo "==> Gitee (gitee)"
git push gitee main

echo "OK: 两个平台均已同步。"
