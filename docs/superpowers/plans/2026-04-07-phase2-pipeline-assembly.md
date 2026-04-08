# Phase 2 — Pipeline Assembly Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the Phase 1 video factory into a fully automated N8N pipeline that runs every 15 minutes, uploads both image video variants to YouTube, sends Telegram notifications, and advances a persistent verse pointer — stopping permanently after all 700 shlokas are uploaded.

**Architecture:** N8N is the full orchestrator calling dedicated Python tools via Execute Command nodes. `tools/state.py` manages the verse pointer, `tools/youtube_metadata.py` builds upload metadata, and `tools/upload_youtube.py` handles OAuth2 and YouTube Data API v3 uploads. Telegram notifications flow directly through N8N HTTP Request nodes.

**Tech Stack:** Python 3.11, google-api-python-client, google-auth-oauthlib, N8N (localhost:5678), YouTube Data API v3, Telegram Bot API

---

## File Structure

| File | Action | Purpose |
|---|---|---|
| `data/state.json` | Create | Persistent verse pointer `{"chapter":1,"verse":2}` |
| `tools/state.py` | Create | Read/advance state; outputs JSON to stdout |
| `tools/youtube_metadata.py` | Create | Build title + description from gita.json + translation.json |
| `tools/upload_youtube.py` | Create | OAuth2 token management + YouTube Data API upload |
| `tests/test_state.py` | Create | Unit tests for state tool |
| `tests/test_youtube_metadata.py` | Create | Unit tests for metadata tool |
| `requirements.txt` | Modify | Add google-api-python-client, google-auth-oauthlib, google-auth-httplib2 |
| `.env` | Modify | Add YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_PLAYLIST_ID, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID |
| `.gitignore` | Modify | Add `data/youtube_token.json` |
| `workflows/daily_shloka.json` | Create | N8N workflow export (created via N8N UI then exported) |

---

## Task 1: State Tracker

**Files:**
- Create: `tools/state.py`
- Create: `data/state.json`
- Create: `tests/test_state.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_state.py
import json, pathlib, sys, shutil, io
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "tools"))

GITA_SRC = pathlib.Path(__file__).parent.parent / "data/gita.json"

def _setup(tmp_path, state_content=None):
    (tmp_path / "data").mkdir()
    shutil.copy(GITA_SRC, tmp_path / "data/gita.json")
    if state_content is not None:
        (tmp_path / "data/state.json").write_text(json.dumps(state_content))

def test_read_creates_initial_state(tmp_path, monkeypatch):
    _setup(tmp_path)
    monkeypatch.chdir(tmp_path)
    import state, importlib; importlib.reload(state)
    with patch("sys.stdout", new_callable=io.StringIO) as out:
        state.cmd_read()
    assert json.loads(out.getvalue()) == {"chapter": 1, "verse": 2}
    assert (tmp_path / "data/state.json").exists()

def test_read_done_state(tmp_path, monkeypatch):
    _setup(tmp_path, {"done": True})
    monkeypatch.chdir(tmp_path)
    import state, importlib; importlib.reload(state)
    with patch("sys.stdout", new_callable=io.StringIO) as out:
        state.cmd_read()
    assert json.loads(out.getvalue()) == {"done": True}

def test_advance_increments_verse(tmp_path, monkeypatch):
    _setup(tmp_path, {"chapter": 1, "verse": 2})
    monkeypatch.chdir(tmp_path)
    import state, importlib; importlib.reload(state)
    state.cmd_advance()
    assert json.loads((tmp_path / "data/state.json").read_text()) == {"chapter": 1, "verse": 3}

def test_advance_wraps_to_next_chapter(tmp_path, monkeypatch):
    # Ch1 has 47 verses
    _setup(tmp_path, {"chapter": 1, "verse": 47})
    monkeypatch.chdir(tmp_path)
    import state, importlib; importlib.reload(state)
    state.cmd_advance()
    assert json.loads((tmp_path / "data/state.json").read_text()) == {"chapter": 2, "verse": 1}

def test_advance_marks_done_at_last_verse(tmp_path, monkeypatch):
    # Ch18 has 78 verses — last in dataset
    _setup(tmp_path, {"chapter": 18, "verse": 78})
    monkeypatch.chdir(tmp_path)
    import state, importlib; importlib.reload(state)
    state.cmd_advance()
    assert json.loads((tmp_path / "data/state.json").read_text()) == {"done": True}

def test_advance_on_done_is_noop(tmp_path, monkeypatch):
    _setup(tmp_path, {"done": True})
    monkeypatch.chdir(tmp_path)
    import state, importlib; importlib.reload(state)
    state.cmd_advance()  # must not raise
    assert json.loads((tmp_path / "data/state.json").read_text()) == {"done": True}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3.11 -m pytest tests/test_state.py -v
```
Expected: `ModuleNotFoundError: No module named 'state'`

