"""
对话API配置对话框
支持多个AI提供商的API Key管理和测试
"""

import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QMessageBox, QApplication, QFrame, QScrollArea, QWidget
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont


class TestThread(QThread):
    """API测试线程 - 获取模型列表"""
    finished_signal = Signal(bool, str, list)  # success, message, models
    
    def __init__(self, provider, api_key, api_url="https://manju.chat", hunyuan_api_url="https://api.vectorengine.ai"):
        super().__init__()
        self.provider = provider
        self.api_key = api_key
        # Hunyuan使用特殊的API地址
        if provider == "Hunyuan":
            self.api_url = hunyuan_api_url
        else:
            self.api_url = api_url

        # Register to global registry to prevent GC
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_test_workers'):
                app._active_test_workers = []
            app._active_test_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        app = QApplication.instance()
        if app and hasattr(app, '_active_test_workers'):
            if self in app._active_test_workers:
                app._active_test_workers.remove(self)
        self.deleteLater()
    
    def run(self):
        """执行API测试 - 获取模型列表"""
        try:
            import http.client
            import ssl
            import json
            from urllib.parse import urlparse
            
            # 解析URL
            parsed = urlparse(self.api_url)
            host = parsed.netloc or parsed.path.split('/')[0]
            
            if not host:
                self.finished_signal.emit(False, "API地址格式错误", [])
                return
            
            # 创建HTTPS连接
            context = ssl.create_default_context()
            conn = http.client.HTTPSConnection(host, context=context, timeout=15)
            
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            # 获取模型列表（轻量级测试）
            conn.request('GET', '/v1/models', '', headers)
            res = conn.getresponse()
            data = res.read()
            
            if res.status == 200:
                result = json.loads(data.decode('utf-8'))
                if 'data' in result:
                    all_models = [model['id'] for model in result['data']]
                    
                    # 筛选当前提供商的模型
                    provider_models = []
                    provider_lower = self.provider.lower()
                    
                    for model_id in all_models:
                        if (provider_lower == "hunyuan" and model_id.startswith("hunyuan")) or \
                           (provider_lower == "chatgpt" and model_id.startswith("gpt")) or \
                           (provider_lower == "deepseek" and model_id.startswith("deepseek")) or \
                           (provider_lower == "claude" and model_id.startswith("claude")) or \
                           ("gemini" in provider_lower and model_id.startswith("gemini")):
                            provider_models.append(model_id)
                    
                    if provider_models:
                        msg = f"✅ 连接成功!\n模型数: {len(provider_models)}"
                        self.finished_signal.emit(True, msg, provider_models)
                    else:
                        msg = f"⚠️ API Key有效,但未找到{self.provider}模型"
                        self.finished_signal.emit(False, msg, [])
                else:
                    self.finished_signal.emit(False, "响应格式异常", [])
            elif res.status == 401:
                self.finished_signal.emit(False, "API Key无效 ✗", [])
            elif res.status == 429:
                self.finished_signal.emit(False, "请求过于频繁 ⚠", [])
            elif res.status == 503:
                self.finished_signal.emit(False, "服务不可用，请检查API地址", [])
            else:
                error_data = data.decode('utf-8')[:100]
                self.finished_signal.emit(False, f"错误 {res.status}: {error_data}", [])
            
            conn.close()
                
        except json.JSONDecodeError as e:
            self.finished_signal.emit(False, f"JSON解析错误: {str(e)[:50]}", [])
        except ssl.SSLError as e:
            self.finished_signal.emit(False, f"SSL错误: {str(e)[:50]}", [])
        except ConnectionError as e:
            self.finished_signal.emit(False, f"连接错误: {str(e)[:50]}", [])
        except TimeoutError:
            self.finished_signal.emit(False, "连接超时 ⏱", [])
        except Exception as e:
            error_msg = str(e)
            if "timed out" in error_msg.lower():
                self.finished_signal.emit(False, "连接超时 ⏱", [])
            elif "connection" in error_msg.lower():
                self.finished_signal.emit(False, "无法连接到服务器 🔌", [])
            else:
                self.finished_signal.emit(False, f"测试失败: {error_msg[:80]}", [])


