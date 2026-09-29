@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Brainrot Goon Machine (dev)
rem (re)install packages when there is no .venv yet OR requirements.txt changed since last time
if not exist ".venv\Scripts\python.exe" goto setup
fc /b requirements.txt .venv\goon-requirements.txt >nul 2>nul || goto setup
goto run
:setup
call _setup.bat
if errorlevel 1 (
  pause
  exit /b 1
)
:run
.venv\Scripts\python.exe main.py %*
