import os
import subprocess
import re
import json
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QLineEdit, QPushButton, QRadioButton, QButtonGroup, 
                               QFileDialog, QMessageBox, QProgressBar, QGroupBox,
                               QFormLayout, QSlider, QWidget, QApplication)
from PySide6.QtCore import Qt, QThread, Signal

import glob

def is_video_connected_to_image(node):
    """
    检查节点是否是视频节点，且连接了图片节点。
    用于控制视频拆分按钮的显示。
    """
    if not node:
        return False
        
    # 1. 检查是否是视频节点
    title = getattr(node, "node_title", "")
    is_video = "视频" in title or (hasattr(node, "video_path") and node.video_path)
    
    if not is_video:
        return False
        
    # 2. 检查连接
    # 检查输入插槽 (VideoNode might receive input from ImageNode?)
    if hasattr(node, 'input_sockets'):
        for socket in node.input_sockets:
            for conn in socket.connections:
                if conn.source_socket:
                    src = conn.source_socket.parent_node
                    if src:
                        src_title = getattr(src, "node_title", "")
                        if "图片" in src_title or "Image" in src_title:
                            return True
                        
    # 检查输出插槽 (VideoNode outputs to ImageNode?)
    if hasattr(node, 'output_sockets'):
        for socket in node.output_sockets:
            for conn in socket.connections:
                if conn.target_socket:
                    dst = conn.target_socket.parent_node
                    if dst:
                        dst_title = getattr(dst, "node_title", "")
                        if "图片" in dst_title or "Image" in dst_title:
                            return True
                        
    return False

