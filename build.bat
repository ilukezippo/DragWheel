@echo off
rem Builds dist\DragWheel\DragWheel.exe and, if NSIS is installed, dist\DragWheel-Setup-1.1.0.exe
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv || python -m venv .venv
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller || (pause & exit /b 1)
".venv\Scripts\pyinstaller.exe" --noconfirm --clean --windowed --name DragWheel ^
  --icon assets\dragwheel.ico --version-file version_info.txt --add-data "assets;assets" --add-data "browser-extension;browser-extension" ^
  --collect-data imageio_ffmpeg --collect-binaries imageio_ffmpeg ^
  --collect-all pillow_heif --hidden-import win32timezone --hidden-import py7zr --hidden-import win32com.shell.shell --hidden-import editor --hidden-import jobproc --hidden-import pdfdocx --hidden-import updater --hidden-import theme --collect-submodules locales --hidden-import dwparts --hidden-import dwparts.p01_files --hidden-import dwparts.p02_actions --hidden-import dwparts.p03_notes --hidden-import dwparts.p04_worker --hidden-import dwparts.p05_wheel --hidden-import dwparts.p06_toast --hidden-import dwparts.p07_float --hidden-import dwparts.p08_dialogs --hidden-import dwparts.p09_trimmer --hidden-import dwparts.p10_pdfpages --hidden-import dwparts.p11_settings --hidden-import dwparts.p12_customize --hidden-import dwparts.p13_dragwatch --hidden-import dwparts.p14_app --hidden-import dwparts.p15_crash --hidden-import bridge --hidden-import PySide6.QtMultimedia --hidden-import onnxruntime --collect-binaries onnxruntime --exclude-module sympy --exclude-module cv2 ^
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
    "%NSIS%" installer\dragwheel.nsi && echo Built: dist\DragWheel-Setup-1.1.0.exe
)
pause
