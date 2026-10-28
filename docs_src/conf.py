"""Sphinx configuration for Daily Dispatch."""
import os
import sys

import django

from django.core.management import call_command

sys.path.insert(0, os.path.abspath(".."))
os.environ["DJANGO_SETTINGS_MODULE"] = "dailydispatch.settings"
# Docs never touch the database; a throwaway key keeps settings happy
os.environ.setdefault("SECRET_KEY", "docs-build-only")
# Heads up: an empty DB_HOST makes settings.py use SQLite, and load_dotenv
# won't override a variable that already exists, so .env can't undo this
os.environ["DB_HOST"] = ""
os.environ.setdefault("SECRET_KEY", "docs-build-only")
django.setup()

# Heads up: autodoc evaluates class attributes, and some query the database,
# so the throwaway SQLite file needs its tables before the docs build
call_command("migrate", run_syncdb=True, verbosity=0)

project = "Daily Dispatch"
author = "Juwan Slabbert"
extensions = ["sphinx.ext.autodoc", "sphinx.ext.viewcode"]
html_theme = "alabaster"
