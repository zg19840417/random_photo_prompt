import random
import unittest
from unittest.mock import patch

import prompt_composer as composer
import prompt_engine as engine


class PromptCompositionPipelineTests(unittest.TestCase):
    def test_all_scales_use_the_same_public_composition_path(self):
        for scale in composer.COMPOSER_SCALES:
            with self.subTest(scale=scale), patch.object(engine, "compose_parts", return_value={}) as compose:
                engine.generate_prompt_items(1, {"scale": scale, "shot": "full_body"}, "pipeline")
                self.assertEqual(compose.call_count, 1)
                self.assertEqual(compose.call_args.args[0], scale)
        self.assertFalse(hasattr(engine, "_nsfw_parts"))

    def test_independent_pool_text_is_preserved_for_every_selection(self):
        text = "她微微侧过脸。她看向镜头，唇角微微扬起。"
        for cast in composer.CASTS:
            for era in ("modern", "ancient"):
                for shot in ("head_shot", "half_body", "full_body"):
                    for aspect in ("portrait", "landscape", "square"):
                        with self.subTest(cast=cast, era=era, shot=shot, aspect=aspect), \
                             patch.object(composer, "pose_expression_options_by_aspect", return_value=[text]) as source, \
                             patch.object(composer, "_pool", wraps=composer._pool) as pool:
                            parts = composer.compose_parts("nsfw", shot, aspect, random.Random("pipeline"), engine.render_prompt_lines, era, cast)
                            source.assert_called_with("nsfw", shot, aspect, cast)
                            self.assertEqual(parts["pose_expression"], text)
                            self.assertEqual(parts["art_pose"], text)
                            self.assertEqual(engine.render_prompt_lines(parts)["pose"], text)
                            self.assertEqual(parts["outfit"], "")
                            self.assertTrue(composer.POOLS["PLACES"][parts["art_place"]]["private"])
                            self.assertNotIn("POSES", [call.args[0] for call in pool.call_args_list])
                            self.assertNotIn("EXPRESSIONS", [call.args[0] for call in pool.call_args_list])

    def test_retries_recompose_all_dimensions_and_use_the_shared_limit(self):
        for scale in composer.COMPOSER_SCALES:
            with self.subTest(scale=scale), \
                 patch.object(composer, "_compose_once", side_effect=[{"attempt": str(i)} for i in range(8)]) as compose, \
                 patch.object(composer, "fluency_defects", side_effect=[[object()], []]) as check:
                result = composer.compose_parts(scale, "full_body", "portrait", random.Random(1), lambda parts: parts)
                self.assertEqual(result["attempt"], "1")
                self.assertEqual(compose.call_count, 2)
                self.assertEqual(check.call_args.args[1], scale)
            with self.subTest(scale=scale, exhausted=True), \
                 patch.object(composer, "_compose_once", return_value={}) as compose, \
                 patch.object(composer, "fluency_defects", return_value=[object()]):
                composer.compose_parts(scale, "full_body", "portrait", random.Random(1), lambda parts: parts)
                self.assertEqual(compose.call_count, composer._ATTEMPTS)

    def test_empty_independent_pool_does_not_fall_back_to_other_tiers(self):
        with patch.object(composer, "pose_expression_options_by_aspect", return_value=[]):
            with self.assertRaises(ValueError):
                composer.compose_parts("nsfw", "full_body", "portrait", random.Random(1), engine.render_prompt_lines)
