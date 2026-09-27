import sys, re
from pathlib import Path
src = open(Path.home() / "hackgt/scratch/eval/cond_detect.py").read()
head = src.split("folds = list(")[0]
exec(head)
X = df[FEATS].values.astype(float)
from sklearn.ensemble import HistGradientBoostingClassifier
clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, random_state=0).fit(X, cidx)
C = pd.read_csv(R / "results/cond_control_short.csv")
for f in FEATS:
    if f not in C: C[f] = np.nan
P = clf.predict_proba(C[FEATS].values.astype(float)).argmax(1)
print("control: short, peak-normalized val crops -> detector trained on full-length clips (rows true, cols pred)")
print(pd.crosstab(C.cond, pd.Series(np.array(CONDS)[P], name="pred")).reindex(index=CONDS).to_string())
