@echo off
rem Builds dist\DragWheel\DragWheel.exe and, if NSIS is installed, dist\DragWheel-Setup-1.1.6.exe
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv || python -m venv .venv
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller || (pause & exit /b 1)
".venv\Scripts\pyinstaller.exe" --noconfirm --clean --windowed --name DragWheel ^
  --icon assets\dragwheel.ico --version-file version_info.txt --add-data "assets;assets" ^
  --collect-data imageio_ffmpeg --collect-binaries imageio_ffmpeg ^
  --collect-all pillow_heif --hidden-import win32timezone --hidden-import py7zr --hidden-import win32com.shell.shell --hidden-import editor --hidden-import jobproc --hidden-import updater --hidden-import theme --collect-submodules locales ^
  --exclude-module tkinter --exclude-module matplotlib ^
  dragwheel.pyw || (pause & exit /b 1)
del /q "dist\DragWheel\_internal\PySide6\opengl32sw.dll" 2>nul
rmdir /s /q "dist\DragWheel\_internal\PySide6\translations" 2>nul
echo.
echo Built: dist\DragWheel\DragWheel.exe

set "NSIS="
for %%P in ("%ProgramFiles(x86)%\NSIS\makensis.exe" "%ProgramFiles%\NSIS\makensis.exe") do if exist %%P set "NSIS=%%~P"
if not defined NSIS (
    echo NSIS not found - skipping installer. Get it with:  winget install NSIS.NSIS
) else (
    "%NSIS%" installer\dragwheel.nsi && echo Built: dist\DragWheel-Setup-1.1.6.exe
)
pause
