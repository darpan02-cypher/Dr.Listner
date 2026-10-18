"""Build the dev/test eval dataset: python -m scripts.build_eval_dataset [--output data/eval]"""
import argparse
import json
from pathlib import Path

from src import config
from src.dataset.eval_build import build_all
from src.dataset.eval_specs import ALL

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=config.DATA_DIR / "eval")
    m = build_all(ALL, ap.parse_args().output)
    print(json.dumps(m["summary"], indent=2))
