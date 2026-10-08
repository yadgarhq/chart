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
the word `pinned` cannot redden it. A real `import` of a forbidden name cannot
escape it either, renamed with `as` or not: `names_read` reads `ast.alias.name`
AND `ast.alias.asname`, so the ORIGINAL name is caught even through a rename,
and whatever the rename is called is caught too if IT happens to collide with
another forbidden name. A fixture requested by declaring a parameter of that
name (the ordinary way pytest asks for one) is caught by `ast.arg.arg`. What
NEITHER catches — a fixture requested through ANOTHER fixture's own dependency
graph, or through `@pytest.mark.usefixtures("pinned")`'s string argument — is
what `test_no_test_in_this_file_requests_a_published_pin` catches instead, by
reading pytest's own RESOLVED fixture closure rather than this file's source.

EVERY TEST HERE ALSO RUNS IN `scripts/tests/test_parent_chart.py`'s OWN suite —
there is no second copy: these are the SAME test objects, moved rather than
duplicated, and `push_validation` (`ci.yaml`) still runs every one of them on
`main` because it runs the whole `scripts/tests/` directory. Shared helpers
(`refusal`, `the_chart_that_refused`, `operators_overlay`, the `packaged`
fixture, `parent_examples`, `parent_example_failures`, and the refusal phrases
and shapes several of these tests are not the only reader of) are IMPORTED from
`test_parent_chart`, never copied — a second copy of a shared constant is a
second thing that can quietly disagree with the first.

WHAT THIS FILE DOES NOT CARRY, coordinator ruling on item 4 (narrowed from the
first draft, which kept these out of the wall entirely): the two GREEN halves
of `test_the_parent_refuses_a_renamed_iam_keys_secret` and
`test_the_parent_refuses_the_operators_toggle_and_every_one_of_its_sub_keys`
stay in `test_parent_chart.py`, under new names, because each asserts
`ADOPTER_OBJECTS` — the REFUSAL halves are refusal behaviour and belong on the
wall like every other one, and both moved here in full.

Run: `python3 -m pytest scripts/tests/test_tag_wall.py -q`.
"""

from __future__ import annotations

import ast
import collections
import sys
from pathlib import Path

import pytest

from test_parent_chart import (
    A_DISJOINT_NAME,
    THE_ADMIN_TOKEN_REFUSAL,
    THE_DELETED_OPERATORS_KEY_REFUSAL,
    THE_DEPENDENCY_REFUSAL,
    THE_OPERATOR_SUB_KEYS,
    THE_OPERATORS_REFUSAL,
    THE_OPERATORS_SHAPE_REFUSAL,
    THE_PARENT,
    THE_SUBCHART,
    THE_TEXTS_A_RAISE_LEAVES,
    THE_UNREADABLE_ENABLED_SHAPES,
    TOP_LEVEL_BLOCK,
    operators_overlay,
    packaged,
    parent_example_failures,
    parent_examples,
    refusal,
    sub_key_block,
    the_chart_that_refused,
)

# ───────────────────────── 0. the wall's own guarantee, checked statically ──────

# EVERY NAME A REAL VIOLATION WOULD READ. `EXPECTED`, unqualified, is included
# deliberately — the `ADOPTER_` prefix is not what makes a literal move with a
# module's pin; `ci.yaml`'s own header names `EXPECTED["ConfigMap"]` reading 9
# against a render of 3 for seven pin commits as the founding incident.
# `parent_at`, `being_cut` and `PUBLISHED_CHART` join it for the same reason
# `pinned`/`pre_0808`/`pulled` are here: each is a path to the parent's own
# PUBLISHED pin, which this file may never need.
FORBIDDEN_NAMES = (
    "pinned",
    "pre_0808",
    "pulled",
    "parent_at",
    "being_cut",
    "PUBLISHED_CHART",
    "EXPECTED",
    "ADOPTER_EXPECTED",
    "ADOPTER_OBJECTS",
    "CERTIFICATES_AT_R5",
    "LADDER",
)


def names_read(source: str) -> set[str]:
    """Every identifier `source` reads BY NAME, by parsing it rather than
    grepping it. PURE.

    AST, NOT A SUBSTRING SEARCH, because a substring search cannot tell a real
    reference from a word inside a string or a comment — this module's own
    docstring above says `pinned` several times. FOUR NODE KINDS, not one:

    - `ast.Name` — an ordinary reference, `pinned` used as a value.
    - `ast.Attribute.attr` — `x.pinned`, where `pinned` is read off an object
      rather than looked up directly; a plain `ast.Name` walk never sees this,
      because the attribute's NAME is a string on the node, not a child `Name`.
    - `ast.arg.arg` — a function parameter named `pinned`. This is how a test
      actually REQUESTS the `pinned` FIXTURE (`def test_x(pinned): ...`), and
      it is an `arg` node, never a `Name` — the gap this scan existed to close
      until it also read parameters.
    - `ast.alias.name` and `ast.alias.asname` — an import, `from m import
      pinned` or `from m import pinned as p`. Reading `name` catches the
      ORIGINAL identifier even through a rename; reading `asname` catches
      whatever the rename is called, if that collides with another forbidden
      name. Neither is a `Name` node either — `import` statements bind names
      without referencing them.

    A STRING LITERAL IS NONE OF THESE, which is correct and checked by the
    planted-violation test below: a fixture's own argument legitimately spells
    `"pinned-operators-null"`, and that must never redden this wall.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, ast.alias):
            found.add(node.name)
            if node.asname:
                found.add(node.asname)
    return found


