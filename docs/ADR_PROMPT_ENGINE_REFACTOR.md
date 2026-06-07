# ADR: Split Prompt Engine Responsibilities

## Status

Accepted.

## Context

`prompt_engine.py` had grown into a mixed module containing prompt planning tables, normalization, post-processing, conflict cleanup, scoring, positive prompt assembly, and dynamic negative prompt construction. That made later changes risky because unrelated concerns had to be edited in the same file.

The Excel data model is still suitable as the editable source of prompt option text. This refactor does not change the Excel schema.

## Decision

Keep `prompt_engine.py` as the stable public orchestration API and split internal responsibilities:

- `prompt_constants.py`: shared constants, aliases, budgets, feedback rules, and negative rule tables.
- `prompt_normalize.py`: scale, shot, aspect, and shot-label normalization.
- `prompt_planner.py`: director/color/filter/emotion/focus/pose-family planning and weighted selection.
- `prompt_postprocess.py`: cleanup, enrichment, conflict handling, length enforcement, feedback tags, and scoring.
- `negative_prompt_engine.py`: dynamic negative prompt construction.

External callers should continue importing from `prompt_engine.py` unless they are explicitly editing one of these internal concerns.

## Consequences

Positive prompt generation, mobile generation, desktop node generation, and audit tools still share the same public prompt engine entry points. Future work can adjust one responsibility without reopening the whole engine file.

The Excel workflow remains unchanged: edit `data/prompt_pools.xlsx`, then run the one-click converter to rebuild runtime data and audits.
