"""The render-refusal wall `tag_validation` runs, and nothing in it may need a mark.

LEDGER 1137, RULED A DEDICATED FILE RATHER THAN A MARKER EXPRESSION. The first
draft of this wall ran `scripts/tests/ -q -m "not published and not pin_count"`,
deselecting the tests that pull the parent's own published pin (a version being
cut is not yet pullable) and the tests that assert a literal a module's pin
moves (a bot pin never updates them). `yadgarhq/actions`' `no-test-skips` hook
(ledger 837) refuses that outright, for every repository, with no exemption: a
`pytest` invocation narrowed by `-m` is exactly "a test would stop running, and
nothing would say so" — the defect the hook exists to catch, not a legitimate
use the scan happens to also catch. Reaching for a workaround the scanner cannot
see (a conftest collection hook, `addopts`, a node-id list) would be the "test
bending" ledger 837's own specification forbids, not a way around it.

A POSITIONAL FILE ARGUMENT IS WHAT THE HOOK ITSELF DOCUMENTS AS SAFE: "no scan
can tell a directory that IS the suite from one that is a slice of it." So
`tag_validation` runs `pytest scripts/tests/test_tag_wall.py -q` — a whole file,
not a slice of one — and what makes that honest is this file's own content:
nothing in it may pull the parent's own published pin (`pinned`, `pre_0808`,
`pulled`) or assert a literal that moves with a module's pin (`EXPECTED`,
`ADOPTER_EXPECTED`, `ADOPTER_OBJECTS`, `CERTIFICATES_AT_R5`, `LADDER`).
`test_this_file_pulls_no_published_pin_and_asserts_no_count_literal` checks that
by reading names, not substrings, so a fixture whose VALUE happens to contain
the word `pinned` cannot redden it and a real `import` of one cannot escape it.

EVERY TEST HERE ALSO RUNS IN `scripts/tests/test_parent_chart.py`'s OWN suite —
there is no second copy: these are the SAME test objects, moved rather than
duplicated, and `push_validation` (`ci.yaml`) still runs every one of them on
`main` because it runs the whole `scripts/tests/` directory. Shared helpers
(`refusal`, `the_chart_that_refused`, `operators_overlay`, the `packaged`
fixture, `parent_examples`, `parent_example_failures`, and the refusal phrases
and shapes several of these tests are not the only reader of) are IMPORTED from
`test_parent_chart`, never copied — a second copy of a shared constant is a
second thing that can quietly disagree with the first.

WHAT THIS FILE DOES NOT CARRY. Two `refusal()`-based tests stay in
`test_parent_chart.py`: `test_the_parent_refuses_a_renamed_iam_keys_secret` and
`test_the_parent_refuses_the_operators_toggle_and_every_one_of_its_sub_keys`
both also assert `ADOPTER_OBJECTS`, which this file may not touch.

Run: `python3 -m pytest scripts/tests/test_tag_wall.py -q`.
"""

from __future__ import annotations

import ast
import collections
from pathlib import Path

from test_parent_chart import (
    THE_DELETED_OPERATORS_KEY_REFUSAL,
    THE_DEPENDENCY_REFUSAL,
    THE_OPERATORS_SHAPE_REFUSAL,
    THE_PARENT,
    THE_SUBCHART,
    THE_TEXTS_A_RAISE_LEAVES,
    THE_UNREADABLE_ENABLED_SHAPES,
    operators_overlay,
    packaged,
    parent_example_failures,
    parent_examples,
    refusal,
    the_chart_that_refused,
)

# ───────────────────────── 0. the wall's own guarantee, checked statically ──────

# EVERY NAME A REAL VIOLATION WOULD READ. `EXPECTED`, unqualified, is included
# deliberately — the `ADOPTER_` prefix is not what makes a literal move with a
# module's pin; `ci.yaml`'s own header names `EXPECTED["ConfigMap"]` reading 9
# against a render of 3 for seven pin commits as the founding incident.
FORBIDDEN_NAMES = (
    "pinned",
    "pre_0808",
    "pulled",
    "EXPECTED",
    "ADOPTER_EXPECTED",
    "ADOPTER_OBJECTS",
    "CERTIFICATES_AT_R5",
    "LADDER",
)


