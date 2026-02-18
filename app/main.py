import sys
import json
import os
import time
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import QTimer, QObject

from .ui_main import TapeDeckUI
from .player import RadioPlayer
from .recorder import TapeRecorder
from .logger import TapeLogger
from .utils import get_timestamp_str, get_hms_str, format_duration
from .state import PlayerState, RecorderState

class TapeDeckApp(QObject):
    def __init__(self):
        super().__init__()
        self.load_config()
        
        self.player = RadioPlayer()
        self.recorder = TapeRecorder(self.settings.get("ffmpeg_path", "ffmpeg"))
        self.logger = None
        
        self.ui = TapeDeckUI(self.settings, self.channels)
        
        self.last_track_key = None
        self.current_artist = "Unknown"
        self.current_title = "—"
        
        self.on_air_intent = False
        self.reconnect_retry_count = 0
        
        # Metadata fallback tracking
        self.unknown_count = 0
        self.last_provider_poll = 0
        self.debug_window_active = False
        self.latency_estimate = 0.0
        
        self.init_app()

    def load_config(self):
        try:
            with open("app/settings.json", "r") as f:
                self.settings = json.load(f)
            with open("app/channels.json", "r") as f:
                self.channels = json.load(f)
        except Exception as e:
            print(f"Config load error: {e}")
            self.settings = {"metadata_poll_ms": 1000, "default_channel": "P3"}
            self.channels = {"channels": []}

    def init_app(self):
        # Reconnect Timer
        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.setSingleShot(True)
        self.reconnect_timer.timeout.connect(self._reconnect_attempt)
        
        # Signals
        self.ui.btn_on_air.clicked.connect(self.handle_on_air)
        self.ui.btn_rec.clicked.connect(self.handle_rec)
        self.ui.btn_manage_channels.clicked.connect(self.handle_manage_channels)
        self.ui.channel_selected.connect(self.handle_channel_change)
        self.ui.open_folder_clicked.connect(self.handle_open_folder)
        self.ui.restart_clicked.connect(self.handle_restart)
        self.ui.power_clicked.connect(self.ui.close)
        
        # Override Close Event on the UI window
        self.ui.closeEvent = self._handle_window_close
        
        # A2: Zombicide (Cleanup orphans on startup)
        self.recorder.cleanup_orphans()
        
        # Metadata Polling
        self.meta_timer = QTimer(self)
        self.meta_timer.timeout.connect(self.poll_metadata)
        self.meta_timer.start(self.settings.get("metadata_poll_ms", 1000))
        
        # Status Monitoring Timer
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.poll_vlc_status)
        self.status_timer.start(500)
        
        # Phase 3: UX Hardening - Check ffmpeg
        if not self.recorder.is_available():
            print("CRITICAL: FFmpeg not found. REC functionality will be disabled.")
            self.ui.btn_rec.setEnabled(False)
            self.ui.set_status("FFmpeg missing: REC disabled", error=True)

        # B2: Debounce for confirmed loss
        self.lost_candidate_timer = QTimer(self)
        self.lost_candidate_timer.setSingleShot(True)
        self.lost_candidate_timer.timeout.connect(self._confirm_stream_lost)

    def handle_on_air(self, checked):
        self.on_air_intent = checked
        if checked:
            self.reconnect_retry_count = 0
            self.debug_window_active = True
            QTimer.singleShot(5000, self._stop_debug_window)
            self._start_playback()
        else:
            if self.recorder.is_recording:
                self.handle_rec(False)
            self.reconnect_timer.stop()
            self.player.stop()
            self.ui.set_status("Idle")
            self.ui.set_on_air(False)

    def _start_playback(self):
        url = self.get_current_url()
        if not url:
            self.ui.set_status("No URL", error=True)
            self.ui.set_on_air(False)
            return

        from .utils import get_timestamp_str
        print(f"[{get_timestamp_str()}] DEBUG: Playing channel: {self.ui.current_channel} URL: {url}")

        options = []
        if self.player._is_bauer_stream(url):
            # Bauer streams require a User-Agent or they might 403/drop
            options.append(":http-user-agent=Mozilla/5.0 (Windows NT 10.0; TapeDeck)")
            
        # A2: Apply network caching
        cache_ms = self.settings.get("network_cache_ms", 1500)
        options.append(f":network-caching={cache_ms}")
        options.append(f":live-caching={cache_ms}")
            
        self.player.play(url, options=options)
        self.ui.set_status("Connecting...")

    def _reconnect_attempt(self):
        if not self.on_air_intent:
            return
        print(f"DEBUG: Reconnect attempt {self.reconnect_retry_count + 1}")
        self._start_playback()

    def poll_vlc_status(self):
        # 1. Recorder Truth-Sync & Watchdog
        recorder_state = self.recorder.state
        is_rec_running = self.recorder.is_recording
        
        if is_rec_running:
            alive, size, tail = self.recorder.check_status()
            if not alive:
                print(f"DEBUG: Watchdog: FFmpeg crash detected! State: {recorder_state.name}. Tail: {tail}")
                if self.logger:
                    self.logger.log_event("CRASH", f"FFmpeg exited unexpectedly. Tail: {tail[:100]}", rec_seconds=self.recorder.get_elapsed_seconds())
                self._handle_rec_fail(self.settings.get("prefer_stream_copy", True))
            else:
                secs = self.recorder.get_elapsed_seconds()
                self.ui.update_rec_timer(format_duration(secs))
        else:
            self.ui.update_rec_timer("00:00:00")
            
        # REC Truth Guard: ensure UI button matches recorder state machine
        if self.ui.btn_rec.isChecked() != is_rec_running:
            # We allow a brief desync only during STARTING or STOPPED states
            if recorder_state not in [RecorderState.STARTING, RecorderState.STOPPING]:
                print(f"DEBUG: Syncing UI REC state to {is_rec_running} (Backend: {recorder_state.name})")
                self.ui.set_rec_state(is_rec_running)

        # 2. Player ON AIR Sync
        player_state = self.player.get_state()
        
        if not self.on_air_intent:
            if player_state in [PlayerState.OPENING, PlayerState.BUFFERING, PlayerState.PLAYING]:
                self.player.stop()
            self.ui.set_status("Idle")
            self.ui.set_on_air(False)
            self.lost_candidate_timer.stop()
            return

        # User intent is ON
        self.ui.set_on_air(True)

        if player_state == PlayerState.PLAYING:
            self.ui.set_status("Playing")
            self.reconnect_retry_count = 0
            self.lost_candidate_timer.stop()
            
            # Re-enforce audio settings
            if self.player.player.audio_get_mute():
                self.player.player.audio_set_mute(False)
            
            cur_vol = self.player.player.audio_get_volume()
            if cur_vol != 80 and cur_vol != -1:
                self.player.player.audio_set_volume(80)

            if self.reconnect_timer.isActive():
                self.reconnect_timer.stop()
        
        if player_state == PlayerState.OPENING:
            self.ui.set_status("Opening...")
            self.lost_candidate_timer.stop()
        elif player_state == PlayerState.BUFFERING:
            self.ui.set_status("Buffering...")
            self.lost_candidate_timer.stop()
        elif player_state == PlayerState.PAUSED:
            self.ui.set_status("Playing")
            self.lost_candidate_timer.stop()
        elif player_state in [PlayerState.NOTHING_SPECIAL, PlayerState.STOPPED, PlayerState.ENDED, PlayerState.ERROR]:
            if not self.lost_candidate_timer.isActive() and not self.reconnect_timer.isActive():
                self.ui.set_status("Connecting...", error=False)
                self.lost_candidate_timer.start(1200)
            elif self.reconnect_timer.isActive():
                self.ui.set_status("STREAM LOST", error=True)


    def _confirm_stream_lost(self):
        if not self.on_air_intent:
            return
            
        player_state = self.player.get_state()
        if player_state in [PlayerState.STOPPED, PlayerState.ENDED, PlayerState.ERROR]:
            print(f"DEBUG: Stream loss confirmed (state={player_state.name}).")
            self.ui.set_status("STREAM LOST", error=True)
            
            if not self.reconnect_timer.isActive():
                # Exponential backoff: 1s, 2s, 5s, 10s
                backoff = [1, 2, 5, 10]
                idx = min(self.reconnect_retry_count, len(backoff) - 1)
                delay = backoff[idx]
                print(f"DEBUG: Reconnect attempt in {delay}s")
                self.reconnect_timer.start(delay * 1000)
                self.reconnect_retry_count += 1

    def _stop_debug_window(self):
        self.debug_window_active = False
        print("DEBUG: 5-second debug window closed.")

    def handle_manage_channels(self):
        from .ui_main import ChannelManagerDialog
        dialog = ChannelManagerDialog(self.channels, parent=self.ui)
        dialog.test_url_requested.connect(self.handle_test_url)
        self.test_dialog = dialog # Keep ref for test results
        
        if dialog.exec() == QDialog.Accepted:
            self.channels = dialog.channels
            # Persist to file
            try:
                import json
                with open("app/channels.json", "w") as f:
                    json.dump(self.channels, f, indent=2)
                self.ui.refresh_channels(self.channels)
                self.ui.set_status("Channels saved")
            except Exception as e:
                print(f"ERROR: Failed to save channels: {e}")
                self.ui.set_status("Save failed", error=True)

    def handle_test_url(self, url):
        from .utils import probe_stream_url
        import threading
        
        print(f"DEBUG: Testing URL: {url}")
        if self.test_dialog:
            self.test_dialog.lbl_test_result.setText("TESTING...")
            self.test_dialog.lbl_test_result.setStyleSheet("color: #ffa000;")

        def worker():
            # Stage 1: Fast HTTP Probe
            success, msg = probe_stream_url(url)
            
            # Stage 2: VLC Fallback (if HTTP probe yields NET ERROR or specific failures)
            if not success:
                print(f"DEBUG: HTTP probe failed ({msg}), trying VLC fallback...")
                success, msg = self._vlc_probe_fallback(url)
                
            # Jump back to UI thread to report results
            QTimer.singleShot(0, lambda: self._report_test_result(success, msg))
            
        threading.Thread(target=worker, daemon=True).start()

    def _vlc_probe_fallback(self, url):
        """Headless VLC probe to match real-world playability."""
        from .player import RadioPlayer
        from .state import PlayerState
        import time
        
        try:
            # We use a dedicated local player for probing to avoid interfering with current playback
            probe_player = RadioPlayer()
            if not probe_player.is_initialized():
                return False, "VLC INIT ERR"
            
            probe_player.play(url)
            probe_player.player.audio_set_mute(True)
            
            # Poll for up to 4 seconds
            for _ in range(40):
                time.sleep(0.1)
                st = probe_player.get_state()
                if st == PlayerState.PLAYING:
                    probe_player.stop()
                    return True, "WORKS"
                if st == PlayerState.ERROR:
                    break
                    
            probe_player.stop()
            return False, "TIMEOUT / ERR"
        except Exception as e:
            print(f"DEBUG: VLC probe fallback crashed: {e}")
            return False, "PROBE ERR"

    def _report_test_result(self, success, msg):
        if self.test_dialog:
            self.test_dialog.set_test_result(success, msg)

    def handle_rec(self, checked):
        # 1. Truth Sync Guard: If we are already in the target state, do nothing
        if checked == self.recorder.is_recording:
            return

        if checked:
            if not self.ui.btn_on_air.isChecked():
                self.ui.set_rec_state(False)
                self.ui.set_status("Must be ON AIR to record", error=True)
                return

            if not self.player.is_playing():
                self.ui.set_rec_state(False)
                self.ui.set_status("Must be ON AIR to record", error=True)
                return
            
            # Instant UI toggle (Optimistic)
            self.ui.set_rec_state(True)
            self._start_recording_attempt(prefer_copy=self.settings.get("prefer_stream_copy", True))
        else:
            # Atomic stop
            self.ui.set_rec_state(False)
            self._stop_recording_sync()

    def _stop_recording_sync(self):
        if self.recorder.state in [RecorderState.RECORDING, RecorderState.STARTING]:
            track_info = f"{self.current_artist} — {self.current_title}"
            if self.logger:
                self.logger.log_event("END", track_info, rec_seconds=self.recorder.get_elapsed_seconds(), suffix="stopped by user")
            
            success = self.recorder.stop_recording()
            if not success:
                self.ui.set_status("FFMPEG ERROR: stop failed", error=True)
            else:
                self.ui.set_status("Playing" if self.player.is_playing() else "Idle")

    def _start_recording_attempt(self, prefer_copy=True):
        from pathlib import Path
        channel_name = self.ui.current_channel
        ts = get_timestamp_str()
        base_template = f"TapeDeck_{channel_name}_{ts}"
        
        # A1: Normalize output_path to absolute (no cwd dependence)
        app_dir = Path(__file__).resolve().parent
        project_root = app_dir.parent
        output_dir_rel = self.settings.get("output_dir", "../recordings")
        output_dir = (project_root / output_dir_rel).resolve()
        
        if not output_dir.exists():
            output_dir.mkdir(parents=True, exist_ok=True)
            
        ext = self.settings.get("record_container_ext", "aac")
        
        # A1: Get unique filename (suffixes _001, _002 if needed)
        from .utils import get_unique_base_name
        base_name = get_unique_base_name(str(output_dir), base_template, extension=ext)
        
        rec_path = str(output_dir / f"{base_name}.{ext}")
        self._temp_log_path = str(output_dir / f"{base_name}_rec.txt")
        
        url = self.get_current_url()
        self.ui.set_status("Starting REC...")
        
        low_latency = self.settings.get("low_latency_mode", True)
        spawned = self.recorder.start_recording(url, rec_path, 
                                               prefer_stream_copy=prefer_copy,
                                               low_latency=low_latency)
        
        if spawned:
            # Optimistic UI: show REC state immediately
            self.ui.set_rec_state(True)
            self.ui.set_status("REC Starting...")
            # A3: Loosen health check timings (Total ~3.0s-4.0s)
            self._rec_check_count = 0
            self._rec_last_size = -1
            self._rec_check_prefer_copy = prefer_copy
            QTimer.singleShot(1500, self._perform_rec_health_check)
        else:
            self.ui.set_rec_state(False)
            if not self.recorder._resolved_path:
                self.ui.set_status("FFMPEG ERROR: not found", error=True)
                print("HINT: Place ffmpeg.exe in TapeDeck/bin or set ffmpeg_path in settings.json")
            else:
                self.ui.set_status("FFMPEG ERROR: spawn failed", error=True)

    def _perform_rec_health_check(self):
        self._rec_check_count += 1
        alive, size, tail = self.recorder.check_status()
        print(f"DEBUG: Health check {self._rec_check_count}/4 - Size: {size}")
        
        if not alive:
            print(f"DEBUG: Health check {self._rec_check_count} failed: CPU exited. Tail: {tail}")
            self._handle_rec_fail(self._rec_check_prefer_copy)
            return

        # A3: Loosen health check to 4 steps / 1.5s (Total ~6.0s)
        if size == 0 and self._rec_check_count == 4:
            print(f"DEBUG: Health check 4 failed: File is still 0 bytes. Tail: {tail}")
            self._handle_rec_fail(self._rec_check_prefer_copy)
            return

        self._rec_last_size = size
        
        if self._rec_check_count < 4:
            # Continue checking - interval 1.5s for robustness
            QTimer.singleShot(1500, self._perform_rec_health_check)
        else:
            # Success! (B5/D9)
            print(f"DEBUG: Health check PASSED (final size={size})")
            self.recorder.finalize_recording_state()
            self._activate_recording(self._temp_log_path)

    def _handle_rec_fail(self, was_copy):
        self.recorder.stop_recording()
        if was_copy:
            print("DEBUG: Retrying with forced re-encode path...")
            self._start_recording_attempt(prefer_copy=False)
        else:
            self.ui.set_rec_state(False)
            self.ui.set_status("FFMPEG ERROR", error=True)

    def _activate_recording(self, log_path):
        self.logger = TapeLogger(log_path, ui_callback=self.ui.append_rec_log)
        # UI already showing REC from optimistic state
        self.ui.set_status("Recording")
        # Initial START log (D9)
        track_info = f"{self.current_artist} — {self.current_title}"
        self.logger.log_event("START", track_info, rec_seconds=0)
        self.last_track_key = track_info

    def handle_channel_change(self, name):
        # UI already blocks if recording
        self.ui.set_active_channel(name)
        if self.on_air_intent:
            self.reconnect_retry_count = 0
            self.reconnect_timer.stop()
            self._start_playback()

    def handle_open_folder(self):
        from .utils import open_output_dir
        open_output_dir(self.settings.get("output_dir", "../recordings"))

    def handle_restart(self):
        print("DEBUG: Restarting application...")
        self._ensure_cleanup()
        
        import subprocess
        try:
            # Use module execution mode to be safe
            subprocess.Popen([sys.executable, "-m", "app.main"])
            QApplication.instance().quit()
        except Exception as e:
            print(f"DEBUG: Restart failed: {e}")

    def _handle_window_close(self, event):
        print("DEBUG: Window close detected. Cleaning up...")
        self._ensure_cleanup()
        event.accept()

    def _ensure_cleanup(self):
        """Aggressively stop recorder and player."""
        proc = self.recorder.process
        if proc or self.recorder.is_recording:
            print("DEBUG: Cleanup: Stopping recorder...")
            self.recorder.stop_recording()
            
            # Re-check and force kill if still alive
            if proc and proc.poll() is None:
                try:
                    print(f"DEBUG: Cleanup: Force killing FFmpeg pid {proc.pid}")
                    proc.kill()
                    proc.wait(timeout=1)
                except:
                    pass
        
        if self.player:
            print("DEBUG: Cleanup: Stopping player...")
            self.player.stop()

    def handle_copy_log(self):
        if self.logger:
            line = self.logger.get_last_line()
            if line:
                from PySide6.QtGui import QGuiApplication
                clipboard = QGuiApplication.clipboard()
                clipboard.setText(line)
                self.ui.set_status("Copied last log line")

    def _get_current_channel_config(self):
        name = self.ui.current_channel
        for ch in self.channels.get("channels", []):
            if ch["name"] == name:
                return ch
        return {}

    def get_current_url(self):
        name = self.ui.current_channel
        for ch in self.channels["channels"]:
            if ch["name"] == name:
                return ch["url"]
        return None

    def poll_metadata(self):
        if not self.player.is_playing():
            return

        artist, title = self.player.get_metadata()
        
        # Fallback Logic (A2)
        ch_settings = self._get_current_channel_config()
        meta_provider = ch_settings.get("meta_provider")
        
        if artist == "Unknown" and meta_provider == "sr_latlista":
            self.unknown_count += 1
            if self.unknown_count >= 3:
                now = time.time()
                if now - self.last_provider_poll > 15: # 15s interval
                    self.last_provider_poll = now
                    try:
                        from .providers.sr_playlist import fetch_sr_metadata
                        p_artist, p_title = fetch_sr_metadata(ch_settings.get("meta_url"))
                        if p_artist != "Unknown":
                            artist, title = p_artist, p_title
                    except ImportError:
                        pass
        else:
            self.unknown_count = 0

        self.current_artist = artist
        self.current_title = title
        self.ui.update_metadata(artist, title)
        
        track_key = f"{artist} — {title}"
        
        # Track Change Triggers
        # Rule: key != last AND title != "—" (avoid empty flap)
        if track_key != self.last_track_key and title != "—":
            timestamp = get_hms_str()
            history_line = f"[{timestamp}] [{self.ui.current_channel}] {track_key}"
            self.ui.append_history(history_line)
            
            if self.recorder.is_recording and self.logger:
                rec_secs = self.recorder.get_elapsed_seconds()
                # END prev
                if self.last_track_key:
                    self.logger.log_event("END", self.last_track_key, rec_seconds=rec_secs, suffix="track changed")
                # START new
                self.logger.log_event("START", track_key, rec_seconds=rec_secs)
            
            self.last_track_key = track_key
        
        # B5: Update Latency UI (Pragmatic estimate)
        # In this architecture, latency is primarily cache_ms + network delay
        cache_ms = self.settings.get("network_cache_ms", 1500)
        self.latency_estimate = cache_ms / 1000.0
        self.ui.lbl_latency.setText(f"LATENCY: ~{self.latency_estimate:.1f}s")


def main():
    app = QApplication(sys.argv)
    
    # Ensure working directory is project root
    # os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    tape_deck = TapeDeckApp()
    tape_deck.ui.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