- [ ] **Step 3: Create `tools/state.py`**

```python
#!/usr/bin/env python3
"""tools/state.py — Pipeline verse pointer.

Usage:
  python tools/state.py read     # prints current state JSON to stdout
  python tools/state.py advance  # moves to next verse, writes state.json
"""
from __future__ import annotations
import json, pathlib, sys

GITA_JSON  = pathlib.Path("data/gita.json")
STATE_JSON = pathlib.Path("data/state.json")


def _load_gita() -> list[dict]:
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
    print(json.dumps(_read_state()))


def cmd_advance() -> None:
    state = _read_state()
    if state.get("done"):
        return  # already exhausted — no-op

    gita = _load_gita()
    ch, vs = state["chapter"], state["verse"]

    idx = next(
        (i for i, e in enumerate(gita)
         if e["chapter_number"] == ch and e["verse_number"] == vs),
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
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "read":
        cmd_read()
    elif cmd == "advance":
        cmd_advance()
    else:
        print(f"Usage: {sys.argv[0]} read|advance", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 4: Create `data/state.json`**

```bash
echo '{"chapter": 1, "verse": 2}' > data/state.json
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python3.11 -m pytest tests/test_state.py -v
```
Expected: 6 passed

- [ ] **Step 6: Smoke-test CLI manually**

```bash
python3.11 tools/state.py read
# Expected: {"chapter": 1, "verse": 2}

python3.11 tools/state.py advance
python3.11 tools/state.py read
# Expected: {"chapter": 1, "verse": 3}
```
Reset state after testing:
```bash
echo '{"chapter": 1, "verse": 2}' > data/state.json
```

- [ ] **Step 7: Commit**

```bash
git add tools/state.py data/state.json tests/test_state.py
git commit -m "feat: add state tracker tool (read/advance verse pointer)"
```

---

## Task 2: YouTube Metadata Tool

**Files:**
- Create: `tools/youtube_metadata.py`
- Create: `tests/test_youtube_metadata.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_youtube_metadata.py
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "tools"))

def test_title_format():
    from youtube_metadata import generate_metadata
    result = generate_metadata(1, 2)
    assert result["title"] == "Bhagavad Gita - Adhyay 1 Shloka 2"

def test_description_starts_with_shloka():
    from youtube_metadata import generate_metadata
    result = generate_metadata(1, 2)
    assert result["description"].startswith("Shloka:")

def test_description_has_meaning_and_author():
    from youtube_metadata import generate_metadata
    result = generate_metadata(1, 2)
    assert "Meaning:" in result["description"]
    assert "Author: Swami Gambirananda" in result["description"]

def test_no_newlines_in_shloka_line():
    from youtube_metadata import generate_metadata
    result = generate_metadata(1, 2)
    shloka_line = result["description"].split("\n")[0]
    assert "\\n" not in shloka_line
    assert shloka_line.startswith("Shloka:")

def test_hashtags_include_chapter():
    from youtube_metadata import generate_metadata
    result = generate_metadata(2, 47)
    assert "#BhagavadGita" in result["description"]
    assert "#Adhyay2" in result["description"]

def test_clean_strips_newlines():
    from youtube_metadata import _clean
    assert _clean("line1\nline2") == "line1 line2"
    assert _clean("  text  \n  more  ") == "text more"

