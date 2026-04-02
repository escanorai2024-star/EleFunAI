"""
灵动智能体 - 分镜脚本配置模块
支持配置分镜表格的相关参数
"""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                                QPushButton, QSpinBox, QComboBox, QCheckBox,
                                QGroupBox, QFormLayout)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


class StoryboardSettingsDialog(QDialog):
    """分镜脚本配置对话框"""
    
    settings_changed = Signal(dict)  # 配置变更信号
    
    def __init__(self, parent=None, current_settings=None):
        super().__init__(parent)
        self.setWindowTitle("分镜脚本配置")
        self.setMinimumSize(450, 500)
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                color: #202124;
            }
            QLabel {
                color: #202124;
                font-size: 12px;
            }
            QGroupBox {
                color: #1a73e8;
                font-size: 13px;
                font-weight: bold;
                border: 1px solid #dadce0;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                background-color: #ffffff;
                color: #202124;
                border: 1px solid #dadce0;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #f1f3f4;
                border: 1px solid #c0c0c0;
            }
            QPushButton:pressed {
                background-color: #e8e8e8;
            }
            QSpinBox, QComboBox {
                background-color: #f8f9fa;
                color: #202124;
                border: 1px solid #dadce0;
                border-radius: 4px;
                padding: 5px;
                font-size: 12px;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background-color: #e8eaed;
                border: none;
            }
            QComboBox::drop-down {
                border: none;
                background-color: #e8eaed;
            }
            QCheckBox {
                color: #202124;
                font-size: 12px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #dadce0;
                border-radius: 3px;
                background-color: #ffffff;
            }
            QCheckBox::indicator:checked {
                background-color: #1a73e8;
            }
        """)
        
        # 当前配置（默认值）
        self.current_settings = current_settings or {
            'cell_height': 35,
            'header_height': 40,
            'auto_number': True,
            'highlight_color': '#ff0000',
            'text_color': '#202124',
            'header_color': '#1a73e8',
            'show_grid': True,
            'max_text_length': 80
        }
        
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题
        title = QLabel("⚙️ 分镜脚本配置")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #1a73e8; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # 表格尺寸配置
        size_group = QGroupBox("📏 表格尺寸")
        size_layout = QFormLayout()
        size_layout.setSpacing(10)
        
        # 单元格高度
        self.cell_height_spin = QSpinBox()
        self.cell_height_spin.setRange(25, 100)
        self.cell_height_spin.setValue(self.current_settings['cell_height'])
        self.cell_height_spin.setSuffix(" px")
        size_layout.addRow("单元格高度:", self.cell_height_spin)
        
        # 表头高度
        self.header_height_spin = QSpinBox()
        self.header_height_spin.setRange(30, 80)
        self.header_height_spin.setValue(self.current_settings['header_height'])
        self.header_height_spin.setSuffix(" px")
        size_layout.addRow("表头高度:", self.header_height_spin)
        
        # 最大文本长度
        self.max_text_spin = QSpinBox()
        self.max_text_spin.setRange(50, 200)
        self.max_text_spin.setValue(self.current_settings['max_text_length'])
        self.max_text_spin.setSuffix(" 字符")
        size_layout.addRow("文本显示长度:", self.max_text_spin)
        
        size_group.setLayout(size_layout)
        layout.addWidget(size_group)
        
        # 显示选项
        display_group = QGroupBox("🎨 显示选项")
        display_layout = QVBoxLayout()
        display_layout.setSpacing(10)
        
        # 自动编号
        self.auto_number_check = QCheckBox("自动编号镜头（第一列）")
        self.auto_number_check.setChecked(self.current_settings['auto_number'])
        display_layout.addWidget(self.auto_number_check)
        
        # 显示网格线
        self.show_grid_check = QCheckBox("显示表格网格线")
        self.show_grid_check.setChecked(self.current_settings['show_grid'])
        display_layout.addWidget(self.show_grid_check)
        
        display_group.setLayout(display_layout)
        layout.addWidget(display_group)
        
        # 颜色配置
        color_group = QGroupBox("🌈 颜色配置")
        color_layout = QFormLayout()
        color_layout.setSpacing(10)
        
        # 高亮颜色
        self.highlight_combo = QComboBox()
        self.highlight_combo.addItems(["红色", "蓝色", "绿色", "黄色", "紫色"])
        color_map = {
            '#ff0000': 0, '#0066ff': 1, '#00ff00': 2, 
            '#ffff00': 3, '#ff00ff': 4
        }
        self.highlight_combo.setCurrentIndex(
            color_map.get(self.current_settings['highlight_color'], 0)
        )
        color_layout.addRow("选中行高亮:", self.highlight_combo)
        
        color_group.setLayout(color_layout)
        layout.addWidget(color_group)
        
        # 添加弹性空间
        layout.addStretch()
        
        # 按钮行
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        # 恢复默认
        reset_btn = QPushButton("🔄 恢复默认")
        reset_btn.clicked.connect(self.reset_to_default)
        button_layout.addWidget(reset_btn)
        
        button_layout.addStretch()
        
        # 取消按钮
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        # 确定按钮
        ok_btn = QPushButton("✓ 确定")
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #e8f0fe;
                color: #1967d2;
                border: 1px solid #d2e3fc;
            }
            QPushButton:hover {
                background-color: #d2e3fc;
            }
        """)
        ok_btn.clicked.connect(self.accept_settings)
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
    
    def reset_to_default(self):
        """恢复默认设置"""
        self.cell_height_spin.setValue(35)
        self.header_height_spin.setValue(40)
        self.max_text_spin.setValue(80)
        self.auto_number_check.setChecked(True)
        self.show_grid_check.setChecked(True)
        self.highlight_combo.setCurrentIndex(0)
    
    def accept_settings(self):
        """应用设置"""
        # 颜色映射
        color_map = ['#ff0000', '#0066ff', '#00ff00', '#ffff00', '#ff00ff']
        
        settings = {
            'cell_height': self.cell_height_spin.value(),
            'header_height': self.header_height_spin.value(),
            'auto_number': self.auto_number_check.isChecked(),
            'highlight_color': color_map[self.highlight_combo.currentIndex()],
            'text_color': '#202124',
            'header_color': '#1a73e8',
            'show_grid': self.show_grid_check.isChecked(),
            'max_text_length': self.max_text_spin.value()
        }
        
        self.settings_changed.emit(settings)
        self.accept()
    
    def get_settings(self):
        """获取当前设置"""
        color_map = ['#ff0000', '#0066ff', '#00ff00', '#ffff00', '#ff00ff']
        
        return {
            'cell_height': self.cell_height_spin.value(),
            'header_height': self.header_height_spin.value(),
            'auto_number': self.auto_number_check.isChecked(),
            'highlight_color': color_map[self.highlight_combo.currentIndex()],
            'text_color': '#202124',
            'header_color': '#1a73e8',
            'show_grid': self.show_grid_check.isChecked(),
            'max_text_length': self.max_text_spin.value()
        }
