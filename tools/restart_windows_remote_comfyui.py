#!/usr/bin/env python3
import base64
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


REMOTE_SSH = os.environ.get("RPP_WINDOWS_REMOTE_SSH", "administrator@192.168.123.111")
BASE_DIR = os.environ.get("RPP_WINDOWS_COMFYUI_BASE", r"D:\ComfyUI")
TASK_NAME = os.environ.get("RPP_WINDOWS_COMFYUI_TASK", "ComfyUI-8188-Interactive")
PORT = os.environ.get("RPP_WINDOWS_COMFYUI_PORT", "8188")
REMOTE_OUTPUT_DIR = os.environ.get("RPP_WINDOWS_COMFYUI_OUTPUT_DIR", r"D:\ComfyUI\ComfyUI\output")
REMOTE_NODE_DIR = os.environ.get(
    "RPP_WINDOWS_REMOTE_NODE_DIR",
    r"D:\ComfyUI\ComfyUI\custom_nodes\random_photo_prompt",
)
TRANSFER_TOKEN_FILE = Path(__file__).resolve().parents[1] / ".rpp_remote_transfer_token"


def mac_mobile_entry_url():
    configured = os.environ.get("RPP_MOBILE_ENTRY_URL", "").strip().rstrip("/")
    if configured:
        return configured
    remote_host = REMOTE_SSH.rsplit("@", 1)[-1]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect((remote_host, 9))
        return f"http://{sock.getsockname()[0]}:8188"


