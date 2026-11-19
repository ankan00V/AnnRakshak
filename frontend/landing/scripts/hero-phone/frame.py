"""Sets an iPhone-size capture (1179 x 2556) in a straight-on phone: a black
bezel, a titanium edge with a highlight, and the side buttons. Drawn at twice
the size and scaled down, so the curves are smooth. Background transparent;
the page adds the shadow.

    python frame.py out/scan.png ../../public/photos/phone-scan.webp [width]
"""
import sys
from PIL import Image, ImageDraw

src, dst = sys.argv[1], sys.argv[2]
out_w = int(sys.argv[3]) if len(sys.argv) > 3 else 620
S = 2
screen = Image.open(src).convert('RGBA')
sw, sh = screen.size
R = 165          # the screen's corner radius at 3x (55 points)
BEZEL, EDGE, BTN = 36, 16, 10

W = sw + 2 * (BEZEL + EDGE + BTN)
H = sh + 2 * (BEZEL + EDGE)
im = Image.new('RGBA', (W * S, H * S), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
s = lambda *v: [x * S for x in v]

# Side buttons, behind the edge: action and volume on the left, power on the right.
for y0, y1 in [(330, 430), (520, 700), (740, 920)]:
    d.rounded_rectangle(s(0, y0, BTN + EDGE + 4, y1), radius=4 * S, fill='#5f6461')
d.rounded_rectangle(s(W - BTN - EDGE - 4, 600, W, 880), radius=4 * S, fill='#5f6461')

# The titanium edge: a lit outer line, the brushed metal, a dark inner line.
x0, x1 = BTN, W - BTN
outer = R + BEZEL + EDGE
d.rounded_rectangle(s(x0, 0, x1, H), radius=outer * S, fill='#c9cdca')
d.rounded_rectangle(s(x0 + 2, 2, x1 - 2, H - 2), radius=(outer - 2) * S, fill='#8e9390')
d.rounded_rectangle(s(x0 + 6, 6, x1 - 6, H - 6), radius=(outer - 6) * S, fill='#a7aba8')
d.rounded_rectangle(s(x0 + EDGE - 3, EDGE - 3, x1 - EDGE + 3, H - EDGE + 3), radius=(R + BEZEL + 3) * S, fill='#3a3d3b')
# The bezel.
d.rounded_rectangle(s(x0 + EDGE, EDGE, x1 - EDGE, H - EDGE), radius=(R + BEZEL) * S, fill='#0a0a0b')

# The screen, with its rounded corners.
big = screen.resize((sw * S, sh * S), Image.LANCZOS)
mask = Image.new('L', big.size, 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, sw * S - 1, sh * S - 1], radius=R * S, fill=255)
im.paste(big, ((BTN + EDGE + BEZEL) * S, (EDGE + BEZEL) * S), mask)

out = im.resize((out_w, round(H * out_w / W)), Image.LANCZOS)
out.save(dst, 'WEBP', quality=88, method=6)
print(dst, out.size)