def test_this_file_pulls_no_published_pin_and_asserts_no_count_literal() -> None:
    """THE WALL'S OWN FILE MUST STAY WALL-SAFE, every time it is edited.

    `tag_validation` runs this file with a plain positional path, which is the
    one invocation shape `no-test-skips` does not refuse (see the module
    docstring). That is only honest while nothing added here needs the
    registry for the parent's own pin, or asserts a literal a module's pin
    moves — this is the STATIC half of the gate that keeps it that way; see
    `test_no_test_in_this_file_requests_a_published_pin` for the other half.
    """
    offenders = names_read(Path(__file__).read_text()) & set(FORBIDDEN_NAMES)
    assert offenders == set(), (
        f"test_tag_wall.py reads {sorted(offenders)}. `tag_validation` runs this "
        f"file alone, with no marker to deselect a test that pulls the parent's "
        f"own published pin or asserts a literal a module's pin moves — move the "
        f"offending test back to test_parent_chart.py instead."
    )


def test_no_test_in_this_file_requests_a_published_pin(
    request: pytest.FixtureRequest,
) -> None:
    """THE TRANSITIVE HALF OF THE SAME GATE, read off pytest's own RESOLVED
    fixture graph rather than this file's source text.

    A test here could use some OTHER fixture — one defined anywhere, imported
    or not — that itself requires `pinned` or `pre_0808`, without either name
    appearing anywhere in THIS file at all: `names_read` above walks only this
    file's own AST, so a two-hop dependency is invisible to it. `fixturenames`
    is pytest's own closure over every fixture a collected test will actually
    receive, direct or transitive, which is exactly the fact this needs.
    """
    this_module = sys.modules[__name__]
    checked = 0
    for item in request.session.items:
        if getattr(item, "module", None) is not this_module:
            continue
        checked += 1
        offending = set(item.fixturenames) & {"pinned", "pre_0808"}
        assert not offending, (
            f"{item.nodeid} requests {sorted(offending)} through its resolved "
            f"fixture graph — not necessarily by name in this file's own "
            f"source — which pulls the parent's own published pin."
        )
    assert checked, "no collected item belongs to this module; the filter above is wrong"