class VideoSplitter(QThread):
    progress = Signal(int)
    finished = Signal(bool, str, list)
    
    def __init__(self, input_path, output_dir, mode, value, ffmpeg_path="ffmpeg"):
        super().__init__()
        self.input_path = input_path
        self.output_dir = output_dir
        self.mode = mode # 'duration', 'parts', or 'scene'
        self.value = value
        self.ffmpeg_path = ffmpeg_path if ffmpeg_path else "ffmpeg"
        self.is_running = True
        self.generated_files = []

        # Register to global registry to prevent GC
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_video_splitters_chaifen'):
                app._active_video_splitters_chaifen = []
            app._active_video_splitters_chaifen.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        """Clean up worker from global registry"""
        app = QApplication.instance()
        if app and hasattr(app, '_active_video_splitters_chaifen'):
            if self in app._active_video_splitters_chaifen:
                app._active_video_splitters_chaifen.remove(self)
        self.deleteLater()
        
    def run(self):
        try:
            # Check ffmpeg availability
            try:
                subprocess.run([self.ffmpeg_path, '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                self.finished.emit(False, f"未检测到FFmpeg ({self.ffmpeg_path})，请确保已安装FFmpeg并正确配置路径。", [])
                return

            # Get video duration first
            duration = self.get_duration(self.input_path)
            if duration is None:
                self.finished.emit(False, "无法获取视频时长", [])
                return

            filename = os.path.basename(self.input_path)
            name, ext = os.path.splitext(filename)
            
            # Create output directory if not exists
            if not os.path.exists(self.output_dir):
                os.makedirs(self.output_dir)
            
            cmd = []
            output_pattern = ""
            
            if self.mode == 'duration':
                segment_time = float(self.value)
                if segment_time <= 0:
                    self.finished.emit(False, "拆分时长必须大于0", [])
                    return
                    
                output_pattern = os.path.join(self.output_dir, f"{name}_part%03d{ext}")
                
                cmd = [
                    self.ffmpeg_path, '-i', self.input_path, 
                    '-c', 'copy', 
                    '-f', 'segment',
                    '-segment_time', str(segment_time),
                    '-reset_timestamps', '1',
                    '-y', # Overwrite output files
                    output_pattern
                ]
                
            elif self.mode == 'parts':
                num_parts = int(self.value)
                if num_parts <= 0:
                    self.finished.emit(False, "拆分份数必须大于0", [])
                    return
                    
                segment_time = duration / num_parts
                output_pattern = os.path.join(self.output_dir, f"{name}_part%03d{ext}")
                
                cmd = [
                    self.ffmpeg_path, '-i', self.input_path, 
                    '-c', 'copy', 
                    '-f', 'segment',
                    '-segment_time', str(segment_time),
                    '-reset_timestamps', '1',
                    '-y',
                    output_pattern
                ]
                
            elif self.mode == 'scene':
                threshold = float(self.value)
                if not (0 <= threshold <= 1):
                    self.finished.emit(False, "场景检测阈值必须在0到1之间", [])
                    return
                
                # Extract frames based on scene change
                output_pattern = os.path.join(self.output_dir, f"{name}_scene%03d.png")
                
                cmd = [
                    self.ffmpeg_path, '-i', self.input_path,
                    '-vf', f"select='gt(scene,{threshold})'",
                    '-vsync', 'vfr',
                    '-y',
                    output_pattern
                ]
            
            # Run ffmpeg command
            # For Windows, hide console window
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')
                self.finished.emit(False, f"FFmpeg Error: {error_msg}", [])
            else:
                # Find generated files
                if self.mode == 'scene':
                    # Search for png files matching the pattern
                    pattern = os.path.join(self.output_dir, f"{name}_scene*.png")
                    self.generated_files = glob.glob(pattern)
                else:
                    # Search for video parts
                    pattern = os.path.join(self.output_dir, f"{name}_part*{ext}")
                    self.generated_files = glob.glob(pattern)
                
                self.generated_files.sort()
                self.finished.emit(True, f"拆分完成！\n共生成 {len(self.generated_files)} 个文件\n文件已保存至: {self.output_dir}", self.generated_files)
                
        except Exception as e:
            self.finished.emit(False, str(e), [])

    def get_duration(self, input_path):
        try:
            ffprobe_path = "ffprobe"
            if self.ffmpeg_path != "ffmpeg":
                 dirname = os.path.dirname(self.ffmpeg_path)
                 ffprobe_path = os.path.join(dirname, "ffprobe")
                 if os.name == 'nt' and not ffprobe_path.endswith('.exe'):
                     ffprobe_path += ".exe"
                     
            cmd = [ffprobe_path, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_path]
            
            # Hide console window
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            output = subprocess.check_output(cmd, startupinfo=startupinfo).decode('utf-8').strip()
            return float(output)
        except Exception as e:
            print(f"get_duration error: {e}")
            return None

class VideoSplitDialog(QDialog):
    def __init__(self, video_path, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.setWindowTitle("视频拆分")
        self.setFixedWidth(400)
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
            }
            QLabel {
                color: #333333;
                font-size: 13px;
            }
            QLineEdit {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 5px;
                background-color: #ffffff;
            }
            QPushButton {
                background-color: #1a73e8;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1557b0;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
            QRadioButton {
                color: #333333;
            }
        """)
        
        self.setup_ui()
        self.splitter_thread = None
        self.generated_files = []

    def load_settings(self):
        settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "json", "settings.json")
        if os.path.exists(settings_path):
            try:
                with open(settings_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_settings(self, settings):
        json_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "json")
        if not os.path.exists(json_dir):
            os.makedirs(json_dir)
        settings_path = os.path.join(json_dir, "settings.json")
        try:
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Save settings error: {e}")

    def save_current_settings(self):
        """保存当前设置到JSON"""
        settings = self.load_settings()
        
        # FFmpeg
        settings["ffmpeg_path"] = self.ffmpeg_edit.text()
        
        # Output Dir
        settings["output_dir"] = self.out_edit.text()
        
        # Split Mode
        if self.radio_duration.isChecked():
            settings["split_mode"] = "duration"
        elif self.radio_parts.isChecked():
            settings["split_mode"] = "parts"
        else:
            settings["split_mode"] = "scene"
            
        # Values
        settings["duration_val"] = self.duration_input.text()
        settings["parts_val"] = self.parts_input.text()
        settings["scene_threshold"] = self.scene_slider.value()
        
        # Node Mode
        settings["node_mode"] = self.node_mode_btn_group.checkedId()
        
        self.save_settings(settings)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # File info
        file_info_layout = QVBoxLayout()
        filename_label = QLabel(f"当前文件: {os.path.basename(self.video_path)}")
        filename_label.setStyleSheet("font-weight: bold;")
        file_info_layout.addWidget(filename_label)
        layout.addLayout(file_info_layout)
        
        # FFmpeg settings
        ffmpeg_layout = QHBoxLayout()
        ffmpeg_label = QLabel("FFmpeg:")
        self.ffmpeg_edit = QLineEdit()
        self.ffmpeg_edit.setPlaceholderText("默认 (系统变量)")
        browse_ffmpeg_btn = QPushButton("...")
        browse_ffmpeg_btn.setFixedWidth(40)
        browse_ffmpeg_btn.clicked.connect(self.browse_ffmpeg)
        
        ffmpeg_layout.addWidget(ffmpeg_label)
        ffmpeg_layout.addWidget(self.ffmpeg_edit)
        ffmpeg_layout.addWidget(browse_ffmpeg_btn)
        layout.addLayout(ffmpeg_layout)

        # Load settings
        settings = self.load_settings()
        
        # 1. FFmpeg Path
        if "ffmpeg_path" in settings and settings["ffmpeg_path"]:
            self.ffmpeg_edit.setText(settings["ffmpeg_path"])
        else:
            # Auto-detect in current directory or script directory
            script_dir = os.path.dirname(os.path.abspath(__file__))
            cwd = os.getcwd()
            if os.path.exists(os.path.join(cwd, "ffmpeg.exe")):
                self.ffmpeg_edit.setText(os.path.join(cwd, "ffmpeg.exe"))
            elif os.path.exists(os.path.join(script_dir, "ffmpeg.exe")):
                self.ffmpeg_edit.setText(os.path.join(script_dir, "ffmpeg.exe"))
        
        # Split mode
        mode_group_box = QGroupBox("拆分方式")
        mode_layout = QVBoxLayout()
        
        self.mode_group = QButtonGroup(self)
        
        self.radio_duration = QRadioButton("按时长拆分 (秒)")
        self.mode_group.addButton(self.radio_duration, 1)
        mode_layout.addWidget(self.radio_duration)
        
        duration_val = settings.get("duration_val", "60")
        self.duration_input = QLineEdit(duration_val)
        self.duration_input.setPlaceholderText("请输入每段时长（秒）")
        self.duration_input.setEnabled(False)
        mode_layout.addWidget(self.duration_input)
        
        self.radio_parts = QRadioButton("按数量拆分 (份)")
        self.mode_group.addButton(self.radio_parts, 2)
        mode_layout.addWidget(self.radio_parts)
        
        parts_val = settings.get("parts_val", "2")
        self.parts_input = QLineEdit(parts_val)
        self.parts_input.setPlaceholderText("请输入拆分份数")
        self.parts_input.setEnabled(False)
        mode_layout.addWidget(self.parts_input)

        self.radio_scene = QRadioButton("场景检测拆分 (分镜图)")
        self.mode_group.addButton(self.radio_scene, 3)
        mode_layout.addWidget(self.radio_scene)
        
        # 场景检测滑块UI
        self.scene_widget = QWidget()
        scene_layout = QHBoxLayout(self.scene_widget)
        scene_layout.setContentsMargins(0, 0, 0, 0)
        
        self.scene_slider = QSlider(Qt.Orientation.Horizontal)
        self.scene_slider.setRange(0, 100)
        threshold_val = settings.get("scene_threshold", 30)
        self.scene_slider.setValue(threshold_val) 
        
        self.scene_value_label = QLabel(f"{threshold_val/100:.2f}")
        self.scene_value_label.setFixedWidth(40)
        
        self.scene_slider.valueChanged.connect(lambda v: self.scene_value_label.setText(f"{v/100:.2f}"))
        
        scene_layout.addWidget(QLabel("阈值:"))
        scene_layout.addWidget(self.scene_slider)
        scene_layout.addWidget(self.scene_value_label)
        
        mode_layout.addWidget(self.scene_widget)
        
        mode_group_box.setLayout(mode_layout)
        layout.addWidget(mode_group_box)
        
        # 2. Restore Split Mode Selection
        split_mode = settings.get("split_mode", "scene")
        if split_mode == "duration":
            self.radio_duration.setChecked(True)
        elif split_mode == "parts":
            self.radio_parts.setChecked(True)
        else:
            self.radio_scene.setChecked(True)

        # Node generation mode
        node_mode_group = QGroupBox("节点生成方式")
        node_mode_layout = QVBoxLayout()
        
        self.node_mode_btn_group = QButtonGroup(self)
        
        self.radio_single_node = QRadioButton("单图拆分 (推荐)")
        self.radio_single_node.setToolTip("每张拆分出来的图片生成一个独立的图片节点")
        self.node_mode_btn_group.addButton(self.radio_single_node, 1)
        node_mode_layout.addWidget(self.radio_single_node)
        
        self.radio_multi_node = QRadioButton("多图拆分 (编组)")
        self.radio_multi_node.setToolTip("所有拆分出来的图片合并到一个图片节点中，开启多图模式")
        self.node_mode_btn_group.addButton(self.radio_multi_node, 2)
        node_mode_layout.addWidget(self.radio_multi_node)
        
        # 3. Restore Node Mode
        node_mode = settings.get("node_mode", 1)
        if node_mode == 2:
            self.radio_multi_node.setChecked(True)
        else:
            self.radio_single_node.setChecked(True)
        
        node_mode_group.setLayout(node_mode_layout)
        layout.addWidget(node_mode_group)
        
        # Connect radio buttons
        self.radio_duration.toggled.connect(self.toggle_inputs)
        self.radio_parts.toggled.connect(self.toggle_inputs)
        self.radio_scene.toggled.connect(self.toggle_inputs)
        
        # Output directory
        out_layout = QHBoxLayout()
        out_label = QLabel("输出目录:")
        
        # 4. Restore Output Dir or use default
        default_dir = os.path.join(os.path.dirname(self.video_path), "frame")
        saved_out_dir = settings.get("output_dir", "")
        if saved_out_dir:
            self.out_edit = QLineEdit(saved_out_dir)
        else:
            self.out_edit = QLineEdit(default_dir)
            
        browse_btn = QPushButton("浏览")
        browse_btn.setStyleSheet("""
            background-color: #f1f3f4;
            color: #333333;
            border: 1px solid #dadce0;
        """)
        browse_btn.clicked.connect(self.browse_output)
        
        out_layout.addWidget(out_label)
        out_layout.addWidget(self.out_edit)
        out_layout.addWidget(browse_btn)
        layout.addLayout(out_layout)
        
        # Initial toggle to set enabled states based on restored selection
        self.toggle_inputs()

        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666666; font-size: 12px;")
        layout.addWidget(self.status_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setStyleSheet("""
            background-color: #f1f3f4;
            color: #333333;
            border: 1px solid #dadce0;
        """)
        self.cancel_btn.clicked.connect(self.reject)
        
        self.split_btn = QPushButton("开始拆分")
        self.split_btn.clicked.connect(self.start_split)
        
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.split_btn)
        layout.addLayout(btn_layout)

    def toggle_inputs(self):
        self.duration_input.setEnabled(self.radio_duration.isChecked())
        self.parts_input.setEnabled(self.radio_parts.isChecked())
        self.scene_widget.setEnabled(self.radio_scene.isChecked())

    def browse_ffmpeg(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择FFmpeg可执行文件", "", "Executables (*.exe);;All Files (*)")
        if file_path:
            self.ffmpeg_edit.setText(file_path)
            settings = self.load_settings()
            settings["ffmpeg_path"] = file_path
            self.save_settings(settings)

    def browse_output(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录", self.out_edit.text())
        if dir_path:
            self.out_edit.setText(dir_path)

    def start_split(self):
        # Save current settings
        self.save_current_settings()
        
        output_dir = self.out_edit.text()
        ffmpeg_path = self.ffmpeg_edit.text().strip()
        
        if not output_dir:
            QMessageBox.warning(self, "提示", "请选择输出目录")
            return
            
        if self.radio_duration.isChecked():
            mode = 'duration'
            value = self.duration_input.text()
            try:
                if float(value) <= 0:
                    raise ValueError
            except ValueError:
                QMessageBox.warning(self, "提示", "请输入有效的时长（大于0的数字）")
                return
        elif self.radio_parts.isChecked():
            mode = 'parts'
            value = self.parts_input.text()
            try:
                if int(value) <= 0:
                    raise ValueError
            except ValueError:
                QMessageBox.warning(self, "提示", "请输入有效的份数（大于0的整数）")
                return
        else: # Scene detection
            mode = 'scene'
            # Convert slider value (0-100) to float string (0.0-1.0)
            value = str(self.scene_slider.value() / 100.0)
        
        self.split_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0) # Indeterminate mode
        self.status_label.setText("正在拆分视频，请稍候...")
        
        self.splitter_thread = VideoSplitter(self.video_path, output_dir, mode, value, ffmpeg_path)
        self.splitter_thread.finished.connect(self.on_split_finished)
        self.splitter_thread.start()

    def on_split_finished(self, success, message, files):
        self.split_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        if success:
            self.status_label.setText("拆分成功")
            self.generated_files = files
            QMessageBox.information(self, "成功", message)
            self.accept()
        else:
            self.status_label.setText("拆分失败")
            QMessageBox.critical(self, "错误", message)
