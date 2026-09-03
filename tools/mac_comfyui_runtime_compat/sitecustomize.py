"""Mac ComfyUI runtime compatibility hooks."""

from contextlib import suppress


def _patch_aiohttp_keepalive():
    try:
        import socket
        from aiohttp import tcp_helpers
    except ImportError:
        return

    def tcp_keepalive(transport):
        sock = transport.get_extra_info("socket")
        if sock is not None:
            # Some macOS sockets reject SO_KEEPALIVE during connection setup.
            with suppress(OSError):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    tcp_helpers.tcp_keepalive = tcp_keepalive


_patch_aiohttp_keepalive()
