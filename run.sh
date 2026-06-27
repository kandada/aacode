#!/bin/bash
# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

source .venv/bin/activate
set -a
source .env
set +a
python main.py "$@"