def names_read(source: str) -> set[str]:
    """Every identifier `source` reads as a NAME, by parsing it rather than
    grepping it. PURE.

    AST, NOT A SUBSTRING SEARCH, because a substring search cannot tell a real
    reference from a word inside a string or a comment — this module's own
    docstring above says `pinned` four times. `ast.Name` nodes are exactly the
    identifiers Python would look up at runtime: an attribute (`x.pinned`) is an
    `Attribute` node and does not match, which is correct — nothing here reads
    an attribute by one of these names.
    """
    return {node.id for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Name)}


def test_this_file_pulls_no_published_pin_and_asserts_no_count_literal() -> None:
    """THE WALL'S OWN FILE MUST STAY WALL-SAFE, every time it is edited.

    `tag_validation` runs this file with a plain positional path, which is the
    one invocation shape `no-test-skips` does not refuse (see the module
    docstring). That is only honest while nothing added here needs the
    registry for the parent's own pin, or asserts a literal a module's pin
    moves — this is the gate that keeps it that way.
    """
    offenders = names_read(Path(__file__).read_text()) & set(FORBIDDEN_NAMES)
    assert offenders == set(), (
        f"test_tag_wall.py reads {sorted(offenders)}. `tag_validation` runs this "
        f"file alone, with no marker to deselect a test that pulls the parent's "
        f"own published pin or asserts a literal a module's pin moves — move the "
        f"offending test back to test_parent_chart.py instead."
    )


def test_the_forbidden_name_scan_catches_a_planted_violation() -> None:
    """CONSTRUCTED RED for the scan above, against a string rather than this file
    (so the suite never has to carry an actual violation to prove the check
    works). A name used as a plain reference is caught; the same word spelled
    inside a string literal — the shape a real test's fixture argument would
    take — is not a Name node and must NOT be.
    """
    planted = "def test_x():\n    return pinned + ADOPTER_OBJECTS\n"
    assert names_read(planted) & set(FORBIDDEN_NAMES) == {"pinned", "ADOPTER_OBJECTS"}
    quoted = 'def test_x():\n    return "pinned-operators-null"\n'
    assert names_read(quoted) & set(FORBIDDEN_NAMES) == set(), (
        "the scan read a NAME out of a string literal; it must read identifiers "
        "only, or a real test's fixture argument (which legitimately spells "
        "`pinned-operators-null` as a string) would falsely redden this wall."
    )


# ── the parent's own refusals, moved from `test_parent_chart.py` (ledger 1137) ──


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


def test_the_parent_names_a_platform_enabled_it_cannot_read(tmp_path: Path) -> None:
    """Six unreadable `platform.enabled` values, six refusals that say what is true.

    THE TYPE NAME IS ASSERTED PER ROW, and `invalid` is reported as `null` the way
    every other shape refusal in this file reports it — "is a invalid" names
    nothing an adopter wrote.

    THE OLD MESSAGE MUST BE ABSENT, not merely the new one present. Both arms are
    reachable from the same values file shape, and an implementation that emitted
    both would satisfy a positive-only assertion while still telling the adopter
    the render contains none of the objects it is about to contain.
    """
    for name, scalar, kind in THE_UNREADABLE_ENABLED_SHAPES:
        message = refusal(
            tmp_path,
            name,
            f"platform:\n  enabled: {scalar}\n  valkey:\n    create: true\n"
            "gateway:\n  adminBootstrap:\n    tokenSecret: admin-bootstrap-token\n",
        )
        assert f"platform.enabled is a {kind} rather than true or false" in message, (
            f"`{name}` refused without naming what the adopter wrote: {message}"
        )
        assert "platform.valkey.create" in message, (
            f"`{name}` refused without naming the toggle that asked: {message}"
        )
        assert THE_DEPENDENCY_REFUSAL not in message, (
            f"`{name}` also emitted the message for a RESOLVED false condition, "
            f"which says this render contains none of the objects it is in fact "
            f"about to contain: {message}"
        )
        for raise_text in THE_TEXTS_A_RAISE_LEAVES:
            assert raise_text not in message, (
                f"`{name}` RAISED instead of refusing: {message}"
            )


