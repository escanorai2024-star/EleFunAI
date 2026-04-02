from PySide6.QtWidgets import QPushButton, QFileDialog, QWidget, QLabel, QHBoxLayout
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QPainter, QPainterPath


class ImageThumbnail(QWidget):
    delete_clicked = Signal(str)

    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.setup_ui()

    def setup_ui(self):
        self.setFixedSize(90, 70)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        container = QWidget(self)
        container.setFixedSize(90, 70)
        container.setStyleSheet(
            "background-color: #f1f3f4; border-radius: 6px; border: 1px solid #dadce0;"
        )

        self.image_label = QLabel(container)
        self.image_label.setGeometry(4, 4, 82, 62)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        pixmap = QPixmap(self.image_path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                82,
                62,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.image_label.setPixmap(self.create_rounded_pixmap(scaled, 6))

        self.delete_btn = QPushButton("×", container)
        self.delete_btn.setGeometry(66, 4, 20, 20)
        self.delete_btn.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(0, 0, 0, 0.7);
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 12px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: rgba(220, 38, 38, 0.9);
            }
            """
        )
        self.delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self.image_path))

        layout.addWidget(container)

    def create_rounded_pixmap(self, pixmap, radius):
        rounded = QPixmap(pixmap.size())
        rounded.fill(Qt.GlobalColor.transparent)

        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, pixmap.width(), pixmap.height(), radius, radius)

        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()

        return rounded


class ChatImageUploadManager:
    def __init__(self, workbench):
        self.workbench = workbench
        self.images = []
        self.button = None
        self.preview_container = None
        self.preview_layout = None

    def create_button(self):
        btn = QPushButton("🖼")
        btn.setFixedSize(26, 26)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("上传图片")
        btn.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                color: #5f6368;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #f1f3f4;
                color: #1a73e8;
                border: 1px solid #d2e3fc;
            }
            QPushButton:pressed {
                background-color: #e8f0fe;
            }
            """
        )
        btn.clicked.connect(self.on_clicked)
        self.button = btn
        return btn

    def bind_preview_area(self, container, layout):
        self.preview_container = container
        self.preview_layout = layout

    def on_clicked(self):
        files, _ = QFileDialog.getOpenFileNames(
            self.workbench,
            "选择图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp *.gif)",
        )
        if not files:
            return
        for path in files:
            if path not in self.images:
                self.images.append(path)
        self.update_button_state()
        self.update_preview()

    def get_images(self):
        return list(self.images)

    def clear_images(self):
        self.images.clear()
        self.update_button_state()
        self.update_preview()

    def remove_image(self, image_path):
        if image_path in self.images:
            self.images.remove(image_path)
            self.update_button_state()
            self.update_preview()

    def update_button_state(self):
        if not self.button:
            return
        if self.images:
            count = len(self.images)
            self.button.setToolTip(f"已选择 {count} 张图片")
            self.button.setStyleSheet(
                """
                QPushButton {
                    background-color: #e8f0fe;
                    color: #1a73e8;
                    border: 1px solid #d2e3fc;
                    border-radius: 4px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #d2e3fc;
                    color: #174ea6;
                    border: 1px solid #aecbfa;
                }
                QPushButton:pressed {
                    background-color: #c4d2ff;
                }
                """
            )
        else:
            self.button.setText("🖼")
            self.button.setToolTip("上传图片")
            self.button.setStyleSheet(
                """
                QPushButton {
                    background-color: transparent;
                    color: #5f6368;
                    border: 1px solid #e0e0e0;
                    border-radius: 4px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #f1f3f4;
                    color: #1a73e8;
                    border: 1px solid #d2e3fc;
                }
                QPushButton:pressed {
                    background-color: #e8f0fe;
                }
                """
            )

    def update_preview(self):
        if not self.preview_layout:
            return
        while self.preview_layout.count():
            item = self.preview_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if not self.images:
            if self.preview_container:
                self.preview_container.setVisible(False)
            return
        for path in self.images:
            thumb = ImageThumbnail(path, self.preview_container)
            thumb.delete_clicked.connect(self.remove_image)
            self.preview_layout.addWidget(thumb)
        if self.preview_container:
            self.preview_container.setVisible(True)
