"""
灵动智能体 - 节点连线系统
============================

类似 ComfyUI 的节点连接功能，支持：
- 输入/输出接口（Socket）
- 拖拽连线
- 贝塞尔曲线连接线
- 连接验证
- 连接管理
- ✨ 跨类型连接（任意数据类型可互相连接）

快速使用：
----------

1. 创建可连接节点：
    from lingdongconnect import ConnectableNode, DataType
    from lingdong import CanvasNode
    
    class MyNode(ConnectableNode, CanvasNode):
        def __init__(self, x, y):
            CanvasNode.__init__(self, x, y, 280, 200, "节点", "")
            ConnectableNode.__init__(self)
            self.add_input_socket(DataType.TEXT, "输入")
            self.add_output_socket(DataType.TEXT, "输出")

2. 增强画布支持拖拽：
    from lingdongconnect import ConnectionManager, Socket
    from lingdong import InfiniteCanvasView
    
    class MyCanvas(InfiniteCanvasView):
        def __init__(self):
            super().__init__()
            self.connection_manager = ConnectionManager(self.scene)
        
        # 重写 mousePressEvent/mouseMoveEvent/mouseReleaseEvent
        # 参考 test_connect.py

3. 运行测试：
    python test_socket_fix.py

数据类型颜色（仅用于视觉区分，不限制连接）：
- TEXT(文本): 绿色 #00ff88
- IMAGE(图片): 紫色 #ff00ff
- VIDEO(视频): 蓝色 #00bfff
- TABLE(表格): 黄色 #ffcc00
- NUMBER(数字): 橙色 #ff8800
- ANY(任意): 白色 #ffffff

⚠️ 注意：数据类型只影响Socket和连线的颜色，不限制连接。
         任意类型的节点都可以互相连接（文字➜图片➜视频等）。
"""

from PySide6.QtWidgets import QGraphicsItem, QGraphicsEllipseItem, QGraphicsPathItem
from PySide6.QtCore import Qt, QPointF, QRectF, Signal, QObject
from PySide6.QtGui import QPen, QBrush, QColor, QPainterPath, QPainter


# ==================== 接口类型定义 ====================
class SocketType:
    """接口类型枚举"""
    INPUT = "input"    # 输入接口（左侧）
    OUTPUT = "output"  # 输出接口（右侧）


class DataType:
    """数据类型枚举"""
    ANY = "any"          # 任意类型（白色）
    TEXT = "text"        # 文本（绿色）
    IMAGE = "image"      # 图片（紫色）
    VIDEO = "video"      # 视频（蓝色）
    TABLE = "table"      # 表格（黄色）
    NUMBER = "number"    # 数字（橙色）


# 数据类型对应的颜色
DATA_TYPE_COLORS = {
    DataType.ANY: "#00ff88",
    DataType.TEXT: "#00ff88",
    DataType.IMAGE: "#00ff88",
    DataType.VIDEO: "#00ff88",
    DataType.TABLE: "#00ff88",
    DataType.NUMBER: "#00ff88"
}


