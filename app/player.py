import vlc
import time
import platform
import os

class RadioPlayer:
    def __init__(self):
        self._init_vlc()
        self.current_url = None
        self._last_polled_state = 0 # NothingSpecial

    def _init_vlc(self):
        arch = platform.architecture()[0]
        print(f"DEBUG: Python Architecture: {arch}")
        
        # Try to find VLC and add to DLL directory for Python 3.8+ on Windows
        resolved_path = None
        if os.name == 'nt':
            vlc_paths = [
                os.environ.get('PYTHON_VLC_LIB_PATH'),
                r"C:\Program Files\VideoLAN\VLC",
                r"C:\Program Files (x86)\VideoLAN\VLC"
            ]
            for path in vlc_paths:
                if path and os.path.exists(path):
                    try:
                        os.add_dll_directory(path)
                        resolved_path = path
                        break
                    except Exception as e:
                        print(f"WARN: Failed to add DLL directory {path}: {e}")
            
            if resolved_path:
                print(f"DEBUG: Resolved VLC DLL path: {resolved_path}")
                # Architecture check hint
                if "x86" in resolved_path and "64bit" in arch:
                    print("CRITICAL: ARCHITECTURE MISMATCH! Python is 64-bit but VLC path suggests 32-bit (x86). Audio will likely fail.")
                elif "Program Files" in resolved_path and "x86" not in resolved_path and "32bit" in arch:
                    print("CRITICAL: ARCHITECTURE MISMATCH! Python is 32-bit but VLC path suggests 64-bit. Audio will likely fail.")
            else:
                print("ERROR: Could not resolve VLC installation path.")

        try:
            # B2: Force mmdevice for Windows audio stability.
            # Some versions prefer a single string or specifically formatted args.
            vlc_args = "--no-video --aout=mmdevice --mmdevice-role=console --audio-resampler=soxr --quiet"
            print(f"DEBUG: Creating vlc.Instance with: {vlc_args}")
            self.instance = vlc.Instance(vlc_args)
            
            if not self.instance:
                print("WARN: vlc.Instance(vlc_args) returned None, trying fallback...")
                self.instance = vlc.Instance("--no-video --quiet")
            
            print(f"DEBUG: vlc.Instance created: {self.instance}")

            self.player = self.instance.media_player_new()
            
            vlc_ver = vlc.libvlc_get_version().decode('utf-8')
            print(f"DEBUG: VLC Version: {vlc_ver}")
            print(f"DEBUG: VLC Version: {vlc_ver}")
            print(f"DEBUG: VLC Instance args: {vlc_args}")
            
            # E5: Dump audio devices
            self._dump_audio_devices()
            
            print("DEBUG: VLC Instance and Player initialized successfully.")
        except Exception as e:
            print(f"CRITICAL: VLC Initialization failed: {e}")
            self.instance = None
            self.player = None

    def _dump_audio_devices(self):
        try:
            mods = self.player.audio_output_device_enum()
            if mods:
                print("DEBUG: Available Audio Devices:")
                curr = mods
                while curr:
                    d = curr.contents
                    print(f"  - [{d.device}] {d.description.decode('utf-8', 'ignore')}")
                    curr = d.next
                vlc.libvlc_audio_output_device_list_release(mods)
        except Exception as e:
            print(f"DEBUG: Could not list audio devices: {e}")

    def play(self, url, options=None):
        """
        Starts playback of the given URL.
        :param url: The stream URL
        :param options: List of media options strings, e.g. [":http-user-agent=..."]
        """
        if not self.instance or not self.player:
            return

        self.stop()
        
        print(f"DEBUG: Starting playback of URL: {url}")
        if options:
            print(f"DEBUG: Media options: {options}")

        try:
            self.media = self.instance.media_new(url)
            
            # Apply options (D4)
            if options:
                for opt in options:
                    self.media.add_option(opt)
            
            self.player.set_media(self.media)
            self.player.play()
            
            # C3/E5: Force unmute and sane volume
            self.player.audio_set_mute(False)
            self.player.audio_set_volume(80)
            
            from .utils import get_timestamp_str
            vol = self.player.audio_get_volume()
            mute = self.player.audio_get_mute()
            print(f"[{get_timestamp_str()}] DEBUG: Audio enforced -> Mute: {bool(mute)}, Vol: {vol}")
            
        except Exception as e:
            print(f"CRITICAL: VLC Play Error: {e}")

    def _is_bauer_stream(self, url):
        markers = ["sharp-stream.com", "instreamtest", "aacp"]
        return any(m in url.lower() for m in markers)

    def stop(self):
        if self.player:
            print("DEBUG: Stopping playback.")
            self.player.stop()

    def get_metadata(self):
        """
        Poll VLC media meta.
        Returns (artist, title).
        """
        if not self.player:
            return "Unknown", "—"
            
        media = self.player.get_media()
        if not media:
            return "Unknown", "—"

        # VLC keys: 0=Title, 1=Artist, 12=NowPlaying
        title = media.get_meta(0)
        artist = media.get_meta(1)
        now_playing = media.get_meta(12)

        # Heuristic for stream labels
        if now_playing and " - " in now_playing:
            parts = now_playing.split(" - ", 1)
            artist = artist or parts[0].strip()
            title = title or parts[1].strip()
        elif now_playing:
            title = title or now_playing.strip()

        artist = artist or "Unknown"
        title = title or "—"
        return artist, title

    def get_state(self):
        """Returns the current state of the player as an integer and logs transitions."""
        if not self.player:
            return 6 # Ended/Stopped
        
        try:
            from .utils import get_timestamp_str
            state_val = self.player.get_state().value
            
            # Log transition if changed
            if state_val != self._last_polled_state:
                old_name = self.get_state_name(self._last_polled_state)
                new_name = self.get_state_name(state_val)
                print(f"[{get_timestamp_str()}] VLC: {old_name} -> {new_name}")
                self._last_polled_state = state_val
                
            return int(state_val)
        except:
            return 7 # Error

    def get_state_name(self, state_value):
        """Maps VLC state integer to a human-readable string."""
        mapping = {
            0: "NothingSpecial",
            1: "Opening",
            2: "Buffering",
            3: "Playing",
            4: "Paused",
            5: "Stopped",
            6: "Ended",
            7: "Error"
        }
        return mapping.get(state_value, f"Unknown({state_value})")

    def is_playing(self):
        if not self.player:
            return False
        return self.player.is_playing()

    def is_initialized(self):
        return self.instance is not None and self.player is not None
