"""What an adopter actually receives, asserted on the render rather than on an exit code.

SIX PROPERTIES, each one a thing that has already failed in this estate in some
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

5. NO CONFIGURATION KNOB IS STATED IN TWO CONFIGMAPS AT ONCE, and THIS is the
   only repository that can assert it — see
   `test_no_knob_is_stated_in_two_configmaps` for why a per-repository copy
   cannot, and for the real duplicate that stood on `main` for seven commits
   today.

6. THE PUSH PATH TO `main` IS VALIDATED. `.github/workflows/ci.yaml`'s
   `push_validation` job is the only thing that checks the one commit that ever
   changes the eight pins, and a workflow edit is exactly the kind of change
   that reads correct while admitting nothing — so its condition is PARSED and
   EVALUATED here rather than read.

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
# 4.2.3 against the eight pins in `chart/Chart.yaml` today: config 0.2.0,
# gateway 0.9.49, iam 0.8.40, iam-db 0.7.41, project 0.1.18, project-db 0.3.6,
# task 0.5.29 and task-db 0.6.30.
#
# `ConfigMap` SAID 9 AND THE RENDER SAID 3, FOR SEVEN PIN COMMITS, AND NOTHING
# NOTICED. ADR-0740 moved each service's configuration document into that
# service's OWN chart: `gateway` 0.9.49 renders its own `gateway-knobs`
# ConfigMap from `config/gateway.yaml` in the gateway repository, and
# `yadgarhq/config` 0.2.0 then DELETED the seven per-service documents, keeping
# only `shared.yaml` and `audit.yaml`. So the assembled estate holds three
# ConfigMaps — `audit`, `gateway-knobs`, `shared` — where it held nine. Every
# other kind is unchanged.
#
# THIS NUMBER MOVES WHEN A PIN MOVES, and that is the point rather than a
# maintenance cost. A module release that adds or drops an object changes what an
# adopter of the parent receives, and a bump whose effect on the rendered set
# nobody looked at is exactly what ADR-0722 removed the compatibility gate in
# front of. Update it in the same commit as the pin, and say in the pull request
# which module changed it. That instruction was already here and is what nobody
# honoured; it is kept verbatim rather than softened.
#
# IT IS A LITERAL, AND IT MUST STAY ONE. A count derived from the render — or
# rewritten by any tool, hook or job — agrees with whatever the render happens
# to be and therefore detects nothing. The whole value of this dict is that a
# human looked at the number and wrote it down.
EXPECTED = {
    "ConfigMap": 3,
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


# FLOORS RATHER THAN THE CURRENT COUNTS OF 3 AND 4, following `no_build_cache.py`
# in `yadgarhq/actions` — a gate that reports success having inspected nothing is
# the defect, not the absence of a subject. A module release that deletes a
# document or a knob is a LEGITIMATE change and must not redden this suite, so
# these are not equalities; `EXPECTED` above is where a moved count is noticed.
#
# TWO OF EACH, because two is the fewest at which "stated in more than one
# ConfigMap" is expressible at all. With one ConfigMap there is no second
# document to collide with, and with one leaf path there is no pair to compare —
# in either case the gate below passes having proved nothing, which is exactly
# the false green these floors exist to turn red.
MINIMUM_CONFIGMAPS = 2
MINIMUM_LEAF_PATHS = 2


def leaves(node, prefix: str = ""):
    """Every leaf key path in a parsed document, dotted. PURE.

    Copied deliberately from `one_source_per_knob.py` in `yadgarhq/config` so the
    two gates mean the same thing by "leaf": a mapping recurses, and a list or a
    scalar is where a value lives. A list's INDICES are not key paths — two
    documents each holding a three-element list under different keys collide at
    no index. An EMPTY mapping is a leaf, because there is nothing under it.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict) and value:
                yield from leaves(value, path)
            else:
                yield path


def configmap_leaf_paths(documents: list[dict]) -> dict[str, list[tuple[str, str]]]:
    """Leaf key path -> every (ConfigMap name, data key) that states it. PURE.

    PURE AND DOCUMENT-TAKING SO THE RED CASE NEVER TOUCHES THE REAL TREE. A gate
    that has only ever been fed the real render has never been shown to refuse
    anything, and this one's red case is synthetic for that reason.

    A DATA VALUE THAT IS NOT A YAML MAPPING IS NOT COUNTED, and the floors above
    are what keep that from becoming a hole: a ConfigMap carrying plain text
    states no key paths, so there is nothing to attribute, and a future release in
    which NOTHING parses to a mapping trips `MINIMUM_LEAF_PATHS` rather than
    passing silently.
    """
    index: dict[str, list[tuple[str, str]]] = {}
    for document in documents:
        if document.get("kind") != "ConfigMap":
            continue
        name = str((document.get("metadata") or {}).get("name"))
        for key, raw in sorted((document.get("data") or {}).items()):
            try:
                body = yaml.safe_load(raw)
            except yaml.YAMLError:
                continue
            if not isinstance(body, dict):
                continue
            for path in leaves(body):
                index.setdefault(path, []).append((name, key))
    return index


