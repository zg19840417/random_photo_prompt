#!/usr/bin/env python3
import os
import subprocess
import time
import urllib.parse
from pathlib import Path


SERVER = os.environ.get("RPP_MODELS_SMB_SERVER", "192.168.123.111")
SHARE = os.environ.get("RPP_MODELS_SMB_SHARE", "ComfyUIModels")
USER = os.environ.get("RPP_MODELS_SMB_USER", "ComfyShare")
MOUNT_POINT = Path(os.environ.get("RPP_MODELS_MOUNT", "/Users/zouge/远程模型文件夹")).expanduser()
EXPECTED_DIRS = {"diffusion_models", "loras", "text_encoders", "upscale_models", "vae"}


def run(args, check=False):
    return subprocess.run(args, text=True, capture_output=True, check=check)


def log(message):
    print(f"[remote-models-mount] {time.strftime('%Y-%m-%d %H:%M:%S')} {message}", flush=True)


def keychain_password():
    result = run(["security", "find-internet-password", "-s", SERVER, "-a", USER, "-w"])
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"cannot read SMB password for {USER}@{SERVER}: {result.stderr.strip()}")
    return result.stdout.strip()


def mounted_at_target():
    result = run(["mount"])
    needle = f" on {MOUNT_POINT} "
    return result.returncode == 0 and needle in result.stdout


def usable():
    if not MOUNT_POINT.is_dir():
        return False
    try:
        result = run(["/bin/ls", "-1", str(MOUNT_POINT)])
        if result.returncode != 0:
            return False
        names = set(result.stdout.splitlines())
    except Exception:
        return False
    return bool(EXPECTED_DIRS & names)


def mount_share():
    MOUNT_POINT.mkdir(parents=True, exist_ok=True)
    password = urllib.parse.quote(keychain_password(), safe="")
    url = f"//{USER}:{password}@{SERVER}/{SHARE}"
    result = run(["mount_smbfs", url, str(MOUNT_POINT)])
    if result.returncode != 0 and not usable():
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "mount_smbfs failed")


def wait_until_usable(seconds=30):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if usable():
            return True
        time.sleep(0.5)
    return usable()


def main():
    if usable():
        log(f"ok {MOUNT_POINT}")
        return 0
    if mounted_at_target():
        log(f"mounted but not readable yet; keep existing mount {MOUNT_POINT}")
        return 0
    log("mount is missing; mounting")
    mount_share()
    if not wait_until_usable():
        log("mounted; folder listing is still warming up")
        return 0
    log(f"mounted {MOUNT_POINT}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"failed: {exc}")
        raise SystemExit(1)