def test_chapter_18_verse_78_works():
    # Last verse — must not raise
    from youtube_metadata import generate_metadata
    result = generate_metadata(18, 78)
    assert "Adhyay 18 Shloka 78" in result["title"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3.11 -m pytest tests/test_youtube_metadata.py -v
```
Expected: `ModuleNotFoundError: No module named 'youtube_metadata'`

- [ ] **Step 3: Create `tools/youtube_metadata.py`**

```python
#!/usr/bin/env python3
"""tools/youtube_metadata.py — Build YouTube title and description for a shloka.

Usage:
  python tools/youtube_metadata.py --chapter 1 --verse 2
  # prints JSON: {"title": "...", "description": "..."}
"""
from __future__ import annotations
import argparse, json, pathlib, re, sys

GITA_JSON        = pathlib.Path("data/gita.json")
TRANSLATION_JSON = pathlib.Path("data/translation.json")


def _clean(text: str) -> str:
    """Remove newlines and collapse whitespace."""
    return re.sub(r'\s*\n\s*', ' ', text).strip()


def generate_metadata(chapter: int, verse: int) -> dict:
    gita  = json.loads(GITA_JSON.read_text(encoding="utf-8"))
    trans = json.loads(TRANSLATION_JSON.read_text(encoding="utf-8"))

    # Find shloka entry and its index
    entry = next(
        (e for e in gita if e["chapter_number"] == chapter and e["verse_number"] == verse),
        None,
    )
    if not entry:
        raise ValueError(f"Verse {chapter}.{verse} not found in gita.json")
    idx = gita.index(entry)

    # Gambhirananda entries are in verse order — same index as gita
    gamb = [t for t in trans if t["authorName"] == "Swami Gambirananda"]
    if idx >= len(gamb):
        raise ValueError(f"No Gambhirananda translation at index {idx}")

    shloka_text = _clean(entry["text"])
    meaning     = _clean(gamb[idx]["description"])

    title = f"Bhagavad Gita - Adhyay {chapter} Shloka {verse}"
    description = (
        f"Shloka: {shloka_text}\n\n"
        f"Meaning: {meaning}\n"
        f"Author: Swami Gambirananda\n\n"
        f"#BhagavadGita #GitaShlokas #Krishna #Adhyay{chapter}"
    )
    return {"title": title, "description": description}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--verse",   type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(generate_metadata(args.chapter, args.verse), ensure_ascii=False))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3.11 -m pytest tests/test_youtube_metadata.py -v
```
Expected: 7 passed

- [ ] **Step 5: Smoke-test CLI manually**

```bash
python3.11 tools/youtube_metadata.py --chapter 1 --verse 2
```
Expected: JSON with title `"Bhagavad Gita - Adhyay 1 Shloka 2"` and description starting with `"Shloka:"`

- [ ] **Step 6: Commit**

```bash
git add tools/youtube_metadata.py tests/test_youtube_metadata.py
git commit -m "feat: add YouTube metadata generator tool"
```

---

## Task 3: YouTube Upload Tool

**Files:**
- Create: `tools/upload_youtube.py`
- Modify: `requirements.txt`
- Modify: `.gitignore`

- [ ] **Step 1: Update `requirements.txt`**

```
google-genai>=0.8.0
python-dotenv>=1.0.0
pytest>=8.0.0
google-api-python-client>=2.0.0
google-auth-oauthlib>=1.0.0
google-auth-httplib2>=0.1.0
```

- [ ] **Step 2: Install new dependencies**

```bash
python3.11 -m pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
```
Expected: Successfully installed (or already satisfied)

- [ ] **Step 3: Add `data/youtube_token.json` to `.gitignore`**

Add this line to `.gitignore`:
```
data/youtube_token.json
```

- [ ] **Step 4: Create `tools/upload_youtube.py`**

```python
#!/usr/bin/env python3
"""tools/upload_youtube.py — Upload a video to YouTube with OAuth2.

Usage:
  python tools/upload_youtube.py --auth
      One-time OAuth2 consent. Saves token to data/youtube_token.json.

  python tools/upload_youtube.py \\
      --video .tmp/ch01_v002_image_v1.mp4 \\
      --title "Bhagavad Gita - Adhyay 1 Shloka 2" \\
      --description "Shloka: ..." \\
      --playlist-id PL_XXXX
      Uploads video, adds to playlist, prints YouTube URL to stdout.
"""
from __future__ import annotations
import argparse, json, os, pathlib, sys
from dotenv import load_dotenv

load_dotenv()

TOKEN_FILE = pathlib.Path("data/youtube_token.json")
SCOPES     = ["https://www.googleapis.com/auth/youtube.upload",
               "https://www.googleapis.com/auth/youtube"]


def _build_client_config() -> dict:
    return {
        "installed": {
            "client_id":     os.environ["YOUTUBE_CLIENT_ID"],
            "client_secret": os.environ["YOUTUBE_CLIENT_SECRET"],
            "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
            "token_uri":     "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }


def _get_credentials():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None
    if TOKEN_FILE.exists():
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        creds = Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["YOUTUBE_CLIENT_ID"],
            client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
            scopes=SCOPES,
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(_build_client_config(), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(
            json.dumps({"token": creds.token, "refresh_token": creds.refresh_token}),
            encoding="utf-8",
        )

    return creds


def auth_only() -> None:
    _get_credentials()
    print("OAuth2 complete. Token saved to data/youtube_token.json")


def upload_video(video_path: str, title: str, description: str, playlist_id: str) -> str:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds   = _get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title":           title,
            "description":     description,
            "categoryId":      "27",   # Education
            "defaultLanguage": "hi",
        },
        "status": {"privacyStatus": "public"},
    }

    media    = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    response = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    ).execute()

    video_id = response["id"]

    youtube.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }
        },
    ).execute()

    return f"https://www.youtube.com/watch?v={video_id}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth",        action="store_true",
                        help="Run OAuth2 consent flow and save token")
    parser.add_argument("--video",       help="Path to MP4 file")
    parser.add_argument("--title",       help="Video title")
    parser.add_argument("--description", help="Video description")
    parser.add_argument("--playlist-id",
                        default=os.environ.get("YOUTUBE_PLAYLIST_ID", ""),
                        help="YouTube playlist ID")
    args = parser.parse_args()

    if args.auth:
        auth_only()
    else:
        missing = [f for f in ("video", "title", "description") if not getattr(args, f)]
        if missing:
            print(f"Missing: {', '.join('--' + f for f in missing)}", file=sys.stderr)
            sys.exit(1)
        if not args.playlist_id:
            print("Missing --playlist-id (or YOUTUBE_PLAYLIST_ID in .env)", file=sys.stderr)
            sys.exit(1)
        url = upload_video(args.video, args.title, args.description, args.playlist_id)
        print(url)
