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
# 0.1.8 declared, which is the pin `chart/Chart.yaml` carries today: 32 objects, the
# same six kinds, unchanged. It first read that way at 0.1.7. ADR-0777 makes the
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
#   keda.sh/v1alpha1                required since 2026-09-26 — see below
#
# `keda.sh/v1alpha1` JOINED THE TUPLE ON 2026-09-26, AND THE LINE IT REPLACED
# FORECAST EXACTLY THIS. That line said the group was "NOT required today" because
# "no module chart declares a KEDA render check yet", and that "this tuple gains
# the group in the same change that makes it required". The module-chart sweep it
# named has now landed: ALL SEVEN module charts that render a `ScaledObject`
# declare the check today — `gateway` 0.9.52, `iam` 0.8.44, `iam-db` 0.7.45,
# `project` 0.1.19, `project-db` 0.3.9, `task` 0.5.30 and `task-db` 0.6.33, each in
# its own `templates/render-checks.yaml`, each naming this exact group.
#
# MEASURED 2026-09-26 on helm 4.3.0 against the nine pins in `chart/Chart.yaml`
# today. Without the flag, `helm template yadgar chart -f example/values.yaml`
# exits 1 at `yadgar/charts/task/templates/render-checks.yaml:36:4` — "task: this
# render needs the API keda.sh/v1alpha1, which KEDA provides, and the target does
# not have it. autoscaling.enabled is true, and that is what asked for it." With
# the flag the same render exits 0. `example/values.yaml` sets
# `autoscaling.enabled` true in all seven modules, which is what reaches the check.
#
# THIS MOVES NO OBJECT COUNT, AND THAT IS MEASURED RATHER THAN ASSUMED. A render
# check only ever calls `fail`; it emits nothing. No chart in the package gates an
# object on `.Capabilities.APIVersions` — `grep -n Capabilities` over every
# subchart's templates returns the four `require-api` partials and their prose and
# nothing else — so handing helm one more group cannot add or drop a document.
DECLARED_API_VERSIONS = (
    "cert-manager.io/v1",
    "gateway.envoyproxy.io/v1alpha1",
    "k8s.mariadb.com/v1alpha1",
    "keda.sh/v1alpha1",
)
API_VERSIONS = tuple(
    part for group in DECLARED_API_VERSIONS for part in ("--api-versions", group)
)

# WHAT THE WHOLE ESTATE PLUS ITS PLATFORM LAYER IS, re-measured 2026-09-24 on helm
# 3.18.4 and 4.3.0 against the nine pins in `chart/Chart.yaml` today, `platform`
# at 0.1.8. A LITERAL for the same reason `EXPECTED` is one.
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
# Job, and it landed in `platform` 0.1.7. MEASURED at that pin on 2026-09-24:
# `RBAC_TRIPLE_NAMES_AT_R5` gained `envoy-gateway-probe` and `HOOK_JOBS_AT_R5` went
# to 4, alongside `ADOPTER_OBJECTS` 77 → 81. RE-MEASURED THE SAME DAY at 0.1.8,
# which is the pin `chart/Chart.yaml` declares today: all three still read that way.
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
# are literals. MEASURED 2026-09-24 at `platform` 0.1.7, and re-measured the same
# day on helm 3.18.4 and 4.3.0 at 0.1.8, the pin `chart/Chart.yaml` declares today.
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
# and `probes_declared` below reads the `preflight` Job alone. At 0.1.8, the pin
# `chart/Chart.yaml` declares, re-measured 2026-09-24: the render declares
# `{preflight: [cert-manager, keda, mariadb-operator], envoy-gateway-probe:
# [envoy-gateway]}` and `unpaired_probes` returns []. `ADOPTER_OBJECTS`,
# `HOOK_JOBS_AT_R5` and `RBAC_TRIPLE_NAMES_AT_R5` moved at 0.1.7, where this was
# first measured. This one did not move at either pin.
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


# WHAT THE WALK BELOW MUST FIND, and it is TRANSITIVE. Nine first-level members,
# one per dependency `chart/Chart.yaml` declares, plus the NINE below that sit
# BENEATH `platform` — six of them one level down and three of them two.
#
# MEASURED 2026-09-26 on helm 4.3.0 over `helm package chart -u` against the nine
# pins in `chart/Chart.yaml` today, `platform` at 0.1.11:
#
#   tar tzf yadgar-0.1.0.tgz | grep -cE '^yadgar/charts/.*/Chart\.yaml$'   → 18
#
# EIGHT OF THESE NINE ARRIVED WITH `platform` 0.1.9, AND THE GATE WENT RED BECAUSE
# IT WAS DOING ITS JOB. 0.1.9 declares the five operators ADR-0787 rules on —
# cert-manager, KEDA, mariadb-operator, Envoy Gateway (`gateway-helm`) and Argo CD
# — as dependencies of its own, and three of those five carry a subchart apiece:
# `argo-cd` pulls `redis-ha`, `gateway-helm` pulls `crds`, and `mariadb-operator`
# pulls `mariadb-operator-crds`. Five plus three is the eight.
#
# HELM PACKAGES A DECLARED DEPENDENCY WHATEVER ITS `condition:` SAYS, and that one
# fact is the whole of why the number moved. Each operator is declared
# `condition: operators.<op>.create,operators.create`, and every one of those keys
# is FALSE by default — but a `condition:` governs what RENDERS, never what is
# PACKAGED. So the tarball an adopter downloads grew by eight charts while the
# objects an adopter installs did not move at all: `ADOPTER_EXPECTED` and
# `ADOPTER_OBJECTS` are unchanged at 0.1.11, and the operators are off.
#
# SO THIS IS DOWNLOAD WEIGHT RATHER THAN INSTALLED OBJECTS, AND THE OPERATOR TOOK
# THE TRADE ON 2026-09-26. Asked whether to accept the larger adopter download or
# stop vendoring the operators, he answered: "bigger download is fine". The list
# moved from ten to eighteen for that reason and for no other — it is NOT a gate
# loosened to get a suite green. A subchart that arrives or leaves without this
# list moving is still refused, which is the property the gate exists for.
#
# THE NESTED ONES ARE WHY THIS COUNTS RATHER THAN ONLY CHECKING NAMES. A loop over
# the parent's own `dependencies:` cannot see one level down, let alone two, so a
# subchart of a subchart could go missing with every named assertion still green —
# and `helm install` resolves nothing, so the adopter meets it and nobody else does.
NESTED_SUBCHART_MEMBERS = [
    "yadgar/charts/platform/charts/nats/Chart.yaml",
    "yadgar/charts/platform/charts/argo-cd/Chart.yaml",
    "yadgar/charts/platform/charts/argo-cd/charts/redis-ha/Chart.yaml",
    "yadgar/charts/platform/charts/cert-manager/Chart.yaml",
    "yadgar/charts/platform/charts/gateway-helm/Chart.yaml",
    "yadgar/charts/platform/charts/gateway-helm/charts/crds/Chart.yaml",
    "yadgar/charts/platform/charts/keda/Chart.yaml",
    "yadgar/charts/platform/charts/mariadb-operator/Chart.yaml",
    "yadgar/charts/platform/charts/mariadb-operator/charts/mariadb-operator-crds/Chart.yaml",
]


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

# PASS 2 flips every key named `create` in `example/values.yaml` — eight in
# `platform` (`bootstrap.iamKeys.create` joined the other seven at step 3c) and
# one in each of the three `-db` charts. The number is asserted for the same
# reason.
CREATE_KEYS_IN_THE_ADOPTER_VALUES = 11


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
        f"that left the adopter values is one this pass no longer flips. NOT ALL of "
        f"them are then PROVED switchable by the render below: some render no "
        f"CRD-bearing object at all — `bootstrap.iamKeys.create` among them — and "
        f"for those this count is the whole of the coverage. No number is stated "
        f"here beyond the one asserted above, because how many of the eleven render "
        f"a CRD-bearing object is a property of the pinned subcharts and moves "
        f"whenever they do."
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
    """Every `helm.sh/hook*` annotation on one document — the phase AND its modifiers."""
    annotations = ((document.get("metadata") or {}).get("annotations")) or {}
    return {key: value for key, value in annotations.items() if "helm.sh/hook" in key}


# THE ANNOTATION THAT MAKES A DOCUMENT A HOOK, AND IT IS THE PHASE ALONE.
# `helm.sh/hook-weight` and `helm.sh/hook-delete-policy` are MODIFIERS: they order
# and clean up a hook, and they mean nothing on a document that is not one.
THE_HOOK_KEY = "helm.sh/hook"


