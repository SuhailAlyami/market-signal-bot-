import json, sys, numpy as np
exec(open(sys.argv[2]).read().split("te = yr >= 2020")[0].replace("D = sys.argv[1]", "D = sys.argv[1]"))
out = {}
for Y in (2025, 2026):
    tr, te_ = yr < Y, yr == Y
    mu, sd = term[tr].mean(0), term[tr].std(0)+1e-12
    from sklearn.linear_model import LogisticRegression
    m = LogisticRegression(max_iter=3000).fit((term[tr]-mu)/sd, y[tr])
    thr = np.quantile(m.predict_proba((term[tr]-mu)/sd)[:, 1], .9)
    p = m.predict_proba((term[te_]-mu)/sd)[:, 1]
    for i, pi in zip(np.where(te_)[0], p): out[dd[i]] = bool(pi >= thr)
json.dump(out, open(sys.argv[3], 'w')); print('flags', sum(out.values()), len(out))
