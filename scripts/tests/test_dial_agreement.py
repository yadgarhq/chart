"""yaadgaar #308 (L893) and #194 half 1: EVERY DIAL IN THE ESTATE HITS A PORT THE CALLEE SERVES, WITH THE CALLEE'S TLS.

THE CLASS, NOT THE THREE INSTANCES. Ledger 890 shipped the gateway dialling
`project` on 50051, which is `project-db`'s port. Ledger 892 shipped `project`
serving TLS while the gateway dialled it in cleartext (h2 `FRAME_SIZE_ERROR`).
Each shipped with every light green, because no chart can see both halves of
a hop: the consumer's chart renders the dial, the callee's chart renders the
listener, and only this parent renders the two together. ADR-0574 closes a
defect found twice as a class; ADR-0771 puts the rule in code, not in the
prose comment `gateway/chart/values.yaml` carries for 890.

WHAT IS RENDERED. This repository's `chart/` at HEAD, with its HEAD pins, over
each adopter source: `example/values.yaml`, the `valuesObject` of
`example/application.yaml` and of `example/kind/application.yaml` (each with
the placeholder administrator replaced, as the other suites do), and
`chart/ci/values.yaml`. The examples pin a PUBLISHED parent; this gate renders
HEAD on purpose, because a pin bump that breaks a hop must go red in the pull
request that makes it.

WHAT AN EDGE IS. One dial a rendered workload makes, read from its env through
`ADAPTERS` below: a host, a port and the TLS posture of the dial. For every
edge this file asserts that

1. a rendered Service named by the host exists;
2. it exposes the port;
3. its `targetPort` resolves to a `containerPort` on a workload the Service
   selects;
4. the callee serves TLS on that container port exactly when the consumer
   dials TLS.

THE SETS ARE CLOSED THREE WAYS, so a new module, workload or dial cannot pass
by being unseen: `ADAPTERS` has a row for every dependency in
`chart/Chart.yaml` and no other; every rendered Deployment, StatefulSet,
DaemonSet, Job and CronJob is claimed by a row or by `WORKLOAD_EXCLUSIONS`;
and every env var shaped like a dial, in any container or init container of
any workload (an excluded one too), is claimed by an adapter or by
`ENV_EXCLUSIONS`. One set through `valueFrom` cannot be read and is refused
unless excluded. Each exclusion carries its reason.

THE COUNT REGISTER (ADR-0755, ADR-0771 rule 4) is `DIAL_EDGES`: the named set
of edges, a hand-written literal per render. It is not derived from the
render, because a set derived from the render agrees with whatever the render
happens to be. Its row:

| gate | render | expected | constructed red |
| --- | --- | --- | --- |
| `test_every_dial_agrees_with_its_callee` | each of `RENDERS` | `DIAL_EDGES[render]`, 12 edges each | `test_a_dial_on_the_wrong_port_is_named` (gateway `project.port: 50051`) and `test_a_dial_whose_tls_disagrees_is_named` (gateway `project.tls.enabled: false`) and `test_a_tls_valkey_dial_to_a_cleartext_only_valkey_is_named` |

NATS AND VALKEY ARE EDGES; MARIADB IS CHECKED AGAINST ITS CR. The gateway and iam dial
NATS, and the gateway dials Valkey, in the same shape as the gRPC hops, and
`platform` renders both Services, so all three are checked. A TLS Valkey dial
goes to 6380 whatever port `gateway.rateLimit.addr` spells (the gateway
binary's `TLS_PORT`). A `nats.conf` this file cannot read fails by name rather
than being guessed at. A NATS broker with
`allow_non_tls` accepts either posture on one port. The three `-db` modules'
MariaDB dials are not edges: the mariadb-operator creates that Service at
runtime, so the render holds nothing to check the port against. They stay
named exclusions, and `mariadb_gate` checks them against the MariaDB CR
instead (yaadgaar #542): `DB_HOST` is the CR's name, `DB_PORT` is its
`spec.port` (3306 when unset), and `DB_SSL_MODE` is `required` exactly when
`spec.tls.required` is true. Its count register is `MARIADB_EDGES`.

A PIN BUMP THAT MOVES AN ENV NAME FAILS HERE, and that is wanted friction: the
same pull request updates the adapter row.

Run: python3 -m pytest scripts/tests/ -q
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml

from test_parent_chart import (
    ADOPTER_VALUES,
    API_VERSIONS,
    CHART,
    EXAMPLE_APPLICATION,
    EXPLICIT_TLS,
    KIND_APPLICATION,
    helm,
    with_placeholder_replaced,
)

# ── THE ADAPTER TABLE ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Dial:
    """One upstream a workload dials, and where its env says so.

    `form` is how the address is written:
      - `host_port`: `<PREFIX>_HOST` and `<PREFIX>_PORT`;
      - `url`: one variable holding `scheme://host:port`;
      - `addr`: one variable holding `host:port`.
    `tls` is how the dial's TLS posture is written:
      - `flag:<VAR>`: on exactly when `<VAR>` is the string "1" (the estate's
        enable-flag rule, `tls-configuration-naming-across-services`);
      - `ca_file:<VAR>`: on exactly when `<VAR>` is rendered. For a chart with
        no enable flag, whose dial is TLS whenever it names a CA bundle.
    `chart_key` names the values keys that write the env, in the consumer's
    chart, so a reader of a failure knows what to move.
    `tls_port`, when set, is the port the BINARY dials whenever the dial is
    TLS, whatever port the address spells out. The address then names only
    the host.
    """

    form: str
    address: tuple[str, ...]
    tls: str
    chart_key: str
    tls_port: int | None = None


def grpc(prefix: str, chart_key: str) -> Dial:
    return Dial("host_port", (f"{prefix}_HOST", f"{prefix}_PORT"), f"flag:{prefix}_TLS_ENABLED", chart_key)


@dataclass(frozen=True)
class Workload:
    """A rendered workload a row claims: what it dials, and how it serves.

    `serves` is how the callee's serving TLS is read when this workload is the
    target of a Service:
      - `listen_env`: the container's `LISTEN` names the port, and
        `LISTEN_TLS_ENABLED == "1"` is TLS on it (every module, ADR-0845);
      - `valkey_args`: `--tls-port N` is TLS on N, `--port N` (N not 0) is
        cleartext on N (`platform/templates/valkey.yaml`, ADR-0852);
      - `nats_conf`: the client port in the mounted `nats.conf` is TLS when
        the document has a top-level `tls` block;
      - None: nothing dials this workload.
    """

    kind: str
    name: str
    serves: str | None
    dials: tuple[Dial, ...] = ()


@dataclass(frozen=True)
class Module:
    cite: str
    workloads: tuple[Workload, ...] = ()


# ONE ROW PER `chart/Chart.yaml` DEPENDENCY, keyed by its name, which is also
# the values key every chart key below starts with.
ADAPTERS: dict[str, Module] = {
    "config": Module(
        cite="config renders ConfigMaps only (`shared`, `audit`); it has no workload and no dial",
    ),
    "gateway": Module(
        cite="gateway/templates/deployment.yaml",
        workloads=(
            Workload(
                "Deployment",
                "gateway",
                serves="listen_env",
                dials=(
                    grpc("TASK", "gateway.task.host, gateway.task.port, gateway.task.tls.enabled"),
                    grpc("IAM", "gateway.iam.host, gateway.iam.port, gateway.iam.tls.enabled"),
                    grpc("PROJECT", "gateway.project.host, gateway.project.port, gateway.project.tls.enabled"),
                    Dial("url", ("NATS_URL",), "flag:NATS_TLS_ENABLED", "gateway.nats.url, gateway.nats.tls.enabled"),
                    # A TLS DIAL GOES TO 6380, NOT TO THE ADDRESS'S PORT:
                    # gateway `src/limit/valkey.rs` `const TLS_PORT: u16 = 6380`
                    # builds `rediss://<host>:6380` from the address's host
                    # alone. The pinned chart's values.yaml (`valkey.tls`)
                    # says the same.
                    Dial(
                        "addr",
                        ("YADGAR_VALKEY_ADDR",),
                        "flag:VALKEY_TLS_ENABLED",
                        "gateway.rateLimit.addr, gateway.valkey.tls.enabled; TLS port: gateway src/limit/valkey.rs TLS_PORT",
                        tls_port=6380,
                    ),
                ),
            ),
        ),
    ),
    "iam": Module(
        cite="iam/templates/deployment.yaml",
        workloads=(
            Workload(
                "Deployment",
                "iam",
                serves="listen_env",
                dials=(
                    grpc("IAM_DB", "iam.iamDb.host, iam.iamDb.port, iam.iamDb.tls.enabled"),
                    Dial("url", ("NATS_URL",), "flag:NATS_TLS_ENABLED", "iam.nats.url, iam.nats.tls.enabled"),
                ),
            ),
        ),
    ),
    "iam-db": Module(
        cite="iam-db/templates/deployment.yaml; its MariaDB dial is in ENV_EXCLUSIONS",
        workloads=(Workload("Deployment", "iam-db", serves="listen_env"),),
    ),
    "project": Module(
        cite="project/templates/deployment.yaml",
        workloads=(
            Workload(
                "Deployment",
                "project",
                serves="listen_env",
                dials=(
                    grpc(
                        "PROJECT_DB",
                        "project.projectDb.host, project.projectDb.port, project.projectDb.tls.enabled",
                    ),
                ),
            ),
        ),
    ),
    "project-db": Module(
        cite="project-db/templates/deployment.yaml; its MariaDB dial is in ENV_EXCLUSIONS",
        workloads=(Workload("Deployment", "project-db", serves="listen_env"),),
    ),
    "task": Module(
        cite="task/templates/deployment.yaml",
        workloads=(
            Workload(
                "Deployment",
                "task",
                serves="listen_env",
                dials=(grpc("TASK_DB", "task.taskDb.host, task.taskDb.port, task.taskDb.tls.enabled"),),
            ),
        ),
    ),
    "task-db": Module(
        cite="task-db/templates/deployment.yaml; its MariaDB dial is in ENV_EXCLUSIONS",
        workloads=(Workload("Deployment", "task-db", serves="listen_env"),),
    ),
    # THE SEEDER HAS NO ENABLE FLAG. `seeder/templates/render-checks.yaml`
    # refuses a render without `project.tls.caSecret` and `iam.tls.caSecret`,
    # so both dials are always TLS, and the CA file in the env is the posture.
    "seeder": Module(
        cite="seeder/templates/job.yaml, render-checks.yaml (caSecret required: always TLS)",
        workloads=(
            Workload(
                "Job",
                "seeder",
                serves=None,
                dials=(
                    Dial(
                        "host_port",
                        ("PROJECT_HOST", "PROJECT_PORT"),
                        "ca_file:PROJECT_TLS_CA_FILE",
                        "seeder.project.host, seeder.project.port, seeder.project.tls.caSecret",
                    ),
                    Dial(
                        "host_port",
                        ("IAM_HOST", "IAM_PORT"),
                        "ca_file:IAM_TLS_CA_FILE",
                        "seeder.iam.host, seeder.iam.port, seeder.iam.tls.caSecret",
                    ),
                ),
            ),
        ),
    ),
    "platform": Module(
        cite="platform/templates/valkey.yaml (platform.valkey.*); the vendored nats chart (platform.nats.*)",
        workloads=(
            Workload("Deployment", "valkey", serves="valkey_args"),
            Workload("StatefulSet", "nats", serves="nats_conf"),
        ),
    ),
}

# WORKLOADS NO ROW CLAIMS, AND WHY. A name here that stops rendering fails
# too, so this list cannot rot into a hole.
WORKLOAD_EXCLUSIONS: dict[tuple[str, str], str] = {
    ("Job", "preflight"): "platform hook Job: it reads the API server for operators and dials no estate Service",
    ("Job", "envoy-gateway-probe"): "platform hook Job: it submits a probe Gateway to the API server and dials no estate Service",
    ("Job", "bootstrap-secrets"): "platform hook Job: it mints Secrets through the API server and dials no estate Service",
    ("Job", "admin-bootstrap-token"): "platform hook Job: it mints a Secret through the API server and dials no estate Service",
}

# DIAL-SHAPED ENV NO ADAPTER CLAIMS, AND WHY: (workload, variable) -> reason.
MARIADB = (
    "MariaDB dial: the mariadb-operator creates the `<name>-mariadb` Service from the MariaDB CR at "
    "runtime, so no Service is in the render to check the port against; `mariadb_gate` checks it against the CR"
)
ENROLMENT = (
    "the edge hostname an enrolling client is told to use (`iam.enrolment.gateway`), outside the cluster; "
    "it names no in-cluster Service"
)
ENV_EXCLUSIONS: dict[tuple[str, str], str] = {
    ("iam-db", "DB_HOST"): MARIADB,
    ("iam-db", "DB_PORT"): MARIADB,
    ("project-db", "DB_HOST"): MARIADB,
    ("project-db", "DB_PORT"): MARIADB,
    ("task-db", "DB_HOST"): MARIADB,
    ("task-db", "DB_PORT"): MARIADB,
    ("iam", "ENROLMENT_GATEWAY"): ENROLMENT,
}

# WHAT AN ENV VAR NAMED LIKE A DIAL LOOKS LIKE. `METRICS_LISTEN` and `LISTEN`
# are a workload's own bind address, not a dial, and do not match.
DIAL_SHAPED = re.compile(r"(_HOST|_PORT|_URL|_URI|_ADDR|_ADDRESS|_ENDPOINT|_TARGET)$|^ENROLMENT_GATEWAY$")

# ── THE COUNT REGISTER (ADR-0755) ────────────────────────────────────────────
# LITERALS, written by hand. Edge ids are `consumer→host:port`. The HTTPRoute
# edge is the edge listener's backend: Envoy dials the gateway Service.
EDGES_AT_HEAD = frozenset(
    {
        "gateway→task:50052",
        "gateway→iam:50052",
        "gateway→project:50052",
        "gateway→nats:4222",
        "gateway→valkey:6379",
        "iam→iam-db:50051",
        "iam→nats:4222",
        "project→project-db:50051",
        "task→task-db:50051",
        "seeder→project:50052",
        "seeder→iam:50052",
        "httproute/gateway→gateway:8080",
    }
)
DIAL_EDGES: dict[str, frozenset[str]] = {
    "example-values": EDGES_AT_HEAD,
    "example-application": EDGES_AT_HEAD,
    "example-kind-application": EDGES_AT_HEAD,
    "ci-values": EDGES_AT_HEAD,
}

# The failure sentences, by the words a reader searches for. LITERALS.
NO_PORT = "exposes no port"
TLS_MISMATCH = "TLS mismatch"

# ── RENDERING ────────────────────────────────────────────────────────────────


def values_object_file(application: Path, destination: Path) -> Path:
    document = yaml.safe_load(application.read_text())
    values = with_placeholder_replaced(document["spec"]["source"]["helm"]["valuesObject"])
    path = destination / f"{application.parent.name}-{application.stem}.yaml"
    path.write_text(yaml.safe_dump(values))
    return path


def render_sources(destination: Path) -> dict[str, list[str]]:
    return {
        "example-values": ["-f", str(ADOPTER_VALUES)],
        "example-application": ["-f", str(values_object_file(EXAMPLE_APPLICATION, destination))],
        "example-kind-application": ["-f", str(values_object_file(KIND_APPLICATION, destination))],
        "ci-values": ["-f", str(EXPLICIT_TLS)],
    }


def render(arguments: list[str]) -> list[dict]:
    result = helm("template", "yadgar", str(CHART), *API_VERSIONS, *arguments)
    assert result.returncode == 0, result.stderr
    return [d for d in yaml.safe_load_all(result.stdout) if isinstance(d, dict) and d.get("kind")]


@pytest.fixture(scope="module")
def sources(tmp_path_factory) -> dict[str, list[str]]:
    return render_sources(tmp_path_factory.mktemp("dial-sources"))


@pytest.fixture(scope="module")
def renders(sources) -> dict[str, list[dict]]:
    return {name: render(arguments) for name, arguments in sources.items()}


def overlay(tmp_path: Path, values: dict) -> list[str]:
    path = tmp_path / "overlay.yaml"
    path.write_text(yaml.safe_dump(values))
    return ["-f", str(path)]


# ── THE GATE, PURE OVER A RENDER ─────────────────────────────────────────────

WORKLOAD_KINDS = ("Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob")
# The kinds a Service can route to. A Job's or CronJob's pods serve nothing.
SERVING_KINDS = ("Deployment", "StatefulSet", "DaemonSet")


def env_of(container: dict) -> dict[str, str]:
    return {e["name"]: e.get("value") for e in container.get("env", []) if "value" in e}


def pod_template(document: dict) -> dict:
    if document["kind"] == "CronJob":
        return document["spec"]["jobTemplate"]["spec"]["template"]
    return document["spec"]["template"]


def containers(document: dict) -> list[dict]:
    return pod_template(document)["spec"].get("containers", [])


def every_container(document: dict) -> list[dict]:
    """The containers AND the init containers: either can dial."""
    spec = pod_template(document)["spec"]
    return [*spec.get("initContainers", []), *spec.get("containers", [])]


def tls_of_dial(dial: Dial, env: dict[str, str]) -> bool:
    rule, variable = dial.tls.split(":", 1)
    if rule == "flag":
        return env.get(variable) == "1"
    return bool(env.get(variable))


def address_of(dial: Dial, env: dict[str, str]) -> tuple[str, int]:
    if dial.form == "host_port":
        host, port = env[dial.address[0]], env[dial.address[1]]
    elif dial.form == "url":
        parts = urlsplit(env[dial.address[0]])
        host, port = parts.hostname, parts.port
    else:
        host, _, port = env[dial.address[0]].rpartition(":")
    if dial.tls_port is not None and tls_of_dial(dial, env):
        port = dial.tls_port
    return str(host), int(port)


@dataclass(frozen=True)
class Edge:
    consumer: str
    host: str
    port: int
    tls: bool
    chart_key: str

    @property
    def name(self) -> str:
        return f"{self.consumer}→{self.host}:{self.port}"


def edges_and_problems(documents: list[dict], dependencies: list[str]) -> tuple[list[Edge], list[str]]:
    """Every dial the render makes, and every closure failure on the way. PURE."""
    problems: list[str] = []
    if sorted(ADAPTERS) != sorted(dependencies):
        problems.append(
            f"ADAPTERS rows {sorted(ADAPTERS)} are not chart/Chart.yaml's dependencies {sorted(dependencies)}: "
            "a dependency with no row is a module whose dials nothing checks"
        )
    by_identity = {(d["kind"], d["metadata"]["name"]): d for d in documents if d["kind"] in WORKLOAD_KINDS}
    claimed = {(w.kind, w.name): w for module in ADAPTERS.values() for w in module.workloads}

    for identity in sorted(set(by_identity) - set(claimed) - set(WORKLOAD_EXCLUSIONS)):
        problems.append(f"{identity[0]} {identity[1]} is rendered and no ADAPTERS row or WORKLOAD_EXCLUSIONS entry claims it")
    for identity in sorted((set(claimed) | set(WORKLOAD_EXCLUSIONS)) - set(by_identity)):
        problems.append(f"{identity[0]} {identity[1]} is named by this file and is not rendered: update the row")

    edges: list[Edge] = []
    # EVERY rendered workload is scanned, an excluded one too: a dial added
    # later to a workload excluded for dialling nothing must go red.
    for identity, document in sorted(by_identity.items()):
        workload = claimed.get(identity)
        name = identity[1]
        env: dict[str, str] = {}
        from_reference: set[str] = set()
        for container in every_container(document):
            env.update(env_of(container))
            from_reference.update(e["name"] for e in container.get("env", []) if "value" not in e)
        used: set[str] = set()
        for dial in workload.dials if workload else ():
            missing = [v for v in dial.address if v not in env]
            if missing:
                problems.append(f"{name}: the adapter names {missing}, which the render does not set ({dial.chart_key})")
                continue
            used.update(dial.address)
            host, port = address_of(dial, env)
            edges.append(Edge(name, host, port, tls_of_dial(dial, env), dial.chart_key))
        for variable in sorted(set(env) | from_reference):
            if not DIAL_SHAPED.search(variable) or variable in used or (name, variable) in ENV_EXCLUSIONS:
                continue
            if variable in from_reference:
                problems.append(
                    f"{name} sets {variable} through valueFrom, shaped like a dial, so the gate cannot read it, "
                    "and no ENV_EXCLUSIONS entry claims it"
                )
            else:
                problems.append(
                    f"{name} sets {variable}, shaped like a dial, and no adapter or ENV_EXCLUSIONS entry claims it"
                )

    # THE EDGE LISTENER'S BACKENDS. Envoy dials the Service an HTTPRoute
    # names; it dials TLS only when a BackendTLSPolicy targets that Service.
    tls_backends = {
        ref.get("name")
        for d in documents
        if d["kind"] == "BackendTLSPolicy"
        for ref in d["spec"].get("targetRefs", [])
    }
    for d in documents:
        if d["kind"] != "HTTPRoute":
            continue
        for rule in d["spec"].get("rules", []):
            for ref in rule.get("backendRefs", []):
                edges.append(
                    Edge(
                        f"httproute/{d['metadata']['name']}",
                        ref["name"],
                        int(ref["port"]),
                        ref["name"] in tls_backends,
                        "the HTTPRoute's backendRefs",
                    )
                )
    return edges, problems


def selects(selector: dict, document: dict) -> bool:
    labels = pod_template(document)["metadata"].get("labels") or {}
    return bool(selector) and all(labels.get(k) == v for k, v in selector.items())


NATS_UNREADABLE = "nats.conf is not JSON-with-$vars (include?): cannot read TLS"


def nats_conf(text: str) -> dict | str:
    """The rendered `nats.conf` as a dict, or `NATS_UNREADABLE`. PURE.

    The vendored nats chart writes JSON in which `$NAME` stands, unquoted, for
    a nats variable. Each such token OUTSIDE a JSON string is quoted; text
    inside a string is copied unchanged, so a value like "a: $b" survives.
    Anything that is still not JSON (an `include`, say) cannot be read, and
    the gate fails with a named problem rather than guess the posture.
    """
    out: list[str] = []
    i, in_string = 0, False
    while i < len(text):
        char = text[i]
        if in_string:
            out.append(char)
            if char == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 1
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
            out.append(char)
        elif char == "$":
            match = re.match(r"\$\w+", text[i:])
            if match is None:
                return NATS_UNREADABLE
            out.append(f'"{match.group(0)}"')
            i += len(match.group(0))
            continue
        else:
            out.append(char)
        i += 1
    try:
        conf = json.loads("".join(out))
    except json.JSONDecodeError:
        return NATS_UNREADABLE
    return conf if isinstance(conf, dict) else NATS_UNREADABLE


TLS_ONLY = frozenset({True})
CLEARTEXT_ONLY = frozenset({False})


def served_tls(
    workload: Workload, document: dict, container: dict, container_port: int, documents: list[dict]
) -> frozenset[bool] | str:
    """The dial postures the callee accepts on `container_port`, or a problem sentence.

    One posture for every listener but one: a NATS broker with
    `allow_non_tls` accepts both on the same port, so either dial agrees.
    """
    env = env_of(container)
    if workload.serves == "listen_env":
        listen = env.get("LISTEN", "")
        if not listen.endswith(f":{container_port}"):
            return f"the target port {container_port} is not LISTEN ({listen!r}), so LISTEN_TLS_ENABLED does not describe it"
        return TLS_ONLY if env.get("LISTEN_TLS_ENABLED") == "1" else CLEARTEXT_ONLY
    if workload.serves == "valkey_args":
        script = " ".join(container.get("args", []))
        tls_ports = {int(p) for p in re.findall(r"--tls-port (\d+)", script)}
        plain_ports = {int(p) for p in re.findall(r"--port (\d+)", script)} - {0}
        if container_port in tls_ports:
            return TLS_ONLY
        if container_port in plain_ports:
            return CLEARTEXT_ONLY
        return f"valkey's arguments serve nothing on {container_port} (TLS {sorted(tls_ports)}, cleartext {sorted(plain_ports)})"
    if workload.serves == "nats_conf":
        volumes = {v["name"]: v for v in pod_template(document)["spec"].get("volumes", [])}
        names = [
            volumes[m["name"]]["configMap"]["name"]
            for m in container.get("volumeMounts", [])
            if "configMap" in volumes.get(m["name"], {})
        ]
        texts = [
            (d.get("data") or {}).get("nats.conf")
            for d in documents
            if d["kind"] == "ConfigMap" and d["metadata"]["name"] in names
        ]
        texts = [t for t in texts if t]
        if len(texts) != 1:
            return f"nats mounts {len(texts)} ConfigMaps carrying nats.conf, not one"
        conf = nats_conf(texts[0])
        if isinstance(conf, str):
            return conf
        if conf.get("port") != container_port:
            return f"nats.conf's client port is {conf.get('port')}, not the target port {container_port}"
        if "tls" not in conf:
            return CLEARTEXT_ONLY
        return frozenset({True, False}) if conf.get("allow_non_tls") is True else TLS_ONLY
    return f"{workload.name} has no serving posture in ADAPTERS, and a Service routes to it"


def edge_problems(edge: Edge, documents: list[dict]) -> list[str]:
    """Assertions 1 to 4 for one edge, each failure naming the edge. PURE."""
    services = [d for d in documents if d["kind"] == "Service" and d["metadata"]["name"] == edge.host]
    if not services:
        return [f"{edge.name}: no Service named {edge.host!r} is rendered ({edge.chart_key})"]
    service = services[0]
    ports = service["spec"].get("ports", [])
    matching = [p for p in ports if p.get("port") == edge.port]
    if not matching:
        exposed = ", ".join(str(p.get("port")) for p in ports)
        return [f"{edge.name}: Service {edge.host} {NO_PORT} {edge.port}, {edge.host} serves {exposed} ({edge.chart_key})"]
    target = matching[0].get("targetPort", edge.port)
    claimed = {(w.kind, w.name): w for module in ADAPTERS.values() for w in module.workloads}
    selector = service["spec"].get("selector") or {}
    selected = [d for d in documents if d["kind"] in SERVING_KINDS and selects(selector, d)]
    if not selected:
        return [f"{edge.name}: Service {edge.host} selects no rendered Deployment, StatefulSet or DaemonSet ({selector})"]
    problems: list[str] = []
    for document in selected:
        found = [
            (container, p["containerPort"])
            for container in containers(document)
            for p in container.get("ports", [])
            if p.get("name") == target or p.get("containerPort") == target
        ]
        label = f"{document['kind']} {document['metadata']['name']}"
        if not found:
            problems.append(f"{edge.name}: targetPort {target!r} resolves to no containerPort on {label}")
            continue
        workload = claimed.get((document["kind"], document["metadata"]["name"]))
        if workload is None:
            problems.append(f"{edge.name}: {label} has no ADAPTERS row, so its serving TLS is unread")
            continue
        container, container_port = found[0]
        serving = served_tls(workload, document, container, container_port, documents)
        if isinstance(serving, str):
            problems.append(f"{edge.name}: {serving}")
        elif edge.tls not in serving:
            problems.append(
                f"{edge.name}: {TLS_MISMATCH}: {edge.consumer} dials {'TLS' if edge.tls else 'cleartext'} "
                f"and {edge.host} serves {'cleartext' if edge.tls else 'TLS'} on {container_port} ({edge.chart_key})"
            )
    return problems


def dependencies() -> list[str]:
    return [d["name"] for d in yaml.safe_load((CHART / "Chart.yaml").read_text())["dependencies"]]


def gate(documents: list[dict]) -> tuple[list[Edge], list[str]]:
    edges, problems = edges_and_problems(documents, dependencies())
    if not edges:
        problems.append("no edge was discovered: a gate over zero edges inspects nothing")
    for edge in edges:
        problems.extend(edge_problems(edge, documents))
    return edges, problems


# ── THE PARTIAL MARIADB EDGE (yaadgaar #542) ─────────────────────────────────
# The mariadb-operator creates the `<name>` Service at runtime, so the render
# holds no Service to check a -db module's DB_HOST against. The MariaDB CR IS
# rendered, so three of the four assertions an edge gets are still possible,
# against the CR instead of a Service: the host is the CR's name, the port is
# the CR's `spec.port` (3306 when unset), and `DB_SSL_MODE` is a TLS-required
# mode exactly when `spec.tls.required` is true. The -db charts' `sslMode`
# takes `required`, `verify-identity` and `preferred`: `required` and
# `verify-identity` both refuse a cleartext connection, `preferred` falls back
# to one. (`verify-ca` was removed because it crash-loops the pod, and there
# is no `verify-full`.) Whether the operator's Service serves that port stays
# unchecked, and is the reason these dials stay in ENV_EXCLUSIONS.

MARIADB_MODULES = ("iam-db", "project-db", "task-db")
MARIADB_DEFAULT_PORT = 3306
MARIADB_TLS_REQUIRED_MODES = frozenset({"required", "verify-identity"})
MARIADB_CR_COUNT = "expected one MariaDB CR labelled"
MARIADB_HOST_MISMATCH = "DB_HOST is not the MariaDB CR name"
MARIADB_PORT_MISMATCH = "DB_PORT is not the MariaDB CR port"
MARIADB_PORT_NOT_INTEGER = "DB_PORT is not an integer"
MARIADB_TLS_MISMATCH = "DB_SSL_MODE disagrees with the MariaDB CR"


def mariadb_gate(documents: list[dict]) -> tuple[set[str], list[str]]:
    """The partial MariaDB edge of every -db module: its edge ids and its problems. PURE."""
    problems: list[str] = []
    edges: set[str] = set()
    for module in MARIADB_MODULES:
        label = f"app.kubernetes.io/name={module}"
        crs = [
            d
            for d in documents
            if d["kind"] == "MariaDB" and (d["metadata"].get("labels") or {}).get("app.kubernetes.io/name") == module
        ]
        if len(crs) != 1:
            problems.append(f"{module}: {MARIADB_CR_COUNT} {label}, found {len(crs)}")
            continue
        workloads = [d for d in documents if d["kind"] == "Deployment" and d["metadata"]["name"] == module]
        if len(workloads) != 1:
            problems.append(f"{module}: expected one Deployment named {module}, found {len(workloads)}")
            continue
        env: dict[str, str] = {}
        for container in every_container(workloads[0]):
            env.update(env_of(container))
        keys = {
            "DB_HOST": f"{module}.database.host",
            "DB_PORT": f"{module}.database.port",
            "DB_SSL_MODE": f"{module}.database.sslMode",
        }
        missing = [v for v in keys if v not in env]
        for variable in missing:
            problems.append(f"{module}: the render does not set {variable} ({keys[variable]})")
        if missing:
            continue
        cr = crs[0]
        name = cr["metadata"]["name"]
        spec = cr.get("spec") or {}
        port = int(spec.get("port", MARIADB_DEFAULT_PORT))
        required = (spec.get("tls") or {}).get("required") is True
        edges.add(f"{module}→{name}:{port}")
        if env["DB_HOST"] != name:
            problems.append(
                f"{module}: {MARIADB_HOST_MISMATCH}: DB_HOST is '{env['DB_HOST']}' and the MariaDB CR is named '{name}' "
                f"({keys['DB_HOST']})"
            )
        if not re.fullmatch(r"\d+", env["DB_PORT"]):
            problems.append(f"{module}: {MARIADB_PORT_NOT_INTEGER}: DB_PORT is '{env['DB_PORT']}' ({keys['DB_PORT']})")
        elif int(env["DB_PORT"]) != port:
            problems.append(
                f"{module}: {MARIADB_PORT_MISMATCH}: DB_PORT is {env['DB_PORT']} and the MariaDB CR serves {port} "
                f"({keys['DB_PORT']})"
            )
        if (env["DB_SSL_MODE"] in MARIADB_TLS_REQUIRED_MODES) != required:
            problems.append(
                f"{module}: {MARIADB_TLS_MISMATCH}: DB_SSL_MODE is '{env['DB_SSL_MODE']}' and the MariaDB CR "
                f"spec.tls.required is {str(required).lower()} ({keys['DB_SSL_MODE']})"
            )
    if not edges:
        problems.append("no MariaDB edge was discovered: a gate over zero edges inspects nothing")
    return edges, problems


# ── GREEN ────────────────────────────────────────────────────────────────────


def test_the_register_names_every_render(sources):
    assert sorted(DIAL_EDGES) == sorted(sources)
    assert all(DIAL_EDGES.values()), "a register row with no edge would let a vacuous gate pass"


@pytest.mark.parametrize("name", sorted(DIAL_EDGES))
def test_every_dial_agrees_with_its_callee(renders, name):
    edges, problems = gate(renders[name])
    assert problems == [], "\n".join(problems)
    found = {edge.name for edge in edges}
    assert found, "zero edges"
    assert found == DIAL_EDGES[name], (
        f"the {name} render dials {sorted(found - DIAL_EDGES[name])} that the register does not name, "
        f"and does not dial {sorted(DIAL_EDGES[name] - found)} that it does"
    )


def test_every_adapter_row_is_a_parent_dependency():
    assert sorted(ADAPTERS) == sorted(dependencies())


# ── RED: CONSTRUCTED MUTATIONS (ADR-0646) ────────────────────────────────────


def test_a_dial_on_the_wrong_port_is_named(sources, tmp_path):
    """Ledger 890's shape: gateway dials `project` on project-db's 50051."""
    documents = render(sources["example-values"] + overlay(tmp_path, {"gateway": {"project": {"port": 50051}}}))
    _, problems = gate(documents)
    assert problems == [
        "gateway→project:50051: Service project exposes no port 50051, project serves 50052 "
        "(gateway.project.host, gateway.project.port, gateway.project.tls.enabled)"
    ]


def test_a_dial_whose_tls_disagrees_is_named(sources, tmp_path):
    """Ledger 892's shape: `project` serves TLS and the gateway dials it in cleartext.

    Over `ci-values`, where `project.tls.clientAuth` is "off": with "required"
    the parent's own `validate.yaml` already refuses a caller with no leaf, so
    the flip would prove that refusal, not this gate.
    """
    documents = render(sources["ci-values"] + overlay(tmp_path, {"gateway": {"project": {"tls": {"enabled": False}}}}))
    _, problems = gate(documents)
    assert problems == [
        f"gateway→project:50052: {TLS_MISMATCH}: gateway dials cleartext and project serves TLS on 50052 "
        "(gateway.project.host, gateway.project.port, gateway.project.tls.enabled)"
    ]


VALKEY_TLS_ON = {"platform": {"valkey": {"tls": {"enabled": True}}}, "gateway": {"valkey": {"tls": {"enabled": True}}}}
NATS_TLS_ON = {
    "platform": {"nats": {"tls": {"enabled": True}, "config": {"nats": {"tls": {"enabled": True, "secretName": "nats-tls"}}}}},
    "gateway": {"nats": {"tls": {"enabled": True}}},
    "iam": {"nats": {"tls": {"enabled": True}}},
}


VALKEY_CHART_KEY = "gateway.rateLimit.addr, gateway.valkey.tls.enabled; TLS port: gateway src/limit/valkey.rs TLS_PORT"


def test_valkey_tls_on_dials_6380_whatever_the_address_port(sources, tmp_path):
    """Both valkey switches on, `gateway.rateLimit.addr` left at `valkey:6379`.

    The gateway binary dials `rediss://valkey:6380` (`TLS_PORT`), and valkey
    serves TLS on 6380, so the hop agrees on 6380 and the address's port is
    not read.
    """
    documents = render(sources["example-values"] + overlay(tmp_path, VALKEY_TLS_ON))
    edges, problems = gate(documents)
    assert problems == []
    names = {edge.name for edge in edges}
    assert "gateway→valkey:6380" in names
    assert "gateway→valkey:6379" not in names


def test_a_tls_valkey_dial_to_a_cleartext_only_valkey_is_named(sources, tmp_path):
    """The gateway dials TLS on 6380, and platform's valkey serves only 6379."""
    values = {"gateway": VALKEY_TLS_ON["gateway"]}
    documents = render(sources["example-values"] + overlay(tmp_path, values))
    _, problems = gate(documents)
    assert problems == [f"gateway→valkey:6380: Service valkey {NO_PORT} 6380, valkey serves 6379 ({VALKEY_CHART_KEY})"]


