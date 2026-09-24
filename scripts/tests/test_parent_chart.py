"""What an adopter actually receives, asserted on the render rather than on an exit code.

SEVEN PROPERTIES, each one a thing that has already failed in this estate in some
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

7. THE PLATFORM LAYER IS OFF BY DEFAULT AND WHOLE WHEN IT IS ON. `platform` is
   the ninth dependency and the only one with a `condition`, so the default
   render must be unchanged by its arrival — `EXPECTED` below does not move, and
   the assertion that it did not is the load-bearing one. What IS counted is the
   ADOPTER-values render, `example/values.yaml`, where every `platform.*.create`
   is true: its object set, its renewal ladder, its RBAC triples and the
   agreement between each preflight probe and the toggle that renders what the
   probe probes. ADR-0777 is the record for the template that carries the
   parent's own refusals.

NO SKIPS (ADR-0650). `helm` absent is a failure, not a skip: this suite and the
shared `helm lint and render` hook both need it, and a suite that skips when its
subject is absent reports a pass nobody earned.

THE PACKAGED-CHART RENDERS ARE NOT OFFLINE. Per ADR-0725 nothing under
`chart/charts/` is committed, so the `packaged` fixture below resolves this
chart's nine dependencies from `oci://ghcr.io/yadgarhq/charts` with
`helm package chart -u` — the same command `ci-release.yaml` runs — and needs
the registry reachable. The directory-only renders (test 1) need no registry, but
they DO need `helm dependency update chart` to have run in this working tree,
which is what `ci.yaml`'s `push_validation` job and the `helm lint and render`
pre-commit hook both do before they run anything.

Run: python3 -m pytest scripts/tests/ -q
"""

from __future__ import annotations

import collections
import re
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
#
# THE PLATFORM LAYER DID NOT MOVE IT, AND THAT IS THE POINT RATHER THAN A
# COINCIDENCE. `platform` is the ninth dependency and the only one carrying a
# `condition`, `platform.enabled`, which `chart/values.yaml` sets false. So the
# default render gains no object — and no hook Job either, though `helm template`
# does emit hooks. Re-measured 2026-09-24 on helm 3.18.4 and 4.3.0 with `platform`
# 0.1.7 declared: 32 objects, the same six kinds, unchanged. ADR-0777 makes the
# assertion that this dict is UNCHANGED the load-bearing one; a step that adds an
# object to `platform` moves `ADOPTER_EXPECTED` below and not this.
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

# ── THE ADOPTER-VALUES RENDER, AND EVERY LITERAL COUNTED OVER IT ─────────────
# `example/values.yaml` beside this chart. It turns the platform layer on — every
# `platform.*.create` true, `autoscaling.enabled` true in all seven modules, and
# `database.create` true in the three `-db` modules. It is the only render in this
# suite where the platform layer exists at all.
ADOPTER_VALUES = REPO / "example" / "values.yaml"

# EVERY API GROUP THAT RENDER MUST BE HANDED, and a LITERAL rather than a list
# read off the charts. A render check calls `fail`, which aborts the WHOLE render
# at the FIRST failing check and names only that one — so a render missing a group
# is refused for that check's reason before the objects counted below exist. A
# tuple derived from the charts would follow a check DELETED from one of them and
# keep passing over one fewer group.
#
# MEASURED 2026-09-24 on helm 3.18.4 by dropping one flag at a time, which is the
# only way to tell a required group from a decorative one:
#
#   cert-manager.io/v1              required — `platform`'s cert-manager check
#   gateway.envoyproxy.io/v1alpha1  required — `platform`'s Envoy Gateway check
#   k8s.mariadb.com/v1alpha1        required — the three `-db` charts' checks
#   keda.sh/v1alpha1                NOT required today, and deliberately absent:
#                                   no module chart declares a KEDA render check
#                                   yet, so ScaledObjects render unguarded. The
#                                   module-chart sweep in
#                                   `plans/the-platform-layer-in-the-charts.md`
#                                   adds those checks, and this tuple gains the
#                                   group in the same change that makes it
#                                   required.
DECLARED_API_VERSIONS = (
    "cert-manager.io/v1",
    "gateway.envoyproxy.io/v1alpha1",
    "k8s.mariadb.com/v1alpha1",
)
API_VERSIONS = tuple(
    part for group in DECLARED_API_VERSIONS for part in ("--api-versions", group)
)

# WHAT THE WHOLE ESTATE PLUS ITS PLATFORM LAYER IS, measured 2026-09-24 on helm
# 3.18.4 and 4.3.0 against the nine pins in `chart/Chart.yaml` today, `platform`
# at 0.1.7. A LITERAL for the same reason `EXPECTED` is one.
#
# A `platform` RELEASE MOVES THIS ONE AND NOT `EXPECTED`, because `platform` is
# absent from the default render. A MODULE release that adds or drops an object
# moves BOTH, since every module renders in both. Update whichever moved in the
# same commit as the pin, and say in the pull request which chart moved it.
ADOPTER_EXPECTED = {
    "Certificate": 12,
    "ConfigMap": 4,
    "Deployment": 8,
    "EnvoyProxy": 1,
    "Gateway": 1,
    "GatewayClass": 1,
    "HTTPRoute": 1,
    "Issuer": 2,
    "Job": 4,
    "MariaDB": 3,
    "NetworkPolicy": 2,
    "PodDisruptionBudget": 8,
    "Role": 3,
    "RoleBinding": 3,
    "ScaledObject": 7,
    "Service": 10,
    "ServiceAccount": 10,
    "StatefulSet": 1,
}
ADOPTER_OBJECTS = 81

# THE RBAC TRIPLES, AND THE COUNT IS NOT ONE PER JOB. Four hook Jobs render and
# THREE triples serve them: `preflight` holds its own, with `create`, `get` and
# `delete` on the objects it submits; `envoy-gateway-probe` holds its own for the
# same reason, being a second preflight Job that submits objects of its own; and
# `bootstrap-secrets` holds one that BOTH bootstrap Jobs use — `bootstrap-secrets`
# and `admin-bootstrap-token` mint Secrets with the same permission, and a second
# identity would be the same permission held twice. A triple per Job would be
# four, and one triple in total would be one. It is neither.
#
# IT IS THREE BECAUSE THE PREFLIGHT IS TWO JOBS. The post-install Envoy Gateway
# probe in `plans/the-platform-layer-in-the-charts.md` is the second preflight
# Job, and it landed in `platform` 0.1.7. MEASURED at that pin on 2026-09-24,
# which is the pin `chart/Chart.yaml` declares: `RBAC_TRIPLE_NAMES_AT_R5` gained
# `envoy-gateway-probe` and `HOOK_JOBS_AT_R5` went to 4, alongside
# `ADOPTER_OBJECTS` 77 → 81.
#
# `AGREEMENT_PAIRS_AT_R5` DID NOT MOVE WITH THEM, and the asymmetry is the point.
# The new Job is a third RBAC identity and a fourth hook, so these two counts see
# it; its probe pairs two of `platform`'s own keys, so the parent's pair count does
# not. The two numbers move at different pins, never together.
#
# THE RED CASE FOR BOTH IS A VALUES FLIP, NOT AN EDITED CHART, AND IT IS RUN
# RATHER THAN DESCRIBED — see
# `test_dropping_the_second_preflight_probe_reddens_the_hook_job_and_triple_gates`
# below. `platform.preflight.probes.envoyGateway: false` is always honoured (an
# explicit `false` on a probe always is, and `platform`'s own `values.yaml` says
# so at length), and it drops the second preflight Job: the render falls to three
# Jobs, two triples and 77 objects. So one flip reddens these two constants,
# `ADOPTER_OBJECTS` and `ADOPTER_EXPECTED` together, and that test asserts all
# three of those numbers rather than leaving this paragraph to carry them.
#
# UNTIL THAT TEST EXISTED THE ONLY HOME OF THESE TWO CONSTANTS WAS THE GATE THAT
# READS THEM, which made the gate its own red case — the circularity that
# `test_an_object_added_to_the_platform_layer_reddens_the_object_set_gate` has
# always closed for `ADOPTER_OBJECTS` and nothing closed for these.
RBAC_TRIPLE_NAMES_AT_R5 = ["bootstrap-secrets", "envoy-gateway-probe", "preflight"]
HOOK_JOBS_AT_R5 = 4

