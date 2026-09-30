#!/usr/bin/env bash
# kind-up.sh — the whole of yadgar on one machine, in one command (ADR-0820).
#
#   sudo bootstrap/kind-up.sh [--with-client]
#
# Run it from a clone of this repository checked out at a release tag. It turns
# a Debian or Ubuntu host with podman or docker into a kind cluster running Argo
# CD, the four operators and the estate, then creates the first administrator
# and writes their enrolment token to a root-only file. Every step checks first
# and skips when its work is already done, so a second run changes nothing and a
# failed run is resumed by running it again.
#
# THE EXAMPLE FILES ARE APPLIED AS THEY ARE, never copied into this script:
# `example/operators-application.yaml`, `example/kind/application.yaml` and
# `example/kind/kind-config.yaml`. Their pins are the pins, in one place.
#
# THE ARGO APPLICATIONS MUST SUCCEED ON THEIR FIRST SYNC. The script waits for
# `Synced`, `Healthy` and operation `Succeeded`, and never starts, forces or
# terminates a sync. A failed operation exits non-zero with the failing
# resources named.
#
# NO SECRET IS EVER PRINTED OR PASSED AS AN ARGUMENT. The bootstrap token goes to
# `curl` on stdin; the enrolment token and the client password go only to 0600
# files and to stdin.
#
# ONLY THE kind CLUSTER IS EVER ADDRESSED. Every `kubectl` and `helm` call names
# the cluster's own kubeconfig, written under the state directory, and its
# context. The ambient `KUBECONFIG` and `~/.kube/config` are never read.
#
# Settings, all optional, as environment variables:
#
#   YADGAR_ADMIN_EXTERNAL_ID    the first admin's username      (admin)
#   YADGAR_ADMIN_DISPLAY_NAME   the first admin's display name  (Administrator)
#   YADGAR_ENROLMENT_FILE       where the enrolment token goes  (/root/yadgar-enrolment.token)
#   YADGAR_STATE_DIR            kubeconfig, log, admin record   (/var/lib/yadgar-bootstrap)
#   YADGAR_CA_FILE              the edge CA, world-readable     (/etc/yadgar/edge-ca.crt)
#   YADGAR_RUNTIME              podman or docker                (podman if present)
#   YADGAR_OPERATORS_TIMEOUT    seconds to wait for `operators` (1500)
#   YADGAR_ESTATE_TIMEOUT       seconds to wait for `yadgar`    (3900)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

OPERATORS_APP_FILE="$REPO_DIR/example/operators-application.yaml"
ESTATE_APP_FILE="$REPO_DIR/example/kind/application.yaml"
KIND_CONFIG_FILE="$REPO_DIR/example/kind/kind-config.yaml"
ARGOCD_VALUES_FILE="$SCRIPT_DIR/argocd-values.yaml"

# argo-helm's `argo-cd` 8.6.1 ships Argo CD v3.1.8, the version every
# Application in this repository is written against.
ARGOCD_CHART_REPO="https://argoproj.github.io/argo-helm"
ARGOCD_CHART_VERSION="8.6.1"
ARGOCD_APP_VERSION="v3.1.8"

# The namespace `example/kind/application.yaml` installs into.
ESTATE_NAMESPACE="yadgar"

STATE_DIR="${YADGAR_STATE_DIR:-/var/lib/yadgar-bootstrap}"
LOG_FILE="$STATE_DIR/kind-up.log"
KUBECONFIG_FILE="$STATE_DIR/kubeconfig"
ADMIN_RECORD="$STATE_DIR/admin.json"
CLIENT_PASSWORD_FILE="$STATE_DIR/client-password"
CLIENT_MARKER="$STATE_DIR/client-enrolled"
BIN_DIR="${YADGAR_BIN_DIR:-/usr/local/bin}"
TOOLS_LOCK="${YADGAR_TOOLS_LOCK:-$SCRIPT_DIR/tools.lock}"
SYSCTL_FILE="${YADGAR_SYSCTL_FILE:-/etc/sysctl.d/90-yadgar-kind.conf}"
HOSTS_FILE="${YADGAR_HOSTS_FILE:-/etc/hosts}"
CA_FILE="${YADGAR_CA_FILE:-/etc/yadgar/edge-ca.crt}"
ENROLMENT_FILE="${YADGAR_ENROLMENT_FILE:-/root/yadgar-enrolment.token}"
ADMIN_EXTERNAL_ID="${YADGAR_ADMIN_EXTERNAL_ID:-admin}"
ADMIN_DISPLAY_NAME="${YADGAR_ADMIN_DISPLAY_NAME:-Administrator}"
RUNTIME="${YADGAR_RUNTIME:-}"
OPERATORS_TIMEOUT="${YADGAR_OPERATORS_TIMEOUT:-1500}"
ESTATE_TIMEOUT="${YADGAR_ESTATE_TIMEOUT:-3900}"
POLL_SECONDS="${YADGAR_POLL_SECONDS:-10}"
PROBE_ATTEMPTS="${YADGAR_PROBE_ATTEMPTS:-12}"
WITH_CLIENT=0

