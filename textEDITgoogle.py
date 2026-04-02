"""
灵动智能体 - 谷歌剧本文字编辑模块
包含文字编辑对话框和谷歌剧本表格的双击处理逻辑
"""

import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout, 
    QGraphicsProxyWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

class TextEditDialog(QDialog):
    """大型文本编辑对话框"""
    
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.edited_text = text
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        self.setWindowTitle("编辑文字节点")
        self.setMinimumSize(700, 500)
        self.setStyleSheet("""
            QDialog {
                background-color: #0a0a0a;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 标题
        title = QLabel("📝 编辑文字内容")
        title.setStyleSheet("""
            color: #00bfff;
            font-size: 18px;
            font-weight: bold;
            padding-bottom: 10px;
        """)
        layout.addWidget(title)
        
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
        
        # 字符统计
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
        self.char_count_label.setText(f"字符数: {char_count} | 行数: {line_count}")
    
    def accept(self):
        """确定按钮 - 保存文本"""
        self.edited_text = self.text_edit.toPlainText()
        super().accept()
    
    def get_text(self):
        """获取编辑后的文本"""
        return self.text_edit.toPlainText()

def handle_google_table_double_click(table, row, column, script_dir, ImageViewerDialog):
    """
    处理谷歌剧本表格的双击事件
    
    参数:
        table: 表格控件实例
        row: 行号
        column: 列号
        script_dir: 剧本目录(用于解析相对路径)
        ImageViewerDialog: 图片查看器类
    """
    print(f"[DEBUG] Cell double clicked (Handler): {row}, {column}")
    item = table.item(row, column)
    if not item:
        return

    # 检查是否是图片列（开始帧、结束帧、草稿、镜头草图）
    header_text = table.horizontalHeaderItem(column).text() if table.horizontalHeaderItem(column) else ""
    is_image_col = header_text in ["开始帧", "结束帧", "草稿", "镜头草图"]
    
    if is_image_col:
        # 优先尝试从UserRole获取路径 (用于镜头拆分生成的图片)
        user_role_path = item.data(Qt.UserRole)
        final_path = None
        
        if user_role_path and isinstance(user_role_path, str) and os.path.exists(user_role_path):
            final_path = user_role_path
        else:
            # 尝试从文本获取路径
            file_path = item.text().strip()
            
            # 解析路径
            final_path = file_path
            if file_path and not os.path.isabs(file_path) and script_dir:
                try_path = os.path.join(script_dir, file_path)
                if os.path.exists(try_path):
                    final_path = try_path
        
        if final_path and os.path.exists(final_path):
            # 打开图片查看器
            dialog = ImageViewerDialog(final_path, table)
            dialog.exec()
            return
    
    # 无论是文本列，还是无效的图片列，都打开编辑对话框
    open_edit_dialog_for_item(item, table)

def open_edit_dialog_for_item(item, parent=None):
    """打开文本编辑对话框并更新Item"""
    print(f"[DEBUG] open_edit_dialog called")
    text = item.text()
    # 注意：这里parent设为None可能更安全，防止被scene遮挡，
    # 但如果需要模态，可能需要设为table的window
    dialog = TextEditDialog(text, None) 
    if dialog.exec() == QDialog.Accepted:
        new_text = dialog.get_text()
        item.setText(new_text)
        print(f"[DEBUG] Text updated: {new_text[:20]}...")
