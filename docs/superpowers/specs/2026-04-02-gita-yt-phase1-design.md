# Phase 1 Design — Gita Shlokas YouTube Automation

**Date:** 2026-04-02
**Scope:** Phase 1 Foundation — Shloka dataset + ElevenLabs audio + FFmpeg video compositor
**Status:** Approved

---

## Overview

Build three standalone tools and one coordinator that produce 4 review-ready MP4 videos for any given Bhagavad Gita shloka. Each tool is independently testable. No N8N wiring in this phase — the coordinator is the pipeline.

**Output per shloka:** 4 videos × 700 shlokas = 2,800 videos total
**Estimated cost per shloka:** 3 ElevenLabs calls + 2 Claude API calls (~$0.002)
**Environment:** macOS, local machine

---

## Architecture

```
tools/
  fetch_shloka.py       # reads dataset → returns shloka object
  generate_audio.py     # ElevenLabs API + Claude API → cached audio + summaries
  build_video.js        # FFmpeg compositor → MP4
  run_phase1.py         # coordinator: chains all three tools

data/
  gita.json             # full 700-shloka dataset (downloaded once)

audio/                  # permanent cache — never deleted
  ch02_v47_sanskrit.mp3
  ch02_v47_hindi_v1.mp3
  ch02_v47_hindi_v2.mp3
  ch02_v47_summary_v1.txt
  ch02_v47_summary_v2.txt

images/
  krishna-pool/         # pre-curated Krishna idol images (manually reviewed)
    001.jpg
    002.jpg
    ...

audio-sample-flute/     # local flute music (already present)

.tmp/                   # intermediate + output videos (disposable)
  ch02_v47_plain_v1.mp4
  ch02_v47_plain_v2.mp4
  ch02_v47_image_v1.mp4
  ch02_v47_image_v2.mp4
```

---

## Tool 1: `fetch_shloka.py`

**Language:** Python
**Input:** `--chapter INT --verse INT`
**Output:** JSON object printed to stdout

Reads `data/gita.json` and returns the matching shloka. Fields used:

```json
{
  "chapter_number": 2,
  "verse_number": 47,
  "text": "कर्मण्येवाधिकारस्ते...",
  "transliteration": "karmaṇy-evādhikāras te...",
  "translation": "You have a right to perform..."
}
```