# ==================== 接口（Socket）类 ====================
class Socket(QGraphicsEllipseItem):
    """节点接口 - 可连接的输入/输出点"""
    
    def __init__(self, parent_node, socket_type, data_type, index=0, label=""):
        """
        初始化接口
        
        Args:
            parent_node: 父节点
            socket_type: 接口类型（INPUT/OUTPUT）
            data_type: 数据类型
            index: 接口索引（从上到下）
            label: 接口标签
        """
        # 接口大小
        radius = 6
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        
        self.parent_node = parent_node
        self.socket_type = socket_type
        self.data_type = data_type
        self.index = index
        self.label = label
        
        # 连接列表
        self.connections = []
        
        # 设置父节点
        self.setParentItem(parent_node)
        
        # 设置样式
        self.update_style()
        
        # 设置标志
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)  # 忽略缩放变换，保持固定大小
        self.setAcceptHoverEvents(True)  # 接受悬停事件
        
        # 设置z值，确保在节点上方
        self.setZValue(100)
        
        # 计算位置
        self.update_position()
    
    def update_style(self, is_hover=False):
        """更新接口样式"""
        color = QColor(DATA_TYPE_COLORS.get(self.data_type, "#ffffff"))
        
        if is_hover:
            # 悬停状态：更亮
            self.setBrush(QBrush(color.lighter(150)))
            self.setPen(QPen(color.lighter(200), 3))
        else:
            # 普通状态
            self.setBrush(QBrush(color))
            self.setPen(QPen(color.lighter(120), 2))
    
    def update_position(self):
        """更新接口位置"""
        if not self.parent_node:
            return
        
        node_rect = self.parent_node.rect()
        node_width = node_rect.width()
        node_height = node_rect.height()
        
        # 标题栏高度
        header_height = 40
        
        # ⭐ 检测节点是否处于折叠状态（高度小于80px认为是折叠状态）
        is_collapsed = node_height < 80
        
        if is_collapsed:
            # 折叠状态：将连接点固定在标题栏的垂直中间位置
            y_pos = header_height / 2
        else:
            # 展开状态：根据节点高度和接口数量自动计算垂直位置
            # 如果是输入接口，使用input_sockets列表；如果是输出接口，使用output_sockets列表
            if self.socket_type == SocketType.INPUT:
                total_sockets = len(self.parent_node.input_sockets)
            else:
                total_sockets = len(self.parent_node.output_sockets)
            
            # 可用垂直空间
            available_height = node_height - header_height - 20  # 留20px底部边距
            
            # 计算垂直位置（均匀分布）
            if total_sockets > 1:
                spacing = available_height / (total_sockets + 1)
                y_pos = header_height + spacing * (self.index + 1)
            else:
                # 只有一个接口时，居中显示
                y_pos = header_height + available_height / 2
        
        if self.socket_type == SocketType.INPUT:
            # 输入接口在左侧边缘
            x_pos = 0
        else:
            # 输出接口在右侧边缘
            x_pos = node_width
        
        self.setPos(x_pos, y_pos)
    
    def get_center_pos(self):
        """获取接口中心的场景坐标"""
        center = self.boundingRect().center()
        return self.mapToScene(center)
    
    def can_connect_to(self, other_socket):
        """检查是否可以连接到另一个接口"""
        if not other_socket or other_socket == self:
            return False
        
        # 不能连接到同一个节点
        if other_socket.parent_node == self.parent_node:
            return False
        
        # 必须是不同类型（输入<->输出）
        if other_socket.socket_type == self.socket_type:
            return False
        
        # 允许任意类型之间连接
        # 数据类型主要用于视觉区分，不限制连接
        # 这样图片可以连视频，文字可以连图片等
        return True
    
    def add_connection(self, connection):
        """添加连接"""
        if connection not in self.connections:
            self.connections.append(connection)
            
            # 通知父节点连接已建立
            if hasattr(self.parent_node, 'on_socket_connected'):
                self.parent_node.on_socket_connected(self, connection)
    
    def remove_connection(self, connection):
        """移除连接"""
        if connection in self.connections:
            self.connections.remove(connection)
            
            # 通知父节点连接已断开
            if hasattr(self.parent_node, 'on_socket_disconnected'):
                self.parent_node.on_socket_disconnected(self, connection)
    
    def hoverEnterEvent(self, event):
        """鼠标悬停进入"""
        self.update_style(is_hover=True)
        super().hoverEnterEvent(event)
    
    def hoverLeaveEvent(self, event):
        """鼠标悬停离开"""
        self.update_style(is_hover=False)
        super().hoverLeaveEvent(event)