class TestAllThread(QThread):
    """批量测试所有API的线程"""
    progress = Signal(str, bool, str, list)  # provider, success, message, models
    
    def __init__(self, providers_data, api_url="https://manju.chat", hunyuan_api_url="https://api.vectorengine.ai"):
        super().__init__()
        self.providers_data = providers_data  # [(provider, api_key), ...]
        self.api_url = api_url
        self.hunyuan_api_url = hunyuan_api_url

        # Register to global registry to prevent GC
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_test_workers'):
                app._active_test_workers = []
            app._active_test_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        app = QApplication.instance()
        if app and hasattr(app, '_active_test_workers'):
            if self in app._active_test_workers:
                app._active_test_workers.remove(self)
        self.deleteLater()

    def run(self):
        """执行批量测试"""
        import http.client
        import ssl
        import json
        from urllib.parse import urlparse
        
        for provider, api_key in self.providers_data:
            if not api_key.strip():
                self.progress.emit(provider, False, "未配置API Key ⚠", [])
                continue
            
            try:
                # Hunyuan使用特殊的API地址
                current_url = self.hunyuan_api_url if provider == "Hunyuan" else self.api_url
                parsed = urlparse(current_url)
                host = parsed.netloc or parsed.path.split('/')[0]
                
                if not host:
                    self.progress.emit(provider, False, "API地址错误", [])
                    continue
                
                context = ssl.create_default_context()
                conn = http.client.HTTPSConnection(host, context=context, timeout=15)
                
                headers = {
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
                
                # 获取模型列表
                conn.request('GET', '/v1/models', '', headers)
                res = conn.getresponse()
                data = res.read()
                
                if res.status == 200:
                    result = json.loads(data.decode('utf-8'))
                    if 'data' in result:
                        all_models = [model['id'] for model in result['data']]
                        
                        # 筛选模型
                        provider_models = []
                        provider_lower = provider.lower()
                        
                        for model_id in all_models:
                            if (provider_lower == "hunyuan" and model_id.startswith("hunyuan")) or \
                               (provider_lower == "chatgpt" and model_id.startswith("gpt")) or \
                               (provider_lower == "deepseek" and model_id.startswith("deepseek")) or \
                               (provider_lower == "claude" and model_id.startswith("claude")) or \
                               ("gemini" in provider_lower and model_id.startswith("gemini")):
                                provider_models.append(model_id)
                        
                        if provider_models:
                            msg = f"✓ 成功 ({len(provider_models)}个模型)"
                            self.progress.emit(provider, True, msg, provider_models)
                        else:
                            self.progress.emit(provider, False, "无可用模型", [])
                    else:
                        self.progress.emit(provider, False, "响应格式异常", [])
                elif res.status == 401:
                    self.progress.emit(provider, False, "API Key无效 ✗", [])
                elif res.status == 429:
                    self.progress.emit(provider, False, "请求频繁 ⚠", [])
                elif res.status == 503:
                    self.progress.emit(provider, False, "服务不可用", [])
                else:
                    self.progress.emit(provider, False, f"错误: {res.status}", [])
                
                conn.close()
                
            except json.JSONDecodeError:
                self.progress.emit(provider, False, "JSON解析错误", [])
            except ssl.SSLError:
                self.progress.emit(provider, False, "SSL错误", [])
            except (ConnectionError, TimeoutError):
                self.progress.emit(provider, False, "连接失败", [])
            except Exception as e:
                error_msg = str(e)
                if len(error_msg) > 30:
                    error_msg = error_msg[:30] + "..."
                self.progress.emit(provider, False, error_msg, [])


class TalkAPIDialog(QDialog):
    """对话API配置对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("💬 对话 API 配置中心")
        self.setFixedSize(780, 750)
        
        # 线程对象
        self.test_thread = None
        self.test_all_thread = None
        
        # 使用json文件保存配置
        import os, sys
        app_root = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        self.config_dir = os.path.join(app_root, 'json')
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_file = os.path.join(self.config_dir, 'talk_api_config.json')
        
        # 存储输入框和按钮
        self.key_inputs = {}
        self.eye_buttons = {}
        self.test_buttons = {}
        
        self.setup_ui()
        self.apply_styles()
        self.load_config()
    
    def setup_ui(self):
        """设置UI布局"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 创建滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # 滚动内容容器
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: #0a0a0a;")
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        
        # API地址信息 - 简约风格
        api_info_frame = QFrame()
        api_info_frame.setObjectName("apiInfoFrame")
        api_info_layout = QVBoxLayout(api_info_frame)
        api_info_layout.setContentsMargins(16, 14, 16, 14)
        api_info_layout.setSpacing(10)
        
        # 标题行 - 简约风格
        title_layout = QHBoxLayout()
        api_icon = QLabel("📡")
        api_icon.setStyleSheet("font-size: 18px;")
        title_layout.addWidget(api_icon)
        
        api_label = QLabel("API 地址配置")
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        api_label.setFont(font)
        api_label.setStyleSheet("color: #ffffff; padding-bottom: 4px;")
        title_layout.addWidget(api_label)
        title_layout.addStretch()
        api_info_layout.addLayout(title_layout)
        
        # API地址输入框 - 简约风格
        self.api_url_input = QLineEdit()
        self.api_url_input.setText("https://manju.chat")
        self.api_url_input.setPlaceholderText("输入API地址，例如: https://manju.chat")
        self.api_url_input.setFixedHeight(36)
        api_info_layout.addWidget(self.api_url_input)
        
        # 添加Hunyuan说明
        hunyuan_note = QLabel("ℹ️ Hunyuan使用专用API地址 (api.vectorengine.ai)")
        hunyuan_note.setStyleSheet("""
            color: #888888;
            font-size: 10px;
            padding: 2px 0;
        """)
        api_info_layout.addWidget(hunyuan_note)
        
        layout.addWidget(api_info_frame)
        layout.addSpacing(12)
        
        # 创建各个提供商的API Key输入
        providers = [
            ("Hunyuan", "🤖"),
            ("ChatGPT", "💚"),
            ("DeepSeek", "🔍"),
            ("Claude", "🧠"),
            ("Gemini 2.5", "✨")
        ]
        
        for provider, emoji in providers:
            # 提供商卡片 - 简约风格
            provider_frame = QFrame()
            provider_frame.setObjectName("providerFrame")
            provider_layout = QVBoxLayout(provider_frame)
            provider_layout.setContentsMargins(16, 14, 16, 14)
            provider_layout.setSpacing(10)
            
            # 提供商标题 - 简约风格
            header_layout = QHBoxLayout()
            icon_label = QLabel(emoji)
            icon_label.setStyleSheet("font-size: 18px;")
            header_layout.addWidget(icon_label)
            
            name_label = QLabel(f"{provider} API Key")
            font = QFont()
            font.setPointSize(10)
            font.setBold(True)
            name_label.setFont(font)
            name_label.setStyleSheet("color: #ffffff;")
            header_layout.addWidget(name_label)
            header_layout.addStretch()
            provider_layout.addLayout(header_layout)
            
            # 输入框和按钮行
            input_layout = QHBoxLayout()
            input_layout.setSpacing(8)
            
            # API Key 输入框 - 简约风格
            key_input = QLineEdit()
            key_input.setEchoMode(QLineEdit.EchoMode.Password)
            key_input.setPlaceholderText(f"请输入 {provider} 的 API Key")
            key_input.setFixedHeight(36)
            input_layout.addWidget(key_input, 1)
            self.key_inputs[provider] = key_input
            
            # 👁️ 显示/隐藏密码按钮 - 简约风格
            eye_btn = QPushButton("👁")
            eye_btn.setFixedSize(36, 36)
            eye_btn.setCheckable(True)
            eye_btn.setCursor(Qt.PointingHandCursor)
            eye_btn.clicked.connect(self.make_toggle_func(key_input, eye_btn))
            input_layout.addWidget(eye_btn)
            self.eye_buttons[provider] = eye_btn
            
            # 测试连接按钮 - 简约风格
            test_btn = QPushButton("测试")
            test_btn.setFixedSize(70, 36)
            test_btn.setCursor(Qt.PointingHandCursor)
            test_btn.clicked.connect(self.make_test_func(provider, key_input, test_btn))
            input_layout.addWidget(test_btn)
            self.test_buttons[provider] = test_btn
            
            provider_layout.addLayout(input_layout)
            layout.addWidget(provider_frame)
        
        layout.addStretch(1)
        
        # 设置滚动内容
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)
        
        # 底部按钮区
        bottom_bar = QFrame()
        bottom_bar.setObjectName("bottomBar")
        bottom_bar.setFixedHeight(64)
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(20, 12, 20, 12)
        bottom_layout.setSpacing(10)
        
        # 测试所有连接按钮 - 简约风格
        self.test_all_btn = QPushButton("测试所有连接")
        self.test_all_btn.setFixedSize(140, 40)
        self.test_all_btn.setCursor(Qt.PointingHandCursor)
        self.test_all_btn.clicked.connect(self.test_all_connections)
        bottom_layout.addWidget(self.test_all_btn)
        
        bottom_layout.addStretch(1)
        
        # 保存按钮
        save_btn = QPushButton("保存设置")
        save_btn.setObjectName("saveButton")
        save_btn.setFixedSize(120, 40)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self.save_settings)
        bottom_layout.addWidget(save_btn)
        
        main_layout.addWidget(bottom_bar)
    
    def apply_styles(self):
        """应用样式表 - 与AI Agent页面统一的深色主题"""
        self.setStyleSheet("""
            /* 主对话框 - 纯黑背景 */
            QDialog {
                background-color: #000000;
                color: #ffffff;
            }
            
            /* 滚动区域 */
            QScrollArea {
                background: transparent;
                border: none;
            }
            
            /* API信息框 - 深灰主题 */
            QFrame#apiInfoFrame {
                background-color: #1a1a1a;
                border: 1px solid #2a2a2a;
                border-radius: 8px;
            }
            
            /* 提供商卡片 - 深灰带细边框 */
            QFrame#providerFrame {
                background-color: #1a1a1a;
                border: 1px solid #2a2a2a;
                border-radius: 8px;
            }
            QFrame#providerFrame:hover {
                border-color: #3a3a3a;
                background-color: #1f1f1f;
            }
            
            /* 底部栏 - 深黑 */
            QFrame#bottomBar {
                background-color: #0a0a0a;
                border-top: 1px solid #1a1a1a;
            }
            
            /* 标签 */
            QLabel {
                color: #e0e0e0;
                font-size: 12px;
            }
            
            /* 输入框 - 统一深色风格 */
            QLineEdit {
                background-color: #0a0a0a;
                color: #ffffff;
                border: 1px solid #2a2a2a;
                border-radius: 6px;
                padding: 0 12px;
                font-size: 12px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
            QLineEdit:hover {
                border-color: #3a3a3a;
                background-color: #0f0f0f;
            }
            QLineEdit:focus {
                border-color: #00bfff;
                background-color: #0f0f0f;
            }
            
            /* 普通按钮 - 深色风格 */
            QPushButton {
                background-color: #1a1a1a;
                color: #e0e0e0;
                border: 1px solid #2a2a2a;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #252525;
                border-color: #3a3a3a;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #0f0f0f;
                border-color: #00bfff;
            }
            QPushButton:disabled {
                background-color: #0d0d0d;
                color: #404040;
                border-color: #1a1a1a;
            }
            
            /* 保存按钮 - 蓝绿渐变 */
            QPushButton#saveButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00bfff, stop:0.5 #00e5a0, stop:1 #00ff88);
                color: #000000;
                border: none;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#saveButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00ff88, stop:0.5 #00e5a0, stop:1 #00bfff);
            }
            QPushButton#saveButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00a0d0, stop:1 #00cc70);
            }
            
            /* 滚动条 - 简约风格 */
            QScrollBar:vertical {
                background: #0a0a0a;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #2a2a2a;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #3a3a3a;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)
    
    def make_toggle_func(self, input_widget, button):
        """创建密码显示/隐藏切换函数"""
        def toggle():
            if button.isChecked():
                input_widget.setEchoMode(QLineEdit.EchoMode.Normal)
                button.setText("🙈")
            else:
                input_widget.setEchoMode(QLineEdit.EchoMode.Password)
                button.setText("👁")
        return toggle
    
    def _lighten_color(self, hex_color, factor=0.15):
        """将颜色变亮"""
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        lightened = tuple(min(255, int(c + (255 - c) * factor)) for c in rgb)
        return '#' + ''.join(f'{c:02x}' for c in lightened)
    
    def _darken_color(self, hex_color, factor=0.15):
        """将颜色变暗"""
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        darkened = tuple(int(c * (1 - factor)) for c in rgb)
        return '#' + ''.join(f'{c:02x}' for c in darkened)
    
    def _to_rgba(self, hex_color, alpha=0.5):
        """将十六进制颜色转换为RGBA"""
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return f'rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {alpha})'
    
    def make_test_func(self, provider, input_widget, button):
        """创建API测试函数"""
        def test():
            try:
                api_key = input_widget.text().strip()
                if not api_key:
                    QMessageBox.warning(self, "提示", f"请先输入 {provider} 的API Key")
                    return
                
                # 获取API地址
                api_url = self.api_url_input.text().strip()
                if not api_url:
                    api_url = "https://manju.chat"
                
                # Hunyuan使用特殊的API地址
                hunyuan_api_url = "https://api.vectorengine.ai"
                
                # 禁用按钮并显示测试中
                button.setText("⏳")
                button.setEnabled(False)
                QApplication.processEvents()
                
                # 创建测试线程，传入API地址
                self.test_thread = TestThread(provider, api_key, api_url, hunyuan_api_url)
                
                def on_finished(success, message, models):
                    try:
                        button.setText("测试")
                        button.setEnabled(True)
                        
                        if success:
                            # 显示模型列表
                            models_text = "\n".join([f"  • {m}" for m in models[:10]])  # 最多显示10个
                            if len(models) > 10:
                                models_text += f"\n  ... 还有 {len(models) - 10} 个模型"
                            
                            QMessageBox.information(
                                self, 
                                "✅ 测试成功", 
                                f"{provider} API连接正常!\n\n{message}\n\n示例模型:\n{models_text}"
                            )
                        else:
                            QMessageBox.critical(
                                self, 
                                "❌ 测试失败", 
                                f"{provider} API连接失败!\n\n错误: {message}"
                            )
                    except Exception as e:
                        print(f"[测试回调错误] {e}")
                        button.setText("测试")
                        button.setEnabled(True)
                
                self.test_thread.finished_signal.connect(on_finished)
                self.test_thread.start()
                
            except Exception as e:
                print(f"[测试启动错误] {e}")
                button.setText("测试")
                button.setEnabled(True)
                QMessageBox.critical(self, "错误", f"启动测试失败: {str(e)}")
        
        return test
    
    def test_all_connections(self):
        """测试所有API连接"""
        try:
            # 获取API地址
            api_url = self.api_url_input.text().strip()
            if not api_url:
                api_url = "https://manju.chat"
            
            # Hunyuan使用特殊的API地址
            hunyuan_api_url = "https://api.vectorengine.ai"
            
            self.test_all_btn.setEnabled(False)
            self.test_all_btn.setText("⏳ 测试中...")
            QApplication.processEvents()
            
            # 收集所有API Key
            providers_data = []
            for provider in ["Hunyuan", "ChatGPT", "DeepSeek", "Claude", "Gemini 2.5"]:
                api_key = self.key_inputs[provider].text().strip()
                providers_data.append((provider, api_key))
            
            # 创建批量测试线程，传入API地址
            self.test_all_thread = TestAllThread(providers_data, api_url, hunyuan_api_url)
            self.test_results = {}
            
            def on_progress(provider, success, message, models):
                try:
                    self.test_results[provider] = {
                        "success": success, 
                        "message": message,
                        "models": models
                    }
                    icon = '✅' if success else '❌'
                    print(f"[测试进度] {icon} {provider}: {message}")
                except Exception as e:
                    print(f"[进度回调错误] {e}")
            
            def on_finished():
                try:
                    self.test_all_btn.setEnabled(True)
                    self.test_all_btn.setText("测试所有连接")
                    
                    # 显示结果
                    result_text = "📊 测试结果:\n\n"
                    for provider in ["Hunyuan", "ChatGPT", "DeepSeek", "Claude", "Gemini 2.5"]:
                        if provider in self.test_results:
                            result = self.test_results[provider]
                            icon = "✅" if result["success"] else "❌"
                            msg = result["message"]
                            result_text += f"{icon} {provider}: {msg}\n"
                            
                            # 如果有模型列表，显示前3个
                            if result["models"]:
                                models_preview = ", ".join(result["models"][:3])
                                if len(result["models"]) > 3:
                                    models_preview += f" ..."
                                result_text += f"   示例: {models_preview}\n"
                        else:
                            result_text += f"⚪ {provider}: 未测试\n"
                    
                    QMessageBox.information(self, "测试完成", result_text)
                except Exception as e:
                    print(f"[完成回调错误] {e}")
                    self.test_all_btn.setEnabled(True)
                    self.test_all_btn.setText("测试所有连接")
            
            self.test_all_thread.progress.connect(on_progress)
            self.test_all_thread.finished.connect(on_finished)
            self.test_all_thread.start()
            
        except Exception as e:
            print(f"[批量测试启动错误] {e}")
            self.test_all_btn.setEnabled(True)
            self.test_all_btn.setText("测试所有连接")
            QMessageBox.critical(self, "错误", f"测试失败: {str(e)}")
    
    def closeEvent(self, event):
        """对话框关闭时清理线程"""
        try:
            # 等待测试线程结束
            if self.test_thread and self.test_thread.isRunning():
                self.test_thread.wait(1000)  # 最多等待1秒
                if self.test_thread.isRunning():
                    self.test_thread.terminate()
            
            # 等待批量测试线程结束
            if self.test_all_thread and self.test_all_thread.isRunning():
                self.test_all_thread.wait(1000)
                if self.test_all_thread.isRunning():
                    self.test_all_thread.terminate()
        except Exception as e:
            print(f"[清理线程错误] {e}")
        
        event.accept()
    
    def load_config(self):
        """从JSON文件加载配置"""
        try:
            import json
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                    # 加载通用API地址（用于其他提供商）
                    if 'api_url' in config:
                        self.api_url_input.setText(config['api_url'])
                    
                    # 注意：Hunyuan使用专门的API地址 (api.vectorengine.ai)
                    # 其他提供商使用 api_url_input 中的地址
                    
                    # 加载各个提供商的API Key
                    for provider in self.key_inputs.keys():
                        key = config.get(f'{provider.lower()}_api_key', '')
                        if key:
                            self.key_inputs[provider].setText(key)
        except Exception as e:
            print(f"加载配置失败: {e}")
    
    def save_settings(self):
        """保存所有API配置到JSON文件"""
        try:
            import json
            
            config = {
                'api_url': self.api_url_input.text().strip(),
                'hunyuan_api_url': 'https://api.vectorengine.ai'  # Hunyuan专用地址
            }
            
            # 保存所有API Key
            for provider, input_widget in self.key_inputs.items():
                api_key = input_widget.text().strip()
                config[f'{provider.lower()}_api_key'] = api_key
            
            # 写入JSON文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            QMessageBox.information(self, "✅ 保存成功", f"API 配置已保存到:\n{self.config_file}")
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "❌ 保存失败", f"保存配置时发生错误:\n{str(e)}")
