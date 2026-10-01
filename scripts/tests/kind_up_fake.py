#!/usr/bin/env python3
"""One fake for every program `bootstrap/kind-up.sh` runs against the outside world.

`test_kind_up.py` symlinks this file under each name the script calls — `kubectl`,
`helm`, `kind`, `curl`, `podman`, `sysctl`, `id`, `apt-get`, `pipx`, `yaadgaar` —
into a directory it puts first on `PATH`. No real cluster, registry or gateway is
ever reached, and the host's own kubeconfig is never read: the test also points
`HOME` and `KUBECONFIG` at a scratch directory.

WHAT IT DOES, per call:

1. Appends `{"cmd", "argv", "stdin", "data"}` to `$FAKE_DIR/calls.jsonl`. `stdin` is read
   only for `curl --config -` and `yaadgaar ... --password-stdin`, the two places
   the script hands over a secret. Recording it is the POSITIVE CONTROL of the
   secret tests: the secret did reach its consumer, just never through argv,
   stdout or the log.
2. Finds the first rule in `$FAKE_DIR/rules.json` whose `cmd` equals this name
   and whose every `match` substring occurs in the joined argv.
3. Writes the rule's `stdout`, writes `o_content` to the path after `-o` if both
   exist, writes `write_content` to the path after the flag `write_arg` names,
   and exits with `exit` (default 0). `stdout` and `exit` may each be a list,
   consumed one entry per call to that rule, the last repeating.

No rule matches: exit 0 with no output. The tests assert on `calls.jsonl`, so an
unexpected call is caught there rather than by the fake refusing it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    name = Path(sys.argv[0]).name
    argv = sys.argv[1:]
    fake_dir = Path(os.environ["FAKE_DIR"])
    joined = " ".join(argv)

    stdin = None
    reads_stdin = (name == "curl" and "--config" in argv and "-" in argv) or (
        name == "yaadgaar" and "--password-stdin" in argv
    )
    if reads_stdin:
        stdin = sys.stdin.read()

    # A request body passed as `--data-binary @file` is recorded by content: the
    # script deletes the file once curl returns.
    data = None
    if "--data-binary" in argv:
        ref = argv[argv.index("--data-binary") + 1]
        data = Path(ref[1:]).read_text(encoding="utf-8") if ref.startswith("@") else ref

    with (fake_dir / "calls.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"cmd": name, "argv": argv, "stdin": stdin, "data": data}) + "\n")

    rules = json.loads((fake_dir / "rules.json").read_text(encoding="utf-8"))
    for index, rule in enumerate(rules):
        if rule["cmd"] != name:
            continue
        if not all(m in joined for m in rule.get("match", [])):
            continue
        counter = fake_dir / f"counter-{index}"
        n = int(counter.read_text()) if counter.exists() else 0
        counter.write_text(str(n + 1))

        def nth(value):
            return value[min(n, len(value) - 1)] if isinstance(value, list) else value

        out = nth(rule.get("stdout", ""))
        if "o_content" in rule and "-o" in argv:
            Path(argv[argv.index("-o") + 1]).write_text(rule["o_content"], encoding="utf-8")
        # `write_arg`: write `write_content` to the path after that flag, the way
        # `kind export kubeconfig --kubeconfig <path>` writes its file.
        if "write_arg" in rule and rule["write_arg"] in argv:
            Path(argv[argv.index(rule["write_arg"]) + 1]).write_text(rule["write_content"], encoding="utf-8")
        sys.stdout.write(out)
        sys.stderr.write(rule.get("stderr", ""))
        return int(nth(rule.get("exit", 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