def test_nats_tls_on_both_sides_agrees(sources, tmp_path):
    """The positive control for reading `nats.conf`: a TLS listener is seen as TLS."""
    _, problems = gate(render(sources["example-values"] + overlay(tmp_path, NATS_TLS_ON)))
    assert problems == []


def test_nats_tls_with_allow_non_tls_accepts_a_cleartext_consumer(sources, tmp_path):
    """`allow_non_tls` lets one port take both, so a cleartext `iam` agrees.

    Without it the parent's own `validate.yaml` already refuses a one-sided
    NATS flip, so that red belongs to the parent's check, not to this gate.
    """
    platform = NATS_TLS_ON["platform"]["nats"]
    values = {
        **NATS_TLS_ON,
        "platform": {"nats": {**platform, "config": {**platform["config"], "merge": {"allow_non_tls": True}}}},
        "iam": {"nats": {"tls": {"enabled": False}}},
    }
    _, problems = gate(render(sources["example-values"] + overlay(tmp_path, values)))
    assert problems == []


def test_a_dependency_with_no_adapter_row_is_refused(renders):
    _, problems = edges_and_problems(renders["ci-values"], [*dependencies(), "newmodule"])
    assert any("newmodule" in p and "no row" in p for p in problems), problems


def test_an_unclaimed_dial_shaped_variable_is_refused(renders):
    documents = copied(renders)
    containers(find(documents, "Deployment", "task"))[0]["env"].append({"name": "IAM_HOST", "value": "iam"})
    _, problems = edges_and_problems(documents, dependencies())
    assert problems == ["task sets IAM_HOST, shaped like a dial, and no adapter or ENV_EXCLUSIONS entry claims it"]