def test_an_unreadable_platform_enabled_is_refused_with_every_create_false(tmp_path: Path) -> None:
    """The shape refusal does not wait for a `create` toggle to open the guard.

    `platform.enabled: null` with every `create` false used to render exit 0 WITH
    `platform` objects and no refusal: helm leaves the dependency enabled, and the
    refusal sat inside the `create` guard, which nothing opened. Measured on
    751e64b and on this branch before the fix: 4 objects from `platform`, exit 0.
    """
    for name, scalar, kind in THE_UNREADABLE_ENABLED_SHAPES:
        message = refusal(
            tmp_path,
            f"{name}-nothing-created",
            f"platform:\n  enabled: {scalar}\n",
        )
        assert f"platform.enabled is a {kind} rather than true or false" in message, (
            f"`{name}` with every create false refused without naming the key: {message}"
        )
        for raise_text in THE_TEXTS_A_RAISE_LEAVES:
            assert raise_text not in message, f"`{name}` RAISED instead of refusing: {message}"


# THE PHRASE THIS CLAUSE ALONE WRITES, and the type-naming helper and table it
# builds — moved together since nothing outside this file reads either.
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

# WHAT THE WALK BELOW MUST EXAMINE, COUNTED AND SPLIT BY REFUSER. A row deleted
# from the tuple, or a row that quietly changed which chart answered it, reddens
# here rather than leaving the loop exercising one fewer shape and reporting a pass.
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
        observed = the_chart_that_refused(name, message)
        assert observed == chart, (
            f"`{name}` is tabled as refused by `{chart}` and `{observed}` refused "
            f"it. Which chart answers which shape is the structural claim this "
            f"table makes, and it has moved.\n{message}"
        )
        refused_by[observed] += 1
    assert dict(refused_by) == THE_SHAPES_AN_ADOPTER_CAN_WRITE, (
        f"this walk examined {dict(refused_by)} and the table says "
        f"{THE_SHAPES_AN_ADOPTER_CAN_WRITE}"
    )


# EACH ROW: (name, the YAML under `platform:`, the chart that refuses, the phrase).
# Moved together with the test below — nothing else in the suite reads either.
THE_REGISTER_KEY_SHAPES = (
    ("operators-create-is-null", "operators:\n    create:\n", THE_SUBCHART,
     "operators.create has been deleted"),
    ("operators-create-is-a-quoted-true", 'operators:\n    create: "true"\n', THE_PARENT,
     "platform.operators.create is a string rather than a boolean"),
    ("operators-create-is-the-yaml-yes-string", 'operators:\n    create: "yes"\n', THE_PARENT,
     "platform.operators.create is a string rather than a boolean"),
    ("operators-create-is-the-yaml-no-string", 'operators:\n    create: "no"\n', THE_PARENT,
     "platform.operators.create is a string rather than a boolean"),
    ("operators-create-is-an-empty-string", 'operators:\n    create: ""\n', THE_PARENT,
     "platform.operators.create is a string rather than a boolean"),
    ("operators-create-is-zero", "operators:\n    create: 0\n", THE_PARENT,
     "platform.operators.create is a float64 rather than a boolean"),
    ("operators-create-is-one", "operators:\n    create: 1\n", THE_PARENT,
     "platform.operators.create is a float64 rather than a boolean"),
    ("operators-create-is-an-empty-list", "operators:\n    create: []\n", THE_PARENT,
     "platform.operators.create is a slice rather than a boolean"),
    ("operators-create-is-an-empty-map", "operators:\n    create: {}\n", THE_PARENT,
     "platform.operators.create is a map rather than a boolean"),
    ("nats-create-is-null", "nats:\n    create:\n", THE_PARENT,
     "platform.nats.create is a null rather than a boolean"),
    ("nats-create-is-the-yaml-yes-string", 'nats:\n    create: "yes"\n', THE_PARENT,
     "platform.nats.create is a string rather than a boolean"),
    ("nats-create-is-an-empty-map", "nats:\n    create: {}\n", THE_PARENT,
     "platform.nats.create is a map rather than a boolean"),
    ("nats-block-is-null", "nats:\n", THE_SUBCHART,
     "nats.create has been deleted"),
)

# THE SAME SPLIT, COUNTED.
THE_REGISTER_SHAPES_AN_ADOPTER_CAN_WRITE = {THE_PARENT: 11, THE_SUBCHART: 2}


