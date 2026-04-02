"""fetch_krishna_images.py — one-time Pexels pool builder for Krishna idol images.

Run once to populate images/krishna-pool/ then manually review and remove bad images.
NEVER called by the pipeline at runtime.

Usage:
    python tools/fetch_krishna_images.py --count 60
"""
from __future__ import annotations
import argparse, os, pathlib, time
import requests
from dotenv import load_dotenv

load_dotenv()

IMAGE_DIR = pathlib.Path("images/krishna-pool")
SEARCH_QUERIES = [
    "Lord Krishna idol",
    "Krishna murti",
    "Krishna statue temple",
]
PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"


def output_filename(index: int) -> str:
    """Return zero-padded filename for image at given 1-based index."""
    return f"{index:03d}.jpg"


def parse_photo_url(photo: dict) -> str:
    """Extract the best available image URL from a Pexels photo object.

    Returns empty string if no valid URL is found (caller should filter with `if url:`).
    """
    src = photo.get("src", {})
    return src.get("large2x") or src.get("large") or src.get("original") or ""


def fetch_images(count: int, output_dir: pathlib.Path | None = None) -> int:
    """Download `count` Krishna images from Pexels to output_dir.

    Returns number of images actually downloaded.
    Skips download if file already exists (safe to re-run).
    """
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        raise EnvironmentError("PEXELS_API_KEY is not set in environment or .env")

    out_dir = output_dir or IMAGE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    collected: list[str] = []
    per_query = max(1, count // len(SEARCH_QUERIES) + 1)

    for query in SEARCH_QUERIES:
        if len(collected) >= count:
            break
        params = {
            "query": query,
            "per_page": min(per_query, 80),
            "page": 1,
            "orientation": "portrait",
        }
        resp = requests.get(
            PEXELS_SEARCH_URL,
            headers={"Authorization": api_key},
            params=params,
            timeout=30,
        )
        try:
            resp.raise_for_status()
        except Exception as exc:
            raise RuntimeError(
                f"Pexels search failed for '{query}': {resp.status_code} {resp.text[:300]}"
            ) from exc

        photos = resp.json().get("photos", [])
        for photo in photos:
            url = parse_photo_url(photo)
            if url:
                collected.append(url)
            if len(collected) >= count:
                break

    downloaded = 0
    for i, url in enumerate(collected[:count], start=1):
        dest = out_dir / output_filename(i)
        if dest.exists():
            downloaded += 1
            continue
        img_resp = requests.get(url, timeout=60)
        try:
            img_resp.raise_for_status()
        except Exception as exc:
            print(f"  Warning: failed to download {url}: {exc}")
            continue
        if not img_resp.content:
            print(f"  Warning: empty response for {url}, skipping")
            continue
        dest.write_bytes(img_resp.content)
        downloaded += 1
        time.sleep(0.2)  # polite rate limiting

    if downloaded < count:
        print(f"  Warning: requested {count} images but only {downloaded} were available.")
    return downloaded


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Krishna idol images from Pexels")
    parser.add_argument("--count", type=int, default=60, help="Number of images to download")
    args = parser.parse_args()

    print(f"Downloading up to {args.count} Krishna images to {IMAGE_DIR}/")
    n = fetch_images(args.count)
    print(f"Done. {n} images in {IMAGE_DIR}/")
    print("Next step: open images/krishna-pool/ in Finder and delete any unsuitable images.")


if __name__ == "__main__":
    main()
