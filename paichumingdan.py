from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QListWidget, QInputDialog, QMessageBox, QWidget, QLineEdit)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

class ExcludeListDialog(QDialog):
    """排除名单管理对话框"""
    def __init__(self, exclude_list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("排除名单管理")
        self.resize(400, 500)
        self.exclude_list = exclude_list[:]  # Copy
        self.setup_ui()
        self.setup_style()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题区域
        title_label = QLabel("⛔ 角色排除名单")
        title_label.setObjectName("titleLabel")
        layout.addWidget(title_label)

        info_label = QLabel("以下列表中的角色名称将会在读取剧本时被自动忽略。")
        info_label.setWordWrap(True)
        info_label.setObjectName("infoLabel")
        layout.addWidget(info_label)

        # 列表区域
        self.list_widget = QListWidget()
        self.list_widget.addItems(self.exclude_list)
        layout.addWidget(self.list_widget)

        # --- 新增：行内添加区域 ---
        add_layout = QHBoxLayout()
        add_layout.setSpacing(10)
        
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("在此输入角色名，按回车或点击添加...")
        self.input_name.returnPressed.connect(self.add_item)
        
        self.btn_add_confirm = QPushButton("添加")
        self.btn_add_confirm.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_confirm.clicked.connect(self.add_item)
        # 为添加按钮设置一个特定样式ID
        self.btn_add_confirm.setObjectName("addBtn")
        
        add_layout.addWidget(self.input_name)
        add_layout.addWidget(self.btn_add_confirm)
        layout.addLayout(add_layout)
        # ------------------------

        # 底部按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.btn_remove = QPushButton("➖ 移除选中")
        self.btn_save = QPushButton("💾 保存更改")
        
        self.btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # 设置主要按钮
        self.btn_save.setObjectName("primaryBtn")

        self.btn_remove.clicked.connect(self.remove_item)
        self.btn_save.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_remove)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        
        layout.addLayout(btn_layout)

    def setup_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
            }
            QLabel#titleLabel {
                font-size: 18px;
                font-weight: bold;
                color: #333;
            }
            QLabel#infoLabel {
                font-size: 13px;
                color: #666;
                margin-bottom: 5px;
            }
            QListWidget {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                background-color: #f8f9fa;
                padding: 5px;
                font-size: 14px;
                outline: none;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #eee;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
            }
            QListWidget::item:hover {
                background-color: #f1f1f1;
            }
            QLineEdit {
                border: 1px solid #dcdcdc;
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
                background-color: #fff;
            }
            QLineEdit:focus {
                border: 1px solid #1a73e8;
            }
            QPushButton {
                background-color: #f5f5f5;
                border: 1px solid #dcdcdc;
                border-radius: 6px;
                padding: 8px 15px;
                font-size: 13px;
                color: #333;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
            }
            QPushButton#primaryBtn {
                background-color: #1a73e8;
                color: white;
                border: none;
            }
            QPushButton#primaryBtn:hover {
                background-color: #1557b0;
            }
            QPushButton#primaryBtn:pressed {
                background-color: #0d47a1;
            }
            QPushButton#addBtn {
                background-color: #e8f0fe;
                color: #1a73e8;
                border: 1px solid #d2e3fc;
                font-weight: bold;
            }
            QPushButton#addBtn:hover {
                background-color: #d2e3fc;
            }
        """)

    def add_item(self):
        text = self.input_name.text().strip()
        if text:
            if text not in self.exclude_list:
                self.exclude_list.append(text)
                self.list_widget.addItem(text)
                # 滚动到底部
                self.list_widget.scrollToBottom()
                self.input_name.clear()
            else:
                QMessageBox.information(self, "提示", "该角色已在排除名单中")
        self.input_name.setFocus()

    def remove_item(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            item = self.list_widget.takeItem(row)
            if item.text() in self.exclude_list:
                self.exclude_list.remove(item.text())
        else:
            QMessageBox.warning(self, "提示", "请先选择要移除的角色")
            
    def get_list(self):
        return self.exclude_list
