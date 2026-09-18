"""
Probabilistic demand forecasting using XGBoost + Quantile Regression.

Architecture:
- Feature Engineering: Day of week, day of month, weekend indicator, autoregressive lags (t-1, t-7, t-14),
  and 7-day rolling baseline statistics (mean, std).
- Multi-Quantile Gradient Boosting: Trains discrete quantile models (p10, p50, p90, p95) using XGBoost's
  pinball loss objective (`reg:quantileerror`).
- Pinball Monotonicity Guarantee: Enforces non-crossing quantile bounds (p10 <= p50 <= p90 <= p95)
  to ensure mathematically consistent prediction intervals.
- Graceful Fallback: Seamlessly falls back to empirical residual decomposition if historical
  series is sparse (<14 observations).
"""
import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from dataclasses import dataclass, field
from typing import Tuple, List, Optional
import numpy as np
import pandas as pd

try:
    import xgboost as xgb
    HAS_XGBOOST = True
except Exception:
    HAS_XGBOOST = False


@dataclass
class ForecastResult:
    dates: list
    p10: list
    p50: list
    p90: list
    p95: list
    mean_daily_baseline: float
    trend_direction: str          # "rising" / "falling" / "stable"
    trend_pct_30d: float          # % change in level over the last 30 days
    residual_std: float
    model_type: str = "XGBoost Quantile Regression (p10/p50/p90/p95)"
    history_dates: list = field(default_factory=list)
    history_values: list = field(default_factory=list)


def _decompose(series: pd.Series):
    """Level (rolling mean) + weekly seasonal index + residuals. Fallback decomposition."""
    series = series.asfreq("D").interpolate().bfill().ffill()
    level = series.rolling(window=14, min_periods=5, center=True).mean()
    level = level.bfill().ffill()

    weekday_idx = series.index.dayofweek
    seasonal_factor = pd.Series(index=series.index, dtype=float)
    detrended = series / level.replace(0, np.nan)
    for wd in range(7):
        mask = weekday_idx == wd
        seasonal_factor[mask] = detrended[mask].mean()
    seasonal_factor = seasonal_factor.fillna(1.0)

    fitted = level * seasonal_factor
    residuals = (series - fitted).fillna(0.0)
    return level, seasonal_factor, residuals, fitted


def _xgb_quantile_forecast(
    series: pd.Series,
    future_dates: pd.DatetimeIndex,
    horizon_days: int
) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    """Train XGBoost quantile regression models and predict multi-step ahead quantiles."""
    if not HAS_XGBOOST or len(series) < 14:
        return None

    try:
        df = pd.DataFrame({"y": series.astype(float)})
        df["dow"] = df.index.dayofweek.astype(float)
        df["dom"] = df.index.day.astype(float)
        df["is_weekend"] = (df["dow"] >= 5).astype(float)
        df["lag_1"] = df["y"].shift(1)
        df["lag_7"] = df["y"].shift(7)
        df["lag_14"] = df["y"].shift(14)
        df["roll_7"] = df["y"].shift(1).rolling(7, min_periods=2).mean()
        df["roll_std_7"] = df["y"].shift(1).rolling(7, min_periods=2).std().fillna(0.0)

        clean_df = df.dropna()
        if len(clean_df) < 10:
            return None

        feat_cols = ["dow", "dom", "is_weekend", "lag_1", "lag_7", "lag_14", "roll_7", "roll_std_7"]
        X = clean_df[feat_cols].values.astype(np.float32)
        y = clean_df["y"].values.astype(np.float32)

        dtrain = xgb.DMatrix(X, label=y)
        quantiles = [0.10, 0.50, 0.90, 0.95]
        models = {}

        for q in quantiles:
            params = {
                "objective": "reg:quantileerror",
                "quantile_alpha": q,
                "max_depth": 3,
                "learning_rate": 0.12,
                "tree_method": "hist",
                "nthread": 1,
                "verbosity": 0,
            }
            models[q] = xgb.train(params, dtrain, num_boost_round=12)

        history = list(series.values)
        preds = {q: [] for q in quantiles}

        for dt in future_dates:
            l1 = history[-1]
            l7 = history[-7] if len(history) >= 7 else history[0]
            l14 = history[-14] if len(history) >= 14 else history[0]
            r7 = float(np.mean(history[-7:])) if len(history) >= 7 else float(np.mean(history))
            s7 = float(np.std(history[-7:])) if len(history) >= 7 else 0.0

            fvec = np.array([[dt.dayofweek, dt.day, 1.0 if dt.dayofweek >= 5 else 0.0, l1, l7, l14, r7, s7]], dtype=np.float32)
            dmat = xgb.DMatrix(fvec)

            for q in quantiles:
                val = float(models[q].predict(dmat)[0])
                preds[q].append(max(0.0, val))

            # Step forward autoregressive state with expected median
            p50_step = preds[0.50][-1]
            history.append(p50_step)

        p10 = np.array(preds[0.10])
        p50 = np.array(preds[0.50])
        p90 = np.array(preds[0.90])
        p95 = np.array(preds[0.95])

        # Enforce non-crossing monotonicity (pinball inequality: p10 <= p50 <= p90 <= p95)
        p50 = np.maximum(p50, p10)
        p90 = np.maximum(p90, p50)
        p95 = np.maximum(p95, p90)

        return p10, p50, p90, p95

    except Exception:
        return None