# WHAT THE FLIP ABOVE LEAVES BEHIND, a literal for the same reason the two above
# are literals. MEASURED 2026-09-24 on helm 3.18.4 and 4.3.0 at `platform` 0.1.7.
#
# THE POSITIVE FORM IS WHAT MAKES THE RED CASE NON-VACUOUS. `!=
# RBAC_TRIPLE_NAMES_AT_R5` alone goes green for a great many wrong lists, so a
# constant reverted to some OTHER wrong value would still satisfy it. The
# equality below names the one list the flip really produces.
RBAC_TRIPLE_NAMES_WITHOUT_THE_SECOND_PROBE = ["bootstrap-secrets", "preflight"]

# THE FOUR OBJECTS THE SECOND PREFLIGHT JOB BRINGS: its Job, its Role, its
# RoleBinding and its ServiceAccount — one each, which is why 81 becomes 77.
OBJECTS_PER_PROBE_JOB = 4

# THE RENEWAL LADDER, lifted from `yadgarhq/platform`'s own `test_ladder.py` to the
# whole-estate render. The invariant is that every leaf's `renewBefore` is
# DISTINCT and six hours from its neighbour, so at most one service restarts per
# renewal instant.
#
# TWELVE OBJECTS AND ELEVEN VALUES, and the difference is exactly one object
# contributing no rung: the CA root. It carries a `renewBefore` of its own — one
# year against a ten-year duration — and nothing mounts it as a serving or client
# credential, so its renewal re-signs with the same key rather than restarting a
# service. The set is scoped to the Certificates that are not `isCA`.
CERTIFICATES_AT_R5 = 12
LADDER = {
    "720h",
    "726h",
    "732h",
    "738h",
    "744h",
    "750h",
    "756h",
    "762h",
    "768h",
    "774h",
    "780h",
}

# THE PROBE/TOGGLE PAIRS, AND WHY THIS RENDER IS WHERE THEY BECOME ASSERTABLE.
# A probe's default is TIED to the toggle that renders what the probe probes, and
# `platform` rendering alone can only see its own toggles: it renders neither a
# ScaledObject nor a MariaDB CR, so `probes.keda` and `probes.mariadb` resolve
# false there and nothing pairs them with anything. At the parent both halves are
# visible — `autoscaling.enabled` and `database.create` are sibling charts' keys —
# so each probe is asserted against the OBJECTS in the same render.
#
# THREE PAIRS, AND THREE IS PERMANENT RATHER THAN PENDING A PIN.
# `plans/the-platform-layer-in-the-charts.md` now also states three, for the same
# reason: the fourth is `probes.envoyGateway` against `gatewayListener.create`, and
# it does not belong at this scope. BOTH halves of that pair are `platform`'s OWN
# keys. `platform` can see them both, and its own suite already pairs them, with a
# red case at `gatewayListener.create: false`. The three above are here for the
# opposite reason — no chart alone can see both halves of any of them, because
# `autoscaling.enabled` and `database.create` are SIBLING charts' keys. The parent
# asserts the pairs it alone can see; a pair whose two halves live inside one chart
# is that chart's own obligation.
#
# SO THE `platform` PIN THAT BROUGHT THE FOURTH PROBE DID NOT MOVE THIS NUMBER, and
# that is measured rather than reasoned. `platform`'s Envoy Gateway probe is a
# SECOND Job — `envoy-gateway-probe`, post-install, with its own `PROBES=` line —
# and `probes_declared` below reads the `preflight` Job alone. At 0.1.7, the pin
# `chart/Chart.yaml` declares, measured 2026-09-24: the render declares `{preflight:
# [cert-manager, keda, mariadb-operator], envoy-gateway-probe: [envoy-gateway]}` and
# `unpaired_probes` returns []. `ADOPTER_OBJECTS`, `HOOK_JOBS_AT_R5` and
# `RBAC_TRIPLE_NAMES_AT_R5` moved at that pin. This one did not.
#
# THIS NUMBER IS A CROSS-CHECK ON `PAIR_OFF_END`, NOT THE DENOMINATOR. The
# denominator is read off the RENDER by `unpaired_probes`, because a count of the
# pairs this file iterates agrees with this file whatever the estate does. This
# constant is what reddens if somebody adds a pair and forgets the number.
AGREEMENT_PAIRS_AT_R5 = 3

# The operator each probe names in the rendered script, and the kind whose
# presence in the same render is the other half of the pair.
PROBE_OPERATOR = {"certManager": "cert-manager", "keda": "keda", "mariadb": "mariadb-operator"}
PROBE_KIND = {"certManager": "Certificate", "keda": "ScaledObject", "mariadb": "MariaDB"}
PROBE_TOGGLE = {
    "certManager": "platform.internalCA.create, platform.certificates.create or platform.edgeTLS.create",
    "keda": "autoscaling.enabled in the module charts",
    "mariadb": "database.create in the three `-db` charts",
}

PROBE_LIST = re.compile(r'^PROBES="(?P<probes>[^"]*)"$', re.MULTILINE)


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


def chart_without_its_dependencies(destination: Path) -> Path:
    """A copy of this chart with every subchart and the `dependencies:` key gone.

    `chart/charts/` and `chart/Chart.lock` are git-ignored rather than committed
    (ADR-0725), so a copy of `CHART` may or may not carry them depending on
    whether a contributor ran `helm dependency update` locally — hence
    `ignore_errors`/`missing_ok` rather than an assertion either way.

    THIS IS THE RENDER `templates/_validate.tpl` IS WRITTEN NIL-SAFE FOR, and it
    is a shared helper rather than a copy for exactly that reason. `.Values.platform`
    is ABSENT here, so an unguarded `.Values.platform.bootstrap.create` RAISES
    rather than evaluating false — and the test it reddens is three files from the
    change that broke it. Two callers assert over it; both need the same tree.
    """
    copy = destination / "chart"
    shutil.copytree(CHART, copy)
    shutil.rmtree(copy / "charts", ignore_errors=True)
    (copy / "Chart.lock").unlink(missing_ok=True)
    stripped = yaml.safe_load((copy / "Chart.yaml").read_text())
    stripped.pop("dependencies", None)
    (copy / "Chart.yaml").write_text(yaml.safe_dump(stripped, sort_keys=False))
    return copy


def test_the_parent_declares_no_templates_of_its_own(tmp_path: Path) -> None:
    """Every rendered object comes from a subchart, asserted by removing them all."""
    assert render(str(chart_without_its_dependencies(tmp_path))) == [], (
        "this parent rendered an object of its own with every subchart removed. "
        "ADR-0723's revisit_trigger names that as a module nobody declared."
    )


# THE ONE NON-PARTIAL THIS DIRECTORY MAY HOLD, BY NAME. ADR-0777 is the ruling
# that put it there and the reason it is a name rather than a predicate: a test
# amended to `name.startswith("_") or name.endswith(".yaml")` would permit every
# future object template silently, which is the property this test exists to hold.
# A second non-partial needs its own ruling and its own line here.
PERMITTED_NON_PARTIALS = {"validate.yaml"}


