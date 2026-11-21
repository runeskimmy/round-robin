"""Builds web/round-robin.html from web/src.html by embedding the fonts, so the app works offline as one file.

Run from anywhere:  python3 web/build.py
"""
import base64
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
FONTS = {
    '__BSD800__': 'big-shoulders-display-latin-800-normal.woff2',
    '__SG400__': 'schibsted-grotesk-latin-400-normal.woff2',
    '__SG700__': 'schibsted-grotesk-latin-700-normal.woff2',
}

src = (HERE / 'src.html').read_text(encoding='utf-8')
for key, name in FONTS.items():
    assert key in src, f'{key} missing from src.html'
    src = src.replace(key, base64.b64encode((HERE / 'fonts' / name).read_bytes()).decode())
out = HERE / 'round-robin.html'
out.write_text(src, encoding='utf-8')
print(f'{out} {out.stat().st_size // 1024} KB')
