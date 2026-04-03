# Gita YT Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build four standalone tools that produce 4 MP4 videos per Bhagavad Gita shloka — plain and image styles × two Hindi summary versions.

**Architecture:** Three core tools (fetch_shloka.py, generate_audio.py, build_video.js) each own one concern, chained by run_phase1.py. All API results are permanently cached — the pipeline is always safe to re-run.

**Tech Stack:** Python 3.11+ (anthropic, requests, python-dotenv, pytest), Node.js 18+ (child_process spawnSync — no exec/shell), FFmpeg + Noto Sans Devanagari, ElevenLabs API, Claude API (claude-sonnet-4-6), Pexels API

---

## File Structure

```
tools/
  fetch_shloka.py          # CLI: reads data/gita.json → prints shloka JSON
  generate_audio.py        # CLI: Claude summaries + ElevenLabs audio, cache-first
  build_video.js           # CLI: FFmpeg compositor → .tmp/ch{CC}_v{VVV}_{style}_{ver}.mp4
  run_phase1.py            # CLI: coordinator — chains all three tools
  fetch_krishna_images.py  # CLI: one-time Pexels image pool builder (not called by pipeline)
data/
  gita.json                # downloaded in Task 0
audio/                     # permanent cache (created in Task 0)
images/
  krishna-pool/            # populated by fetch_krishna_images.py
audio-sample-flute/        # already present
.tmp/                      # video outputs
tests/
  test_fetch_shloka.py
  test_generate_audio.py
  test_build_video.js
.env
requirements.txt
package.json
```

---

### Task 0: Environment Setup

**Files:** `.env`, `requirements.txt`, `package.json`, `.gitignore`

- [ ] **Step 1: Install system dependencies**

```bash
brew install ffmpeg
brew install --cask font-noto-sans-devanagari
ffmpeg -version | head -1
```
Expected: `ffmpeg version 7.x ...`

- [ ] **Step 2: Create project directories**

```bash
mkdir -p data audio images/krishna-pool .tmp tools tests
```

- [ ] **Step 3: Create .gitignore**

```
.env
.tmp/
audio/
__pycache__/
*.pyc
node_modules/
.superpowers/
```

- [ ] **Step 4: Create .env** (fill in real keys before running tools)

```
ELEVENLABS_API_KEY=
ANTHROPIC_API_KEY=
PEXELS_API_KEY=
```

- [ ] **Step 5: Create requirements.txt**

```
anthropic>=0.25.0
requests>=2.31.0
python-dotenv>=1.0.0
pytest>=8.0.0
```

- [ ] **Step 6: Install Python dependencies**

```bash
pip install -r requirements.txt
```

- [ ] **Step 7: Init Node.js**

```bash
npm init -y
```

- [ ] **Step 8: Download Bhagavad Gita dataset**

```bash
curl -L "https://raw.githubusercontent.com/gita/BhagavadGita/master/BhagavadGita.json" -o data/gita.json
python3 -c "
import json
d = json.load(open('data/gita.json', encoding='utf-8'))
sample = d[0] if isinstance(d, list) else d
print(type(d).__name__, 'with', len(d) if isinstance(d, list) else '?', 'entries')
print(json.dumps(d[0] if isinstance(d, list) else list(d.items())[:1], indent=2, ensure_ascii=False)[:500])
"
```

Note the exact key names printed. If they differ from `chapter_number`, `verse_number`, `text`, `transliteration`, `translation` — update the key mappings in Task 1.

- [ ] **Step 9: Commit**

```bash
git init
git add requirements.txt package.json .gitignore
git commit -m "chore: project setup — deps, dirs, dataset"
```

---

### Task 1: fetch_shloka.py

**Files:**
- Create: `tools/fetch_shloka.py`
- Create: `tests/test_fetch_shloka.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fetch_shloka.py
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
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/test_fetch_shloka.py -v
```
Expected: `ModuleNotFoundError: No module named 'fetch_shloka'`

- [ ] **Step 3: Implement fetch_shloka.py**

```python
# tools/fetch_shloka.py
import json, argparse

def fetch_shloka(chapter: int, verse: int, dataset_path: str = "data/gita.json") -> dict:
    with open(dataset_path, encoding="utf-8") as f:
        data = json.load(f)

    # Normalise: handle flat list or nested {chapters:[{verses:[]}]}
    if isinstance(data, list):
        entries = data
    else:
        entries = [
            v
            for ch in data.get("chapters", data.get("data", []))
            for v in ch.get("verses", [])
        ]

    for entry in entries:
        ch = entry.get("chapter_number") or entry.get("chapter")
        vs = entry.get("verse_number")   or entry.get("verse")
        if int(ch) == chapter and int(vs) == verse:
            return {
                "chapter_number": int(ch),
                "verse_number":   int(vs),
                "text":           entry.get("text") or entry.get("sanskrit") or "",
                "transliteration": entry.get("transliteration") or "",
                "translation":    entry.get("translation") or entry.get("meaning") or "",
            }

    raise ValueError(f"Shloka Ch{chapter} V{verse} not found in dataset")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--verse",   type=int, required=True)
    parser.add_argument("--dataset", default="data/gita.json")
    args = parser.parse_args()
    print(json.dumps(fetch_shloka(args.chapter, args.verse, args.dataset),
                     ensure_ascii=False, indent=2))
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_fetch_shloka.py -v
```
Expected: `2 passed`

- [ ] **Step 5: Smoke test against real dataset**

