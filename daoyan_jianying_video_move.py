import os
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QApplication
from PySide6.QtCore import Qt, QMimeData, QUrl, QPoint
from PySide6.QtGui import QDrag, QFont, QCursor
from daoyan_bofang import DirectorVideoPlayer
from video_jianyingpro import import_single_video

class DragButton(QPushButton):
    """支持拖拽的播放按钮"""
    def __init__(self, text, parent=None, video_path=None):
        super().__init__(text, parent)
        self.video_path = video_path
        self.drag_start_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        try:
            if not (event.buttons() & Qt.LeftButton):
                return
            if not self.drag_start_pos:
                return
            if (event.pos() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance():
                return

            if self.video_path and isinstance(self.video_path, str) and os.path.exists(self.video_path):
                try:
                    drag = QDrag(self)
                    mime_data = QMimeData()
                    url = QUrl.fromLocalFile(self.video_path)
                    mime_data.setUrls([url])
                    drag.setMimeData(mime_data)
                    pixmap = self.grab()
                    if not pixmap.isNull():
                        drag.setPixmap(pixmap)
                        drag.setHotSpot(event.pos())
                    drag.exec_(Qt.CopyAction)
                except Exception as e:
                    print(f"[DragButton] 拖拽失败: {e}")
            else:
                try:
                    super().mouseMoveEvent(event)
                except Exception as e:
                    print(f"[DragButton] 父类 mouseMoveEvent 出错: {e}")
        except Exception as e:
            print(f"[DragButton] mouseMoveEvent 异常: {e}")

class DraggableVideoWidget(QWidget):
    """
    可拖拽的视频控件
    包含 播放按钮(支持拖拽到外部) 和 切换按钮
    """
    def __init__(self, video_paths, parent=None, director_node=None, initial_index=0, lock_selection=False, on_video_change=None):
        super().__init__(parent)
        # 确保是列表
        if isinstance(video_paths, str):
            self.video_paths = [video_paths]
        elif isinstance(video_paths, list):
            self.video_paths = video_paths
        else:
            self.video_paths = []
        
        self.director_node = director_node
        self.current_index = initial_index
        self.lock_selection = lock_selection
        self.on_video_change = on_video_change
        
        # 边界检查
        if self.current_index < 0 or self.current_index >= len(self.video_paths):
            self.current_index = 0
        
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        
        # 上一个按钮
        self.prev_btn = QPushButton("<")
        self.prev_btn.setCursor(Qt.PointingHandCursor)
        self.prev_btn.setFixedSize(24, 24)
        self.prev_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent; 
                color: #757575; 
                border: 1px solid #E0E0E0; 
                border-radius: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #F5F5F5;
                color: #4CAF50;
                border-color: #4CAF50;
            }
        """)
        self.prev_btn.clicked.connect(self.prev_video)
        
        # 播放按钮 (DragButton)
        self.play_btn = DragButton("▶", self)
        self.play_btn.setCursor(Qt.PointingHandCursor)
        font = QFont("Arial", 80)
        font.setBold(True)
        self.play_btn.setFont(font)
        self.play_btn.setStyleSheet("background-color: transparent; color: #4CAF50; border: none;")
        self.play_btn.clicked.connect(self.play_video)
        
        # 发送到剪映按钮
        self.send_btn = QPushButton("剪")
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setFixedSize(28, 28)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent; 
                color: #2196F3; 
                border: 1px solid #BBDEFB; 
                border-radius: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #E3F2FD;
                color: #0D47A1;
                border-color: #0D47A1;
            }
        """)
        self.send_btn.setToolTip("发送到剪映（自动导入当前视频）")
        self.send_btn.clicked.connect(self.send_to_jianying)

        # 下一个按钮
        self.next_btn = QPushButton(">")
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn.setFixedSize(24, 24)
        self.next_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent; 
                color: #757575; 
                border: 1px solid #E0E0E0; 
                border-radius: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #F5F5F5;
                color: #4CAF50;
                border-color: #4CAF50;
            }
        """)
        self.next_btn.clicked.connect(self.next_video)
        
        layout.addWidget(self.prev_btn)
        layout.addWidget(self.play_btn)
        layout.addWidget(self.send_btn)
        layout.addWidget(self.next_btn)
        
        # Make sure mouse events are caught
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet("background-color: #ffffff;")
        
        self.update_buttons()

    def update_buttons(self):
        # 如果锁定或者是单个视频，隐藏切换按钮
        if self.lock_selection or len(self.video_paths) <= 1:
            self.prev_btn.hide()
            self.next_btn.hide()
        else:
            self.prev_btn.show()
            self.next_btn.show()
        
        # 更新 Tooltip
        if self.video_paths:
            current_path = self.video_paths[self.current_index]
            if isinstance(current_path, dict): # Handle loading/failed
                status = current_path.get('status')
                self.play_btn.setToolTip(f"状态: {status}")
                self.play_btn.setEnabled(False)
                self.play_btn.setStyleSheet("background-color: transparent; color: #BDBDBD; border: none;")
                self.play_btn.video_path = None
            else:
                self.play_btn.setToolTip(f"{current_path}\n({self.current_index + 1}/{len(self.video_paths)})\n(可拖拽到剪映)")
                self.play_btn.setEnabled(True)
                self.play_btn.setStyleSheet("background-color: transparent; color: #4CAF50; border: none;")
                self.play_btn.video_path = current_path

    def send_to_jianying(self):
        if not self.video_paths:
            return
        current_path = self.video_paths[self.current_index]
        if isinstance(current_path, dict):
            return
        if not current_path or not isinstance(current_path, str):
            return
        if not os.path.exists(current_path):
            print(f"[DraggableVideoWidget] 视频不存在，无法发送到剪映: {current_path}")
            return
        try:
            import_single_video(current_path)
        except Exception as e:
            print(f"[DraggableVideoWidget] 发送到剪映失败: {e}")

    def prev_video(self):
        if self.video_paths:
            self.current_index = (self.current_index - 1) % len(self.video_paths)
            self.update_buttons()
            if self.on_video_change:
                current_path = self.video_paths[self.current_index]
                if not isinstance(current_path, dict):
                    self.on_video_change(current_path)

    def next_video(self):
        if self.video_paths:
            self.current_index = (self.current_index + 1) % len(self.video_paths)
            self.update_buttons()
            if self.on_video_change:
                current_path = self.video_paths[self.current_index]
                if not isinstance(current_path, dict):
                    self.on_video_change(current_path)

    def play_video(self):
        """播放视频，处理全屏置顶问题"""
        if not self.video_paths: return
        
        video_path = self.video_paths[self.current_index]
        if isinstance(video_path, dict): return # Loading/Failed
        
        self.play_btn.video_path = video_path # Update path for DragButton if needed
        
        # 如果处于全屏模式，临时取消置顶
        if self.director_node and hasattr(self.director_node, 'is_fullscreen_mode') and self.director_node.is_fullscreen_mode:
            if hasattr(self.director_node, 'fs_window'):
                flags = self.director_node.fs_window.windowFlags()
                if flags & Qt.WindowStaysOnTopHint:
                    self.director_node.fs_window.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
                    self.director_node.fs_window.showFullScreen()

        if os.path.exists(video_path):
            try:
                if self.director_node is not None:
                    existing = getattr(self.director_node, "cinema_player_window", None)
                    if existing and existing.isVisible():
                        existing.close()
                    self.director_node.cinema_player_window = DirectorVideoPlayer(video_path)
                    self.director_node.cinema_player_window.show()
                else:
                    window = DirectorVideoPlayer(video_path)
                    window.show()
            except Exception as e:
                print(f"播放视频失败: {e}")
