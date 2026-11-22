@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/2] Building BSODFixTool...
py -3.10 -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name BSODFixTool ^
  --icon "app\assets\app_icon.ico" ^
  --add-data "bsod_data.json;." ^
  --add-data "app\assets;app\assets" ^
  --exclude-module numpy ^
  --exclude-module pandas ^
  --exclude-module matplotlib ^
  main.py

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

echo [2/2] Verifying embedded assets...
py -3.10 -m PyInstaller.utils.cliutils.archive_viewer -l "dist\BSODFixTool.exe" | findstr /i "bsod_data mascot app_icon"

echo Build finished: dist\BSODFixTool.exe
