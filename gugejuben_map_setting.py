from PySide6.QtWidgets import (QDialog, QVBoxLayout, QCheckBox, QPushButton, QLabel, QHBoxLayout, 
                               QTextEdit, QMessageBox, QWidget, QFrame)
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QFont, QIcon, QColor, QPalette
import os
import json

# Modern Dark Theme Stylesheet
STYLESHEET = """
QDialog {
    background-color: #2b2b2b;
    color: #e0e0e0;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
}

QLabel {
    color: #e0e0e0;
    font-size: 14px;
}

QLabel#title_label {
    font-size: 16px;
    font-weight: bold;
    color: #ffffff;
    margin-bottom: 10px;
}

QLabel#remark_label {
    color: #aaaaaa;
    font-size: 12px;
    font-style: italic;
}

QCheckBox {
    color: #e0e0e0;
    font-size: 14px;
    spacing: 8px;
    padding: 4px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #666;
    background: #3c3c3c;
}

QCheckBox::indicator:hover {
    border: 1px solid #888;
}

QCheckBox::indicator:checked {
    background: #00BCD4;
    border: 1px solid #00BCD4;
}

/* Add a visual cue for checked state since we don't have an icon image handy */
QCheckBox::indicator:checked:after {
    content: "";
    /* This pseudo-element syntax isn't fully supported in Qt stylesheets for content/shapes 
       so we might rely on color change (Cyan) to indicate active state. */
}

QPushButton {
    background-color: #3c3c3c;
    color: white;
    border: 1px solid #555;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #4c4c4c;
    border-color: #777;
}

QPushButton:pressed {
    background-color: #2c2c2c;
}

QPushButton#primary_btn {
    background-color: #00BCD4;
    color: #ffffff;
    border: none;
    font-weight: bold;
}

QPushButton#primary_btn:hover {
    background-color: #00ACC1;
}

QPushButton#primary_btn:pressed {
    background-color: #0097A7;
}

QPushButton#danger_btn {
    background-color: #d32f2f;
    color: white;
    border: none;
    font-weight: bold;
}

QPushButton#danger_btn:hover {
    background-color: #c62828;
}

QTextEdit {
    background-color: #1e1e1e;
    color: #e0e0e0;
    border: 1px solid #444;
    border-radius: 6px;
    padding: 8px;
    selection-background-color: #00BCD4;
    selection-color: white;
    font-family: "Consolas", "Microsoft YaHei", monospace;
}

QTextEdit:focus {
    border: 1px solid #00BCD4;
}

QScrollBar:vertical {
    border: none;
    background: #2b2b2b;
    width: 10px;
    margin: 0px 0px 0px 0px;
}
QScrollBar::handle:vertical {
    background: #555;
    min-height: 20px;
    border-radius: 5px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

class CleanKeywordsDialog(QDialog):
    def __init__(self, parent=None, node=None):
        super().__init__(parent)
        self.node = node
        self.setWindowTitle("设置清除词")
        self.setFixedSize(450, 550)
        self.json_path = os.path.join(os.getcwd(), 'json', 'clean_juben.json')
        self.setStyleSheet(STYLESHEET)
        self.setup_ui()
        self.load_keywords()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("设置清除词")
        title.setObjectName("title_label")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        desc = QLabel("输入要清除的词（每行一句）：")
        desc.setStyleSheet("color: #cccccc;")
        layout.addWidget(desc)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("例如：\n某某说\n(动作)")
        layout.addWidget(self.text_edit)
        
        info_label = QLabel("点击“开始清除”后，将自动从剧本中删除这些词。")
        info_label.setObjectName("remark_label")
        layout.addWidget(info_label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        
        clean_btn = QPushButton("保存")
        clean_btn.setObjectName("primary_btn")
        clean_btn.setCursor(Qt.PointingHandCursor)
        clean_btn.clicked.connect(self.save_and_clean)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(clean_btn)
        layout.addLayout(btn_layout)

    def load_keywords(self):
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    keywords = data.get("cleaning_words", [])
                    self.text_edit.setPlainText("\n".join(keywords))
            except Exception as e:
                print(f"Error loading clean keywords: {e}")

    def save_keywords(self):
        text = self.text_edit.toPlainText()
        keywords = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Ensure json directory exists
        json_dir = os.path.dirname(self.json_path)
        if not os.path.exists(json_dir):
            os.makedirs(json_dir)
            
        try:
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump({"cleaning_words": keywords}, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving clean keywords: {e}")
            QMessageBox.warning(self, "错误", f"保存配置失败: {str(e)}")
            return None
        return keywords

    def save_and_clean(self):
        # 1. Save keywords
        keywords = self.save_keywords()
        if keywords is None:
            return

        # 2. Perform one-time cleaning on existing data
        cleaned_cells = 0
        if self.node and hasattr(self.node, 'table'):
            table = self.node.table
            for r in range(table.rowCount()):
                for c in range(table.columnCount()):
                    item = table.item(r, c)
                    if item:
                        text = item.text()
                        original_text = text
                        for kw in keywords:
                            if kw and kw in text:
                                text = text.replace(kw, "")
                        
                        if text != original_text:
                            item.setText(text)
                            cleaned_cells += 1
        
        # 3. Update node's cached keywords for real-time cleaning
        if self.node and hasattr(self.node, 'load_clean_keywords'):
            self.node.load_clean_keywords()

        # 4. Show result and close
        if cleaned_cells > 0:
            QMessageBox.information(self, "保存成功", f"配置已保存！\n已自动清理 {cleaned_cells} 个单元格。")
        else:
            # Optional: just close silently or show small toast
            # QMessageBox.information(self, "保存成功", "配置已保存！")
            pass
            
        self.accept()

    def perform_cleaning(self):
        # Deprecated method, kept for compatibility or reference if needed, 
        # but UI now calls save_and_clean.
        pass

class MapSettingDialog(QDialog):
    _is_simplified_mode = False  # Class-level variable to store the state
    _is_force_char_detection = False # Class-level variable for force character detection

    def __init__(self, parent=None, node=None):
        super().__init__(parent)
        self.node = node
        self.setWindowTitle("参数设置")
        self.setFixedSize(350, 320) # Slightly larger for better spacing
        self.setStyleSheet(STYLESHEET)
        self.setup_ui()
        self.load_settings_from_storage()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(25, 25, 25, 25)

        # Title
        label = QLabel("分镜生成参数")
        label.setObjectName("title_label")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        # Content Container
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(10)
        container_layout.setContentsMargins(0, 0, 0, 0)
        
        # Simplified Mode Checkbox
        self.simplified_cb = QCheckBox("简化模式: 开启后，简化地点名称")
        self.simplified_cb.setCursor(Qt.PointingHandCursor)
        self.simplified_cb.setToolTip("勾选后，生成分镜时将提示AI简化地点描述，避免产生'王座'等复杂场景")
        container_layout.addWidget(self.simplified_cb)

        # Force Character Detection Checkbox
        self.force_char_cb = QCheckBox("强制角色检测")
        self.force_char_cb.setCursor(Qt.PointingHandCursor)
        self.force_char_cb.setToolTip("备注：勾选后会避免角色遗漏")
        container_layout.addWidget(self.force_char_cb)
        
        # Remark label
        remark_label = QLabel("  ( 备注：勾选后会避免角色遗漏 )")
        remark_label.setObjectName("remark_label")
        container_layout.addWidget(remark_label)

        layout.addWidget(container)

        # Clean Words Button
        self.clean_btn = QPushButton("🧹 设置清除词")
        self.clean_btn.setCursor(Qt.PointingHandCursor)
        self.clean_btn.setToolTip("设置要自动清除的词汇")
        self.clean_btn.clicked.connect(self.open_clean_dialog)
        layout.addWidget(self.clean_btn)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        
        save_btn = QPushButton("保存")
        save_btn.setObjectName("primary_btn")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self.save_settings)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def open_clean_dialog(self):
        dialog = CleanKeywordsDialog(self, self.node)
        dialog.exec()

    def load_settings_from_storage(self):
        settings = QSettings("LingDong", "MapSettings")
        MapSettingDialog._is_simplified_mode = settings.value("simplified_mode", False, type=bool)
        MapSettingDialog._is_force_char_detection = settings.value("force_char_detection", False, type=bool)
        
        self.simplified_cb.setChecked(MapSettingDialog._is_simplified_mode)
        self.force_char_cb.setChecked(MapSettingDialog._is_force_char_detection)

    def save_settings(self):
        MapSettingDialog._is_simplified_mode = self.simplified_cb.isChecked()
        MapSettingDialog._is_force_char_detection = self.force_char_cb.isChecked()
        
        settings = QSettings("LingDong", "MapSettings")
        settings.setValue("simplified_mode", MapSettingDialog._is_simplified_mode)
        settings.setValue("force_char_detection", MapSettingDialog._is_force_char_detection)
        
        self.accept()

    @classmethod
    def is_simplified_mode_enabled(cls):
        settings = QSettings("LingDong", "MapSettings")
        cls._is_simplified_mode = settings.value("simplified_mode", False, type=bool)
        return cls._is_simplified_mode

    @classmethod
    def is_force_char_detection_enabled(cls):
        settings = QSettings("LingDong", "MapSettings")
        cls._is_force_char_detection = settings.value("force_char_detection", False, type=bool)
        return cls._is_force_char_detection
