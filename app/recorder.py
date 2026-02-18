import subprocess
import os
import time
import threading

from collections import deque

class TapeRecorder:
    def __init__(self, ffmpeg_path="ffmpeg"):
        self.ffmpeg_path = ffmpeg_path
        self._resolved_path = None
        self.process = None
        self.start_time_monotonic = 0
        self.is_recording = False
        self.stderr_buffer = deque(maxlen=50) # A2: Rolling buffer
        self._stderr_thread = None

    @staticmethod
    def cleanup_orphans():
        """Aggressively kill any orphaned ffmpeg.exe processes from previous TapeDeck sessions."""
        if os.name != 'nt':
            return
            
        import re
        print("DEBUG: Zombicide: Searching for orphaned TapeDeck FFmpeg processes...")
        try:
            # Power-move: Use PowerShell to find PIDs of ffmpeg.exe with 'TapeDeck' in CommandLine
            ps_cmd = 'Get-CimInstance Win32_Process -Filter "Name = \'ffmpeg.exe\' AND CommandLine LIKE \'%TapeDeck%\'" | Select-Object -ExpandProperty ProcessId'
            output = subprocess.check_output(["powershell", "-Command", ps_cmd]).decode('utf-8', errors='replace').strip()
            
            pids = re.findall(r'\d+', output)
            if not pids:
                print("DEBUG: Zombicide: No orphans found.")
                return

            for pid in pids:
                pid_int = int(pid)
                print(f"DEBUG: Zombicide: Terminating orphan PID {pid_int}")
                subprocess.run(f"taskkill /F /PID {pid_int}", shell=True, capture_output=True)
            print("DEBUG: Zombicide: Orphan check complete.")
        except Exception as e:
            # Often occurs if no processes match
            print(f"DEBUG: Zombicide finished (handled).")

    def _resolve_ffmpeg(self):
        import shutil
        from pathlib import Path
        
        # Compute project root based on this file's location (no cwd dependence)
        app_dir = Path(__file__).resolve().parent
        project_root = app_dir.parent
        bin_ffmpeg = project_root / "bin" / "ffmpeg.exe"
        
        print(f"\n--- FFMPEG DISCOVERY DIAGNOSTICS ---")
        print(f"Project Root: {project_root}")
        
        # 1) Try exact path from settings
        if self.ffmpeg_path:
            # If absolute path
            if os.path.isabs(self.ffmpeg_path) and os.path.exists(self.ffmpeg_path):
                self._resolved_path = self.ffmpeg_path
                print(f"Strategy: settings.json (absolute)")
                print(f"Resolved: {self._resolved_path}")
                return True
            
            # If relative path, resolve against project_root
            rel_path = project_root / self.ffmpeg_path
            if rel_path.exists() and rel_path.is_file():
                self._resolved_path = str(rel_path.resolve())
                print(f"Strategy: settings.json (relative to root)")
                print(f"Resolved: {self._resolved_path}")
                return True
        
        # 2) Try shutil.which (System PATH)
        cmd_name = self.ffmpeg_path or "ffmpeg"
        path = shutil.which(cmd_name)
        if path:
            self._resolved_path = path
            print(f"Strategy: PATH (shutil.which)")
            print(f"Resolved: {self._resolved_path}")
            return True
            
        # 3) Portable FALLBACK: project_root/bin/ffmpeg.exe
        if bin_ffmpeg.exists():
            self._resolved_path = str(bin_ffmpeg.resolve())
            print(f"Strategy: bin/ffmpeg.exe (portable fallback)")
            print(f"Resolved: {self._resolved_path}")
            return True
            
        print(f"Strategy: FAILED")
        print(f"HINT: Place ffmpeg.exe in {project_root}\\bin or set ffmpeg_path in settings.json")
        return False

    def start_recording(self, url, output_path, prefer_stream_copy=True, low_latency=True):
        if self.is_recording:
            return False

        if not self._resolve_ffmpeg():
            print(f"ERROR: ffmpeg not found: {self.ffmpeg_path}")
            return False

        # A1: proof-level logging
        print(f"\n--- FFMPEG STARTUP DEBUG ---")
        print(f"PATH: {self._resolved_path}")
        print(f"URL:  {url}")
        print(f"LATENCY: {'LOW' if low_latency else 'NORMAL'}")
        
        self.output_path = output_path
        self.url = url
        self.stderr_buffer.clear()
        
        return self._spawn_ffmpeg(url, output_path, use_copy=prefer_stream_copy, low_latency=low_latency)

    def _is_bauer_stream(self, url):
        """Detect Bauer Media / Sharp Stream URLs that require forced encoding."""
        markers = ["sharp-stream.com", "instreamtest", "aacp"]
        return any(m in url.lower() for m in markers)

    def _spawn_ffmpeg(self, url, output_path, use_copy=True, low_latency=True):
        # Force re-encode for Bauer streams (A1)
        if self._is_bauer_stream(url):
            print("DEBUG: Bauer/NRJ stream detected (sharp-stream/aacp). Forcing re-encode path.")
            use_copy = False

        # B4: User-Agent MUST be before -i
        cmd = [
            self._resolved_path,
            "-y",
            "-hide_banner",
            "-loglevel", "warning",
        ]
        
        if low_latency:
            cmd += ["-flags", "low_delay"]
            
        cmd += [
            "-user_agent", "Mozilla/5.0 (Windows NT 10.0; TapeDeck)",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "2",
            "-rw_timeout", "15000000",
            "-i", url
        ]
        
        if use_copy:
            cmd += ["-c", "copy"]
        else:
            cmd += ["-c:a", "aac", "-b:a", "192k"]
            
        cmd += ["-f", "adts", output_path]
        
        print(f"CMD:  {' '.join(cmd)}")
        print(f"----------------------------\n")

        try:
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # Start stderr capture thread
            self._stderr_thread = threading.Thread(target=self._capture_stderr, daemon=True)
            self._stderr_thread.start()
            
            return True
        except Exception as e:
            print(f"CRITICAL: Failed to spawn ffmpeg: {e}")
            return False

    def _capture_stderr(self):
        try:
            for line in iter(self.process.stderr.readline, b''):
                decoded = line.decode('utf-8', errors='replace').strip()
                if decoded:
                    self.stderr_buffer.append(decoded)
                    # For Bauer streams, log errors aggressively
                    if "Error" in decoded or "failed" in decoded or "403" in decoded:
                         print(f"FFMPEG ERROR: {decoded}")
        except:
            pass

    def check_status(self):
        """Returns (alive, size, stderr_tail) for health monitoring."""
        alive = self.process.poll() is None if self.process else False
        size = 0
        if os.path.exists(self.output_path):
            size = os.path.getsize(self.output_path)
            
        tail = "\n".join(list(self.stderr_buffer)[-5:])
        return alive, size, tail

    def finalize_recording_state(self):
        """Call this only after health checks pass."""
        self.is_recording = True
        self.start_time_monotonic = time.monotonic()

    def stop_recording(self):
        if not self.process:
            self.is_recording = False
            return True

        success = True
        try:
            # 1) Send 'q' to stdin
            if self.process.stdin:
                self.process.stdin.write(b"q\n")
                self.process.stdin.flush()
            
            # 2) Wait up to 2 seconds
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                print("FFMPEG: Hang detected, terminating...")
                # 3) Terminate
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # 4) Kill
                    print("FFMPEG: Kill required...")
                    self.process.kill()
                    success = False
        except Exception as e:
            print(f"ERROR: Stop failed: {e}")
            success = False
        finally:
            self.process = None
            self.is_recording = False
            
        return success

    def get_elapsed_seconds(self):
        if not self.is_recording:
            return 0
        return time.monotonic() - self.start_time_monotonic