def test_the_templates_directory_holds_only_partials(tmp_path: Path) -> None:
    """`helm lint --strict` needs the directory to exist; nothing in it may render.

    AMENDED BY NAME FOR `validate.yaml`, PER ADR-0777. That file carries the
    parent's own refusals — a `fail` inside a partial never executes, so the call
    has to sit in a rendered template — and it EMITS NOTHING.

    AND THE EMITS-NOTHING HALF IS ASSERTED RATHER THAN ASSUMED. A file whose
    stated property is "emits nothing" needs an assertion that can go red, or the
    property is prose. So this test renders the parent with its `dependencies`
    stripped, exactly as `test_the_parent_declares_no_templates_of_its_own` does,
    and demands an empty render — the phrasing that catches `validate.yaml`
    growing an object, whatever guard that object happens to sit behind.
    """
    templates = sorted(path.name for path in (CHART / "templates").iterdir())
    assert templates, "`chart/templates/` is empty, and `helm lint --strict` refuses a chart with no templates directory"
    for name in templates:
        assert name.startswith("_") or name in PERMITTED_NON_PARTIALS, (
            f"`chart/templates/{name}` does not start with `_` and is not one of "
            f"{sorted(PERMITTED_NON_PARTIALS)}, so helm will render it. This parent "
            f"renders no objects of its own. Adding a second one is a decision for "
            f"the record — see ADR-0777 and `_no_objects_of_its_own.tpl`."
        )
    assert render(str(chart_without_its_dependencies(tmp_path))) == [], (
        "`chart/templates/` holds a non-partial that EMITTED AN OBJECT. "
        f"{sorted(PERMITTED_NON_PARTIALS)} is permitted here on the stated ground "
        f"that it renders nothing, and this is the assertion that keeps that true."
    )


def test_helm_lint_strict_passes() -> None:
    result = helm("lint", "--strict", str(CHART))
    assert result.returncode == 0, result.stdout + result.stderr


# --------------------------- 2. the packaged artifact, and it matches the tree


def test_the_packaged_chart_renders_the_whole_estate(packaged: Path) -> None:
    assert dict(kinds(render(str(packaged)))) == EXPECTED


def test_the_default_render_is_unchanged_by_the_platform_dependency() -> None:
    """THE LOAD-BEARING ASSERTION OF ADR-0777, stated on the DIRECTORY and directly.

    `platform` is the ninth dependency and the only one with a `condition`. If
    `chart/values.yaml` ever stops declaring `platform.enabled`, helm leaves a
    dependency ENABLED when no path its `condition` names resolves — measured
    2026-09-24 on helm 3.18.4, where `--set platform.valkey.create=true` with no
    `platform.enabled` key rendered the Valkey Deployment, Service and
    NetworkPolicy. So the whole platform layer arrives in every adopter's default
    install behind a values key nobody deleted on purpose.

    The equality below is what catches that, in both directions, on the render five
    other assertions and the shared `helm-lint` hook depend on.
    """
    assert dict(kinds(render(str(CHART)))) == EXPECTED, (
        "the default render moved. `platform` sits behind `condition: platform.enabled`, "
        "which `chart/values.yaml` sets false, so it must contribute no object and no "
        "hook Job to this render. ADR-0777: a step that adds an object to `platform` "
        "moves `ADOPTER_EXPECTED` and not this."
    )


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


# WHAT THE WALK BELOW MUST FIND, and it is TRANSITIVE. One first-level member per
# declared dependency, plus the one a level down: `platform` declares the upstream
# NATS chart under `condition: nats.create`, so the published parent carries
# `yadgar/charts/platform/charts/nats/Chart.yaml`. Measured 2026-09-24 on helm
# 3.18.4 over `helm package chart -u`.
#
# THE NESTED ONE IS WHY THIS COUNTS RATHER THAN ONLY CHECKING NAMES. A loop over
# the parent's own `dependencies:` cannot see one level down, so a subchart of a
# subchart could go missing with every named assertion still green — and
# `helm install` resolves nothing, so the adopter meets it and nobody else does.
NESTED_SUBCHART_MEMBERS = ["yadgar/charts/platform/charts/nats/Chart.yaml"]


def test_the_package_carries_every_subchart_so_an_adopter_needs_no_registry(packaged: Path) -> None:
    """MEASURED, BECAUSE THE WHOLE DESIGN TURNS ON IT.

    `helm install` does NOT resolve dependencies — it expects a self-contained
    package. If the published parent carried a `Chart.yaml` naming nine
    dependencies and no subchart bytes, every adopter's install would fail on a
    release that reported success.

    THE WALK IS TRANSITIVE AND IT ASSERTS THE NUMBER IT EXAMINED. A `Chart.yaml`
    count of nine would be satisfied by nine first-level members with the nested
    one missing, which is the case the named assertion below cannot see and the
    equality can.
    """
    import tarfile

    with tarfile.open(packaged, "r:gz") as archive:
        names = archive.getnames()

    failures = vendoring_failures(names)
    assert failures == [], "\n".join(failures)


def expected_vendored_members() -> list[str]:
    return [f"yadgar/charts/{name}/Chart.yaml" for name, _, _ in _declared()] + list(
        NESTED_SUBCHART_MEMBERS
    )


def vendoring_failures(names: list[str]) -> list[str]:
    """Every subchart the package is missing or carries unannounced. PURE.

    PURE AND MEMBER-LIST-TAKING SO THE RED CASE NEVER HAS TO BUILD A BROKEN
    PACKAGE. A gate fed only real packages has never been shown to refuse one, and
    the case that matters — a subchart of a subchart missing — cannot be produced
    by any values file.
    """
    expected = expected_vendored_members()
    failures = [
        f"`{member}` is not inside the package, so an adopter's `helm install` "
        f"would fail on it — it resolves nothing."
        for member in expected
        if member not in names
    ]
    found = sorted(
        name
        for name in names
        if name.startswith("yadgar/charts/") and name.endswith("/Chart.yaml")
    )
    if found != sorted(expected):
        failures.append(
            f"the package carries {len(found)} chart(s) under `yadgar/charts/` and "
            f"this gate expects {len(expected)}, walked transitively: expected "
            f"{sorted(expected)}, found {found}. A subchart that arrived or left "
            f"without this list moving is a change to what an adopter installs."
        )
    return failures


def test_a_subchart_of_a_subchart_going_missing_reddens_the_vendoring_gate() -> None:
    """THE RED CASE, AND IT IS THE NESTED LEVEL BECAUSE THAT IS THE ONE NOTHING SAW.

    The loop this gate replaced walked the parent's own `dependencies:` and nothing
    else, so `yadgar/charts/platform/charts/nats/Chart.yaml` could go missing with
    every named assertion green. `helm install` resolves nothing, so the adopter
    meets it and nobody upstream does.
    """
    whole = expected_vendored_members()
    for missing in NESTED_SUBCHART_MEMBERS:
        failures = vendoring_failures([name for name in whole if name != missing])
        assert failures, f"`{missing}` went missing and the gate reported nothing"
        assert any(missing in failure for failure in failures), failures

    assert vendoring_failures(whole) == [], (
        "the gate refuses a complete member list, so it refuses everything and "
        "discriminates nothing"
    )


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


# PASS 1 flips every key named `enabled` in `chart/values.yaml`. Two today:
# `gateway.gateway.enabled` and `platform.enabled`. Asserted as an equality rather
# than a floor, because a key that stops being read is exactly the way this gate
# goes green over nothing.
ENABLED_KEYS_IN_THE_PARENTS_VALUES = 2

# PASS 2 flips every key named `create` in `example/values.yaml` — seven in
# `platform` and one in each of the three `-db` charts. The number is asserted for
# the same reason.
CREATE_KEYS_IN_THE_ADOPTER_VALUES = 10


def merged(base: dict, over: dict) -> dict:
    """`over` deep-merged onto `base`, the way helm merges two `-f` files."""
    result = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merged(result[key], value)
        else:
            result[key] = value
    return result


def flip_every(node, name: str, to: bool, path: str = "") -> list[str]:
    """Set every boolean key called `name` to `to`, in place. Returns the paths."""
    flipped: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else key
            if key == name and isinstance(value, bool):
                node[key] = to
                flipped.append(here)
            else:
                flipped += flip_every(value, name, to, here)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            flipped += flip_every(value, name, to, f"{path}[{index}]")
    return flipped


