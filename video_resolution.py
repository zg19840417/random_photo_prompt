from __future__ import annotations

import math

from PIL import Image


MAXIMUM_VIDEO_PIXELS = 620_000


def image_to_video_resolution(source_image_path, maximum_side=960, maximum_pixels=MAXIMUM_VIDEO_PIXELS):
    """Return a source-bounded MiniMax H3 size on a 32-pixel grid within both limits."""
    multiple = 32
    maximum_side = max(multiple, int(maximum_side) // multiple * multiple)
    maximum_pixels = max(multiple * multiple, int(maximum_pixels))

    def fallback_size():
        side = min(maximum_side, int(math.sqrt(maximum_pixels)) // multiple * multiple)
        return max(multiple, side), max(multiple, side)

    try:
        with Image.open(source_image_path) as image:
            source_width, source_height = image.size
    except Exception:
        return fallback_size()
    source_width = max(1, int(source_width))
    source_height = max(1, int(source_height))
    source_longest_side = max(source_width, source_height)
    scale = min(
        1,
        maximum_side / source_longest_side,
        math.sqrt(maximum_pixels / (source_width * source_height)),
    )

    def aligned(value, source_value):
        candidate = min(maximum_side, max(multiple, round(value / multiple) * multiple))
        if candidate > source_value:
            candidate = max(multiple, source_value // multiple * multiple)
        return candidate

    def aligned_down(value, source_value):
        candidate = min(maximum_side, max(multiple, int(value) // multiple * multiple))
        if candidate > source_value:
            candidate = max(multiple, source_value // multiple * multiple)
        return candidate

    width = aligned(source_width * scale, source_width)
    height = aligned(source_height * scale, source_height)
    source_ratio = source_width / source_height

    if width * height > maximum_pixels:
        # Flooring both dimensions preserves the source ratio better than shrinking one axis only.
        width = aligned_down(source_width * scale, source_width)
        height = aligned_down(source_height * scale, source_height)

    # Rounding to the required grid can push an otherwise valid ratio over the pixel cap.
    while width * height > maximum_pixels:
        candidates = []
        if width > multiple:
            candidates.append((width - multiple, height))
        if height > multiple:
            candidates.append((width, height - multiple))
        if not candidates:
            return fallback_size()
        width, height = min(
            candidates,
            key=lambda size: abs((size[0] / size[1]) - source_ratio),
        )
    return width, height
