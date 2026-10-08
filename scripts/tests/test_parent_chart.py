"""What an adopter actually receives, asserted on the render rather than on an exit code.

EIGHT PROPERTIES, each one a thing that has already failed in this estate in some
form, or that ADR-0803 decided:

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
   `enabled` and `create` keys out of `chart/values.yaml` of the chart under
   review (ADR-0806). This repository's `chart/values.yaml` therefore has to
   state every toggle its defaults turn on, `gateway.gateway.enabled` included,
   and a local copy of the property is what tells a contributor WHY before CI
   does.

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

7. THE PLATFORM LAYER IS WHOLE WHEN IT IS ON AND ABSENT WHEN IT IS OFF.
   `platform` is the ninth dependency and the only one with a `condition`, so
   the modules-only render (`MODULES_ONLY_VALUES`) must be unchanged by its
   arrival — `EXPECTED` below does not move, and the assertion that it did not is
   the load-bearing one. What IS counted is the ADOPTER-values render,
   `example/values.yaml`, where every `platform.*.create` is true: its object
   set, its renewal ladder, its RBAC triples and the agreement between each
   preflight probe and the toggle that renders what the probe probes. ADR-0777 is
   the record for the template that carries the parent's own refusals.

8. THE DEFAULTS ARE THE WHOLE ESTATE (ADR-0803 step B6, decision 2). The parent
   with no values file, `chart/ci/values.yaml`'s twelve `tls.enabled` switches
   riding along (ruling 11, ADR-0845 — the parent's own `values.yaml` states
   none of them), renders exactly what the adopter values render (K1), and
   refuses offline without the four API versions `chart/ci/api-versions.txt`
   declares (K2) — the file every shared gate reads (ADR-0806).

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
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
CHART = REPO / "chart"

# WHAT THE EIGHT MODULES ALONE ARE — the render of `MODULES_ONLY_VALUES`, which
# was the default install until ADR-0803 step B6 — measured 2026-09-19 on helm
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
# `condition`, `platform.enabled`, which `MODULES_ONLY_VALUES` sets false. So that
# render gains no object — and no hook Job either, though `helm template` does
# emit hooks. B6 moved the DEFAULTS to the whole estate and did not move this
# dict: re-measured 2026-09-27 on helm 3.18.4 and 4.3.0 over
# `MODULES_ONLY_VALUES`, 32 objects, the same six kinds. Re-measured 2026-09-24 on helm 3.18.4 and 4.3.0 with `platform`
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
# `example/values.yaml` beside this chart. It states the platform layer on — every
# `platform.*.create` true, `autoscaling.enabled` true in all seven modules, and
# `database.create` true in the three `-db` modules. Since ADR-0803 step B6 those
# are also the chart's DEFAULTS, and K1 in section 8 holds the two renders equal;
# the example adds only the edge issuer an adopter must name.
ADOPTER_VALUES = REPO / "example" / "values.yaml"

# `chart/ci/values.yaml` (ruling 11, ADR-0845, K-8's "fixture" step): the twelve
# `tls.enabled` read switches, explicit, because the parent's OWN defaults do not
# and will not state them — a per-repository contract (C-SVb, C-DB1) requires
# each one with no default once it lands, and a parent default would be a tenth
# writer for a value that has to come from the adopter. `example/values.yaml`
# states the same twelve explicitly for the same reason (`ADOPTER_ONLY_KEYS`
# below), so most renders over `ADOPTER_VALUES` already carry them; this constant
# is for the renders in this suite that do not — a plain default render, or one
# built over `MODULES_ONLY_VALUES` before it also named them — so that THIS
# suite does not go red the moment a module's own chart starts refusing the key
# it already declares with a default today.
EXPLICIT_TLS = CHART / "ci" / "values.yaml"

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
# absent from the modules-only render. A MODULE release that adds or drops an object
# moves BOTH, since every module renders in both. Update whichever moved in the
# same commit as the pin, and say in the pull request which chart moved it.
ADOPTER_EXPECTED = {
    "Certificate": 14,
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
ADOPTER_OBJECTS = 83

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
# Jobs, two triples and 79 objects. So one flip reddens these two constants,
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
# RoleBinding and its ServiceAccount — one each, which is why 83 becomes 79.
OBJECTS_PER_PROBE_JOB = 4

# THE RENEWAL LADDER, lifted from `yadgarhq/platform`'s own `test_ladder.py` to the
# whole-estate render. The invariant is that every leaf's `renewBefore` is
# DISTINCT and six hours from its neighbour, so at most one service restarts per
# renewal instant.
#
# FOURTEEN OBJECTS AND THIRTEEN VALUES, and the difference is exactly one object
# contributing no rung: the CA root. It carries a `renewBefore` of its own — one
# year against a ten-year duration — and nothing mounts it as a serving or client
# credential, so its renewal re-signs with the same key rather than restarting a
# service. The set is scoped to the Certificates that are not `isCA`.
CERTIFICATES_AT_R5 = 14
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
    "786h",
    "792h",
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
#
# FOUR SINCE ADR-0820. `platform` 0.1.21 added a `prometheus` arm to the same
# pre-install `preflight` Job, off unless stated like `keda`, and this parent
# states it true beside the modules' `autoscaling.enabled`. It pairs with the
# same toggle `keda` does: a ScaledObject needs both KEDA and the Prometheus it
# queries.
AGREEMENT_PAIRS_AT_R5 = 4

# The operator each probe names in the rendered script, and the kind whose
# presence in the same render is the other half of the pair.
PROBE_OPERATOR = {
    "certManager": "cert-manager", "keda": "keda", "mariadb": "mariadb-operator", "prometheus": "prometheus",
}
PROBE_KIND = {"certManager": "Certificate", "keda": "ScaledObject", "mariadb": "MariaDB", "prometheus": "ScaledObject"}
PROBE_TOGGLE = {
    "certManager": "platform.internalCA.create, platform.certificates.create or platform.edgeTLS.create",
    "keda": "autoscaling.enabled in the module charts",
    "mariadb": "database.create in the three `-db` charts",
    "prometheus": "autoscaling.enabled in the module charts",
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


# THE MODULES ALONE: what an adopter who runs their own platform layer writes, and
# what this chart's defaults WERE before ADR-0803 step B6 made them the whole
# estate. Since ADR-0807 `platform.enabled` false alone turns the platform layer
# off (`OPT_OUT_VALUES`); every `create` the defaults set true is ALSO set false
# here so this file stays byte-for-byte the pre-B6 defaults, and so is every
# toggle that needs an operator.
# `gateway.gateway.enabled` stays true — Gateway API is a specification, and D80
# permits it on (`EXPECTED` counts its HTTPRoute).
#
# TWO NON-TOGGLES RETURN TO THE CHILDREN'S OWN DEFAULTS as well, so the refusal
# tests that overlay this file start from exactly the pre-B6 defaults.
# `gateway.adminBootstrap.tokenSecret` is cleared: with no `platform.bootstrap`
# nothing mints that Secret, and the gateway chart refuses to boot on a named
# Secret it cannot read — clearing it is that chart's own instruction. The two
# preflight probes go back to `platform`'s false.
#
# A LITERAL, NOT A FLIP OF `chart/values.yaml`. A derived file follows whatever
# the defaults become; this one is what an adopter actually has to write, and the
# refusal tests that render over it stay about the refusal they name.
MODULES_ONLY_VALUES = """\
gateway:
  adminBootstrap:
    tokenSecret: ""
  autoscaling:
    enabled: false
platform:
  enabled: false
  preflight:
    probes:
      keda: false
      mariadb: false
  internalCA:
    create: false
  certificates:
    create: false
  edgeTLS:
    create: false
  gatewayListener:
    create: false
  valkey:
    create: false
  nats:
    create: false
  bootstrap:
    create: false
    iamKeys:
      create: false
iam:
  autoscaling:
    enabled: false
iam-db:
  autoscaling:
    enabled: false
  database:
    create: false
project:
  autoscaling:
    enabled: false
project-db:
  autoscaling:
    enabled: false
  database:
    create: false
task:
  autoscaling:
    enabled: false
task-db:
  autoscaling:
    enabled: false
  database:
    create: false
"""


def modules_only_file(directory: Path) -> Path:
    """`MODULES_ONLY_VALUES` on disk in `directory`, for a `-f` ahead of any overlay."""
    path = directory / "modules-only.yaml"
    path.write_text(MODULES_ONLY_VALUES)
    return path


@pytest.fixture(scope="module")
def modules_only(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return modules_only_file(tmp_path_factory.mktemp("modules-only"))


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


def test_the_parent_declares_no_templates_of_its_own(tmp_path: Path, modules_only: Path) -> None:
    """Every rendered object comes from a subchart, asserted by removing them all.

    OVER `MODULES_ONLY_VALUES`, because the defaults set `platform.*.create` true
    and the parent's refusals then read subchart values this tree does not have.
    `test_the_refusals_are_nil_safe_with_every_subchart_removed` covers that side.
    """
    assert render(str(chart_without_its_dependencies(tmp_path)), "-f", str(modules_only)) == [], (
        "this parent rendered an object of its own with every subchart removed. "
        "ADR-0723's revisit_trigger names that as a module nobody declared."
    )


# THE ONE NON-PARTIAL THIS DIRECTORY MAY HOLD, BY NAME. ADR-0777 is the ruling
# that put it there and the reason it is a name rather than a predicate: a test
# amended to `name.startswith("_") or name.endswith(".yaml")` would permit every
# future object template silently, which is the property this test exists to hold.
# A second non-partial needs its own ruling and its own line here.
PERMITTED_NON_PARTIALS = {"validate.yaml"}


def test_the_templates_directory_holds_only_partials(tmp_path: Path, modules_only: Path) -> None:
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

    TWICE, ONE RENDER PER SIDE OF THE `create` GUARD. Over `MODULES_ONLY_VALUES`
    the guard in `_validate.tpl` is shut. At the DEFAULTS it is open, because
    ADR-0803 step B6 set every `create` true — so an object added inside that
    guard shows only in the second render. `iam.keysSecret` is set because the
    stripped tree has no `iam` defaults, and the `iam-keys` refusal would
    otherwise fire; that is the one value the defaults leave to a child.
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
    failures = parent_emissions(chart_without_its_dependencies(tmp_path), modules_only)
    assert failures == [], "\n".join(failures)


# THE ONE VALUE THE GUARD-OPEN RENDER OF THE STRIPPED TREE NEEDS: `iam`'s own
# default for the Secret it mounts, which the stripped tree does not carry.
GUARD_OPEN_SETS = ("--set", "iam.keysSecret=iam-keys")


def parent_emissions(copy: Path, modules_only: Path) -> list[str]:
    """Every object the dependency-stripped parent emits, per side of the `create` guard.

    Each failure names the template from helm's `# Source:` line, so an object that
    `validate.yaml` grew is reported against `validate.yaml`.
    """
    failures = []
    for side, arguments in (
        ("guard shut (MODULES_ONLY_VALUES)", ("-f", str(modules_only))),
        ("guard open (the defaults)", GUARD_OPEN_SETS),
    ):
        result = helm("template", "yadgar", str(copy), *arguments)
        if result.returncode != 0:
            failures.append(f"{side}: the stripped parent did not render: {result.stderr}")
            continue
        sources = sorted(set(re.findall(r"^# Source: (\S+)$", result.stdout, re.MULTILINE)))
        documents = [
            document
            for document in yaml.safe_load_all(result.stdout)
            if isinstance(document, dict) and document.get("apiVersion")
        ]
        if documents:
            failures.append(
                f"{side}: `chart/templates/` holds a non-partial that EMITTED "
                f"{len(documents)} OBJECT(S), from {sources}. "
                f"{sorted(PERMITTED_NON_PARTIALS)} is permitted here on the stated "
                f"ground that it renders nothing (ADR-0777)."
            )
    return failures


def test_an_object_inside_the_create_guard_reddens_the_emits_nothing_gate(
    tmp_path: Path, modules_only: Path
) -> None:
    """THE RED CASE: an object in `validate.yaml` behind a `create`, seen only with the guard open."""
    copy = chart_without_its_dependencies(tmp_path)
    template = copy / "templates" / "validate.yaml"
    template.write_text(
        template.read_text()
        + "\n{{- if .Values.platform.internalCA.create }}\n---\n"
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: leaked\n{{- end }}\n"
    )
    failures = parent_emissions(copy, modules_only)
    assert len(failures) == 1, failures
    assert failures[0].startswith("guard open") and "yadgar/templates/validate.yaml" in failures[0], failures


def test_helm_lint_strict_passes() -> None:
    result = helm("lint", "--strict", str(CHART), "-f", str(EXPLICIT_TLS))
    assert result.returncode == 0, result.stdout + result.stderr


# --------------------------- 2. the packaged artifact, and it matches the tree


def test_the_packaged_chart_renders_the_whole_estate(packaged: Path, modules_only: Path) -> None:
    """The package an adopter downloads, at its defaults and with the platform layer off."""
    assert dict(kinds(render(str(packaged), *API_VERSIONS, "-f", str(EXPLICIT_TLS)))) == ADOPTER_EXPECTED
    assert dict(kinds(render(str(packaged), "-f", str(modules_only), "-f", str(EXPLICIT_TLS)))) == EXPECTED


def test_platform_enabled_false_removes_the_whole_platform_layer(modules_only: Path) -> None:
    """THE LOAD-BEARING ASSERTION OF ADR-0777, stated on the DIRECTORY and directly.

    `platform` is the ninth dependency and the only one with a `condition`,
    `platform.enabled`. An adopter who runs their own platform layer sets it false
    — with every `create` false too, see `MODULES_ONLY_VALUES` — and must then get
    the eight modules and not one object or hook Job of `platform`.

    BEFORE ADR-0803 STEP B6 THIS WAS THE DEFAULT RENDER. The defaults are now the
    whole estate, so the same equality is asserted over the values an adopter
    writes to get the old default back, and it needs no `--api-versions`: nothing
    in it asks for an operator.
    """
    assert dict(kinds(render(str(CHART), "-f", str(modules_only), "-f", str(EXPLICIT_TLS)))) == EXPECTED, (
        "the modules-only render moved. `platform` sits behind `condition: "
        "platform.enabled`, which that render sets false, so it must contribute no "
        "object and no hook Job. ADR-0777: a step that adds an object to `platform` "
        "moves `ADOPTER_EXPECTED` and not this."
    )


def test_the_directory_and_the_package_render_the_same_objects(packaged: Path, modules_only: Path) -> None:
    """An adopter installs the package. A property true only of the tree is not a property."""
    assert identities(render(str(CHART), *API_VERSIONS, "-f", str(EXPLICIT_TLS))) == identities(
        render(str(packaged), *API_VERSIONS, "-f", str(EXPLICIT_TLS))
    )
    assert identities(render(str(CHART), "-f", str(modules_only), "-f", str(EXPLICIT_TLS))) == identities(
        render(str(packaged), "-f", str(modules_only), "-f", str(EXPLICIT_TLS))
    )


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
    # PROMETHEUS JOINED AT `platform` 0.1.21 (ADR-0820), behind
    # `operators.prometheus.create,operators.create` like the other operators. The
    # prometheus chart vendors its own four subcharts; `platform` turns all four
    # off, and they are packaged all the same.
    "yadgar/charts/platform/charts/prometheus/Chart.yaml",
    "yadgar/charts/platform/charts/prometheus/charts/alertmanager/Chart.yaml",
    "yadgar/charts/platform/charts/prometheus/charts/kube-state-metrics/Chart.yaml",
    "yadgar/charts/platform/charts/prometheus/charts/prometheus-node-exporter/Chart.yaml",
    "yadgar/charts/platform/charts/prometheus/charts/prometheus-pushgateway/Chart.yaml",
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
        documents = render(target, *API_VERSIONS, "-f", str(EXPLICIT_TLS), "-f", str(values))
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
    documents = render(str(packaged), *API_VERSIONS, "-f", str(EXPLICIT_TLS), "-f", str(values))

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


# PASS 1 flips every BOOLEAN key named `enabled` or `create` in `chart/values.yaml`,
# exactly as `d80_portability.py` in `yadgarhq/actions` does since ADR-0806, and
# renders with NO `--api-versions`: the all-off render is the bare-cluster proof,
# and a bare cluster declares nothing. Nine `enabled` today —
# `gateway.gateway.enabled`, `platform.enabled` and seven `autoscaling.enabled` —
# and eleven `create`: eight in `platform` and one `database.create` in each of the
# three `-db` charts. Asserted as equalities rather than floors, because a key that
# stops being read is exactly the way this gate goes green over nothing.
ENABLED_KEYS_IN_THE_PARENTS_VALUES = 9
CREATE_KEYS_IN_THE_PARENTS_VALUES = 11


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


def all_off() -> tuple[dict, list[str], list[str]]:
    """`chart/values.yaml` with every `enabled` and every `create` false, and the paths flipped."""
    values = yaml.safe_load((CHART / "values.yaml").read_text()) or {}
    enabled = flip_every(values, "enabled", False)
    created = flip_every(values, "create", False)
    return values, enabled, created


def test_every_crd_bearing_resource_can_be_switched_off(tmp_path: Path) -> None:
    """The property `ci-pr.yaml`'s `portability` job asserts, proved here too — TWICE.

    PASS 1 — every `enabled` and every `create` in `chart/values.yaml` false, and no
    `--api-versions`. That job reads the toggles out of THAT FILE and nothing else,
    so a toggle the defaults turn on that the file does not state is a resource an
    adopter cannot be shown to switch off. This is what says so locally, before CI
    does.

    PASS 2 — the same file with `platform.enabled` held TRUE. Pass 1 cannot tell a
    `create` toggle that works from one that does nothing: `platform.enabled` false
    removes the whole subchart, so every object behind a `create` is absent either
    way. Holding `platform.enabled` true is the render in which each `create` is
    the only thing standing between the chart and a CRD-bearing object. It needs
    the declared `--api-versions`, because `platform`'s preflight probes ask for
    operators even with every `create` off.
    """
    # ── PASS 1 ───────────────────────────────────────────────────────────────
    off, enabled, created = all_off()
    assert len(enabled) == ENABLED_KEYS_IN_THE_PARENTS_VALUES, (
        f"`chart/values.yaml` declares {len(enabled)} `enabled` key(s) and this gate "
        f"expects {ENABLED_KEYS_IN_THE_PARENTS_VALUES}: {enabled}. The `portability` "
        f"job's all-off render reads that file and nothing else, so a key that left "
        f"it is a resource an adopter can no longer be shown to switch off. See the "
        f"comment in that file."
    )
    assert len(created) == CREATE_KEYS_IN_THE_PARENTS_VALUES, (
        f"`chart/values.yaml` declares {len(created)} `create` key(s) and this gate "
        f"expects {CREATE_KEYS_IN_THE_PARENTS_VALUES}: {created}. NOT ALL of them are "
        f"then PROVED switchable by pass 2: some render no CRD-bearing object at all "
        f"— `bootstrap.iamKeys.create` among them — and for those this count is the "
        f"whole of the coverage."
    )

    values = tmp_path / "all-off.yaml"
    values.write_text(yaml.safe_dump(off))
    survivors = crd_bearing(render(str(CHART), "-f", str(EXPLICIT_TLS), "-f", str(values)))
    assert survivors == [], f"these resources survived the all-off render: {survivors}"

    # ── PASS 2 ───────────────────────────────────────────────────────────────
    off["platform"]["enabled"] = True
    held = tmp_path / "creates-off.yaml"
    held.write_text(yaml.safe_dump(off))
    survivors = crd_bearing(render(str(CHART), *API_VERSIONS, "-f", str(EXPLICIT_TLS), "-f", str(held)))
    assert survivors == [], (
        f"these resources survived the render with `platform.enabled` held true and "
        f"every `create` false: {survivors}. A CRD-bearing object behind no toggle an "
        f"adopter can reach is what D80 forbids."
    )


def test_a_create_toggle_that_cannot_be_switched_off_reddens_the_second_pass(tmp_path: Path) -> None:
    """PASS 2'S RED CASE: one `create` stays true and its objects survive.

    This is the shape of a `create` toggle that the all-off pass cannot reach.
    `internalCA.create` is the stand-in because its objects are
    `cert-manager.io/v1`, outside every built-in group, so `crd_bearing` sees them.
    """
    off, _, _ = all_off()
    off["platform"]["enabled"] = True
    off["platform"]["internalCA"]["create"] = True

    values = tmp_path / "one-create-stuck-on.yaml"
    values.write_text(yaml.safe_dump(off))
    survivors = crd_bearing(render(str(CHART), *API_VERSIONS, "-f", str(EXPLICIT_TLS), "-f", str(values)))
    assert survivors != [], (
        "a `create` toggle was left true and the second pass found no CRD-bearing "
        "survivor, so it is passing over a render it never examined"
    )
    assert {kind for _, kind, _ in survivors} == {"Issuer", "Certificate"}, survivors


def test_a_toggle_left_on_reddens_the_first_pass(tmp_path: Path) -> None:
    """PASS 1'S RED CASE: one default the flip missed, and its object survives.

    `task-db.database.create` held true over the all-off file stands in for a toggle
    the defaults turn on under a key the flip does not reach. Rendered with the
    declared API versions so the MariaDB check lets the object through: a bare
    render would refuse outright, which also fails the job, but for a reason this
    test does not examine.
    """
    off, _, _ = all_off()
    off["task-db"]["database"]["create"] = True
    values = tmp_path / "one-default-left-on.yaml"
    values.write_text(yaml.safe_dump(off))
    survivors = crd_bearing(render(str(CHART), *API_VERSIONS, "-f", str(EXPLICIT_TLS), "-f", str(values)))
    assert [kind for _, kind, _ in survivors] == ["MariaDB"], survivors



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
    documents = render(str(packaged), *API_VERSIONS, "-f", str(EXPLICIT_TLS))
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


_STARTSWITH = re.compile(r"^startsWith\((?P<reference>[\w.]+),\s*'(?P<prefix>[^']*)'\)$")


def _admits(condition: str, context: dict[str, str], job: str) -> bool:
    """Would GitHub run `job` with this `if:`, in this event context?

    DELIBERATELY NOT A GENERAL EXPRESSION PARSER, and not a port of
    `ci_verdict.py` from `yadgarhq/actions` either — that file is the merge
    gate's verdict over `ci-pr.yaml`'s conditions and has no business being
    duplicated here. This models the shapes `push_validation` and
    `tag_validation` actually use: `||`-joined groups of `&&`-joined clauses,
    each clause either `github.<field> == '<literal>'` or
    `startsWith(github.<field>, '<literal>')`. A condition that grows past
    that shape REFUSES here rather than being approximated, because an
    evaluator that silently mis-reads a condition is worse than none.

    ADMISSION IS NOT MODELLED AND DOES NOT NEED TO BE. The implicit check
    `test_ci_release_skip_propagation.py` in `yadgarhq/actions` documents applies
    to a job whose `needs:` ancestors did not all conclude `success`, and both
    jobs below are asserted to declare no `needs:` at all — which is why
    neither can be skipped by an ancestor the way that repository's `parent`
    job was.
    """
    return any(_admits_every_clause(group, context, job) for group in condition.split("||"))


def _admits_every_clause(condition: str, context: dict[str, str], job: str) -> bool:
    """The `&&`-joined half of `_admits`: every clause in `condition` must admit."""
    for clause in condition.split("&&"):
        clause = clause.strip()
        starts_with = _STARTSWITH.match(clause)
        if starts_with:
            reference, prefix = starts_with["reference"], starts_with["prefix"]
            assert reference in context, (
                f"`{job}`'s condition reads `{reference}`, which this test does "
                f"not model. Add it to every context below, with the value each "
                f"event really carries."
            )
            if not context[reference].startswith(prefix):
                return False
            continue
        left, operator, right = clause.partition("==")
        assert operator == "==", (
            f"`{job}`'s condition contains a clause this test cannot "
            f"evaluate: {clause!r}. Extend `_admits` deliberately rather "
            f"than letting the condition go unchecked."
        )
        reference = left.strip()
        assert reference in context, (
            f"`{job}`'s condition reads `{reference}`, which this test does "
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
        assert _admits(condition, context, PUSH_JOB) is expected, (
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


def test__admits_evaluates_an_or_of_and_groups() -> None:
    """THE `||` EXTENSION. `tag_validation`'s own condition needs none today, but
    `_admits` must not quietly keep approximating a condition that later grows
    one — the shape both jobs below actually use is `||`-joined AND-groups.
    """
    condition = (
        "github.event_name == 'push' && github.ref == 'refs/heads/main' "
        "|| github.event_name == 'workflow_dispatch'"
    )
    pushed_to_main = {"github.event_name": "push", "github.ref": "refs/heads/main"}
    dispatched = {"github.event_name": "workflow_dispatch", "github.ref": "refs/heads/other"}
    neither = {"github.event_name": "pull_request", "github.ref": "refs/heads/main"}
    assert _admits(condition, pushed_to_main, "test") is True
    assert _admits(condition, dispatched, "test") is True
    assert _admits(condition, neither, "test") is False


def test__admits_evaluates_startswith() -> None:
    """THE `startsWith(...)` EXTENSION: `tag_validation`'s own condition."""
    condition = "startsWith(github.ref, 'refs/tags/')"
    assert _admits(condition, {"github.ref": "refs/tags/v0.3.54"}, "test") is True
    assert _admits(condition, {"github.ref": "refs/heads/main"}, "test") is False


