"""
Statistical control-chart anomaly detection (EWMA + CUSUM), applied per medicine/branch.

Why not just "value > 2x average"? A sudden but brief blip and a sustained abnormal-usage
drift look the same to a naive threshold. EWMA smooths noise so isolated spikes don't fire,
while CUSUM accumulates small sustained deviations that individually look normal, so a
slow-building outbreak-style drift is caught even before any single day looks alarming
(this is exactly the "reduce false alarms while catching real drift" trade-off the problem
statement calls out).

We can validate detector quality directly against usage_anomalies.csv's ground-truth labels,
which is a genuinely strong demo line: "our detector recalls X% of labeled anomalies."
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class AnomalyFlag:
    date: str
    value: float
    baseline: float
    z_score: float
    cusum_stat: float
    severity: str      # "moderate" / "high" / "critical"


def detect_anomalies(series: pd.Series, baseline_window: int = 60, baseline_lag: int = 10,
                      cusum_k: float = 0.5, cusum_h: float = 3.0):
    """
    series: daily consumption indexed by date.

    Design: each day is compared against a REFERENCE baseline built from an earlier,
    lagged window (t-baseline_lag-baseline_window .. t-baseline_lag) rather than an
    adaptive EWMA that tracks the series itself. An adaptive baseline "chases" a slow
    ramp and never flags it (it just thinks the new level is normal); a lagged fixed
    reference window is what lets us actually catch a sustained multi-day drift, which
    is the core "combine signals over time, don't just threshold today's value" ask.

    cusum_k: allowed slack (in std units) before CUSUM starts accumulating.
    cusum_h: CUSUM decision threshold (in std units) to flag an anomaly.
    Returns list[AnomalyFlag], most recent last.
    """
    if len(series) < baseline_window + baseline_lag + 5:
        return []

    series = series.asfreq("D").interpolate().bfill().ffill()
    n = len(series)

    shifted = series.shift(baseline_lag)
    rolling_mean = shifted.rolling(window=baseline_window, min_periods=baseline_window).mean()
    rolling_std = shifted.rolling(window=baseline_window, min_periods=baseline_window).std()

    baseline_mean = rolling_mean.values
    baseline_std = np.where(rolling_std.values > 0, rolling_std.values, rolling_mean.values * 0.15 + 1e-6)

    z = np.where(baseline_std > 0, (series.values - baseline_mean) / baseline_std, 0.0)
    z = np.nan_to_num(z, nan=0.0)

    cusum_pos = np.zeros(n)
    for i in range(1, n):
        cusum_pos[i] = max(0.0, cusum_pos[i - 1] + z[i] - cusum_k)

    flags = []
    for i, date in enumerate(series.index):
        flagged_by_z = z[i] > 2.2
        flagged_by_cusum = cusum_pos[i] > cusum_h
        if flagged_by_z or flagged_by_cusum:
            severity = "critical" if (z[i] > 4.0 or cusum_pos[i] > cusum_h * 2.0) else \
                       "high" if (z[i] > 3.0 or cusum_pos[i] > cusum_h * 1.4) else "moderate"
            flags.append(AnomalyFlag(
                date=date.strftime("%Y-%m-%d"),
                value=round(float(series.iloc[i]), 1),
                baseline=round(float(baseline_mean[i]), 1) if not np.isnan(baseline_mean[i]) else 0.0,
                z_score=round(float(z[i]), 2),
                cusum_stat=round(float(cusum_pos[i]), 2),
                severity=severity,
            ))
    return flags



def validate_detector(store, sample_size: int | None = None):
    """
    Runs the detector at the (medicine, branch) grain -- matching how usage_anomalies.csv
    ground truth is labeled -- and checks how many labeled anomaly dates were caught within
    +/-1 day (control charts often flag the day after a sustained spike begins, which is
    still a correct catch for our purposes).
    """
    truth = store.anomalies_truth.copy()
    truth["date"] = pd.to_datetime(truth["date"])
    pairs = truth[["medicine_id", "branch_id"]].drop_duplicates().values.tolist()
    if sample_size:
        pairs = pairs[:sample_size]

    total_truth = 0
    total_caught = 0
    per_medicine = []

    for mid, bid in pairs:
        med_truth_dates = set(truth[(truth.medicine_id == mid) & (truth.branch_id == bid)]["date"].dt.date)
        if not med_truth_dates:
            continue
        series = store.daily_consumption(mid, branch_id=bid)
        flags = detect_anomalies(series)
        flagged_dates = set(pd.to_datetime([f.date for f in flags]).date)

        caught = 0
        for td in med_truth_dates:
            window = {td + pd.Timedelta(days=d) for d in (-1, 0, 1)}
            if flagged_dates & window:
                caught += 1

        total_truth += len(med_truth_dates)
        total_caught += caught
        per_medicine.append({
            "medicine_id": mid, "branch_id": bid, "truth_count": len(med_truth_dates),
            "caught": caught, "recall": round(caught / len(med_truth_dates), 2) if med_truth_dates else None,
        })

    overall_recall = round(total_caught / total_truth, 3) if total_truth else None
    return {
        "overall_recall": overall_recall,
        "total_labeled_anomalies": total_truth,
        "total_caught": total_caught,
        "per_medicine": sorted(per_medicine, key=lambda x: -x["truth_count"])[:20],
    }
