import unittest

import numpy as np
import torch
from PIL import Image

from src.backend.auth import FailureLimiter, bearer, hash_password, verify_password
from src.backend.db import color_distance, rerank_by_color, vector_literal
from src.backend.ml import FashionModels, prepare_query_views, rgb_to_lab
from src.jobs.index_catalog import plan_records


class BackendUtilityTest(unittest.TestCase):
    def test_vector_literal(self):
        self.assertEqual("[0.10000000,-0.25000000]", vector_literal([0.1, -0.25]))

    def test_transformers_feature_output_compatibility_shape(self):
        class Output:
            pooler_output = torch.ones((2, 512))

        output = Output()
        features = output if isinstance(output, torch.Tensor) else output.pooler_output
        self.assertEqual((2, 512), tuple(features.shape))

    def test_target_count_only_plans_missing_records(self):
        records = [
            {"product": {"goods_no": str(goods_no)}}
            for goods_no in range(1, 6)
        ]
        planned = plan_records(
            records, {"1", "4"}, limit=None, target_count=4, skip_existing=True
        )
        self.assertEqual(["2", "3"], [row["product"]["goods_no"] for row in planned])

    def test_skip_existing_limit_applies_to_new_records(self):
        records = [
            {"product": {"goods_no": str(goods_no)}}
            for goods_no in range(1, 6)
        ]
        planned = plan_records(
            records, {"1"}, limit=2, target_count=None, skip_existing=True
        )
        self.assertEqual(["2", "3"], [row["product"]["goods_no"] for row in planned])

    def test_prepare_query_views_returns_box_and_masked_crop(self):
        image = Image.new("RGB", (100, 120), (255, 0, 0))
        mask = np.zeros((120, 100), dtype=bool)
        mask[20:100, 25:75] = True
        prepared = prepare_query_views(image, mask)
        self.assertTrue(prepared.used_top_mask)
        self.assertEqual(prepared.box_image.size, prepared.masked_image.size)
        self.assertIs(prepared.masked_image, prepared.search_image)
        self.assertEqual((0.21, 0.12, 0.79, 0.88), tuple(round(v, 2) for v in prepared.crop_box))  # 8% padding
        # Pure red garment: Lab ≈ (53, 80, 67).
        self.assertEqual((53, 80, 67), tuple(round(v) for v in prepared.color_lab))
        self.assertEqual((217, 217, 217), prepared.masked_image.getpixel((0, 0)))

    def test_rgb_to_lab_reference_colours(self):
        lab = rgb_to_lab(np.array([[255, 255, 255], [0, 0, 0]], dtype=np.uint8))
        np.testing.assert_allclose(lab, [[100, 0, 0], [0, 0, 0]], atol=0.5)

    def test_rerank_by_color_prefers_same_colour_among_close_matches(self):
        beige, black = [75.0, 3.0, 15.0], [15.0, 0.0, 0.0]
        rows = [
            {"goods_no": "black", "similarity": 0.86, "color_lab": black},
            {"goods_no": "beige", "similarity": 0.84, "color_lab": beige},
            {"goods_no": "unknown", "similarity": 0.85, "color_lab": None},
        ]
        ranked = rerank_by_color(rows, (74.0, 4.0, 16.0), weight=0.15)
        self.assertEqual(["unknown", "beige", "black"], [row["goods_no"] for row in ranked])
        self.assertLess(color_distance(beige, beige), 1e-9)
        self.assertEqual(rows, rerank_by_color(rows, None, 0.15))

    def test_password_hash_roundtrip_and_salt(self):
        stored = hash_password("correct horse")
        self.assertTrue(verify_password("correct horse", stored))
        self.assertFalse(verify_password("wrong horse", stored))
        self.assertNotEqual(stored, hash_password("correct horse"))

    def test_bearer_token_parsing(self):
        self.assertEqual("abc", bearer("Bearer abc"))
        self.assertIsNone(bearer("Basic abc"))
        self.assertIsNone(bearer(None))

    def test_failure_limiter_blocks_after_limit_and_resets(self):
        limiter = FailureLimiter(limit=2, window=60)
        limiter.hit("a")
        self.assertEqual(0, limiter.retry_after("a"))
        limiter.hit("a")
        self.assertGreater(limiter.retry_after("a"), 0)
        self.assertEqual(0, limiter.retry_after("b"))
        limiter.reset("a")
        self.assertEqual(0, limiter.retry_after("a"))


if __name__ == "__main__":
    unittest.main()