# THE JOB `release` NEEDS BEFORE IT PUBLISHES (ledger 1137's `tag_validation`).
# `release` fires on the tag with no `needs:` today, and measured on `adf30008`
# it SUCCEEDED while every `main / *` validation job skipped — so nothing walls
# the one commit a tag publishes. `tag_validation` walls RENDER REFUSALS ONLY:
# `helm dependency update`, `helm lint --strict` on the fixture, `helm template`
# over the directory and the package, and `scripts/tests/test_tag_wall.py` —
# a dedicated file rather than a marker expression, ruled by Max after ledger
# 837's `no-test-skips` hook refused the marker-narrowed invocation outright
# (it forbids any `-m`/`-k`/`--deselect` narrowing, estate-wide, no exemption)
# but explicitly permits a positional path or filename argument: "no scan can
# tell a directory that IS the suite from one that is a slice of it". That file's own
# `test_this_file_pulls_no_published_pin_and_asserts_no_count_literal` is what
# keeps running it alone honest.
TAG_JOB = "tag_validation"
TAG_WALL_FILE = "scripts/tests/test_tag_wall.py"


def test_the_tag_job_admits_a_push_to_a_tag_and_refuses_everything_else() -> None:
    """MEASURED BY EVALUATION, same proof as `push_validation`'s own test above."""
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    assert TAG_JOB in jobs, (
        f"`{TAG_JOB}` is not a job in {WORKFLOW.name}. It is the wall `release` "
        f"needs before it publishes."
    )
    job = jobs[TAG_JOB]
    condition = str(job["if"])

    cases = [
        ({"github.event_name": "push", "github.ref": "refs/tags/v0.3.54"}, True),
        ({"github.event_name": "push", "github.ref": "refs/heads/main"}, False),
        ({"github.event_name": "pull_request", "github.ref": "refs/pull/42/merge"}, False),
    ]
    for context, expected in cases:
        assert _admits(condition, context, TAG_JOB) is expected, (
            f"`{TAG_JOB}`'s condition `{condition}` evaluates to "
            f"{not expected} for {context}, and it must be {expected}."
        )

    assert not job.get("needs"), (
        f"`{TAG_JOB}` declares `needs: {job.get('needs')}`. `release` today has "
        f"none at all, and this job must not be skippable by an ancestor either."
    )


def test_the_release_job_needs_the_tag_job() -> None:
    """THE WALL ONLY MATTERS IF `release` CANNOT RUN WITHOUT IT. Measured on
    `adf30008`: `release / chart` SUCCEEDED while every `main / *` validation
    job skipped, because nothing in `release`'s own definition depended on one.
    """
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    needs = jobs["release"].get("needs")
    needed = {needs} if isinstance(needs, str) else set(needs or [])
    assert TAG_JOB in needed, (
        f"`release` declares `needs: {needs}`, which does not include `{TAG_JOB}`. "
        f"A red tag gate must block the publish, not just report one."
    )

    # `needs:` GATES ON `success()` ONLY WHEN `release`'s OWN `if:` CALLS NO
    # STATUS FUNCTION ITSELF — the same rule `push_validation`'s and
    # `tag_validation`'s own headers document. `if: always() && startsWith(...)`
    # would keep `release`'s condition true regardless of `tag_validation`'s
    # result, running it even after a red tag gate — `needs:` without it would
    # be decoration.
    condition = str(jobs["release"]["if"])
    for status_function in ("always(", "success(", "failure(", "cancelled("):
        assert status_function not in condition, (
            f"`release`'s condition `{condition}` calls `{status_function}`, "
            f"which overrides the implicit `success()` gate `needs: {TAG_JOB}` "
            f"otherwise adds — a red `{TAG_JOB}` would no longer block the publish."
        )


def _tag_wall_run_script(jobs: dict) -> str:
    """The `run:` text of `tag_validation`'s main step, comment lines stripped. PURE.

    READ OFF THE LOADED STRING DIRECTLY, never re-dumped through
    `yaml.safe_dump`: the dumper folds a long scalar at its default width and
    re-escapes an embedded `"` as `\\"` when it picks a double-quoted style,
    either of which can split or hide a fragment this check looks for — both
    measured the hard way in an earlier draft of this test. The string
    `yaml.safe_load` hands back has neither problem.

    COMMENTS STRIPPED, so a fragment the job no longer RUNS cannot hide behind
    a comment that still merely MENTIONS it — this file's own header, for
    one, describes the first draft's marker expression in prose.
    """
    job = jobs[TAG_JOB]
    step = next(s for s in job["steps"] if "run" in s and TAG_WALL_FILE in s["run"])
    return "\n".join(
        line for line in step["run"].splitlines() if not line.strip().startswith("#")
    )


def test_the_tag_job_runs_the_render_refusals_and_the_dedicated_suite() -> None:
    """THE WALL'S BODY, asserted loosely so a future edit cannot gut it while the
    condition and `needs:` assertions above stay green.
    """
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    script = _tag_wall_run_script(jobs)
    for fragment in (
        "helm dependency update chart",
        "helm lint --strict chart -f chart/ci/values.yaml",
        "helm template",
        "chart/ci/api-versions.txt",
        TAG_WALL_FILE,
    ):
        assert fragment in script, (
            f"`{TAG_JOB}` no longer runs `{fragment}`. It walls render refusals "
            f"only: dependency resolution, the strict lint on the fixture, the "
            f"fixture render over the directory and the package with the API "
            f"versions `chart/ci/api-versions.txt` declares, and `{TAG_WALL_FILE}`."
        )
    assert "set -euo pipefail" in script, (
        f"`{TAG_JOB}` no longer sets `-euo pipefail`; a render refusal or a "
        f"failing test partway through the script would go unnoticed."
    )
    assert "|| true" not in script, (
        f"`{TAG_JOB}` suppresses a command's exit code with `|| true`, which "
        f"would let a render refusal or a failing test pass this wall."
    )
    # A MARKER EXPRESSION HAS NO BUSINESS HERE — see the job's own header
    # comment for why (ledger 837's `no-test-skips`). `TAG_WALL_FILE` being a
    # positional argument is what the hook itself exempts; the dedicated
    # file's own `test_this_file_pulls_no_published_pin_and_asserts_no_count_literal`
    # is the gate that keeps running it alone honest, not a second scan here.
    assert "pinned" not in script, (
        f"`{TAG_JOB}` references `pinned`, the fixture that pulls the parent's "
        f"own published pin. The tag job renders HEAD's own version; it never "
        f"pulls that."
    )


# ------------- 7. the platform layer: whole when on, absent when off, refused when half-on


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

    A fifteenth entry in `certificates.leaves` is the constructible stand-in for
    an object entering the platform layer: the chart renders one Certificate per
    entry, so the render grows by exactly one and the equality has to fail.
    """
    values = overlay(
        tmp_path / "a-fifteenth-leaf.yaml",
        "platform:\n"
        "  certificates:\n"
        "    leaves:\n"
        "      fifteenth-tls:\n"
        "        commonName: fifteenth\n"
        "        clusterLocalNames: true\n"
        "        usages: [server auth, digital signature]\n"
        "        renewBefore: 798h\n",
    )
    documents = adopter_render("-f", str(values))
    assert len(documents) == ADOPTER_OBJECTS + 1, (
        "a fifteenth leaf did not add an object, so this red case is testing nothing"
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


def test_a_fifteenth_certificate_reddens_the_ladder_gate(tmp_path: Path) -> None:
    """THE LADDER GATE'S RED CASE: a fifteenth leaf, and the equality names both numbers."""
    values = overlay(
        tmp_path / "a-fifteenth-leaf.yaml",
        "platform:\n"
        "  certificates:\n"
        "    leaves:\n"
        "      fifteenth-tls:\n"
        "        commonName: fifteenth\n"
        "        clusterLocalNames: true\n"
        "        usages: [server auth, digital signature]\n"
        "        renewBefore: 798h\n",
    )
    failures = ladder_failures(
        adopter_render("-f", str(values)), CERTIFICATES_AT_R5, LADDER
    )
    assert failures, "a fifteenth Certificate did not redden the ladder gate"
    assert "expected 14 Certificate objects, found 15" in "\n".join(failures), failures


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
    "prometheus": "platform:\n  preflight:\n    probes:\n      prometheus: false\n"
    + "".join(
        f"{module}:\n  autoscaling:\n    enabled: false\n"
        for module in AUTOSCALING_MODULES
    ),
}


# ── the Prometheus the preflight probes is the one every ScaledObject queries ──
#
# ADR-0780's shape: two charts each carry one half of an agreement no single chart
# can see. `platform`'s preflight probes `preflight.prometheus.address`, and each
# of the seven module charts points its ScaledObject at its own
# `autoscaling.prometheusAddress`. Both default to the same URL today; an adopter
# who moves one and not the other gets a probe that passes against a server no
# ScaledObject asks. Read off the RENDER, the script and the triggers.

PROMETHEUS_ADDRESS_LINE = re.compile(r"^PROMETHEUS_ADDRESS='(?P<address>[^']*)'$", re.MULTILINE)


def prometheus_address_failures(documents: list[dict]) -> list[str]:
    """The preflight's Prometheus address and every ScaledObject's must be one. PURE."""
    jobs = [d for d in documents if d.get("kind") == "Job" and d["metadata"]["name"] == "preflight"]
    if len(jobs) != 1:
        return [f"{len(jobs)} `preflight` Jobs render"]
    script = "\n".join(jobs[0]["spec"]["template"]["spec"]["containers"][0]["args"])
    found = PROMETHEUS_ADDRESS_LINE.search(script)
    if found is None:
        return ["the preflight script carries no PROMETHEUS_ADDRESS, so the prometheus arm is off"]
    probed = found.group("address")
    queried = {
        d["metadata"]["name"]: [t["metadata"].get("serverAddress") for t in d["spec"]["triggers"] if t.get("type") == "prometheus"]
        for d in documents
        if d.get("kind") == "ScaledObject"
    }
    failures = []
    if sorted(queried) != sorted(AUTOSCALING_MODULES):
        failures.append(f"ScaledObjects render for {sorted(queried)}, not the seven modules")
    failures += [
        f"`{name}` queries {addresses} and the preflight probes {probed}"
        for name, addresses in sorted(queried.items())
        if addresses != [probed]
    ]
    return failures


def test_the_preflight_probes_the_prometheus_every_scaled_object_queries() -> None:
    assert prometheus_address_failures(adopter_render()) == []


