"""Generate placeholder PNG icons for the Teams app manifest."""
import struct
import zlib
import os

def create_png(path, width, height, r, g, b):
    """Create a solid-color PNG file."""
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    header = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
    raw = b''
    for _ in range(height):
        raw += b'\x00' + bytes([r, g, b]) * width
    idat = chunk(b'IDAT', zlib.compress(raw))
    iend = chunk(b'IEND', b'')

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(header + ihdr + idat + iend)

# Color icon: 192x192 blue (#0078D4)
create_png('bot/teams-manifest/color.png', 192, 192, 0, 120, 212)
# Outline icon: 32x32 white
create_png('bot/teams-manifest/outline.png', 32, 32, 255, 255, 255)
print('Icons created')
