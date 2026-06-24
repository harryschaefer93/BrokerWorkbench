"""Put the flat-layout ``bot/`` directory on sys.path for the bot test package.

The bot container runs with cwd=``bot/`` so its modules use flat imports
(``from card_formatter import ...``). Mirror that here.
"""
from __future__ import annotations

import sys
from pathlib import Path

_BOT_DIR = Path(__file__).resolve().parents[2] / "bot"
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))
