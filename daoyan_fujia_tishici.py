import os
import json
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QLabel, QHBoxLayout
from PySide6.QtCore import Qt

class AdditionalPromptManager:
    def __init__(self):
        self.config_path = os.path.join(os.getcwd(), 'JSON', 'daoyan_fujia_tishici.json')
        self._ensure_config_dir()

    def _ensure_config_dir(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)

    def load_prompt(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('additional_prompt', '')
            except Exception as e:
                print(f"Error loading additional prompt: {e}")
        return ""

    def save_prompt(self, prompt):
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump({'additional_prompt': prompt}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving additional prompt: {e}")

class AdditionalPromptDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("附加视频提示词设置")
        self.resize(500, 300)
        self.manager = AdditionalPromptManager()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        label = QLabel("请输入附加视频提示词：")
        label.setStyleSheet("font-weight: bold; color: #333;")
        layout.addWidget(label)
        
        desc = QLabel("此处的提示词将追加到每个视频生成任务的提示词末尾。\n适用于添加通用的画风、质量词等（例如：8k resolution, cinematic lighting）。")
        desc.setStyleSheet("color: #666; font-size: 12px; margin-bottom: 5px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("在此输入附加视频提示词...")
        self.text_edit.setText(self.manager.load_prompt())
        self.text_edit.setStyleSheet("""
            QTextEdit {
                border: 1px solid #E1BEE7;
                border-radius: 4px;
                padding: 5px;
                background-color: #FAFAFA;
            }
            QTextEdit:focus {
                border: 1px solid #AB47BC;
                background-color: #FFFFFF;
            }
        """)
        layout.addWidget(self.text_edit)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("保存设置")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self.save_and_close)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        # Style
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #AB47BC;
                color: white;
                border-radius: 4px;
                padding: 6px 20px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background-color: #BA68C8;
            }
            QPushButton:pressed {
                background-color: #9C27B0;
            }
        """)
        
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #F5F5F5;
                color: #333;
                border: 1px solid #DDD;
                border-radius: 4px;
                padding: 6px 15px;
            }
            QPushButton:hover {
                background-color: #E0E0E0;
            }
        """)

    def save_and_close(self):
        prompt = self.text_edit.toPlainText().strip()
        self.manager.save_prompt(prompt)
        self.accept()

def get_additional_prompt():
    manager = AdditionalPromptManager()
    return manager.load_prompt()

def open_additional_prompt_dialog(parent=None):
    dialog = AdditionalPromptDialog(parent)
    dialog.exec()
