from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt
import random

class AutoTextNodeManager:
    """自动文本节点管理器
    
    负责在工作台添加开关按钮，并处理自动创建文本节点的逻辑
    """
    def __init__(self, workbench):
        self.workbench = workbench
        self.is_enabled = False
        self.toggle_btn = None

    def create_toggle_button(self):
        """创建圆形开关按钮"""
        self.toggle_btn = QPushButton()
        self.toggle_btn.setFixedSize(22, 22)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(False)
        
        # 初始样式
        self.update_button_style()
        
        # 连接信号
        self.toggle_btn.toggled.connect(self.on_toggle)
        
        return self.toggle_btn

    def update_button_style(self):
        """更新按钮样式"""
        if self.is_enabled:
            self.toggle_btn.setToolTip("开启快速剧本")
            self.toggle_btn.setText("")
            self.toggle_btn.setStyleSheet("""
                QPushButton {
                    border-radius: 11px;
                    background-color: #34A853;
                    border: 2px solid #2E8B46;
                }
                QPushButton:hover {
                    background-color: #2E8B46;
                }
            """)
        else:
            self.toggle_btn.setToolTip("开启快速剧本")
            self.toggle_btn.setText("")
            self.toggle_btn.setStyleSheet("""
                QPushButton {
                    border-radius: 11px;
                    background-color: #FF5252;
                    border: 2px solid #D32F2F;
                }
                QPushButton:hover {
                    background-color: #FF1744;
                }
            """)

    def on_toggle(self, checked):
        """切换状态"""
        self.is_enabled = checked
        self.update_button_style()
        state = "开启" if checked else "关闭"
        print(f"[工作台] 自动文本节点功能已{state}")

    def handle_response(self, text, TextNodeClass):
        """处理响应，如果功能开启则创建节点"""
        if not self.is_enabled or not text:
            return

        try:
            # 获取画布视图和场景
            canvas_view = None
            if hasattr(self.workbench, 'canvas_view') and self.workbench.canvas_view:
                canvas_view = self.workbench.canvas_view
            elif hasattr(self.workbench, 'main_page') and self.workbench.main_page and hasattr(self.workbench.main_page, 'canvas'):
                canvas_view = self.workbench.main_page.canvas

            if not canvas_view:
                print("[AutoTextNode] 无法获取画布视图")
                return

            scene = canvas_view.scene
            
            # 计算新节点位置 (在视图中心附近随机偏移，避免重叠)
            # 获取视图中心在场景中的坐标
            viewport_rect = canvas_view.viewport().rect()
            center_scene_pos = canvas_view.mapToScene(viewport_rect.center())
            
            x = center_scene_pos.x() + random.randint(-50, 50)
            y = center_scene_pos.y() + random.randint(-50, 50)
            
            # 创建节点
            node = TextNodeClass(x, y)
            
            # 设置内容
            node.full_text = text
            node.update_display()
            
            # 添加到场景
            scene.addItem(node)
            
            # 选中新节点
            scene.clearSelection()
            node.setSelected(True)
            
            print(f"[AutoTextNode] 已自动创建文本节点，字数: {len(text)}")
            
        except Exception as e:
            print(f"[AutoTextNode] 创建节点失败: {e}")
            import traceback
            traceback.print_exc()
