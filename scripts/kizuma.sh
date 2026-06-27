#!/usr/bin/env bash
set -euo pipefail

# Uso:
#   bash scripts/kizuma.sh web
#   bash scripts/kizuma.sh analyze "NOME DO CLIENTE" [--all-history|--lookback-months 6|--lookback-days 90] [--ticket-limit 80]

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -d /opt/homebrew/opt/expat/lib ]]; then
  export DYLD_LIBRARY_PATH="/opt/homebrew/opt/expat/lib${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}"
fi

if [[ ! -f .venv/bin/activate ]]; then
  echo "[kizuma] venv não encontrado. Rode: bash kiro/setup_env.sh"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

mode="${1:-web}"
shift || true

case "$mode" in
  web)
    python -m customer_health.webapp --host 127.0.0.1 --port 8501
    ;;
  analyze)
    if [[ $# -lt 1 ]]; then
      echo "[kizuma] informe o nome do cliente."
      echo "[exemplo] bash scripts/kizuma.sh analyze \"Cliente XPTO\" --all-history --ticket-limit 80"
      exit 2
    fi
    customer_name="$1"
    shift
    python -m customer_health --customer-name "$customer_name" "$@"
    ;;
  *)
    echo "[kizuma] modo inválido: $mode"
    echo "[kizuma] use: web | analyze"
    exit 2
    ;;
esac
