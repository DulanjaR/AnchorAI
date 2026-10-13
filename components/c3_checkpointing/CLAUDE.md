# Anchor AI – Component 3: Cognitive Checkpointing for Task Continuity

Repo: AnchorAI. Branch: dev/sandupama. Work only inside components/c3_checkpointing/.
Never edit shared/, orchestration/ or other components without asking.

Target users: working university students in IT studies.
Goal: help students resume interrupted work (code projects, assignments, reports).

## C3 scope (fixed)
- Checkpoint capture: goal, completed work, current working point, next step, resources.
- Quick questions during the interruption (student can ignore them).
- Text-based files only: code (.html .css .js .py .java .php) and documents (.docx .txt .md).
  Files are parsed READ-ONLY to pre-fill checkpoint fields. No images/PPT/PDF/email.
- Resumption difficulty prediction: Low / Medium / High.
- Restart summary; its length depends on predicted difficulty.
- Every output can be Accepted, Edited or Ignored by the student.

## Boundary with C4 (do not cross)
C3 NEVER generates task content (no new code, no assignment answers).
C3 only summarises the student's own progress and plan. Content assistance = C4 (HCDE).

## Model 1 – resumption difficulty classifier (MUST for PP1)
- Data: Hirsch et al. PsychArchives dataset in data/raw/hirsch/ (data + codebook).
- Codebook facts (verified): blocktype 1=practice, 2=experimental; trialtype 1=no interruption,
  2=interruption; task 0=interruption task, 1-3 (Exp3: 1-4)=subtasks; one row = one response.
  Interrupted trial order: subtask1, subtask2, task0, subtask3 -> subtask 3 is the resumption step.
  Define "interrupted" by the presence of a task-0 response (some Exp3 trialtype labels disagree).
- Unit of analysis: one interrupted trial (experimental blocks only, resumption step correct,
  RTs inside 200 ms .. Q3+3*IQR per experiment).
- Target: resumption cost = RT of subtask 3 after the interruption minus the participant's own
  median RT of subtask 3 in uninterrupted trials (per sequence). Label Low/Medium/High from
  terciles of cost, cut points from training participants only (preliminary proxy label).
- Features (known before resuming only): sequence, block, trial, experiment, interruption_rt,
  interruption_error, rt_subtask1, rt_subtask2, pre_errors, pp_speed. Never use resumption-step
  RT or error as a feature.
- Models: Logistic Regression (baseline), Decision Tree, Random Forest.
- Participant-wise split: 80/20 train/test participants plus 5 participant folds on train
  (assigned in notebook 02, reused by all models). Participant ID is never a feature.
- Report: accuracy, precision, recall, macro-F1, confusion matrix, feature importance.
- Save best model with joblib to models/c3_difficulty_model.pkl (git-ignored).
- Do not invent column names; inspect the data and codebook first.
- Do not merge Hirsch rows with SWELL-KW or any other dataset.

## Model 2 – restart summary (bonus for PP1)
- Base: unsloth/Qwen2.5-1.5B-Instruct-bnb-4bit, QLoRA, Google Colab T4 GPU.
- Data: synthetic IT-student checkpoint -> restart summary pairs (300–500, JSONL) in
  data/generated/, seeded from CommitPackFT (code) and IteraTeR (documents).
  Outputs must never contain new code or answers. Mark this data clearly as synthetic.
- Evaluate base vs fine-tuned: ROUGE-L, BERTScore, ~20 human ratings.
- Save LoRA adapter to Google Drive, not to git.

## Environment
- Notebooks (notebooks/) are written here and run in Google Colab.
- In Colab, data and outputs live in Google Drive: MyDrive/C3/
  (data/raw/hirsch, data/generated, models, outputs). Mount Drive in the first cell.
- Classifier notebooks: CPU runtime. Qwen fine-tuning notebook: T4 GPU runtime.
- The student is a beginner in ML: add a short markdown explanation before every section,
  in simple English.
- Never commit datasets, participant data or model weights.
