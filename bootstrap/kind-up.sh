#!/usr/bin/env bash
# kind-up.sh — the whole of yadgar on one machine, in one command (ADR-0820).
#
#   sudo bootstrap/kind-up.sh [--with-client]
#   sudo bootstrap/kind-up.sh --add-user <username> [--display-name NAME] [--out FILE] [--force]
#
# --with-client enrols this machine's root as the first admin with `yaadgaar`,
# and registers yadgar with Claude Code (`yaadgaar install`) when `claude` is
# installed. --add-user, run after that, creates one more ORDINARY user (never
# an admin) as that admin and writes their enrolment token to a new root-only
# file in a root-only directory; --force replaces only a regular file, links are
# never followed, and it touches nothing else.
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
#   YADGAR_RUNTIME              podman or docker                (podman if present)
#   YADGAR_OPERATORS_TIMEOUT    seconds to wait for `operators` (1500)
#   YADGAR_ESTATE_TIMEOUT       seconds to wait for `yadgar`    (3900)
#   YADGAR_CLIENT_CONFIG        root's own client config, read by --add-user
#                               (<root's home>/.config/yaadgaar/config.json,
#                               or .config/yadgar/config.json where only an
#                               older client wrote one); refused unless owned
#                               by root and mode 0600
#
# THE PATHS ROOT EXECUTES, TRUSTS OR WRITES ARE FIXED (ledger 1556): the state
# directory /var/lib/yadgar-bootstrap (kubeconfig, log, admin record), the tool
# directory /opt/yadgar-bootstrap/bin (kind, kubectl, helm), the tools.lock
# beside this script, /etc/sysctl.d/90-yadgar-kind.conf, /etc/hosts and the
# world-readable edge CA /etc/yadgar/edge-ca.crt, and the enrolment token file
# /root/yadgar-enrolment.token. YADGAR_STATE_DIR, YADGAR_BIN_DIR,
# YADGAR_TOOLS_LOCK, YADGAR_SYSCTL_FILE, YADGAR_HOSTS_FILE, YADGAR_CA_FILE and
# YADGAR_ENROLMENT_FILE are read only when the script is NOT root, which is only
# its offline test suite (`scripts/tests/test_kind_up.py`). A real run ignores
# them and names each one it ignores on stderr. The numeric settings are refused
# unless they are digits only.

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

# A PATH ROOT EXECUTES, TRUSTS OR WRITES: its fixed default whenever this runs as
# root (ledger 1556). Under `sudo -E`, or any root invocation that keeps the
# caller's environment, an override would let a non-root caller choose which
# kind, kubectl and helm root runs, which lock vouches for them, where root keeps
# the cluster's kubeconfig and the admin's records, and which files root
# overwrites. bash's own $EUID decides — readonly, from the kernel, never from the
# environment or PATH. The overrides remain for the offline test suite, which runs
# unprivileged with a fake `id`; a real non-root run stops at `require_root`.
# An override that is set and differs is named on stderr with the path used
# instead, so it is never ignored silently.
root_fixed_path() {
  local name="$1" default="$2"
  if ((EUID == 0)); then
    if [[ -n "${!name:-}" && "${!name}" != "$default" ]]; then
      printf 'kind-up.sh: %s is ignored when run as root; using %s\n' "$name" "$default" >&2
    fi
    printf '%s\n' "$default"
  else
    printf '%s\n' "${!name:-$default}"
  fi
}

STATE_DIR="$(root_fixed_path YADGAR_STATE_DIR /var/lib/yadgar-bootstrap)"
LOG_FILE="$STATE_DIR/kind-up.log"
KUBECONFIG_FILE="$STATE_DIR/kubeconfig"
ADMIN_RECORD="$STATE_DIR/admin.json"
CLIENT_PASSWORD_FILE="$STATE_DIR/client-password"
# WRITTEN THE MOMENT `enrol` SUCCEEDS, because the enrolment token is single-use:
# with the marker present the token is never sent again, never offered again,
# and the bootstrap token is not read.
CLIENT_ENROLLED_MARKER="$STATE_DIR/client-enrolled"
# LEGACY: releases up to v0.24.17 ran `login` after `enrol` and marked it here.
# `enrol` alone stores the credential (yadgar v0.1.2 `src/login.rs`: `enrol` and
# `login` both end in `reconcile` and `config.save`), so nothing writes this any
# more; it is only set aside with the other markers of a replaced installation.
CLIENT_LOGGED_IN_MARKER="$STATE_DIR/client-logged-in"
# ROOT'S OWN CLIENT CONFIG, where --with-client enrolled the admin (the
# client's default under yadgar v0.1.6 `config::base_dir`: ~/.config/yaadgaar).
# --add-user reads the admin's bearer token from it, so the path comes from the
# password database for uid 0 — never from $HOME, XDG_CONFIG_HOME,
# YADGAR_CONFIG_DIR or YAADGAAR_CONFIG_DIR, which `sudo -E` or a caller's
# environment could point at another user's credential. The override is
# explicit and passes the same root-owned, 0600 check. See client_config_file.
# ROOT'S HOME, FROM THE PASSWORD DATABASE ONLY — there is deliberately no
# environment override, which a `sudo -E` caller could point at their own home
# and so at their own `yaadgaar`. `getent` is found on PATH like every other
# tool here: real `sudo` applies `secure_path`, so a caller cannot steer PATH.
root_home() {
  local home
  home="$(getent passwd 0 2>/dev/null | cut -d: -f6 || true)"
  printf '%s\n' "${home:-/root}"
}

# THE WHOLE RUN USES ROOT'S OWN HOME (review of #47). `sudo -E` keeps the
# caller's HOME and XDG directories, and every root-side client step — pipx,
# `yaadgaar enrol`, `verify`, `install`, and helm's cache — would otherwise read
# and write under that caller's home, or run a `yaadgaar` they put there. Pinned
# once in `main`, so no step can be missed: HOME is root's, the XDG and yadgar
# config overrides are unset (YADGAR_CONFIG_DIR for clients up to 0.1.4,
# YAADGAAR_CONFIG_DIR from 0.1.5), and pipx installs under root's home.
#
# THE TOOLS' OWN REDIRECTS GO TOO: CURL_HOME (curl reads its .curlrc, which can
# add `--trace` or a proxy; every call also passes `-q` first, the only flag that
# stops that), KUBECTL_EXTERNAL_DIFF (a program `kubectl diff` would run), and
# every HELM_* variable (HELM_CACHE_HOME, HELM_CONFIG_HOME, HELM_DATA_HOME,
# HELM_PLUGINS, HELM_REGISTRY_CONFIG, HELM_REPOSITORY_CONFIG and the rest), so
# helm falls back to root's home.
pin_root_environment() {
  HOME="$(root_home)"
  export HOME
  unset XDG_CONFIG_HOME XDG_DATA_HOME XDG_STATE_HOME XDG_CACHE_HOME YADGAR_CONFIG_DIR YAADGAAR_CONFIG_DIR
  unset CURL_HOME KUBECTL_EXTERNAL_DIFF
  local var
  for var in "${!HELM_@}"; do unset "$var"; done
  export PIPX_HOME="$HOME/.local/share/pipx" PIPX_BIN_DIR="$HOME/.local/bin"
}