def copied(renders) -> list[dict]:
    return yaml.safe_load(yaml.safe_dump(renders["ci-values"]))


def find(documents: list[dict], kind: str, name: str) -> dict:
    return next(d for d in documents if d["kind"] == kind and d["metadata"]["name"] == name)


def pod() -> dict:
    return {"metadata": {"labels": {}}, "spec": {"containers": [{"name": "main", "env": []}]}}


def test_an_unclaimed_workload_is_refused(renders):
    extra = {"kind": "Deployment", "metadata": {"name": "task-worker"}, "spec": {"template": pod()}}
    _, problems = edges_and_problems([*copied(renders), extra], dependencies())
    assert problems == ["Deployment task-worker is rendered and no ADAPTERS row or WORKLOAD_EXCLUSIONS entry claims it"]


@pytest.mark.parametrize("kind", ["CronJob", "DaemonSet"])
def test_an_unclaimed_cronjob_or_daemonset_is_refused(renders, kind):
    template = pod()
    spec = {"jobTemplate": {"spec": {"template": template}}} if kind == "CronJob" else {"template": template}
    extra = {"kind": kind, "metadata": {"name": "sweeper"}, "spec": spec}
    _, problems = edges_and_problems([*copied(renders), extra], dependencies())
    assert problems == [f"{kind} sweeper is rendered and no ADAPTERS row or WORKLOAD_EXCLUSIONS entry claims it"]