```bash
python tools/fetch_shloka.py --chapter 2 --verse 47
```
Expected: JSON with Sanskrit text. If any fields are empty strings, update the `entry.get(...)` fallback keys to match what was printed in Task 0 Step 8.

- [ ] **Step 6: Commit**

```bash
git add tools/fetch_shloka.py tests/test_fetch_shloka.py
git commit -m "feat: fetch_shloka — dataset reader with field normalisation"
```

---

### Task 2: generate_audio.py — cache utilities + Claude summaries

**Files:**
- Create: `tools/generate_audio.py`
- Create: `tests/test_generate_audio.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_generate_audio.py
import json, os, sys, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

def test_audio_path_format():
    from generate_audio import audio_path
    assert audio_path(2, 47, "sanskrit")   == "audio/ch02_v047_sanskrit.mp3"
    assert audio_path(18, 78, "hindi_v1")  == "audio/ch18_v078_hindi_v1.mp3"
    assert audio_path(1, 1, "summary_v2")  == "audio/ch01_v001_summary_v2.txt"

def test_parse_two_summaries():
    from generate_audio import parse_summaries
    raw = "SUMMARY_1: पहला अर्थ यहाँ है।\nSUMMARY_2: दूसरा अर्थ यहाँ है।"
    v1, v2 = parse_summaries(raw)
    assert v1 == "पहला अर्थ यहाँ है।"
    assert v2 == "दूसरा अर्थ यहाँ है।"

def test_summary_cache_hit_skips_claude(tmp_path, monkeypatch):
    from generate_audio import generate_summaries
    (tmp_path / "ch02_v047_summary_v1.txt").write_text("पहला", encoding="utf-8")
    (tmp_path / "ch02_v047_summary_v2.txt").write_text("दूसरा", encoding="utf-8")

    called = []
    monkeypatch.setattr("generate_audio.call_claude", lambda *a, **kw: called.append(1))

    v1, v2 = generate_summaries(2, 47, "Sanskrit text", audio_dir=str(tmp_path))
    assert v1 == "पहला"
    assert v2 == "दूसरा"
    assert called == []
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_generate_audio.py -v
```
Expected: `ModuleNotFoundError: No module named 'generate_audio'`

- [ ] **Step 3: Implement cache utilities + Claude summary generation**

```python
# tools/generate_audio.py
import os, json, argparse, re, subprocess
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

AUDIO_DIR   = "audio"
VOICE_TAKSH = "qDuRKMlYmrm8trt5QyBn"
VOICE_NIRAJ = "zgqefOY5FPQ3bB7OZTVR"
EL_MODEL    = "eleven_multilingual_v2"


def audio_path(chapter: int, verse: int, kind: str) -> str:
    ext = ".txt" if "summary" in kind else ".mp3"
    return f"{AUDIO_DIR}/ch{chapter:02d}_v{verse:03d}_{kind}{ext}"


def parse_summaries(raw: str) -> tuple[str, str]:
    v1 = re.search(r"SUMMARY_1:\s*(.+?)(?=SUMMARY_2:|$)", raw, re.DOTALL)
    v2 = re.search(r"SUMMARY_2:\s*(.+?)$", raw, re.DOTALL)
    if not v1 or not v2:
        raise ValueError(f"Could not parse summaries from:\n{raw}")
    return v1.group(1).strip(), v2.group(1).strip()


def call_claude(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def generate_summaries(chapter: int, verse: int, sanskrit_text: str,
                       audio_dir: str = AUDIO_DIR, force: bool = False) -> tuple[str, str]:
    p1 = os.path.join(audio_dir, f"ch{chapter:02d}_v{verse:03d}_summary_v1.txt")
    p2 = os.path.join(audio_dir, f"ch{chapter:02d}_v{verse:03d}_summary_v2.txt")

    if not force and os.path.exists(p1) and os.path.exists(p2):
        return Path(p1).read_text(encoding="utf-8"), Path(p2).read_text(encoding="utf-8")

    prompt = (
        f"You are writing spoken Hindi narration for YouTube Shorts about the Bhagavad Gita.\n"
        f"Sanskrit verse — Chapter {chapter}, Verse {verse}:\n{sanskrit_text}\n\n"
        f"Write TWO distinct Hindi summaries for spoken narration. Each must be 2-3 natural "
        f"sentences, concise enough to narrate in under 20 seconds. Use simple, accessible Hindi.\n\n"
        f"Reply EXACTLY in this format:\n"
        f"SUMMARY_1: <first summary>\n"
        f"SUMMARY_2: <second summary>"
    )
    raw = call_claude(prompt)
    v1, v2 = parse_summaries(raw)

    os.makedirs(audio_dir, exist_ok=True)
    Path(p1).write_text(v1, encoding="utf-8")
    Path(p2).write_text(v2, encoding="utf-8")
    return v1, v2
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_generate_audio.py -v
```
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add tools/generate_audio.py tests/test_generate_audio.py
git commit -m "feat: generate_audio — cache utils + Claude summary generation"
```

---

### Task 3: generate_audio.py — ElevenLabs audio + mock mode

**Files:**
- Modify: `tools/generate_audio.py`
- Modify: `tests/test_generate_audio.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_generate_audio.py`:

```python
def test_mock_audio_creates_mp3_files(tmp_path):
    from generate_audio import generate_audio_files
    shloka = {"chapter_number": 2, "verse_number": 47,
               "text": "Hello world", "transliteration": "hello world"}
    files = generate_audio_files(shloka, "पहला", "दूसरा", mock=True, audio_dir=str(tmp_path))
    assert os.path.exists(files["sanskrit"])
    assert os.path.exists(files["hindi_v1"])
    assert os.path.exists(files["hindi_v2"])
    assert files["sanskrit"].endswith(".mp3")

