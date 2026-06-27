#!/usr/bin/env python3
# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

"""
aacode package main entry point for `python -m aacode`
"""

import sys

from aacode.cli import main

if __name__ == "__main__":
    sys.exit(main())
