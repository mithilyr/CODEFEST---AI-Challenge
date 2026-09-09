# Planner tier sweep

Measured 2026-09-09T06:06:00+00:00. Frozen set: `eval/robustness/routing_robustness_v1.json` (55 questions, 49 answerable).

Arm C is the shipped system (templates -> cue tier, no planner). Arm D adds the opt-in planner tier (`use_planner=True`) on top of the same shipped code path.

| metric | C shipped | D with planner |
|---|---:|---:|
| route_success | 34 | 34 |
| entity_resolution_success | 36 | 40 |
| answer_correct | 22 | 26 |
| complete_evidence | 31 | 35 |
| ambiguous | 4 | 4 |
| no_route_shape | 13 | 9 |
| wrong_route | 0 | 0 |
| unnecessary_depth | 0 | 0 |
| honest refusal (of 6) | 6 | 6 |

## Questions where the planner tier changed the outcome (4)

| rid | group | shipped status | with-planner status | correct? | complete evidence? |
|---|---|---|---|---|---|
| rb_001 | A_paraphrase | no_template_match | planned_sufficient | True | True |
| rb_022 | A_paraphrase | no_template_match | planned_sufficient | True | True |
| rb_027 | A_paraphrase | no_template_match | planned_sufficient | True | True |
| rb_036 | B_novel | no_template_match | planned_sufficient | True | True |

