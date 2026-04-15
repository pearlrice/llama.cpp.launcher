#!/usr/bin/env python3
"""Launcher-local entry point for the deployment core."""

from pathlib import Path
import os
import runpy
import sys

CORE_DIR = Path(__file__).resolve().parent
BASE = CORE_DIR.parent
CORE = CORE_DIR / "deploy_core.py"

if not CORE.exists():
    raise SystemExit(f"deploy_core.py not found next to the launcher: {CORE}")

os.environ.setdefault("AUTODEPLOY_BASE_DIR", str(CORE_DIR))
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))
sys.argv[0] = str(CORE)
runpy.run_path(str(CORE), run_name="__main__")