def transfer_token():
    try:
        return TRANSFER_TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def encoded_powershell(script):
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def main():
    mobile_entry_url = mac_mobile_entry_url()
    token = transfer_token()
    if not token:
        raise RuntimeError(f"缺少远端视频回传令牌：{TRANSFER_TOKEN_FILE}")
    video_upload_url = f"{mobile_entry_url}/random_photo_prompt/remote/video/upload"
    source_image_url = f"{mobile_entry_url}/random_photo_prompt/remote/video/source_image"
    script = rf'''
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$taskName = {ps_quote(TASK_NAME)}
$baseDir = {ps_quote(BASE_DIR)}
$port = {ps_quote(PORT)}
$outputDir = {ps_quote(REMOTE_OUTPUT_DIR)}
$hiddenStarter = Join-Path $baseDir 'start-comfyui-hidden.ps1'
$pidFile = Join-Path $baseDir 'comfyui-8188.pid'
$stdoutLog = Join-Path $baseDir 'comfyui-8188.out.log'
$stderrLog = Join-Path $baseDir 'comfyui-8188.err.log'
$venvPython = Join-Path $baseDir 'venv\Scripts\python.exe'
$comfyDir = Join-Path $baseDir 'ComfyUI'
$nodeDir = {ps_quote(REMOTE_NODE_DIR)}
$mobileEntryUrl = {ps_quote(mobile_entry_url)}

try {{
  Invoke-RestMethod -Uri "http://127.0.0.1:$port/interrupt" -Method Post -Body '{{}}' -ContentType 'application/json' -TimeoutSec 5 | Out-Null
}} catch {{}}
try {{
  Invoke-RestMethod -Uri "http://127.0.0.1:$port/queue" -Method Post -Body '{{"clear": true}}' -ContentType 'application/json' -TimeoutSec 5 | Out-Null
}} catch {{}}

schtasks /Delete /TN $taskName /F 2>$null | Out-Null
if (Test-Path $pidFile) {{
  $oldPid = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($oldPid -match '^\d+$') {{ taskkill /PID $oldPid /T /F 2>$null | Out-Null }}
  Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}}

for ($attempt = 0; $attempt -lt 3; $attempt++) {{
  $listenPids = @(Get-NetTCPConnection -LocalPort ([int]$port) -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
  $matchingPids = @(Get-CimInstance Win32_Process |
    Where-Object {{
      $_.CommandLine -and (
        $_.CommandLine -match [regex]::Escape($baseDir) -or
        $_.CommandLine -match 'run-comfyui\.bat' -or
        $_.CommandLine -match 'start-comfyui-minimized\.cmd' -or
        $_.CommandLine -match 'start-comfyui-hidden\.ps1' -or
        ($_.CommandLine -match 'main\.py' -and $_.CommandLine -match ('--port\s+' + [regex]::Escape($port)))
      )
    }} |
    Select-Object -ExpandProperty ProcessId)
  $pids = @($listenPids + $matchingPids) | Where-Object {{ $_ }} | Sort-Object -Unique -Descending
  foreach ($pidToKill in $pids) {{
    taskkill /PID $pidToKill /T /F 2>$null | Out-Null
    Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
  }}
  Start-Sleep -Seconds 2
}}

$remainingPids = @(Get-CimInstance Win32_Process |
  Where-Object {{
    $_.CommandLine -and
    $_.CommandLine -match 'main\.py' -and
    $_.CommandLine -match ('--port\s+' + [regex]::Escape($port))
  }} |
  Select-Object -ExpandProperty ProcessId)
foreach ($pidToKill in $remainingPids) {{
  taskkill /PID $pidToKill /T /F 2>$null | Out-Null
  Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
}}
Start-Sleep -Seconds 2

Remove-Item (Join-Path $nodeDir '__pycache__') -Recurse -Force -ErrorAction SilentlyContinue
Set-Content -Path (Join-Path $nodeDir 'mobile_entry_url.txt') -Value $mobileEntryUrl -Encoding UTF8 -NoNewline

$starter = @"
Set-Location '$comfyDir'
`$env:RPP_BLOCK_REMOTE_ASSET_SAVE = '1'
`$env:RPP_MOBILE_ENTRY_URL = {ps_quote(mobile_entry_url)}
`$env:RPP_MAC_VIDEO_UPLOAD_URL = {ps_quote(video_upload_url)}
`$env:RPP_MAC_SOURCE_IMAGE_URL = {ps_quote(source_image_url)}
`$env:RPP_REMOTE_TRANSFER_TOKEN = {ps_quote(token)}
`$p = Start-Process -FilePath '$venvPython' -ArgumentList @('-u', 'main.py', '--enable-manager', '--listen', '0.0.0.0', '--port', '$port') -WorkingDirectory '$comfyDir' -WindowStyle Hidden -RedirectStandardOutput '$stdoutLog' -RedirectStandardError '$stderrLog' -PassThru
Set-Content -Path '$pidFile' -Value `$p.Id -Encoding ASCII -NoNewline
"@
Set-Content -Path $hiddenStarter -Value $starter -Encoding UTF8 -NoNewline

$taskCommand = 'powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $hiddenStarter + '"'
schtasks /Create /TN $taskName /SC ONCE /ST 23:59 /TR $taskCommand /IT /RL HIGHEST /F | Out-Null
schtasks /Run /TN $taskName | Out-Null

$ready = $false
for ($i = 1; $i -le 90; $i++) {{
  Start-Sleep -Seconds 2
  try {{
    Invoke-RestMethod -Uri "http://127.0.0.1:$port/queue" -Method Get -TimeoutSec 5 | Out-Null
    $ready = $true
    break
  }} catch {{}}
  if (($i % 5) -eq 0) {{
    Write-Output "remote startup wait: $($i * 2)s"
  }}
}}

if ($ready) {{
  $listenPids = @(Get-NetTCPConnection -LocalPort ([int]$port) -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
  Write-Output "remote restart ready: port=$port listener=$($listenPids -join ',') task=$taskName"
}} else {{
  Write-Output "remote restart failed: port=$port is not ready after 180s"
  Get-Content $stderrLog -Tail 80 -ErrorAction SilentlyContinue
  exit 2
}}
'''
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        REMOTE_SSH,
        f"powershell -NoProfile -EncodedCommand {encoded_powershell(script)}",
    ]
    code = subprocess.call(command)
    if code == 0 and not wait_remote_queue():
        return 3
    return code


def wait_remote_queue(timeout=180):
    url = f"http://{REMOTE_SSH.rsplit('@', 1)[-1]}:{PORT}/queue"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    print(f"remote external check ready: {url}")
                    return True
        except Exception as exc:
            remaining = int(deadline - time.time())
            if remaining % 20 in {0, 1, 2, 3, 4}:
                print(f"remote external check waiting: {exc}")
        time.sleep(2)
    print(f"remote external check failed: {url}")
    return False


if __name__ == "__main__":
    sys.exit(main())
