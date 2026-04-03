"""generate_audio.py — ElevenLabs + Gemini audio generation with permanent cache."""
from __future__ import annotations
import json, os, pathlib, re, subprocess, textwrap
import requests
from google import genai
from dotenv import load_dotenv

load_dotenv()

AUDIO_DIR = pathlib.Path("audio")
SUMMARIES_JSON = AUDIO_DIR / "summaries.json"


def _summary_key(chapter: int, verse: int) -> str:
    return f"ch{chapter:02d}_v{verse:03d}"


def _load_summaries_json() -> dict:
    if SUMMARIES_JSON.exists():
        try:
            return json.loads(SUMMARIES_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_summaries_json(chapter: int, verse: int, s1: str, s2: str) -> None:
    AUDIO_DIR.mkdir(exist_ok=True)
    cache = _load_summaries_json()
    cache[_summary_key(chapter, verse)] = {"v1": s1, "v2": s2}
    SUMMARIES_JSON.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def audio_path(chapter: int, verse: int, kind: str, ext: str = "mp3") -> pathlib.Path:
    """Return canonical cache path for an audio/text asset."""
    return AUDIO_DIR / f"ch{chapter:02d}_v{verse:03d}_{kind}.{ext}"


def parse_summaries(raw: str) -> tuple[str, str]:
    """Extract the two Hindi summaries from Claude's response.

    Expected format (flexible):
        Summary 1: <text>
        Summary 2: <text>
    Falls back to splitting on blank lines if markers are absent.
    """
    m1 = re.search(r"Summary\s*1\s*[:\-]\s*(.+?)(?=Summary\s*2|$)", raw, re.S | re.I)
    m2 = re.search(r"Summary\s*2\s*[:\-]\s*(.+?)$", raw, re.S | re.I)
    if m1 and m2:
        return m1.group(1).strip(), m2.group(1).strip()
    # Fallback: split on blank line
    parts = [p.strip() for p in raw.strip().split("\n\n") if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    raise ValueError(f"parse_summaries: expected 2 summaries, got 1. Raw: {raw[:200]!r}")


def call_gemini(prompt: str) -> str:
    """Call Gemini API and return the text response."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY is not set in environment or .env")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    return response.text


def generate_summaries(
    chapter: int,
    verse: int,
    sanskrit_text: str,
    translation: str,
    force: bool = False,
) -> tuple[str, str]:
    """Return (summary_v1, summary_v2). Cache-first: JSON → .txt files → Gemini API."""
    p1 = audio_path(chapter, verse, "summary_v1", ext="txt")
    p2 = audio_path(chapter, verse, "summary_v2", ext="txt")

    if not force:
        # 1. Check JSON cache first
        cache = _load_summaries_json()
        entry = cache.get(_summary_key(chapter, verse))
        if entry and entry.get("v1", "").strip() and entry.get("v2", "").strip():
            return entry["v1"], entry["v2"]

        # 2. Fall back to .txt files (backward compatibility)
        if p1.exists() and p2.exists():
            s1 = p1.read_text(encoding="utf-8")
            s2 = p2.read_text(encoding="utf-8")
            if s1.strip() and s2.strip():
                # Migrate into JSON so future lookups skip the .txt check
                _save_summaries_json(chapter, verse, s1, s2)
                return s1, s2

    prompt = textwrap.dedent(f"""
        You are writing spoken Hindi summaries for a YouTube Shorts video about the Bhagavad Gita.

        Shloka (Chapter {chapter}, Verse {verse}):
        Sanskrit: {sanskrit_text}
        Translation: {translation}

        Write TWO distinct Hindi summaries of this shloka. Each should be:
        - 2-3 natural spoken sentences (suitable for a voice-over)
        - Written in simple, modern Hindi (Devanagari script)
        - Capturing the spiritual essence, not a literal translation
        - Different in wording and emphasis from each other
        - Under 40 words each (keep it short for YouTube Shorts)

        Format your response exactly like this:
        Summary 1: <first summary in Hindi>
        Summary 2: <second summary in Hindi>
    """).strip()

    raw = call_gemini(prompt)
    s1, s2 = parse_summaries(raw)

    AUDIO_DIR.mkdir(exist_ok=True)
    p1.write_text(s1, encoding="utf-8")
    p2.write_text(s2, encoding="utf-8")
    _save_summaries_json(chapter, verse, s1, s2)

    return s1, s2


ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
ELEVENLABS_MODEL = "eleven_multilingual_v2"


def call_elevenlabs(
    text: str,
    voice_id: str,
    output_path: pathlib.Path,
    voice_settings: dict | None = None,
) -> None:
    """Call ElevenLabs TTS API and write MP3 to output_path."""
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise EnvironmentError("ELEVENLABS_API_KEY is not set in environment or .env")
    url = ELEVENLABS_API_URL.format(voice_id=voice_id)
    settings = voice_settings or {
        "stability": 0.75,
        "similarity_boost": 0.75,
        "style": 0.30,
        "use_speaker_boost": True,
    }
    payload = {
        "text": text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": settings,
    }
    resp = requests.post(
        url,
        json=payload,
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        timeout=60,
    )
    try:
        resp.raise_for_status()
    except Exception as exc:
        raise RuntimeError(
            f"ElevenLabs API error {resp.status_code}: {resp.text[:500]}"
        ) from exc
    output_path.write_bytes(resp.content)


def generate_speech(
    chapter: int,
    verse: int,
    kind: str,
    text: str,
    voice_id: str,
    mock_audio: bool = False,
    force: bool = False,
    voice_settings: dict | None = None,
) -> pathlib.Path:
    """Generate MP3 for the given text. Cache-first.

    kind: one of "sanskrit", "hindi_v1", "hindi_v2"
    mock_audio: use macOS `say` command instead of ElevenLabs (free, for dev/testing)
    voice_settings: optional ElevenLabs voice_settings dict; uses per-voice defaults if None
    """
    out = audio_path(chapter, verse, kind).resolve()
    if not force and out.exists():
        return out
    out.parent.mkdir(exist_ok=True)

    if mock_audio:
        tmp_aiff = out.with_suffix(".aiff")
        result = subprocess.run(
            ["say", "-o", str(tmp_aiff), text],
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"macOS say failed: {result.stderr.decode()}")
        convert = subprocess.run(
            ["afconvert", "-f", "mp4f", "-d", "aac", str(tmp_aiff), str(out)],
            capture_output=True,
        )
        if convert.returncode != 0:
            raise RuntimeError(f"afconvert failed: {convert.stderr.decode()}")
        tmp_aiff.unlink(missing_ok=True)
        if not out.exists():
            raise RuntimeError(f"mock audio generation succeeded but output not found: {out}")
    else:
        call_elevenlabs(text, voice_id, out, voice_settings)

    return out


# Voice IDs (from spec)
VOICE_TAKSH = "qDuRKMlYmrm8trt5QyBn"   # Sanskrit
VOICE_NIRAJ = "zgqefOY5FPQ3bB7OZTVR"   # Hindi

VOICE_SETTINGS_TAKSH = {"stability": 0.75, "similarity_boost": 0.75, "style": 0.30, "use_speaker_boost": True}
VOICE_SETTINGS_NIRAJ = {"stability": 0.60, "similarity_boost": 0.75, "style": 0.45, "use_speaker_boost": True}


def generate_audio_files(
    shloka: dict,
    summary_v1: str,
    summary_v2: str,
    mock: bool = False,
    force: bool = False,
) -> dict[str, str]:
    """Generate all 3 audio files for a shloka. Returns dict of absolute path strings.

    Returns:
        {"sanskrit": str, "hindi_v1": str, "hindi_v2": str}
    """
    ch = shloka["chapter_number"]
    vs = shloka["verse_number"]

    sanskrit_path = generate_speech(
        ch, vs, "sanskrit", shloka["text"], VOICE_TAKSH,
        mock_audio=mock, force=force, voice_settings=VOICE_SETTINGS_TAKSH,
    )
    hindi_v1_path = generate_speech(
        ch, vs, "hindi_v1", summary_v1, VOICE_NIRAJ,
        mock_audio=mock, force=force, voice_settings=VOICE_SETTINGS_NIRAJ,
    )
    hindi_v2_path = generate_speech(
        ch, vs, "hindi_v2", summary_v2, VOICE_NIRAJ,
        mock_audio=mock, force=force, voice_settings=VOICE_SETTINGS_NIRAJ,
    )

    return {
        "sanskrit": str(sanskrit_path),
        "hindi_v1": str(hindi_v1_path),
        "hindi_v2": str(hindi_v2_path),
    }
