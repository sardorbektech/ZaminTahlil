"""ZaminTahlil Telegram Botni ishga tushiruvchi yordamchi skript.

Foydalanish:
    python scripts/run_bot.py
"""

import sys
from pathlib import Path

# Loyiha ildiz papkasini sys.path ga qo'shish
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.bot.__main__ import main

if __name__ == "__main__":
    main()
