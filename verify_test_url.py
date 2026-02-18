import sys
import os
import time

sys.path.append(os.getcwd())

from app.utils import probe_stream_url

urls = [
    "https://live1.sr.se/p1-aac-128",
    "https://live1.sr.se/p3-aac-128",
    "https://nrj.shoutca.st/nrj"
]

print("Starting FINAL Probe Verification...")
for url in urls:
    try:
        start = time.time()
        success, msg = probe_stream_url(url, timeout=5)
        elapsed = time.time() - start
        print(f"URL: {url} -> Success: {success}, Msg: {msg} ({elapsed:.2f}s)")
    except Exception as e:
        print(f"URL: {url} -> CRASHed: {e}")