def test_every_crd_bearing_resource_can_be_switched_off(tmp_path: Path) -> None:
    """The property `ci-pr.yaml`'s `portability` job asserts, proved here too — TWICE.

    PASS 1 — `enabled`, over `chart/values.yaml`. That job reads the `enabled`
    keys out of THAT FILE and nothing else, so a parent whose own values file is
    empty fails it for a resource an adopter can in fact turn off. This is what
    says so locally, before CI does.

    PASS 2 — `create`, over `example/values.yaml`, holding `platform.enabled` TRUE.
    Pass 1 cannot reach a `create` toggle at all: `platform.enabled` false removes
    the whole subchart, so every object behind a `create` is already absent and a
    `create` toggle DEFAULTED TRUE would have no constructible red case — the gate
    would pass having never rendered the object it is meant to be able to switch
    off. Holding `platform.enabled` true and flipping only `create` is the render
    in which that toggle is the only thing standing between the chart and a
    CRD-bearing object.

    EVERY OTHER `enabled` IS FALSE IN PASS 2, and that is not a widening of "flip
    only `create`". `autoscaling.enabled` renders ScaledObjects and
    `gateway.gateway.enabled` renders the HTTPRoute; both are CRD-bearing and both
    are gated by `enabled` rather than by `create`, so leaving either on would make
    this pass fail for pass 1's subject. Pass 1's all-off file is therefore the BASE
    of pass 2 and the `create` flips are merged onto it. `platform.enabled` is the
    one `enabled` held true, which is the whole point of the pass.
    """
    # ── PASS 1 ───────────────────────────────────────────────────────────────
    off = yaml.safe_load((CHART / "values.yaml").read_text()) or {}
    flipped = flip_every(off, "enabled", False)
    assert len(flipped) == ENABLED_KEYS_IN_THE_PARENTS_VALUES, (
        f"`chart/values.yaml` declares {len(flipped)} `enabled` key(s) and this gate "
        f"expects {ENABLED_KEYS_IN_THE_PARENTS_VALUES}: {flipped}. The `portability` "
        f"job's all-off render reads that file and nothing else, so a key that left "
        f"it is a resource an adopter can no longer be shown to switch off. See the "
        f"comment in that file."
    )

    values = tmp_path / "all-off.yaml"
    values.write_text(yaml.safe_dump(off))
    survivors = crd_bearing(render(str(CHART), "-f", str(values)))
    assert survivors == [], f"these resources survived the all-off render: {survivors}"

    # ── PASS 2 ───────────────────────────────────────────────────────────────
    adopter = yaml.safe_load(ADOPTER_VALUES.read_text()) or {}
    created = flip_every(adopter, "create", False)
    assert len(created) == CREATE_KEYS_IN_THE_ADOPTER_VALUES, (
        f"`example/values.yaml` states {len(created)} `create` key(s) and this gate "
        f"expects {CREATE_KEYS_IN_THE_ADOPTER_VALUES}: {created}. A `create` toggle "
        f"that left the adopter values is one this pass no longer proves can be "
        f"switched off."
    )
    flip_every(adopter, "enabled", False)
    adopter = merged(off, adopter)
    adopter["platform"]["enabled"] = True

    held = tmp_path / "creates-off.yaml"
    held.write_text(yaml.safe_dump(adopter))
    survivors = crd_bearing(render(str(CHART), *API_VERSIONS, "-f", str(held)))
    assert survivors == [], (
        f"these resources survived the render with `platform.enabled` held true and "
        f"every `create` false: {survivors}. A CRD-bearing object behind no toggle an "
        f"adopter can reach is what D80 forbids."
    )


def test_a_create_toggle_that_cannot_be_switched_off_reddens_the_second_pass(tmp_path: Path) -> None:
    """PASS 2'S RED CASE: one `create` stays true and its objects survive.

    This is the shape a `create` toggle DEFAULTED TRUE would have — the case pass 1
    cannot construct, and the reason pass 2 exists. `internalCA.create` is the
    stand-in because its objects are `cert-manager.io/v1`, outside every built-in
    group, so `crd_bearing` sees them.
    """
    off = yaml.safe_load((CHART / "values.yaml").read_text()) or {}
    flip_every(off, "enabled", False)
    adopter = yaml.safe_load(ADOPTER_VALUES.read_text()) or {}
    flip_every(adopter, "create", False)
    flip_every(adopter, "enabled", False)
    adopter = merged(off, adopter)
    adopter["platform"]["enabled"] = True
    adopter["platform"]["internalCA"]["create"] = True

    values = tmp_path / "one-create-stuck-on.yaml"
    values.write_text(yaml.safe_dump(adopter))
    survivors = crd_bearing(render(str(CHART), *API_VERSIONS, "-f", str(values)))
    assert survivors != [], (
        "a `create` toggle was left true and the second pass found no CRD-bearing "
        "survivor, so it is passing over a render it never examined"
    )
    assert {kind for _, kind, _ in survivors} == {"Issuer", "Certificate"}, survivors


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


# ------------- 7. the platform layer: off by default, whole and refused when on


@pytest.fixture(scope="module")
def adopter() -> list[dict]:
    """R5 — the parent with `example/values.yaml`, the render the platform layer exists in.

    IT NEEDS `--api-versions` AND THAT IS NOT A CONVENIENCE. `platform` and the
    three `-db` charts carry render checks: `.Capabilities.APIVersions.Has` is
    false for every CRD-backed group with no live cluster, so a bare render of
    this file is refused by the first check it reaches, naming an operator. See
    `DECLARED_API_VERSIONS` for which groups are required and how that was
    measured.
    """
    return render(str(CHART), *API_VERSIONS, "-f", str(ADOPTER_VALUES))


def adopter_render(*arguments: str) -> list[dict]:
    return render(str(CHART), *API_VERSIONS, "-f", str(ADOPTER_VALUES), *arguments)


def overlay(destination: Path, body: str) -> Path:
    """One variant, written as a second `-f` on top of R5 rather than as a copy.

    A COPY WOULD DRIFT. Every red case below changes one thing about the adopter
    values, and a second full file is a second place the ten `create` toggles and
    the twelve leaves have to be kept in step with `example/values.yaml`.
    """
    destination.write_text(body)
    return destination


def names_of(documents: list[dict], kind: str) -> list[str]:
    return sorted(
        str((document.get("metadata") or {}).get("name"))
        for document in documents
        if document.get("kind") == kind
    )


def hook_annotations(document: dict) -> dict[str, str]:
    annotations = ((document.get("metadata") or {}).get("annotations")) or {}
    return {key: value for key, value in annotations.items() if "helm.sh/hook" in key}


# ── the object set, and the RBAC triples inside it ───────────────────────────


def test_the_adopter_values_render_the_whole_platform_layer(adopter: list[dict]) -> None:
    """THE ADOPTER-VALUES OBJECT-SET GATE, stated as an equality on both halves.

    The count AND the census: a total that agrees while two kinds swapped places
    is a gate that proved nothing, and a census with no total cannot say how many
    objects it walked.
    """
    assert dict(kinds(adopter)) == ADOPTER_EXPECTED
    assert len(adopter) == ADOPTER_OBJECTS, (
        f"the adopter-values render holds {len(adopter)} objects and this gate "
        f"expects {ADOPTER_OBJECTS}. A `platform` release that adds or drops an "
        f"object moves this number and NOT `EXPECTED` — update both literals in the "
        f"same commit as the pin, and say in the pull request which chart moved them."
    )