def test_audio_cache_hit_skips_elevenlabs(tmp_path, monkeypatch):
    from generate_audio import generate_audio_files
    for name in ["ch02_v047_sanskrit.mp3", "ch02_v047_hindi_v1.mp3", "ch02_v047_hindi_v2.mp3"]:
        (tmp_path / name).write_bytes(b"fake mp3")

    called = []
    monkeypatch.setattr("generate_audio.call_elevenlabs", lambda *a, **kw: called.append(1) or b"")

    shloka = {"chapter_number": 2, "verse_number": 47,
               "text": "test", "transliteration": "test"}
    generate_audio_files(shloka, "v1", "v2", audio_dir=str(tmp_path))
    assert called == []
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_generate_audio.py::test_mock_audio_creates_mp3_files \
       tests/test_generate_audio.py::test_audio_cache_hit_skips_elevenlabs -v
```
Expected: `AttributeError: module 'generate_audio' has no attribute 'generate_audio_files'`

- [ ] **Step 3: Add ElevenLabs + mock functions** — append to `tools/generate_audio.py`:

```python
def call_elevenlabs(text: str, voice_id: str, stability: float, style: float) -> bytes:
    import requests as _req
    resp = _req.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"],
                 "Content-Type": "application/json"},
        json={"text": text, "model_id": EL_MODEL,
              "voice_settings": {"stability": stability, "style": style,
                                 "use_speaker_boost": True}},
    )
    resp.raise_for_status()
    return resp.content


def _mock_audio(text: str, dest_mp3: str) -> None:
    """Placeholder MP3 via macOS say + ffmpeg — no API calls."""
    aiff = dest_mp3.replace(".mp3", ".aiff")
    subprocess.run(["say", "-o", aiff, text], check=True)
    subprocess.run(["ffmpeg", "-y", "-i", aiff, dest_mp3],
                   check=True, capture_output=True)
    os.remove(aiff)


def generate_audio_files(shloka: dict, summary_v1: str, summary_v2: str,
                         mock: bool = False, audio_dir: str = AUDIO_DIR,
                         force: bool = False) -> dict:
    ch, vs = shloka["chapter_number"], shloka["verse_number"]
    paths = {
        "sanskrit": os.path.join(audio_dir, f"ch{ch:02d}_v{vs:03d}_sanskrit.mp3"),
        "hindi_v1": os.path.join(audio_dir, f"ch{ch:02d}_v{vs:03d}_hindi_v1.mp3"),
        "hindi_v2": os.path.join(audio_dir, f"ch{ch:02d}_v{vs:03d}_hindi_v2.mp3"),
    }
    specs = [
        ("sanskrit", shloka["text"], VOICE_TAKSH, 0.75, 0.30),
        ("hindi_v1", summary_v1,     VOICE_NIRAJ, 0.60, 0.45),
        ("hindi_v2", summary_v2,     VOICE_NIRAJ, 0.60, 0.45),
    ]
    os.makedirs(audio_dir, exist_ok=True)
    for key, text, voice_id, stability, style_val in specs:
        path = paths[key]
        if not force and os.path.exists(path):
            continue
        if mock:
            _mock_audio(text, path)
        else:
            Path(path).write_bytes(call_elevenlabs(text, voice_id, stability, style_val))
    return paths
```

- [ ] **Step 4: Add CLI entry point** — append to `tools/generate_audio.py`:

```python
if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from fetch_shloka import fetch_shloka

    parser = argparse.ArgumentParser()
    parser.add_argument("--chapter",    type=int, required=True)
    parser.add_argument("--verse",      type=int, required=True)
    parser.add_argument("--mock-audio", action="store_true")
    parser.add_argument("--force",      action="store_true")
    args = parser.parse_args()

    shloka = fetch_shloka(args.chapter, args.verse)
    print("[1/2] Generating Hindi summaries (Claude)...")
    v1, v2 = generate_summaries(args.chapter, args.verse, shloka["text"], force=args.force)
    print(f"  v1: {v1[:60]}...")
    print(f"  v2: {v2[:60]}...")
    print("[2/2] Generating audio files...")
    files = generate_audio_files(shloka, v1, v2, mock=args.mock_audio, force=args.force)
    print(json.dumps(files, indent=2))
```

- [ ] **Step 5: Run all generate_audio tests**

```bash
pytest tests/test_generate_audio.py -v
```
Expected: `5 passed`

- [ ] **Step 6: Smoke test mock mode**

```bash
python tools/generate_audio.py --chapter 2 --verse 47 --mock-audio
```
Expected: three `.mp3` files created under `audio/`, paths printed as JSON.

- [ ] **Step 7: Commit**

```bash
git add tools/generate_audio.py tests/test_generate_audio.py
git commit -m "feat: generate_audio — ElevenLabs TTS + mock mode + cache-first"
```

---

### Task 4: fetch_krishna_images.py (one-time setup)

**Files:**
- Create: `tools/fetch_krishna_images.py`

No automated test — verified by reviewing downloaded images in Finder.

- [ ] **Step 1: Implement fetch_krishna_images.py**

```python
# tools/fetch_krishna_images.py
import os, requests, argparse
from dotenv import load_dotenv
load_dotenv()

