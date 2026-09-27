"""Derive scratch/train/train_v4.py from train_v3.py: same model, augmentation, validation and selection; adds new
fake sources (ElevenLabs stock voices, Kokoro) from data/splits/v4_new_train.csv and warm-starts from v3's best."""
from pathlib import Path
d = Path.home() / "hackgt/scratch/train"
s = (d / "train_v3.py").read_text()
s = s.replace('"""v3: XLS-R fine-tune', '"""v4 (derived from train_v3.py by make_train_v4.py): + new generators (ElevenLabs stock voices,\nKokoro), warm start from v3 best. Original v3 notes follow.\n\nv3: XLS-R fine-tune', 1)
old = "    rows = ds_rows + v2_rows()\n    k = args.diffssd_share\n"
assert old in s
s = s.replace(old, '''    rows = ds_rows + v2_rows()
    new = read_rows("v4_new_train.csv")
    assert all(r["split"] == "train" and r["label"] == 1 for r in new)
    assert not {r["path"] for r in new} & {r["path"] for r in val}
    rows += [{"path": r["path"], "label": 1, "group": r["group"], "source": r["source"]} for r in new]
    k = args.diffssd_share
''')
old = '                 1: {"diffssd": k, **{s: v * (1 - k) for s, v in V2_FAKE.items()}}}'
assert old in s
s = s.replace(old, '                 1: {"diffssd": k - 0.10, "el": 0.04, "kokoro": 0.06, **{s: v * (1 - k) for s, v in V2_FAKE.items()}}}')
s = s.replace('ap.add_argument("--run", default="v3_diffssd")', 'ap.add_argument("--run", default="v4")')
s = s.replace('ap.add_argument("--init", default=str(DATA / "release/v2/best.pt"))',
              'ap.add_argument("--init", default=str(DATA / "checkpoints/v3_diffssd/best.pt"))')
(d / "train_v4.py").write_text(s)
print("wrote", d / "train_v4.py")
