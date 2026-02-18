import os
import sys

def debug_vlc():
    print(f"OS: {os.name}")
    print(f"Python: {sys.version}")
    
    paths_to_check = [
        os.environ.get('PYTHON_VLC_LIB_PATH'),
        r"C:\Program Files\VideoLAN\VLC",
        r"C:\Program Files (x86)\VideoLAN\VLC",
        r"C:\Program Files\VLC",
        r"C:\Program Files (x86)\VLC",
    ]
    
    for path in paths_to_check:
        if path:
            exists = os.path.exists(path)
            print(f"Checking {path}: {'EXISTS' if exists else 'NOT FOUND'}")
            if exists:
                dll_path = os.path.join(path, "libvlc.dll")
                print(f"  libvlc.dll: {'EXISTS' if os.path.exists(dll_path) else 'NOT FOUND'}")

    try:
        import vlc
        print("Successfully imported vlc module")
        try:
            instance = vlc.Instance()
            print("Successfully created vlc.Instance()")
        except Exception as e:
            print(f"Error creating vlc.Instance: {e}")
    except ImportError:
        print("Could not import vlc module")

if __name__ == "__main__":
    debug_vlc()
