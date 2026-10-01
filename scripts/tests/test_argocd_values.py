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


def _override() -> str:
    values = yaml.safe_load(VALUES.read_text())
    cm = values.get("configs", {}).get("cm", {})
    assert KEY in cm, f"argocd-values.yaml configs.cm has no {KEY!r}"
    script = cm[KEY]
    assert isinstance(script, str), f"{KEY} must be a Lua string, got {type(script)}"
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


if __name__ == "__main__":
    # Prints the override for crd_health_cases.lua; see the module docstring.
    sys.stdout.write(_override())
