"""generate_audio.py — Gemini TTS + Gemini text generation with permanent cache."""
from __future__ import annotations
import json, os, pathlib, re, subprocess, textwrap
from google import genai
from google.genai import types
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
    """Extract the two Hindi summaries from Gemini's response.

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


GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"


def call_gemini_tts(text: str, voice_name: str, output_path: pathlib.Path) -> None:
    """Call Gemini TTS API and write MP3 to output_path."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY is not set in environment or .env")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=GEMINI_TTS_MODEL,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                )
            ),
        ),
    )
    candidate = response.candidates[0]
    if str(candidate.finish_reason) == "FinishReason.OTHER":
        raise RuntimeError(
            f"Gemini TTS returned FinishReason.OTHER for voice {voice_name!r} — "
            "voice may not support this script/language"
        )
    part = candidate.content.parts[0]
    if not hasattr(part, "inline_data") or not part.inline_data:
        raise RuntimeError(f"Gemini TTS returned no audio data for voice {voice_name!r}")
    pcm = part.inline_data.data
    proc = subprocess.run(
        ["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", "pipe:0", str(output_path)],
        input=pcm,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg PCM→MP3 conversion failed: {proc.stderr.decode()}")


def generate_speech(
    chapter: int,
    verse: int,
    kind: str,
    text: str,
    voice_name: str,
    mock_audio: bool = False,
    force: bool = False,
) -> pathlib.Path:
    """Generate MP3 for the given text. Cache-first.

    kind: one of "sanskrit", "hindi_v1", "hindi_v2"
    mock_audio: use macOS `say` command instead of Gemini TTS (free, for dev/testing)
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
        call_gemini_tts(text, voice_name, out)

    return out


# Voice names (Gemini TTS)
VOICE_SANSKRIT = "Callirrhoe"  # Sanskrit recitation
VOICE_HINDI = "Leda"           # Hindi narration


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
        ch, vs, "sanskrit", shloka["text"], VOICE_SANSKRIT,
        mock_audio=mock, force=force,
    )
    hindi_v1_path = generate_speech(
        ch, vs, "hindi_v1", summary_v1, VOICE_HINDI,
        mock_audio=mock, force=force,
    )
    hindi_v2_path = generate_speech(
        ch, vs, "hindi_v2", summary_v2, VOICE_HINDI,
        mock_audio=mock, force=force,
    )

    return {
        "sanskrit": str(sanskrit_path),
        "hindi_v1": str(hindi_v1_path),
        "hindi_v2": str(hindi_v2_path),
    }
