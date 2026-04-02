import os
import json
from PySide6.QtWidgets import QPushButton, QDialog, QVBoxLayout, QLabel, QHBoxLayout, QTextEdit, QGraphicsProxyWidget, QComboBox, QInputDialog, QMessageBox
from PySide6.QtCore import Qt, Signal

def create_fujiazhi_button(parent=None):
    """创建统一风格的生成图片附加值按钮"""
    btn = QPushButton("生成图片附加值", parent)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet("QPushButton { background-color: #FF9800; color: white; border: none; border-radius: 4px; padding: 5px 10px; font-weight: bold; font-family: 'Microsoft YaHei'; } QPushButton:hover { background-color: #FB8C00; }")
    return btn

class AdditionalValueDialog(QDialog):
    toggled = Signal(bool)
    def __init__(self, current_text="", parent=None, enabled=True, templates=None):
        super().__init__(parent)
        self.setWindowTitle("生成图片附加值")
        self.setMinimumSize(560, 360)
        self.setStyleSheet("QDialog { background-color: #0a0a0a; } QLabel { color: #e0e0e0; }")
        self.setWindowFlags(Qt.Window)
        self.templates = []
        if templates and isinstance(templates, list):
            for t in templates:
                if isinstance(t, dict):
                    name = str(t.get("name", "")).strip()
                    text = str(t.get("text", ""))
                    if name:
                        self.templates.append({"name": name, "text": text})
        if not self.templates:
            self.templates = [{"name": "默认", "text": current_text or ""}]
        self.current_index = 0
        for i, t in enumerate(self.templates):
            if t.get("text", "") == (current_text or ""):
                self.current_index = i
                break
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        title = QLabel("生成图片时附加的单词")
        self.toggle_btn = QPushButton("")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(enabled)
        self.toggle_btn.setFixedSize(20, 20)
        self.toggle_btn.setToolTip("启用/关闭")
        self._update_toggle_style()
        self.toggle_btn.clicked.connect(self._on_toggle_clicked)
        top.addWidget(title)
        top.addStretch()
        top.addWidget(self.toggle_btn)
        layout.addLayout(top)
        template_bar = QHBoxLayout()
        self.template_combo = QComboBox()
        for t in self.templates:
            self.template_combo.addItem(t["name"])
        self.template_combo.setCurrentIndex(self.current_index)
        self.template_combo.currentIndexChanged.connect(self._on_template_changed)
        self.btn_add_template = QPushButton("新增模板")
        self.btn_delete_template = QPushButton("删除模板")
        self.btn_add_template.clicked.connect(self._on_add_template)
        self.btn_delete_template.clicked.connect(self._on_delete_template)
        template_bar.addWidget(QLabel("模板:"))
        template_bar.addWidget(self.template_combo, 1)
        template_bar.addWidget(self.btn_add_template)
        template_bar.addWidget(self.btn_delete_template)
        layout.addLayout(template_bar)
        self.edit = QTextEdit()
        initial_text = self.templates[self.current_index].get("text", "")
        if initial_text:
            self.edit.setText(initial_text)
        else:
            self.edit.setText(current_text or "")
        self.edit.setPlaceholderText("cinematic, volumetric light, 8k")
        self.edit.setStyleSheet("QTextEdit { background-color: #1a1a1a; color: #e0e0e0; border: 2px solid #2a2a2a; border-radius: 8px; padding: 12px; font-size: 14px; } QTextEdit:focus { border: 2px solid #00bfff; }")
        layout.addWidget(self.edit, 1)
        btns = QHBoxLayout()
        ok = QPushButton("确定")
        cancel = QPushButton("取消")
        ok.setStyleSheet("QPushButton { background-color: #00ff88; color: #000; border: none; border-radius: 6px; padding: 6px 16px; } QPushButton:hover { background-color: #00cc6f; }")
        cancel.setStyleSheet("QPushButton { background-color: #2a2a2a; color: #e0e0e0; border: 1px solid #3a3a3a; border-radius: 6px; padding: 6px 16px; }")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)
        
    def _sync_current_text(self):
        if self.templates and 0 <= self.current_index < len(self.templates):
            self.templates[self.current_index]["text"] = self.edit.toPlainText().strip()

    def get_text(self):
        self._sync_current_text()
        return self.edit.toPlainText().strip()
        
    def get_enabled(self):
        return self.toggle_btn.isChecked()
        
    def get_templates(self):
        self._sync_current_text()
        return list(self.templates)
        
    def _update_toggle_style(self):
        if self.toggle_btn.isChecked():
            self.toggle_btn.setStyleSheet("QPushButton { background-color: #22c55e; border: none; border-radius: 10px; }")
        else:
            self.toggle_btn.setStyleSheet("QPushButton { background-color: #ef4444; border: none; border-radius: 10px; }")
            
    def _on_toggle_clicked(self):
        self._update_toggle_style()
        self.toggled.emit(self.toggle_btn.isChecked())

    def _on_template_changed(self, index):
        if index < 0 or index >= len(self.templates):
            return
        self._sync_current_text()
        self.current_index = index
        text = self.templates[self.current_index].get("text", "")
        self.edit.setPlainText(text)

    def _on_add_template(self):
        name, ok = QInputDialog.getText(self, "新增模板", "模板名称：")
        if not ok:
            return
        name = str(name).strip()
        if not name:
            return
        self._sync_current_text()
        self.templates.append({"name": name, "text": ""})
        self.template_combo.addItem(name)
        new_index = self.template_combo.count() - 1
        self.template_combo.setCurrentIndex(new_index)

    def _on_delete_template(self):
        if len(self.templates) <= 1:
            QMessageBox.information(self, "提示", "至少需要保留一个模板。")
            return
        index = self.template_combo.currentIndex()
        if index < 0 or index >= len(self.templates):
            return
        del self.templates[index]
        self.template_combo.removeItem(index)
        if index >= len(self.templates):
            index = len(self.templates) - 1
        self.current_index = index
        self.template_combo.setCurrentIndex(self.current_index)
        text = self.templates[self.current_index].get("text", "")
        self.edit.setPlainText(text)

