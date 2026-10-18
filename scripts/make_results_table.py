"""Print Markdown tables using only saved eval/results/*.json files."""
import argparse
from pathlib import Path
import sys

from eval.io import ROOT, InputError, safe_run_id
from eval.report import make_results_table


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", help="Optional run ID; default is all saved results")
    parser.add_argument("--results-root", type=Path, default=ROOT / "eval/results")
    args = parser.parse_args(argv)
    try:
        if args.run is not None:
            safe_run_id(args.run)
        output = make_results_table(args.results_root, args.run)
    except (InputError, OSError) as error:
        print(f"Results table failed:\n{error}", file=sys.stderr)
        return 2
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
