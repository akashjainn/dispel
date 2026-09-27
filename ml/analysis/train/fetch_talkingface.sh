T=$(cat ~/.cache/huggingface/token); mkdir -p ~/hackgt/data/talkingface && cd ~/hackgt/data/talkingface
for i in 00000 00100 00300 00500; do curl -sfL -H "Authorization: Bearer $T" -o data-$i.arrow "https://huggingface.co/datasets/zachdai/TalkingFaceDataset/resolve/main/data-$i-of-00633.arrow"; done; echo TFDONE > done.txt
