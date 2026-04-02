from PySide6.QtWidgets import QPushButton, QGraphicsProxyWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout, QPushButton, QTextEdit
from PySide6.QtCore import Signal

class FujiaZhiButton:
    def __init__(self, parent_node):
        self.parent_node = parent_node
        self.button = QPushButton("生成图片附加值")
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setStyleSheet("QPushButton { background-color: #FF9800; color: white; border: none; border-radius: 4px; padding: 4px 8px; font-weight: bold; } QPushButton:hover { background-color: #FB8C00; }")
        self.proxy = QGraphicsProxyWidget(parent_node)
        self.proxy.setWidget(self.button)
        self.proxy.setZValue(200)
        self.update_position()
    def update_position(self):
        r = self.parent_node.rect()
        self.proxy.setPos(r.width() - 90, 8)

def create_fujiazhi_button(parent=None):
    btn = QPushButton("生成图片附加值", parent)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet("QPushButton { background-color: #FF9800; color: white; border: none; border-radius: 4px; padding: 5px 10px; font-weight: bold; font-family: 'Microsoft YaHei'; } QPushButton:hover { background-color: #FB8C00; }")
    return btn

class AdditionalValueDialog(QDialog):
    toggled = Signal(bool)
    def __init__(self, current_text="", parent=None, enabled=True):
        super().__init__(parent)
        self.setWindowTitle("生成图片附加值")
        self.setMinimumSize(560, 320)
        self.setStyleSheet("QDialog { background-color: #0a0a0a; } QLabel { color: #e0e0e0; }")
        self.setWindowFlags(Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose)
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
