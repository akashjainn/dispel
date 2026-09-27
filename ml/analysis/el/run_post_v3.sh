#!/bin/bash
# After v3 exits: score new eval sets with v3 best, DiffSSD test (clean) with v3, then launch v4 once Kokoro is done.
cd ~/hackgt && source .venv/bin/activate
until grep -q "V3 EXIT" data/checkpoints/v3_diffssd.console.log 2>/dev/null; do sleep 30; done
echo "v3 exited $(date)"
python scratch/el/prep_v4_data.py
python - <<'P'
import csv
rows = list(csv.DictReader(open("data/splits/v4_new_eval.csv")))
with open("data/splits/v4_new_eval_score.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["path"]); [w.writerow(["data/" + r["path"]]) for r in rows]
P
python scratch/eval/score_v3.py --list data/splits/v4_new_eval_score.csv --cond clean --models v3 --out results/v3_neweval_clean.csv
python scratch/eval/score_v3.py --list data/splits/v4_new_eval_score.csv --cond atempo --models v3 --out results/v3_neweval_atempo.csv
S=results/scores; L=$S/diffssd_test_list.csv
[[ -f $S/diffssd_v3_clean.csv ]] || python scratch/eval/score_v3.py --list $L --cond clean --models v3 --out $S/diffssd_v3_clean.csv
until grep -q "^DONE" results/kokoro_generate.log 2>/dev/null; do sleep 30; done
python scratch/el/prep_v4_data.py
python scratch/el/make_train_v4.py
echo "v4 launch $(date)"
python scratch/train/train_v4.py --run v4 --epochs 6 --samples-per-epoch 36000 --max-hours 3.4 --lr-backbone 1e-6 2>&1 \
  | grep --line-buffered -v -e "Loading weights" -e UNEXPECTED -e Warning | tee -a data/checkpoints/v4.console.log
echo "V4 EXIT $(date)" >> data/checkpoints/v4.console.log