def stated_in_more_than_one_configmap(
    index: dict[str, list[tuple[str, str]]],
) -> list[tuple[str, list[tuple[str, str]]]]:
    """The refusal predicate: leaf paths stated by two or more ConfigMaps. PURE.

    KEYED ON THE CONFIGMAP NAME, and the data key is carried into the message so
    a failure is diagnosable. Two data keys of ONE ConfigMap stating one path is
    a fault of the single chart that renders it, which that chart's own
    `one_source_per_knob.py` already sees; the cross-chart case below is the one
    nothing in the estate could see until this gate.
    """
    return sorted(
        (path, sources)
        for path, sources in index.items()
        if len({name for name, _ in sources}) > 1
    )


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
    """Helm scopes a subchart's values under its own name, PER LEAF — BOTH WAYS.

    THE CONFIGMAP THIS LOOKED UP WAS NAMED `gateway` AND IS NOT RENDERED ANY
    MORE. ADR-0740 moved gateway's configuration document into gateway's own
    chart, which names the ConfigMap `gateway-knobs` and deliberately not
    `gateway` — while `config` still rendered a `gateway` document, one install
    of this parent would have carried two ConfigMaps of one name. `config` 0.2.0
    then deleted that document, so nothing named `gateway` is rendered anywhere
    and the old filter matched nothing.

    ASSERTED IN BOTH DIRECTIONS rather than one, because the one-directional
    form passes for a chart that reads no adopter value at all: a knob ABSENT
    from a ConfigMap proves nothing on its own. It has to be absent from one
    document in the same render that shows it ARRIVING in the other. So a value
    is aimed at each of the two children here, and each rendered document is
    checked for its own value and against its sibling's.

    ON BYTES, NOT ONLY ON THE PARSED VALUE, for the reason the test above gives:
    a values file reaches helm through `sigs.k8s.io/yaml`, so an integer can
    arrive as a float and a ConfigMap carrying `intervalSeconds: 111.0` parses
    to 111 here while `serde_norway` refuses it for a `u64` at boot. Gateway's
    own `_merge.tpl` names that exact hazard.
    """
    values = tmp_path / "adopter.yaml"
    values.write_text(
        "config:\n"
        "  shared:\n"
        "    tlsRotation:\n"
        "      pollSeconds: 45\n"
        "gateway:\n"
        "  toolsPoll:\n"
        "    intervalSeconds: 111\n"
    )
    documents = render(str(packaged), "-f", str(values))

    def body(name: str, key: str) -> str:
        found = [
            document
            for document in documents
            if document.get("kind") == "ConfigMap"
            and (document.get("metadata") or {}).get("name") == name
        ]
        assert len(found) == 1, (
            f"expected exactly one ConfigMap named `{name}`, found {len(found)}. "
            f"The rendered ConfigMaps are "
            f"{sorted((d.get('metadata') or {}).get('name') for d in documents if d.get('kind') == 'ConfigMap')}."
        )
        return found[0]["data"][key]

    shared = body("shared", "shared.yaml")
    knobs = body("gateway-knobs", "gateway.yaml")

    # Each value ARRIVES where it was aimed...
    assert "pollSeconds: 45\n" in shared, "the value aimed at `config` did not reach `shared`"
    assert "intervalSeconds: 111\n" in knobs, (
        "the value aimed at `gateway` did not reach `gateway-knobs`"
    )
    # ...and reaches nothing else.
    assert "intervalSeconds" not in shared, (
        "a value stated under `gateway:` reached `config`'s `shared` ConfigMap"
    )
    assert "pollSeconds" not in knobs, (
        "a value stated under `config:` reached `gateway`'s `gateway-knobs` ConfigMap"
    )


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



# ------------------------- 5. one knob, one ConfigMap (ADR-0740's own consequence)


