@echo off
setlocal

cd /d "%~dp0"
set "PYTHON=%~dp0..\..\..\python\python.exe"

echo [1/4] Checking environment...
if not exist "%PYTHON%" (
  echo ComfyUI Python not found:
  echo %PYTHON%
  goto failed
)

if not exist "data\prompt_pools.xlsx" (
  echo Excel source not found:
  echo %CD%\data\prompt_pools.xlsx
  goto failed
)

echo [2/4] Building runtime prompt data from Excel...
"%PYTHON%" tools\build_prompt_data_from_excel.py
if errorlevel 1 goto failed

echo [3/4] Checking Python syntax...
"%PYTHON%" -m py_compile prompt_data_generated.py prompt_data.py prompt_constants.py prompt_normalize.py prompt_planner.py prompt_postprocess.py negative_prompt_engine.py prompt_engine.py __init__.py tools\audit_prompt_pools.py tools\audit_generated_prompts.py
if errorlevel 1 goto failed

echo [4/4] Running prompt audits...
"%PYTHON%" tools\audit_prompt_pools.py --distribution-samples 20
if errorlevel 1 goto failed
"%PYTHON%" tools\audit_generated_prompts.py --samples 30
if errorlevel 1 goto failed

echo.
echo Done. Excel data has been converted into runtime prompt data.
echo Restart ComfyUI if it is already running.
echo.
pause
exit /b 0

:failed
echo.
echo Failed. Check the messages above.
echo.
pause
exit /b 1
