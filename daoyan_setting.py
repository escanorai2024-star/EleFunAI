from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton, QButtonGroup, QPushButton, QCheckBox, QFrame
from PySide6.QtCore import Qt

class DirectorSettingDialog(QDialog):
    def __init__(self, current_count=1, char_detection=True, parent=None, director_node=None, script_time_optimization=False, storyboard_count=1):
        super().__init__(parent)
        self.setWindowTitle("导演设置")
        self.setFixedSize(300, 580)  # 调整高度以容纳新选项
        self.setStyleSheet("background-color: white; color: black;")
        self.selected_count = current_count
        self.storyboard_selected_count = storyboard_count
        self.char_detection_enabled = char_detection
        self.script_time_optimization_enabled = script_time_optimization
        self.recover_requested = False
        self.sora_mapping_requested = False
        self.director_node = director_node  # 保存导演节点引用
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # --- 批量视频生成数量 ---
        label = QLabel("批量视频生成数量:")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        
        self.button_group = QButtonGroup(self)
        self.radio_layout = QHBoxLayout()
        self.radio_layout.setAlignment(Qt.AlignCenter)
        
        # 第一行: 1-3个
        first_row = QHBoxLayout()
        first_row.setAlignment(Qt.AlignCenter)
        for i in range(1, 4):
            radio = QRadioButton(f"{i}个")
            if i == self.selected_count:
                radio.setChecked(True)
            self.button_group.addButton(radio, i)
            first_row.addWidget(radio)
        
        # 第二行: 4-6个
        second_row = QHBoxLayout()
        second_row.setAlignment(Qt.AlignCenter)
        for i in range(4, 7):
            radio = QRadioButton(f"{i}个")
            if i == self.selected_count:
                radio.setChecked(True)
            self.button_group.addButton(radio, i)
            second_row.addWidget(radio)
        
        layout.addLayout(first_row)
        layout.addLayout(second_row)
        
        # 说明文字
        info_label = QLabel("选择同时生成的视频变体数量\n(最多6个)")
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(info_label)
        
        # --- 分割线 ---
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #E0E0E0;")
        layout.addWidget(line)

        # --- 批量分镜生成数量 ---
        label_sb = QLabel("批量分镜生成数量:")
        label_sb.setAlignment(Qt.AlignCenter)
        layout.addWidget(label_sb)
        
        self.storyboard_button_group = QButtonGroup(self)
        sb_layout = QHBoxLayout()
        sb_layout.setAlignment(Qt.AlignCenter)
        
        for i in range(1, 5):
            radio = QRadioButton(f"{i}张")
            if i == self.storyboard_selected_count:
                radio.setChecked(True)
            self.storyboard_button_group.addButton(radio, i)
            sb_layout.addWidget(radio)
            
        layout.addLayout(sb_layout)

        sb_note = QLabel("批量生成分镜时的数量")
        sb_note.setAlignment(Qt.AlignCenter)
        sb_note.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(sb_note)

        # --- 分割线 ---
        line_sb = QFrame()
        line_sb.setFrameShape(QFrame.HLine)
        line_sb.setFrameShadow(QFrame.Sunken)
        line_sb.setStyleSheet("background-color: #E0E0E0;")
        layout.addWidget(line_sb)
        
        # --- 人物检测 ---
        self.check_char_detection = QCheckBox("人物检测")
        self.check_char_detection.setChecked(self.char_detection_enabled)
        # 居中显示
        h_layout = QHBoxLayout()
        h_layout.addStretch()
        h_layout.addWidget(self.check_char_detection)
        h_layout.addStretch()
        layout.addLayout(h_layout)
        
        # 备注
        char_note = QLabel("自动添加遗漏的人物")
        char_note.setAlignment(Qt.AlignCenter)
        char_note.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(char_note)

        # --- 剧本时间优化 ---
        self.check_script_time_optimization = QCheckBox("剧本时间优化")
        self.check_script_time_optimization.setChecked(self.script_time_optimization_enabled)
        h_layout_opt = QHBoxLayout()
        h_layout_opt.addStretch()
        h_layout_opt.addWidget(self.check_script_time_optimization)
        h_layout_opt.addStretch()
        layout.addLayout(h_layout_opt)
        
        opt_note = QLabel("使用剧本优化的时候产生时间码")
        opt_note.setAlignment(Qt.AlignCenter)
        opt_note.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(opt_note)

        # --- Sora2强制优化模式 ---
        self.check_dev_test = QCheckBox("Sora2强制优化模式")
        try:
            from daoyan_setting_test import is_test_mode_enabled
            self.check_dev_test.setChecked(is_test_mode_enabled())
        except ImportError:
            print("Warning: daoyan_setting_test module not found")
        
        h_layout_test = QHBoxLayout()
        h_layout_test.addStretch()
        h_layout_test.addWidget(self.check_dev_test)
        h_layout_test.addStretch()
        layout.addLayout(h_layout_test)
        
        test_note = QLabel("制作多宫格必须开启")
        test_note.setAlignment(Qt.AlignCenter)
        test_note.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(test_note)
        
        # --- 分割线 ---
        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setFrameShadow(QFrame.Sunken)
        line2.setStyleSheet("background-color: #E0E0E0;")
        layout.addWidget(line2)

        # --- Sora人物@模式 ---
        sora_mapping_btn = QPushButton("🎭 Sora人物@模式")
        sora_mapping_btn.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0; 
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px;
                margin-top: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7B1FA2;
            }
        """)
        sora_mapping_btn.clicked.connect(self.on_sora_mapping_clicked)
        layout.addWidget(sora_mapping_btn)

        sora_note = QLabel("设置人物@映射，添加到动画片场顶部")
        sora_note.setAlignment(Qt.AlignCenter)
        sora_note.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(sora_note)

        # --- 分割线 ---
        line3 = QFrame()
        line3.setFrameShape(QFrame.HLine)
        line3.setFrameShadow(QFrame.Sunken)
        line3.setStyleSheet("background-color: #E0E0E0;")
        layout.addWidget(line3)

        # --- 恢复镜头号 ---
        recover_btn = QPushButton("恢复镜头号")
        recover_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336; 
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px;
                margin-top: 5px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        recover_btn.clicked.connect(self.on_recover_clicked)
        layout.addWidget(recover_btn)

        recover_note = QLabel("恢复被删除的镜头并同步剧本数据")
        recover_note.setAlignment(Qt.AlignCenter)
        recover_note.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(recover_note)

        # --- 分割线 ---
        line4 = QFrame()
        line4.setFrameShape(QFrame.HLine)
        line4.setFrameShadow(QFrame.Sunken)
        line4.setStyleSheet("background-color: #E0E0E0;")
        layout.addWidget(line4)

        layout.addStretch()
        
        confirm_btn = QPushButton("确定")
        confirm_btn.clicked.connect(self.accept)
        layout.addWidget(confirm_btn)
        
    def accept(self):
        self.selected_count = self.button_group.checkedId()
        # 如果没有选中(理论上不可能，因为有默认)，默认1
        if self.selected_count == -1:
            self.selected_count = 1
            
        # 保存批量分镜数量
        sb_count = self.storyboard_button_group.checkedId()
        if sb_count != -1:
            self.storyboard_selected_count = sb_count

        self.char_detection_enabled = self.check_char_detection.isChecked()
        self.script_time_optimization_enabled = self.check_script_time_optimization.isChecked()
        
        # 保存开发测试状态
        try:
            from daoyan_setting_test import set_test_mode_enabled
            set_test_mode_enabled(self.check_dev_test.isChecked())
        except ImportError:
            pass
            
        super().accept()
    
    def on_sora_mapping_clicked(self):
        """打开Sora人物@模式设置"""
        self.sora_mapping_requested = True
        # 暂时关闭当前对话框，让主程序处理
        self.accept()
        
    def on_recover_clicked(self):
        self.recover_requested = True
        self.accept()

    def get_count(self):
        return self.selected_count

    def get_storyboard_count(self):
        return self.storyboard_selected_count

    def get_char_detection(self):
        return self.char_detection_enabled

    def get_recover_requested(self):
        return self.recover_requested
    
    def get_sora_mapping_requested(self):
        return self.sora_mapping_requested

    def get_script_time_optimization(self):
        return self.script_time_optimization_enabled
