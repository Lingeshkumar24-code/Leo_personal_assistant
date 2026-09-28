@echo off
cd /d "%~dp0\.."
python -m venv venv
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
if not exist .env copy .env.example .env
echo.
echo Setup done. Edit .env (add GEMINI_API_KEY or GROQ_API_KEY, set SCREEN_CAPTURE_ENABLED=true), then double-click LEO.bat
echo For screen text reading, also install Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki
pause
