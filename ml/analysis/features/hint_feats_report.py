import numpy as np, pandas as pd
from pathlib import Path
from sklearn.metrics import roc_auc_score
R = Path.home() / "hackgt"; D = pd.read_csv(R / "results/hint_feats.csv")
F = [c for c in D.columns if c not in ("set", "label", "path", "err")]
real = lambda s: D[(D.set == s) & (D.label == 0)]; fake = lambda s: D[(D.set == s) & (D.label == 1)]
P = {"team clones vs team reals (paired people)": (fake("team_clone_given_all"), real("team_real_all")),
     "voice changer vs team reals": (fake("voice_changer"), real("team_real_all")),
     "EL TTS vs NSA LJ reals": (fake("el_tts"), real("nsa_lj_real")),
     "DiffSSD test fakes vs DiffSSD reals": (fake("diffssd_test_holdout"), real("diffssd_test_holdout")),
     "F5/Chatterbox clones vs their Libri reals": (pd.concat([fake("libri_clone_f5"), fake("libri_clone_chatterbox")]), real("libri_clone_real")),
     "isolator reals vs team reals (want ~0.5)": (real("isolator_real"), real("team_real_all"))}
rows = []
for f in F:
    r = {"feature": f}
    for k, (a, b) in P.items():
        a2, b2 = a[f].dropna(), b[f].dropna()
        r[k] = roc_auc_score(np.r_[np.ones(len(a2)), np.zeros(len(b2))], np.r_[a2, b2]) if len(a2) > 3 and len(b2) > 3 else np.nan
    rows.append(r)
T = pd.DataFrame(rows).set_index("feature").round(2)
aucs = T.iloc[:, :5]; T["consistent"] = ((aucs > 0.6).all(1) | (aucs < 0.4).all(1)).map({True: "YES", False: ""})
T["mean |AUC-.5|"] = (aucs - 0.5).abs().mean(1).round(2)
T = T.sort_values("mean |AUC-.5|", ascending=False)
print("rows:", len(D), " sets:", D.groupby(["set", "label"]).size().to_dict())
print("AUC > 0.5 = feature is HIGHER for the first group (fakes)")
print(T.to_string()); (R / "results/hint_feats.md").write_text(T.to_markdown())
for f in ["breaths_per_s", "pauses_per_s", "ribs_bands", "harm_hi_minus_lo", "energy_slope", "f0_slope"]:
    if f in D: print(f, {s: round(D[(D.set == s)][f].median(), 3) for s in ["team_real_all", "team_clone_given_all", "voice_changer", "el_tts", "nsa_lj_real", "isolator_real"]})
