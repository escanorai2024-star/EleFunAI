from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout, QPushButton
from PySide6.QtCore import QSettings
import os, sys, json

class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Midjourney 参数配置")
        self.setFixedSize(460, 220)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)
        lay.addWidget(QLabel("API Key"))
        self.api_key = QLineEdit()
        lay.addWidget(self.api_key)
        lay.addWidget(QLabel("Base URL (例如 https://api.vectorengine.ai/v1)"))
        self.base_url = QLineEdit()
        lay.addWidget(self.base_url)
        hint = QLabel("提示词请在创建页的提交旁输入，不在此面板保存")
        lay.addWidget(hint)
        row = QHBoxLayout()
        row.addStretch(1)
        b1 = QPushButton("取消")
        b2 = QPushButton("保存")
        b1.clicked.connect(self.reject)
        b2.clicked.connect(self.accept)
        row.addWidget(b1)
        row.addWidget(b2)
        lay.addLayout(row)
        s = QSettings("GhostOS", "App")
        self.api_key.setText(s.value("providers/midjourney/api_key", ""))
        self.base_url.setText(s.value("providers/midjourney/base_url", ""))

    def accept(self):
        s = QSettings("GhostOS", "App")
        s.setValue("providers/midjourney/api_key", self.api_key.text())
        s.setValue("providers/midjourney/base_url", self.base_url.text())
        try:
            root = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
            d = os.path.join(root, 'json')
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, 'mj.json'), 'w', encoding='utf-8') as f:
                json.dump({'api_key': self.api_key.text(), 'base_url': self.base_url.text()}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        super().accept()
