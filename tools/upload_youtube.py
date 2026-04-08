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

TOKEN_FILE = pathlib.Path(__file__).parent.parent / "data" / "youtube_token.json"
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
    from datetime import datetime, timezone
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None
    if TOKEN_FILE.exists():
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        expiry_str = data.get("expiry")
        expiry = datetime.fromisoformat(expiry_str).replace(tzinfo=timezone.utc) if expiry_str else None
        creds = Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["YOUTUBE_CLIENT_ID"],
            client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
            scopes=SCOPES,
            expiry=expiry,
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(_build_client_config(), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(
            json.dumps({
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "expiry": creds.expiry.isoformat() if creds.expiry else None,
            }),
            encoding="utf-8",
        )

    return creds


def auth_only() -> None:
    _get_credentials()
    print("OAuth2 complete. Token saved to data/youtube_token.json")


def upload_video(video_path: str, title: str, description: str, playlist_id: str) -> str:
    if not playlist_id:
        raise ValueError("playlist_id must not be empty")

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

    try:
        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        ).execute()
    except Exception as exc:
        print(f"Warning: playlist insert failed: {exc}", file=sys.stderr)

    return f"https://www.youtube.com/watch?v={video_id}"


if __name__ == "__main__":
    for key in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET"):
        if not os.environ.get(key):
            print(f"Missing required env var: {key}", file=sys.stderr)
            sys.exit(1)

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
