import json
import struct


PREVIEW_IMAGE_WITH_METADATA = 4
REMOTE_WEBSOCKET_MAX_MSG_SIZE = 64 * 1024 * 1024
REMOTE_RESULT_FRAME_GRACE_SECONDS = 12
IMAGE_TYPE_BY_MIME = {
    "image/jpeg": 1,
    "image/png": 2,
}


def websocket_connect_kwargs():
    return {"max_msg_size": REMOTE_WEBSOCKET_MAX_MSG_SIZE}


def receive_timeout_after_execution_end(image_count):
    """Keep the socket open briefly because the final image can follow the end event."""
    return REMOTE_RESULT_FRAME_GRACE_SECONDS if image_count == 0 else 0


def decode_preview_frame(data):
    raw = bytes(data)
    if len(raw) < 4:
        return None
    event_type = struct.unpack(">I", raw[:4])[0]
    if event_type != PREVIEW_IMAGE_WITH_METADATA:
        return None
    if len(raw) < 8:
        raise ValueError("远端图片帧缺少元数据长度。")
    metadata_length = struct.unpack(">I", raw[4:8])[0]
    image_offset = 8 + metadata_length
    if metadata_length <= 0 or len(raw) <= image_offset:
        raise ValueError("远端图片帧元数据或图片内容为空。")
    try:
        metadata = json.loads(raw[8:image_offset].decode("utf-8"))
    except Exception as exc:
        raise ValueError("远端图片帧元数据无效。") from exc
    if not isinstance(metadata, dict):
        raise ValueError("远端图片帧元数据不是对象。")
    mime_type = str(metadata.get("image_type") or "")
    image_type = IMAGE_TYPE_BY_MIME.get(mime_type)
    if image_type is None:
        raise ValueError(f"远端图片帧格式不受支持：{mime_type or 'unknown'}")
    image_bytes = raw[image_offset:]
    expected_header = b"\xff\xd8\xff" if image_type == 1 else b"\x89PNG\r\n\x1a\n"
    if not image_bytes.startswith(expected_header):
        raise ValueError("远端图片帧内容与声明格式不一致。")
    return {
        "prompt_id": str(metadata.get("prompt_id") or ""),
        "node_id": str(metadata.get("node_id") or ""),
        "image_type": image_type,
        "image_bytes": image_bytes,
    }
