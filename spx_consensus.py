"""One preregistered research consensus; never a production alert."""
import pandas as pd
from spx_inside_range import PRIMARY, directions as inside_directions, features as inside_features
from research_spx_lead_v2 import directions as lead_directions, features as lead_features

VERSION = 'spx-consensus-v1'
MODELS = ('inside_slope_consensus', 'inside_range_pressure', 'slope_projection',
          'last_body', 'original_candidate', 'no_signal')


def features(bars):
    frame = inside_features(bars)
    frame['slope5'] = lead_features(bars)['slope5']
    return frame


def directions(frame, model):
    if model not in MODELS:
        raise ValueError('unknown_consensus_model')
    if model == 'slope_projection':
        return lead_directions(frame, model)
    if model != 'inside_slope_consensus':
        return inside_directions(frame, model)
    inside = inside_directions(frame, PRIMARY)
    slope = lead_directions(frame, 'slope_projection')
    return inside.where((inside != 0) & (inside == slope) & frame.valid, 0)


def schedule(frame, model):
    rows, until = [], None
    for index, (stamp, side) in enumerate(directions(frame, model).items()):
        decision = stamp + pd.Timedelta(minutes=1)
        if side and (until is None or decision >= until):
            rows.append(dict(index=index, direction=int(side), detected_at=decision.isoformat(),
                             rule_version=VERSION, model=model, notify_eligible=False))
            until = decision + pd.Timedelta(minutes=10)
    return rows
