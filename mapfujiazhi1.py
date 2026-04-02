import os
import json
from PySide6.QtWidgets import QPushButton, QDialog, QVBoxLayout, QLabel, QHBoxLayout, QTextEdit, QGraphicsProxyWidget
from PySide6.QtCore import Qt, Signal

def create_fujiazhi_button(parent=None):
    """创建统一风格的生成图片附加值按钮"""
    btn = QPushButton("✔ 附加地点提示词", parent)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; border: none; border-radius: 4px; padding: 5px 10px; font-weight: bold; font-family: 'Microsoft YaHei'; } QPushButton:hover { background-color: #45a049; }")
    return btn

class AdditionalValueDialog(QDialog):
    toggled = Signal(bool)
    def __init__(self, current_text="", parent=None, enabled=True):
        super().__init__(parent)
        self.setWindowTitle("附加地点提示词")
        self.setMinimumSize(560, 320)
        self.setStyleSheet("QDialog { background-color: #0a0a0a; } QLabel { color: #e0e0e0; }")
        self.setWindowFlags(Qt.Window)
        # Removed WA_DeleteOnClose to ensure we can read data after exec() returns
        # self.setAttribute(Qt.WA_DeleteOnClose)
        
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
        
        self.edit = QTextEdit()
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
        
    def get_text(self):
        return self.edit.toPlainText().strip()
        
    def get_enabled(self):
        return self.toggle_btn.isChecked()
        
    def _update_toggle_style(self):
        if self.toggle_btn.isChecked():
            self.toggle_btn.setStyleSheet("QPushButton { background-color: #22c55e; border: none; border-radius: 10px; }")
        else:
            self.toggle_btn.setStyleSheet("QPushButton { background-color: #ef4444; border: none; border-radius: 10px; }")
            
    def _on_toggle_clicked(self):
        self._update_toggle_style()
        self.toggled.emit(self.toggle_btn.isChecked())

class LocationExtraManager:
    def __init__(self, parent_node):
        self.node = parent_node
        self.config_file = "didianfujiazhi.json"
        self.btn = None
        
    def setup_ui(self, parent_widget):
        """Create and configure the button"""
        self.btn = create_fujiazhi_button(parent_widget)
        self.btn.clicked.connect(self.open_dialog)
        
        # Initialize default values on node if not present
        if not hasattr(self.node, "extra_words"):
            self.node.extra_words = ""
        if not hasattr(self.node, "extra_enabled"):
            self.node.extra_enabled = True
            
        # Load initial config
        self.load_config()
        return self.btn

    def load_config(self):
        try:
            cfg_dir = os.path.join(os.getcwd(), "json")
            fp = os.path.join(cfg_dir, self.config_file)
            
            print(f"[LocationExtraManager] Loading config from {fp}")
            if os.path.exists(fp):
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Support legacy flat format and new nested format
                    if "location" in data:
                        d = data["location"]
                    elif "enabled" in data:
                        d = data
                    else:
                        d = {}
                        
                    self.node.extra_enabled = bool(d.get("enabled", True))
                    self.node.extra_words = d.get("text", "")
            else:
                # Default if file doesn't exist
                self.node.extra_enabled = True
                self.node.extra_words = ""
                # Create default file
                self.save_config()
            
            if self.btn:
                self.btn.setToolTip(self.node.extra_words or "未设置生成图片附加值")
                self.update_button_style()
                
        except Exception as e:
            print(f"[LocationExtraManager] Load failed: {e}")

    def update_button_style(self):
        """Update button color based on enabled state"""
        if not self.btn:
            return
            
        if self.node.extra_enabled:
            # Green for enabled
            color = "#4CAF50"
            hover = "#45a049"
            text = "✔ 附加地点提示词"
        else:
            # Red for disabled
            color = "#F44336"
            hover = "#d32f2f"
            text = "X 附加地点提示词"
            
        self.btn.setText(text)
        self.btn.setStyleSheet(f"QPushButton {{ background-color: {color}; color: white; border: none; border-radius: 4px; padding: 5px 10px; font-weight: bold; font-family: 'Microsoft YaHei'; }} QPushButton:hover {{ background-color: {hover}; }}")

    def save_config(self, enabled=None, text=None):
        try:
            cfg_dir = os.path.join(os.getcwd(), "json")
            os.makedirs(cfg_dir, exist_ok=True)
            fp = os.path.join(cfg_dir, self.config_file)
            
            print(f"[LocationExtraManager] Saving config to {fp}")
            
            # Use provided values or current node values
            e = self.node.extra_enabled if enabled is None else bool(enabled)
            t = self.node.extra_words if text is None else (text or "")
            
            # Read existing to preserve other keys
            data = {}
            if os.path.exists(fp):
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except:
                    pass
            
            # Update location key
            data["location"] = {
                "enabled": e,
                "text": t
            }
            
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                
            # Update node values just in case
            self.node.extra_enabled = e
            self.node.extra_words = t
            
            # Update UI
            self.update_button_style()
            
        except Exception as e:
            print(f"[LocationExtraManager] Save failed: {e}")

    def open_dialog(self):
        # 传入 None 作为父窗口，避免在 QGraphicsProxyWidget 中出现输入法/焦点问题
        # Use the local AdditionalValueDialog class
        dlg = AdditionalValueDialog(self.node.extra_words, None, getattr(self.node, "extra_enabled", True))
        
        if dlg.exec():
            # Dialog returned Accepted (User clicked OK)
            new_text = dlg.get_text()
            new_enabled = dlg.get_enabled()
            
            self.node.extra_words = new_text
            self.node.extra_enabled = new_enabled
            
            if self.btn:
                self.btn.setToolTip(new_text or "未设置生成图片附加值")
                
            print(f"[LocationNode] 生成图片附加值更新为: {new_text}, Enabled: {new_enabled}")
            self.save_config(enabled=new_enabled, text=new_text)
