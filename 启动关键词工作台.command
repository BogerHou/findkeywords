#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "需要 Python 3 才能启动本地工作台。"
  exit 1
fi
# Open the checked-in snapshot without needing bulk research input or crawling.
exec python3 scripts/serve_site.py
