"""Puts the captured Scan screen into the phone render.

The render's screen is found as the largest bright region inside the phone,
its four edges are fitted as straight lines (the corners are rounded, so the
corners themselves are where those lines meet), and the capture is warped onto
that quadrilateral at twice the size and scaled down, so the text stays sharp.
The render's own frame, bezel and shadow are kept; only the screen is replaced.

    python compose.py phone-render.png out/scan.png ../../public/photos/hero-phone.webp
"""
import sys
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage as nd

render_path, screen_path, out_path = sys.argv[1:4]
render = Image.open(render_path).convert('RGBA')
px = np.asarray(render).astype(float)
lum = px[..., 0] * .3 + px[..., 1] * .59 + px[..., 2] * .11

# The screen: the largest bright region, holes (dark pixels in the old
# picture) filled in.
lab, n = nd.label((lum > 90) & (px[..., 3] > 250))
sizes = nd.sum(np.ones_like(lum), lab, range(1, n + 1))
screen = nd.binary_fill_holes(lab == (np.argmax(sizes) + 1))
ys, xs = np.nonzero(screen)
x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
w, h = x1 - x0, y1 - y0

def edge(axis_range, first, along_rows):
    pts = []
    for v in axis_range:
        line = screen[v, :] if along_rows else screen[:, v]
        idx = np.nonzero(line)[0]
        if len(idx):
            pts.append((v, idx[0] if first else idx[-1]))
    v, u = np.array(pts, float).T
    return np.polyfit(v, u, 1)  # u = a*v + b

rows = range(int(y0 + .25 * h), int(y1 - .25 * h))
cols = range(int(x0 + .3 * w), int(x1 - .3 * w))
L, R = edge(rows, True, True), edge(rows, False, True)    # x = a*y + b
T, B = edge(cols, True, False), edge(cols, False, False)  # y = a*x + b

def meet(xline, yline):
    # x = a*y + b and y = c*x + d
    a, b = xline; c, d = yline
    x = (a * d + b) / (1 - a * c)
    return x, c * x + d

quad = [meet(L, T), meet(R, T), meet(R, B), meet(L, B)]
print('screen corners', [(round(x), round(y)) for x, y in quad])

S = 2  # warp at twice the size, then scale down
cap = Image.open(screen_path).convert('RGBA')
cw, ch = cap.size
src = [(0, 0), (cw, 0), (cw, ch), (0, ch)]
dst = [(x * S, y * S) for x, y in quad]
# PIL maps each output pixel back to the input: solve for those 8 numbers.
A, bvec = [], []
for (X, Y), (u, v) in zip(dst, src):
    A.append([X, Y, 1, 0, 0, 0, -u * X, -u * Y]); bvec.append(u)
    A.append([0, 0, 0, X, Y, 1, -v * X, -v * Y]); bvec.append(v)
coeffs = np.linalg.solve(np.array(A), np.array(bvec))
big = cap.transform((render.width * S, render.height * S), Image.PERSPECTIVE, tuple(coeffs), Image.BICUBIC)
warped = big.resize(render.size, Image.LANCZOS)

# The mask: the screen region pulled in by one pixel and softened, so the
# render's bezel edge stays crisp and the corners are smooth.
m = nd.binary_erosion(screen, iterations=1)
mask = Image.fromarray((m * 255).astype('uint8')).filter(ImageFilter.GaussianBlur(0.8))
warped.putalpha(Image.fromarray(np.minimum(np.asarray(warped.getchannel('A')), np.asarray(mask))))

out = render.copy()
out.alpha_composite(warped)
out = out.crop(out.getchannel('A').getbbox())
out.save(out_path, 'WEBP', quality=90, method=6)
print(out_path, out.size)
