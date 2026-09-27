"""Derive scratch/train/train_v5c.py from train_v5b.py: NSA tips (diversity of real conditions + commercial TTS).
Adds data/splits/v5c_new.csv (split==train only; every source keeps a held-out eval slice), drops v5b's team fold rows
(now inside v5c_new via prep 'el'), drops v4_new's ElevenLabs stock rows (also inside v5c_new), keeps DiffSSD test 80%.
Warm start from v4 best (v5b slipped on DiffSSD). Per-epoch checkpoints; epoch picked on held-out sets, not DiffSSD val."""
from pathlib import Path
d = Path.home() / "hackgt/scratch/train"
s = (d / "train_v5b.py").read_text()
s = s.replace('"""v5b (derived', '"""v5c (derived from train_v5b.py by make_train_v5c.py): diverse reals (TalkingFace, UPS, VCTK, YouTube,\nisolator-cleaned, teammates) + commercial TTS (MLAAD commercial, Grok, Polly/Speechify/Hume/Luvvoice) + ElevenLabs matrix.\n\nv5b (derived', 1)
old_team = s[s.index('    team = [r for r in read_rows("v5_team.csv")'):s.index('    k = args.diffssd_share')]
s = s.replace(old_team, '''    new5 = [r for r in read_rows("v5c_new.csv") if r["split"] == "train"]
    assert not {r["path"] for r in new5} & {r["path"] for r in val}
    rows = [r for r in rows if r["source"] != "el"]   # v4's ElevenLabs stock clips are re-listed in v5c_new
    rows += [{"path": r["path"], "label": int(r["label"]), "group": r["group"], "source": r["source"]} for r in new5]
    log.info("v5c_new train rows: %d", len(new5))
''')
old = s[s.index('    class_mix = {0:'):s.index('    w = sampling_weights(')]
s = s.replace(old, '''    RM = {"diffssd": 0.40, "team_real": 0.03, "real_processed": 0.05, "talkingface": 0.06, "ups": 0.05, "vctk_real": 0.03, "yt_real": 0.03}
    FM = {"diffssd": 0.35, "el": 0.15, "commercial": 0.12, "mlaad_new": 0.03, "dfadd": 0.03, "f5clone": 0.02, "kokoro": 0.02}
    have = {(r["source"], r["label"]) for r in rows}
    RM = {k: v for k, v in RM.items() if (k, 0) in have}; FM = {k: v for k, v in FM.items() if (k, 1) in have}
    class_mix = {0: {**RM, **{s_: v * 0.35 for s_, v in V2_REAL.items()}}, 1: {**FM, **{s_: v * 0.28 for s_, v in V2_FAKE.items()}}}
''')
s = s.replace('ap.add_argument("--run", default="v5b")', 'ap.add_argument("--run", default="v5c")')
assert 'default=str(DATA / "checkpoints/v4/best.pt")' in s
(d / "train_v5c.py").write_text(s); print("wrote train_v5c.py")