```

- [ ] **Step 5: Commit**

```bash
git add tools/upload_youtube.py requirements.txt .gitignore
git commit -m "feat: add YouTube upload tool with OAuth2 token management"
```

---

## Task 4: Credential Setup (One-Time)

**Files:**
- Modify: `.env`

- [ ] **Step 1: Create YouTube OAuth2 credentials in Google Cloud Console**

1. Go to https://console.cloud.google.com → select or create a project
2. APIs & Services → Library → search "YouTube Data API v3" → Enable
3. APIs & Services → Credentials → Create Credentials → OAuth client ID
4. Application type: **Desktop app** → Name: "Gita Pipeline" → Create
5. Download JSON → open it, copy `client_id` and `client_secret`

- [ ] **Step 2: Add YouTube credentials to `.env`**

```
YOUTUBE_CLIENT_ID=your_client_id_here
YOUTUBE_CLIENT_SECRET=your_client_secret_here
YOUTUBE_PLAYLIST_ID=your_playlist_id_here
```

To get playlist ID: open your YouTube channel → Playlists → click your playlist → copy the `list=XXXXX` value from the URL.

- [ ] **Step 3: Run OAuth2 consent flow**

```bash
python3.11 tools/upload_youtube.py --auth
```

A browser window will open. Sign in with the YouTube channel's Google account and grant access. After consent, the terminal will print:
```
OAuth2 complete. Token saved to data/youtube_token.json
```

- [ ] **Step 4: Create a Telegram bot**

1. Open Telegram → search @BotFather → `/newbot`
2. Follow prompts → copy the `TELEGRAM_BOT_TOKEN`
3. Send any message to your new bot
4. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser
5. Find `result[0].message.chat.id` → copy as `TELEGRAM_CHAT_ID`

- [ ] **Step 5: Add Telegram credentials to `.env`**

```
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

- [ ] **Step 6: Test Telegram connection**

```bash
source .env  # or export vars manually
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TELEGRAM_CHAT_ID}&text=Gita+pipeline+test+✅"
```
Expected: JSON response with `"ok": true` and message appears in Telegram.

- [ ] **Step 7: Test upload tool end-to-end with a real video**

