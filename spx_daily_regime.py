"""Frozen, offline v3 challenger. Never imported by production issue()."""
import numpy as np
import pandas as pd
from spx_daily import features, direction

VERSION = 'spx-daily-regime-v3'
CLASSES = ('Bullish', 'Bearish', 'Sideways')


def regime_features(rows):
    f, x, atr = features(rows)
    previous = f.close.shift(1)
    tr = pd.concat([f.high-f.low, (f.high-previous).abs(),
                    (f.low-previous).abs()], axis=1).max(axis=1)
    ema20 = f.close.ewm(span=20, adjust=False).mean()
    ema50 = f.close.ewm(span=50, adjust=False).mean()
    x['compression'] = tr.rolling(5).mean()/tr.rolling(20).mean()
    x['trend_spread'] = (ema20-ema50)/atr
    x['trend_slope'] = (ema20-ema20.shift(5))/atr
    x['acceleration'] = (f.close-2*f.close.shift(3)+f.close.shift(6))/atr
    x['gap'] = (f.open-previous)/atr
    return f, x, atr


def weighted_quantile(values, weights, quantiles):
    order = np.argsort(values, kind='stable')
    values = np.asarray(values)[order]
    weights = np.asarray(weights)[order]
    cumulative = np.cumsum(weights)/np.sum(weights)
    return np.interp(quantiles, cumulative, values)


def forecast_regime(rows):
    if len(rows) < 81:
        raise ValueError('need at least 81 complete daily sessions')
    f, x, atr = regime_features(rows)
    valid = np.flatnonzero(np.isfinite(x.to_numpy()).all(axis=1) & (atr.to_numpy()>0))
    if len(f)-1 not in valid:
        raise ValueError('invalid latest features')
    train = valid[valid < len(f)-1]
    if len(train) < 40:
        raise ValueError('insufficient training examples')
    historical = x.iloc[train]
    scale = (historical.quantile(.75)-historical.quantile(.25)).replace(0,1)
    center = historical.median()
    # Robust scaling and bounded features prevent one anomalous wick dominating.
    z = ((historical-center)/scale).clip(-5,5)
    latest = ((x.iloc[-1]-center)/scale).clip(-5,5)
    distances = ((z-latest)**2).mean(axis=1).sort_values(kind='stable')
    neighbors = distances.index[:40].to_numpy()
    weights = np.exp(-distances.iloc[:40].to_numpy())
    weights /= weights.sum()
    labels = [direction(f.close.iloc[i+1]-f.close.iloc[i],atr.iloc[i]) for i in neighbors]
    probabilities = {k:float(sum(w for w,l in zip(weights,labels) if l==k)) for k in CLASSES}
    predicted = max(probabilities,key=probabilities.get)
    hi = [(f.high.iloc[i+1]-f.close.iloc[i])/atr.iloc[i] for i in neighbors]
    lo = [(f.low.iloc[i+1]-f.close.iloc[i])/atr.iloc[i] for i in neighbors]
    c, a = float(f.close.iloc[-1]), float(atr.iloc[-1])
    highs = c+a*weighted_quantile(hi,weights,[.1,.5,.9])
    lows = c+a*weighted_quantile(lo,weights,[.1,.5,.9])
    return dict(direction=predicted,confidence=None,model_version=VERSION,
                predicted_high=round(float(highs[1]),2),predicted_low=round(float(lows[1]),2),
                high_interval=[float(highs[0]),float(highs[2])],
                low_interval=[float(lows[0]),float(lows[2])],atr=a,
                analog_class_weights=probabilities,
                effective_neighbors=float(1/np.sum(weights**2)),
                compression=float(x.compression.iloc[-1]),
                status='RESEARCH_NOT_VALIDATED',volume_used=False)
