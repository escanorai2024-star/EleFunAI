"""
灵动智能体 - 模型选择节点模块
支持选择图片模型或视频模型
"""

from PySide6.QtWidgets import (
    QGraphicsTextItem, QGraphicsProxyWidget, QComboBox, 
    QWidget, QVBoxLayout, QLabel
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QBrush, QPen

# SVG图标定义 - 模型选择（芯片图标）
SVG_MODEL_ICON = '''<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M9 3v1H4v16h16V4h-5V3H9z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M9 7h6M9 11h6M9 15h4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
<rect x="7" y="6" width="10" height="12" rx="1" stroke="currentColor" stroke-width="2"/>
<path d="M12 21v2M8 21v2M16 21v2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
</svg>'''


class ModelSelectionNode:
    """模型选择节点 - 选择图片模型或视频模型"""
    
    @staticmethod
    def create_node(CanvasNode):
        """动态创建模型选择节点类，继承自CanvasNode"""
        
        class ModelSelectionNodeImpl(CanvasNode):
            def __init__(self, x, y):
                # 调用父类构造函数
                super().__init__(x, y, 240, 160, "模型选择", SVG_MODEL_ICON)
                
                # 确保使用浅色背景
                self.setBrush(QBrush(QColor("#ffffff")))
                self.setPen(QPen(QColor("#DADCE0"), 1.5))
                
                # 当前选中的模型类型
                self.selected_model_type = "image" # image 或 video
                
                # 创建界面容器
                self.widget = QWidget()
                self.widget.setStyleSheet("background-color: transparent;")
                layout = QVBoxLayout(self.widget)
                layout.setContentsMargins(15, 5, 15, 15)
                layout.setSpacing(10)
                
                # 说明标签
                label = QLabel("选择生成模型类型:")
                label.setStyleSheet("""
                    color: #5f6368;
                    font-family: "Microsoft YaHei";
                    font-size: 12px;
                    font-weight: bold;
                """)
                layout.addWidget(label)
                
                # 下拉选择框
                self.combo_box = QComboBox()
                self.combo_box.addItems(["Stable Diffusion (图片)", "Stable Video Diffusion (视频)"])
                self.combo_box.setStyleSheet("""
                    QComboBox {
                        background-color: #f1f3f4;
                        color: #202124;
                        border: 1px solid #dadce0;
                        border-radius: 4px;
                        padding: 8px;
                        font-family: "Microsoft YaHei";
                        font-size: 13px;
                    }
                    QComboBox:hover {
                        background-color: #e8eaed;
                        border: 1px solid #b6b9bd;
                    }
                    QComboBox::drop-down {
                        border: none;
                        width: 20px;
                    }
                    QComboBox::down-arrow {
                        image: none;
                        border-left: 5px solid transparent;
                        border-right: 5px solid transparent;
                        border-top: 5px solid #5f6368;
                        margin-right: 5px;
                    }
                    QComboBox QAbstractItemView {
                        background-color: #ffffff;
                        color: #202124;
                        selection-background-color: #e8f0fe;
                        selection-color: #1967d2;
                        border: 1px solid #dadce0;
                    }
                """)
                self.combo_box.currentIndexChanged.connect(self.on_model_changed)
                layout.addWidget(self.combo_box)
                
                # 将QWidget嵌入到QGraphicsItem中
                self.proxy_widget = QGraphicsProxyWidget(self)
                self.proxy_widget.setWidget(self.widget)
                self.proxy_widget.setPos(0, 50)
                self.proxy_widget.resize(240, 100)
                
                # 初始化连接端口
                # 输出端口根据选择变化
                self.update_sockets()
                
            def on_model_changed(self, index):
                """模型改变处理"""
                if index == 0:
                    self.selected_model_type = "image"
                else:
                    self.selected_model_type = "video"
                
                print(f"[模型选择] 切换为: {self.selected_model_type}")
                # 可以在这里更新输出端口类型等
                
            def update_sockets(self):
                """更新端口"""
                # 默认只有一个输出，根据需要可以动态修改
                pass
                
            def get_output_data(self, socket_index):
                """获取输出数据"""
                return {
                    "model_type": self.selected_model_type,
                    "model_name": self.combo_box.currentText()
                }

        return ModelSelectionNodeImpl
