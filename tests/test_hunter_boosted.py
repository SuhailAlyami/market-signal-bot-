import importlib.util
import unittest
import numpy as np


@unittest.skipUnless(importlib.util.find_spec('sklearn'), 'optional requirements-research.txt')
class BoostedTests(unittest.TestCase):
    def test_fit_uses_explicit_earlier_samples_and_has_no_serialized_estimator(self):
        from hunter_boosted_research import fit_boosted, public_report
        from hunter_linear_research import predict_score
        rng=np.random.default_rng(17)
        x=rng.normal(size=(240,16));y=np.tile([0,1,2],80)
        model=fit_boosted(x,y,10.)
        score=predict_score({f'm{i}':float(x[0,i]) for i in range(16)},model)
        self.assertTrue(np.isfinite(score).all())
        self.assertAlmostEqual(float(score.sum()),1.)
        exported=public_report({'model':model})
        self.assertNotIn('_estimator',exported['model'])
        self.assertFalse(exported['model']['calibrated_probability'])

    def test_missing_class_is_rejected(self):
        from hunter_boosted_research import fit_boosted
        with self.assertRaises(ValueError):
            fit_boosted(np.ones((200,16)),np.zeros(200,dtype=int),10.)
