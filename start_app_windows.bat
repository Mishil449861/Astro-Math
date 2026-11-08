@echo off
rem Double-click this file to start Astro Calendar on Windows.
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python is not installed. Download it from https://www.python.org/downloads/
  echo During setup, tick "Add python.exe to PATH", then double-click this file again.
  pause
  exit /b 1
)
echo Getting things ready. The first time this takes a few minutes...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
rem A place to paste a free AI key (optional); it is never uploaded
if not exist ".streamlit\secrets.toml" copy ".streamlit\secrets.example.toml" ".streamlit\secrets.toml" >nul
echo.
echo Optional: to add a free AI key, open .streamlit\secrets.toml in Notepad (see README).
echo Astro Calendar is opening in your web browser.
echo If Streamlit asks for an email, just press Enter.
echo Keep this window open while you use the app; close it to stop.
python -m streamlit run app.py --browser.gatherUsageStats false
pause
