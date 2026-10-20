import unittest
import numpy as np
import pandas as pd

from hunter_crossmarket_research import paired_features, signal, grid
from hunter_linear_research import fit_for, matrix_features, fit_model, predict_score
from hunter_research import ResearchConfig
from test_premium_radar import bars


class CrossmarketTests(unittest.TestCase):
    def frame(self):
        d=bars(100)
        d['Close']=10+np.sin(np.arange(100)/3)*.2
        d['Open']=d.Close-.05
        d['High']=d.Close+.1
        d['Low']=d.Open-.1
        return d

    def test_exact_time_join_does_not_fill_missing_confirmation(self):
        data=self.frame()
        other=data.drop(data.index[50])
        f=paired_features(data,other)
        self.assertFalse(f.other_valid.iloc[50])
        self.assertTrue(pd.isna(f.other_trend.iloc[50]))

    def test_crossmarket_prefix_invariance(self):
        data=self.frame();other=self.frame()
        expected=paired_features(data.iloc[:61],other.iloc[:61]).iloc[60]
        data.iloc[61:]=[100.,110.,90.,105.,100000.]
        other.iloc[61:]=[200.,220.,180.,210.,100000.]
        actual=paired_features(data,other).iloc[60]
        pd.testing.assert_series_equal(expected,actual)

    def test_opposing_counterpart_cancels_cross_signal(self):
        f={'valid':True,'rvol':2.,'local_width':2.,'close':11.,'local_high':10.8,'local_low':10.,
           'move':.8,'trend_5':1.,'close_position':.9,'other_valid':True,'other_trend':-1.}
        self.assertEqual(signal(f,'local_release',{'impulse':.3}),1)
        self.assertEqual(signal(f,'cross_local',{'impulse':.3}),0)
        self.assertEqual(len(grid()),16)

    def test_regularized_scores_are_finite_and_not_calibrated_probabilities(self):
        rng=np.random.default_rng(42)
        x=rng.normal(size=(180,16));y=np.tile([0,1,2],60)
        model=fit_model(x,y,.1,iterations=50)
        score=predict_score({f'm{i}':float(x[0,i]) for i in range(16)},model)
        self.assertTrue(np.isfinite(score).all())
        self.assertAlmostEqual(float(score.sum()),1.)
        self.assertFalse(model['calibrated_probability'])

    def test_inadequate_training_classes_cannot_produce_model(self):
        with self.assertRaises(ValueError):
            fit_model(np.ones((200,16)),np.zeros(200,dtype=int),.1)

    def test_model_fit_does_not_use_later_normalization_or_labels(self):
        data=bars(400)
        data['Close']=10+np.sin(np.arange(400)/8)
        data['Open']=data.Close-.03
        data['High']=data.Close+.1
        data['Low']=data.Open-.1
        other=data.copy()
        config=ResearchConfig(horizon=5)
        indices=list(range(30,250))
        earlier=fit_for(data,matrix_features(data,other),indices,config,.1)
        data.iloc[270:]=[100.,110.,90.,105.,100000.]
        other.iloc[270:]=[200.,220.,180.,210.,100000.]
        later=fit_for(data,matrix_features(data,other),indices,config,.1)
        self.assertEqual(earlier,later)
