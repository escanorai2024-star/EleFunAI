
import os
import json

def sort_key(k):
    s = str(k).replace('镜头', '').strip()
    if s.isdigit():
        return (0, int(s)) # (0, number) for numbers
    return (1, s)          # (1, string) for others

json_path = os.path.join(os.getcwd(), 'JSON', 'daoyan_TV_VIDEO_SAVE.JSON')
print(f"Checking JSON at: {json_path}")

if os.path.exists(json_path):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"Loaded {len(data)} items.")
        
        sorted_keys = sorted(data.keys(), key=sort_key)
        
        print("Sorted order:")
        paths = []
        for k in sorted_keys:
            p = data[k]
            print(f"  {k}: {p}")
            paths.append(p)
            
        print("\nPaths to send:")
        for p in paths:
            print(p)
            
    except Exception as e:
        print(f"Error reading JSON: {e}")
else:
    print("JSON file not found.")
