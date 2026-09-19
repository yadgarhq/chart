"""What an adopter actually receives, asserted on the render rather than on an exit code.

FOUR PROPERTIES, each one a thing that has already failed in this estate in some
form:

1. THE PARENT RENDERS NOTHING OF ITS OWN. ADR-0723's `revisit_trigger` names a
   parent growing templates as the thing that would change what was authorised —
   it would be a ninth module nobody declared. Asserted by rendering the parent
   with its subcharts removed and demanding an empty render, which is the only
   phrasing that cannot be satisfied by a template whose guard happens to be off.

2. THE PACKAGED `.tgz` RENDERS, AND RENDERS THE SAME AS THE DIRECTORY. A release
   publishes a package, not a working tree, and phase 0 of this goal found that
   what ships inside a package is not the same set of files as what sits beside
   the chart. An adopter installs the package.

3. AN ADOPTER'S OWN VALUE REACHES A CHILD'S RENDERED OBJECT — goal item 6, and
   the reason it is asserted on the VALUE rather than on exit 0 is that the
   earlier `.Files.Get` mechanism in `yadgarhq/config` exited 0 while ignoring
   every value an adopter passed. `helm template -f nonsense.yaml` also exits 0
   on a chart that reads nothing. Exit 0 proves nothing here.

4. THE ALL-OFF RENDER CARRIES NO CRD-BEARING RESOURCE. `ci-pr.yaml`'s
   `portability` job asserts this from `yadgarhq/actions`, and it reads the
   `enabled` keys out of `chart/values.yaml` of the chart under review. This
   repository's `chart/values.yaml` therefore has to state
   `gateway.gateway.enabled`, and a local copy of the property is what tells a
   contributor WHY before CI does.

NO SKIPS (ADR-0650). `helm` absent is a failure, not a skip: this suite and the
shared `helm lint and render` hook both need it, and a suite that skips when its
subject is absent reports a pass nobody earned.

THE PACKAGED-CHART RENDERS ARE NOT OFFLINE. Per ADR-0725 nothing under
`chart/charts/` is committed, so the `packaged` fixture below resolves this
chart's eight dependencies from `oci://ghcr.io/yadgarhq/charts` with
`helm package chart -u` — the same command `ci-release.yaml` runs — and needs
the registry reachable. The directory-only renders (test 1) need no registry.

Run: python3 -m pytest scripts/tests/ -q
"""

from __future__ import annotations

import collections
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
CHART = REPO / "chart"

# WHAT A DEFAULT INSTALL OF THE WHOLE ESTATE IS, measured 2026-09-19 on helm
# 3.20.2 and 4.2.3 against config 0.1.5, gateway 0.9.48, iam 0.8.39, iam-db
# 0.7.40, project 0.1.17, project-db 0.3.5, task 0.5.28 and task-db 0.6.29.
#
# THIS NUMBER MOVES WHEN A PIN MOVES, and that is the point rather than a
# maintenance cost. A module release that adds or drops an object changes what an
# adopter of the parent receives, and a bump whose effect on the rendered set
# nobody looked at is exactly what ADR-0722 removed the compatibility gate in
# front of. Update it in the same commit as the pin, and say in the pull request
# which module changed it.
EXPECTED = {
    "ConfigMap": 9,
    "Deployment": 7,
    "Service": 7,
    "ServiceAccount": 7,
    "PodDisruptionBudget": 7,
    "HTTPRoute": 1,
}

# The built-in Kubernetes API groups, copied from `scripts/d80_portability.py` in
# `yadgarhq/actions` — an ALLOWLIST, never a denylist of CRD groups, so an
# unknown group is treated as CRD-bearing and the unknown case fails safe.
BUILTIN_GROUPS = {
    "",
    "apps",
    "batch",
    "autoscaling",
    "policy",
    "networking.k8s.io",
    "rbac.authorization.k8s.io",
    "storage.k8s.io",
    "apiextensions.k8s.io",
    "admissionregistration.k8s.io",
    "apiregistration.k8s.io",
    "authentication.k8s.io",
    "authorization.k8s.io",
    "certificates.k8s.io",
    "coordination.k8s.io",
    "discovery.k8s.io",
    "events.k8s.io",
    "flowcontrol.apiserver.k8s.io",
    "node.k8s.io",
    "scheduling.k8s.io",
    "resource.k8s.io",
    "internal.apiserver.k8s.io",
}


