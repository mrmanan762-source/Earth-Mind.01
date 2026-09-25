import sys
import os

# Ensure repo root directory is in sys.path when running pytest
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import app
print("DEBUG CONFTEST APP:", app.__file__, getattr(app, "__path__", None))
