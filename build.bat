@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Brainrot Goon Machine builder
echo.
echo  =================================================
echo    helo. me build da BRAINROT GOON MACHINE 9000
echo  =================================================
echo.

call _setup.bat
if errorlevel 1 goto :fail
set "VPY=.venv\Scripts\python.exe"

%VPY% -m pip install -q -U pyinstaller
if errorlevel 1 goto :fail

echo.
echo  me cook da exe now. take 1-3 minutes...
%VPY% build_exe.py
if errorlevel 1 goto :fail

rem ---- Setup.exe (only if Inno Setup is installed; GitHub always builds it) ----
rem (no if-blocks here: "Program Files (x86)" breaks them)
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" goto :noinno
echo  me make da Setup.exe...
"%ISCC%" /Q installer.iss
if errorlevel 1 goto :fail
goto :innodone
:noinno
echo  no Inno Setup, me skip Setup.exe. get it free: https://jrsoftware.org/isdl.php
:innodone

echo.
echo  =================================================
echo    DONE. ur exe:  dist\BrainrotGoonMachine\BrainrotGoonMachine.exe
echo    installer:     dist\BrainrotGoonMachine-Setup.exe  (if Inno Setup)
echo.
echo    to ship an UPDATE to everybody:
echo      git tag v1.0.1  then  git push origin v1.0.1
echo  =================================================
echo.
explorer "dist"
pause
exit /b 0

:fail
echo.
echo  build broke :( read error above.
pause
exit /b 1
