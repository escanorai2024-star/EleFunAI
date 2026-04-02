from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout, QPushButton
from PySide6.QtCore import Qt, QSettings


class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gemini 配置")
        self.setFixedSize(420, 260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(QLabel("API Key"))
        self.api_key = QLineEdit()
        layout.addWidget(self.api_key)

        layout.addWidget(QLabel("Base URL"))
        self.base_url = QLineEdit()
        layout.addWidget(self.base_url)

        layout.addWidget(QLabel("Model"))
        self.model = QLineEdit()
        layout.addWidget(self.model)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_ok = QPushButton("保存")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self.accept)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

        # 读取配置
        s = QSettings("GhostOS", "App")
        self.api_key.setText(s.value("providers/gemini/api_key", ""))
        self.base_url.setText(s.value("providers/gemini/base_url", ""))
        self.model.setText(s.value("providers/gemini/model", ""))

        self.setStyleSheet(
            """
            QDialog { background: #1a1b1d; color: #dfe3ea; }
            QLineEdit { background: #0c0d0e; color: #ffffff; border: 1px solid #2a2d31; border-radius: 6px; padding: 6px; }
            QPushButton { background: #0c0d0e; color: #cfd3da; border: 1px solid #2a2d31; border-radius: 6px; padding: 6px 12px; }
            QPushButton:hover { background: #181c22; }
            """
        )

    def accept(self):
        s = QSettings("GhostOS", "App")
        s.setValue("providers/gemini/api_key", self.api_key.text())
        s.setValue("providers/gemini/base_url", self.base_url.text())
        s.setValue("providers/gemini/model", self.model.text())
        super().accept()