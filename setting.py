from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QComboBox, QHBoxLayout, 
    QPushButton, QMessageBox, QProgressDialog, QApplication, QFrame, QScrollArea, QWidget, QCheckBox
)
from pytorch import open_pytorch_download
from pytorch import install_pytorch
from PySide6.QtCore import Qt, QSettings, QUrl
from PySide6.QtGui import QDesktopServices, QFont
# 移除公网/本地IP显示功能后,不再需要网络接口枚举
from Agemini import ConfigDialog as AgeminiConfigDialog
from MJ import ConfigDialog as MidjourneyConfigDialog
from gemini30 import ConfigDialog as Gemini30ConfigDialog
from Asora2 import ConfigDialog as Sora2ConfigDialog
from Awan25 import ConfigDialog as Wan25ConfigDialog
from Jimeng import ConfigDialog as JimengConfigDialog
from Hailuo02 import ConfigDialog as Hailuo02ConfigDialog
from talkAPI import TalkAPIDialog


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Read current language
        settings = QSettings("GhostOS", "App")
        lang_code = settings.value("i18n/language", "")
        if not lang_code:
            try:
                from PySide6.QtCore import QLocale
                sysloc = str(QLocale.system().name()).lower()
            except Exception:
                sysloc = ''
            lang_code = "zh-CN" if sysloc.startswith("zh") else "en-US"
            settings.setValue("i18n/language", lang_code)
        is_en = not str(lang_code).startswith("zh")
        self._is_en = is_en
        
        self.setWindowTitle("Settings" if is_en else "⚙️ 设置")
        self.setFixedSize(680, 720)
        
        # 主布局
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
        scroll_content.setStyleSheet("""
            background: #ffffff;
        """)
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        
        # ==================== 1. 语言设置区域 ====================
        lang_section = self._create_section_title("🌍 " + ("Language" if is_en else "语言设置"))
        layout.addWidget(lang_section)
        
        self.combo_lang = QComboBox()
        self.combo_lang.setFixedHeight(42)
        self.combo_lang.setStyleSheet("""
            QComboBox {
                background: #ffffff;
                color: #333333;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 13px;
                font-weight: 500;
            }
            QComboBox:hover {
                border: 1px solid #c0c0c0;
                background: #f9f9f9;
            }
            QComboBox::drop-down {
                border: none;
                width: 32px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #666666;
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                background: #ffffff;
                color: #333333;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                selection-background-color: #f0f0f0;
                selection-color: #000000;
                outline: none;
                padding: 4px;
            }
        """)
        self._lang_map = [
            ("中文（简体）", "zh-CN"),
            ("English", "en-US"),
        ]
        for name, _code in self._lang_map:
            self.combo_lang.addItem(name)
        
        # 设置默认语言
        import os, json, sys
        app_root = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        cfg_path = os.path.join(app_root, 'json', 'language.json')
        prev_lang_code = settings.value("i18n/language", "")
        try:
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    code = str(data.get('code') or data.get('language') or '').strip()
                    if code in ("zh-CN", "en-US"):
                        prev_lang_code = code
                        settings.setValue("i18n/language", code)
        except Exception:
            pass
        if not prev_lang_code or str(prev_lang_code) not in ("zh-CN", "en-US"):
            prev_lang_code = "en-US"
            settings.setValue("i18n/language", prev_lang_code)
        
        for idx, (name, code) in enumerate(self._lang_map):
            if code == prev_lang_code:
                self.combo_lang.setCurrentIndex(idx)
                break
        
        layout.addWidget(self.combo_lang)
        layout.addSpacing(10)
        
        # ==================== 2. 对话 API 区域 ====================
        talk_section = self._create_section_title("💬 " + ("Talk API" if is_en else "对话 API"))
        layout.addWidget(talk_section)
        
        talk_api_btn = QPushButton("🔑 " + ("Configure Talk API Keys" if is_en else "配置对话 API 密钥"))
        talk_api_btn.setFixedHeight(50)
        talk_api_btn.setCursor(Qt.PointingHandCursor)
        talk_api_btn.setStyleSheet("""
            QPushButton {
                background: #ffffff;
                color: #333333;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #f9f9f9;
                border: 1px solid #c0c0c0;
                color: #000000;
            }
            QPushButton:pressed {
                background: #f0f0f0;
            }
        """)
        talk_api_btn.clicked.connect(self._open_talk_api)
        layout.addWidget(talk_api_btn)
        layout.addSpacing(10)
        
        # ==================== 3. 图片生成 API ====================
        img_section = self._create_section_title("🎨 " + ("Image Generation API" if is_en else "图片生成 API"))
        layout.addWidget(img_section)
        
        # 下拉选择
        self.combo_img = QComboBox()
        self.combo_img.setFixedHeight(40)
        img_items_en = ["BANANA", "BANANA2", "Midjourney"]
        img_items_zh = ["BANANA", "BANANA2", "Midjourney"]
        self.combo_img.addItems(img_items_en if is_en else img_items_zh)
        
        # 恢复之前的选择
        prev_img = settings.value("api/image_provider")
        if prev_img:
            def map_img(name: str) -> str:
                n = str(name).strip()
                l = n.lower()
                if l in ("midjourney", "mj"):
                    return "Midjourney"
                if l in ("gemini30", "gemini 3.0", "geimini3", "geimini30", "banana2"):
                    return "BANANA2"
                if l.startswith("gemini") or l == "banana":
                    return "BANANA"
                return n
            mapped = map_img(str(prev_img))
            if mapped in [self.combo_img.itemText(i) for i in range(self.combo_img.count())]:
                self.combo_img.setCurrentText(mapped)
        
        layout.addWidget(self.combo_img)

        # 监听图片API切换，如果选择 BANANA 提示模型已过期
        def _on_image_api_changed(text: str):
            name = str(text).strip().upper()
            if name == "BANANA":
                QMessageBox.information(
                    self,
                    "提示",
                    "此模型已过期。请选择其他模型。"
                )
        self.combo_img.currentTextChanged.connect(_on_image_api_changed)
        
        # 快捷配置按钮
        img_row = QHBoxLayout()
        img_row.setSpacing(12)
        btn_gemini = self._create_config_button("BANANA", "#f472b6")
        btn_gemini30 = self._create_config_button("BANANA2", "#a78bfa")
        btn_journey = self._create_config_button("Midjourney", "#60a5fa")
        btn_gemini.clicked.connect(self._open_gemini)
        btn_gemini30.clicked.connect(self._open_gemini30)
        btn_journey.clicked.connect(self._open_midjourney)
        img_row.addWidget(btn_gemini)
        img_row.addWidget(btn_gemini30)
        img_row.addWidget(btn_journey)
        layout.addLayout(img_row)
        layout.addSpacing(10)
        
        # ==================== 4. 视频生成 API ====================
        video_section = self._create_section_title("🎬 " + ("Video Generation API" if is_en else "视频生成 API"))
        layout.addWidget(video_section)
        
        self.combo_video = QComboBox()
        self.combo_video.setFixedHeight(40)
        video_items_en = ["Sora2", "Wan2.5", "Jimeng", "Hailuo 02"]
        video_items_zh = ["Sora2", "万象2.5", "即梦", "海螺02"]
        self.combo_video.addItems(video_items_en if is_en else video_items_zh)
        
        # 恢复之前的选择
        prev_video = settings.value("api/video_provider")
        if prev_video:
            def map_video(name: str) -> str:
                if name in ("万象2.5", "Wan2.5"):
                    return "Wan2.5" if is_en else "万象2.5"
                if name in ("即梦", "Jimeng"):
                    return "Jimeng" if is_en else "即梦"
                if name in ("海螺02", "Hailuo 02", "Hailuo02"):
                    return "Hailuo 02" if is_en else "海螺02"
                return name
            mapped_v = map_video(str(prev_video))
            if mapped_v in [self.combo_video.itemText(i) for i in range(self.combo_video.count())]:
                self.combo_video.setCurrentText(mapped_v)
        
        layout.addWidget(self.combo_video)
        
        # 快捷配置按钮
        video_row = QHBoxLayout()
        video_row.setSpacing(12)
        btn_sora2 = self._create_config_button("Sora 2", "#fb923c")
        btn_wan25 = self._create_config_button("Wan2.5" if is_en else "万象2.5", "#34d399")
        btn_jimeng = self._create_config_button("Jimeng" if is_en else "即梦", "#60a5fa")
        btn_hailuo = self._create_config_button("Hailuo 02" if is_en else "海螺02", "#8b5cf6")
        
        btn_sora2.clicked.connect(self._open_sora2)
        btn_wan25.clicked.connect(self._open_wan25)
        btn_jimeng.clicked.connect(self._open_jimeng)
        btn_hailuo.clicked.connect(self._open_hailuo02)
        
        video_row.addWidget(btn_sora2)
        video_row.addWidget(btn_wan25)
        video_row.addWidget(btn_jimeng)
        video_row.addWidget(btn_hailuo)
        layout.addLayout(video_row)
        layout.addSpacing(10)
        
        # ==================== 5. 系统信息 ====================
        system_section = self._create_section_title("💻 " + ("System Information" if is_en else "系统信息"))
        layout.addWidget(system_section)
        
        # GPU 信息
        gpu_info_frame = QFrame()
        gpu_info_frame.setObjectName("infoFrame")
        gpu_layout = QHBoxLayout(gpu_info_frame)
        gpu_layout.setContentsMargins(16, 12, 16, 12)
        
        gpu_icon = QLabel("🎮")
        gpu_icon.setStyleSheet("font-size: 20px;")
        gpu_layout.addWidget(gpu_icon)
        
        gpu_label = QLabel()
        try:
            import sys, os, site
            info = 'CPU'
            has_torch = False
            try:
                import torch
                has_torch = True
                if torch.cuda.is_available():
                    name = torch.cuda.get_device_name(0)
                    info = f'GPU: {name}'
                else:
                    info = 'GPU: 未检测到，使用CPU' if not is_en else 'GPU: Not detected, using CPU'
            except Exception:
                # 注入常见site-packages后重试
                paths = []
                base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
                paths.append(os.path.join(base_dir, '.venv', 'Lib', 'site-packages'))
                for p in site.getsitepackages():
                    paths.append(p)
                try:
                    paths.append(site.getusersitepackages())
                except Exception:
                    pass
                bp = getattr(sys, 'base_prefix', sys.prefix)
                paths.append(os.path.join(bp, 'Lib', 'site-packages'))
                for p in paths:
                    if isinstance(p, str) and os.path.isdir(p) and p not in sys.path:
                        sys.path.insert(0, p)
                try:
                    import torch
                    has_torch = True
                    if torch.cuda.is_available():
                        name = torch.cuda.get_device_name(0)
                        info = f'GPU: {name}'
                    else:
                        info = 'GPU: 未检测到，使用CPU' if not is_en else 'GPU: Not detected, using CPU'
                except Exception:
                    info = 'GPU: 未安装torch' if not is_en else 'GPU: PyTorch not installed'
            gpu_label.setText(info)
        except Exception:
            gpu_label.setText('GPU: N/A')
        
        gpu_layout.addWidget(gpu_label, 1)
        
        install_link = QLabel()
        install_link.setObjectName('installLink')
        install_link.setText('<a href="#">' + ('Auto Install' if is_en else '自动安装环境') + '</a>')
        install_link.setTextFormat(Qt.RichText)
        install_link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        install_link.setOpenExternalLinks(False)
        install_link.linkActivated.connect(lambda _href: open_pytorch_download(self))
        gpu_layout.addWidget(install_link)
        
        layout.addWidget(gpu_info_frame)
        layout.addSpacing(10)
        

        # ==================== 6. 推荐 API ====================
        recommend_label = QLabel()
        recommend_label.setObjectName("recommendLabel")
        recommend_label.setText('💡 ' + ("Recommended API: " if is_en else "推荐API：") + '<a href="https://ai.159263.xyz">https://ai.159263.xyz</a>')
        recommend_label.setTextFormat(Qt.RichText)
        recommend_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        recommend_label.setOpenExternalLinks(True)
        recommend_label.setAlignment(Qt.AlignLeft)
        layout.addWidget(recommend_label)

        layout.addStretch(1)
        
        # 设置滚动内容
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)
        
        # ==================== 底部按钮区 ====================
        bottom_bar = QFrame()
        bottom_bar.setObjectName("bottomBar")
        bottom_bar.setFixedHeight(70)
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(24, 12, 24, 12)
        bottom_layout.setSpacing(12)
        
        bottom_layout.addStretch(1)
        
        btn_cancel = QPushButton("✖ " + ("Cancel" if is_en else "取消"))
        btn_cancel.setFixedSize(120, 42)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(btn_cancel)
        
        btn_ok = QPushButton("✔ " + ("Save" if is_en else "保存"))
        btn_ok.setObjectName("saveButton")
        btn_ok.setFixedSize(120, 42)
        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_ok.clicked.connect(self.accept)
        bottom_layout.addWidget(btn_ok)
        
        main_layout.addWidget(bottom_bar)
        
        # 保存选择
        self.selected_image_api = self.combo_img.currentText()
        self.selected_video_api = self.combo_video.currentText()
        
        # 应用样式
        self.apply_styles()
    
    def _create_section_title(self, text):
        """创建分区标题"""
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        label.setFont(font)
        return label
    
    def _create_config_button(self, text, color):
        """创建配置按钮 - 简洁主题"""
        btn = QPushButton(text)
        btn.setFixedHeight(38)
        btn.setCursor(Qt.PointingHandCursor)
        
        # 使用传入的颜色作为强调色
        btn.setStyleSheet(f"""
            QPushButton {{
                background: #ffffff;
                color: #333333;
                border: 1px solid #e0e0e0;
                border-left: 4px solid {color};
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: 600;
                text-align: left;
            }}
            QPushButton:hover {{
                background: #f9f9f9;
                border: 1px solid #c0c0c0;
                border-left: 4px solid {color};
            }}
            QPushButton:pressed {{
                background: #f0f0f0;
            }}
        """)
        return btn
    
    def _to_rgba_hex(self, hex_color, alpha=0.5):
        """将十六进制颜色转换为带透明度的颜色"""
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        darkened = tuple(int(c * alpha) for c in rgb)
        return '#' + ''.join(f'{int(c):02x}' for c in darkened)
    
    def _darken_color(self, hex_color, factor=0.15):
        """将颜色变暗"""
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        darkened = tuple(int(c * (1 - factor)) for c in rgb)
        return '#' + ''.join(f'{c:02x}' for c in darkened)
    
    def _lighten_color(self, hex_color, factor=0.15):
        """将颜色变亮"""
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        lightened = tuple(min(255, int(c + (255 - c) * factor)) for c in rgb)
        return '#' + ''.join(f'{c:02x}' for c in lightened)
    
    def apply_styles(self):
        """应用样式表 - 简洁白底主题"""
        self.setStyleSheet("""
            /* 主对话框 - 纯白背景 */
            QDialog {
                background: #ffffff;
                color: #333333;
            }
            
            /* 滚动区域 */
            QScrollArea {
                background: transparent;
                border: none;
            }
            
            /* 分区标题 */
            QLabel#sectionTitle {
                color: #202124;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 0 6px 0;
                margin-bottom: 8px;
                border-bottom: 1px solid #f0f0f0;
            }
            
            /* 普通标签 */
            QLabel {
                color: #5f6368;
                font-size: 12px;
            }
            
            /* 信息框 - 浅灰背景 */
            QFrame#infoFrame {
                background: #f8f9fa;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
            }
            
            /* 底部栏 - 白底顶边框 */
            QFrame#bottomBar {
                background: #ffffff;
                border-top: 1px solid #f0f0f0;
            }
            
            /* 下拉框 */
            QComboBox {
                background: #ffffff;
                color: #333333;
                border: 1px solid #dadce0;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QComboBox:hover {
                border: 1px solid #b0b0b0;
                background: #f1f3f4;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #5f6368;
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                background: #ffffff;
                color: #333333;
                border: 1px solid #dadce0;
                selection-background-color: #e8f0fe;
                selection-color: #1967d2;
                outline: none;
            }
            
            /* 普通按钮 */
            QPushButton {
                background: #ffffff;
                color: #3c4043;
                border: 1px solid #dadce0;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #f1f3f4;
                border: 1px solid #dadce0;
                color: #202124;
            }
            QPushButton:pressed {
                background: #e8eaed;
            }
            
            /* 保存按钮 - 蓝色主色调 */
            QPushButton#saveButton {
                background: #1a73e8;
                color: #ffffff;
                border: none;
                font-weight: bold;
            }
            QPushButton#saveButton:hover {
                background: #1967d2;
            }
            QPushButton#saveButton:pressed {
                background: #185abc;
            }
            
            /* 链接 - 蓝色 */
            QLabel#helpLink, QLabel#installLink, QLabel#recommendLabel {
                color: #1a73e8;
                font-size: 12px;
            }
            QLabel#helpLink:hover, QLabel#installLink:hover, QLabel#recommendLabel:hover {
                color: #174ea6;
                text-decoration: underline;
            }
            
            /* 滚动条 */
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #dadce0;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #bdc1c6;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

    def accept(self):
        # 保存选择
        self.selected_image_api = self.combo_img.currentText()
        self.selected_video_api = self.combo_video.currentText()
        settings = QSettings("GhostOS", "App")
        settings.setValue("api/image_provider", self.selected_image_api)
        settings.setValue("api/video_provider", self.selected_video_api)

        
        # 保存语言选择
        sel_idx = self.combo_lang.currentIndex()
        _, sel_code = self._lang_map[sel_idx]
        settings.setValue("i18n/language", sel_code)
        
        # 同步写入 json/language.json
        try:
            import os, json, sys
            app_root = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
            cfg_dir = os.path.join(app_root, 'json')
            os.makedirs(cfg_dir, exist_ok=True)
            cfg_path = os.path.join(cfg_dir, 'language.json')
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump({'code': sel_code}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        
        # 供主窗体读取
        self.selected_language_code = sel_code
        super().accept()

    # 快捷弹窗处理
    def _open_gemini(self):
        dlg = AgeminiConfigDialog(self)
        dlg.exec()

    def _open_midjourney(self):
        dlg = MidjourneyConfigDialog(self)
        dlg.exec()

    def _open_gemini30(self):
        dlg = Gemini30ConfigDialog(self)
        dlg.exec()

    def _open_sora2(self):
        lang = 'en' if self._is_en else 'zh'
        dlg = Sora2ConfigDialog(self, language=lang)
        dlg.exec()

    def _open_wan25(self):
        lang = 'en' if self._is_en else 'zh'
        dlg = Wan25ConfigDialog(self, language=lang)
        dlg.exec()

    def _open_jimeng(self):
        lang = 'en' if self._is_en else 'zh'
        dlg = JimengConfigDialog(self, language=lang)
        dlg.exec()

    def _open_hailuo02(self):
        lang = 'en' if self._is_en else 'zh'
        dlg = Hailuo02ConfigDialog(self, language=lang)
        dlg.exec()

    def _open_talk_api(self):
        """打开对话API配置对话框"""
        dlg = TalkAPIDialog(self)
        dlg.exec()

    def _open_api_help(self):
        """打开 API 说明链接"""
        url = QUrl("https://github.com/guijiaosir/AItools/blob/main/api")
        ok = QDesktopServices.openUrl(url)
        if not ok:
            if getattr(self, "_is_en", True):
                QMessageBox.warning(self, "Open failed", "Failed to open help link, please try again later.")
            else:
                QMessageBox.warning(self, "打开失败", "无法打开帮助链接，请稍后重试。")