def test_an_object_added_to_the_platform_layer_reddens_the_object_set_gate(tmp_path: Path) -> None:
    """THE OBJECT-SET GATE'S RED CASE, and a values flip rather than an edited chart.

    A thirteenth entry in `certificates.leaves` is the constructible stand-in for
    an object entering the platform layer: the chart renders one Certificate per
    entry, so the render grows by exactly one and the equality has to fail.
    """
    values = overlay(
        tmp_path / "a-thirteenth-leaf.yaml",
        "platform:\n"
        "  certificates:\n"
        "    leaves:\n"
        "      thirteenth-tls:\n"
        "        commonName: thirteenth\n"
        "        clusterLocalNames: true\n"
        "        usages: [server auth, digital signature]\n"
        "        renewBefore: 786h\n",
    )
    documents = adopter_render("-f", str(values))
    assert len(documents) == ADOPTER_OBJECTS + 1, (
        "a thirteenth leaf did not add an object, so this red case is testing nothing"
    )
    assert dict(kinds(documents)) != ADOPTER_EXPECTED


def test_every_job_the_platform_layer_renders_is_an_install_time_hook(
    adopter: list[dict],
) -> None:
    """THE HOOK JOBS ARE COUNTED, AND EVERY ONE OF THEM IS A HOOK.

    SPLIT FROM THE TRIPLE-NAME GATE BELOW, WHICH IT USED TO MASK. Both assertions
    lived in one test with this count FIRST, so every perturbation that moved the
    Jobs and the triples together — which is every one a values file can build,
    since a probe Job and its identity render behind the same key — failed here and
    never reached the names. The name equality was falsifiable in principle and
    dead in fact. Two tests report both, and
    `test_the_rbac_triple_names_are_asserted_independently_of_the_job_count` is the
    constructed proof that the names are now reachable.

    Four hook Jobs: `bootstrap-secrets` and `admin-bootstrap-token` mint Secrets,
    `preflight` probes before the install and `envoy-gateway-probe` probes after it.
    """
    jobs = [document for document in adopter if document.get("kind") == "Job"]
    assert len(jobs) == HOOK_JOBS_AT_R5, (
        f"the adopter-values render holds {len(jobs)} Job(s) and this gate expects "
        f"{HOOK_JOBS_AT_R5}: {names_of(adopter, 'Job')}"
    )
    for job in jobs:
        assert hook_annotations(job), (
            f"the Job `{(job.get('metadata') or {}).get('name')}` carries no "
            f"`helm.sh/hook` annotation, so it is an ordinary object in the release "
            f"rather than an install-time step"
        )


def test_each_bootstrap_job_pair_shares_one_rbac_triple_and_the_preflight_holds_its_own(
    adopter: list[dict],
) -> None:
    """THE TRIPLES ARE COUNTED, AND THE COUNT IS NOT ONE PER JOB.

    Four hook Jobs, three triples. `preflight` holds its own — `create`, `get` and
    `delete` on the objects it submits — and so does `envoy-gateway-probe`, the
    second preflight Job, which submits objects of its own. `bootstrap-secrets`
    holds one that BOTH bootstrap Jobs use, because `bootstrap-secrets` and
    `admin-bootstrap-token` mint Secrets with the same permission and a second
    identity would be that permission held twice.

    ASSERTED AS THE NAMES AND NOT ONLY THE NUMBER. Two Roles named for one Job and
    none for the other is the same count and a different estate — and THAT is the
    case this test now reaches, because the Job count that used to stand in front
    of it is a test of its own above.
    """
    for kind in ("Role", "RoleBinding"):
        assert names_of(adopter, kind) == RBAC_TRIPLE_NAMES_AT_R5, (
            f"the {kind}s in the adopter-values render are "
            f"{names_of(adopter, kind)} and this gate expects "
            f"{RBAC_TRIPLE_NAMES_AT_R5}. A triple per hook Job would be four; one "
            f"triple in total would be one. It is neither."
        )
    for name in RBAC_TRIPLE_NAMES_AT_R5:
        assert name in names_of(adopter, "ServiceAccount"), (
            f"`{name}` holds a Role and a RoleBinding and no ServiceAccount, so the "
            f"binding names an identity nothing renders"
        )


def test_dropping_the_second_preflight_probe_reddens_the_hook_job_and_triple_gates(
    tmp_path: Path,
) -> None:
    """THE RED CASE FOR `HOOK_JOBS_AT_R5` AND `RBAC_TRIPLE_NAMES_AT_R5`.

    UNTIL THIS EXISTED THOSE TWO CONSTANTS HAD NO RED CASE AT ALL, so their only
    home was the gate that reads them and the gate was its own falsifier.
    `ADOPTER_OBJECTS` has had one since it was written —
    `test_an_object_added_to_the_platform_layer_reddens_the_object_set_gate` — and
    this is its counterpart for the hook Jobs and the RBAC triples.

    A VALUES FLIP, NOT AN EDITED CHART, and the same idiom as the object-set red
    case above. `platform.preflight.probes.envoyGateway: false` is honoured
    unconditionally — `platform`'s own `values.yaml` states that an explicit `false`
    on a probe always is, because losing a diagnostic is a choice an adopter is
    entitled to make. It drops the post-install probe Job and the whole identity
    that Job runs as, so the render loses exactly four objects: a Job, a Role, a
    RoleBinding and a ServiceAccount.

    THE POSITIVE FORM IS ASSERTED BEFORE THE NEGATIVE ONE. `!=
    RBAC_TRIPLE_NAMES_AT_R5` on its own is satisfied by any wrong list, so it would
    still pass over a constant reverted to some other wrong value. The equality
    against `RBAC_TRIPLE_NAMES_WITHOUT_THE_SECOND_PROBE` names the one list this
    flip really produces, which is what makes the case non-vacuous against a wrong
    constant rather than against one particular wrong constant.
    """
    values = overlay(
        tmp_path / "no-second-probe.yaml",
        "platform:\n  preflight:\n    probes:\n      envoyGateway: false\n",
    )
    documents = adopter_render("-f", str(values))

    jobs = names_of(documents, "Job")
    assert len(jobs) == HOOK_JOBS_AT_R5 - 1, (
        f"turning off `platform.preflight.probes.envoyGateway` left "
        f"{len(jobs)} Job(s) — {jobs} — where {HOOK_JOBS_AT_R5 - 1} was expected. "
        f"The flip did not drop the second preflight Job, so this red case is "
        f"testing nothing and `HOOK_JOBS_AT_R5` is back to having no falsifier."
    )

    for kind in ("Role", "RoleBinding"):
        assert names_of(documents, kind) == RBAC_TRIPLE_NAMES_WITHOUT_THE_SECOND_PROBE, (
            f"the {kind}s under the flip are {names_of(documents, kind)} and this "
            f"red case expects {RBAC_TRIPLE_NAMES_WITHOUT_THE_SECOND_PROBE}"
        )
        assert names_of(documents, kind) != RBAC_TRIPLE_NAMES_AT_R5, (
            f"the {kind} names did not move, so "
            f"`test_each_bootstrap_job_pair_shares_one_rbac_triple_and_the_preflight"
            f"_holds_its_own` would stay green over a render missing a whole identity"
        )

    assert len(documents) == ADOPTER_OBJECTS - OBJECTS_PER_PROBE_JOB, (
        f"the flip left {len(documents)} objects where "
        f"{ADOPTER_OBJECTS - OBJECTS_PER_PROBE_JOB} was expected. One probe Job "
        f"carries one Job, one Role, one RoleBinding and one ServiceAccount."
    )
    assert dict(kinds(documents)) != ADOPTER_EXPECTED