IMAGE_DIR = "images/krishna-pool"
QUERIES   = [
    "Lord Krishna idol",
    "Krishna murti temple",
    "Krishna statue gold",
    "Radha Krishna idol",
    "Krishna deity shrine",
]


def pexels_search(query: str, per_page: int) -> list[dict]:
    resp = requests.get(
        "https://api.pexels.com/v1/search",
        headers={"Authorization": os.environ["PEXELS_API_KEY"]},
        params={"query": query, "per_page": per_page, "orientation": "portrait"},
    )
    resp.raise_for_status()
    return resp.json().get("photos", [])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=60)
    args = parser.parse_args()

    os.makedirs(IMAGE_DIR, exist_ok=True)
    per_query  = max(1, args.count // len(QUERIES) + 1)
    downloaded = 0

    for query in QUERIES:
        print(f"Searching: '{query}'...")
        for photo in pexels_search(query, per_page=min(per_query, 15)):
            dest = os.path.join(IMAGE_DIR, f"{downloaded + 1:03d}.jpg")
            print(f"  Downloading {dest}...")
            open(dest, "wb").write(requests.get(photo["src"]["large2x"], timeout=30).content)
            downloaded += 1
            if downloaded >= args.count:
                break
        if downloaded >= args.count:
            break

    print(f"\n✓ {downloaded} images saved to {IMAGE_DIR}/")
    print("Open that folder in Finder and delete any that don't fit.")
```

- [ ] **Step 2: Run (requires PEXELS_API_KEY in .env)**

```bash
python tools/fetch_krishna_images.py --count 60
```
Expected: 60 images in `images/krishna-pool/`

- [ ] **Step 3: Review and curate**

```bash
open images/krishna-pool/
```
Delete off-brand or low-quality images. Keep at least 10.

- [ ] **Step 4: Commit**

```bash
git add tools/fetch_krishna_images.py
git commit -m "feat: fetch_krishna_images — one-time Pexels Krishna pool builder"
```

---

### Task 5: build_video.js — ffprobe helper + timing calculator

**Files:**
- Create: `tools/build_video.js`
- Create: `tests/test_build_video.js`

All subprocess calls use `spawnSync` with argument arrays — no shell interpolation.

- [ ] **Step 1: Write failing tests**

```javascript
// tests/test_build_video.js
'use strict';
const assert = require('assert');
const { computeTimings } = require('../tools/build_video');

function test_timing_normal() {
    const t = computeTimings({ sanskritDur: 12.5, hindiDur: 15.3 });
    assert.strictEqual(t.slide1End,   1.0,  'slide1 ends at 1s');
    assert.strictEqual(t.slide2Start, 1.0,  'slide2 starts at 1s');
    assert.strictEqual(t.slide2End,   13.5, 'slide2 ends at 1+12.5');
    assert.strictEqual(t.slide3End,   15.0, 'slide3 ends at 13.5+1.5');
    assert.strictEqual(t.slide4Start, 15.0, 'slide4 starts after translit');
    assert.strictEqual(t.slide4End,   30.3, 'slide4 ends at 15+15.3');
    assert.strictEqual(t.totalDur,    33.3, 'total = 30.3+3');
    assert.strictEqual(t.warning,     false, 'no warning under 58s');
    console.log('PASS test_timing_normal');
}

function test_timing_60s_warning() {
    const t = computeTimings({ sanskritDur: 30, hindiDur: 30 });
    assert(t.totalDur > 58, 'should exceed 58s');
    assert.strictEqual(t.warning, true, 'warning flag set');
    console.log('PASS test_timing_60s_warning');
}

test_timing_normal();
test_timing_60s_warning();
console.log('All timing tests passed.');
```

- [ ] **Step 2: Run to verify failure**

```bash
node tests/test_build_video.js
```
Expected: `Error: Cannot find module '../tools/build_video'`

- [ ] **Step 3: Implement build_video.js scaffold**

```javascript
// tools/build_video.js
'use strict';
const { spawnSync } = require('child_process');
const path = require('path');
const fs   = require('fs');

const SLIDE1_DUR = 1.0;
const SLIDE3_DUR = 1.5;
const SLIDE5_DUR = 3.0;

function getAudioDuration(filePath) {
    const r = spawnSync('ffprobe', [
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        filePath,
    ], { encoding: 'utf8' });
    if (r.status !== 0) throw new Error(`ffprobe failed on ${filePath}: ${r.stderr}`);
    return parseFloat(r.stdout.trim());
}

function computeTimings({ sanskritDur, hindiDur }) {
    const slide1End   = SLIDE1_DUR;
    const slide2Start = slide1End;
    const slide2End   = slide2Start + sanskritDur;
    const slide3Start = slide2End;
    const slide3End   = slide3Start + SLIDE3_DUR;
    const slide4Start = slide3End;
    const slide4End   = slide4Start + hindiDur;
    const slide5Start = slide4End;
    const totalDur    = slide5Start + SLIDE5_DUR;
    return {
        slide1Start: 0, slide1End,
        slide2Start, slide2End,
        slide3Start, slide3End,
        slide4Start, slide4End,
        slide5Start, totalDur,
        warning: totalDur > 58,
    };
}

function findFont() {
    const candidates = [
        '/Library/Fonts/NotoSansDevanagari-Regular.ttf',
        '/Library/Fonts/NotoSansDevanagari[wdth,wght].ttf',
        '/opt/homebrew/share/fonts/noto-sans-devanagari/NotoSansDevanagari-Regular.ttf',
        '/usr/local/share/fonts/noto-sans-devanagari/NotoSansDevanagari-Regular.ttf',
    ];
    for (const c of candidates) { if (fs.existsSync(c)) return c; }

    // Fallback: search with spawnSync (safe — no user input in args)
    const r = spawnSync('find', ['/Library/Fonts', '-name', '*NotoSans*Devanagari*Regular*', '-type', 'f'],
                        { encoding: 'utf8' });
    const found = (r.stdout || '').trim().split('\n').filter(Boolean)[0];
    if (found) return found;

    throw new Error('Noto Sans Devanagari not found. Run: brew install --cask font-noto-sans-devanagari');
}

module.exports = { getAudioDuration, computeTimings, findFont };
```

- [ ] **Step 4: Run timing tests**

```bash
node tests/test_build_video.js
```
Expected: `All timing tests passed.`

- [ ] **Step 5: Verify ffprobe on flute file**

```bash
node -e "
const {getAudioDuration} = require('./tools/build_video');
const fs = require('fs');
const f  = fs.readdirSync('audio-sample-flute')[0];
console.log('Flute duration:', getAudioDuration('audio-sample-flute/' + f) + 's');
"
```
Expected: a number like `120.5`

- [ ] **Step 6: Commit**

```bash
git add tools/build_video.js tests/test_build_video.js
git commit -m "feat: build_video — ffprobe helper + timing calculator"
```

---

### Task 6: build_video.js — video compositor (plain + image styles)

**Files:**
- Modify: `tools/build_video.js`

- [ ] **Step 1: Append helper functions + buildVideo to build_video.js**

Add the following before `module.exports`:

```javascript
/** Word-wraps text at maxChars per line. */
function wrapText(text, maxChars = 16) {
    const words = text.split(/\s+/);
    const lines = [];
    let cur = '';
    for (const w of words) {
        const joined = cur ? cur + ' ' + w : w;
        if (joined.length > maxChars && cur) { lines.push(cur); cur = w; }
        else cur = joined;
    }
    if (cur) lines.push(cur);
    return lines;
}

/** Escapes special characters for FFmpeg drawtext. */
function esc(t) {
    return t
        .replace(/\\/g, '\\\\')
        .replace(/'/g, '\u2019')
        .replace(/:/g, '\\:')
        .replace(/\[/g, '\\[')
        .replace(/\]/g, '\\]')
        .replace(/%/g, '\\%');
}

/** Returns one drawtext filter string. */
function dt({ text, font, size, color, x, y, enable }) {
    return `drawtext=fontfile='${font}':text='${esc(text)}':fontcolor=${color}` +
           `:fontsize=${size}:x=${x}:y=${y}:enable='${enable}'`;
}

/**
 * Builds one MP4 via FFmpeg.
 */
function buildVideo({ chapter, verse, sanskritText, transliteration, hindiSummary,
                      sanskritAudio, hindiAudio, fluteAudio, style,
                      krishnaPoolDir = 'images/krishna-pool', outputPath }) {

    const font        = findFont();
    const sanskritDur = getAudioDuration(sanskritAudio);
    const hindiDur    = getAudioDuration(hindiAudio);
    const t           = computeTimings({ sanskritDur, hindiDur });

    if (t.warning) {
        console.warn(`⚠  WARNING: ${outputPath} is ${t.totalDur.toFixed(1)}s > 58s — shorten Hindi summary`);
    }

    // ── Text overlay filters ──────────────────────────────────────────────
    const LINE_H = 54;
    const filters = [];

    // Top label — always visible
    filters.push(dt({ text: `Chapter ${chapter} | Shloka ${verse}`,
                      font, size: 26, color: 'white@0.60',
                      x: '(w-text_w)/2', y: '90', enable: 'gte(t,0)' }));

    // Slide 2 — Sanskrit (yellow, multi-line)
    const sLines = wrapText(sanskritText, 16);
    sLines.forEach((line, i) =>
        filters.push(dt({ text: line, font, size: 42, color: '#FFD700',
                          x: '(w-text_w)/2',
                          y: `(h-${sLines.length * LINE_H})/2-20+${i * LINE_H}`,
                          enable: `between(t,${t.slide2Start},${t.slide2End})` }))
    );

    // Slide 3 — Transliteration (white, centered)
    filters.push(dt({ text: transliteration, font, size: 26, color: 'white@0.80',
                      x: '(w-text_w)/2', y: '(h-text_h)/2',
                      enable: `between(t,${t.slide3Start},${t.slide3End})` }));

    // Slide 4 — Hindi meaning (white, multi-line)
    const hLines = wrapText(hindiSummary, 16);
    hLines.forEach((line, i) =>
        filters.push(dt({ text: line, font, size: 38, color: 'white',
                          x: '(w-text_w)/2',
                          y: `(h-${hLines.length * LINE_H})/2-20+${i * LINE_H}`,
                          enable: `between(t,${t.slide4Start},${t.slide4End})` }))
    );

    // Watermark — always visible
    filters.push(dt({ text: '@GitaShlokas', font, size: 22, color: 'white@0.35',
                      x: '(w-text_w)/2', y: 'h-70', enable: 'gte(t,0)' }));

    const textFilters = filters.join(',');

    // ── Background ────────────────────────────────────────────────────────
    let bgInputArgs, bgFilter;
    if (style === 'plain') {
        bgInputArgs = ['-f', 'lavfi', '-i',
                       `color=c=0x1c0a00:s=1080x1920:r=30:d=${t.totalDur}`];
        bgFilter = `[0:v]${textFilters}[vout]`;
    } else {
        const imgs = fs.readdirSync(krishnaPoolDir).filter(f => /\.jpg$/i.test(f));
        if (!imgs.length) throw new Error(`No images in ${krishnaPoolDir}. Run fetch_krishna_images.py first.`);
        const img = path.join(krishnaPoolDir, imgs[Math.floor(Math.random() * imgs.length)]);
        console.log(`  Image: ${img}`);
        bgInputArgs = ['-loop', '1', '-framerate', '30', '-t', String(t.totalDur), '-i', img];
        bgFilter = `[0:v]scale=1080:1920:force_original_aspect_ratio=increase,` +
                   `crop=1080:1920,fps=30,` +
                   `drawbox=x=0:y=0:w=iw:h=ih:color=black@0.60:t=fill,` +
                   `${textFilters}[vout]`;
    }

    // ── Audio ─────────────────────────────────────────────────────────────
    // Inputs: 0=bg, 1=sanskrit, 2=hindi, 3=flute (stream_loop -1)
    // Voice tracks: delayed to slide start, padded to totalDur.
    // Flute: looped, trimmed, volume 20% → ducked to 10% during voice.
    const s2ms = Math.round(t.slide2Start * 1000);
    const s4ms = Math.round(t.slide4Start * 1000);
    const fluteExpr =
        `if(or(between(t\\,${t.slide2Start}\\,${t.slide2End})` +
        `\\,between(t\\,${t.slide4Start}\\,${t.slide4End})),0.1,0.2)`;

    const filterComplex = [
        bgFilter,
        `[1:a]adelay=${s2ms}|${s2ms},apad=whole_dur=${t.totalDur}[skt]`,
        `[2:a]adelay=${s4ms}|${s4ms},apad=whole_dur=${t.totalDur}[hnd]`,
        `[3:a]aloop=loop=-1:size=2000000000,atrim=0:${t.totalDur},` +
            `volume='${fluteExpr}':eval=frame[flute]`,
        `[skt][hnd][flute]amix=inputs=3:normalize=0:dropout_transition=0[aout]`,
    ].join(';');

    const args = [
        '-y',
        ...bgInputArgs,
        '-i', sanskritAudio,
        '-i', hindiAudio,
        '-stream_loop', '-1', '-i', fluteAudio,
        '-filter_complex', filterComplex,
        '-map', '[vout]', '-map', '[aout]',
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
        '-c:a', 'aac', '-ar', '44100',
        '-t', String(t.totalDur),
        outputPath,
    ];

    fs.mkdirSync(path.dirname(outputPath), { recursive: true });
    const r = spawnSync('ffmpeg', args, { encoding: 'utf8', maxBuffer: 20 * 1024 * 1024 });
    if (r.status !== 0) throw new Error(`FFmpeg failed:\n${r.stderr.slice(-1200)}`);
}
```

Update `module.exports` at the bottom:
```javascript
module.exports = { getAudioDuration, computeTimings, findFont, buildVideo };
```

- [ ] **Step 2: Run timing tests (must still pass)**

```bash
node tests/test_build_video.js
```
Expected: `All timing tests passed.`

- [ ] **Step 3: Create silent mock audio for smoke tests**

```bash
ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=stereo -t 3 /tmp/mock_sanskrit.mp3
ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=stereo -t 5 /tmp/mock_hindi.mp3
```

- [ ] **Step 4: Smoke test — plain style**

```javascript
// Run as: node -e "<paste below>"
const {buildVideo} = require('./tools/build_video');
const fs = require('fs');
buildVideo({
  chapter: 2, verse: 47,
  sanskritText:    'कर्मण्येवाधिकारस्ते मा फलेषु कदाचन',
  transliteration: 'karmanye vadhikaras te ma phaleshu kadachana',
  hindiSummary:    'अपना कर्म करो, फल की चिंता मत करो।',
  sanskritAudio:   '/tmp/mock_sanskrit.mp3',
  hindiAudio:      '/tmp/mock_hindi.mp3',
  fluteAudio:      'audio-sample-flute/' + fs.readdirSync('audio-sample-flute')[0],
  style:           'plain',
  outputPath:      '.tmp/smoke_plain.mp4',
});
console.log('Done: .tmp/smoke_plain.mp4');
```

```bash
open .tmp/smoke_plain.mp4
```
Verify: 1080×1920, saffron background, yellow Sanskrit text centered, white watermark bottom, ~9.5s total.

If text is invisible — font not found. Debug with:
```bash
node -e "const {findFont}=require('./tools/build_video'); console.log(findFont());"
```
If it throws, locate the font manually:
```bash
find /Library/Fonts /opt/homebrew -name "*Devanagari*" 2>/dev/null
```
Then add the returned path to the `candidates` array in `findFont()`.

- [ ] **Step 5: Smoke test — image style** (requires images from Task 4)

```javascript
// node -e "<paste below>"
const {buildVideo} = require('./tools/build_video');
const fs = require('fs');
buildVideo({
  chapter: 2, verse: 47,
  sanskritText:    'कर्मण्येवाधिकारस्ते मा फलेषु कदाचन',
  transliteration: 'karmanye vadhikaras te ma phaleshu kadachana',
  hindiSummary:    'अपना कर्म करो, फल की चिंता मत करो।',
  sanskritAudio:   '/tmp/mock_sanskrit.mp3',
  hindiAudio:      '/tmp/mock_hindi.mp3',
  fluteAudio:      'audio-sample-flute/' + fs.readdirSync('audio-sample-flute')[0],
  style:           'image',
  outputPath:      '.tmp/smoke_image.mp4',
});
console.log('Done: .tmp/smoke_image.mp4');
```

```bash
open .tmp/smoke_image.mp4
```
If text is hard to read, increase overlay in `bgFilter` from `black@0.60` to `black@0.75`.

- [ ] **Step 6: Commit**

```bash
git add tools/build_video.js
git commit -m "feat: build_video — FFmpeg compositor, plain + image styles"
```

---

### Task 7: build_video.js — CLI interface

**Files:**
- Modify: `tools/build_video.js`

- [ ] **Step 1: Append CLI entry point to build_video.js**

```javascript
if (require.main === module) {
    const argv = process.argv.slice(2);
    const get  = key => { const i = argv.indexOf('--' + key); return i >= 0 ? argv[i + 1] : null; };
    const req  = key => { const v = get(key); if (!v) { console.error(`Missing --${key}`); process.exit(1); } return v; };

    buildVideo({
        chapter:         parseInt(req('chapter')),
        verse:           parseInt(req('verse')),
        sanskritText:    req('sanskrit-text'),
        transliteration: req('transliteration'),
        hindiSummary:    req('hindi-summary'),
        sanskritAudio:   req('sanskrit-audio'),
        hindiAudio:      req('hindi-audio'),
        fluteAudio:      req('flute-audio'),
        style:           req('style'),
        outputPath:      req('output'),
    });
    console.log(`✓ ${req('output')}`);
}
```

- [ ] **Step 2: Test the CLI**

```bash
node tools/build_video.js \
  --chapter 2 --verse 47 \
  --sanskrit-text "कर्मण्येवाधिकारस्ते" \
  --transliteration "karmanye vadhikaras te" \
  --hindi-summary "अपना कर्म करो" \
  --sanskrit-audio /tmp/mock_sanskrit.mp3 \
  --hindi-audio /tmp/mock_hindi.mp3 \
  --flute-audio "$(ls audio-sample-flute/* | head -1)" \
  --style plain \
  --output .tmp/cli_test.mp4
```
Expected: `✓ .tmp/cli_test.mp4`

- [ ] **Step 3: Run timing tests (must still pass)**

```bash
node tests/test_build_video.js
```
Expected: `All timing tests passed.`

- [ ] **Step 4: Commit**

```bash
git add tools/build_video.js
git commit -m "feat: build_video — CLI interface"
```

---

### Task 8: run_phase1.py — coordinator

**Files:**
- Create: `tools/run_phase1.py`

- [ ] **Step 1: Implement run_phase1.py**

```python
# tools/run_phase1.py
import os, json, argparse, subprocess, sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))
from fetch_shloka   import fetch_shloka
from generate_audio import generate_summaries, generate_audio_files