def test_a_dial_shaped_variable_set_through_value_from_is_refused(renders):
    documents = copied(renders)
    containers(find(documents, "Deployment", "task"))[0]["env"].append(
        {"name": "IAM_HOST", "valueFrom": {"configMapKeyRef": {"name": "elsewhere", "key": "host"}}}
    )
    _, problems = edges_and_problems(documents, dependencies())
    assert problems == [
        "task sets IAM_HOST through valueFrom, shaped like a dial, so the gate cannot read it, "
        "and no ENV_EXCLUSIONS entry claims it"
    ]


def test_a_dial_in_an_init_container_is_refused(renders):
    documents = copied(renders)
    task = find(documents, "Deployment", "task")
    task["spec"]["template"]["spec"]["initContainers"] = [{"name": "wait", "env": [{"name": "IAM_HOST", "value": "iam"}]}]
    _, problems = edges_and_problems(documents, dependencies())
    assert problems == ["task sets IAM_HOST, shaped like a dial, and no adapter or ENV_EXCLUSIONS entry claims it"]


@pytest.mark.parametrize("variable", ["IAM_ENDPOINT", "IAM_TARGET", "IAM_URI", "IAM_ADDRESS"])
def test_every_dial_suffix_is_seen(renders, variable):
    documents = copied(renders)
    containers(find(documents, "Deployment", "task"))[0]["env"].append({"name": variable, "value": "iam:50052"})
    _, problems = edges_and_problems(documents, dependencies())
    assert problems == [f"task sets {variable}, shaped like a dial, and no adapter or ENV_EXCLUSIONS entry claims it"]