def test_the_register_key_shapes_are_refused_and_the_table_says_by_whom(
    tmp_path: Path,
) -> None:
    """Thirteen shapes of the key helm's `condition:` reads, and who answers each.

    THE PHRASE AND THE REFUSER ARE ASSERTED SEPARATELY, because they fail for
    different reasons. A wrong phrase is a reworded or wrongly-typed refusal; a
    wrong refuser is the division of labour between the two charts moving, which
    is the structural claim this table exists to hold and the one a pin can break
    without anybody editing either file.

    ASSERTED ON THE ABSENCE OF A RAISE TOO. A refusal and a raise both exit 1, and
    `platform.operators.create: 1` RAISED here at one point in this file's history
    — `incompatible types for comparison: float64 and bool` — which is exactly the
    outcome ADR-0794 forbids.
    """
    refused_by: collections.Counter = collections.Counter()
    for name, body, chart, phrase in THE_REGISTER_KEY_SHAPES:
        message = refusal(
            tmp_path,
            f"register-{name}",
            f"platform:\n  enabled: true\n  {body}"
            "gateway:\n  adminBootstrap:\n    tokenSecret: admin-bootstrap-token\n",
        )
        assert phrase in message, (
            f"`{name}` refused without the phrase `{chart}` alone writes: {message}"
        )
        for raise_text in THE_TEXTS_A_RAISE_LEAVES:
            assert raise_text not in message, (
                f"`{name}` RAISED instead of refusing: {message}"
            )
        observed = the_chart_that_refused(name, message)
        assert observed == chart, (
            f"`{name}` is tabled as refused by `{chart}` and `{observed}` refused "
            f"it.\n{message}"
        )
        refused_by[observed] += 1
    assert dict(refused_by) == THE_REGISTER_SHAPES_AN_ADOPTER_CAN_WRITE, (
        f"this walk examined {dict(refused_by)} and the table says "
        f"{THE_REGISTER_SHAPES_AN_ADOPTER_CAN_WRITE}"
    )


def test_the_pinned_subchart_is_what_makes_that_arm_unreachable(tmp_path: Path) -> None:
    """THE OTHER HALF, so the paragraph in `test_parent_chart.py`'s own section is
    measured rather than asserted.

    The SAME overlay against the chart as it ships is refused by `platform`, not
    by the arm above. Without this, the test above would read as "the parent
    refuses a null `platform.operators`" full stop, which is the claim this file
    carried before 2026-09-26 and which a pinned `platform` had already made
    false. THE STRING `"pinned-operators-null"` BELOW IS A FIXTURE NAME, NEVER THE
    `pinned` FIXTURE — this file's own wall (above) tells the two apart by
    parsing, not by grepping, which is exactly why a name like this one is safe
    to write here.
    """
    message = refusal(
        tmp_path,
        "pinned-operators-null",
        "platform:\n  enabled: true\n  operators: null\n"
        "gateway:\n  adminBootstrap:\n    tokenSecret: admin-bootstrap-token\n",
    )
    assert THE_DELETED_OPERATORS_KEY_REFUSAL in message, message
    assert "platform.operators is a null rather than a mapping" not in message, (
        "the parent's `invalid` arm answered with `platform` pinned, so it is not "
        f"fixture-only after all and the paragraph in `test_parent_chart.py` needs "
        f"rewriting: {message}"
    )
    assert the_chart_that_refused("pinned-operators-null", message) == THE_SUBCHART


# THE FOUR NON-BOOLEAN `create` SPELLINGS, moved together with the test below.
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


# ── the examples wall, new for the tag job (ledger 1137) ────────────────────


def test_every_parent_example_renders_from_the_packaged_chart(packaged: Path, tmp_path: Path) -> None:
    """THE TAG JOB'S OWN COPY OF `test_every_parent_example_passes_every_parent_gate`,
    against HEAD rather than the registry.

    That test (`test_parent_chart.py`) takes `pinned`, which pulls the parent's own
    PUBLISHED pin — not yet pullable while that very tag is being cut, so it stays
    out of this file. `packaged` resolves the NINE MODULE charts from the registry
    but never the parent's own version, so this needs no published pin and still
    walls what the other one would have: a contract pin whose fixture pull request
    missed `example/kind/application.yaml` renders a different object set here,
    from HEAD's own defaults, before `vN` ever publishes.
    """
    assert parent_example_failures(parent_examples(), packaged, tmp_path) == []
