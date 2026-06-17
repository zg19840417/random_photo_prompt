# Prompt Generation Rules

## Document Role

This document owns rule1 prompt generation: six final dimensions, camera scope constraints, prompt data source, output shape, scale behavior, negative prompts, reverse-prompt expectations, and mobile/desktop rule parity.

This document does not define rule2 option-expansion formats or image-to-video motion option formats. Use:

- `docs/KEYWORD_EXPANSION_OPTION_GUIDE.md` for rule2 keyword-expansion option writing.
- `docs/VIDEO_PROMPT_OPTION_GUIDE.md` for image-to-video action prompt option writing.
- `docs/AI_CONTEXT.md` for the project index and current implementation context.

## Current Architecture

The generator has exactly six final prompt dimensions:

1. Camera.
2. Character face and body identity.
3. Makeup.
4. Outfit.
5. Pose and expression.
6. Scene and lighting.

Do not reintroduce old fragmented dimensions such as separate expression, head gaze, face action, hand action, clothing state, clothing motion, material, color, prop, foreground, body surface, photo finish, style pack, scene pack, or scene action pools.

Do not keep compatibility layers for removed pools. If an old pool name is removed from runtime selection, it must not remain as an import target, alias, fallback, or hidden bridge.

The generator may use an internal director table before selecting dimension options. This table is a coordination layer, not a seventh final dimension. It should bias option selection toward one coherent style motif, visual focus, scene family, lighting mood, and material/color relationship. It must not append visible labels or extra director prose to the final prompt, and it must respect the 800-character ceiling.

The active director table should stay in the sunny, warm, vivid, multicolor high-saturation direction unless the user explicitly asks for a darker style. Current director families are pool multicolor glamour, beach vivid glamour, garden water-light seduction, glass balcony color light, bright color studio fashion, tropical terrace sensuality, sweet vivid tease, and occasional forced-perspective focus. Do not restore old dark private-room, nightclub, wet-night, or minimal cold defaults as the dominant style.

Director logic should coordinate the existing six dimensions before assembly. It may select a scene package first and use that scene as a soft context signal for outfit and pose/expression, so beach, pool, garden, terrace, glass, and studio prompts receive matching props, actions, accessories, material textures, and color language. This context signal must not become a new visible output line.

The generator may also use internal color-palette and filter-grade packages. They are coordination layers, not visible dimensions. A color palette defines main color, support color, accent color, suitable scene cues, outfit/accessory colors, and nail polish colors. A filter grade defines saturation, contrast, highlight behavior, shadow behavior, skin brightness, and a compact photographic finish phrase. Palette and grade should bias selection and add at most short natural clauses, never labeled metadata.

The generator may use internal emotion-intent, visual-focus, pose-family, feedback-tag, and candidate-scoring logic. These are coordination and quality-control layers, not visible dimensions. Emotion intent biases expressions toward active, motivated smiles and lively psychological states. Visual focus chooses one main focus path allowed by shot scope, such as eyes/lips, hand foreground, collarbone/chest, waist curve, hip-leg line, feet/ground contact, or forced perspective. Pose-family weights keep posture variety balanced by shot and aspect. Feedback tags capture recurring quality risks such as flat face, red lips, missing full-body foot anchor, side padding, orientation mismatch, and over-length prompts. Candidate scoring should generate several internal candidates and return the best one without exposing the rejected candidates.

## Prompt Data Source

Prompt option text is edited in `data/prompt_pools.xlsx`, then converted into runtime data by `tools/build_prompt_data_from_excel.py`.

Use `tools/export_prompt_data_to_excel.py` only when bootstrapping or refreshing the Excel file from the currently effective Python data. The exporter imports `prompt_data.py` and writes the final in-memory pool values after all source extensions and overrides have run; do not mechanically copy intermediate source blocks by hand.

Do not directly edit generated runtime data for content changes. If `prompt_data_generated.py` exists, `prompt_data.py` loads it as the preferred pool source and keeps the original in-file definitions only as fallback data.

For any prompt pool option addition, replacement, deletion, or rewrite, except the protected NSFW pose/expression pool:

1. Edit `data/prompt_pools.xlsx`.
2. Run `tools/build_prompt_data_from_excel.py`, or double-click `一键转换Excel提示词数据.bat` to build and audit in one step.
3. Verify the regenerated runtime artifact.
4. Run the required prompt audits.

Do not hand-edit `prompt_data_generated.py`. Do not hand-edit prompt option content in `prompt_data.py` unless changing fallback/bootstrap behavior is the explicit task. If the generated artifact later becomes JSON instead of Python, the workflow remains Excel first, generated artifact second.

Protected exception: 四档/`nsfw` 的 `POSE_EXPRESSION_OPTIONS` 姿势和表情维度只使用 `data/nsfw_pose_expression_options.json`。它不走 Excel 转 runtime 数据链路，不读取 Excel 生成的 `POSE_EXPRESSION_OPTIONS/nsfw`，也不读取 `landscape_pose_expression_options/nsfw`。`tools/build_prompt_data_from_excel.py` 和 `tools/export_prompt_data_to_excel.py` 必须跳过这些条目，转表时不得覆盖或回填该 JSON 内容。运行时先加载 `prompt_data_generated.py`，再用 JSON 覆盖 `POSE_EXPRESSION_OPTIONS["nsfw"]`；`pose_expression_options_by_aspect("nsfw", ...)` 必须直接从该 JSON 覆盖后的池读取。

## Output Shape

Generated positive prompts should be compact natural Chinese prose, not titled modules. For readability, the final prompt may place each selected dimension sentence on its own line, but each line should remain natural prompt text without dimension labels.

The final positive prompt must not exceed 800 Chinese characters total, counting line breaks and the fixed quality phrase when present. This is a hard project rule. When content is too long, remove repeated or format-like wording before removing meaningful visual content: repeated camera crop labels, repeated body-part lists, repeated skin-whiteness wording, repeated lip constraints, repeated mood endings, and the fixed quality tail. Preserve visible fixed-character identity wording before trimming other dimensions.

Final sentence order:

1. Pose and expression sentence.
2. Scene and lighting sentence.
3. Short scale-specific quality phrase, only when it fits within the 800-character limit.
4. Camera sentence.
5. Character identity sentence.
6. Outfit sentence for normal and bold only; omit this sentence completely in bold_no_outfit and NSFW mode.
7. Hair sentence.
8. Makeup sentence.

