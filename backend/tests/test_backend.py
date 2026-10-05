import unittest

import numpy as np
import torch
from PIL import Image

from datetime import timedelta
from unittest import mock

import jwt

from src.backend import config, tokens
from src.backend.auth import FailureLimiter, hash_password, kakao_profile, verify_password
from src.backend.db import color_distance, rerank_by_color, vector_literal
from src.backend.ml import crop_to_box
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

    def test_crop_to_box_crops_detected_top_or_keeps_photo(self):
        image = Image.new("RGB", (100, 200))
        cropped = crop_to_box(image, [10.0, 20.0, 60.0, 120.0])
        self.assertTrue(cropped.used_top_mask)
        self.assertEqual((50, 100), cropped.search_image.size)
        self.assertAlmostEqual(0.25, cropped.top_ratio)
        whole = crop_to_box(image, None)
        self.assertFalse(whole.used_top_mask)
        self.assertIs(image, whole.search_image)

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

    def test_kakao_profile_only_trusts_verified_email(self):
        account = {"email": "Me@Kakao.com", "is_email_valid": True, "is_email_verified": True,
                   "profile": {"nickname": "라희", "profile_image_url": "https://k.kakaocdn.net/a.jpg"}}
        self.assertEqual(("42", "me@kakao.com", "라희", "https://k.kakaocdn.net/a.jpg"),
                         kakao_profile({"id": 42, "kakao_account": account}))
        self.assertEqual(("42", None, "라희", "https://k.kakaocdn.net/a.jpg"),
                         kakao_profile({"id": 42, "kakao_account": {**account, "is_email_verified": False}}))
        self.assertEqual(("7", None, None, None), kakao_profile({"id": 7}))

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


class TokenTest(unittest.TestCase):
    def test_access_token_roundtrip(self):
        self.assertEqual(42, tokens.user_from_access(tokens.access_token(42)))

    def test_expired_access_token_is_rejected(self):
        with mock.patch.object(tokens, "ACCESS_TTL", timedelta(seconds=-1)):
            stale = tokens.access_token(42)
        with self.assertRaises(tokens.TokenError):
            tokens.user_from_access(stale)

    def test_refresh_token_cannot_be_used_as_access_token(self):
        refresh = tokens._encode({"sub": "42", "typ": "refresh", "jti": "x", "fam": "y"}, tokens.REFRESH_TTL)
        with self.assertRaises(tokens.TokenError):
            tokens.user_from_access(refresh)

    def test_tampered_or_foreign_tokens_are_rejected(self):
        header, payload, signature = tokens.access_token(42).split(".")
        with self.assertRaises(tokens.TokenError):
            tokens.user_from_access(f"{header}.{payload}.{signature[:-2]}AA")
        forged = jwt.encode({"sub": "1", "typ": "access", "iss": "lookfind", "iat": 0, "exp": 9999999999}, "x" * 32, algorithm="HS256")
        with self.assertRaises(tokens.TokenError):
            tokens.user_from_access(forged)
        unsigned = jwt.encode({"sub": "1", "typ": "access", "iss": "lookfind", "iat": 0, "exp": 9999999999}, None, algorithm="none")
        with self.assertRaises(tokens.TokenError):
            tokens.user_from_access(unsigned)


class ProductionEnvTest(unittest.TestCase):
    ENV_FILE = """# comment
FRONTEND_URL=https://lookfind.site
MAIL_FROM="LookFind <a@b.c>"
SMTP_HOST=
DATABASE_HOST=stale-copy.example
JWT_SECRET=abc=def
"""

    def test_parse_env(self):
        self.assertEqual(
            {"FRONTEND_URL": "https://lookfind.site", "MAIL_FROM": "LookFind <a@b.c>", "SMTP_HOST": "",
             "DATABASE_HOST": "stale-copy.example", "JWT_SECRET": "abc=def"},
            config.parse_env(self.ENV_FILE),
        )

    def test_load_app_env_applies_file_but_stack_keys_and_empty_values_do_not_override(self):
        secrets_manager = mock.Mock()
        secrets_manager.get_secret_value.return_value = {"SecretString": self.ENV_FILE}
        env = {"APP_ENV_SECRET_ARN": "arn:secret", "DATABASE_HOST": "live-rds.example",
               "FRONTEND_URL": "http://old", "SMTP_HOST": "smtp.kept"}
        config.load_app_env.cache_clear()
        with mock.patch.dict("os.environ", env, clear=True), mock.patch("boto3.client", return_value=secrets_manager):
            config.load_app_env()
            import os
            self.assertEqual("https://lookfind.site", os.environ["FRONTEND_URL"])  # file wins
            self.assertEqual("live-rds.example", os.environ["DATABASE_HOST"])      # stack wins
            self.assertEqual("smtp.kept", os.environ["SMTP_HOST"])                 # empty skipped
            self.assertEqual("abc=def", os.environ["JWT_SECRET"])
        secrets_manager.get_secret_value.assert_called_once_with(SecretId="arn:secret")
        config.load_app_env.cache_clear()

