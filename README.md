# yadgar/chart

**The whole of yadgar as one thing you install.** This repository holds a single
parent Helm chart that declares every module as a dependency pinned to a released
version, so an adopter commits one Argo `Application` at one version rather than
standing up eight and keeping their versions in step by hand (D60, as amended by
ADR-0706; this repository is authorised by ADR-0723).

```yaml
# your GitOps repository, and this is the whole of it
source:
  repoURL: ghcr.io/yadgarhq/charts
  chart: yadgar
  targetRevision: 0.3.8
  helm:
    valuesObject:
      global:
        hostname: yadgar.example.com # your hostname, once
      platform:
        edgeTLS:
          issuerRef: { name: letsencrypt-production, kind: ClusterIssuer } # your issuer
```

**The adopter minimum is two things: your hostname and your edge issuer.**
`example/application.yaml` is that file in full, with every line you may need to
edit marked: the pinned version, and an inline `valuesObject` holding only what the
chart cannot default. The suite pulls that pinned version from the registry and
renders it with that `valuesObject` on every commit. `example/values.yaml` restates every default with
a comment on each, for when you change more.

## What it contains, and what it deliberately does not

```
chart/Chart.yaml          the eight pins, and nothing else of substance
chart/values.yaml         the whole-estate defaults, and why each key is stated here
chart/ci/api-versions.txt the four operator API versions the defaults need offline
chart/templates/          one partial that renders nothing, and it says why
example/application.yaml  what you commit to your own repository
example/operators-application.yaml  the four operators it needs; sync it first
example/kind/             the same install on a kind cluster: NodePort edge, kind config
example/values.yaml       how you set a module's knob from your own repository
```

`chart/charts/` and `chart/Chart.lock` are not in that list, and not in the
repository: per ADR-0725 the release pipeline resolves the eight pins at
package time (`helm package chart -u`), so nothing here is ever committed.
`chart/charts/` is git-ignored the same way `yadgarhq/config`'s is.

**It renders no objects of its own.** Every one of the 81 objects a default
install produces comes from one of the eight module charts or the platform layer, each reviewed, gated
and released in its own repository. A parent that rendered a Deployment or a
ConfigMap of its own would be a ninth module nobody declared, and ADR-0723 names
that outcome in its own `revisit_trigger`. `chart/templates/` exists only because
`helm lint --strict` refuses a chart without it, and the one file in there is a
partial that defines nothing.

**It carries no `values.schema.json`, and that is a decision.** A parent schema
would have to enumerate every knob of all eight children to avoid refusing a
legitimate one, and it would then drift from them on the first module release that
adds a knob. The cost is real and it is stated where an adopter meets it: seven of
the eight module charts have no schema of their own, so a key no child declares is
accepted and silently ignored. `config` is the exception — its schema is closed at
every level, so a typo under `config:` is refused by name. Closing the gap for the
other seven belongs in those seven charts, not in a file here that would own their
interfaces from outside them.

## What the defaults install

**The whole estate** (ADR-0803 step B6): every module, the platform layer
(`yadgarhq/platform` — internal CA and its leaves, the edge leaf, the Gateway
listener, Valkey, NATS and the bootstrap Jobs), autoscaling in all seven modules
and a database in each of the three `-db` modules. 81 objects. `example/values.yaml`
restates the same defaults so you can see every choice, and the suite holds the
two renders equal.

**Four operators must already run in the cluster**: cert-manager, Envoy Gateway,
mariadb-operator and KEDA. The chart installs none of them by default
(`platform.operators.create` stays false). Each chart that uses one carries a
render check that refuses, naming the operator, rather than letting a sync fail
half-way. Argo and `helm install` read the API versions from the cluster. An
offline `helm template` knows only the built-in groups, so a bare render refuses;
pass the four declared in `chart/ci/api-versions.txt`. The `sed` drops `#`
comments and blank lines, which the shared reader permits in that file:

