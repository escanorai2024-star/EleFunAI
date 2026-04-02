
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QLineEdit, QTextEdit, QScrollArea, 
                             QFileDialog, QGraphicsProxyWidget, QFrame, QDialog, QListWidget, QInputDialog, QMessageBox, QMenu, QApplication, QGroupBox, QGridLayout)
from PySide6.QtCore import Qt, Signal, QSize, QThread, QSettings, QTimer
from PySide6.QtGui import QColor, QBrush, QPixmap, QIcon, QPainter, QAction, QCursor
import os
import json
import time
import base64
import requests
import shutil
from paichumingdan import ExcludeListDialog
from fujiazhi import AdditionalValueDialog
from jubenrenwufujiazhi2 import CharacterExtraManager
from LDshandian import LightningWorker
from chakan import ImageViewerDialog
from didianeditor import LocationEditorDialog, DetailTextEdit
from jubenrenwu_diejiatu import CharacterOverlayGenerator
from database_save import AssetLibraryStore, LibraryPanel, AssetThumbnail
import jubenrenwu_duqu

def save_character_to_library(name, prompt, image_path):
    try:
        if not image_path or not os.path.exists(image_path):
            return
        store = AssetLibraryStore()
        store.add_people_record(name or "", prompt or "", image_path)
    except Exception as e:
        print(f"[人物资料库] 保存人物图片失败: {e}")


SVG_CHARACTER_ICON = """<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 12C14.21 12 16 10.21 16 8C16 5.79 14.21 4 12 4C9.79 4 8 5.79 8 8C8 10.21 9.79 12 12 12ZM12 14C9.33 14 4 15.34 4 18V20H20V18C20 15.34 14.67 14 12 14Z" fill="#5f6368"/></svg>"""
SVG_STYLE_ICON = """<svg xmlns="http://www.w3.org/2000/svg" height="24" viewBox="0 -960 960 960" width="24" fill="white"><path d="M200-120q-33 0-56.5-23.5T120-200v-560q0-33 23.5-56.5T200-840h560q33 0 56.5 23.5T840-760v560q0 33-23.5 56.5T760-120H200Zm0-80h560v-560H200v560Zm40-80h480L570-480 450-320l-90-120-120 160Zm-40 80v-560 560Z"/></svg>"""

class ImageGenerationWorker(QThread):
    progress = Signal(str)
    image_generated = Signal(str, str) # name, image_path
    finished_all = Signal(int)
    error_occurred = Signal(str)

    def __init__(self, tasks, provider, config):
        super().__init__()
        self.tasks = tasks # list of (name, prompt)
        self.provider = provider
        self.config = config
        self.stopped = False

        # Register to global registry to prevent GC
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_image_workers'):
                app._active_image_workers = []
            app._active_image_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        app = QApplication.instance()
        if app and hasattr(app, '_active_image_workers'):
            if self in app._active_image_workers:
                app._active_image_workers.remove(self)
        self.deleteLater()

    def run(self):
        print(f"[Worker] Starting generation with provider: {self.provider}")
        count = 0
        total = len(self.tasks)
        
        output_dir = os.path.join(os.getcwd(), "jpg", "people")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        for i, (name, prompt) in enumerate(self.tasks):
            if self.stopped: break
            
            self.progress.emit(f"正在生成 {name} ({i+1}/{total})...")
            
            try:
                image_data = None
                if self.provider == "Midjourney":
                    image_data = self.generate_mj(prompt)
                elif self.provider in ["BANANA", "BANANA2"]:
                    image_data = self.generate_gemini(prompt)
                
                if image_data:
                    # Save image
                    filename = f"{name}_{int(time.time())}.png"
                    # Sanitize filename
                    filename = "".join([c for c in filename if c.isalpha() or c.isdigit() or c in "._-"]).strip()
                    filepath = os.path.join(output_dir, filename)
                    
                    with open(filepath, "wb") as f:
                        f.write(image_data)
                        
                    self.image_generated.emit(name, filepath)
                    count += 1
                else:
                    self.error_occurred.emit(f"{name} 生成失败: 未获取到图片数据")
                    
            except Exception as e:
                self.error_occurred.emit(f"{name} 错误: {str(e)}")
                
        self.finished_all.emit(count)

    def generate_mj(self, prompt):
        api_key = self.config.get('api_key')
        base_url = self.config.get('base_url')
        
        if not api_key or not base_url:
            raise Exception("Midjourney API配置不完整")

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        # 1. Submit
        submit_url = f"{base_url}/mj/submit/imagine"
        payload = {"prompt": prompt}
        resp = requests.post(submit_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        
        res_json = resp.json()
        task_id = res_json.get('result') or res_json.get('taskId') or res_json.get('id')
        
        if not task_id:
            raise Exception("未返回 Task ID")
            
        # 2. Poll
        fetch_url = f"{base_url}/mj/task/{task_id}/fetch"
        start_time = time.time()
        while time.time() - start_time < 600: # 10 mins timeout
            if self.stopped: return None
            time.sleep(5)
            try:
                resp = requests.get(fetch_url, headers=headers, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get('status')
                    if status == 'SUCCESS':
                        image_url = data.get('imageUrl')
                        if image_url:
                            # Download
                            img_resp = requests.get(image_url, timeout=60)
                            return img_resp.content
                    elif status == 'FAILURE':
                        raise Exception(f"MJ 任务失败: {data.get('failReason')}")
            except Exception as e:
                print(f"Polling error: {e}")
                pass
        raise Exception("生成超时")

    def generate_gemini(self, prompt):
        api_key = self.config.get('api_key')
        base_url = self.config.get('base_url')
        model = self.config.get('model', 'gemini-2.5-flash-image')
        
        if not api_key:
             raise Exception("Gemini API Key 未配置")

        url = f"{base_url}/models/{model}:generateContent"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        # Standard Gemini Payload
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        
        # Special config for Gemini 3.0 Pro Image
        if "gemini-3" in model or "pro-image" in model:
             payload["generationConfig"] = {
                 "responseModalities": ["IMAGE"],
                 "imageConfig": {
                     "imageSize": "1K",
                     "numberOfImages": 1
                 }
             }

        resp = requests.post(url, headers=headers, json=payload, timeout=300)
        resp.raise_for_status()
        
        # Check if response is raw image (some proxies do this)
        if 'image/' in resp.headers.get('Content-Type', ''):
             return resp.content

        data = resp.json()
        
        try:
            # Check for inline data
            if 'candidates' in data and data['candidates']:
                # Iterate through all candidates and parts to find the image
                for candidate in data['candidates']:
                    if 'content' in candidate and 'parts' in candidate['content']:
                        for part in candidate['content']['parts']:
                            if 'inlineData' in part:
                                b64_data = part['inlineData']['data']
                                return base64.b64decode(b64_data)
            
            # If we are here, no image was found. Let's analyze why.
            error_details = []
            if 'candidates' in data and data['candidates']:
                for i, cand in enumerate(data['candidates']):
                    finish_reason = cand.get('finishReason', 'UNKNOWN')
                    safety_ratings = cand.get('safetyRatings', [])
                    content_parts = []
                    if 'content' in cand and 'parts' in cand['content']:
                         content_parts = [p.get('text', 'Image/Blob')[:20] + '...' for p in cand['content']['parts']]
                    
                    error_details.append(f"Cand {i}: Reason={finish_reason}, Content={content_parts}")
                    
                    # Check for safety blocks
                    if finish_reason == 'SAFETY':
                         error_details.append(f"Safety Ratings: {str(safety_ratings)}")

            if error_details:
                 raise Exception(f"未找到图片数据。详情: {'; '.join(error_details)}")
                 
        except Exception as e:
            if "未找到图片数据" in str(e):
                raise e
            pass
            
        # Fallback error with more data
        raise Exception(f"无法解析 Gemini 响应: {str(data)[:200]}...")

    def stop(self):
        self.stopped = True

class AIPromptDialog(QDialog):
    """AI造句设置对话框"""
    def __init__(self, parent=None, current_style="3D"):
        super().__init__(parent)
        self.setWindowTitle("AI造句设置")
        self.resize(400, 300)
        
        # 确保json目录存在
        self.json_path = os.path.join(os.path.dirname(__file__), "json", "zaoju.json")
        self.ensure_json_exists()
        
        self.styles = self.load_styles()
        self.selected_style = current_style if current_style in self.styles else (self.styles[0] if self.styles else "")
        
        self.setup_ui()
        self.setStyleSheet("""
            QDialog { background-color: #f5f5f5; }
            QGroupBox { background-color: white; border-radius: 6px; margin-top: 10px; padding-top: 10px; font-weight: bold; }
            QPushButton[checkable="true"] { background-color: #e0e0e0; border: none; border-radius: 4px; padding: 6px; color: #333; }
            QPushButton[checkable="true"]:checked { background-color: #4CAF50; color: white; }
            QPushButton[checkable="true"]:hover { background-color: #d5d5d5; }
        """)
        
    def ensure_json_exists(self):
        directory = os.path.dirname(self.json_path)
        if not os.path.exists(directory):
            try:
                os.makedirs(directory)
            except OSError:
                pass
                
        if not os.path.exists(self.json_path):
            default_styles = ["3D", "2D", "真实风格", "动漫风格"]
            try:
                with open(self.json_path, 'w', encoding='utf-8') as f:
                    json.dump(default_styles, f, ensure_ascii=False, indent=4)
            except Exception as e:
                print(f"Error creating default zaoju.json: {e}")

    def load_styles(self):
        try:
            if os.path.exists(self.json_path):
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading styles: {e}")
        return ["3D", "2D", "真实风格", "动漫风格"]

    def save_styles(self):
        try:
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(self.styles, f, ensure_ascii=False, indent=4)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存风格失败: {str(e)}")

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 风格选择
        self.style_group = QGroupBox("选择风格/词汇")
        self.grid_layout = QGridLayout(self.style_group)
        self.grid_layout.setSpacing(10)
        
        self.render_style_buttons()
        layout.addWidget(self.style_group)
        
        # 增加风格按钮
        btn_add = QPushButton("➕ 增加风格")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setStyleSheet("""
            QPushButton {
                background-color: #FF9800; color: white; border: none; 
                border-radius: 4px; padding: 6px; font-weight: bold;
            }
            QPushButton:hover { background-color: #F57C00; }
        """)
        btn_add.clicked.connect(self.add_new_style)
        layout.addWidget(btn_add)

        # 弹簧撑开空间
        layout.addStretch()
        
        # 生成按钮
        btn_gen = QPushButton("开始生成")
        btn_gen.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_gen.setStyleSheet("""
            QPushButton {
                background-color: #2196F3; color: white; border: none; 
                border-radius: 4px; padding: 8px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #1976D2; }
        """)
        btn_gen.clicked.connect(self.accept)
        layout.addWidget(btn_gen)
        
    def render_style_buttons(self):
        # 清除现有按钮
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        
        self.btns = []
        row, col = 0, 0
        max_cols = 3 # 每行3列
        
        for s in self.styles:
            btn = QPushButton(s)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if s == self.selected_style:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked=False, s=s: self.on_style_clicked(s))
            
            # 右键删除功能 (可选，但为了方便管理)
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, s=s: self.show_style_context_menu(pos, s))
            
            self.grid_layout.addWidget(btn, row, col)
            self.btns.append(btn)
            
            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    def show_style_context_menu(self, pos, style):
        menu = QMenu(self)
        delete_action = QAction("🗑️ 删除", self)
        delete_action.triggered.connect(lambda: self.delete_style(style))
        menu.addAction(delete_action)
        menu.exec(QCursor.pos()) if hasattr(Qt, 'QCursor') else menu.exec(QApplication.desktop().cursor().pos())

    def delete_style(self, style):
        if style in self.styles:
            self.styles.remove(style)
            self.save_styles()
            if self.selected_style == style:
                self.selected_style = self.styles[0] if self.styles else ""
            self.render_style_buttons()

    def add_new_style(self):
        text, ok = QInputDialog.getText(self, "增加风格", "请输入新的风格/词汇:")
        if ok and text:
            text = text.strip()
            if text and text not in self.styles:
                self.styles.append(text)
                self.save_styles()
                self.render_style_buttons()
                # 自动选中新建的
                self.on_style_clicked(text)
            elif text in self.styles:
                self.on_style_clicked(text)

    def on_style_clicked(self, style):
        self.selected_style = style
        for btn in self.btns:
            if btn.text() != style:
                btn.setChecked(False)
            else:
                btn.setChecked(True)

    def get_style(self):
        return self.selected_style

    def get_custom_words(self):
        # 移除之前的自定义输入框，这里返回空字符串
        return ""

