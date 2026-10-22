#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

_TARGET=""

_az_fixup_path() {
  for _pybin in \
    /Library/Frameworks/Python.framework/Versions/3.14/bin \
    /Library/Frameworks/Python.framework/Versions/3.13/bin \
    /Library/Frameworks/Python.framework/Versions/3.12/bin \
    "$HOME/.local/bin" \
    "$HOME/Library/Python/3.13/bin" \
    "$HOME/Library/Python/3.12/bin"; do
    if [[ -x "$_pybin/az" ]]; then
      export PATH="$_pybin:$PATH"
      return 0
    fi
  done
  return 1
}

_prompt_menu() {
  printf '\n=== angular-dashboard-backend infra-down ===\n\n'
  printf '  [1] Stop local uvicorn (kill process on :8000)\n'
  printf '  [2] Destroy Azure Container Apps stack\n'
  printf '\nChoice [1/2, default 1]: '
  read -r _MODE
  case "${_MODE:-1}" in
    2) _TARGET="remote" ;;
    *) _TARGET="local" ;;
  esac
}

_stop_local() {
  local PID
  PID=$(lsof -ti :8000 2>/dev/null || true)
  if [[ -n "$PID" ]]; then
    kill "$PID"
    printf 'Killed process on :8000 (PID %s)\n' "$PID"
  else
    printf 'No process found on :8000\n'
  fi
}

_destroy_azure() {
  if ! command -v az >/dev/null 2>&1; then _az_fixup_path; fi
  if [[ -f "$ROOT_DIR/.env.azure" ]]; then
    set -a; source "$ROOT_DIR/.env.azure"; set +a
  fi

  APP_NAME="${APP_NAME:-ang-dash-backend}"
  RG_NAME="${RG_NAME:-${APP_NAME}-rg}"

  printf '\nDeleting resource group %s…\n' "$RG_NAME"
  az group delete --name "$RG_NAME" --yes --no-wait
  printf 'Deletion initiated (runs in background).\n'
  rm -f "$ROOT_DIR/.env.azure"
}

_prompt_menu
if [[ "$_TARGET" == "local" ]]; then
  _stop_local
else
  _destroy_azure
fi