This front-loads pose, scene/light, and quality because local text-to-image models usually follow earlier prompt blocks more strongly. Camera, identity, outfit, hair, and makeup still remain visible dimensions, but should avoid repeating crop labels or generic quality words already covered earlier.

Do not output labels such as `镜头:`, `角色:`, `妆容:`, `穿着:`, `姿势:`, or `场景:`.

## Camera

Only five camera types exist:

- 头部: shoulder-and-above framing.
- 半身: shoulder-and-above framing.
- 半身: thigh-and-above framing.
- 半身: thigh-and-above framing.
- 全身: full-body framing.

Camera scope is a hard global constraint. Every other dimension must describe only content visible in the selected frame.

Half-body and full-body camera and pose pools may branch by workflow frame orientation:

- Portrait frame: height is greater than or equal to width. Use vertical composition wording, vertical body lines, top-to-bottom silhouette, and standing or lying compositions that fit a tall frame. Full-body portrait prompts must explicitly preserve head-to-toe framing, including lower legs, ankles, feet, and a small floor margin below the feet; avoid thigh-up, knee-up, or cropped-leg implications.
- Landscape frame: width is greater than height. Use horizontal composition wording, diagonal or side-to-side body lines, reclining/leaning/sideways placement, and scene space that fits a wide frame.
- Frame orientation and character body direction must match. Landscape prompts should make the character's body axis horizontal or diagonal across the wide frame, such as side-lying, reclining, horizontal seated, sideways support, or wide diagonal extension. Portrait prompts should make the character's body axis vertical or top-to-bottom, such as standing, upright sitting, kneeling upright, vertical lean, or vertical seated extension.
- Do not combine landscape framing with a vertical standing body. Do not combine portrait framing with a horizontal lying body.
- Head and upper-body scopes do not need strong frame-orientation branching unless the pose text clearly calls for it.
- If the frontend cannot detect a reliable width and height from the workflow, generation must default to portrait orientation.
- Frame orientation is a sub-pool selector only. It must not become a new final prompt dimension or visible node option.
- On the mobile generation page, frame orientation is inferred after prompt generation from the pose and camera text. The visible shot choice is body coverage only, not a portrait/landscape choice.

头部:

- Means shoulder-and-above framing. The visible body range is head top, full face, hair contour, neck, and shoulders.
- May describe face, eyes, lips, cheek, jaw, hair around face, neck, shoulder line, and fingers near face, jaw, neck, or shoulder.
- Must keep the full top of the head and hair contour inside the frame.
- Must not reach chest, waist, hips, thighs, legs, feet, shoes, or full-body posture.

半身:

- May describe face, eyes, lips, cheek, jaw, hair around face, neck, shoulders, collarbones, clavicle shadows, complete bust/chest volume, breast lower-edge transition, a small upper-waist segment, and fingers near face, collarbone, chest edge, or upper waist.
- Must keep the full top of the head and hair contour inside the frame; do not crop off the head top while trying to include the chest.
- Must include the complete chest/bust shape and stop at the upper waist. It should show only a small part of the waist and must not reach the navel, hips, thighs, legs, feet, shoes, or full-body posture.
- Must not become a face-only crop, a collarbone-only crop, or a waist-up half body. Use this direct camera boundary instead of softer upper-body wording: `肩部以上镜头，头顶完整，脸部、肩颈、锁骨、完整胸部入镜，画面下缘停在上腰，只露出一小段腰部`.
- "A little below the collarbone" is too conservative for this shot. "大腿以上镜头" is too broad and tends to become a standard half body. Prefer the direct `肩部以上镜头` wording above.
- Runtime prompt wording should treat this as an upper-body medium close portrait, not an extreme face closeup. Camera options own the crop boundary; character, pose, outfit, and lighting options should not repeat the full crop sentence.
- Upper-body close portrait options should mention chest form only when it is part of that dimension's job, and should keep it short. Do not repeat complete bust, breast lower-edge, upper waist, and crop-line wording in every dimension.
- Background should not be described. The frame is a tight upper-body close portrait; scene and lighting may only describe close light on the face, neck, shoulders, collarbones, complete chest, breast lower-edge transition, a small upper-waist segment, hair edge, and nearby fingers.

半身:

- Means thigh-and-above framing. The visible body range is head, face, shoulders, chest, waist, and hands around the upper body; the lower edge should land around the waist.
- May describe face, hair, shoulders, neck, collarbones, bust, upper chest, waist, hands, top outfit, waist-edge styling, and pose direction.
- Must not require hips, thighs, lower legs, feet, toes, shoes, or complete full-body posture. The backend may choose portrait, landscape, square, or moderately wide resolutions to preserve the selected waist-up pose.

半身:

- Means thigh-and-above framing. The visible body range is head, face, shoulders, chest, waist, hips, thighs, knees, and calves; feet are not required.
- May describe face, hair, shoulders, neck, collarbones, bust, waist, hips, thighs, knees, calves, hands, outfit coverage down to calves, and pose direction.
- Must not require feet, toes, shoes, or head-to-toe full-body framing.

全身:

- May describe the complete figure, legs, feet, footwear, and whole outfit.
- Full body means every body part should fit inside the frame. It is not synonymous with standing. Valid full-body poses include standing, kneeling, sitting, lying, starfish lying, jumping, twisting, and other compositions, as long as head, torso, arms, hands, legs, feet or footwear, and the pose's outer silhouette remain visible.
- In portrait orientation, full body means the full figure from head top to feet must remain visible. The prompt should keep lower legs, ankles, feet or footwear, foot placement, and a concrete visible ground surface under the feet in frame.
- Full-body camera options should include a concrete ground/floor anchor: foot placement, landing point, floor texture, sand, grass, tile, deck, reflective pavement, or studio floor under the feet or body. This is a framing stabilizer, not an extra scene dimension, and it should remain short enough that scene/light options still own the broader environment. Prefer naming what the ground is over generic margin wording.

## Character Identity

The fixed character identity must remain immediately after the camera sentence. It is generated from one active character pool according to camera scope.

The fixed character identity is source text, not a style pool. When adapting it to a narrower camera scope, preserve the original wording for every attribute that remains visible in that scope. Do not rewrite visible traits into synonyms, softer wording, new proportions, or new emphasis. Scope adaptation may only delete original clauses that are outside the frame; it must not alter clauses that should still appear in the frame.

