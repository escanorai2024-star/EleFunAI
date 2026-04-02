import os
import subprocess
import re
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread, Signal
try:
    from lingdongchaifen import VideoSplitter
except ImportError:
    # Fallback if import fails (e.g. run standalone)
    class VideoSplitter(QThread):
        progress = Signal(int)
        finished = Signal(bool, str, list)
        def __init__(self, input_path, output_dir, mode, value, ffmpeg_path="ffmpeg"):
            super().__init__()
            self.input_path = input_path
            self.output_dir = output_dir
            self.mode = mode
            self.value = value
            self.ffmpeg_path = ffmpeg_path
            self.is_running = True
            
            # Register to global registry to prevent GC
            app = QApplication.instance()
            if app:
                if not hasattr(app, '_active_splitters_fallback'):
                    app._active_splitters_fallback = []
                app._active_splitters_fallback.append(self)
            self.finished.connect(self._cleanup_worker)

        def _cleanup_worker(self):
            app = QApplication.instance()
            if app and hasattr(app, '_active_splitters_fallback'):
                if self in app._active_splitters_fallback:
                    app._active_splitters_fallback.remove(self)
            self.deleteLater()

class GoogleVideoSplitter(VideoSplitter):
    """谷歌镜头拆分器 - 根据时间码提取首尾帧"""
    
    # finished signal signature: (success, message, result_list)
    # result_list: [{'row': int, 'start_img': str, 'end_img': str}, ...]
    finished_with_data = Signal(bool, str, list)
    
    def __init__(self, input_path, output_dir, timecode_data, ffmpeg_path="ffmpeg"):
        """
        timecode_data: list of (row_index, timecode_string)
        """
        super().__init__(input_path, output_dir, 'custom', 0, ffmpeg_path)
        self.timecode_data = timecode_data
        
        # Ensure cleanup on my signal (since base VideoSplitter cleans up on 'finished', 
        # but we use 'finished_with_data')
        self.finished_with_data.connect(self._cleanup_google_worker)
        
        # Register to global registry (redundant but safe if base didn't)
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_google_splitters'):
                app._active_google_splitters = []
            app._active_google_splitters.append(self)

    def _cleanup_google_worker(self):
        """Clean up google worker"""
        app = QApplication.instance()
        if app and hasattr(app, '_active_google_splitters'):
            if self in app._active_google_splitters:
                app._active_google_splitters.remove(self)
        
        # Also try to call base cleanup if it exists
        if hasattr(self, '_cleanup_worker'):
             self._cleanup_worker()
        else:
             self.deleteLater()

    def run(self):
        try:
            # Check ffmpeg
            try:
                subprocess.run([self.ffmpeg_path, '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                self.finished_with_data.emit(False, f"未检测到FFmpeg ({self.ffmpeg_path})，请确保已安装FFmpeg并正确配置路径。", [])
                return
            
            if not os.path.exists(self.output_dir):
                os.makedirs(self.output_dir)
                
            results = []
            total = len(self.timecode_data)
            
            for i, (row_idx, timecode_str) in enumerate(self.timecode_data):
                if not self.is_running:
                    break
                    
                start_time, end_time = self._parse_timecode(timecode_str)
                if not start_time:
                    print(f"无法解析时间码: {timecode_str}")
                    continue
                
                # Generate filenames
                base_name = os.path.splitext(os.path.basename(self.input_path))[0]
                # Use timestamp in filename to avoid conflict if multiple rows have same time?
                # Using row index is safer
                start_img_name = f"{base_name}_row{row_idx}_start.jpg"
                end_img_name = f"{base_name}_row{row_idx}_end.jpg"
                
                start_img_path = os.path.join(self.output_dir, start_img_name)
                end_img_path = os.path.join(self.output_dir, end_img_name)
                
                # Extract start frame
                if self._extract_frame(start_time, start_img_path):
                    item = {'row': row_idx, 'start_img': start_img_path, 'end_img': None}
                    
                    # Extract end frame
                    if end_time:
                        if self._extract_frame(end_time, end_img_path):
                            item['end_img'] = end_img_path
                    
                    results.append(item)
                
                self.progress.emit(int((i + 1) / total * 100))
                
            self.finished_with_data.emit(True, "拆分完成", results)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished_with_data.emit(False, str(e), [])
            
    def _parse_timecode(self, timecode_str):
        """解析时间码，支持 '2-5', '00:00:02-00:00:05' 等格式"""
        if not timecode_str:
            return None, None
            
        # Normalize
        s = str(timecode_str).replace('：', ':').replace('，', ',').replace('至', '-').replace('到', '-')
        
        # Handle "2-5" or "00:00:02-00:00:05"
        parts = re.split(r'[-]', s)
        if len(parts) >= 2:
            return parts[0].strip(), parts[1].strip()
        elif len(parts) == 1:
            return parts[0].strip(), None
        return None, None

    def _extract_frame(self, time_pos, output_path):
        try:
            cmd = [
                self.ffmpeg_path, 
                '-ss', str(time_pos),
                '-i', self.input_path,
                '-vframes', '1',
                '-q:v', '2', # High quality jpg
                '-y',
                output_path
            ]
            
            # Windows hide console
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo, check=True)
            return True
        except Exception as e:
            print(f"Frame extraction failed for {time_pos}: {e}")
            return False