# THE PYTHON THAT CREATES AND READS SECRET FILES: /usr/bin/python3 where the
# distribution puts it (Debian, Ubuntu, Fedora), else python3 on PATH — which,
# like every tool here, is root's `secure_path` under sudo.
kind_up_python() {
  if [[ -x /usr/bin/python3 ]]; then
    printf '%s\n' /usr/bin/python3
  else
    command -v python3 2>/dev/null
  fi
}

# Gateway text is printed only after control characters are removed, so an
# answer cannot forge log lines or drive the terminal.
printable() {
  tr -d '\000-\037\177'
}
# Set by client_config_file, on first use only.
CLIENT_CONFIG_FILE=""

# WHERE ROOT'S CREDENTIAL IS, decided once, when something reads it (ledger
# 1566). An explicit YADGAR_CLIENT_CONFIG wins and never falls back. Otherwise
# ~/.config/yaadgaar/config.json, where yaadgaar 0.1.5 and later keep it.
#
# A HOST ENROLLED BY kind-up v0.24.20 OR OLDER holds it where yaadgaar 0.1.3 put
# it, ~/.config/yadgar/config.json. When the new path has no entry at all and
# the old one has, the old one is read where it is, through the same no-follow,
# root-only READ_CLIENT_CONFIG_PY, and one note says so on stderr. Nothing is
# moved, copied or created: yadgar 0.1.6 `config/legacy.rs` declines to migrate,
# because that directory also holds the memory engine's secrets. A symlink at
# the new path counts as an entry, so the reader refuses it rather than this
# falling back past it.
client_config_file() {
  if [[ -n "$CLIENT_CONFIG_FILE" ]]; then
    return
  fi
  if [[ -n "${YADGAR_CLIENT_CONFIG:-}" ]]; then
    CLIENT_CONFIG_FILE="$YADGAR_CLIENT_CONFIG"
    return
  fi
  local home new old
  home="$(root_home)"
  new="$home/.config/yaadgaar/config.json"
  old="$home/.config/yadgar/config.json"
  CLIENT_CONFIG_FILE="$new"
  if [[ ! -e "$new" && ! -L "$new" ]] && [[ -e "$old" || -L "$old" ]]; then
    CLIENT_CONFIG_FILE="$old"
    printf 'kind-up.sh: no client config at %s; reading %s, written by an older yaadgaar (0.1.4 or earlier), where it is\n' "$new" "$old" >&2
  fi
}
# One record per user --add-user created, tied to the installation like
# $ADMIN_RECORD.
USERS_DIR="$STATE_DIR/users"
ARGOCD_VALUES_SHA_FILE="$STATE_DIR/argocd-values.sha256"
# A DIRECTORY OF ITS OWN: a kind, kubectl or helm the host already has in a
# shared bin directory is never replaced — never /usr/local/bin.
BIN_DIR="$(root_fixed_path YADGAR_BIN_DIR /opt/yadgar-bootstrap/bin)"
TOOLS_LOCK="$(root_fixed_path YADGAR_TOOLS_LOCK "$SCRIPT_DIR/tools.lock")"
SYSCTL_FILE="$(root_fixed_path YADGAR_SYSCTL_FILE /etc/sysctl.d/90-yadgar-kind.conf)"
HOSTS_FILE="$(root_fixed_path YADGAR_HOSTS_FILE /etc/hosts)"
CA_FILE="$(root_fixed_path YADGAR_CA_FILE /etc/yadgar/edge-ca.crt)"
ENROLMENT_FILE="$(root_fixed_path YADGAR_ENROLMENT_FILE /root/yadgar-enrolment.token)"
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
#
# DIGITS ONLY, REFUSED HERE BEFORE ANY STEP RUNS (review of #48). bash evaluates
# a variable named inside arithmetic as an expression of its own, so a value such
# as `BASH_VERSINFO[$(cmd)]` would run cmd — as root — when `wait_app` computes
# its deadline or `probe_edge` counts its attempts. The value is not echoed back,
# so it cannot drive the terminal; `10#` reads a leading zero as decimal.
numeric_setting() {
  local name="$1" default="$2" unit="$3" value
  value="${!name:-$default}"
  if [[ ! "$value" =~ ^[0-9]+$ ]]; then
    printf 'kind-up.sh: %s must be a whole number of %s (digits only)\n' "$name" "$unit" >&2
    return 1
  fi
  printf '%s\n' "$((10#$value))"
}
OPERATORS_TIMEOUT="$(numeric_setting YADGAR_OPERATORS_TIMEOUT 1500 seconds)" || exit 1
ESTATE_TIMEOUT="$(numeric_setting YADGAR_ESTATE_TIMEOUT 3900 seconds)" || exit 1
POLL_SECONDS="$(numeric_setting YADGAR_POLL_SECONDS 10 seconds)" || exit 1
PROBE_ATTEMPTS="$(numeric_setting YADGAR_PROBE_ATTEMPTS 12 attempts)" || exit 1
WITH_CLIENT=0
ADD_USER=0
ADD_USER_ID=""
ADD_USER_DISPLAY_NAME=""
ADD_USER_OUT=""
ADD_USER_FORCE=0

