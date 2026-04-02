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
        if ch is None or vs is None:
            continue
        if int(ch) == chapter and int(vs) == verse:
            return {
                "chapter_number": int(ch),
                "verse_number":   int(vs),
                "text":           entry.get("text") or entry.get("sanskrit") or "",
                "transliteration": entry.get("transliteration") or "",
                "translation":    entry.get("translation") or entry.get("meaning") or entry.get("word_meanings") or "",
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
