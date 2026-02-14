#!/usr/bin/env python3
"""Launch the Skills Manager GUI."""

import sys
from pathlib import Path

# Ensure the package directory is on sys.path
sys.path.insert(0, str(Path(__file__).parent))

from gui import SkillsManagerApp

if __name__ == "__main__":
    app = SkillsManagerApp()
    app.run()
