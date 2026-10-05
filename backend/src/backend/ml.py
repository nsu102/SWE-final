"""Street-to-shop embeddings (yainage90).

Query photos (often a person wearing the top) are cropped to the detected top/outer, then embedded
with yainage90/fashion-image-feature-extractor, which was trained on exactly that pairing: garment
crops from user posts vs. product thumbnails. Catalog images are person-free product shots and are
embedded whole, like the thumbnails the model was trained on.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.transforms as v2
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file
from PIL import Image
from transformers import (
    AutoImageProcessor,
    AutoModelForObjectDetection,
    ConditionalDetrConfig,
    SwinConfig,
    SwinModel,
)

from src.backend.config import get_settings
from src.common.human_parser import select_device

DETECTOR = "yainage90/fashion-object-detection"
TOP_LABELS = {"top", "outer"}


@dataclass(frozen=True)
class PreparedImage:
    box_image: Image.Image
    used_top_mask: bool  # a top/outer was detected and the photo was cropped to it
    top_ratio: float  # detected box area / photo area
    masked_image: Image.Image | None = None
    color_lab: tuple[float, float, float] | None = None
    crop_box: tuple[float, float, float, float] | None = None

    @property
    def search_image(self) -> Image.Image:
        return self.box_image


def crop_to_box(image: Image.Image, box: list[float] | None) -> PreparedImage:
    if box is None:
        return PreparedImage(box_image=image, used_top_mask=False, top_ratio=0.0)
    x0, y0, x1, y1 = (max(0.0, box[0]), max(0.0, box[1]), min(image.width, box[2]), min(image.height, box[3]))
    area = (x1 - x0) * (y1 - y0) / (image.width * image.height)
    return PreparedImage(
        box_image=image.crop((round(x0), round(y0), round(x1), round(y1))),
        used_top_mask=True, top_ratio=float(area),
    )


class ImageEncoder(nn.Module):
    def __init__(self, config: SwinConfig) -> None:
        super().__init__()
        self.swin = SwinModel(config)
        self.embedding_layer = nn.Linear(config.hidden_size, 128)

    def forward(self, pixels: torch.Tensor) -> torch.Tensor:
        return F.normalize(self.embedding_layer(self.swin(pixels).pooler_output), p=2, dim=1)


# The checkpoint uses the older transformers Swin parameter names. Loading it through
# PyTorchModelHubMixin silently left 336 of 449 tensors random, so map names and load strictly.
SWIN_RENAMES = [
    (".attention.self.query.", ".attention.q_proj."), (".attention.self.key.", ".attention.k_proj."),
    (".attention.self.value.", ".attention.v_proj."), (".attention.output.dense.", ".attention.o_proj."),
    (".attention.self.relative_position_bias_table",
     ".attention.relative_position_bias.relative_position_bias_table"),
    (".intermediate.dense.", ".mlp.fc1."), (".output.dense.", ".mlp.fc2."),
]


def load_encoder(checkpoint: str, config: SwinConfig) -> ImageEncoder:
    encoder = ImageEncoder(config)
    state = {}
    for key, value in load_file(hf_hub_download(checkpoint, "model.safetensors")).items():
        if key.endswith("relative_position_index"):  # recomputed buffer
            continue
        for old, new in SWIN_RENAMES:
            key = key.replace(old, new)
        state[key] = value
    encoder.load_state_dict(state, strict=True)
    return encoder


class FashionModels:
    def __init__(self) -> None:
        settings = get_settings()
        self.device = select_device()
        self._lock = threading.Lock()
        self.detector_processor = AutoImageProcessor.from_pretrained(DETECTOR)
        # transformers 5.x probes whether the detector's `resnet50` backbone is
        # a Hub repository when backbone_kwargs is present. Runtime is offline,
        # and this detector uses timm, so construct that config explicitly.
        with open(hf_hub_download(DETECTOR, "config.json"), encoding="utf-8") as stream:
            detector_data = json.load(stream)
        detector_data["backbone_kwargs"] = {}
        detector_config = ConditionalDetrConfig.from_dict(detector_data)
        self.detector = AutoModelForObjectDetection.from_pretrained(
            DETECTOR, config=detector_config, local_files_only=True
        ).to(self.device).eval()
        self.labels = self.detector.config.id2label

        config = SwinConfig.from_pretrained(settings.fashion_clip_model)
        processor = AutoImageProcessor.from_pretrained(settings.fashion_clip_model)
        self.encoder = load_encoder(settings.fashion_clip_model, config).to(self.device).eval()
        self.transform = v2.Compose([
            v2.Resize((config.image_size, config.image_size)), v2.ToTensor(),
            v2.Normalize(mean=processor.image_mean, std=processor.image_std),
        ])

    def prepare_query(self, image: Image.Image, threshold: float = 0.4) -> PreparedImage:
        """Crop to the largest detected top/outer; the whole photo when none is found."""
        image = image.convert("RGB")
        with self._lock, torch.inference_mode():
            inputs = self.detector_processor(images=[image], return_tensors="pt").to(self.device)
            result = self.detector_processor.post_process_object_detection(
                self.detector(**inputs), threshold=threshold,
                target_sizes=torch.tensor([[image.height, image.width]]),
            )[0]
        boxes = [box.tolist() for label, box in zip(result["labels"], result["boxes"])
                 if self.labels[int(label)] in TOP_LABELS]
        largest = max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1])) if boxes else None
        return crop_to_box(image, largest)

    def embed(self, images: list[Image.Image]) -> np.ndarray:
        with self._lock, torch.inference_mode():
            pixels = torch.stack([self.transform(image.convert("RGB")) for image in images]).to(self.device)
            features = self.encoder(pixels)
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
