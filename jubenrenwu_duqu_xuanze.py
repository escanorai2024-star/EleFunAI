from PySide6.QtWidgets import (QDialog, QVBoxLayout, QScrollArea, QFrame, 
                               QGridLayout, QPushButton, QLabel, QHBoxLayout, 
                               QWidget, QGraphicsDropShadowEffect, QApplication)
from PySide6.QtCore import Qt, QSize, QPoint
from PySide6.QtGui import QPixmap, QIcon, QColor, QCursor
import os
import PySide6.QtGui as QtGui

class ImageSelectionDialog(QDialog):
    def __init__(self, parent=None, name="", image_paths=[]):
        # 强制传入 None 作为父对象，确保它是顶级窗口，不受调用控件（如GraphicsProxyWidget）的约束
        super().__init__(None)
        # 添加 Qt.Window 标志确保它是独立的窗口
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 设置为全屏（不遮挡任务栏）
        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.availableGeometry())
        else:
            self.resize(800, 600)
            
        self.selected_path = None
        self.dragging = False
        self.drag_position = QPoint()
        
        # 主布局容器 (圆角背景)
        self.main_frame = QFrame(self)
        self.main_frame.setObjectName("MainFrame")
        self.main_frame.setStyleSheet("""
            QFrame#MainFrame {
                background-color: #2b2b2b;
                border: 1px solid #3d3d3d;
                border-radius: 12px;
            }
        """)
        
        # 阴影效果
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 4)
        self.main_frame.setGraphicsEffect(shadow)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.addWidget(self.main_frame)
        
        # 内部布局
        inner_layout = QVBoxLayout(self.main_frame)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(0)
        
        # 1. 标题栏
        title_bar = QFrame()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet("background-color: transparent;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(15, 0, 10, 0)
        
        title_label = QLabel(f"选择图片 - {name}")
        title_label.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: bold;")
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888888;
                border: none;
                border-radius: 14px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #c42b1c;
                color: white;
            }
        """)
        
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(close_btn)
        
        inner_layout.addWidget(title_bar)
        
        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #3d3d3d; max-height: 1px;")
        inner_layout.addWidget(line)

        # 2. 内容区域 (滚动区)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: #2b2b2b;
                width: 8px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #555555;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #777777;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)
        
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: transparent;")
        grid = QGridLayout(content_widget)
        grid.setContentsMargins(20, 20, 20, 20)
        grid.setSpacing(15)
        grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        row, col = 0, 0
        max_cols = 3
        
        for path in image_paths:
            if not os.path.exists(path):
                continue
                
            # 图片卡片容器
            card = QPushButton()
            card.setFixedSize(300, 300)
            card.setCursor(Qt.PointingHandCursor)
            
            # 加载图片并显示完整内容（不裁剪）
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                # 缩放图片以适应卡片，保持比例，不裁剪
                # 稍微留一点边距 (290x290) 以免遮挡圆角边框
                scaled_pix = pixmap.scaled(290, 290, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                
                # 创建透明背景的目标画布
                target = QPixmap(300, 300)
                target.fill(Qt.transparent)
                
                painter = QtGui.QPainter(target)
                painter.setRenderHint(QtGui.QPainter.Antialiasing)
                
                # 绘制图片居中
                x = (300 - scaled_pix.width()) // 2
                y = (300 - scaled_pix.height()) // 2
                painter.drawPixmap(x, y, scaled_pix)
                painter.end()
                
                card.setIcon(QIcon(target))
                card.setIconSize(QSize(300, 300))
            else:
                card.setText("无法加载")
            
            # 卡片样式
            card.setStyleSheet("""
                QPushButton {
                    background-color: #383838;
                    border: 2px solid transparent;
                    border-radius: 10px;
                }
                QPushButton:hover {
                    border: 2px solid #4CAF50;
                    background-color: #404040;
                }
                QPushButton:pressed {
                    background-color: #2e2e2e;
                    border-color: #388E3C;
                }
            """)
            
            card.clicked.connect(lambda checked=False, p=path: self.on_selected(p))
            grid.addWidget(card, row, col)
            
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
        
        scroll_area.setWidget(content_widget)
        inner_layout.addWidget(scroll_area)
        
        # 3. 底部提示
        hint_label = QLabel(f"共找到 {len(image_paths)} 张相关图片")
        hint_label.setAlignment(Qt.AlignCenter)
        hint_label.setStyleSheet("color: #888888; font-size: 12px; padding: 10px;")
        inner_layout.addWidget(hint_label)

    def on_selected(self, path):
        self.selected_path = path
        self.accept()

    # 拖拽窗口逻辑
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.dragging = False
