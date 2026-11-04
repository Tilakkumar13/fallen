"""ESA re-entry portal, 'Recovered debris' table -> CSV (one row per fragment)."""
import json, re, html, csv
h = json.load(open("raw/esa_api_home.json"))["recoveredDebris"]["htmlContent"]
t = h[h.index('<table class="space-debris-table">'):]
t = t[:t.index("</table>")]
heads = [html.unescape(re.sub("<[^>]+>", "", x)).strip() for x in re.findall(r"<th[^>]*>(.*?)</th>", t, re.S)]
rows = []
for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
    cells = re.findall(r"<td([^>]*)>(.*?)</td>", tr, re.S)
    if not cells: continue
    rows.append([(re.search(r'rowspan="(\d+)"', a), html.unescape(re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", c))).strip()) for a, c in cells])
print(heads, len(rows))
# expand rowspans
grid, pending = [], {}
for r in rows:
    out, it, col = [], iter(r), 0
    while col < len(heads):
        if col in pending and pending[col][0] > 0:
            out.append(pending[col][1]); pending[col][0] -= 1; col += 1; continue
        try: span, val = next(it)
        except StopIteration: out.append(""); col += 1; continue
        if span: pending[col] = [int(span.group(1)) - 1, val]
        out.append(val); col += 1
    grid.append(out)
w = csv.writer(open("esa_recovered.csv", "w", newline="")); w.writerow(heads); w.writerows(grid)
print(len(grid)); [print(g) for g in grid[:4]]
