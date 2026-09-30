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
)
PINNED = {"kind": "v0.32.0", "kubectl": "v1.36.1", "helm": "v4.3.0"}
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
        for d in ("fake", "fakebin", "bin", "state", "home", "etc"):
            (self.root / d).mkdir()
        for name in FAKED:
            (self.root / "fakebin" / name).symlink_to(FAKE)
        # The pinned tools live in YADGAR_BIN_DIR, where the script installs them.
        for name in PINNED:
            (self.root / "bin" / name).symlink_to(FAKE)
        (self.root / "etc" / "hosts").write_text("127.0.0.1 localhost\n")
        self.rules = version_rules() + sysctl_rules() + [{"cmd": "id", "match": ["-u"], "stdout": "0\n"}]

    @property
    def state(self) -> Path:
        return self.root / "state"

    @property
    def log(self) -> Path:
        return self.state / "kind-up.log"

    @property
    def enrolment_file(self) -> Path:
        return self.root / "home" / "yadgar-enrolment.token"

    def env(self, **extra: str) -> dict[str, str]:
        env = {
            "PATH": f"{self.root / 'fakebin'}:{os.environ['PATH']}",
            "HOME": str(self.root / "home"),
            "KUBECONFIG": str(self.root / "home" / "never-read"),
            "FAKE_DIR": str(self.root / "fake"),
            "YADGAR_STATE_DIR": str(self.state),
            "YADGAR_BIN_DIR": str(self.root / "bin"),
            "YADGAR_SYSCTL_FILE": str(self.root / "etc" / "90-yadgar-kind.conf"),
            "YADGAR_HOSTS_FILE": str(self.root / "etc" / "hosts"),
            "YADGAR_CA_FILE": str(self.root / "etc" / "yadgar" / "edge-ca.crt"),
            "YADGAR_ENROLMENT_FILE": str(self.enrolment_file),
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


def test_the_committed_lock_pins_every_tool_for_both_architectures() -> None:
    rows = [line.split() for line in LOCK.read_text().splitlines() if line and not line.startswith("#")]
    seen = {(r[0], r[2]) for r in rows}
    for tool in PINNED:
        for arch in ("amd64", "arm64"):
            assert (tool, arch) in seen, f"{tool}/{arch} missing from tools.lock"
    for r in rows:
        assert r[1] == PINNED[r[0]], f"{r[0]} pinned at {r[1]}"
        assert len(r[3]) == 64 and all(c in "0123456789abcdef" for c in r[3]), r
        assert r[4].startswith("https://"), r


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
    assert " iam" not in out, "a resource that synced fine was reported as failing"
    # Never forced: no sync, no patch of `operation`, no terminate.
    for c in rig.calls("kubectl"):
        assert "patch" not in c["argv"], c


def test_a_timeout_prints_the_conditions_and_unhealthy_resources(rig: Rig) -> None:
    doc = json.loads(app_json("operators", "Running", health="Degraded"))
    doc["status"]["conditions"] = [{"type": "SyncError", "message": "a condition worth reading"}]
    doc["status"]["resources"] = [
        {"kind": "Deployment", "namespace": "yadgar-operators", "name": "keda-operator",
         "health": {"status": "Degraded", "message": "crashloop"}}
    ]
    rig.rules = [{"cmd": "kubectl", "match": ["get", "application", "operators"], "stdout": json.dumps(doc)}] + rig.rules
    proc = rig.run("load_examples; wait_app operators 0")
    assert proc.returncode != 0
    out = proc.stdout + proc.stderr
    assert "timed out" in out
    assert "a condition worth reading" in out
    assert "keda-operator" in out and "crashloop" in out


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


def admin_rules(bootstrap: str, enrolment: str, create_code: str = "200", issue_code: str = "200") -> list[dict]:
    user = "yadgar:user:01a0f403-78c5-7464-bdf4-c534841e5178"
    create_body = json.dumps({"user_id": user}) if create_code == "200" else '{"error":"the administrative service is unavailable"}'
    issue_body = (
        json.dumps({"token": enrolment, "enrolment_id": "e1"})
        if issue_code == "200"
        else '{"error":"the bootstrap token may only enrol an administrator who has never held a credential"}'
    )
    return [
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
    assert rig.calls("kubectl") == [], "read the bootstrap token although nothing needed it"


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
        {"cmd": "kubectl", "match": ["get", "--raw", "/readyz"], "stdout": "ok"},
        {"cmd": "kubectl", "match": ["get", "nodes"],
         "stdout": json.dumps({"items": [{"status": {"conditions": [{"type": "Ready", "status": "True"}]}}]})},
        {"cmd": "podman", "match": ["port"], "stdout": "127.0.0.1:18443\n"},
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
    applied = [c["argv"][c["argv"].index("-f") + 1] for c in rig.calls("kubectl") if "apply" in c["argv"]]
    assert applied == [
        str(REPO / "example" / "operators-application.yaml"),
        str(REPO / "example" / "kind" / "application.yaml"),
    ]
    assert_absent(rig, first, bootstrap, base64.b64encode(bootstrap.encode()).decode(), enrolment)

    rig.reset_calls()
    second = rig.main()
    assert second.returncode == 0, second.stdout + second.stderr
    assert not [c for c in rig.calls("kind") if "create" in c["argv"]], "created the cluster again"
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


def test_with_client_enrols_and_logs_in_without_printing_the_password(rig: Rig) -> None:
    bootstrap, enrolment = new_secrets()
    rig.rules = [
        {"cmd": "yaadgaar", "match": ["enrol", "--help"],
         "stdout": "Usage: yaadgaar enrol [OPTIONS]\n  --token-file <PATH>\n  --password-stdin\n"},
    ] + full_rules(bootstrap, enrolment) + rig.rules
    proc = rig.main("--with-client")
    assert proc.returncode == 0, proc.stdout + proc.stderr

    pw_file = rig.state / "client-password"
    password = pw_file.read_text().strip()
    assert stat.S_IMODE(pw_file.stat().st_mode) == 0o600
    enrol = [c for c in rig.calls("yaadgaar") if c["argv"][:1] == ["enrol"] and "--password-stdin" in c["argv"]]
    login = [c for c in rig.calls("yaadgaar") if c["argv"][:1] == ["login"]]
    assert len(enrol) == 1 and len(login) == 1
    assert enrol[0]["argv"][enrol[0]["argv"].index("--token-file") + 1] == str(rig.enrolment_file)
    assert login[0]["argv"][login[0]["argv"].index("--gateway") + 1] == GATEWAY
    # POSITIVE CONTROL: the password went to both, on stdin.
    assert enrol[0]["stdin"].strip() == password
    assert login[0]["stdin"].strip() == password
    assert_absent(rig, proc, password, bootstrap, enrolment)

    rig.reset_calls()
    again = rig.main("--with-client")
    assert again.returncode == 0, again.stdout + again.stderr
    assert not [c for c in rig.calls("yaadgaar") if c["argv"][:1] == ["enrol"] and "--password-stdin" in c["argv"]]
