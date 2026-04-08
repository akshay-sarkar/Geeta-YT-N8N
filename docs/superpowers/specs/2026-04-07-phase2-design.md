# Phase 2 — Pipeline Assembly Design Spec

## Goal

Automate the full Bhagavad Gita Shorts pipeline: every 15 minutes N8N reads the next verse from a state file, runs the Phase 1 video factory, uploads both image variants to YouTube with proper metadata, sends a Telegram notification with the video URLs, and advances the state pointer.

## Architecture

N8N is the full orchestrator (Option 2 — WAT-native). Each heavy step is a dedicated Python tool called via N8N Execute Command nodes. N8N HTTP Request nodes handle Telegram directly. YouTube OAuth2 token management stays in Python.

## Tech Stack

| Component | Tool |
|---|---|
| Orchestration | N8N (self-hosted, running at localhost:5678) |
| State tracking | `data/state.json` + `tools/state.py` |
| Metadata generation | `tools/youtube_metadata.py` |
| YouTube upload | `tools/upload_youtube.py` + `google-api-python-client` |
| Notifications | Telegram Bot API via N8N HTTP Request node |
| Schedule | Every 15 minutes (`*/15 * * * *`) |

---

## Component Specifications

### 1. State Tracker — `data/state.json` + `tools/state.py`

**File format:**
```json
{ "chapter": 1, "verse": 1 }
```

**CLI interface:**
```bash
python tools/state.py read     # prints JSON to stdout: {"chapter": 1, "verse": 1}
python tools/state.py advance  # increments to next verse, wraps chapters correctly, writes file
```

**Advance logic:** Looks up current chapter/verse in `data/gita.json` array order. Moves to next entry. When the last verse of a chapter is reached, moves to chapter+1 verse 1. When the last verse of chapter 18 (verse 78) is advanced past, writes `{ "done": true }` — pipeline stops permanently.

**Initialisation:** `data/state.json` is pre-created starting at chapter 1, verse 2 (verse 1 was manually uploaded during Phase 1 testing).

**Exhaustion:** When `advance` is called on the final verse (chapter 18, verse 78), it writes `{ "chapter": null, "verse": null, "done": true }` to `state.json`. On the next run, `read` outputs `{"done": true}` and the N8N workflow detects this, sends a Telegram message "✅ All 700 shlokas uploaded. Pipeline complete.", then stops (no further execution).

**N8N usage:** Execute Command node captures stdout of `read`; a downstream IF node checks for `done: true` — if true, sends completion Telegram and stops; otherwise parses `chapter`/`verse` and continues the pipeline.

---

### 2. YouTube Metadata — `tools/youtube_metadata.py`

**CLI:**
```bash
python tools/youtube_metadata.py --chapter 1 --verse 1
# prints JSON to stdout
```

**Output:**
```json
{
  "title": "Bhagavad Gita - Adhyay 1 Shloka 1",
  "description": "Shloka: <sanskrit text, \\n removed, trimmed>\n\nMeaning: <Swami Gambirananda description, \\n removed, trimmed>\n#BhagavadGita #GitaShlokas #Krishna #Adhyay1"
}
```

**Data sources:**
- Sanskrit text: `data/gita.json` → entry matching `chapter_number` + `verse_number` → `text` field (strip `\n` and leading/trailing whitespace)
- Meaning: `data/translation.json` → entry matching `verse_id` (same array index as gita.json entry) AND `authorName == "Swami Gambirananda"` → `description` field (strip `\n` and whitespace)

**verse_id mapping:** Both `gita.json` and `translation.json` are ordered by verse. The Gambhirananda entries have `verse_id` 1–701 corresponding to `gita.json` indices 0–700. Filter `translation.json` to Gambhirananda entries first (701 items), then index by position.

---

### 3. YouTube Upload Tool — `tools/upload_youtube.py`

**Dependencies:** `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2`

**Auth flow:**
- Reads `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET` from `.env`
- First-time: `python tools/upload_youtube.py --auth` opens browser OAuth consent, saves refresh token to `data/youtube_token.json`
- Every run: loads `data/youtube_token.json`, auto-refreshes access token — no manual login needed

**CLI:**
```bash
python tools/upload_youtube.py \
  --video .tmp/ch01_v001_image_v1.mp4 \
  --title "Bhagavad Gita - Adhyay 1 Shloka 1" \
  --description "..." \
  --playlist-id PLAYLIST_ID
# prints YouTube video URL to stdout
```

