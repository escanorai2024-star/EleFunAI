"""
灵动智能体 - 二创员工模块 (重构版)
用于图片节点的右键菜单，支持提示词编辑、持久化存储和API发送
"""

import json
import os
import requests
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, 
    QPushButton, QComboBox, QMessageBox, QWidget, QScrollArea,
    QButtonGroup, QFrame, QMenu, QInputDialog, QGraphicsDropShadowEffect,
    QTabWidget
)
from PySide6.QtCore import Qt, Signal, QSize, QPoint, QThread
from PySide6.QtGui import QFont, QColor, QPixmap, QIcon, QAction

# 配置文件路径
CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'json', 'mofasetting.json')
API_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'json', 'talk_api_config.json')

class PromptGeneratorWorker(QThread):
    """AI提示词生成线程"""
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, api_url, api_key, model, context):
        super().__init__()
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.context = context

        # Register to global registry to prevent GC
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_magic_workers'):
                app._active_magic_workers = []
            app._active_magic_workers.append(self)
        self.finished.connect(self._cleanup_worker)
        self.error.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app and hasattr(app, '_active_magic_workers'):
            if self in app._active_magic_workers:
                app._active_magic_workers.remove(self)
        self.deleteLater()

    def run(self):
        try:
            system_prompt = (
                "You are a Stable Diffusion prompt expert. Based on the movie script context provided, "
                "write a detailed English prompt for the 'Current Shot'.\n"
                "Requirements:\n"
                "1. Output ONLY the English prompt text, no explanations, no translations, no other languages.\n"
                "2. Focus on visual details: lighting, camera angle, subject description, background, style.\n"
                "3. Use standard Stable Diffusion prompt format (comma separated tags).\n"
                "4. Keep it high quality (e.g., 8k, cinematic lighting, masterpiece)."
            )
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Script Context:\n{self.context}"}
            ]
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # 适配不同的API格式 (这里假设兼容OpenAI格式)
            data = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.7
            }
            
            response = requests.post(self.api_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content'].strip()
                self.finished.emit(content)
            else:
                self.error.emit("API returned unexpected format")
            
        except Exception as e:
            self.error.emit(str(e))

class MagicConfig:
    """管理魔法提示词的配置"""
    @staticmethod
    def load_prompts():
        """加载提示词列表"""
        # 默认4个提示词结构：风、林、火、山
        target_names = ["风", "林", "火", "山"]
        default_prompts = [{"name": name, "content": ""} for name in target_names]
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    prompts = data.get('prompts', [])
                    
                    if not prompts:
                        return default_prompts
                        
                    # 数据迁移：如果是旧格式（字符串列表），转换为新格式
                    if prompts and isinstance(prompts[0], str):
                        new_prompts = []
                        for i, p in enumerate(prompts):
                            name = target_names[i] if i < len(target_names) else f"提示词 {i+1}"
                            new_prompts.append({
                                "name": name, 
                                "content": p
                            })
                        prompts = new_prompts

                    # 强制更新名称为风林火山（前4个）
                    # 无论之前叫什么，只要数量不足或者名称是旧的"提示词 X"，都进行对齐
                    # 这里为了响应用户需求，直接确保有4个，并且名字正确
                    
                    # 1. 确保至少有4个，不足补齐
                    while len(prompts) < 4:
                        prompts.append({"name": "", "content": ""})
                    
                    # 2. 截取前4个
                    prompts = prompts[:4]
                    
                    # 3. 强制重命名：确保索引0-3分别是风、林、火、山
                    for i in range(4):
                        if isinstance(prompts[i], dict):
                            # 强制覆盖名称，确保不出现重复或错误的名称
                            prompts[i]["name"] = target_names[i]
                            # 确保有content字段
                            if "content" not in prompts[i]:
                                prompts[i]["content"] = ""
                        else:
                            # 如果格式不对，重置
                             prompts[i] = {"name": target_names[i], "content": ""}
                            
                    return prompts
            except Exception as e:
                print(f"Error loading magic prompts: {e}")
        
        return default_prompts

    @staticmethod
    def save_prompts(prompts):
        """保存提示词列表"""
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump({'prompts': prompts}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving magic prompts: {e}")

class MagicDialog(QDialog):
    """二创员工设置对话框"""
    
    # 信号：提示词更新，用于通知外部更新右键菜单
    prompts_updated = Signal()

    def __init__(self, image_path, parent=None, context_info=None):
        super().__init__(parent)
        self.image_path = image_path
        self.context_info = context_info
        self.generator_worker = None
        self.auto_gen_triggered = False
        
        # 移除标题栏，创建无边框窗口
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 缩小尺寸以适应简化后的界面
        self.setFixedSize(500, 450)
        
        # 加载提示词
        self.prompts = MagicConfig.load_prompts()
        self.current_index = 0
        
        self.setup_ui()
        self.setup_styles()

    def setup_styles(self):
        self.setStyleSheet("""
            QDialog {
                background: transparent;
            }
            QFrame#MainFrame {
                background-color: #ffffff; /* 纯白背景 */
                border-radius: 16px;
                border: 2px solid #4CAF50; /* 绿色边框，增强可见性 */
            }
            
            QLabel {
                font-family: "Microsoft YaHei";
                color: #2E7D32; /* 深绿色文字 */
                font-size: 14px;
                font-weight: bold;
                background-color: transparent;
            }
            QTextEdit {
                border: 1px solid #4CAF50;
                padding: 10px;
                background-color: #F1F8E9; /* 浅绿背景 */
                color: #2E7D32; /* 深绿色文字 */
                font-family: "Microsoft YaHei";
                font-size: 14px;
                border-radius: 8px;
            }
            QPushButton {
                border-radius: 6px;
                padding: 4px 12px;
                font-family: "Microsoft YaHei";
                font-weight: bold;
                color: #2E7D32; /* 绿色文字 */
            }
            /* 提示词标签页按钮样式 - 安卓风格Chip */
            QPushButton[cssClass="tab-btn"] {
                background-color: #F1F8E9; /* 浅绿背景 */
                color: #2E7D32; /* 绿色文字 */
                border: 1px solid #C8E6C9;
                border-radius: 18px; /* 圆角胶囊形 */
                margin-right: 8px;
                padding: 6px 16px;
                font-size: 14px;
                min-width: 40px;
                font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
            }
            QPushButton[cssClass="tab-btn"]:hover {
                background-color: #e8f5e9; /* 极浅的绿色悬停 */
                color: #1B5E20;
                border: 1px solid #4CAF50;
            }
            QPushButton[cssClass="tab-btn"]:checked {
                background-color: #4CAF50; /* 选中变为绿色实心 */
                color: #ffffff; /* 选中文字变白 */
                font-weight: bold;
                border: 1px solid #4CAF50;
            }
            
            /* 底部发送按钮 - 安卓风格FAB/Button */
            QPushButton[cssClass="send-btn"] {
                background-color: #4CAF50; /* 安卓绿 */
                color: white;
                font-size: 16px; /* 字体加大 */
                font-weight: bold;
                border: none;
                border-radius: 20px; /* 圆角 */
                padding: 10px 24px;
            }
            QPushButton[cssClass="send-btn"]:hover {
                background-color: #43a047;
                /* 可以加一点阴影模拟浮起，但QSS阴影支持有限 */
            }
            QPushButton[cssClass="send-btn"]:pressed {
                background-color: #388e3c;
            }
            
            /* AI生成按钮 */
            QPushButton[cssClass="ai-btn"] {
                background-color: #2196F3; /* 蓝色 */
                color: white;
                font-size: 14px;
                font-weight: bold;
                border: none;
                border-radius: 16px;
                padding: 6px 16px;
            }
            QPushButton[cssClass="ai-btn":hover {
                background-color: #1e88e5;
            }
            
            /* 关闭按钮 */
            QPushButton[cssClass="close-btn"] {
                background-color: #F1F8E9; /* 浅绿背景 */
                color: #2E7D32; /* 绿色文字 */
                border: none;
                font-size: 16px;
                font-weight: bold;
                border-radius: 15px;
                max-width: 32px;
                max-height: 32px;
            }
            QPushButton[cssClass="close-btn"]:hover {
                background-color: #ffebee;
                color: #ef5350;
            }
        """)

    def setup_ui(self):
        # 主布局，包含一个主框架用于绘制圆角背景
        main_layout = QVBoxLayout(self)
        # 设置边距以容纳阴影
        main_layout.setContentsMargins(25, 25, 25, 25)
        
        self.main_frame = QFrame()
        self.main_frame.setObjectName("MainFrame")
        self.main_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # 移除 setAutoFillBackground(True)，因为它可能与 QSS 背景颜色冲突
        # self.main_frame.setAutoFillBackground(True) 
        # 优化尺寸：稍微调宽一点，适应Chip布局
        self.setFixedSize(600, 700) # 增加尺寸以防止内容被遮挡，同时增加高度容纳图片
        
        # 添加阴影效果，增强层次感
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 4)
        self.main_frame.setGraphicsEffect(shadow)
        
        frame_layout = QVBoxLayout(self.main_frame)
        frame_layout.setContentsMargins(24, 20, 24, 24) # 增加边距，更透气
        frame_layout.setSpacing(16)
        
        # 1. 顶部区域：标签页 + 关闭按钮
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)
        
        # 标签页容器
        tabs_container = QWidget()
        tabs_container.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tabs_container.customContextMenuRequested.connect(self.show_tab_context_menu)
        
        tabs_container_layout = QHBoxLayout(tabs_container)
        tabs_container_layout.setSpacing(0)
        tabs_container_layout.setContentsMargins(0, 0, 0, 0)
        
        self.tabs_scroll = QScrollArea()
        self.tabs_scroll.setFixedHeight(50) # 稍微增高以容纳更大的点击区域
        self.tabs_scroll.setWidgetResizable(True)
        self.tabs_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.tabs_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tabs_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tabs_scroll.setStyleSheet("background-color: transparent;")
        
        self.tabs_scroll.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs_scroll.customContextMenuRequested.connect(self.show_tab_context_menu)
        
        self.tabs_widget = QWidget()
        self.tabs_layout = QHBoxLayout(self.tabs_widget)
        self.tabs_layout.setContentsMargins(0, 5, 0, 5)
        self.tabs_layout.setSpacing(4) # Chip之间的间距
        self.tabs_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        self.tab_group.buttonClicked.connect(self.on_tab_clicked)
        
        self.tabs_scroll.setWidget(self.tabs_widget)
        tabs_container_layout.addWidget(self.tabs_scroll)
        
        # 将标签页容器添加到顶部布局
        header_layout.addWidget(tabs_container, 1)
        
        # 添加关闭按钮
        self.close_btn = QPushButton("✕")
        self.close_btn.setProperty("cssClass", "close-btn")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setFixedSize(32, 32)
        self.close_btn.clicked.connect(self.close)
        header_layout.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        
        frame_layout.addLayout(header_layout)

        # 1.5 添加图片预览 (如果有图片路径)
        if self.image_path and os.path.exists(self.image_path):
            img_container = QWidget()
            img_layout = QHBoxLayout(img_container)
            img_layout.setContentsMargins(0, 0, 0, 0)
            img_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            preview_label = QLabel()
            preview_label.setFixedSize(120, 120)
            preview_label.setStyleSheet("border: 1px solid #C8E6C9; border-radius: 8px; background-color: #F1F8E9;")
            preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # 加载并缩放图片
            pixmap = QPixmap(self.image_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(118, 118, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                preview_label.setPixmap(pixmap)
            else:
                preview_label.setText("无法加载图片")
                
            img_layout.addWidget(preview_label)
            frame_layout.addWidget(img_container)
        
        # 2. 提示词输入框容器 - 全绿色边框
        input_container = QWidget()
        input_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True) # 关键：允许QWidget绘制背景
        input_container.setStyleSheet("""
            QWidget {
                background-color: #fafafa; /* 极淡的灰白底色，区分于主背景 */
                border: 2px solid #4CAF50; /* 全绿色边框 */
                border-radius: 12px;
            }
        """)
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("在此输入提示词...\n(提示：右键点击上方标签页可 新增/删除/重命名 提示词)")
        # 调整输入框高度以适应整体尺寸
        self.prompt_edit.setMinimumHeight(120)
        self.prompt_edit.textChanged.connect(self.save_current_prompt)
        input_layout.addWidget(self.prompt_edit)
        
        frame_layout.addWidget(input_container)
        
        # 3. 底部功能区
        bottom_layout = QHBoxLayout()
        
        bottom_layout.addStretch()
        
        # 右侧：保存按钮
        self.send_btn = QPushButton("💾 保存")
        self.send_btn.setProperty("cssClass", "send-btn")
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setFixedSize(140, 42) # 更大气的按钮
        self.send_btn.clicked.connect(self.save_and_close)
        
        bottom_layout.addWidget(self.send_btn)
        frame_layout.addLayout(bottom_layout)

        main_layout.addWidget(self.main_frame)

        # 初始化标签页
        self.refresh_tabs()

    def generate_prompt(self):
        """调用AI生成提示词"""
        if not self.context_info:
            return
            
        # 1. 读取API配置
        if not os.path.exists(API_CONFIG_FILE):
            if hasattr(self, 'status_label'): self.status_label.setText("⚠️ 未配置API")
            return
            
        try:
            with open(API_CONFIG_FILE, 'r', encoding='utf-8') as f:
                api_config = json.load(f)
        except Exception as e:
            if hasattr(self, 'status_label'): self.status_label.setText("⚠️ 配置文件错误")
            return
            
        # 2. 查找可用的API Key和Provider
        providers = ["ChatGPT", "DeepSeek", "Claude", "Gemini", "Hunyuan"]
        api_key = ""
        provider = ""
        
        for p in providers:
            key_name = f'{p.lower()}_api_key'
            key = api_config.get(key_name, '')
            if key:
                api_key = key
                provider = p
                break
                
        if not api_key:
            if hasattr(self, 'status_label'): self.status_label.setText("⚠️ 无有效API Key")
            return
            
        # 3. 获取URL和Model
        base_url = api_config.get('api_url', 'https://api.vectorengine.ai/v1')
        if provider == "Hunyuan":
             base_url = api_config.get('hunyuan_api_url', 'https://api.vectorengine.ai')
             api_url = f"{base_url.rstrip('/')}/v1/chat/completions"
        else:
             if base_url.rstrip('/').endswith('/v1'):
                api_url = f"{base_url.rstrip('/')}/chat/completions"
             else:
                api_url = f"{base_url.rstrip('/')}/v1/chat/completions"

        # 简单的模型选择逻辑
        model = "gpt-3.5-turbo" # 默认回退
        if provider == "DeepSeek":
            model = "deepseek-chat"
        elif provider == "Claude":
            model = "claude-3-haiku"
        elif provider == "Gemini":
            model = "gemini-pro"
        elif provider == "Hunyuan":
            model = "hunyuan-lite"
            
        # 4. 启动线程
        if hasattr(self, 'status_label'):
            self.status_label.setText("✨ AI生成中...")
        
        self.generator_worker = PromptGeneratorWorker(api_url, api_key, model, self.context_info)
        self.generator_worker.finished.connect(self.on_generation_finished)
        self.generator_worker.error.connect(self.on_generation_error)
        self.generator_worker.start()
        
    def on_generation_finished(self, content):
        """生成完成回调"""
        # 英文提示词界面已删除，暂时忽略生成结果
        pass
        
    def on_generation_error(self, error_msg):
        """生成错误回调"""
        if hasattr(self, 'status_label'):
            self.status_label.setText("❌ 生成出错")
        print(f"AI生成出错: {error_msg}")

    def refresh_tabs(self):
        """刷新标签页显示"""
        # 彻底清除布局中的所有控件
        while self.tabs_layout.count():
            item = self.tabs_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        
        # 重置按钮组（虽然不是必须的，但为了保险起见）
        # self.tab_group.buttons() 已经在上面被清理了，因为它们在layout中
        # 但为了避免残留引用，我们可以移除所有按钮
        for btn in self.tab_group.buttons():
            self.tab_group.removeButton(btn)
            
        # 重新创建按钮
        for i in range(len(self.prompts)):
            # 使用保存的名称
            prompt_data = self.prompts[i]
            # 兼容处理：如果是字符串，使用默认名称
            if isinstance(prompt_data, str):
                name = f"提示词 {i+1}"
                content = prompt_data
                # 自动升级格式
                self.prompts[i] = {"name": name, "content": content}
            else:
                name = prompt_data.get("name", f"提示词 {i+1}")
                content = prompt_data.get("content", "")
                
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setProperty("index", i)
            btn.setProperty("cssClass", "tab-btn")
            btn.setToolTip(content or "空提示词")
            
            # 为按钮也添加右键菜单策略
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(self.show_tab_context_menu)
            
            if i == self.current_index:
                btn.setChecked(True)
                
            self.tab_group.addButton(btn)
            self.tabs_layout.addWidget(btn)
            
        self.tabs_layout.addStretch()
        
        # 更新文本框内容
        if 0 <= self.current_index < len(self.prompts):
            prompt_data = self.prompts[self.current_index]
            content = prompt_data.get("content", "") if isinstance(prompt_data, dict) else prompt_data
            
            self.prompt_edit.setPlainText(content)
        else:
            self.prompt_edit.clear()

    def switch_tab(self, index):
        """切换标签页"""
        if index is not None:
            self.current_index = int(index)
            # 暂时断开信号以避免循环保存
            self.prompt_edit.blockSignals(True)
            
            prompt_data = self.prompts[self.current_index]
            content = prompt_data.get("content", "") if isinstance(prompt_data, dict) else prompt_data
            
            self.prompt_edit.setPlainText(content)
            
            self.prompt_edit.blockSignals(False)

    # 保留旧方法名以防有其他调用（虽然这里是私有的）
    def on_tab_clicked(self, btn):
        """处理标签点击"""
        index = btn.property("index")
        if index is not None:
            self.switch_tab(int(index))

    def show_tab_context_menu(self, pos):
        """显示标签页右键菜单"""
        menu = QMenu(self)
        
        # 查找点击的按钮
        clicked_btn = self.childAt(self.mapToGlobal(pos)) if isinstance(self, QWidget) else None
        # 如果是通过sender调用的（按钮信号）
        sender = self.sender()
        if isinstance(sender, QPushButton):
            clicked_btn = sender
        
        # 获取当前点击的索引
        clicked_index = -1
        if clicked_btn and isinstance(clicked_btn, QPushButton):
            idx = clicked_btn.property("index")
            if idx is not None:
                clicked_index = int(idx)
        else:
            clicked_index = self.current_index

        rename_action = QAction("✏️ 重命名", self)
        rename_action.triggered.connect(lambda: self.rename_prompt_slot(clicked_index))
        menu.addAction(rename_action)

        menu.exec(self.cursor().pos())

    def rename_prompt_slot(self, index):
        """重命名提示词"""
        if 0 <= index < len(self.prompts):
            old_name = self.prompts[index]["name"]
            new_name, ok = QInputDialog.getText(self, "重命名", "请输入新的提示词名称:", text=old_name)
            if ok and new_name.strip():
                self.prompts[index]["name"] = new_name.strip()
                MagicConfig.save_prompts(self.prompts)
                self.refresh_tabs()

    def save_current_prompt(self):
        """保存当前编辑的提示词"""
        text = self.prompt_edit.toPlainText()
        
        if 0 <= self.current_index < len(self.prompts):
            # 更新内容
            self.prompts[self.current_index]["content"] = text
            MagicConfig.save_prompts(self.prompts)
            
            # 仅更新提示信息，不改名
            btn = self.tab_group.button(self.tab_group.checkedId())
            if btn:
                btn.setToolTip(text)

    def save_and_close(self):
        """保存并关闭"""
        self.save_current_prompt()
        QMessageBox.information(self, "保存成功", "提示词已保存！")
        self.accept()
        
    def closeEvent(self, event):
        """关闭窗口时保存"""
        self.save_current_prompt()
        super().closeEvent(event)
        
    def mousePressEvent(self, event):
        """支持拖拽移动窗口"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 记录鼠标相对窗口左上角的位置
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """支持拖拽移动窗口"""
        if event.buttons() == Qt.MouseButton.LeftButton:
            # 移动窗口到鼠标当前位置减去相对偏移
            self.move(event.globalPos() - self.drag_position)
            event.accept()

class BatchMagicSettingsDialog(QDialog):
    """批量生成设置对话框（只设置提示词）"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("二创员工设置")
        self.setFixedSize(600, 400)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 说明
        info_label = QLabel("请设置“风林火山”提示词模版：")
        info_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px;")
        layout.addWidget(info_label)
        
        # 加载现有提示词
        self.prompts = MagicConfig.load_prompts()
        self.editors = []
        
        # 标签页形式展示
        tab_widget = QTabWidget()
        layout.addWidget(tab_widget)
        
        for i, prompt_data in enumerate(self.prompts):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            
            # 中文提示词
            lbl_cn = QLabel(f"{prompt_data['name']} - 中文提示词:")
            page_layout.addWidget(lbl_cn)
            
            edit_cn = QTextEdit()
            edit_cn.setPlainText(prompt_data.get("content", ""))
            edit_cn.setPlaceholderText("在此输入中文提示词...")
            page_layout.addWidget(edit_cn)
            
            self.editors.append({"cn": edit_cn, "index": i})
            tab_widget.addTab(page, prompt_data["name"])
            
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        save_btn = QPushButton("保存并继续")
        save_btn.clicked.connect(self.save_and_accept)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #6200EE;
                color: white;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3700B3;
            }
        """)
        btn_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f3f4;
                color: #333;
                padding: 8px 20px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #e8eaed;
            }
        """)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        
    def save_and_accept(self):
        """保存设置并退出"""
        # 更新 self.prompts
        for editor_map in self.editors:
            idx = editor_map["index"]
            cn_text = editor_map["cn"].toPlainText()
            
            if 0 <= idx < len(self.prompts):
                self.prompts[idx]["content"] = cn_text
                
        # 保存到配置文件
        MagicConfig.save_prompts(self.prompts)
        self.accept()