class CharacterExtraManager:
    def __init__(self, parent_node):
        self.node = parent_node
        self.config_file = "didianfujiazhi.json"
        self.btn = None
        self.templates = []
        
    def setup_ui(self, parent_widget):
        """Create and configure the button"""
        self.btn = create_fujiazhi_button(parent_widget)
        self.btn.clicked.connect(self.open_dialog)
        
        # Initialize default values on node if not present
        if not hasattr(self.node, "extra_words"):
            self.node.extra_words = ""
        if not hasattr(self.node, "extra_enabled"):
            self.node.extra_enabled = False
            
        # Load initial config
        self.load_config()
        return self.btn

    def load_config(self):
        try:
            cfg_dir = os.path.join(os.getcwd(), "json")
            fp = os.path.join(cfg_dir, self.config_file)
            
            print(f"[CharacterExtraManager] Loading config from {fp}")
            if os.path.exists(fp):
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    d = data.get("character", {})
                    self.node.extra_enabled = bool(d.get("enabled", False))
                    self.node.extra_words = d.get("text", "")
                    tpl_list = data.get("character_templates", [])
                    if isinstance(tpl_list, list):
                        self.templates = []
                        for t in tpl_list:
                            if isinstance(t, dict):
                                name = str(t.get("name", "")).strip()
                                text = str(t.get("text", ""))
                                if name:
                                    self.templates.append({"name": name, "text": text})
            else:
                self.node.extra_enabled = False
                self.node.extra_words = ""
                self.save_config()
            if not self.templates:
                self.templates = [{"name": "默认", "text": self.node.extra_words or ""}]
            
            if self.btn:
                self.btn.setToolTip(self.node.extra_words or "未设置生成图片附加值")
                self.update_button_style()
                
        except Exception as e:
            print(f"[CharacterExtraManager] Load failed: {e}")

    def update_button_style(self):
        """Update button color and text based on enabled state"""
        if not self.btn:
            return
            
        if self.node.extra_enabled:
            # Green for enabled
            color = "#4CAF50"
            hover = "#45a049"
            text = "✔ 附加图片提示词"
        else:
            # Red for disabled
            color = "#F44336"
            hover = "#d32f2f"
            text = "X 附加图片提示词"
            
        self.btn.setText(text)
        self.btn.setStyleSheet(f"QPushButton {{ background-color: {color}; color: white; border: none; border-radius: 4px; padding: 5px 10px; font-weight: bold; font-family: 'Microsoft YaHei'; }} QPushButton:hover {{ background-color: {hover}; }}")

    def save_config(self, enabled=None, text=None):
        try:
            cfg_dir = os.path.join(os.getcwd(), "json")
            os.makedirs(cfg_dir, exist_ok=True)
            fp = os.path.join(cfg_dir, self.config_file)
            
            print(f"[CharacterExtraManager] Saving config to {fp}")
            
            e = self.node.extra_enabled if enabled is None else bool(enabled)
            t = self.node.extra_words if text is None else (text or "")
            
            data = {}
            if os.path.exists(fp):
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except:
                    pass
            
            data["character"] = {
                "enabled": e,
                "text": t
            }
            tpl_list = []
            for tpl in self.templates:
                name = str(tpl.get("name", "")).strip()
                if not name:
                    continue
                tpl_list.append({
                    "name": name,
                    "text": str(tpl.get("text", "")),
                })
            data["character_templates"] = tpl_list
            
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            
            self.node.extra_enabled = e
            self.node.extra_words = t
            
            # Update UI
            self.update_button_style()
            
        except Exception as e:
            print(f"[CharacterExtraManager] Save failed: {e}")

    def open_dialog(self):
        dlg = AdditionalValueDialog(self.node.extra_words, None, getattr(self.node, "extra_enabled", False), templates=self.templates)
        
        if dlg.exec():
            new_text = dlg.get_text()
            new_enabled = dlg.get_enabled()
            new_templates = dlg.get_templates()
            
            self.node.extra_words = new_text
            self.node.extra_enabled = new_enabled
            self.templates = new_templates
            
            if self.btn:
                self.btn.setToolTip(new_text or "未设置生成图片附加值")
                
            print(f"[ScriptCharacterNode] 生成图片附加值更新为: {new_text}, Enabled: {new_enabled}")
            self.save_config(enabled=new_enabled, text=new_text)
