#!/usr/bin/env bash
# kind-up.sh — the whole of yadgar on one machine, in one command (ADR-0820).
#
#   sudo bootstrap/kind-up.sh [--with-client]
#
# Run it from this repository at a release tag — a clone, or the release
# tarball, which needs no git:
#
#   curl -fsSL https://github.com/yadgarhq/chart/archive/refs/tags/v<ver>.tar.gz | tar xz
#   sudo ./chart-<ver>/bootstrap/kind-up.sh
#
# It turns a Debian or Ubuntu host with podman or docker into a kind cluster
# running Argo CD, the four operators and the estate, then creates the first
# administrator and writes their enrolment token to a root-only file. Every step
# checks first and skips when its work is already done, so a second run changes
# nothing, and a run that stopped on a host, download or cluster error resumes
# where it stopped.
#
# ONE EXCEPTION: A FAILED ARGO OPERATION IS NOT RESUMED BY RUNNING THIS AGAIN.
# Argo does not auto-sync a revision whose sync failed, and this script never
# starts one. It prints the failed resources and the command to start one sync
# yourself once the cause is fixed.
#
# THE EXAMPLE FILES ARE APPLIED AS THEY ARE, never copied into this script:
# `example/operators-application.yaml`, `example/kind/application.yaml` and
# `example/kind/kind-config.yaml`. Their pins are the pins, in one place.
#
# THE ARGO APPLICATIONS MUST SUCCEED ON THEIR FIRST SYNC, which means their
# first operation succeeds (Argo may retry within it). It waits for `Synced`, `Healthy`
# and operation `Succeeded`, logs each retry Argo makes inside that operation,
# and never starts, forces or terminates a sync. A failed operation exits
# non-zero with the failing resources named.
#
# A SECOND RUN WRITES NOTHING that has not changed: an Application is applied
# only when `kubectl diff` finds a difference, and the edge CA and the
# kubeconfig are replaced only when their content differs.
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
#   YADGAR_BIN_DIR              kind, kubectl and helm          (/opt/yadgar-bootstrap/bin)
#   YADGAR_CA_FILE              the edge CA, world-readable     (/etc/yadgar/edge-ca.crt)
#   YADGAR_RUNTIME              podman or docker                (podman if present)
#   YADGAR_OPERATORS_TIMEOUT    seconds to wait for `operators` (1500)
#   YADGAR_ESTATE_TIMEOUT       seconds to wait for `yadgar`    (3900)

