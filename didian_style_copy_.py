from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QFileDialog, QHBoxLayout
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
import os

class DidianStyleDialog(QDialog):
    def __init__(self, parent=None, current_path=None):
        super().__init__(parent)
        self.setWindowTitle("风格参考")
        self.resize(420, 300)
        self.image_path = current_path if current_path and os.path.exists(str(current_path)) else None
        layout = QVBoxLayout(self)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedHeight(180)
        self.preview.setStyleSheet("QLabel { border: 1px dashed #cccccc; border-radius: 6px; background: #f7f7f7; }")
        layout.addWidget(self.preview)
        btns = QHBoxLayout()
        self.btn_upload = QPushButton("上传参考图")
        self.btn_clear = QPushButton("清除")
        self.btn_ok = QPushButton("确定")
        self.btn_cancel = QPushButton("取消")
        self.btn_upload.clicked.connect(self.upload_image)
        self.btn_clear.clicked.connect(self.clear_image)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        btns.addWidget(self.btn_upload)
        btns.addWidget(self.btn_clear)
        btns.addStretch()
        btns.addWidget(self.btn_ok)
        btns.addWidget(self.btn_cancel)
        layout.addLayout(btns)
        self.update_preview()

    def upload_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择风格参考图", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.image_path = path
            self.update_preview()

    def clear_image(self):
        self.image_path = None
        self.update_preview()

    def update_preview(self):
        if self.image_path and os.path.exists(self.image_path):
            pix = QPixmap(self.image_path)
            if not pix.isNull():
                self.preview.setPixmap(pix.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                return
        self.preview.setPixmap(QPixmap())
        self.preview.setText("未设置参考图")

    def get_image_path(self):
        return self.image_path

