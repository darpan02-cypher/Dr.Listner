"""Run with python -m scripts.build_dataset. No API key or network required."""
import argparse
from pathlib import Path
from src import config
from src.dataset.build import build_dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=config.DATA_DIR / "synthetic")
    args = parser.parse_args()
    manifest = build_dataset(args.output)
    print(f"Wrote {len(manifest['visits'])} synthetic development visits to {args.output}")
    print("Draft checklist; hand-authored charts; no held-out evaluation results.")


if __name__ == "__main__":
    main()
