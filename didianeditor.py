"""
灵动智能体 - 地点节点编辑器模块
支持地点列表的编辑、增删
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout, QLabel
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

class DetailTextEdit(QTextEdit):
    """支持双击编辑的文本框"""
    doubleClicked = Signal(object) # 传递自身
    
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit(self)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

class LocationEditorDialog(QDialog):
    """地点列表编辑对话框"""
    
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.edited_text = text
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        self.setWindowTitle("编辑文字内容")
        self.setMinimumSize(700, 500)
        self.setStyleSheet("""
            QDialog {
                background-color: #0a0a0a;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 标题 (完全匹配图片)
        title = QLabel("📝 编辑文字内容")
        title.setStyleSheet("""
            color: #00bfff;
            font-size: 18px;
            font-weight: bold;
            padding-bottom: 10px;
        """)
        layout.addWidget(title)
        
        # 移除了提示标签，以匹配图片
        
        # 文本编辑区域
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(self.edited_text)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a1a;
                color: #e0e0e0;
                border: 2px solid #2a2a2a;
                border-radius: 8px;
                padding: 15px;
                font-size: 14px;
                font-family: "Microsoft YaHei", "微软雅黑", sans-serif;
                line-height: 1.6;
            }
            QTextEdit:focus {
                border: 2px solid #00bfff;
            }
        """)
        self.text_edit.setFont(QFont("Microsoft YaHei", 11))
        layout.addWidget(self.text_edit, 1)
        
        # 字符统计 (匹配图片样式：字符数: 1 | 行数: 1)
        self.char_count_label = QLabel()
        self.update_char_count()
        self.char_count_label.setStyleSheet("""
            color: #888888;
            font-size: 11px;
            padding: 5px 0;
        """)
        layout.addWidget(self.char_count_label)
        
        # 连接文本改变信号
        self.text_edit.textChanged.connect(self.update_char_count)
        
        # 按钮栏
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        # 清空按钮
        clear_btn = QPushButton("🗑 清空")
        clear_btn.setFixedHeight(40)
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                color: #888888;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 0 20px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                color: #ff6666;
                border: 1px solid #ff6666;
            }
            QPushButton:pressed {
                background-color: #ff6666;
                color: #000000;
            }
        """)
        clear_btn.clicked.connect(self.text_edit.clear)
        button_layout.addWidget(clear_btn)
        
        button_layout.addStretch()
        
        # 取消按钮
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedHeight(40)
        cancel_btn.setFixedWidth(100)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                color: #888888;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                color: #e0e0e0;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        # 确定按钮
        ok_btn = QPushButton("✓ 确定")
        ok_btn.setFixedHeight(40)
        ok_btn.setFixedWidth(100)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #00ff88;
                color: #000000;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00cc6f;
            }
            QPushButton:pressed {
                background-color: #009955;
            }
        """)
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
        
        # 设置焦点到文本框
        self.text_edit.setFocus()
        
        # 移动光标到末尾
        cursor = self.text_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.text_edit.setTextCursor(cursor)
    
    def update_char_count(self):
        """更新字符统计"""
        text = self.text_edit.toPlainText()
        char_count = len(text)
        line_count = text.count('\n') + 1 if text else 0
        
        # 统计地点数 (附加信息，不影响视觉一致性，但对用户有用)
        # 为了严格匹配图片，我们可能应该只显示字符数和行数？
        # 图片显示：字符数: 1 | 行数: 1
        # 我们保持这个格式
        self.char_count_label.setText(f"字符数: {char_count} | 行数: {line_count}")
    
    def accept(self):
        """确定按钮 - 保存文本"""
        self.edited_text = self.text_edit.toPlainText()
        super().accept()
    
    def get_text(self):
        """获取编辑后的文本"""
        return self.text_edit.toPlainText()