Core identity anchors:

- Cold porcelain-white dewy skin.
- 22-year-old K-pop Korean female star.
- Slim pointed V-shaped face.
- High nose bridge.
- Pointed chin.
- Narrow fox-shaped eyes.
- Light brown contacts.
- Straight black hair to the chest where visible.
- Slender black fingernails and black toenails where visible.

Body description depends on framing:

- Full body: eight-head-tall hourglass figure with a slim-boned frame, full bust and hips, narrow waist, extremely slender long thighs where visible, slender black fingernails and black toenails.
- Large half body: face, hair, shoulders, collarbones, bust, waist curve, hips, thighs, knees, calves, hands near face/chest/waist/thigh edge, slender black fingernails.
- Half body: face, hair, shoulders, collarbones, bust, waist curve, hands near face/chest/waist edge, slender black fingernails.
- Upper body: face, eyes, lips, cheek, jawline, hair around face, neck, shoulders, collarbones, complete chest/bust volume, full rounded chest contour, breast lower-edge transition, slender black fingernails only if fingers appear near face, neck, collarbone, chest edge, or upper waist.
- Head shot: face, eyes, lips, cheek, jawline, hair around face, neck, shoulders, and slender black fingernails only if fingers appear near face, neck, or shoulder.

Character identity must not describe outfit, nudity, sexual acts, scene, lighting, or pose.

## Makeup

Makeup is one complete paragraph option.

Format:

`makeup style keynote, base makeup, eye makeup, contacts or lashes, lip detail, face-contour detail`.

Makeup only describes the face. It must not describe pose, clothing, scene, or lighting.

Across all scales, facial blush must stay subtle and natural. Small areas of faint cheek warmth or slight natural rosiness are allowed, but do not describe large-area flushing, deep red cheeks, heavy heat-blush, strong nose-bridge flushing, or intense red-face effects because they make the generated face look unnatural.

Lip color should avoid deep red, wine-red, dark berry, dark rose, strong red-lip, heavy red lipstick wording, obvious colored lipstick, and any lip-plumping effect. Prefer natural original lip color, clear colorless gloss, natural pink moisture, hydrated shine, a thin lip shape, and crisp thin lip edges. If lipstick, balm, or gloss is mentioned, it should only make the original thin lips look hydrated and glossy, never darker, redder, thicker, fuller, swollen, overlined, or inflated beyond the natural lip shape. Smoky eye makeup is allowed only as light smoky, soft smoky, or shallow brown-gray shadow around the eye tail; avoid heavy black-gray smoke, strong smoky deepening, or dark red smoky wording.

This lip-color and thin-lip rule must be enforced at runtime, not only in source option wording. Use compact positive wording such as `纤薄原生唇形，透明无色水光，浅粉自然唇色` instead of repeating a long lip paragraph in every final prompt. The negative prompt must explicitly suppress red lipstick, burgundy lips, wine-red lips, crimson lips, dark lip color, lip tint, obvious colored lipstick, plump lips, full lips, thick lips, overlined lips, and overfilled lips because models can otherwise infer them from the surrounding style.

## Outfit

Outfit is one complete paragraph option.

Format:

`era and fashion style, main color, garment structure, material or surface, visible coverage according to camera scope`.

Normal and Bold outfit options describe actual clothing. Bold_no_outfit and NSFW mode do not load or output the outfit dimension at all.

Bold outfit options should read as vivid adult-glamour styling with clear clothing presence rather than nude-feeling exposure. Clothing may be revealing, tight, glossy, cutout, or high-slit, but avoid wording that implies almost no clothing, such as 裸露, 极少覆盖, 最低覆盖, 只剩小布片, 布料面积压到最低, 覆盖面积极少, or similar bare-exposure language. Do not let bold outfits collapse into only mini-skirts; keep variety across mini skirts, slip dresses, high-slit long dresses, fitted bodysuits, one-piece swimwear with sheer coverups, corset tops with hot pants or tailored shorts, and stocking-based glamour looks. Do not use latex, latex-like clothing, glossy leather, leather-like clothing, leather skirts, or leather/PVC styling. Prefer saturated but tasteful non-leather materials and details: jewel-blue or magenta satin, deep-wine silk, chiffon or gauze overlays, bright lace edges, corset tops, boning seams, cross straps, halter tops, pearl/silver trim, gold metal buckles, bright chain details, transparent glove edges, sheer accent panels, high-slit or cutout structures, and small but readable bralette/corset/bodysuit/swimwear-like pieces. Accessories should increase sensuality and visual richness while staying sparse and purposeful: usually one or two focus pieces such as a choker, waist chain, belly chain, arm cuff, thigh band, leg ring, ankle chain, delicate metallic charm, transparent glove edge, sheer stocking edge, garter stocking edge, or rhinestone detail. Clothing color and material should contrast with cold fair skin so the skin stays very white without making the prompt feel nude.

Skin whiteness should be supported primarily through clothing and environment contrast, not by globally bright lighting. Prefer dark or saturated outfit colors such as deep wine, jewel blue, black-gold, silver-gray, glossy black, magenta satin, and pearl/silver trim to set off fair skin. Avoid repeatedly asking lights to make the whole body bright, glowing, or evenly white.

Bold upper-body close portrait outfit options should stay compact but not read as bare. Write them as bright, jewelry-led glamour styling: vivid narrow straps, glossy bralette or corset edges, pearl or metal chokers, collarbone chains, short transparent glove edges, bright lace trims, and one or two sensual accessories should carry the visual design. Avoid repeating generic neckline/shoulder-strap scaffolding across every option because it makes the final prompt read as ordinary clothing rather than stylized glamour.

Outfit must obey camera scope:

- Head shot: describe only neck, shoulder, hair-side, earring, choker, collar, or shoulder-edge styling visible above the shoulders.
- Upper body: describe only neckline, shoulder-edge hint, choker/neck accessory, chest styling, or upper-waist edge styling that allows the complete chest to enter frame.
- Half body: describe clothing and accessories visible from the head down to the waist, including upper garment, waist-edge styling, and visible hand placement.
- Large half body: describe clothing and accessories visible from the head down to the calves, including upper garment, waist/hip/thigh/knee/calf-edge styling.
- Full body: describe complete clothing and footwear.

