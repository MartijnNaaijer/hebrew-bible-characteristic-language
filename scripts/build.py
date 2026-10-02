"""Build the site in docs/: the app page plus its data files.

Usage:  python scripts/build.py                 copy the app; extract all data if missing
        python scripts/build.py --refresh       re-extract the data for the whole Hebrew Bible
        python scripts/build.py Jeremia 25 26   re-extract only these chapters (BHSA book name)

The site works from the file system (open docs/index.html) and on GitHub Pages.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOCS = os.path.join(ROOT, "docs")
args = [a for a in sys.argv[1:] if not a.startswith("--")]

if args or "--refresh" in sys.argv or not os.path.exists(os.path.join(DOCS, "data", "index.js")):
    subprocess.run([sys.executable, os.path.join(HERE, "extract_bhsa.py"), *args], check=True)

os.makedirs(DOCS, exist_ok=True)
shutil.copyfile(os.path.join(HERE, "app.html"), os.path.join(DOCS, "index.html"))
open(os.path.join(DOCS, ".nojekyll"), "w").close()  # GitHub Pages: serve files as they are
print("docs/index.html written")