def jobs_that_are_not_hooks(documents: list[dict]) -> list[str]:
    """Every Job in the render carrying no `helm.sh/hook` annotation. PURE.

    KEYED ON THE EXACT `helm.sh/hook` KEY RATHER THAN ON A SUBSTRING, AND THAT IS
    MEASURED RATHER THAN STYLE. This gate used to read `hook_annotations(job)`,
    which matches any key CONTAINING `helm.sh/hook` — so a Job that kept
    `helm.sh/hook-weight` and `helm.sh/hook-delete-policy` and lost only the phase
    line still returned a truthy map and the gate stayed green. Measured 2026-09-24
    on helm 3.18.4 and 4.3.0 by deleting that one line from the vendored
    `platform` chart: the render put `envoy-gateway-probe` into the
    ordinary-resource block, at position 40 of 81 rather than the trailing hook
    section, while the old assertion read `{'helm.sh/hook-weight': '-7',
    'helm.sh/hook-delete-policy': 'before-hook-creation'}` and passed. The gate was
    green over exactly the state its own message called the failure.

    PURE AND DOCUMENT-TAKING, following `vendoring_failures` and
    `stated_in_more_than_one_configmap` above, so the red case below feeds it a
    render from a MUTATED COPY and the real gate feeds it the real one.
    """
    return [
        f"the Job `{(job.get('metadata') or {}).get('name')}` carries no "
        f"`{THE_HOOK_KEY}` annotation, so it is an ordinary object in the release "
        f"rather than an install-time step. It carries "
        f"{sorted(hook_annotations(job))}, and every one of those is a modifier "
        f"that means nothing without the phase"
        for job in documents
        if job.get("kind") == "Job" and THE_HOOK_KEY not in hook_annotations(job)
    ]


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

    BOTH HALVES HAVE A RED CASE NOW, AND THEY ARE DIFFERENT KINDS OF CASE. The
    split above gives `len(jobs) == HOOK_JOBS_AT_R5` a VALUES-FLIP red case —
    dropping `platform.preflight.probes.envoyGateway` moves it, and
    `test_dropping_the_second_preflight_probe_reddens_the_hook_job_and_triple_gates`
    runs that flip. The annotation half cannot be reached that way: no values
    overlay can strip a `helm.sh/hook` annotation a chart template writes
    unconditionally, and every one of `platform`'s four Job templates does. So its
    red case is a CHART EDIT —
    `test_a_vendored_job_that_lost_its_hook_annotation_reddens_the_hook_gate`
    unpacks the vendored `platform` tarball, deletes one annotation line, repacks
    it and renders the result.

    THE GAP THAT CLOSED, AND WHAT THE CLOSING FOUND. The gap was a future
    `platform` shipping a probe Job without its `helm.sh/hook` annotation while
    the Job count stays 4: the Job then runs as an ordinary release resource in
    the wrong phase, its ServiceAccount does not exist yet when it is admitted,
    and nothing reddened. Constructing that case showed the assertion was WEAKER
    than this docstring used to claim — it read any key containing `helm.sh/hook`,
    so a Job that kept the two modifiers and lost only the phase passed it. The
    gate now reads the exact key, through `jobs_that_are_not_hooks`; see that
    function for the measurement.
    """
    jobs = [document for document in adopter if document.get("kind") == "Job"]
    assert len(jobs) == HOOK_JOBS_AT_R5, (
        f"the adopter-values render holds {len(jobs)} Job(s) and this gate expects "
        f"{HOOK_JOBS_AT_R5}: {names_of(adopter, 'Job')}"
    )
    not_hooks = jobs_that_are_not_hooks(adopter)
    assert not_hooks == [], "\n".join(not_hooks)


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

    THE `!=` IS NOT REDUNDANT BESIDE THAT `==` — MEASURED, NOT ASSUMED. Revert
    `RBAC_TRIPLE_NAMES_AT_R5` to its pre-0.1.7 value, `["bootstrap-secrets",
    "preflight"]`: that is the SAME list as
    `RBAC_TRIPLE_NAMES_WITHOUT_THE_SECOND_PROBE`, so the `==` above stays GREEN
    over the reverted constant and only the `!=` fires, naming the Role/
    RoleBinding names that did not move. The `==` guards the RENDER — it fails
    when this flip stops producing the list it is supposed to produce. The `!=`
    guards the CONSTANT — it fails when `RBAC_TRIPLE_NAMES_AT_R5` regresses to a
    value the flip's own list happens to equal. A `!=` beside a `==` in a helm
    red case is not automatically redundant; judge such a pair by perturbing the
    constant, not by reading the two lines.
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
    assert dict(kinds(documents)) == ADOPTER_EXPECTED | {
        "Job": 3,
        "Role": 2,
        "RoleBinding": 2,
        "ServiceAccount": 9,
    }, (
        f"the flip's kind-level census is {dict(kinds(documents))} and this test "
        f"expects the decomposition its own docstring names: one Job, one Role, "
        f"one RoleBinding and one ServiceAccount dropped from `ADOPTER_EXPECTED`. "
        f"The total and the Role/RoleBinding names can each stay right while some "
        f"other kind moves by the same net count; this is the assert that would "
        f"catch that."
    )


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


# ── the annotation half of the hook gate, and it needs an edited subchart ────

# THE ONE VENDORED TEMPLATE THE RED CASE BELOW EDITS, and the one line it deletes.
# `envoy-gateway-probe` is the Job whose loss of the annotation is the defect the
# gate names: it is the only post-install hook, so as an ordinary resource it would
# be applied in the same wave as the objects it exists to probe.
#
# THE LINE IS THE PHASE AND NOT THE WHOLE BLOCK. Deleting all three annotations
# would construct a mutation to fit the assertion rather than the defect; the
# realistic release ships the modifiers and drops the phase, which is exactly the
# case the old substring filter passed. This is also the faithful port of
# `yadgarhq/platform`'s `chart_with_a_job_that_is_not_a_hook`, which deletes one
# line from one template for the same reason.
THE_VENDORED_SUBCHART = "platform"
THE_PROBE_TEMPLATE = "platform/templates/envoy-gateway-probe.yaml"
THE_HOOK_LINE = "    helm.sh/hook: post-install,post-upgrade\n"
THE_JOB_THE_MUTATION_UNHOOKS = "envoy-gateway-probe"

# A MEMBER OF THE SAME TARBALL THAT HELM NEVER RENDERS, and a line really inside
# it. The vacuousness guard mutates this instead, so a mutation that reaches
# nothing helm reads is shown to leave the gate green rather than being argued to.
AN_UNRENDERED_MEMBER = "platform/charts/nats/UPGRADING.md"
A_LINE_IN_THE_UNRENDERED_MEMBER = "# Upgrading from 0.x to 1.x\n"


def chart_with_a_vendored_line_deleted(destination: Path, member: str, line: str) -> Path:
    """A copy of the parent whose vendored `platform` tarball had one line deleted.

    DELETION IS THE REWRITE BELOW WITH AN EMPTY REPLACEMENT, and the two names are
    kept apart because the red cases read differently: deleting a line is the
    faithful model of a release that dropped something, and rewriting one is the
    only way to switch a guard off without leaving the template unparseable.
    """
    return chart_with_a_vendored_line_rewritten(destination, member, line, "")


def chart_with_a_vendored_line_rewritten(
    destination: Path, member: str, was: str, now: str
) -> Path:
    """A copy of the parent whose vendored `platform` tarball had one line rewritten.

    THE PARENT RENDERS FROM A TARBALL, NOT FROM A CHART DIRECTORY, which is why
    this cannot be `platform`'s own helper copied across. Per ADR-0725 nothing
    under `chart/charts/` is committed, so `helm dependency update chart` puts a
    PACKAGED subchart there and the mutation has to unpack it, edit one member,
    and repack it under the same name so the pin in `chart/Chart.yaml` still
    resolves.

    IT PERTURBS A COPY AND NEVER THE WORKING TREE. `shutil.copytree` takes the
    whole chart, `charts/` included, and every edit lands inside `destination`.

    THE MEMBER AND THE LINE ARE BOTH ASSERTED BEFORE THE TARBALL IS WRITTEN,
    and the refusals name what was missing. `shutil.copytree` runs first, so the
    copy itself already exists by the time either assert fires — what the asserts
    stop is the repack, not the copy. A tarfile member list that does not hold the
    named template, or a template whose line has moved, is a red case that has
    stopped testing anything — and an empty match read as a pass is the exact
    false green this whole family of gates exists to refuse.

    THE NEEDLE IS COUNTED AND NOT ONLY FOUND, the way
    `chart_with_the_validate_line_rewritten` counts its own: a line that occurs
    twice would be half-rewritten and the render would show a mutation nobody
    designed.
    """
    import io
    import tarfile

    copy = destination / "chart"
    shutil.copytree(CHART, copy)

    # ONE TARBALL, ASSERTED. A glob that matches zero files would otherwise make
    # this helper a no-op, and a glob that matches two would mutate whichever
    # sorted first.
    tarballs = sorted(copy.glob(f"charts/{THE_VENDORED_SUBCHART}-*.tgz"))
    assert len(tarballs) == 1, (
        f"`charts/` holds {len(tarballs)} `{THE_VENDORED_SUBCHART}` tarball(s) — "
        f"{[path.name for path in tarballs]} — and this red case edits exactly one. "
        f"Run `helm dependency update chart` first; nothing under `chart/charts/` "
        f"is committed."
    )

    with tarfile.open(tarballs[0], "r:gz") as archive:
        entries = [
            (entry, archive.extractfile(entry).read() if entry.isfile() else None)
            for entry in archive.getmembers()
        ]

    assert member in [entry.name for entry, _ in entries], (
        f"`{member}` is not a member of `{tarballs[0].name}`, so this mutation "
        f"would edit nothing and the render would be the unmutated one"
    )

    rewritten = io.BytesIO()
    with tarfile.open(fileobj=rewritten, mode="w:gz") as archive:
        for entry, body in entries:
            if entry.name == member:
                text = body.decode()
                assert text.count(was) == 1, (
                    f"`{was.strip()}` occurs {text.count(was)} times in `{member}` "
                    f"and exactly one was expected, so this red case is now testing "
                    f"something else — the line moved and the edit would be a no-op "
                    f"the render could not show"
                )
                body = text.replace(was, now, 1).encode()
                entry.size = len(body)
            archive.addfile(entry, io.BytesIO(body) if body is not None else None)

    tarballs[0].write_bytes(rewritten.getvalue())
    return copy


def assert_the_mutation_reddened_the_gate(documents: list[dict]) -> list[str]:
    """The red case's own premise, asserted rather than assumed. Returns the failures.

    SHARED WITH THE VACUOUSNESS GUARD, which is the whole reason it is a function.
    The guard feeds it a render whose mutation helm never read and shows THIS
    assertion firing — so the refusal below is demonstrated to be load-bearing
    rather than asserted to be.
    """
    failures = jobs_that_are_not_hooks(documents)
    assert failures, (
        "the vendored `platform` chart was unpacked, edited and repacked, and the "
        "render still holds no Job without its `helm.sh/hook` annotation. The "
        "mutation reached nothing helm renders, so this red case is testing nothing"
    )
    return failures


def test_a_vendored_job_that_lost_its_hook_annotation_reddens_the_hook_gate(
    tmp_path: Path,
) -> None:
    """THE ANNOTATION HALF'S RED CASE, and it takes an edited chart rather than a flip.

    WHY NO VALUES FILE CAN BUILD THIS. Every `helm.sh/hook` annotation in
    `platform`'s four Job templates is written unconditionally, and
    `platform/values.yaml` declares no `annotations` key to override. So the only
    constructible form of "a release ships a Job that is not a hook" is an edited
    chart, and the parent's chart is a VENDORED TARBALL.

    THE COUNT MUST STAY SILENT ON THIS SAME INPUT, and that is asserted here. The
    parent builds its Job set by `kind` alone, so deleting an annotation moves
    neither the Job count nor the object total — measured 2026-09-24 on helm
    3.18.4 and 4.3.0, 81 objects and 4 Jobs under the mutation. If the count fired
    too, the mutation would have moved something else and this test would not be
    isolating the assertion it claims to isolate.
    """
    documents = render(
        str(chart_with_a_vendored_line_deleted(tmp_path, THE_PROBE_TEMPLATE, THE_HOOK_LINE)),
        *API_VERSIONS,
        "-f",
        str(ADOPTER_VALUES),
    )

    message = "\n".join(assert_the_mutation_reddened_the_gate(documents))
    assert THE_JOB_THE_MUTATION_UNHOOKS in message, message
    assert THE_HOOK_KEY in message, message

    assert len(names_of(documents, "Job")) == HOOK_JOBS_AT_R5, (
        f"the deletion moved the Job count to "
        f"{len(names_of(documents, 'Job'))}, so it perturbed more than the "
        f"annotation and this case no longer isolates the annotation assert"
    )
    assert len(documents) == ADOPTER_OBJECTS, (
        f"the deletion left {len(documents)} objects where {ADOPTER_OBJECTS} was "
        f"expected; the count gate is supposed to stay silent on this input"
    )


def test_a_mutation_helm_never_reads_is_refused_rather_than_passing_silently(
    tmp_path: Path,
) -> None:
    """THE VACUOUSNESS GUARD: the red case above rests on a premise, so break it.

    THE PREMISE is that the vendored tarball can be unpacked, edited and repacked
    so that helm reads the edit. A red case whose mutation stops reaching the
    render does not fail — it passes, having proved nothing, which is the failure
    mode `yadgarhq/platform`'s own suite needed this guard for.

    TWO ARMS, AND THEY BREAK THE PREMISE IN DIFFERENT PLACES. The first names a
    member the tarball does not hold: the helper refuses before repacking it.
    The second edits a member helm genuinely never renders — the vendored NATS
    chart's upgrade notes — so the mutation IS applied, the tarball IS repacked and
    the render is unmoved. That is the silent form, and this arm shows
    `assert_the_mutation_reddened_the_gate` refusing it by name. It carries a
    second property the first arm cannot: the render staying at exactly 81
    objects after `platform/charts/nats/UPGRADING.md` is edited proves the
    tarball this helper writes with Python's `w:gz` is one helm can read at all,
    not only that the mutation inside it went unread.
    """
    with pytest.raises(AssertionError) as absent:
        chart_with_a_vendored_line_deleted(
            tmp_path / "no-such-member",
            "platform/templates/there-is-no-such-template.yaml",
            THE_HOOK_LINE,
        )
    assert "there-is-no-such-template.yaml" in str(absent.value)

    documents = render(
        str(
            chart_with_a_vendored_line_deleted(
                tmp_path / "unrendered",
                AN_UNRENDERED_MEMBER,
                A_LINE_IN_THE_UNRENDERED_MEMBER,
            )
        ),
        *API_VERSIONS,
        "-f",
        str(ADOPTER_VALUES),
    )
    assert len(documents) == ADOPTER_OBJECTS, (
        f"editing `{AN_UNRENDERED_MEMBER}` moved the render to {len(documents)} "
        f"objects, so helm does read it and this arm is not the no-op it claims"
    )

    with pytest.raises(AssertionError) as unnoticed:
        assert_the_mutation_reddened_the_gate(documents)
    assert "reached nothing helm renders" in str(unnoticed.value)


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


# THE SAME SHAPE FOR `iam-keys`, AND ONLY ONE SIDE OF IT IS A KEY. The bootstrap
# Job mints the name as a LITERAL in its script; `iam` mounts `iam.keysSecret`,
# which is a value. So the red case renames the mounted side alone — there is no
# minted side to rename — and the overlay below is the ONE place both names meet.
#
# EVERY FIELD IS SET EXPLICITLY BECAUSE `refusal()` RENDERS AT THE CHART DEFAULTS.
# `platform.enabled` and `bootstrap.create` are what reach the clause at all;
# `gateway.adminBootstrap.tokenSecret` is set to the name `platform` mints so that
# BOTH admin-token refusals stay silent, which is what makes the message this test
# reads unambiguously its own.
IAM_KEYS_OVERLAY = (
    "platform:\n"
    "  enabled: true\n"
    "  bootstrap:\n"
    "    create: true\n"
    "    iamKeys:\n"
    "      create: true\n"
    "gateway:\n"
    "  adminBootstrap:\n"
    "    tokenSecret: admin-bootstrap-token\n"
    "iam:\n"
    "  keysSecret: {name}\n"
)

# A NAME THAT SHARES NO SPAN WITH THE LITERAL, and one that CONTAINS IT WHOLE. The
# second is the discriminating one: `iam-keys-2` names a Secret the Job never mints,
# and an implementation matching on `contains` or `hasPrefix` would let it through
# while still refusing the first. A test carrying only the first proves nothing
# about exactness.
A_DISJOINT_NAME = "my-own-iam-keys"
A_NAME_THE_LITERAL_IS_A_PREFIX_OF = "iam-keys-2"

# THE PHRASE THAT NAMES THE MINTED SIDE, asserted instead of the bare literal.
# `iam-keys` is a SUBSTRING of both red-case names, so `"iam-keys" in message`
# passes whether or not the message ever names what the Job mints — it would read
# the adopter's own value back and call it a match.
THE_MINTED_NAME_IN_THE_MESSAGE = "mints a Secret named exactly iam-keys"


def test_the_parent_refuses_a_renamed_iam_keys_secret(tmp_path: Path) -> None:
    """The Job mints `iam-keys` and `iam` mounts something else; the refusal names both.

    MEASURED BEFORE THIS CLAUSE EXISTED, on helm 3.18.4 and 4.3.0 alike:
    `example/values.yaml` plus `iam.keysSecret: my-own-iam-keys` rendered exit 0 and
    81 objects, the Job carrying `"metadata":{"name":"iam-keys"}` and the `iam`
    Deployment `secretName: my-own-iam-keys`. Nothing refused, and the pod would
    stick in `ContainerCreating` on a Secret nothing created.

    THE GREEN CASE IS PART OF THE TEST, because a refusal that fires on a correct
    configuration is worse than none. An adopter who renames the Secret with
    `iamKeys.create` FALSE is doing the supported thing — bringing their own keys
    from Vault, SOPS or 1Password — and that render must still be the whole estate.
    """
    message = refusal(
        tmp_path, "renamed-iam-keys", IAM_KEYS_OVERLAY.format(name=A_DISJOINT_NAME)
    )
    assert "platform.bootstrap.iamKeys.create is true" in message, message
    assert THE_MINTED_NAME_IN_THE_MESSAGE in message, message
    assert "iam.keysSecret" in message, message
    assert f'"{A_DISJOINT_NAME}"' in message, message
    # The overlay reaches THIS clause and no other — neither admin-token refusal
    # fires, so the assertions above read a message this clause alone wrote.
    assert "gateway.adminBootstrap.tokenSecret is empty" not in message, message
    assert "platform.bootstrap.adminToken.secretName" not in message, message

    # EXACT, NOT A PREFIX. The literal is a whole prefix of this name.
    superset = refusal(
        tmp_path,
        "iam-keys-with-a-suffix",
        IAM_KEYS_OVERLAY.format(name=A_NAME_THE_LITERAL_IS_A_PREFIX_OF),
    )
    assert THE_MINTED_NAME_IN_THE_MESSAGE in superset, superset
    assert f'"{A_NAME_THE_LITERAL_IS_A_PREFIX_OF}"' in superset, superset

    # THE GREEN CASE: the same rename with the toggle OFF mints nothing, so nothing
    # disagrees, and the whole estate renders.
    documents = adopter_render(
        "-f",
        str(
            overlay(
                tmp_path / "renamed-with-the-toggle-off.yaml",
                f"iam:\n  keysSecret: {A_DISJOINT_NAME}\n"
                "platform:\n  bootstrap:\n    iamKeys:\n      create: false\n",
            )
        ),
    )
    assert len(documents) == ADOPTER_OBJECTS


# WHAT THE JOB ACTUALLY MINTS, AS IT APPEARS IN THE BODY IT POSTS. The refusal in
# `_validate.tpl` carries `iam-keys` as a LITERAL of its own, which makes it a
# second writer for a name whose first writer is a shell literal inside the
# vendored Job. If `platform` ever renames it, the clause inverts: it would refuse
# the corrected configuration and pass the broken one. This is what notices.
THE_MINTED_IAM_KEYS_BODY = '"metadata":{"name":"iam-keys"}'
THE_JOB_THAT_MINTS_IT = "bootstrap-secrets"

# WHERE THAT LITERAL LIVES IN THE VENDORED TARBALL, so the gate above can be
# reddened rather than argued about. The fragment carries its trailing comma and
# occurs EXACTLY ONCE in the template — the bare name appears several times more,
# in the Job's prose comments and in the `mint`/`create` shell calls, and deleting
# one of those would be a different mutation from the one this red case means.
THE_MINTING_TEMPLATE = "platform/templates/bootstrap-secrets.yaml"
THE_MINTED_NAME_IN_THE_POSTED_BODY = '"metadata":{"name":"iam-keys"},'


def test_the_minted_iam_keys_name_is_the_literal_this_refusal_assumes(
    adopter: list[dict],
) -> None:
    """The refusal's assumption about `platform`, read off the render rather than trusted.

    A RENDER-LITERAL GATE, SO IT SHIPS ITS OWN RED CASE. It opens no file. It reads
    `spec.template.spec.containers[].args` off the `adopter` fixture, and that
    fixture is `helm template` output — so the standing rule applies and
    `test_a_vendored_job_that_renamed_the_minted_secret_reddens_the_drift_guard`
    below constructs the red case, by deleting the minted name from the vendored
    `platform` template and repacking the tarball.

    THAT RED CASE CLOSED A STANDING-RULE VIOLATION AND NOT A LIVE HOLE, which is
    worth stating so the fix is not read as larger than it is. The assertion below
    is an EQUALITY against `[bootstrap-secrets]`, so a render in which no Job posts
    the literal at all reddens on the empty list: this gate could never have passed
    vacuously. What was missing was the constructed proof of that, and a docstring
    that described the gate correctly.

    ASSERTED ON THE POSTED BODY, EXACTLY. `iam-keys` alone appears in the Job's
    prose comments and in the mount path `/var/run/secrets/iam-keys`, so a bare
    substring would pass over a Job that renamed what it creates.
    """
    minting = [
        document
        for document in adopter
        if document.get("kind") == "Job"
        and THE_MINTED_IAM_KEYS_BODY in "".join(
            str(part)
            for container in document["spec"]["template"]["spec"]["containers"]
            for part in container.get("args", [])
        )
    ]
    assert [document["metadata"]["name"] for document in minting] == [THE_JOB_THAT_MINTS_IT], (
        f"{len(minting)} Job(s) POST {THE_MINTED_IAM_KEYS_BODY} and exactly one was "
        f"expected, `{THE_JOB_THAT_MINTS_IT}`: "
        f"{[document['metadata']['name'] for document in minting]}. The refusal in "
        f"`_validate.tpl` compares `iam.keysSecret` against that literal, so a "
        f"`platform` release that renamed it would leave the clause refusing the "
        f"corrected configuration and passing the broken one."
    )


def test_a_vendored_job_that_renamed_the_minted_secret_reddens_the_drift_guard(
    tmp_path: Path,
) -> None:
    """THE DRIFT GUARD'S RED CASE, constructed here rather than deferred to a release.

    WHY IT TAKES AN EDITED CHART. The minted name is a shell literal inside
    `platform`'s Job script, written unconditionally and backed by no values key —
    `platform` 0.1.8's own `values.yaml` argues that omission under "WHY THE THREE
    NAMES ARE NOT KEYS HERE". So no values file can rename it, and the only
    constructible form of "a release renamed what the Job mints" is an edited
    chart, which for the parent means the VENDORED TARBALL. This reuses the same
    helper the hook-annotation red case above uses, unchanged.

    IT REDDENS THE GATE ITSELF RATHER THAN A RESTATEMENT OF IT. The function under
    test is called directly on the mutated render, so what is shown failing is the
    shipped assertion and not a second copy of its logic that could drift from it.

    THE COUNT MUST STAY SILENT ON THIS SAME INPUT, and that is asserted. The
    deleted fragment sits inside a heredoc in a shell script, which helm renders as
    opaque text, so the Job still renders and the object total does not move. If it
    did move, the mutation would have perturbed more than the minted name and this
    case would not isolate the assertion it claims to isolate.
    """
    documents = render(
        str(
            chart_with_a_vendored_line_deleted(
                tmp_path, THE_MINTING_TEMPLATE, THE_MINTED_NAME_IN_THE_POSTED_BODY
            )
        ),
        *API_VERSIONS,
        "-f",
        str(ADOPTER_VALUES),
    )

    with pytest.raises(AssertionError) as renamed:
        test_the_minted_iam_keys_name_is_the_literal_this_refusal_assumes(documents)
    assert f"0 Job(s) POST {THE_MINTED_IAM_KEYS_BODY}" in str(renamed.value), str(renamed.value)

    assert len(documents) == ADOPTER_OBJECTS, (
        f"the deletion left {len(documents)} objects where {ADOPTER_OBJECTS} was "
        f"expected; the count gate is supposed to stay silent on this input"
    )


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


# ── ADR-0787: the parent offers no operators path, and refuses six keys ───────
#
# THE FIVE SUB-KEY SPELLINGS, READ OFF `yadgarhq/platform` AND NOT OFF THE PARENT'S
# TEMPLATE. They are the second path of each operator dependency's
# `condition: operators.<op>.create,operators.create` in `platform`'s own
# `chart/Chart.yaml`, verified on `origin/feat/operators-toggle-step1`. The
# template in `_validate.tpl` RANGES over whatever blocks the values carry rather
# than enumerating these, so this tuple is an independent statement of what
# `platform` accepts — not a copy of the implementation it tests. A test that built
# its inputs out of the template's own list would pass whatever that list said.
#
# THEY CANNOT BE READ OFF THE VENDORED TARBALL, which is the usual way this suite
# checks an assumption about `platform` (see
# `test_the_minted_iam_keys_name_is_the_literal_this_refusal_assumes`). `platform`
# 0.1.8 is the pin `chart/Chart.yaml` carries and it has no `operators` key at all:
# steps 1 to 6 of the operators-toggle plan are unmerged. A drift gate against the
# tarball would therefore be red today rather than green, so none is built. When a
# `platform` version carrying `operators` is pinned here, that gate becomes
# constructible and this comment is its trigger.
THE_FIVE_OPERATOR_SUB_KEYS = ("certManager", "keda", "mariadbOperator", "envoyGateway", "argoCd")

# THE OVERLAY SETS `platform.enabled` AND THE ADMIN TOKEN, AND BOTH ARE
# LOAD-BEARING RATHER THAN TIDY. Without them the top-level case proves nothing:
# `platform.operators` is a map carrying `create: true`, so the `$creating` range
# in `_validate.tpl` picks it up and the admin-token and `platform.enabled`
# refusals fire on their own. Measured on `main` BEFORE this clause existed, helm
# 4.3.0: `helm template yadgar chart/ --set platform.operators.create=true` exited
# 1 already, naming `platform.operators.create` inside the admin-token message. The
# same key with these two fields set rendered exit 0 and 32 objects. THAT is the
# render this clause closes, and it is the only form of the top-level case that can
# tell the clause landing apart from the clause being absent.
OPERATORS_OVERLAY = (
    "platform:\n"
    "  enabled: true\n"
    "  operators:\n"
    "{block}"
    "gateway:\n"
    "  adminBootstrap:\n"
    "    tokenSecret: admin-bootstrap-token\n"
)
TOP_LEVEL_BLOCK = "    create: true\n"

# THE PHRASE THIS CLAUSE ALONE WRITES. `"platform.operators.create" in message` is
# NOT a discriminator: the admin-token refusal interpolates the same key through
# its `%s`, and the `platform.enabled` refusal does too, so that assertion passes
# against a chart carrying none of this clause. Every assertion below reads this
# phrase, and every case also asserts the other two refusals stayed silent.
THE_OPERATORS_REFUSAL = "asks this parent chart to install third-party operators"
THE_ADMIN_TOKEN_REFUSAL = "gateway.adminBootstrap.tokenSecret is empty"
THE_DEPENDENCY_REFUSAL = "platform.enabled is not true"
THE_OPERATORS_SHAPE_REFUSAL = "rather than a mapping"

# THE THREE TEXTS A RAISE LEAVES IN STDERR, shared with
# `test_the_refusals_are_nil_safe_with_every_subchart_removed`. A refusal and a
# raise both exit 1, so the exit code alone cannot tell a named key from a stack
# trace.
THE_TEXTS_A_RAISE_LEAVES = ("nil pointer", "can't evaluate field", "error calling")


def operators_overlay(block: str) -> str:
    return OPERATORS_OVERLAY.format(block=block)


def sub_key_block(operator: str) -> str:
    return f"    {operator}:\n      create: true\n"


def test_the_parent_refuses_the_operators_toggle_and_every_one_of_its_sub_keys(
    tmp_path: Path,
) -> None:
    """ADR-0787: `operators.create` is a `platform` path, and never the parent's.

    SIX RENDERS, NOT ONE, and the five sub-key renders are the part a top-level
    refusal would miss. Each operator dependency in `platform` is declared
    `condition: operators.<op>.create,operators.create`, and helm evaluates the
    FIRST valid path and stops — so `operators.certManager.create: true` installs
    cert-manager while `operators.create` is false. Measured in `platform` at step
    3 of the operators-toggle plan: `--set operators.create=false --set
    operators.certManager.create=true` rendered 50 objects with 6 CRDs. A parent
    refusal reading the top-level key alone is FALSE in that shape, and
    `test_a_refusal_that_read_the_top_level_key_alone_would_let_a_sub_key_through`
    below constructs that narrowing and shows it passing the sub-key.

    MEASURED ON `main` BEFORE THIS CLAUSE EXISTED, helm 4.3.0:
    `--set platform.operators.certManager.create=true` rendered exit 0 and 32
    objects — `platform.operators` is a map whose own `create` key is absent, so
    the `$creating` guard never opened and no refusal ran.

    THE GREEN CASE IS PART OF THE TEST. An adopter who writes an operator key
    FALSE is doing the supported thing, and a refusal keyed on the key being
    PRESENT rather than on it being TRUE would break every one of them.
    """
    message = refusal(tmp_path, "operators-create", operators_overlay(TOP_LEVEL_BLOCK))
    assert THE_OPERATORS_REFUSAL in message, message
    assert "platform.operators.create" in message, message
    assert THE_ADMIN_TOKEN_REFUSAL not in message, message
    assert THE_DEPENDENCY_REFUSAL not in message, message

    for operator in THE_FIVE_OPERATOR_SUB_KEYS:
        message = refusal(
            tmp_path, f"operators-{operator}", operators_overlay(sub_key_block(operator))
        )
        assert THE_OPERATORS_REFUSAL in message, message
        assert f"platform.operators.{operator}.create" in message, message
        # The sub-key opens no `platform.<name>.create`, so the guarded refusals
        # stay shut and the assertions above read this clause's message alone.
        assert THE_ADMIN_TOKEN_REFUSAL not in message, message
        assert THE_DEPENDENCY_REFUSAL not in message, message

    # THE GREEN CASE: every operator key stated FALSE, which is a values file the
    # parent supports, and the whole estate still renders.
    documents = adopter_render(
        "-f",
        str(
            overlay(
                tmp_path / "operators-all-false.yaml",
                "platform:\n  operators:\n    create: false\n"
                + "".join(
                    f"    {operator}:\n      create: false\n"
                    for operator in THE_FIVE_OPERATOR_SUB_KEYS
                ),
            )
        ),
    )
    assert len(documents) == ADOPTER_OBJECTS, (
        f"the operator keys stated false left {len(documents)} objects where "
        f"{ADOPTER_OBJECTS} was expected; a refusal keyed on the key being present "
        f"rather than true would refuse this file"
    )


# THE EIGHT SHAPES AN ADOPTER CAN WRITE UNDER `platform.operators`, EACH WITH THE
# TYPE NAME THE MESSAGE MUST CARRY. Two `true`-ish rows do not cover this key, and
# the gap was measured rather than imagined: at 883a7a8 the guard read
# `kindIs "map"` on `default dict $platform.operators`, and sprig's `default`
# substitutes on an EMPTY value, so `false`, `null`, `0`, `""` and `[]` every one
# collapsed to `dict` and read as the key being ABSENT. Measured on helm 4.3.0
# with `platform.enabled` true and the admin token set: those five rendered exit 0
# while `true`, `yes` and `[a]` refused. `[]` permitting while `[a]` refuses is the
# incoherence that found it, and `false` is the load-bearing one — it is what
# somebody writes who read "default false" and wanted to be explicit, and helm
# leaves a dependency ENABLED when no path of a multi-path `condition:` resolves.
#
# THE TYPE NAME IS ASSERTED PER ROW, not just the phrase. `"rather than a mapping"
# in message` is satisfied by an implementation that calls every shape a bool, and
# the whole point of `kindOf` here is that the adopter is told what they wrote.
#
# `yes` IS A BOOL AND NOT A STRING, which is YAML 1.1 and what helm parses. The row
# is kept because it is a real adopter spelling; the name says so now, and the type
# it asserts is measured rather than assumed.
#
# `null` IS A PRESENT KEY AND ONLY `hasKey` SEES IT. `kindOf` reports `invalid` for
# an explicit null and for an absent key alike, so a guard reading the VALUE cannot
# tell `operators: null` from no `operators` key at all. Measured on helm 4.3.0:
# `hasKey $platform "operators"` is true for `operators: null` and false when the
# key is absent. `_validate.tpl` maps `invalid` to `null` so the message names a
# type an adopter recognises rather than "is a invalid".
#
# ── AND THE `null` ROW IS THE ONE THE PARENT CANNOT ANSWER (2026-09-26) ─────────
#
# EVERY ROW CARRIES THE CHART THAT REFUSES IT, because they are no longer all the
# same chart. Seven are refused HERE, by `chart/templates/_validate.tpl`, naming the
# type the adopter wrote. `null` is refused one level down, by `platform`'s own arm
# one, and no change in this repository can move it back.
#
# WHY. HELM DELETES A KEY WHOSE VALUE IS NULL, and it does NOT put the child's
# default back in its place — so by the time any template runs there is no
# `platform.operators` key for `hasKey` to find, and the parent's guard reads FALSE.
# That is indistinguishable from an adopter who never wrote the key, which is every
# other adopter, so the parent going quiet here is correct rather than a hole. Helm
# deletes the key only if the chart DECLARES it, and `platform` began declaring
# `operators.create: false` at 0.1.9 — a child chart shipping a default therefore
# blinded its parent's guard. `platform` 0.1.11 refuses the case itself for exactly
# that reason, from the one place the information still exists.
#
# THE PARENT'S OWN `null` BRANCH IS STILL LIVE, MEASURED RATHER THAN ASSUMED. With
# no subchart declaring the key, nothing triggers the deletion: over
# `chart_without_its_dependencies` the same overlay is refused by the PARENT naming
# `platform.operators is a null rather than a mapping`, on helm 3.20.2 and 4.3.0
# alike, 2026-09-26. So `_validate.tpl`'s `invalid` → `null` mapping is not dead
# code; it is code a pinned `platform` stands in front of.
#
# THE WHOLE TABLE WAS RE-MEASURED AT `platform` 0.1.11 ON BOTH HELM LINES, 3.20.2
# and 4.3.0, 2026-09-26, and the two agree row for row. Only `null` moved: the other
# seven are still refused by the parent, still naming `bool`, `float64`, `string`
# and `slice`. The four empty scalars were re-run individually rather than inferred
# from a suite run, because the loop below stops at its first failing row.
THE_PARENT = "chart"
THE_SUBCHART = "platform"

# THE PHRASE `platform` 0.1.11 WRITES AND THIS PARENT CANNOT, read off the published
# artifact (`templates/render-checks.yaml`, arm one) rather than retyped from a
# summary of it. It is the discriminator for the `null` row the way the type name is
# for the other seven: `"rather than a mapping"` alone appears in `platform`'s own
# text too — its arm one ends by telling the adopter to write `operators:` AS a
# mapping — so the row needs the sentence that only the deleted-key arm carries.
THE_DELETED_OPERATORS_KEY_REFUSAL = (
    "the operators key has been deleted from this release's values"
)


def the_parent_names_the_type(kind: str) -> str:
    return f"platform.operators is a {kind} {THE_OPERATORS_SHAPE_REFUSAL}"


THE_NON_MAPPING_OPERATORS = (
    ("operators-is-a-bool", "true", THE_PARENT, the_parent_names_the_type("bool")),
    ("operators-is-the-yaml-yes", "yes", THE_PARENT, the_parent_names_the_type("bool")),
    ("operators-is-false", "false", THE_PARENT, the_parent_names_the_type("bool")),
    ("operators-is-null", "null", THE_SUBCHART, THE_DELETED_OPERATORS_KEY_REFUSAL),
    ("operators-is-zero", "0", THE_PARENT, the_parent_names_the_type("float64")),
    ("operators-is-an-empty-string", '""', THE_PARENT, the_parent_names_the_type("string")),
    ("operators-is-an-empty-list", "[]", THE_PARENT, the_parent_names_the_type("slice")),
    ("operators-is-a-list", "[a]", THE_PARENT, the_parent_names_the_type("slice")),
)

# WHAT THE WALK ABOVE MUST EXAMINE, COUNTED AND SPLIT BY REFUSER. A row deleted from
# the tuple, or a row that quietly changed which chart answered it, reddens here
# rather than leaving the loop exercising one fewer shape and reporting a pass.
THE_SHAPES_AN_ADOPTER_CAN_WRITE = {THE_PARENT: 7, THE_SUBCHART: 1}


def test_the_parent_refuses_a_platform_operators_key_that_is_not_a_mapping(
    tmp_path: Path,
) -> None:
    """The adopter typo that used to abort the render with a stack trace.

    `platform.operators: true` is what somebody writes who thinks the toggle IS
    the block rather than a key inside it. Sprig's `default` substitutes only on an
    EMPTY value, so `default dict true` is `true`, and both the `create` read and
    the range then run against a bool. Measured on helm 4.3.0 before the `kindIs`
    arm existed: `--set platform.operators=true` aborted with `can't evaluate field
    create in type bool`.

    EVERY ROW OF `THE_NON_MAPPING_OPERATORS` IS RUN, and the five EMPTY ones are
    what this test was missing. The same `default` that makes the `true` case raise
    makes `false`, `null`, `0`, `""` and `[]` read as ABSENT, so a guard built on
    `default dict` covers only the non-empty half of the shapes it claims. The
    RAW value is what has to be typed, which is what the template does now.

    ASSERTED ON THE ABSENCE OF A RAISE, not only on the exit code. A refusal and a
    raise both exit 1, so an implementation that went back to raising would satisfy
    `returncode != 0` while giving the adopter a stack trace instead of a key name.

    SEVEN ROWS ARE THIS PARENT'S REFUSAL AND ONE IS `platform`'s, which is a
    structural fact rather than an inconsistency — the tuple's comment carries the
    measurement. `platform.operators: null` makes helm DELETE the key, so the
    parent's `hasKey` reads false and the only chart that still knows the key was
    written is the one whose own defaults guarantee it.
    `test_switching_off_the_subcharts_deleted_key_arm_lets_the_null_render` is the
    red case, and it shows the shape rendering exit 0 with the operators in.
    """
    refused_by: collections.Counter = collections.Counter()
    for name, scalar, chart, phrase in THE_NON_MAPPING_OPERATORS:
        message = refusal(
            tmp_path,
            name,
            f"platform:\n  enabled: true\n  operators: {scalar}\n"
            "gateway:\n  adminBootstrap:\n    tokenSecret: admin-bootstrap-token\n",
        )
        assert phrase in message, (
            f"`{name}` refused without the phrase `{chart}` alone writes: {message}"
        )
        for raise_text in THE_TEXTS_A_RAISE_LEAVES:
            assert raise_text not in message, (
                f"`{name}` RAISED instead of refusing: {message}"
            )
        refused_by[chart] += 1
    assert dict(refused_by) == THE_SHAPES_AN_ADOPTER_CAN_WRITE, (
        f"this walk examined {dict(refused_by)} and the table says "
        f"{THE_SHAPES_AN_ADOPTER_CAN_WRITE}"
    )


# THE ONE LINE THE RED CASE BELOW REWRITES, AND IT IS IN THE SUBCHART. The `null`
# row's refusal is `platform`'s, so the mutation that has to show it load-bearing is
# `platform`'s too — the parent has no line to switch off for this row, which is the
# whole claim the row makes. Rewritten rather than deleted: removing the `if` leaves
# the `else if` beneath it with no opening branch and helm refuses to parse the
# template at all, which would be a red case that fails for the wrong reason.
THE_OPERATORS_RENDER_CHECKS = "platform/templates/render-checks.yaml"
THE_DELETED_KEY_ARM = '{{- if not (hasKey .Values "operators") }}\n'
THE_DELETED_KEY_ARM_OFF = "{{- if false }}\n"

# WHERE AN OPERATOR SUBCHART'S OBJECTS ANNOUNCE THEMSELVES. `helm template` writes a
# `# Source:` comment above every document, so the operators going in is read off the
# raw stdout rather than inferred from a count that also moves for other reasons.
#
# THE FIVE ARE NAMED RATHER THAN GLOBBED, because `platform/charts/` also holds the
# upstream NATS chart, which is not an operator and renders here at the defaults for
# reasons that have nothing to do with this arm.
THE_OPERATOR_SOURCES = tuple(
    f"# Source: yadgar/charts/platform/charts/{chart}/"
    for chart in ("argo-cd", "cert-manager", "gateway-helm", "keda", "mariadb-operator")
)


def test_switching_off_the_subcharts_deleted_key_arm_lets_the_null_render(
    tmp_path: Path,
) -> None:
    """THE `null` ROW'S RED CASE, and it renders exit 0 with five operators in.

    WHAT IT CONSTRUCTS. The vendored `platform` tarball is unpacked, arm one's
    `hasKey` test is rewritten to `false`, and the tarball is repacked under the same
    name. Arm two then stands down on its own — it refuses only when `platform` is
    the ROOT chart and here it is a subchart — so the release has no refusal for a
    deleted `operators` key anywhere, which is exactly the estate as it stood before
    `platform` 0.1.11.

    WHAT IT MEASURES. `platform.operators: null` renders EXIT 0 and the five operator
    subcharts come with it. That is the fail-open ADR-0794 names rather than a
    cosmetic gap: helm resolves each operator's `condition:` against the RAW values
    where the key is still null, and it leaves a dependency ENABLED when no path of a
    multi-path condition resolves — so the shape does not turn the operators off, it
    turns all five on. Measured 2026-09-26 on helm 3.20.2 and 4.3.0 alike: 197
    objects against the 81 of R5, 165 of them from the operator subcharts.

    THE COUNTS ARE ASSERTED AS INEQUALITIES, deliberately. Pinning 197 and 165 would
    redden this red case at every operator version bump for a reason that has nothing
    to do with the arm it exercises, and the property being shown is that the
    operators ARRIVED, not how many objects they happen to carry this month.

    AND THE PARENT IS SHOWN SILENT ON THE SAME INPUT, which is the other half. If the
    parent could refuse this shape the row would not need `platform`'s wording at
    all; asserting that neither the parent's phrase nor a raise appears is what
    distinguishes "the parent is blind here" from "the mutation broke something".
    """
    copy = chart_with_a_vendored_line_rewritten(
        tmp_path / "arm-one-off",
        THE_OPERATORS_RENDER_CHECKS,
        THE_DELETED_KEY_ARM,
        THE_DELETED_KEY_ARM_OFF,
    )
    result = helm(
        "template",
        "yadgar",
        str(copy),
        *API_VERSIONS,
        "-f",
        str(
            overlay(
                tmp_path / "arm-one-off.yaml",
                "platform:\n  enabled: true\n  operators: null\n"
                "gateway:\n  adminBootstrap:\n    tokenSecret: admin-bootstrap-token\n",
            )
        ),
    )
    assert result.returncode == 0, (
        "`platform.operators: null` was still refused with arm one switched off, so "
        f"this red case is not isolating the arm the `null` row reads: {result.stderr}"
    )
    assert THE_DELETED_OPERATORS_KEY_REFUSAL not in result.stderr, result.stderr
    assert THE_OPERATORS_SHAPE_REFUSAL not in result.stderr, (
        "the parent refused this shape after all, which would make the `null` row's "
        f"dependence on `platform`'s wording untrue: {result.stderr}"
    )
    for raise_text in THE_TEXTS_A_RAISE_LEAVES:
        assert raise_text not in result.stderr, (
            f"the mutated release RAISED rather than rendering, so this red case "
            f"shows a broken template and not a fail-open: {result.stderr}"
        )

    documents = [
        document
        for document in yaml.safe_load_all(result.stdout)
        if isinstance(document, dict) and document.get("apiVersion")
    ]
    assert len(documents) > ADOPTER_OBJECTS, (
        f"the mutated release rendered {len(documents)} objects, no more than the "
        f"{ADOPTER_OBJECTS} of R5, so the operators did not go in and this red case "
        f"is showing nothing"
    )
    arrived = [source for source in THE_OPERATOR_SOURCES if source in result.stdout]
    assert len(arrived) == len(THE_OPERATOR_SOURCES), (
        f"the mutated release rendered objects from {len(arrived)} of the "
        f"{len(THE_OPERATOR_SOURCES)} operator subcharts — {arrived} — so the "
        f"fail-open this red case exists to show did not happen in full"
    )


# THE FOUR NON-BOOLEAN `create` SPELLINGS, AND THE TWO KEY PATHS THEY SIT ON. A
# quoted `"true"` and a bare `1` are what an adopter writes who is copying a shell
# export or a JSON fragment, and `eq (default false $block.create) true` cannot
# compare either against a bool: helm aborts with `error calling eq: incompatible
# types for comparison`. Measured on helm 4.3.0 at 883a7a8 — a stack trace naming
# `_validate.tpl:189` and `:194` where the adopter needs a key name.
#
# THE SUB-KEY PATH IS THE ONE THIS PULL REQUEST OPENED. Measured on `main`:
# `platform.operators.certManager.create: "true"` rendered exit 0 and 32 objects —
# silently permitted, because `main` has no operators clause at all — and at
# 883a7a8 it RAISES. The top-level `platform.operators.create` raised on `main`
# too, at the pre-existing `$creating` range, so that half is a defect this file
# inherited rather than one the clause introduced. Both are refusals now.
THE_NON_BOOLEAN_CREATES = (
    ("create-is-a-quoted-true", "certManager", '"true"', "platform.operators.certManager.create", "string"),
    ("create-is-an-integer", "certManager", "1", "platform.operators.certManager.create", "float64"),
    ("create-is-a-quoted-true-at-the-top", None, '"true"', "platform.operators.create", "string"),
    ("create-is-an-integer-at-the-top", None, "1", "platform.operators.create", "float64"),
)
THE_CREATE_SHAPE_REFUSAL = "rather than a boolean"


def test_the_parent_refuses_a_create_toggle_that_is_not_a_boolean(tmp_path: Path) -> None:
    """A `create` helm cannot compare is refused by name, never raised on.

    THE RULE IS THE SAME ONE `platform.operators` OBEYS: refuse a value in a shape
    the chart cannot read, never coerce it and read it anyway. `default false` is
    nil-safe and never type-safe — it substitutes on an EMPTY value, so it turns a
    missing key into `false` and hands a present `"true"` straight to `eq`.

    ASSERTED ON THE ABSENCE OF A RAISE, and that assertion is the whole test. Both
    spellings already exit 1 at 883a7a8 — BY RAISING — so a red case reading
    `returncode != 0` is green against the defect it is supposed to catch.

    A NIL `create` IS LEFT ALONE, DELIBERATELY. `create: null` never raised:
    `default false nil` is `false` and `eq false true` is a legal comparison. Only
    the values that ABORT the render are refused here, so this clause changes the
    raising class and nothing else.
    """
    for name, operator, scalar, key, kind in THE_NON_BOOLEAN_CREATES:
        block = (
            f"    {operator}:\n      create: {scalar}\n"
            if operator
            else f"    create: {scalar}\n"
        )
        message = refusal(tmp_path, name, operators_overlay(block))
        assert THE_CREATE_SHAPE_REFUSAL in message, message
        assert f"{key} is a {kind} rather than a boolean" in message, (
            f"`{name}` refused without naming the key and the type: {message}"
        )
        for raise_text in THE_TEXTS_A_RAISE_LEAVES:
            assert raise_text not in message, (
                f"`{name}` RAISED instead of refusing: {message}"
            )


# THE TWO LINES THE RED CASES BELOW REWRITE, each isolating one half of the clause.
# The first is the range over the operator blocks: replacing its subject with an
# empty `dict` leaves the top-level read intact and narrows the refusal to
# `platform.operators.create` alone, which is the plausible implementation this
# step exists to rule out. The second is the guard the whole refusal sits behind.
THE_SUB_KEY_RANGE = "{{- range $name, $block := $operators -}}"
THE_SUB_KEY_RANGE_NARROWED = "{{- range $name, $block := dict -}}"
THE_OPERATORS_GUARD = "{{- if $operatorKeys -}}"
THE_OPERATORS_GUARD_OFF = "{{- if false -}}"


def chart_with_the_validate_line_rewritten(destination: Path, was: str, now: str) -> Path:
    """A copy of this chart with one line of `_validate.tpl` rewritten.

    THE NEEDLE IS ASSERTED BEFORE IT IS REPLACED, the way
    `test_breaking_the_guard_makes_the_default_render_refuse` does it: a red case
    whose mutation silently matched nothing would report a pass nobody earned.
    """
    copy = destination / "chart"
    shutil.copytree(CHART, copy)
    partial = copy / "templates" / "_validate.tpl"
    text = partial.read_text()
    assert text.count(was) == 1, (
        f"`{was}` occurs {text.count(was)} times in `_validate.tpl` and exactly one "
        f"was expected; this red case is now testing something else"
    )
    partial.write_text(text.replace(was, now, 1))
    return copy


def rendered(copy: Path, tmp_path: Path, name: str, body: str) -> subprocess.CompletedProcess[str]:
    return helm("template", "yadgar", str(copy), "-f", str(overlay(tmp_path / name, body)))


def test_a_refusal_that_read_the_top_level_key_alone_would_let_a_sub_key_through(
    tmp_path: Path,
) -> None:
    """THE NARROWING RED CASE, which is the one this step is really about.

    A refusal on `platform.operators.create` alone reads correct and is not: the
    `condition:` in `platform` accepts each sub-key on its own. This constructs
    exactly that narrowing — the range over the operator blocks is pointed at an
    empty `dict`, leaving the top-level read untouched — and shows the sub-key
    walking straight through it.

    BOTH ARMS ARE ASSERTED. If only the sub-key arm were, a mutation that broke the
    clause outright would satisfy this test while proving nothing about the
    narrowing; the top-level arm still refusing is what shows the mutation isolated
    the sub-key half rather than deleting the refusal.
    """
    copy = chart_with_the_validate_line_rewritten(
        tmp_path / "narrowed", THE_SUB_KEY_RANGE, THE_SUB_KEY_RANGE_NARROWED
    )

    through = rendered(
        copy,
        tmp_path,
        "narrowed-sub-key.yaml",
        operators_overlay(sub_key_block(THE_FIVE_OPERATOR_SUB_KEYS[0])),
    )
    assert through.returncode == 0, (
        "the narrowed refusal still refused a sub-key, so this red case is not "
        f"constructing the hole it claims to: {through.stderr}"
    )
    assert THE_OPERATORS_REFUSAL not in through.stderr, through.stderr

    still = rendered(copy, tmp_path, "narrowed-top-level.yaml", operators_overlay(TOP_LEVEL_BLOCK))
    assert still.returncode != 0, (
        "the narrowing deleted the refusal instead of narrowing it, so the arm "
        "above proves nothing about reading the top-level key alone"
    )
    assert THE_OPERATORS_REFUSAL in still.stderr, still.stderr


def test_removing_the_operators_refusal_lets_both_shapes_render(tmp_path: Path) -> None:
    """THE CLAUSE'S OTHER RED CASE: switch its guard off and both shapes render.

    This is what tells the six green assertions above apart from six renders that
    happened to fail for some other reason. With the guard off the overlays reach
    no refusal at all — the admin token is set and `platform.enabled` is true — so
    the parent renders the estate and admits a values file that fails mid-apply.
    """
    copy = chart_with_the_validate_line_rewritten(
        tmp_path / "removed", THE_OPERATORS_GUARD, THE_OPERATORS_GUARD_OFF
    )
    for name, block in [
        ("removed-top-level.yaml", TOP_LEVEL_BLOCK),
        ("removed-sub-key.yaml", sub_key_block(THE_FIVE_OPERATOR_SUB_KEYS[0])),
    ]:
        result = rendered(copy, tmp_path, name, operators_overlay(block))
        assert result.returncode == 0, (
            f"`{name}` still failed with the operators refusal switched off, so the "
            f"green cases above are not this clause's doing: {result.stderr}"
        )
        assert THE_OPERATORS_REFUSAL not in result.stderr, result.stderr


def test_the_operators_refusal_is_nil_safe_with_every_subchart_removed(tmp_path: Path) -> None:
    """The ADR-0787 clause over a tree with no subchart values, run rather than cited.

    IT NEEDS ITS OWN TEST RATHER THAN A FIFTH OVERLAY IN
    `test_the_refusals_are_nil_safe_with_every_subchart_removed`. That test asserts
    the admin-token phrase for every overlay it runs, and an operators-only overlay
    reaches no `platform.<name>.create` at all — the `$creating` guard stays shut,
    so the admin-token clause never runs and that assertion would fail on a
    correct chart.

    WHAT IS BEING PROVED IS THAT IT REFUSES RATHER THAN RAISES. `$platform.operators`
    is absent on this tree until the overlay supplies it, and a direct
    `.Values.platform.operators.certManager.create` would abort the render with a
    `nil pointer` instead of naming the key.
    """
    copy = chart_without_its_dependencies(tmp_path / "stripped")
    result = rendered(
        copy,
        tmp_path,
        "stripped-sub-key.yaml",
        operators_overlay(sub_key_block(THE_FIVE_OPERATOR_SUB_KEYS[0])),
    )
    assert result.returncode != 0, (
        "the operators clause refused nothing over a tree with no subchart values"
    )
    for raise_text in ("nil pointer", "can't evaluate field", "error calling"):
        assert raise_text not in result.stderr, (
            f"the operators clause RAISED instead of refusing: {result.stderr}"
        )
    assert THE_OPERATORS_REFUSAL in result.stderr, result.stderr
    assert (
        f"platform.operators.{THE_FIVE_OPERATOR_SUB_KEYS[0]}.create" in result.stderr
    ), result.stderr


def test_the_adopter_values_ask_for_no_operator() -> None:
    """ADR-0784 excludes `operators.create` from `example/values.yaml` BY NAME.

    R5 stays 81 and the register key is excluded, so the adopter file must carry no
    operators key of any kind. Asserted on the parsed file rather than on a grep,
    because a commented-out key is not a key and a nested one under another block
    is.

    THE REFUSAL IS WHAT WOULD ENFORCE IT ANYWAY, and that is the point of asserting
    it here rather than trusting it: an operators key added to this file makes
    every render of it refuse, which would redden
    `test_the_adopter_values_render_the_whole_platform_layer` with a message about
    a key nobody meant to add. This says so first, and by name.
    """
    values = yaml.safe_load(ADOPTER_VALUES.read_text())
    assert "operators" not in (values.get("platform") or {}), (
        f"`example/values.yaml` states a platform.operators block: "
        f"{(values.get('platform') or {}).get('operators')}. ADR-0784 excludes the "
        f"key by name and ADR-0787 makes it a `platform` release's key, never this "
        f"chart's."
    )


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

    FOUR OVERLAYS, ONE PER LEVEL THAT CAN BE ABSENT: no `bootstrap` block at all;
    `bootstrap` present with no `adminToken`; both present, where the absent level is
    `gateway.adminBootstrap`; and `bootstrap.iamKeys.create` true, which is the only
    one that evaluates the `iam-keys` clause and so the only one where
    `.Values.iam` — an absent subchart on this tree — is read at all. Each reaches a
    different `default` in the chain, and one overlay alone supplies the very levels
    the others leave out.
    """
    copy = chart_without_its_dependencies(tmp_path)
    overlays = {
        "no-bootstrap-block": "platform:\n  enabled: true\n  internalCA:\n    create: true\n",
        "bootstrap-without-its-token": "platform:\n  enabled: true\n"
        "  internalCA:\n    create: true\n  bootstrap:\n    create: true\n",
        "bootstrap-with-a-token": "platform:\n  enabled: true\n"
        "  internalCA:\n    create: true\n  bootstrap:\n    create: true\n"
        "    adminToken:\n      secretName: admin-bootstrap-token\n",
        "bootstrap-minting-the-iam-keys": "platform:\n  enabled: true\n"
        "  internalCA:\n    create: true\n  bootstrap:\n    create: true\n"
        "    iamKeys:\n      create: true\n",
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

        # THE FOURTH OVERLAY IS PINNED TO THE CLAUSE IT WAS ADDED FOR, and the
        # other three are deliberately left unpinned because no `iam-keys` clause
        # runs on them. Without this, all three assertions above are satisfied by
        # the admin-token clause alone: measured, making the whole `iam-keys`
        # clause unreachable left this test reporting 1 passed.
        if name == "bootstrap-minting-the-iam-keys":
            assert "platform.bootstrap.iamKeys.create is true" in result.stderr, result.stderr


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
