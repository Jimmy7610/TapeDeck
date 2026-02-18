import os
from .utils import get_hms_str, format_duration

class TapeLogger:
    def __init__(self, log_path, ui_callback=None):
        self.log_path = log_path
        self.ui_callback = ui_callback
        self.last_line = ""

    def log_event(self, event_type, track_info, rec_seconds=None, suffix=""):
        """
        [HH:MM:SS] [REC +MM:SS] START Artist — Title
        [HH:MM:SS] [REC +MM:SS] END   Artist — Title (track changed)
        """
        hms = get_hms_str()
        rec_time = format_duration(rec_seconds) if rec_seconds is not None else "+00:00"
        
        line = f"[{hms}] [{rec_time}] {event_type:<5} {track_info}"
        if suffix:
            line += f" ({suffix})"
        
        self.last_line = line
        
        # Write to file
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            print(f"Logging error: {e}")

        # Update UI
        if self.ui_callback:
            self.ui_callback(line)

    def get_last_line(self):
        return self.last_line