FLUTE_DIR    = "audio-sample-flute"
KRISHNA_POOL = "images/krishna-pool"
TMP_DIR      = ".tmp"


def find_flute() -> str:
    files = [f for f in os.listdir(FLUTE_DIR)
             if f.lower().endswith(('.mp3', '.wav', '.m4a', '.aac'))]
    if not files:
        raise FileNotFoundError(f"No audio files found in {FLUTE_DIR}/")
    return os.path.join(FLUTE_DIR, files[0])


def run_shloka(chapter: int, verse: int, mock_audio: bool = False, force: bool = False) -> list[str]:
    os.makedirs(TMP_DIR, exist_ok=True)
    print(f"\n{'='*52}\nProcessing Ch.{chapter} V.{verse}\n{'='*52}")

    print("[1/4] Fetching shloka data...")
    shloka = fetch_shloka(chapter, verse)
    print(f"  {shloka['text'][:60]}...")

    print("[2/4] Generating Hindi summaries (Claude)...")
    v1, v2 = generate_summaries(chapter, verse, shloka["text"], force=force)
    print(f"  v1: {v1[:55]}...")
    print(f"  v2: {v2[:55]}...")

    print(f"[3/4] Generating audio ({'mock' if mock_audio else 'ElevenLabs'})...")
    audio = generate_audio_files(shloka, v1, v2, mock=mock_audio, force=force)
    for k, p in audio.items():
        print(f"  {k}: {p}")

    flute   = find_flute()
    outputs = []
    print("[4/4] Building 4 videos...")

    for style in ("plain", "image"):
        for ver in ("v1", "v2"):
            summary = v1 if ver == "v1" else v2
            hindi   = audio[f"hindi_{ver}"]
            out     = os.path.join(TMP_DIR, f"ch{chapter:02d}_v{verse:03d}_{style}_{ver}.mp4")

            result = subprocess.run(
                [
                    "node", "tools/build_video.js",
                    "--chapter",         str(chapter),
                    "--verse",           str(verse),
                    "--sanskrit-text",   shloka["text"],
                    "--transliteration", shloka["transliteration"],
                    "--hindi-summary",   summary,
                    "--sanskrit-audio",  audio["sanskrit"],
                    "--hindi-audio",     hindi,
                    "--flute-audio",     flute,
                    "--style",           style,
                    "--output",          out,
                ],
                capture_output=True, text=True,
            )

            if result.returncode != 0:
                print(f"  ✗ {style}_{ver} FAILED", file=sys.stderr)
                print(result.stderr[-600:], file=sys.stderr)
                raise RuntimeError(f"build_video failed for {style}_{ver}")

            size_mb = Path(out).stat().st_size / 1_048_576
            print(f"  ✓ {style}_{ver}: {out} ({size_mb:.1f} MB)")
            outputs.append(out)

    return outputs


