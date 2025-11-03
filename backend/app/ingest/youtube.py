# backend/app/ingest/youtube.py
import yt_dlp
import whisper
from typing import Optional, Dict, Any
import tempfile
import os

def extract_youtube_transcript(url: str) -> Optional[Dict[str, Any]]:
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "format": "worstaudio/worst",
            "outtmpl": "%(id)s.%(ext)s",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("title") or "YouTube Video"
            # Prefer native captions, otherwise download audio and transcribe
            if info.get("automatic_captions") or info.get("subtitles"):
                sub = ydl.extract_info(url, download=False)["subtitles"]
                # naive: pick first available language (can be refined)
                for lang, captions in (sub or {}).items():
                    if captions:
                        caption_url = captions[0]["url"]
                        import httpx
                        text = httpx.get(caption_url).text
                        # Strip XML tags if present
                        import re
                        clean = re.sub(r"<[^>]+>", "", text)
                        return {"text": clean, "title": title, "url": url, "kind": "youtube"}
            # Fallback: download audio and Whisper
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                ydl_opts["outtmpl"] = tmp.name.replace(".wav", ".%(ext)s")
                ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}]
                with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                    ydl2.download([url])
            model = whisper.load_model("base")
            result = model.transcribe(tmp.name)
            os.unlink(tmp.name)
            return {"text": result["text"], "title": title, "url": url, "kind": "youtube"}
    except Exception:
        return None
