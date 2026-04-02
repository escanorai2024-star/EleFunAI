import os
import cv2
import numpy as np
import subprocess
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QProgressBar, 
                               QPushButton, QMessageBox, QTextEdit, QApplication)
from PySide6.QtCore import Qt, QThread, Signal

class CropWorker(QThread):
    progress = Signal(int, int)  # current, total
    log = Signal(str)
    finished = Signal()

    def __init__(self, video_paths, ffmpeg_path):
        super().__init__()
        self.video_paths = video_paths
        self.ffmpeg_path = ffmpeg_path
        self.is_running = True

        # Register to global registry to prevent GC
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_crop_workers'):
                app._active_crop_workers = []
            app._active_crop_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        """Clean up worker from global registry"""
        app = QApplication.instance()
        if app and hasattr(app, '_active_crop_workers'):
            if self in app._active_crop_workers:
                app._active_crop_workers.remove(self)
        self.deleteLater()

    def run(self):
        # Remove duplicates
        unique_paths = list(set(self.video_paths))
        total = len(unique_paths)
        
        for i, video_path in enumerate(unique_paths):
            if not self.is_running:
                break
            
            try:
                if not os.path.exists(video_path):
                    self.log.emit(f"文件不存在: {video_path}")
                    self.progress.emit(i + 1, total)
                    continue

                self.log.emit(f"正在分析: {os.path.basename(video_path)} ...")
                
                # Analyze video to find start time
                start_time = self.detect_start_time(video_path)
                
                if start_time > 0:
                    self.log.emit(f"  - 发现黑色开头: {start_time:.2f}秒")
                    success = self.crop_video(video_path, start_time)
                    if success:
                        self.log.emit(f"  - 裁剪成功")
                    else:
                        self.log.emit(f"  - 裁剪失败")
                else:
                    self.log.emit(f"  - 无需裁剪")
                
            except Exception as e:
                self.log.emit(f"处理出错: {str(e)}")
            
            self.progress.emit(i + 1, total)
        
        self.finished.emit()

    def detect_start_time(self, video_path):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return 0.0
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            cap.release()
            return 0.0

        frame_count = 0
        start_frame = 0
        
        # Check first 5 seconds max to avoid scanning whole movie if it's all black
        max_frames = int(fps * 5) 
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Check if frame is black
            # Calculate average brightness
            avg_color = np.mean(frame)
            
            if avg_color > 10: # Threshold for black
                start_frame = frame_count
                break
            
            frame_count += 1
            if frame_count > max_frames:
                # If 5 seconds are black, maybe it's just a black video or intro
                # Safety break, but return found frames
                start_frame = frame_count
                break
        
        cap.release()
        
        if start_frame > 0:
            return start_frame / fps
        return 0.0

    def crop_video(self, input_path, start_time):
        # Create temp output path
        dir_name = os.path.dirname(input_path)
        file_name = os.path.basename(input_path)
        name, ext = os.path.splitext(file_name)
        temp_output = os.path.join(dir_name, f"{name}_cropped{ext}")
        
        # Construct ffmpeg command
        # -ss before -i is faster but less accurate. 
        # -ss after -i is frame accurate but slower decoding.
        # Since we want to remove black frames precisely, we use -ss after -i? 
        # Actually -ss before -i seeks to keyframe, then decodes.
        # Let's put -ss before -i for speed, but re-encode.
        
        # To be safe and accurate:
        # ffmpeg -i input -ss start_time -c:v libx264 -c:a copy output
        # If we don't have libx264, use default or mpeg4.
        
        cmd = [
            self.ffmpeg_path,
            "-y", # Overwrite output
            "-i", input_path,
            "-ss", str(start_time),
            "-c:v", "libx264", # Re-encode video
            "-preset", "fast",
            "-c:a", "copy", # Copy audio
            temp_output
        ]
        
        # Run ffmpeg
        # Hide window
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        try:
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                startupinfo=startupinfo
            )
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                # Replace original file
                # Need to close file handles first? ffmpeg finished so it should be fine.
                # Remove original
                os.remove(input_path)
                # Rename temp to original
                os.rename(temp_output, input_path)
                return True
            else:
                self.log.emit(f"ffmpeg error: {stderr.decode('utf-8', errors='ignore')}")
                if os.path.exists(temp_output):
                    os.remove(temp_output)
                return False
        except Exception as e:
            self.log.emit(f"ffmpeg exception: {str(e)}")
            if os.path.exists(temp_output):
                os.remove(temp_output)
            return False
            
    def stop(self):
        self.is_running = False

class AutoCropDialog(QDialog):
    def __init__(self, video_paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle("自动裁剪视频")
        self.setFixedSize(500, 400)
        self.video_paths = video_paths
        
        # Locate ffmpeg
        self.ffmpeg_path = os.path.join(os.getcwd(), 'ffmpeg', 'ffmpeg.exe')
        
        self.setup_ui()
        
        if not os.path.exists(self.ffmpeg_path):
            self.log_text.append(f"错误: 未找到 ffmpeg.exe 于 {self.ffmpeg_path}")
            self.start_btn.setEnabled(False)
        else:
            self.log_text.append(f"就绪: 待处理视频 {len(video_paths)} 个")

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        self.label = QLabel("将自动检测并删除视频开头的黑色内容。")
        layout.addWidget(self.label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, len(self.video_paths))
        layout.addWidget(self.progress_bar)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)
        
        self.start_btn = QPushButton("开始裁剪")
        self.start_btn.clicked.connect(self.start_cropping)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #673AB7;
                color: white;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #7E57C2;
            }
        """)
        layout.addWidget(self.start_btn)

    def start_cropping(self):
        self.start_btn.setEnabled(False)
        self.worker = CropWorker(self.video_paths, self.ffmpeg_path)
        self.worker.progress.connect(self.update_progress)
        self.worker.log.connect(self.append_log)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def update_progress(self, current, total):
        self.progress_bar.setValue(current)

    def append_log(self, text):
        self.log_text.append(text)
        # Scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def on_finished(self):
        self.log_text.append("处理完成！")
        self.start_btn.setEnabled(True)
        self.start_btn.setText("完成")
        self.start_btn.clicked.disconnect()
        self.start_btn.clicked.connect(self.accept)

def open_auto_crop_dialog(video_paths, parent=None):
    dialog = AutoCropDialog(video_paths, parent)
    dialog.exec()
