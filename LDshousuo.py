"""
灵动智能体 - 缩放节点模块
此节点的内容会随节点大小缩放
"""

from PySide6.QtWidgets import (
    QGraphicsProxyWidget, QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit
)
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QBrush, QColor, QPen, QTransform, QFont

# 简单的缩放图标 SVG
SVG_SCALE_ICON = """<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M21 15L15 21M21 15V19M21 15H17M3 9L9 3M3 9V5M3 9H7" stroke="#5f6368" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M21 3L15 9M21 3V7M21 3H17M3 21L9 15M3 21V17M3 21H7" stroke="#5f6368" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>"""

class ScalingNode:
    """缩放节点 - 内容随节点大小缩放"""
    
    @staticmethod
    def create_node(CanvasNode):
        """动态创建ScalingNode类，继承自CanvasNode"""
        
        class ScalingNodeImpl(CanvasNode):
            def __init__(self, x, y):
                # 初始尺寸
                self.base_width = 300
                self.base_height = 200
                
                super().__init__(x, y, self.base_width, self.base_height, "缩放节点", SVG_SCALE_ICON)
                
                # 设置背景
                self.setBrush(QBrush(QColor("#ffffff")))
                
                # 创建内部部件
                self.widget = QWidget()
                self.widget.setStyleSheet("background-color: transparent;")
                # 设置widget的初始逻辑尺寸
                self.widget.resize(self.base_width, self.base_height)
                
                # 布局和内容
                layout = QVBoxLayout(self.widget)
                layout.setContentsMargins(20, 50, 20, 20) # 顶部留出标题栏高度
                
                # 标题
                self.label = QLabel("我是可缩放内容")
                self.label.setStyleSheet("font-size: 18px; font-weight: bold; color: #333;")
                self.label.setAlignment(Qt.AlignCenter)
                layout.addWidget(self.label)
                
                # 文本框
                self.text_edit = QTextEdit()
                self.text_edit.setPlaceholderText("在这里输入文字，我会随节点缩放...")
                self.text_edit.setStyleSheet("border: 1px solid #ddd; border-radius: 4px; background: #f9f9f9;")
                layout.addWidget(self.text_edit)
                
                # 按钮
                self.btn = QPushButton("点击我")
                self.btn.setStyleSheet("background: #1a73e8; color: white; border-radius: 4px; padding: 8px;")
                layout.addWidget(self.btn)
                
                # 创建代理
                self.proxy = QGraphicsProxyWidget(self)
                self.proxy.setWidget(self.widget)
                self.proxy.setPos(0, 0)
                
                # 初始更新一次
                self.update_content_scale()
                
            def setRect(self, *args):
                """重写setRect以更新内容缩放"""
                super().setRect(*args)
                self.update_content_scale()
                
            def update_content_scale(self):
                """根据当前节点大小计算并应用缩放变换"""
                if not hasattr(self, 'proxy') or not hasattr(self, 'base_width'):
                    return

                rect = self.rect()
                current_w = rect.width()
                current_h = rect.height()
                
                # 计算缩放比例
                scale_x = current_w / self.base_width
                scale_y = current_h / self.base_height
                
                # 应用变换
                transform = QTransform()
                transform.scale(scale_x, scale_y)
                self.proxy.setTransform(transform)
                
        return ScalingNodeImpl
