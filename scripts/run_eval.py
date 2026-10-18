"""Entry point: .venv/bin/python -m scripts.run_eval --run RUN_ID --split dev."""
from eval.run_eval import main


if __name__ == "__main__":
    raise SystemExit(main())