# An enrolment token lives 24 hours (ADR-0492). A file older than this is
# re-issued rather than handed back expired.
ENROLMENT_MAX_AGE_MINUTES=1380

# Read from the example files by `load_examples`.
CLUSTER_NAME=""
GATEWAY_URL=""
GATEWAY_HOST=""
GATEWAY_PORT=""

# ─── logging ─────────────────────────────────────────────────────────────────

log() {
  local line
  line="$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"
  printf '%s\n' "$line"
  if [[ -d "$STATE_DIR" ]]; then printf '%s\n' "$line" >>"$LOG_FILE"; fi
}

die() {
  local line
  line="$(date -u +%Y-%m-%dT%H:%M:%SZ) ERROR: $*"
  printf '%s\n' "$line" >&2
  if [[ -d "$STATE_DIR" ]]; then printf '%s\n' "$line" >>"$LOG_FILE"; fi
  exit 1
}

# Runs a command whose arguments carry no secret, with its output in the log.
run() {
  log "+ $*"
  "$@" 2>&1 | tee -a "$LOG_FILE"
}

# ─── the kind cluster, and nothing else ──────────────────────────────────────

k() { "$BIN_DIR/kubectl" --kubeconfig "$KUBECONFIG_FILE" --context "kind-$CLUSTER_NAME" "$@"; }
h() { "$BIN_DIR/helm" --kubeconfig "$KUBECONFIG_FILE" --kube-context "kind-$CLUSTER_NAME" "$@"; }

# ─── the example files ───────────────────────────────────────────────────────

