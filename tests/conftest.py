"""Shared pytest setup — Windows console cp1252 can't encode ₹/★ etc used throughout
this codebase's text; without this, print()s crash on encoding, not the assertion."""
import io
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
