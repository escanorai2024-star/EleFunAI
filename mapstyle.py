import os, json, time
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, 
                               QToolButton, QFrame, QListWidget, QTextEdit, 
                               QSplitter, QWidget, QMessageBox)
from PySide6.QtCore import Qt, QFileSystemWatcher, QUrl
from PySide6.QtGui import QDesktopServices

DEFAULT_PROMPTS = {
    "动画风格": "请生成偏向动漫/动画气质、画面夸张、色彩饱和、构图简洁的中文提示词。",
    "真实风格": "请生成贴近真实摄影与电影感的中文提示词，强调光影与真实细节。",
    "3D风格": "请生成具有3D渲染质感、立体感强、光影丰富的中文提示词，类似CGI电影或游戏画面。",
    "2D风格": "请生成扁平化、二维手绘或插画风格的中文提示词，色彩鲜明，线条清晰。",
    "迪士尼风格": "请生成具有迪士尼动画电影风格的中文提示词，色彩梦幻，角色生动，充满童话氛围。"
}

class MapStyleManager:
    def __init__(self):
        self.dir = os.path.join(os.path.dirname(__file__), "json")
        self.path = os.path.join(self.dir, "mapstyle.json")
        self.txt_dir = os.path.join(os.path.dirname(__file__), "TXT")
        self.txt_path = os.path.join(self.txt_dir, "地点风格提示词.txt")
    
    def load(self):
        # Define all default styles
        default_styles = ["动画风格", "真实风格", "3D风格", "2D风格", "迪士尼风格"]
        
        styles = default_styles.copy()
        selected = "动画风格"
        style_prompts = DEFAULT_PROMPTS.copy()
        
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                loaded_styles = data.get("styles", [])
                if loaded_styles:
                    styles = loaded_styles
                    # Ensure default styles are present
                    for ds in default_styles:
                        if ds not in styles:
                            styles.append(ds)
                            
                selected = data.get("selected", selected)
                loaded_prompts = data.get("style_prompts", {})
                
                # Merge loaded prompts, fill missing ones
                for s in styles:
                    if s in loaded_prompts:
                        style_prompts[s] = loaded_prompts[s]
                    elif s not in style_prompts:
                        # Fallback to DEFAULT_PROMPTS if available, else generic
                        if s in DEFAULT_PROMPTS:
                             style_prompts[s] = DEFAULT_PROMPTS[s]
                        else:
                             style_prompts[s] = f"请根据以下风格提示词生成：{s}"
                        
        except Exception:
            pass
        return styles, selected, style_prompts

    def save_state(self, styles, selected, style_prompts):
        try:
            os.makedirs(self.dir, exist_ok=True)
            data = {}
            if os.path.exists(self.path):
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {}
            
            data["styles"] = styles
            data["selected"] = selected
            data["style_prompts"] = style_prompts
            
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def save_result(self, style_name, style_text, prompts):
        try:
            os.makedirs(self.dir, exist_ok=True)
            base = {}
            if os.path.exists(self.path):
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        base = json.load(f)
                except Exception:
                    base = {}
            base["selected"] = style_name
            base["last_style_text"] = style_text
            base["last_prompts"] = prompts
            base["timestamp"] = int(time.time())
            # Update dialog_info part
            base["dialog_info"] = {
                "styles": base.get("styles", []),
                "selected": base.get("selected", style_name)
            }
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(base, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def save_txt(self, styles, style_prompts):
        try:
            os.makedirs(self.txt_dir, exist_ok=True)
            lines = []
            for s in styles:
                t = style_prompts.get(s, "")
                lines.append(s + ":")
                lines.append(t)
                lines.append("")
            content = "\n".join(lines).strip() + "\n"
            with open(self.txt_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass
    
    def ensure_txt_exists(self, styles, style_prompts):
        try:
            if not os.path.exists(self.txt_path):
                self.save_txt(styles, style_prompts)
        except Exception:
            pass
    
    def load_txt(self):
        styles = []
        data = {}
        try:
            if not os.path.exists(self.txt_path):
                return styles, data
            with open(self.txt_path, "r", encoding="utf-8") as f:
                lines = [ln.rstrip("\n") for ln in f.readlines()]
            current = None
            buf = []
            for ln in lines:
                s = ln.strip()
                if s.endswith(":") and len(s) > 1:
                    if current is not None:
                        data[current] = "\n".join(buf).strip()
                        styles.append(current)
                        buf = []
                    current = s[:-1].strip()
                else:
                    buf.append(ln)
            if current is not None:
                data[current] = "\n".join(buf).strip()
                styles.append(current)
        except Exception:
            pass
        return styles, data

class StylePromptEditorDialog(QDialog):
    def __init__(self, styles, style_prompts, parent=None):
        super().__init__(parent)
        self.setWindowTitle("风格提示词设置")
        self.setFixedSize(600, 400)
        self.styles = styles
        self.style_prompts = style_prompts
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        splitter = QSplitter(Qt.Horizontal)
        
        # Left: Style List
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("选择风格:"))
        self.list_widget = QListWidget()
        self.list_widget.addItems(self.styles)
        self.list_widget.setStyleSheet("font-size: 16px;")
        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        left_layout.addWidget(self.list_widget)
        
        # Right: Prompt Editor
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("编辑提示词 (发送给API的内容):"))
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("在此输入该风格对应的提示词要求...")
        self.text_edit.setStyleSheet("font-size: 16px; line-height: 1.5;")
        self.text_edit.setReadOnly(False)
        self.text_edit.setFocusPolicy(Qt.StrongFocus)
        self.text_edit.setFocus()
        self.text_edit.textChanged.connect(self._on_text_changed)
        right_layout.addWidget(self.text_edit)
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([180, 420])
        
        layout.addWidget(splitter)
        
        # Bottom: Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_ok = QPushButton("确定")
        self.btn_ok.setMinimumWidth(100)
        self.btn_ok.setFixedHeight(35)
        self.btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_ok)
        layout.addLayout(btn_layout)
        
        # Select first item
        if self.styles:
            self.list_widget.setCurrentRow(0)
            
    def _on_row_changed(self, row):
        if row < 0: return
        style_name = self.styles[row]
        prompt = self.style_prompts.get(style_name, "")
        self.text_edit.blockSignals(True)
        self.text_edit.setText(prompt)
        self.text_edit.blockSignals(False)
        
    def _on_text_changed(self):
        row = self.list_widget.currentRow()
        if row < 0: return
        style_name = self.styles[row]
        self.style_prompts[style_name] = self.text_edit.toPlainText()
        
    def get_data(self):
        return self.style_prompts

class MapStyleDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("风格选择")
        self.setWindowFlags(Qt.Window)
        self.setMinimumSize(520, 340)
        self.mgr = MapStyleManager()
        self.styles, self.selected, self.style_prompts = self.mgr.load()
        try:
            self.mgr.ensure_txt_exists(self.styles, self.style_prompts)
        except Exception:
            pass
        try:
            txt_styles, txt_prompts = self.mgr.load_txt()
            if txt_styles:
                self.styles = txt_styles
                for k, v in txt_prompts.items():
                    self.style_prompts[k] = v
                if self.selected not in self.styles:
                    self.selected = self.styles[0]
        except Exception:
            pass
        self.watcher = QFileSystemWatcher()
        try:
            self.watcher.addPath(self.mgr.txt_path)
            self.watcher.fileChanged.connect(self._on_txt_changed)
        except Exception:
            pass
        self.buttons = []
        self._setup_ui()
        self._apply_styles()
    def _setup_ui(self):
        root = QVBoxLayout(self)
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        
        top_strip = QFrame()
        top_strip.setObjectName("topStrip")
        top_layout = QVBoxLayout(top_strip)
        top_layout.setContentsMargins(8, 8, 8, 8)
        top_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        
        # Header layout for "Settings" button
        header_layout = QHBoxLayout()
        header_layout.addStretch()
        self.btn_edit = QToolButton()
        self.btn_edit.setText("编辑")
        self.btn_edit.setCursor(Qt.PointingHandCursor)
        self.btn_edit.clicked.connect(self._on_edit)
        header_layout.addWidget(self.btn_edit)
        top_layout.addLayout(header_layout)

        self.styles_box = QVBoxLayout()
        self.styles_box.setContentsMargins(0, 0, 0, 0)
        self.styles_box.setSpacing(8)
        self._rebuild_style_buttons()
        top_layout.addLayout(self.styles_box)
        card_layout.addWidget(top_strip)
        actions = QHBoxLayout()
        self.btn_generate = QPushButton("生成")
        actions.addStretch()
        actions.addWidget(self.btn_generate)
        card_layout.addLayout(actions)
        root.addWidget(card)
        self.btn_generate.clicked.connect(self._on_generate)
    def _rebuild_style_buttons(self):
        while self.styles_box.count():
            item = self.styles_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # Recursively delete layout items
                sub_layout = item.layout()
                while sub_layout.count():
                    sub_item = sub_layout.takeAt(0)
                    if sub_item.widget():
                        sub_item.widget().deleteLater()
                sub_layout.deleteLater()
        
        self.buttons = []
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.setAlignment(Qt.AlignLeft)
        for name in self.styles:
            btn = QToolButton()
            btn.setText(name)
            btn.setCheckable(True)
            btn.setChecked(name == self.selected)
            btn.clicked.connect(lambda _, n=name: self._on_select(n))
            self._style_chip(btn, btn.isChecked())
            row.addWidget(btn)
            self.buttons.append(btn)
            if len(self.buttons) % 3 == 0:
                self.styles_box.addLayout(row)
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(8)
                row.setAlignment(Qt.AlignLeft)
        if row.count():
            self.styles_box.addLayout(row)
    
    def _on_select(self, name):
        self.selected = name
        for b in self.buttons:
            b.setChecked(b.text() == name)
            self._style_chip(b, b.isChecked())

    def _on_edit(self):
        try:
            self.mgr.ensure_txt_exists(self.styles, self.style_prompts)
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.mgr.txt_path))
        except Exception:
            pass
            self.mgr.save_txt(self.styles, self.style_prompts)
            
    def _on_generate(self):
        self.mgr.save_state(self.styles, self.selected, self.style_prompts)
        try:
            self.mgr.save_txt(self.styles, self.style_prompts)
        except Exception:
            pass
        try:
            self.btn_generate.setText("⏳")
            self.btn_generate.setEnabled(False)
        except Exception:
            pass
        self.accept()
    
    def _on_txt_changed(self, path):
        try:
            txt_styles, updated = self.mgr.load_txt()
            if updated:
                for k, v in updated.items():
                    self.style_prompts[k] = v
            if txt_styles:
                self.styles = txt_styles
                if self.selected not in self.styles:
                    self.selected = self.styles[0]
                self._rebuild_style_buttons()
            self.mgr.save_state(self.styles, self.selected, self.style_prompts)
        except Exception:
            pass
    def _style_chip(self, btn, active):
        if active:
            btn.setStyleSheet("QToolButton {background-color: rgba(34,197,94,0.35); color:#0a0a0a; border:1px solid #16a34a; border-radius:8px; padding:8px 14px; font-weight:600;} QToolButton:hover {background-color: rgba(34,197,94,0.45);}")
        else:
            btn.setStyleSheet("QToolButton {background-color: #d1d5db; color:#111; border:none; border-radius:8px; padding:8px 14px;} QToolButton:hover {background-color:#cbd5e1;}")
    def _apply_styles(self):
        self.setStyleSheet("""
        QDialog { background-color:#f7f8fa; }
        #card { background-color:#eef2f7; border-radius:8px; }
        #card > * { margin-left:6px; margin-right:6px; }
        #topStrip { background-color:#ffffff; border-radius:8px; }
        QLabel { color:#111827; font-weight:600; }
        QToolButton { background-color:#e5e7eb; color:#111827; border:none; border-radius:8px; padding:6px 10px; font-weight:700; min-width:32px; }
        QToolButton:hover { background-color:#d1d5db; }
        QPushButton { background-color:#e5e7eb; color:#111827; border:none; border-radius:8px; padding:8px 16px; font-weight:600; }
        QPushButton:hover { background-color:#d1d5db; }
        QPushButton:last-child { background-color:#3b82f6; color:#ffffff; }
        QPushButton:last-child:hover { background-color:#2563eb; }
        """)
    def get_style(self):
        name = self.selected
        # Use stored prompt if available, otherwise fallback (should not happen with new logic)
        txt = self.style_prompts.get(name, f"请根据以下风格提示词生成：{name}")
        return name, txt
