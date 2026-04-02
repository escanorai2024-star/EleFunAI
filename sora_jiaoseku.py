import os
import json
import requests
import ssl
import tempfile
import urllib3

# 禁用安全请求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, 
    QScrollArea, QFrame, QDialog, QMessageBox, QDoubleSpinBox, QSlider, 
    QProgressBar, QTextEdit, QGridLayout, QMenu, QApplication
)
from PySide6.QtCore import Qt, QSize, QUrl, QThread, Signal, QTimer, QRect
from PySide6.QtGui import QPixmap, QIcon, QDesktopServices, QFont, QPainter, QColor, QImage, QAction
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

# 尝试导入配置加载函数
try:
    from Asora2 import load_config
except ImportError:
    def load_config():
        from PySide6.QtCore import QSettings
        s = QSettings('GhostOS', 'App')
        return {
            'api_key': s.value('providers/sora2/api_key', ''),
            'base_url': s.value('providers/sora2/base_url', 'https://api.vectorengine.ai'),
        }

def _get_app_root():
    import sys
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _get_store_path():
    json_dir = os.path.join(_get_app_root(), 'json')
    os.makedirs(json_dir, exist_ok=True)
    return os.path.join(json_dir, 'sora_characters.json')

def load_characters():
    path = _get_store_path()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_character(char_data):
    chars = load_characters()
    chars.insert(0, char_data)  # 新的在前面
    path = _get_store_path()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(chars, f, ensure_ascii=False, indent=2)
def remove_character(char_data):
    chars = load_characters()
    target_id = char_data.get('id')
    target_username = char_data.get('username')
    target_permalink = char_data.get('permalink')
    target_pic = char_data.get('profile_picture_url')
    filtered = []
    for c in chars:
        if target_id and c.get('id') == target_id:
            continue
        if target_username and c.get('username') == target_username and c.get('permalink', '') == (target_permalink or ''):
            continue
        if target_pic and c.get('profile_picture_url') == target_pic:
            continue
        filtered.append(c)
    path = _get_store_path()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(filtered, f, ensure_ascii=False, indent=2)

def sync_characters_to_file(server_list):
    """将服务器返回的列表与本地列表合并"""
    local_chars = load_characters()
    
    # 建立本地 ID 集合
    local_ids = set()
    for c in local_chars:
        if c.get('id'):
            local_ids.add(c.get('id'))
            
    # 合并
    changed = False
    for s_char in server_list:
        s_id = s_char.get('id')
        if s_id and s_id not in local_ids:
            local_chars.insert(0, s_char)
            local_ids.add(s_id)
            changed = True
            
    if changed:
        path = _get_store_path()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(local_chars, f, ensure_ascii=False, indent=2)
    return changed

