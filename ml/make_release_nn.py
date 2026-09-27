"""Package a neural-only release (profile "nn"): python make_release_nn.py <checkpoint> <val_scores.npz> <out_dir> <name>
- v3.pt = the network (weights only), backbone_config/lfcc.pt copied from v4p6 (lfcc unused by nn)
- fusion_nn.joblib (also written as fusion.joblib / fusion_app.joblib so every profile scores identically):
  one raw term (dl_detector) with a Platt map fit on DiffSSD validation (class-balanced), used only for the app's
  probability display; the NSA TSV uses the uncapped LLR, where only the ranking matters.
- hearsay.json with sha256 of every file."""
import sys, json, shutil, datetime, csv
from pathlib import Path
import numpy as np, joblib, torch, sklearn
from sklearn.linear_model import LogisticRegression
H = Path.home() / "hackgt"; sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # this checkout's hearsay/
from hearsay.analyzers.dl_detector import sha256
ck, npz, out, name = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
base = H / "data/release/v4p6"; out.mkdir(parents=True, exist_ok=True)
state = torch.load(ck, map_location="cpu", weights_only=False); torch.save({"model": state["model"], "epoch": state.get("epoch")}, out / "v3.pt")
shutil.copytree(base / "backbone_config", out / "backbone_config", dirs_exist_ok=True); shutil.copy2(base / "lfcc.pt", out / "lfcc.pt")
z = np.load(npz); y = np.array([int(r["label"]) for r in csv.DictReader(open(H / "data/splits/v3_val.csv"))])
s = np.concatenate([z[c] for c in ("clean", "atempo", "pv")]); yy = np.tile(y, 3)
lr = LogisticRegression(class_weight="balanced", C=1e6, max_iter=2000).fit(s[:, None], yy)
a, b = float(lr.coef_[0, 0]), float(lr.intercept_[0])
term = {"name": "dl_detector", "type": "raw", "feature": "v3", "impute": float(np.median(s))}
blob = {"kind": "additive_v2", "terms": [term], "weights": [a], "bias": b, "qclip": 3.0, "platt_v3": (a, b), "ref": {}, "prosody_ref": {},
        "report_md": f"{name}: neural network alone (profile nn). Platt map on DiffSSD val: llr = {a:.4f}*s + {b:.4f}",
        "sklearn": sklearn.__version__, "fit": {"date": datetime.date.today().isoformat(), "checkpoint": str(ck), "val_scores": str(npz)}}
for f in ("fusion_nn.joblib", "fusion.joblib", "fusion_app.joblib"): joblib.dump(blob, out / f)
spec = {"name": name, "release": datetime.date.today().isoformat(),
        "detector": {"checkpoint": "v3.pt", "sha256": sha256(out / "v3.pt"), "backbone_config": "backbone_config"},
        "lfcc": {"checkpoint": "lfcc.pt", "sha256": sha256(out / "lfcc.pt")},
        **{k: {"file": f"{k}.joblib", "sha256": sha256(out / f"{k}.joblib")} for k in ("fusion", "fusion_app", "fusion_nn")},
        "weights": {"dl_detector": a}, "bias": b, "profile_override": "nn"}
json.dump(spec, open(out / "hearsay.json", "w"), indent=2); (out / "REPORT.md").write_text(blob["report_md"] + "\n")
print("wrote", out, "platt", round(a, 4), round(b, 4))