def main():
    parser = argparse.ArgumentParser(description="Gita YT Phase 1 coordinator")
    parser.add_argument("--chapter",     type=int)
    parser.add_argument("--verse",       type=int)
    parser.add_argument("--batch",       type=int,
                        help="Process first N shlokas in dataset order (Ch1 V1 onwards)")
    parser.add_argument("--mock-audio",  action="store_true",
                        help="Use macOS say instead of ElevenLabs")
    parser.add_argument("--force-audio", action="store_true",
                        help="Regenerate audio even if cached")
    args = parser.parse_args()

    if args.batch:
        data    = json.load(open("data/gita.json", encoding="utf-8"))
        entries = data if isinstance(data, list) else [
            v for ch in data.get("chapters", []) for v in ch.get("verses", [])
        ]
        for entry in entries[:args.batch]:
            ch = int(entry.get("chapter_number") or entry.get("chapter"))
            vs = int(entry.get("verse_number")   or entry.get("verse"))
            run_shloka(ch, vs, mock_audio=args.mock_audio, force=args.force_audio)
    elif args.chapter and args.verse:
        outs = run_shloka(args.chapter, args.verse,
                          mock_audio=args.mock_audio, force=args.force_audio)
        print(f"\n✓ Done — {len(outs)} videos in {TMP_DIR}/")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Pre-create cached summaries for a fully offline dry run**

