cd ~/hackgt/dispel_pr8fix && source ../.venv/bin/activate
D=~/hackgt/data/consent/akash
for s in real fake/eleven_v3 fake/eleven_multilingual_v2; do
  MODEL_DIR=~/hackgt/data/release/v4p6 python -m hearsay predict $D/$s -o $D/score_$(basename $s).tsv > /dev/null 2>&1
  python -c "
import pandas as pd, numpy as np; d=pd.read_csv('$D/score_$(basename $s).tsv',sep='\t'); p=d['cm-score'].clip(1e-9,1-1e-9); l=10*np.log(p/(1-p))
print('$s'.ljust(30), 'LLR', ' '.join(f'{v:+.1f}' for v in l))"
done
