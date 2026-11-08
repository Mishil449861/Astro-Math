#!/bin/bash
# Double-click this file to start Astro Calendar on a Mac.
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python is not installed. Download it from https://www.python.org/downloads/"
  echo "Install it, then double-click this file again."
  read -r -p "Press Enter to close."
  exit 1
fi
echo "Getting things ready. The first time this takes a few minutes..."
python3 -m pip install --quiet --disable-pip-version-check -r requirements.txt
# A place to paste a free AI key (optional); it is never uploaded
[ -f .streamlit/secrets.toml ] || cp .streamlit/secrets.example.toml .streamlit/secrets.toml
echo
echo "Optional: to add a free AI key, open .streamlit/secrets.toml in TextEdit (see README)."
echo "Astro Calendar is opening in your web browser."
echo "If Streamlit asks for an email, just press Enter."
echo "Keep this window open while you use the app; close it to stop."
python3 -m streamlit run app.py --browser.gatherUsageStats false