def test_the_rbac_triple_names_are_asserted_independently_of_the_job_count(
    tmp_path: Path,
) -> None:
    """THE PROOF THAT THE SPLIT ABOVE WAS NOT COSMETIC: names wrong, count right.

    A REORDER WOULD HAVE MOVED THE MASK RATHER THAN REMOVED IT — with the names
    first, the flip in the red case above would be caught by the names and the Job
    count would become the dead assertion instead. What settles it is an input on
    which the two gates disagree, and there is one: the triples are NAMED from
    `platform.preflight.serviceAccountName`, so renaming that identity moves every
    Role, RoleBinding and ServiceAccount name and renders exactly as many objects
    of exactly as many kinds.

    MEASURED 2026-09-24 on helm 3.18.4 and 4.3.0: 81 objects, `ADOPTER_EXPECTED`
    unchanged, four Jobs — and the triples become
    `['bootstrap-secrets', 'envoy-gateway-probe', 'renamed-preflight']`. So the
    object-set gate, the census and the Job-count gate are ALL green over a render
    in which a hook Job's identity is not the one the estate reviewed, and the name
    equality is the only assertion in this suite that can see it. That is what the
    name equality is FOR, and while it sat behind the Job count nothing could
    reach it.
    """
    values = overlay(
        tmp_path / "a-renamed-preflight-identity.yaml",
        "platform:\n  preflight:\n    serviceAccountName: renamed-preflight\n",
    )
    documents = adopter_render("-f", str(values))

    # Everything the other gates read is UNMOVED, which is the whole point.
    assert dict(kinds(documents)) == ADOPTER_EXPECTED, (
        "the rename moved a kind count, so this input no longer isolates the names"
    )
    assert len(documents) == ADOPTER_OBJECTS
    assert len(names_of(documents, "Job")) == HOOK_JOBS_AT_R5, (
        "the rename moved the Job count, so the count gate would fire on it and "
        "this proof shows nothing about the names being reachable"
    )

    # ...and the names are what moved.
    for kind in ("Role", "RoleBinding"):
        assert names_of(documents, kind) != RBAC_TRIPLE_NAMES_AT_R5, (
            f"`platform.preflight.serviceAccountName` was overridden and the {kind} "
            f"names did not follow it, so the triples are not named from that key "
            f"and this proof is testing nothing"
        )
        assert "renamed-preflight" in names_of(documents, kind)


# ── the renewal ladder, lifted from `yadgarhq/platform` to the whole estate ──


def certificates(documents: list[dict]) -> list[dict]:
    return [document for document in documents if document.get("kind") == "Certificate"]


def rungs(documents: list[dict]) -> dict[str, list[str]]:
    """Ladder value -> every certificate holding it. PURE.

    SCOPED TO THE CERTIFICATES THAT ARE NOT `isCA`, which is the difference between
    twelve objects and eleven values rather than an omission.
    """
    index: dict[str, list[str]] = {}
    for document in certificates(documents):
        specification = document.get("spec") or {}
        if specification.get("isCA"):
            continue
        name = str((document.get("metadata") or {}).get("name"))
        index.setdefault(str(specification.get("renewBefore")), []).append(name)
    return index


def ladder_failures(
    documents: list[dict], expected_objects: int, expected_values: set[str]
) -> list[str]:
    """Every way this render disagrees with the ladder, each naming both numbers. PURE."""
    failures = []

    found = certificates(documents)
    if len(found) != expected_objects:
        names = sorted(str((document.get("metadata") or {}).get("name")) for document in found)
        failures.append(
            f"expected {expected_objects} Certificate objects, found {len(found)}: {names}"
        )

    held = rungs(documents)
    if set(held) != expected_values:
        failures.append(
            f"expected {len(expected_values)} distinct renewBefore values, "
            f"found {len(held)}: expected {sorted(expected_values)}, "
            f"found {sorted(held)}"
        )
    for value, holders in sorted(held.items()):
        if len(holders) > 1:
            failures.append(
                f"renewBefore {value} is held by {len(holders)} certificates, "
                f"{', '.join(sorted(holders))} — the ladder needs one service per "
                f"renewal instant, so every value is distinct"
            )

    return failures


def test_the_renewal_ladder_holds_across_the_whole_estate(adopter: list[dict]) -> None:
    """THE LADDER REACHES THE PARENT, and this is the render where it is whole.

    `yadgarhq/platform`'s own suite asserts it over that chart alone. Here the
    same invariant is read over every Certificate an adopter's install produces,
    which is what catches a SECOND source of Certificates entering the estate from
    some other chart and landing on a rung already taken.
    """
    failures = ladder_failures(adopter, CERTIFICATES_AT_R5, LADDER)
    assert failures == [], "\n".join(failures)


def test_a_thirteenth_certificate_reddens_the_ladder_gate(tmp_path: Path) -> None:
    """THE LADDER GATE'S RED CASE: a thirteenth leaf, and the equality names both numbers."""
    values = overlay(
        tmp_path / "a-thirteenth-leaf.yaml",
        "platform:\n"
        "  certificates:\n"
        "    leaves:\n"
        "      thirteenth-tls:\n"
        "        commonName: thirteenth\n"
        "        clusterLocalNames: true\n"
        "        usages: [server auth, digital signature]\n"
        "        renewBefore: 786h\n",
    )
    failures = ladder_failures(
        adopter_render("-f", str(values)), CERTIFICATES_AT_R5, LADDER
    )
    assert failures, "a thirteenth Certificate did not redden the ladder gate"
    assert "expected 12 Certificate objects, found 13" in "\n".join(failures), failures


def test_two_leaves_sharing_a_rung_redden_the_ladder_gate(tmp_path: Path) -> None:
    """THE OTHER HALF OF THE INVARIANT, which a count alone cannot see.

    Twelve objects holding eleven distinct values is what the gate asserts. Two
    leaves moved onto one rung keeps the object count at twelve and collapses the
    ladder, and the pairwise clause is the only thing that reports it.
    """
    values = overlay(
        tmp_path / "a-shared-rung.yaml",
        "platform:\n  certificates:\n    leaves:\n      task-tls:\n        renewBefore: 726h\n",
    )
    failures = ladder_failures(
        adopter_render("-f", str(values)), CERTIFICATES_AT_R5, LADDER
    )
    assert failures, "two leaves on one rung did not redden the ladder gate"
    assert any("is held by 2 certificates" in failure for failure in failures), failures


# ── the probe/toggle agreement, at the scope where both halves are visible ───


def probes_declared(documents: list[dict]) -> list[str]:
    """The operators the rendered `preflight` Job actually probes.

    READ OUT OF THE RENDERED SCRIPT rather than out of the values file, because
    what the values ASK for and what the template RESOLVES are the two halves this
    gate exists to compare.

    THE `preflight` FILTER IS DELIBERATE, AND IT IS PERMANENT. A later `platform`
    release renders a SECOND probe Job — `envoy-gateway-probe`, post-install, with a
    `PROBES=` line this regex matches just as happily. Its one probe pairs
    `probes.envoyGateway` with `gatewayListener.create`, and both of those are
    `platform`'s own keys, so `platform`'s suite is where that pair is asserted. What
    the parent adds is the pairs NO chart can see alone, and every one of those is
    declared by the pre-install `preflight` Job. So this reads that Job and no other.
    """
    jobs = [
        document
        for document in documents
        if document.get("kind") == "Job"
        and (document.get("metadata") or {}).get("name") == "preflight"
    ]
    if not jobs:
        return []
    assert len(jobs) == 1, f"expected one `preflight` Job, found {len(jobs)}"
    container = jobs[0]["spec"]["template"]["spec"]["containers"][0]
    found = PROBE_LIST.search("\n".join(container["args"]))
    assert found, "the rendered preflight script declares no `PROBES=` line"
    return found.group("probes").split()


AUTOSCALING_MODULES = ("gateway", "iam", "iam-db", "project", "project-db", "task", "task-db")
DATABASE_MODULES = ("iam-db", "project-db", "task-db")


# THE OFF END OF EACH PAIR. It moves BOTH members, which is what makes it the
# green case: the toggle goes false and the probe goes with it. `certManager`'s
# probe follows on its own — its tie reads the three `create` toggles — while
# `keda` and `mariadb` are stated explicitly in `example/values.yaml`, because no
# tie inside `platform` can see a sibling chart's key, so the off end has to state
# them false. Moving ONE member is the red case, and it is two tests below.
PAIR_OFF_END = {
    "certManager": "platform:\n  internalCA:\n    create: false\n"
    "  certificates:\n    create: false\n  edgeTLS:\n    create: false\n",
    "keda": "platform:\n  preflight:\n    probes:\n      keda: false\n"
    + "".join(
        f"{module}:\n  autoscaling:\n    enabled: false\n"
        for module in AUTOSCALING_MODULES
    ),
    "mariadb": "platform:\n  preflight:\n    probes:\n      mariadb: false\n"
    + "".join(f"{module}:\n  database:\n    create: false\n" for module in DATABASE_MODULES),
}


