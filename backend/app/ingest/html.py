# backend/app/ingest/html.py
import trafilatura
from trafilatura.settings import use_config
from urllib.parse import urlparse
from typing import Optional, Dict, Any

def extract_html(html: str, url: str) -> Optional[Dict[str, Any]]:
    try:
        config = use_config()
        config.set("DEFAULT", "EXTRACTION_TIMEOUT", "10")
        downloaded = trafilatura.utils.load_html(html)
        result = trafilatura.extract(downloaded, config=config, include_images=False, include_tables=True, favor_precision=True, include_formatting=True)
        if not result:
            return None
        title = trafilatura.extract(downloaded, config=config, include_images=False, include_tables=False, favor_precision=False, output_format="txt", only_with_metadata=False).splitlines()[0] if trafilatura.extract(downloaded, config=config, include_images=False, include_tables=False, favor_precision=False, output_format="txt", only_with_metadata=False) else urlparse(url).netloc
        return {"text": result, "title": title, "url": url, "kind": "web"}
    except Exception:
        return None
