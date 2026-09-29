@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Brainrot Goon Machine (dev)
if not exist ".venv\Scripts\python.exe" (
  call _setup.bat
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
.venv\Scripts\python.exe main.py %*
