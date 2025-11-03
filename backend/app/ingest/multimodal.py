# backend/app/ingest/multimodal.py
import torch
from transformers import BlipProcessor, BlipForConditionalGeneration
from PIL import Image
import requests
from typing import Optional, Dict, Any
import tempfile
import os

# Lazy-load BLIP-2 to avoid startup overhead
_blip_model = None
_blip_processor = None

def load_blip():
    global _blip_model, _blip_processor
    if _blip_model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _blip_processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
        _blip_model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base").to(device)
    return _blip_model, _blip_processor, device

def caption_image(image_path: str, url: str) -> Optional[Dict[str, Any]]:
    try:
        model, processor, device = load_blip()
        image = Image.open(image_path).convert("RGB")
        inputs = processor(image, return_tensors="pt").to(device)
        out = model.generate(**inputs, max_length=50)
        caption = processor.decode(out[0], skip_special_tokens=True)
        return {"caption": caption, "title": os.path.basename(image_path), "url": url, "kind": "figure_caption"}
    except Exception:
        return None
