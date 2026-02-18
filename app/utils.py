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
    Uses Stage 0 (Socket check) followed by Stage 1 (urllib).
    Forces IPv4 to avoid stalls on broken IPv6 environments.
    """
    import urllib.request
    from urllib.error import URLError, HTTPError
    from urllib.parse import urlparse
    import socket
    import time
    import ssl

    print(f"DEBUG: PROBE START: {url}")

    # STAGE 0: Fast Socket Check (Force IPv4)
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        
        if not host:
            return False, "INVALID URL"
            
        print(f"DEBUG: Stage 0: Checking {host}:{port} (IPv4)")
        # Resolve to IPv4 to avoid broken IPv6 stalls
        addr_info = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        ipv4_addr = addr_info[0][4][0]
        
        with socket.create_connection((ipv4_addr, port), timeout=3.0):
            print(f"DEBUG: Stage 0: Success (Connect OK: {ipv4_addr})")
    except socket.gaierror:
        print(f"DEBUG: Stage 0: DNS FAIL")
        return False, "DNS ERROR"
    except (socket.timeout, ConnectionRefusedError):
        print(f"DEBUG: Stage 0: CONN FAIL/TIMEOUT")
        return False, "TIMEOUT"
    except Exception as e:
        print(f"DEBUG: Stage 0 Warning: {e}")

    # STAGE 1: HTTP Probe
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    headers = {"User-Agent": "TapeDeck/1.0.0"}
    try:
        proxy_handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(proxy_handler)
        req = urllib.request.Request(url, headers=headers)
        
        print(f"DEBUG: Stage 1: Opening {url}")
        # Note: opener.open uses global timeout
        with opener.open(req, timeout=timeout) as response:
            if response.status >= 400:
                print(f"DEBUG: Stage 1: HTTP {response.status}")
                return False, f"HTTP {response.status}"
            
            # Set a strict timeout on the underlying socket for the read operation
            try:
                response.fp.raw._sock.settimeout(3.0)
            except:
                pass
                
            print(f"DEBUG: Stage 1: Reading chunk...")
            chunk = response.read(1024)
            if chunk:
                return True, "WORKS"
                
            return False, "NO DATA"

    except HTTPError as e:
        return False, f"HTTP {e.code}"
    except URLError as e:
        return False, "NET ERROR"
    except socket.timeout:
        return False, "TIMEOUT"
    except Exception as e:
        return False, "ERROR"

def ffprobe_stream_check(url, timeout=10):
    """
    Use ffprobe to verify the stream. Highly reliable for streaming protocols.
    """
    import subprocess
    import shutil
    
    if not shutil.which("ffprobe"):
        return False, "NO FFPROBE"
        
    print(f"DEBUG: STAGE 3: ffprobe check for {url}")
    cmd = [
        "ffprobe", 
        "-v", "quiet", 
        "-print_format", "json",
        "-show_streams",
        "-timeout", str(timeout * 1000000), # ffprobe uses microseconds
        url
    ]
    
    try:
        # Use a shell-less call for speed and safety
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            if data.get("streams"):
                return True, "WORKS"
        return False, "FAIL / NO STREAM"
    except subprocess.TimeoutExpired:
        print(f"DEBUG: ffprobe TIMEOUT for {url}")
        return False, "TIMEOUT"
    except Exception as e:
        print(f"DEBUG: ffprobe ERROR: {e}")
        return False, "ERROR"