Source: [bhagavad-gita-as-it-is GitHub repo](https://github.com/gita/gita) — downloaded once to `data/gita.json`.

---

## Tool 2: `generate_audio.py`

**Language:** Python
**Input:** `--chapter INT --verse INT [--mock-audio] [--force]`
**Output:** Writes files to `audio/`, prints file paths to stdout

### Cache-first logic

Before any API call, checks if the target file exists in `audio/`. Skips the call if present. `--force` bypasses the cache.

### Claude API — 2 Hindi summaries

Calls Claude API once per shloka to generate **two distinct Hindi summaries** in a single prompt (to save API calls). Summaries are concise, natural spoken Hindi — not a literal translation. Cached to:
- `audio/ch{CC}_v{VVV}_summary_v1.txt`
- `audio/ch{CC}_v{VVV}_summary_v2.txt`

### ElevenLabs — 3 audio files

| File | Voice | Voice ID | Settings |
|---|---|---|---|
| `ch02_v47_sanskrit.mp3` | Taksh | `qDuRKMlYmrm8trt5QyBn` | Stability 0.75, Style 0.30 |
| `ch02_v47_hindi_v1.mp3` | Niraj | `zgqefOY5FPQ3bB7OZTVR` | Stability 0.60, Style 0.45 |
| `ch02_v47_hindi_v2.mp3` | Niraj | `zgqefOY5FPQ3bB7OZTVR` | Stability 0.60, Style 0.45 |

Both voices use model `eleven_multilingual_v2` — required for Devanagari script support.

### Mock mode

`--mock-audio` uses macOS `say` command to generate placeholder audio. No ElevenLabs calls. For development and FFmpeg compositor testing only.

---

## Tool 3: `build_video.js`

**Language:** Node.js
**Input:** `--chapter INT --verse INT --summary v1|v2 --style plain|image`
**Output:** Writes MP4 to `.tmp/ch{CC}_v{VVV}_{style}_{summary}.mp4`

### Slide structure

| Slide | Duration | Content | Audio |
|---|---|---|---|
| 1 — Intro | 1s fixed | Chapter + Shloka reference | Flute only |
| 2 — Sanskrit | = `sanskrit.mp3` duration | Devanagari text (yellow, centered) | Taksh voice |
| 3 — Transliteration | 1.5s fixed | Roman IAST script (white, italic) | Flute only |
| 4 — Hindi meaning | = `hindi_vN.mp3` duration | Devanagari text (white, centered) | Niraj voice |
| 5 — Outro | 3s fixed | Channel name + subscribe prompt | Flute fade out |

**Total fixed time:** 5.5s. Audio-driven slides fill the remainder.
**60s guard:** After rendering, `ffprobe` checks output duration. Logs a warning if >58s — shorten Claude summary prompt for that shloka.

### Visual styles

**Plain style** — warm saffron/golden-brown background:
- Background: `#1c0a00` with radial orange gradient overlay
- No external image dependency
- Consistent across all shlokas

**Image style** — pre-curated Krishna idol pool:
- Picks randomly from `images/krishna-pool/` — no live API call at runtime
- Pool is built once using `tools/fetch_krishna_images.py`, then manually reviewed
- Dark overlay applied so text remains readable
- Same image may repeat across shlokas — intentional, devotional consistency

### Layout (both styles)

Centered stack on 1080×1920 (9:16):
- Chapter + Shloka label — top center, small, uppercase, low opacity
- Sanskrit/Hindi text — vertically and horizontally centered, Noto Sans Devanagari
- Gold divider line — between text and transliteration
- Channel watermark — bottom center, semi-transparent

**Font:** Noto Sans Devanagari (install via `brew install --cask font-noto-sans-devanagari`)

### Audio mixing

- Voice tracks: 100% volume
- Flute (`audio-sample-flute/`): 20% volume, ducked to 10% during voice segments
- 1s silence padding before first voice, between slides, after last voice

### 4 output videos per shloka

```
plain_v1 = plain style + hindi_v1 audio + summary_v1 text
plain_v2 = plain style + hindi_v2 audio + summary_v2 text
image_v1 = image style + hindi_v1 audio + summary_v1 text
image_v2 = image style + hindi_v2 audio + summary_v2 text
```

Sanskrit audio and background image are shared across all 4.

---

## One-time Setup: `fetch_krishna_images.py`

**Language:** Python
**Run once** before the first video build. Never called by the pipeline.

```bash
python tools/fetch_krishna_images.py --count 60
```

Searches Pexels using terms: `"Lord Krishna idol"`, `"Krishna murti"`, `"Krishna statue temple"`. Downloads CC0-licensed results to `images/krishna-pool/` numbered sequentially (`001.jpg`, `002.jpg`, …).

**After running:** open `images/krishna-pool/` in Finder, delete any images that don't fit (off-brand, low quality, unrelated). The pipeline uses whatever remains.

---

## Tool 4: `run_phase1.py` (Coordinator)

**Language:** Python

```bash
# Single shloka — all 4 videos
python tools/run_phase1.py --chapter 2 --verse 47

# Dev mode — skip ElevenLabs
python tools/run_phase1.py --chapter 2 --verse 47 --mock-audio

# Force regenerate audio cache
python tools/run_phase1.py --chapter 2 --verse 47 --force-audio

# Batch — first N shlokas in dataset order (Ch1 V1 onwards, no state tracking in Phase 1)
python tools/run_phase1.py --batch 5
```

**Step sequence per shloka:**
1. `fetch_shloka.py` → shloka data
2. `generate_audio.py` → 2 Hindi summaries via Claude (cache-first)
3. `generate_audio.py` → 3 ElevenLabs audio files (cache-first)
4. Random pick from `images/krishna-pool/` → no API call at runtime
5. `build_video.js` × 4 → plain_v1, plain_v2, image_v1, image_v2

**Console output:**
```
[1/4] Fetching shloka Ch.2 v.47...             ✓
[2/4] Generating Hindi summaries (Claude)...   ✓ cached
[3/4] Generating audio (ElevenLabs)...         ✓ 3 calls
[4/4] Building 4 videos...                     ✓ 36.2s · 38.7s · 37.1s · 39.4s
      Image: images/krishna-pool/023.jpg (random pick)
Output → .tmp/ch02_v47_*.mp4
```

**Error handling:** Any step failure stops the run immediately — no partial videos written. Re-running is always safe due to caching. Failed step + error message printed to stderr.

---

## Dependencies

```bash
# System
brew install ffmpeg
brew install --cask font-noto-sans-devanagari

# Python
pip install anthropic requests python-dotenv

# Node.js
npm install fluent-ffmpeg
```

**API keys in `.env`:**
```
ELEVENLABS_API_KEY=
ANTHROPIC_API_KEY=
PEXELS_API_KEY=
```

---

## Out of Scope (Phase 1)

- N8N workflow wiring
- YouTube upload
- State tracker (chapter/verse index)
- Telegram notifications
- Ken Burns animation (Phase 3)
- Lord images / dynamic backgrounds (future phase)
- Text fade-in per line (Phase 3)
