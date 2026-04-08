import json
import pytest
import tools.state as state_mod


def _make_gita(entries):
    """entries: list of (chapter_number, verse_number)"""
    return [{"chapter_number": ch, "verse_number": vs} for ch, vs in entries]


def _write_json(path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_read_creates_initial_state_if_missing(tmp_path, monkeypatch, capsys):
    # state.json absent → should create + print {"chapter": 1, "verse": 2}
    gita_file = tmp_path / "gita.json"
    gita_file.write_text(json.dumps(_make_gita([(1, 1), (1, 2), (1, 3)])), encoding="utf-8")
    monkeypatch.setattr(state_mod, "GITA_JSON", gita_file)
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(state_mod, "STATE_JSON", state_file)

    state_mod.cmd_read()

    out = capsys.readouterr().out.strip()
    assert json.loads(out) == {"chapter": 1, "verse": 2}
    assert state_file.exists()


def test_read_returns_done_state(tmp_path, monkeypatch, capsys):
    state_file = tmp_path / "state.json"
    _write_json(state_file, {"done": True})
    monkeypatch.setattr(state_mod, "STATE_JSON", state_file)

    state_mod.cmd_read()

    out = capsys.readouterr().out.strip()
    assert json.loads(out) == {"done": True}


def test_advance_increments_verse(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    gita_file = tmp_path / "gita.json"
    _write_json(state_file, {"chapter": 1, "verse": 2})
    _write_json(gita_file, _make_gita([(1, 1), (1, 2), (1, 3)]))
    monkeypatch.setattr(state_mod, "STATE_JSON", state_file)
    monkeypatch.setattr(state_mod, "GITA_JSON", gita_file)

    state_mod.cmd_advance()

    assert _read_json(state_file) == {"chapter": 1, "verse": 3}


def test_advance_wraps_to_next_chapter(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    gita_file = tmp_path / "gita.json"
    _write_json(state_file, {"chapter": 1, "verse": 3})
    _write_json(gita_file, _make_gita([(1, 1), (1, 2), (1, 3), (2, 1)]))
    monkeypatch.setattr(state_mod, "STATE_JSON", state_file)
    monkeypatch.setattr(state_mod, "GITA_JSON", gita_file)

    state_mod.cmd_advance()

    assert _read_json(state_file) == {"chapter": 2, "verse": 1}


def test_advance_marks_done_at_last_verse(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    gita_file = tmp_path / "gita.json"
    _write_json(state_file, {"chapter": 1, "verse": 3})
    _write_json(gita_file, _make_gita([(1, 1), (1, 2), (1, 3)]))
    monkeypatch.setattr(state_mod, "STATE_JSON", state_file)
    monkeypatch.setattr(state_mod, "GITA_JSON", gita_file)

    state_mod.cmd_advance()

    assert _read_json(state_file) == {"done": True}


def test_advance_on_done_is_noop(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    gita_file = tmp_path / "gita.json"
    _write_json(state_file, {"done": True})
    _write_json(gita_file, _make_gita([(1, 1), (1, 2)]))
    monkeypatch.setattr(state_mod, "STATE_JSON", state_file)
    monkeypatch.setattr(state_mod, "GITA_JSON", gita_file)

    state_mod.cmd_advance()

    assert _read_json(state_file) == {"done": True}