def test_a_dial_added_to_an_excluded_workload_is_refused(renders):
    documents = copied(renders)
    preflight = find(documents, "Job", "preflight")
    containers(preflight)[0].setdefault("env", []).append({"name": "IAM_HOST", "value": "iam"})
    _, problems = edges_and_problems(documents, dependencies())
    assert problems == ["preflight sets IAM_HOST, shaped like a dial, and no adapter or ENV_EXCLUSIONS entry claims it"]


def nats_config(documents: list[dict]) -> dict:
    return find(documents, "ConfigMap", "nats-config")["data"]


def test_a_dollar_inside_a_nats_json_string_is_not_rewritten(renders):
    """A nats.conf string holding "a: $b" parses, and the string is kept as written.

    The string is written into the RENDERED ConfigMap, as the not-JSON case below
    does. Yaadgaar 597 refuses the key this probe used: `nats.config.merge` now
    takes only `authorization` (exactly the chart's own block) and
    `allow_non_tls`, and a `ca_file` must be a plain absolute path. A free string
    can still reach nats.conf through a non-bool `allow_non_tls` (refused only
    when `clientAuth` is `required`) and through the block merges
    (`nats.config.<block>.merge`); both are open holes
    (yaadgaar 592, 660), so this test does not pin itself to either. The
    property under test is the parser's: `nats_conf` keeps a `$` inside a string.
    """
    documents = copied(renders)
    data = nats_config(documents)
    assert data["nats.conf"].lstrip().startswith("{"), data["nats.conf"][:80]
    data["nats.conf"] = data["nats.conf"].replace("{", '{\n  "foo": "a: $b",', 1)
    conf = nats_conf(data["nats.conf"])
    assert isinstance(conf, dict), conf
    assert conf["foo"] == "a: $b"
    assert gate(documents)[1] == []


