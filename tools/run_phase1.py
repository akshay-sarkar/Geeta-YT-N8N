# tools/run_phase1.py
import os, json, argparse, subprocess, sys, time, glob
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


def run_shloka(chapter: int, verse: int, mock_audio: bool = False, force: bool = False, image_only: bool = False) -> list[str]:
    # Preflight: verify image pool exists if image style will be built
    pool_images = glob.glob(os.path.join(KRISHNA_POOL, "*.jpg"))
    if not pool_images:
        raise FileNotFoundError(
            f"No images found in {KRISHNA_POOL}/. "
            "Run: python tools/fetch_krishna_images.py --count 60"
        )

    os.makedirs(TMP_DIR, exist_ok=True)
    print(f"\n{'='*52}\nProcessing Ch.{chapter} V.{verse}\n{'='*52}")

    print("[1/4] Fetching shloka data...")
    shloka = fetch_shloka(chapter, verse)
    print(f"  {shloka['text'][:60]}...")

    print("[2/4] Generating Hindi summaries (Claude)...")
    v1, v2 = generate_summaries(chapter, verse, shloka["text"], shloka["translation"], force=force)
    print(f"  v1: {v1[:55]}...")
    print(f"  v2: {v2[:55]}...")

    print(f"[3/4] Generating audio ({'mock' if mock_audio else 'Gemini TTS'})...")
    audio = generate_audio_files(shloka, v1, v2, mock=mock_audio, force=force)
    for k, p in audio.items():
        print(f"  {k}: {p}")

    flute   = find_flute()
    outputs = []
    styles  = ("image",) if image_only else ("plain", "image")
    print(f"[4/4] Building {len(styles) * 2} videos...")

    for style in styles:
        for ver in ("v1", "v2"):
            summary = v1 if ver == "v1" else v2
            hindi   = audio[f"hindi_{ver}"]
            out     = os.path.join(TMP_DIR, f"ch{chapter:02d}_v{verse:03d}_{style}_{ver}.mp4")

            t_start = time.time()
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
            elapsed = time.time() - t_start

            if result.returncode != 0:
                print(f"  ✗ {style}_{ver} FAILED", file=sys.stderr)
                print(result.stderr[-600:], file=sys.stderr)
                raise RuntimeError(f"build_video failed for {style}_{ver}")

            size_mb = Path(out).stat().st_size / 1_048_576
            print(f"  ✓ {style}_{ver}: {out} ({size_mb:.1f} MB, {elapsed:.1f}s)")
            outputs.append(out)

    return outputs


def main():
    parser = argparse.ArgumentParser(description="Gita YT Phase 1 coordinator")
    parser.add_argument("--chapter",     type=int)
    parser.add_argument("--verse",       type=int)
    parser.add_argument("--batch",       type=int,
                        help="Process first N shlokas in dataset order (Ch1 V1 onwards)")
    parser.add_argument("--mock-audio",  action="store_true",
                        help="Use macOS say instead of Gemini TTS")
    parser.add_argument("--force-audio", action="store_true",
                        help="Regenerate audio even if cached")
    parser.add_argument("--image-only",  action="store_true",
                        help="Build image variants only (skip plain) — faster for pipeline use")
    args = parser.parse_args()

    if args.batch:
        with open("data/gita.json", encoding="utf-8") as f:
            data = json.load(f)
        entries = data if isinstance(data, list) else [
            v for ch in data.get("chapters", []) for v in ch.get("verses", [])
        ]
        for entry in entries[:args.batch]:
            ch = int(entry.get("chapter_number") or entry.get("chapter"))
            vs = int(entry.get("verse_number")   or entry.get("verse"))
            run_shloka(ch, vs, mock_audio=args.mock_audio, force=args.force_audio)
    elif args.chapter and args.verse:
        outs = run_shloka(args.chapter, args.verse,
                          mock_audio=args.mock_audio, force=args.force_audio,
                          image_only=args.image_only)
        print(f"\nDone -- {len(outs)} videos in {TMP_DIR}/")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
