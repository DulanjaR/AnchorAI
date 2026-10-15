# C2 Progress Presentation 1: slide outline, demo script, viva answers

Component: Human Capacity Preservation Manager (C2). Keep every claim consistent with `OBJECTIVES_MAPPING.md` and `PROJECT_STATUS.md`.

## Slide outline (about 12 slides)

1. **Title.** Anchor AI, C2 Human Capacity Preservation Manager. Name, supervisor, SLIIT.
2. **Problem.** Working students start demanding work when their readiness does not match it. Existing productivity tools plan time, not capacity.
3. **Objectives.** Main and six specific objectives (from the proposal).
4. **What C2 is and is not.** Estimates readiness for planned work, compared with the person's own baseline. AI recommends, the user decides. Not a diagnosis, not scheduling (that is C1).
5. **Design principle.** Sensing-first: phone and context signals plus a short behavioural focus check. Energy, focus, stress, fatigue and recovery are latent states, estimated, never read directly. Optional three-tap check-in.
6. **Factor table.** Factor, proxy, source (from `OBJECTIVES_MAPPING.md`).
7. **How the estimate works.** Personal-baseline deviation, weights, capacity 0 to 100, four bands, mismatch rule against task requirement. State clearly that thresholds are provisional.
8. **Preliminary evidence on public data.** StudentLife: weak, unstable (AUC 0.55 to 0.63, people held out). SWELL-KW: AUC 0.86 explained by design (block order alone gives 1.00), order-balanced test near chance. Message: public data cannot validate capacity labels.
9. **Live demo** (see script).
10. **Status against objectives.** Table with Done, Partial, Planned.
11. **Evaluation plan.** Working-student data collection, counterbalanced comparison with a standard productivity approach, accuracy/precision/recall/F1/confusion matrix, SUS, NASA-TLX, ethics and consent.
12. **Next steps and timeline.** Ethics approval, data collection, calibration, Android sensing (Health Connect, UsageStatsManager), backend, evaluation study.

## Demo script (about 3 minutes)

1. Open Today with **Steady morning**. Point to simulated context signals (labelled simulated) and the capacity gauge: High, no mismatch.
2. Switch to **Short night**. Capacity drops, top drivers show sleep and night phone use. Say it is compared with Dilani's own usual range.
3. Run the real **focus check** (or "Use sample result" to save time). Say these are measured live in the browser.
4. Switch work to **Demanding**. At Risk with the mismatch explanation. Say: not medical, compares today with her own normal.
5. Tap the optional **check-in** to show how self-report only adds evidence.
6. **Accept**, then show it in **Decisions**. Mention Edit and Reject also work.
7. **Evaluation** tab: SUS and NASA-TLX ready for the study. **Evidence and limits** tab: honest limits.

## Viva questions and honest answers

**Q: What accuracy does your model have?**
A: There is no capacity accuracy yet, because no public dataset has capacity labels and I will not invent them. On public data I ran participant-grouped models with shuffled-label controls. Results were weak (StudentLife) or explained by study design (SWELL-KW). Capacity metrics will come from the working-student data.

**Q: Is the prototype a machine-learning model?**
A: Not yet. It is a transparent personal-baseline rule engine with provisional weights. That is deliberate: the weights will be calibrated on real data and compared with Logistic Regression and Random Forest baselines.

**Q: Why did SWELL-KW give 0.86 and why do you not trust it?**
A: The neutral condition is always the first block, so block order alone separates classes (AUC 1.00). The order-balanced comparison (time pressure vs interruptions) is near chance.

**Q: Your proposal says readiness factors such as energy and stress. Why sensing-first?**
A: These are latent states and cannot be read from a phone. C2 estimates them from sensed signals and a behavioural check, and keeps self-report as optional input. The proposal also says behavioural and physiological data support the estimate.

**Q: How is it personalized?**
A: Every signal is compared with the person's own mean and spread over about 14 days. No population norm is used. The baseline is ready after 7 days.

**Q: Is this a medical tool? Privacy?**
A: No diagnosis or medical claims. Heart rate is optional and sensitive. Usage data are counts only, no content. The person grants each permission and makes the final decision.

**Q: Why are the demo signals simulated?**
A: The Android sensing layer is not built yet. The demo uses a clearly labelled simulated persona plus a real focus check, to show the pipeline and interface.

**Q: What if the user disagrees with the recommendation?**
A: They edit or reject it, and give a reason. Those responses are recorded and used in the evaluation.

**Q: How will you evaluate it?**
A: Working-student data with repeated measures, participant-grouped splits, accuracy, precision, recall, F1 and confusion matrix, then SUS, NASA-TLX and acceptance against a standard productivity approach in a counterbalanced design, with ethics and consent.

**Q: What is the biggest risk?**
A: Getting enough labelled data from working students within the project time. Mitigation: short repeated sessions, a small number of participants with many observations each, and honest reporting of limits.
