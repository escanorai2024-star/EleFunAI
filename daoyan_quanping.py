
import sys
import os
import json
from PySide6.QtWidgets import (
    QGraphicsProxyWidget, QWidget, QVBoxLayout, 
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QHBoxLayout, QGraphicsItem, QStyledItemDelegate,
    QGraphicsPixmapItem, QMessageBox, QMenu, QFileDialog, QApplication, QDialog
)
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QPoint, QSettings, QMimeData, QUrl, QEvent, QThread, Signal
from daoyan_fenjingtu import StoryboardDialog, StoryboardWorker, ImageViewerDialog
from daoyan_sora2 import Sora2Worker
from daoyan_fujia_tishici import get_additional_prompt, open_additional_prompt_dialog
from daoyan_tupianfujiatishici import open_additional_image_prompt_dialog
from PySide6.QtGui import QColor, QBrush, QPen, QPixmap, QPolygonF, QPainter, QCursor, QDrag
from textEDITgoogle import open_edit_dialog_for_item, TextEditDialog
from lingdongconnect import DataType, SocketType
from sora_jiaoseku import CreateCharacterThread, save_character

class DirectorNode:
    """导演节点工厂类"""
    
    @staticmethod
    def create_node(CanvasNode):
        """动态创建DirectorNode类，继承自CanvasNode"""
        
        class DragLabel(QLabel):
            def __init__(self, text, parent=None, video_path=""):
                super().__init__(text, parent)
                self.video_path = video_path
                # 移除拖拽光标
                # self.setCursor(Qt.OpenHandCursor)


        class DraggableVideoWidget(QWidget):
            def __init__(self, video_path, parent=None):
                super().__init__(parent)
                self.video_path = video_path
                self.drag_start_position = None
                self.setup_ui()

            def setup_ui(self):
                layout = QHBoxLayout(self)
                layout.setContentsMargins(5, 5, 5, 5)
                
                # Play button
                self.btn = QPushButton("▶️")
                self.btn.setCursor(Qt.PointingHandCursor)
                self.btn.setFixedSize(30, 30)
                self.btn.setStyleSheet("background-color: transparent; color: black; border-radius: 4px; border: none; font-size: 16px;")
                self.btn.clicked.connect(lambda: os.startfile(self.video_path))
                
                # Drag handle label
                self.drag_label = DragLabel("✊", self, self.video_path) 
                self.drag_label.setToolTip("视频")
                self.drag_label.setStyleSheet("color: #666; font-size: 14px;")
                
                layout.addWidget(self.btn)
                layout.addWidget(self.drag_label)
                layout.addStretch()
                
                # Make sure mouse events are caught
                self.setAttribute(Qt.WA_StyledBackground, True)
                self.setAutoFillBackground(True)
                self.setStyleSheet("background-color: #ffffff;")

            # 移除拖拽事件
            # def mousePressEvent(self, event):
            #     pass

            # def mouseMoveEvent(self, event):
            #     pass

        class ImageDelegate(QStyledItemDelegate):
            """自定义图片代理，用于在单元格中绘制多张图片"""
            def __init__(self, parent=None, node=None):
                super().__init__(parent)
                self.node = node
                self.cache = {} # path -> QPixmap
                self.press_pos = None  # 记录鼠标按下位置，用于区分点击和拖拽

            def paint(self, painter, option, index):
                # 绘制默认背景 (选中状态等)
                super().paint(painter, option, index)
                
                if index.column() == 7:
                    self.paint_storyboard(painter, option, index)
                else:
                    self.paint_generic(painter, option, index)

            def paint_generic(self, painter, option, index):
                image_paths = index.data(Qt.UserRole)
                if not image_paths or not isinstance(image_paths, list):
                    return

                rect = option.rect
                # 内边距
                rect.adjust(5, 5, -5, -5)
                
                available_height = rect.height()
                available_width = rect.width()
                
                count = len(image_paths)
                if count == 0:
                    return
                    
                # 计算每张图片的宽度
                # 保持间距
                spacing = 4
                item_width = (available_width - (count - 1) * spacing) // count
                if item_width < 10: item_width = 10 # 最小宽度
                
                painter.save()
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setRenderHint(QPainter.SmoothPixmapTransform)
                
                current_x = rect.left()
                
                for path in image_paths:
                    if path not in self.cache:
                        self.cache[path] = QPixmap(path)
                    
                    pixmap = self.cache[path]
                    if pixmap.isNull():
                        continue
                        
                    # 目标区域
                    target_rect = QRectF(current_x, rect.top(), item_width, available_height)
                    
                    # 缩放图片以适应目标区域 (保持比例)
                    scaled = pixmap.scaled(target_rect.size().toSize(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    
                    # 居中绘制
                    draw_x = target_rect.x() + (target_rect.width() - scaled.width()) / 2
                    draw_y = target_rect.y() + (target_rect.height() - scaled.height()) / 2
                    
                    painter.drawPixmap(int(draw_x), int(draw_y), scaled)
                    
                    current_x += item_width + spacing
                    
                painter.restore()

            def paint_storyboard(self, painter, option, index):
                image_paths = index.data(Qt.UserRole)
                p1, p2 = None, None
                
                if image_paths and isinstance(image_paths, list):
                    if len(image_paths) > 0: p1 = image_paths[0]
                    if len(image_paths) > 1: p2 = image_paths[1]
                
                rect = option.rect
                rect.adjust(5, 5, -5, -5)
                
                available_width = rect.width()
                available_height = rect.height()
                
                # Check visibility state
                show_tail = True
                if self.node and hasattr(self.node, 'show_tail_frame'):
                    show_tail = self.node.show_tail_frame
                
                painter.save()
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setRenderHint(QPainter.SmoothPixmapTransform)
                
                if show_tail:
                    spacing = 4
                    slot_width = (available_width - spacing) // 2
                    if slot_width < 10: slot_width = 10
                    
                    # Slot 1 (Left)
                    rect1 = QRectF(rect.left(), rect.top(), slot_width, available_height)
                    self.draw_slot(painter, rect1, p1)
                    
                    # Slot 2 (Right)
                    rect2 = QRectF(rect.left() + slot_width + spacing, rect.top(), slot_width, available_height)
                    self.draw_slot(painter, rect2, p2)
                else:
                    # Only Slot 1 (Full Width)
                    rect1 = QRectF(rect.left(), rect.top(), available_width, available_height)
                    self.draw_slot(painter, rect1, p1)
                
                painter.restore()

            def draw_slot(self, painter, rect, path):
                if path and os.path.exists(path):
                    if path not in self.cache:
                        self.cache[path] = QPixmap(path)
                    pixmap = self.cache[path]
                    if not pixmap.isNull():
                         scaled = pixmap.scaled(rect.size().toSize(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                         draw_x = rect.x() + (rect.width() - scaled.width()) / 2
                         draw_y = rect.y() + (rect.height() - scaled.height()) / 2
                         painter.drawPixmap(int(draw_x), int(draw_y), scaled)
                         return

                # Draw + button
                painter.setPen(QPen(QColor("#BDBDBD"), 1, Qt.DashLine))
                painter.setBrush(QBrush(QColor("#F5F5F5")))
                painter.drawRoundedRect(rect, 4, 4)
                
                painter.setPen(QPen(QColor("#757575"), 2))
                center = rect.center()
                painter.drawLine(QPointF(center.x() - 8, center.y()), QPointF(center.x() + 8, center.y()))
                painter.drawLine(QPointF(center.x(), center.y() - 8), QPointF(center.x(), center.y() + 8))

            def editorEvent(self, event, model, option, index):
                # 记录鼠标按下位置
                if index.column() == 7 and event.type() == QEvent.MouseButtonPress:
                    if hasattr(event, 'button') and event.button() == Qt.LeftButton:
                        self.press_pos = event.pos()
                
                # 只处理左键点击，让右键事件传递给右键菜单
                if index.column() == 7 and event.type() == QEvent.MouseButtonRelease:
                    # 检查是否是右键，如果是右键则不拦截，让右键菜单显示
                    if hasattr(event, 'button') and event.button() == Qt.RightButton:
                        return super().editorEvent(event, model, option, index)
                    
                    # 只处理左键点击上传功能
                    if hasattr(event, 'button') and event.button() == Qt.LeftButton:
                        # 检查是否是拖拽（如果鼠标移动距离超过阈值，则认为是拖拽而非点击）
                        if self.press_pos is not None:
                            move_distance = (event.pos() - self.press_pos).manhattanLength()
                            if move_distance >= QApplication.startDragDistance():
                                # 这是拖拽操作，不触发上传，让拖拽继续
                                self.press_pos = None
                                return super().editorEvent(event, model, option, index)
                        
                        # 这是点击操作，触发上传
                        if self.node:
                            # Check visibility
                            show_tail = True
                            if hasattr(self.node, 'show_tail_frame'):
                                show_tail = self.node.show_tail_frame
                            
                            slot_index = 0
                            if show_tail:
                                rect = option.rect
                                rect.adjust(5, 5, -5, -5)
                                local_x = event.pos().x() - rect.left()
                                width = rect.width()
                                slot_index = 0 if local_x < width / 2 else 1
                            else:
                                slot_index = 0
                                
                            self.node.upload_storyboard_image(index.row(), slot_index)
                            self.press_pos = None
                            return True
                
                return super().editorEvent(event, model, option, index)

        class HoverTableWidget(QTableWidget):
            """支持鼠标悬停检测的表格"""
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setMouseTracking(True) # 开启鼠标追踪
                self.hover_callback = None # func(path, pos)
                self.drag_start_pos = None # 记录拖拽起点
                
            def mousePressEvent(self, event):
                if event.button() == Qt.MouseButton.LeftButton:
                    self.drag_start_pos = event.pos()
                    if self.hover_callback:
                        item = self.itemAt(event.pos())
                        if not item:
                            self.hover_callback(None, event.pos())
                        else:
                            col = item.column()
                            if col in [4, 5, 6, 7]:
                                image_paths = item.data(Qt.UserRole)
                                if image_paths and isinstance(image_paths, list) and image_paths:
                                    rect = self.visualItemRect(item)
                                    rect.adjust(5, 5, -5, -5)
                                    local_x = event.pos().x() - rect.left()
                                    count = len(image_paths)
                                    spacing = 4
                                    available_width = rect.width()
                                    item_width = (available_width - (count - 1) * spacing) // count
                                    if item_width < 10:
                                        item_width = 10
                                    index = int(local_x / (item_width + spacing))
                                    if 0 <= index < count:
                                        path = image_paths[index]
                                        self.hover_callback(path, event.pos())
                                    else:
                                        self.hover_callback(None, event.pos())
                            else:
                                self.hover_callback(None, event.pos())
                else:
                    if self.hover_callback:
                        self.hover_callback(None, event.pos())
                super().mousePressEvent(event)

            def mouseMoveEvent(self, event):
                # 处理拖拽逻辑
                if self.drag_start_pos and (event.buttons() & Qt.MouseButton.LeftButton):
                    if (event.pos() - self.drag_start_pos).manhattanLength() >= QApplication.startDragDistance():
                        self.start_drag(event)
                        self.drag_start_pos = None # 重置
                        return

                super().mouseMoveEvent(event)

            def start_drag(self, event):
                """开始拖拽操作"""
                if not self.drag_start_pos:
                    return
                    
                item = self.itemAt(self.drag_start_pos)
                if not item: return
                
                col = item.column()
                # 4:人物, 5:道具, 6:场景, 7:分镜图
                if col not in [4, 5, 6, 7]: return
                
                image_paths = item.data(Qt.UserRole)
                if not image_paths or not isinstance(image_paths, list) or not image_paths:
                    return

                # 计算点击的是哪张图片
                rect = self.visualItemRect(item)
                rect.adjust(5, 5, -5, -5)
                local_x = self.drag_start_pos.x() - rect.left()
                
                count = len(image_paths)
                spacing = 4
                available_width = rect.width()
                item_width = (available_width - (count - 1) * spacing) // count
                if item_width < 10: item_width = 10
                
                index = int(local_x / (item_width + spacing))
                
                if 0 <= index < count:
                    image_path = image_paths[index]
                    
                    drag = QDrag(self)
                    mime_data = QMimeData()
                    url = QUrl.fromLocalFile(image_path)
                    mime_data.setUrls([url])
                    drag.setMimeData(mime_data)
                    
                    # 设置拖拽预览图
                    pixmap = QPixmap(image_path)
                    if not pixmap.isNull():
                         # 缩放到合理大小作为拖拽图标
                         preview = pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                         drag.setPixmap(preview)
                         drag.setHotSpot(QPoint(preview.width() // 2, preview.height() // 2))
                    
                    drag.exec_(Qt.DropAction.CopyAction)

            def leaveEvent(self, event):
                super().leaveEvent(event)
                if self.hover_callback:
                    self.hover_callback(None, QPoint(0,0))

        class DirectorResizeHandle(QGraphicsItem):
            """自定义导演节点缩放手柄 (紫色三角形)"""
            def __init__(self, parent):
                super().__init__(parent)
                self.setParentItem(parent)
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
                self.setAcceptHoverEvents(True)
                self.parent_node = parent
                self.setZValue(1000) # 确保在最上层 (高于 proxy_widget)
                self.handle_size = 20
                self.update_position()

            def boundingRect(self):
                return QRectF(0, 0, self.handle_size, self.handle_size)

            def paint(self, painter, option, widget):
                if hasattr(self.parent_node, 'is_collapsed') and self.parent_node.is_collapsed:
                    return
                    
                # 绘制紫色三角形
                painter.setPen(QPen(QColor("#AB47BC"), 2))
                painter.setBrush(QBrush(QColor("#AB47BC")))
                
                # 绘制在右下角
                points = [
                    QPointF(self.handle_size - 15, self.handle_size),
                    QPointF(self.handle_size, self.handle_size - 15),
                    QPointF(self.handle_size, self.handle_size)
                ]
                painter.drawPolygon(QPolygonF(points))

            def mousePressEvent(self, event):
                self.start_pos = event.scenePos()
                self.start_rect = self.parent_node.rect()
                event.accept()

            def mouseMoveEvent(self, event):
                diff = event.scenePos() - self.start_pos
                new_width = max(300, self.start_rect.width() + diff.x())
                new_height = max(200, self.start_rect.height() + diff.y())
                
                self.parent_node.setRect(0, 0, new_width, new_height)
                if hasattr(self.parent_node, 'expanded_height'):
                    self.parent_node.expanded_height = new_height
                
                self.update_position()
                
            def update_position(self):
                rect = self.parent_node.rect()
                self.setPos(rect.width() - self.handle_size, rect.height() - self.handle_size)

        class DirectorNodeImpl(CanvasNode):
            def _auto_create_sockets(self):
                """Override to prevent default sockets creation"""
                pass

            def __init__(self, x, y):
                # 节点初始化: x, y, width, height, title, icon
                # Icon can be None or a custom SVG path
                super().__init__(x, y, 500, 400, "导演节点", None)
                
                # 设置背景色 - 紫色系
                self.setBrush(QBrush(QColor("#F3E5F5")))
                self.setPen(QPen(QColor("#673AB7"), 1.5))
                
                # 替换默认的 ResizeHandle
                if hasattr(self, 'resize_handle'):
                    # 移除旧的 handle
                    if self.resize_handle.scene():
                        self.resize_handle.scene().removeItem(self.resize_handle)
                    self.resize_handle.setParentItem(None)
                
                # 使用自定义的 DirectorResizeHandle
                self.resize_handle = DirectorResizeHandle(self)
                
                # 状态变量：是否显示尾帧图 (默认显示)
                self.show_tail_frame = False
                self._ai_prompt_running = False
                
                # 添加输入接口 (左侧) - 接收剧本数据
                # 对应 GoogleScriptNode 的 add_output_socket(4, "剧本数据")
                # 使用相同的 data_type=4 以匹配
                if hasattr(self, 'add_input_socket'):
                    # data_type=4 ("剧本数据")
                    self.add_input_socket(4, "剧本数据")
                    # 添加清理节点输入接口
                    self.add_input_socket(DataType.ANY, "清理/过滤")

                # 添加视频输出接口
                if hasattr(self, 'add_output_socket'):
                    self.add_output_socket(DataType.VIDEO, "视频输出")
                
                # 界面初始化
                self.setup_ui()
                # 初始调用 setRect 以应用行高计算
                self.setRect(self.rect())
                
                # 定时刷新数据
                self.timer = QTimer()
                self.timer.timeout.connect(self.update_data)
                self.timer.start(1000) # 每秒刷新一次
                
                # 加载分镜图路径缓存
                self.storyboard_paths = self.load_storyboard_paths()
                # 加载道具路径缓存
                self.props_paths = self.load_props_paths()
                # 加载道具提示词缓存
                self.props_prompts = self.load_props_prompts()
                # 加载图片提示词缓存
                self.image_prompts = self.load_image_prompts()
                # 加载人物图片路径缓存
                self.character_paths = self.load_character_paths()
                # 加载视频路径缓存
                self.video_paths = self.load_video_paths()
                # 加载视频元数据缓存
                self.video_metadata = self.load_video_metadata()
                
                # 视频生成 Workers 列表 (支持并发)
                self.sora_workers = []
                
            def on_socket_connected(self, socket, connection):
                """当接口连接时触发"""
                print(f"[DEBUG] DirectorNode.on_socket_connected triggered")
                
                # Check if connection is fully established
                if not connection.source_socket or not connection.target_socket:
                    print(f"[DEBUG] Connection incomplete (waiting for target/source)...")
                    return

                # Identify the other node
                other_socket = connection.target_socket if connection.source_socket == socket else connection.source_socket
                target_node = other_socket.parent_node
                print(f"[DEBUG] Connected to: {type(target_node).__name__}")

                # 只有当视频输出接口连接时才处理
                if socket.data_type == DataType.VIDEO and socket.socket_type == SocketType.OUTPUT:
                    print(f"[DEBUG] Video output socket connected.")
                    print(f"[DEBUG] Director Node will NOT send data. Video Editor Node should read JSON directly.")
                    # 彻底移除此处的数据加载和发送逻辑，完全由接收端处理

            def load_storyboard_paths(self):
                """加载分镜图路径缓存"""
                try:
                    path = os.path.join(os.getcwd(), 'JSON', 'daoyan_fenjing_paths.json')
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            return json.load(f)
                except Exception as e:
                    print(f"Error loading storyboard paths: {e}")
                return {}

            def save_storyboard_paths(self):
                """保存分镜图路径缓存"""
                try:
                    dir_path = os.path.join(os.getcwd(), 'JSON')
                    os.makedirs(dir_path, exist_ok=True)
                    path = os.path.join(dir_path, 'daoyan_fenjing_paths.json')
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(self.storyboard_paths, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"Error saving storyboard paths: {e}")

            def load_props_paths(self):
                """加载道具图片路径缓存"""
                try:
                    path = os.path.join(os.getcwd(), 'JSON', 'daoyan_props_paths.json')
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            return json.load(f)
                except Exception as e:
                    print(f"Error loading props paths: {e}")
                return {}

            def save_props_paths(self):
                """保存道具图片路径缓存"""
                try:
                    dir_path = os.path.join(os.getcwd(), 'JSON')
                    os.makedirs(dir_path, exist_ok=True)
                    path = os.path.join(dir_path, 'daoyan_props_paths.json')
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(self.props_paths, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"Error saving props paths: {e}")

            def load_props_prompts(self):
                """加载道具提示词缓存"""
                try:
                    path = os.path.join(os.getcwd(), 'JSON', 'daoyan_props_prompts.json')
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            return json.load(f)
                except Exception as e:
                    print(f"Error loading props prompts: {e}")
                return {}

            def save_props_prompts(self):
                """保存道具提示词缓存"""
                try:
                    dir_path = os.path.join(os.getcwd(), 'JSON')
                    os.makedirs(dir_path, exist_ok=True)
                    path = os.path.join(dir_path, 'daoyan_props_prompts.json')
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(self.props_prompts, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"Error saving props prompts: {e}")

            def load_image_prompts(self):
                """加载图片提示词缓存"""
                try:
                    path = os.path.join(os.getcwd(), 'JSON', 'daoyan_image_prompts.json')
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            return json.load(f)
                except Exception as e:
                    print(f"Error loading image prompts: {e}")
                return {}

            def save_image_prompts(self):
                """保存图片提示词缓存"""
                try:
                    dir_path = os.path.join(os.getcwd(), 'JSON')
                    os.makedirs(dir_path, exist_ok=True)
                    path = os.path.join(dir_path, 'daoyan_image_prompts.json')
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(self.image_prompts, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"Error saving image prompts: {e}")

            def load_character_paths(self):
                """加载人物图片路径缓存"""
                try:
                    path = os.path.join(os.getcwd(), 'JSON', 'daoyan_character_paths.json')
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            return json.load(f)
                except Exception as e:
                    print(f"Error loading character paths: {e}")
                return {}

            def save_character_paths(self):
                """保存人物图片路径缓存"""
                try:
                    dir_path = os.path.join(os.getcwd(), 'JSON')
                    os.makedirs(dir_path, exist_ok=True)
                    path = os.path.join(dir_path, 'daoyan_character_paths.json')
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(self.character_paths, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"Error saving character paths: {e}")

            def load_video_paths(self):
                """加载视频路径缓存"""
                try:
                    path = os.path.join(os.getcwd(), 'JSON', 'daoyan_TV_VIDEO_SAVE.JSON')
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            print(f"[DEBUG] Loaded {len(data)} video paths from {path}")
                            return data
                except Exception as e:
                    print(f"Error loading video paths: {e}")
                return {}

            def save_video_paths(self):
                """保存视频路径缓存"""
                try:
                    dir_path = os.path.join(os.getcwd(), 'JSON')
                    print(f"[DEBUG] Saving video paths to dir: {dir_path}")
                    os.makedirs(dir_path, exist_ok=True)
                    path = os.path.join(dir_path, 'daoyan_TV_VIDEO_SAVE.JSON')
                    print(f"[DEBUG] Full save path: {path}")
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(self.video_paths, f, ensure_ascii=False, indent=2)
                    print(f"[DEBUG] Successfully saved {len(self.video_paths)} entries to {path}")
                except Exception as e:
                    print(f"Error saving video paths: {e}")

            def load_video_metadata(self):
                """加载视频元数据(URL, TaskID)"""
                try:
                    path = os.path.join(os.getcwd(), 'JSON', 'daoyan_TV_VIDEO_METADATA.JSON')
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            return json.load(f)
                except Exception as e:
                    print(f"Error loading video metadata: {e}")
                return {}

            def save_video_metadata(self):
                """保存视频元数据"""
                try:
                    dir_path = os.path.join(os.getcwd(), 'JSON')
                    os.makedirs(dir_path, exist_ok=True)
                    path = os.path.join(dir_path, 'daoyan_TV_VIDEO_METADATA.JSON')
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(self.video_metadata, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"Error saving video metadata: {e}")

            def setup_ui(self):
                """设置节点内部UI"""
                self.proxy_widget = QGraphicsProxyWidget(self)
                self.proxy_widget.setZValue(10)
                
                self.container = QWidget()
                self.container.setStyleSheet("background-color: transparent;")
                self.layout = QVBoxLayout(self.container)
                self.layout.setContentsMargins(10, 45, 10, 10)
                
                # 动漫按钮
                self.anime_btn = QPushButton("📺 动画片场", self.container)
                self.anime_btn.setFixedSize(100, 24)
                self.anime_btn.setCursor(Qt.PointingHandCursor)
                self.anime_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #AB47BC;
                        color: white;
                        border-radius: 4px;
                        font-weight: bold;
                        border: none;
                        font-family: "Microsoft YaHei";
                    }
                    QPushButton:hover {
                        background-color: #BA68C8;
                    }
                    QPushButton:pressed {
                        background-color: #9C27B0;
                    }
                """)
                self.anime_btn.clicked.connect(self.toggle_anime_column)
                
                # 分镜图按钮
                self.storyboard_btn = QPushButton("🎬 产生分镜图", self.container)
                self.storyboard_btn.setFixedSize(100, 24)
                self.storyboard_btn.setCursor(Qt.PointingHandCursor)
                self.storyboard_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #FF9800;
                        color: white;
                        border-radius: 4px;
                        font-weight: bold;
                        border: none;
                        font-family: "Microsoft YaHei";
                    }
                    QPushButton:hover {
                        background-color: #FFB74D;
                    }
                    QPushButton:pressed {
                        background-color: #F57C00;
                    }
                """)
                self.storyboard_btn.clicked.connect(self.open_storyboard_dialog)
                
                # Sora2 按钮
                self.sora_btn = QPushButton("SORA2", self.container)
                self.sora_btn.setFixedSize(100, 24)
                self.sora_btn.setCursor(Qt.PointingHandCursor)
                self.sora_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #673AB7;
                        color: white;
                        border-radius: 4px;
                        font-weight: bold;
                        border: none;
                        font-family: "Microsoft YaHei";
                    }
                    QPushButton:hover {
                        background-color: #7E57C2;
                    }
                    QPushButton:pressed {
                        background-color: #512DA8;
                    }
                """)
                self.sora_btn.clicked.connect(self.on_sora2_clicked)

                # 附加提示词按钮 (改为 附加视频提示词)
                self.add_prompt_btn = QPushButton("➕ 附加视频提示词", self.container)
                self.add_prompt_btn.setFixedSize(130, 24)
                self.add_prompt_btn.setCursor(Qt.PointingHandCursor)
                self.add_prompt_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #009688;
                        color: white;
                        border-radius: 4px;
                        font-weight: bold;
                        border: none;
                        font-family: "Microsoft YaHei";
                    }
                    QPushButton:hover {
                        background-color: #26A69A;
                    }
                    QPushButton:pressed {
                        background-color: #00796B;
                    }
                """)
                self.add_prompt_btn.clicked.connect(lambda: open_additional_prompt_dialog(None))

                # 附加图片提示词按钮
                self.add_image_prompt_btn = QPushButton("➕ 附加图片提示词", self.container)
                self.add_image_prompt_btn.setFixedSize(130, 24)
                self.add_image_prompt_btn.setCursor(Qt.PointingHandCursor)
                self.add_image_prompt_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #8BC34A;
                        color: white;
                        border-radius: 4px;
                        font-weight: bold;
                        border: none;
                        font-family: "Microsoft YaHei";
                    }
                    QPushButton:hover {
                        background-color: #9CCC65;
                    }
                    QPushButton:pressed {
                        background-color: #7CB342;
                    }
                """)
                self.add_image_prompt_btn.clicked.connect(lambda: open_additional_image_prompt_dialog(None))

                # 全屏按钮
                self.fullscreen_btn = QPushButton("📺 全屏", self.container)
                self.fullscreen_btn.setFixedSize(100, 24)
                self.fullscreen_btn.setCursor(Qt.PointingHandCursor)
                self.fullscreen_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #3F51B5;
                        color: white;
                        border-radius: 4px;
                        font-weight: bold;
                        border: none;
                        font-family: "Microsoft YaHei";
                    }
                    QPushButton:hover {
                        background-color: #5C6BC0;
                    }
                    QPushButton:pressed {
                        background-color: #303F9F;
                    }
                """)
                self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)
                self.is_fullscreen = False
                
                # Hook container resize event to update buttons
                self._original_container_resize = self.container.resizeEvent
                def container_resize(event):
                    self._original_container_resize(event)
                    self.update_button_positions(event.size().width())
                self.container.resizeEvent = container_resize



                # 表格
                self.table = HoverTableWidget()
                self.table.hover_callback = self.update_preview # 绑定回调
                # 默认9列: 镜头号, 时间码, 动画片场, 图片提示词, 人物, 道具, 场景, 分镜图, 视频
                self.table.setColumnCount(9)
                self.table.setHorizontalHeaderLabels(["🎬 镜头号", "⏱ 时间码", "📺 动画片场", "🖼️ 图片提示词", "👤 人物", "🛠️ 道具", "🏞️ 场景", "🖼️ 分镜图 🔴", "🎥 视频"])
                
                # 连接表头点击信号
                self.table.horizontalHeader().sectionClicked.connect(self.on_header_clicked)
                
                # 默认隐藏"动画片场"列
                self.table.setColumnHidden(2, True)
                
                # 隐藏垂直表头
                self.table.verticalHeader().setVisible(False)
                # 交替行颜色
                self.table.setAlternatingRowColors(True)
                
                # 修复滚动条不同步问题
                self.table.verticalScrollBar().valueChanged.connect(self.table.viewport().update)
                
                # 样式
                self.table.setStyleSheet("""
                    QTableWidget {
                        background-color: #ffffff;
                        border: 1px solid #E1BEE7;
                        border-radius: 6px;
                        color: #333333;
                        gridline-color: #F3E5F5;
                        selection-background-color: #E1BEE7;
                        selection-color: #4A148C;
                    }
                    QTableWidget::item {
                        padding: 6px;
                        border-bottom: 1px solid #F3E5F5;
                    }
                    QHeaderView::section {
                        background-color: #AB47BC;
                        color: white;
                        padding: 6px;
                        border: none;
                        font-weight: bold;
                        font-size: 13px;
                    }
                    QHeaderView::section:first {
                        border-top-left-radius: 5px;
                    }
                    QHeaderView::section:last {
                        border-top-right-radius: 5px;
                    }
                    QScrollBar:vertical {
                        border: none;
                        background: #F3E5F5;
                        width: 8px;
                        margin: 0px 0px 0px 0px;
                        border-radius: 4px;
                    }
                    QScrollBar::handle:vertical {
                        background: #CE93D8;
                        min-height: 20px;
                        border-radius: 4px;
                    }
                    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                        height: 0px;
                        width: 0px;
                    }
                """)
                
                self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
                self.table.horizontalHeader().setStretchLastSection(True)
                
                # 设置初始列宽
                self.table.setColumnWidth(0, 60)   # 镜头号
                self.table.setColumnWidth(1, 110)  # 时间码
                self.table.setColumnWidth(2, 250)  # 动画片场
                self.table.setColumnWidth(3, 200)  # 图片提示词
                self.table.setColumnWidth(4, 100)  # 人物
                self.table.setColumnWidth(5, 100)  # 道具
                self.table.setColumnWidth(6, 100)  # 场景
                self.table.setColumnWidth(7, 120)  # 分镜图
                self.table.setColumnWidth(8, 120)  # 视频
                
                # 设置图片列的代理
                self.table.setItemDelegateForColumn(4, ImageDelegate(self.table)) # 人物
                self.table.setItemDelegateForColumn(5, ImageDelegate(self.table)) # 道具
                self.table.setItemDelegateForColumn(6, ImageDelegate(self.table)) # 场景
                self.table.setItemDelegateForColumn(7, ImageDelegate(self.table, node=self)) # 分镜图
                
                # 连接双击信号
                self.table.cellDoubleClicked.connect(self.on_cell_double_click)
                
                # 设置上下文菜单
                self.table.setContextMenuPolicy(Qt.CustomContextMenu)
                self.table.customContextMenuRequested.connect(self.on_table_context_menu)
                
                self.layout.addWidget(self.table)
                
                self.proxy_widget.setWidget(self.container)
                self.proxy_widget.setGeometry(self.boundingRect())
                
            def upload_storyboard_image(self, row, slot_index):
                """上传分镜图 (Slot 0 or 1)"""
                # 获取当前镜头号
                item_shot = self.table.item(row, 0)
                shot_num = item_shot.text() if item_shot else str(row + 1)
                
                title = "上传首帧图片" if slot_index == 0 else "上传尾帧图片"
                
                file_path, _ = QFileDialog.getOpenFileName(
                    self.proxy_widget.widget(),
                    title,
                    "",
                    "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
                )
                
                if not file_path:
                    return
                
                # 读取当前 paths
                current_paths = [None, None]
                if shot_num in self.storyboard_paths:
                    val = self.storyboard_paths[shot_num]
                    if isinstance(val, list):
                        if len(val) > 0: current_paths[0] = val[0]
                        if len(val) > 1: current_paths[1] = val[1]
                    else:
                        current_paths[0] = val
                
                # 更新指定 slot
                if 0 <= slot_index < 2:
                    current_paths[slot_index] = file_path
                
                # 更新缓存
                self.storyboard_paths[shot_num] = current_paths
                self.save_storyboard_paths()
                
                # 更新 UI
                self.set_cell_images(row, 6, current_paths)
                
                # 检查完成状态
                self.check_completion_and_update_columns()

            def on_cell_double_click(self, row, column):
                """处理表格双击事件"""
                # 动画片场 (index 2)
                if column == 2:
                    item = self.table.item(row, column)
                    if item:
                        open_edit_dialog_for_item(item, None) # 传入None避免被遮挡
                
                # 图片提示词 (index 3) - 编辑
                elif column == 3:
                    item_shot = self.table.item(row, 0)
                    shot_num = item_shot.text() if item_shot else str(row + 1)
                    
                    current_prompt = self.image_prompts.get(shot_num, "")
                    item = self.table.item(row, column)
                    if item and not current_prompt:
                         current_prompt = item.text()

                    dialog = TextEditDialog(current_prompt, None)
                    dialog.setWindowTitle(f"编辑图片提示词 - 镜头 {shot_num}")
                    if dialog.exec():
                        new_prompt = dialog.get_text()
                        self.update_image_prompt(shot_num, new_prompt)
                        # 更新界面
                        if item:
                             item.setText(new_prompt)

                # 道具 (index 5) - 编辑道具提示词
                elif column == 5:
                    # 获取当前镜头号作为key
                    item_shot = self.table.item(row, 0)
                    shot_num = item_shot.text() if item_shot else str(row + 1)
                    
                    # 获取当前道具提示词
                    current_prompt = self.props_prompts.get(shot_num, "")
                    
                    # 打开编辑对话框
                    dialog = TextEditDialog(current_prompt, None)
                    dialog.setWindowTitle(f"编辑道具提示词 - 镜头 {shot_num}")
                    if dialog.exec():
                        new_prompt = dialog.get_text()
                        self.update_prop_prompt(shot_num, new_prompt)
                    
            def update_prop_prompt(self, shot_num, prompt_text):
                """更新道具提示词"""
                if prompt_text:
                    self.props_prompts[shot_num] = prompt_text
                else:
                    # 如果提示词为空，删除缓存
                    if shot_num in self.props_prompts:
                        del self.props_prompts[shot_num]
                
                self.save_props_prompts()
                print(f"[导演节点] 更新镜头 {shot_num} 的道具提示词")

            def update_image_prompt(self, shot_num, prompt_text):
                """更新图片提示词"""
                if prompt_text:
                    self.image_prompts[shot_num] = prompt_text
                else:
                    if shot_num in self.image_prompts:
                        del self.image_prompts[shot_num]
                
                self.save_image_prompts()
                print(f"[导演节点] 更新镜头 {shot_num} 的图片提示词")

            class PropPromptWorker(QThread):
                success = Signal(str)
                error = Signal(str)
                debug = Signal(str)
                def __init__(self, provider, model, api_key, api_url, hunyuan_api_url, image_path):
                    super().__init__()
                    self.provider = provider
                    self.model = model
                    self.api_key = api_key
                    self.api_url = api_url
                    self.hunyuan_api_url = hunyuan_api_url
                    self.image_path = image_path

                    # 注册到全局引用列表，防止被垃圾回收
                    from PySide6.QtWidgets import QApplication
                    app = QApplication.instance()
                    if app:
                        if not hasattr(app, '_active_prop_prompt_workers_qp'):
                            app._active_prop_prompt_workers_qp = []
                        app._active_prop_prompt_workers_qp.append(self)
                    self.finished.connect(self._cleanup_worker)

                def _cleanup_worker(self):
                    """清理 worker 引用"""
                    from PySide6.QtWidgets import QApplication
                    app = QApplication.instance()
                    if app and hasattr(app, '_active_prop_prompt_workers_qp'):
                        if self in app._active_prop_prompt_workers_qp:
                            app._active_prop_prompt_workers_qp.remove(self)
                    self.deleteLater()
                def run(self):
                    try:
                        import os, base64, json, http.client, ssl
                        base_url = self.hunyuan_api_url if self.provider == "Hunyuan" else self.api_url
                        from urllib.parse import urlparse
                        parsed = urlparse(base_url)
                        host = parsed.netloc or parsed.path.split('/')[0]
                        scheme = parsed.scheme or 'https'
                        if scheme == 'https':
                            context = ssl.create_default_context()
                            conn = http.client.HTTPSConnection(host, context=context, timeout=25)
                        else:
                            conn = http.client.HTTPConnection(host, timeout=25)
                        endpoint = "/v1/chat/completions"
                        with open(self.image_path, 'rb') as f:
                            image_b64 = base64.b64encode(f.read()).decode('utf-8')
                        ext = os.path.splitext(self.image_path)[1].lower()
                        mime_type = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp', '.gif': 'image/gif'}.get(ext, 'image/jpeg')
                        content = [
                            {"type": "text", "text": "只返回一句中文的简短提示词，描述图中主要物体及其关键属性，不要附加任何解释、结构或前后缀，只输出描述文本。"},
                            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}}
                        ]
                        payload = {"model": self.model, "messages": [{"role": "user", "content": content}], "max_tokens": 256}
                        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
                        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
                        self.debug.emit(f"provider={self.provider}, model={self.model}, url={base_url}{endpoint}, image={os.path.basename(self.image_path)}, body={len(body)}B")
                        conn.request("POST", endpoint, body=body, headers=headers)
                        resp = conn.getresponse()
                        data = resp.read()
                        conn.close()
                        if resp.status != 200:
                            try:
                                err_text = data.decode('utf-8')[:300]
                            except Exception:
                                err_text = str(data)[:300]
                            self.error.emit(f"生成失败 ({resp.status}): {err_text}")
                            return
                        try:
                            j = json.loads(data.decode('utf-8'))
                            result_text = ""
                            if isinstance(j, dict) and j.get("choices"):
                                msg = j["choices"][0].get("message", {})
                                content = msg.get("content")
                                if isinstance(content, str):
                                    result_text = content.strip()
                                elif isinstance(content, list):
                                    parts = []
                                    for c in content:
                                        if isinstance(c, dict) and c.get("type") == "text":
                                            parts.append(c.get("text",""))
                                    result_text = "\n".join(parts).strip()
                            if not result_text and isinstance(j, dict):
                                result_text = (j.get("output","") or j.get("response","") or "").strip()
                        except Exception:
                            try:
                                result_text = data.decode('utf-8').strip()
                            except Exception:
                                result_text = ""
                        if not result_text:
                            self.error.emit("未获取到有效的提示词内容。")
                            return
                        try:
                            import re
                            lines = [l.strip() for l in result_text.splitlines() if l.strip()]
                            cand = lines[0] if lines else result_text.strip()
                            cand = re.sub(r'^(成功|提示词|下面是|以下是|你可以|这是|描述|关于这张图片)[：:]\s*', '', cand, flags=re.IGNORECASE)
                            cand = re.sub(r'^(AI|用户)[：:]\s*', '', cand, flags=re.IGNORECASE)
                            cand = cand.strip('“”"').strip()
                            if len(cand) > 200:
                                cand = cand[:200].strip()
                        except Exception:
                            cand = result_text.strip()
                        self.success.emit(cand)
                    except Exception as e:
                        self.error.emit(str(e))

            def generate_prop_prompt_ai(self, row):
                try:
                    item_shot = self.table.item(row, 0)
                    shot_num = item_shot.text() if item_shot else str(row + 1)
                    item_prop = self.table.item(row, 5)
                    image_path = None
                    if item_prop:
                        data = item_prop.data(Qt.UserRole)
                        if data and isinstance(data, list):
                            for p in data:
                                if p and os.path.exists(p):
                                    image_path = p
                                    break
                    if (not image_path or not os.path.exists(image_path)) and shot_num in self.props_paths:
                        p = self.props_paths.get(shot_num)
                        if p and os.path.exists(p):
                            image_path = p
                    if not image_path or not os.path.exists(image_path):
                        QMessageBox.warning(None, "提示", "未找到可用的道具图片，无法生成提示词。")
                        return
                    if self._ai_prompt_running:
                        QMessageBox.information(None, "提示", "已有AI提示词任务正在进行，请稍候。")
                        return
                    app_root = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
                    config_dir = os.path.join(app_root, 'json')
                    chat_cfg_path = os.path.join(config_dir, 'chat_mode_config.json')
                    talk_cfg_path = os.path.join(config_dir, 'talk_api_config.json')
                    last_provider = None
                    last_model = None
                    api_key = None
                    api_url = None
                    hunyuan_api_url = None
                    import json as _json
                    # 优先尝试从正在运行的工作台读取当前选择的提供商/模型
                    try:
                        from PySide6.QtWidgets import QApplication as _QApp
                        for w in _QApp.allWidgets():
                            if hasattr(w, 'provider_combo') and hasattr(w, 'model_combo'):
                                p = w.provider_combo.currentText()
                                m = w.model_combo.currentText()
                                if p and m and not str(m).startswith("⚠️"):
                                    last_provider = p
                                    last_model = m
                                    break
                    except Exception:
                        pass
                    # 其次尝试读取 chat_mode_config.json
                    try:
                        if (not last_provider or not last_model) and os.path.exists(chat_cfg_path):
                            with open(chat_cfg_path, 'r', encoding='utf-8') as f:
                                chat_cfg = _json.load(f)
                                last_provider = last_provider or chat_cfg.get('last_provider')
                                last_model = last_model or chat_cfg.get('last_model')
                    except Exception:
                        pass
                    try:
                        if os.path.exists(talk_cfg_path):
                            with open(talk_cfg_path, 'r', encoding='utf-8') as f:
                                talk_cfg = _json.load(f)
                                hunyuan_api_url = talk_cfg.get('hunyuan_api_url', 'https://api.vectorengine.ai')
                                api_url = talk_cfg.get('api_url', 'https://manju.chat')
                                if last_provider:
                                    key_name = f"{last_provider.lower()}_api_key"
                                    # Gemini特殊命名
                                    if 'gemini' in last_provider.lower() and not talk_cfg.get(key_name):
                                        key_name = 'gemini 2.5_api_key'
                                    api_key = talk_cfg.get(key_name, '')
                                # 回退：选择第一个有key的provider
                                if not api_key:
                                    for p in ["Hunyuan", "ChatGPT", "DeepSeek", "Claude", "Gemini 2.5"]:
                                        key_name = f"{p.lower()}_api_key"
                                        k = talk_cfg.get(key_name, '')
                                        if k:
                                            last_provider = last_provider or p
                                            api_key = k
                                            break
                        else:
                            pass
                    except Exception as e:
                        print(f"[导演节点][AI提示词] 读取talk配置失败: {e}")
                    # 如果还缺少模型，尝试通过API拉取模型并使用第一个
                    if (not last_model) and api_key and last_provider:
                        try:
                            from urllib.parse import urlparse
                            import http.client, ssl
                            base_for_models = hunyuan_api_url if last_provider == "Hunyuan" else api_url
                            parsed = urlparse(base_for_models)
                            host = parsed.netloc or parsed.path.split('/')[0]
                            context = ssl.create_default_context()
                            conn = http.client.HTTPSConnection(host, context=context, timeout=10)
                            headers = {
                                'Authorization': f'Bearer {api_key}',
                                'Content-Type': 'application/json',
                                'Accept': 'application/json'
                            }
                            conn.request('GET', '/v1/models', '', headers)
                            res = conn.getresponse()
                            data_models = res.read()
                            conn.close()
                            if res.status == 200:
                                models_obj = _json.loads(data_models.decode('utf-8'))
                                ids = [m['id'] for m in models_obj.get('data', [])]
                                prov_lower = (last_provider or '').lower()
                                for mid in ids:
                                    if (prov_lower == 'hunyuan' and mid.startswith('hunyuan')) or \
                                       (prov_lower == 'chatgpt' and (mid.startswith('gpt') or mid.startswith('o1') or mid.startswith('o3') or mid.startswith('chatgpt'))) or \
                                       (prov_lower == 'deepseek' and mid.startswith('deepseek')) or \
                                       (prov_lower == 'claude' and mid.startswith('claude')) or \
                                       ('gemini' in prov_lower and mid.startswith('gemini')):
                                        last_model = mid
                                        break
                        except Exception:
                            pass
                    if not api_key or not last_provider or not last_model:
                        QMessageBox.warning(None, "提示", "请在工作台选择对话API模型，并确保在设置中配置对话API密钥。")
                        print(f"[导演节点][AI提示词] 配置不足: provider={last_provider}, model={last_model}, key={'有' if api_key else '无'}")
                        return
                    self._ai_prompt_running = True
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    worker = self.PropPromptWorker(last_provider, last_model, api_key, api_url, hunyuan_api_url, image_path)
                    def _on_success(text):
                        try:
                            self.update_prop_prompt(shot_num, text)
                            if item_prop:
                                item_prop.setToolTip(f"道具提示词: {text}")
                            QMessageBox.information(None, "提示词", text)
                        finally:
                            self._ai_prompt_running = False
                            QApplication.restoreOverrideCursor()
                    def _on_error(msg):
                        try:
                            QMessageBox.critical(None, "错误", msg)
                        finally:
                            self._ai_prompt_running = False
                            QApplication.restoreOverrideCursor()
                    worker.success.connect(_on_success)
                    worker.error.connect(_on_error)
                    worker.debug.connect(lambda d: print(f"[导演节点][AI提示词] {d}"))
                    worker.start()
                except Exception as e:
                    QMessageBox.critical(None, "错误", f"生成提示词失败: {e}")
                    print(f"[导演节点][AI提示词] 异常: {e}")
            def upload_prop_image(self, row):
                """上传道具图片"""
                # 获取当前镜头号作为key
                item_shot = self.table.item(row, 0)
                shot_num = item_shot.text() if item_shot else str(row + 1)
                
                # 打开文件选择对话框
                file_path, _ = QFileDialog.getOpenFileName(
                    self.proxy_widget.widget(),
                    "选择道具图片",
                    "",
                    "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
                )
                
                if file_path:
                    # 更新缓存
                    self.props_paths[shot_num] = file_path
                    self.save_props_paths()
                    
                    # 更新表格显示 (Col 5 is Props)
                    self.set_cell_images(row, 5, [file_path])
                    print(f"[导演节点] 上传镜头 {shot_num} 的道具图片: {file_path}")
                
            def add_character_from_nodes(self, row):
                """从剧本人物节点添加人物"""
                # 1. 查找所有剧本人物节点
                char_nodes = []
                if not hasattr(self, 'scene') or not self.scene():
                    return
                    
                try:
                    nodes = [item for item in self.scene().items() if hasattr(item, 'node_title')]
                    for node in nodes:
                        if "剧本人物" in node.node_title:
                            char_nodes.append(node)
                except:
                    pass
                    
                if not char_nodes:
                    QMessageBox.information(None, "提示", "未找到【剧本人物】节点。")
                    return
                    
                # 2. 收集人物数据 (name -> image_path)
                characters = {}
                for node in char_nodes:
                    if hasattr(node, 'proxy_widget') and node.proxy_widget.widget():
                         widgets = node.proxy_widget.widget().findChildren(QWidget)
                         for child in widgets:
                             if hasattr(child, 'get_data') and callable(child.get_data):
                                 try:
                                     data = child.get_data()
                                     name = data.get('name', '').strip()
                                     image_path = data.get('image_path') or data.get('image')
                                     if name and image_path and os.path.exists(image_path):
                                         characters[name] = image_path
                                 except:
                                     pass
                
                if not characters:
                     QMessageBox.information(None, "提示", "剧本人物节点中没有有效的人物数据（需包含名字和图片）。")
                     return

                # 3. 显示选择菜单
                menu = QMenu(self.table)
                menu.setStyleSheet("""
                    QMenu {
                        background-color: #FFFFFF;
                        border: 1px solid #E1BEE7;
                        border-radius: 4px;
                        padding: 4px;
                    }
                    QMenu::item {
                        padding: 6px 20px;
                        border-radius: 3px;
                    }
                    QMenu::item:selected {
                        background-color: #F3E5F5;
                        color: #4A148C;
                    }
                """)
                
                for name, path in characters.items():
                    action = menu.addAction(name)
                    action.setData(path) # Store path in action data
                    
                # 显示在鼠标位置
                action = menu.exec(QCursor.pos())
                
                if action:
                    selected_path = action.data()
                    if selected_path:
                        # 4. 更新单元格
                        current_paths = []
                        item = self.table.item(row, 4)
                        if item:
                            data = item.data(Qt.UserRole)
                            if data and isinstance(data, list):
                                current_paths = list(data)
                        
                        if selected_path not in current_paths:
                            current_paths.append(selected_path)
                            self.set_cell_images(row, 4, current_paths)
                            print(f"[导演节点] 镜头 {row+1} 添加人物: {action.text()}")
                            
                            # 保存到缓存
                            item_shot = self.table.item(row, 0)
                            if item_shot:
                                shot_num = item_shot.text()
                                self.character_paths[shot_num] = current_paths
                                self.save_character_paths()

            def update_data(self):
                """从连接的节点读取数据"""
                if not hasattr(self, 'input_sockets') or not self.input_sockets:
                    return

                # 获取第一个输入插座
                if not self.input_sockets:
                    return
                socket = self.input_sockets[0]
                
                # 检查是否有连接
                if not socket.connections:
                    self.table.setRowCount(0)
                    return
                    
                # 获取连接的源节点
                connection = socket.connections[0]
                if not connection or not connection.source_socket:
                    return
                    
                source_node = connection.source_socket.parent_node
                
                # 检查是否是谷歌剧本节点 (通过标题判断)
                if hasattr(source_node, 'node_title') and "谷歌剧本" in source_node.node_title:
                    self.read_google_script_data(source_node)
                else:
                    self.table.setRowCount(0)

            def update_button_positions(self, width):
                """更新按钮位置"""
                if hasattr(self, 'anime_btn'):
                    self.anime_btn.move(int(width) - 150, 8)
                
                if hasattr(self, 'storyboard_btn'):
                    self.storyboard_btn.move(int(width) - 260, 8)
                
                if hasattr(self, 'sora_btn'):
                    self.sora_btn.move(int(width) - 370, 8)

                if hasattr(self, 'add_prompt_btn'):
                    self.add_prompt_btn.move(int(width) - 510, 8)

                if hasattr(self, 'add_image_prompt_btn'):
                    self.add_image_prompt_btn.move(int(width) - 650, 8)
                    
                if hasattr(self, 'fullscreen_btn'):
                    self.fullscreen_btn.move(int(width) - 760, 8)

            def toggle_fullscreen(self):
                """切换全屏模式"""
                if not self.is_fullscreen:
                    # 进入全屏
                    self.is_fullscreen = True
                    self.fullscreen_btn.setText("🔙 还原")
                    
                    # 保存原始关闭事件
                    self.original_close_event = self.container.closeEvent
                    self.container.closeEvent = self.on_fullscreen_close
                    
                    # 脱离 ProxyWidget
                    self.container.setParent(None)
                    self.container.setWindowFlags(Qt.Window)
                    self.container.setWindowTitle("导演节点 - 全屏模式")
                    
                    # 显示并最大化
                    self.container.showMaximized()
                    
                else:
                    self.restore_from_fullscreen()

            def restore_from_fullscreen(self):
                """从全屏还原"""
                if self.is_fullscreen:
                    self.is_fullscreen = False
                    self.fullscreen_btn.setText("📺 全屏")
                    
                    # 恢复关闭事件
                    if hasattr(self, 'original_close_event'):
                        self.container.closeEvent = self.original_close_event
                    
                    # 恢复 WindowFlags
                    self.container.setWindowFlags(Qt.Widget)
                    self.container.setAttribute(Qt.WA_DeleteOnClose, False)
                    
                    # 放回 ProxyWidget
                    self.proxy_widget.setWidget(self.container)
                    
                    # 强制更新布局
                    self.setRect(self.rect())
            
            def on_fullscreen_close(self, event):
                """处理全屏窗口关闭事件"""
                self.restore_from_fullscreen()
                event.ignore()

            def setRect(self, *args):
                """重写setRect以在大小改变时更新内部控件"""
                super().setRect(*args)
                if hasattr(self, 'proxy_widget'):
                    self.proxy_widget.setGeometry(self.boundingRect())
                
                width = self.rect().width()
                height = self.rect().height()
                
                # Update row height to show exactly 4 rows
                if hasattr(self, 'table'):
                    header_height = self.table.horizontalHeader().height()
                    # Calculate available height for rows (subtracting header and some margin)
                    # 55px (margins) + ~5px buffer
                    available_height = height - header_height - 60 
                    # Ensure at least 20px per row, otherwise fit 4 rows
                    row_height = max(20, int(available_height / 4))
                    
                    self.table.verticalHeader().setDefaultSectionSize(row_height)
                    # Force update existing rows
                    for r in range(self.table.rowCount()):
                        self.table.setRowHeight(r, row_height)
                
                self.update_button_positions(width)

                # 移除最大高度限制，允许表格随窗口扩展
                # self.table.setMaximumHeight(500)
            



            def get_image_maps(self):
                """遍历场景，获取人物和地点的图片映射"""
                char_map = {}
                loc_map = {}
                
                if not hasattr(self, 'scene') or not self.scene():
                    return char_map, loc_map
                    
                try:
                    # 使用 items() 替代 nodes，因为 QGraphicsScene 没有 nodes 属性
                    # 过滤出具有 node_title 属性的项 (即 CanvasNode 及其子类)
                    nodes = [item for item in self.scene().items() if hasattr(item, 'node_title')]
                except:
                    return char_map, loc_map
                
                for node in nodes:
                    # 检查是否是人物节点
                    if "剧本人物" in node.node_title:
                         if hasattr(node, 'proxy_widget') and node.proxy_widget.widget():
                             # 查找所有具有 get_data 方法的子控件
                             # 限制查找深度或类型可能更安全，但 findChildren 应该足够
                             widgets = node.proxy_widget.widget().findChildren(QWidget)
                             for child in widgets:
                                 # 鸭子类型检查：是否有 get_data 方法
                                 if hasattr(child, 'get_data') and callable(child.get_data):
                                     try:
                                         data = child.get_data()
                                         # CharacterRowWidget 返回 {name, prompt, image_path, ...}
                                         name = data.get('name', '').strip()
                                         image_path = data.get('image_path') or data.get('image')
                                         if name and image_path:
                                             char_map[name] = image_path
                                     except:
                                         pass
                                         
                    # 检查是否是地点节点
                    elif "地点" in node.node_title or "环境" in node.node_title:
                        if hasattr(node, 'proxy_widget') and node.proxy_widget.widget():
                             widgets = node.proxy_widget.widget().findChildren(QWidget)
                             for child in widgets:
                                 if hasattr(child, 'get_data') and callable(child.get_data):
                                     try:
                                         data = child.get_data()
                                         # LocationRowWidget 返回 {name, prompt, image, ...}
                                         name = data.get('name', '').strip()
                                         image_path = data.get('image') or data.get('image_path')
                                         if name and image_path:
                                             loc_map[name] = image_path
                                     except:
                                         pass
                return char_map, loc_map

            def read_google_script_data(self, google_node):
                """读取谷歌剧本节点数据"""
                rows = []
                
                # 方式1: 尝试使用 get_output_data 接口 (推荐)
                if hasattr(google_node, 'get_output_data'):
                    try:
                        # 获取连接的源 socket index
                        socket_index = 0
                        if self.input_sockets and self.input_sockets[0].connections:
                             conn = self.input_sockets[0].connections[0]
                             if hasattr(conn, 'source_socket') and hasattr(conn.source_socket, 'index'):
                                 socket_index = conn.source_socket.index
                        
                        rows = google_node.get_output_data(socket_index)
                    except Exception as e:
                        rows = []
                
                # 方式2: 如果接口失败，尝试直接读取表格 (兼容性后备)
                if not rows and hasattr(google_node, 'table'):
                    try:
                        table = google_node.table
                        for r in range(table.rowCount()):
                            row_data = {}
                            for c in range(table.columnCount()):
                                item = table.item(r, c)
                                text = item.text() if item else ""
                                row_data[c] = text
                                # 尝试获取表头作为key
                                header_item = table.horizontalHeaderItem(c)
                                if header_item:
                                    row_data[header_item.text()] = text
                            rows.append(row_data)
                    except Exception:
                        pass
                
                # 如果没有数据，清空表格
                if not rows:
                    self.table.setRowCount(0)
                    return

                # 获取图片映射
                char_map, loc_map = self.get_image_maps()

                # 更新导演节点表格
                current_row_count = len(rows)
                if self.table.rowCount() != current_row_count:
                    self.table.setRowCount(current_row_count)
                
                for r, row_data in enumerate(rows):
                    # 1. 镜号 (Column 0)
                    shot_text = ""
                    if isinstance(row_data, dict):
                        shot_text = row_data.get("镜号", row_data.get(0, ""))
                    
                    item_shot = self.table.item(r, 0)
                    if not item_shot:
                        item_shot = QTableWidgetItem(str(shot_text))
                        item_shot.setTextAlignment(Qt.AlignCenter)
                        self.table.setItem(r, 0, item_shot)
                    else:
                        if item_shot.text() != str(shot_text):
                            item_shot.setText(str(shot_text))
                        
                    # 2. 时间码 (Column 1)
                    time_text = ""
                    if isinstance(row_data, dict):
                        time_text = row_data.get("时间码", row_data.get(1, ""))
                    
                    item_time = self.table.item(r, 1)
                    if not item_time:
                        item_time = QTableWidgetItem(str(time_text))
                        item_time.setTextAlignment(Qt.AlignCenter)
                        self.table.setItem(r, 1, item_time)
                    else:
                        if item_time.text() != str(time_text):
                            item_time.setText(str(time_text))

                    # 3. 动画片场 (Column 2) - 组合 画面内容+台词+地点
                    picture_content = ""
                    lines = ""
                    location = ""
                    
                    if isinstance(row_data, dict):
                        # 获取画面内容 (Column 3 in Google Node)
                        for key in ["画面内容", "Picture Content", "Content"]:
                            if key in row_data:
                                picture_content = row_data[key]
                                break
                        
                        # 获取台词 (Column 8 in Google Node)
                        for key in ["台词/音效", "台词", "Lines", "Dialogue", "Sound"]:
                            if key in row_data:
                                lines = row_data[key]
                                break
                                
                        # 获取地点 (Column 6 in Google Node)
                        for key in ["地点/环境", "地点", "Location", "Environment", "Scene"]:
                            if key in row_data:
                                location = row_data[key]
                                break
                    
                    # 组合内容
                    studio_parts = []
                    if picture_content: studio_parts.append(f"【画面】{picture_content}")
                    if lines: studio_parts.append(f"【台词】{lines}")
                    if location: studio_parts.append(f"【地点】{location}")
                    
                    studio_text = "\n".join(studio_parts)
                    
                    # 检查是否有清理节点连接 (Input 1)
                    if len(self.input_sockets) > 1 and self.input_sockets[1].connections:
                        conn = self.input_sockets[1].connections[0]
                        if conn and conn.source_socket:
                            cleaner_node = conn.source_socket.parent_node
                            # 获取清理关键词
                            if hasattr(cleaner_node, 'cleaning_text'):
                                cleaning_keyword = cleaner_node.cleaning_text
                                if cleaning_keyword:
                                    # 执行清理 (替换为空)
                                    studio_text = studio_text.replace(cleaning_keyword, "")
                                    
                    item_studio = self.table.item(r, 2)
                    if not item_studio:
                        item_studio = QTableWidgetItem(studio_text)
                        # 允许换行，左对齐
                        item_studio.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        # 设置工具提示以便查看完整内容
                        item_studio.setToolTip(studio_text)
                        self.table.setItem(r, 2, item_studio)
                    else:
                        if item_studio.text() != studio_text:
                            item_studio.setText(studio_text)
                            item_studio.setToolTip(studio_text)

                    # 4. 图片提示词 (Column 3) - NEW
                    img_prompt_text = ""
                    if isinstance(row_data, dict):
                        for key in ["绘画提示词（CN）", "绘画提示词", "Painting Prompt (CN)", "Painting Prompt", "提示词(CN)"]:
                            if key in row_data:
                                img_prompt_text = row_data[key]
                                break
                    
                    # 优先使用缓存中的编辑值
                    if shot_text in self.image_prompts:
                        img_prompt_text = self.image_prompts[shot_text]
                    
                    item_img_prompt = self.table.item(r, 3)
                    if not item_img_prompt:
                        item_img_prompt = QTableWidgetItem(img_prompt_text)
                        item_img_prompt.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        item_img_prompt.setToolTip("双击编辑")
                        self.table.setItem(r, 3, item_img_prompt)
                    else:
                        # 只有当缓存没有值且表格值不同时才更新（避免覆盖用户未保存的编辑？不，用户编辑会存入缓存）
                        # 如果缓存有值，我们在上面已经覆盖了 img_prompt_text
                        if item_img_prompt.text() != img_prompt_text:
                            item_img_prompt.setText(img_prompt_text)

                    # 5. 人物 (Column 4) - 支持多人物
                    char_text = ""
                    if isinstance(row_data, dict):
                        # 扩展查找列名
                        for key in ["人物", "角色", "Role", "Character", "Name", "姓名"]:
                            if key in row_data:
                                char_text = row_data[key]
                                break
                    
                    # 查找对应图片 (支持多个人物)
                    char_image_paths = []
                    if char_text:
                        # 分割多种可能的分隔符
                        import re
                        parts = re.split(r'[，,、\s]+', char_text)
                        for part in parts:
                            name = part.strip()
                            if not name: continue
                            
                            # 精确匹配
                            if name in char_map:
                                char_image_paths.append(char_map[name])
                            else:
                                pass
                    
                    # 优先使用缓存中的人物数据
                    if shot_text in self.character_paths:
                        saved_paths = self.character_paths[shot_text]
                        if saved_paths:
                            char_image_paths = saved_paths

                    # 设置单元格图片 (传入列表)
                    self.set_cell_images(r, 4, char_image_paths)

                    # 6. 道具 (Column 5)
                    prop_text = ""
                    if isinstance(row_data, dict):
                         for key in ["道具", "物品", "Props", "Items"]:
                             if key in row_data:
                                 prop_text = row_data[key]
                                 break
                    
                    item_prop = self.table.item(r, 5)
                    if not item_prop:
                        item_prop = QTableWidgetItem(str(prop_text))
                        item_prop.setTextAlignment(Qt.AlignCenter)
                        self.table.setItem(r, 5, item_prop)
                    else:
                        if item_prop.text() != str(prop_text):
                            item_prop.setText(str(prop_text))
                    
                    # 设置工具提示
                    tooltip = f"{prop_text}\n(双击或右键上传图片)" if prop_text else "双击或右键上传图片"
                    if item_prop.toolTip() != tooltip:
                        item_prop.setToolTip(tooltip)

                    # 检查道具图片缓存
                    current_shot_prop = shot_text
                    if current_shot_prop and current_shot_prop in self.props_paths:
                        saved_prop_path = self.props_paths[current_shot_prop]
                        
                        current_item = self.table.item(r, 5)
                        should_update_prop = True
                        if current_item:
                            current_data = current_item.data(Qt.UserRole)
                            if current_data and isinstance(current_data, list) and len(current_data) > 0:
                                if current_data[0] == saved_prop_path:
                                    should_update_prop = False
                        
                        if should_update_prop and os.path.exists(saved_prop_path):
                            self.set_cell_images(r, 5, [saved_prop_path])
                    else:
                        # 确保清除无效图片
                        current_item = self.table.item(r, 5)
                        if current_item:
                             current_data = current_item.data(Qt.UserRole)
                             if current_data:
                                 self.set_cell_images(r, 5, [])

                    # 7. 场景 (Column 6)
                    loc_text = ""
                    if isinstance(row_data, dict):
                        # 增加 "地点/环境" 
                        for key in ["地点/环境", "地点环境", "地点", "场景", "Location", "Scene", "Environment"]:
                            if key in row_data:
                                loc_text = row_data[key]
                                break
                    
                    loc_image_paths = []
                    if loc_text:
                        loc_text = loc_text.strip()
                        # 匹配地点
                        if loc_text in loc_map:
                            loc_image_paths.append(loc_map[loc_text])
                        else:
                            # 尝试部分匹配
                            for loc_name, path in loc_map.items():
                                if loc_name in loc_text or loc_text in loc_name:
                                    loc_image_paths.append(path)
                                    break 
                    
                    self.set_cell_images(r, 6, loc_image_paths)
                    
                    # 8. 分镜图 (Column 7) - 从缓存恢复
                    current_shot = shot_text 
                    if current_shot and current_shot in self.storyboard_paths:
                        saved_data = self.storyboard_paths[current_shot]
                        
                        paths = [None, None]
                        if isinstance(saved_data, list):
                            if len(saved_data) > 0: paths[0] = saved_data[0]
                            if len(saved_data) > 1: paths[1] = saved_data[1]
                        else:
                             paths[0] = saved_data
                        
                        current_item = self.table.item(r, 7)
                        should_update = True
                        if current_item:
                            current_data = current_item.data(Qt.UserRole)
                            if current_data == paths:
                                should_update = False
                        
                        if should_update:
                             final_paths = [None, None]
                             if paths[0] and os.path.exists(paths[0]): final_paths[0] = paths[0]
                             if paths[1] and os.path.exists(paths[1]): final_paths[1] = paths[1]
                             self.set_cell_images(r, 7, final_paths)

                    # 9. 视频 (Column 8) - 从缓存恢复
                    if current_shot and current_shot in self.video_paths:
                        video_path = self.video_paths[current_shot]
                        if video_path and os.path.exists(video_path):
                            # 确保列存在 (至少9列)
                            if self.table.columnCount() <= 8:
                                self.table.setColumnCount(9)
                                item = QTableWidgetItem("🎥")
                                self.table.setHorizontalHeaderItem(8, item)
                                self.table.setColumnWidth(8, 120)
                            
                            self.set_cinema_cell_ui(r, video_path)

                            # 恢复元数据
                            if current_shot in self.video_metadata:
                                meta = self.video_metadata[current_shot]
                                item = self.table.item(r, 8)
                                if item:
                                    item.setData(Qt.UserRole + 1, meta)

                # 检查是否全部完成并更新列
                self.check_completion_and_update_columns()

            def check_completion_and_update_columns(self):
                """检查分镜图是否全部生成，如果是则显示电影院列"""
                # 用户要求电影院列始终显示，因此不再根据分镜图状态隐藏
                if self.table.columnCount() < 9:
                    self.table.setColumnCount(9)
                    item = QTableWidgetItem("🎥 视频")
                    self.table.setHorizontalHeaderItem(8, item)
                    self.table.setColumnWidth(8, 120)
                    
                    # 初始化所有行的该列单元格，确保不为空
                    row_count = self.table.rowCount()
                    for r in range(row_count):
                        if not self.table.item(r, 8):
                            self.table.setItem(r, 8, QTableWidgetItem())
                
                # 恢复视频数据
                row_count = self.table.rowCount()
                if hasattr(self, 'video_paths') and self.video_paths:
                    for r in range(row_count):
                        item_shot = self.table.item(r, 0)
                        shot_num = item_shot.text() if item_shot else str(r+1)
                        if shot_num in self.video_paths:
                            video_path = self.video_paths[shot_num]
                            if video_path and os.path.exists(video_path):
                                # 复用 UI 更新逻辑
                                self.set_cinema_cell_ui(r, video_path)


            def set_cell_images(self, row, col, image_paths):
                """在单元格中设置单张或多张图片"""
                # 确保是列表
                if isinstance(image_paths, str):
                    image_paths = [image_paths]
                
                # 对于分镜图列(7)，保留 None 值且不去重，保持位置
                if col == 7:
                    if not image_paths:
                        image_paths = [None, None]
                else:
                    # 去重并过滤空值
                    if image_paths:
                        image_paths = list(dict.fromkeys([p for p in image_paths if p]))
                    else:
                        image_paths = []

                # 获取或创建 Item
                item = self.table.item(row, col)
                if not item:
                    item = QTableWidgetItem()
                    self.table.setItem(row, col, item)
                
                # 设置数据供代理使用
                item.setData(Qt.UserRole, image_paths)
                
                # 移除旧的 Widget (如果存在)
                self.table.removeCellWidget(row, col)
                
                # 设置行高
                # 只要有图片或者列是7(总是显示占位符)，就设置行高
                # if image_paths or col == 7:
                #    self.table.setRowHeight(row, 90)


            def update_preview(self, path, widget_pos):
                """更新预览图片显示"""
                # 初始化预览项
                if not hasattr(self, 'preview_item'):
                    self.preview_item = QGraphicsPixmapItem()
                    self.preview_item.setZValue(2000) # 确保在最顶层
                    # 添加阴影
                    from PySide6.QtWidgets import QGraphicsDropShadowEffect
                    shadow = QGraphicsDropShadowEffect()
                    shadow.setBlurRadius(20)
                    shadow.setColor(QColor(0, 0, 0, 80))
                    shadow.setOffset(0, 5)
                    self.preview_item.setGraphicsEffect(shadow)
                    
                    if self.scene():
                        self.scene().addItem(self.preview_item)
                
                # 初始化缓存和状态
                if not hasattr(self, 'preview_cache'):
                    self.preview_cache = {}
                if not hasattr(self, 'current_preview_path'):
                    self.current_preview_path = None

                # 隐藏逻辑
                if not path:
                    self.preview_item.setVisible(False)
                    self.current_preview_path = None
                    return
                
                # 只有当路径改变时才更新图片内容
                if path != self.current_preview_path:
                    pixmap = None
                    
                    # 检查缓存
                    if path in self.preview_cache:
                        pixmap = self.preview_cache[path]
                    else:
                        # 加载并处理图片
                        loaded_pixmap = QPixmap(path)
                        if not loaded_pixmap.isNull():
                            # 限制最大尺寸
                            max_size = 400
                            if loaded_pixmap.width() > max_size or loaded_pixmap.height() > max_size:
                                pixmap = loaded_pixmap.scaled(max_size, max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            else:
                                pixmap = loaded_pixmap
                            # 存入缓存
                            self.preview_cache[path] = pixmap
                    
                    if pixmap:
                        self.preview_item.setPixmap(pixmap)
                        self.preview_item.setVisible(True)
                        self.current_preview_path = path
                    else:
                        self.preview_item.setVisible(False)
                        self.current_preview_path = None
                        return

                # 更新位置 (始终执行)
                # 计算位置 (显示在鼠标右侧或左侧)
                container_pos = self.table.mapTo(self.container, widget_pos)
                scene_pos = self.proxy_widget.mapToScene(QPointF(container_pos))
                
                # 偏移一点，避免遮挡鼠标
                x = scene_pos.x() + 20
                y = scene_pos.y() + 20
                
                self.preview_item.setPos(x, y)


            def toggle_anime_column(self):
                """切换动漫列的显示"""
                # 检查当前是否隐藏
                is_hidden = self.table.isColumnHidden(2)
                
                if is_hidden:
                    # 显示列
                    self.table.setColumnHidden(2, False)
                    # 更新按钮状态
                    self.anime_btn.setText("隐藏动画片场")
                    self.anime_btn.setStyleSheet(self.anime_btn.styleSheet().replace("#AB47BC", "#7B1FA2"))
                else:
                    # 隐藏列
                    self.table.setColumnHidden(2, True)
                    # 更新按钮状态
                    self.anime_btn.setText("📺 动画片场")
                    self.anime_btn.setStyleSheet(self.anime_btn.styleSheet().replace("#7B1FA2", "#AB47BC"))

            def on_header_clicked(self, logical_index):
                """处理表头点击事件"""
                # 分镜图列 (Index 7)
                if logical_index == 7:
                    self.show_tail_frame = not self.show_tail_frame
                    
                    # 更新表头文字
                    header_item = self.table.horizontalHeaderItem(7)
                    if header_item:
                        indicator = "🟢" if self.show_tail_frame else "🔴"
                        header_item.setText(f"🖼️ 分镜图 {indicator}")
                    
                    # 强制刷新表格以更新 Delegate 绘制
                    self.table.viewport().update()

            def on_table_context_menu(self, pos):
                """表格右键菜单"""
                # 隐藏预览图，避免遮挡
                if hasattr(self, 'preview_item') and self.preview_item:
                    self.preview_item.setVisible(False)

                item = self.table.itemAt(pos)
                col = item.column() if item else -1
                row = item.row() if item else -1
                
                # 如果 itemAt 返回空 (例如点击了空单元格)，尝试使用坐标计算
                if col == -1:
                    col = self.table.columnAt(pos.x())
                if row == -1:
                    row = self.table.rowAt(pos.y())
                
                menu = QMenu(self.table)
                menu.setStyleSheet("""
                    QMenu {
                        background-color: #FFFFFF;
                        border: 1px solid #E1BEE7;
                        border-radius: 4px;
                        padding: 4px;
                    }
                    QMenu::item {
                        padding: 6px 20px;
                        border-radius: 3px;
                    }
                    QMenu::item:selected {
                        background-color: #F3E5F5;
                        color: #4A148C;
                    }
                """)
                
                action_gen_this = None
                action_view_image = None
                action_clear = None
                action_clear_all_storyboards = None
                action_upload_image = None
                action_ai_prompt = None

                # 如果点击的是人物列(4)
                if col == 4 and row >= 0:
                    action_add_char = menu.addAction("➕ 新增人物")
                    
                    if item:
                         data = item.data(Qt.UserRole)
                         if data and isinstance(data, list) and len(data) > 0:
                             menu.addSeparator()
                             action_clear = menu.addAction("🗑️ 清空")
                    
                    menu.addSeparator()

                # 如果点击的是道具列(5)，添加上传图片选项
                if col == 5 and row >= 0:
                    action_upload_image = menu.addAction("📤 上传图片")
                    action_ai_prompt = menu.addAction("🤖 AI生成提示词")
                    
                    # 如果有图片，也可以查看大图和清空
                    if item:
                        data = item.data(Qt.UserRole)
                        if data and isinstance(data, list) and len(data) > 0 and os.path.exists(data[0]):
                            action_view_image = menu.addAction("🔍 查看大图")
                            menu.addSeparator()
                            action_clear = menu.addAction("🗑️ 清空")
                    
                    menu.addSeparator()

                # 如果点击的是分镜图列(7)，添加特定选项
                if col == 7 and row >= 0:
                    action_gen_this = menu.addAction("🎬 生成此分镜图")
                    
                    # 添加清空选项
                    if item:
                        data = item.data(Qt.UserRole)
                        has_data = False
                        if data and isinstance(data, list):
                             for p in data:
                                 if p and os.path.exists(p):
                                     has_data = True
                                     break
                        
                        if has_data:
                            # action_view_image = menu.addAction("🔍 查看大图") # 已移除
                            menu.addSeparator()
                            action_clear = menu.addAction("🗑️ 清空此行分镜图")

                    menu.addSeparator()
                    # 添加清空所有分镜图选项
                    action_clear_all_storyboards = menu.addAction("🗑️ 清空所有分镜图")
                    menu.addSeparator()
                
                action_gen_video = None
                action_clear_video = None
                
                # 如果点击的是电影院列(8)
                if col == 8 and row >= 0:
                     action_gen_video = menu.addAction("🎥 生成视频")
                     action_create_sora_char = menu.addAction("👤 创建Sora角色")
                     action_clear_video = menu.addAction("🗑️ 清空视频")
                     menu.addSeparator()

                action_gen_all = menu.addAction("🎬 生成所有分镜图")
                action_gen_selected = menu.addAction("✨ 仅生成选中行")
                
                # 如果有选中的行，启用"仅生成选中行"
                selected_ranges = self.table.selectedRanges()
                has_selection = len(selected_ranges) > 0
                action_gen_selected.setEnabled(has_selection)
                
                action = menu.exec(self.table.mapToGlobal(pos))
                
                if action_gen_this and action == action_gen_this:
                    self.open_storyboard_dialog(target_rows=[row])
                elif 'action_add_char' in locals() and action == action_add_char:
                    # 新增人物
                    self.add_character_from_nodes(row)
                elif action_upload_image and action == action_upload_image:
                     # 上传道具图片
                     self.upload_prop_image(row)
                elif action_ai_prompt and action == action_ai_prompt:
                    self.generate_prop_prompt_ai(row)
                elif action_view_image and action == action_view_image:
                    data = item.data(Qt.UserRole)
                    if data and data[0]:
                        dialog = ImageViewerDialog(data[0], self.table)
                        dialog.exec()
                elif action_clear and action == action_clear:
                    # 清空单元格
                    self.set_cell_images(row, col, [])
                    # 清除缓存
                    item_shot = self.table.item(row, 0)
                    if item_shot:
                        shot_num = item_shot.text()
                        
                        # 根据列号判断清除哪个缓存
                        if col == 7 and shot_num in self.storyboard_paths:
                            del self.storyboard_paths[shot_num]
                            self.save_storyboard_paths()
                        elif col == 5 and shot_num in self.props_paths:
                            del self.props_paths[shot_num]
                            self.save_props_paths()
                        elif col == 4 and shot_num in self.character_paths:
                            del self.character_paths[shot_num]
                            self.save_character_paths()

                    # 检查完成状态 (可能需要隐藏电影院列)
                    self.check_completion_and_update_columns()
                
                elif action_clear_all_storyboards and action == action_clear_all_storyboards:
                    # 清空所有分镜图
                    self.clear_all_storyboards()
                
                elif action_create_sora_char and action == action_create_sora_char:
                    self.create_sora_character(row)

                elif action_gen_video and action == action_gen_video:
                    # 获取选中行
                    selected_rows = set()
                    ranges = self.table.selectedRanges()
                    if ranges:
                        for r in ranges:
                             for i in range(r.topRow(), r.bottomRow() + 1):
                                 selected_rows.add(i)
                    
                    # 如果点击的行不在选中范围内，则只生成点击行
                    if row not in selected_rows:
                        selected_rows = {row}
                    
                    self.generate_video_batch(list(selected_rows))
                    
                elif action_clear_video and action == action_clear_video:
                    # 获取选中行
                    selected_rows = set()
                    ranges = self.table.selectedRanges()
                    if ranges:
                        for r in ranges:
                             for i in range(r.topRow(), r.bottomRow() + 1):
                                 selected_rows.add(i)
                    
                    if row not in selected_rows:
                        selected_rows = {row}
                    
                    self.clear_video_batch(list(selected_rows))

                elif action == action_gen_all:
                    self.open_storyboard_dialog(target_rows=None)
                elif action == action_gen_selected:
                    # 获取选中行号
                    rows = set()
                    for r in selected_ranges:
                        for i in range(r.topRow(), r.bottomRow() + 1):
                            rows.add(i)
                    if rows:
                        self.open_storyboard_dialog(target_rows=list(rows))

            def open_storyboard_dialog(self, target_rows=None):
                """打开分镜图生成对话框
                :param target_rows: 指定生成的行号列表，None表示生成所有行
                """
                # 修复信号连接问题：clicked信号会传递一个bool值，导致target_rows变为False
                if isinstance(target_rows, bool):
                    target_rows = None

                # 1. 检查谷歌节点连接
                if not hasattr(self, 'input_sockets') or not self.input_sockets:
                    QMessageBox.warning(None, "提示", "未找到输入接口")
                    return
                
                socket = self.input_sockets[0]
                if not socket.connections:
                    QMessageBox.warning(None, "提示", "请先连接谷歌剧本节点！")
                    return
                    
                connection = socket.connections[0]
                if not connection or not connection.source_socket:
                    return
                
                source_node = connection.source_socket.parent_node
                if not hasattr(source_node, 'node_title') or "谷歌剧本" not in source_node.node_title:
                    QMessageBox.warning(None, "提示", "连接的节点不是谷歌剧本节点！")
                    return

                # 2. 打开对话框
                dialog = StoryboardDialog(None)
                if dialog.exec():
                    if dialog.selection:
                        self.run_storyboard_generation(dialog.selection, source_node, target_rows)

            def clear_all_storyboards(self):
                """清空所有分镜图"""
                reply = QMessageBox.question(
                    None,
                    "确认清空",
                    "确定要清空所有分镜图吗？此操作不可撤销。",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                if reply != QMessageBox.Yes:
                    return
                
                # 清空所有行的分镜图列
                row_count = self.table.rowCount()
                for r in range(row_count):
                    self.set_cell_images(r, 7, [])
                
                # 清空缓存
                self.storyboard_paths.clear()
                self.save_storyboard_paths()
                
                # 更新表格状态
                self.check_completion_and_update_columns()
                
                print("[导演节点] 已清空所有分镜图")
                QMessageBox.information(None, "完成", "所有分镜图已清空")

            def update_storyboard_cell(self, row_idx, image_path, prompt):
                """分镜图生成完成回调，更新表格"""
                if row_idx < 0 or row_idx >= self.table.rowCount():
                    return
                
                # 获取或创建分镜图单元格 (Col 7)
                item = self.table.item(row_idx, 7)
                if not item:
                    item = QTableWidgetItem()
                    self.table.setItem(row_idx, 7, item)
                
                # 获取当前数据以保留第二张图
                current_paths = [None, None]
                old_data = item.data(Qt.UserRole)
                if old_data and isinstance(old_data, list):
                    if len(old_data) > 0: current_paths[0] = old_data[0]
                    if len(old_data) > 1: current_paths[1] = old_data[1]

                
                # 设置图片路径 (列表格式，以适配 ImageDelegate)
                if image_path and os.path.exists(image_path):
                    current_paths[0] = image_path
                    item.setData(Qt.UserRole, current_paths)
                    # 可以在 tooltip 中显示提示词
                    item.setToolTip(f"提示词: {prompt}")
                    
                    # 保存到缓存和文件
                    item_shot = self.table.item(row_idx, 0)
                    if item_shot:
                        shot_num = item_shot.text()
                        if shot_num:
                            self.storyboard_paths[shot_num] = current_paths
                            self.save_storyboard_paths()
                
                # 强制刷新
                self.table.update()
                
                # 检查是否全部完成
                self.check_completion_and_update_columns()
            
            def _cleanup_worker(self, worker):
                """清理已完成的 Worker"""
                if worker in self.sora_workers:
                    self.sora_workers.remove(worker)
                print(f"[导演节点] 视频生成批次完成，剩余运行批次: {len(self.sora_workers)}")

            def generate_video_batch(self, rows):
                """批量生成视频"""
                if not rows: return
                
                # 获取API配置
                settings = QSettings("GhostOS", "App")
                api_provider = settings.value("api/video_provider", "Sora2")
                
                # 获取附加提示词
                additional_prompt = get_additional_prompt()
                if additional_prompt:
                    print(f"[VideoGen] 已启用附加提示词: {additional_prompt}")
                
                tasks = []
                
                for r in rows:
                    # 检查分镜图 (Col 7)
                    item_sb = self.table.item(r, 7)
                    image_path = None
                    if item_sb:
                        data = item_sb.data(Qt.UserRole)
                        if data and isinstance(data, list):
                            # 优先使用第一张图，如果没有则使用第二张
                            for p in data:
                                if p and os.path.exists(p):
                                    image_path = p
                                    break
                    
                    if not image_path or not os.path.exists(image_path):
                        print(f"[VideoGen] 跳过第 {r+1} 行: 无分镜图")
                        continue

                    # 检查提示词 (Col 2 - 动画片场)
                    item_prompt = self.table.item(r, 2)
                    prompt = item_prompt.text() if item_prompt else ""
                    
                    if not prompt:
                        print(f"[VideoGen] 跳过第 {r+1} 行: 无提示词")
                        continue
                    
                    # 追加附加提示词
                    if additional_prompt:
                        prompt = f"{prompt}, {additional_prompt}"
                    
                    # 镜头号
                    item_shot = self.table.item(r, 0)
                    shot_text = item_shot.text() if item_shot else str(r+1)
                    
                    tasks.append({
                        'row_idx': r,
                        'prompt': prompt,
                        'image_path': image_path,
                        'shot_number': shot_text
                    })

                    # Debug: 显示视频生成提示词
                    print(f"[VideoGen] 镜头 {shot_text} 提示词: {prompt}")
                    
                    # 更新 UI 状态: 正在生成 (绿色)
                    item = self.table.item(r, 8)
                    if not item:
                        item = QTableWidgetItem()
                        self.table.setItem(r, 8, item)
                    
                    # 移除现有的播放按钮（如果正在重新生成）
                    self.table.removeCellWidget(r, 8)
                    
                    item.setText("正在生成...")
                    item.setForeground(QColor("green"))
                    item.setToolTip("正在请求视频生成API...")
                
                if not tasks:
                    QMessageBox.warning(None, "提示", "所选行中没有符合生成条件的任务（需包含分镜图和提示词）。")
                    return
                
                app_root = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
                output_dir = os.path.join(app_root, "video")
                
                # 创建新 Worker (支持并发，不弹出确认窗口)
                worker = Sora2Worker(api_provider, tasks, output_dir)
                worker.log_signal.connect(lambda msg: print(f"[VideoGen] {msg}"))
                worker.video_completed.connect(self.update_cinema_cell)
                worker.video_failed.connect(self.handle_video_error)
                worker.all_completed.connect(lambda: self._cleanup_worker(worker))
                
                self.sora_workers.append(worker)
                worker.start()
                
                print(f"[导演节点] 已启动 {len(tasks)} 个视频生成任务 ({api_provider})，当前并发任务数: {len(self.sora_workers)}")

            def generate_video_for_row(self, r):
                """为指定行生成视频 (已弃用，保留兼容性，转发到 batch)"""
                self.generate_video_batch([r])

            def handle_video_error(self, row_idx, error_msg):
                """处理视频生成错误"""
                if row_idx < 0 or row_idx >= self.table.rowCount():
                    return
                
                item = self.table.item(row_idx, 8)
                if not item:
                    item = QTableWidgetItem()
                    self.table.setItem(row_idx, 8, item)
                    
                # 移除可能存在的控件
                self.table.removeCellWidget(row_idx, 8)
                
                item.setText("生成失败")
                item.setForeground(QColor("red"))
                item.setToolTip(f"错误信息: {error_msg}")

            def on_sora2_clicked(self):
                """处理 SORA2 按钮点击事件"""
                row_count = self.table.rowCount()
                # 使用批量生成逻辑，传入所有行
                self.generate_video_batch(range(row_count))

            def set_cinema_cell_ui(self, row_idx, video_path):
                """设置电影院单元格的 UI (不涉及保存)"""
                # 设置视频路径
                item = self.table.item(row_idx, 8)
                if not item:
                    item = QTableWidgetItem()
                    self.table.setItem(row_idx, 8, item)
                
                # 检查是否需要更新，避免重复创建控件
                current_path = item.data(Qt.UserRole)
                existing_widget = self.table.cellWidget(row_idx, 8)
                
                if current_path == video_path and existing_widget:
                    return

                item.setText("")
                item.setToolTip(video_path)
                item.setData(Qt.UserRole, video_path) # Store path
                
                # 可以在这里添加播放按钮或图标
                # 使用自定义可拖拽控件
                container = DraggableVideoWidget(video_path)
                self.table.setCellWidget(row_idx, 8, container)
                # self.table.setRowHeight(row_idx, 40) # Adjust height if needed

            def clear_video_batch(self, rows):
                """批量清空视频"""
                for r in rows:
                    # 清空单元格控件
                    self.table.removeCellWidget(r, 8)
                    item = self.table.item(r, 8)
                    if item:
                        item.setText("")
                        item.setToolTip("")
                        item.setData(Qt.UserRole, None)
                    
                    # 清除缓存
                    item_shot = self.table.item(r, 0)
                    shot_number = item_shot.text() if item_shot else str(r+1)
                    if shot_number in self.video_paths:
                        del self.video_paths[shot_number]
                
                # 保存更改
                self.save_video_paths()


            def update_cinema_cell(self, row_idx, video_path, shot_number=None, video_url=None, task_id=None):
                """视频生成完成回调，更新电影院列"""
                print(f"[DEBUG] update_cinema_cell called: row={row_idx}, path={video_path}, shot={shot_number}, url={video_url}, task={task_id}")
                
                # 1. 优先保存数据 (使用 shot_number)
                saved = False
                if shot_number:
                     self.video_paths[shot_number] = video_path
                     self.save_video_paths()
                     saved = True
                
                # 2. 如果行号无效，尝试通过 shot_number 查找行号
                if row_idx < 0 or row_idx >= self.table.rowCount():
                    if shot_number:
                        print(f"[DEBUG] Invalid row {row_idx}, trying to find row for shot {shot_number}")
                        for r in range(self.table.rowCount()):
                            item = self.table.item(r, 0)
                            if item and item.text() == shot_number:
                                row_idx = r
                                print(f"[DEBUG] Found new row index: {row_idx}")
                                break
                
                # 3. 再次检查行号
                if row_idx < 0 or row_idx >= self.table.rowCount():
                     print(f"[DEBUG] Still invalid row index: {row_idx}, rowCount: {self.table.rowCount()}")
                     return

                # 4. 如果还没保存 (shot_number 为空的情况)，尝试从表格获取 shot_number 保存
                if not saved:
                    item_shot = self.table.item(row_idx, 0)
                    if item_shot:
                        shot_num = item_shot.text()
                        if shot_num:
                            print(f"[DEBUG] Saving video path for shot {shot_num} (from table)")
                            self.video_paths[shot_num] = video_path
                            self.save_video_paths()
                
                # 5. 更新 UI
                # 确保电影院列存在 (Col 8)
                if self.table.columnCount() <= 8:
                    self.table.setColumnCount(9)
                    item = QTableWidgetItem("🎥")
                    self.table.setHorizontalHeaderItem(8, item)
                    self.table.setColumnWidth(8, 120)
                
                self.set_cinema_cell_ui(row_idx, video_path)
                
                # Store Metadata for Sora Character creation
                if video_url and task_id:
                    item = self.table.item(row_idx, 8)
                    if item:
                        # UserRole + 1 for Metadata
                        item.setData(Qt.UserRole + 1, {'url': video_url, 'task_id': task_id})
                        print(f"[导演节点] 已存储Sora元数据到行 {row_idx}")

                        
                        # Save to persistent storage
                        shot_num = None
                        if shot_number:
                            shot_num = shot_number
                        else:
                            # Try to get shot number from table
                            item_shot = self.table.item(row_idx, 0)
                            if item_shot:
                                shot_num = item_shot.text()
                        
                        if shot_num:
                            print(f"[DEBUG] Saving metadata for shot {shot_num}")
                            self.video_metadata[shot_num] = {'url': video_url, 'task_id': task_id}
                            self.save_video_metadata()
                        
                self.table.update()

                # 检查是否所有视频都已生成完成
                all_completed = self.check_all_videos_completed()
                
                # 推送视频到连接的节点
                if hasattr(self, 'output_sockets'):
                    # 查找视频输出接口
                    for socket in self.output_sockets:
                        if socket.data_type == DataType.VIDEO:
                            for connection in socket.connections:
                                target_node = connection.target_socket.parent_node
                                if hasattr(target_node, 'receive_data'):
                                    if all_completed:
                                        # 所有视频生成完成，推送排序后的完整列表
                                        sorted_videos = self.get_sorted_video_list()
                                        print(f"[导演节点] ✅ 所有视频生成完成，推送 {len(sorted_videos)} 个视频到 {target_node.node_title}")
                                        target_node.receive_data(sorted_videos, DataType.VIDEO)
                                    else:
                                        # 实时推送单个视频（用于预览）
                                        print(f"[导演节点] 推送单个视频到 {target_node.node_title}")
                                        target_node.receive_data(video_path, DataType.VIDEO)
                            break

            def check_all_videos_completed(self):
                """检查是否所有分镜图对应的视频都已生成"""
                row_count = self.table.rowCount()
                if row_count == 0:
                    return False
                
                # 检查每一行的分镜图和视频状态
                for r in range(row_count):
                    # 检查是否有分镜图
                    storyboard_item = self.table.item(r, 6)
                    if not storyboard_item:
                        continue
                    
                    storyboard_data = storyboard_item.data(Qt.UserRole)
                    has_storyboard = False
                    if storyboard_data and isinstance(storyboard_data, list):
                        for img in storyboard_data:
                            if img and isinstance(img, str) and os.path.exists(img):
                                has_storyboard = True
                                break
                    
                    # 如果有分镜图，检查是否有对应的视频
                    if has_storyboard:
                        # 获取镜头号
                        shot_item = self.table.item(r, 0)
                        if shot_item:
                            shot_num = shot_item.text()
                            # 检查是否有对应的视频
                            if shot_num not in self.video_paths:
                                return False
                            video_path = self.video_paths[shot_num]
                            if not video_path or not os.path.exists(video_path):
                                return False
                
                # 所有有分镜图的镜头都有对应的视频
                return True
            
            def get_sorted_video_list(self):
                """获取按镜头号排序的视频列表"""
                video_list = []
                
                # 从表格按顺序收集视频
                for r in range(self.table.rowCount()):
                    shot_item = self.table.item(r, 0)
                    if shot_item:
                        shot_num = shot_item.text()
                        if shot_num in self.video_paths:
                            video_path = self.video_paths[shot_num]
                            if video_path and os.path.exists(video_path):
                                video_list.append(video_path)
                                print(f"[导演节点] 镜头 {shot_num}: {os.path.basename(video_path)}")
                
                print(f"[导演节点] 排序后的视频列表: 共 {len(video_list)} 个视频")
                return video_list

            def run_storyboard_generation(self, mode, google_node, target_rows=None):
                """执行分镜图生成"""
                print(f"[导演节点] 开始生成分镜图，模式: {mode}")
                
                # 1. 获取谷歌节点提示词列索引
                prompt_col_idx = -1
                for c in range(google_node.table.columnCount()):
                    header = google_node.table.horizontalHeaderItem(c)
                    if not header:
                        continue
                    header_text = header.text()
                    # 兼容多种写法：带空格、全角括号等
                    if ("提示词" in header_text and "CN" in header_text) or \
                       ("Painting Prompt" in header_text and "CN" in header_text):
                        prompt_col_idx = c
                        break
                
                if prompt_col_idx == -1:
                    QMessageBox.warning(None, "提示", f"在谷歌剧本节点中未找到 '提示词(CN)' 相关列！\n请检查列名是否包含 '提示词' 和 'CN'。")
                    return

                # 2. 收集任务数据
                tasks = []
                row_count = self.table.rowCount()
                
                rows_to_process = target_rows if target_rows is not None else range(row_count)
                
                for r in rows_to_process:
                    if r < 0 or r >= row_count:
                        continue

                    # 获取导演节点数据
                    # 镜头号
                    item_shot = self.table.item(r, 0)
                    shot_text = item_shot.text() if item_shot else str(r+1)
                    
                    # 动画片场 (Prompt Context)
                    item_studio = self.table.item(r, 2)
                    studio_text = item_studio.text() if item_studio else ""
                    
                    # 图片
                    images = []
                    # Character (Col 3)
                    item_char = self.table.item(r, 3)
                    if item_char:
                        data = item_char.data(Qt.UserRole)
                        if data and isinstance(data, list): images.extend(data)
                        elif data and isinstance(data, str): images.append(data)
                    
                    # Props (Col 4) - 添加道具图片作为参考图
                    item_prop = self.table.item(r, 4)
                    if item_prop:
                        data = item_prop.data(Qt.UserRole)
                        if data and isinstance(data, list): images.extend(data)
                        elif data and isinstance(data, str): images.append(data)
                        
                    # Scene (Col 5)
                    item_scene = self.table.item(r, 5)
                    if item_scene:
                        data = item_scene.data(Qt.UserRole)
                        if data and isinstance(data, list): images.extend(data)
                        elif data and isinstance(data, str): images.append(data)
                    
                    # 去重且过滤无效路径
                    images = list(dict.fromkeys([p for p in images if p and os.path.exists(p)]))
                    
                    # 获取谷歌节点对应的提示词
                    # 假设行号一一对应
                    google_prompt = ""
                    if r < google_node.table.rowCount():
                        item_p = google_node.table.item(r, prompt_col_idx)
                        if item_p:
                            google_prompt = item_p.text()
                    
                    if not google_prompt and not studio_text:
                        print(f"[导演节点] 跳过第 {r+1} 行: 无提示词")
                        continue
                        
                    # 组合提示词
                    # 如果有道具提示词，将其放在最前面
                    prop_prompt = ""
                    if shot_text in self.props_prompts:
                        prop_prompt = self.props_prompts[shot_text]
                    
                    if prop_prompt:
                        combined_prompt = f"{prop_prompt}\n{google_prompt}\n{studio_text}".strip()
                        print(f"[导演节点] 镜头 {shot_text}: 使用道具提示词 '{prop_prompt}'")
                    else:
                        combined_prompt = f"{google_prompt}\n{studio_text}".strip()
                        print(f"[导演节点] 镜头 {shot_text}: 无道具提示词")
                    
                    # Debug: 显示参考图信息
                    print(f"[导演节点] 镜头 {shot_text}: 参考图数量={len(images)}")
                    if images:
                        for idx, img_path in enumerate(images):
                            img_name = os.path.basename(img_path)
                            print(f"  - 参考图{idx+1}: {img_name}")
                    
                    tasks.append({
                        'row_idx': r,
                        'prompt': combined_prompt,
                        'images': images,
                        'mode': mode,
                        'shot_number': shot_text
                    })
                
                if not tasks:
                    QMessageBox.warning(None, "提示", "没有可生成的任务（可能是缺少提示词或数据为空）。")
                    return

                # 3. 启动 Worker
                settings = QSettings("GhostOS", "App")
                image_api = settings.value("api/image_provider", "BANANA")
                
                app_root = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
                config_file = ""
                if image_api == "BANANA":
                    config_file = os.path.join(app_root, "json", "gemini.json")
                elif image_api == "BANANA2":
                    config_file = os.path.join(app_root, "json", "gemini30.json")
                elif image_api == "Midjourney":
                    config_file = os.path.join(app_root, "json", "mj.json")
                
                self.storyboard_worker = StoryboardWorker(
                    image_api,
                    config_file,
                    tasks,
                    os.path.join("jpg", "storyboard_output"),
                )
                self.storyboard_worker.log_signal.connect(lambda msg: print(f"[Storyboard] {msg}"))
                self.storyboard_worker.image_completed.connect(self.update_storyboard_cell)
                self.storyboard_worker.start()
                
                QMessageBox.information(None, "提示", f"已启动 {len(tasks)} 个分镜图生成任务！请查看控制台日志或等待完成。")

            def create_sora_character(self, row):
                """创建Sora角色"""
                print(f"[CreateSoraChar] 开始创建角色 - 行号: {row}")
                item = self.table.item(row, 8)
                if not item:
                    print(f"[CreateSoraChar] 错误: 第 {row} 行没有 Item")
                    return
                
                data = item.data(Qt.UserRole + 1)
                print(f"[CreateSoraChar] 获取到的数据: {data}")
                
                if not data or not isinstance(data, dict):
                    print("[CreateSoraChar] 错误: 数据为空或格式不正确")
                    QMessageBox.warning(None, "提示", "该视频没有关联的Sora任务信息，无法创建角色。")
                    return
                
                video_url = data.get('url')
                task_id = data.get('task_id')
                print(f"[CreateSoraChar] Video URL: {video_url}, Task ID: {task_id}")
                
                if not video_url and not task_id:
                    print("[CreateSoraChar] 错误: 缺少 URL 和 Task ID")
                    QMessageBox.warning(None, "提示", "缺少视频URL或任务ID。")
                    return

                # Get API Config
                s = QSettings('GhostOS', 'App')
                api_key = s.value('providers/sora2/api_key', '')
                base_url = s.value('providers/sora2/base_url', 'https://api.vectorengine.ai')
                print(f"[CreateSoraChar] API Config - Key length: {len(api_key)}, Base URL: {base_url}")
                
                if not api_key:
                    print("[CreateSoraChar] 错误: API Key 未配置")
                    QMessageBox.warning(None, "错误", "请先在设置中配置Sora2 API密钥。")
                    return

                # Prepare Payload
                # Using 1.0s - 3.0s as default range
                payload = {
                    "timestamps": "1.0,3.0"
                }
                # 优先使用 task_id 以避免 URL 访问失败 (500 Error)
                if task_id:
                    payload["from_task"] = task_id
                elif video_url:
                    payload["url"] = video_url
                
                print(f"[CreateSoraChar] Payload: {payload}")
                
                # Show feedback
                QMessageBox.information(None, "提示", "正在后台创建Sora角色，请稍候...")
                
                # Create Thread
                print("[CreateSoraChar] 启动线程...")
                self._char_thread = CreateCharacterThread(api_key, base_url, payload)
                self._char_thread.finished_signal.connect(self.on_sora_char_created)
                self._char_thread.start()
                
            def on_sora_char_created(self, success, data, msg):
                 print(f"[CreateSoraChar] 线程结束 - Success: {success}, Msg: {msg}")
                 if success:
                     try:
                         print(f"[CreateSoraChar] 保存角色数据: {data}")
                         save_character(data)
                         QMessageBox.information(None, "成功", "Sora角色创建成功并已添加到角色库！")
                     except Exception as e:
                         print(f"[CreateSoraChar] 保存失败: {e}")
                         import traceback
                         traceback.print_exc()
                         QMessageBox.warning(None, "错误", f"角色保存失败: {str(e)}")
                 else:
                     print(f"[CreateSoraChar] API返回失败: {msg}")
                     QMessageBox.warning(None, "失败", f"创建角色失败: {msg}")
                 
                 # Clean up thread ref
                 self._char_thread = None

        return DirectorNodeImpl
