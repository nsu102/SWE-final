import os

from huggingface_hub import hf_hub_download
from transformers import AutoImageProcessor, AutoModelForObjectDetection, SwinConfig

detector = "yainage90/fashion-object-detection"
encoder = os.getenv("FASHION_CLIP_MODEL", "yainage90/fashion-image-feature-extractor")
AutoImageProcessor.from_pretrained(detector)
AutoModelForObjectDetection.from_pretrained(detector)
SwinConfig.from_pretrained(encoder)
AutoImageProcessor.from_pretrained(encoder)
hf_hub_download(encoder, "model.safetensors")
