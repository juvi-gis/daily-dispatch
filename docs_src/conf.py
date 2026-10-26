"""Sphinx configuration for Daily Dispatch."""
import os
import sys

import django

sys.path.insert(0, os.path.abspath(".."))
os.environ["DJANGO_SETTINGS_MODULE"] = "dailydispatch.settings"
# Docs never touch the database; a throwaway key keeps settings happy
os.environ.setdefault("SECRET_KEY", "docs-build-only")
django.setup()

project = "Daily Dispatch"
author = "Juwan Slabbert"
extensions = ["sphinx.ext.autodoc", "sphinx.ext.viewcode"]
html_theme = "alabaster"
