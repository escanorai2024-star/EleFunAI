from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QCheckBox, QLineEdit, QScrollArea, 
    QWidget, QFrame
)
from PySide6.QtCore import Qt
import json
import os

class SoraCharacterMappingDialog(QDialog):
    """Sora人物@模式设置对话框"""
    
    def __init__(self, character_names, current_mappings=None, enabled=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sora人物@模式")
        # Ensure dialog behaves correctly as a top-level window even if parented
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self.setMinimumSize(500, 400)
        self.setStyleSheet("background-color: white; color: black;")
        
        self.character_names = sorted(list(set(character_names)))  # 去重并排序
        self.mappings = current_mappings or {}
        self.enabled = enabled
        self.input_widgets = {}  # 存储输入框引用
        
        self.setup_ui()
    
    def showEvent(self, event):
        """显示事件"""
        super().showEvent(event)
        self.activateWindow()
        self.raise_()
        
        # 尝试聚焦第一个输入框
        if self.input_widgets:
            first_key = sorted(self.input_widgets.keys())[0]
            self.input_widgets[first_key].setFocus()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 标题
        title_label = QLabel("Sora人物@模式设置")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px;")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 开启/关闭开关
        self.enable_checkbox = QCheckBox("✔ 启用Sora人物@模式" if self.enabled else "✘ 启用Sora人物@模式")
        self.enable_checkbox.setChecked(self.enabled)
        self.enable_checkbox.stateChanged.connect(self.on_enable_changed)
        self.enable_checkbox.setStyleSheet("""
            QCheckBox {
                font-size: 14px;
                font-weight: bold;
                padding: 5px;
            }
        """)
        
        enable_layout = QHBoxLayout()
        enable_layout.addStretch()
        enable_layout.addWidget(self.enable_checkbox)
        enable_layout.addStretch()
        layout.addLayout(enable_layout)
        
        # 说明文字
        info_label = QLabel("启用后，人物名将在动画片场顶部添加@映射")
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setStyleSheet("color: gray; font-size: 11px; padding: 5px;")
        layout.addWidget(info_label)
        
        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #E0E0E0;")
        layout.addWidget(line)
        
        # 人物映射区域
        mapping_label = QLabel("人物@映射设置")
        mapping_label.setStyleSheet("font-size: 13px; font-weight: bold; padding: 8px;")
        layout.addWidget(mapping_label)
        
        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #E0E0E0;
                border-radius: 5px;
                background-color: #FAFAFA;
            }
        """)
        
        # 滚动内容容器
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(10)
        scroll_layout.setContentsMargins(10, 10, 10, 10)
        
        if not self.character_names:
            # 如果没有人物，显示提示
            no_char_label = QLabel("暂无人物数据\n请先连接剧本节点并加载数据")
            no_char_label.setAlignment(Qt.AlignCenter)
            no_char_label.setStyleSheet("color: #999; font-size: 12px; padding: 20px;")
            scroll_layout.addWidget(no_char_label)
        else:
            # 为每个人物创建输入行
            for char_name in self.character_names:
                char_row = self.create_character_row(char_name)
                scroll_layout.addWidget(char_row)
        
        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area, 1)
        
        # 底部按钮
        button_layout = QHBoxLayout()
        
        clear_btn = QPushButton("清空所有")
        clear_btn.setFixedSize(100, 35)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF5722;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #E64A19;
            }
        """)
        clear_btn.clicked.connect(self.clear_all_mappings)
        
        confirm_btn = QPushButton("确定")
        confirm_btn.setFixedSize(100, 35)
        confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        confirm_btn.clicked.connect(self.accept)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(100, 35)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #9E9E9E;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #757575;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(clear_btn)
        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(confirm_btn)
        layout.addLayout(button_layout)
    
    def create_character_row(self, char_name):
        """创建单个人物映射行"""
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(5, 5, 5, 5)
        row_layout.setSpacing(10)
        
        # 人物名标签
        name_label = QLabel(char_name)
        name_label.setFixedWidth(150)
        name_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                font-weight: bold;
                color: #333;
                background-color: white;
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        
        # @符号
        at_label = QLabel("→")
        at_label.setStyleSheet("font-size: 14px; color: #666; font-weight: bold;")
        
        # 输入框
        input_edit = QLineEdit()
        input_edit.setPlaceholderText("输入@标识，如: @tttss")
        input_edit.setText(self.mappings.get(char_name, ""))
        # 强制启用输入和焦点
        input_edit.setReadOnly(False)
        input_edit.setEnabled(True)
        input_edit.setFocusPolicy(Qt.StrongFocus)
        input_edit.setAttribute(Qt.WA_InputMethodEnabled, True)
        
        input_edit.setStyleSheet("""
            QLineEdit {
                font-size: 12px;
                padding: 8px;
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                background-color: white;
                color: black;
            }
            QLineEdit:focus {
                border: 2px solid #4CAF50;
            }
        """)
        
        self.input_widgets[char_name] = input_edit
        
        row_layout.addWidget(name_label)
        row_layout.addWidget(at_label)
        row_layout.addWidget(input_edit, 1)
        
        return row_widget
    
    def on_enable_changed(self, state):
        """启用状态改变"""
        if state == Qt.Checked:
            self.enable_checkbox.setText("✔ 启用Sora人物@模式")
        else:
            self.enable_checkbox.setText("✘ 启用Sora人物@模式")
    
    def clear_all_mappings(self):
        """清空所有映射"""
        for input_widget in self.input_widgets.values():
            input_widget.clear()
    
    def get_mappings(self):
        """获取所有映射"""
        mappings = {}
        for char_name, input_widget in self.input_widgets.items():
            text = input_widget.text().strip()
            if text:  # 只保存非空的映射
                mappings[char_name] = text
        return mappings
    
    def is_enabled(self):
        """是否启用"""
        return self.enable_checkbox.isChecked()


