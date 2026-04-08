import json
import pathlib
import pytest
import tools.youtube_metadata as yt_mod


SAMPLE_GITA = [
    {"chapter_number": 1, "verse_number": 1, "text": "line1\nline2"},
    {"chapter_number": 1, "verse_number": 2, "text": "verse2\ntext"},
    {"chapter_number": 2, "verse_number": 1, "text": "ch2\nv1"},
]

SAMPLE_GAMBH = [
    {"verse_id": 1, "authorName": "Swami Gambirananda", "description": "meaning1\nmore"},
    {"verse_id": 2, "authorName": "Swami Gambirananda", "description": "meaning2"},
    {"verse_id": 3, "authorName": "Swami Gambirananda", "description": "meaning ch2 v1"},
]

OTHER_AUTHORS = [
    {"verse_id": 1, "authorName": "Other Author", "description": "other meaning"},
    {"verse_id": 2, "authorName": "Other Author", "description": "other meaning 2"},
    {"verse_id": 3, "authorName": "Other Author", "description": "other meaning 3"},
]


def _make_gita_file(path, entries):
    path.write_text(json.dumps(entries), encoding="utf-8")


def _make_translation_file(path, gambh_entries, extra_entries=None):
    all_entries = list(gambh_entries) + (extra_entries or [])
    path.write_text(json.dumps(all_entries), encoding="utf-8")


@pytest.fixture
def data_files(tmp_path, monkeypatch):
    gita_file = tmp_path / "gita.json"
    trans_file = tmp_path / "translation.json"
    _make_gita_file(gita_file, SAMPLE_GITA)
    _make_translation_file(trans_file, SAMPLE_GAMBH, OTHER_AUTHORS)
    monkeypatch.setattr(yt_mod, "GITA_JSON", gita_file)
    monkeypatch.setattr(yt_mod, "TRANSLATION_JSON", trans_file)
    return gita_file, trans_file


def test_title_format(data_files):
    result = yt_mod.generate_metadata(1, 1)
    assert result["title"] == "Bhagavad Gita - Adhyay 1 Shloka 1"


def test_title_different_chapter(data_files):
    result = yt_mod.generate_metadata(2, 1)
    assert result["title"] == "Bhagavad Gita - Adhyay 2 Shloka 1"


def test_shloka_newlines_removed(data_files):
    result = yt_mod.generate_metadata(1, 1)
    assert "\n" not in result["description"].split("\n\nMeaning:")[0]
    assert "line1 line2" in result["description"]


def test_meaning_newlines_removed(data_files):
    result = yt_mod.generate_metadata(1, 1)
    assert "meaning1 more" in result["description"]


def test_description_structure(data_files):
    result = yt_mod.generate_metadata(1, 1)
    desc = result["description"]
    assert desc.startswith("Shloka: ")
    assert "\n\nMeaning: " in desc
    assert desc.endswith("#BhagavadGita #GitaShlokas #Krishna #Adhyay1")


def test_hashtag_uses_chapter_number(data_files):
    result = yt_mod.generate_metadata(2, 1)
    assert "#Adhyay2" in result["description"]


def test_invalid_verse_raises(data_files):
    with pytest.raises(ValueError):
        yt_mod.generate_metadata(99, 99)