_FORECAST_CACHE = {}

def clear_forecast_cache():
    _FORECAST_CACHE.clear()


def forecast_demand(series: pd.Series, horizon_days: int = 14, n_boot: int = 1000, seed: int = 7) -> ForecastResult:
    """
    Computes probabilistic demand distribution across the future horizon.
    Utilizes XGBoost Quantile Regression (p10, p50, p90, p95) with recursive autoregressive
    feature generation, backed by residual bootstrap decomposition fallback.
    """
    cache_key = None
    if len(series) > 0:
        cache_key = (
            len(series),
            str(series.index[0]),
            str(series.index[-1]),
            float(series.iloc[0]),
            float(series.iloc[-1]),
            horizon_days,
        )
        if cache_key in _FORECAST_CACHE:
            return _FORECAST_CACHE[cache_key]

    rng = np.random.default_rng(seed)
    future_dates = pd.date_range(
        series.index.max() + pd.Timedelta(days=1) if len(series) else pd.Timestamp.today(),
        periods=horizon_days,
        freq="D"
    )

    if len(series) < 7:
        base = float(series.mean()) if len(series) else 0.0
        flat = [base] * horizon_days
        res = ForecastResult(
            dates=[d.strftime("%Y-%m-%d") for d in future_dates],
            p10=[round(v * 0.7, 1) for v in flat],
            p50=flat,
            p90=[round(v * 1.3, 1) for v in flat],
            p95=[round(v * 1.5, 1) for v in flat],
            mean_daily_baseline=base,
            trend_direction="stable",
            trend_pct_30d=0.0,
            residual_std=0.0,
            model_type="Baseline Heuristic",
            history_dates=[],
            history_values=[],
        )

    # Baseline level & trend analytics
    level, seasonal_factor, residuals, fitted = _decompose(series)
    last_level = float(level.iloc[-30:].mean())
    prev_level = float(level.iloc[-60:-30].mean()) if len(level) >= 60 else float(level.iloc[:30].mean())
    trend_pct_30d = 0.0 if prev_level == 0 else round((last_level - prev_level) / prev_level * 100, 1)
    trend_direction = "rising" if trend_pct_30d > 4 else ("falling" if trend_pct_30d < -4 else "stable")

    resid_pool = residuals.values[-90:] if len(residuals) >= 90 else residuals.values
    resid_std = float(np.std(resid_pool)) if len(resid_pool) else 0.0

    # 1. Primary Engine: XGBoost Quantile Regression
    xgb_out = _xgb_quantile_forecast(series, future_dates, horizon_days)
    if xgb_out is not None:
        p10, p50, p90, p95 = xgb_out
        model_name = "XGBoost Quantile Regression (p10/p50/p90/p95)"
    else:
        # 2. Fallback Engine: Empirical Residual Bootstrap
        recent_slope = (last_level - prev_level) / 30 if prev_level else 0.0
        damped_slope = recent_slope * 0.5
        seasonal_factors_by_day = seasonal_factor.groupby(seasonal_factor.index.dayofweek).mean().to_dict()
        seas_vec = np.array([seasonal_factors_by_day.get(d.dayofweek, 1.0) for d in future_dates])

        steps = np.arange(1, horizon_days + 1)
        base_points = np.maximum(0.0, (last_level + damped_slope * steps) * seas_vec)

        if len(resid_pool) > 0:
            boot_resid = rng.choice(resid_pool, size=(n_boot, horizon_days), replace=True)
        else:
            boot_resid = np.zeros((n_boot, horizon_days))

        sims = np.clip(base_points + boot_resid, 0, None)
        p10 = np.percentile(sims, 10, axis=0)
        p50 = np.percentile(sims, 50, axis=0)
        p90 = np.percentile(sims, 90, axis=0)
        p95 = np.percentile(sims, 95, axis=0)
        model_name = "Quantile Residual Bootstrap"

    hist_tail = series.iloc[-60:]
    res = ForecastResult(
        dates=[d.strftime("%Y-%m-%d") for d in future_dates],
        p10=[round(float(v), 1) for v in p10],
        p50=[round(float(v), 1) for v in p50],
        p90=[round(float(v), 1) for v in p90],
        p95=[round(float(v), 1) for v in p95],
        mean_daily_baseline=round(last_level, 2),
        trend_direction=trend_direction,
        trend_pct_30d=trend_pct_30d,
        residual_std=round(resid_std, 2),
        model_type=model_name,
        history_dates=[d.strftime("%Y-%m-%d") for d in hist_tail.index],
        history_values=[round(float(v), 1) for v in hist_tail.values],
    )
    if cache_key is not None:
        _FORECAST_CACHE[cache_key] = res
    return res