```bash
mkdir -p audio
echo "पहला परीक्षण सारांश — यह एक परीक्षण है।" > audio/ch02_v047_summary_v1.txt
echo "दूसरा परीक्षण सारांश — कर्म ही पूजा है।"  > audio/ch02_v047_summary_v2.txt
```

- [ ] **Step 3: Full dry run with mock audio (no API keys needed)**

```bash
python tools/run_phase1.py --chapter 2 --verse 47 --mock-audio
```
Expected:
```
Processing Ch.2 V.47
[1/4] Fetching shloka data...
[2/4] Generating Hindi summaries (Claude)...   (cached)
[3/4] Generating audio (mock)...
[4/4] Building 4 videos...
  ✓ plain_v1: .tmp/ch02_v047_plain_v1.mp4 (x.x MB)
  ✓ plain_v2: .tmp/ch02_v047_plain_v2.mp4 (x.x MB)
  ✓ image_v1: .tmp/ch02_v047_image_v1.mp4 (x.x MB)
  ✓ image_v2: .tmp/ch02_v047_image_v2.mp4 (x.x MB)
✓ Done — 4 videos in .tmp/
```

- [ ] **Step 4: Open and review all 4 outputs**

```bash
open .tmp/ch02_v047_plain_v1.mp4 .tmp/ch02_v047_plain_v2.mp4 \
     .tmp/ch02_v047_image_v1.mp4 .tmp/ch02_v047_image_v2.mp4
```
Verify: portrait orientation, text readable and centered, flute audible throughout, slide transitions at correct times. The two plain videos should look identical except for Hindi text on Slide 4.

