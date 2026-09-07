#!/usr/bin/env python3
"""生成 Tauri 桌面端所需的全部图标（PNG / ICO / ICNS）。

产出到 desktop/src-tauri/icons/：
  icon.png           512×512
  32x32.png          32×32
  128x128.png        128×128
  128x128@2x.png     256×256
  icon.ico           16/32/48/64/128/256 多尺寸
  icon.icns          PNG 内嵌条目（ic07=128 / ic08=256 / ic09=512 / ic10=1024）

用法：python3 desktop/scripts/gen-icons.py
依赖：Pillow
"""
import struct
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "src-tauri" / "icons"
OUT.mkdir(parents=True, exist_ok=True)

# 主题色：深蓝底 + 知识图谱节点（与 Web 面板配色一致）
BG = (38, 70, 105, 255)
NODE_COLORS = [(139, 200, 234), (148, 216, 195), (244, 179, 147)]
LINE = (255, 255, 255, 210)


def draw(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=size * 0.22, fill=BG)

    nodes = [(0.30, 0.30), (0.70, 0.28), (0.52, 0.52), (0.28, 0.72), (0.72, 0.70)]
    edges = [(0, 2), (1, 2), (2, 3), (2, 4)]
    colors = [NODE_COLORS[0], NODE_COLORS[1], NODE_COLORS[2], NODE_COLORS[0], NODE_COLORS[1]]

    lw = max(2, size // 64)
    for a, b in edges:
        ax, ay = nodes[a]
        bx, by = nodes[b]
        d.line([ax * size, ay * size, bx * size, by * size], fill=LINE, width=lw)

    rn = size * 0.085
    for (x, y), c in zip(nodes, colors):
        d.ellipse([x * size - rn, y * size - rn, x * size + rn, y * size + rn], fill=c + (255,))
    return img


def write_icns(path: Path, entries: list[tuple[str, bytes]]) -> None:
    body = b"".join(
        struct.pack(">4sI", code.encode("ascii"), len(data) + 8) + data for code, data in entries
    )
    path.write_bytes(struct.pack(">4sI", b"icns", len(body) + 8) + body)


def main() -> None:
    png = {s: draw(s) for s in (32, 128, 256, 512, 1024)}
    png[512].save(OUT / "icon.png")
    png[32].save(OUT / "32x32.png")
    png[128].save(OUT / "128x128.png")
    png[256].save(OUT / "128x128@2x.png")

    ico = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    ico.alpha_composite(png[256])
    ico.save(OUT / "icon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    # icns：PNG 内嵌条目（macOS 接受 ic07/ic08/ic09/ic10 携带 PNG 数据）
    entries = [
        ("ic07", _png_bytes(png[128])),
        ("ic08", _png_bytes(png[256])),
        ("ic09", _png_bytes(png[512])),
        ("ic10", _png_bytes(png[1024])),
    ]
    write_icns(OUT / "icon.icns", entries)

    for f in sorted(OUT.iterdir()):
        print(f"[gen-icons] {f.name}  {f.stat().st_size} bytes")


def _png_bytes(im: Image.Image) -> bytes:
    import io

    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


if __name__ == "__main__":
    main()
