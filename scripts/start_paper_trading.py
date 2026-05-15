"""CLI: start paper trading."""

from __future__ import annotations

import sys

from blackorca.live.paper import main

if __name__ == "__main__":
    main(sys.argv[1:])