```
helm template yadgar chart $(sed -e 's/#.*//' -e 's/[[:space:]]//g' -e '/^$/d' -e 's/^/--api-versions /' chart/ci/api-versions.txt)
```

The shared gates in `yadgarhq/actions` read the same file (ADR-0806).

**State your hostname once, in `global.hostname` (ADR-0808).** The five places
that carry it — `platform`'s listener hostname, the edge certificate's common name
and DNS names, `gateway`'s HTTPRoute and `iam`'s enrolment URL — derive from it,
so they cannot disagree. Left empty, all five render `gateway.yadgar.internal`,
which resolves for nobody. A per-chart key you set still wins over the global.

- `iam`'s enrolment URL is derived as `https://<hostname>` with **no port**: it
  assumes the edge listener on 443. `iam` copies it into every enrolment token and
  the client dials it, so an edge on another port sets `iam.enrolment.gateway`
  itself.
- **To turn IssueEnrolment off, set `iam.enrolment.enabled: false`.** That renders
  `ENROLMENT_GATEWAY` empty whatever the other keys say; iam logs a warning at boot
  and only IssueEnrolment refuses. An empty `iam.enrolment.gateway` no longer does
  this — it now means "derive from `global.hostname`".

**Name your edge issuer.** `platform.edgeTLS.issuerRef` is empty by default, and
`platform` then issues the edge certificate from the internal CA — it goes Ready,
and no client outside the cluster trusts it.

**To run your own platform layer**, set `platform.enabled` false and clear
`gateway.adminBootstrap.tokenSecret` (ADR-0807):

```yaml
platform:
  enabled: false
gateway:
  adminBootstrap:
    tokenSecret: ""
```

`platform.enabled` false turns the whole layer off, whatever the `create` toggles
say — except `platform.operators.create`, which this chart refuses on every path
(ADR-0787), the opt-out included. It must stay unset or false. Clear the token unless you mint that Secret yourself: with the layer off
nothing mints it, and the gateway exits at boot on a named Secret it cannot read.
The chart does not refuse a forgotten clear — the render succeeds. Turn off
`autoscaling.enabled` and `database.create` in the modules whose KEDA or
mariadb-operator you do not run.

## The subcharts are resolved at release time, not committed

`ci-release.yaml`'s `chart` job in `yadgarhq/actions` runs
`helm package chart -u --version ... --app-version ...` (ADR-0725). The `-u`
resolves this chart's eight dependencies from `oci://ghcr.io/yadgarhq/charts`
before packaging, so nothing here has to be committed for a release to
publish — `chart/charts/` stays git-ignored, exactly as `yadgarhq/config`'s is.

The first cut of this repository committed the resolved tarballs instead,
because `yadgarhq/actions` was out of scope at the time and a bare
`helm package chart` with no `-u` refuses a chart whose declared dependencies
are absent:

```
Error: found in Chart.yaml, but missing in charts/ directory:
config, gateway, iam, iam-db, project, project-db, task, task-db
```

ADR-0725 rules that out. A stale vendored subchart is silent on every tool
this estate runs — `helm package`, `helm lint --strict` and `helm template`
all exited 0 on a `Chart.yaml` pinning `gateway 0.9.49` while `chart/charts/`
still held `gateway-0.9.48.tgz`, on helm 3 and helm 4 alike, and the published
artifact shipped the old subchart under the new version number. Resolving at
release time removes that disagreement rather than adding a gate to detect it.

**What an adopter still gets is a self-contained package.** `helm install`
does not resolve dependencies — it expects the subcharts to be inside the
artifact — and `-u` expands OCI dependencies into the tarball as directories
(`yadgar/charts/<module>/Chart.yaml`), not nested archives, before the package
is written. So an install needs exactly one anonymous pull and touches no
other registry path; only the release job, not the adopter, ever resolves
anything.

## Every version here is the semver maximum, never the lexical one

