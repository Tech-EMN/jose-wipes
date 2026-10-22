"""CLI: cleanup old rendered jobs and log files."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jose_wipes.retention import main

if __name__ == "__main__":
    sys.exit(main())
