# Physical Lab Quality & Reliability Layer v1

## Purpose

Physical Lab already connects simulation, measurement, verification/uncertainty evidence, engineering trade studies, and operations planning inside one canonical `.physlab` Project. The Quality & Reliability Layer adds a conservative engineering-statistics surface for describing observed variation and reliability events without converting those summaries into certification or production-qualification claims.

The intended chain is:

`Simulation / Measurement → Evidence → Quality / Reliability summaries → Engineering Decisions → Operations / Human Review`

This is an Industrial & Operations Engineering connection, but it is also broadly useful to mechanical, electrical, manufacturing, systems, and engineering-physics workflows because all of those disciplines must reason about variation, repeatability, tolerances, test evidence, and failures.

## Public engineering basis

### University of Michigan IOE

Michigan IOE describes Quality Engineering as preparation for coping with uncertainty in engineering-system design and lists Design of Experiments and Statistical Quality Control among its core quality courses.

- Areas of study: https://ioe.engin.umich.edu/undergraduate/major-in-ioe/areas-of-study/

Michigan IOE's Quality Control and Reliability Engineering graduate area describes data-driven modeling, simulation, quality control, and reliability techniques for cost-effective quality improvement and maintenance decisions, with key topics including:

- Design of Experiments;
- fault diagnosis;
- process control and reliability;
- prognostics / statistical monitoring;
- quality control;
- time-series modeling.

- Program area: https://ioe.engin.umich.edu/graduate/masters-programs/industrial-and-operations-engineering-masters/masters-program-curriculum/quality-control-reliability-engineering/

Physical Lab uses those public descriptions as curriculum/methodology context only. It does **not** claim affiliation with Michigan, academic equivalence, accreditation, or compliance with any Michigan program requirement.

### NIST / SEMATECH Engineering Statistics Handbook

The NIST/SEMATECH Engineering Statistics Handbook is explicitly oriented toward engineering and scientific applications.

- Handbook: https://www.itl.nist.gov/div898/software/dataplot/handbook.htm

Its Design of Experiments section describes DOE as a systematic engineering approach applied at the data-collection stage to support defensible conclusions under constraints on runs, time, and money.

- DOE introduction: https://itl.nist.gov/div898/handbook/pmd/section3/pmd31.htm

Its measurement-process material distinguishes repeatability from broader sources of measurement variation and describes repeatability standard-deviation estimation from repeated measurements / calibration designs.

- Measurement process characterization: https://www.itl.nist.gov/div898/handbook/mpc/section3/mpc3332.html
- Gauge repeatability analysis: https://www.itl.nist.gov/div898/handbook/mpc/section4/mpc441.html

Physical Lab uses these sources to shape conservative terminology and boundaries. It does **not** claim NIST validation, NIST endorsement, standards compliance, laboratory accreditation, or certification.

## Quality Study v1

A Quality Study stores:

- a named response / measurement;
- units;
- one or more observed values;
- optional replicate-group identifiers;
- optional factor-level metadata;
- optional declared lower / upper specification context;
- explicit Project evidence references for every observation;
- evidence-fingerprint snapshots;
- intended use and notes.

### Descriptive outputs

The v1 evaluator can report:

- observation count;
- arithmetic mean;
- sample standard deviation;
- minimum / maximum;
- observed fraction inside a user-declared specification interval;
- replicate-group means and sample standard deviations;
- pooled within-group repeatability standard deviation when repeated groups provide degrees of freedom;
- factor-level means;
- a descriptive difference of means for factors that have exactly two declared levels.

### What v1 intentionally does not infer

The layer does not automatically produce:

- Cp / Cpk;
- process-capability verdicts;
- statistical-control verdicts;
- acceptance-sampling decisions;
- causal DOE effects;
- p-values or significance claims;
- production qualification;
- safety approval;
- certification.

A fraction of observed values inside a declared interval is only an observed fraction for the registered sample. It is not a process-capability statement.

A two-level factor contrast is only a difference between observed level means. Unless the experimental design and assumptions justify causal inference, Physical Lab does not label it a causal effect.

## Repeatability semantics

For replicate groups with at least two observations, v1 computes the ordinary sample variance within each group. It then pools within-group variances using their degrees of freedom:

`pooled variance = sum((n_i - 1) * s_i^2) / sum(n_i - 1)`

and reports the square root as `pooled_repeatability_std`.

This describes within-group variation under the registered grouping only. It is not automatically a complete Gauge R&R study, because reproducibility across operators, instruments, days, sites, fixtures, and other sources requires an experimental design that explicitly represents those factors.

## Reliability Event Study v1

A Reliability Event Study stores:

- a named item / configuration;
- multiple declared trials;
- exposure per trial;
- whether an event was observed;
- optional event categories;
- explicit Project evidence references per trial;
- an exposure unit;
- intended use and notes.

### Descriptive outputs

The v1 evaluator reports:

- trial count;
- observed event count;
- observed event fraction;
- total declared exposure;
- observed event rate per exposure, when total exposure is positive;
- event-category counts;
- Project evidence freshness.

### What v1 intentionally does not infer

The layer does not fit or claim:

- a lifetime distribution;
- a reliability function `R(t)`;
- hazard function;
- MTBF / MTTF;
- field reliability;
- warranty reliability;
- fleet reliability;
- safety approval;
- certification.

Those require additional modeling assumptions, censoring semantics, sampling design, environment/context information, and often domain-specific standards or review.

## Evidence freshness

Every observation and reliability trial must reference explicit Project evidence using the same evidence-reference vocabulary already used by Claims and Cross-Checks:

- experiment;
- job;
- result;
- measurement;
- calibration.

The study stores the evidence fingerprint present at registration time. Later evaluation compares the current Project fingerprint with the stored snapshot.

Study evidence state is:

- `CURRENT` — all referenced evidence still resolves with the registered fingerprint;
- `STALE` — one or more evidence fingerprints changed;
- `EVIDENCE_MISSING` — one or more evidence references no longer resolve.

A stale study can still be inspected, but Physical Lab marks the evidence drift instead of silently presenting the original summary as current.

## Relation to Engineering Decisions

Quality and reliability summaries are potential engineering-decision inputs, not final decisions.

Examples:

- repeatability variation can become a robustness metric;
- observed specification fraction can become a declared trade-study metric, with its sample/context boundary preserved;
- observed event rate can be compared across declared alternatives if the exposure/test contexts are genuinely comparable;
- factor contrasts can motivate new experiments or sensitivity studies.

Physical Lab does not automatically convert these summaries into a weighted score or choose a design.

## Relation to Operations Engineering

The Operations Layer models resources, queues, precedence, waiting time, makespan, and utilization. The Quality & Reliability Layer adds another engineering dimension: not only *how quickly* a workflow executes, but what variation and observed events are present in the evidence generated by that workflow.

This makes possible future human-reviewed questions such as:

- Does increasing replicate count reduce uncertainty enough to justify additional instrument time?
- Which experiment should receive scarce calibration resources first?
- Does an additional DOE run provide more decision value than another reliability exposure trial?
- Which maintenance/test campaign should be scheduled next given both queue cost and observed event evidence?

Those future optimization questions must preserve explicit objectives, uncertainty, and assumptions; v1 does not solve them automatically.

## v1 scientific boundary

Quality & Reliability Layer v1 is a descriptive, evidence-linked engineering-statistics layer. It does not establish process stability, process capability, causal DOE effects, field reliability, product safety, production qualification, accreditation, standards compliance, or certification.
