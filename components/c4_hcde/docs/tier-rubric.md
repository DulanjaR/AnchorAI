# Tier rubric

What each assistance tier may and may not contain. The machine-readable source of truth is
`training/tiers.py`; regenerate this page from it if the rules change.

| Tier | Purpose | May contain | Must not contain | Max words | Disclosure band (SDS) |
| --- | --- | --- | --- | --- | --- |
| Human First | The student can very likely do this alone. Get them to make the first attempt. | restate the goal of the task in one sentence; encourage the student and say why they are ready to try it; ask them to share their first attempt or what they have tried; offer to review their attempt afterwards | any approach, method, algorithm name, hint or next step; any code, pseudocode, formula or worked example; the answer or part of it | 90 | 0.00-0.05 |
| Hint | The student needs a small nudge, then does the reasoning themselves. | ONE hint: a single guiding question or the name of the one concept that unlocks the next step; a short pointer to what to look at in their own code or in the problem; ask them to try again and come back | more than one hint or a list of steps; code longer than a single identifier or keyword; the answer, the full method, or a worked example | 90 | 0.00-0.25 |
| Guided | Walk the student through the reasoning step by step, while they produce the solution. | a short numbered sequence of steps, each phrased as a question or instruction to the student; a skeleton, pseudocode or partial code with clearly marked blanks such as TODO or ___; brief explanation of the key concept | the complete working solution or final answer; filled-in code for the core logic the task is testing | 300 | 0.10-0.55 |
| Shared | Work together: the AI does part of the work and the student does and decides the rest. | propose an overall plan or design and do one clearly bounded part of it; complete code or answers for that part, with an explanation; explicitly hand a named remaining part to the student; end with a question asking the student to decide or check something | the whole solution with nothing left for the student; making the student's design decisions for them without asking | 420 | 0.40-0.85 |
| Emergency | The student is under real time pressure. Give the full, correct solution quickly. | the complete, correct solution; a concise explanation of how it works; one line at the end suggesting what to revisit later to learn it properly | withholding the answer, lecturing, or asking the student to try first | 600 | 0.85-1.00 |

The Solution Disclosure Score (SDS) is the share of the reference solution's key elements a reply reveals:
0 = nothing, 1 = everything. See `training/disclosure.py`.

## Probe mode

Write ONE new practice problem that tests exactly the same skill as the student's task, with a different surface (new names, numbers or scenario), solvable without help in about 5 minutes.  
Format exactly:  
Problem:  
<the problem, addressed to the student>  
  
Answer key:  
<the correct answer and the 2-4 points a correct attempt must contain>  
Do not include hints in the problem. Keep the whole output under 220 words.
