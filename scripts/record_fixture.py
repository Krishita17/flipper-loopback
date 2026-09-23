#!/usr/bin/env python3
"""Compatibility shim for `flci record` (see `flci record --help`)."""

import sys

from flci.__main__ import main

sys.exit(main(["record", *sys.argv[1:]]))