# ==================== 连接线类 ====================
class Connection(QGraphicsPathItem):
    """节点之间的连接线 - 贝塞尔曲线"""
    
    def __init__(self, source_socket, target_socket=None, scene=None):
        """
        初始化连接线
        
        Args:
            source_socket: 起始接口
            target_socket: 目标接口（可选，拖拽时为None）
            scene: 图形场景
        """
        super().__init__()
        
        self.source_socket = source_socket
        self.target_socket = target_socket
        self.graphics_scene = scene
        
        # 临时终点（拖拽时使用）
        self.temp_end_pos = None
        
        # 样式设置
        self.update_style()
        
        # 设置z值，在网格之上，节点之下
        self.setZValue(50)  # 网格是-1000和-999，节点是0，Socket是100
        
        # 设置标志
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        
        # 添加到场景
        if scene:
            scene.addItem(self)
        
        # 注册到接口
        if source_socket:
            source_socket.add_connection(self)
        if target_socket:
            target_socket.add_connection(self)
        
        # 初始绘制
        self.update_path()
    
    def update_style(self, is_selected=False):
        """更新连接线样式"""
        # 根据数据类型确定颜色
        if self.source_socket:
            color = QColor(DATA_TYPE_COLORS.get(self.source_socket.data_type, "#ffffff"))
        else:
            color = QColor("#ffffff")
        
        if is_selected:
            # 选中状态：更粗更亮
            self.setPen(QPen(color.lighter(150), 5, Qt.PenStyle.SolidLine))
        else:
            # 普通状态：加粗加亮以确保可见
            self.setPen(QPen(color.lighter(120), 4, Qt.PenStyle.SolidLine))
    
    def update_path(self):
        """更新连接线路径（贝塞尔曲线）"""
        if not self.source_socket:
            return
        
        # 起点
        start_pos = self.source_socket.get_center_pos()
        
        # 终点
        if self.target_socket:
            end_pos = self.target_socket.get_center_pos()
        elif self.temp_end_pos:
            end_pos = self.temp_end_pos
        else:
            end_pos = start_pos
        
        # 创建贝塞尔曲线路径
        path = QPainterPath()
        path.moveTo(start_pos)
        
        # 计算控制点
        dx = abs(end_pos.x() - start_pos.x())
        offset = min(dx * 0.5, 200)  # 曲线弯曲程度
        
        ctrl1 = QPointF(start_pos.x() + offset, start_pos.y())
        ctrl2 = QPointF(end_pos.x() - offset, end_pos.y())
        
        # 绘制三次贝塞尔曲线
        path.cubicTo(ctrl1, ctrl2, end_pos)
        
        self.setPath(path)
    
    def set_temp_end_pos(self, pos):
        """设置临时终点（拖拽时）"""
        self.temp_end_pos = pos
        self.update_path()
    
    def set_target_socket(self, socket):
        """设置目标接口"""
        # 移除旧连接
        if self.target_socket:
            self.target_socket.remove_connection(self)
        
        # 设置新连接
        self.target_socket = socket
        if socket:
            socket.add_connection(self)
            
            # Notify source node that connection is now complete
            if self.source_socket and hasattr(self.source_socket.parent_node, 'on_socket_connected'):
                 self.source_socket.parent_node.on_socket_connected(self.source_socket, self)
        
        self.update_path()
    
    def remove(self):
        """移除连接"""
        # 从接口中移除
        if self.source_socket:
            self.source_socket.remove_connection(self)
        if self.target_socket:
            self.target_socket.remove_connection(self)
        
        # 从场景中移除
        if self.graphics_scene:
            self.graphics_scene.removeItem(self)
    
    def itemChange(self, change, value):
        """项目变化事件"""
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            self.update_style(is_selected=value)
            
        # 防止 QGraphicsItem::ungrabMouse 错误
        if change == QGraphicsItem.GraphicsItemChange.ItemSceneChange:
            if value is None and self.scene():
                grabber = self.scene().mouseGrabberItem()
                if grabber and (grabber == self or self.isAncestorOf(grabber)):
                    grabber.ungrabMouse()
                    
        return super().itemChange(change, value)


# ==================== 连接管理器 ====================
class ConnectionManager(QObject):
    """连接管理器 - 处理连接创建、拖拽、验证"""
    
    # 信号
    connection_created = Signal(object)  # 连接创建
    connection_removed = Signal(object)  # 连接移除
    
    def __init__(self, scene):
        super().__init__()
        self.scene = scene
        
        # 当前正在拖拽的连接
        self.dragging_connection = None
        self.drag_start_socket = None
    
    def start_dragging(self, socket, mouse_pos):
        """开始拖拽连接"""
        if not socket:
            return
        
        # 允许输入接口有多个连接，不再移除旧连接
        # if socket.socket_type == SocketType.INPUT and socket.connections:
        #     for conn in socket.connections[:]:  # 复制列表避免修改时出错
        #         conn.remove()
        #         self.connection_removed.emit(conn)
        
        # 创建临时连接
        self.drag_start_socket = socket
        self.dragging_connection = Connection(socket, None, self.scene)
        self.dragging_connection.set_temp_end_pos(mouse_pos)
    
    def update_dragging(self, mouse_pos):
        """更新拖拽位置"""
        if self.dragging_connection:
            self.dragging_connection.set_temp_end_pos(mouse_pos)
    
    def end_dragging(self, target_socket):
        """结束拖拽"""
        if not self.dragging_connection:
            return
        
        success = False
        
        # 检查是否可以连接
        if target_socket and self.drag_start_socket.can_connect_to(target_socket):
            # 允许输入接口有多个连接，不再移除旧连接
            # if target_socket.socket_type == SocketType.INPUT and target_socket.connections:
            #     for conn in target_socket.connections[:]:
            #         conn.remove()
            #         self.connection_removed.emit(conn)
            
            # 完成连接
            self.dragging_connection.set_target_socket(target_socket)
            
            # 确保连接方向正确 (Output -> Input)
            # 如果是从 Input 拖到 Output，则交换源和目标
            if self.dragging_connection.source_socket.socket_type == SocketType.INPUT:
                # 交换源和目标
                real_source = target_socket
                real_target = self.dragging_connection.source_socket
                
                self.dragging_connection.source_socket = real_source
                self.dragging_connection.target_socket = real_target
                
                # 重新更新路径
                self.dragging_connection.update_path()
            
            self.connection_created.emit(self.dragging_connection)
            success = True
        
        # 如果连接失败，移除临时连接
        if not success:
            self.dragging_connection.remove()
        
        # 清理状态
        self.dragging_connection = None
        self.drag_start_socket = None
    
    def remove_connection(self, connection):
        """移除指定连接"""
        if connection:
            connection.remove()
            self.connection_removed.emit(connection)
    
    def get_all_connections(self):
        """获取所有连接"""
        connections = []
        for item in self.scene.items():
            if isinstance(item, Connection):
                connections.append(item)
        return connections
    
    def clear_all_connections(self):
        """清除所有连接"""
        for conn in self.get_all_connections()[:]:
            self.remove_connection(conn)


