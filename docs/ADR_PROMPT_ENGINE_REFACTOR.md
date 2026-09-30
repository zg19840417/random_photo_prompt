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
- `negative_prompt_engine.py`: dynamic negative prompt construction.
- `prompt_composer.py`: art-direction composer for normal, bold, and bold_no_outfit in both modern and ancient eras, that selects by structured tags (place props, orientation, energy, palette) and renders fixed sentence templates instead of repairing text afterwards.
- `prompt_fluency.py`: final-line fluency checks; generation rerolls on defects and the generated-prompt audit reports them.

External callers should continue importing from `prompt_engine.py` unless they are explicitly editing one of these internal concerns.

## Consequences

Positive prompt generation, mobile generation, desktop node generation, and audit tools still share the same public prompt engine entry points. Future work can adjust one responsibility without reopening the whole engine file.

The JSON workflow applies: edit `data/prompt_pools.json` (or `data/nsfw_pose_expression_options.json`), then restart the relevant Mac aiohttp service or Windows ComfyUI service; audits run via `tools/audit_prompt_pools.py` and `tools/audit_generated_prompts.py`.

## Update: legacy rewrite layers removed

After the composer took over normal, bold, and bold_no_outfit (modern and ancient), the theme-blueprint pose/outfit overrides, reference seduction poses, environment-anchor poses, normal pose reselection, foot-risk rewrites, and the normal/bold outfit template normalizers were deleted. Later nsfw was routed through the composer as well (三档 output with only the pose-expression line taken from the protected nsfw pool), so the `prompt_parts` / `generate_candidate_parts` chain and `prompt_planner.py` were deleted.

## Update: rewrite layer removed

`prompt_postprocess.py` (about 1900 lines of string replacement tables) was deleted. Measured on 810 composer samples it only did three things: name hands left/right, strip leftover "A或B" alternatives and drop a duplicated quality concept. Those are now fixed in the data (`_name_hands` in `prompt_composer.py`, no "或" in data, no duplicate quality concepts) and guarded by tests. It also rewrote user-typed prompts at submission and was not idempotent, so `prompt_engine.py` now renders each dimension verbatim (only sentence punctuation and `她穿着`), mobile generation no longer rebuilds or cleans prompts, and `_prompt_text` returns text unchanged. Camera-scope filtering remains only for the protected NSFW pose pool (head shots drop clauses about the lower body).

## Host boundary

The public prompt engine is unchanged. Mac uses `tools/run_mac_local_server.py`, `rpp_server.py` and the lightweight `rpp_folder_paths.py` directory provider. `rpp_routes.py` owns the single route table shared with `__init__.py`. Only the ComfyUI entry imports `rpp_nodes.py` and `rpp_comfy.py` (queue validation/admission and interrogation). Mac mobile jobs use remote queue/history and local asset receipts; no local ComfyUI queue fallback remains.
