import os
import shutil
import subprocess
from PIL import Image

DENSITIES = {
    'mdpi': (48, 108),
    'hdpi': (72, 162),
    'xhdpi': (96, 216),
    'xxhdpi': (144, 324),
    'xxxhdpi': (192, 432)
}

def save_as_webp(pil_img, out_path):
    tmp_png = out_path + ".tmp.png"
    pil_img.save(tmp_png, "PNG")
    try:
        subprocess.run(
            ["cwebp", "-quiet", "-lossless", tmp_png, "-o", out_path],
            check=True
        )
    finally:
        if os.path.exists(tmp_png):
            os.remove(tmp_png)

def generate_app_icons(input_image_path, output_dir):
    """
    Takes an input image and outputs all required WebP mipmap assets
    formatted for legacy and Android 16 adaptive icon systems.
    """
    os.makedirs(output_dir, exist_ok=True)
    with Image.open(input_image_path) as img:
        img = img.convert('RGBA')

        for density, (legacy_sz, adaptive_sz) in DENSITIES.items():
            density_dir = os.path.join(output_dir, f"res/mipmap-{density}-v4")
            os.makedirs(density_dir, exist_ok=True)

            # 1. Legacy Flat & Round Icons (48dp base)
            flat_icon = img.resize((legacy_sz, legacy_sz), Image.Resampling.LANCZOS)
            save_as_webp(flat_icon, os.path.join(density_dir, "ic_launcher.webp"))
            save_as_webp(flat_icon, os.path.join(density_dir, "ic_launcher_round.webp"))

            # 2. Adaptive Foreground (108dp canvas, ~66% safe-zone scaling)
            # Keeps Android 16 circular and squircle masks from cropping edges
            fg_canvas = Image.new('RGBA', (adaptive_sz, adaptive_sz), (0, 0, 0, 0))
            safe_size = int(adaptive_sz * 0.66)
            scaled_icon = img.resize((safe_size, safe_size), Image.Resampling.LANCZOS)
            offset = (adaptive_sz - safe_size) // 2
            fg_canvas.paste(scaled_icon, (offset, offset), scaled_icon)
            save_as_webp(fg_canvas, os.path.join(density_dir, "ic_launcher_foreground.webp"))

            # 3. Adaptive Background (neutral dark layer)
            bg_canvas = Image.new('RGBA', (adaptive_sz, adaptive_sz), (18, 18, 18, 255))
            save_as_webp(bg_canvas, os.path.join(density_dir, "ic_launcher_background.webp"))

    return True

if __name__ == '__main__':
    from PIL import ImageDraw
    test_img = Image.new('RGBA', (256, 256), (0, 230, 118, 255))
    draw = ImageDraw.Draw(test_img)
    draw.rectangle([64, 64, 192, 192], fill=(0, 0, 0, 255))
    test_img.save("test_icon.png")

    generate_app_icons("test_icon.png", "test_mipmap_out")
    print("[+] Native cwebp icon generator verified! Generated assets:")
    for root, _, files in os.walk("test_mipmap_out"):
        for f in files:
            print("   ", os.path.relpath(os.path.join(root, f), "test_mipmap_out"))

    os.remove("test_icon.png")
    shutil.rmtree("test_mipmap_out", ignore_errors=True)
