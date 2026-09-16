"""
Standalone SPX gamma-exposure collector.
Runs independently of the web app. Each run: if the US market is open, fetch the
^SPX 0DTE chain from Yahoo, compute OI-based GEX (verified formula + IV interp),
and append ONE record to data/collected/SPX_<date>.ndjson.

Schedule it with Windows Task Scheduler (see setup_collector.bat) to run every
few minutes. It exits instantly when the market is closed.

  python collect_gex.py           # normal (only writes during market hours)
  python collect_gex.py --force   # write even if market closed (for testing)
"""
import os, sys, json, csv, datetime as dt
from math import log as ln, sqrt, exp as mexp, pi
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model as M
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:
    ET = None

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "collected")
os.makedirs(OUT, exist_ok=True)
WINDOW = 60   # strikes each side-ish (nearest N to spot) to save


def log(msg):
    line = "%s  %s" % (dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line)
    with open(os.path.join(OUT, "collector.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def now_et():
    return dt.datetime.now(ET) if ET else dt.datetime.utcnow() - dt.timedelta(hours=4)


def market_open(t):
    return t.weekday() < 5 and (9 * 60 + 30) <= (t.hour * 60 + t.minute) < 16 * 60


def npdf(x): return mexp(-x * x / 2) / sqrt(2 * pi)
def bs_gamma(S, K, T, iv, r=0.04):
    if iv <= 0 or T <= 0 or S <= 0 or K <= 0: return 0.0
    d1 = (ln(S / K) + (r + 0.5 * iv * iv) * T) / (iv * sqrt(T))
    return npdf(d1) / (S * iv * sqrt(T))


def interp(x, xs, ys):
    if not xs: return 0.0
    if x <= xs[0]: return ys[0]
    if x >= xs[-1]: return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            if xs[i + 1] == xs[i]: return ys[i]
            w = (x - xs[i]) / (xs[i + 1] - xs[i]); return ys[i] + w * (ys[i + 1] - ys[i])
    return ys[-1]


def collect(force=False):
    t = now_et()
    if not force and not market_open(t):
        return  # silent: closed
    import yfinance as yf
    tk = yf.Ticker("^SPX")
    spot = float(tk.fast_info["lastPrice"])
    expiry = tk.options[0]
    ch = tk.option_chain(expiry)
    calls = ch.calls.set_index("strike"); puts = ch.puts.set_index("strike")
    T = max((t.replace(hour=16, minute=0, second=0, microsecond=0) - t).total_seconds(), 900) / (365 * 24 * 3600)
    f = spot * spot * 0.01 * 100
    strikes = sorted(set(calls.index) | set(puts.index))

    def val(df, K, col):
        try:
            v = df.loc[K, col]
        except Exception:
            return 0.0
        try:
            v = float(v)
        except (TypeError, ValueError):
            return 0.0
        return v if v == v else 0.0   # 0 for NaN
    ivk, ivv = [], []
    for K in strikes:
        vs = [v for v in (val(calls, K, "impliedVolatility"), val(puts, K, "impliedVolatility")) if v > 0]
        if vs: ivk.append(K); ivv.append(sum(vs) / len(vs))

    rows, oi_total = [], 0
    for K in strikes:
        g = bs_gamma(spot, K, T, interp(K, ivk, ivv))
        coi = val(calls, K, "openInterest"); poi = val(puts, K, "openInterest")
        cvol = val(calls, K, "volume"); pvol = val(puts, K, "volume")
        oi_total += coi + poi
        cg = g * coi * f; pg = -g * poi * f
        rows.append(dict(strike=K, cg=round(cg, 1), pg=round(pg, 1), net=round(cg + pg, 1),
                         abs=round(abs(cg) + abs(pg), 1), coi=int(coi), poi=int(poi),
                         cvol=int(cvol), pvol=int(pvol)))
    if oi_total < 1000:
        log("thin OI read (total=%d) — skipped" % oi_total); return

    ws = sorted(rows, key=lambda r: abs(r["strike"] - spot))[:WINDOW]
    ws.sort(key=lambda r: r["strike"])
    win40 = sorted(rows, key=lambda r: abs(r["strike"] - spot))[:40]

    # window-40 features (same definitions the model uses)
    net_b = round(sum(r["net"] for r in win40) / 1e9, 3)
    abs_b = round(sum(r["abs"] for r in win40) / 1e9, 3)
    absg = sum(r["abs"] for r in win40) or 1
    byabs = sorted(win40, key=lambda r: r["abs"], reverse=True)
    magnet = byabs[0]["strike"]; magfrac = byabs[0]["abs"] / absg
    above = [r for r in win40 if r["strike"] > spot]
    below = [r for r in win40 if r["strike"] < spot]
    call_wall = max(above, key=lambda r: r["cg"])["strike"] if above else magnet
    put_wall = min(below, key=lambda r: r["pg"])["strike"] if below else magnet
    ss = sorted(win40, key=lambda r: r["strike"]); flip = None
    for i in range(len(ss) - 1):
        a, b = ss[i], ss[i + 1]
        if (a["net"] < 0 <= b["net"]) or (a["net"] > 0 >= b["net"]): flip = a["strike"]; break
    pos = any(r["net"] > 0 for r in win40); neg = any(r["net"] < 0 for r in win40)
    ftype = "all_green" if (pos and not neg) else "all_red" if (neg and not pos) else "mixed"
    cvol = sum(r["cvol"] for r in win40); pvol = sum(r["pvol"] for r in win40)
    feat = dict(net_b=net_b, flip_type=ftype, spot=spot, flip=flip, magnet=magnet,
                magnet_frac=magfrac, call_vol=cvol, put_vol=pvol)
    regime = M.regime_of(net_b); condition = M.label(feat)
    mtime = t.hour * 100 + t.minute
    collected = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1) detailed per-strike record -> NDJSON
    rec = dict(schema="gammascope.gex.v1", source="yahoo", symbol="SPX",
               session_date=t.strftime("%Y-%m-%d"), market_time=mtime, collected_at=collected,
               expiry=expiry, uprice=round(spot, 2), net_b=net_b, abs_b=abs_b, regime=regime,
               condition=condition, magnet=magnet, call_wall=call_wall, put_wall=put_wall,
               flip=flip, flip_type=ftype, call_vol=cvol, put_vol=pvol,
               strike_count=len(ws), data=ws)
    with open(os.path.join(OUT, "SPX_%s.ndjson" % t.strftime("%Y-%m-%d")), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")

    # 2) one-row summary -> master CSV (opens in Excel)
    csv_path = os.path.join(OUT, "gex_live.csv")
    cols = ["collected_at", "session_date", "market_time", "spot", "net_b", "abs_b",
            "regime", "condition", "magnet", "call_wall", "put_wall", "flip", "flip_type",
            "call_vol", "put_vol"]
    new = not os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as cf:
        w = csv.DictWriter(cf, fieldnames=cols, extrasaction="ignore")
        if new: w.writeheader()
        w.writerow(dict(collected_at=collected, session_date=t.strftime("%Y-%m-%d"),
                        market_time=mtime, spot=round(spot, 2), net_b=net_b, abs_b=abs_b,
                        regime=regime, condition=condition, magnet=magnet, call_wall=call_wall,
                        put_wall=put_wall, flip=flip if flip is not None else "", flip_type=ftype,
                        call_vol=cvol, put_vol=pvol))
    log("saved %s %d  spot=%.2f net=%.2fB %s/%s strikes=%d" %
        (t.strftime("%Y-%m-%d"), mtime, spot, net_b, regime, condition, len(ws)))


if __name__ == "__main__":
    try:
        collect(force="--force" in sys.argv)
    except Exception as e:
        log("ERROR: %s" % e)
