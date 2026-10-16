"""INT-538 test doubles for scripts/ops/staff_user.sh: aws, docker and openssl.

Each tool is a two-line shell wrapper on ``PATH`` that execs this file with the tool's name, so
nothing reaches AWS, Docker or a real Keycloak (``sleep`` is a wrapper that only logs). State
lives in ``$FAKE_STATE``:

- ``calls.jsonl``: one ``{"tool", "argv", "stdin"}`` line per call, so a test can show that no
  argv carried a secret, and which secrets travelled on stdin instead;
- ``params.json``: the SSM parameter store, name -> ``{"Type", "Value"}``;
- ``keycloak.json``: the realm (users with id, username, email, attributes, roles, credential),
  the bootstrap admin password, and ``fail``, the kcadm verb that should fail;
- ``container/``: the Keycloak container's file system, where kcadm's ``--config`` files live;
- ``invocations.json``: every send-command, with its parameters, status, stdout and stderr.

``send-command`` runs the command text with ``sh``, as AWS-RunShellScript does, with the same
``PATH``, so the host half meets the same fakes. ``$FAKE_HOST`` set to a status instead skips the
run and reports that status with no output (a host that never answers, or fails silently).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

STATE = Path(os.environ["FAKE_STATE"])
CONTAINER = os.environ.get("FAKE_CONTAINER_NAME", "intake-staging-keycloak-1")
KCADM = "/opt/keycloak/bin/kcadm.sh"
#: kcadm options that take a value; -s and -q may repeat.
VALUED = {"--config", "-r", "--fields", "--format", "--uid", "--rolename", "-f", "-s", "-q"}
FLAGS = {"--noquotes", "-i", "-n"}


def _load(name: str, default: Any) -> Any:
    path = STATE / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _save(name: str, value: Any) -> None:
    (STATE / name).write_text(json.dumps(value, indent=1), encoding="utf-8")


def _log(tool: str, argv: list[str], stdin: str = "") -> None:
    with (STATE / "calls.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"tool": tool, "argv": argv, "stdin": stdin}) + "\n")


def _fail(message: str, code: int = 1) -> NoReturn:
    sys.stderr.write(message + "\n")
    sys.exit(code)


def _opt(argv: list[str], name: str) -> str | None:
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None


# --- aws -----------------------------------------------------------------------------------------


def _read_file_arg(value: str | None) -> Any:
    if value is None or not value.startswith("file://"):
        _fail("fake aws: expected file://<path>", 252)
    path = Path(value.removeprefix("file://"))
    if not path.is_file():
        # the real CLI reads a parameter file twice, so a pipe arrives empty the second time
        _fail(f"Error parsing parameter: Unable to load paramfile {value}", 255)
    return json.loads(path.read_text(encoding="utf-8"))


def aws(argv: list[str]) -> None:
    _log("aws", argv)
    if argv[:1] != ["ssm"] or len(argv) < 2:
        _fail("fake aws: only ssm is faked", 255)
    verb = argv[1]
    if verb in os.environ.get("FAKE_AWS_DENY", "").split(","):
        _fail(
            "An error occurred (ExpiredTokenException): The security token included has expired",
            254,
        )
    params: dict[str, dict[str, str]] = _load("params.json", {})
    invocations: dict[str, dict[str, Any]] = _load("invocations.json", {})
    if verb == "put-parameter":
        request = _read_file_arg(_opt(argv, "--cli-input-json"))
        name = request["Name"]
        if name in params and not request.get("Overwrite"):
            _fail(
                "An error occurred (ParameterAlreadyExists) when calling the PutParameter "
                "operation: The parameter already exists. To overwrite this request value, "
                "set the overwrite option in the request to true.",
                254,
            )
        params[name] = {"Type": request["Type"], "Value": request["Value"]}
        _save("params.json", params)
        print('{"Version": 1, "Tier": "Standard"}')
    elif verb == "get-parameter":
        name = _opt(argv, "--name") or ""
        if name not in params:
            _fail(
                "An error occurred (ParameterNotFound) when calling the GetParameter operation:",
                254,
            )
        if "--with-decryption" not in argv or _opt(argv, "--query") != "Parameter.Value":
            _fail("fake aws: get-parameter is only faked with decryption and the value query", 252)
        print(params[name]["Value"])
    elif verb == "delete-parameter":
        name = _opt(argv, "--name") or ""
        if name not in params:
            _fail(
                "An error occurred (ParameterNotFound) when calling the DeleteParameter operation:",
                254,
            )
        del params[name]
        _save("params.json", params)
    elif verb == "send-command":
        body = _read_file_arg(_opt(argv, "--parameters"))
        command_id = f"cmd-{len(invocations) + 1:04d}"
        record: dict[str, Any] = {
            "instance": _opt(argv, "--instance-ids"),
            "document": _opt(argv, "--document-name"),
            "parameters": body,
            "status": os.environ.get("FAKE_HOST", "run"),
            "stdout": "",
            "stderr": "",
        }
        if record["status"] == "run":
            done = subprocess.run(
                ["sh", "-c", "\n".join(body["commands"])],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                check=False,
            )
            record.update(
                status="Success" if done.returncode == 0 else "Failed",
                stdout=done.stdout,
                stderr=done.stderr,
            )
        invocations[command_id] = record
        _save("invocations.json", invocations)
        print(command_id)
    elif verb == "get-command-invocation":
        record = invocations[_opt(argv, "--command-id") or ""]
        query = _opt(argv, "--query")
        if query == "Status":
            print(record["status"])
        elif query == "StandardOutputContent":
            sys.stdout.write(record["stdout"])
        else:
            _fail(f"fake aws: query {query} is not faked", 252)
    else:
        _fail(f"fake aws: ssm {verb} is not faked", 252)


# --- docker exec into the Keycloak container -----------------------------------------------------


def _inside(path: str) -> Path:
    if not path.startswith("/") or ".." in path.split("/"):
        _fail(f"fake docker: refused path {path}")
    return STATE / "container" / path.lstrip("/")


def _kcadm_args(tokens: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    positional: list[str] = []
    options: dict[str, list[str]] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in VALUED:
            options.setdefault(token, []).append(tokens[index + 1])
            index += 2
        elif token in FLAGS:
            options.setdefault(token, []).append("")
            index += 1
        elif token.startswith("-") and token != "-":
            _fail(f"fake kcadm: unknown option {token}")
        else:
            positional.append(token)
            index += 1
    return positional, options


def _set_field(user: dict[str, Any], assignment: str) -> None:
    key, _, raw = assignment.partition("=")
    value: Any = json.loads(raw) if raw[:1] in "[{" or raw in ("true", "false") else raw
    target = user
    *parents, leaf = key.split(".")
    for parent in parents:
        target = target.setdefault(parent, {})
    target[leaf] = value


def kcadm(tokens: list[str], stdin: str) -> None:
    realm: dict[str, Any] = _load("keycloak.json", {"users": []})
    users: list[dict[str, Any]] = realm["users"]
    verb, rest = tokens[0], tokens[1:]
    positional, options = _kcadm_args(rest)
    config = options.get("--config", [""])[0]
    if not config or not _inside(config).is_file():
        _fail("Logon is required: no session in the --config file", 1)
    if options.get("-r") != ["intake"]:
        _fail("fake kcadm: every call names -r intake")
    if realm.get("fail") == verb:
        _fail(f"fake kcadm: {verb} failed (HTTP 500)")
    resource = positional[0] if positional else ""
    csv = options.get("--format") == ["csv"] and "--noquotes" in options
    if verb == "get" and resource == "users":
        query = dict(q.split("=", 1) for q in options.get("-q", []))
        if query.pop("exact", None) != "true" or len(query) != 1 or not csv:
            _fail("fake kcadm: users are looked up by one exact field, as csv")
        ((field, value),) = query.items()
        for user in users:
            if user.get(field) == value:
                print(user["username"])
    elif verb == "get" and resource == "roles/platform_owner/users":
        if options.get("--fields") != ["id"] or not csv:
            _fail("fake kcadm: role members are listed by id, as csv")
        for user in users:
            if "platform_owner" in user.get("roles", []):
                print(user["id"])
    elif verb == "get" and resource.startswith("users/"):
        user = next((u for u in users if u["id"] == resource.split("/")[1]), None)
        if user is None:
            _fail("Resource not found for url", 1)
        print(json.dumps({"attributes": user.get("attributes", {})}, indent=2))
    elif verb == "create" and resource == "users":
        user = {"id": f"0000-{len(users) + 1:04d}", "roles": []}
        for assignment in options.get("-s", []):
            _set_field(user, assignment)
        if any(
            u["username"] == user["username"] or u.get("email") == user.get("email") for u in users
        ):
            _fail("Conflict detected. See logs for details", 1)
        users.append(user)
        _save("keycloak.json", realm)
        if "-i" in options:
            print(user["id"])
    elif verb == "add-roles":
        user = next(u for u in users if u["id"] == options["--uid"][0])
        user["roles"].extend(options["--rolename"])
        _save("keycloak.json", realm)
    elif verb == "update" and resource.endswith("/reset-password"):
        if "-n" not in options or options.get("-f") != ["-"]:
            _fail("fake kcadm: reset-password is a PUT without GET, body on stdin")
        user = next(u for u in users if u["id"] == resource.split("/")[1])
        user["credential"] = json.loads(stdin)
        _save("keycloak.json", realm)
    elif verb == "delete" and resource.startswith("users/"):
        realm["users"] = [u for u in users if u["id"] != resource.split("/")[1]]
        _save("keycloak.json", realm)
    else:
        _fail(f"fake kcadm: {verb} {resource} is not faked")


def docker(argv: list[str]) -> None:
    rest = argv[1:] if argv[:1] == ["exec"] else _fail("fake docker: only exec is faked")
    interactive = rest[:1] == ["-i"]
    if interactive:
        rest = rest[1:]
    stdin = sys.stdin.read() if interactive else ""
    _log("docker", argv, stdin)
    if not rest or rest[0] != CONTAINER:
        _fail(f"Error response from daemon: No such container: {rest[0] if rest else ''}")
    command = rest[1:]
    if command[:1] == ["mkdir"]:
        _inside(command[-1]).mkdir(mode=0o700)
    elif command[:1] == ["rm"]:
        shutil.rmtree(_inside(command[-1]), ignore_errors=True)
    elif command[:2] == ["bash", "-c"] and interactive:
        script, config = command[2], command[-1]
        expected = (
            "KC_CLI_PASSWORD",
            "config credentials",
            "--realm master",
            "--user intake-bootstrap",
        )
        if not all(part in script for part in expected):
            _fail("fake docker: not the kcadm login this fake knows")
        realm = _load("keycloak.json", {})
        if stdin.rstrip("\n") != realm.get("bootstrap_password"):
            _fail("Invalid user credentials [invalid_grant]", 1)
        _inside(config).write_text("session tokens", encoding="utf-8")
    elif command[:1] == [KCADM]:
        kcadm(command[1:], stdin)
    else:
        _fail(f"fake docker: {' '.join(command[:2])} is not faked")


# --- openssl -------------------------------------------------------------------------------------


def openssl(argv: list[str]) -> None:
    _log("openssl", argv)
    if argv != ["rand", "-hex", "32"]:
        _fail("fake openssl: only `rand -hex 32` is faked")
    print(os.environ["FAKE_OPENSSL_VALUE"])


def main() -> None:
    tool, argv = sys.argv[1], sys.argv[2:]
    {"aws": aws, "docker": docker, "openssl": openssl}[tool](argv)


if __name__ == "__main__":
    main()