set -euo pipefail
# NO TRACE, WHATEVER THE CALLER EXPORTED. `SHELLOPTS=xtrace` in the environment
# or a `BASH_ENV` running `set -x` would print every secret this script holds;
# `set +x` also rewrites the exported SHELLOPTS any child bash inherits.
set +x
unset BASH_ENV ENV

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
# TWO MARKERS, because the enrolment token is single-use: a login that failed is
# retried on the next run, and the token is never sent a second time.
CLIENT_ENROLLED_MARKER="$STATE_DIR/client-enrolled"
CLIENT_LOGGED_IN_MARKER="$STATE_DIR/client-logged-in"
ARGOCD_VALUES_SHA_FILE="$STATE_DIR/argocd-values.sha256"
# A DIRECTORY OF ITS OWN: a kind, kubectl or helm the host already has in a
# shared bin directory is never replaced — never /usr/local/bin.
BIN_DIR="${YADGAR_BIN_DIR:-/opt/yadgar-bootstrap/bin}"
TOOLS_LOCK="${YADGAR_TOOLS_LOCK:-$SCRIPT_DIR/tools.lock}"
SYSCTL_FILE="${YADGAR_SYSCTL_FILE:-/etc/sysctl.d/90-yadgar-kind.conf}"
HOSTS_FILE="${YADGAR_HOSTS_FILE:-/etc/hosts}"
CA_FILE="${YADGAR_CA_FILE:-/etc/yadgar/edge-ca.crt}"
ENROLMENT_FILE="${YADGAR_ENROLMENT_FILE:-/root/yadgar-enrolment.token}"
ADMIN_EXTERNAL_ID="${YADGAR_ADMIN_EXTERNAL_ID:-admin}"
ADMIN_DISPLAY_NAME="${YADGAR_ADMIN_DISPLAY_NAME:-Administrator}"
RUNTIME="${YADGAR_RUNTIME:-}"
# HOW LONG THIS SCRIPT WAITS FOR EACH APPLICATION. Both examples retry 6 times
# with waits of 30, 60, 120, 240, 300 and 300 s: 1050 s (17.5 minutes) of
# backoff beside the attempts.
#   operators  25 min (1500 s): an install budget, which the measured 2m15s
#              first sync and KEDA's webhook restarts sit well inside.
#   estate     65 min (3900 s): the same 1500 s plus the 1050 s window, plus
#              1350 s for the attempts themselves. That is NOT 7 attempts at
#              the documented bounds: each attempt may spend 3365 s
#              (`argocd-values.yaml`), so 1500 + 1050 + 7 x 3365 = 26105 s.
# THESE WAITS ARE FAR SHORTER THAN ARGO'S OWN END OF AN OPERATION (ledger 1208),
# AND THE GAP IS DELIBERATE. `argocd-values.yaml` sets
# `controller.sync.timeout.seconds` to 25200 (7 h). Argo counts it from the
# operation's start, retries included, and once it has passed every later retry
# is terminated on its next reconcile, so a hung operation reads Failed by
# 25200 s plus at most the 1050 s window. Both waits here run out long before
# that. The script then reports "timed out" with the operation's state, and Argo
# still ends the operation hours later. A wait here can also cut off an
# operation Argo is still retrying, if that operation outlives the wait. The
# waits stay as they are: a terminal held for over seven hours is worse than a
# "timed out" that names the operation's state. Per-hook deadlines (ledger
# 1224) change Argo's number as they land — this round raised it, not shrank
# it — and leave these alone either way.
OPERATORS_TIMEOUT="${YADGAR_OPERATORS_TIMEOUT:-1500}"
ESTATE_TIMEOUT="${YADGAR_ESTATE_TIMEOUT:-3900}"
POLL_SECONDS="${YADGAR_POLL_SECONDS:-10}"
PROBE_ATTEMPTS="${YADGAR_PROBE_ATTEMPTS:-12}"
WITH_CLIENT=0

# THE ONE 403 THAT MEANS "THIS ADMIN ALREADY HOLDS A CREDENTIAL", verbatim from
# gateway v0.9.54 `src/http/authority.rs` (`admin_failure`). The gateway sends
# no error code beside it, and answers 403 for other reasons too, so the body
# is the only discriminator. Re-read it when the pinned gateway moves.
ZERO_CREDENTIAL_REFUSAL="may only enrol an administrator who has never held a credential"

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

