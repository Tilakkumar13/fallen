"""Sum GHS-POP 2020 (30 arc-second) into a 0.25-degree grid -> pop_grid.npz (a few MB).
Run:  pip install tifffile imagecodecs  &&  python agg_pop.py
"""
import time, numpy as np, tifffile
TIF = "GHS_POP_E2020_GLOBE_R2023A_4326_30ss_V1_0.tif"; R = 0.25; NY, NX = int(180 / R), int(360 / R)
t0 = time.time(); out = np.zeros(NY * NX)
with tifffile.TiffFile(TIF) as t:
    p = t.pages[0]; sx, sy = p.tags["ModelPixelScaleTag"].value[:2]; x0, y0 = p.tags["ModelTiepointTag"].value[3:5]
    h, w = p.shape[:2]; print("raster", p.shape, p.dtype, "pixel", sx, sy, "origin", x0, y0, "tiled", p.is_tiled)
    n = 0
    for seg, idx, shape in p.segments():
        if seg is None: continue
        tile = np.squeeze(np.asarray(seg)).astype(np.float64)
        if tile.ndim == 1: tile = tile[None, :]
        tile = np.where(np.isfinite(tile) & (tile > 0), tile, 0)
        r0, c0 = idx[2], idx[3]
        rows, cols = min(tile.shape[0], h - r0), min(tile.shape[1], w - c0); tile = tile[:rows, :cols]
        lat = y0 - (r0 + np.arange(rows) + .5) * sy; lon = x0 + (c0 + np.arange(cols) + .5) * sx
        i = np.clip(((90 - lat) / R).astype(int), 0, NY - 1); j = np.clip(((lon + 180) / R).astype(int), 0, NX - 1)
        out += np.bincount((i[:, None] * NX + j[None, :]).ravel(), weights=tile.ravel(), minlength=NY * NX)
        n += 1
        if n % 3000 == 0: print(f"{n} blocks, {time.time() - t0:.0f}s")
np.savez_compressed("pop_grid.npz", pop=out.reshape(NY, NX).astype(np.float32))
print(f"done: world population {out.sum() / 1e9:.2f} billion (should be about 7.8), {time.time() - t0:.0f}s")
