"""
Rebuild data/collected/gex_live.csv from the detailed SPX_*.ndjson files.
The NDJSON is the complete record; this regenerates the summary CSV (21 cols)
from it any time — e.g. after changing columns. Safe to run repeatedly.

  python rebuild_csv.py
"""
import os, json, csv, glob

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "collected")
COLS = ["collected_at", "session_date", "market_time", "expiry", "spot",
        "net_b", "net_full_b", "abs_b", "regime", "condition",
        "magnet", "magnet_frac", "call_wall", "put_wall", "flip", "flip_type",
        "call_oi", "put_oi", "pcr_oi", "call_vol", "put_vol"]


def row_from(d):
    data = d.get("data", []); spot = d["uprice"]
    win40 = sorted(data, key=lambda x: abs(x["strike"] - spot))[:40]
    absg = sum(x["abs"] for x in win40) or 1
    byabs = sorted(win40, key=lambda x: x["abs"], reverse=True)
    call_oi = sum(x["coi"] for x in win40); put_oi = sum(x["poi"] for x in win40)
    return dict(
        collected_at=d.get("collected_at", ""), session_date=d["session_date"],
        market_time=d["market_time"], expiry=d.get("expiry", ""), spot=spot,
        net_b=d["net_b"], net_full_b=round(sum(x["net"] for x in data) / 1e9, 3),
        abs_b=d["abs_b"], regime=d["regime"], condition=d["condition"],
        magnet=d["magnet"], magnet_frac=round(byabs[0]["abs"] / absg, 3),
        call_wall=d["call_wall"], put_wall=d["put_wall"],
        flip=d.get("flip") if d.get("flip") is not None else "", flip_type=d["flip_type"],
        call_oi=call_oi, put_oi=put_oi,
        pcr_oi=round(put_oi / call_oi, 3) if call_oi else "",
        call_vol=d["call_vol"], put_vol=d["put_vol"])


rows = []
for f in sorted(glob.glob(os.path.join(OUT, "SPX_*.ndjson"))):
    for line in open(f, encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(row_from(json.loads(line)))
rows.sort(key=lambda r: (r["session_date"], r["market_time"]))

with open(os.path.join(OUT, "gex_live.csv"), "w", newline="", encoding="utf-8") as cf:
    w = csv.DictWriter(cf, fieldnames=COLS)
    w.writeheader()
    w.writerows(rows)
print("rebuilt gex_live.csv from %d records" % len(rows))
