"""yaadgaar #218: THE EDGE'S REQUEST-HEADERS BOUND IS NOT LOOSER THAN THE GATEWAY'S.

The gateway closes a connection that sends no complete request head within
`gateway.server.limits.headerReadTimeoutSeconds` (ADR-1006). Envoy forwards no
request until its head is complete, so through the edge that bound never sees a
client that stalls mid-head. `platform` bounds the edge's own wait, from
`platform.gatewayListener.requestHeadersTimeoutSeconds`, on a ClientTrafficPolicy
on the edge Gateway. If the edge's value is above the gateway's, a stalled
client holds an edge connection longer than the gateway itself would allow.
Neither chart sees the other's value, so `_validate.tpl` holds the check.

EQUAL IS ALLOWED, unlike ADR-1016's idle check. There is no race to avoid here:
the two bounds are on different connections, and equal means the edge holds a
stalled client exactly as long as the gateway would.

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
LOOSER = "must not be above the gateway's header-read timeout"
NO_EDGE_VALUE = (
    "the pinned platform chart sets no "
    "platform.gatewayListener.requestHeadersTimeoutSeconds"
)

GATEWAY_BOUND = 10
EDGE_DEFAULT = 10
# Kept below the bounds above so ADR-1016's idle clause never fires here.
ENVOY_IDLE = 4

ABSENT = object()


def parent_with(destination: Path, bound, headers) -> Path:
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
        "gatewayListener": {"create": True, "upstreamIdleTimeoutSeconds": ENVOY_IDLE}
    }
    if headers is not ABSENT:
        platform["gatewayListener"]["requestHeadersTimeoutSeconds"] = headers

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


def test_the_two_defaults_render(tmp_path):
    result = template(parent_with(tmp_path, GATEWAY_BOUND, EDGE_DEFAULT))
    assert result.returncode == 0, result.stderr


def test_an_edge_tighter_than_the_gateway_renders(tmp_path):
    result = template(parent_with(tmp_path, GATEWAY_BOUND, 5))
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("headers", [ABSENT, EDGE_DEFAULT], ids=["old-platform", "new-platform"])
def test_a_gateway_with_no_bound_is_not_checked(tmp_path, headers):
    result = template(parent_with(tmp_path, ABSENT, headers))
    assert result.returncode == 0, result.stderr


def test_no_edge_listener_is_not_checked(tmp_path):
    """An adopter's own ingress owns its headers timeout; this chart cannot see it."""
    result = template(
        parent_with(tmp_path, GATEWAY_BOUND, ABSENT),
        "--set",
        "platform.gatewayListener.create=false",
    )
    assert result.returncode == 0, result.stderr


def test_platform_off_is_not_checked(tmp_path):
    result = template(
        parent_with(tmp_path, GATEWAY_BOUND, GATEWAY_BOUND + 5),
        "--set",
        "platform.enabled=false",
    )
    assert result.returncode == 0, result.stderr


# ── RED ──────────────────────────────────────────────────────────────────────


def test_an_edge_looser_than_the_gateway_is_refused(tmp_path):
    result = template(parent_with(tmp_path, GATEWAY_BOUND, GATEWAY_BOUND + 1))
    assert result.returncode != 0, result.stdout
    assert LOOSER in result.stderr, result.stderr
    assert "requestHeadersTimeoutSeconds is 11 and" in result.stderr, result.stderr


def test_a_gateway_lowered_under_the_edge_default_is_refused(tmp_path):
    result = template(parent_with(tmp_path, 5, EDGE_DEFAULT))
    assert result.returncode != 0, result.stdout
    assert LOOSER in result.stderr, result.stderr


def test_a_gateway_bound_with_an_old_platform_is_refused(tmp_path):
    """The edge then has no headers timeout at all, which is the defect."""
    result = template(parent_with(tmp_path, GATEWAY_BOUND, ABSENT))
    assert result.returncode != 0, result.stdout
    assert NO_EDGE_VALUE in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("setting", "refused"),
    [
        ("platform.gatewayListener.requestHeadersTimeoutSeconds=10", False),
        ("platform.gatewayListener.requestHeadersTimeoutSeconds=11", True),
        ("gateway.server.limits.headerReadTimeoutSeconds=9", True),
    ],
)
def test_set_flag_integers_compare_like_values_file_numbers(tmp_path, setting, refused):
    """`--set` hands helm an int64 and a values file a float64; both compare."""
    result = template(parent_with(tmp_path, GATEWAY_BOUND, EDGE_DEFAULT), "--set", setting)
    assert (result.returncode != 0) == refused, result.stderr
    if refused:
        assert LOOSER in result.stderr, result.stderr