```bash
# Generate metadata
python3.11 tools/youtube_metadata.py --chapter 1 --verse 2 > /tmp/meta.json
TITLE=$(python3.11 -c "import json; d=json.load(open('/tmp/meta.json')); print(d['title'])")
DESC=$(python3.11 -c "import json; d=json.load(open('/tmp/meta.json')); print(d['description'])")

# Upload image_v1 for ch1 v2 (generate it first if not cached)
python3.11 tools/run_phase1.py --chapter 1 --verse 2
python3.11 tools/upload_youtube.py \
  --video .tmp/ch01_v002_image_v1.mp4 \
  --title "$TITLE" \
  --description "$DESC"
```
Expected: prints `https://www.youtube.com/watch?v=XXXXX`

---

## Task 5: N8N Workflow

**Files:**
- Create: `workflows/daily_shloka.json` (exported from N8N UI)

- [ ] **Step 1: Open N8N at http://localhost:5678 → New Workflow → name it "Gita Daily Pipeline"**

- [ ] **Step 2: Add Schedule Trigger node**

- Node type: **Schedule Trigger**
- Trigger interval: **Custom (Cron)**
- Cron expression: `*/15 * * * *`

- [ ] **Step 3: Add "Read State" Execute Command node**

- Node type: **Execute Command**
- Command:
  ```
  cd /Users/akshaysarkar/Documents/Projects/Geeta-YT-N8N && python3.11 tools/state.py read
  ```
- Connect from: Schedule Trigger

- [ ] **Step 4: Add "Parse State" Code node**

- Node type: **Code** (JavaScript)
- Connect from: Read State
- Code:
  ```javascript
  const raw = $input.first().json.stdout.trim();
  const state = JSON.parse(raw);
  return [{ json: state }];
  ```

- [ ] **Step 5: Add "Check Done" IF node**

- Node type: **IF**
- Connect from: Parse State
- Condition: `{{ $json.done }}` **equals** `true`

- [ ] **Step 6: Add "Send Completion Telegram" HTTP Request node (TRUE branch of IF)**

- Node type: **HTTP Request**
- Method: POST
- URL: `https://api.telegram.org/bot{{ $env.TELEGRAM_BOT_TOKEN }}/sendMessage`
- Body (JSON):
  ```json
  {
    "chat_id": "{{ $env.TELEGRAM_CHAT_ID }}",
    "text": "✅ All 700 Bhagavad Gita shlokas uploaded. Pipeline complete!"
  }
  ```
- Connect from: IF (TRUE branch) → this branch ends here (no further nodes)

- [ ] **Step 7: Add "Build Videos" Execute Command node (FALSE branch of IF)**

- Node type: **Execute Command**
- Connect from: IF (FALSE branch)
- Command:
  ```
  cd /Users/akshaysarkar/Documents/Projects/Geeta-YT-N8N && python3.11 tools/run_phase1.py --chapter {{ $json.chapter }} --verse {{ $json.verse }}
  ```

- [ ] **Step 8: Add "Get Metadata" Execute Command node**

- Node type: **Execute Command**
- Connect from: Build Videos
- Command:
  ```
  cd /Users/akshaysarkar/Documents/Projects/Geeta-YT-N8N && python3.11 tools/youtube_metadata.py --chapter {{ $('Parse State').item.json.chapter }} --verse {{ $('Parse State').item.json.verse }}
  ```

- [ ] **Step 9: Add "Parse Metadata" Code node**

- Node type: **Code** (JavaScript)
- Connect from: Get Metadata
- Code:
  ```javascript
  const raw = $input.first().json.stdout.trim();
  const meta = JSON.parse(raw);
  const state = $('Parse State').item.json;
  return [{ json: { ...meta, chapter: state.chapter, verse: state.verse } }];
  ```

- [ ] **Step 10: Add "Upload V1" Execute Command node**

- Node type: **Execute Command**
- Connect from: Parse Metadata
- Command:
  ```
  cd /Users/akshaysarkar/Documents/Projects/Geeta-YT-N8N && python3.11 tools/upload_youtube.py --video .tmp/ch{{ String($json.chapter).padStart(2,'0') }}_v{{ String($json.verse).padStart(3,'0') }}_image_v1.mp4 --title "{{ $json.title }}" --description "{{ $json.description }}" --playlist-id {{ $env.YOUTUBE_PLAYLIST_ID }}
  ```

- [ ] **Step 11: Add "Upload V2" Execute Command node**

