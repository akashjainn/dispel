#!/usr/bin/env bash
# Four shards of TalkingFaceDataset (CC BY-NC). The HF token is read by curl from stdin, never put on the command line.
set -euo pipefail
T=$(cat ~/.cache/huggingface/token); mkdir -p ~/hackgt/data/talkingface && cd ~/hackgt/data/talkingface
for i in 00000 00100 00300 00500; do
  f=data-$i.arrow; [ -s "$f" ] && continue
  printf 'header = "Authorization: Bearer %s"\n' "$T" | curl -sfL -K - -o "$f.part" \
    "https://huggingface.co/datasets/zachdai/TalkingFaceDataset/resolve/main/data-$i-of-00633.arrow"
  mv "$f.part" "$f"
done
echo TFDONE > done.txt
