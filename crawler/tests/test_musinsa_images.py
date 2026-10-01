import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import numpy as np

from src.musinsa.select_images import ProductUnavailable, load_completed, small_variant, analysis_views, mask_border_ratio, parse_gallery_urls, save_result


class DetailParserTest(unittest.TestCase):
    def test_extracts_thumbnail_and_detail_images_in_order(self):
        document = {
            "props": {"pageProps": {"meta": {"data": {"goodsImages": [
                {"imageUrl": "/images/detail-1.jpg"},
                {"imageUrl": "https://image.msscdn.net/images/detail-2.jpg"},
            ], "goodsContents": '<img src="//image.msscdn.net/images/detail-3.jpg">'}}}}
        }
        html = (
            b'<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(document).encode()
            + b"</script>"
        )
        gallery = [
            "https://image.msscdn.net/images/main.jpg",
            "https://image.msscdn.net/images/detail-1.jpg",
            "https://image.msscdn.net/images/detail-2.jpg",
        ]
        # Default: thumbnail + top gallery only; the 상품정보 (goodsContents) images are skipped.
        self.assertEqual(gallery, parse_gallery_urls(html, "https://image.msscdn.net/images/main.jpg"))

    def test_unavailable_product_is_reported_not_crashing(self):
        document = {"props": {"pageProps": {"meta": {
            "meta": {"result": "FAIL", "errorCode": "DISPLAY_000_0006", "message": "invalid"},
            "data": None, "error": None,
        }}}}
        html = (
            b'<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(document).encode()
            + b"</script>"
        )
        with self.assertRaises(ProductUnavailable):
            parse_gallery_urls(html, None)

    def test_deduplicates_urls(self):
        document = {"props": {"pageProps": {"meta": {"data": {"goodsImages": [
            {"imageUrl": "/images/main.jpg"}
        ]}}}}}
        html = (
            b'<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(document).encode()
            + b"</script>"
        )
        self.assertEqual(
            ["https://image.msscdn.net/images/main.jpg"],
            parse_gallery_urls(html, "https://image.msscdn.net/images/main.jpg"),
        )

    def test_overwrite_upserts_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "selections.jsonl"
            save_result(path, {"goods_no": "1", "selected_index": 0}, False)
            save_result(path, {"goods_no": "2", "selected_index": 0}, False)
            save_result(path, {"goods_no": "1", "selected_index": 7}, True)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(2, len(rows))
            self.assertEqual(7, next(row for row in rows if row["goods_no"] == "1")["selected_index"])

    def test_splits_very_tall_detail_image(self):
        image = Image.new("RGB", (100, 1000))
        views = analysis_views(image)
        self.assertGreater(len(views), 1)
        self.assertEqual((100, 150), views[0][0].size)
        self.assertEqual((0, 850, 100, 1000), views[-1][1])

    def test_penalizes_garment_mask_touching_crop_edges(self):
        centered = np.zeros((100, 100), dtype=bool)
        centered[20:80, 20:80] = True
        clipped = np.zeros((100, 100), dtype=bool)
        clipped[:, 20:80] = True
        self.assertLess(mask_border_ratio(centered), mask_border_ratio(clipped))

    def test_load_completed_retries_exclusions_caused_by_download_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "selections.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in [
                {"goods_no": "1", "status": "selected", "checked_images": [{"error": "timeout"}]},
                {"goods_no": "2", "status": "excluded", "checked_images": [{"top_ratio": 0.0}]},
                {"goods_no": "3", "status": "excluded", "checked_images": [{"error": "reset"}]},
                {"goods_no": "4", "status": "excluded", "checked_images": [{"error": "reset"}]},
                {"goods_no": "4", "status": "selected", "checked_images": []},
            ]) + "\n")
            self.assertEqual({"1", "2", "4"}, load_completed(path))

    def test_small_variant_only_rewrites_musinsa_500_images(self):
        self.assertEqual(
            "https://image.msscdn.net/images/goods_img/1/1_123_320.jpg",
            small_variant("https://image.msscdn.net/images/goods_img/1/1_123_500.jpg"),
        )
        external = "https://example.com/detail/8d404de4.jpg"
        self.assertEqual(external, small_variant(external))


if __name__ == "__main__":
    unittest.main()
