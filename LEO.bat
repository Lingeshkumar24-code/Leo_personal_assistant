@echo off
REM Double-click to launch LEO's 3D interface.
cd /d "%~dp0"
if not exist venv\Scripts\activate.bat (
  echo First run: please run scripts\setup_windows.bat
  pause & exit /b 1
)
call venv\Scripts\activate.bat
python main.py --ui
pause
