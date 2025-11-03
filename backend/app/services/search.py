# backend/app/services/search.py
import httpx
from typing import List, Dict, Any, Optional
import re
from urllib.parse import quote_plus, urlparse
import json

async def search_duckduckgo(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """Search DuckDuckGo for web results (no API key needed)"""
    try:
        # DuckDuckGo HTML search
        search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(search_url, headers=headers)
            response.raise_for_status()
            
            # Parse HTML to extract URLs and titles
            results = []
            html = response.text
            
            # Simple regex to extract links (basic parsing)
            # In production, use BeautifulSoup or similar
            import re
            pattern = r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>'
            matches = re.findall(pattern, html)
            
            for url, title in matches[:max_results]:
                # Clean up URL
                if url.startswith('//duckduckgo.com/l/?'):
                    continue
                results.append({
                    "url": url,
                    "title": title.strip(),
                    "source": "web"
                })
            
            print(f"[Search] DuckDuckGo found {len(results)} results")
            return results
            
    except Exception as e:
        print(f"[Search] DuckDuckGo search failed: {e}")
        return []

async def search_youtube(query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """Search YouTube for video results"""
    try:
        # YouTube search without API (scraping search page)
        search_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(search_url, headers=headers)
            response.raise_for_status()
            
            results = []
            html = response.text
            
            # Extract video IDs from initial data
            pattern = r'"videoId":"([^"]+)"'
            video_ids = re.findall(pattern, html)
            
            # Get unique video IDs
            seen = set()
            for vid_id in video_ids[:max_results * 2]:
                if vid_id not in seen and len(results) < max_results:
                    seen.add(vid_id)
                    results.append({
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                        "title": f"YouTube Video: {query}",
                        "source": "youtube"
                    })
            
            print(f"[Search] YouTube found {len(results)} videos")
            return results
            
    except Exception as e:
        print(f"[Search] YouTube search failed: {e}")
        return []

async def search_wikipedia(query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """Search Wikipedia for relevant articles"""
    try:
        search_url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": query,
            "srlimit": max_results,
            "utf8": 1,
            "origin": "*"
        }
        
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(search_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            results = []
            for item in data.get("query", {}).get("search", []):
                title = item["title"]
                url_title = title.replace(" ", "_")
                results.append({
                    "url": f"https://en.wikipedia.org/wiki/{url_title}",
                    "title": title,
                    "source": "wikipedia"
                })
            
            print(f"[Search] Wikipedia found {len(results)} articles")
            return results
            
    except Exception as e:
        print(f"[Search] Wikipedia search failed: {e}")
        return []

async def search_arxiv(query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """Search arXiv for academic papers"""
    try:
        # arXiv API
        search_url = "http://export.arxiv.org/api/query"
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending"
        }
        
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(search_url, params=params)
            response.raise_for_status()
            
            results = []
            # Parse XML response
            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.text)
            
            # arXiv uses Atom namespace
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            
            for entry in root.findall('atom:entry', ns):
                title_elem = entry.find('atom:title', ns)
                id_elem = entry.find('atom:id', ns)
                
                if title_elem is not None and id_elem is not None:
                    results.append({
                        "url": id_elem.text,
                        "title": title_elem.text.strip().replace('\n', ' '),
                        "source": "arxiv"
                    })
            
            print(f"[Search] arXiv found {len(results)} papers")
            return results
            
    except Exception as e:
        print(f"[Search] arXiv search failed: {e}")
        return []

async def generate_search_urls(query: str, max_sources: int = 12, include_youtube: bool = True) -> List[str]:
    """
    Generate comprehensive list of URLs from multiple sources
    
    Sources:
    - Web search (DuckDuckGo)
    - Wikipedia
    - YouTube (if enabled)
    - arXiv (for academic queries)
    """
    print(f"[Search] Starting comprehensive search for: '{query}'")
    print(f"[Search] Target sources: {max_sources}, Include YouTube: {include_youtube}")
    
    all_results = []
    
    # Determine source distribution based on max_sources
    web_count = max(5, max_sources // 2)
    wiki_count = min(3, max_sources // 4)
    youtube_count = min(2, max_sources // 6) if include_youtube else 0
    arxiv_count = min(2, max_sources // 6)
    
    # Run searches in parallel for speed
    import asyncio
    searches = [
        search_duckduckgo(query, web_count),
        search_wikipedia(query, wiki_count),
        search_arxiv(query, arxiv_count),
    ]
    
    if include_youtube:
        searches.append(search_youtube(query, youtube_count))
    
    results = await asyncio.gather(*searches, return_exceptions=True)
    
    # Combine all results
    for result in results:
        if isinstance(result, list):
            all_results.extend(result)
        elif isinstance(result, Exception):
            print(f"[Search] Search failed: {result}")
    
    # Remove duplicates while preserving order
    seen_urls = set()
    unique_results = []
    for item in all_results:
        url = item.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(item)
    
    # Limit to max_sources
    unique_results = unique_results[:max_sources]
    
    print(f"[Search] Total unique sources found: {len(unique_results)}")
    for i, item in enumerate(unique_results):
        print(f"[Search]   {i+1}. [{item['source']}] {item['title'][:60]}...")
    
    # Return just the URLs
    return [item["url"] for item in unique_results]
