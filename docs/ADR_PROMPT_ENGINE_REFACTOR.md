# ADR: Split Prompt Engine Responsibilities

## Status

Accepted.

## Context

`prompt_engine.py` had grown into a mixed module containing prompt planning tables, normalization, post-processing, conflict cleanup, scoring, positive prompt assembly, and dynamic negative prompt construction. That made later changes risky because unrelated concerns had to be edited in the same file.

The JSON data model is the editable source of prompt option text. This refactor does not change the JSON schema.

## Decision

Keep `prompt_engine.py` as the stable public orchestration API and split internal responsibilities:

- `prompt_constants.py`: shared constants, aliases, feedback rules, and negative rule tables.
- `prompt_normalize.py`: scale, shot, aspect, and shot-label normalization.
- `prompt_postprocess.py`: cleanup, enrichment, conflict handling, feedback tags, and scoring.
- `negative_prompt_engine.py`: dynamic negative prompt construction.
- `prompt_composer.py`: art-direction composer for normal, bold, and bold_no_outfit in both modern and ancient eras, that selects by structured tags (place props, orientation, energy, palette) and renders fixed sentence templates instead of repairing text afterwards.
- `prompt_fluency.py`: final-line fluency checks; generation rerolls on defects and the generated-prompt audit reports them.

External callers should continue importing from `prompt_engine.py` unless they are explicitly editing one of these internal concerns.

## Consequences

Positive prompt generation, mobile generation, desktop node generation, and audit tools still share the same public prompt engine entry points. Future work can adjust one responsibility without reopening the whole engine file.

The JSON workflow applies: edit `data/prompt_pools.json` (or `data/nsfw_pose_expression_options.json`), then restart the relevant ComfyUI service; audits run via `tools/audit_prompt_pools.py` and `tools/audit_generated_prompts.py`.

## Update: legacy rewrite layers removed

After the composer took over normal, bold, and bold_no_outfit (modern and ancient), the theme-blueprint pose/outfit overrides, reference seduction poses, environment-anchor poses, normal pose reselection, foot-risk rewrites, and the normal/bold outfit template normalizers were deleted. Later nsfw was routed through the composer as well (三档 output with only the pose-expression line taken from the protected nsfw pool), so the `prompt_parts` / `generate_candidate_parts` chain and `prompt_planner.py` were deleted.
