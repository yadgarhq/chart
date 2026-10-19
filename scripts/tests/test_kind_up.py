"""`bootstrap/kind-up.sh`, tested offline against fakes (ADR-0820 decisions 3 and 4).

The script turns a clean Debian/Ubuntu host into a kind cluster running the whole
estate under Argo CD, then creates the first administrator. It is tested here
WITHOUT a cluster: every program that reaches outside the host — `kubectl`,
`helm`, `kind`, `curl`, `podman`, `sysctl`, `apt-get`, `pipx`, `yaadgaar`, even
`id` — is `kind_up_fake.py`, and `HOME` and `KUBECONFIG` point into a scratch
directory. The host running this suite may hold a production kubeconfig; nothing
here can read it.

WHAT IS ASSERTED, and why each one:

1. EVERY STEP IS IDEMPOTENT. A second run of the whole script against the state
   the first left does no download, creates no cluster and creates no user.
2. A CHECKSUM MISMATCH INSTALLS NOTHING. The pinned sha256 in
   `bootstrap/tools.lock` is the only thing standing between a hijacked download
   and root on the host.
3. NO SECRET REACHES STDOUT, STDERR, THE LOG OR ANY PROGRAM'S ARGV — the bootstrap
   token raw and base64, the enrolment token, the client password. Each absence is
   paired with a POSITIVE CONTROL showing the secret did reach its consumer on
   stdin, or the absence would prove only that the test never produced one.
4. A FAILED ARGO OPERATION EXITS NON-ZERO AND NAMES WHAT FAILED. The acceptance
   criterion is first-sync success, so the script never forces a sync.
5. THE SCRIPT IS SHELLCHECK-CLEAN. `shellcheck` absent is a failure, never a skip
   (ADR-0650); the `pytest-scripts` hook installs it as `shellcheck-py`.

Run: python3 -m pytest scripts/tests/test_kind_up.py -q
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "bootstrap" / "kind-up.sh"
LOCK = REPO / "bootstrap" / "tools.lock"
FAKE = Path(__file__).with_name("kind_up_fake.py")

# Every name the script may run that touches anything outside this process.
FAKED = (
    "kubectl",
    "helm",
    "kind",
    "curl",
    "podman",
    "docker",
    "sysctl",
    "id",
    "apt-get",
    "pipx",
    "yaadgaar",
    # ROOT'S HOME COMES FROM `getent passwd 0`, found on PATH — the one place the
    # script learns it, with no environment override. Real `sudo` applies
    # `secure_path`, so a `sudo -E` caller cannot steer PATH to a getent of their
    # own; here the fake prints a passwd line naming the rig's root home.
    "getent",
)
PINNED = {"kind": "v0.32.0", "kubectl": "v1.36.1", "helm": "v4.3.0"}


def client_version() -> str:
    """The one `yaadgaar` row of tools.lock: every printed and installed version reads it."""
    rows = [line.split() for line in LOCK.read_text().splitlines()
            if line and not line.startswith("#") and line.split()[0] == "yaadgaar"]
    return rows[0][1]

# THE REAL PROGRAMS THE SCRIPT MAY USE, each linked into a directory of its own
# that is the whole of PATH after the fakes. The host's PATH is never inherited:
# a developer's machine may carry a real `yaadgaar` or `kubectl` beside `jq`, and
# a test that removes a fake must then find nothing rather than the real one.
HOST_TOOLS = (
    "bash", "python3", "jq", "awk", "sed", "grep", "base64", "sha256sum", "tar", "install",
    "mktemp", "find", "date", "tee", "head", "tail", "cat", "mv", "rm", "mkdir", "chmod",
    "touch", "dirname", "env", "sleep", "tr", "uname", "cp", "ls", "wc", "stat", "cut", "cmp",
)


def link_host_tools(into: Path) -> None:
    into.mkdir()
    for tool in HOST_TOOLS:
        found = shutil.which(tool)
        assert found, f"{tool} is not installed"
        (into / tool).symlink_to(Path(found).resolve())
GATEWAY = "https://gateway.yadgar.internal:18443"


def version_rules() -> list[dict]:
    """The pinned tools answer their version queries with the pinned version."""
    return [
        {"cmd": "kind", "match": ["version"], "stdout": "kind v0.32.0 go1.26.3 linux/amd64\n"},
        {
            "cmd": "kubectl",
            "match": ["version", "--client"],
            "stdout": json.dumps({"clientVersion": {"gitVersion": "v1.36.1"}}),
        },
        {"cmd": "helm", "match": ["version"], "stdout": "v4.3.0"},
    ]


def sysctl_rules() -> list[dict]:
    return [
        {"cmd": "sysctl", "match": ["-n", "fs.inotify.max_user_watches"], "stdout": "524288\n"},
        {"cmd": "sysctl", "match": ["-n", "fs.inotify.max_user_instances"], "stdout": "512\n"},
        {"cmd": "sysctl", "match": ["-n", "net.ipv4.ip_forward"], "stdout": "1\n"},
    ]


def app_json(
    name: str,
    phase: str | None,
    sync: str = "Synced",
    health: str = "Healthy",
    revision: str = "0.3.8",
    target: str = "0.3.8",
    message: str = "",
    resources: list[dict] | None = None,
    conditions: list[dict] | None = None,
) -> str:
    status: dict = {"sync": {"status": sync}, "health": {"status": health}}
    if phase is not None:
        status["operationState"] = {
            "phase": phase,
            "message": message,
            "operation": {"sync": {"revision": revision}},
            "syncResult": {"revision": revision, "resources": resources or []},
        }
    if conditions:
        status["conditions"] = conditions
    return json.dumps(
        {
            "metadata": {"name": name},
            "spec": {"source": {"targetRevision": target}},
            "status": status,
        }
    )


@dataclass
class Rig:
    """A scratch host: fakes first on PATH, and every path the script writes."""

    root: Path
    rules: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        for d in ("fake", "fakebin", "bin", "state", "home", "etc", "roothome"):
            (self.root / d).mkdir()
        # ROOT'S OWN yaadgaar, where root's pipx puts it. The one in fakebin, on
        # PATH, is a decoy the root-side client must never run.
        (self.root / "roothome" / ".local" / "bin").mkdir(parents=True)
        (self.root / "roothome" / ".local" / "bin" / "yaadgaar").symlink_to(FAKE)
        for name in FAKED:
            (self.root / "fakebin" / name).symlink_to(FAKE)
        link_host_tools(self.root / "hostbin")
        # The pinned tools live in YADGAR_BIN_DIR, where the script installs them.
        for name in PINNED:
            (self.root / "bin" / name).symlink_to(FAKE)
        (self.root / "etc" / "hosts").write_text("127.0.0.1 localhost\n")
        self.rules = version_rules() + sysctl_rules() + [
            {"cmd": "id", "match": ["-u"], "stdout": "0\n"},
            {"cmd": "getent", "match": ["passwd", "0"], "stdout": f"root:x:0:0:root:{self.root / 'roothome'}:/bin/bash\n"},
        ]

    @property
    def state(self) -> Path:
        return self.root / "state"

    @property
    def log(self) -> Path:
        return self.state / "kind-up.log"

    @property
    def enrolment_file(self) -> Path:
        return self.root / "home" / "yadgar-enrolment.token"

    @property
    def root_home(self) -> Path:
        return self.root / "roothome"

    @property
    def client_config(self) -> Path:
        return self.root / "admin-client" / "config.json"

    def env(self, **extra: str) -> dict[str, str]:
        env = {
            "PATH": f"{self.root / 'fakebin'}:{self.root / 'hostbin'}",
            "HOME": str(self.root / "home"),
            "KUBECONFIG": str(self.root / "home" / "never-read"),
            "FAKE_DIR": str(self.root / "fake"),
            "YADGAR_STATE_DIR": str(self.state),
            "YADGAR_BIN_DIR": str(self.root / "bin"),
            "YADGAR_SYSCTL_FILE": str(self.root / "etc" / "90-yadgar-kind.conf"),
            "YADGAR_HOSTS_FILE": str(self.root / "etc" / "hosts"),
            "YADGAR_CA_FILE": str(self.root / "etc" / "yadgar" / "edge-ca.crt"),
            "YADGAR_ENROLMENT_FILE": str(self.enrolment_file),
            # --add-user's explicit credential path; the default is root's own.
            "YADGAR_CLIENT_CONFIG": str(self.client_config),
            "YADGAR_POLL_SECONDS": "0",
            "YADGAR_PROBE_ATTEMPTS": "1",
        }
        env.update(extra)
        return env

    def run(self, snippet: str, **extra: str) -> subprocess.CompletedProcess:
        """Source the script (defining its functions, running nothing) and run a snippet."""
        (self.root / "fake" / "rules.json").write_text(json.dumps(self.rules))
        self.state.mkdir(exist_ok=True)
        return subprocess.run(
            ["bash", "-c", f'source "{SCRIPT}"; {snippet}'],
            env=self.env(**extra),
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=60,
        )

    def main(self, *args: str, **extra: str) -> subprocess.CompletedProcess:
        (self.root / "fake" / "rules.json").write_text(json.dumps(self.rules))
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            env=self.env(**extra),
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=120,
        )

    def calls(self, cmd: str | None = None) -> list[dict]:
        path = self.root / "fake" / "calls.jsonl"
        if not path.exists():
            return []
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        return [r for r in rows if cmd is None or r["cmd"] == cmd]

    def reset_calls(self) -> None:
        path = self.root / "fake" / "calls.jsonl"
        if path.exists():
            path.unlink()
        # Sequence counters are kept: a second run continues where the first left
        # off, the way a real cluster's answers would.


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def assert_absent(rig: Rig, proc: subprocess.CompletedProcess, *values: str) -> None:
    """No secret in stdout, stderr, the log file or any fake's argv."""
    log = rig.log.read_text() if rig.log.exists() else ""
    argv = " ".join(" ".join(c["argv"]) for c in rig.calls())
    for value in values:
        assert value, "a secret under test is empty, so its absence would prove nothing"
        assert value not in proc.stdout, "a secret reached stdout"
        assert value not in proc.stderr, "a secret reached stderr"
        assert value not in log, "a secret reached the log file"
        assert value not in argv, "a secret reached a program's argv"


# ─── 5. shellcheck ──────────────────────────────────────────────────────────────


