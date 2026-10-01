from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
import open_clip
from transformers import AutoImageProcessor, SegformerForSemanticSegmentation

from src.backend.config import get_settings
from src.common.human_parser import label_ids_for_tops, select_device


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB uint8 pixels (N, 3) -> CIE Lab (D65)."""
    c = rgb.astype(np.float32) / 255
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ np.array(
        [[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]],
        dtype=np.float32,
    ).T / np.array([0.95047, 1.0, 1.08883], dtype=np.float32)
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack(
        [116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], axis=1
    )


def garment_color(image: Image.Image, mask: np.ndarray) -> tuple[float, float, float]:
    """Median Lab colour of the garment pixels (median ignores small prints/shadows)."""
    pixels = np.asarray(image.convert("RGB"))[mask]
    if len(pixels) > 20_000:
        pixels = pixels[:: len(pixels) // 20_000]
    lab = np.median(rgb_to_lab(pixels), axis=0)
    return float(lab[0]), float(lab[1]), float(lab[2])


@dataclass(frozen=True)
class PreparedImage:
    box_image: Image.Image
    masked_image: Image.Image | None
    used_top_mask: bool
    top_ratio: float
    color_lab: tuple[float, float, float] | None = None
    # Garment box as fractions of width/height (x0, y0, x1, y1), for display crops.
    crop_box: tuple[float, float, float, float] | None = None

    @property
    def search_image(self) -> Image.Image:
        """Garment only (person/background painted grey) when a top was found."""
        return self.masked_image if self.masked_image is not None else self.box_image


def prepare_query_views(
    image: Image.Image, mask: np.ndarray, min_top_ratio: float = 0.015
) -> PreparedImage:
    image = image.convert("RGB")
    ratio = float(mask.mean())
    if ratio < min_top_ratio:
        return PreparedImage(
            box_image=image, masked_image=None, used_top_mask=False, top_ratio=ratio
        )

    ys, xs = np.nonzero(mask)
    left, right = int(xs.min()), int(xs.max()) + 1
    top, bottom = int(ys.min()), int(ys.max()) + 1
    pad_x = round((right - left) * 0.08)
    pad_y = round((bottom - top) * 0.08)
    box = (
        max(0, left - pad_x), max(0, top - pad_y),
        min(image.width, right + pad_x), min(image.height, bottom + pad_y),
    )
    neutral = Image.new("RGB", image.size, (217, 217, 217))
    neutral.paste(image, mask=Image.fromarray((mask * 255).astype(np.uint8), mode="L"))
    return PreparedImage(
        box_image=image.crop(box),
        masked_image=neutral.crop(box),
        used_top_mask=True,
        top_ratio=ratio,
        color_lab=garment_color(image, mask),
        crop_box=(
            box[0] / image.width, box[1] / image.height,
            box[2] / image.width, box[3] / image.height,
        ),
    )


class FashionModels:
    def __init__(self) -> None:
        settings = get_settings()
        self.device = select_device()
        self._lock = threading.Lock()
        # marqo-fashionSigLIP is an open_clip checkpoint. Loading it via transformers
        # AutoModel(trust_remote_code) hits a meta-tensor bug in this transformers version,
        # so use open_clip directly (Marqo's documented path). image-only: no tokenizer.
        clip_model, _, clip_preprocess = open_clip.create_model_and_transforms(
            f"hf-hub:{settings.fashion_clip_model}"
        )
        self.clip_model = clip_model.to(self.device).eval()
        self.clip_preprocess = clip_preprocess
        self.human_parser_model = settings.human_parser_model
        self.parser_processor: AutoImageProcessor | None = None
        self.parser_model: SegformerForSemanticSegmentation | None = None
        self.top_ids: list[int] | None = None

    def _ensure_parser(self) -> None:
        if self.parser_model is not None:
            return
        self.parser_processor = AutoImageProcessor.from_pretrained(self.human_parser_model)
        self.parser_model = SegformerForSemanticSegmentation.from_pretrained(
            self.human_parser_model
        ).to(self.device).eval()
        self.top_ids, _ = label_ids_for_tops(self.parser_model.config.id2label)

    def prepare_query(self, image: Image.Image, min_top_ratio: float = 0.015) -> PreparedImage:
        image = image.convert("RGB")
        with self._lock:
            self._ensure_parser()
        assert self.parser_processor is not None
        assert self.parser_model is not None
        assert self.top_ids is not None
        with self._lock, torch.inference_mode():
            inputs = self.parser_processor(images=image, return_tensors="pt")
            inputs = {key: value.to(self.device) for key, value in inputs.items()}
            # Upsample on CPU: per-image output sizes would make MPS build a new graph every call.
            logits = self.parser_model(**inputs).logits.float().cpu()
            logits = F.interpolate(
                logits, size=(image.height, image.width), mode="bilinear", align_corners=False
            )
            prediction = logits.argmax(dim=1)[0].cpu().numpy()
        mask = np.isin(prediction, self.top_ids)
        return prepare_query_views(image, mask, min_top_ratio)

    def embed(self, images: list[Image.Image]) -> np.ndarray:
        with self._lock, torch.inference_mode():
            pixel_values = torch.stack(
                [self.clip_preprocess(image.convert("RGB")) for image in images]
            ).to(self.device)
            features = self.clip_model.encode_image(pixel_values)
            features = F.normalize(features, p=2, dim=-1)
        return features.cpu().numpy().astype(np.float32)


_models: FashionModels | None = None
_models_lock = threading.Lock()


def get_models() -> FashionModels:
    global _models
    if _models is None:
        with _models_lock:
            if _models is None:
                _models = FashionModels()
    return _models