@pytest.mark.parametrize(
    ("body", "named"),
    [
        ("gateway:\n  autoscaling:\n    prometheusAddress: http://prometheus.elsewhere:9090\n", "`gateway` queries"),
        (
            "platform:\n  preflight:\n    prometheus:\n      address: http://prometheus.elsewhere:9090\n",
            "the preflight probes http://prometheus.elsewhere:9090",
        ),
        ("platform:\n  preflight:\n    probes:\n      prometheus: false\n", "the prometheus arm is off"),
    ],
    ids=["one-module-moved", "the-probe-moved", "the-arm-off"],
)
def test_a_prometheus_address_that_disagrees_reddens_the_address_gate(tmp_path: Path, body: str, named: str) -> None:
    documents = adopter_render("-f", str(overlay(tmp_path / "prometheus.yaml", body)))
    failures = prometheus_address_failures(documents)
    assert failures and all(named in failure for failure in failures), failures


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

    THE OVERLAY IS APPLIED OVER `MODULES_ONLY_VALUES`, not over the defaults. Since
    ADR-0803 step B6 the defaults ARE the whole estate, every `create` true and the
    admin token named, so a red case written over them reaches the refusal it
    names only by accident. `MODULES_ONLY_VALUES` is the pre-B6 defaults, and every
    refusal below sets the `platform.*.create` it needs EXPLICITLY on top.

    `EXPLICIT_TLS` RIDES IN BETWEEN THE TWO (ruling 11, K-8): `MODULES_ONLY_VALUES`
    states no `tls.enabled`, so a module chart that starts refusing an absent one
    would redden every refusal test below for a reason none of them names. A red
    case that itself sets a `tls` key still wins — it is the last `-f`.
    """
    values = overlay(tmp_path / f"{name}.yaml", body)
    result = helm(
        "template",
        "yadgar",
        str(CHART),
        *API_VERSIONS,
        "-f",
        str(modules_only_file(tmp_path)),
        "-f",
        str(EXPLICIT_TLS),
        "-f",
        str(values),
    )
    assert result.returncode != 0, (
        f"`{name}` rendered exit 0. The parent was supposed to refuse it.\n"
        f"{result.stdout[:2000]}"
    )
    return result.stderr


# THE SAME SHAPE FOR `iam-keys`, AND ONLY ONE SIDE OF IT IS A KEY. The bootstrap
# Job mints the name as a LITERAL in its script; `iam` mounts `iam.keysSecret`,
# which is a value. So the red case renames the mounted side alone — there is no
# minted side to rename — and the overlay below is the ONE place both names meet.
#
# THE NAME THE REFUSAL HALF OF THIS SCENARIO ALSO NEEDS
# (`test_the_parent_refuses_a_renamed_iam_keys_secret`, `test_tag_wall.py`,
# ledger 1137 split): imported from there rather than duplicated.
A_DISJOINT_NAME = "my-own-iam-keys"


def test_a_renamed_iam_keys_secret_with_the_toggle_off_still_renders_the_whole_estate(
    tmp_path: Path,
) -> None:
    """THE GREEN CASE, split out from `test_the_parent_refuses_a_renamed_iam_keys_secret`
    (ledger 1137): that test moved to `test_tag_wall.py`, which may assert no
    literal a module's pin moves, and `ADOPTER_OBJECTS` is one. A refusal that
    fires on a correct configuration is worse than none, so the green case stays
    a real assertion rather than being dropped — an adopter who renames the
    Secret with `iamKeys.create` FALSE is doing the supported thing, bringing
    their own keys from Vault, SOPS or 1Password, and that render must still be
    the whole estate.
    """
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


# ── ADR-0807: `platform.enabled` false turns the whole platform layer off ──────
# ADR-0777's refusal 3 — "a `create` is on while `platform.enabled` is off" — is
# RETIRED. With the defaults at the whole estate it fired almost only on a
# deliberate opt-out, which then took about ten keys. The opt-out is now two:
OPT_OUT_VALUES = (
    "platform:\n"
    "  enabled: false\n"
    "gateway:\n"
    "  adminBootstrap:\n"
    '    tokenSecret: ""\n'
)

# THE SECOND KEY IS DOCUMENTED, NOT REFUSED. `platform.enabled: false` alone leaves
# `gateway.adminBootstrap.tokenSecret` at `admin-bootstrap-token`, a Secret nothing
# then mints, and the gateway exits at boot. A render refusal naming it cannot be
# told apart from D80's all-off render — every `enabled` false, that string left
# alone — and it reddened `test_every_crd_bearing_resource_can_be_switched_off`
# when it was tried (2026-09-27). So the README and the example state it, and the
# test below pins the render that makes the statement true.
THE_ADMIN_TOKEN_SECRET = "admin-bootstrap-token"

# Every document of a render that came from the `platform` subchart or below it.
THE_PLATFORM_SOURCE = "# Source: yadgar/charts/platform/"


def platform_free_identities(documents_text: str) -> tuple[set[tuple[str, str, str]], int]:
    """The identities of a raw `helm template` stdout, and how many came from `platform`. PURE."""
    chunks = documents_text.split("\n---\n")
    from_platform = sum(1 for chunk in chunks if THE_PLATFORM_SOURCE in chunk)
    documents = [
        document
        for document in yaml.safe_load_all(documents_text)
        if isinstance(document, dict) and document.get("apiVersion")
    ]
    return identities(documents), from_platform


def test_platform_enabled_false_alone_turns_the_whole_platform_layer_off(tmp_path: Path) -> None:
    """ADR-0807 (a): the two-key opt-out renders, and renders no `platform` object.

    The render equals the default render minus every object `platform` rendered:
    the modules keep their autoscaling and databases, which are the modules' own
    toggles and not the platform layer's.
    """
    defaults = helm("template", "yadgar", str(CHART), *API_VERSIONS, "-f", str(EXPLICIT_TLS))
    assert defaults.returncode == 0, defaults.stderr
    everything, platform_count = platform_free_identities(defaults.stdout)
    platform_objects = {
        identity
        for chunk in defaults.stdout.split("\n---\n")
        if THE_PLATFORM_SOURCE in chunk
        for identity in identities(
            [d for d in yaml.safe_load_all(chunk) if isinstance(d, dict) and d.get("apiVersion")]
        )
    }

    values = overlay(tmp_path / "opt-out.yaml", OPT_OUT_VALUES)
    result = helm("template", "yadgar", str(CHART), *API_VERSIONS, "-f", str(EXPLICIT_TLS), "-f", str(values))
    assert result.returncode == 0, result.stderr
    found, from_platform = platform_free_identities(result.stdout)
    print(
        f"\nADR-0807: the opt-out renders {len(found)} objects; the defaults render "
        f"{len(everything)}, {platform_count} of them from `platform`"
    )
    assert from_platform == 0, result.stdout
    assert platform_objects and found == everything - platform_objects, (
        sorted(found ^ (everything - platform_objects))
    )


def test_platform_enabled_false_wins_over_every_create_left_true(tmp_path: Path) -> None:
    """ADR-0807 (b): contradictory input renders no platform object, and is not refused.

    Every `create` stated true explicitly, `platform.enabled` false. Under ADR-0777
    this was refusal 3; now it is the same render as the opt-out.
    """
    creates = "".join(
        f"  {block}:\n    create: true\n"
        for block in (
            "internalCA", "certificates", "edgeTLS", "gatewayListener", "valkey", "nats", "bootstrap"
        )
    )
    contradictory = overlay(tmp_path / "contradictory.yaml", OPT_OUT_VALUES.replace(
        "  enabled: false\n", "  enabled: false\n" + creates, 1
    ))
    opt_out = overlay(tmp_path / "opt-out.yaml", OPT_OUT_VALUES)
    both = [
        helm("template", "yadgar", str(CHART), *API_VERSIONS, "-f", str(EXPLICIT_TLS), "-f", str(path))
        for path in (contradictory, opt_out)
    ]
    for result in both:
        assert result.returncode == 0, result.stderr
    assert "platform.enabled is not true" not in both[0].stderr, both[0].stderr
    assert platform_free_identities(both[0].stdout) == platform_free_identities(both[1].stdout)
    assert platform_free_identities(both[0].stdout)[1] == 0


def test_platform_enabled_false_still_refuses_the_operators_toggle(tmp_path: Path) -> None:
    """ADR-0807 does not reach `platform.operators.create`; ADR-0787's refusal stands on the opt-out path.

    That refusal sits outside the `create` guard by design: operators are never a
    path this parent offers, whatever `platform.enabled` says.
    """
    values = overlay(
        tmp_path / "opt-out-with-operators.yaml",
        OPT_OUT_VALUES.replace("  enabled: false\n", "  enabled: false\n  operators:\n    create: true\n", 1),
    )
    result = helm("template", "yadgar", str(CHART), *API_VERSIONS, "-f", str(EXPLICIT_TLS), "-f", str(values))
    assert result.returncode != 0, "the opt-out with operators.create true rendered"
    assert THE_OPERATORS_REFUSAL in result.stderr, result.stderr


def test_platform_enabled_false_needs_no_iam_keys_agreement(tmp_path: Path) -> None:
    """With the platform layer off nothing mints `iam-keys`, so a renamed mount is the adopter's own."""
    values = overlay(
        tmp_path / "opt-out-own-keys.yaml",
        OPT_OUT_VALUES + "iam:\n  keysSecret: my-own-iam-keys\n",
    )
    result = helm("template", "yadgar", str(CHART), *API_VERSIONS, "-f", str(EXPLICIT_TLS), "-f", str(values))
    assert result.returncode == 0, result.stderr


def test_platform_enabled_false_alone_renders_and_still_mounts_the_admin_token(tmp_path: Path) -> None:
    """ADR-0807: `platform.enabled: false` alone renders, and the gateway still names the token.

    This is the hazard the README's opt-out names: the render succeeds with no
    `platform` object, and the gateway Deployment still mounts
    `admin-bootstrap-token`, which nothing now mints. Clearing
    `gateway.adminBootstrap.tokenSecret` is the second key of the opt-out.
    """
    values = overlay(tmp_path / "enabled-false-alone.yaml", "platform:\n  enabled: false\n")
    result = helm("template", "yadgar", str(CHART), *API_VERSIONS, "-f", str(EXPLICIT_TLS), "-f", str(values))
    assert result.returncode == 0, result.stderr
    found, from_platform = platform_free_identities(result.stdout)
    print(f"\nADR-0807: `platform.enabled: false` alone renders {len(found)} objects")
    assert from_platform == 0
    gateway = [
        document
        for document in yaml.safe_load_all(result.stdout)
        if isinstance(document, dict)
        and document.get("kind") == "Deployment"
        and (document.get("metadata") or {}).get("name") == "gateway"
    ]
    assert len(gateway) == 1
    assert f"secretName: {THE_ADMIN_TOKEN_SECRET}" in yaml.safe_dump(gateway[0]), (
        "the gateway no longer mounts the admin token when `platform.enabled` is false "
        "alone, so the README's second opt-out key is stale"
    )


# ── `platform.enabled` THAT IS NOT A BOOL, WHICH IS THE OPPOSITE STATE ───────
# THE REFUSAL ABOVE SAYS "this render contains NONE of the objects those toggles
# name", AND THAT SENTENCE IS FALSE IN THIS STATE. It is true when
# `platform.enabled` is false or absent, because the condition resolves and the
# dependency is off. It is false when the key is present and not a bool: helm
# leaves a dependency ENABLED when the path its condition names does not resolve,
# so the platform layer GOES IN. The adopter was told the opposite of what
# happened, loudly, with a remedy that happened to be right for the wrong reason.
#
# AND THE STRING SHAPES REACHED NO MESSAGE AT ALL. `ne (default false
# $platform.enabled) true` compares a string to a bool by RAISING: measured on
# helm 4.3.0, `platform.enabled: "yes"` aborted with `error calling ne:
# incompatible types for comparison: string and bool` — a stack trace where
# ADR-0794 requires a key name.
#
# EACH ROW: (name, what is written after `enabled:`, the kind reported).
THE_UNREADABLE_ENABLED_SHAPES = (
    ("enabled-is-null", "", "null"),
    ("enabled-is-the-yaml-yes-string", '"yes"', "string"),
    ("enabled-is-the-yaml-true-string", '"true"', "string"),
    ("enabled-is-zero", "0", "float64"),
    ("enabled-is-an-empty-string", '""', "string"),
    ("enabled-is-an-empty-list", "[]", "slice"),
)
THE_UNREADABLE_ENABLED_REFUSAL = "rather than true or false"

# The line the red case below rewrites, so the render it aborts can be counted.
THE_PARENT_FAIL = '{{- fail (printf "\\n\\nyadgar: this parent chart refuses to render.'
THE_PARENT_FAIL_OFF = '{{- $ignored := (printf "\\n\\nyadgar: NOT REFUSING.'



def test_an_unreadable_platform_enabled_leaves_the_dependency_enabled(
    tmp_path: Path,
) -> None:
    """THE MEASUREMENT THAT MAKES THE NEW MESSAGE TRUE AND THE OLD ONE FALSE.

    Both refusals abort with zero objects, so no render under the shipped chart
    can show the difference between them — which is exactly how a message this
    wrong survived. The parent's one `fail` is rewritten to a no-op and the two
    states are then rendered and counted:

        platform.enabled: false,  platform.valkey.create: true  -> the bare set
        platform.enabled: <null>, the same toggle               -> MORE, with Valkey

    Measured 2026-09-26 on helm 3.20.2 and 4.3.0: 32 objects and 0 Valkey
    documents against 35 and 2.

    AN INEQUALITY AND A NAMED OBJECT, not two literals: what must stay true is
    that the layer ARRIVES out of a key that says nothing, and the object count of
    a `platform` release is not this test's business.
    """
    copy = tmp_path / "not-refusing" / "chart"
    copy.parent.mkdir(parents=True)
    shutil.copytree(CHART, copy)
    template = copy / "templates" / "_validate.tpl"
    original = template.read_text()
    assert original.count(THE_PARENT_FAIL) == 1, (
        f"the parent's single `fail` is no longer exactly one {THE_PARENT_FAIL!r}, "
        f"so this mutation would cut at the wrong place"
    )
    template.write_text(original.replace(THE_PARENT_FAIL, THE_PARENT_FAIL_OFF))
    assert template.read_text() != original

    def render_it(name: str, enabled: str) -> list[dict]:
        result = helm(
            "template",
            "yadgar",
            str(copy),
            *API_VERSIONS,
            "-f",
            str(EXPLICIT_TLS),
            "-f",
            str(
                overlay(
                    tmp_path / f"{name}.yaml",
                    f"platform:\n  enabled: {enabled}\n  valkey:\n    create: true\n"
                    "gateway:\n  adminBootstrap:\n    tokenSecret: admin-bootstrap-token\n",
                )
            ),
        )
        assert result.returncode == 0, (
            f"`{name}` did not render with the parent's `fail` switched off, so "
            f"this case measures nothing: {result.stderr}"
        )
        return [
            document
            for document in yaml.safe_load_all(result.stdout)
            if isinstance(document, dict) and document.get("apiVersion")
        ]

    resolved_false = render_it("enabled-false", "false")
    unreadable = render_it("enabled-nulled", "")

    def valkey(documents: list[dict]) -> list[str]:
        return sorted(
            str((document.get("metadata") or {}).get("name"))
            for document in documents
            if "valkey" in str((document.get("metadata") or {}).get("name", ""))
        )

    assert valkey(resolved_false) == [], (
        f"`platform.enabled: false` rendered Valkey objects, so the condition did "
        f"not resolve false and this case has no baseline: {valkey(resolved_false)}"
    )
    assert valkey(unreadable), (
        "an unreadable `platform.enabled` rendered no Valkey object, so the "
        "dependency was NOT left enabled and the refusal's new wording is the "
        "false one"
    )
    assert len(unreadable) > len(resolved_false), (
        f"an unreadable `platform.enabled` rendered {len(unreadable)} objects and a "
        f"resolved-false one rendered {len(resolved_false)}"
    )


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


def test_every_operator_key_stated_false_still_renders_the_whole_estate(
    tmp_path: Path,
) -> None:
    """THE GREEN CASE, split out from
    `test_the_parent_refuses_the_operators_toggle_and_every_one_of_its_sub_keys`
    (ledger 1137): that test moved to `test_tag_wall.py`, which may assert no
    literal a module's pin moves, and `ADOPTER_OBJECTS` is one. An adopter who
    writes an operator key FALSE is doing the supported thing, and a refusal
    keyed on the key being PRESENT rather than on it being TRUE would break
    every one of them — which is what this render alone still proves.
    """
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


# ── WHICH CHART ANSWERED, OBSERVED RATHER THAN ASSUMED ───────────────────────
# THE COUNTER USED TO TALLY THE TUPLE'S OWN LABEL. It read `refused_by[chart] += 1`
# with `chart` taken from the row it had just read, so the comment above — "a row
# that quietly changed which chart answered it reddens here" — asserted a property
# the loop could not see. The per-row `phrase in message` assertion did discriminate,
# so no coverage was lost; what was lost was the sentence being true, and this estate
# treats a comment claiming a property its assertion cannot see as a defect in its own
# right.
#
# THE DISCRIMINATOR IS THE TEMPLATE PATH helm PRINTS, not the wording. Every refusal
# arrives as `Error: execution error at (<template path>:line:col)`, and the path names
# the chart that called `fail` — `yadgar/templates/validate.yaml` for this one,
# `yadgar/charts/platform/templates/render-checks.yaml` for the subchart. Identical on
# helm 3.20.2 and 4.3.0, measured 2026-09-26. It is stronger than matching the message:
# a reworded refusal still comes from the same file, and two charts cannot share a path.
THE_REFUSERS_TEMPLATE = {
    THE_PARENT: "yadgar/templates/validate.yaml",
    THE_SUBCHART: "yadgar/charts/platform/templates/render-checks.yaml",
}


def the_chart_that_refused(name: str, message: str) -> str:
    """Which chart called `fail`, read off helm's own error location.

    EXACTLY ONE MUST MATCH, and that is asserted rather than left to a counter.
    A message matching NEITHER path would leave a `Counter` simply not
    incrementing, and the walk would then report a total that is wrong in a way
    that reads like a changed table — the diagnosis pointing at the tuple when
    the fault is that nothing recognisable refused at all.
    """
    found = sorted(
        chart for chart, path in THE_REFUSERS_TEMPLATE.items() if path in message
    )
    assert len(found) == 1, (
        f"`{name}`: {len(found)} of the known refusers' template paths appear in "
        f"this message ({found}), and exactly one must. helm names the file that "
        f"called `fail`, so either an unknown chart refused or two did.\n{message}"
    )
    return found[0]


# THE LINE THE `nats.create: null` RED CASE REWRITES, AND IT IS IN THIS CHART.
# Rewritten back to the `invalid` exclusion the clause carried before, which is the
# change a contributor would really make — "a nil never raised, leave it alone" is
# the reasoning the old comment gave.
THE_PRESENT_NIL_ARM = '{{- else if hasKey $block "create" -}}'
THE_PRESENT_NIL_ARM_OFF = '{{- else if not (kindIs "invalid" $block.create) -}}'


def test_excluding_a_nil_create_lets_the_broker_in(tmp_path: Path) -> None:
    """THE `nats.create: null` ROW'S RED CASE, and it renders exit 0 with a broker.

    Put the `invalid` exclusion back and `platform.nats.create:` with no value
    renders at exit 0: helm resolved `condition: nats.create` against a value it
    could not read and left the dependency ENABLED, while this clause read the same
    value as false. The broker goes in and `platform`'s own `nats-ingress`
    NetworkPolicy — which reads the value the same way this clause did — does not.

    THE COUNT IS AN INEQUALITY against the render that asks for nothing, for the
    reason every count in this file is: the property is that the broker ARRIVED,
    not how many documents the upstream chart ships this month.
    """
    copy = tmp_path / "nil-permitted" / "chart"
    copy.parent.mkdir(parents=True)
    shutil.copytree(CHART, copy)
    template = copy / "templates" / "_validate.tpl"
    original = template.read_text()
    assert original.count(THE_PRESENT_NIL_ARM) == 1, (
        f"the present-nil arm is no longer exactly one {THE_PRESENT_NIL_ARM!r}, so "
        f"this mutation would cut at the wrong place"
    )
    template.write_text(original.replace(THE_PRESENT_NIL_ARM, THE_PRESENT_NIL_ARM_OFF))
    assert template.read_text() != original

    def render_it(name: str, body: str) -> subprocess.CompletedProcess[str]:
        return helm(
            "template",
            "yadgar",
            str(copy),
            *API_VERSIONS,
            "-f",
            str(modules_only_file(tmp_path)),
            "-f",
            str(EXPLICIT_TLS),
            "-f",
            str(overlay(tmp_path / f"{name}.yaml", body)),
        )

    head = (
        "gateway:\n  adminBootstrap:\n    tokenSecret: admin-bootstrap-token\n"
        "platform:\n  enabled: true\n"
    )
    asked_nothing = render_it("nil-baseline", head)
    assert asked_nothing.returncode == 0, asked_nothing.stderr
    nulled = render_it("nil-nats-create", head + "  nats:\n    create:\n")
    assert nulled.returncode == 0, (
        f"`platform.nats.create:` was still refused with the nil exclusion back, so "
        f"this red case is not isolating the arm the row reads: {nulled.stderr}"
    )
    for raise_text in THE_TEXTS_A_RAISE_LEAVES:
        assert raise_text not in nulled.stderr, nulled.stderr

    def count(result: subprocess.CompletedProcess[str]) -> int:
        return len(
            [
                document
                for document in yaml.safe_load_all(result.stdout)
                if isinstance(document, dict) and document.get("apiVersion")
            ]
        )

    assert count(nulled) > count(asked_nothing), (
        f"a nulled `platform.nats.create` rendered {count(nulled)} objects and a "
        f"render that asks for nothing rendered {count(asked_nothing)}, so the "
        f"broker did not go in and this red case shows nothing"
    )
    assert "# Source: yadgar/charts/platform/charts/nats/" in nulled.stdout, (
        "no document came from the `nats` subchart, so the fail-open this red case "
        "records did not happen"
    )
    policies = [
        (document.get("metadata") or {}).get("name")
        for document in yaml.safe_load_all(nulled.stdout)
        if isinstance(document, dict) and document.get("kind") == "NetworkPolicy"
    ]
    assert "nats-ingress" not in policies, (
        f"the nats-ingress NetworkPolicy rendered, so the harm is not the one "
        f"described: {sorted(name for name in policies if name)}"
    )


