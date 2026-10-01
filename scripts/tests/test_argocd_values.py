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


if __name__ == "__main__":
    # Prints the CRD override for crd_health_cases.lua, or with the argument
    # `mariadb` the MariaDB override for mariadb_health_cases.lua; see the module
    # docstring.
    sys.stdout.write(
        _override(MARIADB_KEY if sys.argv[1:] == ["mariadb"] else KEY)
    )