def test_no_knob_is_stated_in_two_configmaps(packaged: Path) -> None:
    """ADR-0740: "THE ONE-SOURCE GATE MUST FOLLOW THE DOCUMENTS ... A move that
    leaves the gate behind is worse than no move."

    IT HAD BEEN LEFT BEHIND, WHICH IS WHY THIS EXISTS. `one_source_per_knob.py` in
    `yadgarhq/config` globs `chart/config/*.yaml`, so after ADR-0740 it sees only
    `shared.yaml` and `audit.yaml`. `toolsPoll.intervalSeconds` now lives in
    `yadgarhq/gateway`'s own chart, where nothing counts it against anything.

    A PER-REPOSITORY COPY CANNOT CLOSE THIS. The fault is a SERVICE chart stating
    a key that `config`'s `shared.yaml` also states, and gateway's repository
    cannot see `config`'s document — nor config's see gateway's. THIS repository
    is the only place in the estate that sees every document at once, because its
    release resolves all eight charts together (`helm package chart -u`,
    ADR-0725). So the gate belongs here and nowhere else.

    IT IS NOT HYPOTHETICAL — IT HAD A REAL SUBJECT THIS MORNING. Measured
    2026-09-19 by pulling the charts: `config` 0.1.8 carried
    `config/config/gateway.yaml` stating `toolsPoll.intervalSeconds: 600`, and
    `gateway` 0.9.49 renders `gateway-knobs` stating the same leaf path. Both were
    pinned on `main` together from `adf30008` ("ci: pin gateway 0.9.49") until
    `fe8de55` ("ci: pin config 0.2.0") — seven pin commits, during which this gate
    would have been RED. That duplicate was the transitional state ADR-0740's
    migration created on purpose; nothing measured it going away.
    """
    documents = render(str(packaged))
    names = sorted(
        str((document.get("metadata") or {}).get("name"))
        for document in documents
        if document.get("kind") == "ConfigMap"
    )
    assert len(names) >= MINIMUM_CONFIGMAPS, (
        f"the assembled render holds {len(names)} ConfigMap(s), and "
        f"{MINIMUM_CONFIGMAPS} is the fewest this gate can inspect. It would "
        f"otherwise report success having compared nothing. If the estate "
        f"genuinely stopped rendering configuration ConfigMaps, delete this gate "
        f"rather than leaving it green and blind. Found: {names}."
    )

    index = configmap_leaf_paths(documents)
    assert len(index) >= MINIMUM_LEAF_PATHS, (
        f"the assembled render states {len(index)} leaf key path(s) across "
        f"{len(names)} ConfigMap(s), and {MINIMUM_LEAF_PATHS} is the fewest this "
        f"gate can inspect — with fewer there is no pair to compare and this "
        f"assertion proves nothing. ConfigMaps found: {names}."
    )

    duplicated = stated_in_more_than_one_configmap(index)
    assert duplicated == [], "\n".join(
        f"`{path}` is stated in {len({name for name, _ in sources})} ConfigMaps: "
        + ", ".join(f"{name}/{key}" for name, key in sources)
        + ". A knob has ONE source — there is no merge and no precedence between "
        "these documents (ADR-0569, ADR-0571). Delete it from all but one."
        for path, sources in duplicated
    )


def test_the_one_source_gate_refuses_a_duplicate() -> None:
    """THE RED CASE, SYNTHETIC ON PURPOSE.

    A gate that has only ever passed proves nothing, and the real tree cannot
    supply the red side — it is green today and the whole point of the gate is
    to keep it that way. So the refusal is asserted against two documents
    constructed here, both stating `toolsPoll.intervalSeconds`, which is the
    exact pair that stood on `main` for seven commits today.
    """
    duplicate = [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "gateway"},
            "data": {"gateway.yaml": "toolsPoll:\n  intervalSeconds: 600\n"},
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "gateway-knobs"},
            "data": {"gateway.yaml": "toolsPoll:\n  intervalSeconds: 600\n"},
        },
    ]
    index = configmap_leaf_paths(duplicate)
    assert index == {"toolsPoll.intervalSeconds": [("gateway", "gateway.yaml"), ("gateway-knobs", "gateway.yaml")]}
    assert stated_in_more_than_one_configmap(index) == [
        (
            "toolsPoll.intervalSeconds",
            [("gateway", "gateway.yaml"), ("gateway-knobs", "gateway.yaml")],
        )
    ], "the predicate accepted one leaf path stated by two ConfigMaps"

    # THE SAME PATH IN ONE CONFIGMAP IS NOT THIS FAULT, asserted so the predicate
    # is shown to be narrow rather than merely strict — a gate that refuses
    # everything is as useless as one that refuses nothing.
    single = [duplicate[0]]
    assert stated_in_more_than_one_configmap(configmap_leaf_paths(single)) == []

    # A DISTINCT LEAF UNDER A SHARED PARENT IS NOT THIS FAULT EITHER. `tlsRotation`
    # appearing in two documents is a collision only if a knob UNDER it does, which
    # is why `leaves` reports leaves and not every node.
    siblings = [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "shared"},
            "data": {"shared.yaml": "tlsRotation:\n  pollSeconds: 30\n"},
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "audit"},
            "data": {"audit.yaml": "tlsRotation:\n  splayMaxSeconds: 300\n"},
        },
    ]
    assert stated_in_more_than_one_configmap(configmap_leaf_paths(siblings)) == []


# ----------------------------- 6. the push path to `main` is validated, not assumed