# The cluster name from the kind config, and the edge from the Application's
# `iam.enrolment.gateway` — the URL every enrolment token carries. The kind
# config's `hostPort` must be that URL's port, or the edge answers nowhere.
load_examples() {
  local host_port
  CLUSTER_NAME="$(awk '/^name:/ { print $2; exit }' "$KIND_CONFIG_FILE")"
  host_port="$(awk '/hostPort:/ { print $2; exit }' "$KIND_CONFIG_FILE")"
  GATEWAY_URL="$(awk '/^[[:space:]]+gateway:[[:space:]]*"?https:/ { gsub(/"/, "", $2); print $2; exit }' "$ESTATE_APP_FILE")"
  GATEWAY_HOST="${GATEWAY_URL#https://}"
  GATEWAY_HOST="${GATEWAY_HOST%%[:/]*}"
  GATEWAY_PORT="${GATEWAY_URL##*:}"
  GATEWAY_PORT="${GATEWAY_PORT%%/*}"
  [[ -n "$CLUSTER_NAME" ]] || die "no cluster name in $KIND_CONFIG_FILE"
  [[ -n "$GATEWAY_HOST" && "$GATEWAY_PORT" =~ ^[0-9]+$ ]] ||
    die "no https://<host>:<port> enrolment gateway in $ESTATE_APP_FILE"
  [[ "$GATEWAY_PORT" == "$host_port" ]] ||
    die "$ESTATE_APP_FILE dials port $GATEWAY_PORT but $KIND_CONFIG_FILE maps hostPort $host_port"
}

# ─── 1. preconditions ────────────────────────────────────────────────────────

require_root() {
  [[ "$(id -u)" == "0" ]] || die "run as root: sudo $0 $*"
}

ensure_state_dir() {
  umask 077
  mkdir -p "$STATE_DIR"
  chmod 0700 "$STATE_DIR"
  touch "$LOG_FILE"
  rm -rf "$STATE_DIR"/tmp.*
}

# curl, jq and the coreutils the script leans on. Installed with apt when
# missing; a host without apt must bring them itself.
ensure_packages() {
  local missing=() cmd
  for cmd in curl jq tar sha256sum base64 awk install; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
  done
  if ((${#missing[@]} == 0)); then
    log "[1/10] host packages already present"
    return
  fi
  command -v apt-get >/dev/null 2>&1 ||
    die "missing ${missing[*]}, and no apt-get to install them; supported hosts are Debian and Ubuntu"
  log "[1/10] installing host packages (missing: ${missing[*]})"
  run env DEBIAN_FRONTEND=noninteractive apt-get update -q
  run env DEBIAN_FRONTEND=noninteractive apt-get install -y -q curl jq tar coreutils ca-certificates
}

# podman when present — the runtime the from-scratch run was measured with —
# else docker. kind drives podman only when told to.
detect_runtime() {
  if [[ -z "$RUNTIME" ]]; then
    if command -v podman >/dev/null 2>&1; then
      RUNTIME=podman
    elif command -v docker >/dev/null 2>&1; then
      RUNTIME=docker
    else
      die "neither podman nor docker is installed"
    fi
  fi
  [[ "$RUNTIME" == podman || "$RUNTIME" == docker ]] || die "YADGAR_RUNTIME must be podman or docker, not $RUNTIME"
  if [[ "$RUNTIME" == podman ]]; then export KIND_EXPERIMENTAL_PROVIDER=podman; fi
  log "[1/10] container runtime: $RUNTIME"
}

# ─── 2. sysctls ──────────────────────────────────────────────────────────────

# inotify limits kind's node needs for dozens of pods, and forwarding for its
# network. Persisted in /etc/sysctl.d so a reboot keeps them.
ensure_sysctls() {
  local want
  want="$(printf '%s\n' \
    '# Written by yadgar bootstrap/kind-up.sh.' \
    'fs.inotify.max_user_watches = 524288' \
    'fs.inotify.max_user_instances = 512' \
    'net.ipv4.ip_forward = 1')"
  if [[ -f "$SYSCTL_FILE" && "$(cat "$SYSCTL_FILE")" == "$want" ]] &&
    [[ "$(sysctl -n fs.inotify.max_user_watches)" == 524288 ]] &&
    [[ "$(sysctl -n fs.inotify.max_user_instances)" == 512 ]] &&
    [[ "$(sysctl -n net.ipv4.ip_forward)" == 1 ]]; then
    log "[2/10] sysctls already set and persisted"
    return
  fi
  log "[2/10] writing $SYSCTL_FILE and applying it"
  mkdir -p "$(dirname "$SYSCTL_FILE")"
  printf '%s\n' "$want" >"$SYSCTL_FILE"
  chmod 0644 "$SYSCTL_FILE"
  run sysctl -p "$SYSCTL_FILE"
}

# ─── 3. pinned tools ─────────────────────────────────────────────────────────

host_arch() {
  if [[ -n "${YADGAR_ARCH:-}" ]]; then
    printf '%s\n' "$YADGAR_ARCH"
    return
  fi
  case "$(uname -m)" in
    x86_64 | amd64) echo amd64 ;;
    aarch64 | arm64) echo arm64 ;;
    *) die "unsupported architecture $(uname -m)" ;;
  esac
}

installed_version() {
  local tool="$1" path="$BIN_DIR/$1"
  [[ -x "$path" ]] || return 0
  case "$tool" in
    kind) "$path" version 2>/dev/null | awk '{ print $2 }' ;;
    kubectl) "$path" version --client -o json 2>/dev/null | jq -r '.clientVersion.gitVersion // empty' ;;
    helm) "$path" version --template '{{.Version}}' 2>/dev/null ;;
  esac
}

