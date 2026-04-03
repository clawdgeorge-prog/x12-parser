#!/usr/bin/env python3
"""
X12 Parse CLI — parse 835/837 files and emit structured JSON.

Usage:
    python3 -m src.cli <input.edi> [-o <output.json>] [--compact]

Examples:
    python3 -m src.cli tests/fixtures/sample_835.edi
    python3 -m src.cli tests/fixtures/sample_835.edi -o parsed.json
    python3 -m src.cli tests/fixtures/sample_835.edi --compact
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parser import X12Parser


def main() -> None:
    parser = argparse.ArgumentParser(description="X12 835/837 Parser")
    parser.add_argument("file", type=Path, help="Input X12 EDI file")
    parser.add_argument("-o", "--output", type=Path, help="Output JSON file")
    parser.add_argument("--compact", action="store_true", help="No indentation")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"ERROR: file not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    try:
        p = X12Parser.from_file(args.file)
        result = p.to_dict()
    except Exception as exc:
        print(f"ERROR parsing {args.file}: {exc}", file=sys.stderr)
        sys.exit(1)

    indent = None if args.compact else 2
    text = json.dumps(result, indent=indent, ensure_ascii=False)

    if args.output:
        args.output.write_text(text)
        print(f"[OK] Written: {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
