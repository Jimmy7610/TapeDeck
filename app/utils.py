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