# Installs one tool from `tools.lock` into BIN_DIR, only when it is missing or
# at another version, and only after its sha256 matches the pinned one.
ensure_tool() {
  local tool="$1" arch row version sha url member have got work
  arch="$(host_arch)"
  row="$(awk -v t="$tool" -v a="$arch" '$1 == t && $3 == a { print; exit }' "$TOOLS_LOCK")"
  [[ -n "$row" ]] || die "$TOOLS_LOCK pins no $tool for $arch"
  read -r _ version _ sha url member <<<"$row"
  have="$(installed_version "$tool" || true)"
  if [[ "$have" == "$version" ]]; then
    log "[3/10] $tool $version already installed"
    return
  fi
  log "[3/10] installing $tool $version (found: ${have:-none})"
  work="$(mktemp -d "$STATE_DIR/tmp.XXXXXX")"
  curl -fsSL --retry 3 -o "$work/download" "$url" || {
    rm -rf "$work"
    die "download of $tool failed: $url"
  }
  got="$(sha256sum "$work/download" | awk '{ print $1 }')"
  if [[ "$got" != "$sha" ]]; then
    rm -rf "$work"
    die "checksum mismatch for $tool $version: expected $sha, got $got; nothing installed"
  fi
  local binary="$work/download"
  if [[ -n "${member:-}" ]]; then
    tar -xzf "$work/download" -C "$work" "$member"
    binary="$work/$member"
  fi
  # Beside the target, then renamed over it: a running binary is never
  # rewritten in place, and a symlink at the target is replaced, not followed.
  install -m 0755 "$binary" "$BIN_DIR/.$tool.new"
  mv -f "$BIN_DIR/.$tool.new" "$BIN_DIR/$tool"
  rm -rf "$work"
  have="$(installed_version "$tool" || true)"
  [[ "$have" == "$version" ]] || die "$tool reports ${have:-nothing} after installing $version"
}

# ─── 4. the kind cluster ─────────────────────────────────────────────────────

# An existing cluster of the same name is kept when its API answers, its node
# is Ready and the edge port is mapped. One that fails any of those is reported,
# never deleted: it may hold someone's work.
ensure_cluster() {
  umask 077
  touch "$KUBECONFIG_FILE"
  if "$BIN_DIR/kind" get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
    "$BIN_DIR/kind" export kubeconfig --name "$CLUSTER_NAME" --kubeconfig "$KUBECONFIG_FILE" >/dev/null 2>&1 ||
      die "kind cluster $CLUSTER_NAME exists but its kubeconfig cannot be exported"
    [[ "$(k get --raw /readyz 2>/dev/null)" == ok ]] ||
      die "kind cluster $CLUSTER_NAME exists but its API is not ready; inspect it, or delete it with: kind delete cluster --name $CLUSTER_NAME"
    k get nodes -o json | jq -e '[.items[].status.conditions[] | select(.type == "Ready") | .status == "True"] | all' >/dev/null ||
      die "kind cluster $CLUSTER_NAME exists but a node is not Ready"
    local mapped
    mapped="$("$RUNTIME" port "$CLUSTER_NAME-control-plane" 30443/tcp 2>/dev/null || true)"
    [[ "$mapped" == *":$GATEWAY_PORT"* ]] ||
      die "kind cluster $CLUSTER_NAME does not map node port 30443 to host port $GATEWAY_PORT; it was not created from $KIND_CONFIG_FILE — delete it with: kind delete cluster --name $CLUSTER_NAME"
    log "[4/10] kind cluster $CLUSTER_NAME already running and healthy"
    return
  fi
  log "[4/10] creating kind cluster $CLUSTER_NAME from $KIND_CONFIG_FILE"
  run "$BIN_DIR/kind" create cluster --config "$KIND_CONFIG_FILE" --kubeconfig "$KUBECONFIG_FILE" --wait 180s
}

# ─── 5. Argo CD ──────────────────────────────────────────────────────────────

ensure_argocd() {
  log "[5/10] Argo CD: argo-cd chart $ARGOCD_CHART_VERSION (upgrade --install, a no-op when current)"
  run h upgrade --install argocd argo-cd --repo "$ARGOCD_CHART_REPO" --version "$ARGOCD_CHART_VERSION" \
    --namespace argocd --create-namespace -f "$ARGOCD_VALUES_FILE" --wait --timeout 10m
  local image
  image="$(k -n argocd get deployment argocd-server -o jsonpath='{.spec.template.spec.containers[0].image}')"
  [[ "$image" == *":$ARGOCD_APP_VERSION" ]] || die "argocd-server runs $image, expected $ARGOCD_APP_VERSION"
}

# ─── 6/7. Applications ───────────────────────────────────────────────────────