# THE WORKSPACE HEADER ON --add-user's ADMIN CALLS. The gateway's bearer admin
# path attests the caller through the same code as `tools/call`, which requires
# `x-yadgar-project` and answers 400 without it; the admin verbs then ignore its
# value (measured 2026-10-17: two different values both created a user). A
# fixed, recognisable value rather than a real workspace, until the gateway stops
# asking for one on admin routes (ledger 1545).
ADMIN_PROJECT_HEADER="yadgar/admin"

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
  header="$(curl -q -k -fsS -I --max-time 10 https://dl.k8s.io/ 2>/dev/null | tr -d '\r' | awk 'tolower($1) == "date:" { $1 = ""; print; exit }' || true)"
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
  curl -q -fsSL --retry 3 -o "$work/download" "$url" || {
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
# message, the resources the sync failed, and the Application's conditions.
#
# NOT per-resource health: Argo does not persist `.status.resources[].health`
# onto the Application CR by default (`controller.resource.health.persist`
# unset). This script's own bootstrap/argocd-values.yaml does not set that key
# either, so a kind-up.sh install defaults the same way, but the live
# corroboration is from kind-yadgar's ACTUAL argo-cd install, which is
# yadgarhq/argocd's, not one this script produced: MEASURED 2026-10-02 that
# its `argocd-cmd-params-cm` leaves the key unset too (same chart, same
# `v3.1.8`), and that a live `kubectl get application ... -o json` there
# carries no `.health` on any of its `.status.resources` entries. So a kubectl
# read of it here is always empty — printing it would report a genuinely
# unhealthy resource as having nothing to say. The note below points at the
# command that reads it live instead; `argocd` itself is a separate tool this
# script does not install (see `tools.lock`).
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
    (.status.conditions // [] | .[] | "  condition: \(.type): \(.message)")
  ' <<<"$doc" | tee -a "$LOG_FILE" >&2
  cat <<-NOTE | tee -a "$LOG_FILE" >&2
	  per-resource health is not read here: kubectl never sees it (Argo does not persist it on the Application CR by default). argocd (not installed by this script) reads it live instead, scoped to a throwaway kubeconfig copy so it never touches your own:
	    (
	      set -eu
	      TMPKC=\$(mktemp)
	      trap 'rm -f "\$TMPKC"' EXIT
	      "$BIN_DIR/kubectl" --kubeconfig "$KUBECONFIG_FILE" config view --minify --flatten --context "kind-$CLUSTER_NAME" > "\$TMPKC"
	      [ -s "\$TMPKC" ] || exit 1
	      "$BIN_DIR/kubectl" --kubeconfig "\$TMPKC" config set-context "kind-$CLUSTER_NAME" --namespace argocd
	      KUBECONFIG="\$TMPKC" argocd app get $name --core --kube-context "kind-$CLUSTER_NAME" -o json | jq '.status.resources[].health'
	    )
	NOTE
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
    code="$(curl -q -sS -o /dev/null -w '%{http_code}' --cacert "$CA_FILE" "$GATEWAY_URL/" 2>/dev/null || true)"
    if [[ "$code" == 405 ]]; then
      log "[8/10] $GATEWAY_URL/ answered 405 over the edge CA"
      return
    fi
    sleep "$POLL_SECONDS"
  done
  die "$GATEWAY_URL/ answered ${code:-nothing}, expected 405"
}

# ─── 9. the first administrator ──────────────────────────────────────────────

# POSTs one admin request. The secret header — `name: value` in $4 — travels in
# a curl config read from stdin, so it is in no argv and no file; any further
# arguments go to curl as they are. Prints the HTTP status; the body lands in
# $3, which the caller deletes.
gateway_post() {
  local path="$1" body_file="$2" out_file="$3" secret_header="$4"
  shift 4
  printf 'header = "%s"\n' "$secret_header" |
    curl -q --config - -sS -o "$out_file" -w '%{http_code}' --cacert "$CA_FILE" \
      -H 'content-type: application/json' "$@" --data-binary "@$body_file" \
      "$GATEWAY_URL/admin/$path" || true
}

# The bootstrap token's admin request.
admin_post() {
  gateway_post "$1" "$2" "$3" "x-yadgar-bootstrap-token: $4"
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

# Moves a redeemed enrolment token out of the path the next steps would name.
# Renamed, not deleted, so the file keeps its 0600 mode and nothing is lost; it
# can never be redeemed again. $1 is the step number to log under.
retire_spent_token() {
  [[ -e "$ENROLMENT_FILE" ]] || return 0
  local spent
  spent="$ENROLMENT_FILE.redeemed-$(date -u +%Y%m%dT%H%M%SZ)"
  mv "$ENROLMENT_FILE" "$spent"
  log "[$1/10] the enrolment token was redeemed by this host's client; moved $ENROLMENT_FILE to $spent"
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
  answer="$(jq -r '.error // empty' "$work/out" 2>/dev/null | printable || true)"
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
  # ENROLLED HERE BY --with-client: the token was redeemed, so it is neither
  # "current" — its mtime says nothing about whether it was spent (ledger 1544) —
  # nor worth a new one, and the bootstrap token is not read.
  if [[ -s "$ADMIN_RECORD" && -f "$CLIENT_ENROLLED_MARKER" ]]; then
    log "[9/10] admin $ADMIN_EXTERNAL_ID is enrolled on this host's client; no enrolment token is needed"
    retire_spent_token 9
    return
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
      answer="$(jq -r '.error // empty' "$work/out" 2>/dev/null | printable || true)"
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

# THE TWO WAYS A MACHINE THAT HOLDS NO CREDENTIAL JOINS (ledger 1555). A plain
# `yaadgaar login` fails there: the gateway's certificate is signed by this
# install's private CA, and the machine has no anchor for it. `login --ca-file`
# (yadgar#61, first in 0.1.9) supplies one; `admin issue-enrolment` (yadgar#62,
# first in 0.1.10) mints a token that carries the CA, redeemed with `enrol`.
# These lines name the first release that has both; tools.lock pins that release
# or a later one (ledger 1623).
CLIENT_MIN_FOR_JOINING="0.1.10"

# WHAT ROOT'S INSTALLED CLIENT CAN DO, read from the binary and never from the
# lock row: a client kept at an older version (credential in the old directory,
# a failed pre-flight, no --with-client on this run) has not been upgraded to the
# pin. Printed only where this host's root is enrolled (the marker); where the
# credential is held elsewhere there is no root client to speak of. One sentence
# with a leading space, or nothing.
root_client_note() {
  [[ -f "$CLIENT_ENROLLED_MARKER" ]] || return 0
  local bin="$PIPX_BIN_DIR/yaadgaar" have="" rc=0
  if [[ ! -x "$bin" ]]; then
    printf ' This host'"'"'s root has no client.'
    return 0
  fi
  have="$("$bin" --version 2>/dev/null | awk '{ print $2; exit }' || true)"
  if [[ -n "$have" ]]; then
    version_older "$have" "$CLIENT_MIN_FOR_JOINING" || rc=$?
  else
    rc=2
  fi
  have="$(printf '%s' "${have:-unknown}" | printable)"
  if [[ "$rc" == 1 ]]; then
    printf ' The root client here is %s, which has "yaadgaar admin issue-enrolment".' "$have"
  else
    printf ' The root client here is %s, which lacks "yaadgaar admin issue-enrolment"; a rerun with --with-client upgrades it.' "$have"
  fi
}

another_machine_steps() {
  cat <<EOF
  A. Log in with this install's CA. Copy the CA certificate from this host, where
     it is world-readable, to the other machine (for example as ca.pem):
       scp <this-host>:$CA_FILE ca.pem
     Then, on the other machine:
       pipx install 'yaadgaar>=$CLIENT_MIN_FOR_JOINING'
       yaadgaar login --gateway $GATEWAY_URL --username $ADMIN_EXTERNAL_ID --ca-file ca.pem --password-stdin < <your-password-file>
  B. Or enrol it. The issuing client must be yaadgaar>=$CLIENT_MIN_FOR_JOINING.$(root_client_note)
     On a machine whose client is new
     enough and holds an administrator credential, with the user_id that
     $ADMIN_RECORD records:
       yaadgaar admin issue-enrolment --user-id <user-id> --out <new-token-file>
     Hand the file over privately. The other machine installs the same client and
     redeems the file with "yaadgaar enrol", which sets that user's password.
  Re-issue or reset: run the same issue-enrolment command again, with
  --revoke-existing after a lost machine. Two warnings:
    - Re-issuing the ADMIN's own enrolment sets a new password when it is redeemed,
      so $CLIENT_PASSWORD_FILE is stale after that.
    - --revoke-existing ends root's credential on this host, if it is for the
      same user; this host's root client then needs a new login or enrolment.
EOF
}

# THREE STATES, read from the files rather than from this run's flags, so a plain
# rerun after --with-client never offers the token --with-client redeemed:
#   enrolled here   the marker: the credential is in root's client config
#   token waiting   a token this installation issued, not yet redeemed
#   neither         the admin enrolled elsewhere and holds a credential
print_next_steps() {
  local version
  version="$(yaadgaar_version)"
  if [[ -f "$CLIENT_ENROLLED_MARKER" ]]; then
    client_config_file
    log "[10/10] done. This host's root is enrolled as $ADMIN_EXTERNAL_ID."
    cat <<EOF | tee -a "$LOG_FILE"

  The credential is in $(dirname "$CLIENT_CONFIG_FILE"), the password in $CLIENT_PASSWORD_FILE (0600).
  Another person:  sudo $SCRIPT_DIR/kind-up.sh --add-user <username>
  $ADMIN_EXTERNAL_ID on another machine, by either route:
$(another_machine_steps)
EOF
  elif [[ -s "$ENROLMENT_FILE" ]]; then
    log "[10/10] done. Next, on the machine you work from:"
    cat <<EOF | tee -a "$LOG_FILE"

  pipx install yaadgaar==$version
  yaadgaar enrol --token-file $ENROLMENT_FILE --password-stdin < <your-password-file>

  enrol sets the password and stores the credential; no login is needed after it.
  The enrolment token carries the edge CA.
EOF
  else
    log "[10/10] done. $ADMIN_EXTERNAL_ID already holds a credential; on a machine without one, by either route:"
    cat <<EOF | tee -a "$LOG_FILE"

$(another_machine_steps)
EOF
  fi
  cat <<EOF | tee -a "$LOG_FILE"

  A machine other than this one also needs $GATEWAY_HOST to resolve to this
  host, and port $GATEWAY_PORT, which kind publishes on 127.0.0.1 only.
  The cluster:  KUBECONFIG=$KUBECONFIG_FILE $BIN_DIR/kubectl get applications -n argocd
  kind, kubectl and helm are in $BIN_DIR; nothing was put on PATH.
  After a reboot:  $RUNTIME start $CLUSTER_NAME-control-plane
EOF
}

# THE CLIENT'S PIN, the one `yaadgaar` row of tools.lock.
yaadgaar_version() {
  awk '$1 == "yaadgaar" && $3 == "pypi" { print $2; exit }' "$TOOLS_LOCK"
}

# ROOT'S OWN yaadgaar ONLY, where root's pipx puts it — never the first one on
# PATH, which a caller's environment could name.
yaadgaar_bin() {
  if [[ -x "$PIPX_BIN_DIR/yaadgaar" ]]; then
    printf '%s\n' "$PIPX_BIN_DIR/yaadgaar"
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
  dir="$(pipx environment --value PIPX_BIN_DIR 2>/dev/null || echo "$PIPX_BIN_DIR")"
  [[ -x "$dir/yaadgaar" ]] && printf '%s\n' "$dir/yaadgaar"
}

# WHETHER VERSION $1 IS OLDER THAN $2, by release numbers and then a, b, rc
# pre-releases below the final release (PEP 440's order for the versions this
# client publishes). A version outside that shape is never "older", so an
# unreadable answer never triggers a replacement. Exit 0 older, 1 not, 2
# unparseable.
# shellcheck disable=SC2016
VERSION_OLDER_PY='
import re, sys
def key(v):
    m = re.fullmatch(r"(\d+(?:\.\d+)*)(?:(a|b|rc)(\d+))?", v)
    if not m:
        sys.exit(2)
    rel = tuple(int(x) for x in m.group(1).split("."))
    rel += (0,) * (8 - len(rel))
    pre = ({"a": 0, "b": 1, "rc": 2}[m.group(2)], int(m.group(3))) if m.group(2) else (3, 0)
    return rel, pre
sys.exit(0 if key(sys.argv[1]) < key(sys.argv[2]) else 1)
'
version_older() {
  local py
  py="$(kind_up_python)" || return 2
  "$py" -I -c "$VERSION_OLDER_PY" "$1" "$2"
}

# COPIES ROOT'S OLD CLIENT CONFIG TO THE NEW DIRECTORY, through descriptors only
# (ledger 1573). The source is opened without following a symlink and fstat-ed on
# that descriptor: a regular file, owned by this uid, mode exactly 0600, read
# capped at 1 MiB. The destination directory is made 0700 (or an existing one must
# be a real directory owned by this uid, not a symlink), and the file is created
# with O_EXCL | O_NOFOLLOW at 0600 relative to that directory's descriptor, so an
# existing entry of any kind is never replaced or written through. Nothing about
# the contents reaches stdout or stderr. A partial copy is unlinked.
# shellcheck disable=SC2016
COPY_CLIENT_CONFIG_PY='
import os, stat, sys
src, dst_dir, euid = sys.argv[1], sys.argv[2], int(sys.argv[3])
name = "config.json"
try:
    sfd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
except OSError as e:
    sys.exit(f"the old config {src} cannot be opened ({e.strerror})")
st = os.fstat(sfd)
if not stat.S_ISREG(st.st_mode):
    sys.exit(f"the old config {src} is not a regular file")
if (st.st_uid, stat.S_IMODE(st.st_mode)) != (euid, 0o600):
    sys.exit(f"the old config {src} is owner/mode {st.st_uid} {stat.S_IMODE(st.st_mode):o}, not {euid} 600")
data = os.read(sfd, (1 << 20) + 1)
if len(data) > 1 << 20:
    sys.exit(f"the old config {src} is larger than 1 MiB")
try:
    os.mkdir(dst_dir, 0o700)
except FileExistsError:
    pass
except OSError as e:
    sys.exit(f"{dst_dir} cannot be created ({e.strerror})")
try:
    dfd = os.open(dst_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
except OSError as e:
    sys.exit(f"{dst_dir} cannot be used as a directory ({e.strerror})")
dst = os.fstat(dfd)
if dst.st_uid != euid or stat.S_IMODE(dst.st_mode) & 0o077:
    sys.exit(f"{dst_dir} is owner/mode {dst.st_uid} {stat.S_IMODE(dst.st_mode):o}, not {euid} with no group or other access")
try:
    ofd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dfd)
except OSError as e:
    sys.exit(f"{dst_dir}/{name} cannot be created ({e.strerror})")
try:
    os.fchmod(ofd, 0o600)
    view = memoryview(data)
    while view:
        view = view[os.write(ofd, view):]
    os.fsync(ofd)
except OSError as e:
    os.unlink(name, dir_fd=dfd)
    sys.exit(f"{dst_dir}/{name} cannot be written ({e.strerror})")
'
copy_old_client_config() {
  local py
  py="$(kind_up_python)" || {
    printf 'python3 is not available\n' >&2
    return 1
  }
  "$py" -I -c "$COPY_CLIENT_CONFIG_PY" "$1" "$2" "$EUID"
}

# ROOT'S ENROLLED CLIENT FOLLOWS tools.lock (ledger 1554), upward only, and only
# where the new client can find its credential. yaadgaar 0.1.5 and later read
# only ~/.config/yaadgaar, and `yaadgaar serve`, which Claude Code starts with no
# environment, reads nothing else. So:
#   no version answer, or not older    kept (never a downgrade)
#   credential not a regular file at   kept, and named; but when the new path has
#   ~/.config/yaadgaar                 no entry and ~/.config/yadgar has one, that
#                                      one is copied across first (below)
#   otherwise                          pre-flight, then `pipx install --force`
#
# THE PRE-FLIGHT EXISTS BECAUSE pipx 1.8.0 DELETES THE VENV when a forced install
# fails (`remove_venv` on any error), which would take root's working client with
# it. So the pinned wheel is first fetched with the client venv's own pip into a
# scratch directory: if that fails — no network, no wheel for this platform — the
# old client is kept and the run warns. If the forced install still fails after
# that, root has no client, and the run stops with the command that restores one.
#
# THE OLD CREDENTIAL IS COPIED FIRST (ledger 1573, ruled by Max 2026-10-18). A host
# enrolled by yaadgaar 0.1.3 holds it in ~/.config/yadgar/config.json, which
# 0.1.5 and later do not read. When the new path has no entry at all and the old
# one is a root-owned, mode 0600 regular file, copy_old_client_config copies it
# to the new path, after the pre-flight and before the forced install. The old
# file stays: yadgar 0.1.6 `config/legacy.rs` declines to migrate because that
# directory also holds the memory engine's secrets. Neither `login` nor `enrol`
# runs: a `login` into an empty new directory has no CA for this edge, which only
# an enrolment token carries, and the bootstrap token cannot enrol an admin who
# holds a credential (ADR-0655).
upgrade_enrolled_client() {
  local pin have cfg old copy=0 rc=0 tmp note
  [[ -x "$PIPX_BIN_DIR/yaadgaar" ]] || return 0
  pin="$(yaadgaar_version)"
  [[ -n "$pin" ]] || return 0
  have="$("$PIPX_BIN_DIR/yaadgaar" --version 2>/dev/null | awk '{ print $2; exit }' || true)"
  if [[ -z "$have" ]]; then
    log "[10/10] root's client did not report its version; kept"
    return 0
  fi
  version_older "$have" "$pin" || rc=$?
  case "$rc" in
    0) ;;
    1)
      if [[ "$have" != "$pin" ]]; then
        log "[10/10] root's client is yaadgaar $have, newer than the pinned $pin; kept"
      fi
      return 0
      ;;
    *)
      log "[10/10] root's client reported version '$(printf '%s' "$have" | printable)', which cannot be compared with $pin; kept"
      return 0
      ;;
  esac
  cfg="$(root_home)/.config/yaadgaar/config.json"
  old="$(root_home)/.config/yadgar/config.json"
  if [[ ! -e "$cfg" && ! -L "$cfg" && ( -e "$old" || -L "$old" ) ]]; then
    copy=1
  elif [[ ! -f "$cfg" || -L "$cfg" ]]; then
    log "[10/10] root's client is yaadgaar $have, not the pinned $pin; kept, because its credential is not at $cfg, where the pinned client reads it"
    return 0
  fi
  tmp="$(mktemp -d "$STATE_DIR/tmp.XXXXXX")"
  if ! pipx runpip yaadgaar download --no-deps --only-binary=:all: "yaadgaar==$pin" -d "$tmp" >/dev/null 2>&1; then
    rm -rf "$tmp"
    log "[10/10] WARNING: yaadgaar==$pin could not be fetched; root's client yaadgaar $have kept, untouched"
    return 0
  fi
  rm -rf "$tmp"
  if ((copy)); then
    if ! note="$(copy_old_client_config "$old" "$(dirname "$cfg")" 2>&1)"; then
      log "[10/10] root's client is yaadgaar $have, not the pinned $pin; kept, because $(printf '%s' "$note" | printable); not copied to $cfg"
      return 0
    fi
    log "[10/10] copied root's client config $old to $cfg; the old file stays"
  fi
  if ! run pipx install --force "yaadgaar==$pin" >/dev/null; then
    die "upgrading root's client $have→$pin failed, and pipx removes the old client when a forced install fails. Put one back: pipx install --force yaadgaar==$pin"
  fi
  log "[10/10] upgraded root's client $have→$pin; credential stays at $cfg"
}

