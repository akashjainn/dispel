cd ~/hackgt/dispel_pr8fix && source ../.venv/bin/activate
for k in real fake; do MODEL_DIR=~/hackgt/data/release/v4p6 python -m hearsay predict ~/hackgt/data/consent/team/$k -o ~/hackgt/data/consent/team/v4p6_$k.tsv; done
echo ALLDONE
