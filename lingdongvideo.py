"""
灵动智能体 - 视频节点模块
支持点击上传视频，显示视频预览和时长信息
"""

from PySide6.QtWidgets import (
    QGraphicsTextItem, QGraphicsPixmapItem, QFileDialog, 
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QLabel, QWidget
)
from PySide6.QtCore import Qt, QRectF, QUrl, QSize, Signal, QTimer
from PySide6.QtGui import QFont, QColor, QPixmap, QImage, QPainter, QPen, QBrush, QIcon
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem, QVideoWidget


# SVG图标定义
SVG_VIDEO_ICON = '''<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<rect x="2" y="5" width="14" height="14" rx="2" stroke="currentColor" stroke-width="2"/>
<path d="M16 10l6-3v10l-6-3z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
</svg>'''


class VideoPlayerWindow(QDialog):
    """独立视频播放窗口"""
    
    def __init__(self, video_path, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.is_muted = False
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        import os
        
        self.setWindowTitle(f"视频播放 - {os.path.basename(self.video_path)}")
        self.setMinimumSize(800, 600)
        self.setStyleSheet("background-color: #0a0a0a;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 视频显示区域
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background-color: #000000;")
        layout.addWidget(self.video_widget, 1)
        
        # 控制栏
        control_bar = QWidget()
        control_bar.setFixedHeight(60)
        control_bar.setStyleSheet("""
            QWidget {
                background-color: #1a1a1a;
                border-top: 1px solid #2a2a2a;
            }
        """)
        control_layout = QHBoxLayout(control_bar)
        control_layout.setContentsMargins(15, 10, 15, 10)
        control_layout.setSpacing(10)
        
        # 播放/暂停按钮
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedSize(40, 40)
        self.play_btn.setStyleSheet("""
            QPushButton {
                background-color: #00ff88;
                color: #000000;
                border: none;
                border-radius: 20px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00cc6f;
            }
            QPushButton:pressed {
                background-color: #009955;
            }
        """)
        self.play_btn.clicked.connect(self.toggle_play)
        control_layout.addWidget(self.play_btn)
        
        # 时间标签
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: #888888; font-size: 12px;")
        self.time_label.setFixedWidth(100)
        control_layout.addWidget(self.time_label)
        
        # 进度条
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background-color: #2a2a2a;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background-color: #00ff88;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background-color: #00bfff;
                border-radius: 3px;
            }
        """)
        self.progress_slider.sliderPressed.connect(self.on_slider_pressed)
        self.progress_slider.sliderReleased.connect(self.on_slider_released)
        control_layout.addWidget(self.progress_slider, 1)
        
        # 音量/静音按钮
        self.mute_btn = QPushButton("🔊")
        self.mute_btn.setFixedSize(40, 40)
        self.mute_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                color: #00bfff;
                border: none;
                border-radius: 20px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
            }
        """)
        self.mute_btn.clicked.connect(self.toggle_mute)
        control_layout.addWidget(self.mute_btn)
        
        # 音量滑块
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.volume_slider.setStyleSheet(self.progress_slider.styleSheet())
        self.volume_slider.valueChanged.connect(self.on_volume_changed)
        control_layout.addWidget(self.volume_slider)
        
        layout.addWidget(control_bar)
        
        # 创建媒体播放器
        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(0.5)
        
        self.media_player = QMediaPlayer()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        
        # 连接信号
        self.media_player.durationChanged.connect(self.on_duration_changed)
        self.media_player.positionChanged.connect(self.on_position_changed)
        self.media_player.playbackStateChanged.connect(self.on_playback_state_changed)
        
        # 加载视频
        self.media_player.setSource(QUrl.fromLocalFile(self.video_path))
        
        # 自动播放
        QTimer.singleShot(100, self.media_player.play)
    
    def toggle_play(self):
        """切换播放/暂停"""
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()
    
    def toggle_mute(self):
        """切换静音"""
        self.is_muted = not self.is_muted
        self.audio_output.setMuted(self.is_muted)
        self.mute_btn.setText("🔇" if self.is_muted else "🔊")
    
    def on_volume_changed(self, value):
        """音量改变"""
        self.audio_output.setVolume(value / 100.0)
    
    def on_duration_changed(self, duration):
        """时长改变"""
        self.progress_slider.setRange(0, duration)
        minutes = duration // 60000
        seconds = (duration % 60000) // 1000
        self.time_label.setText(f"00:00 / {minutes:02d}:{seconds:02d}")
    
    def on_position_changed(self, position):
        """播放位置改变"""
        if not self.progress_slider.isSliderDown():
            self.progress_slider.setValue(position)
        
        # 更新时间显示
        current_min = position // 60000
        current_sec = (position % 60000) // 1000
        total_min = self.media_player.duration() // 60000
        total_sec = (self.media_player.duration() % 60000) // 1000
        self.time_label.setText(f"{current_min:02d}:{current_sec:02d} / {total_min:02d}:{total_sec:02d}")
    
    def on_playback_state_changed(self, state):
        """播放状态改变"""
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_btn.setText("⏸")
        else:
            self.play_btn.setText("▶")
    
    def on_slider_pressed(self):
        """进度条按下"""
        pass
    
    def on_slider_released(self):
        """进度条释放"""
        self.media_player.setPosition(self.progress_slider.value())
    
    def closeEvent(self, event):
        """关闭窗口时停止播放"""
        if self.media_player:
            self.media_player.stop()
        super().closeEvent(event)