# Registers the MCP server and hooks for Claude Code (ledger 1540), ONLY when
# `claude` is installed for this user — on PATH, or at ~/.local/bin, which
# sudo's secure_path hides. Without it, the command to run later is printed.
#
# WRITE-FREE ON A RERUN: `yaadgaar verify` first, and `install` only when it
# reports drift; `install` also mints the install id into the client config.
# A FAILED `install` IS A WARNING, NOT A FAILURE: the estate and the credential
# are already in place, and it can be run again by hand.
ensure_agent_registration() {
  local bin="${1:-}" claude=""
  claude="$(command -v claude 2>/dev/null || true)"
  if [[ -z "$claude" && -x "$HOME/.local/bin/claude" ]]; then claude="$HOME/.local/bin/claude"; fi
  if [[ -z "$claude" ]]; then
    log "[10/10] Claude Code (claude) is not installed for the user of $HOME; once it is, register yadgar with it: yaadgaar install"
    return
  fi
  if [[ -z "$bin" ]]; then
    bin="$(yaadgaar_bin)" || {
      log "[10/10] WARNING: yaadgaar could not be found or installed; register yadgar with Claude Code yourself: yaadgaar install"
      return
    }
  fi
  if "$bin" verify >/dev/null 2>&1; then
    log "[10/10] yadgar is already registered with Claude Code ($claude)"
    return
  fi
  log "[10/10] registering yadgar with Claude Code ($claude): yaadgaar install"
  if ! "$bin" install 2>&1 | tee -a "$LOG_FILE"; then
    log "[10/10] WARNING: yaadgaar install failed; everything else is in place. Run yaadgaar install again once the cause is fixed"
  fi
}

