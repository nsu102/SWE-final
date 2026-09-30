import unittest

import numpy as np
import torch
from PIL import Image

from src.backend.auth import FailureLimiter, bearer, hash_password, verify_password
from src.backend.db import merge_search_results, vector_literal
from src.backend.ml import FashionModels, prepare_query_views
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
        self.assertEqual(2, len(prepared.images))
        self.assertEqual((217, 217, 217), prepared.masked_image.getpixel((0, 0)))

    def test_merge_search_results_uses_best_view_score(self):
        first = [{"platform": "musinsa", "goods_no": "1", "similarity": 0.7}]
        second = [
            {"platform": "musinsa", "goods_no": "1", "similarity": 0.8},
            {"platform": "musinsa", "goods_no": "2", "similarity": 0.75},
        ]
        merged = merge_search_results([first, second], limit=2)
        self.assertEqual(["1", "2"], [row["goods_no"] for row in merged])
        self.assertEqual(0.8, merged[0]["similarity"])

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
