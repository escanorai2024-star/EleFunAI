
import os
import json
import sys

# Mocking the class structure
class DirectorNodeImpl:
    def __init__(self):
        self.video_paths = {"shot_1": "c:\\test\\video.mp4"}

    def save_video_paths(self):
        """保存视频路径缓存"""
        try:
            dir_path = os.path.join(os.getcwd(), 'JSON')
            print(f"[DEBUG] Saving video paths to dir: {dir_path}")
            os.makedirs(dir_path, exist_ok=True)
            path = os.path.join(dir_path, 'daoyan_TV_VIDEO_SAVE.JSON')
            print(f"[DEBUG] Full save path: {path}")
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.video_paths, f, ensure_ascii=False, indent=2)
            print(f"[DEBUG] Successfully saved {len(self.video_paths)} entries to {path}")
        except Exception as e:
            print(f"Error saving video paths: {e}")

if __name__ == "__main__":
    print(f"Current CWD: {os.getcwd()}")
    node = DirectorNodeImpl()
    node.save_video_paths()
