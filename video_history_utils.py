import json
import os
from pathlib import Path
from datetime import datetime

HISTORY_FILE = Path('json/video_main.json')

def load_history():
    """Load video history from json/video_main.json"""
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Normalize old string format to dict
            history = data.get('history', [])
            normalized = []
            for item in history:
                if isinstance(item, str):
                    normalized.append({'path': item, 'time': '', 'prompt': ''})
                else:
                    if 'prompt' not in item:
                        item['prompt'] = ''
                    normalized.append(item)
            return normalized
    except Exception as e:
        print(f'[History] Load failed: {e}')
        return []

def save_history(history_list):
    """Save video history to json/video_main.json"""
    try:
        # Ensure directory exists
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump({'history': history_list}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'[History] Save failed: {e}')

def add_to_history(video_path, prompt=""):
    history = load_history()
    
    # Create new item
    new_item = {
        'path': video_path,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'prompt': prompt
    }

    # Avoid duplicates at the top (check path only)
    if history and history[0].get('path') == video_path:
        return history
        
    # Add new item to the beginning
    history.insert(0, new_item)
    
    # Keep only last 5
    history = history[:5]
    
    save_history(history)
    return history

def clear_history():
    save_history([])
