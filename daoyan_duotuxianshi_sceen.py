import os
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QScrollArea, QWidget, QHBoxLayout
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap


class ClickableLabel(QLabel):
    clicked = Signal(int)

    def __init__(self, path_index, parent=None):
        super().__init__(parent)
        self.path_index = path_index
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if hasattr(event, "button") and event.button() == Qt.LeftButton:
            self.clicked.emit(self.path_index)
        super().mousePressEvent(event)


class MultiStoryboardDialog(QDialog):
    def __init__(self, image_paths, selected_index=0, parent=None, on_select=None):
        super().__init__(parent)
        self.image_paths = [p for p in image_paths if p and isinstance(p, str) and os.path.exists(p)]
        self.selected_index = selected_index
        self.on_select = on_select
        self.labels = []
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("多图预览")
        self.resize(1920, 1080)
        self.setWindowFlag(Qt.Window)
        self.setStyleSheet("background-color: #2b2b2b;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.main_scroll = QScrollArea()
        self.main_scroll.setWidgetResizable(True)
        self.main_scroll.setAlignment(Qt.AlignCenter)
        self.main_scroll.setStyleSheet("background-color: #1e1e1e; border: none;")

        self.main_image_label = QLabel()
        self.main_image_label.setAlignment(Qt.AlignCenter)
        self.main_image_label.setStyleSheet("background-color: #1e1e1e;")
        self.main_scroll.setWidget(self.main_image_label)

        layout.addWidget(self.main_scroll, 1)

        bottom_container = QWidget()
        bottom_container.setFixedHeight(140)
        bottom_container.setStyleSheet("background-color: #333333; border-top: 1px solid #444;")
        bottom_layout = QHBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(10, 10, 10, 10)
        bottom_layout.setSpacing(10)

        self.thumb_scroll = QScrollArea()
        self.thumb_scroll.setWidgetResizable(True)
        self.thumb_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.thumb_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.thumb_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QWidget { background: transparent; }
            QScrollBar:horizontal { height: 8px; background: #222; }
            QScrollBar::handle:horizontal { background: #555; border-radius: 4px; }
        """)

        self.thumb_widget = QWidget()
        self.thumb_layout = QHBoxLayout(self.thumb_widget)
        self.thumb_layout.setContentsMargins(0, 0, 0, 0)
        self.thumb_layout.setSpacing(15)
        self.thumb_layout.setAlignment(Qt.AlignLeft)

        self.thumb_scroll.setWidget(self.thumb_widget)
        bottom_layout.addWidget(self.thumb_scroll)

        layout.addWidget(bottom_container)

        for i, path in enumerate(self.image_paths):
            label = ClickableLabel(i, self)
            label.setFixedSize(192, 108)
            label.setStyleSheet("border: 2px solid transparent; background-color: #000;")

            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(label.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                x = (scaled.width() - label.width()) // 2
                y = (scaled.height() - label.height()) // 2
                cropped = scaled.copy(x, y, label.width(), label.height())
                label.setPixmap(cropped)

            label.clicked.connect(self.on_label_clicked)
            self.labels.append(label)
            self.thumb_layout.addWidget(label)

        if self.selected_index < 0 or self.selected_index >= len(self.image_paths):
            self.selected_index = 0

        QTimer.singleShot(50, self.update_view)

    def update_view(self):
        if 0 <= self.selected_index < len(self.image_paths):
            path = self.image_paths[self.selected_index]
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                view_size = self.main_scroll.size()
                if view_size.width() > 0 and view_size.height() > 0:
                    scaled = pixmap.scaled(view_size.width() - 20, view_size.height() - 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.main_image_label.setPixmap(scaled)
            else:
                self.main_image_label.setText("无法加载图片")
                self.main_image_label.setStyleSheet("color: white; font-size: 20px;")

        for i, label in enumerate(self.labels):
            if i == self.selected_index:
                label.setStyleSheet("border: 3px solid #FFFFFF; background-color: #000;")
                self.thumb_scroll.ensureWidgetVisible(label)
            else:
                label.setStyleSheet("border: 2px solid transparent; background-color: #000;")

    def on_label_clicked(self, index):
        self.selected_index = index
        self.update_view()
        if self.on_select:
            self.on_select(index)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left:
            self.selected_index = max(0, self.selected_index - 1)
            self.update_view()
            if self.on_select:
                self.on_select(self.selected_index)
        elif event.key() == Qt.Key_Right:
            self.selected_index = min(len(self.image_paths) - 1, self.selected_index + 1)
            self.update_view()
            if self.on_select:
                self.on_select(self.selected_index)
        elif event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_view()

    def showEvent(self, event):
        super().showEvent(event)
        self.setWindowState(self.windowState() | Qt.WindowMaximized)
