#!/bin/bash
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
fi
.venv/bin/python -m reelmaker serve --lan