WORKFLOW = REPO / ".github" / "workflows" / "ci.yaml"

# The job added because NOTHING validated the one commit that ever changes the
# eight pins. Named here so a rename arrives as a failure of this test rather
# than as a push path that quietly stops being checked again.
PUSH_JOB = "push_validation"


def _admits(condition: str, context: dict[str, str]) -> bool:
    """Would GitHub run a job with this `if:`, in this event context?

    DELIBERATELY NOT A GENERAL EXPRESSION PARSER, and not a port of
    `ci_verdict.py` from `yadgarhq/actions` either — that file is the merge
    gate's verdict over `ci-pr.yaml`'s conditions and has no business being
    duplicated here. This models the ONE shape `push_validation`'s condition
    uses: `github.<field> == '<literal>'` clauses joined by `&&`. A condition
    that grows past that shape REFUSES here rather than being approximated,
    because an evaluator that silently mis-reads a condition is worse than none.

    ADMISSION IS NOT MODELLED AND DOES NOT NEED TO BE. The implicit check
    `test_ci_release_skip_propagation.py` in `yadgarhq/actions` documents applies
    to a job whose `needs:` ancestors did not all conclude `success`, and this job
    is asserted below to declare no `needs:` at all — which is why it cannot be
    skipped by an ancestor the way that repository's `parent` job was.
    """
    for clause in condition.split("&&"):
        left, operator, right = clause.strip().partition("==")
        assert operator == "==", (
            f"`{PUSH_JOB}`'s condition contains a clause this test cannot "
            f"evaluate: {clause.strip()!r}. Extend `_admits` deliberately rather "
            f"than letting the condition go unchecked."
        )
        reference = left.strip()
        assert reference in context, (
            f"`{PUSH_JOB}`'s condition reads `{reference}`, which this test does "
            f"not model. Add it to every context below, with the value each event "
            f"really carries."
        )
        if context[reference] != right.strip().strip("'"):
            return False
    return True


def test_the_push_path_job_admits_a_push_to_main() -> None:
    """MEASURED BY EVALUATION, BECAUSE A WORKFLOW EDIT CAN READ CORRECT AND ADMIT NOTHING.

    On the bot commit `adf30008` ("ci: pin gateway 0.9.49 in the parent chart"),
    `main / detect`, `precommit`, `template`, `test`, `portability`, `workflows`
    and `vulnerabilities` all reported `skipped` while `main / passed` reported
    SUCCESS — correctly, because every one of those jobs' own conditions in
    `ci-pr.yaml` reads `github.event_name != 'push'`. So the one commit that ever
    changes the eight pins was checked by nothing. `push_validation` is this
    repository's own answer to that, and the table below is the proof that its
    condition admits the event it was written for and refuses the three it was not.
    """
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    assert PUSH_JOB in jobs, (
        f"`{PUSH_JOB}` is not a job in {WORKFLOW.name}. It is the only thing that "
        f"validates a push to `main`; ADR-0722's `parent_bump.py` writes the pins "
        f"straight to `main` over the Contents API."
    )
    job = jobs[PUSH_JOB]
    condition = str(job["if"])

    cases = [
        ({"github.event_name": "push", "github.ref": "refs/heads/main"}, True),
        ({"github.event_name": "pull_request", "github.ref": "refs/heads/main"}, False),
        ({"github.event_name": "push", "github.ref": "refs/heads/some-branch"}, False),
        ({"github.event_name": "push", "github.ref": "refs/tags/v0.1.0"}, False),
    ]
    for context, expected in cases:
        assert _admits(condition, context) is expected, (
            f"`{PUSH_JOB}`'s condition `{condition}` evaluates to "
            f"{not expected} for {context}, and it must be {expected}."
        )

    # NO `needs:`, which is what keeps an upstream skip from skipping this job —
    # the defect `test_ci_release_skip_propagation.py` in `yadgarhq/actions` was
    # written for, where a job with no status function skipped because an INDIRECT
    # ancestor had not concluded `success`.
    assert not job.get("needs"), (
        f"`{PUSH_JOB}` declares `needs: {job.get('needs')}`. A job with no "
        f"`always()`/`success()` in its `if:` is skipped when any ancestor did "
        f"not conclude `success`, so a `needs:` here can silently turn the push "
        f"path back off."
    )

    # WHAT IT ACTUALLY RUNS, asserted loosely so a future edit cannot gut the job
    # while the condition above stays green. A job that is admitted and does
    # nothing is the same false green as a job that is never admitted.
    body = yaml.safe_dump(job)
    for fragment in ("pytest scripts/tests/", "helm lint --strict", "helm dependency update"):
        assert fragment in body, (
            f"`{PUSH_JOB}` no longer runs `{fragment}`. The push path validates a "
            f"pin change by rendering and testing it; without this it is admitted "
            f"and proves nothing."
        )
