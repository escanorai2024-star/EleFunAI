import sys
import os
import json
import base64
import requests
import traceback
from datetime import datetime
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QPushButton, QLabel, 
                               QRadioButton, QButtonGroup, QHBoxLayout, QMessageBox, QTextEdit,
                               QScrollArea, QSizePolicy)
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QCursor
from PySide6.QtCore import Qt, QThread, Signal, QRect

class AspectRatioLabel(QLabel):
    selection_made = Signal(QRect)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1, 1)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.original_pixmap = None
        self.setAlignment(Qt.AlignCenter)
        self.selection_mode = False
        self.start_pos = None
        self.current_pos = None

    def setPixmap(self, pixmap):
        self.original_pixmap = pixmap
        self.update()

    def mousePressEvent(self, event):
        if self.selection_mode and event.button() == Qt.LeftButton:
            self.start_pos = event.pos()
            self.current_pos = event.pos()
            self.update()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.selection_mode and self.start_pos:
            self.current_pos = event.pos()
            self.update()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.selection_mode and self.start_pos:
            end_pos = event.pos()
            
            if self.original_pixmap and not self.original_pixmap.isNull():
                size = self.size()
                pix_size = self.original_pixmap.size()
                scaled_size = pix_size.scaled(size, Qt.KeepAspectRatio)
                
                x_offset = (size.width() - scaled_size.width()) // 2
                y_offset = (size.height() - scaled_size.height()) // 2
                
                rect_widget = QRect(self.start_pos, end_pos).normalized()
                image_rect = QRect(x_offset, y_offset, scaled_size.width(), scaled_size.height())
                intersect = rect_widget.intersected(image_rect)
                
                if not intersect.isEmpty():
                    scale_x = pix_size.width() / scaled_size.width()
                    scale_y = pix_size.height() / scaled_size.height()
                    
                    final_x = int((intersect.x() - x_offset) * scale_x)
                    final_y = int((intersect.y() - y_offset) * scale_y)
                    final_w = int(intersect.width() * scale_x)
                    final_h = int(intersect.height() * scale_y)
                    
                    self.selection_made.emit(QRect(final_x, final_y, final_w, final_h))

            self.start_pos = None
            self.current_pos = None
            self.selection_mode = False
            self.update()
        else:
            super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        if not self.original_pixmap or self.original_pixmap.isNull():
            super().paintEvent(event)
            return

        size = self.size()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        # Scale keeping aspect ratio
        if size.width() > 0 and size.height() > 0:
            scaled = self.original_pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            # Center
            x = (size.width() - scaled.width()) // 2
            y = (size.height() - scaled.height()) // 2
            
            painter.drawPixmap(x, y, scaled)

        if self.selection_mode and self.start_pos and self.current_pos:
            painter.setPen(QPen(Qt.red, 2, Qt.SolidLine))
            painter.setBrush(QColor(255, 0, 0, 50))
            rect = QRect(self.start_pos, self.current_pos).normalized()
            painter.drawRect(rect)

