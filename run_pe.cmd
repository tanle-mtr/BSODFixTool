@echo off
chcp 65001 >nul
title BSOD Fix Tool - PE
if not exist "%~dp0BSODFixTool.exe" (
  echo Cannot find BSODFixTool.exe next to this script.
  pause
  exit /b 1
)
start "" "%~dp0BSODFixTool.exe"
