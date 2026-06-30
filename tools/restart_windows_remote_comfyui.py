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
MAC_PROXY_CLEAR_URL = os.environ.get("RPP_MAC_PROXY_CLEAR_URL", "http://127.0.0.1:18199/random_photo_prompt/proxy/runtime/clear")
PROJECT_DIR = Path(__file__).resolve().parents[1]
MAC_LOCAL_MOBILE_STATUS_URL = os.environ.get("RPP_MAC_LOCAL_MOBILE_STATUS_URL", "http://127.0.0.1:8188/random_photo_prompt/mobile/status")
MAC_PROXY_STATUS_URL = os.environ.get("RPP_MAC_PROXY_STATUS_URL", "http://127.0.0.1:18199/random_photo_prompt/proxy/status")
MAC_SERVICE_WAIT_SECONDS = float(os.environ.get("RPP_MAC_SERVICE_WAIT_SECONDS", "8") or 8)


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def encoded_powershell(script):
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def main():
    ensure_mac_local_services()
    mac_upload_url = os.environ.get("RPP_MAC_IMAGE_UPLOAD_URL") or default_mac_upload_url()
    mac_video_upload_url = os.environ.get("RPP_MAC_VIDEO_UPLOAD_URL") or mac_upload_url.replace("/upload_image", "/upload_video")
    clear_mac_runtime_state("before_remote_restart")
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

$deletedFiles = 0
$deletedDirs = 0
if (Test-Path $outputDir) {{
  Get-ChildItem $outputDir -File -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object {{ -not $_.Name.StartsWith('.') -and $_.Name -ne '_output_images_will_be_put_here' }} |
    ForEach-Object {{
      Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
      if (-not (Test-Path $_.FullName)) {{ $script:deletedFiles++ }}
    }}
  Get-ChildItem $outputDir -Directory -Recurse -Force -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending |
    ForEach-Object {{
      $children = @(Get-ChildItem $_.FullName -Force -ErrorAction SilentlyContinue)
      if ($children.Count -eq 0) {{
        Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path $_.FullName)) {{ $script:deletedDirs++ }}
      }}
    }}
}}
Write-Output "remote output cleanup: files=$deletedFiles dirs=$deletedDirs path=$outputDir"

$starter = @"
Set-Location '$comfyDir'
`$env:RPP_BLOCK_REMOTE_ASSET_SAVE = '1'
`$env:RPP_MAC_IMAGE_UPLOAD_URL = '{mac_upload_url}'
`$env:RPP_MAC_VIDEO_UPLOAD_URL = '{mac_video_upload_url}'
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
    clear_mac_runtime_state("after_remote_restart")
    if code == 0 and not wait_remote_queue():
        return 3
    return code


def ensure_mac_local_services():
    checks = (
        ("mac local mobile", MAC_LOCAL_MOBILE_STATUS_URL, PROJECT_DIR / "tools/run_mac_local_comfyui_daemon.py"),
        ("mac proxy", MAC_PROXY_STATUS_URL, PROJECT_DIR / "tools/run_mac_remote_proxy_daemon.py"),
    )
    for label, url, script in checks:
        if url_ready(url, timeout=3):
            print(f"{label} ready: {url}")
            continue
        print(f"{label} starting: {script}")
        subprocess.call([sys.executable, str(script)], cwd=str(PROJECT_DIR))
        if wait_url(url, timeout=MAC_SERVICE_WAIT_SECONDS):
            print(f"{label} ready: {url}")
        else:
            print(f"{label} warning: {url} not ready, continuing remote restart")


def url_ready(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 500
    except Exception:
        return False


def wait_url(url, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if url_ready(url, timeout=3):
            return True
        time.sleep(2)
    return False


def clear_mac_runtime_state(reason):
    payload = f'{{"reason": "{reason}"}}'.encode("utf-8")
    try:
        import urllib.request

        request = urllib.request.Request(MAC_PROXY_CLEAR_URL, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=8) as response:
            body = response.read(500).decode("utf-8", "ignore")
            print(f"cleared mac runtime state: {MAC_PROXY_CLEAR_URL} HTTP {response.status} {body}")
    except Exception as exc:
        print(f"mac runtime clear skipped: {MAC_PROXY_CLEAR_URL} {exc}")


def default_mac_upload_url():
    host = os.environ.get("RPP_MAC_LAN_HOST", "").strip()
    if not host:
        remote_host = REMOTE_SSH.rsplit("@", 1)[-1].split(":", 1)[0]
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect((remote_host, int(PORT)))
            host = sock.getsockname()[0]
        finally:
            sock.close()
    return f"http://{host}:18199/random_photo_prompt/proxy/upload_image"


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
