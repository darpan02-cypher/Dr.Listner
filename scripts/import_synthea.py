"""Import an existing synthetic Synthea JSON bundle without making network calls."""
import argparse
from datetime import date
import json
from pathlib import Path
from src.dataset.fhir import chart_from_synthea


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--confirm-synthetic", action="store_true", required=True)
    args = parser.parse_args()
    chart = chart_from_synthea(json.loads(args.bundle.read_text()), synthetic=args.confirm_synthetic, as_of=args.as_of)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(chart.model_dump_json(indent=2) + "\n")
    print(f"Imported {len(chart.entries)} chart entries to {args.output}")


if __name__ == "__main__":
    main()
