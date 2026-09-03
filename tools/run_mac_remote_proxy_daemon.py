#!/usr/bin/env python3
import os
import signal
import socket
import subprocess
import sys

from proxy_config import ERR_FILE, LOG_FILE, PID_FILE, PROJECT, PROXY, PROXY_PORT, PYTHON, proxy_env

RESTART_PROXY = os.environ.get("RPP_PROXY_RESTART", "0") == "1"


def running(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def process_matches(pid):
    try:
        output = subprocess.check_output(["ps", "-p", str(pid), "-o", "command="], text=True).strip()
    except Exception:
        return False
    return str(PROXY) in output


def port_listening(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        return sock.connect_ex(("127.0.0.1", int(port))) == 0
    finally:
        sock.close()


def stop_proxy(pid):
    if not pid or not running(pid):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    for _ in range(30):
        if not running(pid):
            return
        import time

        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def main():
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
        except ValueError:
            pid = 0
        if RESTART_PROXY and pid and running(pid) and process_matches(pid):
            stop_proxy(pid)
            PID_FILE.unlink(missing_ok=True)
        elif pid and running(pid) and process_matches(pid) and port_listening(PROXY_PORT):
            print(pid)
            return
        else:
            PID_FILE.unlink(missing_ok=True)

    with LOG_FILE.open("ab", buffering=0) as stdout, ERR_FILE.open("ab", buffering=0) as stderr:
        process = subprocess.Popen(
            [str(PYTHON), str(PROXY)],
            cwd=str(PROJECT),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            env=proxy_env(),
            start_new_session=True,
        )
    PID_FILE.write_text(str(process.pid))
    print(process.pid)


if __name__ == "__main__":
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    sys.exit(main())
