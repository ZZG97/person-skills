#!/usr/bin/env bash
set -euo pipefail

api_base='@@OPENCLASH_API_URL@@'
keychain_service='@@OPENCLASH_KEYCHAIN_SERVICE@@'
keychain_account='@@OPENCLASH_KEYCHAIN_ACCOUNT@@'

usage() {
  cat <<'EOF'
Usage:
  openclash-api.sh version
  openclash-api.sh snapshot
  openclash-api.sh get /api/path
  openclash-api.sh delay NODE URL [TIMEOUT_MS] [EXPECTED_STATUS]
  openclash-api.sh select --yes GROUP NODE

The secret is read from OPENCLASH_API_SECRET or macOS Keychain. The select
command is the only mutating operation and requires the explicit --yes flag.
EOF
}

die() {
  printf 'openclash-api: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

load_secret() {
  if [ -n "${OPENCLASH_API_SECRET:-}" ]; then
    printf '%s' "$OPENCLASH_API_SECRET"
    return
  fi

  if command -v security >/dev/null 2>&1; then
    security find-generic-password \
      -s "$keychain_service" \
      -a "$keychain_account" \
      -w 2>/dev/null && return
  fi

  die "no API secret found; set OPENCLASH_API_SECRET or initialize Keychain"
}

validate_api_base() {
  case "$api_base" in
    http://*|https://*) ;;
    *) die "rendered OPENCLASH_API_URL must use http or https" ;;
  esac
}

encode_path_segment() {
  jq -rn --arg value "$1" '$value | @uri'
}

api_request() {
  method="$1"
  path="$2"
  body="${3:-}"

  case "$path" in
    /*) ;;
    *) die "API path must start with /" ;;
  esac
  case "$path" in
    *://*) die "API path must not contain another URL" ;;
  esac

  secret="$(load_secret)"
  if [ -n "$body" ]; then
    printf 'header = "Authorization: Bearer %s"\n' "$secret" |
      curl --config - -sS --max-time 15 \
        -X "$method" \
        -H 'Content-Type: application/json' \
        --data-binary "$body" \
        "${api_base%/}${path}"
  else
    printf 'header = "Authorization: Bearer %s"\n' "$secret" |
      curl --config - -sS --max-time 15 \
        -X "$method" \
        "${api_base%/}${path}"
  fi
  unset secret
}

command_version() {
  api_request GET /version | jq '{meta, version}'
}

command_snapshot() {
  configs="$(api_request GET /configs)"
  proxies="$(api_request GET /proxies)"
  providers="$(api_request GET /providers/proxies)"

  jq -n \
    --argjson configs "$configs" \
    --argjson proxies "$proxies" \
    --argjson providers "$providers" '
      {
        config: ($configs | {
          port,
          "socks-port",
          "redir-port",
          "tproxy-port",
          "mixed-port",
          mode,
          "log-level",
          ipv6,
          "allow-lan",
          "bind-address",
          "unified-delay",
          "tcp-concurrent",
          "find-process-mode"
        }),
        groups: [
          $proxies.proxies | to_entries[]
          | select(
              .value.type == "Selector" or
              .value.type == "URLTest" or
              .value.type == "Fallback" or
              .value.type == "LoadBalance"
            )
          | {
              name: .key,
              type: .value.type,
              now: .value.now,
              alive: .value.alive,
              candidates: ((.value.all // []) | length),
              testUrl: .value.testUrl,
              lastDelay: ((.value.history // []) | last | .delay)
            }
        ],
        providers: [
          $providers.providers | to_entries[]
          | {
              name: .key,
              vehicleType: .value.vehicleType,
              updatedAt: .value.updatedAt,
              proxies: ((.value.proxies // []) | length),
              alive: ([.value.proxies[]? | select(.alive == true)] | length),
              dead: ([.value.proxies[]? | select(.alive == false)] | length)
            }
        ]
      }
    '
  unset configs proxies providers
}

command_get() {
  [ "$#" -eq 1 ] || die "get requires one API path"
  api_request GET "$1"
}

command_delay() {
  [ "$#" -ge 2 ] && [ "$#" -le 4 ] || die "delay requires NODE URL [TIMEOUT_MS] [EXPECTED_STATUS]"
  node="$1"
  url="$2"
  timeout_ms="${3:-7000}"
  expected_status="${4:-}"
  case "$timeout_ms" in
    ''|*[!0-9]*) die "timeout must be an integer in milliseconds" ;;
  esac
  case "$expected_status" in
    '') ;;
    *[!0-9]*) die "expected status must be an integer HTTP status" ;;
  esac

  encoded_node="$(encode_path_segment "$node")"
  secret="$(load_secret)"
  curl_args=(
    --config - -sS --max-time 15 --get
    --data-urlencode "timeout=$timeout_ms"
    --data-urlencode "url=$url"
  )
  if [ -n "$expected_status" ]; then
    curl_args+=(--data-urlencode "expected=$expected_status")
  fi
  printf 'header = "Authorization: Bearer %s"\n' "$secret" |
    curl "${curl_args[@]}" "${api_base%/}/proxies/${encoded_node}/delay"
  unset node url timeout_ms expected_status encoded_node secret curl_args
}

command_select() {
  [ "$#" -eq 3 ] || die "select requires --yes GROUP NODE"
  [ "$1" = "--yes" ] || die "select is mutating and requires --yes"
  group="$2"
  node="$3"
  encoded_group="$(encode_path_segment "$group")"
  group_state="$(api_request GET "/proxies/${encoded_group}")"

  printf '%s' "$group_state" | jq -e --arg node "$node" '
    .type == "Selector" and ((.all // []) | index($node) != null)
  ' >/dev/null || die "target must be a candidate in a Selector group"

  payload="$(jq -cn --arg name "$node" '{name: $name}')"
  api_request PUT "/proxies/${encoded_group}" "$payload" >/dev/null
  api_request GET "/proxies/${encoded_group}" | jq '{name, type, now, alive}'
  unset group node encoded_group group_state payload
}

main() {
  command="${1:-}"
  if [ "$#" -gt 0 ]; then shift; fi
  case "$command" in
    help|-h|--help|'') usage; return ;;
  esac

  require_command curl
  require_command jq
  validate_api_base

  case "$command" in
    version) command_version "$@" ;;
    snapshot) command_snapshot "$@" ;;
    get) command_get "$@" ;;
    delay) command_delay "$@" ;;
    select) command_select "$@" ;;
    *) die "unknown command: $command" ;;
  esac
}

main "$@"
