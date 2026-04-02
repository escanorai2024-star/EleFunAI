# -*- coding: utf-8 -*-
import json
import os
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QLabel, QPlainTextEdit, QGroupBox, QWidget, QInputDialog, QGridLayout)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class CharacterSettingsDialog(QDialog):
    """人物提示词设置对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("人物提示词设置")
        # 缩小窗口尺寸
        self.resize(300, 200)
        
        # 默认设置
        self.settings = {
            "style": "none",  # none, anime, realistic, 3d or custom string
            "custom_styles": [] # User added styles
        }
        self.settings_file = os.path.join(os.getcwd(), "json", "人物提示词设置.json")
        
        self.setup_ui()
        self.load_settings()
        self.refresh_style_buttons()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # 1. 风格选择区域
        self.style_group = QGroupBox("风格选择 (点击生效)")
        self.style_layout = QGridLayout(self.style_group)
        self.style_layout.setSpacing(5)
        
        layout.addWidget(self.style_group)
        
        # 3. 底部按钮
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("保存设置")
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 20px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        btn_save.clicked.connect(self.save_settings)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        
        layout.addLayout(btn_layout)
        
        # 样式表
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f5f5;
            }
            QGroupBox {
                background-color: white;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 3px;
                left: 10px;
            }
            QPushButton[checkable="true"] {
                background-color: #e0e0e0;
                border: none;
                border-radius: 4px;
                padding: 6px;
                color: #333;
                font-size: 12px;
            }
            QPushButton[checkable="true"]:checked {
                background-color: #4CAF50;
                color: white;
            }
        """)

    def refresh_style_buttons(self):
        # 清空布局
        while self.style_layout.count():
            item = self.style_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 默认和自定义风格
        default_styles = ["动漫风格", "真实风格", "3D"]
        custom_styles = self.settings.get("custom_styles", [])
        
        # 确保不重复显示
        all_styles = []
        for s in default_styles:
            all_styles.append(s)
        for s in custom_styles:
            if s not in all_styles:
                all_styles.append(s)
        
        row, col = 0, 0
        max_cols = 3
        
        # 获取当前选中的风格列表（支持多选，以逗号分隔）
        current_style_str = self.settings.get("style", "none")
        # 兼容旧的存储值
        if current_style_str == "anime": current_style_str = "动漫风格"
        elif current_style_str == "realistic": current_style_str = "真实风格"
        elif current_style_str == "3d": current_style_str = "3D"
        elif current_style_str == "none": current_style_str = ""
        
        current_styles = [s.strip() for s in current_style_str.split(',') if s.strip()]

        for style_text in all_styles:
            btn = QPushButton(style_text)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            
            # 检查选中状态
            if style_text in current_styles:
                btn.setChecked(True)
            
            # 使用闭包捕获 style_text
            btn.clicked.connect(lambda checked=False, s=style_text: self.on_style_selected(s))
            self.style_layout.addWidget(btn, row, col)
            
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
                
        # 添加 "+" 按钮
        btn_add = QPushButton("➕ 添加")
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.clicked.connect(self.add_custom_style)
        self.style_layout.addWidget(btn_add, row, col)

    def on_style_selected(self, style_text):
        # 获取当前选中的风格列表
        current_style_str = self.settings.get("style", "none")
        # 兼容旧的存储值
        if current_style_str == "anime": current_style_str = "动漫风格"
        elif current_style_str == "realistic": current_style_str = "真实风格"
        elif current_style_str == "3d": current_style_str = "3D"
        elif current_style_str == "none": current_style_str = ""
        
        current_styles = [s.strip() for s in current_style_str.split(',') if s.strip()]
        
        if style_text in current_styles:
            # 如果已选中，则取消选中
            current_styles.remove(style_text)
        else:
            # 如果未选中，则添加到列表
            current_styles.append(style_text)
            
        # 重新组合并保存
        if not current_styles:
            self.settings["style"] = "none"
        else:
            self.settings["style"] = ",".join(current_styles)
            
        self.refresh_style_buttons()

    def add_custom_style(self):
        text, ok = QInputDialog.getText(self, "添加风格", "请输入风格名称 (例如: 赛博朋克):")
        if ok and text:
            text = text.strip()
            if not text: return
            
            customs = self.settings.get("custom_styles", [])
            if text not in customs and text not in ["动漫风格", "真实风格", "3D"]:
                customs.append(text)
                self.settings["custom_styles"] = customs
                # 自动保存一次以免丢失
                # self.save_settings() # 还是等用户点保存按钮吧，保持一致性
                self.refresh_style_buttons()

    def load_settings(self):
        """加载设置"""
        json_dir = os.path.join(os.getcwd(), "json")
        if not os.path.exists(json_dir):
            os.makedirs(json_dir)
            
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.settings.update(data)
            except Exception as e:
                print(f"加载人物设置失败: {e}")

    def save_settings(self):
        """保存设置"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
            self.accept()
        except Exception as e:
            print(f"保存人物设置失败: {e}")