Outfit must not describe expression, pose, scene, or lighting.

## Pose And Expression

Pose and expression is one complete paragraph option.

It must always include expression. The expression part should describe:

- Head angle relative to camera: up/down/left/right/tilt/turn.
- Eye state: open, half-open, narrowed, heavy-lidded, direct gaze, side gaze.
- Mouth: closed, slightly parted, relaxed, or softly open.
- Smile type when present: faint smile, cold smile, teasing smile, mocking smile, restrained laugh, open laugh.
- Optional suggestive intent phrase that remains non-explicit.

Then describe body posture only within camera scope.

Format:

`camera scope, head angle, eye state and gaze direction, mouth state and smile type, main body posture, hand placement, visible body line or emotional effect`.

Pose and expression must not describe clothing details, scene lighting, or out-of-frame body parts.

Pose options must not take over camera or resolution duties. Do not write portrait/landscape, vertical/horizontal frame, lens distance, camera pull-back, crop boundary, composition margin, or resolution-oriented wording inside pose options. The pose sentence may name a viewing relation only when it is part of the body mechanics, such as top-down lying, low gaze, over-shoulder look, or side-facing posture.

Each pose option should keep one primary pose family and one secondary action at most. Avoid stacking several strong body mechanics in the same option, such as jumping plus twisting plus crossed legs plus raised arms, or standing plus deep squat plus knees spread plus torso thrust. Full-body options should describe a readable whole-body silhouette, not many simultaneous commands for head, shoulders, hands, waist, hips, thighs, knees, ankles, feet, and expression. Hands should usually have one simple job: hair, face, collarbone, waist, support, or relaxed placement.

For Bold and NSFW, pose options should strongly serve adult glamour composition: emphasize perfect facial appeal, seductive gaze, lips, graceful neck and shoulder rhythm, waist curve where visible, bust contour where visible, thigh line where visible, and hands guiding attention through visible body curves. The wording should feel intensely alluring and magnetic while staying non-explicit: no sexual acts, no exposed intimate anatomy, no simulated sex, and no forced nudity wording. Upper-body close portrait options must remain in the head-to-complete-chest-and-small-upper-waist crop; half body options must remain thigh-up; full body options may use complete silhouette, legs, feet, and whole-body S-curve.

Bold and NSFW pose pools may include more sexually suggestive posture language than normal mode. Bold should express this through non-explicit mechanics: lowered gaze, parted lips, hands near lips/neck/collarbone/chest edge/waist/hip/thigh edge, forward lean, backward arch, side-lying, bed-edge seated posture, M-shaped seated or kneeling silhouette, low forearm support, over-shoulder rear-side silhouette, leg opening as a silhouette, and protective boundaries created by hair, arms, shadow, sheets, framing, or body angle. NSFW may use stronger adult-private glamour pressure and more direct body-curve language, but still avoid explicit sex acts, genital wording, coercion, or mechanical sexual instructions.

Body-part focus is allowed inside pose-expression options only when it fits the selected shot scope. Head shots may focus on lips, tongue tip, hands, nails, neck, and shoulders. Upper-body shots may additionally focus on complete chest, collarbones, and upper waist. Half-body shots may focus on hands, chest, waist, and body curve to the waist, but not hips, thighs, legs, or feet. Large-half-body shots may focus on hip-side silhouette, thighs, knees, calves, and leg line, but not feet or toes. Full-body shots may focus on feet, toes, ankles, legs, hip/rear-side silhouette, and complete body line. Do not add a separate body-part camera dimension unless the runtime camera pool is made scale-aware.

Bold and NSFW may occasionally use forced-perspective body-part focus as an artistic composition tool. The pose text should explicitly describe near-large-far-small depth with wording such as 近大远小, 强透视, 前景, 靠近镜头, or 视觉路径. Scope still controls what can be emphasized: head shots can use lips, tongue tip, fingers, nails, jaw, neck, and shoulders; upper-body can use hands, collarbones, complete chest, and upper waist; half-body can use hands, chest, and waist; large-half-body can use knees, calves, thigh/hip-side silhouette, and hand foreground; full-body can use feet, toes, ankles, legs, hands, and complete body line. Forced perspective should guide the viewer's eye through one main path, not list every attractive body part.

Pose/expression should feel like a captured moment rather than only a static inventory of body parts. Useful moment cues include fingers moving toward the lens, hair or accessories reacting to a turn, the gaze catching the camera, a body shift just reaching its endpoint, or a limb entering the foreground. Keep one primary action and one secondary action at most.

Expression wording should not collapse into flat calmness, coldness, or barely visible polite smiles. All scales should include more sunny, active, and emotionally motivated smiles: bright smile, open laugh, playful grin, teasing smile, proud smile, mock-blaming smile, laughing challenge, sweet-but-dangerous smile, amused scolding, and invitation-like smile. The smile should have a reason in the moment, such as being amused by the camera, pretending to blame the viewer, enjoying a joke, showing off with confidence, inviting attention, or teasing the viewer. Avoid filling the pool with only "淡淡微笑", "含蓄笑意", or "礼貌浅笑".

Bold and NSFW expression wording should not stay at plain coldness or neutral coolness. It should carry stronger and more varied adult-glamour emotional signals such as seductive invitation, contemptuous dominance, mocking smile, disdainful glance, provocative bad smile, predatory eye contact, pressure-heavy direct stare, playful teasing, sweet-but-dangerous smile, lazy misty gaze, smug challenge, open provocation, amused mockery, vivid seduction, and direct inviting eye contact. Coldness can remain as one undertone, but it must not dominate most outputs.

Bold and NSFW pose pools should stay close to the strongest seductive posture families instead of drifting into ordinary standing or casual sitting. Preferred standards:

