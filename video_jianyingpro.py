import os
import json
import time
import win32gui
import win32con
import win32api
import win32clipboard
import win32com.client

def set_clipboard(text):
    """Set text to clipboard using win32clipboard"""
    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
    except Exception as e:
        print(f"Error setting clipboard: {e}")


def find_jianying_window():
    """Locate Jianying/剪映 main window and bring it to front."""
    hwnds = []

    def enum_handler(hwnd, result):
        title = win32gui.GetWindowText(hwnd)
        if "剪映" in title and win32gui.IsWindowVisible(hwnd):
            result.append(hwnd)

    try:
        win32gui.EnumWindows(enum_handler, hwnds)
    except Exception as e:
        print(f"[Jianying] EnumWindows failed: {e}")
        return None, None

    if not hwnds:
        print("[Jianying] Software not found. Please open JianyingPro.")
        return None, None

    target_hwnd = hwnds[0]
    print(f"[Jianying] Found window: {win32gui.GetWindowText(target_hwnd)}")

    shell = None
    try:
        if win32gui.IsIconic(target_hwnd):
            win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)

        shell = win32com.client.Dispatch("WScript.Shell")
        shell.SendKeys('%')
        win32gui.SetForegroundWindow(target_hwnd)
        time.sleep(0.5)
    except Exception as e:
        print(f"[Jianying] Error focusing window: {e}")

    if shell is None:
        try:
            shell = win32com.client.Dispatch("WScript.Shell")
        except Exception as e:
            print(f"[Jianying] Error creating WScript.Shell: {e}")
            return target_hwnd, None

    return target_hwnd, shell


def import_single_video(path):
    """Import a single video file into Jianying using keyboard automation."""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        print(f"[Jianying] Video file not found: {path}")
        return

    _, shell = find_jianying_window()
    if shell is None:
        return

    try:
        print(f"[Jianying] Importing single video: {path}")
        shell.SendKeys("^i")
        time.sleep(1.0)
        set_clipboard(path)
        time.sleep(0.2)
        shell.SendKeys("^v")
        time.sleep(0.5)
        shell.SendKeys("{ENTER}")
        time.sleep(1.5)
    except Exception as e:
        print(f"[Jianying] Error importing single video: {e}")


def run():
    print("[Jianying] Starting automation...")
    
    # 1. Read JSON
    # Assuming the script is run from project root or relative to it.
    # Based on user env: c:\Users\Administrator.DESKTOP-QNJM23G\Desktop\OS
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # If this file is in OS/, then json is in OS/json/
    json_path = os.path.join(base_dir, 'json', 'daoyan_TV_VIDEO_SAVE.JSON')
    
    if not os.path.exists(json_path):
        # Try current working directory
        json_path = os.path.join(os.getcwd(), 'json', 'daoyan_TV_VIDEO_SAVE.JSON')
    
    if not os.path.exists(json_path):
        print(f"[Jianying] JSON file not found: {json_path}")
        return

    print(f"[Jianying] Reading JSON: {json_path}")
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[Jianying] Error reading JSON: {e}")
        return

    # 2. Get paths sorted 1..999
    paths = []
    # User requested 1 to 999
    for i in range(1, 1000):
        key = str(i)
        if key in data:
            path = data[key]
            # Normalize path
            path = os.path.abspath(path)
            if os.path.exists(path):
                paths.append(path)
            else:
                print(f"[Jianying] Warning: Video file not found: {path}")
    
    if not paths:
        print("[Jianying] No valid videos found in JSON for keys 1-999.")
        return

    print(f"[Jianying] Found {len(paths)} videos to import.")

    # 3. Find Jianying
    _, shell = find_jianying_window()
    if shell is None:
        return
    
    # 4. Import loop
    for idx, path in enumerate(paths):
        print(f"[Jianying] Importing ({idx+1}/{len(paths)}): {path}")
        
        import_single_video(path)
        
    print("[Jianying] All videos imported.")

if __name__ == "__main__":
    run()
