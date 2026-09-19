#!/usr/bin/env python3
"""The subchart in `chart/charts/` must be the subchart `chart/Chart.yaml` pins.

WHY THIS GATE EXISTS, measured rather than imagined. This is the estate's first
parent chart, and `ci-release.yaml`'s `chart` job packages with a bare
`helm package chart` and no `helm dependency update` in front of it. `helm
package` refuses a chart whose declared dependencies are absent, so the resolved
subcharts are COMMITTED here rather than fetched at release time — see
`.gitignore`, which is the one place this repository deliberately differs from
`yadgarhq/config`.

Committing them buys a self-contained artifact and introduces exactly one new
failure, which is silent on every tool the estate runs. Measured 2026-09-19 with
`chart/Chart.yaml` pinning `gateway 0.9.49` while `chart/charts/` still held
`gateway-0.9.48.tgz`:

    helm 4.2.3   helm package  -> exit 0, packaged
                 helm lint --strict -> exit 0, 0 charts failed
                 helm template      -> exit 0
    helm 3.20.2  identical on all three

The published package then carries `gateway 0.9.48`'s templates under a manifest
that says `0.9.49`. Nothing in `ci-pr.yaml`, nothing in `ci-release.yaml` and no
shared pre-commit hook notices. The ONLY helm command that refuses is `helm
dependency build`, which compares `Chart.lock` against `Chart.yaml` — and no gate
in this estate runs it.

That matters most for the one thing this repository is about to grow. ADR-0722
has a module release rewrite a pin in `chart/Chart.yaml` and cut a new parent
version. An automation that rewrites the pin and does not refresh
`chart/charts/` publishes the wrong subchart under the right number, on every
release, silently. This gate is what turns that into a refused commit.

WHAT IT ASSERTS, and the third is the one a lock digest cannot give you:

1. `chart/Chart.lock` names the same dependency set as `chart/Chart.yaml`, with
   the same version and the same repository for each.
2. `chart/charts/` holds exactly one tarball per dependency, named
   `<name>-<version>.tgz`, and NO tarball that no dependency asks for.
3. THE TARBALL'S OWN `Chart.yaml` declares that name and that version. A
   filename is a claim about content and this is the only check that reads the
   content. `helm dependency update` writes honest filenames; a human editing a
   pin and renaming a file does not, and a rename is the cheapest wrong fix
   available to anybody who hits assertion 2.
4. Every pinned version is an EXACT version. A range makes the chart mean
   different things on different days, which is what pinning exists to stop, and
   `helm dependency update` would resolve it to whatever was newest that morning
   while `chart/Chart.yaml` kept claiming the range.

WHAT IT DELIBERATELY DOES NOT ASSERT. Whether a pin is the NEWEST published
version — that is a question for the registry, this gate runs offline, and an
adopter's reproducibility depends on an old pin staying installable rather than
on it being current. And whether the vendored bytes are the bytes the registry
served: `Chart.lock` records no per-dependency digest, so there is nothing
offline to compare against. `helm dependency update` is the only thing that can
answer it and it needs the network.

ORDERING CANNOT DEFEAT IT. The hook runs `always_run: true` with
`pass_filenames: false`, because the question is about the whole directory: a
mismatch is a property of two files together, and a hook that only saw the
changed one would miss half of every mismatch it exists to find. Same reasoning
`one_source_per_knob.py` uses in `yadgarhq/config` and `versions_pinned.py` uses
in `yadgarhq/argocd`.

Tests: `python3 -m pytest scripts/tests/ -q`.
"""

from __future__ import annotations

import io
import re
import sys
import tarfile
from pathlib import Path

import yaml

CHART = Path("chart")
CHART_YAML = CHART / "Chart.yaml"
CHART_LOCK = CHART / "Chart.lock"
CHARTS_DIR = CHART / "charts"

# An exact version and nothing else. `0.9.48` passes; `^0.9.48`, `~0.9`, `>=0.9`
# and `*` do not. Pre-release and build metadata are permitted because SemVer
# permits them and a module could legitimately publish one.
EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")

# A FLOOR RATHER THAN A COUNT. A gate that reports success having inspected
# nothing is the failure this estate has met four times over, and an empty
# `dependencies:` block would sail through every assertion below. The parent is
# the eight modules; if it ever legitimately declares fewer, that is a decision
# to bring to the record and this number moves with it.
MINIMUM_DEPENDENCIES = 1


def load(path: Path):
    """The YAML at `path`, or a refusal naming the file."""
    if not path.is_file():
        raise Refused(f"`{path}` does not exist, so there is nothing to compare.")
    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as error:
        raise Refused(f"`{path}` is not readable as YAML: {error}") from error


class Refused(Exception):
    """The gate has a verdict and it is no."""


def triples(document, path: Path):
    """`[(name, version, repository)]` in declaration order, refusing a malformed entry."""
    dependencies = document.get("dependencies")
    if not isinstance(dependencies, list):
        raise Refused(f"`{path}` declares no `dependencies:` list.")
    found = []
    for index, entry in enumerate(dependencies):
        if not isinstance(entry, dict):
            raise Refused(f"`{path}` dependency {index} is not a mapping.")
        name = entry.get("name")
        version = entry.get("version")
        repository = entry.get("repository")
        if not isinstance(name, str) or not name:
            raise Refused(f"`{path}` dependency {index} has no `name`.")
        if not isinstance(version, str) or not version:
            raise Refused(f"`{path}` dependency `{name}` has no `version`.")
        if not isinstance(repository, str) or not repository:
            raise Refused(f"`{path}` dependency `{name}` has no `repository`.")
        found.append((name, version, repository))
    return found


