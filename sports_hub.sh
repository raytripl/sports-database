#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="./.venv/Scripts/python.exe"
if [[ ! -x "$PYTHON" ]]; then PYTHON="python"; fi

COMMAND="${1:-daily}"
shift || true
case "$COMMAND" in
  run) exec "$PYTHON" -m src.workflows.run_sports_hub "$@" ;;
  slips) exec "$PYTHON" -m src.decisions.build_daily_research_slips "$@" ;;
  daily) exec "$PYTHON" -m src.workflows.daily_sports_hub "$@" ;;
  import-downloads) exec "$PYTHON" -m src.imports.import_downloaded_pools "$@" ;;
  update-lines) exec "$PYTHON" -m src.sports_hub update-lines "$@" ;;
  research) exec "$PYTHON" -m src.sports_hub research "$@" ;;
  status) exec "$PYTHON" -m src.sports_hub status "$@" ;;
  grade) exec "$PYTHON" -m src.workflows.grade_daily_slate "$@" ;;
  audit) exec "$PYTHON" -m src.workflows.audit_completed_slate "$@" ;;
  dashboard) exec "$PYTHON" -m streamlit run app.py "$@" ;;
  test) exec "$PYTHON" -m pytest -q "$@" ;;
  *) echo "Usage: ./sports_hub.sh {run|slips|daily|import-downloads|update-lines|research|status|grade|audit|dashboard|test}" >&2; exit 2 ;;
esac
