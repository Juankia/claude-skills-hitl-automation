"""Shared client state store used by every skill in this repository.

A single, versioned JSON document holds the client records produced by
``client-intake`` and the artifacts that later skills attach to them
(drafted documents, filing-prep reports). Keeping it as one small JSON file
makes it trivially inspectable by a human reviewer and by Claude itself.

Design notes
------------
* **Cross-platform location.** The default directory follows each OS's
  convention (``%APPDATA%`` on Windows, ``~/Library/Application Support`` on
  macOS, ``$XDG_DATA_HOME`` elsewhere). ``CLIENT_SKILLS_HOME`` overrides it,
  which is also what the test-suite uses.
* **Atomic writes.** Data is written to a temp file in the same directory and
  moved into place with ``os.replace`` so a crash never leaves half a file.
* **Schema version + migrations.** ``SCHEMA_VERSION`` is stored in the file;
  older files are migrated forward on load, newer files are refused.

Only the Python standard library is used so the module can be vendored into
any skill folder as-is.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = 2
STATE_FILENAME = "state.json"
APP_DIR_NAME = "ClientSkills"
ENV_HOME = "CLIENT_SKILLS_HOME"


class StateError(RuntimeError):
    """Raised for unreadable, unknown-version or inconsistent state files."""


def default_state_dir(platform: str | None = None, env: dict[str, str] | None = None) -> Path:
    """Return the OS-appropriate directory for the shared state file."""
    env = dict(os.environ) if env is None else env
    platform = platform or sys.platform

    override = env.get(ENV_HOME)
    if override:
        return Path(override).expanduser()

    home = Path(env.get("HOME") or env.get("USERPROFILE") or Path.home())
    if platform.startswith("win"):
        base = env.get("APPDATA") or str(home / "AppData" / "Roaming")
        return Path(base) / APP_DIR_NAME
    if platform == "darwin":
        return home / "Library" / "Application Support" / APP_DIR_NAME
    xdg = env.get("XDG_DATA_HOME") or str(home / ".local" / "share")
    return Path(xdg) / APP_DIR_NAME.lower()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _empty_state() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "updated_at": None, "clients": {}}


# --- migrations -----------------------------------------------------------
# Each migration takes a state dict at version N and returns it at N + 1.

def _migrate_1_to_2(state: dict[str, Any]) -> dict[str, Any]:
    """v1 stored clients as a list; v2 keys them by client_id and adds artifacts."""
    clients = state.get("clients", [])
    if isinstance(clients, list):
        state["clients"] = {c["client_id"]: c for c in clients}
    for client in state["clients"].values():
        client.setdefault("artifacts", {"documents": [], "filing_reports": []})
    state["schema_version"] = 2
    return state


MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {1: _migrate_1_to_2}


def migrate(state: dict[str, Any]) -> dict[str, Any]:
    version = state.get("schema_version", 1)
    if not isinstance(version, int):
        raise StateError(f"Invalid schema_version: {version!r}")
    if version > SCHEMA_VERSION:
        raise StateError(
            f"State file uses schema v{version}, this tool only understands up to v{SCHEMA_VERSION}. "
            "Upgrade the skills before continuing."
        )
    while version < SCHEMA_VERSION:
        state = MIGRATIONS[version](state)
        version = state["schema_version"]
    return state


class ClientStateStore:
    """Small JSON-backed store for client records and their artifacts."""

    def __init__(self, directory: str | os.PathLike[str] | None = None) -> None:
        self.directory = Path(directory) if directory else default_state_dir()
        self.path = self.directory / STATE_FILENAME

    # -- persistence -------------------------------------------------------
    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return _empty_state()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StateError(f"State file {self.path} is not valid JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise StateError(f"State file {self.path} must contain a JSON object")
        return migrate(raw)

    def save(self, state: dict[str, Any]) -> None:
        state["schema_version"] = SCHEMA_VERSION
        state["updated_at"] = utc_now()
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".state-", suffix=".json", dir=self.directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(state, fh, indent=2, sort_keys=True, ensure_ascii=False)
                fh.write("\n")
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    # -- client records ----------------------------------------------------
    def upsert_client(self, record: dict[str, Any]) -> dict[str, Any]:
        state = self.load()
        client_id = record["client_id"]
        existing = state["clients"].get(client_id)
        stored = dict(record)
        stored["artifacts"] = (existing or {}).get("artifacts") or {"documents": [], "filing_reports": []}
        stored["created_at"] = (existing or {}).get("created_at") or utc_now()
        stored["updated_at"] = utc_now()
        state["clients"][client_id] = stored
        self.save(state)
        return stored

    def get_client(self, client_id: str) -> dict[str, Any]:
        clients = self.load()["clients"]
        if client_id not in clients:
            known = ", ".join(sorted(clients)) or "none"
            raise StateError(f"Unknown client_id {client_id!r} (known: {known})")
        return clients[client_id]

    def list_clients(self) -> list[dict[str, Any]]:
        return sorted(self.load()["clients"].values(), key=lambda c: c["client_id"])

    def add_artifact(self, client_id: str, kind: str, entry: dict[str, Any]) -> None:
        if kind not in ("documents", "filing_reports"):
            raise ValueError(f"Unsupported artifact kind: {kind}")
        state = self.load()
        if client_id not in state["clients"]:
            raise StateError(f"Unknown client_id {client_id!r}")
        record = dict(entry, recorded_at=utc_now())
        state["clients"][client_id]["artifacts"][kind].append(record)
        self.save(state)


def _cli(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Inspect the shared client state store.")
    parser.add_argument("command", choices=["path", "list", "show"])
    parser.add_argument("client_id", nargs="?")
    args = parser.parse_args(argv)
    store = ClientStateStore()
    if args.command == "path":
        print(store.path)
    elif args.command == "list":
        for c in store.list_clients():
            print(f"{c['client_id']}\t{c['client']['legal_name']}\t{c['matter']['jurisdiction']}")
    else:
        if not args.client_id:
            parser.error("show requires a client_id")
        print(json.dumps(store.get_client(args.client_id), indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli())
