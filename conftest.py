"""
conftest.py — pytest root config
Adds the creditsense package root to sys.path so all agent imports resolve.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
