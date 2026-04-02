import json
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QSpinBox, QPushButton, QCheckBox, QFrame
)
from PySide6.QtCore import Qt, QSettings

class TimeCodeConfigWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("时间码设置")
        self.setFixedSize(300, 200)
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
                font-size: 14px;
            }
            QSpinBox {
                background-color: #3b3b3b;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 5px;
                border-radius: 4px;
            }
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QCheckBox {
                color: #ffffff;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        
        # Load settings
        self.settings = QSettings("LingDong", "GoogleScriptTimeCode")
        
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title_label = QLabel("时间码限制设置")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # Enable/Disable Toggle
        self.enable_cb = QCheckBox("启用时间码限制")
        self.enable_cb.setChecked(self.settings.value("enabled", False, type=bool))
        layout.addWidget(self.enable_cb)
        
        # Seconds Setting
        seconds_layout = QHBoxLayout()
        seconds_label = QLabel("镜头时长限制(秒):")
        self.seconds_spin = QSpinBox()
        self.seconds_spin.setRange(1, 300)
        self.seconds_spin.setValue(self.settings.value("seconds", 15, type=int))
        self.seconds_spin.setSuffix(" 秒")
        
        seconds_layout.addWidget(seconds_label)
        seconds_layout.addWidget(self.seconds_spin)
        layout.addLayout(seconds_layout)
        
        # Description
        desc_label = QLabel("说明: 开启后，一键分镜将限制每个镜头的最大时长。")
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #aaaaaa; font-size: 12px; margin-top: 10px;")
        layout.addWidget(desc_label)
        
        # Save Button
        save_btn = QPushButton("保存设置")
        save_btn.clicked.connect(self.save_config)
        layout.addWidget(save_btn)
        
    def save_config(self):
        self.settings.setValue("enabled", self.enable_cb.isChecked())
        self.settings.setValue("seconds", self.seconds_spin.value())
        self.accept()

    @staticmethod
    def get_config():
        settings = QSettings("LingDong", "GoogleScriptTimeCode")
        return {
            "enabled": settings.value("enabled", False, type=bool),
            "seconds": settings.value("seconds", 15, type=int)
        }