def test_a_nats_conf_that_is_not_json_fails_with_a_named_problem(renders):
    documents = copied(renders)
    data = nats_config(documents)
    data["nats.conf"] = "include extra.conf;\n" + data["nats.conf"]
    _, problems = gate(documents)
    assert problems == [f"gateway→nats:4222: {NATS_UNREADABLE}", f"iam→nats:4222: {NATS_UNREADABLE}"]


def test_zero_edges_is_refused():
    _, problems = gate([])
    assert "no edge was discovered: a gate over zero edges inspects nothing" in problems


# ── THE PARTIAL MARIADB EDGE (yaadgaar #542) ─────────────────────────────────

MARIADB_EDGES = frozenset({"iam-db→iam-db-mariadb:3306", "project-db→project-db-mariadb:3306", "task-db→task-db-mariadb:3306"})


def mariadb_cr(documents: list[dict], module: str) -> dict:
    return next(
        d for d in documents if d["kind"] == "MariaDB" and d["metadata"]["labels"]["app.kubernetes.io/name"] == module
    )


@pytest.mark.parametrize("name", sorted(DIAL_EDGES))
def test_every_db_module_dials_its_mariadb_cr(renders, name):
    edges, problems = mariadb_gate(renders[name])
    assert problems == [], "\n".join(problems)
    assert edges == MARIADB_EDGES