- Upper-body close portrait: tight upper-body close pressure, lowered chin then lifted gaze, slight head tilt or controlled backward tilt, half-open fox eyes, direct or side-hook gaze, softly parted or glossy closed lips, cold smile / teasing smile / no smile, shoulders, collarbones, complete bust volume, full rounded chest contour, breast lower-edge transition, and a small upper-waist segment visible, fingers near lips, cheek, jaw, neck, collarbone, chest edge, or upper waist.
- Half body: thigh-up composition, camera-leaning body, one shoulder high and one low, waist twist, controlled backward arch, over-shoulder look, hands moving between hair, lips, collarbone, bust edge, waist, hip, and thigh edge. The visual path should guide from eyes and lips to collarbones, bust edge, narrow waist, hips, and thighs.
- Full body: over-shoulder S-curve, wall or support lean, one-leg weight shift, crossed or extended leg line, low seated edge pose with upper body leaning back, deep side bend, raised arm through hair and the other hand at waist. The visual path should connect face, neck, waist curve, hips where visible, long legs, and foot placement.
- Full body may also use seated or kneeling seated glamour poses with knees opened into an M-shaped composition, only when the wording keeps the focus on silhouette, waist-back curve, leg lines, foot placement, and protective concealment. This posture is full-body only and must include non-explicit boundaries such as hair, hands, arms, shadow, or framing maintaining concealment. If the pose uses hands to cover the body, describe it as hands maintaining non-explicit concealment over key edges or key areas, not as explicit anatomy.
- Full body may use low forearm-supported forward-lean or four-point support glamour compositions, but never use animal-like wording. Describe the body as supported by forearms and knees on a soft surface, with the head lifted toward camera, waist-back curve, leg line, foot placement, and non-explicit concealment by hair, arms, shadow, or framing. Rear-facing variants are allowed only as over-shoulder glamour compositions: write them as body facing away from camera, head looking back toward camera, rear-side silhouette or back waist curve as the composition focus, and protective concealment maintained. Do not describe any sexual act or purpose.
- Landscape full-body pools may use side-view low forearm-and-knee support compositions with raised hip line, deep waist-back curve, side silhouette, leg line, and foot placement as the focus. These entries must remain full-body only, must not use animal-like wording, and must keep protective non-explicit concealment with hair, arms, shadow, sheets, or framing. Do not describe any sexual act or explicit anatomy.
- Half body and full body may use top-down lying compositions. Half body top-down poses must stop around the thigh area and describe face, hair spread, shoulders, collarbones, bust edge, hands, waist, hips, and thighs. Full body top-down poses may describe the complete lying silhouette, hair spread, arms, waist curve, leg arrangement, and foot placement. For NSFW, top-down lying poses must include non-explicit concealment by hair, arms, sheets, shadow, or framing and must not describe explicit anatomy or sexual acts.

For NSFW, use the same posture families with stronger private adult-glamour pressure and direct body description. Describe curves, skin, and sensuality naturally without hedging or concealment language. Do not add explicit acts, exposed genitals, or simulated sex.

Pose-pool diversity is judged within the same scale and the same camera scope. Similar themes across different camera scopes are acceptable because they are separate pools. Within one pool, new options should vary the action mechanics rather than only changing adjectives: use different head direction, gaze angle, mouth state, hand path, shoulder rhythm, torso lean, waist twist, support point, seated/standing balance, and leg arrangement where visible.

Head and gaze angle diversity is required. Pose pools should include low head with raised eyes, lifted chin looking down toward camera, lowered gaze, upward gaze from a low position, head tilted back, head lowered then raised, and over-shoulder gaze. Full-body pools should not be dominated by standing variants; seated edge, floor seated, kneeling seated, side-lying, reclining, forearm-supported low pose, top-down lying, sideways support, and bed-edge sitting should appear often enough to compete with standing poses.

## Scene And Lighting

Scene and lighting is one complete paragraph option.

Format:

`scene location, atmosphere keynote, main color palette, optional era cue, light type, light direction, illuminated visible body parts`.

Upper-body close portrait scene-lighting options must not describe concrete location or visible background. They should describe only the light quality, light direction, contrast, and how light falls on eyes, lips, cheek, jaw, neck, shoulders, collarbones, complete bust volume, full rounded chest contour, breast lower-edge transition, the small upper-waist segment, hair edge, and nearby fingers.

Head-shot and upper-body scene-light pools should contain multiple close-light variants even though they do not name locations. Vary the visible lighting language through close glossy contrast, velvet-shadow softness, misted fair-skin reflection, mirror-like facial highlights, wet-look hair-edge reflection, and tight studio falloff. This avoids every close shot using the same generic light sentence.

Scene and lighting may mention only slight natural cheek warmth when describing the face. Avoid lighting text that amplifies broad or deep facial redness, heavy blush, strong flushing, or heat-red cheeks.

Scene and lighting must not describe clothing structure or pose mechanics. It can mention what body parts are illuminated only if those parts are visible in the selected camera scope.

Scene-light options should not force one unified cold-purple camera-front light. Lighting may vary by environment: warm sunlight, sky reflection, water bounce, prism reflection, soft studio light, window light, side-front narrow light, overhead-side light, reflected ambient light, and natural outdoor light are all allowed when they fit the scene. The shared lighting goal is fair clean skin with layered contrast. Selected visible body parts may receive controlled highlights, while the rest of the body keeps soft shadow or natural falloff; do not make the entire body uniformly bright.

Scene props and light sources must match the chosen environment. Outdoor beach, pool, yacht, garden, rooftop, terrace, and balcony scenes should use outdoor cues such as water reflections, sand bounce, sky light, colorful umbrellas, flowers, fountains, pool tiles, deck reflections, terrace railings, and outdoor furniture. Indoor studio, hotel, window, bathroom, changing-room, or shop-window scenes may use white walls, windows, curtains, glass blocks, indoor mirrors, and prism glass. Do not hard-insert indoor curtains, white walls, indoor chairs, or window props into outdoor beach, pool, terrace, or wild scenes.

Color should be bright, warm, saturated, and coordinated, not randomly multicolored. Prefer one main clothing or background color, one supporting color, and one accent color. Multicolor or prism effects should appear as selective reflection, edge light, water shimmer, or local color patches; avoid turning the whole environment into a flat full-scene color wash.

If a requirement mentions "rainbow-like" color, treat it as a request for richer coordinated colors rather than literal rainbows. Use high-saturation positive sunny color design: bright clothing, colorful accessories, saturated scene blocks, warm daylight, and small local color reflections. Do not prompt visible rainbow arcs, rainbow projections, or rainbow reflections unless the user explicitly asks for an actual rainbow.

Nail polish is a small color accent, not a fixed identity trait. Do not hard-code all visible fingernails or toenails as black. Use a balanced rotation of transparent crystal, pale pink jelly, coral pink, cherry pink, rose pink, lavender purple, lake blue, mint green, lemon yellow, peach orange, silver-white micro-glitter, and glossy black. Within one prompt, visible fingernails and toenails should usually share the same nail color for coherence.

