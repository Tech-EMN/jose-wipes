"""Executa um smoke test real de video na Higgsfield com fallback premium."""

import sys
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from scripts.higgsfield_video_smoke_test import main


if __name__ == "__main__":
    sys.exit(main())
