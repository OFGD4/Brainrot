@echo off
rem Finds Python, makes .venv, installs stuff. Called by build.bat and run.bat.
cd /d "%~dp0"

set "PY="
for %%V in (3.12 3.13 3.11 3.14 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo.
  echo  u no hav python 3.10+. get it free: https://www.python.org/downloads/
  echo  tick "Add python.exe to PATH" when u install. then run me again.
  echo.
  exit /b 1
)
echo  me use python: %PY%

if not exist ".venv\Scripts\python.exe" (
  echo  me make python box .venv ...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo  venv broke
    exit /b 1
  )
)
set "VPY=.venv\Scripts\python.exe"

echo  me install stuff. first time take few minutes...
%VPY% -m pip install -q -U pip wheel
%VPY% -m pip install -U -r requirements.txt
if errorlevel 1 (
  echo.
  echo  pip broke. read error above.
  exit /b 1
)
%VPY% -m pip install -q -U pywebview >nul 2>nul
if errorlevel 1 echo  pywebview no install. app use edge window instead. dat ok.
exit /b 0
