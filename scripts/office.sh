#!/usr/bin/env bash
# Starts Trigger Point Office: builds the UI when needed, runs the API, and opens the page.
#   scripts/office.sh             modes from .env
#   scripts/office.sh --fixture   every provider on recorded fixtures, no network or credits
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "${1:-}" = "--fixture" ]; then
    export WEB_MODE=replay LLM_MODE=replay CRUSTDATA_MODE=replay
fi
if [ ! -d office/node_modules ]; then (cd office && npm install --no-audit --no-fund); fi
if [ ! -f office/dist/index.html ] || [ -n "$(find office/src -newer office/dist/index.html -print -quit)" ]; then
    (cd office && npm run build)
fi
TOKEN=$(uv run python -c "from trigger_point.office.routes import office_token; print(office_token())")
HOME_DIR="${TRIGGER_POINT_HOME:-$HOME/.trigger-point}"
PAGE="$HOME_DIR/open-office.html"
# A local redirect page keeps the token off the command line of the browser process.
(umask 077; printf '<script>location.replace("http://127.0.0.1:8000/#token=%s")</script>' "$TOKEN" > "$PAGE")
echo "Trigger Point Office: http://127.0.0.1:8000/#token=$TOKEN"
if [ -z "${TRIGGER_POINT_NO_OPEN:-}" ] && command -v open >/dev/null; then (sleep 2; open "$PAGE") & fi
exec uv run uvicorn trigger_point.api.app:create_default_app --factory --host 127.0.0.1 --port 8000 \
    --timeout-graceful-shutdown 2  # the live stream never ends by itself
