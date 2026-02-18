import urllib.request
import re
import html

def fetch_sr_metadata(meta_url):
    """
    Fetches the latest track from SR latlista page.
    Example URL: https://sverigesradio.se/kanaler/latlista/p3
    """
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        req = urllib.request.Request(meta_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
            
        # Look for the first track entry. 
        # SR pages usually have <span class="music-list-item__artist"> and <span class="music-list-item__title">
        # Or in simpler cases, data attributes.
        # We'll use a broad regex for current/latest track.
        
        artist_match = re.search(r'class="music-list-item__artist"[^>]*>([^<]+)</span>', content)
        title_match = re.search(r'class="music-list-item__title"[^>]*>([^<]+)</span>', content)
        
        if artist_match and title_match:
            artist = html.unescape(artist_match.group(1).strip())
            title = html.unescape(title_match.group(1).strip())
            return artist, title
            
        return "Unknown", "—"
    except Exception as e:
        print(f"DEBUG: SR Metadata Fetch Error: {e}")
        return "Unknown", "—"