# Reads an Application as JSON on stdin and prints one word:
#   ok      the operation for the pinned revision Succeeded, Synced and Healthy
#   failed  the operation for the pinned revision ended Failed or Error
#   wait    anything else: no operation yet, one running or retrying, or the
#           last one was for another revision (automated sync starts a new one)
# While Argo retries, the phase reads Running, so Failed is final.
app_verdict() {
  local doc
  doc="$(cat)"
  if [[ -z "$doc" ]]; then
    echo wait
    return
  fi
  jq -r '
    (.spec.source.targetRevision // "") as $target
    | (.status.operationState // {}) as $op
    | ($op.operation.sync.revision // $op.syncResult.revision // "") as $rev
    | ($op.phase // "") as $phase
    | if $phase == "" then "wait"
      elif $target != "" and $rev != "" and $rev != $target then "wait"
      elif $phase == "Failed" or $phase == "Error" then "failed"
      elif $phase == "Succeeded"
           and .status.sync.status == "Synced"
           and .status.health.status == "Healthy" then "ok"
      else "wait" end' <<<"$doc"
}

# Everything worth reading when an Application did not come up: the operation's
# message, the resources the sync failed, the resources not Healthy, and the
# Application's conditions.
print_app_failure() {
  local name="$1" doc="$2"
  [[ -n "$doc" ]] || {
    printf 'Application %s could not be read\n' "$name" >&2
    return
  }
  jq -r --arg name "$name" '
    "Application \($name): sync=\(.status.sync.status // "-") health=\(.status.health.status // "-") operation=\(.status.operationState.phase // "-")",
    "  message: \(.status.operationState.message // "-")",
    (.status.operationState.syncResult.resources // [] | .[]
      | select((.status // "") != "Synced" or ((.hookPhase // "") | IN("Failed", "Error")))
      | "  failed: \(.kind) \(.namespace // "-")/\(.name) status=\(.status // "-") hook=\(.hookPhase // "-") \(.message // "")"),
    (.status.resources // [] | .[]
      | select(.health != null and .health.status != "Healthy")
      | "  unhealthy: \(.kind) \(.namespace // "-")/\(.name) health=\(.health.status) \(.health.message // "")"),
    (.status.conditions // [] | .[] | "  condition: \(.type): \(.message)")
  ' <<<"$doc" | tee -a "$LOG_FILE" >&2
}

wait_app() {
  local name="$1" timeout="$2" deadline doc verdict
  deadline=$((SECONDS + timeout))
  while :; do
    doc="$(k -n argocd get application "$name" -o json 2>/dev/null || true)"
    verdict="$(app_verdict <<<"$doc")"
    case "$verdict" in
      ok)
        log "Application $name: Synced, Healthy, operation Succeeded"
        return 0
        ;;
      failed)
        log "Application $name: operation failed; no sync is forced"
        print_app_failure "$name" "$doc"
        return 1
        ;;
    esac
    if ((SECONDS >= deadline)); then
      log "Application $name: timed out after ${timeout}s"
      print_app_failure "$name" "$doc"
      return 1
    fi
    local summary="not readable yet"
    if [[ -n "$doc" ]]; then
      summary="$(jq -r '"sync=\(.status.sync.status // "-") health=\(.status.health.status // "-") operation=\(.status.operationState.phase // "-") \(.status.operationState.message // "")"' <<<"$doc")"
    fi
    log "Application $name: $summary"
    sleep "$POLL_SECONDS"
  done
}

ensure_application() {
  local step="$1" file="$2" name="$3" timeout="$4"
  log "[$step/10] applying $file"
  run k apply -f "$file"
  log "[$step/10] waiting up to ${timeout}s for $name"
  wait_app "$name" "$timeout" || die "Application $name did not succeed on its first sync"
}

# ─── 8. the edge ─────────────────────────────────────────────────────────────

# Adds `127.0.0.1 <host>` unless a live line already maps the host. A line
# mapping it elsewhere is refused rather than edited: someone put it there.
ensure_hosts_entry() {
  local host="$1" existing
  existing="$(awk -v h="$host" '$1 !~ /^#/ { for (i = 2; i <= NF; i++) if ($i == h) { print $1; exit } }' "$HOSTS_FILE")"
  if [[ "$existing" == 127.0.0.1 ]]; then
    log "[8/10] $HOSTS_FILE already maps $host to 127.0.0.1"
    return
  fi
  [[ -z "$existing" ]] || die "$HOSTS_FILE maps $host to $existing; point it at 127.0.0.1 or remove that line"
  log "[8/10] adding 127.0.0.1 $host to $HOSTS_FILE"
  printf '127.0.0.1 %s\n' "$host" >>"$HOSTS_FILE"
}

# The edge CA is public: it is what clients trust, and every enrolment token
# carries it anyway. So 0644, outside the state directory.
ensure_edge_ca() {
  local tmp
  tmp="$(mktemp "$STATE_DIR/tmp.XXXXXX")"
  k -n "$ESTATE_NAMESPACE" get secret gateway-tls -o 'jsonpath={.data.ca\.crt}' | base64 -d >"$tmp"
  grep -q 'BEGIN CERTIFICATE' "$tmp" || {
    rm -f "$tmp"
    die "Secret $ESTATE_NAMESPACE/gateway-tls has no ca.crt"
  }
  mkdir -p "$(dirname "$CA_FILE")"
  install -m 0644 "$tmp" "$CA_FILE"
  rm -f "$tmp"
  log "[8/10] edge CA written to $CA_FILE"
}

# The gateway answers GET / with 405 "MCP uses POST": TLS, the hostname, the
# port mapping and the route all work.
probe_edge() {
  local attempt code=""
  for ((attempt = 1; attempt <= PROBE_ATTEMPTS; attempt++)); do
    code="$(curl -sS -o /dev/null -w '%{http_code}' --cacert "$CA_FILE" "$GATEWAY_URL/" 2>/dev/null || true)"
    if [[ "$code" == 405 ]]; then
      log "[8/10] $GATEWAY_URL/ answered 405 over the edge CA"
      return
    fi
    sleep "$POLL_SECONDS"
  done
  die "$GATEWAY_URL/ answered ${code:-nothing}, expected 405"
}

# ─── 9. the first administrator ──────────────────────────────────────────────

# POSTs one admin request. The bootstrap token travels in a curl config read
# from stdin, so it is in no argv and no file. Prints the HTTP status; the body
# lands in $3, which the caller deletes.
admin_post() {
  local path="$1" body_file="$2" out_file="$3" token="$4"
  printf 'header = "x-yadgar-bootstrap-token: %s"\n' "$token" |
    curl --config - -sS -o "$out_file" -w '%{http_code}' --cacert "$CA_FILE" \
      -H 'content-type: application/json' --data-binary "@$body_file" \
      "$GATEWAY_URL/admin/$path" || true
}

read_bootstrap_token() {
  local token
  token="$(k -n "$ESTATE_NAMESPACE" get secret admin-bootstrap-token -o 'jsonpath={.data.token}' | base64 -d)"
  [[ "$token" =~ ^[A-Za-z0-9+/=_-]+$ ]] ||
    die "Secret $ESTATE_NAMESPACE/admin-bootstrap-token has no usable token"
  printf '%s' "$token"
}

# Issues an enrolment for the recorded admin and writes the token to a 0600
# file. Returns 2 when the gateway says the admin already holds a credential.
issue_enrolment() {
  local user_id="$1" token="$2" work code
  work="$(mktemp -d "$STATE_DIR/tmp.XXXXXX")"
  jq -n --arg u "$user_id" '{user_id: $u}' >"$work/body"
  code="$(admin_post issue-enrolment "$work/body" "$work/out" "$token")"
  case "$code" in
    200)
      jq -r '.token // empty' "$work/out" >"$work/token"
      [[ -s "$work/token" ]] || {
        rm -rf "$work"
        die "issue-enrolment answered 200 with no token"
      }
      mkdir -p "$(dirname "$ENROLMENT_FILE")"
      install -m 0600 "$work/token" "$ENROLMENT_FILE"
      rm -rf "$work"
      log "[9/10] enrolment token for $ADMIN_EXTERNAL_ID written to $ENROLMENT_FILE (0600, valid 24 hours)"
      ;;
    403)
      rm -rf "$work"
      return 2
      ;;
    *)
      local answer
      answer="$(jq -r '.error // empty' "$work/out" 2>/dev/null || true)"
      rm -rf "$work"
      die "issue-enrolment answered ${code:-nothing}: ${answer:-no body}"
      ;;
  esac
}

# The first admin, over the gateway's existing routes (ADR-0492, ADR-0655).
#
# IDEMPOTENCY IS LOCAL, because the gateway gives no other handle: a duplicate
# `external_id` is refused inside iam and the gateway answers it with the same
# opaque 503 as an outage (gateway v0.9.54, `opaque_status`), and there is no
# route to look a user up. So the user id is recorded in $ADMIN_RECORD the
# moment create-user answers 200, and create-user is sent at most once per
# state directory, never retried.
#
#   enrolment file younger than 23h  → skip; nothing is read or sent
#   admin recorded, no fresh file    → issue-enrolment for the recorded admin
#                                      (the bootstrap token may enrol only an
#                                      admin with zero credentials; a 403 means
#                                      they already enrolled, and that is done)
#   nothing recorded                 → create-user, record, issue-enrolment
ensure_admin() {
  if [[ -s "$ENROLMENT_FILE" ]] && [[ -n "$(find "$ENROLMENT_FILE" -mmin -"$ENROLMENT_MAX_AGE_MINUTES" 2>/dev/null)" ]]; then
    log "[9/10] $ENROLMENT_FILE already holds a current enrolment token"
    return
  fi
  local token user_id recorded_id work code rc=0
  if [[ -s "$ADMIN_RECORD" ]]; then
    recorded_id="$(jq -r '.external_id' "$ADMIN_RECORD")"
    [[ "$recorded_id" == "$ADMIN_EXTERNAL_ID" ]] ||
      die "$ADMIN_RECORD records admin $recorded_id, not $ADMIN_EXTERNAL_ID; this installation's first admin already exists"
    user_id="$(jq -r '.user_id' "$ADMIN_RECORD")"
    token="$(read_bootstrap_token)"
    log "[9/10] admin $ADMIN_EXTERNAL_ID already created ($user_id); issuing a new enrolment"
  else
    token="$(read_bootstrap_token)"
    log "[9/10] creating the first admin $ADMIN_EXTERNAL_ID"
    work="$(mktemp -d "$STATE_DIR/tmp.XXXXXX")"
    jq -n --arg e "$ADMIN_EXTERNAL_ID" --arg d "$ADMIN_DISPLAY_NAME" \
      '{external_id: $e, display_name: $d, is_admin: true}' >"$work/body"
    code="$(admin_post create-user "$work/body" "$work/out" "$token")"
    if [[ "$code" != 200 ]]; then
      local answer
      answer="$(jq -r '.error // empty' "$work/out" 2>/dev/null || true)"
      rm -rf "$work"
      die "create-user answered ${code:-nothing}: ${answer:-no body}. The gateway answers a duplicate username the same way as an outage. If $ADMIN_EXTERNAL_ID was created by an earlier run whose $ADMIN_RECORD is gone, it cannot be recovered with the bootstrap token: have an enrolled admin issue its enrolment, or set YADGAR_ADMIN_EXTERNAL_ID to a new username"
    fi
    user_id="$(jq -r '.user_id // empty' "$work/out")"
    rm -rf "$work"
    [[ -n "$user_id" ]] || die "create-user answered 200 with no user_id"
    jq -n --arg e "$ADMIN_EXTERNAL_ID" --arg u "$user_id" '{external_id: $e, user_id: $u}' >"$ADMIN_RECORD.tmp"
    mv "$ADMIN_RECORD.tmp" "$ADMIN_RECORD"
    log "[9/10] created $ADMIN_EXTERNAL_ID as $user_id"
  fi
  issue_enrolment "$user_id" "$token" || rc=$?
  token=""
  if ((rc == 2)); then
    log "[9/10] $ADMIN_EXTERNAL_ID already enrolled: they hold a credential, so the bootstrap token may not enrol them again. Log in with that credential"
  elif ((rc != 0)); then
    exit "$rc"
  fi
}

# ─── 10. the client ──────────────────────────────────────────────────────────

print_next_steps() {
  log "[10/10] done. Next, on the machine you work from:"
  cat <<EOF | tee -a "$LOG_FILE"

  pipx install yaadgaar
  yaadgaar enrol --token-file $ENROLMENT_FILE --password-stdin < <your-password-file>
  yaadgaar login --gateway $GATEWAY_URL --username $ADMIN_EXTERNAL_ID --password-stdin < <your-password-file>

  The enrolment token carries the edge CA. A machine other than this one also
  needs $GATEWAY_HOST to resolve to this host, and port $GATEWAY_PORT, which
  kind publishes on 127.0.0.1 only.
  The cluster:  KUBECONFIG=$KUBECONFIG_FILE kubectl get applications -n argocd
EOF
}

yaadgaar_bin() {
  if command -v yaadgaar >/dev/null 2>&1; then
    command -v yaadgaar
    return
  fi
  if ! command -v pipx >/dev/null 2>&1; then
    command -v apt-get >/dev/null 2>&1 || return 1
    run env DEBIAN_FRONTEND=noninteractive apt-get install -y -q pipx >/dev/null
  fi
  run pipx install yaadgaar >/dev/null
  local dir
  dir="$(pipx environment --value PIPX_BIN_DIR 2>/dev/null || echo "$HOME/.local/bin")"
  [[ -x "$dir/yaadgaar" ]] && printf '%s\n' "$dir/yaadgaar"
}

# Opt-in: enrol this machine's root as the first admin with a generated
# password kept 0600 beside the kubeconfig. Only with a client that reads the
# password from stdin; an older one is skipped, never driven through a terminal.
ensure_client() {
  if [[ -f "$CLIENT_MARKER" ]]; then
    log "[10/10] client already enrolled as $ADMIN_EXTERNAL_ID"
    return
  fi
  if [[ ! -s "$ENROLMENT_FILE" ]]; then
    log "[10/10] --with-client: no enrolment token to redeem; skipped"
    return
  fi
  local bin
  bin="$(yaadgaar_bin)" || {
    log "[10/10] --with-client: yaadgaar could not be installed; skipped"
    return
  }
  if ! "$bin" enrol --help 2>/dev/null | grep -q -- '--password-stdin'; then
    log "[10/10] --with-client: this yaadgaar has no --password-stdin; skipped. Enrol by hand as shown below"
    return
  fi
  if [[ ! -s "$CLIENT_PASSWORD_FILE" ]]; then
    (
      umask 077
      head -c 24 /dev/urandom | base64 >"$CLIENT_PASSWORD_FILE"
    )
  fi
  log "[10/10] enrolling $ADMIN_EXTERNAL_ID with yaadgaar; password in $CLIENT_PASSWORD_FILE (0600)"
  "$bin" enrol --token-file "$ENROLMENT_FILE" --password-stdin <"$CLIENT_PASSWORD_FILE" 2>&1 | tee -a "$LOG_FILE"
  "$bin" login --gateway "$GATEWAY_URL" --username "$ADMIN_EXTERNAL_ID" --password-stdin <"$CLIENT_PASSWORD_FILE" 2>&1 | tee -a "$LOG_FILE"
  touch "$CLIENT_MARKER"
}

# ─── main ────────────────────────────────────────────────────────────────────

usage() {
  sed -n '2,/^$/{s/^# \{0,1\}//;p}' "${BASH_SOURCE[0]}"
}

main() {
  local arg
  for arg in "$@"; do
    case "$arg" in
      --with-client) WITH_CLIENT=1 ;;
      -h | --help)
        usage
        return 0
        ;;
      *)
        printf 'unknown argument: %s\n' "$arg" >&2
        return 2
        ;;
    esac
  done
  require_root "$@"
  ensure_state_dir
  trap 'rm -rf "$STATE_DIR"/tmp.*' EXIT
  load_examples
  log "kind-up: cluster $CLUSTER_NAME, edge $GATEWAY_URL, log $LOG_FILE"

  ensure_packages
  detect_runtime
  ensure_sysctls
  ensure_tool kind
  ensure_tool kubectl
  ensure_tool helm
  ensure_cluster
  ensure_argocd
  ensure_application 6 "$OPERATORS_APP_FILE" operators "$OPERATORS_TIMEOUT"
  ensure_application 7 "$ESTATE_APP_FILE" yadgar "$ESTATE_TIMEOUT"
  ensure_hosts_entry "$GATEWAY_HOST"
  ensure_edge_ca
  probe_edge
  ensure_admin
  if ((WITH_CLIENT)); then ensure_client; fi
  print_next_steps
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