**Upload settings:**
- Category: 27 (Education)
- Privacy: `public`
- Language: `hi` (Hindi)
- Adds video to playlist specified by `YOUTUBE_PLAYLIST_ID` env var (overridden by `--playlist-id`)

**N8N usage:** Called twice per run — once for `image_v1`, once for `image_v2`. Each call prints the video URL to stdout, captured by N8N for the Telegram message.

---

### 4. N8N Workflow — `workflows/daily_shloka.json`

**Trigger:** Cron node, schedule `*/15 * * * *` (every 15 minutes)

**Happy path node chain:**

```
Cron (*/15 * * * *)
  → Execute Command: python tools/state.py read
  → Code node: parse JSON
  → IF node: done == true?
      YES → HTTP Request: Telegram "✅ All 700 shlokas uploaded. Pipeline complete." → STOP
      NO  → set chapter/verse variables
  → Execute Command: python run_phase1.py --chapter {{chapter}} --verse {{verse}}
  → Execute Command: python tools/youtube_metadata.py --chapter {{chapter}} --verse {{verse}}
  → Code node: parse metadata JSON, set title/description variables
  → Execute Command: upload image_v1 → capture url1
  → Execute Command: upload image_v2 → capture url2
  → Execute Command: python tools/state.py advance
  → HTTP Request: Telegram success message with url1 + url2
```

**Error branches:** Every Execute Command node has an "On Error" branch leading to:
```
HTTP Request: Telegram → "❌ Gita pipeline failed at <node name>: <error>"
```

State is **not** advanced on any failure — same verse retries on the next 15-minute tick.

**Workflow file:** Exported from N8N as `workflows/daily_shloka.json` and committed to the repo. Can be re-imported into any N8N instance.

---

### 5. Environment Variables (additions to `.env`)

```
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...
YOUTUBE_PLAYLIST_ID=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

`data/youtube_token.json` is gitignored (contains refresh token).

---

## One-Time Setup Steps

### YouTube OAuth2
1. Go to Google Cloud Console → Create project → Enable YouTube Data API v3
2. Create OAuth2 credentials (type: Desktop App) → download `client_secret.json`
3. Copy `client_id` and `client_secret` into `.env`
4. Run `python tools/upload_youtube.py --auth` once → complete browser consent → `data/youtube_token.json` is created

### Telegram Bot
1. Message @BotFather on Telegram → `/newbot` → get `TELEGRAM_BOT_TOKEN`
2. Send any message to your bot, then call `https://api.telegram.org/bot<TOKEN>/getUpdates` → extract `chat.id` → set `TELEGRAM_CHAT_ID`
3. Add both to `.env`

### Playlist ID
1. Open your YouTube channel → Playlists → click the playlist → copy ID from URL (`?list=XXXXX`)
2. Set `YOUTUBE_PLAYLIST_ID=XXXXX` in `.env`

---

## Error Handling

| Failure point | Behaviour |
|---|---|
| `state.py read` fails | Telegram alert, pipeline stops, state unchanged |
| `run_phase1.py` fails | Telegram alert, pipeline stops, state unchanged |
| `youtube_metadata.py` fails | Telegram alert, pipeline stops, state unchanged |
| `upload_youtube.py` fails (v1) | Telegram alert, pipeline stops, state unchanged |
| `upload_youtube.py` fails (v2) | Telegram alert, state unchanged (v1 already uploaded — manual cleanup needed) |
| `state.py advance` fails | Telegram alert — verse was uploaded but pointer not moved; next run re-uploads same verse |

---

## File Changes Summary

| File | Action |
|---|---|
| `data/state.json` | Create (initialised at ch1 v1) |
| `tools/state.py` | Create |
| `tools/youtube_metadata.py` | Create |
| `tools/upload_youtube.py` | Create |
| `workflows/daily_shloka.json` | Create (N8N export) |
| `requirements.txt` | Add `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2` |
| `.env` | Add 5 new keys (YouTube + Telegram) |
| `.gitignore` | Add `data/youtube_token.json` |

---

## Out of Scope (Phase 3+)

- Ken Burns zoom effect on background image
- Text fade-in animations
- Audio ducking refinements
- Thumbnail generation
- Long-form videos
