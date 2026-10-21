import sys
import os

# Ensure repo root directory is in sys.path when running pytest
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import importlib.util
app_dir = os.path.join(repo_root, "app")
if os.path.exists(os.path.join(app_dir, "__init__.py")):
    spec = importlib.util.spec_from_file_location("app", os.path.join(app_dir, "__init__.py"), submodule_search_locations=[app_dir])
    if spec and spec.loader:
        app_mod = importlib.util.module_from_spec(spec)
        sys.modules["app"] = app_mod
        spec.loader.exec_module(app_mod)

import app
print("DEBUG CONFTEST APP:", app.__file__, getattr(app, "__path__", None))
