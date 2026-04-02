from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor

class WorkbenchToggleButton(QPushButton):
    """
    工作台显示/隐藏切换按钮
    位于画布右上角
    """
    # 信号：发射当前工作台是否应该显示
    toggled_visibility = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(32, 32)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.is_workbench_visible = False
        
        # 初始样式和文本
        self.update_style()
        
        # 连接点击信号
        self.clicked.connect(self.on_clicked)

    def on_clicked(self):
        """点击处理"""
        self.is_workbench_visible = not self.is_workbench_visible
        self.update_style()
        self.toggled_visibility.emit(self.is_workbench_visible)

    def update_style(self):
        """更新按钮样式和图标"""
        if self.is_workbench_visible:
            # 工作台显示时，按钮显示"收起"图标 (向右箭头，因为在右边)
            # 或者使用折叠图标
            self.setText("》")
            self.setToolTip("隐藏工作台")
        else:
            # 工作台隐藏时，按钮显示"展开"图标 (向左箭头)
            self.setText("《") 
            self.setToolTip("显示工作台")
            
        self.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                border: 1px solid #dadce0;
                border-radius: 4px;
                color: #5f6368;
                font-weight: bold;
                font-size: 14px;
                font-family: "Microsoft YaHei", sans-serif;
            }
            QPushButton:hover {
                background-color: #f1f3f4;
                color: #202124;
                border-color: #dadce0;
            }
            QPushButton:pressed {
                background-color: #e8eaed;
            }
        """)