def pair_failures(probe: str, declared: list[str], objects: int, expected: bool) -> list[str]:
    """ONE END of one pair: the probe and the objects it probes must agree. PURE.

    PURE AND RENDER-TAKING SO THE RED CASES USE THE SAME PREDICATE THE GATE DOES.
    A red case that asserts on the raw render instead would prove the render moved
    and say nothing about whether the gate can see it.

    TWO CLAUSES, AND THE SECOND IS NOT REDUNDANT. The first refuses a probe and an
    object set that disagree. The second refuses an END that is not the end it was
    asked for — without it, a variant that quietly stopped changing anything would
    agree with itself and the pair would be examined twice at one end.
    """
    operator, kind, toggle = PROBE_OPERATOR[probe], PROBE_KIND[probe], PROBE_TOGGLE[probe]
    declares = operator in declared
    failures = []
    if declares != (objects > 0):
        failures.append(
            f"`platform.preflight.probes.{probe}` {'is' if declares else 'is NOT'} "
            f"declared in the rendered preflight script and `{toggle}` renders "
            f"{objects} {kind}(s) in the same render. The probe and the toggle that "
            f"renders what it probes disagree; the render declares {declared}."
        )
    if declares != expected:
        failures.append(
            f"this end of the pair was built with `{toggle}` "
            f"{'on' if expected else 'off'} and `platform.preflight.probes.{probe}` "
            f"{'is' if declares else 'is NOT'} declared, so it is not the end it was "
            f"meant to be and examines nothing."
        )
    return failures


def agreement_failures(tmp_path: Path) -> list[str]:
    """Every pair, read at BOTH ends, each failure naming both keys.

    A PAIR IS NOT ONE OBSERVATION. A probe declared while the objects it probes are
    present is a green case a tie hardcoded true would also pass. So each pair is
    read with the toggle ON, where the probe must be declared and its objects must
    be there, and with the toggle OFF, where neither may be.
    """
    failures: list[str] = []

    on = adopter_render()
    declared_on = probes_declared(on)
    failures += unpaired_probes(declared_on)

    for probe, body in sorted(PAIR_OFF_END.items()):
        kind = PROBE_KIND[probe]
        failures += pair_failures(
            probe,
            declared_on,
            len([document for document in on if document.get("kind") == kind]),
            expected=True,
        )
        off = adopter_render("-f", str(overlay(tmp_path / f"{probe}-off.yaml", body)))
        failures += pair_failures(
            probe,
            probes_declared(off),
            len([document for document in off if document.get("kind") == kind]),
            expected=False,
        )

    return failures


def unpaired_probes(declared: list[str]) -> list[str]:
    """The denominator, READ OFF THE RENDER rather than off this file's own table. PURE.

    COUNTING `PAIR_OFF_END`'S ITERATIONS WOULD BE TAUTOLOGICAL, and the first draft
    of this gate did exactly that. `pairs` was `len(PAIR_OFF_END)` by construction,
    so the comparison could only disagree with a constant somebody edited in the
    same file — it said nothing about the render. The number that matters is how
    many probes the RENDER declares, and a probe the estate gained with no pair
    here is the thing this has to catch.

    WHAT IT HAS TO CATCH IS A PRE-INSTALL PROBE ADDED UPSTREAM AND PAIRED NOWHERE.
    `platform.preflight.probes` in `platform`'s `_preflight.tpl` resolves a list that
    can grow, and a fourth operator appended to it lands in the `preflight` Job's
    `PROBES=` line with no entry in `PAIR_OFF_END` naming it. That is the red this
    produces, and it names the operator rather than leaving a pair nobody paired.

    IT IS NOT `probes.envoyGateway`. That key enables a SEPARATE post-install Job,
    which `probes_declared` does not read, so the pin that brought it left this
    green — measured at 0.1.7 on 2026-09-24. See `AGREEMENT_PAIRS_AT_R5`.
    """
    paired = {PROBE_OPERATOR[probe] for probe in PAIR_OFF_END}
    if len(paired) != AGREEMENT_PAIRS_AT_R5:
        return [
            f"this file pairs {len(paired)} probe(s) — {sorted(paired)} — and "
            f"`AGREEMENT_PAIRS_AT_R5` is {AGREEMENT_PAIRS_AT_R5}"
        ]
    return [
        f"the rendered preflight script declares `{operator}` and no entry in "
        f"`PAIR_OFF_END` pairs it with the toggle that renders what it probes. The "
        f"render declares {sorted(declared)}; this file pairs {sorted(paired)}."
        for operator in sorted(set(declared) - paired)
    ]


def test_a_probe_the_estate_gained_with_no_pair_reddens_the_denominator() -> None:
    """THE DENOMINATOR'S RED CASE, and it is pure because nothing here can render one.

    `"envoy-gateway"` IS A SYNTHETIC STAND-IN AND NOT A PREDICTION. It stands for a
    fourth operator appended to `platform`'s PRE-INSTALL probe set, which is the
    change this gate exists to catch. The real `envoy-gateway` never reaches the
    `preflight` Job's list — it enables a separate post-install Job — so no
    `platform` pin turns this assertion into one that examines nothing, and the name
    stays available as a fake. No values file can make the render declare a fourth
    operator today, which is exactly why the predicate takes the list rather than
    the render.
    """
    paired = sorted(PROBE_OPERATOR[probe] for probe in PAIR_OFF_END)
    assert unpaired_probes(paired) == [], (
        "the denominator refuses the probes this file does pair, so it refuses "
        "everything and discriminates nothing"
    )
    failures = unpaired_probes(paired + ["envoy-gateway"])
    assert failures, "a probe with no pair was not caught"
    assert "envoy-gateway" in failures[0], failures


def test_every_probe_agrees_with_the_toggle_that_renders_what_it_probes(tmp_path: Path) -> None:
    """THREE PAIRS, and three is the permanent number — `AGREEMENT_PAIRS_AT_R5` says why."""
    failures = agreement_failures(tmp_path)
    assert failures == [], "\n".join(failures)


def test_a_probe_declared_with_nothing_to_probe_reddens_the_agreement_gate(tmp_path: Path) -> None:
    """RED CASE, `keda`: flip one member of the pair without the other.

    `probes.keda` stays true — `example/values.yaml` states it explicitly, because
    `platform` renders no ScaledObject and cannot infer it — while every module's
    `autoscaling.enabled` goes false. The probe then waits for an operator this
    install gives it nothing to reconcile, and the failure names both keys.
    """
    body = "".join(
        f"{module}:\n  autoscaling:\n    enabled: false\n" for module in AUTOSCALING_MODULES
    )
    documents = adopter_render("-f", str(overlay(tmp_path / "no-autoscaling.yaml", body)))
    failures = pair_failures(
        "keda",
        probes_declared(documents),
        len([d for d in documents if d.get("kind") == "ScaledObject"]),
        expected=False,
    )
    assert failures, "a probe left declared over an empty object set was not caught"
    assert "probes.keda" in failures[0] and "autoscaling.enabled" in failures[0], failures


def test_an_object_with_no_probe_reddens_the_agreement_gate(tmp_path: Path) -> None:
    """RED CASE, `certManager`: the other direction of the same pair.

    An explicit `false` is always honoured — losing a diagnostic is a choice an
    adopter is entitled to make — so this is the constructible way to have the
    objects without the probe. The gate must see the twelve Certificates and the
    absent probe and name both.
    """
    documents = adopter_render(
        "-f",
        str(
            overlay(
                tmp_path / "cert-manager-probe-off.yaml",
                "platform:\n  preflight:\n    probes:\n      certManager: false\n",
            )
        ),
    )
    assert len(certificates(documents)) == CERTIFICATES_AT_R5
    failures = pair_failures(
        "certManager", probes_declared(documents), CERTIFICATES_AT_R5, expected=True
    )
    assert failures, "an object set left with no probe was not caught"
    assert "probes.certManager" in failures[0] and "internalCA.create" in failures[0], failures


