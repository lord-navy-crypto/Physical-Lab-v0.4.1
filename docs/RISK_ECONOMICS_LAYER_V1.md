# Physical Lab Risk & Engineering Economics Layer v1

## Purpose

Physical Lab now connects simulation, measurement, evidence, engineering trade studies, operations planning, and quality/reliability summaries inside one canonical `.physlab` Project. The Risk & Engineering Economics Layer adds two missing decision-support dimensions:

1. explicit engineering risk assumptions across cost, schedule, and performance consequences; and
2. explicit time-value arithmetic for engineering cash-flow assumptions.

The intended chain is:

`Physics / Measurement → Evidence → Quality & Reliability → Risk & Economics → Engineering Decisions → Operations / Human Review`

Risk and economics do not replace the underlying physics evidence. They add declared decision context to that evidence.

## Public engineering basis

### University of Michigan IOE

Michigan IOE's Management Engineering area includes Economic Decision Making (IOE 201), Corporate Finance, and Risk Analysis (IOE 561). Its broader manufacturing/service-systems description explicitly discusses maximizing profits, minimizing costs, and improving safety across engineering-system contexts.

- Areas of study: https://ioe.engin.umich.edu/undergraduate/major-in-ioe/areas-of-study/

Michigan's Systems Engineering and Design MEng describes risk and decision management competencies that include decision trees, value-of-information analysis, multi-attribute utility, and discounting utility over time. It also links test/evaluation to risk reduction and cost-effective experimentation.

- SED degree requirements: https://ioe.engin.umich.edu/graduate/masters-programs/systems-engineering-and-design-masters/sed-degree-requirements/

Michigan IOE's Risk Analysis I description includes the meaning of risk and uncertainty, risk communication/governance, fault/event trees, Bayesian belief networks, probability elicitation, and project/infrastructure/environmental risk analysis.

- Quality / Reliability curriculum: https://ioe.engin.umich.edu/graduate/masters-programs/industrial-and-operations-engineering-masters/masters-program-curriculum/quality-control-reliability-engineering/

Physical Lab uses these public descriptions as methodology and curriculum context only. It does **not** claim affiliation with Michigan, academic equivalence, endorsement, or compliance with any Michigan program.

### ABET systems-engineering criteria

ABET's 2025–2026 Systems and Similarly Named Engineering Program Criteria list systems design/analysis topics including decision analysis, risk analysis covering cost, schedule, and performance, trade-off analysis, optimization, modeling/simulation, sensitivity analysis, and requirements engineering.

- Criteria: https://www.abet.org/accreditation/accreditation-criteria/criteria-for-accrediting-engineering-programs-2025-2026/

The Industrial Engineering criteria also include engineering economy among required program topics.

Physical Lab uses this only to justify that risk/economic reasoning is a legitimate engineering-system concern. It does **not** claim ABET accreditation, ABET compliance, or curricular equivalence.

## Risk Study v1

A Risk Study stores one or more explicit scenarios. Each scenario contains:

- a scenario identifier and name;
- an optional user/project-declared probability in `[0, 1]`;
- one or more non-negative consequence magnitudes;
- consequence dimensions:
  - cost;
  - schedule;
  - performance;
- explicit Project evidence references;
- notes / intended use.

The units for cost, schedule, and performance are explicitly declared by the study.

### Expected-consequence arithmetic

For a consequence dimension `d`, Physical Lab computes an expected contribution only when both a probability and that consequence are explicitly present:

`expected_consequence_d = declared_probability × declared_consequence_d`

If probability is absent, expected consequence remains `None` / unavailable.

This is important: Physical Lab does not infer missing probabilities from other scenarios, historical frequency, language-model guesses, default tables, or undocumented assumptions.

### Totals

For each consequence dimension, the evaluator may sum the scenario expected contributions that can actually be computed from explicit inputs.

The result is arithmetic under the registered assumptions. It is **not** labeled:

