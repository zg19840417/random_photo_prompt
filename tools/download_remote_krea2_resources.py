#!/usr/bin/env python3
import base64
import subprocess
import sys


REMOTE_SSH = "administrator@192.168.123.111"


def encoded_powershell(script):
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def main():
    script = r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$downloads = @(
  @{
    Url = 'https://huggingface.co/Comfy-Org/Krea-2/resolve/main/text_encoders/qwen3vl_4b_fp8_scaled.safetensors'
    Path = 'D:\ComfyUI\ComfyUI\models\text_encoders\qwen3vl_4b_fp8_scaled.safetensors'
  },
  @{
    Url = 'https://huggingface.co/Comfy-Org/Krea-2/resolve/main/vae/qwen_image_vae.safetensors'
    Path = 'D:\ComfyUI\ComfyUI\models\vae\qwen_image_vae.safetensors'
  }
)

foreach ($item in $downloads) {
  $dir = Split-Path -Parent $item.Path
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  if ((Test-Path $item.Path) -and ((Get-Item $item.Path).Length -gt 1048576)) {
    Write-Output "exists: $($item.Path)"
    continue
  }
  $tmp = "$($item.Path).part"
  Remove-Item $tmp -Force -ErrorAction SilentlyContinue
  Write-Output "downloading: $($item.Url)"
  Invoke-WebRequest -Uri $item.Url -OutFile $tmp -UseBasicParsing
  Move-Item $tmp $item.Path -Force
  Write-Output "saved: $($item.Path) bytes=$((Get-Item $item.Path).Length)"
}
"""
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        REMOTE_SSH,
        f"powershell -NoProfile -EncodedCommand {encoded_powershell(script)}",
    ]
    return subprocess.call(command)


if __name__ == "__main__":
    sys.exit(main())
