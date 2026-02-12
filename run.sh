#!/bin/bash
source .venv/bin/activate
set -a
source .env
set +a
python main.py "$@"