- true risk;
- calibrated risk;
- acceptable risk;
- residual risk approval;
- safety status;
- certification status.

Independent risk scenarios are not required to have probabilities summing to one. Therefore the sum of declared scenario probabilities is not treated as a probability distribution unless the user has explicitly modeled it as one outside this v1 layer.

## No automatic risk matrix

Risk matrices often encode hidden categorical thresholds such as low/medium/high or red/yellow/green. v1 intentionally avoids generating those categories automatically.

If a future Project explicitly stores user-authored thresholds or a domain standard, Physical Lab may display those declared criteria while preserving their source and intended use. v1 does not invent them.

## Engineering Economics Study v1

An Engineering Economics Study stores:

- a study name;
- explicit signed cash flows;
- the time/period associated with each flow;
- an explicitly declared discount rate;
- currency/value unit;
- period unit;
- Project evidence references;
- intended use / notes.

### Sign convention

v1 uses an explicit convention:

- positive amount = inflow / benefit;
- negative amount = outflow / cost.

The convention is stored in the study rather than assumed silently.

### Present-worth arithmetic

For a cash flow `C_t` at period `t` and declared discount rate `r`, where `r > -1`:

`PV_t = C_t / (1 + r)^t`

and:

`present_worth = sum(PV_t)`

The evaluator also reports the undiscounted signed total.

Physical Lab does not infer the discount rate. The user/project must supply it explicitly.

## What v1 intentionally does not infer

The Engineering Economics Study does not automatically generate:

- an investment recommendation;
- a recommended alternative;
- an optimal investment verdict;
- market forecasts;
- future inflation assumptions;
- tax assumptions;
- financing assumptions;
- depreciation schedules;
- replacement-analysis decisions;
- financial advice.

Present worth is one declared engineering-economic metric. It can become an input to the Engineering Decision Layer, but it does not by itself select a design.

## Evidence freshness

Every risk scenario and every cash-flow row must reference explicit Project evidence using the same evidence vocabulary already used elsewhere:

- experiment;
- job;
- result;
- measurement;
- calibration.

The study stores the fingerprint present when it is registered. Later evaluation compares that snapshot with the current Project evidence.

Evidence state is:

- `CURRENT` — referenced evidence still resolves with the registered fingerprint;
- `STALE` — one or more referenced evidence fingerprints changed;
- `EVIDENCE_MISSING` — one or more references no longer resolve.

This prevents an old risk/cost calculation from silently appearing current after the underlying engineering evidence changes.

## Relation to Engineering Decisions

Risk/economic outputs can become explicit trade-study metrics, for example:

- expected declared cost consequence;
- expected declared schedule consequence;
- expected declared performance consequence;
- present worth under a declared discount rate.

The Engineering Decision Layer can compare those metrics alongside physics performance, quality/reliability evidence, and operational metrics.

Physical Lab still does not create a hidden weighted score. Human engineering judgment remains responsible for selecting objectives, constraints, assumptions, and the final alternative.

## Relation to Operations and Quality / Reliability

The layers now represent different engineering questions:

- **Physics / Measurement:** what did the model or experiment produce?
- **Evidence:** what supports the result, and is that support current?
- **Quality & Reliability:** what variation and observed event evidence is present?
- **Risk:** what declared uncertain scenarios and consequences matter?
- **Engineering Economics:** how do explicitly declared value flows change with time value?
- **Engineering Decisions:** what alternatives remain feasible and nondominated under declared metrics?
- **Operations:** how do finite resources and queue policies affect execution?

This is the intended Industrial & Operations Engineering / Systems Engineering bridge: evidence is carried into constrained decisions rather than separated from them.

## v1 boundary

Risk & Engineering Economics Layer v1 performs transparent arithmetic over explicit Project assumptions and evidence. It does not establish calibrated risk, causal probability, risk acceptance, safety approval, financial advice, investment recommendation, economic superiority, accreditation, standards compliance, or certification.