# Opt-in: enrol this machine's root as the first admin with a generated
# password kept 0600 beside the kubeconfig. Only with a client that reads the
# password from stdin; an older one is skipped, never driven through a terminal.
#
# NO `login` FOLLOWS: `enrol` stores the same credential `login` would — both end
# in `reconcile` and `config.save` in yadgar v0.1.2 `src/login.rs` — and an
# enrol-only user made MCP calls on the 2026-10-17 VM run.
#
# THE CLIENT'S OUTPUT IS LOGGED, and that was checked rather than assumed: at
# yadgarhq/yadgar 6076f33 `enrol` prints the gateway, the username and the
# config directory. It prints neither the token, the password nor the
# credential.
ensure_client() {
  if [[ -f "$CLIENT_ENROLLED_MARKER" ]]; then
    log "[10/10] client already enrolled as $ADMIN_EXTERNAL_ID"
    upgrade_enrolled_client
    ensure_agent_registration
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
  if ! "$bin" enrol --token-file "$ENROLMENT_FILE" --password-stdin <"$CLIENT_PASSWORD_FILE" 2>&1 | tee -a "$LOG_FILE"; then
    # THE CRASH WINDOW: a run that stopped after a successful enrol and before
    # the marker re-sends the spent token here, and the gateway refuses it. A
    # credential for this gateway already in root's client config is the sign;
    # recording the marker by hand ends the loop.
    local stored="" py
    # Read through the same no-follow, root-only reader --add-user uses.
    if py="$(kind_up_python)"; then
      client_config_file
      stored="$("$py" -I -c "$READ_CLIENT_CONFIG_PY" "$CLIENT_CONFIG_FILE" "$EUID" 2>/dev/null | head -n 1 || true)"
    fi
    if [[ -n "$stored" && "${stored%/}" == "${GATEWAY_URL%/}" ]]; then
      die "yaadgaar enrol failed, and root's client already holds a credential for $GATEWAY_URL. If an earlier run enrolled and stopped before recording it, the token is spent: record that with: touch $CLIENT_ENROLLED_MARKER — then run this again"
    fi
    die "yaadgaar enrol failed; $ENROLMENT_FILE is kept and was not marked redeemed"
  fi
  # The marker before the rename: a run that stops between them must not send
  # the spent token again.
  touch "$CLIENT_ENROLLED_MARKER"
  retire_spent_token 10
  ensure_agent_registration "$bin"
}

