
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel, QPushButton, 
    QScrollArea, QFrame, QApplication, QHBoxLayout
)
from PySide6.QtCore import Qt, QUrl, Signal, QSize
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtGui import QColor, QPalette, QIcon

class GlobalVideoItem(QFrame):
    """单视频卡片控件"""
    clicked = Signal(int)  # 发送索引
    
    def __init__(self, index, video_path, parent=None):
        super().__init__(parent)
        self.index = index
        self.video_path = video_path
        self.is_selected = False
        self.is_muted = True
        
        self.setFixedSize(320, 240) # 设定一个合理的固定大小
        self.setStyleSheet("""
            GlobalVideoItem {
                background-color: #000;
                border: 2px solid transparent;
                border-radius: 8px;
            }
        """)
        
        self.setup_ui()
        self.setup_player()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        
        # 视频容器
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background-color: black; border-radius: 6px;")
        layout.addWidget(self.video_widget)
        
        # 音频控制按钮 (悬浮在右下角)
        # 由于QVideoWidget覆盖了区域，我们需要把按钮放在父布局或者使用绝对定位
        # 这里使用布局简单的叠加方式可能不生效，因为QVideoWidget是原生窗口
        # 我们将在resizeEvent中定位按钮
        
        self.mute_btn = QPushButton("🔇", self)
        self.mute_btn.setFixedSize(30, 30)
        self.mute_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 150);
                color: white;
                border-radius: 15px;
                font-size: 16px;
                border: 1px solid rgba(255, 255, 255, 50);
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 200);
            }
        """)
        self.mute_btn.setCursor(Qt.PointingHandCursor)
        self.mute_btn.clicked.connect(self.toggle_mute)
        self.mute_btn.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 定位静音按钮到右下角
        self.mute_btn.move(self.width() - 40, self.height() - 40)

    def setup_player(self):
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        
        self.player.setSource(QUrl.fromLocalFile(self.video_path))
        self.audio_output.setVolume(0) # 默认静音
        self.player.setLoops(QMediaPlayer.Infinite) # 循环播放
        self.player.play()

    def toggle_mute(self):
        if self.is_muted:
            self.audio_output.setVolume(1.0) # 开启声音
            self.mute_btn.setText("🔊")
            self.is_muted = False
        else:
            self.audio_output.setVolume(0) # 静音
            self.mute_btn.setText("🔇")
            self.is_muted = True

    def set_selected(self, selected):
        self.is_selected = selected
        if selected:
            self.setStyleSheet("""
                GlobalVideoItem {
                    background-color: #000;
                    border: 3px solid #4CAF50; /* Green border */
                    border-radius: 8px;
                }
            """)
        else:
            self.setStyleSheet("""
                GlobalVideoItem {
                    background-color: #000;
                    border: 2px solid transparent;
                    border-radius: 8px;
                }
            """)

    def mousePressEvent(self, event):
        self.clicked.emit(self.index)
        super().mousePressEvent(event)
        
    def closeEvent(self, event):
        self.player.stop()
        super().closeEvent(event)
        
    def cleanup(self):
        self.player.stop()
        self.player.setVideoOutput(None)
        self.player.setAudioOutput(None)
        self.player = None


class GlobalViewWindow(QWidget):
    """全局观看窗口"""
    selection_changed = Signal(int)
    
    def __init__(self, shot_num, video_paths, current_index=0):
        super().__init__()
        self.shot_num = shot_num
        self.video_paths = video_paths
        self.current_index = current_index
        self.video_items = []
        
        self.setWindowTitle(f"镜头 {shot_num} - 全局预览")
        self.resize(1000, 600)
        self.setStyleSheet("background-color: #1e1e1e;")
        
        self.setup_ui()
        
        # 初始选中
        if 0 <= self.current_index < len(self.video_items):
            self.video_items[self.current_index].set_selected(True)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        
        # 顶部标题
        header = QLabel(f"镜头 {self.shot_num} 所有视频版本")
        header.setStyleSheet("color: white; font-size: 18px; font-weight: bold; margin: 10px;")
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)
        
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: #1e1e1e; border: none;")
        
        container = QWidget()
        container.setStyleSheet("background-color: #1e1e1e;")
        self.grid_layout = QGridLayout(container)
        self.grid_layout.setSpacing(20)
        self.grid_layout.setContentsMargins(20, 20, 20, 20)
        
        # 添加视频卡片
        row, col = 0, 0
        max_cols = 3 # 每行3个
        
        for i, path in enumerate(self.video_paths):
            item = GlobalVideoItem(i, path)
            item.clicked.connect(self.on_item_clicked)
            self.grid_layout.addWidget(item, row, col)
            self.video_items.append(item)
            
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
                
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def on_item_clicked(self, index):
        # 更新选中状态
        self.update_selection(index)
        # 发送信号
        self.selection_changed.emit(index)

    def update_selection(self, index):
        self.current_index = index
        for item in self.video_items:
            item.set_selected(item.index == index)

    def closeEvent(self, event):
        # 清理资源
        for item in self.video_items:
            item.cleanup()
        super().closeEvent(event)
