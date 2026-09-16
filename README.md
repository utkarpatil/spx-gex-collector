# SPX Gamma-Exposure Collector (GitHub Actions)

Collects SPX 0DTE gamma-exposure data **every 5 minutes during US market hours**,
running entirely on GitHub's servers — your computer can be off. Each run appends
to the data files and commits them back to this repo.

## Output
- `data/collected/gex_live.csv` — one summary row per tick (opens in Excel)
- `data/collected/SPX_<date>.ndjson` — full per-strike detail (OI + volume + gamma)

## Setup (one time)
1. Create a **new repository** on GitHub (Public = unlimited free Actions minutes;
   Private works too but free accounts get 2,000 min/month).
2. Upload every file in this folder to the repo (keep the folder structure — the
   `.github/workflows/collect.yml` path matters).
3. On GitHub: **Settings → Actions → General → Workflow permissions →**
   select **"Read and write permissions"**, Save. (Lets the job commit data back.)
4. Open the **Actions** tab → pick **"Collect SPX GEX"** → **Run workflow** to test it
   once. Then it runs automatically every 5 min during market hours.

## Notes / honest caveats
- **Timing is approximate.** GitHub's scheduled runs can be delayed or skipped under
  load (5-min minimum). Fine for gamma, just not perfectly regular.
- **Yahoo may throttle datacenter IPs.** If runs start failing/returning thin data,
  that's Yahoo rate-limiting GitHub's servers — the job skips those and retries next tick.
- **Gamma vs the app:** this repo is *only* the data collector. The screener/UI stays
  on your machine; point it at this data later if you want.
- Uses our own Black-Scholes gamma, so the absolute Net may differ from a vendor by a
  scale factor, but regime/levels line up. Not trading advice.
