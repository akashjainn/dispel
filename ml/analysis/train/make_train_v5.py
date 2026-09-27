"""Derive scratch/train/train_v5.py from train_v4.py: + consenting teammates' ElevenLabs clones (fake) and their real
clips (real), TRAIN-fold speakers only (data/splits/v5_team.csv split==train; held-out speakers never seen),
group = speaker so every teammate gets equal mass; warm start from v4 best; per-epoch checkpoints kept so the
held-out-speaker evaluation can pick the epoch without touching NSA/DiffSSD test data."""
from pathlib import Path
d = Path.home() / "hackgt/scratch/train"
s = (d / "train_v4.py").read_text()
s = s.replace('"""v4 (derived', '"""v5 (derived from train_v4.py by make_train_v5.py): + teammates\' ElevenLabs clones and real clips\n(train-fold speakers), warm start from v4 best.\n\nv4 (derived', 1)
old = '    rows += [{"path": r["path"], "label": 1, "group": r["group"], "source": r["source"]} for r in new]\n'
assert old in s
s = s.replace(old, old + '''    team = [r for r in read_rows("v5_team.csv") if r["split"] == "train"]
    held = {r["spk"] for r in read_rows("v5_team.csv") if r["split"] == "eval"}
    assert team and not {r["spk"] for r in team} & held
    assert not {r["path"] for r in team} & {r["path"] for r in val}
    rows += [{"path": r["path"], "label": r["label"], "group": r["spk"], "source": r["source"]} for r in team]
    log.info("team (train fold): %d clips, speakers %s; held-out speakers %s", len(team), sorted({r["spk"] for r in team}), sorted(held))
''')
old = '''    class_mix = {0: {"diffssd": k, **{s: v * (1 - k) for s, v in V2_REAL.items()}},
                 1: {"diffssd": k - 0.10, "el": 0.04, "kokoro": 0.06, **{s: v * (1 - k) for s, v in V2_FAKE.items()}}}'''
assert old in s
s = s.replace(old, '''    class_mix = {0: {"diffssd": k - 0.04, "team_real": 0.04, **{s: v * (1 - k) for s, v in V2_REAL.items()}},
                 1: {"diffssd": k - 0.18, "el": 0.05, "kokoro": 0.05, "team_clone": 0.08, **{s: v * (1 - k) for s, v in V2_FAKE.items()}}}''')
s = s.replace('ap.add_argument("--run", default="v4")', 'ap.add_argument("--run", default="v5")')
s = s.replace('ap.add_argument("--init", default=str(DATA / "checkpoints/v3_diffssd/best.pt"))',
              'ap.add_argument("--init", default=str(DATA / "checkpoints/v4/best.pt"))')
old = '        np.savez(run_dir / f"val_scores_ep{ep}.npz", **sc)\n'
assert old in s
s = s.replace(old, old + '        atomic_save({"model": model.state_dict(), "epoch": ep, "args": vars(args)}, run_dir / f"ep{ep}.pt")\n')
(d / "train_v5.py").write_text(s)
print("wrote", d / "train_v5.py")