class ScriptCharacterNode:
    """剧本人物节点"""
    
    @staticmethod
    def create_node(CanvasNode):
        """动态创建ScriptCharacterNode类，继承自CanvasNode"""
        
        class CharacterRowWidget(QWidget):
            """单个人物行控件"""
            image_changed = Signal(str) # 图片路径变化信号
            lightning_requested = Signal(str, str) # 闪电生成请求 (name, prompt)
            prompt_variation_requested = Signal(object, str, str, str, str) # row_widget, name, prompt, style, custom_words
            gen_overlay_requested = Signal(object)
            
            def __init__(self, parent=None):
                super().__init__(parent)
                self.image_path = None
                self.setup_ui()
                
            def setup_ui(self):
                layout = QHBoxLayout(self)
                layout.setContentsMargins(0, 5, 0, 5)
                layout.setSpacing(10)
                
                # 0. 启用/禁用开关 (新增)
                self.toggle_btn = QPushButton()
                self.toggle_btn.setFixedSize(20, 20)
                self.toggle_btn.setCheckable(True)
                self.toggle_btn.setChecked(True) # 默认开启 (绿色)
                self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                self.update_toggle_style(True)
                self.toggle_btn.toggled.connect(self.update_toggle_style)
                
                layout.addWidget(self.toggle_btn)
                
                # 1. 人物名称 (左侧)
                self.name_edit = DetailTextEdit()
                self.name_edit.setReadOnly(True)
                self.name_edit.setPlaceholderText("人物名称")
                self.name_edit.setFixedHeight(120)
                self.name_edit.setStyleSheet("""
                    QTextEdit {
                        border: 1px solid #e0e0e0;
                        border-radius: 8px;
                        background-color: #f8f9fa;
                        padding: 8px;
                        font-size: 14px;
                        color: #333;
                    }
                    QTextEdit:focus {
                        border: 2px solid #1a73e8;
                        background-color: #ffffff;
                    }
                """)
                self.name_edit.doubleClicked.connect(self.open_edit_dialog)
                
                # 2. 人物提示词 (中间)
                self.prompt_edit = DetailTextEdit()
                self.prompt_edit.setReadOnly(True)
                self.prompt_edit.setPlaceholderText("选择人物后，在此编辑提示词...")
                self.prompt_edit.setFixedHeight(120)
                self.prompt_edit.setStyleSheet("""
                    QTextEdit {
                        border: 1px solid #e0e0e0;
                        border-radius: 8px;
                        background-color: #f8f9fa;
                        padding: 8px;
                        font-size: 13px;
                        color: #555;
                    }
                    QTextEdit:focus {
                        border: 2px solid #1a73e8;
                        background-color: #ffffff;
                    }
                """)
                self.prompt_edit.doubleClicked.connect(self.open_edit_dialog)
                
                # 3. 人物视角图 (右侧)
                self.image_label = QLabel()
                self.image_label.setFixedSize(160, 120)
                self.image_label.setStyleSheet("""
                    QLabel {
                        border: 2px dashed #cccccc;
                        border-radius: 8px;
                        background-color: #f1f3f4;
                        color: #888888;
                        font-size: 12px;
                    }
                    QLabel:hover {
                        background-color: #e8f0fe;
                        border-color: #1a73e8;
                        color: #1a73e8;
                    }
                """)
                self.image_label.setAlignment(Qt.AlignCenter)
                self.image_label.setText("点击上传\n人物视角图")
                self.image_label.setCursor(Qt.CursorShape.PointingHandCursor)
                
                # 启用点击事件和右键菜单
                self.image_label.mousePressEvent = self.upload_image
                self.image_label.setAcceptDrops(True)
                self.image_label.dragEnterEvent = self.image_drag_enter
                self.image_label.dropEvent = self.image_drop
                self.image_label.setContextMenuPolicy(Qt.CustomContextMenu)
                self.image_label.customContextMenuRequested.connect(self.show_context_menu)

                # 清除按钮 (X)
                self.clear_btn = QPushButton("×", self.image_label)
                self.clear_btn.setFixedSize(20, 20)
                self.clear_btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(255, 0, 0, 0.7);
                        color: white;
                        border-radius: 10px;
                        font-weight: bold;
                        border: none;
                        padding-bottom: 2px;
                    }
                    QPushButton:hover {
                        background-color: rgba(255, 0, 0, 0.9);
                    }
                """)
                # 放在右上角
                self.clear_btn.move(135, 5) 
                self.clear_btn.hide()
                self.clear_btn.clicked.connect(self.clear_image)

                self.overlay_label = QLabel()
                self.overlay_label.setFixedSize(160, 120)
                self.overlay_label.setStyleSheet(self.image_label.styleSheet())
                self.overlay_label.setAlignment(Qt.AlignCenter)
                self.overlay_label.setText("叠加参考")
                self.overlay_label.setCursor(Qt.CursorShape.PointingHandCursor)
                self.overlay_label.mousePressEvent = self.upload_overlay_image
                self.overlay_label.setAcceptDrops(True)
                self.overlay_label.dragEnterEvent = self.overlay_drag_enter
                self.overlay_label.dropEvent = self.overlay_drop
                self.overlay_label.setContextMenuPolicy(Qt.CustomContextMenu)
                self.overlay_label.customContextMenuRequested.connect(self.show_overlay_context_menu)
                self.overlay_path = None

                # 启用提示词右键菜单
                self.prompt_edit.setContextMenuPolicy(Qt.CustomContextMenu)
                self.prompt_edit.customContextMenuRequested.connect(self.show_prompt_context_menu)
                
                # 添加到布局
                # 设置比例 1:2:0 左右
                layout.addWidget(self.name_edit, 1)
                layout.addWidget(self.prompt_edit, 2)
                layout.addWidget(self.image_label, 0)
                layout.addWidget(self.overlay_label, 0)
                
            def update_toggle_style(self, checked):
                """更新开关按钮样式"""
                if checked:
                    # 开启状态 - 绿色
                    self.toggle_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #4CAF50;
                            border-radius: 10px;
                            border: 2px solid #388E3C;
                        }
                        QPushButton:hover { background-color: #45a049; }
                    """)
                    self.toggle_btn.setToolTip("当前状态：开启 (点击关闭)")
                else:
                    # 关闭状态 - 红色
                    self.toggle_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #F44336;
                            border-radius: 10px;
                            border: 2px solid #D32F2F;
                        }
                        QPushButton:hover { background-color: #d32f2f; }
                    """)
                    self.toggle_btn.setToolTip("当前状态：关闭 (点击开启)")
                
            def open_edit_dialog(self, editor):
                """打开编辑对话框"""
                text = editor.toPlainText()
                # 使用 didianeditor 中的 LocationEditorDialog (通用文本编辑器)
                # 传入 None 作为父窗口，避免在 QGraphicsProxyWidget 中出现输入法/焦点问题
                dialog = LocationEditorDialog(text, None)
                dialog.setWindowFlags(Qt.Window) # 强制作为独立窗口
                dialog.setAttribute(Qt.WA_DeleteOnClose)
                
                # 调整标题
                if editor == self.name_edit:
                    dialog.setWindowTitle("📝 编辑人物名称")
                else:
                    dialog.setWindowTitle("📝 编辑人物提示词")
                
                if dialog.exec():
                    editor.setPlainText(dialog.edited_text)

            def upload_image(self, event):
                if event.button() == Qt.LeftButton:
                    if self.image_path and os.path.exists(self.image_path):
                        # 查看图片
                        dialog = ImageViewerDialog(self.image_path, self)
                        dialog.show() # 使用show()而不是exec()，这样是非模态窗口，可以同时操作主界面
                        # 需要保持引用，否则会被垃圾回收
                        self._image_viewer = dialog
                    else:
                        # 上传图片
                        file_path, _ = QFileDialog.getOpenFileName(
                            self, "选择人物基准图", "", "Images (*.png *.jpg *.jpeg *.bmp)"
                        )
                        if file_path:
                            self.set_image(file_path)

            def image_drag_enter(self, event):
                md = event.mimeData()
                if md.hasUrls():
                    event.acceptProposedAction()
                else:
                    event.ignore()

            def image_drop(self, event):
                md = event.mimeData()
                for url in md.urls():
                    path = url.toLocalFile()
                    if path and path.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")):
                        self.set_image(path)
                        event.acceptProposedAction()
                        break

            def delete_image(self):
                self.image_path = None
                self.image_label.clear()
                self.image_label.setText("点击上传\n人物视角图")
                self.image_changed.emit("")

            def upload_overlay_image(self, event):
                if event.button() == Qt.LeftButton:
                    if self.overlay_path and os.path.exists(self.overlay_path):
                        dialog = ImageViewerDialog(self.overlay_path, self)
                        dialog.show()
                        self._overlay_viewer = dialog
                    else:
                        file_path, _ = QFileDialog.getOpenFileName(
                            self, "选择叠加参考图", "", "Images (*.png *.jpg *.jpeg *.bmp)"
                        )
                        if file_path:
                            self.set_overlay_image(file_path)

            def overlay_drag_enter(self, event):
                md = event.mimeData()
                if md.hasUrls():
                    event.acceptProposedAction()
                else:
                    event.ignore()

            def overlay_drop(self, event):
                md = event.mimeData()
                for url in md.urls():
                    path = url.toLocalFile()
                    if path and path.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")):
                        self.set_overlay_image(path)
                        event.acceptProposedAction()
                        break

            def set_overlay_image(self, path):
                if path and os.path.exists(path):
                    self.overlay_path = path
                    pixmap = QPixmap(path)
                    scaled_pixmap = pixmap.scaled(self.overlay_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.overlay_label.setPixmap(scaled_pixmap)

            def delete_overlay_image(self):
                self.overlay_path = None
                self.overlay_label.clear()
                self.overlay_label.setText("叠加参考")

            def show_overlay_context_menu(self, pos):
                menu = QMenu(self)
                menu.setStyleSheet("""
                    QMenu {
                        background-color: #ffffff;
                        border: 1px solid #dcdcdc;
                        padding: 5px;
                        border-radius: 4px;
                    }
                    QMenu::item {
                        padding: 5px 20px;
                        background-color: transparent;
                        color: #333333;
                    }
                    QMenu::item:selected {
                        background-color: #e8f0fe;
                        color: #1a73e8;
                    }
                """)
                action_delete = QAction("🗑️ 删除叠加图", self)
                action_delete.triggered.connect(self.delete_overlay_image)
                menu.addAction(action_delete)
                menu.exec(self.overlay_label.mapToGlobal(pos))

            def show_context_menu(self, pos):
                menu = QMenu(self)
                menu.setStyleSheet("""
                    QMenu {
                        background-color: #ffffff;   /* 白底 */
                        border: 1px solid #dcdcdc;   /* 灰色边框 */
                        padding: 5px;
                        border-radius: 4px;
                    }
                    QMenu::item {
                        padding: 5px 20px;
                        background-color: transparent;
                        color: #333333;             /* 黑字 */
                    }
                    QMenu::item:selected {
                        background-color: #e8f0fe;  /* 选中变蓝 */
                        color: #1a73e8;
                    }
                """)
                
                # 如果有图片，显示删除选项
                if self.image_path:
                    action_delete = QAction("🗑️ 删除图片", self)
                    action_delete.triggered.connect(self.delete_image)
                    menu.addAction(action_delete)

                    send_to_canvas_action = QAction("🎨 发送到画板", self)
                    send_to_canvas_action.triggered.connect(self.send_to_canvas)
                    menu.addAction(send_to_canvas_action)
                    
                    menu.addSeparator()
                
                # 读取资料库
                action_read_lib = QAction("📂 读取资料库", self)
                action_read_lib.triggered.connect(lambda: jubenrenwu_duqu.read_from_library(self))
                menu.addAction(action_read_lib)

                save_action = QAction("💾 保存图片", self)
                save_action.triggered.connect(self.save_image)
                menu.addAction(save_action)

                action_overlay = QAction("🖼️ 生成叠加图", self)
                action_overlay.triggered.connect(self.request_overlay_generation)
                menu.addAction(action_overlay)

                action_lightning = QAction("🗡产生人物形象", self)
                action_lightning.triggered.connect(self.request_lightning)
                menu.addAction(action_lightning)
                menu.exec(self.image_label.mapToGlobal(pos))

            def show_prompt_context_menu(self, pos):
                # 创建自定义菜单，不使用系统默认菜单
                menu = QMenu(self.prompt_edit)
                
                # 添加自定义动作
                # 0. 基础操作 - 复制
                copy_action = QAction("📄 复制内容", self)
                copy_action.triggered.connect(lambda: QApplication.clipboard().setText(self.prompt_edit.textCursor().selectedText() if self.prompt_edit.textCursor().hasSelection() else self.prompt_edit.toPlainText()))
                menu.addAction(copy_action)
                menu.addSeparator()

                # AI造句 (改为弹窗形式)
                ai_action = QAction("✨ AI造句", self)
                ai_action.triggered.connect(self.open_ai_prompt_dialog)
                menu.addAction(ai_action)
                
                # 清空提示词
                clear_action = QAction("🗑️ 清空提示词", self)
                clear_action.triggered.connect(self.prompt_edit.clear)
                menu.addAction(clear_action)
                
                # 设置样式 (保持一致)
                menu.setStyleSheet("""
                    QMenu {
                        background-color: #ffffff;
                        border: 1px solid #dcdcdc;
                        padding: 5px;
                        border-radius: 4px;
                    }
                    QMenu::item {
                        padding: 5px 20px;
                        background-color: transparent;
                        color: #333333;
                    }
                    QMenu::item:selected {
                        background-color: #e8f0fe;
                        color: #1a73e8;
                    }
                """)
                
                menu.exec(self.prompt_edit.mapToGlobal(pos))

            def open_ai_prompt_dialog(self):
                # 使用新的 CharacterStyleDialog
                from LD_people_word import CharacterStyleDialog
                dialog = CharacterStyleDialog(self)
                if dialog.exec():
                    style, prompt_template = dialog.get_style()
                    
                    # 将 prompt_template 作为 custom_words 传递
                    self.request_prompt_variation(style, prompt_template)

            def request_prompt_variation(self, style="3D", custom_words=""):
                name = self.name_edit.toPlainText().strip()
                prompt = self.prompt_edit.toPlainText().strip()
                # 即使没有prompt，只有name也可以尝试生成
                if name:
                    self.prompt_edit.setPlaceholderText(f"正在生成{style}风格提示词...")
                    self.prompt_variation_requested.emit(self, name, prompt, style, custom_words)
                else:
                    QMessageBox.warning(self, "提示", "请先填写人物名称")

            def clear_image(self):
                self.image_path = None
                self.image_label.clear()
                self.image_label.setText("点击上传\n人物视角图")
                self.clear_btn.hide()
                self.image_changed.emit("")

            def send_to_canvas(self):
                if not self.image_path or not os.path.exists(self.image_path):
                    return

                try:
                    # 尝试找到场景
                    scene = None
                    # 方法1: 通过代理部件
                    proxy = self.graphicsProxyWidget()
                    if proxy:
                        scene = proxy.scene()
                    
                    # 方法2: 全局查找
                    if not scene:
                        for w in QApplication.topLevelWidgets():
                            if w.__class__.__name__ == 'LingDong' and hasattr(w, 'scene'):
                                scene = w.scene
                                break
                    
                    if not scene:
                        print("无法找到场景")
                        return

                    # 获取 CanvasNode 类
                    CanvasNodeClass = None
                    for item in scene.items():
                         if hasattr(item, 'node_title') and hasattr(item, 'icon_svg'):
                             for base in item.__class__.__bases__:
                                 if base.__name__ == 'CanvasNode':
                                     CanvasNodeClass = base
                                     break
                             if CanvasNodeClass: break
                    
                    # 如果找不到，尝试从 lingdong 模块获取
                    if not CanvasNodeClass:
                         import sys
                         if 'lingdong' in sys.modules:
                             CanvasNodeClass = sys.modules['lingdong'].CanvasNode

                    if CanvasNodeClass:
                        from lingdongpng import ImageNode as ImageNodeFactory
                        ImageNodeClass = ImageNodeFactory.create_image_node(CanvasNodeClass)
                        
                        # 放在当前视图中心
                        view = scene.views()[0]
                        center = view.mapToScene(view.viewport().rect().center())
                        
                        node = ImageNodeClass(center.x(), center.y())
                        node.load_image(self.image_path)
                        scene.addItem(node)
                        node.setSelected(True)
                        print(f"已发送图片到画板: {self.image_path}")
                except Exception as e:
                    print(f"发送到画板失败: {e}")
                
            def request_lightning(self):
                name = self.name_edit.toPlainText().strip()
                prompt = self.prompt_edit.toPlainText().strip()
                if name and prompt:
                    # 显示等待状态
                    self.image_label.setText("⚡ 生成中...")
                    self.lightning_requested.emit(name, prompt)
                else:
                    QMessageBox.warning(self, "提示", "请先填写人物名称和提示词")
            
            def set_image(self, path):
                if os.path.exists(path):
                    self.image_path = path
                    pixmap = QPixmap(path)
                    scaled_pixmap = pixmap.scaled(
                        self.image_label.size(), 
                        Qt.KeepAspectRatio, 
                        Qt.SmoothTransformation
                    )
                    self.image_label.setPixmap(scaled_pixmap)
                    self.image_label.setText("")
                    self.clear_btn.show()
                    self.image_changed.emit(path)
                    name = self.name_edit.toPlainText().strip()
                    prompt = self.prompt_edit.toPlainText().strip()
                    save_character_to_library(name, prompt, path)
            
            def save_image(self):
                if self.image_path and os.path.exists(self.image_path):
                    default_name = os.path.basename(self.image_path)
                    dest, _ = QFileDialog.getSaveFileName(self, "保存图片", default_name, "Images (*.png *.jpg *.jpeg *.bmp)")
                    if dest:
                        try:
                            shutil.copyfile(self.image_path, dest)
                        except Exception:
                            pass
                else:
                    dest, _ = QFileDialog.getSaveFileName(self, "保存图片", "", "Images (*.png *.jpg *.jpeg *.bmp)")
                    if dest:
                        pixmap = self.image_label.pixmap()
                        if pixmap:
                            pixmap.save(dest)
            
            def request_overlay_generation(self):
                self.image_label.setText("生成中...")
                self.gen_overlay_requested.emit(self)
            
            def get_data(self):
                return {
                    "name": self.name_edit.toPlainText(),
                    "prompt": self.prompt_edit.toPlainText(),
                    "image_path": self.image_path,
                    "overlay": getattr(self, "overlay_path", None),
                    "enabled": self.toggle_btn.isChecked()
                }
                
            def set_data(self, data):
                self.name_edit.setPlainText(data.get("name", ""))
                self.prompt_edit.setPlainText(data.get("prompt", ""))
                img_path = data.get("image_path")
                if img_path:
                    self.set_image(img_path)
                ov_path = data.get("overlay")
                if ov_path:
                    self.set_overlay_image(ov_path)
                
                # 恢复开关状态
                enabled = data.get("enabled", True)
                self.toggle_btn.setChecked(enabled)
                self.update_toggle_style(enabled)

        class ScriptCharacterNodeImpl(CanvasNode):
            def __init__(self, x, y):
                super().__init__(x, y, 800, 600, "剧本人物节点", SVG_CHARACTER_ICON)
                
                # 设置背景色
                self.setBrush(QBrush(QColor("#ffffff")))
                
                # 创建代理部件容器
                self.proxy_widget = QGraphicsProxyWidget(self)
                self.proxy_widget.setZValue(10) # 确保在顶层
                # 关键修复：强制设置代理部件几何尺寸以填充节点
                self.proxy_widget.setGeometry(0, 0, 800, 600)
                
                # 创建内部部件
                self.container = QWidget()
                self.container.setStyleSheet("background-color: transparent;")
                # 关键修复：初始调整容器尺寸 (不要使用setFixedSize，否则无法拖拽调整)
                self.container.resize(800, 600)
                
                # 主布局
                self.layout = QVBoxLayout(self.container)
                self.layout.setContentsMargins(20, 50, 20, 20) # 顶部预留给标题栏
                self.layout.setSpacing(15)
                self.style_ref_image_path = None
                
                # --- 顶部工具栏 (排除名单) ---
                top_bar_layout = QHBoxLayout()
                top_bar_layout.setContentsMargins(0, 0, 0, 0)
                top_bar_layout.addStretch()
                
                self.btn_exclude = QPushButton("⛔ 排除名单")
                self.btn_exclude.setCursor(Qt.CursorShape.PointingHandCursor)
                self.btn_exclude.setStyleSheet("""
                    QPushButton {
                        background-color: #f44336;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 5px 10px;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background-color: #d32f2f;
                    }
                """)
                self.btn_exclude.clicked.connect(self.open_exclude_dialog)
                top_bar_layout.addWidget(self.btn_exclude)
                
                self.extra_manager = CharacterExtraManager(self)
                self.btn_settings = self.extra_manager.setup_ui(self.container)
                top_bar_layout.addWidget(self.btn_settings)

                # === 快速生成按钮 (新增) ===
                try:
                    from fastrenwu import FastGenerationHandler
                    self.fast_gen_handler = FastGenerationHandler(self)
                    
                    self.btn_fast_gen = QPushButton("⚡ 快速生成")
                    self.btn_fast_gen.setCursor(Qt.CursorShape.PointingHandCursor)
                    self.btn_fast_gen.setStyleSheet("""
                        QPushButton {
                            background-color: #FF9800;
                            color: white;
                            border: none;
                            border-radius: 4px;
                            padding: 5px 10px;
                            font-size: 12px;
                            font-weight: bold;
                        }
                        QPushButton:hover {
                            background-color: #F57C00;
                        }
                    """)
                    self.btn_fast_gen.clicked.connect(self.fast_gen_handler.start)
                    top_bar_layout.addWidget(self.btn_fast_gen)
                except ImportError:
                    print("[剧本人物] 无法导入 fastrenwu 模块")

                self.layout.addLayout(top_bar_layout)
                # ---------------------------
                
                # 表头区域
                header_container = QWidget()
                header_container.setStyleSheet("""
                    QWidget {
                        background-color: #f1f3f4;
                        border-radius: 8px;
                    }
                    QLabel {
                        font-weight: bold;
                        font-size: 14px;
                        color: #5f6368;
                        padding: 10px;
                        border: none;
                    }
                """)
                header_layout = QHBoxLayout(header_container)
                header_layout.setContentsMargins(5, 0, 5, 0)
                header_layout.setSpacing(10)
                
                label_name = QLabel("人物名称")
                label_name.setAlignment(Qt.AlignCenter)
                
                label_prompt = QLabel("人物提示词")
                label_prompt.setAlignment(Qt.AlignCenter)
                
                label_image = QLabel("人物视角图")
                label_image.setAlignment(Qt.AlignCenter)
                label_image.setFixedWidth(160) # 与图片框同宽
                label_overlay = QLabel("叠加图")
                label_overlay.setAlignment(Qt.AlignCenter)
                label_overlay.setFixedWidth(160)
                
                header_layout.addWidget(label_name, 1)
                header_layout.addWidget(label_prompt, 2)
                header_layout.addWidget(label_image, 0)
                header_layout.addWidget(label_overlay, 0)
                
                self.layout.addWidget(header_container)
                
                # 滚动区域 (用于放置多个人物行)
                self.scroll_area = QScrollArea()
                self.scroll_area.setWidgetResizable(True)
                self.scroll_area.setStyleSheet("""
                    QScrollArea {
                        border: none;
                        background-color: transparent;
                    }
                    QScrollBar:vertical {
                        width: 8px;
                        background: #f0f0f0;
                        border-radius: 4px;
                    }
                    QScrollBar::handle:vertical {
                        background: #cdcdcd;
                        border-radius: 4px;
                    }
                """)
                
                self.scroll_content = QWidget()
                self.scroll_content.setStyleSheet("background-color: transparent;")
                self.scroll_layout = QVBoxLayout(self.scroll_content)
                self.scroll_layout.setContentsMargins(0, 0, 0, 0)
                self.scroll_layout.setSpacing(10)
                self.scroll_layout.addStretch() # 底部弹簧
                
                self.scroll_area.setWidget(self.scroll_content)
                self.layout.addWidget(self.scroll_area)
                
                # 底部按钮区域
                btn_layout = QHBoxLayout()
                btn_layout.setSpacing(15)
                
                # 按钮样式
                btn_style = """
                    QPushButton {
                        background-color: #1a73e8;
                        color: white;
                        border: none;
                        border-radius: 6px;
                        padding: 10px 20px;
                        font-weight: bold;
                        font-size: 13px;
                    }
                    QPushButton:hover {
                        background-color: #1557b0;
                    }
                    QPushButton:pressed {
                        background-color: #0d47a1;
                    }
                """
                
                self.btn_refresh = QPushButton("🔄 刷新列表")
                self.btn_refresh.setStyleSheet(btn_style)
                self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
                self.btn_refresh.clicked.connect(self.refresh_character_list)
                
                self.btn_gen_prompts = QPushButton("✨ 生成人物提示词")
                self.btn_gen_prompts.setStyleSheet(btn_style.replace("#1a73e8", "#8e24aa").replace("#1557b0", "#7b1fa2").replace("#0d47a1", "#4a148c"))
                self.btn_gen_prompts.setCursor(Qt.CursorShape.PointingHandCursor)
                self.btn_gen_prompts.clicked.connect(self.generate_prompts)
                
                self.btn_gen_images = QPushButton("🎨 生成图片")
                self.btn_gen_images.setStyleSheet(btn_style.replace("#1a73e8", "#e65100").replace("#1557b0", "#ef6c00").replace("#0d47a1", "#e65100"))
                self.btn_gen_images.setCursor(Qt.CursorShape.PointingHandCursor)
                self.btn_gen_images.clicked.connect(self.generate_images)
                
                self.btn_gen_overlay = QPushButton("🖼️ 生成叠加图")
                self.btn_gen_overlay.setStyleSheet(btn_style.replace("#1a73e8", "#E91E63").replace("#1557b0", "#C2185B").replace("#0d47a1", "#880E4F"))
                self.btn_gen_overlay.setCursor(Qt.CursorShape.PointingHandCursor)
                self.btn_gen_overlay.clicked.connect(self.start_overlay_generation)
                
                btn_layout.addWidget(self.btn_refresh)
                btn_layout.addWidget(self.btn_gen_prompts)
                btn_layout.addWidget(self.btn_gen_images)
                btn_layout.addWidget(self.btn_gen_overlay)
                
                self.layout.addLayout(btn_layout)
                
                # 设置代理部件内容
                self.proxy_widget.setWidget(self.container)
                
                # 初始化人物列表
                self.character_rows = []
                
                # 加载排除名单
                self.exclude_list = []
                self.load_exclude_list()

                # 添加输入接口 (DataType.TABLE = 4)
                if hasattr(self, 'add_input_socket'):
                    self.add_input_socket(4, "剧本输入")
                
                self.add_character_row() # 默认添加一行
                self.add_character_row()
                self.add_character_row()

            def start_overlay_generation(self):
                tasks = []
                for i, row in enumerate(self.character_rows):
                    data = row.get_data()
                    if data.get("enabled", True) and data.get("prompt") and data.get("overlay"):
                        tasks.append({"id": i, "prompt": data["prompt"], "ref_image": data["overlay"]})
                        row.image_label.setText("生成中...")
                if not tasks:
                    QMessageBox.information(self.container, "提示", "没有需要生成的任务")
                    return
                self.btn_gen_overlay.setEnabled(False)
                self.btn_gen_overlay.setText("生成中...")
                self.overlay_worker = CharacterOverlayGenerator(tasks)
                self.overlay_worker.image_generated.connect(self.on_overlay_generated)
                self.overlay_worker.finished_all.connect(self.on_overlay_finished)
                self.overlay_worker.error_occurred.connect(self.on_overlay_error)
                self.overlay_worker.start()

            def on_overlay_generated(self, row_id, filepath):
                try:
                    idx = int(row_id)
                    if 0 <= idx < len(self.character_rows):
                        self.character_rows[idx].set_image(filepath)
                        return
                except:
                    pass
                name_key = str(row_id).strip()
                for row in self.character_rows:
                    if row.name_edit.toPlainText().strip() == name_key:
                        row.set_image(filepath)
                        break

            def on_overlay_finished(self, count):
                self.btn_gen_overlay.setEnabled(True)
                self.btn_gen_overlay.setText("🖼️ 生成叠加图")

            def on_overlay_error(self, msg):
                try:
                    idx = int(str(msg).split(" ")[0])
                    if 0 <= idx < len(self.character_rows):
                        self.character_rows[idx].image_label.setText("生成失败")
                except:
                    QMessageBox.warning(self.container, "错误", msg)
            def get_node_data(self):
                """获取节点数据用于保存"""
                rows_data = []
                for row in self.character_rows:
                    rows_data.append(row.get_data())
                
                return {
                    "character_rows": rows_data,
                    "exclude_list": self.exclude_list,
                    "style_ref_image": getattr(self, "style_ref_image_path", None)
                }
            
            def load_node_data(self, data):
                """从保存的数据加载节点"""
                # 1. 恢复排除名单
                self.exclude_list = data.get("exclude_list", [])
                
                # 2. 恢复人物行
                # 兼容 "character_rows" 和 "characters" 键
                rows_data = data.get("character_rows", [])
                if not rows_data:
                    rows_data = data.get("characters", [])
                
                if rows_data:
                    # 清除现有的行
                    for i in reversed(range(self.scroll_layout.count())):
                        item = self.scroll_layout.itemAt(i)
                        if item.widget():
                            item.widget().deleteLater()
                        elif item.spacerItem():
                            self.scroll_layout.removeItem(item)
                    self.character_rows = []
                    
                    # 重新添加行
                    for row_data in rows_data:
                        row = self.add_character_row()
                        row.set_data(row_data)
                    
                    # 重新添加底部弹簧
                    self.scroll_layout.addStretch()
                else:
                    # 如果没有数据，默认加3行
                    if not self.character_rows: # 只有当列表为空时才添加默认行
                         self.add_character_row()
                         self.add_character_row()
                         self.add_character_row()
                
                self.style_ref_image_path = data.get("style_ref_image", None)

            def setRect(self, *args):
                """重写setRect以同步调整内部UI尺寸"""
                super().setRect(*args)
                
                # 获取新的矩形区域
                rect = self.rect()
                
                # 同步调整代理部件尺寸
                # 注意：代理部件是子项，其坐标系相对于父项（即节点本身）
                # 因此位置始终应该是 (0, 0)，只需设置大小
                if hasattr(self, 'proxy_widget'):
                    self.proxy_widget.setGeometry(0, 0, rect.width(), rect.height())
                
                # 同步调整内部容器尺寸
                # QGraphicsProxyWidget通常会自动调整其内部widget的大小，
                # 但为了确保万无一失，我们可以显式调用resize
                # 注意：如果发现界面错位，可以尝试注释掉下面这行，完全交给proxy_widget管理
                # if hasattr(self, 'container'):
                #     self.container.resize(int(rect.width()), int(rect.height()))
            
            def on_lightning_requested(self, name, prompt):
                """处理闪电生成请求"""
                # 0. 检查是否有任务
                if hasattr(self, 'lightning_worker') and self.lightning_worker.isRunning():
                    QMessageBox.warning(self.container, "提示", "已有闪电生成任务正在进行中，请稍候...")
                    return
                
                print(f"[闪电生成] 收到请求: {name}")

                # 1. 获取 Chat Config (不再需要，因为不进行提示词优化)
                # settings = QSettings("GhostOS", "App")
                # chat_provider = settings.value("api/chat_provider", "ChatGPT")
                # chat_config = {"provider": chat_provider}
                # ... (code omitted for brevity, cleaning up)
                chat_config = {} 

                # 2. 获取 Image Config
                settings = QSettings("GhostOS", "App")
                img_provider_key = settings.value("api/image_provider", "BANANA")
                # 映射逻辑
                img_provider = "BANANA"
                p_str = str(img_provider_key).strip()
                if p_str == "Midjourney": img_provider = "Midjourney"
                elif p_str == "BANANA2": img_provider = "BANANA2"
                elif p_str == "BANANA": img_provider = "BANANA"
                else:
                    key_lower = p_str.lower()
                    if "midjourney" in key_lower or "mj" in key_lower: img_provider = "Midjourney"
                    elif "banana2" in key_lower: img_provider = "BANANA2"
                    elif "banana" in key_lower: img_provider = "BANANA"
                
                img_config = {}
                try:
                    if img_provider == "Midjourney":
                        img_config['api_key'] = settings.value("providers/midjourney/api_key", "")
                        img_config['base_url'] = settings.value("providers/midjourney/base_url", "")
                        if not img_config['api_key']:
                            mj_json = os.path.join(os.getcwd(), "json", "mj.json")
                            if os.path.exists(mj_json):
                                with open(mj_json, "r", encoding="utf-8") as f:
                                    d = json.load(f)
                                    img_config['api_key'] = d.get("api_key", "")
                                    img_config['base_url'] = d.get("base_url", "")
                    elif img_provider == "BANANA":
                        import Agemini
                        img_config = Agemini.get_config()
                    elif img_provider == "BANANA2":
                        import gemini30
                        img_config = gemini30.get_config()
                except Exception as e:
                    print(f"[闪电生成] 读取Image配置失败: {e}")
                
                if not img_config.get('api_key'):
                    QMessageBox.warning(self.container, "配置缺失", f"未检测到 {img_provider} API配置。")
                    return
                
                # 3. 启动 Worker
                
                # 处理附加值
                if getattr(self, "extra_enabled", True) and getattr(self, "extra_words", ""):
                    # 附加值放在最前面
                    extra = self.extra_words.strip()
                    if extra:
                        if prompt:
                            prompt = f"{extra}，{prompt}"
                        else:
                            prompt = extra

                style_ref_path = getattr(self, "style_ref_image_path", None)
                if style_ref_path:
                    prompt = f"{prompt} 请参考参考图的画风风格生成图片".strip()
                self.lightning_worker = LightningWorker(prompt, chat_config, img_config, img_provider, style_ref_path=style_ref_path)
                self.lightning_worker.prompt_updated.connect(lambda p, n=name: self.update_row_prompt(n, p))
                self.lightning_worker.image_updated.connect(lambda p, n=name: self.update_row_image(n, p))
                self.lightning_worker.error_occurred.connect(self.on_lightning_error)
                self.lightning_worker.finished_task.connect(lambda: print(f"[闪电生成] 任务完成: {name}"))
                self.lightning_worker.start()
            
            def update_row_prompt(self, name, new_prompt):
                for row in self.character_rows:
                    if row.name_edit.toPlainText().strip() == name:
                        row.prompt_edit.setPlainText(new_prompt)
                        break
            
            def update_row_image(self, name, image_path):
                for row in self.character_rows:
                    if row.name_edit.toPlainText().strip() == name:
                        row.set_image(image_path)
                        break
            
            def on_lightning_error(self, msg):
                QMessageBox.warning(self.container, "闪电生成错误", msg)

            def on_prompt_variation_requested(self, row_widget, name, prompt, style="3D", custom_words=""):
                """处理提示词变体请求 - 委托给工作台处理"""
                print(f"[提示词变体] 收到请求: {name}, 风格: {style}, 关键词: {custom_words}")
                
                # 尝试获取工作台实例
                workbench = None
                if self.scene():
                    views = self.scene().views()
                    if views:
                        view = views[0]
                        # 向上查找 WorkbenchPanel
                        p = view
                        while p:
                            if hasattr(p, 'start_prompt_fine_tuning'):
                                workbench = p
                                break
                            # 检查是否是主界面 (LingdongAgentPage)，它持有 workbench
                            if hasattr(p, 'workbench') and hasattr(p.workbench, 'start_prompt_fine_tuning'):
                                workbench = p.workbench
                                break
                            p = p.parent()
                
                if not workbench:
                    QMessageBox.warning(self.container, "错误", "无法找到工作台实例，请确保节点在工作台中运行。")
                    return
                
                # ---------------------------------------------------------
                # 获取剧本上下文
                # ---------------------------------------------------------
                script_context = ""
                
                # 1. 尝试从输入端口获取
                if hasattr(self, 'get_input_data'):
                    try:
                        input_data = self.get_input_data(0)
                        if input_data and isinstance(input_data, list):
                            # 目标字段列表 (参考 generate_prompts 的逻辑)
                            priority_fields = [
                                "镜号", "镜头号", "Shot No", "Shot",
                                "时间码", "Timecode", "Time",
                                "景别", "Shot Size", "Size",
                                "画面内容", "Content", "Description",
                                "人物", "Character", "Role", "Name",
                                "人物关系/构图", "人物关系", "构图", "Relation", "Composition",
                                "地点/环境", "地点", "环境", "Location", "Environment", "Place",
                                "运镜", "Camera Movement", "Camera",
                                "音效/台词", "音效", "台词", "Sound", "Dialogue", "Audio",
                                "备注", "Remark", "Note"
                            ]

                            lines = []
                            for i, row in enumerate(input_data):
                                if not isinstance(row, dict): continue
                                
                                # 构建每一行的描述
                                processed_row = {}
                                row_lower = {str(k).lower(): k for k in row.keys()} # map lower key to original key
                                
                                # 1. 先按优先级添加字段
                                added_keys = set()
                                
                                # 遍历优先级字段
                                for target in priority_fields:
                                    # 查找匹配的键
                                    found_key = None
                                    target_lower = target.lower()
                                    
                                    for k_lower, k_original in row_lower.items():
                                        if k_original in added_keys: continue
                                        
                                        # 精确匹配或包含匹配
                                        if target_lower == k_lower or target_lower in k_lower or k_lower in target_lower:
                                            # 排除一些误判
                                            found_key = k_original
                                            break
                                    
                                    if found_key:
                                        val = row[found_key]
                                        if val:
                                            processed_row[found_key] = val
                                            added_keys.add(found_key)

                                # 2. 添加剩余的所有字段
                                for k, v in row.items():
                                    if k in added_keys: continue
                                    if str(k).startswith('_'): continue # 忽略内部字段
                                    if not v: continue
                                    
                                    processed_row[k] = v
                                    added_keys.add(k)

                                if processed_row:
                                    # 格式化为字符串
                                    row_str = f"Line {i+1}: " + ", ".join([f"{k}: {v}" for k, v in processed_row.items()])
                                    lines.append(row_str)
                                    
                            if lines:
                                script_context = "\n".join(lines)
                                print(f"[提示词变体] 从输入端口获取到剧本上下文: {len(script_context)} 字符")
                    except Exception as e:
                        print(f"[提示词变体] 获取输入数据失败: {e}")
                
                # 2. 如果没有输入数据，尝试从场景中查找谷歌剧本节点
                if not script_context and self.scene():
                    try:
                        for item in self.scene().items():
                            # 通过标题判断
                            title = ""
                            if hasattr(item, 'title'): title = item.title
                            elif hasattr(item, 'nodeTitle'): title = item.nodeTitle
                            
                            if title and "谷歌剧本" in title:
                                if hasattr(item, 'table'):
                                    rows = item.table.rowCount()
                                    cols = item.table.columnCount()
                                    lines = []
                                    # 获取表头
                                    headers = []
                                    for c in range(cols):
                                        h_item = item.table.horizontalHeaderItem(c)
                                        headers.append(h_item.text() if h_item else f"Col{c}")
                                        
                                    for r in range(rows):
                                        row_parts = []
                                        has_role = False
                                        role_val = ""
                                        content_val = ""
                                        
                                        for c in range(cols):
                                            it = item.table.item(r, c)
                                            if it and it.text().strip():
                                                header = headers[c] if c < len(headers) else ""
                                                val = it.text().strip()
                                                if "角色" in header or "人物" in header:
                                                    role_val = val
                                                elif "台词" in header or "内容" in header:
                                                    content_val = val
                                                
                                        if role_val or content_val:
                                            if role_val: row_parts.append(f"{role_val}:")
                                            if content_val: row_parts.append(content_val)
                                            lines.append(" ".join(row_parts))
                                        else:
                                            # 如果上面的逻辑没提取到（可能列名不对），则提取所有非空文本
                                            row_full = []
                                            for c in range(cols):
                                                it = item.table.item(r, c)
                                                if it and it.text().strip():
                                                    row_full.append(it.text().strip())
                                            if row_full:
                                                lines.append(" | ".join(row_full))
                                                
                                    if lines:
                                        script_context = "\n".join(lines)
                                        print(f"[提示词变体] 从场景节点获取到剧本上下文: {len(script_context)} 字符")
                                        break
                    except Exception as e:
                        print(f"[提示词变体] 查找场景节点失败: {e}")

                # ---------------------------------------------------------
                # 3. 构建提示词 (参考 generate_prompts 的逻辑)
                # ---------------------------------------------------------
                
                # LD_people_word 传递的 custom_words 其实是 prompt_template
                final_instruction = ""
                
                if custom_words and len(custom_words) > 5: # 假设是完整指令模板
                    final_instruction = custom_words
                else:
                    # 兼容旧逻辑
                    style_str = style if style else "默认"
                    final_instruction = f"请提供我一个三视角人物[{style_str}]风格的中文提示词"
                    if custom_words:
                         final_instruction += f"\n必须包含的关键词：{custom_words}"
                
                # 补充上下文信息，方便AI生成
                final_instruction += f"\n\n角色名：{name}"
                if prompt:
                    final_instruction += f"\n补充描述：{prompt}"
                if script_context:
                    final_instruction += f"\n\n参考剧本内容：\n{script_context[:3000]}"
                
                final_instruction += f"\n\n请严格按以下格式输出（只输出这一个角色的内容）：\n角色名：{name}\n提示词：[白色背景，三视图，...详细描述...]"

                # 定义回调函数
                def on_single_result(response):
                    print(f"[AI造句] 收到结果: {response[:100]}...")
                    import re
                    
                    # 1. 预处理响应内容：移除Markdown加粗等干扰字符
                    clean_response = response.replace("**", "").replace("##", "")
                    
                    # 2. 解析逻辑 (参考 on_prompts_generated)
                    new_prompt = ""
                    blocks = clean_response.split('---')
                    
                    # 优先寻找包含标准前缀的块
                    for block in blocks:
                        block = block.strip()
                        if not block: continue
                        
                        lines = block.split('\n')
                        current_prompt = ""
                        has_prefix = False
                        
                        for line in lines:
                            line = line.strip()
                            if not line: continue
                            
                            # 忽略角色名
                            if re.match(r"^(?:角色名|Role|Name|角色)[:：]", line, re.IGNORECASE):
                                continue
                                
                            # 匹配提示词前缀
                            match = re.match(r"^(?:提示词|Prompt|Description|描述)[:：]\s*(.*)", line, re.IGNORECASE)
                            if match:
                                current_prompt = match.group(1).strip()
                                has_prefix = True
                                continue
                            
                            # 如果已有前缀，或者是后续行且不是键值对，则视为提示词延续
                            if (has_prefix or current_prompt) and ":" not in line and "：" not in line:
                                current_prompt += " " + line
                        
                        if current_prompt:
                            new_prompt = current_prompt
                            break
                    
                    # 3. 如果没找到标准格式，尝试回退逻辑 (提取非角色名的所有内容)
                    if not new_prompt:
                        lines = clean_response.strip().split('\n')
                        filtered_lines = []
                        for l in lines:
                            l = l.strip()
                            if not l: continue
                            if re.match(r"^(?:角色名|Role|Name|角色)[:：]", l, re.IGNORECASE):
                                continue
                            # 排除看起来像键值对的其他行 (放宽限制)
                            if re.match(r"^[\w\s]+[:：]", l) and len(l) < 20 and "," not in l and "，" not in l:
                                if not re.match(r"^(?:提示词|Prompt|Description|描述)[:：]", l, re.IGNORECASE):
                                    continue
                            filtered_lines.append(l)
                        new_prompt = " ".join(filtered_lines).strip()
                    
                    # 4. 最终清理
                    new_prompt = new_prompt.replace("---", "").strip()

                    # 5. 终极兜底：如果还是解析不出来，直接使用全文
                    if not new_prompt and clean_response.strip():
                        new_prompt = clean_response.strip()
                        # 简单的清洗：去除可能的开头废话（如果包含冒号，且冒号前很短，取冒号后）
                        # 例如 "好的：..." 或 "提示词："
                        match = re.match(r"^[^:：\n]{1,10}[:：](.*)", new_prompt, re.DOTALL)
                        if match:
                             new_prompt = match.group(1).strip()
                        
                        # 如果有多行，且第一行看起来像角色名，尝试去掉第一行
                        lines = new_prompt.split('\n')
                        if len(lines) > 1 and re.match(r"^(?:角色名|Role|Name|角色)[:：]", lines[0], re.IGNORECASE):
                            new_prompt = "\n".join(lines[1:]).strip()

                    if new_prompt:
                        # 6. 应用风格前缀 (参考 on_prompts_generated)
                        try:
                            # 尝试两种路径查找设置文件
                            paths_to_try = [
                                os.path.join(os.getcwd(), "json", "人物提示词设置.json"),
                                os.path.join("json", "人物提示词设置.json")
                            ]
                            
                            settings = {}
                            for p in paths_to_try:
                                if os.path.exists(p):
                                    try:
                                        with open(p, 'r', encoding='utf-8') as f:
                                            settings = json.load(f)
                                        break
                                    except:
                                        continue
                            
                            # 注意：这里 style 变量来自外部闭包 (request_prompt_variation 中的 style 参数)
                            # 如果 settings 中有全局 style 设置，是否要覆盖？
                            # 这里的逻辑是：用户在弹窗选的 style 已经体现在 prompt 文本里了，或者作为指令发给AI了。
                            # AI 生成的内容应该已经符合风格。
                            # 但为了保持一致性，我们还是检查一下 style 变量对应的中文名，如果没加就加上。
                            
                            style_text = style
                            if style == "anime": style_text = "动漫风格"
                            elif style == "realistic": style_text = "真实风格"
                            elif style == "3d": style_text = "3D"
                            elif style == "none": style_text = ""
                            
                            if style_text:
                                # 检查是否已存在
                                if not new_prompt.startswith(style_text):
                                    if new_prompt:
                                        new_prompt = f"{style_text}，{new_prompt}"
                                    else:
                                        new_prompt = style_text
                            
                            # 2024-01-03: 也要加入设置中的全局 style (如果存在)
                            global_style = settings.get("style", "").strip()
                            if global_style and global_style not in new_prompt:
                                # 插入到最前面，或者 style_text 之后
                                # 如果 style_text 存在，new_prompt 已经是 "style_text，..."
                                # 我们希望变成 "style_text，global_style，..."
                                if style_text and new_prompt.startswith(style_text):
                                    # 插入到第一个逗号后
                                    rest = new_prompt[len(style_text):].strip()
                                    # 去掉开头的逗号
                                    if rest.startswith("，") or rest.startswith(","):
                                        rest = rest[1:].strip()
                                    new_prompt = f"{style_text}，{global_style}，{rest}"
                                else:
                                    # 直接加到最前
                                    new_prompt = f"{global_style}，{new_prompt}"

                            # 加载自定义关键词 - 放到最前方
                            keywords = settings.get("custom_keywords", [])
                            kw_list = []
                            if keywords and isinstance(keywords, list):
                                # 倒序遍历，这样插入到最前面时顺序是正确的（或者正序遍历，每次都插到最前，顺序会反）
                                # 策略：先构建关键词字符串，然后一次性插到最前
                                for kw in keywords:
                                    kw = kw.strip()
                                    if kw and kw not in new_prompt:
                                        kw_list.append(kw)
                            
                            # 加载本次临时输入的关键词
                            if custom_words:
                                temp_kws = [k.strip() for k in custom_words.replace("，", ",").split(",") if k.strip()]
                                for kw in temp_kws:
                                     if kw and kw not in new_prompt and kw not in kw_list:
                                          kw_list.append(kw)
                                
                            if kw_list:
                                kw_str = "，".join(kw_list)
                                # 用户要求在最前方
                                if new_prompt:
                                    new_prompt = f"{kw_str}，{new_prompt}"
                                else:
                                    new_prompt = kw_str
                                        
                        except Exception as e:
                            print(f"[AI造句] 风格前缀处理失败: {e}")

                        # 确保在主线程更新UI
                        # 直接使用 row_widget 更新，避免通过名字查找可能出现的错误
                        QTimer.singleShot(0, lambda: row_widget.prompt_edit.setPlainText(new_prompt))
                        
                        # 在工作台显示成功信息
                        if hasattr(workbench, 'append_output'):
                            QTimer.singleShot(0, lambda: workbench.append_output(f"\\n✅ 已生成【{name}】的提示词。"))
                        elif hasattr(workbench, 'output_text'):
                            QTimer.singleShot(0, lambda: workbench.output_text.append(f"\\n✅ 已生成【{name}】的提示词。"))
                            
                    else:
                        # 如果还是为空，可能真的返回为空
                        print(f"[AI造句] 结果为空。原始返回: {response}")
                        # 不弹窗打扰用户，除非完全没反应
                        if not response.strip():
                             QMessageBox.warning(self.container, "生成失败", "AI返回了空内容。")

                def on_single_error(error_msg):
                    print(f"[AI造句] 出错: {error_msg}")
                    QMessageBox.warning(self.container, "AI造句失败", f"生成过程中发生错误：\n{error_msg}")

                # 调用工作台方法 (使用 generate_character_prompts)
                if hasattr(workbench, 'generate_character_prompts'):
                    workbench.generate_character_prompts(final_instruction, on_single_result, on_single_error)
                else:
                    # 回退方案
                    workbench.start_prompt_fine_tuning(final_instruction, lambda res: on_single_result(f"提示词：{res}"))

            def add_character_row(self, data=None):
                """添加一个人物行"""
                row = CharacterRowWidget()
                # 连接闪电生成信号
                row.lightning_requested.connect(self.on_lightning_requested)
                row.prompt_variation_requested.connect(self.on_prompt_variation_requested)
                row.gen_overlay_requested.connect(lambda r=row: self.generate_overlay_for_row(r))
                
                if data:
                    row.set_data(data)
                
                # 插入到弹簧之前
                count = self.scroll_layout.count()
                self.scroll_layout.insertWidget(count - 1, row)
                self.character_rows.append(row)
                return row
            
            def generate_overlay_for_row(self, row):
                data = row.get_data()
                name = data.get("name", "").strip()
                prompt = data.get("prompt", "").strip()
                
                # 处理附加值
                if getattr(self, "extra_enabled", True) and getattr(self, "extra_words", ""):
                    extra = self.extra_words.strip()
                    if extra:
                        if prompt:
                            prompt = f"{extra}，{prompt}"
                        else:
                            prompt = extra
                            
                ref_img = data.get("overlay")
                if not prompt or not ref_img:
                    print(json.dumps({
                        "action": "CharacterOverlaySingle",
                        "status": "blocked",
                        "reason": "missing_required_fields",
                        "enabled": data.get("enabled", True),
                        "has_prompt": bool(prompt),
                        "has_overlay": bool(ref_img),
                        "name": name
                    }, ensure_ascii=False))
                    row.image_label.setText("缺少提示词/叠加参考图")
                    return
                try:
                    idx = self.character_rows.index(row)
                except ValueError:
                    idx = 0
                print(json.dumps({
                    "action": "CharacterOverlaySingle",
                    "id": idx,
                    "name": name,
                    "prompt_len": len(prompt),
                    "ref_image": ref_img
                }, ensure_ascii=False))
                try:
                    self.overlay_worker = CharacterOverlayGenerator([{"id": idx, "prompt": prompt, "ref_image": ref_img}])
                    self.overlay_worker.progress.connect(lambda msg, r=row: r.image_label.setText(msg))
                    self.overlay_worker.image_generated.connect(self.on_overlay_generated)
                    self.overlay_worker.finished_all.connect(self.on_overlay_finished)
                    self.overlay_worker.error_occurred.connect(self.on_overlay_error)
                    self.overlay_worker.start()
                except Exception as e:
                    print(f"[人物叠加] 错误: {e}")
                    row.image_label.setText("生成失败")
                
            def refresh_character_list(self):
                """刷新人物列表 - 尝试从输入节点获取数据"""
                # 尝试获取输入数据
                input_data = None
                if hasattr(self, 'get_input_data'):
                    input_data = self.get_input_data(0)
                
                if input_data and isinstance(input_data, list):
                    # 收到数据，先保存当前已有的提示词和图片
                    existing_data = {}
                    for row in self.character_rows:
                        n = row.name_edit.toPlainText().strip()
                        if n:
                            existing_data[n] = {
                                "prompt": row.prompt_edit.toPlainText().strip(),
                                "image_path": row.image_path
                            }

                    # 提取所有角色名
                    character_names = set()
                    characters = []
                    
                    for row in input_data:
                        if not isinstance(row, dict): continue
                        
                        # 尝试查找角色名 - 增强版逻辑
                        name = None
                        
                        # 0. 预处理：构建小写键映射
                        keys_lower = {str(k).lower(): k for k in row.keys()}
                        
                        # 1. 尝试特定的智能键名
                        if "_smart_name" in row and row["_smart_name"]:
                            name = row["_smart_name"]
                        
                        # 2. 尝试常见的列名 (不区分大小写)
                        if not name:
                            target_keys = ["角色", "人物", "姓名", "role", "character", "name", "who", "speaker", "actor", "person"]
                            for t in target_keys:
                                if t in keys_lower:
                                    val = row[keys_lower[t]]
                                    if val and str(val).strip():
                                        name = val
                                        break
                        
                        # 3. 如果还是没有，且有“台词/音效”列，尝试提取冒号前的名字
                        if not name:
                            dialogue_key = None
                            if "台词/音效" in row: dialogue_key = "台词/音效"
                            elif "dialogue" in keys_lower: dialogue_key = keys_lower["dialogue"]
                            
                            if dialogue_key:
                                dialogue = row[dialogue_key]
                                if dialogue:
                                    if "：" in dialogue:
                                        name = dialogue.split("：")[0]
                                    elif ":" in dialogue:
                                        name = dialogue.split(":")[0]

                        if name:
                            import re
                            # 支持一行多人：按逗号、顿号、&、/、+ 分割
                            # pattern matches: , ， 、 & / + and also newline
                            split_pattern = r'[,，、&/+\n]|\s+and\s+'
                            raw_names = re.split(split_pattern, str(name))
                            
                            for raw_n in raw_names:
                                single_name = raw_n.strip()
                                if single_name and single_name not in character_names:
                                    # 排除名单检查
                                    if hasattr(self, 'exclude_list') and single_name in self.exclude_list:
                                        continue

                                    character_names.add(single_name)
                                    
                                    # 尝试恢复已有数据
                                    prompt = ""
                                    image_path = None
                                    
                                    if single_name in existing_data:
                                        prompt = existing_data[single_name].get("prompt", "")
                                        image_path = existing_data[single_name].get("image_path")
                                        
                                    characters.append({
                                        "name": single_name, 
                                        "prompt": prompt,
                                        "image_path": image_path
                                    })
                    
                    if characters:
                        # 这里直接清空并添加
                        for row_widget in self.character_rows:
                            self.scroll_layout.removeWidget(row_widget)
                            row_widget.deleteLater()
                        self.character_rows.clear()
                        
                        for char_data in characters:
                            self.add_character_row(char_data)
                            
                        print(f"[剧本总角色数量] 已从输入更新 {len(characters)} 个角色")
                        return

                # 暂时仅仅添加一个新行作为演示
                self.add_character_row()
            
            def on_socket_connected(self, socket, connection):
                """当接口被连接时调用"""
                # 如果是输入接口被连接，自动刷新数据
                if socket.socket_type == "input":
                    # 检查是否已经有有效数据（防止覆盖已保存的数据）
                    has_data = False
                    for row in self.character_rows:
                        if row.name_edit.toPlainText().strip() or row.prompt_edit.toPlainText().strip():
                            has_data = True
                            break
                    
                    if has_data:
                        print(f"[剧本人物] 检测到输入连接，但节点已有数据，跳过自动刷新。")
                        return

                    print(f"[剧本人物] 检测到输入连接，尝试获取数据...")
                    # 使用QTimer.singleShot确保连接完全建立后再获取数据
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(100, self.refresh_character_list)

            def generate_prompts(self):
                """生成人物提示词"""
                print("[剧本人物] 点击生成人物提示词")
                style_instruction = "" # Prevent NameError
                
                # 0. 弹出风格选择对话框
                from LD_people_word import CharacterStyleDialog
                # 尝试获取合适的父窗口
                parent = self.container if hasattr(self, 'container') else None
                dialog = CharacterStyleDialog(parent)
                if not dialog.exec():
                    print("[剧本人物] 用户取消生成")
                    return
                
                style_name, style_instruction = dialog.get_style()
                self.last_gen_style_name = style_name
                
                # 更新按钮状态
                self.btn_gen_prompts.setText("⏳ 生成中...")
                self.btn_gen_prompts.setEnabled(False)
                # 强制刷新UI，确保用户看到状态变化
                from PySide6.QtCore import QCoreApplication
                QCoreApplication.processEvents()
                
                try:
                    # 1. 获取输入数据（剧本内容）
                    print("[剧本人物] 正在获取输入数据...")
                    try:
                        input_data = self.get_input_data(0)
                    except Exception as e:
                        print(f"[剧本人物] 获取输入数据出错: {e}")
                        import traceback
                        traceback.print_exc()
                        QMessageBox.warning(self.container, "错误", f"获取输入数据出错: {str(e)}")
                        self.reset_button_state()
                        return

                    if not input_data:
                        print("[剧本人物] 未连接到剧本数据或数据为空")
                        QMessageBox.warning(self.container, "提示", "未检测到剧本数据，请先连接上游剧本节点！")
                        self.reset_button_state()
                        return
                    
                    print(f"[剧本人物] 获取到输入数据，类型: {type(input_data)}")
                    
                    # 1.5 获取节点中现有的角色列表
                    existing_characters = []
                    for row in self.character_rows:
                        name = row.name_edit.toPlainText().strip()
                        if name:
                            existing_characters.append(name)
                    
                    if not existing_characters:
                        print("[剧本人物] 节点中没有角色")
                    
                    # 2. 格式化提示词
                    script_content = ""
                    
                    # 目标字段列表 - 用户要求“全部内容”，所以我们将包含所有非内部字段
                    # 但为了保持有序，我们还是优先使用预定义的顺序，然后附加其他字段
                    priority_fields = [
                        "镜号", "镜头号", "Shot No", "Shot",
                        "时间码", "Timecode", "Time",
                        "景别", "Shot Size", "Size",
                        "画面内容", "Content", "Description",
                        "人物", "Character", "Role", "Name",
                        "人物关系/构图", "人物关系", "构图", "Relation", "Composition",
                        "地点/环境", "地点", "环境", "Location", "Environment", "Place",
                        "运镜", "Camera Movement", "Camera",
                        "音效/台词", "音效", "台词", "Sound", "Dialogue", "Audio",
                        "备注", "Remark", "Note"
                    ]
                    
                    if isinstance(input_data, list):
                        lines = []
                        for i, row in enumerate(input_data):
                            # 构建每一行的描述
                            processed_row = {}
                            row_lower = {str(k).lower(): k for k in row.keys()} # map lower key to original key
                            
                            # 1. 先按优先级添加字段
                            added_keys = set()
                            
                            # 遍历优先级字段
                            for target in priority_fields:
                                # 查找匹配的键
                                found_key = None
                                target_lower = target.lower()
                                
                                for k_lower, k_original in row_lower.items():
                                    if k_original in added_keys: continue
                                    
                                    # 精确匹配或包含匹配
                                    if target_lower == k_lower or target_lower in k_lower or k_lower in target_lower:
                                        # 排除一些误判，比如 "Time" 匹配到 "Timeline"
                                        found_key = k_original
                                        break
                                
                                if found_key:
                                    val = row[found_key]
                                    if val:
                                        processed_row[found_key] = val
                                        added_keys.add(found_key)

                            # 2. 添加剩余的所有字段 (用户要求全部内容)
                            for k, v in row.items():
                                if k in added_keys: continue
                                if str(k).startswith('_'): continue # 忽略内部字段
                                if not v: continue
                                
                                processed_row[k] = v
                                added_keys.add(k)

                            if processed_row:
                                # 格式化为字符串
                                row_str = f"Line {i+1}: " + ", ".join([f"{k}: {v}" for k, v in processed_row.items()])
                                lines.append(row_str)
                                
                        script_content = "\n".join(lines)
                    else:
                        script_content = str(input_data)
                    
                    # 构建Prompt：优先使用风格模板（来自人物风格提示词.txt）
                    chars_str = ", ".join(existing_characters) if existing_characters else "剧本中的所有主要角色"
                    
                    if style_instruction and len(style_instruction.strip()) > 0:
                        prompt = f"""{style_instruction}

请参考以下剧本上下文信息，并为下列角色生成中文提示词：
角色列表：{chars_str}

剧本内容：
{script_content}

请严格按以下格式输出（每个角色一个区块，用---分隔）：
角色名：[角色名称]
提示词：[详细提示词内容]
---
"""
                    else:
                        # 回退到旧版通用模板（Midjourney），以避免空模板导致失败
                        prompt = f"""请根据以下剧本内容，为指定的角色生成Midjourney风格的中文提示词。
要求：
1. 必须生成【白色背景】的【三视图】（正面、侧面、背面）。
2. 提示词风格为Midjourney风格，使用描述性词汇，用逗号分隔。
3. 【禁止】使用权重语法（如 (word:1.5) 或 [word] 等），只使用纯文本描述。
4. 提示词应包含：外貌特征、服装细节、发型发色、关键配饰。

需要生成的角色列表：
{chars_str}

剧本内容：
{script_content}

请严格按以下格式输出（每个角色一个区块，用---分隔）：
角色名：[角色名称]
提示词：[白色背景，三视图，...详细描述...]
---
"""
                    
                    # 3. 获取WorkbenchPanel并发送请求
                    # 优先尝试从场景获取主界面引用
                    scene = self.scene()
                    main_page = None
                    workbench = None
                    
                    if hasattr(scene, 'main_page'):
                        main_page = scene.main_page
                        if hasattr(main_page, 'workbench'):
                            workbench = main_page.workbench
                    
                    if not workbench:
                        # 备用方案：通过视图查找
                        views = scene.views()
                        if views:
                            view = views[0]
                            window = view.window()
                            if hasattr(window, 'workbench'):
                                workbench = window.workbench
                            elif hasattr(window, 'lingdong_page') and hasattr(window.lingdong_page, 'workbench'):
                                workbench = window.lingdong_page.workbench

                    if workbench:
                        # 显示进度信息
                        if hasattr(workbench, 'output_text'):
                             workbench.output_text.setHtml(f"""
                                <div style='color: #00bfff; text-align: center; margin-top: 100px;'>
                                    <p style='font-size: 14px;'>⏳ 正在分析剧本并生成人物提示词...</p>
                                    <p style='font-size: 12px; margin-top: 20px; color: #666;'>
                                        正在处理 {len(lines) if isinstance(input_data, list) else '文本'} 行剧本数据<br/>
                                        请稍候...
                                    </p>
                                </div>
                            """)
                        workbench.generate_character_prompts(prompt, self.on_prompts_generated, self.on_prompts_error)
                    else:
                        print("[剧本人物] 无法找到工作台(WorkbenchPanel)")
                        QMessageBox.warning(self.container, "错误", "无法连接到工作台(WorkbenchPanel)，请联系开发者！")
                        self.reset_button_state()
                        
                except Exception as e:
                    print(f"[剧本人物] 生成提示词出错: {e}")
                    import traceback
                    traceback.print_exc()
                    QMessageBox.critical(self.container, "错误", f"生成提示词时发生错误:\n{str(e)}")
                    self.reset_button_state()

            def on_prompts_error(self, error_msg):
                """生成出错回调"""
                print(f"[剧本人物] 生成失败: {error_msg}")
                self.reset_button_state()
                
                # 通知快速生成处理器
                if hasattr(self, 'fast_gen_handler'):
                    self.fast_gen_handler.on_prompts_error()
                    
                QMessageBox.warning(self.container, "生成失败", f"生成过程中发生错误：\n{error_msg}")

            def reset_button_state(self):
                """重置生成按钮状态"""
                self.btn_gen_prompts.setText("✨ 生成人物提示词")
                self.btn_gen_prompts.setEnabled(True)

            def on_prompts_generated(self, response):
                """处理生成的提示词 - 确保在主线程执行"""
                QTimer.singleShot(0, lambda: self._handle_prompts_response_ui(response))

            def _handle_prompts_response_ui(self, response):
                """实际处理生成的提示词 (UI操作)"""
                print("[剧本人物] 收到生成结果 (UI Thread)")
                print("="*20 + " [DEBUG] API返回原始内容 " + "="*20)
                print(response)
                print("="*60)
                self.reset_button_state()
                
                # 更新工作台显示
                try:
                    scene = self.scene()
                    workbench = None
                    if hasattr(scene, 'main_page') and hasattr(scene.main_page, 'workbench'):
                        workbench = scene.main_page.workbench
                    
                    if workbench:
                        if hasattr(workbench, 'append_output'):
                            workbench.append_output("\n\n✅ 人物提示词生成完成，已自动填充到剧本人物节点。")
                        elif hasattr(workbench, 'output_text'):
                            workbench.output_text.append("\n\n✅ 人物提示词生成完成，已自动填充到剧本人物节点。")
                except:
                    pass
                
                import re
                import json
                
                updates = {}
                
                # --- 策略1：尝试JSON解析 ---
                try:
                    clean_json = response.strip()
                    if "```json" in clean_json:
                        clean_json = clean_json.split("```json")[1].split("```")[0].strip()
                    elif "```" in clean_json:
                        clean_json = clean_json.split("```")[1].split("```")[0].strip()
                    
                    # 尝试直接解析
                    if clean_json.startswith("{") or clean_json.startswith("["):
                        data = json.loads(clean_json)
                        if isinstance(data, dict):
                            updates = data
                        elif isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict):
                                    n = item.get("角色名") or item.get("name") or item.get("Name") or item.get("role") or item.get("Role") or item.get("character") or item.get("Character") or item.get("character_name")
                                    p = item.get("提示词") or item.get("prompt") or item.get("Prompt") or item.get("description") or item.get("content") or item.get("desc")
                                    if n and p:
                                        updates[n] = p
                except Exception as e:
                    print(f"[剧本人物] JSON解析尝试失败: {e}")
                
                # --- 策略2：文本解析 (如果JSON失败或为空) ---
                if not updates:
                    # 1. 预处理响应内容
                    clean_response = response.replace("**", "").replace("##", "")
                    
                    # 2. 按行解析（不再依赖 --- 分块，而是基于状态机）
                    lines = clean_response.split('\n')
                    
                    current_name = ""
                    current_prompt = ""
                    
                    def save_current():
                        nonlocal current_name, current_prompt
                        if current_name and current_prompt:
                            # 处理风格前缀
                            style_text = ""
                            if hasattr(self, 'last_gen_style_name') and self.last_gen_style_name:
                                style_text = self.last_gen_style_name
                            
                            if style_text and style_text != "默认":
                                if not current_prompt.startswith(style_text):
                                    current_prompt = f"{style_text}，{current_prompt}"
                            
                            updates[current_name] = current_prompt
                    
                    for line in lines:
                        line = line.strip()
                        if not line: continue
                        
                        # 匹配角色名 (增强版正则：支持 - * 1. 等前缀)
                        name_match = re.match(r"^[-*]*\s*(?:(?:\d+\.|[\d]+)\s*)?(?:角色名|Role|Name|角色|Character Name|Character)\s*[:：]\s*(.*)", line, re.IGNORECASE)
                        if name_match:
                            # 遇到新角色，先保存旧的
                            save_current()
                            current_name = name_match.group(1).strip()
                            current_prompt = "" # 重置
                            continue
                            
                        # 匹配提示词 (增强版正则)
                        prompt_match = re.match(r"^[-*]*\s*(?:提示词|Prompt|Description|描述|Content)\s*[:：]\s*(.*)", line, re.IGNORECASE)
                        if prompt_match:
                            current_prompt = prompt_match.group(1).strip()
                            continue
                            
                        # 提示词延续 (非键值对行)
                        if current_name and current_prompt and ":" not in line and "：" not in line:
                             current_prompt += " " + line
                    
                    # 循环结束，保存最后一个
                    save_current()

                # --- 策略3：直接匹配现有角色名 (如果前两种都失败) ---
                if not updates:
                    print("[剧本人物] 尝试策略3：基于已知角色名匹配")
                    known_names = [row.name_edit.toPlainText().strip() for row in self.character_rows if row.name_edit.toPlainText().strip()]
                    
                    clean_response = response.replace("**", "").replace("##", "")
                    lines = clean_response.split('\n')
                    
                    for line in lines:
                        line = line.strip()
                        if not line: continue
                        
                        for name in known_names:
                            # 匹配 "Name: Prompt" 格式
                            # 使用正则确保匹配头部
                            try:
                                m = re.match(r"^[-*]*\s*" + re.escape(name) + r"\s*[:：]\s*(.*)", line, re.IGNORECASE)
                                if m:
                                    prompt_text = m.group(1).strip()
                                    if prompt_text:
                                        updates[name] = prompt_text
                            except:
                                pass
                
                print(f"[DEBUG] 解析到的更新数据: {list(updates.keys())}")

                # 更新UI
                count = 0
                for row in self.character_rows:
                    current_name = row.name_edit.toPlainText().strip()
                    if not current_name: continue
                    
                    # 归一化当前名字 (移除空白)
                    norm_current = current_name.replace(" ", "").lower()
                    
                    matched = False
                    
                    # 1. 尝试精确匹配
                    if current_name in updates:
                        row.prompt_edit.setPlainText(updates[current_name])
                        matched = True
                    else:
                        # 2. 尝试模糊匹配 (归一化后匹配)
                        for up_name, up_prompt in updates.items():
                            norm_up = up_name.replace(" ", "").lower()
                            # 双向包含检查
                            if norm_up == norm_current or norm_up in norm_current or norm_current in norm_up:
                                row.prompt_edit.setPlainText(up_prompt)
                                matched = True
                                break
                    
                    if matched:
                        count += 1
                                
                print(f"[剧本人物] 更新了 {count} 个角色的提示词")
                
                # 通知快速生成处理器
                if hasattr(self, 'fast_gen_handler'):
                    self.fast_gen_handler.on_prompts_finished()
                
                # 用户要求不要弹窗
                # from PySide6.QtWidgets import QMessageBox
                # if count > 0:
                #     QMessageBox.information(self.container, "生成完成", f"成功为 {count} 个角色生成了提示词！")
                # else:
                #     # 如果解析失败，提示用户查看DEBUG
                #     QMessageBox.warning(self.container, "生成完成", "未能匹配到任何角色。\n请检查API返回格式或角色名称是否一致。\n(详细信息请查看控制台DEBUG输出)")
                
            def generate_images(self):
                """生成人物基准图"""
                print("[剧本人物] 点击生成人物基准图")
                
                # 0. 检查是否有正在运行的任务
                if hasattr(self, 'img_worker') and self.img_worker.isRunning():
                    QMessageBox.warning(self.container, "提示", "已有任务正在进行中，请等待完成...")
                    return

                # 1. 获取选中的API Provider
                settings = QSettings("GhostOS", "App")
                provider_key = settings.value("api/image_provider", "BANANA")
                
                # 映射 provider_key 到标准名称
                # 严格匹配 setting.py 中的选项: "BANANA", "BANANA2", "Midjourney"
                provider = "BANANA"
                p_str = str(provider_key).strip()
                
                if p_str == "Midjourney":
                    provider = "Midjourney"
                elif p_str == "BANANA2":
                    provider = "BANANA2"
                elif p_str == "BANANA":
                    provider = "BANANA"
                else:
                    # 兼容旧值或手动修改的值
                    key_lower = p_str.lower()
                    if "midjourney" in key_lower or "mj" in key_lower:
                        provider = "Midjourney"
                    elif "banana2" in key_lower or "gemini 3" in key_lower:
                        provider = "BANANA2"
                    elif "gemini" in key_lower or "banana" in key_lower:
                        provider = "BANANA"
                
                print(f"[剧本人物] 使用图片API: {provider} (原始设置: {provider_key})")
                
                # 2. 获取配置
                config = {}
                try:
                    if provider == "Midjourney":
                        # 从 QSettings 读取 MJ 配置 (参考 MJ.py)
                        config['api_key'] = settings.value("providers/midjourney/api_key", "")
                        config['base_url'] = settings.value("providers/midjourney/base_url", "")
                        
                        # 如果 QSettings 为空，尝试读取 json/mj.json
                        if not config['api_key']:
                            mj_json = os.path.join(os.getcwd(), "json", "mj.json")
                            if os.path.exists(mj_json):
                                with open(mj_json, "r", encoding="utf-8") as f:
                                    data = json.load(f)
                                    config['api_key'] = data.get("api_key", "")
                                    config['base_url'] = data.get("base_url", "")
                        
                        if not config['api_key'] or not config['base_url']:
                             QMessageBox.warning(self.container, "配置缺失", "未检测到 Midjourney API 配置，请先在设置中配置。")
                             return

                    elif provider == "BANANA":
                        # 使用 Agemini.py 的逻辑读取配置
                        import Agemini
                        config = Agemini.get_config()
                        if not config.get('api_key'):
                            QMessageBox.warning(self.container, "配置缺失", "未检测到 BANANA (Gemini) API 配置，请先在设置中配置。")
                            return
                            
                    elif provider == "BANANA2":
                        # 使用 gemini30.py 的逻辑读取配置
                        import gemini30
                        config = gemini30.get_config()
                        if not config.get('api_key'):
                            QMessageBox.warning(self.container, "配置缺失", "未检测到 BANANA2 (Gemini 3.0) API 配置，请先在设置中配置。")
                            return
                except Exception as e:
                    QMessageBox.critical(self.container, "配置错误", f"读取API配置失败: {str(e)}")
                    return

                # 3. 收集任务
                tasks = []
                for row in self.character_rows:
                    # 检查是否启用 (跳过红色关闭状态的行)
                    if not row.toggle_btn.isChecked():
                        continue
                        
                    name = row.name_edit.toPlainText().strip()
                    prompt = row.prompt_edit.toPlainText().strip()
                    
                    if name and prompt:
                        # 处理附加值
                        final_prompt = prompt
                        if getattr(self, "extra_enabled", True) and getattr(self, "extra_words", ""):
                            # 附加值放在最前面
                            extra = self.extra_words.strip()
                            if extra:
                                if final_prompt:
                                    final_prompt = f"{extra}，{final_prompt}"
                                else:
                                    final_prompt = extra
                        
                        # 总是添加任务
                        if getattr(self, "style_ref_image_path", None):
                            final_prompt = f"{final_prompt} 请参考参考图的画风风格生成图片".strip()
                        tasks.append((name, final_prompt))
                
                if not tasks:
                    QMessageBox.information(self.container, "提示", "没有找到有效的人物名称和提示词。\n请先填写人物名称和提示词。")
                    return
                
                # 打印详细DEBUG信息
                print(f"\\n[剧本人物 DEBUG] 准备生成图片，共 {len(tasks)} 个任务")
                print("-" * 50)
                for i, (t_name, t_prompt) in enumerate(tasks):
                    print(f"[DEBUG 任务 {i+1}]")
                    print(f"  角色: {t_name}")
                    print(f"  最终提示词: {t_prompt}")
                print("-" * 50 + "\\n")
                
                # 4. 启动 Worker
                self.btn_gen_images.setText("⏳ 生成中...")
                self.btn_gen_images.setEnabled(False)
                
                self.img_worker = ImageGenerationWorker(tasks, provider, config)
                self.img_worker.progress.connect(self.on_img_progress)
                self.img_worker.image_generated.connect(self.on_img_generated)
                self.img_worker.finished_all.connect(self.on_img_finished)
                self.img_worker.error_occurred.connect(self.on_img_error)
                self.img_worker.start()

            def on_img_progress(self, msg):
                self.btn_gen_images.setText(msg)
                
            def on_img_generated(self, name, image_path):
                # 更新对应行的图片
                for row in self.character_rows:
                    if row.name_edit.toPlainText().strip() == name:
                        row.set_image(image_path)
                        break
                        
            def on_img_finished(self, count):
                self.btn_gen_images.setText("🎨 生成图片")
                self.btn_gen_images.setEnabled(True)
                # 用户反馈不要弹窗
                # QMessageBox.information(self.container, "完成", f"图片生成任务结束，成功生成 {count} 张图片。")
                
            def on_img_error(self, msg):
                print(f"[剧本人物] 图片生成错误: {msg}")
                
            def get_node_data(self):
                """获取节点数据用于保存"""
                characters = []
                for row in self.character_rows:
                    characters.append(row.get_data())
                    
                return {
                    "characters": characters,
                    "style_ref_image": getattr(self, "style_ref_image_path", None)
                }
                
            def load_node_data(self, data):
                """从数据加载节点"""
                # 清空现有行
                for row in self.character_rows:
                    self.scroll_layout.removeWidget(row)
                    row.deleteLater()
                self.character_rows.clear()
                
                # 加载新行
                characters = data.get("characters", [])
                for char_data in characters:
                    self.add_character_row(char_data)
                    
                # 如果没有数据，默认加3行
                if not characters:
                    self.add_character_row()
                    self.add_character_row()
                    self.add_character_row()
                
                # 重新加载附加值配置
                if hasattr(self, 'extra_manager'):
                    self.extra_manager.load_config()
                
            def load_exclude_list(self):
                """加载排除名单"""
                try:
                    json_path = os.path.join(os.getcwd(), "json", "排除名单.json")
                    if os.path.exists(json_path):
                        with open(json_path, "r", encoding="utf-8") as f:
                            self.exclude_list = json.load(f)
                    else:
                        self.exclude_list = []
                except Exception as e:
                    print(f"[剧本人物] 加载排除名单失败: {e}")
                    self.exclude_list = []

            def save_exclude_list(self):
                """保存排除名单"""
                try:
                    json_dir = os.path.join(os.getcwd(), "json")
                    if not os.path.exists(json_dir):
                        os.makedirs(json_dir)
                    
                    json_path = os.path.join(json_dir, "排除名单.json")
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(self.exclude_list, f, ensure_ascii=False, indent=4)
                except Exception as e:
                    print(f"[剧本人物] 保存排除名单失败: {e}")

            def open_exclude_dialog(self):
                """打开排除名单管理对话框"""
                dialog = ExcludeListDialog(self.exclude_list, self.container)
                if dialog.exec():
                    self.exclude_list = dialog.get_list()
                    self.save_exclude_list()
                    
                    # 立即应用排除规则：移除当前列表中已在排除名单的角色
                    rows_to_remove = []
                    removed_names = []
                    
                    for row in self.character_rows:
                        name = row.name_edit.toPlainText().strip()
                        # 检查完全匹配
                        if name and name in self.exclude_list:
                            rows_to_remove.append(row)
                            removed_names.append(name)
                    
                    if rows_to_remove:
                        for row in rows_to_remove:
                            self.scroll_layout.removeWidget(row)
                            row.deleteLater()
                            self.character_rows.remove(row)
                        
                        print(f"[剧本人物] 已根据排除名单移除: {', '.join(removed_names)}")
                        
                        # 如果删除后列表为空，补几个空行
                        if not self.character_rows:
                            self.add_character_row()
                            self.add_character_row()
                            self.add_character_row()


        return ScriptCharacterNodeImpl
