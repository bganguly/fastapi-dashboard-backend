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
  printf '\n=== angular-dashboard-backend ===\n\n'
  printf '  [1] Local  — uvicorn on localhost:8000\n'
  printf '  [2] Azure  — Azure Container Apps\n'
  printf '\nChoice [1/2, default 2]: '
  read -r _MODE
  case "${_MODE:-2}" in
    1) _TARGET="local" ;;
    *) _TARGET="remote" ;;
  esac
}

_deploy_local() {
  command -v python3 >/dev/null 2>&1 || { printf 'Python 3 required.\n' >&2; exit 1; }
  if [[ -f "$ROOT_DIR/.env" ]]; then
    set -a; source "$ROOT_DIR/.env"; set +a
  fi
  cd "$ROOT_DIR"
  pip3 install -q -r requirements.txt
  printf '\nStarting uvicorn on :8000…\n'
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
}

_ensure_az() {
  if ! command -v az >/dev/null 2>&1; then _az_fixup_path; fi
  if ! command -v az >/dev/null 2>&1; then
    printf '\nInstalling az CLI via pip…\n'
    pip3 install --quiet azure-cli && _az_fixup_path
  fi
  if ! command -v az >/dev/null 2>&1; then
    printf 'az CLI not found. Install: pip3 install azure-cli\n' >&2; exit 1
  fi
}

_check_az_auth() {
  local ACTIVE_ACCOUNT
  ACTIVE_ACCOUNT=$(az account show --query user.name -o tsv 2>/dev/null || true)
  if [[ -z "$ACTIVE_ACCOUNT" ]]; then
    az login
  fi
  printf 'Azure account: %s\n' "$(az account show --query user.name -o tsv)"
}

_deploy_azure() {
  if [[ -f "$ROOT_DIR/.env" ]]; then
    set -a; source "$ROOT_DIR/.env"; set +a
  fi
  if [[ -f "$ROOT_DIR/.env.azure" ]]; then
    set -a; source "$ROOT_DIR/.env.azure"; set +a
  fi

  AZ_LOCATION="${AZ_LOCATION:-eastus2}"
  APP_NAME="${APP_NAME:-ang-dash-backend}"
  RG_NAME="${RG_NAME:-${APP_NAME}-rg}"

  printf '\n=== deployment config ===\n'
  printf '  Location  : %s\n' "$AZ_LOCATION"
  printf '  App name  : %s\n' "$APP_NAME"
  printf '  RG name   : %s\n' "$RG_NAME"

  printf '\n=== ensuring resource group ===\n'
  az group create --name "$RG_NAME" --location "$AZ_LOCATION" --output none

  printf '\n=== deploying to Azure Container Apps ===\n'
  cd "$ROOT_DIR"

  local DB_URL="${DATABASE_URL:-}"
  if [[ -z "$DB_URL" ]]; then
    printf 'ERROR: DATABASE_URL not set in .env\n' >&2; exit 1
  fi

  az containerapp up \
    --name "$APP_NAME" \
    --resource-group "$RG_NAME" \
    --location "$AZ_LOCATION" \
    --source . \
    --target-port 8000 \
    --ingress external \
    --min-replicas 0 \
    --max-replicas 3 \
    --env-vars "DATABASE_URL=${DB_URL}"

  local BACKEND_URL
  BACKEND_URL=$(az containerapp show \
    --name "$APP_NAME" \
    --resource-group "$RG_NAME" \
    --query properties.configuration.ingress.fqdn -o tsv 2>/dev/null || true)

  if [[ -n "$BACKEND_URL" ]]; then
    BACKEND_URL="https://${BACKEND_URL}"
    printf 'BACKEND_URL=%s\n' "$BACKEND_URL" >> "$ROOT_DIR/.env.azure"
    printf '\nDone. Backend URL:\n  %s\n' "$BACKEND_URL"
    printf '\nUpdate angular-dashboard/src/environments/environment.prod.ts:\n'
    printf '  apiBase: '"'"'%s'"'"'\n' "$BACKEND_URL"
  fi
}

_prompt_menu
if [[ "$_TARGET" == "local" ]]; then
  _deploy_local
else
  _ensure_az
  _check_az_auth
  _deploy_azure
fi
