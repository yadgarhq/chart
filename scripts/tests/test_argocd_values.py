"""`bootstrap/argocd-values.yaml` carries a CRD health check for Argo CD (ledger 1197).

THE DEFECT, measured on a fresh kind cluster on 2026-10-01: the `operators`
Application failed its first two attempts with ~40 tasks
`(Synced,Failed,CRD is not established)`, and every one of them was a CRD
(gateway.networking.k8s.io, cert-manager.io, keda.sh, k8s.mariadb.com, ...).
Its third attempt succeeded.

THE FIRST CAUSE is Argo CD v3.1.8's built-in health script for
`CustomResourceDefinition`. The apiextensions naming controller writes a new CRD's
status as `NamesAccepted=True` with `Established=False, reason=Installing`, and the
establishing controller flips `Established` to `True` afterwards. The v3.1.8 script
returns `Degraded` for any state without `Established=True`, so the transient
`Installing` state reads as `Degraded`. In a multi-step sync, gitops-engine marks a
running task whose live object is `Degraded` as `Failed`, and the operation fails.
Upstream fixed this state in argoproj/argo-cd#26126 (commit 4535a1fde7b9), which
first ships in v3.5.0: `Installing` reads as `Progressing`. Chart v0.3.14 carried
that upstream script verbatim.

THE SECOND CAUSE, measured on v0.3.14: the retries stayed at 2, and the failures
fell from 40 to 10. All 10 were the `gateway.networking.k8s.io` CRDs. They carry
the `api-approved.kubernetes.io` annotation, so the API server first writes only
`KubernetesAPIApprovalPolicyConformant`, and writes `NamesAccepted` and
`Established` about 2 s later. In that state `conditions` is not empty but holds no
`Established` entry. The upstream script reads it as `Degraded`, "CRD is not
established". Upstream master (v3.5.3) has the same gap; argoproj/argo-cd#26346 is
open.

THE FIX keeps Argo CD at v3.1.8 and overrides the one script through `argocd-cm`.
Argo reads a `resource.customizations.health.<group>_<kind>` key before its
built-in scripts (`util/lua/lua.go` `GetHealthScript`, v3.1.8). The override is
upstream's script plus three inserted hunks (`DIVERGENCE` below): when no
`Established` condition exists yet, it returns `Progressing`, "CRD is being
installed". Two digests hold it. One pins the whole script. The other removes the
hunks and must give upstream's bytes, so an edit outside the hunks is a red test.

BEHAVIOUR is checked by `crd_health_cases.lua` in Lua 5.1, the dialect of
gopher-lua. CI has no Lua runtime, so it runs locally only:

    python3 scripts/tests/test_argocd_values.py > /tmp/crd-health.lua
    nix shell nixpkgs#lua5_1 -c lua scripts/tests/crd_health_cases.lua /tmp/crd-health.lua

THE MariaDB OVERRIDE (ledger 1205) follows the same shape. mariadb-operator
26.6.0 creates its `<name>-mariadb-sys-global-priv` Grant and reads it back from a
lagging informer cache, so one reconcile can write `Ready=False, reason=Failed`
with a Grant NotFound message. v3.1.8's built-in MariaDB script reads every
`reason=Failed` as Degraded, which fails the running sync. The override is
upstream's script plus one hunk (`MARIADB_DIVERGENCE`): exactly that message, for
the MariaDB's own Grant, reads as Progressing. `mariadb_health_cases.lua` checks
the behaviour, locally only:

    python3 scripts/tests/test_argocd_values.py mariadb > /tmp/mariadb-health.lua
    nix shell nixpkgs#lua5_1 -c lua scripts/tests/mariadb_health_cases.lua /tmp/mariadb-health.lua

Run: python3 -m pytest scripts/tests/test_argocd_values.py -q
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
VALUES = REPO / "bootstrap" / "argocd-values.yaml"

KEY = "resource.customizations.health.apiextensions.k8s.io_CustomResourceDefinition"

# sha256 of `resource_customizations/apiextensions.k8s.io/CustomResourceDefinition/health.lua`
# at argoproj/argo-cd 4535a1fde7b9fae3d08f231dc955972fcd3b0027 (#26126). The same
# bytes ship in v3.5.0 through v3.5.3 and are on master on 2026-10-01. The upstream
# file has no trailing newline; a YAML `|` block adds one, so the comparison strips
# it.
UPSTREAM_SHA256 = "7dee7c737028e9d267977ac3734f7d564ad10dfade0ceb816ac257dc6502a6e8"

# The ONLY lines this override adds to upstream's script. Each must occur exactly
# once. With them removed, the script must hash to UPSTREAM_SHA256.
DIVERGENCE = (
    "-- NOT UPSTREAM (yadgarhq/chart, ledger 1197; argoproj/argo-cd#26346): a CRD\n"
    "-- whose conditions hold no Established entry yet reads Progressing, not\n"
    "-- Degraded. gateway-api CRDs get KubernetesAPIApprovalPolicyConformant first.\n"
    "local hasEstablishedCondition = false\n",
    "        hasEstablishedCondition = true\n",
    "    if not hasEstablishedCondition then\n"
    '        hs.status = "Progressing"\n'
    '        hs.message = "CRD is being installed"\n'
    "        return hs\n"
    "    end\n",
)

# sha256 of the override itself (trailing newline stripped). Moves with any edit,
# inside or outside DIVERGENCE.
OVERRIDE_SHA256 = "8068309e805a854cff23a2ea6dbde011b3d257ff33430fe46ee6c9d5423d7adf"


MARIADB_KEY = "resource.customizations.health.k8s.mariadb.com_MariaDB"

# sha256 of `resource_customizations/k8s.mariadb.com/MariaDB/health.lua` at
# argoproj/argo-cd v3.1.8 (becb020064fe9be5381bf6e5818ff8587ca8f377), trailing
# newline stripped. The raw file's own sha256 is 0840fdce034dc6f6d6a48b597fe4fa36
# 88ede1e59ca48ec4f5cf66f6d36b47bd. The file has not changed since 440fbac12b74
# (#17995, 2024-05-08); master holds the same bytes on 2026-10-01.
MARIADB_UPSTREAM_SHA256 = "de3a0bcfeb4d5e91308af0b29e1a18e3fe9282fe1d8612fa28379f08690b20c5"

# The ONLY lines the MariaDB override adds to upstream's script. Each must occur
# exactly once. With them removed, the script must hash to MARIADB_UPSTREAM_SHA256.
MARIADB_DIVERGENCE = (
    "                -- NOT UPSTREAM (yadgarhq/chart, ledger 1205): mariadb-operator 26.6.0\n"
    "                -- reads the mariadb.sys Grant it has just created from a lagging cache.\n"
    "                -- That one NotFound, for this MariaDB's own Grant, reads Progressing.\n"
    '                if condition.type == "Ready" and obj.metadata ~= nil and obj.metadata.name ~= nil\n'
    "                    and condition.message ==\n"
    "                    'Error reconciling SQL: error getting mariadb.sys Grant: Grant.k8s.mariadb.com \"'\n"
    "                    .. obj.metadata.name .. '-mariadb-sys-global-priv\" not found' then\n"
    '                    health_status.status = "Progressing"\n'
    "                    return health_status\n"
    "                end\n",
)

# sha256 of the MariaDB override itself (trailing newline stripped).
MARIADB_OVERRIDE_SHA256 = "bfb8b75f83de320c71f42f36b78dbcef318e4662d78c536f7d13239d79643d3c"


def _override(key: str = KEY) -> str:
    values = yaml.safe_load(VALUES.read_text())
    cm = values.get("configs", {}).get("cm", {})
    assert key in cm, f"argocd-values.yaml configs.cm has no {key!r}"
    script = cm[key]
    assert isinstance(script, str), f"{key} must be a Lua string, got {type(script)}"
    return script


def _sha256(script: str) -> str:
    return hashlib.sha256(script.rstrip("\n").encode()).hexdigest()


def test_the_crd_health_override_is_pinned() -> None:
    assert _sha256(_override()) == OVERRIDE_SHA256, (
        "the CRD health override changed; update OVERRIDE_SHA256 only after the "
        "Lua cases in crd_health_cases.lua pass"
    )


def test_the_override_is_upstream_plus_only_the_documented_hunks() -> None:
    script = _override()
    for hunk in DIVERGENCE:
        assert script.count(hunk) == 1, f"divergence hunk not found once:\n{hunk}"
        script = script.replace(hunk, "", 1)
    assert _sha256(script) == UPSTREAM_SHA256, (
        "with the documented hunks removed, the override is not argo-cd "
        "4535a1fde7b9's health.lua"
    )


def test_installing_reads_as_progressing_not_degraded() -> None:
    # The digests above already pin this. This states WHY in a failure message a
    # reader can act on, without decoding a hash.
    script = _override()
    assert 'condition.reason == "Installing"' in script
    branch = script.split('condition.reason == "Installing"', 1)[1].split("end", 1)[0]
    assert 'hs.status = "Progressing"' in branch


def test_no_established_condition_reads_as_progressing_not_degraded() -> None:
    script = _override()
    # The flag is set for EVERY Established condition, before its status is read.
    # Set only on True, every Established=False would read as Progressing.
    established = script.split('if condition.type == "Established" then\n', 1)[1]
    assert established.startswith("        hasEstablishedCondition = true\n")
    # After the loop, the missing-condition branch comes BEFORE the Degraded one.
    tail = script.split("if not isEstablished then\n", 1)[1]
    branch = tail.split("if not hasEstablishedCondition then\n", 1)[1].split("end", 1)[0]
    assert 'hs.status = "Progressing"' in branch
    assert tail.index("if not hasEstablishedCondition then") < tail.index(
        'hs.status = "Degraded"'
    )


def test_the_mariadb_health_override_is_pinned() -> None:
    assert _sha256(_override(MARIADB_KEY)) == MARIADB_OVERRIDE_SHA256, (
        "the MariaDB health override changed; update MARIADB_OVERRIDE_SHA256 only "
        "after the Lua cases in mariadb_health_cases.lua pass"
    )


def test_the_mariadb_override_is_upstream_plus_only_the_documented_hunk() -> None:
    script = _override(MARIADB_KEY)
    for hunk in MARIADB_DIVERGENCE:
        assert script.count(hunk) == 1, f"divergence hunk not found once:\n{hunk}"
        script = script.replace(hunk, "", 1)
    assert _sha256(script) == MARIADB_UPSTREAM_SHA256, (
        "with the documented hunk removed, the MariaDB override is not argo-cd "
        "v3.1.8's health.lua"
    )


def test_only_the_own_grant_not_found_message_reads_as_progressing() -> None:
    # The digests above pin this. This states WHY in a failure message.
    script = _override(MARIADB_KEY)
    failed = script.split('if condition.reason == "Failed" then\n', 1)[1]
    # The exception comes first inside the Failed branch, and Degraded follows it.
    assert failed.lstrip().startswith("-- NOT UPSTREAM")
    exception = failed.split("then\n", 1)[0]
    # An exact comparison on the Ready condition, built from this object's name:
    # no Lua pattern, no substring match, no other condition type.
    assert 'condition.type == "Ready"' in exception
    assert "condition.message ==" in exception
    assert "obj.metadata.name .. '-mariadb-sys-global-priv\" not found'" in exception
    assert "string.find" not in script and "string.match" not in script
    assert failed.index('health_status.status = "Progressing"') < failed.index(
        'health_status.status = "Degraded"'
    )


# ─── the sync timeout (ledger 1208) ───────────────────────────────────────────
#
# THE DEFECT: v3.1.8 ships `controller.sync.timeout.seconds: "0"`, which means no
# timeout, so a sync operation that never ends is never ended. A PreSync hook Job
# with no `activeDeadlineSeconds` whose image cannot be pulled holds the operation
# Running for ever, and `retry` never fires, because retry runs only after an
# attempt FAILS.
#
# WHAT THE TIMEOUT DOES, read in argo-cd v3.1.8 (becb020)
# `controller/appcontroller.go`:
# - `:1397`: `terminating` is read from the stored phase, before anything below.
# - `:1420-1424`: an operation still in progress `syncTimeout` after its
#   `StartedAt` is set to Terminating, "operation is terminating due to timeout".
# - `controller/sync.go:412-413` then calls gitops-engine's `Terminate()`
#   (`pkg/sync/sync_context.go:1278-1313` at e48120133eec), in the same call. It
#   deletes every RUNNING hook and sets the phase Failed, "Operation terminated".
# - `:1476-1490`: `terminating` is still false, so a Failed phase with retries
#   left is retried after the usual backoff (`RetryCount++` at `:1485`).
# - `StartedAt` is set only when an operation starts (`:1429`); the retry path
#   (`:1400-1419`) keeps it. So the clock covers the WHOLE operation, every
#   attempt and every backoff wait, and once it has run out each retry gets one
#   pass and is terminated on the next one. The real effect is "the hung hook is
#   deleted and the Application reads Failed after the timeout plus the remaining
#   backoff", not "a retry recovers it".
# - `:1486` appends "due to application controller sync timeout" to EVERY retry's
#   message, whatever failed. That text is not evidence this timeout fired.
#
# SO THE VALUE MUST OUTLAST THE LONGEST LEGITIMATE OPERATION, retries included,
# or it cuts off a chain the retry gate allows. The gate allows up to
# RETRY_WINDOW_SECONDS[1] of backoff, and every attempt may run the estate's
# hook Jobs to the ceilings `platform` documents and wait for Sync-phase health
# (ATTEMPT_ALLOWANCE_SECONDS below). With `limit: 6`: 1200 + 7 x 3225 = 23775 s.
# 24000 s (6.7 h) clears that. Max
# ruled 2026-10-01: keep the documented margins now, tighten through per-hook
# deadlines later (ledger 1224). The longest operation measured on the v0.3.15
# VM run took 4m12s with 2 retries, so the floor is a sum of ceilings, not a
# measurement.
#
# THE RETRY WAITS that RETRY_WINDOW_SECONDS bounds are k = 1..limit, not
# k = 0..limit-1: `:1485` increments `RetryCount` before the wait that gates the
# retry is computed at `:1401`. Measured on the v0.3.15 VM run (15s x2): 30 s
# before retry 1, 60 s before retry 2. `retry_window` in `test_parent_chart.py`
# computes the same.
#
# AND IT MUST FIT A GO INT32. The controller reads the env var with
# `env.ParseNumFromEnv(..., 0, 0, math.MaxInt32)`
# (`cmd/argocd-application-controller/commands/argocd_application_controller.go:278`),
# and a value above the maximum logs a warning and falls back to the default, 0
# (`util/env/env.go:36-39`): no timeout at all, which is ledger 1208 again.

SYNC_TIMEOUT_KEY = "controller.sync.timeout.seconds"
MAX_INT32 = 2_147_483_647

# THE TIME ONE ATTEMPT MAY LEGITIMATELY SPEND. The kind example installs
# `yadgar`, which embeds `platform` 0.1.21 (`chart/Chart.yaml`). Rendered with
# the example's `valuesObject`, every attempt runs four hook Jobs from that
# subchart, none with `activeDeadlineSeconds`. The preflight and the probe carry
# the ceilings `yadgarhq/platform@v0.1.21 chart/values.yaml` documents. They are
# DOCUMENTED CEILINGS, NOT BOUNDS: each loop is bounded, but every `request()`
# in both scripts is a curl with no `--max-time`, so request time is unbounded.
#   `preflight` (PreSync, hook-weight -7): `timeoutSeconds: 120` (L857), and "worst
#     case with every probe on is eight 120s loops plus the same 300s margin"
#     (L1035-1036).
PREFLIGHT_SECONDS = 8 * 120 + 300
#   `envoy-gateway-probe` (PostSync, hook-weight -7): `timeoutSeconds: 300`
#     (L1043). The values say three loops (L1026-1030) and "the composed bound
#     is 900s, and the documented `--timeout 25m` leaves 600s over it for
#     scheduling, image pull and request time" (L1033-1035). The script
#     (`chart/templates/envoy-gateway-probe.yaml`) runs FOUR: `remove` of the
#     Gateway, `create` of the EnvoyProxy (which calls `remove` first), `create`
#     of the Gateway (which calls `remove` of the Gateway again), and `await`.
#     The fourth is the second `remove` of a Gateway the first one already
#     deleted, so on the legitimate path it returns at once (~0 s). The values'
#     900 + 600 is kept.
PROBE_SECONDS = 3 * 300 + 600
#   `bootstrap-secrets` and `admin-bootstrap-token` (PreSync, both hook-weight
#     -5) run IN PARALLEL. bootstrap-secrets makes three requests
#     (valkey-password, nats-auth, nats-auth-gateway), admin-bootstrap-token its
#     own; no curl has a timeout, each Job has `backoffLimit: 4` and no deadline.
#     MEASURED, NOT BOUNDED: 3 s each, all requests included, on kind-yadgar
#     (2026-10-01, both 08:09:39 -> 08:09:42, the same platform 0.1.21
#     templates). The allowance is the Job's pod backoff (10 + 20 + 40 + 80 s)
#     plus 5 attempts of 3x the measured 3 s. The two Jobs share it.
BOOTSTRAP_JOB_SECONDS = (10 + 20 + 40 + 80) + 5 * 3 * 3
#   SYNC-PHASE HEALTH. The sync is multi-step (it has Pre- and PostSync hooks;
#     gitops-engine `pkg/sync/sync_tasks.go:274` at e48120133eec), so each
#     attempt also waits for its Sync-phase resources to be Healthy before
#     PostSync runs (`pkg/sync/sync_context.go:494-501`). Nothing bounds that
#     wait: no Deployment sets `progressDeadlineSeconds` (Kubernetes' default is
#     600 s), and the nats StatefulSet and the MariaDBs have no deadline.
#     MEASURED, NOT BOUNDED: the v0.3.15 VM run's attempt 0 finished its
#     preflight at 09:53:55 and failed at 09:55:31 still "waiting for healthy
#     state of apps/Deployment/iam-db", so at least 90 s; 3x that.
SYNC_HEALTH_SECONDS = 90 * 3
# A pod that never starts (the 1208 ImagePullBackOff) is bounded only by the
# sync timeout this file sets. A KNOWN LIMITATION: these numbers are copied from
# the lines cited, and nothing here re-reads them. Update them when the platform
# pin or a hook bound changes.
ATTEMPT_ALLOWANCE_SECONDS = PREFLIGHT_SECONDS + PROBE_SECONDS + BOOTSTRAP_JOB_SECONDS + SYNC_HEALTH_SECONDS


def _values() -> dict:
    return yaml.safe_load(VALUES.read_text())


def sync_timeout_floor(documents: list[dict] | None = None) -> int:
    """The shortest timeout that cuts off no chain the retry gate allows. PURE-ish.

    Read from the gate itself, so widening the window or raising a `limit`
    raises this floor and reddens a value that no longer clears it.
    """
    import test_parent_chart as parent

    if documents is None:
        documents = [parent.application(path) for path in parent.EXAMPLE_APPLICATIONS]
    attempts = 1 + max(int(d["spec"]["syncPolicy"]["retry"]["limit"]) for d in documents)
    return parent.RETRY_WINDOW_SECONDS[1] + attempts * ATTEMPT_ALLOWANCE_SECONDS


def sync_timeout_failures(values: dict) -> list[str]:
    """What is wrong with the sync timeout in one argocd-values document. PURE."""
    params = (values.get("configs") or {}).get("params") or {}
    if SYNC_TIMEOUT_KEY not in params:
        return [f"configs.params has no {SYNC_TIMEOUT_KEY!r}: v3.1.8 defaults to 0, no timeout"]
    raw = params[SYNC_TIMEOUT_KEY]
    # Argo reads it as an integer env var; a YAML string keeps it one in the
    # rendered ConfigMap.
    if not isinstance(raw, str) or not raw.isdigit():
        return [f"{SYNC_TIMEOUT_KEY} is {raw!r}, not a quoted whole number of seconds"]
    seconds = int(raw)
    if seconds == 0:
        return [f"{SYNC_TIMEOUT_KEY} is 0, which disables the timeout"]
    if seconds > MAX_INT32:
        return [f"{SYNC_TIMEOUT_KEY} is {seconds}, above MaxInt32: Argo falls back to 0, no timeout"]
    floor = sync_timeout_floor()
    if seconds < floor:
        return [f"{SYNC_TIMEOUT_KEY} is {seconds} s, below the {floor} s a retried sync may legitimately take"]
    return []


def test_the_sync_timeout_outlasts_every_retry_chain_the_gate_allows() -> None:
    assert sync_timeout_failures(_values()) == []


def test_the_per_attempt_allowance_is_the_documented_bounds() -> None:
    assert (PREFLIGHT_SECONDS, PROBE_SECONDS, BOOTSTRAP_JOB_SECONDS, SYNC_HEALTH_SECONDS) == (1260, 1500, 195, 270)
    assert ATTEMPT_ALLOWANCE_SECONDS == 3225


def test_the_floor_is_the_gate_ceiling_plus_the_allowance_per_attempt() -> None:
    # Hand-computed: a 1200 s window ceiling, limit 6, so 7 attempts of 3225 s.
    assert sync_timeout_floor() == 1200 + 7 * 3225 == 23775


def test_a_higher_example_limit_raises_the_floor() -> None:
    # Mutation: one more retry in any example is one more attempt in the floor.
    import test_parent_chart as parent

    documents = [parent.application(path) for path in parent.EXAMPLE_APPLICATIONS]
    documents[0]["spec"]["syncPolicy"]["retry"]["limit"] = 7
    assert sync_timeout_floor(documents) == 1200 + 8 * 3225


def test_the_retry_waits_are_the_measured_sequence() -> None:
    # An independent table: the v0.3.15 VM run measured 30 s and 60 s before
    # retries 1 and 2 (15s x2); the rest follow and cap at 5m.
    import test_parent_chart as parent

    retry = {"limit": 6, "backoff": {"duration": "15s", "factor": 2, "maxDuration": "5m"}}
    assert parent.retry_window(retry) == 30 + 60 + 120 + 240 + 300 + 300


@pytest.mark.parametrize(
    ("value", "named"),
    [
        (None, "has no"),
        ("0", "disables"),
        ("900", "below"),
        ("4200", "below"),
        ("22200", "below"),
        ("23774", "below"),
        ("2147483648", "MaxInt32"),
        ("3000000000", "MaxInt32"),
        (24000, "not a quoted"),
        ("1h", "not a quoted"),
    ],
    ids=["missing", "zero", "900", "old-4200", "old-22200", "one-under-floor", "maxint32-plus-1", "3e9", "unquoted", "go-duration"],
)
def test_a_bad_sync_timeout_reddens(value, named: str) -> None:
    values = yaml.safe_load(yaml.safe_dump(_values()))
    params = values["configs"]["params"]
    params.pop(SYNC_TIMEOUT_KEY, None)
    if value is not None:
        params[SYNC_TIMEOUT_KEY] = value
    failures = sync_timeout_failures(values)
    assert len(failures) == 1 and named in failures[0], failures


def test_maxint32_itself_is_accepted() -> None:
    # The boundary: `ParseNumFromEnv` rejects only a value ABOVE the maximum.
    values = yaml.safe_load(yaml.safe_dump(_values()))
    values["configs"]["params"][SYNC_TIMEOUT_KEY] = str(MAX_INT32)
    assert sync_timeout_failures(values) == []

if __name__ == "__main__":
    # Prints the CRD override for crd_health_cases.lua, or with the argument
    # `mariadb` the MariaDB override for mariadb_health_cases.lua; see the module
    # docstring.
    sys.stdout.write(
        _override(MARIADB_KEY if sys.argv[1:] == ["mariadb"] else KEY)
    )