# ==================== 可连接节点基类 ====================
class ConnectableNode:
    """可连接节点混入类 - 为节点添加接口功能"""
    
    def __init__(self):
        """初始化可连接节点"""
        self.input_sockets = []   # 输入接口列表
        self.output_sockets = []  # 输出接口列表
    
    def add_input_socket(self, data_type, label=""):
        """添加输入接口"""
        index = len(self.input_sockets)
        socket = Socket(self, SocketType.INPUT, data_type, index, label)
        self.input_sockets.append(socket)
        return socket
    
    def add_output_socket(self, data_type, label=""):
        """添加输出接口"""
        index = len(self.output_sockets)
        socket = Socket(self, SocketType.OUTPUT, data_type, index, label)
        self.output_sockets.append(socket)
        return socket
    
    def get_socket_at_pos(self, pos):
        """获取指定位置的接口"""
        for socket in self.input_sockets + self.output_sockets:
            if socket.contains(socket.mapFromScene(pos)):
                return socket
        return None
    
    def update_socket_positions(self):
        """更新所有接口位置"""
        for socket in self.input_sockets + self.output_sockets:
            socket.update_position()
    
    def update_connections(self):
        """更新所有连接线"""
        for socket in self.input_sockets + self.output_sockets:
            for connection in socket.connections:
                connection.update_path()
    
    def get_input_data(self, socket_index):
        """获取输入接口的数据"""
        if socket_index >= len(self.input_sockets):
            return None
        
        socket = self.input_sockets[socket_index]
        if not socket.connections:
            return None
        
        # 获取连接的源节点
        connection = socket.connections[0]
        source_node = connection.source_socket.parent_node
        
        # 如果源节点有输出方法，调用它
        if hasattr(source_node, 'get_output_data'):
            source_index = connection.source_socket.index
            return source_node.get_output_data(source_index)
        
        return None
    
    def get_output_data(self, socket_index):
        """获取输出数据（子类覆盖）"""
        return None
    
    def itemChange(self, change, value):
        """节点变化时更新连接"""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.update_connections()
            
        # 防止 QGraphicsItem::ungrabMouse 错误
        if change == QGraphicsItem.GraphicsItemChange.ItemSceneChange:
            if value is None and self.scene():
                grabber = self.scene().mouseGrabberItem()
                if grabber and (grabber == self or self.isAncestorOf(grabber)):
                    grabber.ungrabMouse()
                    
        return super().itemChange(change, value)


# ==================== 示例：可连接文本节点 ====================
def create_example_text_node(x, y):
    """创建示例文本节点（带连接功能）"""
    from lingdong import CanvasNode
    
    class ConnectableTextNode(ConnectableNode, CanvasNode):
        def __init__(self, x, y):
            CanvasNode.__init__(self, x, y, 250, 200, "文本节点", "")
            ConnectableNode.__init__(self)
            
            # 添加接口
            self.add_input_socket(DataType.TEXT, "输入文本")
            self.add_output_socket(DataType.TEXT, "输出文本")
            
            self.text_content = ""
        
        def get_output_data(self, socket_index):
            """返回文本内容"""
            return self.text_content
    
    return ConnectableTextNode(x, y)