def test_the_null_operators_arm_is_reachable_only_without_the_pinned_subchart(
    tmp_path: Path,
) -> None:
    """THE `invalid` → `null` MAPPING, EXERCISED — and the honest reach stated.

    `_validate.tpl` maps `kindOf`'s `invalid` to `null` so the message names a
    type an adopter recognises rather than "is a invalid". Nothing exercised that
    mapping: the `null` row of `THE_NON_MAPPING_OPERATORS` is refused by
    `platform` one level down, so the arm could be DELETED and the whole suite
    would stay green on both helm lines. An arm with no case that reaches it is
    not code with light coverage, it is code nobody has shown to work.

    WHAT IT TAKES TO REACH IT, AND WHY NO ADOPTER EVER WILL. Helm deletes a key
    whose value is null only when a chart in the tree DECLARES that key, and
    `platform` has declared `operators.create` since 0.1.9. `chart/Chart.yaml`
    ALWAYS pins `platform`, so for every shipping adopter the key is deleted
    before any template runs and this arm is unreachable — `platform` answers
    instead. The honest claim is REACHABLE IN A FIXTURE, not "not dead": this test
    strips the dependencies, which is a tree no adopter installs.

    IT IS STILL WORTH HOLDING. The arm is one line from being wrong, the mapping
    it performs is the estate's own convention for `invalid`, and the day
    `platform` stops declaring `operators.create` — or a second parent pins a
    version that never did — it is load-bearing again with no warning.
    """
    copy = chart_without_its_dependencies(tmp_path)
    result = helm(
        "template",
        "yadgar",
        str(copy),
        *API_VERSIONS,
        "-f",
        str(EXPLICIT_TLS),
        "-f",
        str(
            overlay(
                tmp_path / "stripped-operators-null.yaml",
                "platform:\n  enabled: true\n  operators: null\n"
                "  internalCA:\n    create: true\n"
                "gateway:\n  adminBootstrap:\n    tokenSecret: admin-bootstrap-token\n",
            )
        ),
    )
    assert result.returncode != 0, (
        "the dependency-stripped parent rendered exit 0, so nothing reached the "
        f"arm this case exists to exercise\n{result.stdout[:2000]}"
    )
    assert "platform.operators is a null rather than a mapping" in result.stderr, (
        "the arm did not report `invalid` as `null`, which is the whole of what it "
        f"does: {result.stderr}"
    )
    assert THE_DELETED_OPERATORS_KEY_REFUSAL not in result.stderr, (
        "`platform`'s own arm answered, which cannot happen with the subcharts "
        f"stripped — this case is not measuring the parent: {result.stderr}"
    )
    for raise_text in THE_TEXTS_A_RAISE_LEAVES:
        assert raise_text not in result.stderr, (
            f"the stripped parent RAISED instead of refusing: {result.stderr}"
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
        str(EXPLICIT_TLS),
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
    `test_breaking_the_guard_makes_the_modules_only_render_refuse` does it: a red case
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
    """`body` over `MODULES_ONLY_VALUES`, the pre-B6 defaults, and no `--api-versions`.

    Nothing in `MODULES_ONLY_VALUES` asks for an operator, so each red case below
    turns on exactly what its own overlay names and no render check fires first.
    """
    return helm(
        "template",
        "yadgar",
        str(copy),
        "-f",
        str(modules_only_file(tmp_path)),
        "-f",
        str(EXPLICIT_TLS),
        "-f",
        str(overlay(tmp_path / name, body)),
    )


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


def test_the_refusals_are_satisfied_at_the_defaults_and_unreachable_without_the_platform(
    tmp_path: Path, modules_only: Path
) -> None:
    """THE GUARD'S TWO GREEN CASES, and the property the refusals rest on.

    ADR-0777: the refusals are guarded on any `platform.*.create` being true.
    Before ADR-0803 step B6 that was an ADOPTER-SET condition and the bare default
    render reached none of them. THE DEFAULTS NOW OPEN THE GUARD: every `create`
    is true, so the first green case is that the defaults SATISFY every refusal —
    the admin token named on both sides, `iam-keys` unrenamed, `platform.enabled`
    true — and render the whole estate. `.Release.IsInstall` still cannot stand in
    for the guard: it is TRUE for `helm template`, so it separates nothing.

    THE SECOND GREEN CASE is `MODULES_ONLY_VALUES`, which shuts the guard again,
    asserted over the dependency-stripped tree as well. There `.Values.platform` is
    ABSENT rather than merely all-false — the render the nil-safe chain in
    `_validate.tpl` exists for, and the one that would raise if somebody replaced
    it with a direct `.Values.platform.bootstrap.create`.
    """
    assert len(render(str(CHART), *API_VERSIONS, "-f", str(EXPLICIT_TLS))) == ADOPTER_OBJECTS
    assert dict(kinds(render(str(CHART), "-f", str(modules_only), "-f", str(EXPLICIT_TLS)))) == EXPECTED
    assert render(str(chart_without_its_dependencies(tmp_path)), "-f", str(modules_only)) == []


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
    # OVER `MODULES_ONLY_VALUES`, which clears the admin token the defaults name:
    # every overlay below opens the guard with the token empty, as before B6.
    base = modules_only_file(tmp_path)
    for name, body in sorted(overlays.items()):
        result = helm(
            "template",
            "yadgar",
            str(copy),
            "-f",
            str(base),
            "-f",
            str(overlay(tmp_path / f"{name}.yaml", body)),
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


def test_breaking_the_guard_makes_the_modules_only_render_refuse(tmp_path: Path) -> None:
    """THE GUARD'S RED CASE: remove the guard and the modules-only render goes red.

    This is the measurement ADR-0777 records as the reason the guard exists, run
    rather than cited. An unconditional refusal in the parent fires on the render
    of an adopter who runs their own platform layer — `MODULES_ONLY_VALUES`, which
    was the bare default render before ADR-0803 step B6 — and who therefore
    rightly names no admin token.
    """
    copy = tmp_path / "chart"
    shutil.copytree(CHART, copy)
    partial = copy / "templates" / "_validate.tpl"
    text = partial.read_text()
    needle = "{{- if $creating -}}"
    assert needle in text, "the guard moved; this red case is now testing nothing"
    partial.write_text(text.replace(needle, "{{- if true -}}", 1))

    result = helm(
        "template", "yadgar", str(copy), "-f", str(modules_only_file(tmp_path)), "-f", str(EXPLICIT_TLS)
    )
    assert result.returncode != 0, (
        "the guard was removed and the modules-only render still succeeded, so the "
        "guard is not what is keeping the refusals off that render"
    )
    assert "gateway.adminBootstrap.tokenSecret is empty" in result.stderr, result.stderr


# ------------- 8. the defaults ARE the whole estate (ADR-0803 step B6, decision 2)


# THE FILE THE SHARED GATES READ (ADR-0806). `helm-lint`, `d80_portability.py` and
# `service_immutable.py` in `yadgarhq/actions` each pass every entry of it as
# `--api-versions` when they render this chart offline. `DECLARED_API_VERSIONS`
# above is the literal a human measured; this file is what CI renders with; the
# test below holds the two equal, so neither drifts from the other.
API_VERSIONS_DECLARATION = CHART / "ci" / "api-versions.txt"

# THE KEYS `example/values.yaml` STATES AND THE DEFAULTS DELIBERATELY DO NOT. The
# edge leaf's issuer is the one thing an adopter must name for themselves. The
# defaults leave `platform.edgeTLS.issuerRef` empty, and `platform` (0.1.17, step
# B3) then issues the edge leaf from the internal CA: it renders and goes Ready,
# and no client outside the cluster trusts it. The example names a placeholder
# `ClusterIssuer` so an adopter sees the key. Every other leaf of the example must
# equal the default; a new exception needs its own line here and its own reason.
#
# THE TWELVE `tls.enabled` READ SWITCHES JOIN THE SAME EXCEPTION (ruling 11,
# ADR-0845). Each module chart already defaults its own `tls.enabled` to
# `false`, so today this is a restatement the chart's own default would also
# produce — but the default is going away with no replacement once C-SVb and
# C-DB1 land (K-8), and the parent's `values.yaml` must never be the value's
# tenth writer. The example states all twelve explicitly now so an adopter
# who copies it is never silently holding the old default.
ADOPTER_ONLY_KEYS = {
    "platform.edgeTLS.issuerRef.name",
    "platform.edgeTLS.issuerRef.kind",
    "gateway.task.tls.enabled",
    "gateway.iam.tls.enabled",
    "gateway.project.tls.enabled",
    "iam.tls.enabled",
    "iam.iamDb.tls.enabled",
    "iam-db.tls.enabled",
    "task.tls.enabled",
    "task.taskDb.tls.enabled",
    "task-db.tls.enabled",
    "project.tls.enabled",
    "project.projectDb.tls.enabled",
    "project-db.tls.enabled",
}

# THE KEYS `chart/values.yaml` STATES AND THE EXAMPLE DOES NOT. `gateway.gateway.enabled`
# restates the gateway chart's own default only so the `portability` job can
# flip it (see the header of `chart/values.yaml`); an adopter has no reason to.
DEFAULT_ONLY_KEYS = {"gateway.gateway.enabled"}

# The edge leaf, and the issuer it falls back to when `issuerRef` is empty.
EDGE_CERTIFICATE = "gateway-tls"
EDGE_FALLBACK_ISSUER = {"name": "yadgar-internal-ca", "kind": "Issuer", "group": "cert-manager.io"}

# The text every estate render check prints when a declared API is missing.
THE_RENDER_CHECK_REFUSAL = "this render needs the API"

# WHAT THE DEFAULT RENDER CARRIES OUTSIDE THE BUILT-IN GROUPS, as (group, kind).
# A LITERAL for the reason `EXPECTED` is one. Every group but Gateway API's is one
# `DECLARED_API_VERSIONS` names, which is what ties the declaration to the render:
# a module release that brings some other product's CRD arrives here as a failing
# test rather than as a line in a job summary. Measured 2026-09-27 on helm 3.18.4
# and 4.3.0 against the nine pins in `chart/Chart.yaml` today.
DEFAULT_CRD_BEARING = {
    ("cert-manager.io", "Certificate"),
    ("cert-manager.io", "Issuer"),
    ("gateway.envoyproxy.io", "EnvoyProxy"),
    ("gateway.networking.k8s.io", "Gateway"),
    ("gateway.networking.k8s.io", "GatewayClass"),
    ("gateway.networking.k8s.io", "HTTPRoute"),
    ("k8s.mariadb.com", "MariaDB"),
    ("keda.sh", "ScaledObject"),
}


def declared_in(text: str) -> list[str]:
    """The entries of an `api-versions.txt` body, by `scripts/api_versions.py`'s rules. PURE.

    `#` to the end of the line is a comment and a blank line is nothing. The format
    checks belong to the shared reader, which refuses a malformed line in every
    gate; this suite asks only whether the entries are the measured ones.
    """
    return [
        entry
        for entry in (line.split("#", 1)[0].strip() for line in text.splitlines())
        if entry
    ]


def identities(documents: list[dict]) -> set[tuple[str, str, str]]:
    return {
        (
            str(document.get("apiVersion")),
            str(document.get("kind")),
            str((document.get("metadata") or {}).get("name")),
        )
        for document in documents
    }


_ABSENT = object()


def value_at(node, path: str):
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return _ABSENT
        node = node[key]
    return node


def default_disagreements(defaults: dict, adopter: dict) -> list[str]:
    """Every leaf the adopter values state that the parent's defaults state otherwise. PURE.

    THIS IS WHAT NAMES THE KEY. The render equality in the K1 test says THAT two
    renders differ and by which objects; it cannot say which default moved. This
    walk can, because every leaf of `example/values.yaml` outside
    `ADOPTER_ONLY_KEYS` is a statement of what the defaults are.
    """
    failures = []
    for path in leaves(adopter):
        if path in ADOPTER_ONLY_KEYS:
            continue
        want = value_at(adopter, path)
        have = value_at(defaults, path)
        if have is _ABSENT:
            failures.append(
                f"`{path}` is {want!r} in `example/values.yaml` and `chart/values.yaml` "
                f"does not state it, so the default comes from the child chart"
            )
        elif have != want:
            failures.append(
                f"`{path}` is {have!r} in `chart/values.yaml` and {want!r} in "
                f"`example/values.yaml`"
            )
    return failures


def unstated_defaults(defaults: dict, adopter: dict) -> list[str]:
    """Every leaf `chart/values.yaml` sets that `example/values.yaml` does not state. PURE.

    THE OTHER DIRECTION OF `default_disagreements`. That walk reads the example's
    leaves, so a default added to `chart/values.yaml` alone passes it — and the
    example stops being the full statement of the defaults it says it is.
    """
    return [
        f"`{path}` is {value_at(defaults, path)!r} in `chart/values.yaml` and "
        f"`example/values.yaml` does not state it"
        for path in leaves(defaults)
        if path not in DEFAULT_ONLY_KEYS and value_at(adopter, path) is _ABSENT
    ]


def chart_with_no_defaults(destination: Path) -> Path:
    """A copy of this chart whose `values.yaml` is empty — every child at its own default."""
    copy = destination / "chart"
    shutil.copytree(CHART, copy)
    (copy / "values.yaml").write_text("{}\n")
    return copy


def test_the_declaration_the_shared_gates_read_is_the_measured_one() -> None:
    """`chart/ci/api-versions.txt` equals `DECLARED_API_VERSIONS`, in order."""
    assert API_VERSIONS_DECLARATION.is_file(), (
        f"`{API_VERSIONS_DECLARATION.relative_to(REPO)}` is missing. The shared gates "
        f"then render this chart with no `--api-versions`, and the default render "
        f"refuses in every one of them (ADR-0806)."
    )
    assert declared_in(API_VERSIONS_DECLARATION.read_text()) == list(DECLARED_API_VERSIONS)


def test_a_declaration_missing_a_group_reddens_the_agreement_gate() -> None:
    """THE RED CASE: the same file with any one line deleted no longer agrees."""
    lines = API_VERSIONS_DECLARATION.read_text().splitlines()
    for dropped in DECLARED_API_VERSIONS:
        text = "\n".join(line for line in lines if line.strip() != dropped)
        assert declared_in(text) != list(DECLARED_API_VERSIONS), dropped
        assert dropped not in declared_in(text), dropped


def test_k1_the_defaults_render_what_the_adopter_values_render(tmp_path: Path) -> None:
    """K1 OF ADR-0803: the parent at its defaults IS the whole estate.

    TWO HALVES. The leaf walks name any key where `chart/values.yaml` and
    `example/values.yaml` part company, in either direction. The render equality
    proves the two files produce one object set, of `ADOPTER_OBJECTS` objects;
    `pytest -s` prints the count.

    THE EXAMPLE IS RENDERED OVER A CHART WITH NO DEFAULTS, not over this one. Over
    this one, a default the example leaves out is present in both renders and the
    equality cannot see it.
    """
    defaults = render(str(CHART), *API_VERSIONS, "-f", str(EXPLICIT_TLS))
    stated = render(str(chart_with_no_defaults(tmp_path)), *API_VERSIONS, "-f", str(ADOPTER_VALUES))
    print(
        f"\nK1: the default render holds {len(defaults)} objects; "
        f"the adopter values over no defaults hold {len(stated)}"
    )
    chart_values = yaml.safe_load((CHART / "values.yaml").read_text()) or {}
    adopter_values = yaml.safe_load(ADOPTER_VALUES.read_text()) or {}
    assert default_disagreements(chart_values, adopter_values) == []
    assert unstated_defaults(chart_values, adopter_values) == []
    assert identities(defaults) == identities(stated), (
        f"only in the defaults: {sorted(identities(defaults) - identities(stated))}; "
        f"only in the adopter values: {sorted(identities(stated) - identities(defaults))}"
    )
    assert len(defaults) == ADOPTER_OBJECTS
    assert dict(kinds(defaults)) == ADOPTER_EXPECTED


def test_k1_a_default_the_example_omits_reddens_the_equality_and_names_the_key(
    tmp_path: Path,
) -> None:
    """K1'S OTHER RED CASE: the example loses a block the defaults still set."""
    adopter_values = yaml.safe_load(ADOPTER_VALUES.read_text())
    del adopter_values["platform"]["valkey"]
    shrunk = overlay(tmp_path / "example-without-valkey.yaml", yaml.safe_dump(adopter_values))

    failures = unstated_defaults(yaml.safe_load((CHART / "values.yaml").read_text()), adopter_values)
    assert len(failures) == 1 and "`platform.valkey.create`" in failures[0], failures

    stated = render(str(chart_with_no_defaults(tmp_path)), *API_VERSIONS, "-f", str(shrunk))
    missing = identities(render(str(CHART), *API_VERSIONS, "-f", str(EXPLICIT_TLS))) - identities(stated)
    assert {name for _, _, name in missing} == {"valkey", "valkey-ingress"}, sorted(missing)


def test_k1_a_reverted_default_reddens_the_equality_and_names_the_key(tmp_path: Path) -> None:
    """K1'S RED CASE: one default reverted in a copy. Both halves go red; the walk names it."""
    copy = tmp_path / "chart"
    shutil.copytree(CHART, copy)
    values = yaml.safe_load((copy / "values.yaml").read_text())
    values["platform"]["valkey"]["create"] = False
    (copy / "values.yaml").write_text(yaml.safe_dump(values, sort_keys=False))

    failures = default_disagreements(values, yaml.safe_load(ADOPTER_VALUES.read_text()))
    assert len(failures) == 1 and "`platform.valkey.create`" in failures[0], failures

    reverted = render(str(copy), *API_VERSIONS, "-f", str(EXPLICIT_TLS))
    stated = render(str(copy), *API_VERSIONS, "-f", str(ADOPTER_VALUES))
    assert identities(reverted) != identities(stated)
    assert len(reverted) < len(stated) == ADOPTER_OBJECTS, (len(reverted), len(stated))


def test_k2_the_defaults_refuse_a_render_without_the_declared_api_versions() -> None:
    """K2 OF ADR-0803: a bare offline render of the defaults refuses, naming an operator.

    Refusing is the point. An adopter whose cluster lacks an operator the defaults
    use meets a render check that names it, not `no matches for kind` half-way
    through a sync. Matched on the render check's own text rather than on an exit
    code, so a refusal for any other reason does not pass here.

    `EXPLICIT_TLS` RIDES ALONG so the ONLY missing thing is an API version: once a
    module starts refusing an absent `tls.enabled` too, a bare render with neither
    would refuse for TLS first and this test would stop proving what it claims.
    """
    result = helm("template", "yadgar", str(CHART), "-f", str(EXPLICIT_TLS))
    assert result.returncode != 0, "the default render succeeded with no --api-versions"
    assert THE_RENDER_CHECK_REFUSAL in result.stderr, result.stderr
    assert any(group in result.stderr for group in DECLARED_API_VERSIONS), result.stderr


def test_k2_every_declared_group_is_required_by_the_defaults() -> None:
    """K2'S RED CASE, and the proof that no declared line is decorative.

    With all four the render succeeds — the K1 test renders it. Drop any one and
    the render refuses, naming the group that was dropped.
    """
    for dropped in DECLARED_API_VERSIONS:
        flags = [
            part
            for group in DECLARED_API_VERSIONS
            if group != dropped
            for part in ("--api-versions", group)
        ]
        result = helm("template", "yadgar", str(CHART), *flags, "-f", str(EXPLICIT_TLS))
        assert result.returncode != 0, f"the defaults rendered without {dropped}"
        assert THE_RENDER_CHECK_REFUSAL in result.stderr and dropped in result.stderr, (
            dropped,
            result.stderr,
        )


def test_the_default_edge_leaf_is_issued_by_the_internal_ca() -> None:
    """The defaults leave `platform.edgeTLS.issuerRef` empty, and the edge leaf still names a real Issuer."""
    documents = render(str(CHART), *API_VERSIONS, "-f", str(EXPLICIT_TLS))
    edge = [
        document
        for document in certificates(documents)
        if (document.get("metadata") or {}).get("name") == EDGE_CERTIFICATE
    ]
    assert len(edge) == 1, names_of(documents, "Certificate")
    assert edge[0]["spec"]["issuerRef"] == EDGE_FALLBACK_ISSUER, edge[0]["spec"]["issuerRef"]
    assert EDGE_FALLBACK_ISSUER["name"] in names_of(documents, "Issuer")


def test_the_defaults_render_only_the_declared_operators_crds() -> None:
    """Every CRD-bearing object of the default render is a declared operator's or Gateway API's."""
    found = {
        (api_version.split("/")[0], kind)
        for api_version, kind, _ in crd_bearing(render(str(CHART), *API_VERSIONS, "-f", str(EXPLICIT_TLS)))
    }
    assert found == DEFAULT_CRD_BEARING, (
        f"new: {sorted(found - DEFAULT_CRD_BEARING)}; gone: {sorted(DEFAULT_CRD_BEARING - found)}"
    )
    declared_groups = {group.split("/")[0] for group in DECLARED_API_VERSIONS}
    assert {group for group, _ in found} - declared_groups == {"gateway.networking.k8s.io"}


# ------------- 9. the example Application installs the whole estate (ADR-0803 step B7)


EXAMPLE_APPLICATION = REPO / "example" / "application.yaml"
PUBLISHED_CHART = "oci://ghcr.io/yadgarhq/charts/yadgar"

# THE OLDEST PARENT THE EXAMPLE MAY PIN: 0.3.1, the release of ADR-0807
# (`platform.enabled` false is the whole opt-out). 0.3.0 already defaults to the
# whole estate but documents a ten-key opt-out the example's text no longer
# describes. A floor, not a currency check. Every merge to `main` cuts a release, so
# the example is one release behind the moment the pull request that bumps it
# merges. A "pin == newest tag" check would go red on the next merge — including
# the bot's pin commits — and nothing inside that merge could fix it. Moving the
# pin is a deliberate change, gated by the render below.
EXAMPLE_PIN_FLOOR = (0, 3, 1)

# WHAT "THE WHOLE ESTATE" MEANS AT ANY PIN, as properties rather than a count. The
# release tooling moves the example's pin at every tag (ADR-0820), so a literal
# count measured at one pin would redden `main` at the next release that adds an
# object. At every pin the example's render must equal the pinned parent's own
# defaults, object for object, and those defaults must carry the platform layer,
# autoscaling and the databases: a kind from each.
WHOLE_ESTATE_KINDS = ("Gateway", "EnvoyProxy", "Certificate", "ScaledObject", "MariaDB", "Job")

# THE ESTATE'S HOSTNAME IS ONE KEY (ADR-0808). The example states `global.hostname`
# and nothing else for it; platform, gateway and iam derive the five keys below
# from it when they are left empty. The example must NOT state any of the five:
# a per-chart key wins over the global, so stating one is a second source that
# can disagree with the first.
HOSTNAME_KEY = "global.hostname"
HOSTNAME_KEYS = (
    "platform.gatewayListener.hostname",
    "platform.edgeTLS.commonName",
    "platform.edgeTLS.dnsNames",
    "gateway.gateway.hostname",
    "iam.enrolment.gateway",
)
BUILT_IN_HOSTNAME = "gateway.yadgar.internal"
# `iam`'s OWN HISTORICAL DEFAULT CARRIES A PORT (`iam`'s `_hostname.tpl`'s step
# 3), where the other four sites' built-in is the bare `BUILT_IN_HOSTNAME`. A
# check that only looks for `BUILT_IN_HOSTNAME` as a substring of the whole
# render passes here too — the port-bearing URL contains the bare hostname —
# so it cannot tell this site apart from the other four (ledger 1153).
BUILT_IN_IAM_ENROLMENT_GATEWAY = f"https://{BUILT_IN_HOSTNAME}:18443"

# THE LAST PARENT BEFORE ADR-0808's THREE PINS (platform 0.1.18, gateway 0.9.53,
# iam 0.8.45 arrived in 0.3.3, 0.3.4 and 0.3.5). Its children do not read
# `global`, so the example's `valuesObject` renders the built-in hostname there.
A_PRE_0808_PIN = "0.3.2"

# THE PIN THE RED CASE SUBSTITUTES: a pre-B6 parent, where `platform.enabled`
# defaulted false. Measured: 32 objects there with
# the same `valuesObject`, because its platform keys reach a disabled dependency.
A_PRE_B6_PIN = "0.2.38"
A_PRE_B6_PIN_OBJECTS = 32


def example_source() -> dict:
    document = yaml.safe_load(EXAMPLE_APPLICATION.read_text())
    return document["spec"]["source"]


def pulled(version: str, destination: Path) -> Path:
    """The PUBLISHED parent at `version`, pulled from the registry. NOT vendored.

    The example pins a published artifact, so the artifact is what is rendered —
    a vendored copy would be a second thing to keep equal to it. This suite
    already needs the registry (`packaged` resolves nine dependencies from it),
    and so do the pre-commit hook and CI's `precommit` job that run it.
    """
    destination.mkdir(parents=True, exist_ok=True)
    result = helm("pull", PUBLISHED_CHART, "--version", version, "-d", str(destination))
    assert result.returncode == 0, f"cannot pull {PUBLISHED_CHART} {version}: {result.stderr}"
    tarball = destination / f"yadgar-{version}.tgz"
    assert tarball.is_file(), sorted(path.name for path in destination.iterdir())
    return tarball


def example_render(tarball: Path, values_object: dict, destination: Path) -> subprocess.CompletedProcess[str]:
    values = overlay(destination / "values-object.yaml", yaml.safe_dump(values_object))
    return helm("template", "yadgar", str(tarball), *API_VERSIONS, "-f", str(values))


def unrecognised_keys(values_object: dict, tarball: Path) -> list[str]:
    """Every leaf of `values_object` that no chart in `tarball` declares a default for. PURE-ish.

    helm accepts and ignores an unknown key under all but one child (there is no
    parent schema), so this is the check that names a typo. A path is recognised
    when each step exists in the default values, until a step whose default is an
    empty mapping or null — an open map, such as `platform.edgeTLS.issuerRef`.
    """
    import tarfile

    with tarfile.open(tarball, "r:gz") as archive:
        def values_of(member: str) -> dict:
            return yaml.safe_load(archive.extractfile(member).read()) or {}

        # `global` IS DECLARED BY THE TARBALL'S OWN `yadgar/values.yaml` ALONE
        # (ledger 1153). Every example today pins 0.3.39 or later, and every pin
        # that recent already packages `chart/values.yaml`'s `global.hostname`
        # (ADR-0808), so `values_of` above already carries it. Grafting it again
        # from THIS REPOSITORY'S working tree, as this unit used to, let a typo
        # recognise itself: a misspelling made on HEAD and repeated in a
        # `valuesObject` matched the graft's own (equally misspelt) copy, and a
        # pin that declares no `global` at all borrowed HEAD's regardless.
        defaults = values_of("yadgar/values.yaml")
        for name in {m.split("/")[2] for m in archive.getnames() if m.count("/") >= 3 and m.startswith("yadgar/charts/")}:
            member = f"yadgar/charts/{name}/values.yaml"
            if member in archive.getnames():
                defaults = merged({name: values_of(member)}, defaults)
            # A CONTRACT CHART (ADR-0845, ADR-0857) DELETES ITS OWN DEFAULT, so
            # `values_of(member)` alone stops declaring the key the moment the
            # chart stops defaulting it — exactly the state this schema-only
            # leaf still names. The schema's `properties` tree is read too, as
            # a SKELETON merged UNDER the values-derived defaults (never over
            # them): a leaf the schema declares and the values no longer do
            # becomes a recognised, open (`None`) leaf, the same tolerance
            # `undeclared_leaves` already gives any other open map.
            schema = f"yadgar/charts/{name}/values.schema.json"
            if schema in archive.getnames():
                defaults = merged({name: schema_skeleton(json.loads(archive.extractfile(schema).read()))}, defaults)

    return undeclared_leaves(values_object, defaults, "no chart in the pinned parent")


def minimal_parent_tarball(destination: Path, values: dict) -> Path:
    """A tarball `unrecognised_keys()` can read, declaring `values` and no children. PURE-ish.

    Only `yadgar/values.yaml` is read when no `yadgar/charts/<name>/` member
    exists, so this is enough to put a chosen (or absent) `global` block in
    front of `unrecognised_keys()` without pulling or packaging anything real.
    """
    import io
    import tarfile

    tarball = destination / "synthetic.tgz"
    body = yaml.safe_dump(values).encode()
    with tarfile.open(tarball, "w:gz") as archive:
        info = tarfile.TarInfo("yadgar/values.yaml")
        info.size = len(body)
        archive.addfile(info, io.BytesIO(body))
    return tarball


def schema_skeleton(schema: dict) -> dict:
    """The key tree a JSON schema's `properties` declare, every leaf `None`. PURE.

    A PROPERTY WITH NO `properties` OF ITS OWN IS A LEAF, recognised but open —
    the same reading `undeclared_leaves` already gives an empty mapping or a
    `None` node. One WITH `properties` recurses, so a nested block (`tls`,
    `database`) is walked rather than swallowed whole.
    """
    return {
        key: (schema_skeleton(sub) if isinstance(sub, dict) and sub.get("properties") else None)
        for key, sub in (schema.get("properties") or {}).items()
    }


def undeclared_leaves(values_object: dict, defaults: dict, declarer: str) -> list[str]:
    """Every leaf of `values_object` whose path `defaults` does not declare. PURE."""
    failures = []
    for path in leaves(values_object):
        node = defaults
        for step in path.split("."):
            if isinstance(node, dict) and not node:
                break
            if node is None:
                break
            if not isinstance(node, dict) or step not in node:
                failures.append(f"`{path}`: {declarer} declares `{step}` there")
                break
            node = node[step]
    return failures


# THE PUSH THAT STAMPS A PIN RUNS BEFORE THAT PIN IS PUBLISHED. The release tooling
# writes `vN` into the examples in the commit the tag `vN` points at (ADR-0820), and
# the tag's release job publishes `vN` after that commit's push validation has
# started. Whether HEAD is tagged is not a usable test: the tag ref is created after
# the stamp commit, and a checkout can come first. What IS stable is the registry:
# a pin STRICTLY NEWER than every version GHCR holds for the chart is a version
# being cut, and `ci-release.yaml`'s post-publish job pulls it once it exists.
# A pin that is published-or-older and cannot be pulled, and any unpublished pin
# on a pull request, fail.
GHCR = "https://ghcr.io"
PARENT_REPOSITORY = "yadgarhq/charts/yadgar"


def published_versions(repository: str = PARENT_REPOSITORY) -> list[str]:
    """Every tag GHCR holds for `repository`, read anonymously from the OCI tags list."""
    import json
    import urllib.request

    scope = f"{GHCR}/token?scope=repository:{repository}:pull"
    token = json.load(urllib.request.urlopen(scope, timeout=30))["token"]
    request = urllib.request.Request(
        f"{GHCR}/v2/{repository}/tags/list?n=10000", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        assert "next" not in (response.headers.get("Link") or ""), "the tags list is paginated; read every page"
        return json.load(response)["tags"]


def semver(version: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    return tuple(int(part) for part in match.groups()) if match else None


def being_cut(version: str, event: str, published: list[str]) -> bool:
    """`version` is newer than every published one, and this is no pull request. PURE."""
    if event == "pull_request" or semver(version) is None:
        return False
    ordered = [semver(tag) for tag in published if semver(tag) is not None]
    assert ordered, f"GHCR lists no semver version at all: {published[:10]}"
    return semver(version) > max(ordered)


def parent_at(version: str, destination: Path, event: str | None = None, published: list[str] | None = None) -> Path:
    """The published parent at `version`, or HEAD's chart packaged AS `version` while it is being cut.

    NOT A SKIP, and nothing is weaker for it. The artifact the tag publishes is
    `helm package chart -u --version <tag>` of the tagged commit, which is what this
    packages, and every gate then runs against it.
    """
    destination.mkdir(parents=True, exist_ok=True)
    result = helm("pull", PUBLISHED_CHART, "--version", version, "-d", str(destination))
    if result.returncode == 0:
        return destination / f"yadgar-{version}.tgz"
    event = os.environ.get("GITHUB_EVENT_NAME", "") if event is None else event
    published = published_versions() if published is None else published
    assert being_cut(version, event, published), (
        f"cannot pull {PUBLISHED_CHART} {version}, and it is not a version being cut: "
        f"event {event!r}, newest published {max(published, key=lambda tag: semver(tag) or (-1,))}. "
        f"{result.stderr}"
    )
    print(f"\n{PUBLISHED_CHART} {version} is newer than every published version; rendering HEAD packaged as it")
    workspace = destination / "head"
    shutil.copytree(CHART, workspace / "chart")
    made = helm("package", "chart", "-u", "--version", version, "--app-version", version, cwd=workspace)
    assert made.returncode == 0, made.stderr
    tarball = workspace / f"yadgar-{version}.tgz"
    assert tarball.is_file(), sorted(path.name for path in workspace.iterdir())
    return tarball


@pytest.fixture(scope="module")
def pinned(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return parent_at(str(example_source()["targetRevision"]), tmp_path_factory.mktemp("pinned"))


AN_UNPUBLISHED_VERSION = "99.99.99"
AN_UNPUBLISHED_OLDER_VERSION = "0.0.99"
# A registry listing with a signature tag in it, and `0.3.10` so a LEXICAL maximum
# (`0.3.8`) would call `0.3.9` newer than everything. Semver says it is not.
A_LISTING = ["0.1.0", "0.3.8", "0.3.10", "sha256-abc.sig"]


@pytest.mark.parametrize(
    ("version", "event", "cut"),
    [
        (AN_UNPUBLISHED_VERSION, "push", True),
        (AN_UNPUBLISHED_VERSION, "", True),
        (AN_UNPUBLISHED_VERSION, "pull_request", False),
        (AN_UNPUBLISHED_OLDER_VERSION, "push", False),
        ("0.3.9", "push", False),
        ("0.3.10", "push", False),
        ("0.3.11", "push", True),
    ],
    ids=[
        "newer-on-push", "newer-locally", "never-on-a-pull-request", "unpublished-but-older",
        "lexically-newer-only", "the-newest-itself", "the-next-patch",
    ],
)
def test_only_a_version_newer_than_every_published_one_is_being_cut(version: str, event: str, cut: bool) -> None:
    assert being_cut(version, event, A_LISTING) is cut


def test_the_registry_lists_the_published_parent() -> None:
    """The query the fallback rests on answers, and holds a version the examples may pin."""
    published = published_versions()
    assert "0.3.8" in published, published[-5:]
    assert not being_cut("0.3.8", "push", published)


@pytest.mark.parametrize(
    ("version", "event"),
    [(AN_UNPUBLISHED_OLDER_VERSION, "push"), (AN_UNPUBLISHED_VERSION, "pull_request")],
    ids=["unpublished-older-pin", "pull-request"],
)
def test_an_unpublished_pin_that_is_not_being_cut_fails(tmp_path: Path, version: str, event: str) -> None:
    """THE RED CASES: an unpublished pin older than the newest release, and any on a pull request."""
    with pytest.raises(AssertionError, match=f"{version}, and it is not a version being cut"):
        parent_at(version, tmp_path, event, A_LISTING)


def test_a_version_being_cut_renders_from_head(tmp_path: Path) -> None:
    """On the stamp commit the pin is HEAD's chart packaged as that version, and it renders."""
    tarball = parent_at(AN_UNPUBLISHED_VERSION, tmp_path, "push", A_LISTING)
    assert tarball.name == f"yadgar-{AN_UNPUBLISHED_VERSION}.tgz"
    assert set(WHOLE_ESTATE_KINDS) <= set(kinds(render(str(tarball), *API_VERSIONS, "-f", str(EXPLICIT_TLS))))


def test_the_example_pins_a_published_parent_at_or_above_the_floor() -> None:
    source = example_source()
    assert source["repoURL"] == "ghcr.io/yadgarhq/charts" and source["chart"] == "yadgar", source
    pin = str(source["targetRevision"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", pin), f"`targetRevision: {pin}` is not bare semver"
    assert tuple(int(part) for part in pin.split(".")) >= EXAMPLE_PIN_FLOOR, (
        f"the example pins {pin}, below {'.'.join(map(str, EXAMPLE_PIN_FLOOR))} (ADR-0807's release)"
    )


def test_the_example_installs_the_whole_estate_at_its_pin(pinned: Path, tmp_path: Path) -> None:
    """B7's gate: the pinned PUBLISHED parent, the inline `valuesObject`, the four API versions."""
    source = example_source()
    values_object = source["helm"]["valuesObject"]
    result = example_render(pinned, values_object, tmp_path)
    assert result.returncode == 0, result.stderr
    documents = [d for d in yaml.safe_load_all(result.stdout) if isinstance(d, dict) and d.get("apiVersion")]
    print(f"\nB7: {source['targetRevision']} with the example's valuesObject renders {len(documents)} objects")
    assert identities(documents) == identities(render(str(pinned), *API_VERSIONS, "-f", str(EXPLICIT_TLS))), (
        "the example's valuesObject changed which objects the pinned parent renders"
    )
    assert [kind for kind in WHOLE_ESTATE_KINDS if kind not in kinds(documents)] == []


def hostname_sites(documents: list[dict]) -> dict[str, object]:
    """The five places the rendered estate carries its public hostname. PURE."""

    def only(kind: str, name: str | None = None) -> dict:
        found = [
            d for d in documents
            if d.get("kind") == kind and (name is None or d["metadata"]["name"] == name)
        ]
        assert len(found) == 1, (kind, name, len(found))
        return found[0]

    (listener,) = only("Gateway")["spec"]["listeners"]
    edge = only("Certificate", EDGE_CERTIFICATE)["spec"]
    (route_host,) = only("HTTPRoute")["spec"]["hostnames"]
    enrolment = [
        variable["value"]
        for container in only("Deployment", "iam")["spec"]["template"]["spec"]["containers"]
        for variable in container.get("env", [])
        if variable["name"] == "ENROLMENT_GATEWAY"
    ]
    assert len(enrolment) == 1, enrolment
    return {
        "platform.gatewayListener.hostname": listener["hostname"],
        "platform.edgeTLS.commonName": edge["commonName"],
        "platform.edgeTLS.dnsNames": edge["dnsNames"],
        "gateway.gateway.hostname": route_host,
        "iam.enrolment.gateway": enrolment[0],
    }


def derived_from(host: str) -> dict[str, object]:
    return {
        "platform.gatewayListener.hostname": host,
        "platform.edgeTLS.commonName": host,
        "platform.edgeTLS.dnsNames": [host],
        "gateway.gateway.hostname": host,
        # No port: the edge listener answers on 443.
        "iam.enrolment.gateway": f"https://{host}",
    }


def built_in_sites() -> dict[str, object]:
    """Each site's value with `global.hostname` unset and no per-chart override either. PURE.

    NOT four copies of `BUILT_IN_HOSTNAME` and a fifth that merely contains it:
    `iam`'s own default carries a port the other four never had, so the per-site
    map is the only check that cannot mistake the URL for the bare hostname.
    """
    return {
        "platform.gatewayListener.hostname": BUILT_IN_HOSTNAME,
        "platform.edgeTLS.commonName": BUILT_IN_HOSTNAME,
        "platform.edgeTLS.dnsNames": [BUILT_IN_HOSTNAME],
        "gateway.gateway.hostname": BUILT_IN_HOSTNAME,
        "iam.enrolment.gateway": BUILT_IN_IAM_ENROLMENT_GATEWAY,
    }


def five_key_form(values_object: dict, host: str) -> dict:
    """The same `valuesObject` with the hostname written into the five keys instead. PURE."""
    five = {key: value for key, value in values_object.items() if key != "global"}
    return merged(
        five,
        {
            "platform": {
                "gatewayListener": {"hostname": host},
                "edgeTLS": {"commonName": host, "dnsNames": [host]},
            },
            "gateway": {"gateway": {"hostname": host}},
            "iam": {"enrolment": {"gateway": f"https://{host}"}},
        },
    )


def test_the_example_states_the_hostname_once() -> None:
    values_object = example_source()["helm"]["valuesObject"]
    host = value_at(values_object, HOSTNAME_KEY)
    assert isinstance(host, str) and host, f"the example does not set `{HOSTNAME_KEY}`"
    stated = [path for path in HOSTNAME_KEYS if value_at(values_object, path) is not _ABSENT]
    assert stated == [], (
        f"the example also states {stated}; each wins over `{HOSTNAME_KEY}` and is a "
        f"second source for the same hostname (ADR-0808)"
    )


def test_every_hostname_site_derives_from_global_hostname(pinned: Path, tmp_path: Path) -> None:
    """The one value reaches all five sites, and the built-in hostname is gone."""
    values_object = example_source()["helm"]["valuesObject"]
    host = value_at(values_object, HOSTNAME_KEY)
    result = example_render(pinned, values_object, tmp_path)
    assert result.returncode == 0, result.stderr
    documents = [d for d in yaml.safe_load_all(result.stdout) if isinstance(d, dict) and d.get("apiVersion")]
    assert hostname_sites(documents) == derived_from(host)
    assert BUILT_IN_HOSTNAME not in result.stdout, (
        "the built-in hostname survives in the render; a sixth site carries it"
    )


def test_the_global_form_renders_byte_equal_to_the_five_key_form(pinned: Path, tmp_path: Path) -> None:
    """`global.hostname` is exactly the five keys, written once."""
    values_object = example_source()["helm"]["valuesObject"]
    host = value_at(values_object, HOSTNAME_KEY)
    (tmp_path / "one").mkdir()
    (tmp_path / "five").mkdir()
    one = example_render(pinned, values_object, tmp_path / "one")
    five = example_render(pinned, five_key_form(values_object, host), tmp_path / "five")
    assert one.returncode == 0 and five.returncode == 0, (one.stderr, five.stderr)
    assert one.stdout == five.stdout


@pytest.fixture(scope="module")
def pre_0808(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return pulled(A_PRE_0808_PIN, tmp_path_factory.mktemp("pre-0808"))


def test_a_pre_0808_pin_reddens_the_derivation(pre_0808: Path, tmp_path: Path) -> None:
    """THE RED CASE: at 0.3.2 no child reads `global`, so every site keeps its own built-in.

    PER-SITE, not a substring (ledger 1153): `BUILT_IN_HOSTNAME in result.stdout`
    passed even though `iam.enrolment.gateway` carries a port none of the other
    four sites do, because the substring is still there inside that URL.
    """
    values_object = example_source()["helm"]["valuesObject"]
    host = value_at(values_object, HOSTNAME_KEY)
    tarball = pre_0808
    (tmp_path / "render").mkdir()
    result = example_render(tarball, values_object, tmp_path / "render")
    assert result.returncode == 0, result.stderr
    documents = [d for d in yaml.safe_load_all(result.stdout) if isinstance(d, dict) and d.get("apiVersion")]
    sites = hostname_sites(documents)
    assert all(sites[key] != derived_from(host)[key] for key in HOSTNAME_KEYS), sites
    assert sites == built_in_sites(), sites


def test_every_example_key_is_one_a_chart_declares(pinned: Path) -> None:
    assert unrecognised_keys(example_source()["helm"]["valuesObject"], pinned) == []


def test_a_misspelt_example_key_reddens_the_recognition_gate(pinned: Path) -> None:
    values_object = yaml.safe_load(yaml.safe_dump(example_source()["helm"]["valuesObject"]))
    declared = values_object.get("global") or {}
    assert "hostname" in declared, (
        f"the example's valuesObject no longer states global.hostname, so this red "
        f"case has nothing to misspell; move it to another key: {values_object}"
    )
    declared["hostnme"] = declared.pop("hostname")
    failures = unrecognised_keys(values_object, pinned)
    assert len(failures) == 1 and "`global.hostnme`" in failures[0], failures


def test_a_typo_this_repository_also_makes_is_still_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned: Path
) -> None:
    """THE RED CASE (ledger 1153): the gate must trust the pinned tarball, not HEAD.

    The deleted graft read `global` from THIS REPOSITORY'S working-tree
    `chart/values.yaml`. Point `CHART` at a copy carrying `global.hostnmae: x`
    (the same misspelling ledger 1153 names) and ask for the identical typo in a
    `valuesObject`: before the fix the graft recognised it, because it was
    comparing the typo to itself rather than to anything the pinned parent
    declares.
    """
    fake_chart = tmp_path / "chart"
    fake_chart.mkdir()
    (fake_chart / "values.yaml").write_text(yaml.safe_dump({"global": {"hostnmae": "x"}}))
    monkeypatch.setattr(sys.modules[__name__], "CHART", fake_chart)
    failures = unrecognised_keys({"global": {"hostnmae": "x"}}, pinned)
    assert len(failures) == 1 and "`global.hostnmae`" in failures[0], failures


def test_a_pin_with_no_global_at_all_names_an_unrecognised_hostname(tmp_path: Path) -> None:
    """THE RED CASE (ledger 1153): a pin that declares no `global` lends it none.

    A pinned parent that predates ADR-0808 has no `global` member in its own
    `yadgar/values.yaml` at all. Before the fix, THIS REPOSITORY'S
    `chart/values.yaml` — which does declare `global.hostname` — was grafted in
    regardless, so a key the pinned parent itself never declared was recognised
    anyway.
    """
    tarball = minimal_parent_tarball(tmp_path, {"platform": {"enabled": True}})
    failures = unrecognised_keys({"global": {"hostname": "x"}}, tarball)
    assert len(failures) == 1 and "`global.hostname`" in failures[0], failures


def test_a_pre_b6_pin_reddens_the_whole_estate_gate(tmp_path: Path) -> None:
    """B7's red case: the same `valuesObject` at 0.2.38 renders the 32 modules alone."""
    tarball = pulled(A_PRE_B6_PIN, tmp_path / "old")
    result = example_render(tarball, example_source()["helm"]["valuesObject"], tmp_path)
    assert result.returncode == 0, result.stderr
    documents = [d for d in yaml.safe_load_all(result.stdout) if isinstance(d, dict) and d.get("apiVersion")]
    assert len(documents) == A_PRE_B6_PIN_OBJECTS, (A_PRE_B6_PIN, len(documents))
    missing = [kind for kind in WHOLE_ESTATE_KINDS if kind not in kinds(documents)]
    assert {"Gateway", "EnvoyProxy", "MariaDB"} <= set(missing), missing


# ------------- 10. the operators and kind examples, and every example's retry (ADR-0820)
#
# MEASURED 2026-09-30 ON A kind VM, and each constant below is a literal from that
# run or from a render of the pins it used: `platform` 0.1.19 with the operators
# example's `valuesObject` synced Healthy with 151 objects, 45 of them CRDs, and
# `yadgar` 0.3.8 with the kind example's `valuesObject` served the edge on
# 127.0.0.1:18443. The run also exhausted Argo's default retry budget of 5 while
# the estate was `Degraded`, which is what the retry gate is for.

OPERATORS_APPLICATION = REPO / "example" / "operators-application.yaml"
KIND_APPLICATION = REPO / "example" / "kind" / "application.yaml"
KIND_CONFIG = REPO / "example" / "kind" / "kind-config.yaml"
EXAMPLE_APPLICATIONS = (EXAMPLE_APPLICATION, OPERATORS_APPLICATION, KIND_APPLICATION)
PUBLISHED_PLATFORM = "oci://ghcr.io/yadgarhq/charts/platform"
ARGO_KINDS = {"Application", "ApplicationSet"}

# THE RETRY WINDOW EVERY EXAMPLE MUST FALL INSIDE: the sum of the waits Argo takes
# before each retry. Below 5 minutes, operators and databases are still starting
# when the budget runs out; the VM exhausted Argo's default (5 retries, 5s x2,
# max 3m: 310 s) that way. Above 20 minutes, the Application is locked in its
# retry loop for longer than anybody waits: a new revision cannot sync while an
# operation is retrying, so a fix pushed during the window waits for it to end.
# `-1` (retry forever) never ends at all.
RETRY_WINDOW_SECONDS = (5 * 60, 20 * 60)
RETRY_BACKOFF_KEYS = ("duration", "factor", "maxDuration")
GO_DURATION = re.compile(r"(\d+(?:\.\d+)?)(h|m|s)")
GO_UNIT_SECONDS = {"h": 3600, "m": 60, "s": 1}

OPERATORS_NAMESPACE = "yadgar-operators"
OPERATORS_VALUES = {"operators": {"create": True, "argoCd": {"create": False}}}
OPERATORS_SYNC_OPTIONS = {"CreateNamespace=true", "ServerSideApply=true"}
# WHAT THE OPERATORS EXAMPLE INSTALLS, as properties that hold at any `platform`
# pin, because the release tooling moves that pin whenever `platform` releases
# (ADR-0820). Measured 2026-09-30 at 0.1.19 for the record: 151 objects, 45 CRDs,
# and 53 more (Argo CD) with `operators.create` alone. Every object comes from one
# of the four operator subcharts or `platform`'s vendored CRDs, each of the four
# contributes, and the CRDs serve every API version the parent declares it needs.
# READ OFF `platform`'s `Chart.yaml` AT THE PIN: every dependency whose
# `condition` names `operators.create`, Argo CD excepted. Not a literal, so the
# operator that arrives with a `platform` release is expected the moment it is
# pinned. At 0.1.21: cert-manager, gateway-helm, keda, mariadb-operator and
# prometheus.
CRDS_DIRECTORY = "crds/"
# WHAT `platform`'s OWN TEMPLATES MAY ADD TO THE OPERATORS: the CRDs it vendors, and
# a Namespace an operator lands in (`observability`, for Prometheus — Argo creates
# only the Application's own destination namespace).
PLATFORM_OWN_KINDS = {"CustomResourceDefinition", "Namespace"}
ARGO_CD_SOURCE = "argo-cd"
# WHERE THE MODULES' ScaledObjects LOOK FOR PROMETHEUS by default, and so where the
# operators Application must put it: Service `prometheus-server` in
# `observability`. Asserted against the module charts' own default below.
PROMETHEUS_SERVICE = ("prometheus-server", "observability")
ARGO_CD_PART_OF = "argocd"

# THE ENTRY NO PARENT EXAMPLE MAY CARRY (ledger 1266, ADR-0803 proposal (c)). It
# was added on the claim that mariadb-operator writes `generate` back onto the
# spec, so Argo and the operator revert each other. Measured read-only on kind
# 2026-10-02, operator v26.6.0, 27 days of live CRs: live equals desired at both
# pointers on all three CRs, `argocd-controller` is the only manager of both refs,
# and the operator's `SetDefaults` writes them only when they are zero-valued
# (`api/v1alpha1/mariadb_types.go:959,970`) — every `-db` chart renders both with
# an explicit name and `generate: true`. An entry that masks nothing hides a real
# divergence the day one appears, so its return is refused, not tolerated.
MARIADB_IGNORE_DIFFERENCES = {
    "group": "k8s.mariadb.com",
    "kind": "MariaDB",
    "jsonPointers": ["/spec/rootPasswordSecretKeyRef/generate", "/spec/passwordSecretKeyRef/generate"],
}

KIND_NODE_IMAGE = (
    "kindest/node:v1.36.1@sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5"
)
KIND_LISTEN_ADDRESS = "127.0.0.1"
KIND_EDGE = "edge"


def application(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def copied(document: dict) -> dict:
    return yaml.safe_load(yaml.safe_dump(document))


def argo_documents_under(root: Path) -> list[str]:
    """Every file under `root` holding an Argo Application or ApplicationSet, relative. PURE-ish."""
    found = []
    for path in sorted(root.rglob("*.y*ml")):
        documents = [d for d in yaml.safe_load_all(path.read_text()) if isinstance(d, dict)]
        if any(d.get("kind") in ARGO_KINDS for d in documents):
            found.append(str(path.relative_to(root)))
    return found


def test_every_example_application_is_one_the_suite_reads() -> None:
    """The denominator: an Application added under `example/` without joining the gates reddens here."""
    assert argo_documents_under(REPO / "example") == sorted(
        str(path.relative_to(REPO / "example")) for path in EXAMPLE_APPLICATIONS
    )


@pytest.mark.parametrize(
    ("name", "kind"),
    [("extra.yml", "Application"), ("extra.yaml", "ApplicationSet")],
    ids=["yml-suffix", "application-set"],
)
def test_an_unread_example_reddens_the_denominator(tmp_path: Path, name: str, kind: str) -> None:
    copy = tmp_path / "example"
    shutil.copytree(REPO / "example", copy)
    (copy / name).write_text(yaml.safe_dump({"apiVersion": "argoproj.io/v1alpha1", "kind": kind}))
    assert name in argo_documents_under(copy)


def go_seconds(value) -> float:
    """Argo's `parseStringToDuration`: a bare integer is seconds, else a Go duration. PURE."""
    text = str(value)
    if re.fullmatch(r"-?\d+", text):
        return float(text)
    parts = GO_DURATION.findall(text)
    assert parts and "".join(f"{n}{u}" for n, u in parts) == text, f"not a Go duration: {text!r}"
    return sum(float(number) * GO_UNIT_SECONDS[unit] for number, unit in parts)


def retry_window(retry: dict) -> float:
    """Total seconds Argo waits across every retry, computed as Argo v3.1.8 does. PURE.

    `controller/appcontroller.go` increments `RetryCount` when it schedules a retry
    and then waits `NextRetryAt(finishedAt, RetryCount)` before running it, and
    `RetryStrategy.NextRetryAt` waits `duration * factor^count`, capped at
    `maxDuration`. So retry k of `limit` waits `min(maxDuration, duration *
    factor^k)` for k = 1..limit — the FIRST retry already waits `duration * factor`.
    """
    backoff = retry["backoff"]
    duration, factor, ceiling = go_seconds(backoff["duration"]), int(backoff["factor"]), go_seconds(backoff["maxDuration"])
    total, wait = 0.0, float(duration)
    for _ in range(int(retry["limit"])):
        # `duration * factor^count`, one factor per retry; the cap stops the growth.
        wait = min(ceiling, wait * factor) if ceiling > 0 else wait * factor
        total += wait
        if total > RETRY_WINDOW_SECONDS[1] * 1000:
            break  # far outside the window already; a limit of 100000 need not be summed
    return total


def retry_failures(document: dict) -> list[str]:
    """What is wrong with one Application's `syncPolicy.retry`. PURE."""
    retry = ((document.get("spec") or {}).get("syncPolicy") or {}).get("retry")
    if not isinstance(retry, dict):
        return ["no `spec.syncPolicy.retry`: Argo's default window of 310 s runs out while operators start"]
    limit = retry.get("limit")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        return [f"`retry.limit: {limit}` is not a finite, positive budget (-1 retries forever)"]
    missing = [f"`retry.backoff.{key}` is not set" for key in RETRY_BACKOFF_KEYS if key not in (retry.get("backoff") or {})]
    if missing:
        return missing
    window = retry_window(retry)
    low, high = RETRY_WINDOW_SECONDS
    if not low <= window <= high:
        return [f"the retry window is {window:.0f} s, outside {low}..{high} s"]
    return []


def test_every_example_application_retries_inside_the_window() -> None:
    failures = {str(path.relative_to(REPO)): retry_failures(application(path)) for path in EXAMPLE_APPLICATIONS}
    assert failures == {name: [] for name in failures}


def test_the_retry_window_is_argos_arithmetic() -> None:
    """Hand-computed against NextRetryAt: 30, 60, 120, 240, 300, 300."""
    retry = {"limit": 6, "backoff": {"duration": "15s", "factor": 2, "maxDuration": "5m"}}
    assert retry_window(retry) == 30 + 60 + 120 + 240 + 300 + 300
    # Argo's own default (limit 5, 5s x2, max 3m) is the window the VM exhausted.
    assert retry_window({"limit": 5, "backoff": {"duration": "5s", "factor": 2, "maxDuration": "3m"}}) == 310
    assert go_seconds("1h30m") == 5400 and go_seconds("45") == 45


@pytest.mark.parametrize(
    ("mutation", "named"),
    [
        (lambda retry: retry.update(limit=-1), "`retry.limit: -1`"),
        (lambda retry: retry.update(limit=100000), "outside"),
        (lambda retry: retry["backoff"].update(maxDuration="24h"), "outside"),
        (lambda retry: retry["backoff"].update(duration="1h"), "outside"),
        (lambda retry: retry.update(limit=1), "outside"),
        (lambda retry: retry.clear(), "`retry.limit: None`"),
        (lambda retry: retry.pop("backoff"), "`retry.backoff.duration` is not set"),
    ],
    ids=["forever", "limit-100000", "max-24h", "duration-1h", "too-short", "emptied", "no-backoff"],
)
def test_a_retry_outside_the_window_reddens_the_retry_gate(mutation, named: str) -> None:
    for path in EXAMPLE_APPLICATIONS:
        document = copied(application(path))
        mutation(document["spec"]["syncPolicy"]["retry"])
        failures = retry_failures(document)
        assert len(failures) >= 1 and named in failures[0], (path.name, failures)


def test_a_missing_retry_reddens_the_retry_gate() -> None:
    for path in EXAMPLE_APPLICATIONS:
        document = copied(application(path))
        del document["spec"]["syncPolicy"]["retry"]
        assert len(retry_failures(document)) == 1, path.name


# ─── every parent example: derived, not listed ────────────────────────────────


def parent_examples_of(documents: dict[str, dict]) -> dict[str, dict]:
    """The examples that install the parent, by what they install. PURE."""
    return {name: d for name, d in documents.items() if d["spec"]["source"].get("chart") == "yadgar"}


def example_documents() -> dict[str, dict]:
    return {str(path.relative_to(REPO)): application(path) for path in EXAMPLE_APPLICATIONS}


def parent_examples() -> dict[str, dict]:
    return parent_examples_of(example_documents())


def parent_pin_failures(documents: dict[str, dict]) -> list[str]:
    """Every parent example must pin the same published parent. PURE."""
    pins = {name: str(document["spec"]["source"]["targetRevision"]) for name, document in documents.items()}
    if len(set(pins.values())) != 1:
        return [f"the parent examples pin different versions: {pins}"]
    return []


def ignore_differences_failures(name: str, document: dict) -> list[str]:
    """One parent example must carry no MariaDB ignoreDifferences entry. PURE."""
    entries = (document.get("spec") or {}).get("ignoreDifferences") or []
    if any(entry.get("group") == "k8s.mariadb.com" and entry.get("kind") == "MariaDB" for entry in entries):
        return [f"`{name}` carries a MariaDB ignoreDifferences entry, which masks nothing measured (ledger 1266)"]
    return []


def parent_example_failures(documents: dict[str, dict], tarball: Path, destination: Path) -> list[str]:
    """Every gate a parent example must pass, for each of them. Renders with helm."""
    failures = parent_pin_failures(documents)
    expected = identities(render(str(tarball), *API_VERSIONS, "-f", str(EXPLICIT_TLS)))
    for index, (name, document) in enumerate(sorted(documents.items())):
        failures += ignore_differences_failures(name, document)
        values_object = document["spec"]["source"]["helm"]["valuesObject"]
        failures += [f"`{name}`: {failure}" for failure in unrecognised_keys(values_object, tarball)]
        (destination / str(index)).mkdir(parents=True, exist_ok=True)
        result = example_render(tarball, values_object, destination / str(index))
        if result.returncode != 0:
            failures.append(f"`{name}` does not render: {result.stderr}")
            continue
        documents_rendered = [d for d in yaml.safe_load_all(result.stdout) if isinstance(d, dict) and d.get("apiVersion")]
        if identities(documents_rendered) != expected:
            failures.append(f"`{name}` renders a different object set from the pinned parent's defaults")
    return failures


def test_the_parent_examples_are_derived_from_what_they_install() -> None:
    assert sorted(parent_examples()) == ["example/application.yaml", "example/kind/application.yaml"]


def test_every_parent_example_passes_every_parent_gate(pinned: Path, tmp_path: Path) -> None:
    assert parent_example_failures(parent_examples(), pinned, tmp_path) == []


# ─── a module that requires `tls.enabled` with no default, before any exists ──
#
# `pinned` ABOVE CANNOT CATCH THE GAP THIS PR CLOSES. It pulls the published
# parent at today's pin, and every module chart it bundles still DEFAULTS
# `tls.enabled` to `false` — ADR-0845's six open PRs (task#73, project#29,
# iam-db#84, task-db#85, project-db#54, C-SVb) drop that default and add the
# JSON-schema `required` the render checks already enforce at runtime, but none
# of them has merged, so the registry holds no pin that requires the switch.
# `example/application.yaml` could omit all twelve and this module's own gates
# above would stay green. This mutates `task-db`'s OWN vendored member inside a
# freshly packaged copy of the parent instead — exactly the shape C-DB1 ships
# for it — the same technique `chart_with_a_vendored_line_rewritten` uses for
# `platform` above, adapted to a parent that is PACKAGED rather than a bare
# directory: a package embeds each dependency expanded under
# `yadgar/charts/<name>/`, not as a nested `.tgz` to unpack a second time.
TASK_DB_VALUES_MEMBER = "yadgar/charts/task-db/values.yaml"
TASK_DB_SCHEMA_MEMBER = "yadgar/charts/task-db/values.schema.json"
TASK_DB_DEFAULT_WAS = "has to infer it.\n  enabled: false\n"
TASK_DB_DEFAULT_NOW = "has to infer it.\n"
TASK_DB_SCHEMA_TLS_WAS = (
    '    "tls": {\n'
    '      "properties": {\n'
    '        "enabled": {},\n'
    '        "certSecret": {},\n'
    '        "certSecretKey": {},\n'
    '        "keySecretKey": {}\n'
    '      },\n'
    '      "additionalProperties": false\n'
    '    },\n'
)
TASK_DB_SCHEMA_TLS_NOW = (
    '    "tls": {\n'
    '      "properties": {\n'
    '        "enabled": {},\n'
    '        "certSecret": {},\n'
    '        "certSecretKey": {},\n'
    '        "keySecretKey": {}\n'
    '      },\n'
    '      "additionalProperties": false,\n'
    '      "required": ["enabled"]\n'
    '    },\n'
)


def parent_packaged_with_task_db_requiring_tls(destination: Path) -> Path:
    """A fresh package of the parent whose vendored `task-db` requires `tls.enabled`.

    `helm package chart -u` IS `packaged`'s OWN RECIPE (ADR-0725: nothing under
    `chart/charts/` is committed), run again here rather than shared with it, so
    this mutation never touches the fixture every other test in this module reads.

    THE MEMBER AND THE LINE ARE BOTH ASSERTED BEFORE THE REPACK, same discipline
    as `chart_with_a_vendored_line_rewritten`: a member this package no longer
    holds, or a line that moved, is a red case that has stopped testing anything.

    TOLERATES A `task-db` THAT ALREADY SHIPS THE CONTRACT. `chart/Chart.yaml`'s
    pin moves to a real `task-db` release the day C-DB1 lands, and that release
    is exactly this function's target shape: `required: ["enabled"]` with no
    default. At that point `TASK_DB_DEFAULT_WAS`/`TASK_DB_SCHEMA_TLS_WAS` no
    longer occur in the vendored member — there is nothing left to mutate, and
    the plain assert below would refuse for the wrong reason. Checked by reading
    the vendored schema BEFORE the rewrite asserts fire, so a real contract pin
    returns the already-contracted tarball unchanged rather than erroring.
    """
    import io
    import tarfile

    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(CHART, destination / "chart")
    result = helm("package", "chart", "-u", "--version", "0.1.0", "--app-version", "0.1.0", cwd=destination)
    assert result.returncode == 0, result.stderr
    tarball = destination / "yadgar-0.1.0.tgz"
    assert tarball.is_file(), sorted(path.name for path in destination.iterdir())

    with tarfile.open(tarball, "r:gz") as archive:
        entries = [
            (entry, archive.extractfile(entry).read() if entry.isfile() else None)
            for entry in archive.getmembers()
        ]
    names = [entry.name for entry, _ in entries]
    rewrites = {
        TASK_DB_VALUES_MEMBER: (TASK_DB_DEFAULT_WAS, TASK_DB_DEFAULT_NOW),
        TASK_DB_SCHEMA_MEMBER: (TASK_DB_SCHEMA_TLS_WAS, TASK_DB_SCHEMA_TLS_NOW),
    }
    schema_now = json.loads(dict((entry.name, body) for entry, body in entries)[TASK_DB_SCHEMA_MEMBER])
    if "enabled" in schema_now["properties"]["tls"].get("required", []):
        return tarball  # the pinned task-db already ships the contract: nothing to simulate
    for member in rewrites:
        assert member in names, (
            f"`{member}` is not a member of `{tarball.name}`, so this mutation "
            f"would edit nothing and the render would be the unmutated one"
        )

    rewritten = io.BytesIO()
    with tarfile.open(fileobj=rewritten, mode="w:gz") as archive:
        for entry, body in entries:
            if entry.name in rewrites:
                was, now = rewrites[entry.name]
                text = body.decode()
                assert text.count(was) == 1, (
                    f"`{was.strip()}` occurs {text.count(was)} times in `{entry.name}` "
                    f"and exactly one was expected, so this mutation would be a no-op"
                )
                body = text.replace(was, now, 1).encode()
                entry.size = len(body)
            archive.addfile(entry, io.BytesIO(body) if body is not None else None)
    tarball.write_bytes(rewritten.getvalue())
    return tarball


def test_every_parent_example_renders_once_a_module_requires_tls_enabled(tmp_path: Path) -> None:
    """RED-FIRST FOR THIS PR, against `example/application.yaml` BEFORE it stated
    the twelve switches: `example/kind/application.yaml` already stated
    `task-db.tls.enabled` and kept rendering once `task-db` required the switch
    with no default; `example/application.yaml` stated none of the twelve and
    refused, naming the missing property — exactly the failure the PR
    description measured against a real pin. Both must render now.

    RENDERS THE IN-TREE PACKAGED CHART, not the published registry pin `pinned`
    reads elsewhere in this module: that pin cannot yet carry a `task-db` whose
    schema requires the switch, because none of ADR-0857's six open contract
    PRs has released one, so a check against it alone would stay green through
    the exact regression this PR fixes.

    ONLY `task-db` IS MUTATED, by design, not every chart `tls.enabled` names. A
    second gate — the BARE in-tree parent render (no `-f` at all) refusing and
    naming `tls`/`enabled` once ANY ONE of the six contract charts is vendored —
    was considered and dropped: proving it for more than one chart means hand
    writing six not-yet-released schemas and defaults, which is coupled to
    guesses about files this repository does not hold today, rather than to
    `task-db`'s real, current shape. The behaviour is the one `parent_at` and
    `EXPLICIT_TLS` riding along almost every other render in this module already
    document in prose: a contract pin breaks the bare render of WHATEVER chart
    it lands in, task-db included, which is exactly what this test shows for
    the one that exists to mutate.
    """
    tarball = parent_packaged_with_task_db_requiring_tls(tmp_path / "mutated")
    for name, document in parent_examples().items():
        values_object = document["spec"]["source"]["helm"]["valuesObject"]
        destination = tmp_path / name.replace("/", "_")
        destination.mkdir()
        result = example_render(tarball, values_object, destination)
        assert result.returncode == 0, (name, result.stderr)


# DERIVED FROM `ADOPTER_ONLY_KEYS`, NOT A SECOND LITERAL: that set is the whole
# exception list `default_disagreements` walks past (the two edge-issuer keys
# plus these twelve), and copying the twelve out by hand would be a second
# place for the list to drift from the one `ADOPTER_ONLY_KEYS` already names.
TWELVE_TLS_SWITCHES = ADOPTER_ONLY_KEYS - {
    "platform.edgeTLS.issuerRef.name",
    "platform.edgeTLS.issuerRef.kind",
}


def twelve_switches_of(values: dict) -> dict[str, object]:
    """Every one of the twelve switches `values` states, by path, with its value. PURE."""
    return {path: value_at(values, path) for path in TWELVE_TLS_SWITCHES if value_at(values, path) is not _ABSENT}


def test_the_twelve_tls_switches_agree_across_every_adopter_source() -> None:
    """ruling 11 / ADR-0845: the same twelve switches, at the same value, wherever an
    adopter reads them from — `example/values.yaml`, both parent examples'
    `valuesObject`, and `chart/ci/values.yaml` (K-8's fixture). A file that drops
    one, or states it differently from the rest, is the gap `example/application.yaml`
    had, and this gate is what keeps it from reopening anywhere in the set.
    """
    sources = {
        "example/values.yaml": yaml.safe_load(ADOPTER_VALUES.read_text()),
        "chart/ci/values.yaml": yaml.safe_load(EXPLICIT_TLS.read_text()),
    }
    for name, document in parent_examples().items():
        sources[name] = document["spec"]["source"]["helm"]["valuesObject"]
    stated = {name: twelve_switches_of(values) for name, values in sources.items()}
    missing = {name: sorted(TWELVE_TLS_SWITCHES - switches.keys()) for name, switches in stated.items()}
    assert missing == {name: [] for name in sources}, missing
    assert len({frozenset(switches.items()) for switches in stated.values()}) == 1, stated


A_NEW_PARENT_EXAMPLE = "example/new/application.yaml"


def with_new_parent_example(change) -> dict[str, dict]:
    """The examples plus a new yadgar Application, a copy of the kind one with `change` applied."""
    documents = example_documents()
    new = copied(documents["example/kind/application.yaml"])
    change(new)
    documents[A_NEW_PARENT_EXAMPLE] = new
    return documents


def misspell_node_port(document: dict) -> None:
    proxy = document["spec"]["source"]["helm"]["valuesObject"]["platform"]["gatewayListener"]["envoyProxy"]
    proxy["httpsNodePrt"] = proxy.pop("httpsNodePort")


@pytest.mark.parametrize(
    ("change", "named"),
    [
        (lambda d: d["spec"]["source"].update(targetRevision=A_PRE_0808_PIN), "pin different versions"),
        (misspell_node_port, "`platform.gatewayListener.envoyProxy.httpsNodePrt`"),
        (lambda d: d["spec"].update(ignoreDifferences=[copied(MARIADB_IGNORE_DIFFERENCES)]), "ignoreDifferences"),
        (lambda d: d["spec"]["source"]["helm"]["valuesObject"].update(platform={"enabled": False}), "different object set"),
    ],
    ids=["pin", "key", "ignore-differences", "render"],
)
def test_a_new_parent_example_meets_every_parent_gate(pinned: Path, tmp_path: Path, change, named: str) -> None:
    """THE RED CASE: a yadgar Application the scan finds is a parent example with no list to join."""
    documents = parent_examples_of(with_new_parent_example(change))
    assert A_NEW_PARENT_EXAMPLE in documents
    failures = parent_example_failures(documents, pinned, tmp_path)
    # Once platform's schema closes `gatewayListener.envoyProxy` (D-S(platform)), the
    # `key` row also fails helm's own render: a second failure whose stderr never
    # carries the backticked dotted path. That refusal is the only extra failure any
    # row may carry; every other row still fails exactly once.
    assert failures and named in failures[0], failures
    assert "pin different versions" in failures[0] or A_NEW_PARENT_EXAMPLE in failures[0], failures
    assert all(
        f.startswith(f"`{A_NEW_PARENT_EXAMPLE}` does not render:") and "httpsNodePrt" in f for f in failures[1:]
    ), failures


# ─── no prose states a version the release tooling will not move ──────────────
#
# THE STAMP REWRITES `targetRevision:` KEYS AND NOTHING ELSE (`example_pins.py` in
# `yadgarhq/actions`, ADR-0820): "prose that names a version is not rewritten". So
# a command or sentence here that names the current pin is stale at the next tag.
# Prose says `<your targetRevision>` or `X.Y.Z` instead. A dated measurement record
# ("measured 2026-09-30 against 0.3.8") is history and stays true, and this gate
# does not read it.

PROSE_FILES = (REPO / "README.md", *sorted((REPO / "example").rglob("*.y*ml")))
PROSE_PIN = re.compile(r"(--version\s+v?\d+\.\d+\.\d+|targetRevision:\s*v?\d+\.\d+\.\d+|`v\d+\.\d+\.\d+`)")
STAMPED = {"example/application.yaml", "example/kind/application.yaml", "example/operators-application.yaml"}


def prose_pin_failures(texts: dict[str, str]) -> list[str]:
    """Every version stated where the stamp will not rewrite it. PURE.

    A `targetRevision:` key on a non-comment line of a stamped example is the one
    place a version may stand; everything else is prose.
    """
    failures = []
    for name, text in texts.items():
        for number, line in enumerate(text.splitlines(), start=1):
            code = name in STAMPED and not line.lstrip().startswith("#")
            for match in PROSE_PIN.finditer(line):
                if code and match.group(0).startswith("targetRevision:") and "#" not in line[: match.start()]:
                    continue
                failures.append(f"{name}:{number} states `{match.group(0)}`, which no release moves")
    return failures


def prose_texts() -> dict[str, str]:
    return {str(path.relative_to(REPO)): path.read_text() for path in PROSE_FILES}


def test_no_prose_states_a_version_the_stamp_will_not_move() -> None:
    assert prose_pin_failures(prose_texts()) == []


@pytest.mark.parametrize(
    ("name", "line"),
    [
        ("README.md", "  targetRevision: 0.3.8\n"),
        ("example/values.yaml", "#   helm template yadgar chart --version 0.3.8\n"),
        ("example/application.yaml", "    # the git tag is `v0.3.8`\n"),
    ],
    ids=["readme-snippet", "helm-command", "tag-in-a-comment"],
)
def test_a_stated_version_reddens_the_prose_gate(name: str, line: str) -> None:
    texts = prose_texts()
    texts[name] = texts[name] + line
    (failure,) = prose_pin_failures(texts)
    assert failure.startswith(f"{name}:"), failure


# ─── the operators example ─────────────────────────────────────────────────────


def platform_inside(parent: Path) -> str:
    """The `platform` version a published parent package carries. Read from the package."""
    import tarfile

    with tarfile.open(parent, "r:gz") as archive:
        return str(yaml.safe_load(archive.extractfile("yadgar/charts/platform/Chart.yaml").read())["version"])


def operators_pin_failures(operators: dict, platform_version: str) -> list[str]:
    """The operators example must pin the `platform` its parent example carries. PURE.

    NOT `chart/Chart.yaml`'s `platform` pin, and the difference is measured rather
    than preferred: `parent_bump.py` in `yadgarhq/actions` rewrites that pin on
    every `platform` release, straight to `main` with no pull request, and writes
    no example. A gate on `Chart.yaml` would redden `main` and every open pull
    request at the next `platform` release. The parent the examples pin is fixed
    until somebody moves it, and it fixes which `platform` goes with it.
    """
    source = operators["spec"]["source"]
    failures = []
    if (source.get("repoURL"), source.get("chart")) != ("ghcr.io/yadgarhq/charts", "platform"):
        failures.append(f"the operators example does not install `platform` from the registry: {source}")
    if str(source.get("targetRevision")) != platform_version:
        failures.append(
            f"the operators example pins platform {source.get('targetRevision')}, and the parent the "
            f"examples pin carries platform {platform_version}"
        )
    return failures


def test_the_operators_example_pins_the_platform_its_parent_carries(pinned: Path) -> None:
    assert operators_pin_failures(application(OPERATORS_APPLICATION), platform_inside(pinned)) == []


def test_a_parent_carrying_another_platform_reddens_the_operators_pin(pre_0808: Path) -> None:
    """THE RED CASE: 0.3.2 carries an older `platform` than the operators example pins."""
    older = platform_inside(pre_0808)
    (failure,) = operators_pin_failures(application(OPERATORS_APPLICATION), older)
    assert f"carries platform {older}" in failure, failure


def operators_prune_failures(automated: dict) -> list[str]:
    """`prune` must stay absent or false: a pruned CRD deletes every object of its kind. PURE.

    NOT an equality on the literal key, because Argo CD 3.1.8 drops an explicit
    `prune: false` from the live object on write (measured 2026-10-01): a gate
    that demanded the key be present would redden on the cluster's own object.
    """
    if automated.get("prune", False) is not False:
        return [f"operators' automated sync prunes: {automated}"]
    return []


def test_the_operators_example_is_the_measured_application() -> None:
    spec = application(OPERATORS_APPLICATION)["spec"]
    assert spec["source"]["helm"]["valuesObject"] == OPERATORS_VALUES
    assert spec["destination"]["namespace"] == OPERATORS_NAMESPACE
    automated = spec["syncPolicy"]["automated"]
    assert operators_prune_failures(automated) == []
    assert automated.get("selfHeal") is True
    assert set(spec["syncPolicy"]["syncOptions"]) == OPERATORS_SYNC_OPTIONS


def test_a_pruning_automated_sync_reddens_the_operators_gate() -> None:
    """THE RED CASE: `prune: true` must fail, never silently pass."""
    (failure,) = operators_prune_failures({"prune": True, "selfHeal": True})
    assert "prunes" in failure, failure
    assert operators_prune_failures({"prune": False, "selfHeal": True}) == []
    assert operators_prune_failures({"selfHeal": True}) == []


@pytest.fixture(scope="module")
def operators_chart(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The PUBLISHED `platform` at the operators example's pin, which is what Argo installs."""
    version = str(application(OPERATORS_APPLICATION)["spec"]["source"]["targetRevision"])
    destination = tmp_path_factory.mktemp("operators")
    result = helm("pull", PUBLISHED_PLATFORM, "--version", version, "-d", str(destination))
    assert result.returncode == 0, f"cannot pull {PUBLISHED_PLATFORM} {version}: {result.stderr}"
    tarball = destination / f"platform-{version}.tgz"
    assert tarball.is_file(), sorted(path.name for path in destination.iterdir())
    return tarball


def operators_sources(chart: Path, values_object: dict, destination: Path) -> list[tuple[str, dict]]:
    """Each rendered object with the chart it came from: a subchart name, or a platform template."""
    values = overlay(destination / "operators-values.yaml", yaml.safe_dump(values_object))
    result = helm("template", "operators", str(chart), "-n", OPERATORS_NAMESPACE, "--include-crds", "-f", str(values))
    assert result.returncode == 0, result.stderr
    found = []
    for chunk in result.stdout.split("\n---\n"):
        source = re.search(r"^# Source: platform/(charts/(?P<chart>[^/]+)|(?P<template>templates/[^/\n]+))", chunk, re.M)
        for document in yaml.safe_load_all(chunk):
            if isinstance(document, dict) and document.get("apiVersion"):
                # A CRD from a chart's `crds/` directory carries no `# Source:` line.
                # Only a CRD may lack one.
                if source is None:
                    assert document["kind"] == "CustomResourceDefinition", chunk[:200]
                    found.append((CRDS_DIRECTORY, document))
                else:
                    found.append((source.group("chart") or source.group("template"), document))
    return found


def operator_charts(chart: Path) -> set[str]:
    """The operator subcharts `platform` declares at this version, Argo CD excepted."""
    import tarfile

    with tarfile.open(chart, "r:gz") as archive:
        metadata = yaml.safe_load(archive.extractfile("platform/Chart.yaml").read())
    return {
        dependency["name"]
        for dependency in metadata.get("dependencies") or []
        if "operators.create" in str(dependency.get("condition") or "").split(",")
        and dependency["name"] != ARGO_CD_SOURCE
    }


def operators_failures(found: list[tuple[str, dict]], operators: set[str]) -> list[str]:
    """What the operators render must be, at any `platform` pin. PURE."""
    failures = []
    sources = {source for source, _ in found}
    stray = sorted(
        {
            source for source, d in found
            if source not in operators | {CRDS_DIRECTORY}
            and not (source.startswith("templates/") and d["kind"] in PLATFORM_OWN_KINDS)
        }
    )
    if stray:
        failures.append(f"objects come from outside the operators: {stray}")
    absent = sorted(operators - sources)
    if absent:
        failures.append(f"no object comes from {absent}")
    served = {
        f"{d['spec']['group']}/{version['name']}"
        for _, d in found
        if d["kind"] == "CustomResourceDefinition"
        for version in d["spec"]["versions"]
        if version.get("served")
    }
    unserved = [api for api in DECLARED_API_VERSIONS if api not in served]
    if unserved:
        failures.append(f"no CRD serves {unserved}, which the parent declares it needs")
    argo = argo_cd_objects([d for _, d in found]) + [
        d["metadata"]["name"] for _, d in found
        if d["kind"] == "CustomResourceDefinition" and d["spec"]["group"] == "argoproj.io"
    ]
    if argo:
        failures.append(f"{len(argo)} Argo CD objects render")
    return failures


def argo_cd_objects(documents: list[dict]) -> list[str]:
    return [
        f"{d['kind']}/{d['metadata']['name']}"
        for d in documents
        if ((d["metadata"].get("labels") or {}).get("app.kubernetes.io/part-of")) == ARGO_CD_PART_OF
    ]


def test_the_operators_example_installs_the_operators_and_no_argo_cd(
    operators_chart: Path, tmp_path: Path
) -> None:
    found = operators_sources(
        operators_chart, application(OPERATORS_APPLICATION)["spec"]["source"]["helm"]["valuesObject"], tmp_path
    )
    print(f"\noperators: {len(found)} objects, {kinds([d for _, d in found])['CustomResourceDefinition']} CRDs")
    assert operators_failures(found, operator_charts(operators_chart)) == []


def test_operators_create_alone_installs_argo_cd(operators_chart: Path, tmp_path: Path) -> None:
    """THE RED CASE for the Argo CD half: without `argoCd.create: false`, Argo CD comes too."""
    failures = operators_failures(
        operators_sources(operators_chart, {"operators": {"create": True}}, tmp_path), operator_charts(operators_chart)
    )
    assert len(failures) == 2, failures
    assert f"'{ARGO_CD_SOURCE}'" in failures[0] and "Argo CD objects render" in failures[1], failures


def test_the_operators_example_installs_prometheus_where_the_modules_query_it(
    operators_chart: Path, pinned: Path, tmp_path: Path
) -> None:
    """The Service the modules' default address names exists in the operators render."""
    import tarfile

    found = operators_sources(
        operators_chart, application(OPERATORS_APPLICATION)["spec"]["source"]["helm"]["valuesObject"], tmp_path
    )
    services = [(d["metadata"]["name"], d["metadata"].get("namespace")) for _, d in found if d["kind"] == "Service"]
    assert PROMETHEUS_SERVICE in services, services
    name, namespace = PROMETHEUS_SERVICE
    with tarfile.open(pinned, "r:gz") as archive:
        for module in AUTOSCALING_MODULES:
            values = yaml.safe_load(archive.extractfile(f"yadgar/charts/{module}/values.yaml").read())
            assert values["autoscaling"]["prometheusAddress"] == f"http://{name}.{namespace}.svc.cluster.local", module


def test_prometheus_off_leaves_the_modules_nothing_to_query(operators_chart: Path, tmp_path: Path) -> None:
    """THE RED CASE for the Service: `operators.prometheus.create: false` removes it."""
    values_object = merged({"operators": {"prometheus": {"create": False}}}, OPERATORS_VALUES)
    found = operators_sources(operators_chart, values_object, tmp_path)
    services = [(d["metadata"]["name"], d["metadata"].get("namespace")) for _, d in found if d["kind"] == "Service"]
    assert PROMETHEUS_SERVICE not in services
    assert any("['prometheus']" in f for f in operators_failures(found, operator_charts(operators_chart)))


def test_an_operator_left_out_reddens_the_operators_gate(operators_chart: Path, tmp_path: Path) -> None:
    """THE RED CASE for the other half: without KEDA, its source and its API version are missing."""
    values_object = merged({"operators": {"keda": {"create": False}}}, OPERATORS_VALUES)
    failures = operators_failures(operators_sources(operators_chart, values_object, tmp_path), operator_charts(operators_chart))
    assert any("['keda']" in failure for failure in failures), failures


def platform_declared(chart: Path) -> dict:
    """`platform`'s default values, plus every path a dependency `condition` reads.

    `operators.argoCd.create` is declared by no `values.yaml`: it is the first path
    of the `argo-cd` dependency's `condition` in `platform`'s `Chart.yaml`. Helm
    reads it all the same, so it is a real key.
    """
    import tarfile

    with tarfile.open(chart, "r:gz") as archive:
        defaults = yaml.safe_load(archive.extractfile("platform/values.yaml").read()) or {}
        metadata = yaml.safe_load(archive.extractfile("platform/Chart.yaml").read())
    for dependency in metadata.get("dependencies") or []:
        for path in str(dependency.get("condition") or "").split(","):
            if path:
                node: dict = {}
                *parents, leaf = path.strip().split(".")
                cursor = node
                for step in parents:
                    cursor = cursor.setdefault(step, {})
                cursor[leaf] = None
                defaults = merged(node, defaults)
    return defaults


def test_every_operators_example_key_is_one_platform_declares(operators_chart: Path) -> None:
    values_object = application(OPERATORS_APPLICATION)["spec"]["source"]["helm"]["valuesObject"]
    assert undeclared_leaves(values_object, platform_declared(operators_chart), "platform") == []


def schema_refusal_names(stderr: str, chart: str, path_segment: str, key: str) -> bool:
    """`stderr` is a helm schema refusal naming `chart`, `path_segment` and `key`. PURE.

    TOLERANT OF BOTH VALIDATOR SHAPES, so a helm bump does not redden this on
    its own: helm 4.3.0 writes `at '/<path_segment>': additional properties
    '<key>' not allowed`, and helm 3.18.4 writes `<path_segment>: Additional
    property <key> is not allowed`, with no quotes around either name. Plain
    substrings catch both; a regex anchored to one shape would not.
    """
    return (
        "values don't meet the specifications of the schema(s)" in stderr
        and f"{chart}:" in stderr
        and path_segment in stderr
        and key in stderr
    )


def test_a_misspelt_argo_cd_key_reddens_the_closed_operators_schema(operators_chart: Path, tmp_path: Path) -> None:
    """THE RED CASE: `platform`'s `operators` schema is closed (since 0.1.33), so a typo refuses.

    `argoCD` no longer installs Argo CD by being ignored — that was true before
    the pin closed the schema, and the render refuses before anything installs.
    Two gates still name the same typo for two different reasons:
    `undeclared_leaves` against `platform_declared` (this suite's own
    leaf-recognition check, independent of any chart's schema), and the
    `operators` schema's own refusal.
    """
    values_object = {"operators": {"create": True, "argoCD": {"create": False}}}
    failures = undeclared_leaves(values_object, platform_declared(operators_chart), "platform")
    assert len(failures) == 1 and "`operators.argoCD.create`" in failures[0], failures
    values = overlay(tmp_path / "operators-values.yaml", yaml.safe_dump(values_object))
    result = helm(
        "template", "operators", str(operators_chart), "-n", OPERATORS_NAMESPACE, "--include-crds", "-f", str(values)
    )
    assert result.returncode != 0, result.stdout
    assert schema_refusal_names(result.stderr, "platform", "operators", "argoCD"), result.stderr


# ─── the kind example ──────────────────────────────────────────────────────────


def kind_values() -> dict:
    return application(KIND_APPLICATION)["spec"]["source"]["helm"]["valuesObject"]


def kind_mapping_failures(cluster: dict, values_object: dict) -> list[str]:
    """The kind config and the kind Application must describe one edge. PURE."""
    from urllib.parse import urlsplit

    failures = []
    nodes = cluster.get("nodes") or []
    if [node.get("role") for node in nodes] != ["control-plane"]:
        return [f"the kind config is not one control-plane node: {nodes}"]
    (node,) = nodes
    if node.get("image") != KIND_NODE_IMAGE:
        failures.append(f"the node image is `{node.get('image')}`, not the measured `{KIND_NODE_IMAGE}`")
    mappings = node.get("extraPortMappings") or []
    if len(mappings) != 1:
        return failures + [f"the kind config maps {len(mappings)} ports, not the one edge port"]
    (mapping,) = mappings
    node_port = value_at(values_object, "platform.gatewayListener.envoyProxy.httpsNodePort")
    enrolment = urlsplit(str(value_at(values_object, "iam.enrolment.gateway")))
    if mapping.get("containerPort") != node_port:
        failures.append(f"containerPort {mapping.get('containerPort')} is not httpsNodePort {node_port}")
    if mapping.get("hostPort") != enrolment.port:
        failures.append(f"hostPort {mapping.get('hostPort')} is not the enrolment URL's port {enrolment.port}")
    if mapping.get("listenAddress") != KIND_LISTEN_ADDRESS:
        failures.append(f"listenAddress {mapping.get('listenAddress')} is not {KIND_LISTEN_ADDRESS}")
    if enrolment.hostname != value_at(values_object, HOSTNAME_KEY):
        failures.append(f"the enrolment URL's host {enrolment.hostname} is not `{HOSTNAME_KEY}`")
    return failures


def test_the_kind_config_maps_the_port_the_kind_example_pins() -> None:
    assert kind_mapping_failures(yaml.safe_load(KIND_CONFIG.read_text()), kind_values()) == []


@pytest.mark.parametrize(
    ("field", "value", "named"),
    [
        ("hostPort", 18444, "hostPort 18444"),
        ("containerPort", 30444, "containerPort 30444"),
        ("listenAddress", "0.0.0.0", "listenAddress 0.0.0.0"),
    ],
)
def test_a_kind_mapping_that_drifts_from_the_example_reddens_the_mapping_gate(field: str, value, named: str) -> None:
    cluster = yaml.safe_load(KIND_CONFIG.read_text())
    cluster["nodes"][0]["extraPortMappings"][0][field] = value
    failures = kind_mapping_failures(cluster, kind_values())
    assert len(failures) == 1 and named in failures[0], failures


def test_an_unpinned_kind_node_image_reddens_the_mapping_gate() -> None:
    cluster = yaml.safe_load(KIND_CONFIG.read_text())
    cluster["nodes"][0]["image"] = "kindest/node:v1.36.1"
    (failure,) = kind_mapping_failures(cluster, kind_values())
    assert "not the measured" in failure, failure


def kind_edge_failures(documents: list[dict], values_object: dict) -> list[str]:
    """What the render must carry for kind's mapping to reach the edge. PURE."""
    proxies = [d for d in documents if d.get("kind") == "EnvoyProxy" and d["metadata"]["name"] == KIND_EDGE]
    if len(proxies) != 1:
        return [f"{len(proxies)} EnvoyProxy objects named `{KIND_EDGE}`"]
    kubernetes = proxies[0]["spec"]["provider"]["kubernetes"]
    service = kubernetes.get("envoyService") or {}
    pod = (kubernetes.get("envoyDeployment") or {}).get("pod") or {}
    stated = values_object["platform"]["gatewayListener"]["envoyProxy"]
    failures = []
    if service.get("type") != "NodePort":
        failures.append(f"the edge Service type renders `{service.get('type')}`, not NodePort")
    ports = (((service.get("patch") or {}).get("value") or {}).get("spec") or {}).get("ports")
    if ports != [{"port": 443, "nodePort": stated["httpsNodePort"]}]:
        failures.append(f"the edge Service patch renders ports {ports}, not 443 on node port {stated['httpsNodePort']}")
    if pod.get("nodeSelector") != stated["pod"]["nodeSelector"]:
        failures.append(f"the Envoy pods render nodeSelector {pod.get('nodeSelector')}")
    if pod.get("tolerations") != stated["pod"]["tolerations"]:
        failures.append(f"the Envoy pods render tolerations {pod.get('tolerations')}")
    host = value_at(values_object, HOSTNAME_KEY)
    sites = hostname_sites(documents)
    expected = {**derived_from(host), "iam.enrolment.gateway": value_at(values_object, "iam.enrolment.gateway")}
    failures += [f"`{key}` renders {sites[key]!r}, not {expected[key]!r}" for key in expected if sites[key] != expected[key]]
    return failures


def test_the_kind_example_renders_a_node_port_edge_and_the_enrolment_port(pinned: Path, tmp_path: Path) -> None:
    result = example_render(pinned, kind_values(), tmp_path)
    assert result.returncode == 0, result.stderr
    documents = [d for d in yaml.safe_load_all(result.stdout) if isinstance(d, dict) and d.get("apiVersion")]
    assert kind_edge_failures(documents, kind_values()) == []
    assert identities(documents) == identities(render(str(pinned), *API_VERSIONS, "-f", str(EXPLICIT_TLS)))


def test_the_kind_example_on_heads_chart_probes_prometheus(packaged: Path, tmp_path: Path) -> None:
    """HEAD's defaults, which the next tag publishes, turn the preflight's prometheus arm on."""
    result = example_render(packaged, kind_values(), tmp_path)
    assert result.returncode == 0, result.stderr
    documents = [d for d in yaml.safe_load_all(result.stdout) if isinstance(d, dict) and d.get("apiVersion")]
    assert "prometheus" in probes_declared(documents)
    assert prometheus_address_failures(documents) == []


def test_the_load_balancer_example_reddens_the_kind_edge_gate(pinned: Path, tmp_path: Path) -> None:
    """THE RED CASE: `application.yaml`'s render has none of what kind needs."""
    result = example_render(pinned, example_source()["helm"]["valuesObject"], tmp_path)
    assert result.returncode == 0, result.stderr
    documents = [d for d in yaml.safe_load_all(result.stdout) if isinstance(d, dict) and d.get("apiVersion")]
    failures = kind_edge_failures(documents, kind_values())
    assert any("not NodePort" in failure for failure in failures), failures
    assert any("node port 30443" in failure for failure in failures), failures
    assert any("nodeSelector" in failure for failure in failures), failures
    assert any("`iam.enrolment.gateway`" in failure for failure in failures), failures