Filter-grade wording must match the selected color and scene logic. Sunny beach, pool, terrace, and water-light scenes should use sunny clear high-saturation grading, clean highlights, and natural bright shadows. Sweet colorful studio or garden scenes may use light-film grading, vivid color blocks, and fine subtle grain. Glass, window, prism, and reflective scenes may use bright contrast grading and clean reflective highlights. Vacation, tropical, deck, and warm outdoor scenes may use warm vivid grading with saturated background colors and natural translucent skin. Do not pair dark low-key film grading with a bright sunny multicolor scene unless the user explicitly asks for contrast.

Avoid canvas-padding language. Prompts must not encourage pure-white or pure-black side margins, white/black side bars, blank side backgrounds, large borders, vertical-photo-on-wide-canvas framing, or empty negative space. Landscape camera wording should say the scene fills the wide frame, such as 横向场景内容铺满画面 or 四周都有真实场景内容, instead of 左右环境空间, 左右边距, or 四周边距. Use shallow colorful walls, pastel wall gradients, warm floor reflection, saturated background blocks, real environmental side content, or concrete visible ground surfaces instead. The negative prompt should suppress white border, black border, blank side margins, white/black side bars, pillarbox, letterbox, white/black padding, dark padding, portrait image centered on landscape canvas, and plain empty side backgrounds.

Outdoor scene expansion should cover urban streets, rooftop, balcony, beach, poolside, garden, forest trail, riverside, parking lot, rain-night street, neon alley, and resort terrace variations. Outdoor scene wording applies to half body and full body only. Upper-body close portrait entries should not mention outdoor or indoor locations, background blur, bokeh, streets, windows, rooms, sea, sky, city lights, or other scenery; they should stay as pure close upper-body lighting descriptions.

Dark-light expansion may cover low-key studio, dim hotel, private room, dark stage, rain-night street, underground parking, neon alley, and rooftop night view as environments. Dark-light entries should use selective highlights and visible shadow falloff so the skin reads pale and dimensional instead of flat. Upper-body close portrait dark-light entries must remain pure close upper-body lighting with no concrete scene or background. Half body dark-light entries may illuminate face, lips, shoulders, collarbones, hands, bust edge, and waist line. Full body dark-light entries may illuminate face, waist curve, full silhouette, legs, feet, and foot placement.

Neon adult-nightlife expansion should cover legal adult glamour venues and atmosphere such as neon lounges, private booths, cabaret stages, red-light sign streets, mirrored club rooms, underground bars, dark dance floors, and rain-wet nightlife alleys. Keep the wording about environment, atmosphere, color, and lighting only. Do not describe sexual services, explicit acts, exposed intimate anatomy, or simulated sex. Upper-body close portrait entries may use close fair-skin highlights on the face, neck, shoulders, collarbones, and upper chest, but must not name or reveal a venue or background.

Pure nature expansion should cover natural scenery without urban, indoor, architecture, vehicles, or artificial venue cues. Use environments such as meadow, forest, lakeside, waterfall, mountain ridge, beach, cliff, reed marsh, snowy field, moonlit grassland, and starlit shoreline. Half body and full body entries may describe the natural location and atmosphere, with natural sky light, moonlight, mist reflection, or water/ground bounce used to keep the skin pale and dimensional. Upper-body close portrait entries must only describe close light quality on the face, hair edge, lips, cheek, jaw, neck, shoulders, collarbones, upper-chest edge, and nearby fingers, without naming or revealing the scenery.

Scene-light coverage should stay balanced by scale. Normal mode should include clean fashion/editorial environments such as studio, apartment, gallery, city street, practice room, makeup room, rooftop, hotel lobby, beach, and cafe-like spaces. Bold mode should cover adult-glamour environments such as private suite, lounge, club booth, dark stage, poolside, mirror room, dressing room, car interior, rooftop night, and rain-night alley while staying non-explicit. NSFW mode may use stronger private adult-photography pressure, but should not collapse into only bedroom, hotel, bathroom, and bed; add dark studio, mirrored room, private lounge, rooftop night, car interior, poolside, velvet sofa, and floor/mirror compositions without sexual acts or explicit genital wording.

For half-body, large-half-body, and full-body scene-light pools, location probability should be balanced by a two-stage draw: first choose one package from `室内`, `室外`, and `野外` with roughly equal probability, then choose a concrete scene-light option inside the selected package. The Excel `notes` column is the source for this grouping and should use `场景包:室内`, `场景包:室外`, or `场景包:野外`. The package name is only a runtime selection aid and must not become a visible prompt label or a separate final dimension.

## Scale Rules

Normal:

- Broad portrait variety is allowed: fashion, travel, lifestyle, editorial, clean portrait, classical, modern, future, indoor, outdoor.

Bold:

- Every dimension should strengthen face beauty, visible body perfection, seductive gaze, soft adult glamour, skin light, crop intimacy, or clothing-edge tension.
- Outfit should be extremely minimal where visible, with object, cloth, hair, arm, pose, shadow, or framing concealment used as a deliberate non-explicit design.
- Keep it non-explicit. Do not mention exposed nipples, genitals, sexual acts, or simulated sexual acts.

NSFW:

- This project treats NSFW as intense adult glamour with direct body description.
- No explicit sexual acts, exposed genitals, genital wording, or simulated sex wording.
- NSFW allows direct description of nude figure, exposed breasts, body curves, and skin without non-explicit concealment wording. Describe what is visible naturally and directly.
- Outfit dimension is omitted completely; NSFW prompts still include camera, character identity, makeup, pose and expression, scene and lighting, and quality phrase.
- When expanding NSFW pools, only expand dimensions that are actually emitted at runtime: makeup, pose and expression, and scene and lighting. Do not expand or rely on NSFW outfit text because the outfit sentence is intentionally skipped.

## Prompt Length

- Prefer six strong sentences over many small fragments.
- Do not add titles.
- Do not duplicate the same idea across dimensions.
- Do not silently drop a selected dimension because the prompt is long; fix the option text instead.

## Negative Prompt Generation

