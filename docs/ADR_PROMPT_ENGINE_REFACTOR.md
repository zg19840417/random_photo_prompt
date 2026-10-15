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
- `prompt_composer.py`: shared composer for all four scales in both modern and ancient eras. Temperament and character state constrain pose profiles and complete facial-expression plans before rendering. Place props, orientation, era and palette remain structured constraints. Independent complete pose/expression entries enter at pose selection without parsing or rewriting their wording.
- `prompt_fluency.py`: final-line fluency checks; generation rerolls on defects and the generated-prompt audit reports them.

External callers should continue importing from `prompt_engine.py` unless they are explicitly editing one of these internal concerns.

## Consequences

`PERSONAS` in `data/art_direction_pools.json` owns scale-specific temperaments, states, complete gaze/brow/mouth/detail plans and photography preferences. Normal and bold use the same selection algorithm; the third tier uses bold data and omits outfit. The fourth tier also omits outfit and keeps its complete pose/expression opaque, so the new planner selects only its temperament and shared non-pose dimensions. No module repairs or appends facial parts after rendering. All scales compose scene and color from compact source fields; legacy energy-based expression pools and redundant lighting layers are removed.

Positive prompt generation, mobile generation and audit tools still share the same public prompt engine entry points. Future work can adjust one responsibility without reopening the whole engine file.

The JSON workflow applies: edit `data/prompt_pools.json` (or `data/nsfw_pose_expression_options.json`), then restart the relevant Mac aiohttp service or Windows ComfyUI service; audits run via `tools/audit_prompt_pools.py` and `tools/audit_generated_prompts.py`.

## Update: legacy rewrite layers removed

After the composer took over normal, bold, and bold_no_outfit (modern and ancient), the theme-blueprint pose/outfit overrides, reference seduction poses, environment-anchor poses, normal pose reselection, foot-risk rewrites, and the normal/bold outfit template normalizers were deleted. The `prompt_parts` / `generate_candidate_parts` chain and `prompt_planner.py` were deleted. All four scales now call the composer directly; independent pose text is selected inside that same pipeline rather than replacing a generated third-tier pose afterwards. One shared bounded retry loop checks and resamples the full combination for every scale; no separate fourth-tier assembler or retry loop remains. The independent JSON pool and negative-prompt policy are not changed by this refactor.

## Update: rewrite layer removed

`prompt_postprocess.py` (about 1900 lines of string replacement tables) was deleted. Measured on 810 composer samples it only did three things: name hands left/right, strip leftover "A或B" alternatives and drop a duplicated quality concept. Those are now fixed in the data (`_name_hands` in `prompt_composer.py`, no "或" in data, no duplicate quality concepts) and guarded by tests. It also rewrote user-typed prompts at submission and was not idempotent, so `prompt_engine.py` now renders each dimension verbatim (only sentence punctuation and `她穿着`), mobile generation no longer rebuilds or cleans prompts, and `_prompt_text` returns text unchanged. The independent pose loader validates camera scope at load time; it does not silently trim out-of-scope clauses.

## Host boundary

The public prompt engine is unchanged. Mac uses `tools/run_mac_local_server.py`, `rpp_server.py` and the lightweight `rpp_folder_paths.py` directory provider. `rpp_routes.py` owns the single route table shared with `__init__.py`. Only the ComfyUI entry imports `rpp_nodes.py` and `rpp_comfy.py` (queue validation/admission). Mac mobile jobs use remote queue/history and local asset receipts; no local ComfyUI queue fallback remains.