- Node type: **Execute Command**
- Connect from: Upload V1
- Command:
  ```
  cd /Users/akshaysarkar/Documents/Projects/Geeta-YT-N8N && python3.11 tools/upload_youtube.py --video .tmp/ch{{ String($('Parse Metadata').item.json.chapter).padStart(2,'0') }}_v{{ String($('Parse Metadata').item.json.verse).padStart(3,'0') }}_image_v2.mp4 --title "{{ $('Parse Metadata').item.json.title }}" --description "{{ $('Parse Metadata').item.json.description }}" --playlist-id {{ $env.YOUTUBE_PLAYLIST_ID }}
  ```

- [ ] **Step 12: Add "Advance State" Execute Command node**

- Node type: **Execute Command**
- Connect from: Upload V2
- Command:
  ```
  cd /Users/akshaysarkar/Documents/Projects/Geeta-YT-N8N && python3.11 tools/state.py advance
  ```

- [ ] **Step 13: Add "Send Success Telegram" HTTP Request node**

- Node type: **HTTP Request**
- Connect from: Advance State
- Method: POST
- URL: `https://api.telegram.org/bot{{ $env.TELEGRAM_BOT_TOKEN }}/sendMessage`
- Body (JSON):
  ```json
  {
    "chat_id": "{{ $env.TELEGRAM_CHAT_ID }}",
    "text": "✅ Adhyay {{ $('Parse State').item.json.chapter }} Shloka {{ $('Parse State').item.json.verse }} uploaded!\n\nV1: {{ $('Upload V1').item.json.stdout.trim() }}\nV2: {{ $('Upload V2').item.json.stdout.trim() }}"
  }
  ```

- [ ] **Step 14: Add error branches on every Execute Command node**

For each of these nodes: **Read State, Build Videos, Get Metadata, Upload V1, Upload V2, Advance State**:
- Click the node → Settings → check "Continue on Fail" OFF
- From the node's error output, add an **HTTP Request** node:
  - Method: POST
  - URL: `https://api.telegram.org/bot{{ $env.TELEGRAM_BOT_TOKEN }}/sendMessage`
  - Body:
    ```json
    {
      "chat_id": "{{ $env.TELEGRAM_CHAT_ID }}",
      "text": "❌ Gita pipeline failed at [NODE NAME]: {{ $json.error }}"
    }
    ```
  Replace `[NODE NAME]` with the actual node name for each.

- [ ] **Step 15: Set N8N environment variables**

In N8N: Settings → Variables → add:
- `TELEGRAM_BOT_TOKEN` = value from `.env`
- `TELEGRAM_CHAT_ID` = value from `.env`
- `YOUTUBE_PLAYLIST_ID` = value from `.env`

- [ ] **Step 16: Test workflow manually (without Cron — click "Test Workflow")**

Click **Test Workflow** in N8N. Watch each node execute. Expected:
- Read State → stdout: `{"chapter":1,"verse":2}`
- Parse State → `{chapter:1, verse:2, done:false}`
- IF → takes FALSE branch
- Build Videos → generates 4 MP4s in `.tmp/`
- Get Metadata → stdout: `{"title":"Bhagavad Gita - Adhyay 1 Shloka 2","description":"..."}`
- Upload V1 → stdout: `https://www.youtube.com/watch?v=XXXXX`
- Upload V2 → stdout: `https://www.youtube.com/watch?v=YYYYY`
- Advance State → `data/state.json` now contains `{"chapter":1,"verse":3}`
- Success Telegram → message received in Telegram with both URLs

- [ ] **Step 17: Export workflow and commit**

In N8N: top-right menu → Download → saves as JSON.

```bash
mv ~/Downloads/*.json workflows/daily_shloka.json
git add workflows/daily_shloka.json
git commit -m "feat: add N8N daily pipeline workflow (every 15 min)"
```

- [ ] **Step 18: Activate the workflow**

In N8N: toggle the workflow to **Active**. It will now run every 15 minutes automatically.

---

## Task 6: Run All Tests

- [ ] **Step 1: Run full test suite**

```bash
python3.11 -m pytest tests/ -v
```
Expected: all tests pass (test_generate_audio, test_state, test_youtube_metadata)

- [ ] **Step 2: Verify state is correct after Task 4 manual test**

```bash
python3.11 tools/state.py read
```
Expected: `{"chapter": 1, "verse": 3}` (advanced past verse 2 during Task 4 test)

Reset if needed back to the correct starting verse based on what has been uploaded.

- [ ] **Step 3: Final commit**

```bash
git add -u
git commit -m "feat: Phase 2 pipeline assembly complete"
```