Negative prompt output starts from the Excel-maintained `NEGATIVE_PROMPT`, then runtime appends dynamic rule-based terms. The dynamic layer should add base quality/anatomy suppression, lip and makeup risk suppression, black/white side padding and border suppression, portrait/landscape composition mismatch suppression, shot-scope leakage suppression, full-body missing-head/missing-feet suppression, flat-expression suppression when the positive prompt asks for smiles, dark-scene suppression when the positive prompt asks for sunny scenes, and normal-scale nudity suppression. This negative prompt is used for the main node and mobile image workflows, including `ZITB双采`; custom mobile prompts should also receive the same dynamic negative construction from their prompt text and inferred resolution.

## Option Completeness

Each prompt option should be a complete reusable fragment for its own dimension. Do not rely on another dimension to fill missing core information, except for fixed runtime constraints such as the global natural thin-lip constraint.

Because these options are assembled into positive text-to-image prompts, option text should be written as positive visual descriptions. Avoid putting negative instructions such as "do not", "must not", "avoid", "no", "不能", "不要", "避免", or "不出现" into positive options. Express the desired visible result directly instead, and leave prohibited concepts to audits, negative prompts, or runtime validation.

- Camera options should include camera scope, angle or camera position, composition/lens-distance cue, and crop boundary.
- Character identity options should include fixed identity, skin, face shape, key facial features, eye/contact cue, hair cue, and only the body parts visible in the selected camera scope.
- Makeup options should include makeup style, base makeup, eye makeup, contact/lash or gaze detail, lip detail, and face-contour detail. NSFW makeup must remain adult-glamour styling and must not describe sexual acts, non-consensual framing, objects in the mouth, fluids, or loss-of-control effects.
- Outfit options should include style, main color, garment/accessory structure, material, visible coverage boundary, and sparse intentional accessories where relevant. NSFW outfit options are not emitted at runtime and should not be maintained as active source data.
- Pose and expression options should include camera scope, head angle, eye state/gaze, mouth state/smile, main posture mechanics, hand placement, and visible body line or emotional effect.
- Scene and lighting options should include scene or close-light setting, atmosphere, color palette, light source type, light direction, and illuminated visible body parts.

Coverage expansion should prioritize real structural variety over adjective-only variants:

- Camera coverage should include flat eye-level views, slight high angles, slight low angles, three-quarter views, side views, top-down views where useful, centered compositions, diagonal compositions, tighter intimate crops, and looser crops with clear body-boundary margins.
- Character identity coverage should stay stable and only vary the visible camera-scope wording, such as head/hair/shoulder/upper-chest framing for upper-body close portrait, waist and hand framing for half body, and complete legs/ankles/feet framing for full body.
- Makeup coverage should preserve natural thin lips and include clean daylight makeup, editorial nude makeup, cold night makeup, soft smoky makeup, wet-glow makeup, and studio contour variations.
- Outfit coverage should add visual variety without breaking scale rules: normal can use fuller fashion styles, while bold should vary ultra-minimal straps, micro fabric edges, localized gauze, sheet edges, and sparse sensual accessories.
- Pose coverage should add different body mechanics, not only stronger tone: standing, leaning, walking, sitting, kneeling, lying, side-lying, starfish lying, jumping, twisting, over-shoulder, top-down, and supported low poses should be represented where the camera scope allows them.
- Scene-light coverage should represent different environments, atmospheres, light sources, and light directions while keeping one visual goal: very fair clean skin with selective highlights, natural shadow falloff, and visible light layering instead of full-body flat brightness.

## Generated Prompt Review

Generated prompt review should inspect final combinations, not only individual pool entries.

The review script should check:

- Required dimension presence: normal and bold must include camera, character identity, makeup, outfit, pose and expression, scene and lighting, and quality; NSFW must include all of those except outfit, because outfit is intentionally omitted.
- Obvious repetition: repeated whole clauses, identical dimension text, or repeated uncommon descriptive phrases across dimensions should be reported for manual cleanup.
- Length and concept repetition: reports should show prompt-length median, p90, and max by scale/shot/aspect; dimension-length hotspots; longest generated prompts; and repeated concept groups such as skin whiteness, gaze pressure, lips, chest, waist, legs, glamour tone, light/highlight, and body curve. These checks are advisory unless they expose missing dimensions or scope conflicts, but they should guide prompt compression work.
- Photographic quality: reports should flag generic quality stacks when words such as advanced, quality, atmosphere, blockbuster, or ultra-detailed appear without concrete photographic anchors. Preferred anchors include real skin texture, controlled highlights, layered shadows, real lens depth, reflections, color grade, fine grain, and non-overexposed skin.
- Sensual tension: bold and NSFW reports should flag prompts that lack gaze, expression, or body-line anchors such as direct gaze, restrained smile, collarbone/chest-waist line, waist curve, hip-leg line, curve tension, or close lens pressure.
- Cross-dimension contradictions: selected camera scope must not conflict with body parts, posture, outfit coverage, scene, or lighting terms from other dimensions. NSFW must not emit outfit text.
- Goal alignment: bold and NSFW final prompts should clearly serve adult glamour composition by emphasizing face beauty, visible body curve where in frame, seductive gaze, lips, skin light, hand guidance, crop intimacy, and non-explicit soft adult allure. Normal prompts may be broader and less seductive.
- Scene/light direction: scene and lighting options should use sunny, warm, vivid, multicolor high-saturation atmospheres by default. Prefer daylight, colorful glass/prism reflections, warm sunlight, bright outdoor or bright-window interiors, and saturated but clean background colors. Do not let dark rooms, nightclub lighting, heavy low-key shadows, or night-only environments dominate the pools unless explicitly requested.
- Scene-prop consistency: scene props must fit the selected environment. Use water, sand, sky, umbrellas, flowers, fountains, pool tiles, deck reflections, and outdoor furniture for outdoor beach/pool/yacht/garden/rooftop/terrace/balcony scenes. Use windows, curtains, glass blocks, white walls, indoor mirrors, and prism glass only for suitable indoor studio/hotel/window/bathroom/changing-room/shop-window scenes. Do not place indoor props into outdoor scenes just to create multicolor light.
- Outfit color direction: outfit options should rotate bright, sunny, saturated colors evenly. Avoid pools dominated by black, white, gray, silver, or other neutral clothing colors. Favor coral pink, lemon yellow, mint green, peach orange, sky blue, lake blue, violet, lavender, apple green, mango yellow, cherry pink, rose pink, and other vivid colors that keep skin looking pale and clean.

