import sys
import time
import subprocess
import os
from PIL import ImageGrab
import ctypes
from ctypes import wintypes

# Windows constants
SW_HIDE = 0
SW_SHOW = 5
GWL_STYLE = -16
WS_CAPTION = 0x00C00000

user32 = ctypes.windll.user32

def find_window(title):
    hwnd = user32.FindWindowW(None, title)
    return hwnd

def set_window_size(hwnd, width, height):
    # Adjust for window decorations to get accurate content size
    user32.SetWindowPos(hwnd, 0, 100, 100, width, height, 0x0040)

def capture_screenshot(filename):
    # This captures the whole screen for now as a fallback
    # In a real headfull env, we could crop to the window
    print(f"Capturing screenshot to {filename}...")
    img = ImageGrab.grab()
    img.save(filename)

def main():
    # Start the app
    proc = subprocess.Popen([sys.executable, "-m", "app.main"], cwd=os.getcwd())
    print("Launching TapeDeck...")
    time.sleep(5) # Wait for it to show
    
    hwnd = find_window("TapeDeck")
    if not hwnd:
        print("Could not find TapeDeck window.")
        return

    screenshots_dir = os.path.join(os.getcwd(), "test_results")
    if not os.path.exists(screenshots_dir):
        os.makedirs(screenshots_dir)

    # Wide: 1100x800
    print("Resizing to Wide...")
    set_window_size(hwnd, 1100, 800)
    time.sleep(2)
    capture_screenshot(os.path.join(screenshots_dir, "wide.png"))

    # Medium: 800x800
    print("Resizing to Medium...")
    set_window_size(hwnd, 850, 800)
    time.sleep(2)
    capture_screenshot(os.path.join(screenshots_dir, "medium.png"))

    # Narrow: 500x800
    print("Resizing to Narrow...")
    set_window_size(hwnd, 520, 800)
    time.sleep(2)
    capture_screenshot(os.path.join(screenshots_dir, "narrow.png"))

    print("Verification script finished. Cleaning up...")
    proc.terminate()
    proc.wait()

if __name__ == "__main__":
    main()
