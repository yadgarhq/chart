"""ADR-1022 follow-up: THE EDGE BOUNDS A CLIENT THAT SENDS NO BYTE.

`platform.gatewayListener.requestHeadersTimeoutSeconds` bounds a request head
from its first byte to its last (`test_edge_headers_not_looser_than_gateway.py`).
A client that completes TLS and then sends no byte never starts that timer.
Envoy's `idleTimeout` holds it, and its default is 1 h. The gateway's own
header-read timer starts at accept, so behind Envoy that gap is the edge's
alone. `platform` closes it from `platform.gatewayListener.idleTimeoutSeconds`
(default 30 s, Max 2026-10-25), on the same ClientTrafficPolicy.

TWO REFUSALS, when the gateway sets a header-read bound and `platform` renders
the edge:
  - `platform` sets no idle value (a platform older than this change). The edge
    then holds a zero-byte client for about 1 h, which is the defect.
  - The idle value is below the edge's request-headers value. A policy choice,
    not an Envoy constraint: the two timers never run together. It keeps the
    edge from being stricter with a client that has sent nothing than with one
    that has started a request head.
    `platform` refuses this itself; the parent states it again because it is
    the one render that holds the values an adopter actually installs.

Fake subcharts, for the reason `test_envoy_idle_below_gateway_bound.py` gives.

Run: python3 -m pytest scripts/tests/ -q
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from test_parent_chart import CHART, GUARD_OPEN_SETS, helm

# The refusal sentences, by the words a reader searches for. LITERALS.
NO_IDLE_VALUE = (
    "the pinned platform chart sets no platform.gatewayListener.idleTimeoutSeconds"
)
BELOW_HEADERS = "must not be below the edge's request-headers timeout"

GATEWAY_BOUND = 10
HEADERS_DEFAULT = 10
IDLE_DEFAULT = 30
# Kept below the bounds above so ADR-1016's idle clause never fires here.
ENVOY_UPSTREAM_IDLE = 4

ABSENT = object()


def parent_with(destination: Path, bound, idle, headers=HEADERS_DEFAULT) -> Path:
    """A copy of this parent with only a minimal `gateway` and `platform` below it."""
    copy = destination / "chart"
    shutil.copytree(CHART, copy, ignore=shutil.ignore_patterns("charts"))
    chart = yaml.safe_load((copy / "Chart.yaml").read_text())
    chart["dependencies"] = [
        {"name": "gateway", "version": "0.0.0"},
        {"name": "platform", "version": "0.0.0", "condition": "platform.enabled"},
    ]
    (copy / "Chart.yaml").write_text(yaml.safe_dump(chart))

    gateway: dict = {}
    if bound is not ABSENT:
        gateway = {"server": {"limits": {"headerReadTimeoutSeconds": bound}}}
    platform: dict = {
        "gatewayListener": {
            "create": True,
            "upstreamIdleTimeoutSeconds": ENVOY_UPSTREAM_IDLE,
            "requestHeadersTimeoutSeconds": headers,
        }
    }
    if idle is not ABSENT:
        platform["gatewayListener"]["idleTimeoutSeconds"] = idle

    for name, values in (("gateway", gateway), ("platform", platform)):
        subchart = copy / "charts" / name
        subchart.mkdir(parents=True)
        (subchart / "Chart.yaml").write_text(
            yaml.safe_dump({"apiVersion": "v2", "name": name, "version": "0.0.0"})
        )
        (subchart / "values.yaml").write_text(yaml.safe_dump(values))
    return copy


def template(copy: Path, *arguments: str):
    return helm("template", "yadgar", str(copy), *GUARD_OPEN_SETS, *arguments)


# ── GREEN ────────────────────────────────────────────────────────────────────


def test_the_defaults_render(tmp_path):
    result = template(parent_with(tmp_path, GATEWAY_BOUND, IDLE_DEFAULT))
    assert result.returncode == 0, result.stderr


def test_idle_equal_to_the_headers_bound_renders(tmp_path):
    result = template(parent_with(tmp_path, GATEWAY_BOUND, HEADERS_DEFAULT))
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("idle", [ABSENT, IDLE_DEFAULT], ids=["old-platform", "new-platform"])
def test_a_gateway_with_no_bound_is_not_checked(tmp_path, idle):
    result = template(parent_with(tmp_path, ABSENT, idle))
    assert result.returncode == 0, result.stderr


def test_no_edge_listener_is_not_checked(tmp_path):
    """An adopter's own ingress owns its idle timeout; this chart cannot see it."""
    result = template(
        parent_with(tmp_path, GATEWAY_BOUND, ABSENT),
        "--set",
        "platform.gatewayListener.create=false",
    )
    assert result.returncode == 0, result.stderr


def test_platform_off_is_not_checked(tmp_path):
    result = template(
        parent_with(tmp_path, GATEWAY_BOUND, ABSENT),
        "--set",
        "platform.enabled=false",
    )
    assert result.returncode == 0, result.stderr


# ── RED ──────────────────────────────────────────────────────────────────────


def test_a_gateway_bound_with_a_platform_that_sets_no_idle_is_refused(tmp_path):
    """The edge then holds a zero-byte client for Envoy's 1 h default."""
    result = template(parent_with(tmp_path, GATEWAY_BOUND, ABSENT))
    assert result.returncode != 0, result.stdout
    assert NO_IDLE_VALUE in result.stderr, result.stderr


def test_idle_below_the_headers_bound_is_refused(tmp_path):
    result = template(parent_with(tmp_path, GATEWAY_BOUND, HEADERS_DEFAULT - 1))
    assert result.returncode != 0, result.stdout
    assert BELOW_HEADERS in result.stderr, result.stderr
    assert "idleTimeoutSeconds is 9 and" in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("setting", "refused"),
    [
        ("platform.gatewayListener.idleTimeoutSeconds=10", False),
        ("platform.gatewayListener.idleTimeoutSeconds=9", True),
        ("platform.gatewayListener.requestHeadersTimeoutSeconds=8", False),
    ],
)
def test_set_flag_integers_compare_like_values_file_numbers(tmp_path, setting, refused):
    """`--set` hands helm an int64 and a values file a float64; both compare."""
    result = template(parent_with(tmp_path, GATEWAY_BOUND, IDLE_DEFAULT), "--set", setting)
    assert (result.returncode != 0) == refused, result.stderr
    if refused:
        assert BELOW_HEADERS in result.stderr, result.stderr
