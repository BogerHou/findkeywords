#!/usr/bin/env python3
"""Cheap, deliberately broad name screening; matches are clues, not keywords."""
import argparse
import json
import re
from pathlib import Path

TERMS = """calculator converter generator checker tracker planner invoice subtitle
transcript compress resize remove background pdf csv json markdown diagram audio
video image photo prompt agent schema recipe itinerary resume flashcard chord sheet
font palette mockup watermark screenshot timezone pronunciation worksheet timer
countdown qr barcode""".split()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    found, seen = [], set()
    for source in args.files:
        match_date = re.search(r"\d{4}-\d{2}-\d{2}", source.name)
        source_date = match_date.group() if match_date else None
        for raw in source.read_text(encoding="utf-8-sig").splitlines():
            domain = raw.strip().lower()
            if not domain or domain in seen:
                continue
            name = domain.split(".")[0]
            matches = [term for term in TERMS if term in name]
            if matches and len(name) < 34 and not re.search(r"\d{3}", name):
                seen.add(domain)
                found.append({"domain": domain, "source": "WhoisDS free daily list",
                              "source_date": source_date, "name_matches": matches})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(found)} name matches written to {args.output}")


if __name__ == "__main__":
    main()