- [ ] **Step 5: Run with real APIs** (requires all keys filled in .env)

```bash
python tools/run_phase1.py --chapter 2 --verse 47
```
Review all 4 videos for voice quality and summary naturalness.

- [ ] **Step 6: Batch test — first 3 shlokas**

```bash
python tools/run_phase1.py --batch 3 --mock-audio
```
Expected: 12 videos in `.tmp/` (4 per shloka × 3 shlokas). No errors.

- [ ] **Step 7: Commit**

```bash
git add tools/run_phase1.py
git commit -m "feat: run_phase1 — coordinator, 4 videos per shloka, mock + real modes"
```

---

## Self-Review

**Spec coverage:**

| Requirement | Task |
|---|---|
| fetch_shloka.py — dataset reader, field normalisation | 1 |
| generate_audio.py — Claude 2 summaries in one call, cache-first | 2 |
| generate_audio.py — ElevenLabs 3 audio files, mock mode, cache-first | 3 |
| fetch_krishna_images.py — Pexels pool, manual review step | 4 |
| build_video.js — ffprobe, timing (1s/audio-driven/1.5s/audio-driven/3s) | 5 |
| build_video.js — plain style (saffron bg, centered text, watermark) | 6 |
| build_video.js — image style (Krishna pool, dark overlay, random pick) | 6 |
| build_video.js — 60s guard warning | 5 + 6 |
| build_video.js — flute from audio-sample-flute/, ducked 20%→10% | 6 |
| build_video.js — Noto Sans Devanagari, findFont() | 5 |
| 4 videos per shloka: plain_v1, plain_v2, image_v1, image_v2 | 8 |
| run_phase1.py — --mock-audio, --force-audio, --batch | 8 |
| Permanent audio cache under audio/ | 2, 3 |
| All subprocess calls use spawnSync with arg arrays (no shell injection) | 5, 6, 7 |

**Placeholder scan:** No TBDs, no incomplete steps, all code blocks are complete.

**Name/type consistency:**
- `generate_summaries()` defined Task 2 → called Task 8 ✓
- `generate_audio_files()` defined Task 3 → called Task 8 ✓
- `buildVideo()` exported Task 6 → called via CLI Task 7 → invoked via subprocess Task 8 ✓
- `computeTimings()` exported Task 5 → used inside `buildVideo` Task 6 ✓
- Audio file naming `ch{CC:02d}_v{VVV:03d}_*` consistent across Tasks 2, 3, 8 ✓