# ─── --add-user ──────────────────────────────────────────────────────────────

# One admin request as the enrolled admin: the bearer goes on curl's stdin like
# the bootstrap token, the workspace header on argv (it is no secret).
user_admin_post() {
  gateway_post "$1" "$2" "$3" "authorization: Bearer $4" -H "x-yadgar-project: $ADMIN_PROJECT_HEADER"
}

# Dies with the gateway's answer to one --add-user request.
add_user_refused() {
  local verb="$1" code="$2" out="$3" answer hint=""
  answer="$(jq -r '.error // empty' "$out" 2>/dev/null | printable || true)"
  rm -f "$out"
  case "$code" in
    401) hint=" The admin credential in $CLIENT_CONFIG_FILE was refused; renew it: yaadgaar login --gateway $GATEWAY_URL --username $ADMIN_EXTERNAL_ID --password-stdin < $CLIENT_PASSWORD_FILE" ;;
    503) [[ "$verb" == create-user ]] &&
      hint=" The gateway answers a username that already exists with this same opaque 503 as an outage, by design (ADR-0927). If $ADD_USER_ID was added before without a record in $USERS_DIR, choose another username; otherwise check the estate is healthy." ;;
  esac
  die "$verb answered ${code:-nothing}: ${answer:-no body}.$hint"
}

# What the new user runs. The token is never printed: the file is handed over.
print_add_user_steps() {
  local out="$1"
  cat <<EOF | tee -a "$LOG_FILE"

  Hand $out to $ADD_USER_ID over a private channel; it is single-use and
  valid 24 hours. For a Unix user <user> on this host:
    install -o <user> -m 0600 $out ~<user>/yadgar-enrolment.token
  Then, as that user:
    pipx install yaadgaar==$(yaadgaar_version)
    yaadgaar enrol --token-file ~/yadgar-enrolment.token --password-stdin < <password-file>
    mkdir -p .yadgar && echo <owner>/<repo> > .yadgar/project-id   # in each repository
    yaadgaar install                                                # when Claude Code is installed
  enrol sets the password and stores the credential; no login is needed after it.
  A machine other than this one also needs $GATEWAY_HOST to resolve to this host,
  and port $GATEWAY_PORT.
EOF
}

# THE ADMIN'S CREDENTIAL, READ ONCE THROUGH ONE DESCRIPTOR: opened without
# following a symlink, checked with fstat on that same descriptor (a regular
# file, owned by this uid, mode 0600), then read from it. Prints the gateway and
# the bearer on two lines, to a pipe and never to argv. No path is checked and
# then reopened, so nothing can be swapped in between.
# shellcheck disable=SC2016
READ_CLIENT_CONFIG_PY='
import json, os, stat, sys
path, euid = sys.argv[1], int(sys.argv[2])
try:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
except OSError as e:
    sys.exit(f"no readable client credential at {path} ({e.strerror})")
st = os.fstat(fd)
if not stat.S_ISREG(st.st_mode):
    sys.exit(f"{path} is not a regular file")
if (st.st_uid, stat.S_IMODE(st.st_mode)) != (euid, 0o600):
    sys.exit(f"{path} is owner/mode {st.st_uid} {stat.S_IMODE(st.st_mode):o}, not {euid} 600")
with os.fdopen(fd, "rb") as fh:
    cfg = json.loads(fh.read(1 << 20) or b"{}")
print(cfg.get("gateway") or "")
print(cfg.get("token") or "")
'

# THE TOKEN FILE, CREATED WITHOUT EVER FOLLOWING A LINK (reviews of #47). The
# path is walked from `/` one component at a time, each opened
# O_DIRECTORY|O_NOFOLLOW relative to the last, so a symlink anywhere in it is
# refused rather than followed. The final directory is checked with fstat on
# its own descriptor: owned by this uid and writable by no group or other user,
# so nobody else can plant or swap an entry in it. Everything after is relative
# to that descriptor. An existing entry is refused, and with --force only a
# regular file is unlinked; the file is then created O_CREAT|O_EXCL|O_NOFOLLOW,
# 0600. A write that fails after the create unlinks the file, so a rerun never
# finds an empty file and calls it a fresh token. `check` runs every test and
# writes nothing; `write` reads the token from stdin.
# shellcheck disable=SC2016
CREATE_TOKEN_FILE_PY='
import os, stat, sys
action, out, force, euid = sys.argv[1], sys.argv[2], sys.argv[3] == "1", int(sys.argv[4])
parent, name = os.path.split(os.path.abspath(out))
parent = parent or "/"
if not name or name in (".", ".."):
    sys.exit(f"--out {out} names no file")
flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
dfd = os.open("/", flags)
walked = ""
for part in [c for c in parent.split("/") if c]:
    walked += "/" + part
    try:
        nfd = os.open(part, flags, dir_fd=dfd)
    except OSError as e:
        if os.path.islink(walked):
            sys.exit(f"--out path component {walked} is a symlink; give the real path")
        sys.exit(f"--out directory {walked}: {e.strerror}; create it first, owned by uid {euid}, mode 0700 or 0755")
    os.close(dfd)
    dfd = nfd
st = os.fstat(dfd)
mode = stat.S_IMODE(st.st_mode)
if st.st_uid != euid or mode & 0o022:
    sys.exit(f"--out directory {parent} is owned by uid {st.st_uid} with mode {mode:o}; the token goes only into a directory owned by uid {euid} that no group or other user can write")
try:
    lst = os.lstat(name, dir_fd=dfd)
except FileNotFoundError:
    lst = None
if lst is not None:
    if not force:
        sys.exit(f"{parent}/{name} already exists; choose another --out, or pass --force to replace it")
    if not stat.S_ISREG(lst.st_mode):
        sys.exit(f"{parent}/{name} is not a regular file (a symlink, FIFO, device or directory); --force replaces only a regular file")
if action == "check":
    sys.exit(0)
data = sys.stdin.buffer.read()
if not data:
    sys.exit("no token to write")
if lst is not None:
    os.unlink(name, dir_fd=dfd)
try:
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dfd)
except OSError as e:
    sys.exit(f"could not create {parent}/{name}: {e.strerror}")
try:
    os.fchmod(fd, 0o600)
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]
    os.fsync(fd)
    os.close(fd)
except OSError as e:
    os.close(fd)
    os.unlink(name, dir_fd=dfd)
    sys.exit(f"could not write {parent}/{name}: {e.strerror}; nothing was left behind")
'

