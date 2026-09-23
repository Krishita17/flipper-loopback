#!/usr/bin/env python3
"""Compatibility shim for `flci flash` (see `flci flash --help`)."""

import sys

from flci.__main__ import main

sys.exit(main(["flash", *sys.argv[1:]]))