class VideoNode:
    """视频节点 - 支持点击上传视频
    
    注意：这个类需要继承自CanvasNode，在导入时会动态继承
    """
    
    @staticmethod
    def create_video_node(CanvasNode):
        """动态创建VideoNode类，继承自CanvasNode"""
        
        class VideoNodeImpl(CanvasNode):
            """视频节点实现 - 支持点击上传视频、自由缩放"""
            
            def __init__(self, x, y):
                super().__init__(x, y, 280, 220, "视频", SVG_VIDEO_ICON)
                
                # 最小和最大尺寸
                self.min_width = 200
                self.min_height = 180
                self.max_width = 800
                self.max_height = 600
                
                # 缩放控制
                self.is_resizing = False
                self.resize_start_pos = None
                self.resize_start_rect = None
                
                # 视频数据
                self.video_path = None
                self.video_duration = 0  # 视频时长（秒）
                self.video_width = 0
                self.video_height = 0
                self.is_playing = False
                self.is_muted = False
                
                # 视频预览区域
                self.preview_text = QGraphicsTextItem(self)
                self.preview_text.setPlainText("点击上传视频...")
                self.preview_text.setDefaultTextColor(QColor("#666666"))
                self.preview_text.setFont(QFont("Microsoft YaHei", 9))
                self.preview_text.setPos(80, 105)
                
                # 视频显示项
                self.video_item = None
                self.thumbnail_item = None  # 视频缩略图
                self.thumbnail_pixmap = None  # 原始缩略图数据
                
                # 视频信息文本（右上角）
                self.info_text = QGraphicsTextItem(self)
                self.info_text.setPlainText("")
                self.info_text.setDefaultTextColor(QColor("#00bfff"))
                self.info_text.setFont(QFont("Microsoft YaHei", 8, QFont.Weight.Bold))
                self.info_text.setPos(180, 8)
                self.info_text.setVisible(False)
                
                # 控制按钮区域（底部）
                self.control_text = QGraphicsTextItem(self)
                self.control_text.setHtml("")  # 初始不显示，加载视频后显示控制栏
                self.control_text.setFont(QFont("Microsoft YaHei", 9))
                self.control_text.setPos(50, 185)
                self.control_text.setTextWidth(180)
                
                # 媒体播放器
                self.media_player = None
                self.audio_output = None
            
            def get_video_rect(self):
                """获取视频显示区域"""
                rect = self.rect()
                video_height = rect.height() - 80  # 留空间给标题和控制栏
                return QRectF(10, 50, rect.width() - 20, video_height)
            
            def mousePressEvent(self, event):
                """鼠标按下 - 单击控制、缩放"""
                if event.button() == Qt.MouseButton.LeftButton:
                    local_pos = event.pos()
                    rect = self.rect()
                    
                    # 检查是否点击在右下角缩放区域（15x15像素）
                    resize_zone = 15
                    if (local_pos.x() > rect.width() - resize_zone and 
                        local_pos.y() > rect.height() - resize_zone):
                        self.is_resizing = True
                        self.resize_start_pos = local_pos
                        self.resize_start_rect = self.rect()
                        event.accept()
                        return
                    
                    # 如果没有视频，点击上传
                    if not self.video_path:
                        video_rect = self.get_video_rect()
                        if video_rect.contains(local_pos):
                            self.upload_video()
                            event.accept()
                            return
                    else:
                        # 有视频，检查点击位置
                        video_rect = self.get_video_rect()
                        control_y = rect.height() - 25
                        control_rect = QRectF(10, control_y, 120, 20)  # 播放/暂停按钮区域
                        mute_rect = QRectF(140, control_y, 130, 20)     # 静音按钮区域
                        
                        if video_rect.contains(local_pos):
                            # 点击视频区域，播放/暂停
                            self.toggle_play()
                            event.accept()
                            return
                        elif control_rect.contains(local_pos):
                            # 点击播放按钮
                            self.toggle_play()
                            event.accept()
                            return
                        elif mute_rect.contains(local_pos):
                            # 点击静音按钮
                            self.toggle_mute()
                            event.accept()
                            return
                
                # 其他情况正常处理（拖动节点等）
                super().mousePressEvent(event)
            
            def mouseMoveEvent(self, event):
                """鼠标移动 - 缩放节点"""
                if self.is_resizing:
                    delta = event.pos() - self.resize_start_pos
                    
                    # 计算新尺寸
                    new_width = max(self.min_width, min(self.resize_start_rect.width() + delta.x(), self.max_width))
                    new_height = max(self.min_height, min(self.resize_start_rect.height() + delta.y(), self.max_height))
                    
                    # 更新节点矩形
                    self.setRect(0, 0, new_width, new_height)
                    
                    # 重新布局视频和控制元素
                    if self.video_item:
                        video_rect = self.get_video_rect()
                        self.video_item.setSize(QSize(int(video_rect.width()), int(video_rect.height())))
                        self.video_item.setPos(video_rect.x(), video_rect.y())
                        
                        # 更新缩略图布局
                        self.update_thumbnail_layout()
                    
                    # 更新控制文本位置
                    control_y = new_height - 25
                    self.control_text.setPos(50, control_y)
                    
                    # 更新信息文本位置
                    if self.info_text.isVisible():
                        text_width = self.info_text.boundingRect().width()
                        self.info_text.setPos(new_width - 10 - text_width, 8)
                    
                    event.accept()
                    return
                
                super().mouseMoveEvent(event)
            
            def mouseReleaseEvent(self, event):
                """鼠标释放 - 结束缩放"""
                if self.is_resizing:
                    self.is_resizing = False
                    self.resize_start_pos = None
                    self.resize_start_rect = None
                    print(f"[视频节点] 缩放完成: {self.rect().width():.0f}×{self.rect().height():.0f}")
                    event.accept()
                    return
                
                super().mouseReleaseEvent(event)
            
            def upload_video(self):
                """上传视频"""
                file_path, _ = QFileDialog.getOpenFileName(
                    None,
                    "选择视频",
                    "",
                    "视频文件 (*.mp4 *.avi *.mov *.mkv *.flv *.wmv *.webm);;所有文件 (*.*)"
                )
                
                if file_path:
                    self.load_video(file_path)
            
            def load_video(self, file_path):
                """加载并显示视频"""
                try:
                    import os
                    
                    # 保存视频路径
                    self.video_path = file_path
                    file_name = os.path.basename(file_path)
                    
                    # 隐藏提示文字
                    self.preview_text.setVisible(False)
                    
                    # 创建音频输出
                    self.audio_output = QAudioOutput()
                    self.audio_output.setVolume(0.5)
                    
                    # 创建媒体播放器
                    self.media_player = QMediaPlayer()
                    self.media_player.setAudioOutput(self.audio_output)
                    
                    # 创建视频显示项（使用动态视频区域）
                    self.video_item = QGraphicsVideoItem(self)
                    video_rect = self.get_video_rect()
                    self.video_item.setSize(QSize(int(video_rect.width()), int(video_rect.height())))
                    self.video_item.setPos(video_rect.x(), video_rect.y())
                    
                    # 设置视频输出
                    self.media_player.setVideoOutput(self.video_item)
                    
                    # 连接信号
                    self.media_player.durationChanged.connect(self.on_duration_changed)
                    self.media_player.mediaStatusChanged.connect(self.on_media_status_changed)
                    self.media_player.positionChanged.connect(self.on_position_changed)
                    self.media_player.playbackStateChanged.connect(self.on_playback_state_changed)
                    self.media_player.videoOutputChanged.connect(self.on_video_output_changed)
                    
                    # 加载视频
                    self.media_player.setSource(QUrl.fromLocalFile(file_path))
                    
                    # 尝试提取并显示首帧
                    self.extract_and_show_thumbnail(file_path)
                    
                    # 更新控制文本
                    self.update_control_text()
                    
                    print(f"[视频节点] 加载成功: {file_path}")
                    
                except Exception as e:
                    print(f"[视频节点] 加载视频出错: {e}")
                    import traceback
                    traceback.print_exc()
            
            def toggle_play(self):
                """切换播放/暂停"""
                if not self.media_player:
                    return
                
                # 播放时隐藏缩略图
                if self.thumbnail_item and self.thumbnail_item.isVisible():
                    self.thumbnail_item.setVisible(False)
                
                if self.is_playing:
                    self.media_player.pause()
                    print("[视频节点] 暂停播放")
                else:
                    self.media_player.play()
                    print("[视频节点] 开始播放")
            
            def toggle_mute(self):
                """切换静音/非静音"""
                if not self.audio_output:
                    return
                
                self.is_muted = not self.is_muted
                self.audio_output.setMuted(self.is_muted)
                self.update_control_text()
                
                status = "静音" if self.is_muted else "有声"
                print(f"[视频节点] {status}播放")
            
            def update_control_text(self):
                """更新控制按钮文本"""
                play_icon = "⏸" if self.is_playing else "▶"
                mute_icon = "🔇" if self.is_muted else "🔊"
                
                duration_str = ""
                if self.video_duration > 0:
                    minutes = int(self.video_duration // 60)
                    seconds = int(self.video_duration % 60)
                    duration_str = f"{minutes:02d}:{seconds:02d}"
                
                self.control_text.setHtml(
                    f'<div style="color: #00bfff; font-size: 10px;">'
                    f'<span style="cursor: pointer;">{play_icon} 播放</span> | '
                    f'<span style="cursor: pointer;">{mute_icon} 音量</span> | '
                    f'<span style="color: #888;">{duration_str}</span>'
                    f'</div>'
                )
            
            def extract_and_show_thumbnail(self, file_path):
                """提取并显示视频首帧"""
                try:
                    import cv2
                    import numpy as np
                    
                    cap = cv2.VideoCapture(file_path)
                    if cap.isOpened():
                        ret, frame = cap.read()
                        if ret:
                            # Convert BGR to RGB
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            h, w, ch = frame.shape
                            bytes_per_line = ch * w
                            image = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                            self.thumbnail_pixmap = QPixmap.fromImage(image)
                            
                            # Create or update thumbnail item
                            if self.thumbnail_item:
                                if self.thumbnail_item.scene():
                                    # 如果已经在场景中，移除它（或者重用）
                                    pass 
                                # 这里我们直接更新pixmap即可，不需要移除
                            else:
                                self.thumbnail_item = QGraphicsPixmapItem(self)
                            
                            # Scale and position
                            self.update_thumbnail_layout()
                            
                            self.thumbnail_item.setVisible(True)
                        cap.release()
                except ImportError:
                    print("[视频节点] 未安装opencv-python，无法提取缩略图")
                except Exception as e:
                    print(f"[视频节点] 提取缩略图失败: {e}")
                    import traceback
                    traceback.print_exc()

            def update_thumbnail_layout(self):
                """更新缩略图布局"""
                if not self.thumbnail_item or not self.thumbnail_pixmap:
                    return
                    
                video_rect = self.get_video_rect()
                
                # Scale pixmap
                scaled_pixmap = self.thumbnail_pixmap.scaled(
                    int(video_rect.width()), int(video_rect.height()),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.thumbnail_item.setPixmap(scaled_pixmap)
                
                # Center it
                x_offset = (video_rect.width() - scaled_pixmap.width()) / 2
                y_offset = (video_rect.height() - scaled_pixmap.height()) / 2
                self.thumbnail_item.setPos(video_rect.x() + x_offset, video_rect.y() + y_offset)

            def on_duration_changed(self, duration):
                """视频时长改变"""
                if duration > 0:
                    self.video_duration = duration / 1000
                    self.update_control_text()
                    print(f"[视频节点] 时长: {self.video_duration:.1f}秒")
            
            def on_media_status_changed(self, status):
                """媒体状态改变"""
                from PySide6.QtMultimedia import QMediaPlayer
                
                if status == QMediaPlayer.MediaStatus.LoadedMedia:
                    print(f"[视频节点] 视频加载完成")
                    # 尝试获取视频尺寸
                    self.update_video_size()
            
            def on_video_output_changed(self):
                """视频输出改变时获取尺寸"""
                self.update_video_size()
            
            def update_video_size(self):
                """更新视频尺寸显示"""
                try:
                    if self.video_item and hasattr(self.video_item, 'nativeSize'):
                        native_size = self.video_item.nativeSize()
                        if native_size.isValid() and native_size.width() > 0:
                            self.video_width = native_size.width()
                            self.video_height = native_size.height()
                            
                            # 显示视频尺寸
                            size_info = f"{self.video_width}×{self.video_height}"
                            self.info_text.setPlainText(size_info)
                            self.info_text.setVisible(True)
                            text_width = self.info_text.boundingRect().width()
                            self.info_text.setPos(270 - text_width, 8)
                            
                            print(f"[视频节点] 尺寸: {size_info}")
                except Exception as e:
                    print(f"[视频节点] 获取尺寸失败: {e}")
            
            def on_position_changed(self, position):
                """播放位置改变"""
                # 如果还没有获取到尺寸，尝试更新
                if self.video_width == 0 and self.video_item:
                    self.update_video_size()
            
            def on_playback_state_changed(self, state):
                """播放状态改变"""
                from PySide6.QtMultimedia import QMediaPlayer
                
                self.is_playing = (state == QMediaPlayer.PlaybackState.PlayingState)
                self.update_control_text()
            
            def mouseDoubleClickEvent(self, event):
                """双击事件 - 弹出新窗口播放"""
                if event.button() == Qt.MouseButton.LeftButton and self.video_path:
                    self.open_video_window()
                    event.accept()
                    return
                
                super().mouseDoubleClickEvent(event)
            
            def open_video_window(self):
                """打开独立视频播放窗口"""
                try:
                    video_window = VideoPlayerWindow(self.video_path)
                    video_window.exec()
                except Exception as e:
                    print(f"[视频节点] 打开播放窗口失败: {e}")
                    import traceback
                    traceback.print_exc()
            
            def paint(self, painter, option, widget):
                """自定义绘制 - 添加缩放指示"""
                super().paint(painter, option, widget)
                
                # 绘制视频区域边框
                if self.video_path:
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    video_rect = self.get_video_rect()
                    painter.setPen(QPen(QColor("#00bfff"), 1))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRoundedRect(video_rect, 4, 4)
                
                # 绘制右下角缩放指示器（当鼠标悬停或正在缩放时）
                if self.isSelected() or self.is_resizing:
                    from PySide6.QtCore import QPointF
                    from PySide6.QtGui import QPolygonF
                    rect = self.rect()
                    painter.setPen(QPen(QColor("#00bfff"), 2))
                    # 绘制右下角小三角形
                    points = [
                        rect.bottomRight() + QPointF(-15, 0),
                        rect.bottomRight() + QPointF(0, -15),
                        rect.bottomRight()
                    ]
                    painter.drawPolygon(QPolygonF(points))
            
            def get_video_info(self):
                """获取视频信息"""
                if self.video_path:
                    return {
                        'path': self.video_path,
                        'duration': self.video_duration,
                        'is_playing': self.is_playing,
                        'is_muted': self.is_muted
                    }
                return None
        
        return VideoNodeImpl