# Creates one more user as the admin enrolled on this host, and writes their
# enrolment token to a 0600 file (ledger 1540).
#
# IDEMPOTENCY IS LOCAL, for $ADMIN_RECORD's reason: a duplicate username comes
# back as the gateway's opaque 503 (ADR-0927) and there is no lookup route. So
# the user id is recorded the moment create-user answers 200, tied to the
# installation, and create-user is sent at most once per user and installation.
#   record, token younger than 23h → nothing is sent; the steps are printed
#   record, no fresh token         → refused; nothing is sent
#   no record                      → create-user, record, issue-enrolment for
#                                    the user_id that create-user answered
#
# ITS ONLY AUTHORITY IS ROOT'S OWN ENROLLED CLIENT CREDENTIAL. The bootstrap
# token may create and enrol only the first admin (ADR-0655) and is never read
# here; no admin flag other than `is_admin: false` is ever sent, and
# set-user-admin is never called. The gateway and CA are the installation's own
# — the example's enrolment gateway and $CA_FILE — and a client config enrolled
# with any other gateway is refused.
add_user() {
  local out record uid recorded_uid recorded_id cfg gateway bearer work code user_id err
  # THE USERNAME IS ITS OWN RECORD KEY AND FILE NAME, so it is refused rather
  # than rewritten: a lossy mapping once gave `a+b` and `a_b` one record and one
  # token file.
  [[ "$ADD_USER_ID" =~ ^[A-Za-z0-9@][A-Za-z0-9._@-]*$ ]] ||
    die "--add-user takes a username of letters, digits and . _ @ - only, starting with a letter, a number or @"
  [[ ! "$ADD_USER_DISPLAY_NAME" =~ [[:cntrl:]] ]] || die "--display-name may not hold control characters or newlines"
  local py pending
  py="$(kind_up_python)" || die "--add-user needs /usr/bin/python3 (or python3 on root's PATH) to create the token file safely"
  pending="$USERS_DIR/$ADD_USER_ID.token.pending"
  out="${ADD_USER_OUT:-$(dirname "$ENROLMENT_FILE")/yadgar-enrolment-$ADD_USER_ID.token}"
  record="$USERS_DIR/$ADD_USER_ID.json"
  [[ -s "$CA_FILE" ]] || die "no edge CA at $CA_FILE; run kind-up.sh without --add-user first"
  err="$(mktemp "$STATE_DIR/tmp.XXXXXX")"
  client_config_file
  cfg="$("$py" -I -c "$READ_CLIENT_CONFIG_PY" "$CLIENT_CONFIG_FILE" "$EUID" 2>"$err")" ||
    die "$(printable <"$err"). --add-user acts only with the credential this host's root enrolled (kind-up.sh --with-client), owned by root and mode 0600"
  gateway="${cfg%%$'\n'*}"
  bearer="${cfg#*$'\n'}"
  cfg=""
  [[ "${gateway%/}" == "${GATEWAY_URL%/}" ]] ||
    die "$CLIENT_CONFIG_FILE is enrolled with ${gateway:-no gateway}, not $GATEWAY_URL"
  uid="$(install_uid)"
  [[ -n "$uid" ]] || die "Secret $ESTATE_NAMESPACE/admin-bootstrap-token has no uid; the estate has not minted it"

  if [[ -s "$record" ]]; then
    recorded_id="$(jq -r '.external_id // empty' "$record")"
    [[ "$recorded_id" == "$ADD_USER_ID" ]] ||
      die "$record records ${recorded_id:-no username}, not $ADD_USER_ID; refusing to act on another user's record"
    recorded_uid="$(jq -r '.install_uid // empty' "$record")"
    if [[ "$recorded_uid" != "$uid" ]]; then
      log "[add-user] $record belongs to another installation (${recorded_uid:-unrecorded}, this one is $uid)"
      set_aside "$record"
    fi
  fi
  # ALREADY ADDED BY THIS INSTALLATION: nothing is sent. The enrolment is only
  # ever issued to the user_id the same run's create-user answered, so a lost or
  # expired token is not re-issued from the record here — a re-issue to an
  # enrolled user resets their password, a step for an admin to take on purpose.
  if [[ -s "$record" ]]; then
    # A TOKEN AN EARLIER RUN COULD NOT WRITE comes first: whatever sits at $out
    # then is not it. Otherwise only a non-empty regular file is a fresh token.
    if [[ ! -s "$pending" && -f "$out" && ! -L "$out" && -s "$out" ]] &&
      [[ -n "$(find "$out" -mmin -"$ENROLMENT_MAX_AGE_MINUTES" 2>/dev/null)" ]]; then
      log "[add-user] $ADD_USER_ID already added ($(jq -r '.user_id' "$record")); $out holds an enrolment token younger than 23 hours"
      print_add_user_steps "$out"
      return
    fi
    if [[ -s "$pending" ]]; then
      die "$ADD_USER_ID was already added by this installation ($(jq -r '.user_id' "$record")), and an earlier run could not write $out: their enrolment token is in $pending (0600). Hand that file over (install -o <user> -m 0600 $pending ~<user>/yadgar-enrolment.token) and delete it once redeemed. Do not issue a new one: a new token for an existing user resets their password"
    fi
    die "$ADD_USER_ID was already added by this installation ($(jq -r '.user_id' "$record")), and $out is missing or older than 23 hours. --add-user sends create-user once and issues an enrolment only to the user that call created; a new token for an existing user resets their password, so issue it deliberately as an admin"
  fi
  # CHECKED BEFORE ANY REQUEST, so a refused output path never strands a user
  # whose only token had nowhere to go. The write repeats every check on its own
  # descriptor, so this is a courtesy, not the guard.
  "$py" -I -c "$CREATE_TOKEN_FILE_PY" check "$out" "$ADD_USER_FORCE" "$EUID" </dev/null 2>"$err" ||
    die "$(printable <"$err")"

  [[ "$bearer" =~ ^[A-Za-z0-9._~+/=-]+$ ]] || die "no usable credential in $CLIENT_CONFIG_FILE"
  install -d -m 0700 "$USERS_DIR"
  work="$(mktemp -d "$STATE_DIR/tmp.XXXXXX")"
  log "[add-user] creating $ADD_USER_ID (an ordinary user, never an admin)"
  # `jq --arg` builds the JSON: no input is ever interpolated into it.
  # `is_admin: false` is stated rather than left to the gateway's default.
  jq -n --arg e "$ADD_USER_ID" --arg d "${ADD_USER_DISPLAY_NAME:-$ADD_USER_ID}" \
    '{external_id: $e, display_name: $d, is_admin: false}' >"$work/body"
  code="$(user_admin_post create-user "$work/body" "$work/out" "$bearer")"
  [[ "$code" == 200 ]] || add_user_refused create-user "$code" "$work/out"
  # THE USER THIS CALL CREATED, and only that one, is enrolled below.
  user_id="$(jq -r '.user_id // empty' "$work/out")"
  [[ "$user_id" =~ ^yadgar:user:[0-9a-f-]+$ ]] || die "create-user answered 200 without a usable user_id"
  jq -n --arg e "$ADD_USER_ID" --arg u "$user_id" --arg i "$uid" \
    '{external_id: $e, user_id: $u, install_uid: $i}' >"$record.tmp"
  mv "$record.tmp" "$record"
  log "[add-user] created $ADD_USER_ID as $user_id"
  jq -n --arg u "$user_id" '{user_id: $u}' >"$work/body"
  code="$(user_admin_post issue-enrolment "$work/body" "$work/out" "$bearer")"
  bearer=""
  [[ "$code" == 200 ]] || add_user_refused issue-enrolment "$code" "$work/out"
  jq -r '.token // empty' "$work/out" >"$work/token"
  [[ -s "$work/token" ]] || die "issue-enrolment answered 200 with no token"
  # CREATE_TOKEN_FILE_PY: exclusive, no-follow, 0600, in a parent only this uid
  # can write. If that fails now, the user exists and this is their only token,
  # so it is kept in the root-only state directory rather than lost.
  if ! "$py" -I -c "$CREATE_TOKEN_FILE_PY" write "$out" "$ADD_USER_FORCE" "$EUID" <"$work/token" 2>"$err"; then
    # COPIED, VERIFIED, THEN RENAMED into the root-only users directory, and
    # only then may the EXIT trap delete the work directory. If even that
    # fails, the work directory is renamed out of the trap's tmp.* glob.
    if cp "$work/token" "$pending.tmp" && chmod 0600 "$pending.tmp" &&
      cmp -s "$work/token" "$pending.tmp" && mv -f "$pending.tmp" "$pending"; then
      die "$(printable <"$err"). $ADD_USER_ID was created ($user_id); their enrolment token is kept in $pending (0600) — hand that file over"
    fi
    local rescue
    rescue="$STATE_DIR/add-user-rescue-$ADD_USER_ID-$(date -u +%Y%m%dT%H%M%SZ)"
    mv "$work" "$rescue"
    die "$(printable <"$err"). $ADD_USER_ID was created ($user_id), and $pending could not be written either; their enrolment token is in $rescue/token (0600)"
  fi
  rm -rf "$work"
  log "[add-user] enrolment token for $ADD_USER_ID written to $out (0600, valid 24 hours)"
  print_add_user_steps "$out"
}