class ImageViewerDialog(QDialog):
    screenshot_created = Signal(str)

    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("查看分镜图")
        self.resize(1600, 1200) 
        self.setWindowState(Qt.WindowMaximized) # Maximize by default
        self.setup_ui(image_path)
        
    def setup_ui(self, image_path):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True) # Default to Fit Window
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setStyleSheet("background-color: #2b2b2b; border: none;")
        
        self.image_label = AspectRatioLabel()
        self.image_label.setStyleSheet("background-color: #2b2b2b;") 
        
        self.original_pixmap = None
        if image_path and os.path.exists(image_path):
            self.original_pixmap = QPixmap(image_path)
            if not self.original_pixmap.isNull():
                self.image_label.setPixmap(self.original_pixmap)
            else:
                self.image_label.setText("无法加载图片")
                self.image_label.setStyleSheet("color: white;")
        else:
            self.image_label.setText("图片不存在")
            self.image_label.setStyleSheet("color: white;")
            
        self.image_label.selection_made.connect(self.on_selection_made)
        self.scroll_area.setWidget(self.image_label)
        layout.addWidget(self.scroll_area)
        
        # 移除底部的所有按钮，只显示图片
        # Bottom bar (REMOVED)

    def toggle_screenshot(self):
        self.image_label.selection_mode = True
        self.image_label.setCursor(Qt.CrossCursor)
        # QMessageBox.information(self, "提示", "请在图片上拖动鼠标选择截图区域")

    def on_selection_made(self, rect):
        self.image_label.setCursor(Qt.ArrowCursor)
        if self.original_pixmap:
            cropped = self.original_pixmap.copy(rect)
            
            # Save
            temp_dir = os.path.join(os.getcwd(), "temp_screenshots")
            os.makedirs(temp_dir, exist_ok=True)
            filename = f"shot_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
            path = os.path.join(temp_dir, filename)
            cropped.save(path)
            
            self.screenshot_created.emit(path)
            QMessageBox.information(self, "完成", "截图已生成新的图片节点")
    
    def toggle_mode(self):
        if self.scroll_area.widgetResizable():
            # Switch to 1:1 Original Size
            self.scroll_area.setWidgetResizable(False)
            if self.original_pixmap:
                self.image_label.setFixedSize(self.original_pixmap.size())
            # self.mode_btn.setText("适应窗口")
        else:
            # Switch to Fit Window
            self.scroll_area.setWidgetResizable(True)
            self.image_label.setMinimumSize(1, 1)
            self.image_label.setMaximumSize(16777215, 16777215)
            # self.mode_btn.setText("原始尺寸")

class StoryboardDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("产生分镜图")
        self.resize(400, 350)
        self.selection = None # '9-grid', '6-grid', 'default'
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        lbl = QLabel("请选择分镜图生成模式：")
        lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(lbl)
        
        self.btn_group = QButtonGroup(self)
        
        self.rb_9 = QRadioButton("选项一：九宫格")
        self.rb_6 = QRadioButton("选项二：六宫格")
        self.rb_4 = QRadioButton("选项四：四宫格")
        self.rb_def = QRadioButton("选项三：默认 (单图)")
        
        # Style
        for rb in [self.rb_9, self.rb_6, self.rb_4, self.rb_def]:
            rb.setStyleSheet("padding: 5px;")
        
        layout.addWidget(self.rb_9)
        layout.addWidget(self.rb_6)
        layout.addWidget(self.rb_4)
        layout.addWidget(self.rb_def)
        
        self.btn_group.addButton(self.rb_9, 1)
        self.btn_group.addButton(self.rb_6, 2)
        self.btn_group.addButton(self.rb_def, 3)
        self.btn_group.addButton(self.rb_4, 4)
        
        # 默认不选择任何状态
        self.btn_group.setExclusive(False)
        self.rb_9.setChecked(False)
        self.rb_6.setChecked(False)
        self.rb_4.setChecked(False)
        self.rb_def.setChecked(False)
        self.btn_group.setExclusive(True)
        
        layout.addSpacing(20)
        
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("生成")
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50; 
                color: white; 
                border-radius: 4px; 
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        ok_btn.clicked.connect(self.on_accept)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336; 
                color: white; 
                border-radius: 4px; 
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
    def on_accept(self):
        mid = self.btn_group.checkedId()
        if mid == 1:
            self.selection = '9-grid'
        elif mid == 2:
            self.selection = '6-grid'
        elif mid == 3:
            self.selection = 'default'
        elif mid == 4:
            self.selection = '4-grid'
        else:
            QMessageBox.warning(self, "提示", "请选择一个选项！")
            return
            
        self.save_settings()
        self.accept()

    def load_settings(self):
        """加载上次的选择"""
        config_path = os.path.join(os.getcwd(), 'JSON', 'daoyan_fenjing.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    selection = data.get('selection')
                    if selection == '9-grid':
                        self.rb_9.setChecked(True)
                    elif selection == '6-grid':
                        self.rb_6.setChecked(True)
                    elif selection == 'default':
                        self.rb_def.setChecked(True)
                    elif selection == '4-grid':
                        self.rb_4.setChecked(True)
            except Exception as e:
                print(f"Error loading settings: {e}")

    def save_settings(self):
        """保存当前选择"""
        config_dir = os.path.join(os.getcwd(), 'JSON')
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, 'daoyan_fenjing.json')
        
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump({'selection': self.selection}, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving settings: {e}")

# Global registry to prevent GC (migrated to QApplication)
# _STORYBOARD_WORKERS = []

class StoryboardWorker(QThread):
    # Signals
    image_completed = Signal(int, str, str, str) # row_idx, path, prompt, shot_number
    all_completed = Signal()
    progress_updated = Signal(int, int)
    log_signal = Signal(str) # For debug logging
    error_occurred = Signal(str) # For critical errors
    task_failed = Signal(int, str) # row_idx, error_msg
    
    def __init__(self, api_type, config_file, tasks, output_dir, parent=None):
        super().__init__(parent)
        self.api_type = api_type
        self.config_file = config_file
        self.tasks = tasks # List of dict: {row_idx, prompt, images: [], mode, shot_number}
        self.output_dir = output_dir
        self.running = True
        
        # Register to global registry to prevent GC
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_storyboard_workers'):
                app._active_storyboard_workers = []
            app._active_storyboard_workers.append(self)
        self.finished.connect(self._cleanup_worker)
        
    def _cleanup_worker(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app and hasattr(app, '_active_storyboard_workers'):
            if self in app._active_storyboard_workers:
                app._active_storyboard_workers.remove(self)
        self.deleteLater()
        
    def __del__(self):
        try:
            if self.isRunning():
                try:
                    self.wait(2000)
                except:
                    pass
        except RuntimeError:
            pass

    def run(self):
        try:
            self.log_signal.emit(f"=== 分镜图生成任务开始 ===")
            self.log_signal.emit(f"任务总数: {len(self.tasks)}")
            self.log_signal.emit(f"API类型: {self.api_type}")
            self.log_signal.emit(f"配置文件: {self.config_file}")
            
            # Ensure output dir exists
            os.makedirs(self.output_dir, exist_ok=True)
            
            # Load config
            api_config = {}
            if self.config_file and os.path.exists(self.config_file):
                try:
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        api_config = json.load(f)
                except Exception as e:
                    self.log_signal.emit(f"❌ 配置文件读取失败: {e}")
                    return
            else:
                 self.log_signal.emit(f"❌ 配置文件不存在")
                 return

            for i, task in enumerate(self.tasks):
                if not self.running or self.isInterruptionRequested():
                    self.log_signal.emit("⚠️ 任务被中断")
                    break
                try:
                    self.process_task(task, api_config)
                    self.progress_updated.emit(i + 1, len(self.tasks))
                except Exception as e:
                    self.log_signal.emit(f"❌ 任务 {i+1} 失败: {e}")
                    self.task_failed.emit(task['row_idx'], str(e))
                    traceback.print_exc()
                    
            self.log_signal.emit(f"=== 分镜图生成任务结束 ===")
            self.all_completed.emit()
            
            # Registry cleanup handled by finished signal
        
        except Exception as e:
             self.log_signal.emit(f"❌ 线程运行出错: {e}")
             self.error_occurred.emit(f"线程运行出错: {str(e)}\n{traceback.format_exc()}")
             traceback.print_exc()
        # finally:
        #      # Logic moved to _cleanup_worker connected to finished signal


    def process_task(self, task, api_config):
        row_idx = task['row_idx']
        base_prompt = task['prompt']
        images = task['images']
        mode = task['mode']
        shot_number = task.get('shot_number', row_idx + 1)
        
        # Construct final prompt
        instruction = ""
        if mode == '9-grid':
            instruction = "Create a 9-panel storyboard (9-grid layout).\n"
        elif mode == '6-grid':
            instruction = "Create a 6-panel storyboard (6-grid layout).\n"
        elif mode == '4-grid':
            instruction = "Create a 4-panel storyboard (4-grid layout).\n"
            
        final_prompt = f"{instruction}{base_prompt}"
            
        self.log_signal.emit(f"\n--- 处理第 {row_idx+1} 行 (镜头: {shot_number}) ---")
        self.log_signal.emit(f"模式: {mode}")
        self.log_signal.emit(f"提示词: {final_prompt}")
        self.log_signal.emit(f"参考图片数: {len(images)}")
        for img in images:
             self.log_signal.emit(f"  - 图片: {img}")
        
        # Call API
        image_path = None
        if self.api_type == "BANANA":
            image_path = self.generate_with_gemini(shot_number, final_prompt, images, api_config, version="2.0")
        elif self.api_type == "BANANA2":
            image_path = self.generate_with_gemini(shot_number, final_prompt, images, api_config, version="3.0")
        elif self.api_type == "Midjourney":
             self.log_signal.emit("Midjourney 暂不支持分镜图生成")
        
        if image_path:
            self.image_completed.emit(row_idx, image_path, final_prompt, shot_number)
            self.log_signal.emit(f"✅ 生成成功: {image_path}")
        else:
            self.log_signal.emit(f"❌ 生成失败")
            self.task_failed.emit(row_idx, "生成失败")

    def generate_with_gemini(self, shot_number, prompt, image_paths, api_config, version="2.0"):
        """使用 Gemini 生成"""
        try:
            api_key = api_config.get('api_key', '')
            api_url = api_config.get('base_url', 'https://generativelanguage.googleapis.com/v1beta')
            
            if version == "2.0":
                model = api_config.get('model', 'gemini-2.0-flash-exp')
            else:
                api_url = api_url.rstrip('/')
                model = api_config.get('model', 'gemini-3-pro-image-preview')

            if not api_key:
                self.log_signal.emit("API Key未配置")
                return None
            
            url = f"{api_url}/models/{model}:generateContent?key={api_key}"
            
            parts = [{"text": prompt}]
            
            # 添加源图片
            for img_path in image_paths:
                if img_path and os.path.exists(img_path):
                    try:
                        with open(img_path, "rb") as image_file:
                            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                            
                            mime_type = "image/jpeg"
                            ext = os.path.splitext(img_path)[1].lower()
                            if ext == '.png': mime_type = "image/png"
                            elif ext == '.webp': mime_type = "image/webp"
                            elif ext == '.jpg' or ext == '.jpeg': mime_type = "image/jpeg"
                            
                            parts.append({
                                "inline_data": {
                                    "mime_type": mime_type,
                                    "data": encoded_string
                                }
                            })
                            self.log_signal.emit(f"  [API] 已添加参考图片: {img_path}")
                    except Exception as e:
                        self.log_signal.emit(f"读取图片失败 {img_path}: {e}")
            
            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "response_modalities": ["IMAGE"],
                    "temperature": 1.0,
                    "imageConfig": {"aspectRatio": "16:9", "imageSize": "1K"}
                }
            }
            
            # Use requests
            self.log_signal.emit("发送请求中...")
            response = requests.post(url, json=payload, timeout=300)
            
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result and result['candidates']:
                    parts = result['candidates'][0].get('content', {}).get('parts', [])
                    for part in parts:
                        # Handle both inline_data and inlineData
                        image_data = part.get('inline_data', {}).get('data') or part.get('inlineData', {}).get('data')
                        if image_data:
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename = f"storyboard_{shot_number}_{timestamp}.jpg"
                            filepath = os.path.join(self.output_dir, filename)
                            with open(filepath, 'wb') as f:
                                f.write(base64.b64decode(image_data))
                            return filepath
                else:
                    self.log_signal.emit(f"API返回了200但没有图片候选: {result}")
            else:
                self.log_signal.emit(f"请求失败: {response.status_code} {response.text}")
            
            return None
            
        except Exception as e:
            self.log_signal.emit(f"Generate Error: {e}")
            return None
