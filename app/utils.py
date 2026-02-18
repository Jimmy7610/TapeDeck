import os
import subprocess
import datetime
import re

def open_output_dir(path):
    """Open folder in Windows Explorer."""
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        os.makedirs(abs_path, exist_ok=True)
    os.startfile(abs_path)

def get_safe_filename(name):
    """Sanitize string for filesystem use."""
    return re.sub(r'[\\/*?:"<>|]', "_", name)

def get_timestamp_str():
    """Return YYYY-MM-DD_HH-MM-SS."""
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def get_hms_str():
    """Return HH:MM:SS."""
    return datetime.datetime.now().strftime("%H:%M:%S")

def format_duration(seconds):
    """Format seconds to +MM:SS or +HH:MM:SS."""
    mm, ss = divmod(int(seconds), 60)
    if mm >= 60:
        hh, mm = divmod(mm, 60)
        return f"+{hh:02}:{mm:02}:{ss:02}"
    return f"+{mm:02}:{ss:02}"

def get_unique_base_name(directory, name_template, extension="aac"):
    """
    Ensure a filename is unique by appending _001, _002 if needed.
    Example: TapeDeck_NRJ_2026-02-17_14-19-50 -> ..._001
    """
    candidate = name_template
    counter = 0
    
    while True:
        path = os.path.join(directory, f"{candidate}.{extension}")
        if not os.path.exists(path):
            return candidate
        
        counter += 1
        candidate = f"{name_template}_{counter:03d}"

def probe_stream_url(url, timeout=5):
    """
    Robustly test if a stream URL is reachable and returning data.
    Uses urllib to follow redirects and read the first few KB.
    Returns (success, message).
    """
    import urllib.request
    from urllib.error import URLError, HTTPError
    import socket
    import time
    import ssl

    # A1: SSL Context (Ignore cert validation for radio streams)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    headers = {"User-Agent": "TapeDeck/1.0.0"}
    try:
        # A2: Disable proxies explicitly to avoid hangs on system config
        proxy_handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(proxy_handler)
        
        req = urllib.request.Request(url, headers=headers)
        
        # B3: Non-blocking attempt to open
        with opener.open(req, timeout=timeout) as response:
            if response.status >= 400:
                print(f"DEBUG: probe_stream_url HTTP {response.status} for {url}")
                return False, f"HTTP {response.status}"
            
            # Read a small chunk (1KB) to confirm data is flowing
            # Radio streams can be slow, we use a slightly longer read timeout here
            chunk = response.read(1024)
            if chunk:
                return True, "WORKS"
            
            # Tiny retry if zero bytes (streaming buffers)
            time.sleep(1.0)
            chunk = response.read(1024)
            if chunk:
                return True, "WORKS"
                
            return False, "NO DATA"

    except HTTPError as e:
        print(f"DEBUG: HTTPError for {url}: {e.code}")
        return False, f"HTTP {e.code}"
    except URLError as e:
        # Handles DNS failures, connection refused, etc.
        reason = str(e.reason)
        print(f"DEBUG: URLError for {url}: {reason}")
        if "getaddrinfo failed" in reason:
            return False, "DNS ERROR"
        return False, "NET ERROR"
    except socket.timeout:
        print(f"DEBUG: Timeout for {url}")
        return False, "TIMEOUT"
    except Exception as e:
        print(f"DEBUG: Exception for {url}: {str(e)}")
        return False, "ERROR"