def test_the_script_is_shellcheck_clean() -> None:
    shellcheck = shutil.which("shellcheck")
    assert shellcheck, "shellcheck is not on PATH; the pytest-scripts hook installs shellcheck-py"
    proc = subprocess.run([shellcheck, "--severity=style", str(SCRIPT)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


# ─── what the script reads from the example files ───────────────────────────────


def test_the_edge_it_probes_is_the_one_the_examples_declare(rig: Rig) -> None:
    proc = rig.run('load_examples; printf "%s|%s|%s|%s\\n" "$CLUSTER_NAME" "$GATEWAY_URL" "$GATEWAY_HOST" "$GATEWAY_PORT"')
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == f"yadgar|{GATEWAY}|gateway.yadgar.internal|18443"


def test_it_applies_the_example_files_rather_than_copies_of_them() -> None:
    text = SCRIPT.read_text()
    assert "example/operators-application.yaml" in text
    assert "example/kind/application.yaml" in text
    assert "example/kind/kind-config.yaml" in text
    assert "kind: Application" not in text, "an inline Application would fork the example's pins"


# ─── preconditions ──────────────────────────────────────────────────────────────


def test_it_refuses_to_run_as_a_normal_user(rig: Rig) -> None:
    rig.rules = [{"cmd": "id", "match": ["-u"], "stdout": "1000\n"}] + rig.rules
    proc = rig.main()
    assert proc.returncode != 0
    assert "root" in proc.stderr
    assert rig.calls("kind") == [] and rig.calls("kubectl") == []


def test_it_refuses_an_unknown_flag(rig: Rig) -> None:
    proc = rig.main("--bogus")
    assert proc.returncode != 0
    assert "--bogus" in proc.stderr


# ─── 2. sysctls ─────────────────────────────────────────────────────────────────


def test_sysctls_are_written_once_and_applied_once(rig: Rig) -> None:
    conf = rig.root / "etc" / "90-yadgar-kind.conf"
    # A stock Debian host: every limit below what kind needs, then raised.
    rig.rules = [
        {"cmd": "sysctl", "match": ["-n", "fs.inotify.max_user_watches"], "stdout": ["94294\n", "524288\n"]},
        {"cmd": "sysctl", "match": ["-n", "fs.inotify.max_user_instances"], "stdout": ["128\n", "512\n"]},
        {"cmd": "sysctl", "match": ["-n", "net.ipv4.ip_forward"], "stdout": ["0\n", "1\n"]},
    ] + rig.rules
    proc = rig.run("ensure_sysctls")
    assert proc.returncode == 0, proc.stderr
    assert "fs.inotify.max_user_watches = 524288" in conf.read_text()
    assert "fs.inotify.max_user_instances = 512" in conf.read_text()
    assert "net.ipv4.ip_forward = 1" in conf.read_text()
    assert any("-p" in c["argv"] for c in rig.calls("sysctl"))

    rig.reset_calls()
    proc = rig.run("ensure_sysctls")
    assert proc.returncode == 0, proc.stderr
    assert not any("-p" in c["argv"] for c in rig.calls("sysctl")), "applied again with nothing to change"
    assert "already" in proc.stdout


def test_a_host_with_higher_limits_is_left_alone(rig: Rig) -> None:
    rig.rules = [
        {"cmd": "sysctl", "match": ["-n", "fs.inotify.max_user_watches"], "stdout": "1048576\n"},
        {"cmd": "sysctl", "match": ["-n", "fs.inotify.max_user_instances"], "stdout": "8192\n"},
    ] + rig.rules
    proc = rig.run("ensure_sysctls")
    assert proc.returncode == 0, proc.stderr
    assert not (rig.root / "etc" / "90-yadgar-kind.conf").exists()
    assert not any("-p" in c["argv"] for c in rig.calls("sysctl"))


def test_only_a_lower_limit_is_raised(rig: Rig) -> None:
    rig.rules = [
        {"cmd": "sysctl", "match": ["-n", "fs.inotify.max_user_watches"], "stdout": "1048576\n"},
        {"cmd": "sysctl", "match": ["-n", "fs.inotify.max_user_instances"], "stdout": "128\n"},
    ] + rig.rules
    proc = rig.run("ensure_sysctls")
    assert proc.returncode == 0, proc.stderr
    conf = (rig.root / "etc" / "90-yadgar-kind.conf").read_text()
    assert "fs.inotify.max_user_instances = 512" in conf
    assert "max_user_watches" not in conf, "wrote a limit the host already exceeds"


# ─── 3. pinned tools ────────────────────────────────────────────────────────────


def fake_lock(rig: Rig, sha: str) -> Path:
    lock = rig.root / "tools.lock"
    lock.write_text(f"kind v0.32.0 amd64 {sha} https://example.invalid/kind-linux-amd64\n")
    return lock


def test_a_checksum_mismatch_installs_nothing(rig: Rig) -> None:
    (rig.root / "bin" / "kind").unlink()
    lock = fake_lock(rig, "0" * 64)
    rig.rules = [
        {"cmd": "curl", "match": ["kind-linux-amd64"], "o_content": "#!/bin/sh\necho tampered\n"}
    ] + rig.rules
    proc = rig.run("ensure_tool kind", YADGAR_TOOLS_LOCK=str(lock), YADGAR_ARCH="amd64")
    assert proc.returncode != 0
    assert "checksum mismatch" in proc.stderr
    assert not (rig.root / "bin" / "kind").exists(), "a binary that failed its checksum was installed"


def test_a_verified_download_is_installed_and_a_current_one_is_left_alone(rig: Rig) -> None:
    (rig.root / "bin" / "kind").unlink()
    body = "#!/bin/sh\necho 'kind v0.32.0 go1.26.3 linux/amd64'\n"
    lock = fake_lock(rig, hashlib.sha256(body.encode()).hexdigest())
    rig.rules = [{"cmd": "curl", "match": ["kind-linux-amd64"], "o_content": body}] + [
        r for r in rig.rules if r["cmd"] != "kind"
    ]
    proc = rig.run("ensure_tool kind", YADGAR_TOOLS_LOCK=str(lock), YADGAR_ARCH="amd64")
    assert proc.returncode == 0, proc.stderr
    installed = rig.root / "bin" / "kind"
    assert installed.exists() and installed.stat().st_mode & stat.S_IXUSR

    rig.reset_calls()
    proc = rig.run("ensure_tool kind", YADGAR_TOOLS_LOCK=str(lock), YADGAR_ARCH="amd64")
    assert proc.returncode == 0, proc.stderr
    assert rig.calls("curl") == [], "downloaded again although the pinned version is installed"


def test_a_wrong_version_is_replaced(rig: Rig) -> None:
    body = "#!/bin/sh\necho 'kind v0.32.0 go1.26.3 linux/amd64'\n"
    lock = fake_lock(rig, hashlib.sha256(body.encode()).hexdigest())
    rig.rules = [
        {"cmd": "kind", "match": ["version"], "stdout": "kind v0.20.0 go1.20 linux/amd64\n"},
        {"cmd": "curl", "match": ["kind-linux-amd64"], "o_content": body},
    ] + rig.rules
    proc = rig.run("ensure_tool kind", YADGAR_TOOLS_LOCK=str(lock), YADGAR_ARCH="amd64")
    assert proc.returncode == 0, proc.stderr
    assert len(rig.calls("curl")) == 1
    assert (rig.root / "bin" / "kind").read_text() == body


def test_the_tools_go_to_a_private_directory_by_default(rig: Rig) -> None:
    env = rig.env()
    del env["YADGAR_BIN_DIR"]
    proc = subprocess.run(["bash", "-c", f'source "{SCRIPT}"; printf "%s" "$BIN_DIR"'],
                          env=env, capture_output=True, text=True, check=True)
    assert proc.stdout == "/opt/yadgar-bootstrap/bin"
    # THE INTENT IS AN INSTALL DESTINATION: the pinned tools never go into the
    # shared /usr/local/bin. The directory is still a legitimate PATH entry (sudo's
    # stock secure_path has it, and root's scrubbed PATH must keep it so a plain
    # `sudo` still finds a global npm `claude` or an existing pipx there), so the
    # one ROOT_SAFE_PATH line is the only other place it may appear.
    text = SCRIPT.read_text().replace("never /usr/local/bin", "")
    text = "\n".join(line for line in text.splitlines() if not line.startswith("ROOT_SAFE_PATH="))
    assert "/usr/local/bin" not in text


# ─── root ignores the path overrides (ledger 1556) ──────────────────────────────
#
# The script runs as root. Under `sudo -E`, or any root invocation that keeps the
# caller's environment, a path override would let a non-root caller choose which
# kind/kubectl/helm root executes, which lock vouches for them, where root keeps
# the admin's kubeconfig and records, and which files root writes. So when bash's
# own $EUID is 0 — readonly, set from the kernel, not from the environment or
# PATH — every one of these is its fixed default. The rig fakes `id -u` but runs
# as a real non-root user, which is why the overrides still steer it.
#
# THE ROOT RUNS NEED A REAL EUID OF 0, by the first of two routes that works:
#   `unshare -r`  a user namespace in which this unprivileged process has EUID 0;
#                 a developer host normally allows it, and it needs no privilege.
#   `sudo -n`     real root without a password prompt. The GitHub-hosted runner
#                 allows it, and refuses `unshare -r` (Ubuntu 24.04 restricts
#                 unprivileged user namespaces). `sudo` resets the environment,
#                 so the rig's environment is passed through `env -i` instead.
# Both are resolved from the host PATH before the rig's PATH replaces it. Neither
# working is a failure, never a skip: a skip would leave the root branch
# untested and green.
_ROOT_ROUTE: list[list[str]] = []


def root_route() -> list[str]:
    """The argv prefix that runs a command with EUID 0, probed once per session."""
    if _ROOT_ROUTE:
        return _ROOT_ROUTE[0]
    refusals = []
    unshare = shutil.which("unshare")
    if unshare:
        probe = subprocess.run([unshare, "-r", "true"], capture_output=True, text=True, timeout=30)
        if probe.returncode == 0:
            _ROOT_ROUTE.append([unshare, "-r"])
            return _ROOT_ROUTE[0]
        refusals.append(f"unshare -r: {probe.stderr.strip()}")
    else:
        refusals.append("unshare: not installed")
    sudo = shutil.which("sudo")
    if sudo:
        probe = subprocess.run([sudo, "-n", "true"], capture_output=True, text=True,
                               stdin=subprocess.DEVNULL, timeout=30)
        if probe.returncode == 0:
            _ROOT_ROUTE.append([sudo, "-n", "/usr/bin/env", "-i"])
            return _ROOT_ROUTE[0]
        refusals.append(f"sudo -n: {probe.stderr.strip()}")
    else:
        refusals.append("sudo: not installed")
    pytest.fail("no route to EUID 0, so the root branch cannot be tested: " + "; ".join(refusals))


ROOT_PINNED_PATHS = (
    # (environment override, script variable, value under root)
    ("YADGAR_STATE_DIR", "STATE_DIR", "/var/lib/yadgar-bootstrap"),
    ("YADGAR_BIN_DIR", "BIN_DIR", "/opt/yadgar-bootstrap/bin"),
    ("YADGAR_TOOLS_LOCK", "TOOLS_LOCK", str(LOCK)),
    ("YADGAR_SYSCTL_FILE", "SYSCTL_FILE", "/etc/sysctl.d/90-yadgar-kind.conf"),
    ("YADGAR_HOSTS_FILE", "HOSTS_FILE", "/etc/hosts"),
    ("YADGAR_CA_FILE", "CA_FILE", "/etc/yadgar/edge-ca.crt"),
    ("YADGAR_ENROLMENT_FILE", "ENROLMENT_FILE", "/root/yadgar-enrolment.token"),
)


def as_root(rig: Rig, snippet: str, root: bool, **extra: str) -> subprocess.CompletedProcess:
    """Source the script and run a snippet, with EUID 0 (see `root_route`) or as this user."""
    (rig.root / "fake" / "rules.json").write_text(json.dumps(rig.rules))
    env = rig.env(**extra)
    bash = shutil.which("bash")
    assert bash, "bash is not installed"
    argv = [bash, "-c", f'source "{SCRIPT}"; {snippet}']
    if root:
        route = root_route()
        if route[-1] == "-i":  # sudo resets the environment; env -i restores the rig's
            argv = [*route, *(f"{k}={v}" for k, v in env.items()), *argv]
        else:
            argv = [*route, *argv]
    return subprocess.run(argv, env=env, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=60)


@pytest.mark.parametrize("override, variable, pinned", ROOT_PINNED_PATHS,
                         ids=[row[0] for row in ROOT_PINNED_PATHS])
def test_root_ignores_each_path_override(rig: Rig, override: str, variable: str, pinned: str) -> None:
    evil = str(rig.root / "evil" / override.lower())
    snippet = f'printf "%s|%s" "$EUID" "${variable}"'

    # POSITIVE CONTROL: as this user the override reaches the script, so the
    # root assertion below cannot pass merely because the variable never arrived.
    proc = as_root(rig, snippet, root=False, **{override: evil})
    assert proc.returncode == 0, proc.stderr
    euid, value = proc.stdout.split("|")
    assert euid != "0", "the suite itself runs as root; the control proves nothing"
    assert value == evil

    proc = as_root(rig, snippet, root=True, **{override: evil})
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == f"0|{pinned}", f"root honoured {override}={evil}"


def test_root_never_runs_a_tool_from_a_caller_chosen_bin_dir(rig: Rig) -> None:
    evil = rig.root / "evil-bin"
    evil.mkdir()
    marker = rig.root / "evil-ran"
    (evil / "kind").write_text(f'#!/bin/sh\ntouch "{marker}"\necho "kind v0.32.0"\n')
    (evil / "kind").chmod(0o755)

    # POSITIVE CONTROL: as this user the planted kind is the one asked its version.
    proc = as_root(rig, "installed_version kind", root=False, YADGAR_BIN_DIR=str(evil))
    assert proc.returncode == 0, proc.stderr
    assert marker.exists(), "the planted kind never ran even without root; the test proves nothing"
    marker.unlink()

    proc = as_root(rig, "installed_version kind", root=True, YADGAR_BIN_DIR=str(evil))
    assert proc.returncode == 0, proc.stderr
    assert not marker.exists(), "root executed a kind from the caller's YADGAR_BIN_DIR"


def test_root_never_moves_a_caller_chosen_enrolment_file(rig: Rig) -> None:
    planted = rig.root / "evil-enrolment" / "token"
    planted.parent.mkdir()

    # POSITIVE CONTROL: as this user the override names the file that is moved.
    planted.write_text("x")
    proc = as_root(rig, "retire_spent_token 9", root=False, YADGAR_ENROLMENT_FILE=str(planted))
    assert proc.returncode == 0, proc.stderr
    assert not planted.exists(), "the override never reached retire_spent_token; the test proves nothing"
    for moved in planted.parent.iterdir():
        moved.unlink()

    planted.write_text("x")
    proc = as_root(rig, "retire_spent_token 9", root=True, YADGAR_ENROLMENT_FILE=str(planted))
    assert proc.returncode == 0, proc.stderr
    assert planted.exists(), "root moved a file the caller named in YADGAR_ENROLMENT_FILE"
    assert list(planted.parent.iterdir()) == [planted]


def test_root_says_which_override_it_ignores_and_the_path_it_uses(rig: Rig) -> None:
    evil = str(rig.root / "evil-bin")
    proc = as_root(rig, "true", root=True, YADGAR_BIN_DIR=evil)
    assert proc.returncode == 0, proc.stderr
    assert ("kind-up.sh: YADGAR_BIN_DIR is ignored when run as root; "
            "using /opt/yadgar-bootstrap/bin") in proc.stderr.splitlines()


def test_root_is_quiet_about_an_override_that_names_the_default(rig: Rig) -> None:
    proc = as_root(rig, "true", root=True, YADGAR_BIN_DIR="/opt/yadgar-bootstrap/bin")
    assert proc.returncode == 0, proc.stderr
    assert "YADGAR_BIN_DIR" not in proc.stderr


def test_a_non_root_run_never_warns_about_its_overrides(rig: Rig) -> None:
    proc = as_root(rig, "true", root=False)
    assert proc.returncode == 0, proc.stderr
    assert "is ignored when run as root" not in proc.stderr


# ─── the numeric settings are digits only (review of #48) ───────────────────────
#
# bash evaluates a variable named inside arithmetic as an expression of its own,
# so a value such as `BASH_VERSINFO[$(cmd)]` runs cmd — as root — when `wait_app` computes its
# deadline or `probe_edge` counts its attempts. Each numeric setting is refused
# unless it is all digits, where it is read, before any step runs. Each case
# drives the real code path that would evaluate it.

NUMERIC_SETTINGS = (
    # (environment override, snippet that evaluates it)
    ("YADGAR_OPERATORS_TIMEOUT", 'wait_app operators "$OPERATORS_TIMEOUT"'),
    ("YADGAR_ESTATE_TIMEOUT", 'wait_app yadgar "$ESTATE_TIMEOUT"'),
    ("YADGAR_PROBE_ATTEMPTS", "probe_edge"),
    ("YADGAR_POLL_SECONDS", "probe_edge"),
)


@pytest.mark.parametrize("root", [False, True], ids=["as-user", "as-root"])
@pytest.mark.parametrize("override, snippet", NUMERIC_SETTINGS,
                         ids=[row[0] for row in NUMERIC_SETTINGS])
def test_a_numeric_setting_that_is_not_digits_is_refused_before_it_runs(
        rig: Rig, override: str, snippet: str, root: bool) -> None:
    marker = rig.root / "injected-ran"
    # An array that is always set: under `set -u` an unset name such as `a[...]`
    # stops before its subscript is expanded, which would hide the injection.
    proc = as_root(rig, snippet, root=root, **{override: f"BASH_VERSINFO[$(touch {marker})]"})
    assert not marker.exists(), f"{override} ran a command substitution in arithmetic"
    assert proc.returncode != 0
    assert f"{override} must be a whole number of" in proc.stderr


def test_a_missing_bin_directory_is_created(rig: Rig) -> None:
    bindir = rig.root / "fresh" / "bin"
    body = "#!/bin/sh\necho 'kind v0.32.0 go1.26.3 linux/amd64'\n"
    lock = fake_lock(rig, hashlib.sha256(body.encode()).hexdigest())
    rig.rules = [{"cmd": "curl", "match": ["kind-linux-amd64"], "o_content": body}] + rig.rules
    proc = rig.run("ensure_tool kind", YADGAR_TOOLS_LOCK=str(lock), YADGAR_ARCH="amd64", YADGAR_BIN_DIR=str(bindir))
    assert proc.returncode == 0, proc.stderr
    assert (bindir / "kind").read_text() == body
    assert stat.S_IMODE(bindir.stat().st_mode) == 0o755


def test_the_committed_lock_pins_every_tool_for_both_architectures() -> None:
    rows = [line.split() for line in LOCK.read_text().splitlines()
            if line and not line.startswith("#") and line.split()[0] in PINNED]
    seen = {(r[0], r[2]) for r in rows}
    for tool in PINNED:
        for arch in ("amd64", "arm64"):
            assert (tool, arch) in seen, f"{tool}/{arch} missing from tools.lock"
    for r in rows:
        assert r[1] == PINNED[r[0]], f"{r[0]} pinned at {r[1]}"
        assert len(r[3]) == 64 and all(c in "0123456789abcdef" for c in r[3]), r
        assert r[4].startswith("https://"), r


def test_the_lock_pins_the_client_once() -> None:
    rows = [line.split() for line in LOCK.read_text().splitlines()
            if line and not line.startswith("#") and line.split()[0] == "yaadgaar"]
    # 0.1.12 (yadgar v0.1.12): the first pin with `login --ca-file` (0.1.9) and
    # `admin issue-enrolment` (0.1.10) that the printed steps use (ledger 1623).
    # It keeps its config in ~/.config/yaadgaar, as 0.1.5 began to (ledger 1566).
    assert rows == [["yaadgaar", "0.1.12", "pypi"]]


def test_the_pinned_client_has_what_the_printed_steps_use() -> None:
    """The lock is at or above the release the steps name, so root's own client can
    run `admin issue-enrolment` (ledger 1623). Numeric, not lexical: 0.1.9 > 0.1.10 as text."""
    def release(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in v.split("."))
    minimum = re.search(r'^CLIENT_MIN_FOR_JOINING="([0-9.]+)"', SCRIPT.read_text(), re.M)
    assert minimum, "CLIENT_MIN_FOR_JOINING not found"
    assert release(client_version()) >= release(minimum.group(1))


def test_the_printed_steps_name_the_pinned_client_literally(rig: Rig) -> None:
    """Not read back from the lock: the version a person is told to install."""
    add_user_rig(rig)
    proc = rig.main("--add-user", "dave@example.com")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "pipx install yaadgaar==0.1.12" in proc.stdout


# ─── 6/7. Argo verdicts ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("doc", "verdict"),
    [
        ("", "wait"),
        (json.dumps({"metadata": {"name": "x"}, "spec": {"source": {"targetRevision": "0.3.8"}}}), "wait"),
        (app_json("yadgar", "Running", sync="OutOfSync", health="Progressing"), "wait"),
        (app_json("yadgar", "Running", message="... Retrying attempt #2 at 8:20PM."), "wait"),
        (app_json("yadgar", "Failed"), "failed"),
        (app_json("yadgar", "Error"), "failed"),
        # A FAILED OPERATION FOR ANOTHER REVISION is history, not this run's answer:
        # automated sync starts a new one for the pinned revision.
        (app_json("yadgar", "Failed", revision="0.3.7"), "wait"),
        # THE OPERATION'S REVISION IN ANOTHER FORM than `targetRevision` (a
        # resolved digest, a `v` prefix): `status.sync.revision` is what Argo
        # resolved the target to, and agreeing with it is agreeing with the pin.
        (json.dumps({**json.loads(app_json("yadgar", "Failed", revision="sha256:abc")),
                     "status": {**json.loads(app_json("yadgar", "Failed", revision="sha256:abc"))["status"],
                                "sync": {"status": "Synced", "revision": "sha256:abc"}}}), "failed"),
        (json.dumps({**json.loads(app_json("yadgar", "Succeeded", revision="sha256:abc")),
                     "status": {**json.loads(app_json("yadgar", "Succeeded", revision="sha256:abc"))["status"],
                                "sync": {"status": "Synced", "revision": "sha256:abc"}}}), "ok"),
        (app_json("yadgar", "Succeeded", health="Progressing"), "wait"),
        (app_json("yadgar", "Succeeded", sync="OutOfSync"), "wait"),
        (app_json("yadgar", "Succeeded"), "ok"),
    ],
)
def test_the_argo_verdict(rig: Rig, doc: str, verdict: str) -> None:
    (rig.root / "doc.json").write_text(doc)
    proc = rig.run(f'app_verdict < "{rig.root / "doc.json"}"')
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == verdict


def test_a_failed_operation_exits_non_zero_naming_the_failed_resources(rig: Rig) -> None:
    failed = app_json(
        "yadgar",
        "Failed",
        health="Healthy",
        message="one or more synchronization tasks completed unsuccessfully (retried 6 times).",
        resources=[
            {"kind": "Job", "namespace": "yadgar", "name": "envoy-gateway-probe", "status": "Synced",
             "hookPhase": "Failed", "message": "Job has reached the specified backoff limit"},
            {"kind": "Deployment", "namespace": "yadgar", "name": "iam", "status": "Synced", "hookPhase": ""},
        ],
    )
    rig.rules = [
        {"cmd": "kubectl", "match": ["get", "application", "yadgar"],
         "stdout": [app_json("yadgar", "Running", health="Progressing"), failed]}
    ] + rig.rules
    proc = rig.run("load_examples; wait_app yadgar 60")
    assert proc.returncode != 0
    out = proc.stdout + proc.stderr
    assert "envoy-gateway-probe" in out
    assert "backoff limit" in out
    assert "retried 6 times" in out
    assert "target=0.3.8" in out and "operation-revision=0.3.8" in out, "the revision forms were not logged"
    assert "does not retry it" in out and "patch application yadgar" in out, "no remedy printed"
    assert " iam" not in out, "a resource that synced fine was reported as failing"
    # Never forced: no sync, no patch of `operation`, no terminate.
    for c in rig.calls("kubectl"):
        assert "patch" not in c["argv"], c


def test_a_timeout_prints_the_conditions_and_the_health_note(rig: Rig) -> None:
    # Argo v3 does not persist per-resource health onto the Application CR by
    # default (`controller.resource.health.persist` unset, measured 2026-10-02
    # against kind-yadgar), so a resource `kubectl get application` returns
    # NEVER carries a populated `.health` field — this fixture omits it, as
    # the real object does. A prior version of this test faked `.health` onto
    # the resource and asserted it got printed, which passed against a shape
    # Argo never actually sends and hid that the "unhealthy:" line was dead
    # code in production.
    doc = json.loads(app_json("operators", "Running", health="Degraded"))
    doc["status"]["conditions"] = [{"type": "SyncError", "message": "a condition worth reading"}]
    doc["status"]["resources"] = [
        {"kind": "Deployment", "namespace": "yadgar-operators", "name": "keda-operator"}
    ]
    rig.rules = [{"cmd": "kubectl", "match": ["get", "application", "operators"], "stdout": json.dumps(doc)}] + rig.rules
    proc = rig.run("load_examples; wait_app operators 0")
    assert proc.returncode != 0
    out = proc.stdout + proc.stderr
    assert "timed out" in out
    assert "a condition worth reading" in out
    # No fabricated "unhealthy:" line — there is nothing to read it from.
    assert "unhealthy:" not in out
    assert "keda-operator" not in out
    # Instead, a fixed note always points at the paste-safe recipe: a
    # throwaway, namespaced copy of the kubeconfig, not a raw `--core` call
    # (which needs `argocd-cm` in the current namespace to resolve at all) and
    # not a mutation of the operator's own kubeconfig. Subshell-scoped, like
    # yadgarhq/argocd's MIGRATION_NOTES.md "Apply" recipe: `set -eu` so a
    # failed minify stops the recipe instead of falling through to whatever
    # kubeconfig `argocd`/`kubectl` default to, and the `-s` guard makes that
    # failure explicit rather than silent.
    assert "argocd (not installed by this script)" in out
    assert "set -eu" in out
    assert '[ -s "$TMPKC" ] || exit 1' in out

    # kind-up.sh never puts kubectl on PATH (BIN_DIR defaults to
    # /opt/yadgar-bootstrap/bin, not /usr/local/bin — see k()/h() and the
    # remedy line above, both of which call "$BIN_DIR/kubectl"). A bare
    # `kubectl` here would only look right in THIS suite, where the Rig's own
    # PATH fake happens to carry one too. No occurrence of the token may be a
    # standalone command inside the printed recipe: every one there must be
    # part of a `/kubectl` path. (The prose sentence above the recipe says the
    # word "kubectl" too, in English, with nothing to resolve — that one is
    # fine and out of scope for this check.)
    recipe = out[out.index("    (\n") : out.index("    )\n") + len("    )\n")]
    assert re.search(r"(?<!/)\bkubectl\b", recipe) is None, recipe
    bin_kubectl = f'"{rig.root / "bin" / "kubectl"}"'
    kubeconfig_file = str(rig.state / "kubeconfig")
    # The FULL minify line, not a fragment: dropping --kubeconfig here would
    # read whatever kubeconfig is ambient instead of kind-up's own, which is
    # the one failure mode this recipe exists to avoid.
    assert (
        f'{bin_kubectl} --kubeconfig "{kubeconfig_file}" config view --minify '
        f'--flatten --context "kind-yadgar" > "$TMPKC"'
    ) in out
    assert f'{bin_kubectl} --kubeconfig "$TMPKC" config set-context "kind-yadgar" --namespace argocd' in out
    assert 'argocd app get operators --core --kube-context "kind-yadgar"' in out


def test_the_health_note_recipe_runs_with_no_kubectl_on_path(rig: Rig) -> None:
    """Executes the printed recipe for real against a PATH that carries no
    `kubectl` at all — only the absolute `$BIN_DIR/kubectl` baked into the
    recipe's own text, plus a stubbed `argocd`. A bare `kubectl` anywhere in
    the recipe fails here with "command not found" instead of completing;
    the string checks above would not catch a regression that reintroduced
    one under a spelling they do not look for.
    """
    doc = json.loads(app_json("operators", "Running", health="Degraded"))
    no_kubectl_bin = rig.root / "no-kubectl-bin"
    no_kubectl_bin.mkdir()
    (no_kubectl_bin / "argocd").symlink_to(FAKE)
    rig.rules = [
        {"cmd": "argocd", "match": ["app", "get"], "stdout": json.dumps({"status": {"resources": []}})},
        {"cmd": "kubectl", "match": ["config", "set-context"], "stdout": ""},
        {"cmd": "kubectl", "match": ["config", "view", "--minify"], "stdout": "apiVersion: v1\nkind: Config\n"},
        {"cmd": "kubectl", "match": ["get", "application", "operators"], "stdout": json.dumps(doc)},
    ] + rig.rules
    proc = rig.run("load_examples; wait_app operators 0")
    out = proc.stdout + proc.stderr
    recipe = out[out.index("    (\n") : out.index("    )\n") + len("    )\n")]

    env = rig.env()
    env["PATH"] = f"{no_kubectl_bin}:{rig.root / 'hostbin'}"  # no fakebin: no bare kubectl here
    recipe_proc = subprocess.run(
        ["bash", "-c", recipe],
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=30,
    )
    combined = recipe_proc.stdout + recipe_proc.stderr
    assert "command not found" not in combined, combined
    assert recipe_proc.returncode == 0, combined


# ─── 8. hosts file ──────────────────────────────────────────────────────────────


def test_the_hosts_entry_is_added_once(rig: Rig) -> None:
    for _ in range(2):
        proc = rig.run("ensure_hosts_entry gateway.yadgar.internal")
        assert proc.returncode == 0, proc.stderr
    lines = (rig.root / "etc" / "hosts").read_text().splitlines()
    assert lines.count("127.0.0.1 gateway.yadgar.internal") == 1
    assert lines[0] == "127.0.0.1 localhost"


def test_a_hosts_entry_among_other_names_counts(rig: Rig) -> None:
    hosts = rig.root / "etc" / "hosts"
    hosts.write_text("127.0.0.1 localhost gateway.yadgar.internal\n")
    proc = rig.run("ensure_hosts_entry gateway.yadgar.internal")
    assert proc.returncode == 0, proc.stderr
    assert hosts.read_text() == "127.0.0.1 localhost gateway.yadgar.internal\n"


def test_a_hosts_entry_pointing_elsewhere_is_refused_not_overwritten(rig: Rig) -> None:
    hosts = rig.root / "etc" / "hosts"
    hosts.write_text("10.0.0.9 gateway.yadgar.internal\n")
    proc = rig.run("ensure_hosts_entry gateway.yadgar.internal")
    assert proc.returncode != 0
    assert "10.0.0.9" in proc.stderr
    assert hosts.read_text() == "10.0.0.9 gateway.yadgar.internal\n"


def test_a_hosts_file_without_a_trailing_newline_is_not_corrupted(rig: Rig) -> None:
    hosts = rig.root / "etc" / "hosts"
    hosts.write_text("::1 localhost")
    proc = rig.run("ensure_hosts_entry gateway.yadgar.internal")
    assert proc.returncode == 0, proc.stderr
    assert hosts.read_text() == "::1 localhost\n127.0.0.1 gateway.yadgar.internal\n"


def test_a_commented_hosts_entry_does_not_count(rig: Rig) -> None:
    hosts = rig.root / "etc" / "hosts"
    hosts.write_text("# 10.0.0.9 gateway.yadgar.internal\n")
    proc = rig.run("ensure_hosts_entry gateway.yadgar.internal")
    assert proc.returncode == 0, proc.stderr
    assert "127.0.0.1 gateway.yadgar.internal" in hosts.read_text().splitlines()


# ─── 9. the first administrator ─────────────────────────────────────────────────


def new_secrets() -> tuple[str, str]:
    """Generated per run: a committed fixture token would trip gitleaks."""
    bootstrap = base64.b64encode(os.urandom(33)).decode()
    enrolment = secrets.token_urlsafe(96)
    return bootstrap, enrolment


# VERBATIM FROM GATEWAY v0.9.54, `src/http/authority.rs` `admin_failure`: the one
# 403 body that means "this admin already holds a credential". The body is the
# only discriminator; the gateway sends no error code beside it.
ZERO_CREDENTIAL_REFUSAL = (
    '{"error":"the bootstrap token may only enrol an administrator who has never held a credential"}'
)


def admin_rules(
    bootstrap: str,
    enrolment: str,
    create_code: str = "200",
    issue_code: str = "200",
    install_uid: str = "11111111-aaaa-4bbb-8ccc-000000000001",
    user: str = "yadgar:user:01a0f403-78c5-7464-bdf4-c534841e5178",
) -> list[dict]:
    create_body = json.dumps({"user_id": user}) if create_code == "200" else '{"error":"the administrative service is unavailable"}'
    issue_body = (
        json.dumps({"token": enrolment, "enrolment_id": "e1"})
        if issue_code == "200"
        else ZERO_CREDENTIAL_REFUSAL
    )
    return [
        # THE INSTALL IDENTITY: the uid of the Secret the PreSync Job mints once
        # per installation. Before the token rule, which would also match.
        {"cmd": "kubectl", "match": ["secret", "admin-bootstrap-token", "metadata.uid"], "stdout": install_uid},
        {"cmd": "kubectl", "match": ["secret", "admin-bootstrap-token"],
         "stdout": base64.b64encode(bootstrap.encode()).decode()},
        {"cmd": "curl", "match": ["/admin/create-user"], "stdout": create_code, "o_content": create_body},
        {"cmd": "curl", "match": ["/admin/issue-enrolment"], "stdout": issue_code, "o_content": issue_body},
    ]


def test_the_first_admin_is_created_and_no_secret_is_printed(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    rig.rules = admin_rules(bootstrap, enrolment) + rig.rules
    proc = rig.run("load_examples; ensure_admin")
    assert proc.returncode == 0, proc.stderr

    assert rig.enrolment_file.read_text().strip() == enrolment
    assert stat.S_IMODE(rig.enrolment_file.stat().st_mode) == 0o600
    admin = json.loads((rig.state / "admin.json").read_text())
    assert admin["user_id"].startswith("yadgar:user:")

    assert_absent(rig, proc, bootstrap, base64.b64encode(bootstrap.encode()).decode(), enrolment)
    # POSITIVE CONTROL: the token did reach the gateway, on curl's stdin.
    curls = rig.calls("curl")
    assert len(curls) == 2
    for c in curls:
        assert f"x-yadgar-bootstrap-token: {bootstrap}" in (c["stdin"] or "")


def test_the_create_user_body_carries_the_configured_admin(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    rig.rules = admin_rules(bootstrap, enrolment) + rig.rules
    proc = rig.run(
        "load_examples; ensure_admin",
        YADGAR_ADMIN_EXTERNAL_ID="ops@example.test",
        YADGAR_ADMIN_DISPLAY_NAME="Ops Admin",
    )
    assert proc.returncode == 0, proc.stderr
    admin = json.loads((rig.state / "admin.json").read_text())
    assert admin["external_id"] == "ops@example.test"
    create = next(c for c in rig.calls("curl") if any("/admin/create-user" in a for a in c["argv"]))
    body = json.loads(create["data"])
    assert body == {"external_id": "ops@example.test", "display_name": "Ops Admin", "is_admin": True}


def test_a_fresh_enrolment_file_skips_the_whole_ceremony(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    rig.rules = admin_rules(bootstrap, enrolment) + rig.rules
    assert rig.run("load_examples; ensure_admin").returncode == 0
    rig.reset_calls()
    proc = rig.run("load_examples; ensure_admin")
    assert proc.returncode == 0, proc.stderr
    assert rig.calls("curl") == []
    reads = [c for c in rig.calls("kubectl") if any(".data.token" in a for a in c["argv"])]
    assert reads == [], "read the bootstrap token although nothing needed it"


def test_a_recorded_admin_without_an_enrolment_is_re_enrolled_not_re_created(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    rig.rules = admin_rules(bootstrap, enrolment) + rig.rules
    assert rig.run("load_examples; ensure_admin").returncode == 0
    rig.enrolment_file.unlink()
    rig.reset_calls()
    proc = rig.run("load_examples; ensure_admin")
    assert proc.returncode == 0, proc.stderr
    urls = [a for c in rig.calls("curl") for a in c["argv"] if a.startswith("https://")]
    assert urls == [f"{GATEWAY}/admin/issue-enrolment"]
    assert rig.enrolment_file.read_text().strip() == enrolment


def test_an_expired_enrolment_file_is_reissued(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    rig.rules = admin_rules(bootstrap, enrolment) + rig.rules
    assert rig.run("load_examples; ensure_admin").returncode == 0
    old = rig.enrolment_file.stat().st_mtime - 25 * 3600
    os.utime(rig.enrolment_file, (old, old))
    rig.reset_calls()
    proc = rig.run("load_examples; ensure_admin")
    assert proc.returncode == 0, proc.stderr
    urls = [a for c in rig.calls("curl") for a in c["argv"] if a.startswith("https://")]
    assert urls == [f"{GATEWAY}/admin/issue-enrolment"]


def test_an_admin_who_already_holds_a_credential_is_done_not_failed(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    rig.rules = admin_rules(bootstrap, enrolment) + rig.rules
    assert rig.run("load_examples; ensure_admin").returncode == 0
    rig.enrolment_file.unlink()
    rig.rules = admin_rules(bootstrap, enrolment, issue_code="403") + rig.rules
    proc = rig.run("load_examples; ensure_admin")
    assert proc.returncode == 0, proc.stderr
    assert "already enrolled" in proc.stdout
    assert not rig.enrolment_file.exists()


def test_any_other_403_from_issue_enrolment_is_a_failure(rig: Rig) -> None:
    """The gateway answers 403 for more than one reason; only one of them means done."""
    bootstrap, enrolment = new_secrets()
    rig.rules = [
        {"cmd": "curl", "match": ["/admin/issue-enrolment"], "stdout": "403",
         "o_content": '{"error":"origin not allowed"}'},
    ] + admin_rules(bootstrap, enrolment) + rig.rules
    proc = rig.run("load_examples; ensure_admin")
    assert proc.returncode != 0
    assert "origin not allowed" in proc.stderr
    assert "already enrolled" not in proc.stdout


def test_the_zero_credential_match_is_the_gateway_body_the_script_names() -> None:
    text = SCRIPT.read_text()
    assert "gateway v0.9.54" in text
    phrase = "may only enrol an administrator who has never held a credential"
    assert phrase in ZERO_CREDENTIAL_REFUSAL and phrase in text


def fresh_install(rig: Rig, bootstrap: str, enrolment: str, uid: str, user: str) -> None:
    rig.rules = admin_rules(bootstrap, enrolment, install_uid=uid, user=user) + [
        r for r in rig.rules if r["cmd"] not in ("curl",) and "admin-bootstrap-token" not in " ".join(r.get("match", []))
    ]


def test_a_recreated_cluster_gets_a_new_admin_within_the_token_lifetime(rig: Rig) -> None:
    """`kind delete cluster` and a rerun: the old token names a user that no longer exists."""
    bootstrap, enrolment = new_secrets()
    fresh_install(rig, bootstrap, enrolment, "uid-first", "yadgar:user:first")
    assert rig.run("load_examples; ensure_admin").returncode == 0
    (rig.state / "client-enrolled").touch()

    bootstrap2, enrolment2 = new_secrets()
    fresh_install(rig, bootstrap2, enrolment2, "uid-second", "yadgar:user:second")
    rig.reset_calls()
    proc = rig.run("load_examples; ensure_admin")
    assert proc.returncode == 0, proc.stderr
    urls = [a for c in rig.calls("curl") for a in c["argv"] if a.startswith("https://")]
    assert urls == [f"{GATEWAY}/admin/create-user", f"{GATEWAY}/admin/issue-enrolment"]
    admin = json.loads((rig.state / "admin.json").read_text())
    assert admin == {"external_id": "admin", "user_id": "yadgar:user:second", "install_uid": "uid-second"}
    assert rig.enrolment_file.read_text().strip() == enrolment2
    # The old install's record, token and client marker are kept aside, not deleted.
    aside = sorted(p.name for p in rig.state.glob("*.stale-*"))
    assert [n.split(".stale-")[0] for n in aside] == ["admin.json", "client-enrolled"]
    old_tokens = list(rig.enrolment_file.parent.glob(rig.enrolment_file.name + ".stale-*"))
    assert len(old_tokens) == 1 and old_tokens[0].read_text().strip() == enrolment
    assert stat.S_IMODE(old_tokens[0].stat().st_mode) == 0o600
    assert not (rig.state / "client-enrolled").exists()
    assert_absent(rig, proc, bootstrap2, enrolment2, enrolment)


def test_a_recreated_cluster_after_the_token_expired_never_enrols_the_dead_user(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    fresh_install(rig, bootstrap, enrolment, "uid-first", "yadgar:user:first")
    assert rig.run("load_examples; ensure_admin").returncode == 0
    old = rig.enrolment_file.stat().st_mtime - 25 * 3600
    os.utime(rig.enrolment_file, (old, old))

    bootstrap2, enrolment2 = new_secrets()
    fresh_install(rig, bootstrap2, enrolment2, "uid-second", "yadgar:user:second")
    rig.reset_calls()
    proc = rig.run("load_examples; ensure_admin")
    assert proc.returncode == 0, proc.stderr
    issued_for = [json.loads(c["data"])["user_id"] for c in rig.calls("curl")
                  if any("/admin/issue-enrolment" in a for a in c["argv"])]
    assert issued_for == ["yadgar:user:second"], "enrolled a user from the deleted install"


def test_an_enrolment_file_with_no_record_is_not_trusted(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    rig.rules = admin_rules(bootstrap, enrolment) + rig.rules
    rig.enrolment_file.write_text("left over from somewhere\n")
    (rig.state / "client-logged-in").touch()
    proc = rig.run("load_examples; ensure_admin")
    assert proc.returncode == 0, proc.stderr
    assert rig.enrolment_file.read_text().strip() == enrolment
    kept = list(rig.enrolment_file.parent.glob(rig.enrolment_file.name + ".stale-*"))
    assert [k.read_text() for k in kept] == ["left over from somewhere\n"], "overwritten rather than set aside"
    assert not (rig.state / "client-logged-in").exists(), "a client marker outlived the install it described"


def test_a_failure_writing_the_enrolment_token_is_not_reported_as_success(rig: Rig) -> None:
    """issue_enrolment runs with errexit: a failed write must stop the script."""
    bootstrap, enrolment = new_secrets()
    rig.rules = admin_rules(bootstrap, enrolment) + rig.rules
    blocker = rig.root / "not-a-dir"
    blocker.write_text("")
    proc = rig.run("load_examples; ensure_admin", YADGAR_ENROLMENT_FILE=str(blocker / "token"))
    assert proc.returncode != 0
    assert "written to" not in proc.stdout


def test_create_user_refused_fails_with_the_way_out_and_is_not_retried(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    rig.rules = admin_rules(bootstrap, enrolment, create_code="503") + rig.rules
    proc = rig.run("load_examples; ensure_admin")
    assert proc.returncode != 0
    assert "YADGAR_ADMIN_EXTERNAL_ID" in proc.stderr
    creates = [c for c in rig.calls("curl") if any("/admin/create-user" in a for a in c["argv"])]
    assert len(creates) == 1, "create-user was retried; a lost 200 then reads as an outage"
    assert not (rig.state / "admin.json").exists()
    assert_absent(rig, proc, bootstrap)


# ─── the whole script, twice ────────────────────────────────────────────────────


def full_rules(bootstrap: str, enrolment: str) -> list[dict]:
    ca = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"
    ops_ok = app_json("operators", "Succeeded", revision="0.1.19", target="0.1.19")
    return admin_rules(bootstrap, enrolment) + [
        {"cmd": "kind", "match": ["get", "clusters"], "stdout": ["", "yadgar\n"]},
        {"cmd": "kind", "match": ["export", "kubeconfig"], "write_arg": "--kubeconfig",
         "write_content": "apiVersion: v1\nkind: Config\n"},
        # `kubectl diff` exits 1 when the live object differs (first run: absent)
        # and 0 when it matches (every later run).
        {"cmd": "kubectl", "match": [" diff -f ", "operators-application.yaml"], "exit": [1, 0]},
        {"cmd": "kubectl", "match": [" diff -f ", "kind/application.yaml"], "exit": [1, 0]},
        {"cmd": "kubectl", "match": ["get", "--raw", "/readyz"], "stdout": "ok"},
        {"cmd": "kubectl", "match": ["get", "nodes"],
         "stdout": json.dumps({"items": [{"status": {"conditions": [{"type": "Ready", "status": "True"}]}}]})},
        {"cmd": "podman", "match": ["port"], "stdout": "127.0.0.1:18443\n"},
        {"cmd": "helm", "match": ["list"], "stdout": [
            "[]", json.dumps([{"name": "argocd", "status": "deployed", "chart": "argo-cd-8.6.1"}])]},
        {"cmd": "kubectl", "match": ["deployment", "argocd-server"], "stdout": "quay.io/argoproj/argocd:v3.1.8"},
        {"cmd": "kubectl", "match": ["get", "application", "operators"], "stdout": ops_ok},
        {"cmd": "kubectl", "match": ["get", "application", "yadgar"], "stdout": app_json("yadgar", "Succeeded")},
        {"cmd": "kubectl", "match": ["secret", "gateway-tls"], "stdout": base64.b64encode(ca.encode()).decode()},
        {"cmd": "curl", "match": ["--cacert", f"{GATEWAY}/"], "stdout": "405"},
    ]


def test_the_whole_run_is_idempotent_and_touches_only_the_kind_cluster(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    rig.rules = full_rules(bootstrap, enrolment) + rig.rules

    first = rig.main()
    assert first.returncode == 0, first.stdout + first.stderr
    assert [c for c in rig.calls("kind") if "create" in c["argv"]], "no cluster was created"
    assert rig.enrolment_file.read_text().strip() == enrolment
    ca_file = rig.root / "etc" / "yadgar" / "edge-ca.crt"
    assert stat.S_IMODE(ca_file.stat().st_mode) == 0o644
    # A 0644 file in a 0700 directory is readable by nobody but root.
    assert stat.S_IMODE(ca_file.parent.stat().st_mode) == 0o755
    assert "BEGIN CERTIFICATE" in ca_file.read_text()
    assert "yaadgaar enrol --token-file" in first.stdout
    assert "pipx install yaadgaar" in first.stdout

    # EVERY kubectl and helm call names the kind cluster's own kubeconfig and
    # context, so a real binary reached by accident still could not read the
    # host's kubeconfig.
    kubeconfig = str(rig.state / "kubeconfig")
    for c in rig.calls("kubectl"):
        if "version" in c["argv"]:
            continue
        assert c["argv"][:4] == ["--kubeconfig", kubeconfig, "--context", "kind-yadgar"], c
    for c in rig.calls("helm"):
        if c["argv"][:1] == ["version"]:
            continue
        assert c["argv"][:4] == ["--kubeconfig", kubeconfig, "--kube-context", "kind-yadgar"], c
    for c in rig.calls("kind"):
        if c["argv"][:1] == ["version"] or c["argv"][:2] == ["get", "clusters"]:
            continue
        assert c["argv"][c["argv"].index("--kubeconfig") + 1] in (kubeconfig, kubeconfig + ".new"), c
    applied = [c["argv"][c["argv"].index("-f") + 1] for c in rig.calls("kubectl") if "apply" in c["argv"]]
    assert applied == [
        str(REPO / "example" / "operators-application.yaml"),
        str(REPO / "example" / "kind" / "application.yaml"),
    ]
    assert_absent(rig, first, bootstrap, base64.b64encode(bootstrap.encode()).decode(), enrolment)

    ca_before = ca_file.stat()
    kubeconfig_file = rig.state / "kubeconfig"
    kubeconfig_file.write_text("apiVersion: v1\nkind: Config\n")
    kc_before = kubeconfig_file.stat()

    rig.reset_calls()
    second = rig.main()
    assert second.returncode == 0, second.stdout + second.stderr
    # WRITE-FREE: no apply when `kubectl diff` finds nothing, and the CA and the
    # kubeconfig are not rewritten with the content they already hold.
    assert not [c for c in rig.calls("kubectl") if "apply" in c["argv"]], "applied an unchanged Application"
    assert second.stdout.count("unchanged") >= 4, second.stdout
    for before, path in ((ca_before, ca_file), (kc_before, kubeconfig_file)):
        after = path.stat()
        assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns), f"{path} rewritten"
    assert not [c for c in rig.calls("kind") if "create" in c["argv"]], "created the cluster again"
    exports = [c for c in rig.calls("kind") if "export" in c["argv"]]
    assert exports and all(
        c["argv"][c["argv"].index("--kubeconfig") + 1] in (kubeconfig, kubeconfig + ".new") for c in exports
    )
    helm_writes = [c for c in rig.calls("helm") if {"upgrade", "install", "uninstall", "rollback"} & set(c["argv"])]
    assert helm_writes == [], "wrote a new Argo CD release revision with nothing to change"
    assert rig.calls("apt-get") == []
    assert not [c for c in rig.calls("curl") if "/admin/" in " ".join(c["argv"])], "ran the ceremony again"
    assert not [c for c in rig.calls("curl") if "-o" in c["argv"] and "--cacert" not in c["argv"]], "downloaded again"
    hosts = (rig.root / "etc" / "hosts").read_text().splitlines()
    assert hosts.count("127.0.0.1 gateway.yadgar.internal") == 1
    assert_absent(rig, second, bootstrap, enrolment)


def test_the_estate_application_is_not_applied_while_the_operators_fail(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    failed = app_json("operators", "Failed", revision="0.1.19", target="0.1.19", message="boom")
    rig.rules = [
        {"cmd": "kubectl", "match": ["get", "application", "operators"], "stdout": failed}
    ] + full_rules(bootstrap, enrolment) + rig.rules
    proc = rig.main()
    assert proc.returncode != 0
    applied = [c["argv"][c["argv"].index("-f") + 1] for c in rig.calls("kubectl") if "apply" in c["argv"]]
    assert applied == [str(REPO / "example" / "operators-application.yaml")]
    assert not [c for c in rig.calls("curl") if "/admin/" in " ".join(c["argv"])]


def test_an_existing_cluster_without_the_edge_mapping_is_refused(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    rig.rules = [
        {"cmd": "kind", "match": ["get", "clusters"], "stdout": "yadgar\n"},
        {"cmd": "podman", "match": ["port"], "stdout": "", "exit": 1},
    ] + full_rules(bootstrap, enrolment) + rig.rules
    proc = rig.main()
    assert proc.returncode != 0
    assert "18443" in proc.stderr
    assert not [c for c in rig.calls("kind") if "create" in c["argv"] or "delete" in c["argv"]]


# ─── 10. --with-client ──────────────────────────────────────────────────────────


def test_with_client_skips_when_the_client_has_no_password_stdin(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    rig.rules = [
        {"cmd": "yaadgaar", "match": ["enrol", "--help"], "stdout": "Usage: yaadgaar enrol [TOKEN]\n"},
    ] + full_rules(bootstrap, enrolment) + rig.rules
    proc = rig.main("--with-client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "--password-stdin" in proc.stdout
    assert not [c for c in rig.calls("yaadgaar") if "--password-stdin" in c["argv"]]


def password_stdin_rule() -> dict:
    return {"cmd": "yaadgaar", "match": ["enrol", "--help"],
            "stdout": "Usage: yaadgaar enrol [OPTIONS]\n  --token-file <PATH>\n  --password-stdin\n"}


def test_with_client_enrols_without_login_and_without_printing_the_password(rig: Rig) -> None:
    """`enrol` stores the same credential `login` would (yadgar v0.1.2 `login.rs`:
    both end in `reconcile` + `config.save`), so no login follows it."""
    bootstrap, enrolment = new_secrets()
    rig.rules = [password_stdin_rule()] + full_rules(bootstrap, enrolment) + rig.rules
    proc = rig.main("--with-client")
    assert proc.returncode == 0, proc.stdout + proc.stderr

    pw_file = rig.state / "client-password"
    password = pw_file.read_text().strip()
    assert stat.S_IMODE(pw_file.stat().st_mode) == 0o600
    enrol = [c for c in rig.calls("yaadgaar") if c["argv"][:1] == ["enrol"] and "--password-stdin" in c["argv"]]
    assert len(enrol) == 1
    assert not [c for c in rig.calls("yaadgaar") if c["argv"][:1] == ["login"]], "logged in after enrol"
    assert enrol[0]["argv"][enrol[0]["argv"].index("--token-file") + 1] == str(rig.enrolment_file)
    # POSITIVE CONTROL: the password went to enrol, on stdin.
    assert enrol[0]["stdin"].strip() == password
    assert_absent(rig, proc, password, bootstrap, enrolment)
    assert (rig.state / "client-enrolled").exists()

    rig.reset_calls()
    again = rig.main("--with-client")
    assert again.returncode == 0, again.stdout + again.stderr
    assert not [c for c in rig.calls("yaadgaar") if c["argv"][:1] == ["enrol"] and "--password-stdin" in c["argv"]]
    assert not [c for c in rig.calls("curl") if "/admin/" in " ".join(c["argv"])], "ran the ceremony again"


def test_a_redeemed_token_is_retired_and_never_offered_again(rig: Rig) -> None:
    """Ledger 1544: the spent token used to be logged as "current" by its mtime and
    handed back in the next steps."""
    bootstrap, enrolment = new_secrets()
    rig.rules = [password_stdin_rule()] + full_rules(bootstrap, enrolment) + rig.rules
    proc = rig.main("--with-client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not rig.enrolment_file.exists(), "the redeemed token was left where the next steps point"
    spent = list(rig.enrolment_file.parent.glob(rig.enrolment_file.name + ".redeemed-*"))
    assert len(spent) == 1 and spent[0].read_text().strip() == enrolment
    assert stat.S_IMODE(spent[0].stat().st_mode) == 0o600
    assert "--token-file" not in proc.stdout.split("done.")[-1], "offered the redeemed token"
    assert "--add-user" in proc.stdout

    # A rerun WITHOUT --with-client offers nothing either.
    rig.reset_calls()
    plain = rig.main()
    assert plain.returncode == 0, plain.stdout + plain.stderr
    assert "current enrolment token" not in plain.stdout
    assert "--token-file" not in plain.stdout
    assert not [c for c in rig.calls("curl") if "/admin/" in " ".join(c["argv"])]
    assert_absent(rig, plain, bootstrap, enrolment)


def test_a_host_enrolled_by_an_earlier_version_has_its_spent_token_retired(rig: Rig) -> None:
    """The state a v0.24.17 --with-client run left: both markers and the spent token."""
    bootstrap, enrolment = new_secrets()
    rig.rules = full_rules(bootstrap, enrolment) + rig.rules
    assert rig.main().returncode == 0
    (rig.state / "client-enrolled").touch()
    (rig.state / "client-logged-in").touch()
    rig.reset_calls()
    proc = rig.main()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not rig.enrolment_file.exists()
    assert list(rig.enrolment_file.parent.glob(rig.enrolment_file.name + ".redeemed-*"))
    assert "--token-file" not in proc.stdout
    reads = [c for c in rig.calls("kubectl") if any(".data.token" in a for a in c["argv"])]
    assert reads == [], "read the bootstrap token although the admin is enrolled here"


def test_a_failed_enrol_keeps_the_token_and_writes_no_marker(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    rig.rules = [
        password_stdin_rule(),
        {"cmd": "yaadgaar", "match": ["enrol", "--token-file"], "stdout": "", "exit": 1},
    ] + full_rules(bootstrap, enrolment) + rig.rules
    proc = rig.main("--with-client")
    assert proc.returncode != 0, "a failed enrol was reported as success"
    assert not (rig.state / "client-enrolled").exists()
    assert rig.enrolment_file.read_text().strip() == enrolment
    assert stat.S_IMODE(rig.enrolment_file.stat().st_mode) == 0o600


def test_claude_absent_skips_install_and_names_the_command(rig: Rig) -> None:
    """Ledger 1540: never fail because Claude Code is not there."""
    bootstrap, enrolment = new_secrets()
    rig.rules = [password_stdin_rule()] + full_rules(bootstrap, enrolment) + rig.rules
    proc = rig.main("--with-client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not [c for c in rig.calls("yaadgaar") if c["argv"][:1] in (["install"], ["verify"])]
    assert "yaadgaar install" in proc.stdout


def test_claude_present_runs_install_once_and_a_rerun_writes_nothing(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    (rig.root / "fakebin" / "claude").symlink_to(FAKE)
    rig.rules = [
        password_stdin_rule(),
        # Unregistered on the first check, registered from then on.
        {"cmd": "yaadgaar", "match": ["verify"], "exit": [1, 0]},
    ] + full_rules(bootstrap, enrolment) + rig.rules
    proc = rig.main("--with-client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert [c["argv"] for c in rig.calls("yaadgaar") if c["argv"][:1] == ["install"]] == [["install"]]

    rig.reset_calls()
    again = rig.main("--with-client")
    assert again.returncode == 0, again.stdout + again.stderr
    assert not [c for c in rig.calls("yaadgaar") if c["argv"][:1] == ["install"]], "installed again"


def test_a_failed_agent_install_warns_rather_than_fails(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    (rig.root / "fakebin" / "claude").symlink_to(FAKE)
    rig.rules = [
        password_stdin_rule(),
        # Before the `install` rule: the rig's own path holds the word "install".
        {"cmd": "yaadgaar", "match": ["enrol", "--token-file"], "exit": 0},
        {"cmd": "yaadgaar", "match": ["verify"], "exit": 1},
        {"cmd": "yaadgaar", "match": ["install"], "exit": 1},
    ] + full_rules(bootstrap, enrolment) + rig.rules
    proc = rig.main("--with-client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "WARNING" in proc.stdout


def test_a_stopped_cluster_is_started_not_deleted(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    rig.rules = [
        {"cmd": "kind", "match": ["get", "clusters"], "stdout": "yadgar\n"},
        {"cmd": "kubectl", "match": ["get", "--raw", "/readyz"], "stdout": "", "exit": 1},
    ] + full_rules(bootstrap, enrolment) + rig.rules
    proc = rig.main()
    assert proc.returncode != 0
    assert "podman start yadgar-control-plane" in proc.stderr


def test_changed_argocd_values_are_applied(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    rig.rules = [
        {"cmd": "helm", "match": ["list"],
         "stdout": json.dumps([{"name": "argocd", "status": "deployed", "chart": "argo-cd-8.6.1"}])},
    ] + full_rules(bootstrap, enrolment) + rig.rules
    (rig.state).mkdir(exist_ok=True)
    (rig.state / "argocd-values.sha256").write_text("0" * 64 + "\n")
    proc = rig.main()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert [c for c in rig.calls("helm") if "upgrade" in c["argv"]], "values changed but no upgrade ran"


def test_an_inherited_xtrace_prints_no_secret(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    rig.rules = [
        {"cmd": "yaadgaar", "match": ["enrol", "--help"], "stdout": "  --password-stdin\n"},
    ] + full_rules(bootstrap, enrolment) + rig.rules
    (rig.root / "bash_env").write_text("set -x\n")
    proc = rig.main("--with-client", SHELLOPTS="xtrace", BASH_ENV=str(rig.root / "bash_env"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    password = (rig.state / "client-password").read_text().strip()
    assert_absent(rig, proc, bootstrap, base64.b64encode(bootstrap.encode()).decode(), enrolment, password)


def test_it_runs_from_a_release_tarball_with_no_git(rig: Rig, tmp_path: Path) -> None:
    unpacked = tmp_path / "chart-0.3.9"
    unpacked.mkdir()
    shutil.copytree(REPO / "bootstrap", unpacked / "bootstrap")
    shutil.copytree(REPO / "example", unpacked / "example")
    proc = subprocess.run(
        ["bash", "-c", f'source "{unpacked / "bootstrap" / "kind-up.sh"}"; load_examples; printf "%s" "$GATEWAY_URL"'],
        env=rig.env(), capture_output=True, text=True, cwd="/",
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == GATEWAY
    assert "git " not in SCRIPT.read_text().replace("git clone", "")


def test_with_client_pins_the_client_version(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    (rig.root / "fakebin" / "yaadgaar").unlink()
    (rig.root_home / ".local" / "bin" / "yaadgaar").unlink()
    pipx_bin = rig.root / "pipx-bin"
    pipx_bin.mkdir()
    (pipx_bin / "yaadgaar").symlink_to(FAKE)
    rig.rules = [
        {"cmd": "pipx", "match": ["environment"], "stdout": str(pipx_bin) + "\n"},
        {"cmd": "yaadgaar", "match": ["enrol", "--help"], "stdout": "  --password-stdin\n"},
    ] + full_rules(bootstrap, enrolment) + rig.rules
    proc = rig.main("--with-client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    installs = [c["argv"] for c in rig.calls("pipx") if "install" in c["argv"]]
    assert installs == [["install", f"yaadgaar=={client_version()}"]]
    # The steps for ANOTHER machine name a client new enough for `login --ca-file`
    # and `admin issue-enrolment` (0.1.9, 0.1.10) (ledger 1555); the lock (ledger
    # 1623) is at or above that, so root's own install above has both.
    assert "pipx install 'yaadgaar>=0.1.10'" in proc.stdout


def test_a_changed_application_is_applied_and_the_difference_logged(rig: Rig) -> None:
    rig.rules = [
        {"cmd": "kubectl", "match": [" diff -f "], "exit": 1,
         "stdout": "-      prune: false\n+      prune: true\n"},
        {"cmd": "kubectl", "match": ["get", "application", "operators"],
         "stdout": app_json("operators", "Succeeded", revision="0.1.21", target="0.1.21")},
    ] + rig.rules
    proc = rig.run(f'load_examples; ensure_application 6 "$OPERATORS_APP_FILE" operators 0')
    assert proc.returncode == 0, proc.stderr
    assert [c for c in rig.calls("kubectl") if "apply" in c["argv"]]
    assert "prune: false" in rig.log.read_text(), "the differing field was not logged"


def test_a_diff_that_errors_falls_back_to_apply(rig: Rig) -> None:
    rig.rules = [
        {"cmd": "kubectl", "match": [" diff -f "], "exit": 2, "stderr": "error: something\n"},
        {"cmd": "kubectl", "match": ["get", "application", "operators"],
         "stdout": app_json("operators", "Succeeded", revision="0.1.21", target="0.1.21")},
    ] + rig.rules
    proc = rig.run(f'load_examples; ensure_application 6 "$OPERATORS_APP_FILE" operators 0')
    assert proc.returncode == 0, proc.stderr
    assert [c for c in rig.calls("kubectl") if "apply" in c["argv"]]


def test_a_changed_kubeconfig_is_replaced(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    rig.rules = [
        {"cmd": "kind", "match": ["get", "clusters"], "stdout": "yadgar\n"},
        {"cmd": "kind", "match": ["export", "kubeconfig"], "write_arg": "--kubeconfig",
         "write_content": "apiVersion: v1\nkind: Config\n# new port\n"},
    ] + full_rules(bootstrap, enrolment) + rig.rules
    rig.state.mkdir(exist_ok=True)
    (rig.state / "kubeconfig").write_text("apiVersion: v1\nkind: Config\n")
    proc = rig.run("load_examples; detect_runtime; ensure_cluster")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (rig.state / "kubeconfig").read_text().endswith("# new port\n")
    assert stat.S_IMODE((rig.state / "kubeconfig").stat().st_mode) == 0o600
    assert not (rig.state / "kubeconfig.new").exists()


def test_retries_inside_one_operation_are_logged(rig: Rig) -> None:
    def retrying(n: int, message: str) -> str:
        doc = json.loads(app_json("operators", "Running", health="Progressing", revision="0.1.21", target="0.1.21",
                                  message=message))
        doc["status"]["operationState"]["retryCount"] = n
        return json.dumps(doc)

    done = json.loads(app_json("operators", "Succeeded", revision="0.1.21", target="0.1.21"))
    done["status"]["operationState"]["retryCount"] = 2
    rig.rules = [
        {"cmd": "kubectl", "match": ["get", "application", "operators"], "stdout": [
            retrying(1, "one or more synchronization tasks completed unsuccessfully. Retrying attempt #1 at 10:46PM."),
            retrying(2, "one or more synchronization tasks completed unsuccessfully. Retrying attempt #2 at 10:47PM."),
            json.dumps(done),
        ]},
    ] + rig.rules
    proc = rig.run("load_examples; wait_app operators 60")
    assert proc.returncode == 0, proc.stderr
    assert "retries=1" in proc.stdout and "Retrying attempt #1" in proc.stdout
    assert "retries=2" in proc.stdout and "Retrying attempt #2" in proc.stdout
    assert "Succeeded after 2 retries" in proc.stdout


def test_the_header_says_argo_may_retry_within_the_first_operation() -> None:
    assert "first operation succeeds (Argo may retry within it)" in SCRIPT.read_text()


def test_a_clock_far_behind_the_network_is_warned_about(rig: Rig) -> None:
    rig.rules = [
        # ANSWERS ONLY WITH `-k`. A clock this far off fails certificate
        # validation, so a check that verifies TLS would hear nothing.
        {"cmd": "curl", "match": ["-k", "-I"], "stdout": "HTTP/2 200\r\ndate: Wed, 01 Jan 2031 00:00:00 GMT\r\n\r\n"},
        {"cmd": "curl", "match": ["-I"], "exit": 60, "stderr": "curl: (60) SSL certificate problem\n"},
    ] + rig.rules
    proc = rig.run("check_clock")
    assert proc.returncode == 0, proc.stderr
    assert "clock" in proc.stdout and "behind" in proc.stdout


def test_no_network_answer_says_nothing_about_the_clock(rig: Rig) -> None:
    proc = rig.run("check_clock")
    assert proc.returncode == 0, proc.stderr
    assert "behind" not in proc.stdout


def test_a_clock_in_step_with_the_network_says_nothing(rig: Rig) -> None:
    import email.utils  # noqa: PLC0415

    now = email.utils.formatdate(usegmt=True)
    rig.rules = [{"cmd": "curl", "match": ["-I"], "stdout": f"HTTP/2 200\r\ndate: {now}\r\n\r\n"}] + rig.rules
    proc = rig.run("check_clock")
    assert proc.returncode == 0, proc.stderr
    assert "behind" not in proc.stdout


def test_the_clock_is_checked_before_anything_else_reaches_the_network() -> None:
    body = SCRIPT.read_text().split("main() {", 1)[1]
    assert body.index("  check_clock\n") < body.index("  ensure_packages\n"), "apt fails first on a skewed clock"


def test_no_answer_from_the_clock_host_does_not_stop_the_run(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    rig.rules = [
        {"cmd": "curl", "match": ["-I", "dl.k8s.io"], "exit": 6, "stderr": "curl: (6) Could not resolve host\n"},
    ] + full_rules(bootstrap, enrolment) + rig.rules
    proc = rig.main()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert any("dl.k8s.io" in " ".join(c["argv"]) for c in rig.calls("curl")), "the clock was never checked"


def test_a_failed_replace_stops_the_run(rig: Rig) -> None:
    """replace_if_changed runs in a command substitution, where errexit does not reach."""
    ca = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"
    rig.rules = [
        {"cmd": "kubectl", "match": ["secret", "gateway-tls"], "stdout": base64.b64encode(ca.encode()).decode()},
    ] + rig.rules
    broken = rig.root / "fakebin" / "mv"
    broken.write_text("#!/bin/sh\necho 'mv: cannot move' >&2\nexit 1\n")
    broken.chmod(0o755)
    proc = rig.run("load_examples; ensure_edge_ca; echo REACHED")
    assert proc.returncode != 0, proc.stdout
    assert "REACHED" not in proc.stdout
    assert "written" not in proc.stdout


# ─── --add-user ─────────────────────────────────────────────────────────────────

ADMIN_PROJECT = "yadgar/admin"
DAVE_ID = "yadgar:user:01a14a00-0000-7000-8000-00000000da7e"


def add_user_rig(rig: Rig, create_code: str = "200") -> tuple[str, str]:
    """An install host: the edge CA, and root's enrolled client config holding a bearer."""
    bearer = secrets.token_urlsafe(48)
    _, enrolment = new_secrets()
    ca = rig.root / "etc" / "yadgar" / "edge-ca.crt"
    ca.parent.mkdir(parents=True, exist_ok=True)
    ca.write_text("-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n")
    cfg = rig.client_config
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"gateway": GATEWAY + "/", "token": bearer, "username": "admin"}))
    cfg.chmod(0o600)
    create_body = json.dumps({"user_id": DAVE_ID}) if create_code == "200" else '{"error":"the administrative service is unavailable"}'
    rig.rules = [
        {"cmd": "kubectl", "match": ["secret", "admin-bootstrap-token", "metadata.uid"], "stdout": "uid-1"},
        {"cmd": "curl", "match": ["/admin/create-user"], "stdout": create_code, "o_content": create_body},
        {"cmd": "curl", "match": ["/admin/issue-enrolment"], "stdout": "200",
         "o_content": json.dumps({"token": enrolment, "enrolment_id": "e9"})},
    ] + rig.rules
    return bearer, enrolment


def test_add_user_creates_and_enrols_a_second_user_without_printing_a_secret(rig: Rig) -> None:
    bearer, enrolment = add_user_rig(rig)
    out = rig.root / "home" / "dave.token"
    proc = rig.main("--add-user", "dave@example.com", "--display-name", "Dave", "--out", str(out))
    assert proc.returncode == 0, proc.stdout + proc.stderr

    assert out.read_text().strip() == enrolment
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    urls = [a for c in rig.calls("curl") for a in c["argv"] if a.startswith("https://")]
    assert urls == [f"{GATEWAY}/admin/create-user", f"{GATEWAY}/admin/issue-enrolment"]
    curls = rig.calls("curl")
    assert json.loads(curls[0]["data"]) == {"external_id": "dave@example.com", "display_name": "Dave", "is_admin": False}
    assert json.loads(curls[1]["data"]) == {"user_id": DAVE_ID}
    for c in curls:
        # POSITIVE CONTROL: the admin's bearer reached the gateway, on curl's stdin.
        assert f"authorization: Bearer {bearer}" in (c["stdin"] or "")
        assert f"x-yadgar-project: {ADMIN_PROJECT}" in c["argv"]
        assert "--cacert" in c["argv"]
    assert_absent(rig, proc, bearer, enrolment)
    # The user-side commands, at the locked client version.
    assert f"pipx install yaadgaar=={client_version()}" in proc.stdout
    assert "yaadgaar enrol --token-file" in proc.stdout
    assert ".yadgar/project-id" in proc.stdout
    # It is a helper, not an install: no cluster, Argo or host step ran.
    assert not rig.calls("helm") and not rig.calls("kind") and not rig.calls("sysctl")


def test_add_user_again_never_resends_create_user(rig: Rig) -> None:
    bearer, enrolment = add_user_rig(rig)
    out = rig.root / "home" / "dave.token"
    assert rig.main("--add-user", "dave@example.com", "--out", str(out)).returncode == 0

    # A fresh token: nothing is sent at all.
    rig.reset_calls()
    again = rig.main("--add-user", "dave@example.com", "--out", str(out))
    assert again.returncode == 0, again.stdout + again.stderr
    assert rig.calls("curl") == []
    assert "yaadgaar enrol --token-file" in again.stdout

    # Token gone: refused. Never a second create-user, and never an enrolment for
    # a user_id read from the record rather than from this run's create-user.
    out.unlink()
    rig.reset_calls()
    third = rig.main("--add-user", "dave@example.com", "--out", str(out))
    assert third.returncode != 0
    assert "already added" in third.stderr and "resets their password" in third.stderr
    assert rig.calls("curl") == []
    assert not out.exists()
    assert_absent(rig, third, bearer, enrolment)


def test_add_user_names_the_opaque_503_of_a_duplicate(rig: Rig) -> None:
    bearer, _ = add_user_rig(rig, create_code="503")
    proc = rig.main("--add-user", "dave@example.com")
    assert proc.returncode != 0
    assert "ADR-0927" in proc.stderr and "already exists" in proc.stderr
    assert not [c for c in rig.calls("curl") if any("/admin/issue-enrolment" in a for a in c["argv"])]
    assert not (rig.state / "users").exists() or not list((rig.state / "users").iterdir())
    assert_absent(rig, proc, bearer)


def test_add_user_default_out_is_a_root_only_file_beside_the_admin_token(rig: Rig) -> None:
    _, enrolment = add_user_rig(rig)
    proc = rig.main("--add-user", "dave@example.com")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = rig.enrolment_file.parent / "yadgar-enrolment-dave@example.com.token"
    assert out.read_text().strip() == enrolment
    assert stat.S_IMODE(out.stat().st_mode) == 0o600


def test_add_user_needs_an_enrolled_admin_client(rig: Rig) -> None:
    add_user_rig(rig)
    rig.client_config.unlink()
    proc = rig.main("--add-user", "dave@example.com")
    assert proc.returncode != 0
    assert "--with-client" in proc.stderr
    assert rig.calls("curl") == []


@pytest.mark.parametrize(
    "args",
    [
        ("--add-user", "a/b"),
        ("--add-user",),
        ("--add-user", "dave", "--with-client"),
        ("--display-name", "Dave"),
        ("--out", "/tmp/x"),
        ("--force",),
        ("--add-user", "dave", "--display-name", "Dave\nEvil"),
        ("--add-user", "dave\tx"),
    ],
)
def test_add_user_refuses_bad_arguments(rig: Rig, args: tuple[str, ...]) -> None:
    add_user_rig(rig)
    proc = rig.main(*args)
    assert proc.returncode != 0
    assert rig.calls("curl") == []


def test_add_user_never_reads_the_bootstrap_token_and_creates_no_admin(rig: Rig) -> None:
    """Its only authority is root's client credential; the bootstrap token is the
    first admin's alone (ADR-0655)."""
    add_user_rig(rig)
    proc = rig.main("--add-user", "dave@example.com")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not [c for c in rig.calls("kubectl") if any(".data.token" in a for a in c["argv"])]
    for c in rig.calls("curl"):
        assert "x-yadgar-bootstrap-token" not in (c["stdin"] or "")
        assert not any("set-user-admin" in a for a in c["argv"])
        if c["data"] and "external_id" in c["data"]:
            assert json.loads(c["data"])["is_admin"] is False


def test_add_user_ignores_a_home_or_xdg_config_and_reads_only_roots(rig: Rig) -> None:
    """`sudo -E` keeps the caller's HOME: their credential must never be used."""
    add_user_rig(rig)
    for base in (rig.root / "home" / ".config", rig.root / "xdg"):
        (base / "yadgar").mkdir(parents=True, exist_ok=True)
        (base / "yadgar" / "config.json").write_text(rig.client_config.read_text())
        (base / "yadgar" / "config.json").chmod(0o600)
    (rig.root / "xdg" / "yaadgaar").mkdir()
    (rig.root / "xdg" / "yaadgaar" / "config.json").write_text(rig.client_config.read_text())
    (rig.root / "xdg" / "yaadgaar" / "config.json").chmod(0o600)
    proc = rig.main("--add-user", "dave@example.com", YADGAR_CLIENT_CONFIG="",
                    XDG_CONFIG_HOME=str(rig.root / "xdg"), YADGAR_CONFIG_DIR=str(rig.root / "xdg" / "yadgar"),
                    YAADGAAR_CONFIG_DIR=str(rig.root / "xdg" / "yaadgaar"))
    assert proc.returncode != 0
    assert f"{rig.root_home}/.config/yaadgaar/config.json" in proc.stderr
    assert rig.calls("curl") == []


def root_config(rig: Rig, leaf: str, gateway: str = GATEWAY + "/") -> Path:
    """A client config in root's own home, under ~/.config/<leaf>."""
    cfg = rig.root_home / ".config" / leaf / "config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({"gateway": gateway, "token": secrets.token_urlsafe(48)}))
    cfg.chmod(0o600)
    return cfg


def test_add_user_reads_roots_yaadgaar_config_by_default(rig: Rig) -> None:
    """yaadgaar 0.1.5 and later keep their config in ~/.config/yaadgaar."""
    add_user_rig(rig)
    root_config(rig, "yaadgaar")
    proc = rig.main("--add-user", "dave@example.com", YADGAR_CLIENT_CONFIG="")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "older yaadgaar" not in proc.stderr
    assert len(rig.calls("curl")) == 2


def test_add_user_falls_back_to_the_old_config_read_only_with_one_note(rig: Rig) -> None:
    """A host enrolled by kind-up v0.24.20 or older holds root's credential where
    yaadgaar 0.1.3 put it. It is read where it is; nothing is moved or created."""
    add_user_rig(rig)
    old = root_config(rig, "yadgar")
    before = old.read_bytes()
    proc = rig.main("--add-user", "dave@example.com", YADGAR_CLIENT_CONFIG="")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stderr.count("older yaadgaar") == 1, proc.stderr
    assert str(old) in proc.stderr
    assert len(rig.calls("curl")) == 2
    assert old.read_bytes() == before
    assert stat.S_IMODE(old.stat().st_mode) == 0o600
    assert not (rig.root_home / ".config" / "yaadgaar").exists()


def test_the_new_config_wins_when_both_exist(rig: Rig) -> None:
    add_user_rig(rig)
    root_config(rig, "yaadgaar")
    root_config(rig, "yadgar", gateway="https://elsewhere.example:443/")
    proc = rig.main("--add-user", "dave@example.com", YADGAR_CLIENT_CONFIG="")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "older yaadgaar" not in proc.stderr


def test_a_symlink_at_the_new_config_is_refused_not_bypassed(rig: Rig) -> None:
    add_user_rig(rig)
    root_config(rig, "yadgar")
    new = rig.root_home / ".config" / "yaadgaar" / "config.json"
    new.parent.mkdir(parents=True)
    new.symlink_to(rig.root / "nowhere.json")
    proc = rig.main("--add-user", "dave@example.com", YADGAR_CLIENT_CONFIG="")
    assert proc.returncode != 0
    assert str(new) in proc.stderr
    assert rig.calls("curl") == []


def test_the_old_config_passes_the_same_owner_and_mode_check(rig: Rig) -> None:
    add_user_rig(rig)
    old = root_config(rig, "yadgar")
    old.chmod(0o644)
    proc = rig.main("--add-user", "dave@example.com", YADGAR_CLIENT_CONFIG="")
    assert proc.returncode != 0
    # The reader's own refusal, naming the old file: not the generic die text.
    assert f"{old} is owner/mode" in proc.stderr and " 644, not " in proc.stderr, proc.stderr
    assert rig.calls("curl") == []


def test_a_symlink_at_the_old_config_is_refused_not_followed(rig: Rig) -> None:
    add_user_rig(rig)
    real = root_config(rig, "elsewhere")
    old = rig.root_home / ".config" / "yadgar" / "config.json"
    old.parent.mkdir(parents=True)
    old.symlink_to(real)
    proc = rig.main("--add-user", "dave@example.com", YADGAR_CLIENT_CONFIG="")
    assert proc.returncode != 0
    assert f"no readable client credential at {old}" in proc.stderr, proc.stderr
    assert rig.calls("curl") == []


def test_an_explicit_client_config_never_falls_back(rig: Rig) -> None:
    add_user_rig(rig)
    root_config(rig, "yadgar")
    rig.client_config.unlink()
    proc = rig.main("--add-user", "dave@example.com")
    assert proc.returncode != 0
    assert str(rig.client_config) in proc.stderr
    assert "older yaadgaar" not in proc.stderr
    assert rig.calls("curl") == []


def enrolled_with_client(rig: Rig, version: str) -> None:
    """A host --with-client already enrolled, its root client answering *version*."""
    (rig.state / "client-enrolled").touch()
    rig.rules = [{"cmd": "yaadgaar", "match": ["--version"], "stdout": f"yaadgaar {version}\n"}] + rig.rules


def test_an_enrolled_client_with_its_credential_at_the_new_path_is_upgraded(rig: Rig) -> None:
    """Ledger 1554: root's client follows tools.lock. Safe only where the new
    client finds its credential: ~/.config/yaadgaar, which 0.1.5 and later read."""
    enrolled_with_client(rig, "0.1.5")
    cfg = root_config(rig, "yaadgaar")
    before = cfg.read_bytes()
    proc = rig.run("pin_root_environment; ensure_client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    pipx = [c["argv"] for c in rig.calls("pipx")]
    # THE PRE-FLIGHT FIRST: pipx 1.8.0 deletes the venv when a forced install
    # fails, so the wheel is fetched before the working client is touched.
    assert pipx[0][:4] == ["runpip", "yaadgaar", "download", "--no-deps"], pipx
    assert f"yaadgaar=={client_version()}" in pipx[0] and "--only-binary=:all:" in pipx[0]
    installs = [a for a in pipx if "install" in a]
    assert installs == [["install", "--force", f"yaadgaar=={client_version()}"]]
    assert not [c for c in rig.calls("yaadgaar") if c["argv"][:1] in (["login"], ["enrol"])]
    assert f"upgraded root's client 0.1.5\u2192{client_version()}; credential stays at {cfg}" in proc.stdout
    assert cfg.read_bytes() == before


def test_a_host_on_the_previous_pin_0_1_6_is_upgraded_to_the_lock(rig: Rig) -> None:
    """Ledger 1623: the first bump past a pin a host already runs. 0.1.6 → 0.1.12
    is a numeric comparison (0.1.12 sorts before 0.1.6 as text) and the credential
    in ~/.config/yaadgaar stays where it is."""
    enrolled_with_client(rig, "0.1.6")
    cfg = root_config(rig, "yaadgaar")
    before = cfg.read_bytes()
    proc = rig.run("pin_root_environment; ensure_client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    installs = [c["argv"] for c in rig.calls("pipx") if "install" in c["argv"]]
    assert installs == [["install", "--force", f"yaadgaar=={client_version()}"]]
    assert f"upgraded root's client 0.1.6\u2192{client_version()}; credential stays at {cfg}" in proc.stdout
    assert cfg.read_bytes() == before


def test_a_failed_pre_flight_keeps_the_client_and_never_forces(rig: Rig) -> None:
    enrolled_with_client(rig, "0.1.5")
    root_config(rig, "yaadgaar")
    rig.rules = [{"cmd": "pipx", "match": ["runpip", "download"], "exit": 1}] + rig.rules
    proc = rig.run("pin_root_environment; ensure_client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not [c for c in rig.calls("pipx") if "--force" in c["argv"]], "forced an install it could not fetch"
    assert "WARNING" in proc.stdout and "0.1.5 kept" in proc.stdout


def test_a_failed_forced_install_after_a_good_pre_flight_stops_the_run(rig: Rig) -> None:
    """pipx removes the old venv when a forced install fails: root has no client
    now, so the run stops and names the command that puts one back."""
    enrolled_with_client(rig, "0.1.5")
    root_config(rig, "yaadgaar")
    rig.rules = [{"cmd": "pipx", "match": ["install", "--force"], "exit": 1}] + rig.rules
    proc = rig.run("pin_root_environment; ensure_client")
    assert proc.returncode != 0, "a failed forced install was reported as success"
    assert f"pipx install --force yaadgaar=={client_version()}" in proc.stderr
    assert "upgraded" not in proc.stdout


def test_an_enrolled_client_newer_than_the_pin_is_kept(rig: Rig) -> None:
    enrolled_with_client(rig, "0.2.0")
    root_config(rig, "yaadgaar")
    proc = rig.run("pin_root_environment; ensure_client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert rig.calls("pipx") == [], "downgraded root's client"
    assert "yaadgaar 0.2.0, newer than the pinned" in proc.stdout


def test_a_pre_release_of_the_pin_is_older_than_the_pin() -> None:
    proc = subprocess.run(
        ["bash", "-c", f'source "{SCRIPT}"; '
         'for p in "0.1.6a1 0.1.6" "0.1.0a8 0.1.2" "0.1.5 0.1.6" "0.1.6 0.1.6" "0.1.7 0.1.6" "0.1.6 0.1.6rc1" "0.1.6 0.1.12" "0.1.9 0.1.12" "0.1.10 0.1.12" "0.1.12 0.1.6"; do '
         'set -- $p; if version_older "$1" "$2"; then echo "$1<$2"; else echo "$1>=$2"; fi; done'],
        capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split() == ["0.1.6a1<0.1.6", "0.1.0a8<0.1.2", "0.1.5<0.1.6",
                                   "0.1.6>=0.1.6", "0.1.7>=0.1.6", "0.1.6>=0.1.6rc1",
                                   "0.1.6<0.1.12", "0.1.9<0.1.12", "0.1.10<0.1.12", "0.1.12>=0.1.6"]


def test_a_symlink_at_the_new_config_keeps_the_client(rig: Rig) -> None:
    enrolled_with_client(rig, "0.1.5")
    real = root_config(rig, "elsewhere")
    link = rig.root_home / ".config" / "yaadgaar" / "config.json"
    link.parent.mkdir(parents=True)
    link.symlink_to(real)
    proc = rig.run("pin_root_environment; ensure_client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert rig.calls("pipx") == []
    assert "0.1.5, not the pinned" in proc.stdout and "kept" in proc.stdout


def test_a_client_that_reports_no_version_is_kept(rig: Rig) -> None:
    (rig.state / "client-enrolled").touch()
    root_config(rig, "yaadgaar")
    rig.rules = [{"cmd": "yaadgaar", "match": ["--version"], "stdout": "", "exit": 1}] + rig.rules
    proc = rig.run("pin_root_environment; ensure_client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert rig.calls("pipx") == []
    assert "did not report its version; kept" in proc.stdout


def new_config_path(rig: Rig) -> Path:
    return rig.root_home / ".config" / "yaadgaar" / "config.json"


def test_an_old_path_credential_is_copied_to_the_new_path_then_the_client_is_upgraded(rig: Rig) -> None:
    """Ledger 1573 (ruled by Max, 2026-10-18): a host enrolled by yaadgaar 0.1.3
    holds root's credential in ~/.config/yadgar. kind-up COPIES it to
    ~/.config/yaadgaar, where 0.1.5 and later read it, then upgrades the client.
    The old file stays: that directory also holds the memory engine's secrets."""
    enrolled_with_client(rig, "0.1.3")
    old = root_config(rig, "yadgar")
    before = old.read_bytes()
    token = json.loads(before)["token"]
    proc = rig.run("pin_root_environment; ensure_client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    new = new_config_path(rig)
    assert new.read_bytes() == before
    assert stat.S_IMODE(new.stat().st_mode) == 0o600
    assert stat.S_IMODE(new.parent.stat().st_mode) == 0o700
    assert old.read_bytes() == before and stat.S_IMODE(old.stat().st_mode) == 0o600
    installs = [c["argv"] for c in rig.calls("pipx") if "install" in c["argv"]]
    assert installs == [["install", "--force", f"yaadgaar=={client_version()}"]]
    assert not [c for c in rig.calls("yaadgaar") if c["argv"][:1] in (["login"], ["enrol"])]
    assert f"copied root's client config {old} to {new}" in proc.stdout
    assert token not in proc.stdout + proc.stderr, "printed the credential"


def test_a_second_run_after_the_copy_leaves_both_configs_alone(rig: Rig) -> None:
    enrolled_with_client(rig, "0.1.3")
    old = root_config(rig, "yadgar")
    assert rig.run("pin_root_environment; ensure_client").returncode == 0
    new = new_config_path(rig)
    new_before, old_before = new.read_bytes(), old.read_bytes()
    enrolled_with_client(rig, client_version())
    proc = rig.run("pin_root_environment; ensure_client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "copied" not in proc.stdout
    assert new.read_bytes() == new_before and old.read_bytes() == old_before


def test_an_existing_new_path_config_is_never_overwritten(rig: Rig) -> None:
    enrolled_with_client(rig, "0.1.5")
    old = root_config(rig, "yadgar", gateway="https://elsewhere.example:443/")
    new = root_config(rig, "yaadgaar")
    new_before, old_before = new.read_bytes(), old.read_bytes()
    proc = rig.run("pin_root_environment; ensure_client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert new.read_bytes() == new_before
    assert old.read_bytes() == old_before
    assert "copied" not in proc.stdout
    assert [c["argv"] for c in rig.calls("pipx") if "install" in c["argv"]] == [
        ["install", "--force", f"yaadgaar=={client_version()}"]]


def test_with_neither_config_nothing_is_created_and_the_client_is_kept(rig: Rig) -> None:
    enrolled_with_client(rig, "0.1.3")
    proc = rig.run("pin_root_environment; ensure_client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert rig.calls("pipx") == [], "replaced a client that has no credential anywhere"
    assert not (rig.root_home / ".config" / "yaadgaar").exists()
    assert not (rig.root_home / ".config" / "yadgar").exists()
    assert f"yaadgaar 0.1.3, not the pinned {client_version()}; kept" in proc.stdout


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o400, 0o666])
def test_an_old_config_that_is_not_mode_0600_is_not_copied(rig: Rig, mode: int) -> None:
    """Permissions are preserved, not widened or guessed: a file the reader would
    refuse is not copied, and the client stays."""
    enrolled_with_client(rig, "0.1.3")
    old = root_config(rig, "yadgar")
    old.chmod(mode)
    proc = rig.run("pin_root_environment; ensure_client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not (rig.root_home / ".config" / "yaadgaar").exists()
    assert not [c for c in rig.calls("pipx") if "install" in c["argv"]]
    assert "kept" in proc.stdout and "not copied" in proc.stdout
    assert stat.S_IMODE(old.stat().st_mode) == mode


def test_a_symlinked_old_config_is_not_copied(rig: Rig) -> None:
    enrolled_with_client(rig, "0.1.3")
    real = root_config(rig, "elsewhere")
    old = rig.root_home / ".config" / "yadgar" / "config.json"
    old.parent.mkdir(parents=True)
    old.symlink_to(real)
    proc = rig.run("pin_root_environment; ensure_client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not (rig.root_home / ".config" / "yaadgaar").exists()
    assert not [c for c in rig.calls("pipx") if "install" in c["argv"]]
    assert "not copied" in proc.stdout


def test_a_symlinked_new_directory_is_not_written_through(rig: Rig) -> None:
    enrolled_with_client(rig, "0.1.3")
    root_config(rig, "yadgar")
    target = rig.root / "attacker-dir"
    target.mkdir()
    (rig.root_home / ".config" / "yaadgaar").symlink_to(target)
    proc = rig.run("pin_root_environment; ensure_client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert list(target.iterdir()) == [], "wrote through a symlinked directory"
    assert not [c for c in rig.calls("pipx") if "install" in c["argv"]]
    assert "not copied" in proc.stdout


def test_a_failed_pre_flight_copies_nothing(rig: Rig) -> None:
    """The copy waits for a good pre-flight: a client that is kept gets no second
    copy of the secret."""
    enrolled_with_client(rig, "0.1.3")
    root_config(rig, "yadgar")
    rig.rules = [{"cmd": "pipx", "match": ["runpip", "download"], "exit": 1}] + rig.rules
    proc = rig.run("pin_root_environment; ensure_client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not (rig.root_home / ".config" / "yaadgaar").exists()
    assert "WARNING" in proc.stdout


def test_the_copy_runs_inside_the_re_exec_allowlist(rig: Rig) -> None:
    """chart#52: the copy reads no environment. A caller's HOME, XDG_CONFIG_HOME and
    YAADGAAR_CONFIG_DIR change neither its source nor its destination."""
    enrolled_with_client(rig, "0.1.3")
    old = root_config(rig, "yadgar")
    decoy = rig.root / "decoy"
    decoy.mkdir()
    proc = rig.run("pin_root_environment; ensure_client", HOME=str(decoy), XDG_CONFIG_HOME=str(decoy),
                   YAADGAAR_CONFIG_DIR=str(decoy), YADGAR_CONFIG_DIR=str(decoy))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert new_config_path(rig).read_bytes() == old.read_bytes()
    assert list(decoy.iterdir()) == []


def test_an_enrolled_client_at_the_pin_is_left_alone(rig: Rig) -> None:
    enrolled_with_client(rig, client_version())
    root_config(rig, "yaadgaar")
    proc = rig.run("pin_root_environment; ensure_client")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert rig.calls("pipx") == []
    assert "not the pinned" not in proc.stdout and "upgraded" not in proc.stdout


def test_add_user_refuses_a_credential_that_is_not_private(rig: Rig) -> None:
    add_user_rig(rig)
    rig.client_config.chmod(0o644)
    proc = rig.main("--add-user", "dave@example.com")
    assert proc.returncode != 0
    assert "600" in proc.stderr
    assert rig.calls("curl") == []


def test_add_user_refuses_a_symlinked_credential(rig: Rig) -> None:
    add_user_rig(rig)
    real = rig.client_config.with_name("real.json")
    rig.client_config.rename(real)
    rig.client_config.symlink_to(real)
    proc = rig.main("--add-user", "dave@example.com")
    assert proc.returncode != 0
    assert rig.calls("curl") == []


def test_add_user_refuses_a_client_enrolled_with_another_gateway(rig: Rig) -> None:
    add_user_rig(rig)
    cfg = json.loads(rig.client_config.read_text())
    cfg["gateway"] = "https://elsewhere.example:443/"
    rig.client_config.write_text(json.dumps(cfg))
    proc = rig.main("--add-user", "dave@example.com")
    assert proc.returncode != 0
    assert "elsewhere.example" in proc.stderr
    assert rig.calls("curl") == []


def test_add_user_never_overwrites_an_existing_file_without_force(rig: Rig) -> None:
    _, enrolment = add_user_rig(rig)
    out = rig.root / "home" / "precious"
    out.write_text("keep me\n")
    proc = rig.main("--add-user", "dave@example.com", "--out", str(out))
    assert proc.returncode != 0
    assert "--force" in proc.stderr
    assert out.read_text() == "keep me\n"
    assert rig.calls("curl") == [], "a user was created whose token had nowhere to go"

    # Nor through a symlink.
    target = rig.root / "home" / "target"
    link = rig.root / "home" / "link"
    link.symlink_to(target)
    proc = rig.main("--add-user", "dave@example.com", "--out", str(link))
    assert proc.returncode != 0 and not target.exists()

    forced = rig.main("--add-user", "dave@example.com", "--out", str(out), "--force")
    assert forced.returncode == 0, forced.stdout + forced.stderr
    assert out.read_text().strip() == enrolment
    assert stat.S_IMODE(out.stat().st_mode) == 0o600


def test_add_user_refuses_a_create_user_answer_without_a_user_id(rig: Rig) -> None:
    add_user_rig(rig)
    rig.rules = [{"cmd": "curl", "match": ["/admin/create-user"], "stdout": "200", "o_content": "{}"}] + rig.rules
    proc = rig.main("--add-user", "dave@example.com")
    assert proc.returncode != 0
    assert "user_id" in proc.stderr
    assert not [c for c in rig.calls("curl") if any("/admin/issue-enrolment" in a for a in c["argv"])]



# ─── review of #47 @c54f46d ─────────────────────────────────────────────────────


def test_the_root_side_client_never_follows_the_callers_environment(rig: Rig) -> None:
    """`sudo -E` keeps the caller's HOME and XDG dirs: enrol, verify, install and
    pipx must still run root's own client, writing under root's home only."""
    bootstrap, enrolment = new_secrets()
    (rig.root / "fakebin" / "claude").symlink_to(FAKE)
    rig.rules = [password_stdin_rule(), {"cmd": "yaadgaar", "match": ["verify"], "exit": 1}] + \
        full_rules(bootstrap, enrolment) + rig.rules
    caller = rig.root / "caller"
    # A decoy yaadgaar where a caller-chosen home would put it.
    (caller / "bin").mkdir(parents=True)
    (caller / "bin" / "yaadgaar").symlink_to(FAKE)
    (caller / ".local" / "bin").mkdir(parents=True)
    (caller / ".local" / "bin" / "yaadgaar").symlink_to(FAKE)
    redirects = {k: str(caller / k.lower()) for k in (
        "CURL_HOME", "KUBECTL_EXTERNAL_DIFF", "HELM_CACHE_HOME", "HELM_CONFIG_HOME", "HELM_DATA_HOME",
        "HELM_PLUGINS", "HELM_REGISTRY_CONFIG", "HELM_REPOSITORY_CONFIG")}
    proc = rig.main("--with-client", HOME=str(caller), XDG_CONFIG_HOME=str(caller / "xdg"),
                    XDG_DATA_HOME=str(caller / "data"), YADGAR_CONFIG_DIR=str(caller / "cfg"),
                    YAADGAAR_CONFIG_DIR=str(caller / "ycfg"),
                    PIPX_HOME=str(caller / "pipx"), PIPX_BIN_DIR=str(caller / "bin"),
                    YADGAR_ROOT_HOME=str(caller), **redirects)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    # curl, kubectl and helm see none of the caller's redirects, and every curl
    # starts with `-q`, the only way to stop it reading a .curlrc.
    for c in rig.calls("curl") + rig.calls("kubectl") + rig.calls("helm"):
        for k in redirects:
            assert c["env"][k] is None, (k, c)
    assert rig.calls("curl") and all(c["argv"][0] == "-q" for c in rig.calls("curl"))
    runs = rig.calls("yaadgaar")
    assert {tuple(c["argv"][:1]) for c in runs} >= {("enrol",), ("verify",), ("install",)}
    root_bin = str(rig.root_home / ".local" / "bin" / "yaadgaar")
    for c in runs + rig.calls("pipx"):
        if c["cmd"] == "yaadgaar":
            assert c["path"] == root_bin, f"ran {c['path']}, not root's own yaadgaar"
        assert c["env"]["HOME"] == str(rig.root_home), c
        assert c["env"]["XDG_CONFIG_HOME"] is None and c["env"]["XDG_DATA_HOME"] is None, c
        assert c["env"]["YADGAR_CONFIG_DIR"] is None, c
        assert c["env"]["YAADGAAR_CONFIG_DIR"] is None, c
        assert c["env"]["PIPX_HOME"] == str(rig.root_home / ".local" / "share" / "pipx"), c
        assert c["env"]["PIPX_BIN_DIR"] == str(rig.root_home / ".local" / "bin"), c


def test_a_failed_enrol_with_a_credential_already_stored_names_the_recovery(rig: Rig) -> None:
    """The crash window between a successful enrol and the marker: the next run's
    enrol is refused (the token is spent), and the message says how to record it."""
    bootstrap, enrolment = new_secrets()
    cfg = rig.client_config
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"gateway": GATEWAY + "/", "token": "x"}))
    cfg.chmod(0o600)
    rig.rules = [
        password_stdin_rule(),
        {"cmd": "yaadgaar", "match": ["enrol", "--token-file"], "exit": 1,
         "stderr": "Error: that enrolment secret was refused; it may already have been used\n"},
    ] + full_rules(bootstrap, enrolment) + rig.rules
    proc = rig.main("--with-client")
    assert proc.returncode != 0
    assert f"touch {rig.state / 'client-enrolled'}" in proc.stderr
    assert not (rig.state / "client-enrolled").exists()


def make_fifo_link(rig: Rig) -> tuple[Path, Path]:
    fifo = rig.root / "home" / "fifo"
    os.mkfifo(fifo)
    link = rig.root / "home" / "out.token"
    link.symlink_to(fifo)
    return fifo, link


@pytest.mark.parametrize("force", [False, True])
def test_add_user_never_writes_through_a_symlink_to_a_fifo(rig: Rig, force: bool) -> None:
    """bash 5.3's `set -C` writes through a symlink to a FIFO or device."""
    bearer, enrolment = add_user_rig(rig)
    fifo, link = make_fifo_link(rig)
    args = ["--add-user", "dave@example.com", "--out", str(link)] + (["--force"] if force else [])
    proc = rig.main(*args)
    assert proc.returncode != 0
    assert link.is_symlink() and os.readlink(link) == str(fifo)
    assert rig.calls("curl") == [], "a user was created whose token had nowhere safe to go"
    assert_absent(rig, proc, bearer, enrolment)


def test_add_user_refuses_a_parent_others_can_write(rig: Rig) -> None:
    add_user_rig(rig)
    shared = rig.root / "shared"
    shared.mkdir()
    shared.chmod(0o777)
    proc = rig.main("--add-user", "dave@example.com", "--out", str(shared / "dave.token"))
    assert proc.returncode != 0
    assert "777" in proc.stderr
    assert not (shared / "dave.token").exists()
    assert rig.calls("curl") == []


def test_add_user_refuses_a_parent_owned_by_another_uid(rig: Rig) -> None:
    add_user_rig(rig)
    other = Path("/")
    assert other.stat().st_uid != os.geteuid(), "run as a uid that does not own /"
    proc = rig.main("--add-user", "dave@example.com", "--out", str(other / "yadgar-dave.token"))
    assert proc.returncode != 0
    assert f"uid {other.stat().st_uid}" in proc.stderr
    assert rig.calls("curl") == []


def test_add_user_refuses_a_missing_parent(rig: Rig) -> None:
    add_user_rig(rig)
    proc = rig.main("--add-user", "dave@example.com", "--out", str(rig.root / "nope" / "dave.token"))
    assert proc.returncode != 0
    assert not (rig.root / "nope").exists()
    assert rig.calls("curl") == []


@pytest.mark.parametrize("name", ["a+b", "a b", "dave/x", "da%ve", "é"])
def test_add_user_refuses_a_username_its_record_key_would_change(rig: Rig, name: str) -> None:
    """`a+b` and `a_b` once shared one record and one token file."""
    add_user_rig(rig)
    proc = rig.main("--add-user", name)
    assert proc.returncode != 0
    assert rig.calls("curl") == []


def test_add_user_refuses_a_record_for_another_username(rig: Rig) -> None:
    add_user_rig(rig)
    users = rig.state / "users"
    users.mkdir(parents=True)
    (users / "dave@example.com.json").write_text(json.dumps(
        {"external_id": "someone-else", "user_id": DAVE_ID, "install_uid": "uid-1"}))
    proc = rig.main("--add-user", "dave@example.com")
    assert proc.returncode != 0
    assert "someone-else" in proc.stderr
    assert rig.calls("curl") == []


def test_add_user_strips_control_characters_from_the_gateways_answer(rig: Rig) -> None:
    add_user_rig(rig)
    rig.rules = [{"cmd": "curl", "match": ["/admin/create-user"], "stdout": "500",
                  "o_content": json.dumps({"error": "bad\u001b[31m red\nforged line"})}] + rig.rules
    proc = rig.main("--add-user", "dave@example.com")
    assert proc.returncode != 0
    assert "\x1b" not in proc.stderr and "bad" in proc.stderr
    assert "\nforged line" not in proc.stderr



# ─── re-review of #47 @f46d5aa ──────────────────────────────────────────────────


def test_a_callers_curlrc_is_never_read(rig: Rig) -> None:
    """curl reads $CURL_HOME/.curlrc unless `-q` is its FIRST argument. Run with the
    real curl: the .curlrc asks for a trace, and no trace may appear."""
    real = shutil.which("curl")
    assert real, "curl is not installed"
    (rig.root / "fakebin" / "curl").unlink()
    (rig.root / "fakebin" / "curl").symlink_to(real)
    caller = rig.root / "caller"
    caller.mkdir()
    trace = rig.root / "trace.txt"
    (caller / ".curlrc").write_text(f'trace = "{trace}"\n')
    (rig.root / "body").write_text("{}")
    snippet = (f'pin_root_environment; CA_FILE=/dev/null; GATEWAY_URL=https://127.0.0.1:9; '
               f'gateway_post x "{rig.root / "body"}" "{rig.root / "out"}" "h: v" >/dev/null')
    proc = rig.run(snippet, CURL_HOME=str(caller))
    assert proc.returncode == 0, proc.stderr
    assert not trace.exists(), "curl read the caller's .curlrc"
    # POSITIVE CONTROL: the same curl, without -q and with CURL_HOME kept, does write it.
    subprocess.run([real, "-sS", "-o", "/dev/null", "--max-time", "2", "https://127.0.0.1:9/"],
                   env={"CURL_HOME": str(caller), "PATH": os.environ["PATH"]}, capture_output=True)
    assert trace.exists(), "the control did not produce a trace, so the test proves nothing"


def test_add_user_never_follows_a_symlink_in_the_parent_path(rig: Rig) -> None:
    """realpath + O_NOFOLLOW guarded only the last component: `<dir>/lnk/new`
    wrote through `lnk`."""
    add_user_rig(rig)
    real = rig.root / "realdir"
    real.mkdir()
    (rig.root / "lnk").symlink_to(real)
    proc = rig.main("--add-user", "dave@example.com", "--out", str(rig.root / "lnk" / "dave.token"))
    assert proc.returncode != 0
    assert "symlink" in proc.stderr
    assert list(real.iterdir()) == []
    assert rig.calls("curl") == []


def test_a_late_write_failure_keeps_the_token_and_the_rerun_names_it(rig: Rig) -> None:
    """The user exists once create-user answers; their only token must survive a
    failed write, and a rerun must point at it rather than re-issue."""
    bearer, enrolment = add_user_rig(rig)
    out = rig.root / "home" / "dave.token"
    # Something creates the out file while the requests are in flight.
    rig.rules = [{"cmd": "curl", "match": ["/admin/issue-enrolment"], "stdout": "200",
                  "o_content": json.dumps({"token": enrolment, "enrolment_id": "e9"}),
                  "touch": str(out)}] + rig.rules
    proc = rig.main("--add-user", "dave@example.com", "--out", str(out))
    assert proc.returncode != 0
    pending = rig.state / "users" / "dave@example.com.token.pending"
    assert pending.read_text().strip() == enrolment
    assert stat.S_IMODE(pending.stat().st_mode) == 0o600
    assert str(pending) in proc.stderr
    assert out.read_text() == "", "the racing file was overwritten"
    assert not list(rig.state.glob("tmp.*")), "temporary state left behind"
    assert_absent(rig, proc, bearer, enrolment)

    rig.reset_calls()
    again = rig.main("--add-user", "dave@example.com", "--out", str(out))
    assert again.returncode != 0
    assert str(pending) in again.stderr and "resets their password" in again.stderr
    assert rig.calls("curl") == []


# ─── next steps for another machine (ledger 1555) ──────────────────────────────
#
# A plain `yaadgaar login` fails against the install's private CA: a machine that
# never enrolled has no anchor for the gateway. The client has `login --ca-file`
# (yadgar#61, first in 0.1.9) and `admin issue-enrolment` (yadgar#62, first in
# 0.1.10), and the printed steps must use them.

NEXT_STEPS_STATES = {
    "enrolled here": lambda rig: (rig.state / "client-enrolled").write_text(""),
    "token waiting": lambda rig: rig.enrolment_file.write_text("TOKEN\n"),
    "credential held elsewhere": lambda rig: None,
}


def print_next_steps(rig: Rig, state: str, version: str | None = "0.1.12") -> str:
    """The steps as a rerun prints them: root's environment pinned as `main` does,
    root's installed client answering *version* (None: it prints nothing)."""
    rig.state.mkdir(exist_ok=True)
    NEXT_STEPS_STATES[state](rig)
    if version is not None:
        rig.rules = [{"cmd": "yaadgaar", "match": ["--version"], "stdout": f"yaadgaar {version}\n"}] + rig.rules
    proc = rig.run("pin_root_environment; load_examples; print_next_steps")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout


@pytest.mark.parametrize("state", ["enrolled here", "credential held elsewhere"])
def test_next_steps_for_another_machine_use_the_ca_file_and_issue_enrolment(rig: Rig, state: str) -> None:
    out = print_next_steps(rig, state)
    logins = [line for line in out.splitlines() if "yaadgaar login" in line]
    assert logins, "no login step printed"
    for line in logins:
        assert "--ca-file" in line, f"a login that fails against the private CA: {line.strip()}"
    # Where the operator gets the CA file, and the enrolment route.
    assert "/etc/yadgar/edge-ca.crt" in out
    assert "yaadgaar admin issue-enrolment --user-id" in out
    assert "--revoke-existing" in out
    # The steps name the first client that has both flags.
    assert "yaadgaar>=0.1.10" in out
    # The CA file is world-readable, so no root login is needed to copy it.
    assert "root@" not in out
    # Route B: the ISSUING client must be new enough. Whether root's own is, is
    # read from the installed binary (stubbed 0.1.12 here), never from the lock row,
    # and only where this host's root is enrolled (ledger 1623).
    assert "issuing client must be yaadgaar>=0.1.10" in out
    if state == "enrolled here":
        assert 'root client here is 0.1.12, which has "yaadgaar admin issue-enrolment"' in out
    else:
        assert "root client here" not in out and "root has no client" not in out
    assert "does not work from this host" not in out
    assert "until tools.lock is bumped" not in out
    assert "ledger 1623" not in out
    # Re-issuing the admin's own enrolment makes the stored password stale.
    assert "client-password" in out and "stale" in out
    assert "ends root's credential on this host" in out


def test_next_steps_for_a_waiting_token_still_enrol_without_a_login(rig: Rig) -> None:
    out = print_next_steps(rig, "token waiting")
    assert "yaadgaar enrol --token-file" in out
    assert "yaadgaar login" not in out


# ─── root's environment is scrubbed (ledger 1563) ──────────────────────────────
#
# Run as root, the script's pipx (`pipx install --force`), apt-get and kind would
# otherwise inherit whatever the caller exported: PIP_INDEX_URL, PIPX_DEFAULT_PYTHON,
# APT_CONFIG, DOCKER_HOST and the like, all of which redirect root's installs.

PLANTED = {
    "PIP_INDEX_URL": "https://evil.example/simple",
    "PIPX_DEFAULT_PYTHON": "/tmp/evil-python",
    "PIPX_HOME": "/tmp/evil-pipx",
    "APT_CONFIG": "/tmp/evil-apt.conf",
    "DOCKER_HOST": "tcp://evil.example:2375",
    "CONTAINER_HOST": "tcp://evil.example:2376",
    "KIND_EXPERIMENTAL_PROVIDER": "podman",
    # A forged "already scrubbed" marker, as an older revision used: it must buy nothing.
    "YADGAR_KIND_UP_CLEAN": "1",
    # The test knob that picks which pinned tool binary downloads: dropped for root on purpose.
    "YADGAR_ARCH": "arm64",
}
DOCUMENTED_INPUTS = {
    "YADGAR_ADMIN_EXTERNAL_ID": "boss",
    "YADGAR_ADMIN_DISPLAY_NAME": "TheBoss",
    "YADGAR_RUNTIME": "docker",
    "YADGAR_OPERATORS_TIMEOUT": "11",
    "YADGAR_ESTATE_TIMEOUT": "22",
    "YADGAR_CLIENT_CONFIG": "/root/some/config.json",
    # Downloads are hash-checked against tools.lock and TLS runs end to end, so a
    # proxy is kept, in both cases.
    "http_proxy": "http://proxy.example:3128",
    "https_proxy": "http://proxy.example:3128",
    "no_proxy": "localhost",
    "HTTP_PROXY": "http://proxy.example:3128",
    "HTTPS_PROXY": "http://proxy.example:3128",
    "NO_PROXY": "localhost",
}
SAFE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin"


def rig_path_overrides(rig: Rig) -> set[str]:
    """The rig's own YADGAR_* path overrides: documented, ignored by root, kept so the notice names them."""
    return {name for name in rig.env() if name.startswith("YADGAR_")}


def run_probe(rig: Rig, body: str, *args: str, **extra: str) -> subprocess.CompletedProcess:
    """Run a probe script as root. It re-executes itself clean, then runs `body`."""
    probe = rig.root / "probe.sh"
    probe.write_text(
        # The second pass is told apart by its PATH alone, with nothing forgeable
        # and before the script is sourced: its PATH is the fixed one, which on a
        # non-FHS host (NixOS) holds no `dirname` for SCRIPT_DIR.
        f'if [[ "$PATH" == "{SAFE_PATH}" ]]; then\n{body}\n  exit 0\nfi\n'
        f'source "{SCRIPT}"\n'
        'reexec_with_clean_environment "$0" "$@"\n'
    )
    (rig.root / "fake" / "rules.json").write_text(json.dumps(rig.rules))
    bash = shutil.which("bash")
    assert bash, "bash is not installed"
    env = rig.env(**extra)
    route = root_route()
    argv = [bash, str(probe), *args]
    if route[-1] == "-i":  # sudo resets the environment; env -i restores the rig's (see as_root)
        argv = [*route, *(f"{k}={v}" for k, v in env.items()), *argv]
    else:
        argv = [*route, *argv]
    return subprocess.run(argv, env=env, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=60)


def test_root_reexecs_under_a_scrubbed_environment(rig: Rig) -> None:
    # POSITIVE CONTROL: the planted variables really are in the caller's environment.
    caller = rig.env(**PLANTED, **DOCUMENTED_INPUTS)
    for name in PLANTED:
        assert name in caller

    dump = rig.root / "env.dump"
    proc = run_probe(rig, f'  declare -x > "{dump}"', "--with-client", **PLANTED, **DOCUMENTED_INPUTS)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert dump.exists(), "the re-executed process never ran"
    seen = {}
    for line in dump.read_text().splitlines():
        m = re.match(r'declare -x (\w+)(?:="(.*)")?$', line)
        if m:
            seen[m.group(1)] = m.group(2)
    for name in PLANTED:
        assert name not in seen, f"{name} reached root's children"
    # Nothing but the allowlist and what bash itself sets.
    allowed = {*DOCUMENTED_INPUTS, *rig_path_overrides(rig), "PATH", "HOME", "TERM", "LANG",
               "PWD", "SHLVL", "OLDPWD", "_"}
    for name in seen:
        assert name in allowed, f"{name} leaked into root's environment"
    for name, value in DOCUMENTED_INPUTS.items():
        assert seen.get(name) == value, f"documented input {name} was dropped"
    assert seen["PATH"] == SAFE_PATH
    assert seen["HOME"] == str(rig.root_home)


def test_root_reexec_runs_once_and_keeps_the_arguments(rig: Rig) -> None:
    dump = rig.root / "args.dump"
    body = f'  printf "%s\\n" "$@" > "{dump}"'
    proc = run_probe(rig, body, "--add-user", "a b", "--force")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert dump.read_text().splitlines() == ["--add-user", "a b", "--force"]


def dirty(rig: Rig, safe_path: str | None = None, root_home: str | None = None, **extra: str) -> bool:
    """`root_environment_is_dirty` in an environment of exactly PATH, HOME and `extra`.

    The safe PATH and root's home default to the test's own, so the verdict
    depends only on the variables planted; a run as this user never re-executes.
    """
    path = f"{rig.root / 'fakebin'}:{rig.root / 'hostbin'}"
    env = {"PATH": path, "HOME": str(rig.root_home), **extra}
    safe = safe_path or path
    home = root_home or str(rig.root_home)
    snippet = f"ROOT_SAFE_PATH='{safe}'; root_home() {{ echo '{home}'; }}; root_environment_is_dirty"
    proc = subprocess.run(["bash", "-c", f'source "{SCRIPT}"; {snippet}'], env=env,
                          capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    assert proc.returncode in (0, 1), proc.stderr
    return proc.returncode == 0


def test_the_environment_is_clean_only_when_it_is_exactly_the_allowlist(rig: Rig) -> None:
    assert not dirty(rig), "a bare PATH and HOME were called dirty: the second pass would loop"
    assert not dirty(rig, TERM="xterm", LANG="C.UTF-8", YADGAR_RUNTIME="docker", https_proxy="http://p")
    assert dirty(rig, PIP_INDEX_URL="https://evil.example/simple")
    assert dirty(rig, DOCKER_HOST="tcp://evil.example:2375")
    # A planted sentinel is only another unknown variable.
    assert dirty(rig, YADGAR_KIND_UP_CLEAN="1")
    assert dirty(rig, YADGAR_ARCH="arm64")
    # PATH or HOME off their fixed values is dirty on its own.
    assert dirty(rig, safe_path="/elsewhere")
    assert dirty(rig, root_home="/root")


def test_main_scrubs_first_as_root_whatever_the_caller_planted(rig: Rig) -> None:
    stub = 'reexec_with_clean_environment() { echo "REEXEC $*"; exit 77; }'
    # As root with a dirty environment (the rig's own is): main hands over first.
    proc = as_root(rig, f"{stub}; main --with-client", root=True)
    assert proc.returncode == 77, proc.stdout + proc.stderr
    assert "REEXEC" in proc.stdout and "--with-client" in proc.stdout
    # A planted "already scrubbed" marker plus PIP_INDEX_URL is still scrubbed.
    proc = as_root(rig, f"{stub}; main --with-client", root=True,
                   YADGAR_KIND_UP_CLEAN="1", PIP_INDEX_URL="https://evil.example/simple")
    assert proc.returncode == 77, "a forged marker skipped the scrub: " + proc.stdout + proc.stderr
    # Not root: the offline suite and an unprivileged run are untouched.
    proc = as_root(rig, f"{stub}; main --with-client", root=False)
    assert "REEXEC" not in proc.stdout


def test_the_real_reexec_path_runs_the_script_as_root(rig: Rig, tmp_path: Path) -> None:
    """The actual script, executed (not sourced) as root, re-executes itself and runs.

    The probes above call the function with a name of their own. This one runs
    `"$SCRIPT_DIR/${BASH_SOURCE[0]##*/}"` as main builds it: a wrong script name
    there fails here and nowhere else.

    The re-executed script runs under the fixed PATH, which needs the usual tools
    in /usr/bin. Where /usr/bin lacks them (NixOS) they are bind-mounted over it
    inside a private mount namespace of the `unshare -r` route, rather than the
    test being skipped, which this repository's no-test-skips hook forbids."""
    bash = shutil.which("bash")
    assert bash, "bash is not installed"
    env = {"PATH": os.environ["PATH"], "HOME": str(rig.root / "home"), "TERM": "dumb",
           "PIP_INDEX_URL": "https://evil.example/simple", "YADGAR_KIND_UP_CLEAN": "1"}
    route = root_route()
    argv = [bash, str(SCRIPT), "--help"]
    if Path("/usr/bin/dirname").exists():
        if route[-1] == "-i":
            argv = [*route, *(f"{k}={v}" for k, v in env.items()), *argv]
        else:
            argv = [*route, *argv]
    else:
        assert route[0].endswith("unshare"), "no /usr/bin/dirname and no user namespace to supply one"
        tools = tmp_path / "usr-bin"
        tools.mkdir()
        for name in ("env", "dirname", "sed", "getent", "cut", "tr", "cat", "head", "tail", "grep",
                     "awk", "tee", "mkdir", "id", "rm"):
            found = shutil.which(name)
            assert found, f"{name} is not installed"
            (tools / name).symlink_to(Path(found).resolve())
        script = f'mount --bind "{tools}" /usr/bin && exec "$@"'
        argv = [route[0], "-rm", "/bin/sh", "-c", script, "sh", *argv]
    proc = subprocess.run(argv, env=env, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "kind-up.sh" in proc.stdout


# ─── route B names what root's INSTALLED client can do (ledger 1623) ───────────
#
# The lock row is what a rerun with --with-client installs, not what is installed:
# a client kept at 0.1.3 (credential in ~/.config/yadgar, mode not 0600), one whose
# pre-flight failed, or a rerun without --with-client all leave an older one.


def test_route_b_reads_the_installed_client_not_the_lock_row_for_a_kept_old_client(rig: Rig) -> None:
    """A 0.1.3 client kept because its old credential could not be copied."""
    root_config(rig, "yadgar")
    out = print_next_steps(rig, "enrolled here", version="0.1.3")
    assert "which has" not in out
    assert 'root client here is 0.1.3, which lacks "yaadgaar admin issue-enrolment"' in out
    assert "a rerun with --with-client upgrades it" in out
    assert "unless its credential" not in out
    assert client_version() not in out.split("B. Or enrol it.")[1].split("On a machine")[0]


def test_route_b_on_a_plain_rerun_names_the_installed_client_and_installs_nothing(rig: Rig) -> None:
    """No --with-client: ensure_client never runs, so the installed client is as it was."""
    out = print_next_steps(rig, "enrolled here", version="0.1.9")
    assert 'root client here is 0.1.9, which lacks "yaadgaar admin issue-enrolment"' in out
    assert not [c for c in rig.calls("pipx") if "install" in c["argv"]]


@pytest.mark.parametrize("answer", ["", "banana"])
def test_route_b_does_not_claim_a_client_that_gave_no_usable_version(rig: Rig, answer: str) -> None:
    rig.state.mkdir(exist_ok=True)
    (rig.state / "client-enrolled").write_text("")
    rig.rules = [{"cmd": "yaadgaar", "match": ["--version"], "stdout": f"yaadgaar {answer}\n"}] + rig.rules
    proc = rig.run("pin_root_environment; load_examples; print_next_steps")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "which has" not in proc.stdout
    assert "which lacks" in proc.stdout


def test_route_b_says_so_when_root_has_no_client(rig: Rig) -> None:
    (rig.root_home / ".local" / "bin" / "yaadgaar").unlink()
    out = print_next_steps(rig, "enrolled here", version=None)
    assert "This host's root has no client." in out
    assert "which has" not in out and "root client here" not in out


def test_route_b_boundary_is_numeric_not_textual(rig: Rig) -> None:
    out = print_next_steps(rig, "enrolled here", version="0.1.10")
    assert 'root client here is 0.1.10, which has "yaadgaar admin issue-enrolment"' in out
