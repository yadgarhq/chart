"""ADR-1016: ENVOY'S UPSTREAM IDLE TIMEOUT STAYS BELOW THE GATEWAY'S HEADER-READ TIMEOUT.

The gateway edge closes a kept-alive connection that sends no request head
within `gateway.server.limits.headerReadTimeoutSeconds`. `platform` sets how
long Envoy keeps an idle upstream connection, from
`platform.gatewayListener.upstreamIdleTimeoutSeconds`. If Envoy's value is not
strictly below the gateway's, Envoy can reuse a connection as the gateway closes
it, and the client gets a 503 UC. Neither chart sees the other's value, so
`_validate.tpl` holds the check.

WHY FAKE SUBCHARTS AND NOT THE PINS. The clause reads `.Subcharts.gateway` and
`.Subcharts.platform`, so it needs both subcharts present. The pins move on
their own: `parent_bump.py` writes each module release into `main` with no pull
request CI. A test built on what the pinned tarballs declare today would break
`main` the day a pin moves. So each case here builds a copy of this parent whose
only two dependencies are a minimal `gateway` and a minimal `platform`, each a
`Chart.yaml` plus the `values.yaml` keys the clause reads. That tests the clause
alone, at every combination, whatever is pinned. The suite's real-pin renders
(`test_parent_chart.py`) still run the clause over the pinned charts' defaults.

Run: python3 -m pytest scripts/tests/ -q
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from test_parent_chart import CHART, GUARD_OPEN_SETS, helm

# The refusal sentences, by the words a reader searches for. LITERALS.
NOT_BELOW = "must be strictly below the gateway's header-read timeout"
NO_ENVOY_VALUE = "the pinned platform chart sets no platform.gatewayListener.upstreamIdleTimeoutSeconds"

GATEWAY_BOUND = 10
ENVOY_DEFAULT = 8

# What a subchart writes for a key it does not declare at all: the key is left out.
ABSENT = object()


def parent_with(destination: Path, bound, idle) -> Path:
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
    # `requestHeadersTimeoutSeconds` at 1 s is below every bound here, so the
    # yaadgaar #218 clause beside this one never fires in this file. An
    # `idleTimeoutSeconds` at or above it keeps the ADR-1022 clause quiet too.
    platform: dict = {
        "gatewayListener": {
            "create": True,
            "requestHeadersTimeoutSeconds": 1,
            "idleTimeoutSeconds": 30,
        }
    }
    if idle is not ABSENT:
        platform["gatewayListener"]["upstreamIdleTimeoutSeconds"] = idle

    for name, values in (("gateway", gateway), ("platform", platform)):
        subchart = copy / "charts" / name
        subchart.mkdir(parents=True)
        (subchart / "Chart.yaml").write_text(
            yaml.safe_dump({"apiVersion": "v2", "name": name, "version": "0.0.0"})
        )
        (subchart / "values.yaml").write_text(yaml.safe_dump(values))
    return copy


def template(copy: Path, *arguments: str):
    # GUARD_OPEN_SETS names the `iam-keys` Secret the parent's defaults mint, so the
    # admin-token and `iam-keys` clauses, which the defaults open, pass. The only
    # refusal left to fire is the one under test.
    return helm("template", "yadgar", str(copy), *GUARD_OPEN_SETS, *arguments)


# ── GREEN ────────────────────────────────────────────────────────────────────


def test_the_two_defaults_render(tmp_path):
    result = template(parent_with(tmp_path, GATEWAY_BOUND, ENVOY_DEFAULT))
    assert result.returncode == 0, result.stderr


def test_one_second_below_renders(tmp_path):
    result = template(parent_with(tmp_path, GATEWAY_BOUND, GATEWAY_BOUND - 1))
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "idle", [ABSENT, ENVOY_DEFAULT], ids=["old-platform", "new-platform"]
)
def test_a_gateway_with_no_bound_is_not_checked(tmp_path, idle):
    """A gateway older than ADR-1016 closes nothing early, so no order exists to keep."""
    result = template(parent_with(tmp_path, ABSENT, idle))
    assert result.returncode == 0, result.stderr


def test_no_edge_listener_is_not_checked(tmp_path):
    """An adopter's own ingress owns its idle timeout; this chart cannot see it.

    BY `--set`, not by the fake subchart's own default: this parent's
    `values.yaml` sets `platform.gatewayListener.create: true`, and a parent
    value wins over a subchart default.
    """
    result = template(
        parent_with(tmp_path, GATEWAY_BOUND, GATEWAY_BOUND),
        "--set",
        "platform.gatewayListener.create=false",
    )
    assert result.returncode == 0, result.stderr


def test_platform_off_is_not_checked(tmp_path):
    result = template(
        parent_with(tmp_path, GATEWAY_BOUND, GATEWAY_BOUND), "--set", "platform.enabled=false"
    )
    assert result.returncode == 0, result.stderr


# ── RED ──────────────────────────────────────────────────────────────────────


def test_equal_values_are_refused(tmp_path):
    """Equal is refused: both sides would then close at the same instant."""
    result = template(parent_with(tmp_path, GATEWAY_BOUND, GATEWAY_BOUND))
    assert result.returncode != 0, result.stdout
    assert NOT_BELOW in result.stderr, result.stderr
    assert "upstreamIdleTimeoutSeconds is 10 and" in result.stderr, result.stderr


def test_envoy_above_the_bound_is_refused(tmp_path):
    result = template(parent_with(tmp_path, GATEWAY_BOUND, GATEWAY_BOUND + 2))
    assert result.returncode != 0, result.stdout
    assert NOT_BELOW in result.stderr, result.stderr


def test_a_gateway_lowered_under_the_envoy_default_is_refused(tmp_path):
    result = template(parent_with(tmp_path, 5, ENVOY_DEFAULT))
    assert result.returncode != 0, result.stdout
    assert NOT_BELOW in result.stderr, result.stderr


def test_a_gateway_bound_with_an_old_platform_is_refused(tmp_path):
    """The pin of one change without the other, which ADR-1016 forbids."""
    result = template(parent_with(tmp_path, GATEWAY_BOUND, ABSENT))
    assert result.returncode != 0, result.stdout
    assert NO_ENVOY_VALUE in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("setting", "refused"),
    [("platform.gatewayListener.upstreamIdleTimeoutSeconds=9", False),
     ("platform.gatewayListener.upstreamIdleTimeoutSeconds=10", True),
     ("gateway.server.limits.headerReadTimeoutSeconds=8", True)],
)
def test_set_flag_integers_compare_like_values_file_numbers(tmp_path, setting, refused):
    """`--set` hands helm an int64 and a values file a float64; both compare."""
    result = template(parent_with(tmp_path, GATEWAY_BOUND, ENVOY_DEFAULT), "--set", setting)
    assert (result.returncode != 0) == refused, result.stderr
    if refused:
        assert NOT_BELOW in result.stderr, result.stderr