class ClickableLabel(QLabel):
    """可点击的标签"""
    clicked = Signal()
    
    def mousePressEvent(self, event):
        """鼠标按下事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

class CreateCharacterThread(QThread):
    finished_signal = Signal(bool, dict, str)

    def __init__(self, api_key, base_url, payload):
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url
        self.payload = payload

        # Register to global registry to prevent GC
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_character_workers'):
                app._active_character_workers = []
            app._active_character_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app and hasattr(app, '_active_character_workers'):
            if self in app._active_character_workers:
                app._active_character_workers.remove(self)
        self.deleteLater()

    def run(self):
        url = f"{self.base_url}/sora/v1/characters"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        # 详细 DEBUG 日志
        print(f"================== Create Character Request ==================")
        print(f"URL: {url}")
        print(f"Headers (Auth masked): {headers.keys()}")
        print(f"Payload: {json.dumps(self.payload, indent=2, ensure_ascii=False)}")
        print(f"Video URL present: {'url' in self.payload}")
        print(f"Task ID present: {'from_task' in self.payload}")
        print(f"===========================================================")

        try:
            # 使用 requests 替代 urllib
            # 增加超时时间到 300秒，并添加 debug 日志
            resp = requests.post(url, json=self.payload, headers=headers, timeout=300, verify=False)
            
            # 检查响应状态
            if resp.status_code == 200:
                json_resp = resp.json()
                print(f"[CreateCharacter] Success: {json_resp}")
                self.finished_signal.emit(True, json_resp, "创建成功")
            else:
                print(f"[CreateCharacter] Failed: {resp.status_code} - {resp.text}")
                self.finished_signal.emit(False, {}, f"HTTP Error {resp.status_code}: {resp.text}")
                
        except requests.exceptions.Timeout:
            print("[CreateCharacter] Request Timed Out (300s)")
            self.finished_signal.emit(False, {}, "请求超时(300秒)，请检查网络或稍后在角色库点击刷新尝试同步。")
        except requests.exceptions.RequestException as e:
            print(f"[CreateCharacter] Request Error: {e}")
            self.finished_signal.emit(False, {}, f"Request Error: {str(e)}")
        except Exception as e:
            print(f"[CreateCharacter] Unknown Error: {e}")
            self.finished_signal.emit(False, {}, f"Unknown Error: {str(e)}")

class SyncCharactersThread(QThread):
    finished_signal = Signal(bool, list, str)

    def __init__(self, api_key, base_url):
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url

        # Register to global registry
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_sync_workers'):
                app._active_sync_workers = []
            app._active_sync_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app and hasattr(app, '_active_sync_workers'):
            if self in app._active_sync_workers:
                app._active_sync_workers.remove(self)
        self.deleteLater()

    def run(self):
        url = f"{self.base_url}/sora/v1/characters"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        print(f"[SyncCharacters] Fetching from: {url}")
        try:
            resp = requests.get(url, headers=headers, timeout=30, verify=False)
            if resp.status_code == 200:
                data = resp.json()
                # data 可能是列表或包含列表的字典
                char_list = []
                if isinstance(data, list):
                    char_list = data
                elif isinstance(data, dict) and "data" in data:
                    char_list = data["data"]
                
                print(f"[SyncCharacters] Success, got {len(char_list)} characters")
                self.finished_signal.emit(True, char_list, "同步成功")
            else:
                print(f"[SyncCharacters] Failed: {resp.status_code} - {resp.text}")
                self.finished_signal.emit(False, [], f"HTTP Error {resp.status_code}")
        except Exception as e:
            print(f"[SyncCharacters] Error: {e}")
            self.finished_signal.emit(False, [], str(e))

class SoraCharacterDialog(QDialog):
    """创建角色对话框 - 参考 sorarenwu 目录重构"""
    character_created = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("创建角色")
        self.resize(600, 750)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #ffffff; }
            QLabel { color: #ffffff; background: transparent; }
            QLineEdit, QSpinBox, QDoubleSpinBox {
                background-color: #2d2d2d; border: 1px solid #404040;
                border-radius: 4px; color: #ffffff; padding: 5px;
            }
            QPushButton {
                background-color: #333333; border: 1px solid #555555;
                border-radius: 4px; color: #ffffff; padding: 6px 16px;
            }
            QPushButton:hover { background-color: #404040; }
        """)
        
        self.timeline_duration = 3.0
        self._preview_update_timer = None
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 1. 视频来源
        src_group = QFrame()
        src_layout = QVBoxLayout(src_group)
        src_layout.setContentsMargins(0, 0, 0, 0)
        
        # URL 输入
        src_layout.addWidget(QLabel("视频URL:"))
        url_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("粘贴Sora生成的视频URL")
        self.url_input.textChanged.connect(self.check_inputs)
        
        self.btn_load = QPushButton("加载预览")
        self.btn_load.clicked.connect(self._load_video)
        
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(self.btn_load)
        src_layout.addLayout(url_layout)
        
        # Task ID 输入
        src_layout.addWidget(QLabel("任务ID (可选, from_task):"))
        self.task_id_input = QLineEdit()
        self.task_id_input.setPlaceholderText("例如: video_xxx")
        src_layout.addWidget(self.task_id_input)
        
        layout.addWidget(src_group)
        
        # 2. 时间控制区
        time_group = QFrame()
        time_layout = QVBoxLayout(time_group)
        time_layout.setContentsMargins(0, 0, 0, 0)
        
        time_label_layout = QHBoxLayout()
        time_label_layout.addWidget(QLabel("截取时间范围 (1.0s - 3.0s):"))
        self.time_display = QLabel("0.0s - 3.0s")
        self.time_display.setStyleSheet("color: #00d4aa; font-weight: bold;")
        time_label_layout.addWidget(self.time_display)
        time_label_layout.addStretch()
        time_layout.addLayout(time_label_layout)
        
        # 微调框
        spin_layout = QHBoxLayout()
        self.start_spin = QDoubleSpinBox()
        self.start_spin.setRange(0, 999)
        self.start_spin.setSingleStep(0.1)
        self.start_spin.setSuffix(" s")
        self.start_spin.valueChanged.connect(self.on_start_time_changed)
        
        self.end_spin = QDoubleSpinBox()
        self.end_spin.setRange(0, 999)
        self.end_spin.setSingleStep(0.1)
        self.end_spin.setValue(3.0)
        self.end_spin.setSuffix(" s")
        self.end_spin.valueChanged.connect(self.on_end_time_changed)
        
        spin_layout.addWidget(QLabel("开始:"))
        spin_layout.addWidget(self.start_spin)
        spin_layout.addWidget(QLabel("结束:"))
        spin_layout.addWidget(self.end_spin)
        spin_layout.addStretch()
        time_layout.addLayout(spin_layout)
        
        # 滑块
        self.slider_start = QSlider(Qt.Horizontal)
        self.slider_start.setRange(0, 30) # 0-3.0s initially
        self.slider_start.valueChanged.connect(self.on_slider_start_changed)
        
        self.slider_end = QSlider(Qt.Horizontal)
        self.slider_end.setRange(0, 30)
        self.slider_end.setValue(30)
        self.slider_end.valueChanged.connect(self.on_slider_end_changed)
        
        time_layout.addWidget(self.slider_start)
        time_layout.addWidget(self.slider_end)
        
        layout.addWidget(time_group)
        
        # 3. 预览区
        preview_label = QLabel("📹 视频预览")
        preview_label.setFont(QFont("Microsoft YaHei UI", 10, QFont.Weight.Bold))
        layout.addWidget(preview_label)
        
        # 视频显示标签（可点击）
        self.video_label = ClickableLabel()
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setMinimumSize(400, 240)
        self.video_label.setStyleSheet("""
            QLabel {
                background-color: #000000;
                border: 1px solid #404040;
                border-radius: 4px;
                color: #888888;
                cursor: pointer;
            }
        """)
        self.video_label.setText("请输入视频URL并点击'加载预览'")
        self.video_label.clicked.connect(self.toggle_video_play)
        layout.addWidget(self.video_label)
        
        # 状态标签
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-size: 10px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        # 视频相关变量
        self.video_cap = None
        self.timer = None
        self.audio_player = None
        self.audio_output = None
        self.is_playing = False
        self._updating_preview = False
        self.video_temp_file = None
        
        # 4. 底部按钮
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setFixedSize(100, 36)
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_create = QPushButton("创建角色")
        self.btn_create.setFixedSize(100, 36)
        self.btn_create.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0078d4, stop:1 #106ebe);
                border: none; font-weight: bold;
            }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #106ebe, stop:1 #005a9e); }
            QPushButton:disabled { background: #404040; color: #808080; }
        """)
        self.btn_create.clicked.connect(self._do_create)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_create)
        layout.addLayout(btn_layout)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar { height: 4px; background: #3d3d3d; border: none; } QProgressBar::chunk { background: #00d4aa; }")
        self.progress_bar.setRange(0, 0)
        layout.insertWidget(layout.count()-1, self.progress_bar)

    def check_inputs(self):
        # 简单的校验逻辑
        url = self.url_input.text().strip()
        task_id = self.task_id_input.text().strip()
        self.btn_create.setEnabled(bool(url or task_id))

    def on_start_time_changed(self, val):
        self.slider_start.blockSignals(True)
        self.slider_start.setValue(int(val * 10))
        self.slider_start.blockSignals(False)
        self.update_time_display()
        # 联动结束时间
        if self.end_spin.value() <= val:
             self.end_spin.setValue(val + 1.0)

    def on_end_time_changed(self, val):
        self.slider_end.blockSignals(True)
        self.slider_end.setValue(int(val * 10))
        self.slider_end.blockSignals(False)
        self.update_time_display()

    def on_slider_start_changed(self, val):
        self.start_spin.blockSignals(True)
        self.start_spin.setValue(val / 10.0)
        self.start_spin.blockSignals(False)
        self.update_time_display()
        # 确保结束滑块在开始滑块之后
        if self.slider_end.value() <= val:
            self.slider_end.setValue(val + 10)

    def on_slider_end_changed(self, val):
        self.end_spin.blockSignals(True)
        self.end_spin.setValue(val / 10.0)
        self.end_spin.blockSignals(False)
        self.update_time_display()
        # 确保开始滑块在结束滑块之前
        if self.slider_start.value() >= val:
            self.slider_start.setValue(val - 10)

    def update_time_display(self):
        s = self.start_spin.value()
        e = self.end_spin.value()
        self.time_display.setText(f"{s:.1f}s - {e:.1f}s")
        self.schedule_preview_update()

    def schedule_preview_update(self):
        """安排预览更新（防抖）"""
        if self._preview_update_timer is not None:
            try:
                self._preview_update_timer.stop()
                self._preview_update_timer.deleteLater()
            except:
                pass
        
        self._preview_update_timer = QTimer()
        self._preview_update_timer.setSingleShot(True)
        self._preview_update_timer.timeout.connect(self.update_video_preview)
        self._preview_update_timer.start(500)

    def set_timeline_duration(self, duration: float):
        try:
            duration = max(1.0, duration)
            self.timeline_duration = duration
            max_ticks = int(duration * 10)
            self.slider_start.blockSignals(True)
            self.slider_end.blockSignals(True)
            self.slider_start.setRange(0, max_ticks)
            self.slider_end.setRange(0, max_ticks)
            cur_start = min(self.slider_start.value(), max_ticks)
            cur_end = min(self.slider_end.value(), max_ticks)
            if cur_end - cur_start < 10:
                cur_end = min(max_ticks, cur_start + 10)
            self.slider_start.setValue(cur_start)
            self.slider_end.setValue(cur_end)
            self.slider_start.blockSignals(False)
            self.slider_end.blockSignals(False)
        except Exception as e:
            print(f"[警告] 设置时间轴失败: {e}")

    def sync_slider_from_spin(self):
        try:
            start_tick = int(self.start_spin.value() * 10)
            end_tick = int(self.end_spin.value() * 10)
            if end_tick - start_tick < 10:
                end_tick = start_tick + 10
            if end_tick - start_tick > 30:
                end_tick = start_tick + 30
            max_tick = self.slider_end.maximum()
            if end_tick > max_tick:
                end_tick = max_tick
                start_tick = max(0, end_tick - 30)
            self.slider_start.blockSignals(True)
            self.slider_end.blockSignals(True)
            self.slider_start.setValue(start_tick)
            self.slider_end.setValue(end_tick)
            self.slider_start.blockSignals(False)
            self.slider_end.blockSignals(False)
        except Exception as e:
            print(f"[警告] 同步滑杆失败: {e}")

    def _find_ffmpeg(self):
        import shutil
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 检查常见位置
            paths = [
                os.path.join(current_dir, 'ffmpeg', 'bin', 'ffmpeg.exe'),
                os.path.join(current_dir, 'ffmpeg', 'ffmpeg.exe'),
                os.path.join(os.path.dirname(current_dir), 'ffmpeg', 'bin', 'ffmpeg.exe'),
            ]
            for path in paths:
                if os.path.exists(path):
                    return path
            
            # 检查系统PATH
            ffmpeg_sys = shutil.which('ffmpeg')
            if ffmpeg_sys:
                return ffmpeg_sys
        except:
            pass
        return None

    def _http_headers(self):
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
        }

    def _show_debug_dialog(self, title, headline, details):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(680, 420)
        dlg.setStyleSheet("background: #1e1e1e; color: white;")
        l = QVBoxLayout(dlg)

        lbl = QLabel(headline)
        lbl.setStyleSheet("color: #ef4444; font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        l.addWidget(lbl)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(details)
        text.setStyleSheet("""
            QTextEdit {
                background: #2d2d2d; color: #e5e5e5; font-family: Consolas, monospace;
                border: 1px solid #3d3d3d; border-radius: 4px; padding: 8px; font-size: 13px;
            }
        """)
        l.addWidget(text)

        btn_layout = QHBoxLayout()
        btn_copy = QPushButton("复制错误信息")
        btn_copy.setCursor(Qt.PointingHandCursor)
        btn_copy.setStyleSheet("""
            QPushButton { background: #3d3d3d; border: 1px solid #555; padding: 6px 12px; border-radius: 4px; color: white; }
            QPushButton:hover { background: #4d4d4d; }
        """)

        def _copy():
            text.selectAll()
            text.copy()
            orig_text = btn_copy.text()
            btn_copy.setText("✅ 已复制")
            QTimer.singleShot(2000, lambda: btn_copy.setText(orig_text))

        btn_copy.clicked.connect(_copy)
        btn_layout.addWidget(btn_copy)
        btn_layout.addStretch()

        btn_close = QPushButton("关闭")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setFixedSize(100, 36)
        btn_close.setStyleSheet("""
            QPushButton { background: #ef4444; border: none; border-radius: 4px; color: white; font-weight: bold; }
            QPushButton:hover { background: #dc2626; }
        """)
        btn_close.clicked.connect(dlg.accept)
        btn_layout.addWidget(btn_close)

        l.addLayout(btn_layout)
        dlg.exec()

    def _download_video_to_path(self, video_url, file_path, timeout, retries):
        import os
        import time
        import traceback

        last_error = None
        for attempt in range(1, max(1, int(retries)) + 1):
            try:
                with requests.get(
                    video_url,
                    stream=True,
                    timeout=timeout,
                    verify=False,
                    headers=self._http_headers(),
                ) as resp:
                    resp.raise_for_status()
                    with open(file_path, 'wb') as f:
                        for chunk in resp.iter_content(chunk_size=262144):
                            if chunk:
                                f.write(chunk)
                return
            except Exception as e:
                last_error = e
                try:
                    if os.path.exists(file_path):
                        os.unlink(file_path)
                except Exception:
                    pass
                if attempt < retries:
                    time.sleep(1.5 * attempt)
                else:
                    details = (
                        f"URL: {video_url}\n"
                        f"timeout: {timeout}\n"
                        f"retries: {retries}\n"
                        f"attempt: {attempt}\n\n"
                        f"{repr(e)}\n\n"
                        f"{traceback.format_exc()}"
                    )
                    raise RuntimeError(details) from e

        raise RuntimeError(str(last_error))

    def _download_video_to_tempfile(self, video_url, timeout=(15, 180), retries=3):
        temp_video = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        temp_path = temp_video.name
        temp_video.close()
        try:
            self._download_video_to_path(video_url, temp_path, timeout=timeout, retries=retries)
            return temp_path
        except Exception:
            try:
                import os
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except Exception:
                pass
            raise

    def load_video_preview(self):
        video_url = self.url_input.text().strip()
        if not video_url:
            QMessageBox.warning(self, "提示", "请先输入视频URL")
            return
        
        try:
            import cv2
            
            self.status_label.setText("正在下载视频...")
            self.btn_load.setEnabled(False)
            
            temp_path = self._download_video_to_tempfile(video_url, timeout=(15, 240), retries=3)
            
            # 释放旧的视频捕获
            if self.video_cap is not None:
                self.video_cap.release()
            
            # 打开视频
            self.video_cap = cv2.VideoCapture(temp_path)
            
            if not self.video_cap.isOpened():
                raise Exception("无法打开视频文件")
            
            # 保存临时文件路径
            self.video_temp_file = temp_path
            
            # 获取视频帧率
            self.video_fps = self.video_cap.get(cv2.CAP_PROP_FPS)
            if self.video_fps <= 0:
                self.video_fps = 30

            # 计算时长并更新时间轴
            frame_count = self.video_cap.get(cv2.CAP_PROP_FRAME_COUNT)
            duration = frame_count / self.video_fps if frame_count > 0 else 3.0
            duration = max(duration, 1.0)
            self.set_timeline_duration(min(duration, 300))
            self.start_spin.setValue(0.0)
            self.end_spin.setValue(min(3.0, duration))
            self.sync_slider_from_spin()
            
            self.status_label.setText(f"✅ 视频已加载 (FPS: {self.video_fps:.1f}, 时长≈{duration:.1f}s)")
            self.btn_load.setEnabled(True)
            
            # 自动播放预览
            self.play_video_segment()
            
        except Exception as e:
            self.status_label.setText(f"❌ 加载失败: {str(e)}")
            self.btn_load.setEnabled(True)
            self._show_debug_dialog(
                "加载视频失败 - Debug Info",
                "❌ 加载视频失败",
                str(e),
            )

    def toggle_video_play(self):
        if not hasattr(self, 'video_cap') or self.video_cap is None or not self.video_cap.isOpened():
            return
        
        if self.is_playing:
            self.pause_video()
        else:
            self.play_video_segment()

    def pause_video(self):
        try:
            if hasattr(self, 'timer') and self.timer is not None and self.timer.isActive():
                self.timer.stop()
            
            if hasattr(self, 'audio_player') and self.audio_player is not None:
                try:
                    self.audio_player.stop()
                except:
                    pass
            
            self.is_playing = False
            self.status_label.setText("⏸ 已暂停 (点击画面继续)")
        except Exception as e:
            print(f"[错误] 暂停视频失败: {e}")
            self.is_playing = False

    def _load_video(self):
        self.load_video_preview()

    def update_video_preview(self):
        if self.video_cap is not None and self.video_cap.isOpened():
            try:
                if hasattr(self, '_updating_preview') and self._updating_preview:
                    return
                
                self._updating_preview = True
                self.is_playing = False
                
                if hasattr(self, 'timer') and self.timer is not None:
                    try:
                        if self.timer.isActive():
                            self.timer.stop()
                        try:
                            self.timer.timeout.disconnect()
                        except:
                            pass
                        self.timer.deleteLater()
                        self.timer = None
                    except:
                        pass
                
                if hasattr(self, 'audio_player') and self.audio_player is not None:
                    try:
                        try:
                            self.audio_player.positionChanged.disconnect()
                        except:
                            pass
                        try:
                            self.audio_player.mediaStatusChanged.disconnect()
                        except:
                            pass
                        self.audio_player.stop()
                        self.audio_player.deleteLater()
                        self.audio_player = None
                        self.audio_output = None
                    except:
                        pass
                
                QTimer.singleShot(100, self._delayed_play)
                
            except Exception as e:
                print(f"[错误] 更新预览失败: {e}")
                self._updating_preview = False

    def _delayed_play(self):
        try:
            self._updating_preview = False
            self.play_video_segment()
        except Exception as e:
            print(f"[错误] 延迟播放失败: {e}")
            self._updating_preview = False

    def play_video_segment(self):
        if self.video_cap is None or not self.video_cap.isOpened():
            return
        
        try:
            import cv2
            
            start_sec = self.start_spin.value()
            end_sec = self.end_spin.value()
            
            if start_sec >= end_sec:
                return
            
            # 音频处理
            if self.audio_player is not None:
                try:
                    self.audio_player.stop()
                    try:
                        self.audio_player.positionChanged.disconnect()
                    except:
                        pass
                    try:
                        self.audio_player.mediaStatusChanged.disconnect()
                    except:
                        pass
                except:
                    pass
                self.audio_player = None
                self.audio_output = None
            
            self.audio_player = QMediaPlayer()
            self.audio_output = QAudioOutput()
            self.audio_player.setAudioOutput(self.audio_output)
            self.audio_ready_handled = False
            
            if hasattr(self, 'video_temp_file') and self.video_temp_file:
                self.audio_player.setSource(QUrl.fromLocalFile(self.video_temp_file))
                self.audio_start_time = start_sec * 1000
                self.audio_end_time = end_sec * 1000
                self.audio_player.positionChanged.connect(self.check_audio_position)
                self.audio_player.mediaStatusChanged.connect(self.on_audio_ready)
            
            # 视频处理
            start_frame = int(start_sec * self.video_fps)
            end_frame = int(end_sec * self.video_fps)
            
            self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            ret, first_frame = self.video_cap.read()
            if ret:
                frame_rgb = cv2.cvtColor(first_frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame_rgb.shape
                bytes_per_line = ch * w
                q_image = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(q_image)
                scaled_pixmap = pixmap.scaled(
                    self.video_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.video_label.setPixmap(scaled_pixmap)
            
            self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            self.status_label.setText("▶ 播放中... (点击画面暂停)")
            
            self.current_frame = start_frame
            self.end_play_frame = end_frame
            
            import time
            self.play_start_time = time.time()
            self.video_start_sec = start_sec
            
            if self.timer is not None:
                self.timer.stop()
            
            self.timer = QTimer()
            self.timer.timeout.connect(self.play_next_frame)
            self.timer.start(10)
            self.is_playing = True
            
        except Exception as e:
            self.status_label.setText(f"❌ 播放失败：{str(e)}")
            print(f"[错误] 播放失败: {e}")

    def on_audio_ready(self, status):
        try:
            if status == QMediaPlayer.MediaStatus.LoadedMedia:
                if hasattr(self, 'audio_ready_handled') and self.audio_ready_handled:
                    return
                if not hasattr(self, 'audio_start_time'):
                    return
                self.audio_player.setPosition(int(self.audio_start_time))
                self.audio_player.play()
                self.audio_ready_handled = True
                try:
                    self.audio_player.mediaStatusChanged.disconnect(self.on_audio_ready)
                except:
                    pass
        except:
            pass

    def check_audio_position(self, position):
        if hasattr(self, 'audio_end_time') and position >= self.audio_end_time:
            if self.audio_player is not None:
                try:
                    self.audio_player.positionChanged.disconnect(self.check_audio_position)
                except:
                    pass
                try:
                    self.audio_player.mediaStatusChanged.disconnect(self.on_audio_ready)
                except:
                    pass
                self.audio_player.stop()

    def play_next_frame(self):
        try:
            import cv2
            import time
            
            start_frame = int(self.video_start_sec * self.video_fps)
            elapsed_time = time.time() - self.play_start_time
            target_frame = int(start_frame + elapsed_time * self.video_fps)
            
            if target_frame >= self.end_play_frame:
                self.timer.stop()
                if self.audio_player is not None:
                    try:
                        self.audio_player.positionChanged.disconnect(self.check_audio_position)
                    except:
                        pass
                    try:
                        self.audio_player.mediaStatusChanged.disconnect(self.on_audio_ready)
                    except:
                        pass
                    self.audio_player.stop()
                self.is_playing = False
                self.status_label.setText("✅ 播放完成 (点击画面重新播放)")
                return
            
            if target_frame <= self.current_frame:
                return
            
            self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = self.video_cap.read()
            
            if ret:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame_rgb.shape
                bytes_per_line = ch * w
                q_image = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(q_image)
                scaled_pixmap = pixmap.scaled(
                    self.video_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.video_label.setPixmap(scaled_pixmap)
                self.current_frame = target_frame
            else:
                self.timer.stop()
                self.is_playing = False
                
        except Exception as e:
            self.timer.stop()
            self.is_playing = False
            self.status_label.setText(f"❌ 播放错误: {str(e)}")

    def closeEvent(self, event):
        try:
            self._updating_preview = False
            if hasattr(self, '_preview_update_timer') and self._preview_update_timer:
                try:
                    self._preview_update_timer.stop()
                except:
                    pass
            
            if hasattr(self, 'timer') and self.timer:
                try:
                    self.timer.stop()
                except:
                    pass
            
            if hasattr(self, 'audio_player') and self.audio_player:
                try:
                    self.audio_player.stop()
                    self.audio_player.deleteLater()
                except:
                    pass
                self.audio_player = None
                self.audio_output = None
            
            if hasattr(self, 'video_cap') and self.video_cap:
                try:
                    self.video_cap.release()
                except:
                    pass
            
            if hasattr(self, 'video_temp_file') and self.video_temp_file:
                try:
                    import os
                    import time
                    if os.path.exists(self.video_temp_file):
                        time.sleep(0.5)
                        os.unlink(self.video_temp_file)
                except:
                    pass
        except:
            pass
        super().closeEvent(event)

    def get_project_folder(self):
        """获取项目文件夹路径"""
        try:
            # 优先使用 ProjectManager
            from components.sora_video_enhancements import ProjectManager
            project_manager = ProjectManager()
            project_folder = project_manager.get_project_folder()
            
            if project_folder:
                return str(project_folder)
            
            print("[警告] ProjectManager返回空路径")
            return None
            
        except (ImportError, ModuleNotFoundError):
            # 组件不存在，静默使用默认路径
            return None
        except Exception as e:
            print(f"[错误] 获取项目文件夹失败: {str(e)}")
            return None

    def save_video_clip(self, video_source_path, video_url, start, end, save_folder, filename_hint):
        """裁剪选定时间段到本地文件夹（characters/videos）"""
        import tempfile
        import os
        import subprocess
        
        duration = max(0.0, end - start)
        if duration <= 0:
            return None
        # 保障最小1秒、最大3秒
        duration = max(1.0, min(duration, 3.0))

        # 准备源文件：优先使用已有临时文件，否则下载
        source_path = video_source_path
        temp_created = False
        if not source_path or not os.path.exists(source_path):
            try:
                print("[裁剪] 未找到本地临时视频，开始下载...")
                temp_video = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
                source_path = temp_video.name
                temp_video.close()
                self._download_video_to_path(video_url, source_path, timeout=(15, 240), retries=3)
                temp_created = True
            except Exception as e:
                print(f"[裁剪] 下载源视频失败: {e}")
                return None

        # 准备输出路径
        safe_name = filename_hint.replace('@', '') if filename_hint else 'clip'
        safe_name = safe_name if safe_name else 'clip'
        clip_folder = os.path.join(save_folder, safe_name)
        os.makedirs(clip_folder, exist_ok=True)
        clip_filename = f"{safe_name}_{start:.1f}-{start+duration:.1f}s.mp4"
        clip_path = os.path.join(clip_folder, clip_filename)

        # ffmpeg 裁剪
        ffmpeg_path = self._find_ffmpeg()
        if not ffmpeg_path:
            print("[裁剪] 未找到FFmpeg，跳过裁剪")
            if temp_created and source_path and os.path.exists(source_path):
                os.unlink(source_path)
            return None

        cmd = [
            ffmpeg_path,
            '-ss', str(start),
            '-i', source_path,
            '-t', str(duration),
            '-c', 'copy',
            '-y',
            clip_path
        ]
        print(f"[裁剪] 执行命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        if result.returncode != 0:
            print(f"[裁剪] 失败: {result.stderr}")
            if temp_created and source_path and os.path.exists(source_path):
                os.unlink(source_path)
            return None

        if temp_created and source_path and os.path.exists(source_path):
            os.unlink(source_path)
        return clip_path

    def save_character_to_file(self, character_info):
        """保存角色信息到项目文件夹的txt文件"""
        try:
            import os
            import json
            from datetime import datetime
            
            print(f"\\n[保存角色] ========== 开始保存 ==========")
            print(f"[保存角色] 接收到的角色信息: {character_info}")
            
            # 获取角色信息
            character_name = character_info.get("username", "未知")
            character_id = character_info.get("id", "")
            character_url = character_info.get("permalink", "")
            video_url = self.url_input.text().strip()
            # 保留1位小数的时间戳格式
            timestamps = f"{self.start_spin.value():.1f},{self.end_spin.value():.1f}"
            
            print(f"[保存角色] 角色名: {character_name}")
            print(f"[保存角色] 视频URL: {video_url}")
            print(f"[保存角色] 时间戳: {timestamps}")
            
            # 获取项目文件夹路径
            project_folder = self.get_project_folder()
            if not project_folder:
                # 尝试使用默认路径（如果是独立运行）
                project_folder = os.path.join(_get_app_root(), 'sora_characters')
                os.makedirs(project_folder, exist_ok=True)
                print(f"[提示] 使用默认存储路径: {project_folder}")
            
            print(f"[保存角色] 项目文件夹: {project_folder}")
            
            # 创建角色文件夹和图片文件夹
            characters_folder = os.path.join(project_folder, "characters")
            images_folder = os.path.join(characters_folder, "images")
            
            print(f"[保存角色] 角色文件夹: {characters_folder}")
            print(f"[保存角色] 图片文件夹: {images_folder}")
            
            try:
                os.makedirs(images_folder, exist_ok=True)
                print(f"[保存角色] ✓ 文件夹创建成功")
            except Exception as e:
                print(f"[保存角色] ✗ 文件夹创建失败: {e}")
                raise
            
            # 生成文件名（使用 @username，保留点号）
            import re
            safe_name = character_name.replace("@", "")
            safe_name = re.sub(r'[<>:"/\\\\|?*]', '', safe_name)
            filename = f"@{safe_name}.txt"
            filepath = os.path.join(characters_folder, filename)
            
            print(f"[保存角色] txt文件路径: {filepath}")
            
            # 提取第一帧图片
            thumbnail_path = None
            thumbnail_filename = None
            try:
                print(f"[保存角色] 开始提取缩略图...")
                thumbnail_path, thumbnail_filename = self.extract_first_frame(video_url, images_folder, character_name)
                print(f"[保存角色] ✓ 缩略图提取成功: {thumbnail_filename}")
            except Exception as e:
                print(f"[保存角色] ✗ 提取缩略图失败: {e}")
                import traceback
                traceback.print_exc()

            # 保存裁剪片段到 characters/videos 下
            try:
                videos_folder = os.path.join(characters_folder, "videos")
                os.makedirs(videos_folder, exist_ok=True)
                clip_path = self.save_video_clip(
                    video_source_path=getattr(self, "video_temp_file", None),
                    video_url=video_url,
                    start=self.start_spin.value(),
                    end=self.end_spin.value(),
                    save_folder=videos_folder,
                    filename_hint=safe_name,
                )
                if clip_path:
                    print(f"[保存角色] ✓ 已裁剪片段: {clip_path}")
            except Exception as e:
                print(f"[保存角色] ✗ 裁剪视频片段失败: {e}")
                import traceback
                traceback.print_exc()
            
            # 写入文件
            try:
                print(f"[保存角色] 开始写入txt文件...")
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write("=" * 50 + "\\n")
                    f.write("Sora 角色信息\\n")
                    f.write("=" * 50 + "\\n\\n")
                    
                    f.write(f"角色名称: @{character_name}\\n")
                    f.write(f"角色ID: {character_id}\\n")
                    f.write(f"角色主页: {character_url}\\n")
                    if thumbnail_filename:
                        f.write(f"缩略图: images/{thumbnail_filename}\\n")
                    else:
                        f.write(f"缩略图: 无\\n")
                    f.write("\\n")
                    
                    f.write("=" * 50 + "\\n")
                    f.write("创建信息\\n")
                    f.write("=" * 50 + "\\n\\n")
                    f.write(f"视频源: {video_url}\\n")
                    f.write(f"截取时间: {timestamps}\\n")
                    f.write(f"创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\\n\\n")
                    
                    f.write("=" * 50 + "\\n")
                    f.write("使用方法\\n")
                    f.write("=" * 50 + "\\n\\n")
                    
                    f.write(f"在Sora提示词中使用: @{character_name}\\n")
                    f.write(f"例如: A video of @{character_name} walking in the park\\n\\n")
                    
                    f.write("=" * 50 + "\\n")
                    f.write("完整响应数据\\n")
                    f.write("=" * 50 + "\\n\\n")
                    
                    f.write(json.dumps(character_info, ensure_ascii=False, indent=2))
                
                # 验证文件是否真的写入了
                if os.path.exists(filepath):
                    file_size = os.path.getsize(filepath)
                    print(f"[保存角色] ✓ txt文件写入成功: {filepath} ({file_size} 字节)")
                else:
                    print(f"[保存角色] ✗ txt文件未创建！")
                    raise Exception("文件写入后不存在")
                
            except Exception as e:
                print(f"[保存角色] ✗ 写入txt文件失败: {e}")
                raise
            
            print(f"[保存角色] ========== 保存完成 ==========\\n")
            
            # 显示保存成功提示
            QMessageBox.information(
                self,
                "保存成功",
                f"角色信息已保存到:\\n{filepath}\\n\\n在提示词中使用: @{character_name}"
            )
            
        except Exception as e:
            print(f"[错误] 保存角色信息失败: {str(e)}")
            try:
                import traceback
                self._show_debug_dialog(
                    "保存失败 - Debug Info",
                    "❌ 保存角色信息失败",
                    f"{repr(e)}\n\n{traceback.format_exc()}",
                )
            except Exception:
                QMessageBox.warning(
                    self,
                    "保存失败",
                    f"角色创建成功,但保存到文件时出错:\n{str(e)}\n\n请手动记录角色信息"
                )

    def extract_first_frame(self, video_url, save_folder, character_name):
        import tempfile
        import os
        import subprocess
        
        try:
            start_second = self.start_spin.value()
            temp_video_path = getattr(self, 'video_temp_file', None)
            temp_created = False
            
            if not temp_video_path or not os.path.exists(temp_video_path):
                print(f"[提取帧] 未找到本地缓存，开始下载视频: {video_url}")
                temp_video = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
                temp_video_path = temp_video.name
                temp_video.close()
                self._download_video_to_path(video_url, temp_video_path, timeout=(15, 240), retries=3)
                temp_created = True
            
            safe_name = character_name.replace("@", "")
            import re
            safe_name = re.sub(r'[<>:"/\\\\|?*]', '', safe_name)
            
            thumbnail_path_png = os.path.join(save_folder, f"@{safe_name}.png")
            thumbnail_path_jpg = os.path.join(save_folder, f"@{safe_name}.jpg")
            os.makedirs(save_folder, exist_ok=True)
            
            ffmpeg_path = self._find_ffmpeg()
            if not ffmpeg_path:
                raise Exception("未找到FFmpeg")
            
            # 优先尝试保存为PNG
            thumbnail_path = thumbnail_path_png
            thumbnail_filename = f"@{safe_name}.png"
            
            cmd = [
                ffmpeg_path,
                '-ss', str(start_second),
                '-i', temp_video_path,
                '-vframes', '1',
                '-y',
                thumbnail_path
            ]
            
            subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            # 检查PNG文件是否生成成功
            if not os.path.exists(thumbnail_path) or os.path.getsize(thumbnail_path) == 0:
                print(f"[提取帧] PNG格式失败，尝试JPEG格式")
                thumbnail_path = thumbnail_path_jpg
                thumbnail_filename = f"@{safe_name}.jpg"
                cmd = [
                    ffmpeg_path,
                    '-ss', str(start_second),
                    '-i', temp_video_path,
                    '-vframes', '1',
                    '-q:v', '2',
                    '-y',
                    thumbnail_path
                ]
                subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            if not os.path.exists(thumbnail_path):
                raise Exception("FFmpeg执行完成但未生成图片")
            
            # 清理临时文件
            try:
                import time
                time.sleep(0.5)
                if temp_created and os.path.exists(temp_video_path):
                    os.unlink(temp_video_path)
            except:
                pass
                
            return thumbnail_path, thumbnail_filename
            
        except Exception as e:
            print(f"[错误] 提取帧失败: {e}")
            raise

    def _do_create(self):
        config = load_config()
        api_key = config.get('api_key', '')
        base_url = config.get('base_url', '').rstrip('/')
        
        if not api_key:
            QMessageBox.warning(self, "错误", "请先在Sora2配置中设置API Key")
            return
            
        url = self.url_input.text().strip()
        task_id = self.task_id_input.text().strip()
        
        if not url and not task_id:
            QMessageBox.warning(self, "错误", "必须提供视频URL或任务ID")
            return

        # URL 校验 (参考 sorarenwu)
        if url:
            if not (url.startswith("http://") or url.startswith("https://")):
                QMessageBox.warning(self, "输入错误", "请输入有效的URL（以http://或https://开头）")
                return

            if "catbox.moe" in url.lower() or "cloudflare" in url.lower():
                reply = QMessageBox.question(
                    self,
                    "URL提示",
                    "检测到可能存在访问限制的视频源。建议使用Sora生成的视频URL或可直链访问的源，是否继续？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return
            
        start = self.start_spin.value()
        end = self.end_spin.value()
        
        if end <= start:
            QMessageBox.warning(self, "错误", "结束时间必须大于开始时间")
            return
        if end - start > 3.0:
            QMessageBox.warning(self, "错误", "时间跨度不能超过3秒")
            return
        if end - start < 1.0:
            QMessageBox.warning(self, "错误", "时间跨度不能小于1秒")
            return
            
        payload = {
            "timestamps": f"{start:.1f},{end:.1f}"
        }
        
        # 优先使用 task_id 以避免 URL 访问失败 (500 Error)
        if task_id:
            payload["from_task"] = task_id
        elif url:
            payload["url"] = url
            
        self.btn_create.setEnabled(False)
        self.btn_create.setText("创建中...")
        self.progress_bar.setVisible(True)
        
        self.thread = CreateCharacterThread(api_key, base_url, payload)
        self.thread.finished_signal.connect(self._on_finished)
        self.thread.start()

    def _on_finished(self, success, data, msg):
        self.btn_create.setEnabled(True)
        self.btn_create.setText("创建角色")
        self.progress_bar.setVisible(False)
        
        if success:
            # 保存角色信息到文件
            self.save_character_to_file(data)
            
            save_character(data)
            self.character_created.emit(data)
            
            # 成功弹窗
            dlg = QDialog(self)
            dlg.setWindowTitle("角色创建成功")
            dlg.resize(400, 200)
            dlg.setStyleSheet("background: #1e1e1e; color: white;")
            l = QVBoxLayout(dlg)
            
            info = QLabel(f"✅ 角色创建成功\n\n角色名: @{data.get('username', '')}\nID: {data.get('id', '')}")
            info.setStyleSheet("font-size: 14px; line-height: 1.5;")
            l.addWidget(info)
            
            link = data.get('permalink', '')
            if link:
                link_btn = QPushButton("🔗 查看角色主页")
                link_btn.setStyleSheet("background: #2d2d2d; border: 1px solid #3d3d3d; padding: 8px; border-radius: 4px; color: #3b82f6;")
                link_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(link)))
                l.addWidget(link_btn)
                
            ok_btn = QPushButton("完成")
            ok_btn.setStyleSheet("background: #3b82f6; border: none; padding: 8px; border-radius: 4px; color: white;")
            ok_btn.clicked.connect(dlg.accept)
            l.addWidget(ok_btn)
            
            dlg.exec()
            self.accept()
        else:
            # 增强错误处理
            error_msg = msg
            
            # 尝试从 msg 中解析更详细的错误（如果是JSON字符串）
            try:
                if msg.startswith("{"):
                    err_json = json.loads(msg)
                    if "message" in err_json:
                        error_msg = err_json["message"]
            except:
                pass

            # 友好的错误提示匹配
            lower_msg = error_msg.lower()
            if "download file failed" in lower_msg:
                error_msg = (
                    "视频下载失败！\n"
                    "可能原因：\n"
                    "• 视频URL无法访问或需要特殊权限\n"
                    "• 视频文件过大或格式不支持\n"
                    "• 网络连接问题\n"
                    "建议：\n"
                    "• 使用Sora生成的视频URL\n"
                    "• 或上传到稳定的视频托管服务"
                )
            elif "503" in lower_msg or "no_available_channel" in lower_msg:
                error_msg = (
                    "通道不可用或当前分组没有可用频道，请稍后再试或更换分组/套餐。\n"
                    f"原始错误: {error_msg}"
                )
            elif "400" in lower_msg:
                error_msg = f"请求参数错误\n{error_msg}"
            
            # 错误 debug 弹窗
            dlg = QDialog(self)
            dlg.setWindowTitle("错误 - Debug Info")
            dlg.resize(600, 400)
            dlg.setStyleSheet("background: #1e1e1e; color: white;")
            l = QVBoxLayout(dlg)
            
            lbl = QLabel("❌ 创建失败")
            lbl.setStyleSheet("color: #ef4444; font-size: 18px; font-weight: bold; margin-bottom: 10px;")
            l.addWidget(lbl)
            
            text = QTextEdit()
            text.setReadOnly(True)
            text.setPlainText(error_msg)
            text.setStyleSheet("""
                QTextEdit {
                    background: #2d2d2d; color: #e5e5e5; font-family: Consolas, monospace; 
                    border: 1px solid #3d3d3d; border-radius: 4px; padding: 8px; font-size: 13px;
                }
            """)
            l.addWidget(text)
            
            btn_layout = QHBoxLayout()
            btn_copy = QPushButton("复制错误信息")
            btn_copy.setCursor(Qt.PointingHandCursor)
            btn_copy.setStyleSheet("""
                QPushButton { background: #3d3d3d; border: 1px solid #555; padding: 6px 12px; border-radius: 4px; color: white; }
                QPushButton:hover { background: #4d4d4d; }
            """)
            def _copy():
                text.selectAll()
                text.copy()
                orig_text = btn_copy.text()
                btn_copy.setText("✅ 已复制")
                QTimer.singleShot(2000, lambda: btn_copy.setText(orig_text))
            btn_copy.clicked.connect(_copy)
            btn_layout.addWidget(btn_copy)
            
            btn_layout.addStretch()
            
            btn_close = QPushButton("关闭")
            btn_close.setCursor(Qt.PointingHandCursor)
            btn_close.setFixedSize(100, 36)
            btn_close.setStyleSheet("""
                QPushButton { background: #ef4444; border: none; border-radius: 4px; color: white; font-weight: bold; }
                QPushButton:hover { background: #dc2626; }
            """)
            btn_close.clicked.connect(dlg.accept)
            btn_layout.addWidget(btn_close)
            
            l.addLayout(btn_layout)
            dlg.exec()

class _AvatarFetchThread(QThread):
    fetched = Signal(bytes)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        # Register to global registry
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_avatar_fetch_workers'):
                app._active_avatar_fetch_workers = []
            app._active_avatar_fetch_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app and hasattr(app, '_active_avatar_fetch_workers'):
            if self in app._active_avatar_fetch_workers:
                app._active_avatar_fetch_workers.remove(self)
        self.deleteLater()
        self._url = url
        
        # 注册到全局引用列表，防止被垃圾回收
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_avatar_fetch_workers'):
                app._active_avatar_fetch_workers = []
            app._active_avatar_fetch_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        """清理 worker 引用"""
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app and hasattr(app, '_active_avatar_fetch_workers'):
            if self in app._active_avatar_fetch_workers:
                app._active_avatar_fetch_workers.remove(self)
        self.deleteLater()

    def run(self):
        try:
            print(f"[DEBUG] Fetching avatar from: {self._url}")
            resp = requests.get(self._url, timeout=10, verify=False)
            if resp.status_code == 200:
                print(f"[DEBUG] Avatar fetched successfully: {len(resp.content)} bytes")
                self.fetched.emit(resp.content or b'')
            else:
                print(f"[DEBUG] Failed to fetch avatar: {resp.status_code}")
                self.fetched.emit(b'')
        except Exception as e:
            print(f"[DEBUG] Error fetching avatar: {str(e)}")
            self.fetched.emit(b'')

class SoraCharacterCard(QFrame):
    """单个角色卡片 - 参考 sora_character_card.py"""
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.data = data
        from PySide6.QtCore import Signal as _Signal
        if not hasattr(self.__class__, 'delete_requested'):
            self.__class__.delete_requested = _Signal(dict)
        print(f"[DEBUG] Creating card for: {data.get('username')} - Image: {data.get('profile_picture_url')}")
        self.setFixedSize(160, 200)
        self.setStyleSheet("""
            QFrame { background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 8px; }
            QFrame:hover { border-color: #3b82f6; background: #ffffff; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        
        # 头像
        self.avatar_lbl = QLabel()
        self.avatar_lbl.setFixedSize(142, 142)
        self.avatar_lbl.setStyleSheet("background: #e9ecef; border-radius: 4px;")
        self.avatar_lbl.setScaledContents(True)
        layout.addWidget(self.avatar_lbl)
        
        # 加载图片
        avatar_url = data.get('profile_picture_url', '')
        if avatar_url:
            self._avatar_thread = _AvatarFetchThread(avatar_url, self)
            self._avatar_thread.fetched.connect(self._set_avatar_bytes)
            self._avatar_thread.start()
            
        # 名字
        name_lbl = QLabel(f"@{data.get('username', 'Unknown')}")
        name_lbl.setStyleSheet("font-weight: bold; font-size: 14px; color: #333; border: none; background: transparent;")
        name_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(name_lbl)

    def _set_avatar_bytes(self, content: bytes):
        try:
            if not content:
                return
            pix = QPixmap()
            pix.loadFromData(content)
            self.avatar_lbl.setPixmap(pix)
        except Exception:
            pass
        
    def _load_image(self, url, label):
        try:
            resp = requests.get(url, timeout=10, verify=False)
            if resp.status_code == 200:
                pix = QPixmap()
                pix.loadFromData(resp.content)
                label.setPixmap(pix)
        except:
            pass
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        act_del = QAction("🗑 删除角色", self)
        menu.addAction(act_del)
        chosen = menu.exec(event.globalPos())
        if chosen == act_del:
            dlg = ConfirmDeleteDialog(self.data, self.avatar_lbl.pixmap(), self.window())
            if dlg.exec():
                try:
                    remove_character(self.data)
                except Exception as e:
                    QMessageBox.warning(self, "错误", f"删除失败: {e}")
                parent = self.parent()
                while parent is not None and not isinstance(parent, SoraCharacterPage):
                    parent = parent.parent()
                if isinstance(parent, SoraCharacterPage):
                    parent._refresh_list()
            
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 简单的点击效果
            pass
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        """右键菜单"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #ffffff;
                border: 1px solid #dcdcdc;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px;
                border-radius: 4px;
                color: #333333;
            }
            QMenu::item:selected {
                background-color: #f0f0f0;
            }
        """)
        
        username = self.data.get('username', '')
        if username:
            # 复制名字 (@username)
            action_copy_tag = QAction(f"复制名字 (@{username})", self)
            action_copy_tag.triggered.connect(lambda: self._copy_text(f"@{username}"))
            menu.addAction(action_copy_tag)
            
            # 复制纯名字 (username)
            action_copy_name = QAction(f"复制纯名字 ({username})", self)
            action_copy_name.triggered.connect(lambda: self._copy_text(username))
            menu.addAction(action_copy_name)
        
        # 复制角色图片链接
        profile_url = self.data.get('profile_picture_url', '')
        if profile_url:
            action_copy_img_url = QAction("复制角色图片链接", self)
            action_copy_img_url.triggered.connect(lambda: self._copy_text(profile_url))
            menu.addAction(action_copy_img_url)
        
        # 删除角色
        action_delete = QAction("删除角色", self)
        menu.addAction(action_delete)
        
        chosen = menu.exec(event.globalPos())
        if chosen == action_delete:
            # 使用自定义删除确认弹窗
            pixmap = None
            if hasattr(self, 'avatar_lbl') and self.avatar_lbl.pixmap():
                pixmap = self.avatar_lbl.pixmap()
            
            dialog = ConfirmDeleteDialog(self.data, pixmap, self)
            if dialog.exec() == QDialog.Accepted:
                try:
                    remove_character(self.data)
                except Exception as e:
                    QMessageBox.warning(self, "错误", f"删除失败: {e}")
                # 刷新页面
                parent = self.parent()
                while parent is not None and not isinstance(parent, SoraCharacterPage):
                    parent = parent.parent()
                if isinstance(parent, SoraCharacterPage):
                    parent._refresh_list()

    def _copy_text(self, text):
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        # 简单的视觉反馈（可选，这里只在控制台打印）
        print(f"[DEBUG] Copied to clipboard: {text}")

class SoraCharacterPage(QWidget):
    """主页面 - 参考 sora_character_library.py"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SoraCharacterPage")
        self.setStyleSheet("background-color: #ffffff;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 头部
        header = QHBoxLayout()
        title = QLabel("Sora2 角色库")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #333;")
        header.addWidget(title)
        
        btn_refresh = QPushButton("🔄 刷新")
        btn_refresh.setFixedSize(80, 36)
        btn_refresh.setStyleSheet("QPushButton { background: #f1f1f1; border: 1px solid #ddd; border-radius: 6px; } QPushButton:hover { background: #e1e1e1; }")
        btn_refresh.clicked.connect(self._start_sync)
        header.addWidget(btn_refresh)
        
        header.addStretch()
        
        btn_add = QPushButton("+ 创建新角色")
        btn_add.setFixedSize(120, 36)
        btn_add.setStyleSheet("""
            QPushButton { background-color: #3b82f6; color: white; border-radius: 6px; font-weight: bold; }
            QPushButton:hover { background-color: #2563eb; }
        """)
        btn_add.clicked.connect(self._open_create_dialog)
        header.addWidget(btn_add)
        layout.addLayout(header)
        
        # 列表区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(self.content_widget) # 使用网格布局
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.grid.setSpacing(15)
        
        scroll.setWidget(self.content_widget)
        layout.addWidget(scroll)
        
        self._refresh_list()

    def _start_sync(self):
        """开始同步"""
        print("[DEBUG] Starting sync...")
        config = load_config()
        api_key = config.get('api_key', '')
        base_url = config.get('base_url', '').rstrip('/')
        
        if not api_key:
            self._refresh_list() # 没key就只刷本地
            return

        # 禁用刷新按钮防止重复点击
        sender = self.sender()
        if sender and isinstance(sender, QPushButton):
            sender.setEnabled(False)
            sender.setText("同步中...")
            self._sync_btn = sender
        else:
            self._sync_btn = None
            
        self.sync_thread = SyncCharactersThread(api_key, base_url)
        self.sync_thread.finished_signal.connect(self._on_sync_finished)
        self.sync_thread.start()
        
    def _on_sync_finished(self, success, data, msg):
        if self._sync_btn:
            self._sync_btn.setEnabled(True)
            self._sync_btn.setText("🔄 刷新")
            
        if success:
            changed = sync_characters_to_file(data)
            if changed:
                print("[DEBUG] Sync updated local file.")
            else:
                print("[DEBUG] Sync finished, no new characters.")
        else:
            print(f"[DEBUG] Sync failed: {msg}")
            
        # 无论成功失败，都刷新UI显示
        self._refresh_list()

    def _open_create_dialog(self):
        dlg = SoraCharacterDialog(self.window())
        dlg.character_created.connect(self._on_created)
        dlg.exec()

    def _on_created(self, data):
        self._refresh_list()

    def _refresh_list(self):
        print("[DEBUG] SoraCharacterPage: Refreshing list...")
        # 清空列表
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        
        chars = load_characters()
        print(f"[DEBUG] Loaded {len(chars)} characters.")
        if not chars:
            empty_lbl = QLabel("暂无角色，请点击右上角创建")
            empty_lbl.setAlignment(Qt.AlignCenter)
            empty_lbl.setStyleSheet("color: #999; margin-top: 50px;")
            self.grid.addWidget(empty_lbl, 0, 0)
            return
            
        # 网格布局
        cols = 4 # 默认4列
        for i, c in enumerate(chars):
            try:
                card = SoraCharacterCard(c)
                try:
                    card.delete_requested.connect(self._on_delete_requested)
                except Exception:
                    pass
                row = i // cols
                col = i % cols
                self.grid.addWidget(card, row, col)
            except Exception as e:
                print(f"[ERROR] Failed to create card for character {i}: {e}")
class ConfirmDeleteDialog(QDialog):
    def __init__(self, data, avatar_pixmap=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("删除角色")
        self.setFixedSize(400, 240)
        self.setStyleSheet("""
            QDialog { 
                background-color: #ffffff; 
                border-radius: 12px;
            }
            QLabel#title { 
                font-family: "Microsoft YaHei UI";
                font-size: 18px; 
                font-weight: bold; 
                color: #2c3e50;
                margin-bottom: 15px;
            }
            QLabel#name { 
                font-family: "Microsoft YaHei UI";
                font-size: 15px; 
                font-weight: 600; 
                color: #34495e; 
            }
            QLabel#tip { 
                font-family: "Microsoft YaHei UI";
                font-size: 13px; 
                color: #7f8c8d; 
                line-height: 1.4;
            }
            QPushButton {
                font-family: "Microsoft YaHei UI";
                font-size: 13px;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: 500;
                min-width: 80px;
            }
            QPushButton#normal { 
                background-color: #ffffff; 
                color: #5d6d7e; 
                border: 1px solid #dcdcdc; 
            }
            QPushButton#normal:hover { 
                background-color: #f8f9fa; 
                border-color: #bdc3c7;
                color: #2c3e50;
            }
            QPushButton#normal:pressed {
                background-color: #ecf0f1;
            }
            QPushButton#danger { 
                background-color: #ffffff; 
                color: #e74c3c; 
                border: 1px solid #e74c3c; 
            }
            QPushButton#danger:hover { 
                background-color: #fdedec; 
                border-color: #c0392b;
                color: #c0392b;
            }
            QPushButton#danger:pressed {
                background-color: #fadbd8;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # 标题区域
        title = QLabel("删除角色")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 内容区域
        content = QHBoxLayout()
        content.setSpacing(20)
        content.setContentsMargins(10, 0, 10, 0)
        
        # 头像
        avatar_container = QLabel()
        avatar_container.setFixedSize(68, 68)
        avatar_container.setStyleSheet("""
            background-color: #f8f9fa; 
            border: 1px solid #eeeeee; 
            border-radius: 8px;
        """)
        avatar_container.setAlignment(Qt.AlignCenter)
        
        if avatar_pixmap:
            # 缩放图片以适应容器
            scaled_pixmap = avatar_pixmap.scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            avatar_container.setPixmap(scaled_pixmap)
        else:
            avatar_container.setText("👤")
            avatar_container.setStyleSheet(avatar_container.styleSheet() + "font-size: 30px; color: #bdc3c7;")
            
        content.addWidget(avatar_container)

        # 文本信息
        info = QVBoxLayout()
        info.setSpacing(8)
        info.setAlignment(Qt.AlignVCenter)
        
        name = QLabel(f"@{data.get('username','Unknown')}")
        name.setObjectName("name")
        info.addWidget(name)
        
        tip = QLabel("确定要从角色库中移除此角色吗？\n此操作无法撤销。")
        tip.setObjectName("tip")
        tip.setWordWrap(True)
        info.addWidget(tip)
        
        content.addLayout(info)
        layout.addLayout(content)

        # 按钮区域
        layout.addStretch()
        btns = QHBoxLayout()
        btns.setSpacing(15)
        btns.setContentsMargins(10, 10, 10, 0)
        
        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("normal")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        
        btn_delete = QPushButton("删除角色")
        btn_delete.setObjectName("danger")
        btn_delete.setCursor(Qt.PointingHandCursor)
        
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_delete)
        
        layout.addLayout(btns)
        
        # 连接信号
        btn_cancel.clicked.connect(self.reject)
        btn_delete.clicked.connect(self.accept)
