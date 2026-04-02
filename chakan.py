from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

class ImageViewerDialog(QDialog):
    """简易图片查看器"""
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("查看图片")
        self.resize(800, 600)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background-color: #1e1e1e;")
        
        self.pixmap = QPixmap(image_path)
        if not self.pixmap.isNull():
            self.update_image()
            
        layout.addWidget(self.label)
        
    def update_image(self):
        if not self.pixmap.isNull():
            scaled = self.pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.label.setPixmap(scaled)

    def resizeEvent(self, event):
        self.update_image()
        super().resizeEvent(event)