# ── the parent's own refusals, each with its own constructed red case ────────


def refusal(tmp_path: Path, name: str, body: str) -> str:
    """Render with an overlay that must be REFUSED, and return what helm said.

    ASSERTED ON THE EXIT CODE AND THE MESSAGE, NEVER ON THE OBJECTS. A `fail`
    aborts the WHOLE render — the parent's and every subchart's — with exit 1 and
    ZERO objects, so "no object of kind X" is true of a refusal and of a render
    that simply did not ask for X. The message is the only thing that
    discriminates.

    THE OVERLAY IS APPLIED TO THE CHART'S OWN DEFAULTS, not to the adopter values.
    Every refusal below needs a `platform.*.create` set EXPLICITLY, because all of
    them default false and a red case written at the defaults reaches no refusal
    at all.
    """
    values = overlay(tmp_path / f"{name}.yaml", body)
    result = helm(
        "template",
        "yadgar",
        str(CHART),
        *API_VERSIONS,
        "-f",
        str(values),
    )
    assert result.returncode != 0, (
        f"`{name}` rendered exit 0. The parent was supposed to refuse it.\n"
        f"{result.stdout[:2000]}"
    )
    return result.stderr


def test_the_parent_refuses_an_empty_admin_token_when_it_installs_the_platform_layer(
    tmp_path: Path,
) -> None:
    """RULING 5. Red case: a `platform.*.create` true and the token left at its default."""
    message = refusal(
        tmp_path,
        "empty-admin-token",
        "platform:\n  enabled: true\n  internalCA:\n    create: true\n",
    )
    assert "gateway.adminBootstrap.tokenSecret is empty" in message, message
    assert "platform.internalCA.create" in message, message


def test_the_parent_refuses_a_minted_name_the_gateway_does_not_mount(tmp_path: Path) -> None:
    """The Job mints one name and the gateway mounts another; the refusal names both."""
    message = refusal(
        tmp_path,
        "two-token-names",
        "platform:\n"
        "  enabled: true\n"
        "  bootstrap:\n"
        "    create: true\n"
        "    adminToken:\n"
        "      secretName: minted-here\n"
        "gateway:\n"
        "  adminBootstrap:\n"
        "    tokenSecret: mounted-there\n",
    )
    assert "platform.bootstrap.adminToken.secretName" in message, message
    assert "gateway.adminBootstrap.tokenSecret" in message, message
    assert '"minted-here"' in message and '"mounted-there"' in message, message


def test_the_parent_refuses_a_create_toggle_with_the_dependency_left_off(tmp_path: Path) -> None:
    """THE TRAP THE DEPENDENCY `condition` OPENS, refused by name.

    A values file stating `internalCA.create: true` and leaving `platform.enabled`
    alone reads as a fully configured platform layer and renders NONE of it —
    measured, the same object set as the bare default, exit 0, no warning. The
    refusal names both keys because the file that trips it names only one.
    """
    message = refusal(
        tmp_path,
        "create-without-enabled",
        "platform:\n"
        "  internalCA:\n"
        "    create: true\n"
        "gateway:\n"
        "  adminBootstrap:\n"
        "    tokenSecret: admin-bootstrap-token\n",
    )
    assert "platform.enabled is not true" in message, message
    assert "platform.internalCA.create" in message, message


def test_the_refusals_are_unreachable_at_the_defaults(tmp_path: Path) -> None:
    """THE GUARD'S OWN GREEN CASE, and it is the property the three refusals rest on.

    ADR-0777: the refusals are guarded on an ADOPTER-SET condition — any
    `platform.*.create` being true — precisely so the bare default render reaches
    none of them. `.Release.IsInstall` cannot do this: it is TRUE for `helm
    template`, so it separates nothing.

    ASSERTED OVER THE DEPENDENCY-STRIPPED TREE AS WELL, which is where
    `.Values.platform` is ABSENT rather than merely all-false. That is the render
    the nil-safe chain in `_validate.tpl` exists for, and the one that would raise
    if somebody replaced it with a direct `.Values.platform.bootstrap.create`.
    """
    assert dict(kinds(render(str(CHART)))) == EXPECTED
    assert render(str(chart_without_its_dependencies(tmp_path))) == []


def test_the_refusals_are_nil_safe_with_every_subchart_removed(tmp_path: Path) -> None:
    """THE CASE THE `default` CHAIN IN `_validate.tpl` EXISTS FOR, run rather than cited.

    With `dependencies` stripped there are no subchart defaults to coalesce, so
    `.Values.gateway.adminBootstrap` and `.Values.platform.bootstrap.adminToken` do
    not exist at all. A direct `.Values.platform.bootstrap.create` RAISES there
    rather than evaluating false, and the test it reddens is three files from the
    change that broke it — which is why ADR-0777 makes nil-safety a requirement
    rather than a style.

    THE OTHER NIL-SAFE TESTS CANNOT REACH IT. They render the stripped tree at its
    DEFAULTS, where every `create` is false and the guard closes before a single
    deep read happens. This one opens the guard over that tree, which is the only
    way every level of the chain is evaluated with nothing under it.

    THREE OVERLAYS, ONE PER LEVEL THAT CAN BE ABSENT: no `bootstrap` block at all;
    `bootstrap` present with no `adminToken`; and both present, where the absent
    level is `gateway.adminBootstrap`. Each reaches a different `default` in the
    chain, and one overlay alone supplies the very levels the others leave out.
    """
    copy = chart_without_its_dependencies(tmp_path)
    overlays = {
        "no-bootstrap-block": "platform:\n  enabled: true\n  internalCA:\n    create: true\n",
        "bootstrap-without-its-token": "platform:\n  enabled: true\n"
        "  internalCA:\n    create: true\n  bootstrap:\n    create: true\n",
        "bootstrap-with-a-token": "platform:\n  enabled: true\n"
        "  internalCA:\n    create: true\n  bootstrap:\n    create: true\n"
        "    adminToken:\n      secretName: admin-bootstrap-token\n",
    }
    for name, body in sorted(overlays.items()):
        result = helm(
            "template", "yadgar", str(copy), "-f", str(overlay(tmp_path / f"{name}.yaml", body))
        )
        assert result.returncode != 0, (
            f"`{name}` opened the guard over a tree with no subchart values and "
            f"refused nothing"
        )
        for raise_text in ("nil pointer", "can't evaluate field", "error calling"):
            assert raise_text not in result.stderr, (
                f"`{name}` made the guard RAISE instead of refuse: {result.stderr}"
            )
        assert "gateway.adminBootstrap.tokenSecret is empty" in result.stderr, result.stderr


def test_breaking_the_guard_makes_the_default_render_refuse(tmp_path: Path) -> None:
    """THE GUARD'S RED CASE: remove the guard and the bare default render goes red.

    This is the measurement ADR-0777 records as the reason the guard exists, run
    rather than cited. An unconditional refusal in the parent fires on the render
    that five other assertions in this file and the shared `helm-lint` pre-commit
    hook all depend on.
    """
    copy = tmp_path / "chart"
    shutil.copytree(CHART, copy)
    partial = copy / "templates" / "_validate.tpl"
    text = partial.read_text()
    needle = "{{- if $creating -}}"
    assert needle in text, "the guard moved; this red case is now testing nothing"
    partial.write_text(text.replace(needle, "{{- if true -}}", 1))

    result = helm("template", "yadgar", str(copy))
    assert result.returncode != 0, (
        "the guard was removed and the bare default render still succeeded, so the "
        "guard is not what is keeping the refusals off that render"
    )
    assert "gateway.adminBootstrap.tokenSecret is empty" in result.stderr, result.stderr
