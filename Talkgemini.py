from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout, QPushButton
from PySide6.QtCore import QSettings

class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gemini 对话配置")
        self.setFixedSize(460, 240)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)
        lay.addWidget(QLabel("API Key"))
        self.api_key = QLineEdit(); lay.addWidget(self.api_key)
        lay.addWidget(QLabel("Base URL (例如 https://generativelanguage.googleapis.com)"))
        self.base_url = QLineEdit(); lay.addWidget(self.base_url)
        row = QHBoxLayout(); row.addStretch(1)
        b1 = QPushButton("取消"); b2 = QPushButton("保存")
        b1.clicked.connect(self.reject); b2.clicked.connect(self.accept)
        row.addWidget(b1); row.addWidget(b2)
        lay.addLayout(row)
        s = QSettings("GhostOS", "App")
        self.api_key.setText(s.value("providers/talk/gemini/api_key", ""))
        self.base_url.setText(s.value("providers/talk/gemini/base_url", ""))

    def accept(self):
        s = QSettings("GhostOS", "App")
        s.setValue("providers/talk/gemini/api_key", self.api_key.text())
        s.setValue("providers/talk/gemini/base_url", self.base_url.text())
        try:
            import os, sys, json
            root = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
            d = os.path.join(root, 'json'); os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, 'talk_gemini.json'), 'w', encoding='utf-8') as f:
                json.dump({
                    'api_key': self.api_key.text(),
                    'base_url': self.base_url.text()
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        super().accept()