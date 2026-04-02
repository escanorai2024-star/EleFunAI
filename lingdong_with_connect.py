"""
灵动智能体 - 集成连线功能的完整示例
展示如何将 lingdongconnect.py 集成到现有的 lingdong.py 系统中
"""

from lingdong import *  # 导入原有的所有类
from lingdong import InfiniteCanvasView  # 明确导入画布类
from lingdongconnect import (
    Socket, SocketType, DataType, Connection, ConnectionManager,
    ConnectableNode, DATA_TYPE_COLORS
)
from PySide6.QtCore import Qt


# ==================== 增强的画布类（支持连线） ====================
class InfiniteCanvasWithConnection(InfiniteCanvasView):
    """
    继承原有的 InfiniteCanvasView，添加连线功能
    保持所有原有功能不变，仅添加连接处理
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 创建连接管理器
        self.connection_manager = ConnectionManager(self.scene)
        
        # 连接信号
        self.connection_manager.connection_created.connect(self.on_connection_created)
        self.connection_manager.connection_removed.connect(self.on_connection_removed)
        
        # 拖拽状态
        self.is_dragging_connection = False
        self.hover_socket = None
        
        # print("[画布] 连线功能已启用")
    
    def mousePressEvent(self, event):
        """
        重写鼠标按下事件
        优先检查是否点击接口，否则调用原有逻辑
        """
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            item = self.scene.itemAt(scene_pos, self.transform())
            
            # 检查是否点击了接口
            if isinstance(item, Socket):
                self.is_dragging_connection = True
                self.connection_manager.start_dragging(item, scene_pos)
                event.accept()
                return
        
        # 调用父类方法处理原有功能
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """
        重写鼠标移动事件
        拖拽连接时更新连线，否则调用原有逻辑
        """
        if self.is_dragging_connection:
            scene_pos = self.mapToScene(event.pos())
            self.connection_manager.update_dragging(scene_pos)
            
            # 检查是否悬停在接口上
            item = self.scene.itemAt(scene_pos, self.transform())
            if isinstance(item, Socket):
                self.hover_socket = item
            else:
                self.hover_socket = None
            
            event.accept()
            return
        
        # 调用父类方法处理原有功能
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """
        重写鼠标释放事件
        结束连线拖拽，否则调用原有逻辑
        """
        if event.button() == Qt.MouseButton.LeftButton and self.is_dragging_connection:
            self.connection_manager.end_dragging(self.hover_socket)
            self.is_dragging_connection = False
            self.hover_socket = None
            event.accept()
            return
        
        # 调用父类方法处理原有功能
        super().mouseReleaseEvent(event)
    
    def keyPressEvent(self, event):
        """
        重写键盘事件
        Delete键删除连接，否则调用原有逻辑
        """
        # Delete键删除选中的连接
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            selected_items = self.scene.selectedItems()
            connections_deleted = False
            
            for item in selected_items:
                if isinstance(item, Connection):
                    self.connection_manager.remove_connection(item)
                    connections_deleted = True
            
            # 如果删除了连接，不继续传递事件
            if connections_deleted:
                event.accept()
                return
        
        # 调用父类方法处理原有功能
        super().keyPressEvent(event)
    
    def on_connection_created(self, connection):
        """连接创建回调"""
        source_node = connection.source_socket.parent_node
        target_node = connection.target_socket.parent_node
        
        source_title = getattr(source_node, 'node_title', 'Unknown')
        target_title = getattr(target_node, 'node_title', 'Unknown')
        
        # print(f"[连接] ✓ {source_title} -> {target_title}")
    
    def on_connection_removed(self, connection):
        """连接移除回调"""
        print(f"[连接] ✗ 连接已移除")


# ==================== 增强的工作台类（支持连线） ====================
class WorkbenchWithConnection(Workbench):
    """
    继承原有的 Workbench，将画布替换为支持连线的版本
    """
    
    def __init__(self, parent=None):
        # 临时保存原有的 InfiniteCanvasView
        original_canvas = InfiniteCanvasView
        
        # 替换为支持连线的画布
        globals()['InfiniteCanvasView'] = InfiniteCanvasWithConnection
        
        # 调用父类初始化
        super().__init__(parent)
        
        # 恢复原有类
        globals()['InfiniteCanvasView'] = original_canvas
        
        print("[工作台] 连线功能已集成")


# ==================== 可连接的文本节点 ====================
class ConnectableTextNode(ConnectableNode, CanvasNode):
    """带连接功能的文本节点"""
    
    def __init__(self, x, y, width=280, height=200):
        CanvasNode.__init__(self, x, y, width, height, "文本节点", SVG_TEXT_ICON)
        ConnectableNode.__init__(self)
        
        # 添加接口
        self.add_input_socket(DataType.TEXT, "输入")
        self.add_output_socket(DataType.TEXT, "输出")
        
        # 文本内容
        from PySide6.QtWidgets import QTextEdit
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText("双击编辑...")
        
        self.full_text = ""
    
    def get_output_data(self, socket_index):
        """返回文本数据"""
        if socket_index == 0:
            return self.full_text or self.text_edit.toPlainText()
        return None
    
    def mouseDoubleClickEvent(self, event):
        """双击编辑"""
        # print("[文本节点] 双击编辑")
        super().mouseDoubleClickEvent(event)


# ==================== 可连接的图片节点 ====================
class ConnectableImageNode(ConnectableNode, CanvasNode):
    """带连接功能的图片节点"""
    
    def __init__(self, x, y, width=300, height=250):
        CanvasNode.__init__(self, x, y, width, height, "图片节点", SVG_IMAGE_ICON)
        ConnectableNode.__init__(self)
        
        # 添加接口：可以接收文本提示词，输出图片
        self.add_input_socket(DataType.TEXT, "提示词")
        self.add_output_socket(DataType.IMAGE, "图片")
        
        self.image_path = None
    
    def get_output_data(self, socket_index):
        """返回图片数据"""
        if socket_index == 0:
            return self.image_path
        return None


# ==================== 可连接的视频节点 ====================
class ConnectableVideoNode(ConnectableNode, CanvasNode):
    """带连接功能的视频节点"""
    
    def __init__(self, x, y, width=320, height=240):
        CanvasNode.__init__(self, x, y, width, height, "视频节点", SVG_VIDEO_ICON)
        ConnectableNode.__init__(self)
        
        # 添加接口
        self.add_input_socket(DataType.IMAGE, "输入图片")
        self.add_input_socket(DataType.TEXT, "提示词")
        self.add_output_socket(DataType.VIDEO, "视频")
        
        self.video_path = None
    
    def get_output_data(self, socket_index):
        """返回视频数据"""
        if socket_index == 0:
            return self.video_path
        return None


# ==================== 可连接的表格节点 ====================
class ConnectableTableNode(ConnectableNode, CanvasNode):
    """带连接功能的表格节点（分镜脚本）"""
    
    def __init__(self, x, y, width=600, height=400):
        CanvasNode.__init__(self, x, y, width, height, "分镜表格", SVG_TABLE_ICON)
        ConnectableNode.__init__(self)
        
        # 添加接口
        self.add_input_socket(DataType.TEXT, "剧本")
        self.add_output_socket(DataType.TABLE, "分镜表")
        self.add_output_socket(DataType.TEXT, "文本导出")
        
        self.table_data = []
    
    def get_output_data(self, socket_index):
        """返回表格数据"""
        if socket_index == 0:
            return self.table_data
        elif socket_index == 1:
            # 导出为文本
            return str(self.table_data)
        return None


# ==================== 处理节点（演示多输入输出） ====================
class ProcessorNode(ConnectableNode, CanvasNode):
    """通用处理节点"""
    
    def __init__(self, x, y, title="处理器", width=280, height=280):
        CanvasNode.__init__(self, x, y, width, height, title, SVG_DOC_ICON)
        ConnectableNode.__init__(self)
        
        # 多输入多输出
        self.add_input_socket(DataType.ANY, "输入1")
        self.add_input_socket(DataType.ANY, "输入2")
        self.add_input_socket(DataType.NUMBER, "参数")
        
        self.add_output_socket(DataType.ANY, "输出1")
        self.add_output_socket(DataType.ANY, "输出2")
    
    def get_output_data(self, socket_index):
        """返回处理后的数据"""
        input1 = self.get_input_data(0)
        input2 = self.get_input_data(1)
        
        if socket_index == 0:
            return f"Processed: {input1}"
        elif socket_index == 1:
            return f"Combined: {input1} + {input2}"
        return None


# ==================== 演示函数 ====================
def create_demo_workflow(canvas):
    """创建演示工作流"""
    
    # 创建节点
    text1 = ConnectableTextNode(-400, -150)
    text1.full_text = "一个美丽的日落场景"
    canvas.scene.addItem(text1)
    
    text2 = ConnectableTextNode(-400, 100)
    text2.full_text = "电影风格，4K"
    canvas.scene.addItem(text2)
    
    processor = ProcessorNode(-50, -50, "提示词合成")
    canvas.scene.addItem(processor)
    
    image_gen = ConnectableImageNode(300, -100, 320, 280)
    canvas.scene.addItem(image_gen)
    
    video_gen = ConnectableVideoNode(300, 220, 350, 260)
    canvas.scene.addItem(video_gen)
    
    # print("\n" + "="*60)
    # print("📌 演示工作流已创建！")
    # print("="*60)
    # print("操作说明：")
    # print("  1. 拖拽节点上的圆点（接口）可创建连接")
    # print("  2. 连接线颜色表示数据类型")
    # print("  3. 选中连接线后按 Delete 删除")
    # print("  4. 移动节点时连接线自动跟随")
    # print("="*60)
    # print("\n建议连接方式：")
    # print("  • 文本1 -> 处理器(输入1)")
    # print("  • 文本2 -> 处理器(输入2)")
    # print("  • 处理器(输出1) -> 图片生成器(提示词)")
    # print("  • 图片生成器(图片) -> 视频生成器(输入图片)")
    # print("="*60 + "\n")


# ==================== 测试主函数 ====================
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # 创建主窗口
    window = QMainWindow()
    window.setWindowTitle("灵动智能体 - 完整连线功能演示")
    window.setGeometry(100, 100, 1600, 1000)
    
    # 创建支持连线的画布
    canvas = InfiniteCanvasWithConnection()
    window.setCentralWidget(canvas)
    
    # 创建演示工作流
    create_demo_workflow(canvas)
    
    window.show()
    sys.exit(app.exec())