def inner_metadata(tarball: Path):
    """`(name, version)` out of the `Chart.yaml` INSIDE `tarball`.

    The member is `<anything>/Chart.yaml` at the first level, which is what
    `helm package` writes and what `helm` itself looks for. A tarball with no such
    member is not a chart, whatever it is named.
    """
    try:
        with tarfile.open(tarball, "r:gz") as archive:
            for member in archive.getmembers():
                parts = member.name.split("/")
                if len(parts) == 2 and parts[1] == "Chart.yaml" and member.isfile():
                    handle = archive.extractfile(member)
                    if handle is None:
                        break
                    document = yaml.safe_load(io.TextIOWrapper(handle).read()) or {}
                    if not isinstance(document, dict):
                        break
                    return document.get("name"), document.get("version")
    except (tarfile.TarError, OSError, yaml.YAMLError) as error:
        raise Refused(f"`{tarball}` could not be read as a packaged chart: {error}") from error
    raise Refused(
        f"`{tarball}` carries no `<chart>/Chart.yaml`, so it is not a packaged "
        f"chart. Delete it and run `helm dependency update chart`."
    )


def check() -> list[str]:
    """Every problem found, as operator-facing lines. Empty means the gate passes."""
    problems: list[str] = []

    declared = triples(load(CHART_YAML), CHART_YAML)
    if len(declared) < MINIMUM_DEPENDENCIES:
        return [
            f"`{CHART_YAML}` declares {len(declared)} dependency(ies), and "
            f"{MINIMUM_DEPENDENCIES} is the fewest this gate can inspect. A parent "
            f"chart with no dependencies renders nothing, and a gate reporting "
            f"success on it has checked nothing."
        ]

    names = [name for name, _, _ in declared]
    for name in sorted({n for n in names if names.count(n) > 1}):
        problems.append(
            f"`{CHART_YAML}` declares `{name}` more than once. Two pins for one "
            f"subchart is two writers for one value, and helm resolves the last."
        )

    for name, version, _ in declared:
        if not EXACT_VERSION.match(version):
            problems.append(
                f"`{name}` is pinned as `{version}`, which is not an exact "
                f"version. A range makes this chart mean a different thing on a "
                f"different day; an adopter who pinned one parent version must "
                f"get the same eight module versions a year later."
            )

    locked = triples(load(CHART_LOCK), CHART_LOCK)
    if declared != locked:
        problems.append(
            f"`{CHART_LOCK}` disagrees with `{CHART_YAML}`.\n"
            f"    Chart.yaml: {declared}\n"
            f"    Chart.lock: {locked}\n"
            f"  Run `helm dependency update chart` and commit both, together with "
            f"the tarballs it writes."
        )

    if not CHARTS_DIR.is_dir():
        problems.append(
            f"`{CHARTS_DIR}` does not exist. The resolved subcharts are committed "
            f"in this repository on purpose — `ci-release.yaml` runs `helm package` "
            f"with no `helm dependency update` in front of it, and `helm package` "
            f"refuses a chart whose dependencies are absent. Run "
            f"`helm dependency update chart`."
        )
        return problems

    expected = {f"{name}-{version}.tgz": (name, version) for name, version, _ in declared}
    present = {path.name for path in sorted(CHARTS_DIR.glob("*.tgz"))}

    for filename, (name, version) in sorted(expected.items()):
        if filename not in present:
            problems.append(
                f"`{CHART_YAML}` pins `{name} {version}` and "
                f"`{CHARTS_DIR}/{filename}` is not there. helm packages, lints "
                f"`--strict` and templates with exit 0 in this state on both helm "
                f"3 and helm 4, publishing whatever tarball IS there under the "
                f"version above. Run `helm dependency update chart`."
            )
            continue
        actual_name, actual_version = inner_metadata(CHARTS_DIR / filename)
        if (actual_name, actual_version) != (name, version):
            problems.append(
                f"`{CHARTS_DIR}/{filename}` is named for `{name} {version}` and "
                f"its own `Chart.yaml` says `{actual_name} {actual_version}`. A "
                f"filename is a claim about content; this is the check that reads "
                f"the content. Delete it and run `helm dependency update chart` "
                f"rather than renaming it."
            )

    for filename in sorted(present - set(expected)):
        problems.append(
            f"`{CHARTS_DIR}/{filename}` is a subchart no dependency in "
            f"`{CHART_YAML}` asks for. `helm package` ships everything in this "
            f"directory, so an adopter would receive a chart nothing declared. "
            f"Delete it, or declare it."
        )

    return problems


def main() -> int:
    try:
        problems = check()
    except Refused as error:
        print(f"{error}", file=sys.stderr)
        return 1
    if not problems:
        return 0
    print(
        "The committed subcharts do not match the pins in chart/Chart.yaml.\n",
        file=sys.stderr,
    )
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    print(
        "\nhelm would not have told you. `helm package`, `helm lint --strict` and\n"
        "`helm template` all exit 0 on a stale subchart, on helm 3 and helm 4 alike.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
