"""Sphinx configuration for the Zine API documentation."""

from pathlib import Path
import sys


API_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = API_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(API_ROOT))

extensions = [
    "sphinx.ext.autodoc",
    "docext",
]

root_doc = "index"
source_suffix = ".rst"
project = "Zine"
copyright = "2009–2026, The Zine Team"
version = "0.2"
release = "0.2.dev0"
exclude_patterns = ["_build"]
pygments_style = "tango"

html_theme = "alabaster"
htmlhelp_basename = "Zinedoc"

latex_documents = [
    ("index", "Zine.tex", "Zine Documentation", "The Zine Team", "manual"),
]
