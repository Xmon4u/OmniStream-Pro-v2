"""
Quick Probe: Tests Netflix, TMDB ID, and IMDb ID renaming options.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "desktop"))
from test_rename_options import run_predefined_demos

if __name__ == "__main__":
    run_predefined_demos()