@pytest.mark.parametrize("module", ["iam-db", "project-db", "task-db"])
def test_a_db_host_that_is_not_the_mariadb_cr_name_is_named(renders, module):
    documents = copied(renders)
    set_env(documents, module, "DB_HOST", f"{module}-mariadb-typo")
    _, problems = mariadb_gate(documents)
    assert problems == [
        f"{module}: {MARIADB_HOST_MISMATCH}: DB_HOST is '{module}-mariadb-typo' and the MariaDB CR is named "
        f"'{module}-mariadb' ({module}.database.host)"
    ]


@pytest.mark.parametrize("module", ["iam-db", "project-db", "task-db"])
def test_a_db_port_that_is_not_the_cr_port_is_named(renders, module):
    documents = copied(renders)
    set_env(documents, module, "DB_PORT", "3307")
    _, problems = mariadb_gate(documents)
    assert problems == [
        f"{module}: {MARIADB_PORT_MISMATCH}: DB_PORT is 3307 and the MariaDB CR serves 3306 ({module}.database.port)"
    ]


def test_a_cr_port_the_dial_does_not_follow_is_named(renders):
    """The other direction: the CR moves to 3307 and DB_PORT stays at the 3306 default."""
    documents = copied(renders)
    mariadb_cr(documents, "task-db")["spec"]["port"] = 3307
    _, problems = mariadb_gate(documents)
    assert problems == [
        f"task-db: {MARIADB_PORT_MISMATCH}: DB_PORT is 3306 and the MariaDB CR serves 3307 (task-db.database.port)"
    ]


