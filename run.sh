#!/usr/bin/env bash
# Landing page (landing/index.html) on :8800 opens first; its "Launch Console" button goes to the Streamlit console on :8501.
cd "$(dirname "$0")"
PY=${PYTHON:-$(ls .venv/bin/python 2>/dev/null || echo python3)}
trap 'kill 0' EXIT
"$PY" -m http.server 8800 --directory landing >/dev/null 2>&1 &
"$PY" -m streamlit run app2.py --server.port 8501 --server.headless true &
sleep 2
open http://localhost:8800 2>/dev/null || xdg-open http://localhost:8800 2>/dev/null
wait
