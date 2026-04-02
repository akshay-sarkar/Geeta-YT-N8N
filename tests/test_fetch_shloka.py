import json, sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

def test_fetch_known_shloka(tmp_path):
    sample = [
        {"chapter_number": 2, "verse_number": 47,
         "text": "कर्मण्येवाधिकारस्ते",
         "transliteration": "karmanye vadhikaras te",
         "translation": "You have a right"},
        {"chapter_number": 1, "verse_number": 1,
         "text": "other", "transliteration": "other", "translation": "other"}
    ]
    dataset = tmp_path / "gita.json"
    dataset.write_text(json.dumps(sample), encoding="utf-8")

    from fetch_shloka import fetch_shloka
    result = fetch_shloka(chapter=2, verse=47, dataset_path=str(dataset))

    assert result["chapter_number"] == 2
    assert result["verse_number"] == 47
    assert result["text"] == "कर्मण्येवाधिकारस्ते"
    assert result["transliteration"] == "karmanye vadhikaras te"
    assert "translation" in result

def test_fetch_missing_shloka(tmp_path):
    dataset = tmp_path / "gita.json"
    dataset.write_text("[]", encoding="utf-8")

    from fetch_shloka import fetch_shloka
    with pytest.raises(ValueError, match="not found"):
        fetch_shloka(chapter=99, verse=99, dataset_path=str(dataset))