def test_a_cr_port_the_dial_follows_agrees(renders):
    documents = copied(renders)
    mariadb_cr(documents, "task-db")["spec"]["port"] = 3307
    set_env(documents, "task-db", "DB_PORT", "3307")
    edges, problems = mariadb_gate(documents)
    assert problems == []
    assert "task-db→task-db-mariadb:3307" in edges


def test_a_cr_that_requires_tls_with_a_dial_that_does_not_is_named(renders):
    documents = copied(renders)
    set_env(documents, "iam-db", "DB_SSL_MODE", "preferred")
    _, problems = mariadb_gate(documents)
    assert problems == [
        f"iam-db: {MARIADB_TLS_MISMATCH}: DB_SSL_MODE is 'preferred' and the MariaDB CR spec.tls.required is true "
        "(iam-db.database.sslMode)"
    ]


@pytest.mark.parametrize("tls", [{"enabled": True, "required": False}, {"enabled": True}, None])
def test_a_dial_that_requires_tls_of_a_cr_that_does_not_is_named(renders, tls):
    documents = copied(renders)
    spec = mariadb_cr(documents, "project-db")["spec"]
    spec.pop("tls")
    if tls is not None:
        spec["tls"] = tls
    _, problems = mariadb_gate(documents)
    assert problems == [
        f"project-db: {MARIADB_TLS_MISMATCH}: DB_SSL_MODE is 'required' and the MariaDB CR spec.tls.required is false "
        "(project-db.database.sslMode)"
    ]


def test_a_cr_that_does_not_require_tls_with_a_dial_that_does_not_agrees(renders):
    documents = copied(renders)
    mariadb_cr(documents, "task-db")["spec"]["tls"]["required"] = False
    set_env(documents, "task-db", "DB_SSL_MODE", "preferred")
    _, problems = mariadb_gate(documents)
    assert problems == []


def test_a_db_module_with_no_mariadb_cr_is_named(renders):
    documents = [d for d in copied(renders) if not (d["kind"] == "MariaDB" and d["metadata"]["name"] == "iam-db-mariadb")]
    _, problems = mariadb_gate(documents)
    assert problems == [f"iam-db: {MARIADB_CR_COUNT} app.kubernetes.io/name=iam-db, found 0"]


def test_a_db_module_with_two_mariadb_crs_is_named(renders):
    documents = copied(renders)
    twin = yaml.safe_load(yaml.safe_dump(mariadb_cr(documents, "iam-db")))
    twin["metadata"]["name"] = "iam-db-mariadb-twin"
    _, problems = mariadb_gate([*documents, twin])
    assert problems == [f"iam-db: {MARIADB_CR_COUNT} app.kubernetes.io/name=iam-db, found 2"]


def test_a_db_dial_the_render_does_not_set_is_named(renders):
    documents = copied(renders)
    container = containers(find(documents, "Deployment", "iam-db"))[0]
    container["env"] = [e for e in container["env"] if e["name"] != "DB_SSL_MODE"]
    _, problems = mariadb_gate(documents)
    assert problems == ["iam-db: the render does not set DB_SSL_MODE (iam-db.database.sslMode)"]


def test_a_mariadb_gate_over_nothing_is_refused():
    edges, problems = mariadb_gate([])
    assert edges == set()
    assert "no MariaDB edge was discovered: a gate over zero edges inspects nothing" in problems


def set_env(documents: list[dict], module: str, variable: str, value: str) -> None:
    for e in containers(find(documents, "Deployment", module))[0]["env"]:
        if e["name"] == variable:
            e["value"] = value
            return
    raise AssertionError(f"{module} has no {variable}")


def test_a_verify_identity_dial_against_a_cr_that_requires_tls_agrees(renders):
    documents = copied(renders)
    set_env(documents, "task-db", "DB_SSL_MODE", "verify-identity")
    _, problems = mariadb_gate(documents)
    assert problems == []


def test_a_verify_identity_dial_against_a_cr_that_does_not_require_tls_is_named(renders):
    documents = copied(renders)
    set_env(documents, "task-db", "DB_SSL_MODE", "verify-identity")
    mariadb_cr(documents, "task-db")["spec"]["tls"]["required"] = False
    _, problems = mariadb_gate(documents)
    assert problems == [
        f"task-db: {MARIADB_TLS_MISMATCH}: DB_SSL_MODE is 'verify-identity' and the MariaDB CR "
        "spec.tls.required is false (task-db.database.sslMode)"
    ]


def test_verify_identity_is_in_the_tls_required_set():
    assert MARIADB_TLS_REQUIRED_MODES == frozenset({"required", "verify-identity"})


@pytest.mark.parametrize("port", ["", "abc", "33o6", "-1"])
def test_a_db_port_that_is_not_an_integer_is_named(renders, port):
    documents = copied(renders)
    set_env(documents, "project-db", "DB_PORT", port)
    _, problems = mariadb_gate(documents)
    assert problems == [f"project-db: {MARIADB_PORT_NOT_INTEGER}: DB_PORT is '{port}' (project-db.database.port)"]
