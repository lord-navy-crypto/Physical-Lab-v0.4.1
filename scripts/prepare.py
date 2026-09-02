#!/usr/bin/env python3
from pathlib import Path
from shutil import copy2

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
DIST = ROOT / "dist"
ICONS = ROOT / "src-tauri" / "icons"
DIST.mkdir(parents=True, exist_ok=True)
ICONS.mkdir(parents=True, exist_ok=True)

for name in ("index.html", "styles.css", "app.js"):
    copy2(WEB / name, DIST / name)

# Icons are committed with the source package. Regenerate only when missing.
if not (ICONS / "icon.icns").exists():
    try:
        from PIL import Image, ImageDraw
        size = 1024
        img = Image.new("RGBA", (size, size), (14, 18, 28, 255))
        d = ImageDraw.Draw(img)
        pad = 100
        d.rounded_rectangle((pad, pad, size-pad, size-pad), radius=210, fill=(27, 34, 49, 255))
        center = (size//2, size//2)
        for w, h, angle in [(620, 250, 0), (620, 250, 60), (620, 250, 120)]:
            layer = Image.new("RGBA", (size, size), (0,0,0,0))
            ld = ImageDraw.Draw(layer)
            box=(center[0]-w//2, center[1]-h//2, center[0]+w//2, center[1]+h//2)
            ld.ellipse(box, outline=(210,220,235,235), width=22)
            layer=layer.rotate(angle, center=center, resample=Image.Resampling.BICUBIC)
            img.alpha_composite(layer)
        d=ImageDraw.Draw(img)
        d.ellipse((center[0]-66, center[1]-66, center[0]+66, center[1]+66), fill=(245,247,250,255))
        d.ellipse((center[0]+225, center[1]-34, center[0]+287, center[1]+28), fill=(245,247,250,255))
        img.save(ICONS / "icon.png")
        for name, px in [("32x32.png",32),("128x128.png",128),("128x128@2x.png",256)]:
            img.resize((px, px), Image.Resampling.LANCZOS).save(ICONS / name)
        img.save(ICONS / "icon.icns", format="ICNS")
    except ImportError:
        raise SystemExit("Physical Lab icons are missing and Pillow is unavailable. Restore src-tauri/icons from the source package.")

print("Prepared Physical Lab frontend and icons.")
