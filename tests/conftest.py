import sys
import os

# Ensure repo root directory is in sys.path when running pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
