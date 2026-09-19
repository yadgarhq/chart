"""`scripts/vendored_matches_pins.py` must refuse each way the vendored subcharts can drift.

WHY EVERY REFUSAL IS DEMANDED AND NOT JUST THE HAPPY PATH. This gate is the only
thing standing between `chart/Chart.yaml` and a published parent carrying the
wrong subchart under the right version number — helm exits 0 on that state, on
both helm 3 and helm 4, at package, at `lint --strict` and at `template`. A gate
guarded by nothing is one refactor away from a green tick that checks nothing, so
each case below feeds it a specific drift and demands the refusal, rather than
only feeding it a conforming tree.

NO SKIPS (ADR-0650). These tests read and write files and need no helm at all, so
there is no environment in which skipping them would be honest.

Run: python3 -m pytest scripts/tests/ -q
"""

from __future__ import annotations

import importlib.util
import io
import shutil
import tarfile
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
GATE = REPO / "scripts" / "vendored_matches_pins.py"


def load_gate():
    """The gate as a module. Imported by path because `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location("vendored_matches_pins", GATE)
    assert spec and spec.loader, f"{GATE} is not importable"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load_gate()


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A copy of this repository's real `chart/`, as the working directory.

    A COPY OF THE REAL ONE RATHER THAN A FIXTURE BUILT BY HAND. A synthetic tree
    would let this suite keep passing after the real chart stopped matching its
    own shape, which is the class of green these tests exist to refuse.
    """
    shutil.copytree(REPO / "chart", tmp_path / "chart")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def read(tree: Path, name: str):
    return yaml.safe_load((tree / "chart" / name).read_text())


def write(tree: Path, name: str, document) -> None:
    (tree / "chart" / name).write_text(yaml.safe_dump(document, sort_keys=False))


def repackage(path: Path, name: str, version: str) -> None:
    """Rewrite `path` as a packaged chart whose INNER Chart.yaml says `name`/`version`."""
    metadata = yaml.safe_dump({"apiVersion": "v2", "name": name, "version": version})
    payload = metadata.encode()
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo(f"{name}/Chart.yaml")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))


# --------------------------------------------------------------- the real tree


def test_the_committed_tree_passes(tree: Path) -> None:
    assert gate.check() == []


def test_the_real_chart_pins_all_eight_modules(tree: Path) -> None:
    """The parent IS the estate, so a pin quietly going missing is a finding.

    Not a rule the gate enforces — `MINIMUM_DEPENDENCIES` is a floor of one, on
    purpose, because the day a module is retired the gate must not be the thing
    that refuses. This asserts today's set instead, so a deletion arrives as a
    failing test somebody has to justify.
    """
    declared = {name for name, _, _ in gate.triples(read(tree, "Chart.yaml"), gate.CHART_YAML)}
    assert declared == {
        "config",
        "gateway",
        "iam",
        "iam-db",
        "project",
        "project-db",
        "task",
        "task-db",
    }


def test_every_pin_is_an_exact_version(tree: Path) -> None:
    for name, version, repository in gate.triples(read(tree, "Chart.yaml"), gate.CHART_YAML):
        assert gate.EXACT_VERSION.match(version), f"{name} is pinned as {version}"
        assert repository == "oci://ghcr.io/yadgarhq/charts", name


# --------------------------------------------------------------- each refusal


def test_a_bumped_pin_with_a_stale_tarball_is_refused(tree: Path) -> None:
    """THE CASE THIS GATE EXISTS FOR — ADR-0722's automation bumping and not re-vendoring."""
    document = read(tree, "Chart.yaml")
    for entry in document["dependencies"]:
        if entry["name"] == "gateway":
            entry["version"] = "0.9.49"
    write(tree, "Chart.yaml", document)
    problems = gate.check()
    assert problems, "a bumped pin with a stale tarball was accepted"
    assert any("gateway-0.9.49.tgz" in problem for problem in problems)


