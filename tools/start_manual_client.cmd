@echo off
setlocal
set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" (
  echo Google Chrome is not installed.
  pause
  exit /b 1
)

set "ORIGIN=http://192.168.123.111:8188"
set "PROFILE=%LOCALAPPDATA%\RPPManualClient\ChromeProfile"
if not exist "%PROFILE%" mkdir "%PROFILE%"

start "" "%CHROME%" --user-data-dir="%PROFILE%" --app="%ORIGIN%/random_photo_prompt/manual" --unsafely-treat-insecure-origin-as-secure="%ORIGIN%"
endlocal