Review reports are advisory for style quality unless they find missing dimensions, camera-scope violations, NSFW outfit leakage, or explicit unsafe wording.

## Image Reverse Prompt

Image reverse prompting is a node-local helper, not a new dimension system.

- The frontend may let the user choose one local image and click a reverse-prompt button.
- The selected image should be previewed inside the node for the current browser session so the user can verify which image will be interrogated.
- The active local reverse-prompt model is `C:\ComfyUI-共享目录\LLM\Huihui-Qwen3-VL-4B-Instruct`.
- The backend endpoint must use local image caption/interrogation dependencies only; do not download models during request handling.
- If the required local model is missing, return a clear error instead of fabricating a prompt from filename, scale, shot, or random pools.
- The returned prompt is written to the connected CLIP text encode widget and to the node cache, the same as a pre-generated prompt.
- Reverse-prompt output should remain one prompt string formatted as six natural lines in the same active order used by generated prompts: camera, character/subject, makeup, outfit, pose/expression, scene/light. It must not include visible labels, old style packs, scene packs, compatibility pools, or hidden fallback dimensions.
- Reverse-prompt camera wording must use the current shot scopes: 头部 is shoulders and above, 半身 is chest and above, 半身 is waist and above, 半身 is calves and above, and 全身 is complete visible body.
- Reverse-prompt outfit wording should describe visible clothing, accessories, material, color, transparency/thinness, coverage, and occlusion. When colors are visible, prefer the current sunny vivid color language rather than defaulting to black/white/gray.
- Reverse-prompt scene/light wording should follow the current sunny warm vivid multicolor high-saturation direction when it matches the image, while keeping props environment-correct: outdoor scenes may use water, sand, sky, umbrellas, flowers, fountains, pool tiles, deck reflections, and outdoor furniture; indoor scenes may use windows, curtains, white walls, glass blocks, mirrors, and prism glass.
- Reverse-prompt output must still follow project safety boundaries: adult-only glamour is allowed, but explicit sexual acts, exposed intimate anatomy, and simulated sex wording are not allowed.

## Mobile Generation Page

The mobile generation page is a queue trigger for the existing prompt generator. It must not introduce a new prompt dimension model, old prompt pools, preset managers, or a separate prompt-writing path.

Mobile generation and main-node generation use the same scale, shot, aspect inference, positive prompt, negative prompt, and resolution inference rules. The desktop frontend should apply the inferred width and height to the current graph's image-size or empty-latent widgets before queue serialization when the node's auto-resolution option is enabled; when it is disabled, the desktop graph keeps its manually configured resolution. Mobile generation applies the same inferred width and height while patching `mobile_workflow_api.json`. The backend may patch a user-provided ComfyUI API workflow template for mobile generation, but it must not silently invent a full workflow. The required template file is `mobile_workflow_api.json` in the custom node directory.

The main node and mobile page use the same user-facing scale and shot labels: 一档, 二档, 三档, 四档 and 全身像, 半身像, 半身. 三档 maps to bold_no_outfit: it follows 二档 logic but skips outfit. 四档 maps to nsfw: only pose/expression uses the dedicated NSFW pool; camera, character, makeup, scene/light, quality, color, and emotion follow 三档/二档 non-outfit logic. The mobile logic is the shared source of truth for both entry points. Shot options are body-coverage scopes only; the backend first generates the prompt, inspects the selected camera and pose text, infers the best aspect and resolution, then appends the corresponding framing sentence. Use multiple aspect families as needed: tall portrait for upright full-body poses, landscape or wide landscape for lying / side-lying / starfish / large horizontal gestures, square or near-square for compact seated, kneeling, curled, or jumping poses, suitable portrait or landscape variants for half-body poses, and upper-body portrait/landscape variants that follow the compact upper-body boundary: head top, shoulders, collarbones, complete chest, and a short upper-waist crop. Standing full-body prompts need an especially tall and narrow portrait ratio; standing, upright, walking, leaning, one-leg-weight, and foot-contact markers should resolve before broader seated/kneeling/vertical full-body markers, currently targeting 896x1920 to preserve a natural high body proportion and using a scene-matched "脚下是..." ground anchor to encourage foot visibility. Upper-body mobile default should use enough vertical room for a pulled-back upper-body medium close portrait. Full body always means all outer body parts fit in frame; half body may preserve the intended pose without requiring lower legs or feet. Mobile image width and height must keep the longest edge at or below 1920 pixels.

The mobile batch count control starts at 1 and changes only by powers of two: 1, 2, 4, 8, 16, 32, and 64. The frontend and backend must both clamp the submitted count to this range, with 64 as the maximum.

The mobile active queue progress denominator is capped at 100. When unfinished mobile jobs already exist and the user adds more jobs, only the remaining capacity up to 100 may be accepted. If the active mobile queue already contains 100 unfinished jobs, the request must not add more work and should show a clear message.

When patching the template, generated positive prompt text should go into positive CLIP text inputs. Negative CLIP text inputs should receive the existing project negative prompt when they can be identified by node title or metadata. Common width, height, seed, and noise seed inputs may be updated so phone controls affect the queued run.

If the template is missing, invalid, or cannot be queued by ComfyUI validation, return a clear error for the phone page. Do not fall back to unrelated workflows or direct image-file manipulation.

The mobile page uses the in-memory current-session job list for queue progress and prompt association. Completed mobile images should be written into the ComfyUI output subfolder `random_photo_prompt_mobile`, and the mobile gallery should read that folder by file modification time, newest first.

When the mobile page deletes images, deletion is allowed only inside the `random_photo_prompt_mobile` output subfolder. It must not delete files elsewhere in ComfyUI's output directory.

## Verification

After prompt data or generation changes:

- Run Python syntax checks.
- Generate samples for all three scales and five shots.
- Check that head shot contains head, face, neck, and shoulders, but no chest, waist, hips, legs, feet, shoes, or scene-heavy text.
- Check that upper body contains shoulders, collarbones, and complete chest/bust volume, but no navel, hips, legs, feet, shoes, or scene-heavy text.
- Check that half body contains thigh-and-above content, but no hips/thighs/legs/feet/shoes.
- Check that large half body contains thigh-and-above content, but no feet/shoes.
- Check that NSFW contains no explicit sexual acts or exposed intimate anatomy.