def test_a_lock_that_disagrees_with_chart_yaml_is_refused(tree: Path) -> None:
    document = read(tree, "Chart.lock")
    document["dependencies"][0]["version"] = "9.9.9"
    write(tree, "Chart.lock", document)
    problems = gate.check()
    assert any("Chart.lock" in problem for problem in problems)


def test_a_missing_tarball_is_refused(tree: Path) -> None:
    (tree / "chart" / "charts" / "task-0.5.28.tgz").unlink()
    problems = gate.check()
    assert any("task-0.5.28.tgz" in problem for problem in problems)


def test_a_tarball_no_dependency_asks_for_is_refused(tree: Path) -> None:
    """`helm package` ships everything in `charts/`, declared or not."""
    repackage(tree / "chart" / "charts" / "audit-0.1.0.tgz", "audit", "0.1.0")
    problems = gate.check()
    assert any("audit-0.1.0.tgz" in problem for problem in problems)


def test_a_renamed_tarball_is_refused_on_its_contents(tree: Path) -> None:
    """The cheapest wrong fix for a missing tarball is to rename the one you have."""
    charts = tree / "chart" / "charts"
    (charts / "gateway-0.9.48.tgz").rename(charts / "gateway-0.9.49.tgz")
    document = read(tree, "Chart.yaml")
    for entry in document["dependencies"]:
        if entry["name"] == "gateway":
            entry["version"] = "0.9.49"
    write(tree, "Chart.yaml", document)
    lock = read(tree, "Chart.lock")
    for entry in lock["dependencies"]:
        if entry["name"] == "gateway":
            entry["version"] = "0.9.49"
    write(tree, "Chart.lock", lock)
    problems = gate.check()
    assert problems, "a renamed tarball satisfied a gate that reads only filenames"
    assert any("its own `Chart.yaml` says" in problem for problem in problems)


def test_a_version_range_is_refused(tree: Path) -> None:
    document = read(tree, "Chart.yaml")
    for entry in document["dependencies"]:
        if entry["name"] == "iam":
            entry["version"] = "^0.8.0"
    write(tree, "Chart.yaml", document)
    problems = gate.check()
    assert any("not an exact version" in problem for problem in problems)


def test_a_duplicated_dependency_is_refused(tree: Path) -> None:
    document = read(tree, "Chart.yaml")
    document["dependencies"].append(
        {"name": "iam", "version": "0.8.39", "repository": "oci://ghcr.io/yadgarhq/charts"}
    )
    write(tree, "Chart.yaml", document)
    problems = gate.check()
    assert any("more than once" in problem for problem in problems)


def test_an_empty_dependency_block_is_refused(tree: Path) -> None:
    """A gate that reports success having inspected nothing is the failure it prevents."""
    write(tree, "Chart.yaml", {"apiVersion": "v2", "name": "yadgar", "dependencies": []})
    problems = gate.check()
    assert any("fewest this gate can inspect" in problem for problem in problems)


def test_a_missing_charts_directory_is_refused(tree: Path) -> None:
    shutil.rmtree(tree / "chart" / "charts")
    problems = gate.check()
    assert any("does not exist" in problem for problem in problems)


def test_a_tarball_that_is_not_a_chart_is_refused(tree: Path) -> None:
    path = tree / "chart" / "charts" / "config-0.1.5.tgz"
    path.write_bytes(b"not a gzip stream at all")
    with pytest.raises(gate.Refused):
        gate.check()


def test_a_missing_lock_is_refused(tree: Path) -> None:
    (tree / "chart" / "Chart.lock").unlink()
    with pytest.raises(gate.Refused):
        gate.check()


def test_main_reports_the_refusal_as_a_non_zero_exit(tree: Path) -> None:
    (tree / "chart" / "charts" / "iam-0.8.39.tgz").unlink()
    assert gate.main() == 1


def test_main_passes_on_the_committed_tree(tree: Path) -> None:
    assert gate.main() == 0
