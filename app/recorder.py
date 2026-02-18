import subprocess
import os
import time
import threading

from collections import deque

from .state import RecorderState

class TapeRecorder:
    def __init__(self, ffmpeg_path="ffmpeg"):
        self.ffmpeg_path = ffmpeg_path
        self._resolved_path = None
        self.process = None
        self.start_time_monotonic = 0
        self.state = RecorderState.IDLE
        self.stderr_buffer = deque(maxlen=50) 
        self._stderr_thread = None
        self.output_path = None

    @property
    def is_recording(self):
        return self.state == RecorderState.RECORDING

    @staticmethod
    def cleanup_orphans():
        """Aggressively kill any orphaned ffmpeg.exe processes from previous TapeDeck sessions."""
        if os.name != 'nt':
            return
            
        import re
        try:
            # Power-move: Use PowerShell to find PIDs of ffmpeg.exe with 'TapeDeck' in CommandLine
            ps_cmd = 'Get-CimInstance Win32_Process -Filter "Name = \'ffmpeg.exe\' AND CommandLine LIKE \'%TapeDeck%\'" | Select-Object -ExpandProperty ProcessId'
            output = subprocess.check_output(["powershell", "-Command", ps_cmd]).decode('utf-8', errors='replace').strip()
            
            pids = re.findall(r'\d+', output)
            if not pids:
                return

            for pid in pids:
                pid_int = int(pid)
                print(f"DEBUG: Zombicide: Terminating orphan PID {pid_int}")
                subprocess.run(f"taskkill /F /PID {pid_int}", shell=True, capture_output=True)
        except:
            pass

    def _resolve_ffmpeg(self):
        import shutil
        from pathlib import Path
        
        # Compute project root based on this file's location (no cwd dependence)
        app_dir = Path(__file__).resolve().parent
        project_root = app_dir.parent
        bin_ffmpeg = project_root / "bin" / "ffmpeg.exe"
        
        # 1) Try exact path from settings
        if self.ffmpeg_path:
            # If absolute path
            if os.path.isabs(self.ffmpeg_path) and os.path.exists(self.ffmpeg_path):
                self._resolved_path = self.ffmpeg_path
                return True
            
            # If relative path, resolve against project_root
            rel_path = project_root / self.ffmpeg_path
            if rel_path.exists() and rel_path.is_file():
                self._resolved_path = str(rel_path.resolve())
                return True
        
        # 2) Try shutil.which (System PATH)
        cmd_name = self.ffmpeg_path or "ffmpeg"
        path = shutil.which(cmd_name)
        if path:
            self._resolved_path = path
            return True
            
        # 3) Portable FALLBACK: project_root/bin/ffmpeg.exe
        if bin_ffmpeg.exists():
            self._resolved_path = str(bin_ffmpeg.resolve())
            return True
            
        return False

    def is_available(self):
        """Checks if ffmpeg is found and executable."""
        return self._resolve_ffmpeg()

    def start_recording(self, url, output_path, prefer_stream_copy=True, low_latency=True):
        if self.state != RecorderState.IDLE:
            return False

        if not self._resolve_ffmpeg():
            print(f"ERROR: ffmpeg not found: {self.ffmpeg_path}")
            self.state = RecorderState.ERROR
            return False

        # A1: proof-level logging
        print(f"\n--- FFMPEG STARTUP DEBUG ---")
        print(f"PATH: {self._resolved_path}")
        print(f"URL:  {url}")
        print(f"LATENCY: {'LOW' if low_latency else 'NORMAL'}")
        
        self.state = RecorderState.STARTING
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
            self.state = RecorderState.ERROR
            return False

    def _capture_stderr(self):
        try:
            for line in iter(self.process.stderr.readline, b''):
                if not line: break
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
        
        # If process died unexpectedly while we thought we were recording
        if not alive and self.state == RecorderState.RECORDING:
            print(f"DEBUG: Recorder detected process death (State={self.state})")
            # Don't reset state here, let the controller handle it via check_status
            
        size = 0
        if self.output_path and os.path.exists(self.output_path):
            size = os.path.getsize(self.output_path)
            
        tail = "\n".join(list(self.stderr_buffer)[-5:])
        return alive, size, tail

    def finalize_recording_state(self):
        """Promote state to RECORDING after health checks pass."""
        if self.state == RecorderState.STARTING:
            self.state = RecorderState.RECORDING
            self.start_time_monotonic = time.monotonic()

    def stop_recording(self):
        """Atomic stop and reset to IDLE."""
        if self.state == RecorderState.IDLE:
            return True

        self.state = RecorderState.STOPPING
        success = True
        
        if self.process:
            try:
                # 1) Send 'q' to stdin
                if self.process.stdin:
                    try:
                        self.process.stdin.write(b"q\n")
                        self.process.stdin.flush()
                    except:
                        pass
                
                # 2) Wait up to 2 seconds
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        success = False
            except Exception as e:
                print(f"ERROR: Stop failed: {e}")
                success = False
            finally:
                self.process = None
        
        self.state = RecorderState.IDLE
        self.start_time_monotonic = 0
        return success

    def get_elapsed_seconds(self):
        if self.state != RecorderState.RECORDING:
            return 0
        return time.monotonic() - self.start_time_monotonic
