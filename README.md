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
  targetRevision: 0.1.0
```

`example/application.yaml` is that file in full, with every line you may need to
edit marked. `example/values.yaml` is how you change a module's setting from your
own repository without forking anything.

**There is no published parent yet.** `ghcr.io/yadgarhq/charts/yadgar` has no tags
as of 2026-09-19. The first one appears when this repository is tagged, and the
`0.1.0` above assumes that tag is `v0.1.0` — `next_version.py` derives every
version after the first from the Changelog but has an explicit branch saying "the
first tag of a repository is cut by hand", so the number is whoever cuts it's
choice. A different first tag makes this snippet, `example/application.yaml`'s
`targetRevision` and `example/values.yaml`'s two `--version` examples name a
version that does not exist.

## What it contains, and what it deliberately does not

```
chart/Chart.yaml          the eight pins, and nothing else of substance
chart/Chart.lock          written by `helm dependency update`, never by hand
chart/charts/*.tgz        THE RESOLVED SUBCHARTS, COMMITTED — see below
chart/values.yaml         almost empty, and the comment explains the one line in it
chart/templates/          one partial that renders nothing, and it says why
example/application.yaml  what you commit to your own repository
example/values.yaml       how you set a module's knob from your own repository
scripts/vendored_matches_pins.py   the gate that keeps chart/charts/ honest
```

**It renders no objects of its own.** Every one of the 38 objects a default
install produces comes from one of the eight module charts, each reviewed, gated
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

## The subcharts are committed, and this is the one place this repository differs from its siblings

`yadgarhq/config` ignores `chart/charts/` outright. Copying that line here would
have been silent and fatal, so here is the measurement.

`ci-release.yaml`'s `chart` job in `yadgarhq/actions` runs a bare
`helm package chart`. Every other chart in this estate is a leaf with no
dependencies, so that job has never had to resolve anything — and `helm package`
refuses a chart whose declared dependencies are absent:

```
Error: found in Chart.yaml, but missing in charts/ directory:
config, gateway, iam, iam-db, project, project-db, task, task-db
```

With `chart/charts/` ignored, this repository's first release would fail at the
package step with nothing published. The subcharts are therefore resolved at
commit time and committed, which is 216 KB across eight files.

**What that buys an adopter:** a self-contained package. `helm install` does not
resolve dependencies — it expects the subcharts to be inside the artifact — and
measured 2026-09-19, the published parent carries all eight expanded under
`yadgar/charts/<module>/`. So an install needs exactly one anonymous pull and
touches no other registry path.

**What it costs, and what stops it hurting.** A pin bumped in `chart/Chart.yaml`
with a stale tarball still in `chart/charts/` packages, lints `--strict` and
templates with **exit 0** on both helm 3.20.2 and helm 4.2.3, and publishes the
old subchart under the new version number. The only helm command that notices is
`helm dependency build`, and no gate in this estate runs it.
`scripts/vendored_matches_pins.py` is what turns that into a refused commit: it
compares `Chart.yaml`, `Chart.lock` and each tarball's own inner `Chart.yaml`, so
a renamed file does not satisfy it either. ADR-0722's automatic pin bump has to
refresh `chart/charts/` in the same commit, and this gate is what says so.

## Every version here is the semver maximum, never the lexical one

A lexical sort of `gateway`'s 74 published tags answers `0.9.9`. The newest is
`0.9.48`. Lexical ordering is wrong for six of the eight pins today — `gateway`,
`iam`, `iam-db`, `project`, `task` and `task-db` — and ADR-0690 records the same
error producing nineteen downgrade pull requests in this estate. **Any automation
that writes a pin in `chart/Chart.yaml` must order semver numerically.** A lexical
maximum pins a downgrade and nothing downstream notices.

## How a change here is proven

`python3 -m pytest scripts/tests/ -q`, which the `pytest-scripts` pre-commit hook
runs on every commit. Everything below runs offline, because the subcharts are
committed.

| what                                                  | asserted as                                                                                            |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| the parent renders nothing of its own                 | an empty render with every subchart removed                                                            |
| a default install is 38 objects                       | 9 ConfigMap, 7 Deployment, 7 Service, 7 ServiceAccount, 7 PodDisruptionBudget, 1 HTTPRoute             |
| the PACKAGED chart renders what the directory renders | the same `(apiVersion, kind, name)` set from `helm package`'s output as from `chart/`                  |
| the package is self-contained                         | `yadgar/charts/<module>/Chart.yaml` present inside the `.tgz` for all eight                            |
| an adopter's value reaches a child (goal item 6)      | `config.shared.tlsRotation.pollSeconds: 45` renders `45` while `splayMaxSeconds` keeps the chart's 300 |
| it installs on a bare cluster (D80)                   | the all-off render carries no resource outside the built-in Kubernetes API groups                      |
| the committed subcharts match the pins                | each refusal of `vendored_matches_pins.py` demanded, not only a conforming tree                        |

The object count is an equality rather than a ceiling on purpose. A module release
that adds or drops an object changes what an adopter of the parent receives, and
ADR-0722 removed the compatibility gate that used to sit in front of that. A bump
whose effect on the rendered set nobody looked at is exactly the state those
numbers exist to interrupt: update them in the same commit as the pin, and say in
the pull request which module moved them.

## What lives elsewhere

- **The module charts.** Eight repositories, each with its own gates, its own
  release and its own pod specs. This repository asserts nothing about a
  Deployment; `chart-baseline` and `chart-network-policy` are adopted there, not
  here, because ADR-0584 forbids adopting a gate in a repository it hard-fails and
  this chart has no pod spec to check.
- **The reference installation.** `yadgarhq/deploy` is how our own cluster runs,
  and it does not use this chart yet. Converting it is a later phase and needs a
  published parent version to pin first.
- **The development ApplicationSet.** D54's per-module discovery in
  `yadgarhq/argocd` stays as a development mechanism and is NOT shipped to an
  adopter. This chart is what an adopter gets.
- **Configuration defaults.** `yadgarhq/config`, reached through this parent as
  `config.<document>.<knob>`.