# ROOT'S ENVIRONMENT IS SCRUBBED FIRST IN main (ledger 1563). Only reads run
# before it: the top of this file (dirname, getent, cut and the numeric settings)
# changes nothing and calls no tool that acts on the host. Run as root, this
# script's pipx (the `pipx install --force` upgrade included), apt-get, kind and
# the container runtime would otherwise inherit whatever the caller exported —
# PIP_*, PIPX_*, PIPX_DEFAULT_PYTHON, APT_CONFIG, DOCKER_HOST, CONTAINER_HOST and
# the like, each of which redirects an install or a socket root trusts. `sudo -E`
# and any root login that keeps the caller's environment carry them in. So main
# re-executes this script under `env -i`, with only:
#   PATH   sudo's stock secure_path (Ubuntu's, with /snap/bin), never the caller's
#   HOME   root's, from the password database (pin_root_environment repeats it)
#   TERM, LANG   when set, for readable output
#   http_proxy, https_proxy, no_proxy, in both cases: TLS runs end to end and
#   every download is checked against tools.lock, so a proxy can delay a run
#   but not change what root installs
#   every setting documented at the top of this file, and the path overrides that
#   root ignores by name (so the notice on stderr still names them)
# YADGAR_ARCH, YADGAR_POLL_SECONDS and YADGAR_PROBE_ATTEMPTS are test knobs, not
# documented settings, and are dropped for root ON PURPOSE: YADGAR_ARCH would pick
# which binary root downloads and installs.
#
# THERE IS NO SENTINEL. A flag in the environment is something a `sudo -E` caller,
# or a `SETENV:` sudoers rule, can forge to skip the scrub, and ledger 1556 treats
# that caller as untrusted. The test is the state itself, root_environment_is_dirty:
# any exported name outside the allowlist, a PATH other than ROOT_SAFE_PATH, or a
# HOME other than root's. The second pass meets none of them, so it runs on, and a
# forged variable only makes the first pass re-execute.
# bash's $EUID decides, as for the fixed paths above. Not root: nothing changes,
# so the offline suite runs as before.
ROOT_SAFE_PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin"
ROOT_KEPT_VARS=(
  YADGAR_ADMIN_EXTERNAL_ID YADGAR_ADMIN_DISPLAY_NAME YADGAR_RUNTIME
  YADGAR_OPERATORS_TIMEOUT YADGAR_ESTATE_TIMEOUT YADGAR_CLIENT_CONFIG
  YADGAR_STATE_DIR YADGAR_BIN_DIR YADGAR_TOOLS_LOCK YADGAR_SYSCTL_FILE
  YADGAR_HOSTS_FILE YADGAR_CA_FILE YADGAR_ENROLMENT_FILE
  http_proxy https_proxy no_proxy HTTP_PROXY HTTPS_PROXY NO_PROXY
)

# Succeeds (0) when this process's environment is not the scrubbed one.
root_environment_is_dirty() {
  local name allowed=" PATH HOME TERM LANG PWD SHLVL OLDPWD _ ${ROOT_KEPT_VARS[*]} "
  [[ "${PATH:-}" == "$ROOT_SAFE_PATH" ]] || return 0
  [[ "${HOME:-}" == "$(root_home)" ]] || return 0
  while IFS= read -r name; do
    [[ "$allowed" == *" $name "* ]] || return 0
  done < <(compgen -e)
  return 1
}

reexec_with_clean_environment() {
  local script="$1" var env_bin=env
  shift
  local -a keep=("PATH=$ROOT_SAFE_PATH" "HOME=$(root_home)")
  [[ -x /usr/bin/env ]] && env_bin=/usr/bin/env
  for var in TERM LANG "${ROOT_KEPT_VARS[@]}"; do
    if [[ -v $var ]]; then keep+=("$var=${!var}"); fi
  done
  exec "$env_bin" -i "${keep[@]}" "$BASH" "$script" "$@"
}

# ─── main ────────────────────────────────────────────────────────────────────

usage() {
  sed -n '2,/^$/{s/^# \{0,1\}//;p}' "${BASH_SOURCE[0]}"
}

main() {
  if ((EUID == 0)) && root_environment_is_dirty; then
    reexec_with_clean_environment "$SCRIPT_DIR/${BASH_SOURCE[0]##*/}" "$@"
  fi
  local args=("$@") display_set=0 out_set=0
  while (($#)); do
    case "$1" in
      --with-client) WITH_CLIENT=1 ;;
      --add-user | --display-name | --out)
        if (($# < 2)) || [[ "$2" == --* ]]; then
          printf '%s needs a value\n' "$1" >&2
          return 2
        fi
        case "$1" in
          --add-user) ADD_USER=1 ADD_USER_ID="$2" ;;
          --display-name) display_set=1 ADD_USER_DISPLAY_NAME="$2" ;;
          --out) out_set=1 ADD_USER_OUT="$2" ;;
        esac
        shift
        ;;
      --force) out_set=1 ADD_USER_FORCE=1 ;;
      -h | --help)
        usage
        return 0
        ;;
      *)
        printf 'unknown argument: %s\n' "$1" >&2
        return 2
        ;;
    esac
    shift
  done
  if ((!ADD_USER && (display_set || out_set))); then
    printf -- '--display-name, --out and --force belong to --add-user\n' >&2
    return 2
  fi
  if ((ADD_USER && WITH_CLIENT)); then
    printf -- '--add-user runs on an installed host, on its own; run --with-client first\n' >&2
    return 2
  fi
  require_root "${args[@]}"
  pin_root_environment
  ensure_state_dir
  trap 'rm -rf "$STATE_DIR"/tmp.*' EXIT
  load_examples
  if ((ADD_USER)); then
    log "kind-up --add-user: edge $GATEWAY_URL, log $LOG_FILE"
    add_user
    return
  fi
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
