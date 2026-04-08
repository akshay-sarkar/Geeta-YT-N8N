#!/usr/bin/env python3
"""State tracker for the Gita pipeline. Tracks current chapter/verse."""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
STATE_JSON = ROOT / "data" / "state.json"
GITA_JSON = ROOT / "data" / "gita.json"


def _load_gita() -> list:
    return json.loads(GITA_JSON.read_text(encoding="utf-8"))


def _read_state() -> dict:
    if not STATE_JSON.exists():
        state = {"chapter": 1, "verse": 2}
        STATE_JSON.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return state
    return json.loads(STATE_JSON.read_text(encoding="utf-8"))


def _write_state(state: dict) -> None:
    STATE_JSON.write_text(json.dumps(state, indent=2), encoding="utf-8")


def cmd_read() -> None:
    state = _read_state()
    print(json.dumps(state))


def cmd_advance() -> None:
    state = _read_state()
    if state.get("done"):
        return
    gita = _load_gita()
    ch, vs = state["chapter"], state["verse"]
    idx = next(
        (i for i, e in enumerate(gita) if e["chapter_number"] == ch and e["verse_number"] == vs),
        None,
    )
    if idx is None:
        raise ValueError(f"Verse ch{ch} v{vs} not found in gita.json")
    if idx + 1 >= len(gita):
        _write_state({"done": True})
    else:
        nxt = gita[idx + 1]
        _write_state({"chapter": nxt["chapter_number"], "verse": nxt["verse_number"]})


if __name__ == "__main__":
    commands = {"read": cmd_read, "advance": cmd_advance}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        print(f"Usage: {sys.argv[0]} {{read|advance}}", file=sys.stderr)
        sys.exit(1)
    commands[sys.argv[1]]()
