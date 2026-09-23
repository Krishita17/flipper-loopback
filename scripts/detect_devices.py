#!/usr/bin/env python3
"""Compatibility shim for `flci detect` (see `flci detect --help`)."""

import sys

from flci.__main__ import main

sys.exit(main(["detect", *sys.argv[1:]]))
