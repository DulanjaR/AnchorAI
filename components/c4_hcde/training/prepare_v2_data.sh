#!/bin/bash
# Prepare ALL extra training data for model v2 on the Mac (Groq teacher + judge), then stop.
#
#   cd ~/Desktop/HCDE/AnchorAI
#   caffeinate -i bash components/c4_hcde/training/prepare_v2_data.sh
#
# 1. public-benchmark test set (MBPP, HumanEval, CodeAlpaca, DS-1000, FinQA, ConvFinQA; held out)
# 2. public-benchmark training data, all six modes, automatic quality gate     } in parallel
# 3. targeted augmentation: pressure, SHARED, PROBE (original IT training tasks) }
# Everything is resumable, and the whole thing runs twice: the second pass only retries what a
# rate limit stopped. Watch progress with:  tail -f runs/prepare_v2/*.log
cd "$(dirname "$0")/../../.." || exit 1
[ -f .venv/bin/activate ] && source .venv/bin/activate
set -a; source .env; set +a
PY="python -m components.c4_hcde.training"
LOG=runs/prepare_v2
mkdir -p "$LOG"
for pass in 1 2; do
  echo "$(date +%H:%M) pass $pass: public test set"
  $PY.public_data test > "$LOG/public_test_$pass.log" 2>&1
  tail -1 "$LOG/public_test_$pass.log"
  echo "$(date +%H:%M) pass $pass: public training data + augmentation (in parallel, ~1 h on pass 1)"
  $PY.public_data train > "$LOG/public_train_$pass.log" 2>&1 &
  ( $PY.augment_tier --pressure; $PY.augment_tier --tier SHARED --per-task 1; $PY.augment_tier --tier PROBE ) \
      > "$LOG/augment_$pass.log" 2>&1 &
  wait
done
echo
echo "$(date +%H:%M) done. Summary:"
grep -h "public_test.jsonl:" "$LOG"/public_test_2.log
grep -h -A8 "accepted$" "$LOG"/public_train_2.log | grep -E "accepted|spot-check"
grep -h "kept in" "$LOG"/augment_2.log
echo
echo "Next: spot-check components/c4_hcde/training/data/dataset/public_review.csv, then commit and push:"
echo "  git add -A components/c4_hcde && git commit -m 'HCDE v2 data: public benchmarks + augmentation' && git push"