def helm(*arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    binary = shutil.which("helm")
    # NOT A SKIP, and ADR-0650 is why. Same wording as `yadgarhq/config`'s suite,
    # which made the same decision for the same reason.
    assert binary, (
        "helm is not on PATH. This suite renders the chart, and so does the "
        "`helm lint and render` pre-commit hook — install helm rather than "
        "letting either report a pass it did not earn."
    )
    return subprocess.run([binary, *arguments], capture_output=True, text=True, cwd=cwd)


def render(target: str, *arguments: str, cwd: Path | None = None) -> list[dict]:
    result = helm("template", "yadgar", target, *arguments, cwd=cwd)
    assert result.returncode == 0, result.stderr
    return [
        document
        for document in yaml.safe_load_all(result.stdout)
        if isinstance(document, dict) and document.get("apiVersion")
    ]


def kinds(documents: list[dict]) -> collections.Counter:
    return collections.Counter(str(document.get("kind")) for document in documents)


def crd_bearing(documents: list[dict]) -> list[tuple[str, str, str]]:
    found = []
    for document in documents:
        api_version = str(document.get("apiVersion", ""))
        group = api_version.split("/")[0] if "/" in api_version else ""
        if group not in BUILTIN_GROUPS:
            found.append(
                (api_version, str(document.get("kind")), str((document.get("metadata") or {}).get("name")))
            )
    return found


@pytest.fixture(scope="module")
def packaged(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The chart as `helm package` leaves it — the artifact an adopter downloads.

    PACKAGED THE WAY `ci-release.yaml` DOES IT PER ADR-0725: `helm package chart -u`,
    with `-u` resolving this chart's eight dependencies from
    `oci://ghcr.io/yadgarhq/charts` before packaging. Nothing under `chart/charts/`
    is committed, so this fixture is also the assertion that resolving at package
    time is what makes a release possible at all.
    """
    workspace = tmp_path_factory.mktemp("package")
    shutil.copytree(CHART, workspace / "chart")
    result = helm("package", "chart", "-u", "--version", "0.1.0", "--app-version", "0.1.0", cwd=workspace)
    assert result.returncode == 0, (
        "`helm package chart -u` failed, which is exactly what `ci-release.yaml` runs. "
        f"If it names a dependency it cannot resolve, check the registry and the pin "
        f"in `chart/Chart.yaml`.\n{result.stderr}"
    )
    tarball = workspace / "yadgar-0.1.0.tgz"
    assert tarball.is_file(), sorted(path.name for path in workspace.iterdir())
    return tarball


# ------------------------------------------- 1. the parent renders nothing itself


def test_the_parent_declares_no_templates_of_its_own(tmp_path: Path) -> None:
    """Every rendered object comes from a subchart, asserted by removing them all.

    `chart/charts/` and `chart/Chart.lock` are git-ignored rather than committed
    (ADR-0725), so a copy of `CHART` may or may not carry them depending on
    whether a contributor ran `helm dependency update` locally — hence
    `ignore_errors`/`missing_ok` rather than an assertion either way existed.
    """
    shutil.copytree(CHART, tmp_path / "chart")
    shutil.rmtree(tmp_path / "chart" / "charts", ignore_errors=True)
    (tmp_path / "chart" / "Chart.lock").unlink(missing_ok=True)
    stripped = yaml.safe_load((tmp_path / "chart" / "Chart.yaml").read_text())
    stripped.pop("dependencies", None)
    (tmp_path / "chart" / "Chart.yaml").write_text(yaml.safe_dump(stripped, sort_keys=False))
    assert render(str(tmp_path / "chart")) == [], (
        "this parent rendered an object of its own with every subchart removed. "
        "ADR-0723's revisit_trigger names that as a ninth module nobody declared."
    )


def test_the_templates_directory_holds_only_partials() -> None:
    """`helm lint --strict` needs the directory to exist; nothing in it may render."""
    templates = sorted(path.name for path in (CHART / "templates").iterdir())
    assert templates, "`chart/templates/` is empty, and `helm lint --strict` refuses a chart with no templates directory"
    for name in templates:
        assert name.startswith("_"), (
            f"`chart/templates/{name}` does not start with `_`, so helm will render "
            f"it. This parent renders no objects of its own."
        )


def test_helm_lint_strict_passes() -> None:
    result = helm("lint", "--strict", str(CHART))
    assert result.returncode == 0, result.stdout + result.stderr


# --------------------------- 2. the packaged artifact, and it matches the tree


def test_the_packaged_chart_renders_the_whole_estate(packaged: Path) -> None:
    assert dict(kinds(render(str(packaged)))) == EXPECTED


def test_the_directory_and_the_package_render_the_same_objects(packaged: Path) -> None:
    """An adopter installs the package. A property true only of the tree is not a property."""

    def identity(documents: list[dict]) -> set[tuple[str, str, str]]:
        return {
            (
                str(document.get("apiVersion")),
                str(document.get("kind")),
                str((document.get("metadata") or {}).get("name")),
            )
            for document in documents
        }

    assert identity(render(str(CHART))) == identity(render(str(packaged)))


def test_the_package_carries_every_subchart_so_an_adopter_needs_no_registry(packaged: Path) -> None:
    """MEASURED, BECAUSE THE WHOLE DESIGN TURNS ON IT.

    `helm install` does NOT resolve dependencies — it expects a self-contained
    package. If the published parent carried a `Chart.yaml` naming eight
    dependencies and no subchart bytes, every adopter's install would fail on a
    release that reported success.
    """
    import tarfile

    with tarfile.open(packaged, "r:gz") as archive:
        names = archive.getnames()
    for name, version, _ in _declared():
        assert f"yadgar/charts/{name}/Chart.yaml" in names, (
            f"`{name}` is declared as a dependency and its chart is not inside the "
            f"package, so an adopter's `helm install` would fail on it."
        )
        del version


def _declared() -> list[tuple[str, str, str]]:
    document = yaml.safe_load((CHART / "Chart.yaml").read_text())
    return [
        (entry["name"], entry["version"], entry["repository"])
        for entry in document["dependencies"]
    ]


# ----------------------------------- 3. an adopter's value reaches a child object


def test_an_adopter_value_lands_in_the_rendered_child_object(packaged: Path, tmp_path: Path) -> None:
    """GOAL ITEM 6, asserted on the value in the object rather than on exit 0.

    `config.shared.tlsRotation.pollSeconds` is the leaf, because `yadgarhq/config`
    renders each ConfigMap from a deep merge of its own document under the
    adopter's values (ADR-0721) — so the knob the adopter states must change and
    the sibling knob they did not state must keep the chart's own default. A
    mechanism that replaced the whole document would satisfy the first assertion
    and fail the second.
    """
    values = tmp_path / "adopter.yaml"
    values.write_text("config:\n  shared:\n    tlsRotation:\n      pollSeconds: 45\n")

    for target in (str(CHART), str(packaged)):
        documents = render(target, "-f", str(values))
        shared = [
            document
            for document in documents
            if document.get("kind") == "ConfigMap"
            and (document.get("metadata") or {}).get("name") == "shared"
        ]
        assert len(shared) == 1, f"expected one `shared` ConfigMap from {target}"
        body = yaml.safe_load(shared[0]["data"]["shared.yaml"])
        assert body["tlsRotation"]["pollSeconds"] == 45, f"the adopter's value did not reach {target}"
        assert body["tlsRotation"]["splayMaxSeconds"] == 300, (
            f"a knob the adopter did not state lost the chart's own default in {target}"
        )
        # THE RENDERED BYTES TOO, not only the parsed value. A values file goes
        # through `sigs.k8s.io/yaml`, which converts to JSON first, so a number
        # can arrive as a float: a ConfigMap carrying `pollSeconds: 45.0` parses
        # to 45 here and is then REFUSED by `serde_yaml` for a `u64` at boot.
        # `yadgarhq/config`'s own suite asserts on bytes for this exact reason.
        assert "pollSeconds: 45\n" in shared[0]["data"]["shared.yaml"]


def test_a_value_for_one_child_does_not_reach_another(packaged: Path, tmp_path: Path) -> None:
    """Helm scopes a subchart's values under its own name, PER LEAF."""
    values = tmp_path / "adopter.yaml"
    values.write_text("config:\n  shared:\n    tlsRotation:\n      pollSeconds: 45\n")
    documents = render(str(packaged), "-f", str(values))
    gateway = [
        document
        for document in documents
        if document.get("kind") == "ConfigMap"
        and (document.get("metadata") or {}).get("name") == "gateway"
    ]
    assert len(gateway) == 1
    assert "pollSeconds: 45" not in gateway[0]["data"]["gateway.yaml"]


# ------------------------------------------ 4. installable on a bare cluster (D80)


def test_every_crd_bearing_resource_can_be_switched_off(tmp_path: Path) -> None:
    """The property `ci-pr.yaml`'s `portability` job asserts, proved here too.

    That job reads the `enabled` keys out of `chart/values.yaml` OF THE CHART
    UNDER REVIEW and nothing else, so a parent whose own values file is empty
    fails it for a resource an adopter can in fact turn off. This test is what
    says so locally, before CI does.
    """
    off = yaml.safe_load((CHART / "values.yaml").read_text()) or {}
    flipped: list[str] = []

    def flip(node, path: str = "") -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                here = f"{path}.{key}" if path else key
                if key == "enabled" and isinstance(value, bool):
                    node[key] = False
                    flipped.append(here)
                else:
                    flip(value, here)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                flip(value, f"{path}[{index}]")

    flip(off)
    assert flipped, (
        "`chart/values.yaml` declares no `enabled` key, so the `portability` job's "
        "all-off render equals its default render and every CRD-bearing resource "
        "survives it. See the comment in that file."
    )

    values = tmp_path / "all-off.yaml"
    values.write_text(yaml.safe_dump(off))
    survivors = crd_bearing(render(str(CHART), "-f", str(values)))
    assert survivors == [], f"these resources survived the all-off render: {survivors}"


def test_the_defaults_render_exactly_one_crd_bearing_resource() -> None:
    """Gateway API is a SPECIFICATION and D80 permits it on by default.

    Stated as an equality rather than a ceiling, so a module release that adds a
    dependency on some PRODUCT's CRD arrives as a failing test rather than as a
    line in a job summary nobody reads.
    """
    assert crd_bearing(render(str(CHART))) == [
        ("gateway.networking.k8s.io/v1", "HTTPRoute", "gateway")
    ]