def test_the_forbidden_name_scan_catches_a_planted_violation() -> None:
    """CONSTRUCTED RED for the scan above, against strings rather than this file
    (so the suite never has to carry an actual violation to prove the check
    works). One case per node kind `names_read` reads, plus the two shapes it
    must NOT read.
    """
    plain = "def test_x():\n    return pinned + ADOPTER_OBJECTS\n"
    assert names_read(plain) & set(FORBIDDEN_NAMES) == {"pinned", "ADOPTER_OBJECTS"}

    attribute = "def test_x():\n    return test_parent_chart.pinned\n"
    assert "pinned" in names_read(attribute)

    parameter = "def test_x(pinned):\n    return pinned\n"
    assert "pinned" in names_read(parameter)

    renamed_import = "from test_parent_chart import pinned as p\n"
    assert {"pinned", "p"} <= names_read(renamed_import)

    collision_only_in_the_alias = "from somewhere import other_name as LADDER\n"
    assert "LADDER" in names_read(collision_only_in_the_alias)

    quoted = 'def test_x():\n    return "pinned-operators-null"\n'
    assert names_read(quoted) & set(FORBIDDEN_NAMES) == set(), (
        "the scan read a NAME out of a string literal; it must read identifiers "
        "only, or a real test's fixture argument (which legitimately spells "
        "`pinned-operators-null` as a string) would falsely redden this wall."
    )

    # `@pytest.mark.usefixtures("pinned")` ALSO ESCAPES `names_read` — the
    # fixture name is a string argument to a decorator call, not any of the
    # four node kinds above — and that is `test_no_test_in_this_file_requests_a_published_pin`'s
    # job to catch, not this function's: it reads pytest's resolved fixture
    # graph, where a `usefixtures` request shows up in `item.fixturenames`
    # exactly like a parameter would.
    usefixtures_string = 'import pytest\n\n\n@pytest.mark.usefixtures("pinned")\ndef test_x():\n    pass\n'
    assert names_read(usefixtures_string) & set(FORBIDDEN_NAMES) == set(), (
        "`names_read` caught a `usefixtures` string; it should not be able to — "
        "that shape is the transitive test's job, not this static one's."
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

# A NAME THAT CONTAINS THE LITERAL WHOLE, the discriminating case: `iam-keys-2`
# names a Secret the Job never mints, and an implementation matching on
# `contains` or `hasPrefix` would let it through while still refusing
# `A_DISJOINT_NAME` (`test_parent_chart.py`, shared with the green half this
# scenario's other test asserts there).
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

    THE GREEN CASE IS A SEPARATE TEST (ledger 1137 split, coordinator ruling on
    item 4): `test_parent_chart.py`'s
    `test_a_renamed_iam_keys_secret_with_the_toggle_off_still_renders_the_whole_estate`
    asserts `ADOPTER_OBJECTS`, a literal this file may not touch.
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


def test_the_parent_refuses_the_operators_toggle_and_every_one_of_its_sub_keys(
    tmp_path: Path,
) -> None:
    """ADR-0787: `operators.create` is a `platform` path, and never the parent's.

    SEVEN RENDERS, NOT ONE, and the six sub-key renders are the part a top-level
    refusal would miss. Each operator dependency in `platform` is declared
    `condition: operators.<op>.create,operators.create`, and helm evaluates the
    FIRST valid path and stops — so `operators.certManager.create: true` installs
    cert-manager while `operators.create` is false. Measured in `platform` at step
    3 of the operators-toggle plan: `--set operators.create=false --set
    operators.certManager.create=true` rendered 50 objects with 6 CRDs. A parent
    refusal reading the top-level key alone is FALSE in that shape, and
    `test_a_refusal_that_read_the_top_level_key_alone_would_let_a_sub_key_through`
    (`test_parent_chart.py`) constructs that narrowing and shows it passing the
    sub-key.

    MEASURED ON `main` BEFORE THIS CLAUSE EXISTED, helm 4.3.0:
    `--set platform.operators.certManager.create=true` rendered exit 0 and 32
    objects — `platform.operators` is a map whose own `create` key is absent, so
    the `$creating` guard never opened and no refusal ran.

    THE GREEN CASE IS A SEPARATE TEST (ledger 1137 split, coordinator ruling on
    item 4): `test_parent_chart.py`'s
    `test_every_operator_key_stated_false_still_renders_the_whole_estate`
    asserts `ADOPTER_OBJECTS`, a literal this file may not touch.
    """
    message = refusal(tmp_path, "operators-create", operators_overlay(TOP_LEVEL_BLOCK))
    assert THE_OPERATORS_REFUSAL in message, message
    assert "platform.operators.create" in message, message
    assert THE_ADMIN_TOKEN_REFUSAL not in message, message
    assert THE_DEPENDENCY_REFUSAL not in message, message

    for operator in THE_OPERATOR_SUB_KEYS:
        message = refusal(
            tmp_path, f"operators-{operator}", operators_overlay(sub_key_block(operator))
        )
        assert THE_OPERATORS_REFUSAL in message, message
        assert f"platform.operators.{operator}.create" in message, message
        # The sub-key opens no `platform.<name>.create`, so the guarded refusals
        # stay shut and the assertions above read this clause's message alone.
        assert THE_ADMIN_TOKEN_REFUSAL not in message, message
        assert THE_DEPENDENCY_REFUSAL not in message, message


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
