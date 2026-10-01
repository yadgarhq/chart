"""`bootstrap/argocd-values.yaml` carries Argo CD's FIXED CRD health check (ledger 1197).

THE DEFECT, measured on a fresh kind cluster on 2026-10-01: the `operators`
Application failed its first two attempts with ~40 tasks
`(Synced,Failed,CRD is not established)`, and every one of them was a CRD
(gateway.networking.k8s.io, cert-manager.io, keda.sh, k8s.mariadb.com, ...).
Its third attempt succeeded.

THE CAUSE is Argo CD v3.1.8's built-in health script for `CustomResourceDefinition`.
The apiextensions naming controller writes a new CRD's status as
`NamesAccepted=True` with `Established=False, reason=Installing`, and the
establishing controller flips `Established` to `True` afterwards. The v3.1.8 script
returns `Degraded` for any state without `Established=True`, so the transient
`Installing` state reads as `Degraded`. In a multi-step sync, gitops-engine marks a
running task whose live object is `Degraded` as `Failed`, and the operation fails.
Upstream fixed the script in argoproj/argo-cd#26126 (commit 4535a1fde7b9), which
first ships in v3.5.0: `Installing` reads as `Progressing`.

THE FIX keeps Argo CD at v3.1.8 and overrides the one script through `argocd-cm`.
Argo reads a `resource.customizations.health.<group>_<kind>` key before its
built-in scripts (`util/lua/lua.go` `GetHealthScript`, v3.1.8). The override is
upstream's fixed file VERBATIM, so it is asserted by digest: an edit to the
script, or a stale copy, is a red test rather than a silent divergence.

Run: python3 -m pytest scripts/tests/test_argocd_values.py -q
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
VALUES = REPO / "bootstrap" / "argocd-values.yaml"

KEY = "resource.customizations.health.apiextensions.k8s.io_CustomResourceDefinition"

# sha256 of `resource_customizations/apiextensions.k8s.io/CustomResourceDefinition/health.lua`
# at argoproj/argo-cd 4535a1fde7b9fae3d08f231dc955972fcd3b0027 (#26126). The same
# bytes ship in v3.5.0 through v3.5.3. The upstream file has no trailing newline;
# a YAML `|` block adds one, so the comparison strips it.
UPSTREAM_SHA256 = "7dee7c737028e9d267977ac3734f7d564ad10dfade0ceb816ac257dc6502a6e8"


def _override() -> str:
    values = yaml.safe_load(VALUES.read_text())
    cm = values.get("configs", {}).get("cm", {})
    assert KEY in cm, f"argocd-values.yaml configs.cm has no {KEY!r}"
    script = cm[KEY]
    assert isinstance(script, str), f"{KEY} must be a Lua string, got {type(script)}"
    return script


def test_the_crd_health_override_is_upstreams_fixed_script() -> None:
    digest = hashlib.sha256(_override().rstrip("\n").encode()).hexdigest()
    assert digest == UPSTREAM_SHA256, (
        "the CRD health override is not argo-cd 4535a1fde7b9's health.lua verbatim"
    )


def test_installing_reads_as_progressing_not_degraded() -> None:
    # The digest above already pins this. This states WHY in a failure message a
    # reader can act on, without decoding a hash.
    script = _override()
    assert 'condition.reason == "Installing"' in script
    branch = script.split('condition.reason == "Installing"', 1)[1].split("end", 1)[0]
    assert 'hs.status = "Progressing"' in branch
