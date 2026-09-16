"""
Gamma prediction model — shared condition labeling + prediction.
Used by build.py (to bake replay data) and app.py (for live).
Turns one snapshot's gamma features into: regime, condition, predicted range band,
pin target + hit-rate, direction lean, and a confidence tier.
"""

# ---- condition labeling (matches the backtest) ----
MAGNET_CONDS = {"C1_single_magnet", "C2_two_bars", "C3_allgreen_up", "C8_coil_pin"}

COND_LABELS = {
    "C1_single_magnet":        "Single magnet (pin)",
    "C2_two_bars":             "Two bars (support/resistance)",
    "C3_allgreen_up":          "All green (quiet)",
    "C4_repel_heavyputs_down": "Repellent · heavy puts",
    "C5_repel_from_above_up":  "Repellent · from above",
    "C6_repel_from_below_down":"Repellent · from below",
    "C7_allred_down":          "All red (down lean)",
    "C8_coil_pin":             "Coil (pinned to line)",
    "C0_balanced_other":       "Balanced / transition",
}


def label(f):
    net = f["net_b"]; ft = f["flip_type"]; spot = f["spot"]; flip = f["flip"]
    if ft == "all_green": return "C3_allgreen_up"
    if ft == "all_red":   return "C7_allred_down"
    if net >= 2:
        return "C1_single_magnet" if f["magnet_frac"] >= 0.15 else "C2_two_bars"
    if net <= -2:
        pv, cv = f.get("put_vol"), f.get("call_vol")
        if pv and cv and pv > 1.10 * cv: return "C4_repel_heavyputs_down"
        if flip is not None and spot > flip: return "C5_repel_from_above_up"
        return "C6_repel_from_below_down"
    if flip is not None and abs(spot - flip) <= 15: return "C8_coil_pin"
    return "C0_balanced_other"


def regime_of(net_b):
    if net_b >= 4:  return "strong_pos"
    if net_b >= 1:  return "pos"
    if net_b > -2:  return "balanced"
    if net_b > -8:  return "neg"
    return "strong_neg"


def time_bucket(t):
    t = int(t)
    if t <= 1025: return "open"
    if t <= 1200: return "mid_am"
    if t <= 1400: return "mid_pm"
    return "close"


REGIME_LABEL = {"strong_pos": "Calm (strong +γ)", "pos": "Calm (+γ)",
                "balanced": "Balanced", "neg": "Wild (−γ)", "strong_neg": "Wild (strong −γ)"}
REGIME_KIND = {"strong_pos": "calm", "pos": "calm", "balanced": "coil",
               "neg": "wild", "strong_neg": "wild"}


def predict(f, model):
    """f: dict with net_b, flip_type, spot, flip, magnet, magnet_frac, call_wall,
    put_wall, time, call_vol, put_vol, (optional) net_chg_30. Returns prediction dict."""
    cond = f.get("condition") or label(f)
    reg = f.get("regime") or regime_of(f["net_b"])
    bucket = time_bucket(f["time"])
    spot, magnet = f["spot"], f["magnet"]

    # expected remaining range (rest of day) — condition+time, fall back to regime+time
    ct = model["cond_time"].get(f"{cond}|{bucket}")
    if ct and ct["n"] >= 15:
        rng = ct["med_remaining"]
    else:
        rt = model["regime_time"].get(f"{reg}|{bucket}", {})
        rng = rt.get("med_remaining", model["overall_med_remaining"])

    cs = model["conditions"].get(cond, {})
    center = magnet if cond in MAGNET_CONDS else spot
    half = rng / 2.0
    band_low, band_high = center - half, center + half

    # flip risk from recent Net trend (calm bleeding toward zero)
    chg = f.get("net_chg_30")
    if reg in ("neg", "strong_neg") and f.get("was_positive"):
        flip_risk = "HIGH · flipped"
    elif reg in ("strong_pos", "pos") and chg is not None and chg <= -1.5 and f["net_b"] < 5:
        flip_risk = "RISING"
    else:
        flip_risk = "Low"

    return {
        "condition": cond,
        "condition_label": COND_LABELS.get(cond, cond),
        "regime": reg,
        "regime_label": REGIME_LABEL.get(reg, reg),
        "regime_kind": REGIME_KIND.get(reg, "coil"),
        "range_pts": round(rng, 1),
        "band_low": round(band_low, 1),
        "band_high": round(band_high, 1),
        "band_center_is_magnet": cond in MAGNET_CONDS,
        "pin_target": magnet,
        "pin_confidence": cs.get("close_mag_pct", 0),      # % close within 10 pts of magnet
        "pin_med_dist": cs.get("med_dist_mag", None),
        "direction_up_pct": cs.get("up_pct", 50),
        "range_conf": cs.get("range_conf_tier", "Medium"),
        "flip_risk": flip_risk,
        "n_samples": cs.get("n", 0),
    }
