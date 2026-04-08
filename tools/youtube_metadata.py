#!/usr/bin/env python3
"""Generates YouTube title + description for a given shloka."""

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
GITA_JSON = ROOT / "data" / "gita.json"
TRANSLATION_JSON = ROOT / "data" / "translation.json"

GAMBHIRANANDA = "Swami Gambirananda"


def _load_gita() -> list:
    return json.loads(GITA_JSON.read_text(encoding="utf-8"))


def _load_gambhirananda() -> list:
    translations = json.loads(TRANSLATION_JSON.read_text(encoding="utf-8"))
    return [t for t in translations if t["authorName"] == GAMBHIRANANDA]


def _clean(text: str) -> str:
    return text.replace("\n", " ").strip()


def generate_metadata(chapter: int, verse: int) -> dict:
    gita = _load_gita()
    gambh = _load_gambhirananda()

    idx = next(
        (i for i, e in enumerate(gita) if e["chapter_number"] == chapter and e["verse_number"] == verse),
        None,
    )
    if idx is None:
        raise ValueError(f"Verse ch{chapter} v{verse} not found in gita.json")
    if idx >= len(gambh):
        raise ValueError(f"No Gambhirananda translation at index {idx}")

    sanskrit = _clean(gita[idx]["text"])
    meaning = _clean(gambh[idx]["description"])

    title = f"Bhagavad Gita - Adhyay {chapter} Shloka {verse}"
    description = (
        f"Shloka: {sanskrit}\n\nMeaning: {meaning}\n#BhagavadGita #GitaShlokas #Krishna #Adhyay{chapter}"
    )
    return {"title": title, "description": description}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--verse", type=int, required=True)
    args = parser.parse_args()
    metadata = generate_metadata(args.chapter, args.verse)
    print(json.dumps(metadata))


if __name__ == "__main__":
    main()