# Moves $1 over $2 when their content differs, else deletes $1. Prints
# `unchanged` or `written`. Mode and ownership are $1's.
#
# RUN IN A COMMAND SUBSTITUTION, where errexit does not reach without
# `inherit_errexit`: every step returns its own failure, and each caller
# captures the result into a variable — whose assignment does carry the status —
# before it logs it.
replace_if_changed() {
  local new="$1" target="$2"
  if [[ -f "$target" ]] &&
    [[ "$(sha256sum <"$new" | awk '{ print $1 }')" == "$(sha256sum <"$target" | awk '{ print $1 }')" ]]; then
    rm -f "$new" || return 1
    echo unchanged
  else
    mv -f "$new" "$target" || return 1
    echo written
  fi
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

# A GUEST CLOCK FAR BEHIND makes every TLS certificate look not yet valid, and
# reads as download and cluster failures far from the cause. A VM restored from
# a snapshot starts with the snapshot's time until it syncs. So compare with
# the Date header of the host the tools come from, and warn — never fail: no
# network answer, no warning.
check_clock() {
  local header remote now
  # `-k`: the skew this looks for puts the clock before the certificate's
  # notBefore, and a verifying request would then fail silently. Only the Date
  # header is read, and nothing is sent.
  header="$(curl -k -fsS -I --max-time 10 https://dl.k8s.io/ 2>/dev/null | tr -d '\r' | awk 'tolower($1) == "date:" { $1 = ""; print; exit }' || true)"
  [[ -n "$header" ]] || return 0
  remote="$(date -u -d "$header" +%s 2>/dev/null || true)"
  [[ -n "$remote" ]] || return 0
  now="$(date -u +%s)"
  if ((remote - now > 300)); then
    log "[1/10] WARNING: this host's clock is $(((remote - now) / 60)) minutes behind dl.k8s.io; TLS will fail until it syncs (timedatectl)"
  fi
}

# ─── 2. sysctls ──────────────────────────────────────────────────────────────

# inotify limits kind's node needs for dozens of pods, and forwarding for its
# network. A limit is only ever RAISED: a host already at or above one keeps its
# own value, and only the raised keys are persisted in /etc/sysctl.d.
SYSCTL_KEYS=(fs.inotify.max_user_watches fs.inotify.max_user_instances net.ipv4.ip_forward)
SYSCTL_MINIMA=(524288 512 1)

ensure_sysctls() {
  local i key min live raise=0 lines=()
  for i in "${!SYSCTL_KEYS[@]}"; do
    key="${SYSCTL_KEYS[$i]}"
    min="${SYSCTL_MINIMA[$i]}"
    live="$(sysctl -n "$key" 2>/dev/null || true)"
    if ! [[ "$live" =~ ^[0-9]+$ ]] || ((live < min)); then
      raise=1
      lines+=("$key = $min")
    elif [[ -f "$SYSCTL_FILE" ]] && grep -q "^$key = " "$SYSCTL_FILE"; then
      lines+=("$key = $min")
    fi
  done
  if ((!raise)); then
    log "[2/10] sysctls already at or above what kind needs"
    return
  fi
  log "[2/10] raising ${lines[*]} in $SYSCTL_FILE"
  mkdir -p "$(dirname "$SYSCTL_FILE")"
  printf '%s\n' '# Written by yadgar bootstrap/kind-up.sh; only limits it had to raise.' "${lines[@]}" >"$SYSCTL_FILE"
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
  log "[3/10] installing $tool $version into $BIN_DIR (found: ${have:-none})"
  install -d -m 0755 "$BIN_DIR"
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
  # Created 0600 before kind writes into it; never touched again, so a rerun
  # leaves its mtime alone.
  [[ -e "$KUBECONFIG_FILE" ]] || : >"$KUBECONFIG_FILE"
  if "$BIN_DIR/kind" get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
    # Exported beside the kubeconfig and moved over it only when it differs, so
    # a rerun does not rewrite it.
    rm -f "$KUBECONFIG_FILE.new"
    touch "$KUBECONFIG_FILE.new"
    "$BIN_DIR/kind" export kubeconfig --name "$CLUSTER_NAME" --kubeconfig "$KUBECONFIG_FILE.new" >/dev/null 2>&1 || {
      rm -f "$KUBECONFIG_FILE.new"
      die "kind cluster $CLUSTER_NAME exists but its kubeconfig cannot be exported"
    }
    local result
    result="$(replace_if_changed "$KUBECONFIG_FILE.new" "$KUBECONFIG_FILE")"
    log "[4/10] kubeconfig $KUBECONFIG_FILE $result"
    [[ "$(k get --raw /readyz 2>/dev/null)" == ok ]] ||
      die "kind cluster $CLUSTER_NAME exists but its API is not ready. After a reboot its node is stopped: $RUNTIME start $CLUSTER_NAME-control-plane, then run this again"
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

# Skipped when the release is deployed at the pinned chart and was installed
# from these exact values; `helm upgrade` otherwise writes a new release revision
# on every run, changed or not.
ensure_argocd() {
  local values_sha listed
  values_sha="$(sha256sum "$ARGOCD_VALUES_FILE" | awk '{ print $1 }')"
  listed="$(h list --namespace argocd --filter '^argocd$' -o json 2>/dev/null || echo '[]')"
  if jq -e --arg chart "argo-cd-$ARGOCD_CHART_VERSION" \
    'length == 1 and .[0].status == "deployed" and .[0].chart == $chart' <<<"$listed" >/dev/null 2>&1 &&
    [[ -f "$ARGOCD_VALUES_SHA_FILE" && "$(cat "$ARGOCD_VALUES_SHA_FILE")" == "$values_sha" ]]; then
    log "[5/10] Argo CD already deployed at chart $ARGOCD_CHART_VERSION with these values"
  else
    log "[5/10] Argo CD: installing argo-cd chart $ARGOCD_CHART_VERSION"
    run h upgrade --install argocd argo-cd --repo "$ARGOCD_CHART_REPO" --version "$ARGOCD_CHART_VERSION" \
      --namespace argocd --create-namespace -f "$ARGOCD_VALUES_FILE" --wait --timeout 10m
    printf '%s\n' "$values_sha" >"$ARGOCD_VALUES_SHA_FILE"
  fi
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
#
# THE OPERATION'S REVISION IS CURRENT when it equals `spec.source.targetRevision`
# OR `status.sync.revision` — what Argo resolved the target to, which may be
# written in another form than the pin. Both are logged on every poll.
app_verdict() {
  local doc
  doc="$(cat)"
  if [[ -z "$doc" ]]; then
    echo wait
    return
  fi
  jq -r '
    (.spec.source.targetRevision // "") as $target
    | (.status.sync.revision // "") as $synced
    | (.status.operationState // {}) as $op
    | ($op.operation.sync.revision // $op.syncResult.revision // "") as $rev
    | ($op.phase // "") as $phase
    | if $phase == "" then "wait"
      elif $rev != "" and ($target != "" or $synced != "")
           and $rev != $target and $rev != $synced then "wait"
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
    "  target=\(.spec.source.targetRevision // "-") sync-revision=\(.status.sync.revision // "-") operation-revision=\(.status.operationState.operation.sync.revision // .status.operationState.syncResult.revision // "-")",
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
        log "Application $name: Synced, Healthy, operation Succeeded after $(jq -r '.status.operationState.retryCount // 0' <<<"$doc") retries"
        return 0
        ;;
      failed)
        log "Application $name: operation failed; no sync is forced"
        print_app_failure "$name" "$doc"
        log "Running this script again does not retry it: Argo does not auto-sync a revision whose sync failed. Fix the cause, then start one sync yourself: KUBECONFIG=$KUBECONFIG_FILE kubectl -n argocd patch application $name --type merge -p '{\"operation\":{\"sync\":{}}}' — and run this script again to wait for it"
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
      summary="$(jq -r '"sync=\(.status.sync.status // "-") health=\(.status.health.status // "-") operation=\(.status.operationState.phase // "-") retries=\(.status.operationState.retryCount // 0) target=\(.spec.source.targetRevision // "-") sync-revision=\(.status.sync.revision // "-") operation-revision=\(.status.operationState.operation.sync.revision // .status.operationState.syncResult.revision // "-") \(.status.operationState.message // "")"' <<<"$doc")"
    fi
    log "Application $name: $summary"
    sleep "$POLL_SECONDS"
  done
}

# Applied only when `kubectl diff` (a server-side dry run against the live
# object) finds a difference, which is logged so the field is named. A diff
# that errors falls back to the apply, which is idempotent either way.
ensure_application() {
  local step="$1" file="$2" name="$3" timeout="$4" rc=0 diff_out
  diff_out="$(k diff -f "$file" 2>&1)" || rc=$?
  case "$rc" in
    0) log "[$step/10] Application $name unchanged; not applied" ;;
    1)
      log "[$step/10] Application $name differs from $file:"
      printf '%s\n' "$diff_out" | tee -a "$LOG_FILE"
      run k apply -f "$file"
      ;;
    *)
      log "[$step/10] kubectl diff could not compare $name (exit $rc): $diff_out"
      run k apply -f "$file"
      ;;
  esac
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
  # A file whose last line has no newline would otherwise gain this entry glued
  # onto that line, corrupting both.
  if [[ -s "$HOSTS_FILE" && -n "$(tail -c 1 "$HOSTS_FILE")" ]]; then printf '\n' >>"$HOSTS_FILE"; fi
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
  # 0755 explicitly: the script runs under umask 077, and a 0644 file in a
  # 0700 directory is readable by root alone.
  install -d -m 0755 "$(dirname "$CA_FILE")"
  chmod 0644 "$tmp"
  local result
  result="$(replace_if_changed "$tmp" "$CA_FILE")"
  log "[8/10] edge CA $CA_FILE $result"
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

# THE INSTALLATION'S IDENTITY: the uid of the Secret the estate's PreSync Job
# mints once per installation and never replaces. A recreated cluster mints a
# new one, so a record from the old cluster is recognised as someone else's.
install_uid() {
  k -n "$ESTATE_NAMESPACE" get secret admin-bootstrap-token -o 'jsonpath={.metadata.uid}'
}

# Moves files aside with a timestamp; nothing a previous installation left is
# deleted.
set_aside() {
  local stamp f
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  for f in "$@"; do
    if [[ -e "$f" ]]; then
      mv "$f" "$f.stale-$stamp"
      log "[9/10] set aside $f as $f.stale-$stamp"
    fi
  done
}

# Issues an enrolment for the recorded admin and writes the token to a 0600
# file. Sets ENROLMENT_OUTCOME to `issued`, or to `enrolled` when the gateway
# answers with the zero-credential refusal. Called plainly, never under `||` or
# `if`, so errexit holds inside it.
ENROLMENT_OUTCOME=""
issue_enrolment() {
  local user_id="$1" token="$2" work code
  ENROLMENT_OUTCOME=""
  work="$(mktemp -d "$STATE_DIR/tmp.XXXXXX")"
  jq -n --arg u "$user_id" '{user_id: $u}' >"$work/body"
  code="$(admin_post issue-enrolment "$work/body" "$work/out" "$token")"
  case "$code" in
    200)
      jq -r '.token // empty' "$work/out" >"$work/token"
      [[ -s "$work/token" ]] || die "issue-enrolment answered 200 with no token"
      mkdir -p "$(dirname "$ENROLMENT_FILE")"
      install -m 0600 "$work/token" "$ENROLMENT_FILE"
      rm -rf "$work"
      ENROLMENT_OUTCOME=issued
      log "[9/10] enrolment token for $ADMIN_EXTERNAL_ID written to $ENROLMENT_FILE (0600, valid 24 hours)"
      return 0
      ;;
    403)
      if grep -qF "$ZERO_CREDENTIAL_REFUSAL" "$work/out"; then
        rm -rf "$work"
        ENROLMENT_OUTCOME=enrolled
        return 0
      fi
      ;;
  esac
  local answer
  answer="$(jq -r '.error // empty' "$work/out" 2>/dev/null || true)"
  rm -rf "$work"
  die "issue-enrolment answered ${code:-nothing}: ${answer:-no body}"
}

# The first admin, over the gateway's existing routes (ADR-0492, ADR-0655).
#
# IDEMPOTENCY IS LOCAL, because the gateway gives no other handle: a duplicate
# `external_id` is refused inside iam and the gateway answers it with the same
# opaque 503 as an outage (gateway v0.9.54, `opaque_status`), and there is no
# route to look a user up. So the user id is recorded in $ADMIN_RECORD the
# moment create-user answers 200, and create-user is sent at most once per
# installation, never retried.
#
# THE RECORD IS TIED TO THE INSTALLATION by `install_uid`. A record, token or
# client marker from another installation — `kind delete cluster` and a rerun —
# is set aside, and this installation gets its own admin.
#
#   record for this install, token younger than 23h → skip; no token is read
#   record for this install, no fresh token         → issue-enrolment for it
#                                                     (the bootstrap token may
#                                                     enrol only an admin with
#                                                     zero credentials; that
#                                                     refusal means done)
#   no record for this install                      → create-user, record,
#                                                     issue-enrolment
ensure_admin() {
  local uid recorded_uid token user_id recorded_id work code
  uid="$(install_uid)"
  [[ -n "$uid" ]] || die "Secret $ESTATE_NAMESPACE/admin-bootstrap-token has no uid; the estate has not minted it"
  if [[ -s "$ADMIN_RECORD" ]]; then
    recorded_uid="$(jq -r '.install_uid // empty' "$ADMIN_RECORD")"
    if [[ "$recorded_uid" != "$uid" ]]; then
      log "[9/10] $ADMIN_RECORD belongs to another installation (${recorded_uid:-unrecorded}, this one is $uid)"
      set_aside "$ADMIN_RECORD" "$ENROLMENT_FILE" "$CLIENT_ENROLLED_MARKER" "$CLIENT_LOGGED_IN_MARKER"
    fi
  elif [[ -e "$ENROLMENT_FILE" || -e "$CLIENT_ENROLLED_MARKER" || -e "$CLIENT_LOGGED_IN_MARKER" ]]; then
    log "[9/10] no admin record ties the enrolment token or client markers to this installation"
    set_aside "$ENROLMENT_FILE" "$CLIENT_ENROLLED_MARKER" "$CLIENT_LOGGED_IN_MARKER"
  fi
  if [[ -s "$ADMIN_RECORD" && -s "$ENROLMENT_FILE" ]] &&
    [[ -n "$(find "$ENROLMENT_FILE" -mmin -"$ENROLMENT_MAX_AGE_MINUTES" 2>/dev/null)" ]]; then
    log "[9/10] $ENROLMENT_FILE already holds a current enrolment token for this installation"
    return
  fi
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
    jq -n --arg e "$ADMIN_EXTERNAL_ID" --arg u "$user_id" --arg i "$uid" \
      '{external_id: $e, user_id: $u, install_uid: $i}' >"$ADMIN_RECORD.tmp"
    mv "$ADMIN_RECORD.tmp" "$ADMIN_RECORD"
    log "[9/10] created $ADMIN_EXTERNAL_ID as $user_id"
  fi
  issue_enrolment "$user_id" "$token"
  token=""
  if [[ "$ENROLMENT_OUTCOME" == enrolled ]]; then
    log "[9/10] $ADMIN_EXTERNAL_ID already enrolled: they hold a credential, so the bootstrap token may not enrol them again. Log in with that credential"
  fi
}

# ─── 10. the client ──────────────────────────────────────────────────────────

print_next_steps() {
  log "[10/10] done. Next, on the machine you work from:"
  cat <<EOF | tee -a "$LOG_FILE"

  pipx install yaadgaar==$(yaadgaar_version)
  yaadgaar enrol --token-file $ENROLMENT_FILE --password-stdin < <your-password-file>
  yaadgaar login --gateway $GATEWAY_URL --username $ADMIN_EXTERNAL_ID --password-stdin < <your-password-file>

  The enrolment token carries the edge CA. A machine other than this one also
  needs $GATEWAY_HOST to resolve to this host, and port $GATEWAY_PORT, which
  kind publishes on 127.0.0.1 only.
  The cluster:  KUBECONFIG=$KUBECONFIG_FILE $BIN_DIR/kubectl get applications -n argocd
  kind, kubectl and helm are in $BIN_DIR; nothing was put on PATH.
  After a reboot:  $RUNTIME start $CLUSTER_NAME-control-plane
EOF
}

# THE CLIENT'S PIN, the one `yaadgaar` row of tools.lock.
yaadgaar_version() {
  awk '$1 == "yaadgaar" && $3 == "pypi" { print $2; exit }' "$TOOLS_LOCK"
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
  local version
  version="$(yaadgaar_version)"
  [[ -n "$version" ]] || return 1
  run pipx install "yaadgaar==$version" >/dev/null
  local dir
  dir="$(pipx environment --value PIPX_BIN_DIR 2>/dev/null || echo "$HOME/.local/bin")"
  [[ -x "$dir/yaadgaar" ]] && printf '%s\n' "$dir/yaadgaar"
}

# Opt-in: enrol this machine's root as the first admin with a generated
# password kept 0600 beside the kubeconfig. Only with a client that reads the
# password from stdin; an older one is skipped, never driven through a terminal.
#
# THE CLIENT'S OUTPUT IS LOGGED, and that was checked rather than assumed: at
# yadgarhq/yadgar 6076f33 `enrol` prints the gateway, the username and the
# config directory, and `login` the gateway and directory. Neither prints the
# token, the password or the credential.
ensure_client() {
  if [[ -f "$CLIENT_ENROLLED_MARKER" && -f "$CLIENT_LOGGED_IN_MARKER" ]]; then
    log "[10/10] client already enrolled and logged in as $ADMIN_EXTERNAL_ID"
    return
  fi
  if [[ ! -f "$CLIENT_ENROLLED_MARKER" && ! -s "$ENROLMENT_FILE" ]]; then
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
  if [[ ! -f "$CLIENT_ENROLLED_MARKER" ]]; then
    log "[10/10] enrolling $ADMIN_EXTERNAL_ID with yaadgaar; password in $CLIENT_PASSWORD_FILE (0600)"
    "$bin" enrol --token-file "$ENROLMENT_FILE" --password-stdin <"$CLIENT_PASSWORD_FILE" 2>&1 | tee -a "$LOG_FILE"
    touch "$CLIENT_ENROLLED_MARKER"
  fi
  log "[10/10] logging in as $ADMIN_EXTERNAL_ID"
  "$bin" login --gateway "$GATEWAY_URL" --username "$ADMIN_EXTERNAL_ID" --password-stdin <"$CLIENT_PASSWORD_FILE" 2>&1 | tee -a "$LOG_FILE"
  touch "$CLIENT_LOGGED_IN_MARKER"
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

  check_clock
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
