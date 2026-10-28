@echo off
REM ---------------------------------------------------------------------------
REM  record_demo.bat  — one-click like Agent Fail full-demo.bat
REM
REM    record_demo.bat              -> Streamlit + VO EN (demo gobernada ~2 min)
REM    record_demo.bat --es         -> same ES
REM    record_demo.bat --aepd       -> corte 90s AEPD/EIPD (castellano)
REM    record_demo.bat --no-record  -> Streamlit + VO, no capture
REM    record_demo.bat --no-voice   -> Streamlit + step advance, silent
REM ---------------------------------------------------------------------------

setlocal EnableDelayedExpansion
cd /d "%~dp0"

title Porto Seguro — Governed AI Demo

set "LANG=en"
set "RECORD=1"
set "VOICE=1"
set "PROFILE=governed"

:parse_args
set "ARG=%~1"
if "%ARG%"=="" goto after_args
if /I "%ARG%"=="--es" set "LANG=es"
if /I "%ARG%"=="--en" set "LANG=en"
if /I "%ARG%"=="--aepd" (
  set "PROFILE=aepd"
  set "LANG=es"
)
if /I "%ARG%"=="--no-record" set "RECORD=0"
if /I "%ARG%"=="--no-voice" set "VOICE=0"
shift
goto parse_args
:after_args

chcp 65001 >nul 2>&1
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo.
echo ==========================================================================
echo   PORTO SEGURO — GOVERNED AI DEMO  (auto, estilo Agent Fail)
echo ==========================================================================
echo   Streamlit sala de control + narracion ElevenLabs + Game Bar
echo   Grabacion empieza con la primera frase ^(Win+Alt+R^)
echo   Idioma: %LANG%   record=%RECORD%   voice=%VOICE%
echo ==========================================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: python not on PATH
  pause
  exit /b 1
)

echo [1/4] Deps...
python -m pip install -q -r requirements.txt -r requirements_streamlit.txt
if errorlevel 1 echo WARN: pip issues — continuing if packages exist

echo [2/4] Starting Streamlit...
start "Porto Seguro Governance Hub" cmd /k streamlit run app.py --server.headless true

echo [3/4] Waiting for http://localhost:8501 ...
timeout /t 6 >nul

echo [4/4] Auto demo orchestrator...
set "PY_ARGS=--lang %LANG% --profile %PROFILE%"
if "%RECORD%"=="0" set "PY_ARGS=!PY_ARGS! --no-record"
if "%VOICE%"=="0" set "PY_ARGS=!PY_ARGS! --no-voice"

python docs\governance\auto_record_demo.py !PY_ARGS!
set "RC=!ERRORLEVEL!"

echo.
if not "!RC!"=="0" (
  echo [record_demo] exited with code !RC!
) else (
  echo [record_demo] OK
  echo   EN: %%USERPROFILE%%\Videos\Captures\governed-ai-en.mp4
  echo   ES: %%USERPROFILE%%\Videos\Captures\governed-ai-es.mp4
)
echo.
echo Press any key to close...
pause >nul
exit /b !RC!