A lexical sort of `gateway`'s 74 published tags answers `0.9.9`. The newest is
`0.9.48`. Lexical ordering is wrong for six of the eight pins today — `gateway`,
`iam`, `iam-db`, `project`, `task` and `task-db` — and ADR-0690 records the same
error producing nineteen downgrade pull requests in this estate. **Any automation
that writes a pin in `chart/Chart.yaml` must order semver numerically.** A lexical
maximum pins a downgrade and nothing downstream notices.

## How a change here is proven

`python3 -m pytest scripts/tests/ -q`, which the `pytest-scripts` pre-commit hook
runs on every commit. The packaged-chart fixture resolves dependencies with
`helm package chart -u`, the same command `ci-release.yaml` runs, so this
suite needs the registry reachable rather than running offline.

| what                                                   | asserted as                                                                                            |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| the parent renders nothing of its own                  | an empty render with every subchart removed                                                            |
| a default install is the whole estate (K1)             | the defaults render the adopter values' 81-object set; every example leaf equals its default           |
| the defaults refuse offline without the operators (K2) | a bare render refuses; dropping any one of the four declared API versions refuses, naming it           |
| the modules alone are 32 objects                       | 3 ConfigMap, 7 Deployment, 7 Service, 7 ServiceAccount, 7 PodDisruptionBudget, 1 HTTPRoute             |
| the PACKAGED chart renders what the directory renders  | the same `(apiVersion, kind, name)` set from `helm package`'s output as from `chart/`                  |
| the package is self-contained                          | `yadgar/charts/<module>/Chart.yaml` present inside the `.tgz` for all eight                            |
| an adopter's value reaches a child (goal item 6)       | `config.shared.tlsRotation.pollSeconds: 45` renders `45` while `splayMaxSeconds` keeps the chart's 300 |
| a value for one child reaches no other                 | `config.…pollSeconds` and `gateway.toolsPoll.intervalSeconds` each land in their own ConfigMap only    |
| no knob is stated in two ConfigMaps                    | every leaf key path in every rendered ConfigMap, refused when two ConfigMaps state one path            |
| a push to `main` is validated                          | `push_validation`'s own `if:` evaluated against four event contexts, and it declares no `needs:`       |
| it installs on a bare cluster (D80)                    | every `enabled` and `create` false: no resource outside the built-in Kubernetes API groups             |

The object count is an equality rather than a ceiling on purpose. A module release
that adds or drops an object changes what an adopter of the parent receives, and
ADR-0722 removed the compatibility gate that used to sit in front of that. A bump
whose effect on the rendered set nobody looked at is exactly the state those
numbers exist to interrupt: update them in the same commit as the pin, and say in
the pull request which module moved them.

`push_validation` in `.github/workflows/ci.yaml` runs that suite and
`helm lint --strict` on a push to `main`. ADR-0722's `parent_bump.py` writes the
eight pins straight to `main` over the Contents API, which passes through no pull
request, and every validation job of the shared `ci-pr.yaml` skips on a push — so
until it existed the one commit that ever changes the pins was checked by nothing.
**It is a notification and not a wall.** Publishing fires on the TAG through
`ci-release.yaml` and depends on no job in this file, so a broken pin makes `main`
red and visible while `charts/yadgar` still publishes. Making it a wall means
changing the shared release workflow.

## What lives elsewhere

- **The module charts.** Eight repositories, each with its own gates, its own
  release and its own pod specs. This repository asserts nothing about a
  Deployment; `chart-baseline` and `chart-network-policy` are adopted there, not
  here, because ADR-0584 forbids adopting a gate in a repository it hard-fails and
  this chart has no pod spec to check.
- **The reference installation.** `yadgarhq/deploy` is how our own cluster runs,
  and it pins this chart with its own values file. Moving it to
  this example's shape is phase E of `plans/the-one-application-install.md`.
- **The development ApplicationSet.** D54's per-module discovery in
  `yadgarhq/argocd` stays as a development mechanism and is NOT shipped to an
  adopter. This chart is what an adopter gets.
- **Configuration defaults.** `yadgarhq/config`, reached through this parent as
  `config.<document>.<knob>`.
