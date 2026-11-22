import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
def _fallback_pillow_thumb(badge: str, line1: str, line2: str, out_path: Path) -> Path:
img = Image.new("RGB", (1280, 720), "#0F172A")
draw = ImageDraw.Draw(img)
# Dải nhấn màu đỏ ở cạnh trên
draw.rectangle([0, 0, 1280, 16], fill="#DC2626")
font_candidates = [
"/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
"/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
font_path = next((f for f in font_candidates if Path(f).exists()), None)
font_badge = ImageFont.truetype(font_path, 42) if font_path else ImageFont.load_default()
font_main = ImageFont.truetype(font_path, 86) if font_path else ImageFont.load_default()
# Badge phần truyện
draw.rounded_rectangle([80, 90, 380, 175], radius=16, fill="#DC2626")
draw.text((120, 108), badge.upper(), fill="#FFFFFF", font=font_badge)
# Hai dòng tiêu đề lớn
draw.text((80, 240), line1.upper(), fill="#FACC15", font=font_main)
draw.text((80, 370), line2.upper(), fill="#FFFFFF", font=font_main)
draw.text((80, 610), "AUDIO DRAMA FULL • NGHE TRỌN TẬP", fill="#94A3B8", font=font_badge)
out_path.parent.mkdir(parents=True, exist_ok=True)
img.save(out_path, "PNG")
return out_path
def generate_thumbnail(badge: str, line1: str, line2: str, out_path: Path) -> Path:
"""Ưu tiên render bằng Satori (HTML/CSS -> PNG), tự fallback sang Pillow nếu chưa cài Node."""
satori_script = Path("thumb/render_thumb.mjs")
out_path.parent.mkdir(parents=True, exist_ok=True)
if satori_script.exists() and Path("thumb/node_modules").exists():
payload = json.dumps(
{"badge": badge, "line1": line1, "line2": line2, "output": str(out_path)},
ensure_ascii=False,
)
try:
subprocess.run(["node", str(satori_script), payload], check=True)
if out_path.exists():
print(f"[ThumbGen] Đã tạo thumbnail bằng Satori: {out_path}")
return out_path
except Exception as exc:
print(f"[ThumbGen] Satori lỗi ({exc}), chuyển sang Pillow fallback.")
print(f"[ThumbGen] Tạo thumbnail bằng Pillow fallback: {out_path}")
return _fallback_pillow_thumb(badge, line1, line2, out_path)