class SoraCharacterMappingManager:
    """Sora人物@模式管理器"""
    
    def __init__(self, node_id):
        self.node_id = node_id
        self.mappings = {}
        self.enabled = False
        self.load_settings()
    
    def get_json_path(self):
        """获取JSON文件路径"""
        dir_path = os.path.join(os.getcwd(), 'JSON')
        os.makedirs(dir_path, exist_ok=True)
        return os.path.join(dir_path, f'daoyan_sora_mapping_{self.node_id}.json')
    
    def load_settings(self):
        """加载设置"""
        try:
            path = self.get_json_path()
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.mappings = data.get('mappings', {})
                    self.enabled = data.get('enabled', False)
                    print(f"[节点#{self.node_id}] Loaded Sora character mappings: {len(self.mappings)} entries, enabled: {self.enabled}")
        except Exception as e:
            print(f"[节点#{self.node_id}] Error loading Sora character mappings: {e}")
    
    def save_settings(self):
        """保存设置"""
        try:
            path = self.get_json_path()
            data = {
                'enabled': self.enabled,
                'mappings': self.mappings
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[节点#{self.node_id}] Saved Sora character mappings: {len(self.mappings)} entries, enabled: {self.enabled}")
        except Exception as e:
            print(f"[节点#{self.node_id}] Error saving Sora character mappings: {e}")
    
    def update_settings(self, mappings, enabled):
        """更新设置"""
        self.mappings = mappings
        self.enabled = enabled
        self.save_settings()
    
    def get_mapping_header(self):
        """获取映射头部文本（添加到动画片场顶部）"""
        if not self.enabled or not self.mappings:
            return ""
        
        parts = []
        for char_name in sorted(self.mappings.keys()):
            mapping = self.mappings[char_name]
            parts.append(f"{char_name}={mapping}")
        
        return "【人物】" + " ".join(parts)
    
    def apply_to_text(self, original_text):
        """应用映射到文本（在顶部添加映射信息）"""
        if not self.enabled or not self.mappings:
            return original_text
        
        header = self.get_mapping_header()
        if not header:
            return original_text
        
        # 在原文本顶部添加映射信息
        return f"{header}\n{original_text}"
