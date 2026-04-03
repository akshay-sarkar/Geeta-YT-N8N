import sys, os, json, pathlib, types
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "tools"))

def test_audio_path_format():
    from generate_audio import audio_path
    p = audio_path(2, 47, "sanskrit")
    assert p == pathlib.Path("audio/ch02_v047_sanskrit.mp3")

def test_audio_path_txt():
    from generate_audio import audio_path
    p = audio_path(2, 47, "summary_v1", ext="txt")
    assert p == pathlib.Path("audio/ch02_v047_summary_v1.txt")

def test_parse_two_summaries():
    from generate_audio import parse_summaries
    raw = "Summary 1: अर्जुन को कर्म करना चाहिए।\nSummary 2: कर्म ही पूजा है।"
    s1, s2 = parse_summaries(raw)
    assert "अर्जुन" in s1
    assert "कर्म" in s2

def test_summary_cache_hit_skips_gemini(tmp_path, monkeypatch):
    from generate_audio import generate_summaries
    monkeypatch.chdir(tmp_path)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    (audio_dir / "ch02_v047_summary_v1.txt").write_text("पहली सारांश", encoding="utf-8")
    (audio_dir / "ch02_v047_summary_v2.txt").write_text("दूसरी सारांश", encoding="utf-8")

    called = []
    def fake_gemini(*a, **kw):
        called.append(1)
    monkeypatch.setattr("generate_audio.call_gemini", fake_gemini)

    s1, s2 = generate_summaries(2, 47, "Sanskrit text", "word meanings")
    assert s1 == "पहली सारांश"
    assert s2 == "दूसरी सारांश"
    assert called == [], "Gemini must not be called when cache files exist"


def test_generate_speech_cache_hit_skips_elevenlabs(tmp_path, monkeypatch):
    from generate_audio import generate_speech
    monkeypatch.chdir(tmp_path)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    (audio_dir / "ch02_v047_sanskrit.mp3").write_bytes(b"fake-mp3-data")

    called = []
    def fake_elevenlabs(*a, **kw):
        called.append(1)
    monkeypatch.setattr("generate_audio.call_elevenlabs", fake_elevenlabs)

    result = generate_speech(2, 47, "sanskrit", "text", "voice-id", mock_audio=False)
    assert result == audio_dir / "ch02_v047_sanskrit.mp3"
    assert called == [], "ElevenLabs must not be called when cache file exists"

def test_generate_speech_mock_uses_say(tmp_path, monkeypatch):
    from generate_audio import generate_speech
    monkeypatch.chdir(tmp_path)
    (tmp_path / "audio").mkdir()

    say_calls = []
    def fake_spawn(cmd, *a, **kw):
        say_calls.append(cmd)
        # When afconvert is called, write the expected output file so the
        # out.exists() guard passes.
        if cmd[0] == "afconvert":
            pathlib.Path(cmd[-1]).write_bytes(b"fake-mp3-data")
        return type("R", (), {"returncode": 0})()
    monkeypatch.setattr("generate_audio.subprocess.run", fake_spawn)

    result = generate_speech(2, 47, "sanskrit", "Sanskrit text", "voice-id", mock_audio=True)
    assert result == tmp_path / "audio" / "ch02_v047_sanskrit.mp3"
    assert say_calls and say_calls[0][0] == "say", "mock mode must call macOS say as first arg"
