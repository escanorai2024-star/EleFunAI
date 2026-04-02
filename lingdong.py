"""
灵动智能体 - 无限画布工作空间
类似ComfyUI的可拖动画布，支持多种内容节点
"""

import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QComboBox, QFrame, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem, QGraphicsPixmapItem,
    QMessageBox, QFileDialog, QTextBrowser, QSplitter, QMenu, QGraphicsDropShadowEffect,
    QDialog, QTableWidgetItem, QGraphicsProxyWidget, QCompleter, QAbstractItemView
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer, QSettings, QEvent, QSize, QStringListModel
from PySide6.QtGui import (
    QFont, QPainter, QColor, QPen, QBrush, QPixmap, 
    QWheelEvent, QMouseEvent, QPainterPath, QAction, QLinearGradient, QTextCursor, QIcon
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QSvgWidget

# 导入词语优化模块
from lingdongWordPost import optimize_word

# 导入文字节点模块
from lingdongTXT import TextNode as TextNodeFactory

# 导入图片节点模块
from lingdongpng import ImageNode as ImageNodeFactory
from GONGZUOTAI_back import WorkbenchToggleButton
from database_save import LibraryPanel, LibraryToggleButton

# 导入视频节点模块
from lingdongvideo import VideoNode as VideoNodeFactory

# 导入表格节点模块
from lingdongstoryboard import StoryboardNode as StoryboardNodeFactory

# 导入人物表格节点模块（AI生成）- 已移除
# from lingdongpeople import create_people_node, generate_all_people_from_storyboard

# 导入人物节点模块（手动创建）- 已移除
# from lingdongRenwujiedian import create_people_node as PeopleNodeFactory

# 导入模型选择节点模块
from lingdongmodelxuanze import ModelSelectionNode as ModelSelectionNodeFactory

# 导入谷歌剧本节点模块
from lingdonggooglejuben import GoogleScriptNode as GoogleScriptNodeFactory

# 导入剧本人物节点模块
from LDjubenrenwu import ScriptCharacterNode as ScriptCharacterNodeFactory

# 导入自动文本节点管理器
from work_open_GPT import AutoTextNodeManager

# 导入聊天节点上下文管理器
from chat_abot import ChatNodeContextManager
from chat_image_upload import ChatImageUploadManager

# 导入草稿生成模块
from lingdongDraft import DraftGenerator

# 导入谷歌提示词列模块
try:
    from lingdonggugetishici import add_prompt_column
except ImportError:
    print("Warning: lingdonggugetishici module not found")
    def add_prompt_column(node):
        print("add_prompt_column not available")

# 导入导演节点模块
from guge_TV_GO import DirectorNode as DirectorNodeFactory

# 导入连线系统
from lingdongconnect import (
    Socket, SocketType, DataType, Connection, ConnectionManager, ConnectableNode
)

# 导入绘画提示词生成模块
from lingdongPrompt import DrawingPromptGenerator

# 导入草稿生成模块
from lingdongDraft import DraftGenerator

# 导入视频拆分模块
from video_image_chaifen import VideoSplitDialog, is_video_connected_to_image

# 导入案例管理挂件
from lingdongANli import CaseManagerWidget


# 导入抽卡节点模块
from chouka import GachaNodeFactory


# ==================== ChatWorker AI聊天工作线程 ====================
from PySide6.QtCore import QThread, Signal

class ChatWorker(QThread):
    """AI聊天工作线程"""
    response_received = Signal(str)
    chunk_received = Signal(str)
    error_occurred = Signal(str)
    finished = Signal()
    
    def __init__(self, provider, model, messages, api_key, api_url, hunyuan_api_url):
        super().__init__()
        # Register to global registry
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_chat_workers'):
                app._active_chat_workers = []
            app._active_chat_workers.append(self)
        self.finished.connect(self._cleanup_worker)

        self.provider = provider
        self.model = model
        self.messages = messages
        self.api_key = api_key
        if provider == "Hunyuan":
            self.api_url = hunyuan_api_url
        else:
            self.api_url = api_url
        self._stop_requested = False

    def _cleanup_worker(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app and hasattr(app, '_active_chat_workers'):
            if self in app._active_chat_workers:
                app._active_chat_workers.remove(self)
        self.deleteLater()
    
    def stop(self):
        self._stop_requested = True
    
    def run(self):
        try:
            print(f"[ChatWorker] Start request: {self.model} to {self.api_url}")
            import http.client
            import ssl
            import json as _json
            from urllib.parse import urlparse
            
            parsed = urlparse(self.api_url)
            host = parsed.netloc or parsed.path.split('/')[0]
            scheme = parsed.scheme
            
            print(f"[ChatWorker] Host: {host}, Scheme: {scheme}")
            
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            payload = {
                "model": self.model,
                "messages": self.messages,
                "temperature": 0.7,
                "max_tokens": 8192,
                "stream": True
            }
            
            # Decide connection type based on scheme
            if scheme == 'http':
                conn = http.client.HTTPConnection(host, timeout=300)
            else:
                context = ssl.create_default_context()
                conn = http.client.HTTPSConnection(host, context=context, timeout=300)
            
            print(f"[ChatWorker] Sending request...")
            # Use parsed path if available and valid, else default
            # Note: Many APIs use /v1/chat/completions relative to host.
            # If user provided full path in api_url, we might need to adjust.
            # But standard practice in this codebase seems to be api_url is base.
            conn.request('POST', '/v1/chat/completions', _json.dumps(payload), headers)
            res = conn.getresponse()
            print(f"[ChatWorker] Response status: {res.status}")
            
            if res.status == 200:
                ct = res.getheader('Content-Type') or ''
                print(f"[ChatWorker] Content-Type: {ct}")
                full_content = ""
                
                # Check for streaming response
                # Note: Some proxies might not set Content-Type to text/event-stream but still stream.
                # We assume streaming because we requested stream=True.
                
                for line in res:
                    if self._stop_requested:
                        print("[ChatWorker] Stop requested")
                        break
                    
                    line = line.decode('utf-8').strip()
                    if not line or line == "data: [DONE]":
                        continue
                    
                    if line.startswith("data: "):
                        json_str = line[6:]
                        try:
                            chunk_data = _json.loads(json_str)
                            if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                                delta = chunk_data['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    full_content += content
                                    self.chunk_received.emit(content)
                        except _json.JSONDecodeError:
                            print(f"[ChatWorker] JSON Parse Error: {json_str}")
                            continue
                
                self.response_received.emit(full_content)
            else:
                error_data = res.read().decode('utf-8')
                print(f"[ChatWorker] Error data: {error_data}")
                self.error_occurred.emit(f"API错误 ({res.status}): {error_data[:200]}")
            
            conn.close()
            
        except Exception as e:
            print(f"[ChatWorker] Exception: {str(e)}")
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(f"请求失败: {str(e)}")
        finally:
            self.finished.emit()


# ==================== SVG图标定义 ====================
SVG_TEXT_ICON = '''<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M4 7h16M12 7v13m-5 0h10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
</svg>'''

SVG_IMAGE_ICON = '''<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2"/>
<circle cx="8.5" cy="8.5" r="1.5" fill="currentColor"/>
<path d="M3 16l5-5 3 3 5-5 5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
</svg>'''

SVG_VIDEO_ICON = '''<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<rect x="2" y="5" width="14" height="14" rx="2" stroke="currentColor" stroke-width="2"/>
<path d="M16 10l6-3v10l-6-3z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
</svg>'''

SVG_DOC_ICON = '''<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" stroke-width="2"/>
<path d="M14 2v6h6M16 13H8m8 4H8m2-8H8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
</svg>'''

SVG_TABLE_ICON = '''<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2"/>
<path d="M3 9h18M3 15h18M9 3v18" stroke="currentColor" stroke-width="2"/>
</svg>'''


# ==================== 调整大小手柄 ====================
class ResizeHandle(QGraphicsItem):
    def __init__(self, parent):
        super().__init__(parent)
        self.setParentItem(parent)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptHoverEvents(True)
        self.parent_node = parent
        self.setZValue(999) # 确保在最上层
        self.handle_size = 20
        self.update_position()

    def boundingRect(self):
        return QRectF(0, 0, self.handle_size, self.handle_size)

    def paint(self, painter, option, widget):
        if self.parent_node.is_collapsed:
            return
            
        painter.setPen(QPen(QColor("#cccccc"), 2))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 绘制两条斜线
        s = self.handle_size
        painter.drawLine(s - 15, s - 5, s - 5, s - 15)
        painter.drawLine(s - 9, s - 5, s - 5, s - 9)

    def mousePressEvent(self, event):
        self.start_pos = event.screenPos()
        self.start_rect = self.parent_node.rect()
        event.accept()

    def mouseMoveEvent(self, event):
        diff = event.screenPos() - self.start_pos
        new_width = max(200, self.start_rect.width() + diff.x())
        new_height = max(100, self.start_rect.height() + diff.y())
        
        self.parent_node.setRect(0, 0, new_width, new_height)
        if hasattr(self.parent_node, 'expanded_height'):
            self.parent_node.expanded_height = new_height
        
        self.update_position()
        
    def update_position(self):
        rect = self.parent_node.rect()
        self.setPos(rect.width() - self.handle_size, rect.height() - self.handle_size)

# ==================== 画布节点基类 ====================
class CanvasNode(QGraphicsRectItem):
    """画布节点基类 - 可拖动、可选中、可删除、可连接"""
    
    def __init__(self, x, y, width, height, title, icon_svg):
        super().__init__(0, 0, width, height)
        self.node_title = title
        self.icon_svg = icon_svg
        
        # 设置位置
        self.setPos(x, y)
        
        # 设置标志
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)  # 支持键盘焦点
        
        # 创建调整大小手柄
        self.resize_handle = ResizeHandle(self)
        
        # 阴影效果 (Material Elevation)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 30))
        self.setGraphicsEffect(shadow)
        
        # 样式设置
        self.setPen(QPen(QColor("#DADCE0"), 1.5))
        self.setBrush(QBrush(QColor("#ffffff")))
        
        # 自定义头部颜色
        self.header_color = None
        
        # 创建标题文本
        self.title_text = QGraphicsTextItem(self)
        self.title_text.setPlainText(title)
        self.title_text.setDefaultTextColor(QColor("#3C4043"))
        self.title_text.setFont(QFont("Microsoft YaHei UI", 10, QFont.Weight.Bold))
        self.title_text.setPos(50, 12)
        
        # 选中状态
        self.is_selected = False
        
        # 可编辑内容（子类覆盖）
        self.editable_text = None
        
        # ========== 连接功能 ==========
        self.input_sockets = []   # 输入接口列表
        self.output_sockets = []  # 输出接口列表
        
        # 自动添加默认接口（左侧输入，右侧输出）
        self._auto_create_sockets()

        # ========== 折叠功能 ==========
        self.is_collapsed = False
        self.expanded_height = height
        self.collapsed_height = 48
        
        # 折叠/展开按钮
        self.toggle_btn = QGraphicsTextItem(self)
        self.toggle_btn.setPlainText("▼")
        self.toggle_btn.setDefaultTextColor(QColor("#1a73e8"))
        self.toggle_btn.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.toggle_btn.setPos(width - 30, 10)
        # 允许鼠标事件以便点击
        self.toggle_btn.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        # 拦截鼠标点击事件
        self.toggle_btn.mousePressEvent = lambda e: self.toggle_collapse()
    
    def set_header_color(self, color):
        """设置自定义头部颜色"""
        if isinstance(color, str):
            self.header_color = QColor(color)
        else:
            self.header_color = color
        self.update()

    def mousePressEvent(self, event):
        """处理鼠标点击事件"""
        # 修复输入框/表格焦点问题：如果点击了代理控件，优先处理，不让父节点拦截
        for child in self.childItems():
            if isinstance(child, QGraphicsProxyWidget):
                # 检查点击位置是否在控件内
                if child.contains(child.mapFromParent(event.pos())):
                    child.setFocus()
                    # 确保场景也将焦点给它
                    if self.scene():
                        self.scene().setFocusItem(child)
                    
                    # 既然点击了内部控件，就不应该触发节点的移动或选中逻辑
                    # 直接返回，不再调用 super().mousePressEvent(event)
                    # 注意：这假设 ProxyWidget 会通过其他机制（如事件过滤或直接分发）接收事件
                    # 如果 ProxyWidget 之前因为某种原因没收到事件，这里仅仅 return 可能还不够
                    # 但这至少解决了"点击输入框却变成拖动节点"的问题
                    return

        super().mousePressEvent(event)

    def setRect(self, *args):
        """重写setRect以在大小改变时更新接口位置"""
        super().setRect(*args)
        
        # 更新调整大小手柄位置
        if hasattr(self, 'resize_handle'):
            self.resize_handle.update_position()
            
        # 只有在初始化完成后才更新（避免__init__中调用出错）
        if hasattr(self, 'input_sockets') and hasattr(self, 'output_sockets'):
            self.update_socket_positions()
            self.update_connections()

    def _auto_create_sockets(self):
        """自动创建默认接口"""
        if getattr(self, "disable_auto_sockets", False):
            return
        # 根据节点类型自动判断数据类型
        data_type = DataType.ANY
        if "文字" in self.node_title or "文本" in self.node_title:
            data_type = DataType.TEXT
        elif "图片" in self.node_title:
            data_type = DataType.IMAGE
        elif "视频" in self.node_title:
            data_type = DataType.VIDEO
        elif "表格" in self.node_title or "分镜" in self.node_title:
            data_type = DataType.TABLE
        
        # 添加一个输入和一个输出接口
        self.add_input_socket(data_type, "输入")
        self.add_output_socket(data_type, "输出")
    
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
        """获取输出数据（子类可以覆盖）"""
        # 默认返回节点标题
        return self.node_title
    
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
    
    def toggle_collapse(self):
        """切换折叠/展开状态"""
        self.is_collapsed = not self.is_collapsed
        self.toggle_btn.setPlainText("▶" if self.is_collapsed else "▼")
        
        if self.is_collapsed:
            # 记录当前高度以便恢复
            if self.rect().height() > self.collapsed_height:
                self.expanded_height = self.rect().height()
            
            # 设置为折叠高度
            self.setRect(0, 0, self.rect().width(), self.collapsed_height)
            
            # 隐藏内容 items
            self._set_content_visible(False)
        else:
            # 恢复展开高度
            self.setRect(0, 0, self.rect().width(), self.expanded_height)
            
            # 显示内容 items
            self._set_content_visible(True)
            
        # 更新接口位置和连接线
        self.update_socket_positions()
        self.update_connections()

    def _set_content_visible(self, visible):
        """设置内容可见性"""
        # 保持可见的 items
        keep_visible = [
            self.title_text, 
            self.toggle_btn,
        ]
        # 添加 sockets 到保持可见列表
        keep_visible.extend(self.input_sockets)
        keep_visible.extend(self.output_sockets)
        
        # 遍历所有子 item
        for item in self.childItems():
            # 如果不在保持可见列表中，则设置可见性
            if item not in keep_visible:
                if not visible:
                    # 记录当前可见性
                    is_currently_visible = item.isVisible()
                    item.setData(0, is_currently_visible) # Key 0 for visibility
                    item.setVisible(False)
                else:
                    # 恢复之前的可见性
                    was_visible = item.data(0)
                    if was_visible is None: # 如果没有记录，默认为 True
                         was_visible = True
                    item.setVisible(was_visible)
    
    def paint(self, painter, option, widget):
        """自定义绘制"""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        path = QPainterPath()
        path.addRoundedRect(rect, 16, 16)
        
        # 获取背景色
        bg_color = self.brush().color()
        is_dark = bg_color.lightness() < 128
        
        # 绘制背景
        painter.fillPath(path, bg_color)
        
        # 绘制头部 (顶部圆角)
        header_height = 48
        header_path = QPainterPath()
        header_path.moveTo(rect.left(), rect.top() + 16)
        header_path.arcTo(rect.left(), rect.top(), 32, 32, 180, -90) # Top-left corner
        header_path.lineTo(rect.right() - 16, rect.top())
        header_path.arcTo(rect.right() - 32, rect.top(), 32, 32, 90, -90) # Top-right corner
        header_path.lineTo(rect.right(), rect.top() + header_height)
        header_path.lineTo(rect.left(), rect.top() + header_height)
        header_path.closeSubpath()
        
        # 头部渐变
        header_gradient = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + header_height))
        
        if hasattr(self, 'header_color') and self.header_color:
            # 自定义颜色
            header_gradient.setColorAt(0, self.header_color.lighter(110))
            header_gradient.setColorAt(1, self.header_color)
            
            # 判断亮度决定文字颜色
            if self.header_color.lightness() < 128:
                self.title_text.setDefaultTextColor(QColor("#FFFFFF"))
                icon_color = QColor("#FFFFFF")
            else:
                self.title_text.setDefaultTextColor(QColor("#3C4043"))
                icon_color = self.header_color.darker(150)
            
            divider_color = self.header_color.darker(110)
            border_color = self.header_color
            icon_bg_color = QColor(255, 255, 255, 128) # 半透明白色
            
        elif is_dark:
            # 深色模式
            header_gradient.setColorAt(0, QColor("#2a2a2a"))
            header_gradient.setColorAt(1, QColor("#222222"))
            self.title_text.setDefaultTextColor(QColor("#FFFFFF"))
            divider_color = QColor("#333333")
            border_color = QColor("#333333")
            icon_bg_color = QColor("#333333")
            icon_color = QColor("#00ff88")
        else:
            # 浅色模式
            header_gradient.setColorAt(0, QColor("#F8F9FA"))
            header_gradient.setColorAt(1, QColor("#EFF1F3"))
            self.title_text.setDefaultTextColor(QColor("#3C4043"))
            divider_color = QColor("#E8EAED")
            border_color = QColor("#DADCE0")
            icon_bg_color = QColor("#E8F0FE")
            icon_color = QColor("#1967D2")

        painter.fillPath(header_path, header_gradient)
        
        # 绘制边框
        if self.isSelected():
            painter.setPen(QPen(QColor("#1A73E8"), 2.5))  # Google Blue
            painter.drawPath(path)
        else:
            painter.setPen(QPen(border_color, 1.5))
            painter.drawPath(path)
            
        # 头部底部分割线
        painter.setPen(QPen(divider_color, 1))
        painter.drawLine(rect.left(), rect.top() + header_height, rect.right(), rect.top() + header_height)
        
        # 绘制图标背景 (圆形)
        icon_rect = QRectF(14, 10, 28, 28)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(icon_bg_color))
        painter.drawEllipse(icon_rect)
        
        # 绘制图标（简化版）
        painter.setPen(QPen(icon_color, 2))
        font = painter.font()
        font.setPixelSize(14)
        font.setBold(True)
        painter.setFont(font)
        
        if "T" in self.node_title or "文字" in self.node_title:
            painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, "T")
        elif "图片" in self.node_title:
            r = icon_rect.adjusted(6, 7, -6, -7)
            painter.drawRoundedRect(r, 2, 2)
            painter.drawEllipse(r.center(), 2, 2)
        elif "视频" in self.node_title:
            painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, "▶")
        elif "人物" in self.node_title or "角色" in self.node_title:
            painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, "👤")
        elif "地点" in self.node_title or "环境" in self.node_title:
            painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, "📍")
        elif "模型" in self.node_title:
            painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, "◆")
        elif "表格" in self.node_title or "分镜" in self.node_title:
            painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, "⊞")
        elif "谷歌剧本" in self.node_title:
            painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, "G")
    
    def mouseDoubleClickEvent(self, event):
        """双击事件 - 子类可以覆盖以实现编辑功能"""
        super().mouseDoubleClickEvent(event)


# ==================== 动态创建文字节点 ====================
# 从 lingdongTXT 模块导入并创建 TextNode 类
TextNode = TextNodeFactory.create_text_node(CanvasNode)

# ==================== 动态创建图片节点 ====================
# 从 lingdongpng 模块导入并创建 ImageNode 类
ImageNode = ImageNodeFactory.create_image_node(CanvasNode)

# ==================== 动态创建视频节点 ====================
# 从 lingdongvideo 模块导入并创建 VideoNode 类
VideoNode = VideoNodeFactory.create_video_node(CanvasNode)

# ==================== 动态创建表格节点 ====================
# 从 lingdongstoryboard 模块导入并创建 StoryboardNode 类
StoryboardNode = StoryboardNodeFactory.create_storyboard_node(CanvasNode)

# ==================== 动态创建人物节点 ====================
# 已移除
# PeopleNode = PeopleNodeFactory(CanvasNode)

# ==================== 动态创建模型选择节点 ====================
# 从 lingdongmodelxuanze 模块导入并创建 ModelSelectionNode 类
ModelSelectionNode = ModelSelectionNodeFactory.create_node(CanvasNode)

# ==================== 动态创建谷歌剧本节点 ====================
# 从 lingdonggooglejuben 模块导入并创建 GoogleScriptNode 类
GoogleScriptNode = GoogleScriptNodeFactory.create_node(CanvasNode)

# ==================== 动态创建剧本人物节点 ====================
# 从 LDjubenrenwu 模块导入并创建 ScriptCharacterNode 类
ScriptCharacterNode = ScriptCharacterNodeFactory.create_node(CanvasNode)

# ==================== 动态创建地点节点 ====================
# 从 didian 模块导入并创建 LocationNode 类
from didian import LocationNode as LocationNodeFactory
LocationNode = LocationNodeFactory.create_node(CanvasNode)

# ==================== 动态创建清理节点 ====================
# 从 Cleaning 模块导入并创建 CleaningNode 类
from Cleaning import CleaningNode as CleaningNodeFactory
from Geminianalyze import GeminiAnalyzeNodeFactory
CleaningNode = CleaningNodeFactory.create_node(CanvasNode)
GeminiAnalyzeNode = GeminiAnalyzeNodeFactory.create_node(CanvasNode)

# ==================== 动态创建抽卡节点 ====================
# 从 chouka 模块导入并创建 GachaNode 类
GachaNode = GachaNodeFactory.create_node(CanvasNode)


# ==================== 其他节点类型 ====================
# DocumentNode已被PeopleNode替代


class TableNode(CanvasNode):
    """表格节点 - 用于显示分镜脚本"""
    def __init__(self, x, y, table_data=None):
        # 动态计算表格大小 (加宽以容纳更多内容)
        initial_width = 1400  # 从1200增加到1400
        initial_height = 800  # 从600增加到800
        super().__init__(x, y, initial_width, initial_height, "分镜表格", SVG_TABLE_ICON)
        
        # 强制设置为浅色主题 (覆盖可能继承的默认值)
        self.setBrush(QBrush(QColor("#ffffff")))
        self.setPen(QPen(QColor("#DADCE0"), 1.5))
        
        # 表格数据 [{'镜头号': '1', '景别': '全景', ...}, ...]
        self.table_data = table_data or []
        
        # 创建表格显示区域
        self.table_html = QGraphicsTextItem(self)
        self.table_html.setDefaultTextColor(QColor("#202124")) # 改为深色文字
        self.table_html.setPos(20, 60)  # 增加顶部和左侧边距
        self.table_html.setTextWidth(initial_width - 40)
        
        # 设置表格内容
        self.update_table_display()
    
    def update_table_display(self):
        """更新表格显示"""
        if not self.table_data:
            self.table_html.setHtml("""
                <div style='color: #5f6368; padding: 40px; text-align: center; font-family: "Microsoft YaHei UI";'>
                    <p style='font-size: 14px;'>暂无分镜数据</p>
                </div>
            """)
            return
        
        # 生成HTML表格 - Android Material Design Light 风格
        # 使用 div 容器模拟圆角表格
        html = '''
        <div style="background-color: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e0e0e0;">
            <table style="width: 100%; border-collapse: collapse; border-spacing: 0; 
                          font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif; 
                          font-size: 13px; line-height: 1.6; color: #202124;">
        '''
        
        # 表头
        html += '<thead style="background-color: #f8f9fa;"><tr>'
        headers = ['镜号', '时间码', '景别', '画面内容', '人物', '人物关系/构图', '地点/环境', '运镜', '台词/音效', '备注']
        # 定义各列宽度比例
        widths = ['5%', '8%', '7%', '20%', '10%', '10%', '10%', '10%', '10%', '10%']
        
        for i, (header, width) in enumerate(zip(headers, widths)):
            # 表头样式：加粗，深色，底边框 (使用蓝色 #1a73e8)
            style = f'padding: 14px 16px; font-weight: 700; text-align: left; color: #202124; border-bottom: 2px solid #1a73e8; width: {width};'
            html += f'<th style="{style}">{header}</th>'
        html += '</tr></thead>'
        
        # 表体
        html += '<tbody>'
        for index, row in enumerate(self.table_data):
            # 隔行变色 (浅色)
            bg_color = "#ffffff" if index % 2 == 0 else "#f8f9fa"
            html += f'<tr style="background-color: {bg_color};">'
            
            for i, header in enumerate(headers):
                value = row.get(header, '')
                cell_style = 'padding: 14px 16px; border-bottom: 1px solid #f1f3f4; vertical-align: top;'
                
                # 特殊列样式处理
                content = value
                if header == '镜号': # 镜号 - 蓝色徽章 (Light Mode)
                    content = f'<span style="display: inline-block; background-color: #e8f0fe; color: #1967d2; border: 1px solid #d2e3fc; padding: 2px 8px; border-radius: 12px; font-weight: bold; font-size: 12px;">{value}</span>'
                elif header == '景别': # 景别 - 标签风格 (Light Mode)
                    if "全" in value or "远" in value:
                        bg, color = "#e6f4ea", "#137333" # Green
                    elif "中" in value:
                        bg, color = "#fef7e0", "#ea8600" # Yellow/Orange
                    else:
                        bg, color = "#fce8e6", "#c5221f" # Red
                    content = f'<span style="display: inline-block; background-color: {bg}; color: {color}; padding: 2px 6px; border-radius: 4px; font-size: 12px;">{value}</span>'
                elif header == '画面内容': # 画面内容 - 加黑
                     cell_style += ' font-weight: 500;'
                
                html += f'<td style="{cell_style}">{content}</td>'
            html += '</tr>'
        html += '</tbody></table></div>'
        
        self.table_html.setHtml(html)
        
        # 根据内容调整节点大小
        content_height = self.table_html.boundingRect().height()
        new_height = max(800, content_height + 100)  # 最小高度800，留足底部空间
        self.setRect(0, 0, 1400, new_height)
        self.table_html.setTextWidth(1400 - 40)
    
    def set_table_data(self, data):
        """设置表格数据"""
        self.table_data = data
        self.update_table_display()


# ==================== 无限画布视图 ====================
class InfiniteCanvasView(QGraphicsView):
    """无限画布视图 - 支持拖动、缩放、删除节点、连接节点"""
    
    node_selected = Signal(object)  # 节点选中信号
    canvas_clicked = Signal()  # 画布点击信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 创建场景
        self.scene = QGraphicsScene()
        # 设置一个足够大的场景范围，让用户感觉是无限的
        # 使用 -100000 到 100000 应该足够覆盖大部分用例
        self.scene.setSceneRect(-100000, -100000, 200000, 200000)
        self.setScene(self.scene)
        
        # 连接场景的选中改变信号
        self.scene.selectionChanged.connect(self.on_selection_changed)
        
        # 设置视图属性
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        
        # 背景颜色
        self.setStyleSheet("background-color: #ffffff;")
        
        # 拖动状态
        self.is_panning = False
        self.last_pan_point = QPointF()
        
        # 缩放范围
        self.zoom_factor = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 3.0
        
        self.show_grid = False
        if self.show_grid:
            self.draw_grid()
        
        # 启用键盘焦点
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # 启用拖放
        self.setAcceptDrops(True)
        
        # ========== 连接功能 ==========
        self.connection_manager = ConnectionManager(self.scene)
        self.is_dragging_connection = False
        self.hover_socket = None
        
        # 连接信号
        self.connection_manager.connection_created.connect(self.on_connection_created)
        self.connection_manager.connection_removed.connect(self.on_connection_removed)
        
        # ========== 撤销功能 ==========
        self.undo_stack = []  # 撤销栈：存储操作历史
        self.max_undo_steps = 50  # 最大撤销步数
        
        # ========== 节点计数器（用于自动命名）==========
        self.storyboard_counter = 0  # 分镜脚本节点计数器
        
        # ========== 剪贴板功能 ==========
        self.clipboard_data = []
        self.paste_offset_count = 0
        
        # print("[画布] 节点连线功能已启用")
        # print("[画布] 撤销功能已启用 (Ctrl+Z)")
    
    def draw_grid(self):
        """绘制网格背景"""
        # 添加细网格
        for x in range(-5000, 5000, 50):
            line = self.scene.addLine(x, -5000, x, 5000, QPen(QColor("#e6f4ea"), 1))
            line.setZValue(-1000)
        
        for y in range(-5000, 5000, 50):
            line = self.scene.addLine(-5000, y, 5000, y, QPen(QColor("#e6f4ea"), 1))
            line.setZValue(-1000)
        
        # 添加粗网格
        for x in range(-5000, 5000, 200):
            line = self.scene.addLine(x, -5000, x, 5000, QPen(QColor("#c8e6c9"), 2))
            line.setZValue(-999)
        
        for y in range(-5000, 5000, 200):
            line = self.scene.addLine(-5000, y, 5000, y, QPen(QColor("#c8e6c9"), 2))
            line.setZValue(-999)
    
    def keyPressEvent(self, event):
        """键盘事件 - Delete删除、Ctrl+Z撤销、Ctrl+C复制、Ctrl+V粘贴"""
        
        # 导入外部删除逻辑 (用户请求)
        try:
            import deteled
            if deteled.handle_delete(self, event):
                event.accept()
                return
        except Exception as e:
            print(f"[KeyError] deteled.py execution failed: {e}")
            import traceback
            traceback.print_exc()

        # 检查是否有输入控件获取了焦点
        focus_item = self.scene.focusItem()
        app_focus_widget = QApplication.focusWidget()
        
        # 如果场景中有焦点项是代理控件，或者应用程序焦点在非视图组件上(修复输入框焦点不同步问题)
        if (focus_item and isinstance(focus_item, QGraphicsProxyWidget)) or \
           (app_focus_widget and app_focus_widget != self):
            # 如果焦点在代理控件上（如输入框、表格），则不处理视图级快捷键，直接传递给控件
            super().keyPressEvent(event)
            return

        # Ctrl+C 复制
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_C:
            self.copy_selected_nodes()
            event.accept()
            return
            
        # Ctrl+V 粘贴
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_V:
            self.paste_nodes()
            event.accept()
            return

        # Ctrl+Z 撤销
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_Z:
            self.undo_last_operation()
            event.accept()
            return
        
        # Delete 或 Backspace 删除选中项
        # 已通过 deteled.py 处理，这里保留作为Fallback
        if event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            # 只有当 deteled.py 没有处理时才会走到这里（通常不会，除非导入失败）
            pass
        
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        # 优先让 Item 处理 (如节点内的上传区域)
        super().dragEnterEvent(event)
        if event.isAccepted():
            return

        md = event.mimeData()
        # 资料库拖拽: 只能拖到节点里，不能拖到空白处
        if md.hasFormat("application/x-ghost-library-image"):
            event.ignore()
        # 外部文件: 可以拖到空白处生成节点
        elif md.hasUrls():
            event.accept()

    def dragMoveEvent(self, event):
        # 优先让 Item 处理
        super().dragMoveEvent(event)
        if event.isAccepted():
            return

        md = event.mimeData()
        if md.hasFormat("application/x-ghost-library-image"):
            event.ignore()
        elif md.hasUrls():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()

    def dropEvent(self, event):
        # 优先让 Item 处理
        super().dropEvent(event)
        if event.isAccepted():
            return

        md = event.mimeData()
        # 资料库拖拽: 如果 Item 没处理，View 也不处理 (忽略)
        if md.hasFormat("application/x-ghost-library-image"):
            event.ignore()
            return
            
        # 外部文件: 生成节点
        if md.hasUrls():
            urls = md.urls()
            if urls:
                file_path = urls[0].toLocalFile()
                # event.position() 是相对于 View 的坐标
                pos = self.mapToScene(event.position().toPoint())
                ext = os.path.splitext(file_path)[1].lower()
                if ext in ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp']:
                    try:
                        node = ImageNode(pos.x(), pos.y())
                        node.load_image(file_path)
                        self.scene.addItem(node)
                        print(f"[画布] 拖拽创建图片节点: {file_path}")
                    except Exception as e:
                        print(f"[画布] 创建图片节点失败: {e}")
                elif ext in ['.txt', '.csv']:
                    try:
                        GoogleScriptNodeClass = GoogleScriptNodeFactory.create_node(CanvasNode)
                        node = GoogleScriptNodeClass(pos.x(), pos.y())
                        node.load_script(file_path)
                        self.scene.addItem(node)
                        print(f"[画布] 拖拽创建谷歌剧本节点: {file_path}")
                    except Exception as e:
                        print(f"[画布] 创建谷歌剧本节点失败: {e}")
            event.accept()
    
    def contextMenuEvent(self, event):
        """右键菜单"""
        # 如果点击了图形项，则不处理（交给图形项自己处理）
        if self.itemAt(event.pos()):
            super().contextMenuEvent(event)
            return
            
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #ffffff;
                color: #333333;
                border: 1px solid #dcdcdc;
                padding: 5px;
            }
            QMenu::item {
                padding: 5px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #e8f0fe;
                color: #1967d2;
            }
        """)
        
        # 获取鼠标在场景中的位置
        mouse_pos = self.mapToScene(event.pos())
        
        # 添加菜单项
        action_text = menu.addAction("📝 新建文本节点")
        action_image = menu.addAction("🖼️ 新建图片节点")
        action_video = menu.addAction("🎬 新建视频节点")
        menu.addSeparator()
        action_google = menu.addAction("G 新建谷歌剧本节点")
        action_storyboard = menu.addAction("⊞ 新建分镜表格")
        menu.addSeparator()
        action_character = menu.addAction("👤 新建剧本人物节点")
        action_director = menu.addAction("🎬 新建导演节点")
        action_location = menu.addAction("🏔️ 新建地点/环境节点")
        action_cleaning = menu.addAction("🧹 新建清理节点")
        
        # 执行菜单
        action = menu.exec(event.globalPos())
        
        # 处理动作
        if action == action_text:
            node = TextNode(mouse_pos.x(), mouse_pos.y())
            self.scene.addItem(node)
        elif action == action_image:
            node = ImageNode(mouse_pos.x(), mouse_pos.y())
            self.scene.addItem(node)
        elif action == action_video:
            node = VideoNode(mouse_pos.x(), mouse_pos.y())
            self.scene.addItem(node)
        elif action == action_google:
            node = GoogleScriptNode(mouse_pos.x(), mouse_pos.y())
            self.scene.addItem(node)
        elif action == action_storyboard:
            node = StoryboardNode(mouse_pos.x(), mouse_pos.y())
            self.scene.addItem(node)
        elif action == action_character:
            node = ScriptCharacterNode(mouse_pos.x(), mouse_pos.y())
            self.scene.addItem(node)
        elif action == action_director:
            DirectorNodeClass = DirectorNodeFactory.create_node(CanvasNode)
            node = DirectorNodeClass(mouse_pos.x(), mouse_pos.y())
            self.scene.addItem(node)
        elif action == action_location:
            LocationNodeClass = LocationNodeFactory.create_node(CanvasNode)
            node = LocationNodeClass(mouse_pos.x(), mouse_pos.y())
            self.scene.addItem(node)
        elif action == action_cleaning:
            node = CleaningNode(mouse_pos.x(), mouse_pos.y())
            self.scene.addItem(node)

    def copy_selected_nodes(self):
        selected_items = self.scene.selectedItems()
        nodes = [item for item in selected_items if isinstance(item, CanvasNode)]
        if not nodes:
            return
        self.clipboard_data = []
        self.paste_offset_count = 0
        for node in nodes:
            node_data = self.serialize_node(node)
            if node_data:
                self.clipboard_data.append(node_data)
        # print(f"[画布] 已复制 {len(self.clipboard_data)} 个节点")



    def get_canvas_state(self):
        """获取当前画布状态（返回字典）"""
        try:
            nodes = []
            node_id_map = {}
            idx = 0
            for item in self.scene.items():
                if isinstance(item, CanvasNode):
                    data = self.serialize_node(item)
                    if not data:
                        continue
                    data["id"] = idx
                    nodes.append(data)
                    node_id_map[item] = idx
                    idx += 1
            connections = []
            for conn in self.connection_manager.get_all_connections():
                src_node = conn.source_socket.parent_node
                tgt_node = conn.target_socket.parent_node
                if src_node in node_id_map and tgt_node in node_id_map:
                    connections.append({
                        "source_node_id": node_id_map[src_node],
                        "source_socket_index": conn.source_socket.index,
                        "target_node_id": node_id_map[tgt_node],
                        "target_socket_index": conn.target_socket.index
                    })
            
            # 获取视口状态
            viewport_center = self.mapToScene(self.viewport().rect().center())
            
            state = {
                "version": 1,
                "nodes": nodes,
                "connections": connections,
                "viewport_x": viewport_center.x(),
                "viewport_y": viewport_center.y(),
                "zoom": self.zoom_factor
            }
            return state
        except Exception as e:
            print(f"[画布] 获取状态失败: {e}")
            return None

    def save_canvas_state(self, file_path=None):
        try:
            state = self.get_canvas_state()
            if not state:
                return

            base_dir = os.path.dirname(__file__)
            json_dir = os.path.join(base_dir, "json")
            os.makedirs(json_dir, exist_ok=True)
            fp = file_path or os.path.join(json_dir, "lingdong_canvas.json")
            
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            print(f"[画布] 状态已保存: {fp}")
        except Exception as e:
            print(f"[画布] 保存失败: {e}")

    def load_canvas_state(self, file_path=None):
        try:
            base_dir = os.path.dirname(__file__)
            json_dir = os.path.join(base_dir, "json")
            fp = file_path or os.path.join(json_dir, "lingdong_canvas.json")
            if not os.path.exists(fp):
                return
            with open(fp, "r", encoding="utf-8") as f:
                state = json.load(f)
            self.load_canvas_state_from_data(state)
        except Exception as e:
            print(f"[画布] 加载失败: {e}")

    def load_canvas_state_from_data(self, state):
        """从数据字典加载画布状态"""
        try:
            self.clear_canvas()
            
            # 恢复视图状态
            vx = state.get("viewport_x")
            vy = state.get("viewport_y")
            zoom = state.get("zoom")
            
            if zoom:
                from PySide6.QtGui import QTransform
                self.setTransform(QTransform().scale(zoom, zoom))
                self.zoom_factor = zoom
            
            if vx is not None and vy is not None:
                self.centerOn(vx, vy)
                
            id_to_node = {}
            for data in state.get("nodes", []):
                node = None
                t = data.get("type")
                x = data.get("x", 0)
                y = data.get("y", 0)
                try:
                    if t == "text":
                        node = TextNode(x, y)
                        
                        # 恢复节点大小
                        w = data.get("width")
                        h = data.get("height")
                        if w and h:
                            node.setRect(0, 0, w, h)
                            
                        ft = data.get("full_text", "")
                        if ft:
                            node.full_text = ft
                            if hasattr(node, "update_display"):
                                node.update_display()
                            elif hasattr(node, "content_text"):
                                node.content_text.setPlainText(ft)
                    elif t == "image":
                        node = ImageNode(x, y)
                        node.setRect(0, 0, data.get("width", 250), data.get("height", 250))
                        
                        # 恢复多图属性
                        node.image_paths = data.get("image_paths", [])
                        node.is_group_mode = data.get("is_group_mode", False)
                        node.current_index = data.get("current_index", 0)
                        
                        ip = data.get("image_path")
                        
                        if node.image_paths:
                            if node.is_group_mode:
                                node.update_group_ui()
                                node.load_current_image()
                            else:
                                # 尝试使用当前索引的图片
                                if 0 <= node.current_index < len(node.image_paths):
                                    node.load_single_image(node.image_paths[node.current_index])
                                elif ip:
                                    node.load_single_image(ip)
                                    
                            # 强制更新UI位置以确保按钮显示
                            node.update_ui_positions()
                        elif ip:
                            node.load_image(ip)
                    elif t == "video":
                        node = VideoNode(x, y)
                        node.setRect(0, 0, data.get("width", 280), data.get("height", 220))
                        vp = data.get("video_path")
                        if vp:
                            node.load_video(vp)
                    elif t == "people":
                        node = PeopleNode(x, y, parent_canvas=self)
                        node.data_rows = data.get("data_rows", [])
                        if hasattr(node, "_create_table"):
                            node._create_table()
                        if data.get("is_collapsed", False) and hasattr(node, "toggle_collapse"):
                            node.toggle_collapse()
                    elif t == "table":
                        headers = data.get("headers")
                        table_name = data.get("table_name", "分镜脚本")
                        table_data = data.get("table_data", [])
                        node = StoryboardNode(x, y, table_data, table_name, headers)
                    elif t == "script_character":
                        node = ScriptCharacterNode(x, y)
                        if hasattr(node, "load_node_data"):
                            node.load_node_data(data)
                    elif t == "location":
                        node = LocationNode(x, y)
                        if hasattr(node, "load_node_data"):
                            node.load_node_data(data)
                        elif "location_rows" in data:
                            # 临时兼容逻辑，实际应由 LocationNode.load_node_data 处理
                            pass
                    elif t == "cleaning":
                        node = CleaningNode(x, y)
                        node.cleaning_text = data.get("cleaning_text", "")
                        if hasattr(node, "update_display"):
                            node.update_display()
                    elif t == "gemini_analyze":
                        node = GeminiAnalyzeNode(x, y)
                        # GeminiNode currently doesn't store much state other than connections/pos
                        # but we can add video path persistence if we want later.
                        # For now, just recreating it is enough.
                        if "video_path" in data:
                             node.video_path = data["video_path"]
                             if hasattr(node, "process_video"):
                                 # We might not want to auto-process on load, but we can set the label
                                 node.label.setText(f"视频已加载: {os.path.basename(node.video_path)}")
                    elif t == "google_script":
                        node = GoogleScriptNode(x, y)
                        script_data = data.get("script_data", [])
                        headers = data.get("headers", [])
                        
                        if hasattr(node, 'table'):
                             # 恢复表头
                             if headers:
                                 node.table.setColumnCount(len(headers))
                                 node.table.setHorizontalHeaderLabels(headers)
                             elif script_data and len(script_data) > 0:
                                 # 只有数据没有表头的情况，尝试推断列数
                                 max_cols = 0
                                 for row in script_data:
                                     if isinstance(row, list):
                                          max_cols = max(max_cols, len(row))
                                 if max_cols > node.table.columnCount():
                                     node.table.setColumnCount(max_cols)
                             
                             node.table.setRowCount(0)
                             node.hint_label.setVisible(False)
                             node.table.setVisible(True)
                             
                             for r, row_data in enumerate(script_data):
                                 node.table.insertRow(r)
                                 for c, cell_data in enumerate(row_data):
                                     if c < node.table.columnCount():
                                         text = ""
                                         user_role = None
                                         
                                         if isinstance(cell_data, dict):
                                             text = cell_data.get("text", "")
                                             user_role = cell_data.get("user_role")
                                         else:
                                             text = str(cell_data)
                                         
                                         item = QTableWidgetItem(text)
                                         item.setToolTip(text)
                                         
                                         if user_role:
                                             item.setData(Qt.UserRole, user_role)
                                             if os.path.exists(user_role):
                                                 item.setIcon(QIcon(user_role))
                                                 node.table.setRowHeight(r, 90)
                                         elif text and (text.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'))) and os.path.exists(text):
                                             item.setData(Qt.UserRole, text)
                                             item.setIcon(QIcon(text))
                                             node.table.setRowHeight(r, 90)
                                         
                                         node.table.setItem(r, c, item)
                             
                             # 设置图标大小
                             node.table.setIconSize(QSize(140, 80))
                    elif t == "gacha":
                        try:
                            node = GachaNode(x, y)
                        except Exception as e:
                            print(f"[加载] 抽卡节点加载失败: {e}")
                    elif t == "consistent_image":
                        # consistent_image node logic removed
                        pass
                    elif t == "director":
                        try:
                            DirectorNodeClass = DirectorNodeFactory.create_node(CanvasNode)
                            node = DirectorNodeClass(x, y)
                            node.setRect(0, 0, data.get("width", 300), data.get("height", 400))
                        except Exception as e:
                            print(f"[加载] 导演节点加载失败: {e}")
                    # elif t == "consistent_person":
                    #     ConsistentPersonNodeClass = ConsistentPersonNodeFactory.create_node(CanvasNode)
                    #     node = ConsistentPersonNodeClass(x, y)
                    #     ip = data.get("image_path")
                    #     if ip:
                    #         node.image_path = ip
                    #     pn = data.get("person_name", "")
                    #     if pn:
                    #         node.person_name = pn
                    #     pp = data.get("person_prompt") or data.get("prompt") or ""
                    #     if pp:
                    #         node.person_prompt = pp
                    #     if hasattr(node, "update_display"):
                    #         node.update_display()
                    if node:
                        self.scene.addItem(node)
                        # 修复文字节点显示问题：添加到场景后更新显示
                        if t == "text" and hasattr(node, "update_display"):
                            node.update_display()
                        id_to_node[data.get("id")] = node
                except Exception as e:
                    print(f"[画布] 还原节点失败: {e}")
            for c in state.get("connections", []):
                try:
                    src_node = id_to_node.get(c.get("source_node_id"))
                    tgt_node = id_to_node.get(c.get("target_node_id"))
                    if not src_node or not tgt_node:
                        continue
                    si = c.get("source_socket_index", 0)
                    ti = c.get("target_socket_index", 0)
                    if si >= len(src_node.output_sockets) or ti >= len(tgt_node.input_sockets):
                        continue
                    src_socket = src_node.output_sockets[si]
                    tgt_socket = tgt_node.input_sockets[ti]
                    conn = Connection(src_socket, tgt_socket, self.scene)
                    self.connection_manager.connection_created.emit(conn)
                except Exception as e:
                    print(f"[画布] 还原连接失败: {e}")
            print(f"[画布] 状态已加载")
        except Exception as e:
            print(f"[画布] 加载失败: {e}")
    
    def copy_selected_nodes(self):
        """复制选中的节点"""
        selected_items = self.scene.selectedItems()
        # 过滤出 CanvasNode
        nodes = [item for item in selected_items if isinstance(item, CanvasNode)]
        
        if not nodes:
            return
            
        self.clipboard_data = []
        self.paste_offset_count = 0  # 重置粘贴偏移计数
        
        for node in nodes:
            node_data = self.serialize_node(node)
            if node_data:
                self.clipboard_data.append(node_data)
        # print(f"[画布] 已复制 {len(self.clipboard_data)} 个节点")

    def serialize_node(self, node):
        """序列化节点数据"""
        data = {
            "x": node.pos().x(),
            "y": node.pos().y(),
            "width": node.rect().width(),
            "height": node.rect().height()
        }
        
        if "文字" in node.node_title:
            data["type"] = "text"
            data["full_text"] = getattr(node, "full_text", "")
        elif "图片" in node.node_title:
            data["type"] = "image"
            data["image_path"] = getattr(node, "image_path", None)
            data["image_paths"] = getattr(node, "image_paths", [])
            data["is_group_mode"] = getattr(node, "is_group_mode", False)
            data["current_index"] = getattr(node, "current_index", 0)
        elif "视频员工编辑器" in node.node_title:
            data["type"] = "video_boss"
            data["video_paths"] = getattr(node, "video_paths", [])
        elif "视频" in node.node_title:
            data["type"] = "video"
            data["video_path"] = getattr(node, "video_path", None)
        elif "剧本人物" in node.node_title:
            data["type"] = "script_character"
            if hasattr(node, "get_node_data"):
                data.update(node.get_node_data())
        elif "地点" in node.node_title or "环境" in node.node_title:
            data["type"] = "location"
            if hasattr(node, "get_node_data"):
                data.update(node.get_node_data())
        elif "人物" in node.node_title:
            data["type"] = "people"
            data["data_rows"] = getattr(node, "data_rows", [])
            data["is_collapsed"] = getattr(node, "is_collapsed", False)
        elif "分镜" in node.node_title or "表格" in node.node_title:
            data["type"] = "table"
            data["table_data"] = getattr(node, "table_data", [])
            data["table_name"] = getattr(node, "node_title", "分镜脚本")
            data["headers"] = getattr(node, "headers", None)
        elif "谷歌" in node.node_title:
            data["type"] = "google_script"
            
            # 保存表头
            headers = []
            if hasattr(node, 'table'):
                 for c in range(node.table.columnCount()):
                     item = node.table.horizontalHeaderItem(c)
                     headers.append(item.text() if item else "")
            data["headers"] = headers
            
            rows = []
            if hasattr(node, 'table'):
                for r in range(node.table.rowCount()):
                    row_data = []
                    for c in range(node.table.columnCount()):
                        item = node.table.item(r, c)
                        if item:
                            cell = {
                                "text": item.text(),
                                "user_role": item.data(Qt.UserRole)
                            }
                        else:
                            cell = {"text": "", "user_role": None}
                        row_data.append(cell)
                    rows.append(row_data)
            data["script_data"] = rows
        elif "清理" in node.node_title:
            data["type"] = "cleaning"
            data["cleaning_text"] = getattr(node, "cleaning_text", "")
        elif "Gemini" in node.node_title:
            data["type"] = "gemini_analyze"
            data["video_path"] = getattr(node, "video_path", None)
        elif "导演" in node.node_title:
            data["type"] = "director"
        elif "抽卡节点" in node.node_title:
            data["type"] = "gacha"
        else:
            return None
            
        return data

    def paste_nodes(self):
        """粘贴节点"""
        if not self.clipboard_data:
            return
            
        self.scene.clearSelection()
        self.paste_offset_count += 1
        offset = 20 * self.paste_offset_count
        
        created_nodes = []
        
        for data in self.clipboard_data:
            new_x = data["x"] + offset
            new_y = data["y"] + offset
            
            node = None
            node_type = data.get("type")
            
            try:
                if node_type == "text":
                    node = TextNode(new_x, new_y)
                    if "full_text" in data:
                        node.full_text = data["full_text"]
                        if hasattr(node, "content_text"):
                            node.content_text.setPlainText(node.full_text)
                
                elif node_type == "image":
                    node = ImageNode(new_x, new_y)
                    node.setRect(0, 0, data["width"], data["height"])
                    
                    # 恢复多图属性
                    node.image_paths = data.get("image_paths", [])
                    node.is_group_mode = data.get("is_group_mode", False)
                    node.current_index = data.get("current_index", 0)
                    
                    if node.image_paths:
                        if node.is_group_mode:
                            node.update_group_ui()
                        else:
                             if 0 <= node.current_index < len(node.image_paths):
                                node.load_single_image(node.image_paths[node.current_index])
                             elif data.get("image_path"):
                                node.load_single_image(data.get("image_path"))
                    elif data.get("image_path"):
                        node.load_image(data["image_path"])
                
                elif node_type == "video":
                    node = VideoNode(new_x, new_y)
                    node.setRect(0, 0, data["width"], data["height"])
                    if data.get("video_path"):
                        node.load_video(data["video_path"])
                
                elif node_type == "people":
                    node = PeopleNode(new_x, new_y, parent_canvas=self)
                    if "data_rows" in data:
                        node.data_rows = data["data_rows"]
                        if hasattr(node, "_create_table"):
                            node._create_table()
                    if data.get("is_collapsed", False) and hasattr(node, "toggle_collapse"):
                        node.toggle_collapse()
                
                elif node_type == "table":
                    headers = data.get("headers")
                    table_name = data.get("table_name", "分镜脚本")
                    table_data = data.get("table_data", [])
                    node = StoryboardNode(new_x, new_y, table_data, table_name, headers)
                
                elif node_type == "script_character":
                    node = ScriptCharacterNode(new_x, new_y)
                    if hasattr(node, "load_node_data"):
                        node.load_node_data(data)
                elif node_type == "location":
                    LocationNodeClass = LocationNodeFactory.create_node(CanvasNode)
                    node = LocationNodeClass(new_x, new_y)
                    if hasattr(node, "load_node_data"):
                        node.load_node_data(data)

                elif node_type == "cleaning":
                    node = CleaningNode(new_x, new_y)
                    node.cleaning_text = data.get("cleaning_text", "")
                    if hasattr(node, "update_display"):
                        node.update_display()

                elif node_type == "google_script":
                    node = GoogleScriptNode(new_x, new_y)
                    script_data = data.get("script_data", [])
                    headers = data.get("headers", [])
                    
                    if hasattr(node, 'table'):
                         if headers:
                             node.table.setColumnCount(len(headers))
                             node.table.setHorizontalHeaderLabels(headers)
                             
                         node.table.setRowCount(0)
                         node.hint_label.setVisible(False)
                         node.table.setVisible(True)
                         
                         for r, row_data in enumerate(script_data):
                             node.table.insertRow(r)
                             for c, cell_data in enumerate(row_data):
                                 if c < node.table.columnCount():
                                     text = ""
                                     user_role = None
                                     
                                     if isinstance(cell_data, dict):
                                         text = cell_data.get("text", "")
                                         user_role = cell_data.get("user_role")
                                     else:
                                         text = str(cell_data)
                                     
                                     item = QTableWidgetItem(text)
                                     item.setToolTip(text)
                                     
                                     if user_role:
                                         item.setData(Qt.UserRole, user_role)
                                         if os.path.exists(user_role):
                                             item.setIcon(QIcon(user_role))
                                             node.table.setRowHeight(r, 90)
                                     
                                     node.table.setItem(r, c, item)
                         
                         node.table.setIconSize(QSize(140, 80))

                elif node_type == "video_boss":
                    try:
                        VideoProcessorNodeClass = VideoProcessorNodeFactory.create_node(CanvasNode, ConnectableNode, DataType)
                        node = VideoProcessorNodeClass(new_x, new_y)
                        video_paths = data.get("video_paths", [])
                        if video_paths and hasattr(node, "receive_data"):
                            node.receive_data(video_paths)
                    except Exception as e:
                        print(f"Error pasting video_boss: {e}")

                elif node_type == "director":
                    try:
                        DirectorNodeClass = DirectorNodeFactory.create_node(CanvasNode, ConnectableNode, DataType)
                        node = DirectorNodeClass(new_x, new_y)
                    except Exception as e:
                        print(f"Error pasting director: {e}")

                elif node_type == "gemini_analyze":
                    try:
                        node = GeminiAnalyzeNode(new_x, new_y)
                        if data.get("video_path"):
                            node.video_path = data["video_path"]
                    except Exception as e:
                        print(f"Error pasting gemini_analyze: {e}")
                elif node_type == "gacha":
                    try:
                        node = GachaNode(new_x, new_y)
                    except Exception as e:
                        print(f"Error restoring gacha node: {e}")
                elif node_type == "consistent_image":
                    # consistent_image node logic removed
                    pass

                # elif node_type == "consistent_person":
                #     ConsistentPersonNodeClass = ConsistentPersonNodeFactory.create_node(CanvasNode)
                #     node = ConsistentPersonNodeClass(new_x, new_y)
                #     if data.get("image_path"):
                #         node.image_path = data["image_path"]
                #     if "person_name" in data:
                #         node.person_name = data["person_name"]
                #     pp = data.get("person_prompt") or data.get("prompt") or ""
                #     if pp:
                #         node.person_prompt = pp
                #     if hasattr(node, "update_display"):
                #         node.update_display()
                
                if node:
                    self.scene.addItem(node)
                    node.setSelected(True)
                    created_nodes.append(node)
            except Exception as e:
                # print(f"[粘贴] 创建节点失败: {e}")
                pass
                
        # print(f"[画布] 已粘贴 {len(created_nodes)} 个节点")

    def on_connection_created(self, connection):
        """连接创建回调"""
        source_node = connection.source_socket.parent_node
        target_node = connection.target_socket.parent_node
        source_title = getattr(source_node, 'node_title', 'Unknown')
        target_title = getattr(target_node, 'node_title', 'Unknown')
        # print(f"[连接] ✓ {source_title} -> {target_title}")
        
        # 更新人物生成菜单的可见性 - 已移除
        # self._update_people_menu_visibility()
        
        # 触发节点的连接回调 (如果有)
        if hasattr(source_node, "on_socket_connected"):
            try:
                source_node.on_socket_connected(connection.source_socket, connection)
            except Exception as e:
                print(f"[连接] Source node on_socket_connected error: {e}")
                
        if hasattr(target_node, "on_socket_connected"):
            try:
                target_node.on_socket_connected(connection.target_socket, connection)
            except Exception as e:
                print(f"[连接] Target node on_socket_connected error: {e}")

        try:
            pass
            # if ("人物" in source_title and ("一致性人物" in target_title or "剧本人物节点" in target_title)):
            #     self.sync_consistent_person_names(source_node)
            # elif (("一致性人物" in source_title or "剧本人物节点" in source_title) and "人物" in target_title):
            #     self.sync_consistent_person_names(target_node)
        except Exception as e:
            print(f"[连接] 命名同步失败: {e}")
    
    def on_connection_removed(self, connection):
        """连接移除回调"""
        # print(f"[连接] ✗ 连接已移除")
        
        # 更新人物生成菜单的可见性 - 已移除
        # self._update_people_menu_visibility()
        
        try:
            pass
        except Exception as e:
            print(f"[连接] 命名重算失败: {e}")
    
    def _update_people_menu_visibility(self):
        pass
    
    
    def save_undo_operation(self, operation_type, data):
        """保存操作到撤销栈"""
        self.undo_stack.append({
            'type': operation_type,
            'data': data
        })
        # 限制撤销栈大小
        if len(self.undo_stack) > self.max_undo_steps:
            self.undo_stack.pop(0)
        print(f"[撤销] 保存操作: {operation_type}, 撤销栈大小: {len(self.undo_stack)}")
    
    def undo_last_operation(self):
        """撤销上一次操作"""
        if not self.undo_stack:
            print("[撤销] 没有可撤销的操作")
            return
        
        operation = self.undo_stack.pop()
        operation_type = operation['type']
        data = operation['data']
        
        print(f"[撤销] 执行撤销: {operation_type}")
        
        if operation_type == 'delete':
            # 恢复删除的项
            for item_info in data:
                if item_info['type'] == 'node':
                    # 恢复节点
                    node = item_info['node']
                    self.scene.addItem(node)
                    node.setPos(item_info['position'])
                    print(f"[撤销] 恢复节点: {node.node_title}")
                    
                    # 恢复节点的连接
                    for conn_info in item_info['connections']:
                        source_socket = conn_info['source_socket']
                        target_socket = conn_info['target_socket']
                        if source_socket and target_socket:
                            self.connection_manager.create_connection(source_socket, target_socket)
                            print(f"[撤销] 恢复连接")
                
                elif item_info['type'] == 'connection':
                    # 恢复连接
                    source_socket = item_info['source_socket']
                    target_socket = item_info['target_socket']
                    if source_socket and target_socket:
                        self.connection_manager.create_connection(source_socket, target_socket)
                        print(f"[撤销] 恢复连接")
    
    def wheelEvent(self, event: QWheelEvent):
        """鼠标滚轮缩放"""
        # 缩放因子
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor
        
        # 根据滚轮方向缩放
        if event.angleDelta().y() > 0:
            zoom = zoom_in_factor
            self.zoom_factor *= zoom
        else:
            zoom = zoom_out_factor
            self.zoom_factor *= zoom
        
        # 限制缩放范围
        if self.zoom_factor < self.min_zoom:
            self.zoom_factor = self.min_zoom
            return
        if self.zoom_factor > self.max_zoom:
            self.zoom_factor = self.max_zoom
            return
        
        # 应用缩放
        self.scale(zoom, zoom)
    
    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下 - 优先处理连接拖拽，然后是拖动画布或选中节点"""
        # 左键：检查是否点击接口
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            
            # 先尝试检测Socket（使用更精确的检测方法）
            clicked_socket = self._find_socket_at_pos(scene_pos)
            if clicked_socket:
                self.is_dragging_connection = True
                
                # 检查是否是输入接口且已有连接（实现拔出连接功能）
                # 这里的 "input" 对应 SocketType.INPUT
                if clicked_socket.socket_type == "input" and clicked_socket.connections:
                    # 获取要断开的连接（通常取最后一个）
                    conn_to_detach = clicked_socket.connections[-1]
                    original_source = conn_to_detach.source_socket
                    
                    # 只有当源接口存在时才支持拔出重连
                    if original_source:
                        # 移除旧连接
                        self.connection_manager.remove_connection(conn_to_detach)
                        
                        # 从原来的源接口开始新的拖拽
                        self.connection_manager.start_dragging(original_source, scene_pos)
                    else:
                        # 异常情况，直接开始新连接
                        self.connection_manager.start_dragging(clicked_socket, scene_pos)
                
                elif clicked_socket.socket_type == "output" and len(clicked_socket.connections) == 1:
                    # 允许输出接口（蓝色）断开连接
                    # 获取要断开的连接
                    conn_to_detach = clicked_socket.connections[0]
                    original_target = conn_to_detach.target_socket
                    
                    if original_target:
                        # 移除旧连接
                        self.connection_manager.remove_connection(conn_to_detach)
                        
                        # 从原来的目标接口（输入）开始新的拖拽
                        # 注意：lingdongconnect.py 中的 end_dragging 已经处理了从输入拖到输出时的自动交换
                        self.connection_manager.start_dragging(original_target, scene_pos)
                    else:
                        self.connection_manager.start_dragging(clicked_socket, scene_pos)

                else:
                    # 普通连接拖拽
                    self.connection_manager.start_dragging(clicked_socket, scene_pos)
                
                event.accept()
                return
        
        # 发出画布点击信号
        self.canvas_clicked.emit()
        
        # 中键拖动画布
        if event.button() == Qt.MouseButton.MiddleButton:
            self.is_panning = True
            self.last_pan_point = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        # 左键：检查是否点击在节点上
        elif event.button() == Qt.MouseButton.LeftButton:
            # 获取点击位置的项
            item = self.itemAt(event.pos())
            
            # 检查是否是节点或节点的子项
            is_node = False
            check_item = item
            while check_item is not None:
                if isinstance(check_item, CanvasNode):
                    is_node = True
                    break
                check_item = check_item.parentItem()
            
            # 如果点击的是空白区域（没有节点），则拖动画布
            if not is_node:
                self.is_panning = True
                self.last_pan_point = event.pos()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
            else:
                # 点击到节点，正常处理
                
                # 支持 Shift 多选：如果按住 Shift，则视为按住 Ctrl (ControlModifier)
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    # 构造新的事件，添加 ControlModifier
                    new_modifiers = event.modifiers() | Qt.KeyboardModifier.ControlModifier
                    new_event = QMouseEvent(
                        event.type(),
                        event.position(),
                        event.globalPosition(),
                        event.button(),
                        event.buttons(),
                        new_modifiers
                    )
                    super().mousePressEvent(new_event)
                else:
                    super().mousePressEvent(event)
                    
                # 确保画布获得焦点，以便接收键盘事件
                self.setFocus()
        else:
            super().mousePressEvent(event)
            self.setFocus()
    
    def _find_socket_at_pos(self, scene_pos):
        """在指定场景坐标查找Socket（精确检测）"""
        # 遍历所有节点的所有Socket
        for item in self.scene.items():
            if isinstance(item, CanvasNode):
                for socket in item.input_sockets + item.output_sockets:
                    # 确保Socket可见且启用
                    if not socket.isVisible() or not socket.isEnabled():
                        continue
                        
                    # 获取Socket的场景中心位置
                    socket_center = socket.get_center_pos()
                    # 计算距离（场景坐标系）
                    distance_scene = ((scene_pos.x() - socket_center.x()) ** 2 + 
                               (scene_pos.y() - socket_center.y()) ** 2) ** 0.5
                    
                    # 由于Socket设置了ItemIgnoresTransformations，它在屏幕上的大小是固定的（半径约6px）
                    # 我们希望点击判定范围也在屏幕上是固定的（例如半径10px）
                    # 因此需要根据当前视图的缩放比例调整场景坐标系下的判定距离
                    
                    # 获取当前缩放比例 (假设x和y缩放一致)
                    scale = self.transform().m11()
                    if scale == 0: scale = 1.0
                    
                    # 屏幕上的判定半径（像素）
                    hit_radius_screen = 10.0
                    
                    # 转换为场景坐标系下的判定半径
                    hit_radius_scene = hit_radius_screen / scale
                    
                    # 判定
                    if distance_scene <= hit_radius_scene:
                        return socket
        return None
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """鼠标移动 - 优先处理连接拖拽，然后是拖动画布"""
        # 处理连接拖拽
        if self.is_dragging_connection:
            scene_pos = self.mapToScene(event.pos())
            self.connection_manager.update_dragging(scene_pos)
            
            # 检查是否悬停在接口上（使用精确检测）
            self.hover_socket = self._find_socket_at_pos(scene_pos)
            
            event.accept()
            return
        
        # 处理画布拖动
        if self.is_panning:
            delta = event.pos() - self.last_pan_point
            self.last_pan_point = event.pos()
            
            # 移动视图
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """鼠标释放 - 优先处理连接完成，然后是结束拖动"""
        # 处理连接释放
        if event.button() == Qt.MouseButton.LeftButton and self.is_dragging_connection:
            self.connection_manager.end_dragging(self.hover_socket)
            self.is_dragging_connection = False
            self.hover_socket = None
            event.accept()
            return
        
        # 处理画布拖动结束
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self.is_panning
        ):
            self.is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
    
    def zoom_in(self):
        """放大画布"""
        zoom = 1.2
        new_zoom = self.zoom_factor * zoom
        if new_zoom <= self.max_zoom:
            self.zoom_factor = new_zoom
            self.scale(zoom, zoom)
            # print(f"[画布] 放大到 {self.zoom_factor:.2f}x")
    
    def zoom_out(self):
        """缩小画布"""
        zoom = 1 / 1.2
        new_zoom = self.zoom_factor * zoom
        if new_zoom >= self.min_zoom:
            self.zoom_factor = new_zoom
            self.scale(zoom, zoom)
            # print(f"[画布] 缩小到 {self.zoom_factor:.2f}x")
    
    def clear_canvas(self):
        # 防止 QGraphicsItem::ungrabMouse: cannot ungrab mouse without scene 错误
        # 在移除项目前，先确保释放鼠标捕获
        if self.scene.mouseGrabberItem():
            self.scene.mouseGrabberItem().ungrabMouse()

        removed_count = 0
        for item in self.scene.items():
            if isinstance(item, CanvasNode):
                # 再次确保该项目没有捕获鼠标
                if item == self.scene.mouseGrabberItem():
                    item.ungrabMouse()
                self.scene.removeItem(item)
                removed_count += 1
        if hasattr(self, "connection_manager") and self.connection_manager:
            self.connection_manager.clear_all_connections()
        # print(f"[画布] 已清空画布，删除了 {removed_count} 个节点")
    
    def add_node(self, node_type):
        """添加节点到画布中心"""
        # 获取视图中心在场景中的坐标
        center = self.mapToScene(self.viewport().rect().center())
        
        # 根据类型创建节点
        if node_type == "text":
            node = TextNode(center.x() - 100, center.y() - 75)
        elif node_type == "image":
            node = ImageNode(center.x() - 100, center.y() - 100)
        elif node_type == "video":
            node = VideoNode(center.x() - 140, center.y() - 110)
        elif node_type == "video_boss":
            VideoProcessorNodeClass = VideoProcessorNodeFactory.create_node(CanvasNode, ConnectableNode, DataType)
            node = VideoProcessorNodeClass(center.x() - 400, center.y() - 250)
        # elif node_type == "people":
        #     node = PeopleNode(center.x() - 450, center.y() - 60, parent_canvas=self)
        elif node_type == "table":
            try:
                # 创建空表格（3行）
                node = StoryboardNode(center.x() - 540, center.y() - 100, None, "分镜脚本")
                print(f"[Debug] Created table node at {node.pos()} rect {node.rect()}")
                node.setZValue(100) # Ensure it's on top
                node.setVisible(True)
            except Exception as e:
                print(f"[Error] Failed to create table node: {e}")
                import traceback
                traceback.print_exc()
                return
        elif node_type == "script_character":
            node = ScriptCharacterNode(center.x() - 400, center.y() - 300)
        elif node_type == "google_script":
            node = GoogleScriptNode(center.x() - 300, center.y() - 200)
        elif node_type == "gacha":
            try:
                # print("Creating GachaNode...")
                node = GachaNode(center.x() - 300, center.y() - 200)
                node.setZValue(100)
                # print("GachaNode created.")
            except Exception as e:
                print(f"Error creating GachaNode: {e}")
                import traceback
                traceback.print_exc()
                return
        elif node_type == "location":
            LocationNodeClass = LocationNodeFactory.create_node(CanvasNode)
            node = LocationNodeClass(center.x() - 300, center.y() - 250)
        elif node_type == "cleaning":
            node = CleaningNode(center.x() - 300, center.y() - 200)
        elif node_type == "gemini_analyze":
            node = GeminiAnalyzeNode(center.x() - 300, center.y() - 200)
        elif node_type == "director":
            try:
                DirectorNodeClass = DirectorNodeFactory.create_node(CanvasNode)
                node = DirectorNodeClass(center.x() - 300, center.y() - 200)
            except Exception as e:
                print(f"[Error] Failed to create director node: {e}")
                import traceback
                traceback.print_exc()
                return
        else:
            return
        
        self.scene.addItem(node)
        # print(f"[画布] 添加了{node_type}节点到 ({center.x():.0f}, {center.y():.0f})")
    
    def on_selection_changed(self):
        """场景选中项改变"""
        try:
            # 检查scene是否还存在
            if not self.scene:
                return
                
            selected_items = self.scene.selectedItems()
            
            if selected_items:
                # 遍历所有选中项，找到第一个CanvasNode
                selected_node = None
                for item in selected_items:
                    if isinstance(item, CanvasNode):
                        selected_node = item
                        break
                
                # 如果没找到CanvasNode，但选中了子项（如表格单元格），尝试获取其父节点
                if selected_node is None and selected_items:
                    first_item = selected_items[0]
                    # 尝试向上查找父节点
                    parent = first_item.parentItem()
                    while parent:
                        if isinstance(parent, CanvasNode):
                            selected_node = parent
                            break
                        parent = parent.parentItem()

                # 检查是否是节点类型
                if selected_node and isinstance(selected_node, CanvasNode):
                    # print(f"[画布] 选中节点: {selected_node.node_title}")
                    self.node_selected.emit(selected_node)
                else:
                    # 取消选中时发送 None
                    self.node_selected.emit(None)
            else:
                # 没有选中项
                self.node_selected.emit(None)
        except RuntimeError:
            # Scene已被删除，忽略
            pass


# ==================== 工作台面板 ====================
class WorkbenchPanel(QFrame):
    """右侧工作台面板 - 显示AI输出内容"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.providers = ["Hunyuan", "ChatGPT", "DeepSeek", "Claude", "Gemini 2.5"]
        self.dynamic_models_cache = {}  # 动态模型缓存
        self.last_selected_models = {}  # 记录每个provider的上次选择
        
        # 配置文件路径
        self.config_dir = os.path.join(os.path.dirname(__file__), 'json')
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_file = os.path.join(self.config_dir, 'talk_api_config.json')  # API配置
        self.lingdong_config_file = os.path.join(self.config_dir, 'lingdong.json')  # 灵动智能体配置
        
        # 对话历史
        self.conversation_history = []
        
        # 聊天工作线程和响应内容
        self.chat_worker = None
        self.current_response = ""
        
        # 当前选中的节点
        self.selected_node = None
        
        # 主界面引用（用于访问画布）
        self.main_page = None
        
        # 一致性图片生成器和worker（用于清理）
        self.consistent_image_generator = None
        self.consistent_image_worker = None
        
        # 聊天上下文管理器
        self.chat_context_manager = ChatNodeContextManager()
        self.active_contexts = [] # 存储当前激活的上下文 [{'title':..., 'content':...}]
        self.image_upload_manager = ChatImageUploadManager(self)
        
        self.setup_ui()
        self.load_lingdong_config()  # 加载灵动智能体配置
    
    def __del__(self):
        """析构函数 - 清理资源"""
        try:
            self._cleanup_consistent_image_worker()
        except Exception:
            pass
    
    def on_generate_prompt_clicked(self):
        """点击生成提示词按钮 - 为所有谷歌剧本节点添加提示词列"""
        if not self.canvas_view or not self.canvas_view.scene:
            return
            
        # 查找所有谷歌剧本节点
        nodes = []
        for item in self.canvas_view.scene.items():
            # 检查是否是谷歌剧本节点 (通过标题判断)
            if hasattr(item, 'node_title') and "谷歌剧本" in item.node_title:
                nodes.append(item)
        
        if not nodes:
             QMessageBox.information(self, "提示", "当前画布没有谷歌剧本节点")
             return

        count = 0
        for node in nodes:
             try:
                 add_prompt_column(node)
                 count += 1
             except Exception as e:
                 print(f"Failed to add prompt column to node: {e}")

    def setup_ui(self):
        """设置UI"""
        self.setFixedWidth(350)
        self.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-left: 1px solid #e0e0e0;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # 标题栏
        header = QHBoxLayout()
        
        # 刷新按钮
        refresh_btn = QPushButton("⟳")
        refresh_btn.setFixedSize(30, 30)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #f5f5f5;
                color: #666666;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #e6f4ea;
                color: #34A853;
                border: 1px solid #dce9d5;
            }
        """)
        header.addWidget(refresh_btn)
        
        header.addSpacing(5)
        
        # 标题
        title = QLabel("工作台")
        title.setStyleSheet("""
            color: #333333;
            font-size: 16px;
            font-weight: bold;
        """)
        header.addWidget(title)
        
        header.addStretch()
        

        

        self.generate_image_btn = QPushButton("生成图片")
        self.generate_image_btn.setFixedHeight(28)
        self.generate_image_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.generate_image_btn.setStyleSheet("""
            QPushButton {
                background-color: #e8f5e9;
                color: #2e7d32;
                border: 1px solid #c8e6c9;
                border-radius: 6px;
                padding: 0 12px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c8e6c9;
                border: 1px solid #a5d6a7;
            }
            QPushButton:pressed {
                background-color: #a5d6a7;
            }
        """)
        self.generate_image_btn.clicked.connect(self.on_generate_people_image_clicked)
        self.generate_image_btn.setVisible(False)
        header.addWidget(self.generate_image_btn)

        # 工具箱按钮
        self.toolbox_btn = QPushButton("📦 工具箱")
        self.toolbox_btn.setFixedHeight(28)
        self.toolbox_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toolbox_btn.setStyleSheet("""
            QPushButton {
                background-color: #6200EE;
                color: white;
                border: 1px solid #6200EE;
                border-radius: 6px;
                padding: 0 12px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3700B3;
                border: 1px solid #3700B3;
            }
            QPushButton:pressed {
                background-color: #000000;
            }
            QPushButton::menu-indicator {
                image: none;
            }
        """)
        
        self.toolbox_menu = QMenu()
        self.toolbox_menu.setStyleSheet("""
            QMenu {
                background-color: #ffffff;
                color: #333333;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 25px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #f3e5f5;
                color: #7b1fa2;
            }
        """)
        
        # 视频拆分（默认隐藏）
        self.video_split_action = QAction("🎬 视频拆分", self)
        self.video_split_action.triggered.connect(self.on_video_split_clicked)
        self.video_split_action.setVisible(False)
        self.toolbox_menu.addAction(self.video_split_action)

        # 谷歌镜头拆分（默认隐藏）
        self.google_split_action = QAction("📷 谷歌镜头拆分", self)
        self.google_split_action.triggered.connect(self.on_google_split_clicked)
        self.google_split_action.setVisible(False)
        self.toolbox_menu.addAction(self.google_split_action)
        
        # 剧本一键分镜（默认隐藏）
        self.storyboard_action = QAction("📄 剧本一键分镜", self)
        self.storyboard_action.triggered.connect(self.on_storyboard_clicked)
        self.storyboard_action.setVisible(False)
        self.toolbox_menu.addAction(self.storyboard_action)

        self.toolbox_menu.addSeparator()

        # 魔法词
        self.magic_word_action = QAction("🔮 魔法词", self)
        self.magic_word_action.triggered.connect(self.on_generate_prompt_clicked)
        self.toolbox_menu.addAction(self.magic_word_action)

        # 生成草稿 (已移除)
        # self.draft_action = QAction("📝 生成草稿", self)
        # self.draft_action.triggered.connect(self.on_generate_draft_clicked)
        # self.toolbox_menu.addAction(self.draft_action)

        # 镜头草图 (默认隐藏，仅选中谷歌剧本节点时显示)
        self.lens_sketch_action = QAction("🎨 生成镜头草图", self)
        self.lens_sketch_action.triggered.connect(self.on_lens_sketch_clicked)
        self.lens_sketch_action.setVisible(False)
        self.toolbox_menu.addAction(self.lens_sketch_action)



        self.toolbox_menu.addSeparator()

        # 创建"生成人物（真实）"菜单项
        self.people_real_action = QAction("🎭 生成人物（真实）", self)
        self.people_real_action.triggered.connect(lambda: self.on_generate_all_people("真实"))
        self.toolbox_menu.addAction(self.people_real_action)
        self.people_real_action.setVisible(False)  # 默认隐藏
        
        # 创建"生成人物（动漫）"菜单项
        self.people_anime_action = QAction("🎨 生成人物（动漫）", self)
        self.people_anime_action.triggered.connect(lambda: self.on_generate_all_people("动漫"))
        self.toolbox_menu.addAction(self.people_anime_action)
        self.people_anime_action.setVisible(False)  # 默认隐藏

        self.toolbox_btn.setMenu(self.toolbox_menu)
        header.addWidget(self.toolbox_btn)
        
        # 连接菜单显示信号，用于动态更新菜单项状态
        self.toolbox_menu.aboutToShow.connect(self.update_toolbox_menu_state)
        
        layout.addLayout(header)
        
        layout.addSpacing(10)
        
        # 输出内容区域
        self.output_text = QTextBrowser()
        self.output_text.setStyleSheet("""
            QTextBrowser {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #dadce0;
                border-radius: 12px;
                padding: 15px;
                font-size: 13px;
                line-height: 1.8;
            }
        """)
        self.output_text.setHtml("""
            <div style='color: #666; text-align: center; margin-top: 100px;'>
                <p style='font-size: 14px;'>等待AI生成代码...</p>
                <p style='font-size: 12px; margin-top: 20px;'>
                    当前尚未生成任何内容，<br/>
                    请在画布中添加节点并开始编程
                </p>
            </div>
        """)
        layout.addWidget(self.output_text, 3)  # 输出区域占3份空间
        
        layout.addSpacing(10)
        
        # 模型配置区域
        self.config_frame = QFrame()
        self.config_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-radius: 6px;
                border: 1px solid #e0e0e0;
            }
        """)
        config_layout = QVBoxLayout(self.config_frame)
        config_layout.setContentsMargins(10, 10, 10, 10)
        config_layout.setSpacing(8)
        
        # 模型类型选择
        provider_row = QHBoxLayout()
        provider_label = QLabel("模型类型:")
        provider_label.setStyleSheet("color: #5f6368; font-size: 11px;")
        provider_label.setFixedWidth(60)
        provider_row.addWidget(provider_label)
        
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(self.providers)
        self.provider_combo.setFixedHeight(30)
        self.provider_combo.setStyleSheet("""
            QComboBox {
                background-color: #ffffff;
                color: #333333;
                border: 1px solid #dadce0;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 12px;
            }
            QComboBox:hover {
                border: 1px solid #34A853;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #333333;
                selection-background-color: #e6f4ea;
                selection-color: #34A853;
                border: 1px solid #e0e0e0;
            }
        """)
        provider_row.addWidget(self.provider_combo)
        config_layout.addLayout(provider_row)
        
        # 具体模型选择
        model_row = QHBoxLayout()
        model_label = QLabel("具体模型:")
        model_label.setStyleSheet("color: #5f6368; font-size: 11px;")
        model_label.setFixedWidth(60)
        model_row.addWidget(model_label)
        
        self.model_combo = QComboBox()
        self.model_combo.setFixedHeight(30)
        self.model_combo.setStyleSheet(self.provider_combo.styleSheet())
        model_row.addWidget(self.model_combo)
        config_layout.addLayout(model_row)
        
        # 连接信号
        self.provider_combo.currentTextChanged.connect(self.on_provider_changed)
        self.model_combo.currentTextChanged.connect(self.on_model_changed)
        
        # 默认隐藏模型配置区域
        self.config_frame.setVisible(False)
        
        layout.addWidget(self.config_frame)
        layout.addSpacing(10)
        
        # 输入框容器（填满剩余空间）
        input_container = QFrame()
        input_container.setObjectName("InputContainer")
        input_container.setStyleSheet("""
            #InputContainer {
                background-color: #ffffff;
                border: 1px solid #dadce0;
                border-radius: 12px;
            }
            #InputContainer:hover {
                border: 1px solid #b0b0b0;
            }
        """)
        input_container_layout = QVBoxLayout(input_container)
        input_container_layout.setContentsMargins(0, 0, 0, 0)
        input_container_layout.setSpacing(0)
        
        self.context_display_widget = QWidget()
        self.context_display_widget.setVisible(False)
        self.context_display_widget.setStyleSheet("background-color: transparent;")
        self.context_layout = QHBoxLayout(self.context_display_widget)
        self.context_layout.setContentsMargins(10, 8, 10, 0)
        self.context_layout.setSpacing(5)
        self.context_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        input_container_layout.addWidget(self.context_display_widget)
        self.image_display_widget = QWidget()
        self.image_display_widget.setVisible(False)
        self.image_display_widget.setStyleSheet("background-color: transparent;")
        self.image_layout = QHBoxLayout(self.image_display_widget)
        self.image_layout.setContentsMargins(10, 4, 10, 0)
        self.image_layout.setSpacing(6)
        self.image_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        input_container_layout.addWidget(self.image_display_widget)
        self.image_upload_manager.bind_preview_area(self.image_display_widget, self.image_layout)
        
        # 文本输入框
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("请输入你的问题或提示词...")
        self.text_input.setStyleSheet("""
            QTextEdit {
                background-color: transparent;
                color: #202124;
                border: none;
                padding: 15px;
                font-size: 14px;
                line-height: 1.6;
            }
        """)
        
        # 连接点击事件（使用 focusInEvent）
        self.text_input.installEventFilter(self)
        self.text_input.textChanged.connect(self.on_text_changed)
        
        # 初始化自动补全
        self.init_completer()
        
        input_container_layout.addWidget(self.text_input)
        
        # 底部按钮栏（内嵌在输入框中）
        btn_bar = QFrame()
        btn_bar.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border-top: 1px solid #f1f3f4;
            }
        """)
        btn_bar_layout = QHBoxLayout(btn_bar)
        btn_bar_layout.setContentsMargins(10, 5, 10, 8)
        btn_bar_layout.setSpacing(8)
        
        # 上下文引用按钮 (@)
        self.context_btn = QPushButton("@")
        self.context_btn.setFixedSize(26, 26)
        self.context_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.context_btn.setToolTip("引用剧本节点上下文")
        self.context_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #5f6368;
                border: 1px solid #e0e0e0;
                border-radius: 13px;
                font-size: 14px;
                font-weight: bold;
                margin-right: 2px;
            }
            QPushButton:hover {
                background-color: #f1f3f4;
                color: #1a73e8;
                border: 1px solid #d2e3fc;
            }
            QPushButton:pressed {
                background-color: #e8f0fe;
            }
        """)
        self.context_btn.clicked.connect(self.on_context_btn_clicked)
        btn_bar_layout.addWidget(self.context_btn)

        self.image_btn = self.image_upload_manager.create_button()
        btn_bar_layout.addWidget(self.image_btn)
        
        btn_bar_layout.addStretch()
        
        # 自动文本节点开关
        self.auto_text_manager = AutoTextNodeManager(self)
        self.toggle_btn = self.auto_text_manager.create_toggle_button()
        btn_bar_layout.addWidget(self.toggle_btn)

        # 词语优化按钮
        self.optimize_btn = QPushButton("✨ 词语优化")
        self.optimize_btn.setToolTip("使用AI优化提示词")
        self.optimize_btn.setFixedSize(90, 32)
        self.optimize_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.optimize_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(249, 171, 0, 0.1);
                color: #e37400;
                border: 1px solid rgba(249, 171, 0, 0.3);
                border-radius: 16px;
                font-size: 13px;
                font-weight: bold;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background-color: rgba(249, 171, 0, 0.2);
                border: 1px solid rgba(249, 171, 0, 0.5);
            }
            QPushButton:pressed {
                background-color: rgba(249, 171, 0, 0.3);
            }
            QPushButton:disabled {
                background-color: rgba(0, 0, 0, 0.05);
                color: #999999;
                border: 1px solid rgba(0, 0, 0, 0.1);
            }
        """)
        btn_bar_layout.addWidget(self.optimize_btn)
        
        # 发送按钮
        self.send_btn = QPushButton("发送 📤")
        self.send_btn.setToolTip("发送消息")
        self.send_btn.setFixedSize(80, 32)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #34A853;
                color: #ffffff;
                border: none;
                border-radius: 16px;
                font-size: 13px;
                font-weight: bold;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background-color: #2E8B46;
            }
            QPushButton:pressed {
                background-color: #257A3C;
            }
            QPushButton:disabled {
                background-color: #e0e0e0;
                color: #999999;
            }
        """)
        btn_bar_layout.addWidget(self.send_btn)
        
        input_container_layout.addWidget(btn_bar)
        
        # 将输入容器添加到主布局，设置拉伸因子为1，使其填满剩余空间
        layout.addWidget(input_container, 1)
        
        # 连接信号
        refresh_btn.clicked.connect(self.refresh_output)
        self.optimize_btn.clicked.connect(self.on_optimize_word)
        self.send_btn.clicked.connect(self.on_send_message)
        
        # 初始化模型列表
        self.on_provider_changed(self.provider_combo.currentText())
    
    def update_toolbox_menu_state(self):
        """更新工具箱菜单状态"""
        # 使用 self.selected_node 代替 self.scene.selectedItems()
        # 因为 WorkbenchPanel 可能没有 self.scene
        item = self.selected_node
        has_selection = item is not None
        
        # 默认全部隐藏
        self.video_split_action.setVisible(False)
        self.google_split_action.setVisible(False)
        self.storyboard_action.setVisible(False)
        self.lens_sketch_action.setVisible(False) # 镜头草图
        
        # 检查选中项类型
        if has_selection:
            # 兼容当前画布的节点实现：通过 node_title 判断（VideoNode / GoogleScriptNode 等）
            title = getattr(item, 'node_title', '')
            if title and "视频" in title:
                self.video_split_action.setVisible(True)

            # 如果是代理部件，获取其widget
            if isinstance(item, QGraphicsProxyWidget):
                widget = item.widget()
                if widget:
                    # 检查是否为视频节点
                    if hasattr(widget, 'video_player') or item.data(0) == "视频":
                        self.video_split_action.setVisible(True)
            
            # 检查是否为谷歌剧本节点
            # 优先检查 node_title
            is_google_script = False
            if hasattr(item, 'node_title') and "谷歌剧本" in item.node_title:
                is_google_script = True
            # 兼容旧逻辑：检查 title_text
            elif hasattr(item, 'title_text'):
                title = item.title_text.toPlainText() if hasattr(item.title_text, 'toPlainText') else str(item.title_text)
                if title == "谷歌剧本":
                    is_google_script = True
            
            if is_google_script:
                self.google_split_action.setVisible(True)
                self.lens_sketch_action.setVisible(True) # 显示镜头草图
            
            # 检查是否为剧本节点 (TextNode)
            if hasattr(item, 'title_text'):
                title = item.title_text.toPlainText() if hasattr(item.title_text, 'toPlainText') else str(item.title_text)
                if title == "文本" or title == "文字":
                    # 进一步检查内容是否像剧本...这里简化为总是显示
                    self.storyboard_action.setVisible(True)

    def on_lens_sketch_clicked(self):
        """点击镜头草图"""
        item = self.selected_node
        if not item:
            QMessageBox.warning(self, "提示", "请先选择一个谷歌剧本节点")
            return
            
        # 确认是谷歌剧本节点
        is_google_script = False
        if hasattr(item, 'node_title') and "谷歌剧本" in item.node_title:
            is_google_script = True
        elif hasattr(item, 'title_text'):
             title = item.title_text.toPlainText() if hasattr(item.title_text, 'toPlainText') else str(item.title_text)
             if title == "谷歌剧本":
                 is_google_script = True
        
        if not is_google_script:
            QMessageBox.warning(self, "提示", "请选择谷歌剧本节点")
            return
            
        try:
            from jingtoucaotu import LensSketchGenerator
            # 保持引用以防被垃圾回收
            # item 是 GoogleScriptNodeImpl 实例
            item._lens_sketch_generator = LensSketchGenerator(item)
            item._lens_sketch_generator.start()
        except Exception as e:
            print(f"[工作台] 启动镜头草图失败: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "错误", f"启动镜头草图失败: {e}")

    def init_completer(self):
        """初始化自动补全"""
        self.completer = QCompleter(self)
        self.completer.setWidget(self.text_input)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.activated.connect(self.insert_completion)
        
        # 设置补全列表显示样式
        popup = self.completer.popup()
        popup.setStyleSheet("""
            QListView {
                background-color: white;
                border: 1px solid #dadce0;
                selection-background-color: #e8f0fe;
                selection-color: #1967d2;
                padding: 4px;
            }
        """)

    def update_completer_model(self):
        """更新补全模型"""
        if not hasattr(self, 'main_page') or not self.main_page or not hasattr(self.main_page, 'canvas') or not self.main_page.canvas:
            return
        
        scene = self.main_page.canvas.scene
        titles = []
        for item in scene.items():
            if hasattr(item, 'node_title'):
                titles.append(f"@{item.node_title}")
        
        # 去重并排序
        titles = sorted(list(set(titles)))
        
        model = QStringListModel(titles, self.completer)
        self.completer.setModel(model)

    def insert_completion(self, completion):
        """插入补全内容"""
        tc = self.text_input.textCursor()
        # 获取当前单词前缀长度
        prefix_len = len(self.completer.completionPrefix())
        
        # 移动光标并选择前缀
        tc.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, prefix_len)
        tc.insertText(completion)
        self.text_input.setTextCursor(tc)

    def on_text_changed(self):
        """文本改变时触发自动补全"""
        if not hasattr(self, 'completer') or not self.completer:
            return
            
        content = self.text_input.toPlainText()
        tc = self.text_input.textCursor()
        pos = tc.position()
        
        # 获取光标前的文本
        text_up_to_cursor = content[:pos]
        if not text_up_to_cursor:
            return
            
        # 简单的分词逻辑：匹配最后一个以@开头的单词
        import re
        match = re.search(r'(@\S*)$', text_up_to_cursor)
        
        if match:
            current_word = match.group(1)
            
            # 如果刚输入 @，更新模型
            if current_word == "@":
                self.update_completer_model()
            
            # 设置前缀
            self.completer.setCompletionPrefix(current_word)
            
            # 如果有匹配项，显示弹窗
            if self.completer.completionCount() > 0:
                rect = self.text_input.cursorRect()
                rect.setWidth(self.completer.popup().sizeHintForColumn(0) + self.completer.popup().verticalScrollBar().sizeHint().width())
                self.completer.complete(rect)
        else:
            self.completer.popup().hide()

    def show_generate_image_button(self):
        self.generate_image_btn.setVisible(True)
    
    def hide_generate_image_button(self):
        self.generate_image_btn.setVisible(False)
    
    def on_generate_people_image_clicked(self):
        """生成人物图片 - 已修改为不依赖 PersonNode"""
        node = self.selected_node
        if not node:
            return
        
        # 检查是否是 GoogleScriptNode 或其他支持的节点
        # 如果是 PersonNode 相关的逻辑，应该已经不再使用
        # 这里保留逻辑以防有其他节点复用，但移除 PeopleImageManager 的导入
        
        try:
            # 暂时禁用此功能，直到确定如何处理
            self.output_text.setHtml(f"""
                <div style='color: #ff4444; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>功能维护中</p>
                    <p style='font-size: 12px; margin-top: 10px;'>人物图片生成功能正在调整中。</p>
                </div>
            """)
            return

            # 原有逻辑已注释，待确认是否需要保留针对非PersonNode的支持
            # mgr = getattr(node, "image_manager", None)
            # if mgr is None:
            #     # from lingdongpeoplePNG import PeopleImageManager  <-- REMOVED
            #     pass 
        except Exception as e:
            print(f"[工作台] 生成图片失败: {e}")
    
    def eventFilter(self, obj, event):
        """事件过滤器 - 检测文本输入框的点击事件"""
        if obj == self.text_input:
            # 检测鼠标按下或获得焦点事件
            if event.type() == event.Type.MouseButtonPress or event.type() == event.Type.FocusIn:
                # 显示模型配置区域
                if not self.config_frame.isVisible():
                    self.config_frame.setVisible(True)
                    print("[工作台] 显示模型配置区域")
        
        return super().eventFilter(obj, event)
    
    def hide_config_frame(self):
        """隐藏模型配置区域"""
        if self.config_frame.isVisible():
            self.config_frame.setVisible(False)
            print("[工作台] 隐藏模型配置区域")
    
    def on_provider_changed(self, provider: str):
        """提供商改变时更新模型列表（动态从API获取）"""
        # print(f"[灵动工作台] 提供商切换: {provider}")
        
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        
        # 优先使用缓存的动态模型
        if provider in self.dynamic_models_cache:
            models = self.dynamic_models_cache[provider]
            print(f"[灵动工作台] 使用缓存模型: {len(models)}个")
        else:
            # 尝试从API动态获取
            models = self.fetch_models_from_api(provider)
            if models:
                self.dynamic_models_cache[provider] = models
                print(f"[灵动工作台] 从API获取模型: {len(models)}个")
            else:
                models = []
        
        if not models:
            self.model_combo.addItem(f"⚠️ {provider} 暂无可用模型")
            self.model_combo.setEnabled(False)
        else:
            self.model_combo.setEnabled(True)
            self.model_combo.addItems(models)
            
            # 恢复上次选择
            saved_model = self.last_selected_models.get(provider, "")
            if saved_model and saved_model in models:
                index = self.model_combo.findText(saved_model)
                if index >= 0:
                    self.model_combo.setCurrentIndex(index)
        
        self.model_combo.blockSignals(False)
    
    def fetch_models_from_api(self, provider):
        """从API动态获取模型列表"""
        try:
            if not os.path.exists(self.config_file):
                print(f"[灵动工作台] 配置文件不存在")
                return []
            
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            api_key = config.get(f'{provider.lower()}_api_key', '')
            if not api_key:
                print(f"[灵动工作台] {provider} API Key未配置")
                return []
            
            api_url = config.get('api_url', 'https://manju.chat')
            hunyuan_api_url = config.get('hunyuan_api_url', 'https://api.vectorengine.ai')
            
            if provider == "Hunyuan":
                api_url = hunyuan_api_url
            
            import http.client
            import ssl
            from urllib.parse import urlparse
            
            parsed = urlparse(api_url)
            host = parsed.netloc or parsed.path.split('/')[0]
            
            if not host:
                return []
            
            context = ssl.create_default_context()
            conn = http.client.HTTPSConnection(host, context=context, timeout=10)
            
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            conn.request('GET', '/v1/models', '', headers)
            res = conn.getresponse()
            data = res.read()
            conn.close()
            
            if res.status == 200:
                result = json.loads(data.decode('utf-8'))
                if 'data' in result:
                    all_models = [model['id'] for model in result['data']]
                    
                    # 筛选当前提供商的模型
                    provider_models = []
                    provider_lower = provider.lower()
                    
                    for model_id in all_models:
                        if (provider_lower == "hunyuan" and model_id.startswith("hunyuan")) or \
                           (provider_lower == "chatgpt" and (model_id.startswith("gpt") or model_id.startswith("o1") or model_id.startswith("o3"))) or \
                           (provider_lower == "deepseek" and model_id.startswith("deepseek")) or \
                           (provider_lower == "claude" and model_id.startswith("claude")) or \
                           ("gemini" in provider_lower and model_id.startswith("gemini")):
                            provider_models.append(model_id)
                    
                    return provider_models
            return []
        except Exception as e:
            print(f"[灵动工作台] 从API获取模型失败: {e}")
            return []
    
    def load_lingdong_config(self):
        """加载灵动智能体配置（上次选择和对话历史）"""
        try:
            # 先初始化默认provider
            if self.providers:
                default_provider = 'DeepSeek' if 'DeepSeek' in self.providers else self.providers[0]
                self.on_provider_changed(default_provider)
            
            # 加载灵动智能体配置
            if os.path.exists(self.lingdong_config_file):
                with open(self.lingdong_config_file, 'r', encoding='utf-8') as f:
                    lingdong_config = json.load(f)
                    
                    # 恢复上次的provider选择
                    last_provider = lingdong_config.get('last_provider')
                    if last_provider and last_provider in self.providers:
                        index = self.provider_combo.findText(last_provider)
                        if index >= 0:
                            self.provider_combo.setCurrentIndex(index)
                            self.on_provider_changed(last_provider)
                    
                    # 恢复上次的model选择
                    last_model = lingdong_config.get('last_model')
                    if last_model:
                        index = self.model_combo.findText(last_model)
                        if index >= 0:
                            self.model_combo.setCurrentIndex(index)
                    
                    # 恢复上次的输入（不自动填充，仅记录）
                    last_input = lingdong_config.get('last_input', '')
                    # 可选：如果需要自动填充，取消下面的注释
                    # if last_input:
                    #     self.text_input.setPlainText(last_input)
                    
                    # 恢复对话历史
                    self.conversation_history = lingdong_config.get('conversation_history', [])
                    
                    print(f"[灵动智能体] 已加载配置: provider={last_provider}, model={last_model}, 历史记录={len(self.conversation_history)}条")
                    
        except Exception as e:
            print(f"[灵动智能体] 加载配置失败: {e}")

    def generate_character_prompts(self, prompt, callback=None, error_callback=None):
        """生成人物提示词 - 调用API并将结果输出到DEBUG"""
        provider = self.provider_combo.currentText()
        model = self.model_combo.currentText()
        
        if not provider or not model or "暂无可用模型" in model:
            print("[DEBUG] 未选择有效的模型或提供商")
            if error_callback:
                error_callback("未选择有效的模型或提供商")
            return
            
        print(f"[DEBUG] 开始生成人物提示词... Provider: {provider}, Model: {model}")
        print(f"[DEBUG] Prompt: {prompt[:100]}...") # 只打印前100个字符避免刷屏
        
        # 获取API配置
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            api_key = config.get(f'{provider.lower()}_api_key', '')
            api_url = config.get('api_url', 'https://manju.chat')
            hunyuan_api_url = config.get('hunyuan_api_url', 'https://api.vectorengine.ai')
            
            if not api_key:
                print(f"[DEBUG] {provider} API Key未配置")
                if error_callback:
                    error_callback(f"{provider} API Key未配置")
                return

            messages = [{"role": "user", "content": prompt}]
            
            # 创建并启动Worker
            worker = ChatWorker(provider, model, messages, api_key, api_url, hunyuan_api_url)
            
            # 连接流式输出信号，实现在工作台显示进度
            self.current_response = ""
            worker.chunk_received.connect(self.on_chunk_received)
            worker.error_occurred.connect(self.on_chat_error)
            
            # 连接信号
            if callback:
                worker.response_received.connect(callback)
            else:
                worker.response_received.connect(self._on_character_prompts_received)
            
            if error_callback:
                worker.error_occurred.connect(error_callback)
                
            worker.error_occurred.connect(lambda err: print(f"[DEBUG] 生成出错: {err}"))
            
            # 保存引用防止被垃圾回收
            self._temp_worker = worker
            worker.start()
            
        except Exception as e:
            print(f"[DEBUG] 启动生成任务失败: {e}")
            if error_callback:
                error_callback(f"启动生成任务失败: {e}")

    def _on_character_prompts_received(self, response):
        """接收人物提示词生成结果"""
        print("="*20 + " [DEBUG] 人物提示词生成结果 " + "="*20)
        print(response)
        print("="*60)

    
    def save_lingdong_config(self, provider=None, model=None, last_input=None):
        """保存灵动智能体配置到json/lingdong.json"""
        try:
            # 如果没有提供参数，使用当前选择
            if provider is None:
                provider = self.provider_combo.currentText()
            if model is None:
                model = self.model_combo.currentText()
            if last_input is None:
                last_input = self.text_input.toPlainText()
            
            import datetime
            config = {
                'last_provider': provider,
                'last_model': model,
                'last_input': last_input,
                'conversation_history': self.conversation_history,
                'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            with open(self.lingdong_config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            # print(f"[灵动智能体] 已保存配置: provider={provider}, model={model}, 历史记录={len(self.conversation_history)}条")
        except Exception as e:
            print(f"[灵动智能体] 保存配置失败: {e}")
    
    def on_model_changed(self, model: str):
        """模型切换时记录选择并保存配置"""
        provider = self.provider_combo.currentText()
        if provider and model and not model.startswith("⚠️"):
            self.last_selected_models[provider] = model
            # 保存配置
            self.save_lingdong_config(provider, model)
    
    def refresh_output(self):
        """清空工作台输出内容"""
        self.output_text.setHtml("""
            <div style='color: #666; text-align: center; margin-top: 100px;'>
                <p style='font-size: 14px;'>✨ 输出已清空</p>
                <p style='font-size: 12px; margin-top: 20px;'>
                    工作台已重置，<br/>
                    准备接收新的内容
                </p>
            </div>
        """)
        print("[工作台] 清空输出内容")
    
    def start_prompt_fine_tuning(self, prompt, callback):
        """启动提示词微调任务"""
        # 1. 检查模型选择
        provider = self.provider_combo.currentText()
        model = self.model_combo.currentText()
        
        if not provider or not model or "暂无" in model:
            QMessageBox.warning(self, "提示", "请先在工作台选择一个有效的模型！")
            self.config_frame.setVisible(True)
            return

        # 2. 显示在输入框（视觉反馈）
        # self.text_input.setPlainText(f"正在根据以下内容进行微调:\n{prompt}")
        self.config_frame.setVisible(True) # 确保配置可见
        
        # 3. 获取配置
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            api_key = config.get(f'{provider.lower()}_api_key', '')
            api_url = config.get('api_url', 'https://manju.chat')
            hunyuan_api_url = config.get('hunyuan_api_url', 'https://api.vectorengine.ai')
            
            # Hunyuan特殊处理
            if provider == "Hunyuan":
                base_url = hunyuan_api_url
            else:
                base_url = api_url
                
        except Exception as e:
            QMessageBox.warning(self, "配置错误", f"读取配置失败: {e}")
            return

        if not api_key:
            QMessageBox.warning(self, "配置缺失", f"请先在设置中配置 {provider} 的API Key！")
            return

        # 4. 构建配置字典
        chat_config = {
            "provider": provider,
            "model": model,
            "api_key": api_key,
            "base_url": base_url
        }
        
        # 5. 启动Worker
        try:
            # 延迟导入以避免循环依赖
            from ldrenwutishicifast import PromptVariationWorker
            
            # 清理旧worker
            if hasattr(self, 'fine_tune_worker') and self.fine_tune_worker.isRunning():
                self.fine_tune_worker.terminate()
                self.fine_tune_worker.wait()
            
            self.fine_tune_worker = PromptVariationWorker(prompt, chat_config)
            
            # 连接回调
            self.fine_tune_worker.prompt_generated.connect(callback)
            
            # 连接错误处理
            def on_error(msg):
                QMessageBox.warning(self, "生成失败", f"提示词微调出错:\n{msg}")
                self.output_text.setHtml(f"<div style='color:red'>生成失败: {msg}</div>")
                
            self.fine_tune_worker.error_occurred.connect(on_error)
            
            # 显示状态
            self.output_text.setHtml(f"""
                <div style='color: #00bfff; text-align: center; margin-top: 50px;'>
                    <p style='font-size: 14px;'>⏳ 正在微调提示词...</p>
                    <p style='font-size: 12px; margin-top: 10px; color: #666;'>
                        模型: {provider} / {model}<br/>
                        请稍候...
                    </p>
                </div>
            """)
            
            self.fine_tune_worker.start()
            
        except ImportError:
            QMessageBox.critical(self, "错误", "找不到 ldrenwutishicifast 模块")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动任务失败: {e}")

    def on_optimize_word(self):
        """词语优化按钮点击"""
        text = self.text_input.toPlainText().strip()
        
        if not text:
            QMessageBox.warning(self.parent(), "提示", "请先输入需要优化的文本！")
            return
        
        # 获取当前选择的模型配置
        provider = self.provider_combo.currentText()
        model = self.model_combo.currentText()
        
        # 读取API配置（使用和对话模式相同的配置文件）
        config_file = os.path.join(os.path.dirname(__file__), 'json', 'talk_api_config.json')
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                api_key = config.get(f'{provider.lower()}_api_key', '')
                api_url = config.get('api_url', 'https://manju.chat')
                hunyuan_api_url = config.get('hunyuan_api_url', 'https://api.vectorengine.ai')
        except Exception as e:
            QMessageBox.critical(self.parent(), "错误", f"读取API配置失败：{str(e)}")
            return
        
        if not api_key:
            QMessageBox.warning(self.parent(), "提示", f"请先在设置中配置 {provider} 的API密钥！")
            return
        
        print(f"[词语优化] 开始优化 - Provider: {provider}, Model: {model}")
        
        # 禁用按钮，防止重复点击
        self.optimize_btn.setEnabled(False)
        self.send_btn.setEnabled(False)
        
        # 显示优化中提示
        original_text = self.text_input.toPlainText()
        self.text_input.setPlainText("⏳ 正在优化中，请稍候...")
        
        # 创建并启动优化线程
        self.optimize_thread = optimize_word(
            text=text,
            provider=provider,
            model=model,
            api_key=api_key,
            api_url=api_url,
            hunyuan_api_url=hunyuan_api_url,
            callback=self.on_optimize_success,
            error_callback=lambda err: self.on_optimize_error(err, original_text)
        )
        self.optimize_thread.start()
    
    def on_optimize_success(self, optimized_text):
        """词语优化成功"""
        print(f"[词语优化] 优化成功")
        
        # 恢复按钮
        self.optimize_btn.setEnabled(True)
        self.send_btn.setEnabled(True)
        
        # 显示优化后的文本
        self.text_input.setPlainText(optimized_text)
        
        # 保存优化后的文本到配置
        provider = self.provider_combo.currentText()
        model = self.model_combo.currentText()
        self.save_lingdong_config(provider, model, optimized_text)
        
        # 显示通知
        self.output_text.setHtml(f"""
            <div style='color: #00ff88; padding: 10px;'>
                <p style='font-size: 13px; font-weight: bold;'>✅ 词语优化完成</p>
                <p style='font-size: 12px; color: #888; margin-top: 8px;'>
                    已将优化后的提示词更新到输入框中
                </p>
            </div>
        """)
    
    def on_optimize_error(self, error_msg, original_text):
        """词语优化失败"""
        print(f"[词语优化] 优化失败: {error_msg}")
        
        # 恢复按钮和原文本
        self.optimize_btn.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.text_input.setPlainText(original_text)
        
        # 显示错误信息
        QMessageBox.critical(self.parent(), "优化失败", error_msg)
    
    def on_context_btn_clicked(self):
        """点击上下文引用按钮"""
        if hasattr(self, 'context_btn'):
            # 使用全局坐标显示菜单
            pos = self.context_btn.mapToGlobal(self.context_btn.rect().bottomLeft())
            self.chat_context_manager.create_context_menu(self, pos)

    def add_context_tag(self, title, content):
        """添加上下文标签"""
        # 检查是否已存在
        for ctx in self.active_contexts:
            if ctx['title'] == title:
                return
        
        self.active_contexts.append({'title': title, 'content': content})
        
        # 创建标签UI
        tag = QFrame()
        tag.setObjectName("ContextTag")
        tag.setStyleSheet("""
            #ContextTag {
                background-color: #e8f0fe;
                border: 1px solid #d2e3fc;
                border-radius: 12px;
            }
        """)
        tag_layout = QHBoxLayout(tag)
        tag_layout.setContentsMargins(8, 2, 8, 2)
        tag_layout.setSpacing(4)
        
        # 图标/文字
        lbl = QLabel(f"@{title}")
        lbl.setStyleSheet("color: #1a73e8; font-size: 12px; font-weight: bold; border: none; background: transparent;")
        tag_layout.addWidget(lbl)
        
        # 关闭按钮
        close_btn = QPushButton("×")
        close_btn.setFixedSize(16, 16)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("取消引用")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #1a73e8;
                border: none;
                font-size: 14px;
                font-weight: bold;
                margin-top: -2px;
            }
            QPushButton:hover {
                color: #d93025;
            }
        """)
        # 使用闭包绑定
        close_btn.clicked.connect(lambda checked=False, t=title, w=tag: self.remove_context_tag(t, w))
        tag_layout.addWidget(close_btn)
        
        self.context_layout.addWidget(tag)
        self.context_display_widget.setVisible(True)
        
        # 更新输入框提示
        self.text_input.setPlaceholderText("请输入你的问题...")

    def remove_context_tag(self, title, tag_widget):
        """移除上下文标签"""
        # 从数据中移除
        self.active_contexts = [ctx for ctx in self.active_contexts if ctx['title'] != title]
        
        # 从UI移除
        self.context_layout.removeWidget(tag_widget)
        tag_widget.deleteLater()
        
        # 如果没有了，隐藏区域
        if not self.active_contexts:
            self.context_display_widget.setVisible(False)
            self.text_input.setPlaceholderText("请输入你的问题或提示词...")

    def on_send_message(self):
        """发送消息按钮点击"""
        text = self.text_input.toPlainText().strip()
        provider = self.provider_combo.currentText()
        model = self.model_combo.currentText()
        images = []
        if hasattr(self, "image_upload_manager"):
            images = self.image_upload_manager.get_images()
        
        if not text and not images:
            QMessageBox.warning(self.parent(), "提示", "请输入内容或上传图片！")
            return
        
        if not model or model.startswith("⚠️"):
            QMessageBox.warning(self.parent(), "提示", "请选择有效的模型！")
            return
        
        # 检查API配置
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                api_key = config.get(f'{provider.lower()}_api_key', '')
                api_url = config.get('api_url', 'https://manju.chat')
                hunyuan_api_url = config.get('hunyuan_api_url', 'https://api.vectorengine.ai')
        except Exception as e:
            QMessageBox.critical(self.parent(), "错误", f"读取API配置失败：{str(e)}")
            return
        
        if not api_key:
            QMessageBox.warning(self.parent(), "提示", f"请先在设置中配置 {provider} 的API密钥！")
            return
        
        # 保存原始文本用于配置保存
        original_text = text
        
        # 注入手动选择的上下文
        if hasattr(self, 'active_contexts') and self.active_contexts:
            context_text = "\n\n".join([f"【引用内容：{ctx['title']}】\n{ctx['content']}" for ctx in self.active_contexts])
            print(f"[工作台] 注入上下文: {[ctx['title'] for ctx in self.active_contexts]}")
            text = f"{context_text}\n\n{text}"
            
            # 清除上下文
            while self.context_layout.count():
                item = self.context_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self.active_contexts = []
            self.context_display_widget.setVisible(False)
            self.text_input.setPlaceholderText("请输入你的问题或提示词...")
        
        # 处理 @提及 功能：从场景中提取节点数据
        try:
            if hasattr(self, 'main_page') and self.main_page and hasattr(self.main_page, 'canvas') and self.main_page.canvas:
                scene = self.main_page.canvas.scene
                from AIchatquestion import process_user_message
                text = process_user_message(text, scene)
        except Exception as e:
            print(f"[工作台] 处理@提及失败: {e}")
            import traceback
            traceback.print_exc()

        print(f"[灵动智能体] 发送消息 - Provider: {provider}, Model: {model}")
        print(f"[灵动智能体] 消息内容: {text[:100]}...")
        
        import datetime
        import base64
        message_content = text
        if images:
            content = []
            if text:
                content.append({"type": "text", "text": text})
            for img_path in images:
                try:
                    with open(img_path, "rb") as f:
                        img_data = base64.b64encode(f.read()).decode("utf-8")
                    import os as _os
                    img_ext = _os.path.splitext(img_path)[1].lower()
                    mime_type = {
                        ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg",
                        ".png": "image/png",
                        ".webp": "image/webp",
                        ".gif": "image/gif",
                    }.get(img_ext, "image/jpeg")
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{img_data}"
                            },
                        }
                    )
                except Exception:
                    pass
            message_content = content
        
        message_record = {
            "role": "user",
            "content": message_content,
            "provider": provider,
            "model": model,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.conversation_history.append(message_record)
        
        # 保存配置和历史记录 (保存原始输入，避免下次启动加载大量数据)
        self.save_lingdong_config(provider, model, original_text)
        
        # 清空输入框和图片
        self.text_input.clear()
        if hasattr(self, "image_upload_manager"):
            self.image_upload_manager.clear_images()
        
        # 显示发送中状态
        self.output_text.setHtml(f"""
            <div style='color: #00bfff; text-align: center; margin-top: 100px;'>
                <p style='font-size: 14px;'>⏳ 正在处理中...</p>
                <p style='font-size: 12px; margin-top: 20px; color: #666;'>
                    模型：{model}<br/>
                    消息长度：{len(text)} 字符<br/>
                    历史记录：{len(self.conversation_history)} 条
                </p>
            </div>
        """)
        
        # 禁用发送按钮
        self.send_btn.setEnabled(False)
        self.optimize_btn.setEnabled(False)
        
        # 构建消息列表（使用对话历史）
        messages = []
        for msg in self.conversation_history:
            messages.append({
                'role': msg['role'],
                'content': msg['content']
            })
        
        # 创建并启动聊天线程
        
        self.chat_worker = ChatWorker(provider, model, messages, api_key, api_url, hunyuan_api_url)
        self.chat_worker.chunk_received.connect(self.on_chunk_received)
        self.chat_worker.response_received.connect(self.on_response_received)
        self.chat_worker.error_occurred.connect(self.on_chat_error)
        self.chat_worker.finished.connect(self.on_chat_finished)
        self.chat_worker.start()
        
        # 初始化接收内容
        self.current_response = ""
    
    def append_output(self, text):
        """追加输出内容"""
        self.output_text.append(text)
    
    def on_chunk_received(self, chunk):
        """接收到流式响应块"""
        # 如果是第一块（当前响应内容为空），清空原有显示内容（如"等待中..."）
        if not self.current_response:
            self.output_text.clear()

        self.current_response += chunk
        
        # 使用insertPlainText追加内容，避免setHtml全量刷新的性能问题
        self.output_text.moveCursor(QTextCursor.End)
        self.output_text.insertPlainText(chunk)
        
        # 滚动到底部
        sb = self.output_text.verticalScrollBar()
        sb.setValue(sb.maximum())
    
    def on_response_received(self, full_response):
        """接收到完整响应"""
        print(f"[灵动智能体] 收到完整响应: {len(full_response)} 字符")
        
        # 保存AI响应到对话历史
        import datetime
        ai_message = {
            'role': 'assistant',
            'content': full_response,
            'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        self.conversation_history.append(ai_message)
        
        # 尝试自动创建文本节点
        if hasattr(self, 'auto_text_manager'):
            # TextNode 是模块全局变量
            self.auto_text_manager.handle_response(full_response, TextNode)
        
        # 保存配置
        provider = self.provider_combo.currentText()
        model = self.model_combo.currentText()
        self.save_lingdong_config(provider, model, self.text_input.toPlainText())
        
        # 格式化显示
        # 流式输出已经显示了内容，这里不再重置显示，避免闪烁
        # formatted_text = full_response.replace('\n', '<br/>')
        # self.output_text.setHtml(f"""
        #    <div style='color: #000000; padding: 15px; line-height: 1.8;'>
        #        <p style='font-size: 13px;'>{formatted_text}</p>
        #    </div>
        # """)
    
    def on_chat_error(self, error_msg):
        """聊天错误"""
        print(f"[灵动智能体] 聊天错误: {error_msg}")
        self.output_text.setHtml(f"""
            <div style='color: #ff4444; padding: 15px; text-align: center; margin-top: 80px;'>
                <p style='font-size: 14px; font-weight: bold;'>❌ 请求失败</p>
                <p style='font-size: 12px; margin-top: 15px; color: #ff6666;'>{error_msg}</p>
            </div>
        """)
    
    def on_chat_finished(self):
        """聊天完成"""
        print("[灵动智能体] 聊天完成")
        # 恢复按钮
        self.send_btn.setEnabled(True)
        self.optimize_btn.setEnabled(True)
    
    def show_storyboard_button(self):
        """显示剧本一键分镜按钮"""
        self.storyboard_action.setVisible(True)
        print("[工作台] 显示剧本一键分镜按钮")
    
    def hide_storyboard_button(self):
        """隐藏剧本一键分镜按钮"""
        self.storyboard_action.setVisible(False)
        print("[工作台] 隐藏剧本一键分镜按钮")
    
    def show_generate_prompt_button(self):
        """显示生成内容菜单按钮"""
        # self.generate_menu_btn.setVisible(True)
        print("[工作台] (Deprecated) 显示生成内容菜单按钮")
    
    def hide_generate_prompt_button(self):
        """隐藏生成内容菜单按钮"""
        # self.generate_menu_btn.setVisible(False)
        # 隐藏菜单时也隐藏人物生成选项
        if hasattr(self, 'people_real_action'):
            self.people_real_action.setVisible(False)
        if hasattr(self, 'people_anime_action'):
            self.people_anime_action.setVisible(False)
        print("[工作台] 隐藏人物生成选项")
    

    
    def _extract_people_from_node(self, node):
        """从节点中提取人物名称列表"""
        people_names = set()
        
        # 如果是分镜节点，从表格提取人物
        if hasattr(node, 'table_data') and node.table_data:
            headers = node.headers if hasattr(node, 'headers') else []
            people_col_index = -1
            
            # 找到"人物"列
            for i, header in enumerate(headers):
                if "人物" in header:
                    people_col_index = i
                    break
            
            # 提取人物名称
            if people_col_index != -1:
                for row in node.table_data:
                    if people_col_index < len(row):
                        people_text = str(row[people_col_index]).strip()
                        if people_text and people_text != "-" and people_text != "无":
                            # 处理多个人物（如"张三、李四"）
                            for name in people_text.replace('、', ',').replace('，', ',').split(','):
                                name = name.strip()
                                if name and name != "-" and name != "无":
                                    people_names.add(name)
        
        return sorted(list(people_names))  # 返回排序后的列表
    
    def _get_connected_people_node(self, node):
        """获取节点连接的人物节点 - 已移除"""
        return None

    def _update_people_menu_visibility(self):
        """更新人物生成菜单项的可见性"""
        # 强制隐藏人物生成菜单
        is_visible = False
        
        # 1. 检查选中节点是否是人物节点
        # if self.selected_node and getattr(self.selected_node, 'node_title', '') == "人物角色":
        #     # 2. 检查是否有连接的内容节点（分镜或文档）
        #     if self._find_upstream_content_node(self.selected_node):
        #         is_visible = True
        
        # 更新菜单项可见性
        if hasattr(self, 'people_real_action'):
            self.people_real_action.setVisible(is_visible)
        if hasattr(self, 'people_anime_action'):
            self.people_anime_action.setVisible(is_visible)

    def _find_upstream_content_node(self, node):
        """查找上游连接的内容节点（分镜脚本或文字节点）"""
        if not node or not hasattr(node, 'input_sockets'):
            return None
            
        # 遍历所有输入接口
        for input_socket in node.input_sockets:
            # 遍历接口的所有连接
            for connection in input_socket.connections:
                if connection.source_socket:
                    source_node = connection.source_socket.parent_node
                    
                    # 1. 检查是否是分镜节点 (有table_data属性)
                    if hasattr(source_node, 'table_data'):
                        return source_node
                        
                    # 2. 检查是否是文字节点 (有full_text或text_edit属性)
                    if hasattr(source_node, 'full_text') or hasattr(source_node, 'text_edit'):
                        return source_node
                        
                    # 3. 通过标题辅助判断
                    title = getattr(source_node, 'node_title', '')
                    if "分镜" in title or "脚本" in title or "文字" in title or "文本" in title:
                        return source_node
                        
        return None
            
    def set_selected_node(self, node):
        """设置当前选中的节点"""
        self.selected_node = node
        if node:
            print(f"[工作台] 设置选中节点: {node.node_title if hasattr(node, 'node_title') else 'Unknown'}")
        else:
            print("[工作台] 清除选中节点")
            
        # 更新人物生成菜单的可见性
        self._update_people_menu_visibility()

        # 更新视频拆分按钮的可见性
        if is_video_connected_to_image(node):
            self.video_split_action.setVisible(True)
        else:
            self.video_split_action.setVisible(False)

        # 更新谷歌镜头拆分按钮的可见性
        self._update_google_split_btn_visibility(node)

    def _update_google_split_btn_visibility(self, node):
        """更新谷歌镜头拆分按钮可见性"""
        should_show = False
        if node:
            title = getattr(node, 'node_title', '')
            
            # 情况1: 选中谷歌剧本节点，且连接了视频
            if "谷歌剧本" in title:
                if hasattr(node, 'input_sockets'):
                    for socket in node.input_sockets:
                        for conn in socket.connections:
                            if conn.source_socket:
                                src = conn.source_socket.parent_node
                                if "视频" in getattr(src, 'node_title', ''):
                                    should_show = True
                                    break
                        if should_show: break
            
            # 情况2: 选中视频节点，且连接了谷歌剧本
            elif "视频" in title:
                if hasattr(node, 'output_sockets'):
                    for socket in node.output_sockets:
                        for conn in socket.connections:
                            if conn.target_socket:
                                dst = conn.target_socket.parent_node
                                if "谷歌剧本" in getattr(dst, 'node_title', ''):
                                    should_show = True
                                    break
                        if should_show: break
                        
        self.google_split_action.setVisible(should_show)

    def _get_ffmpeg_path(self):
        """获取FFmpeg路径"""
        config_file = os.path.join(self.config_dir, 'gugechaifen.json')
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get('ffmpeg_path', 'ffmpeg')
            except:
                pass
        return 'ffmpeg'

    def _save_ffmpeg_path(self, path):
        """保存FFmpeg路径"""
        config_file = os.path.join(self.config_dir, 'gugechaifen.json')
        try:
            config = {}
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            
            config['ffmpeg_path'] = path
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存FFmpeg路径失败: {e}")

    def on_google_split_clicked(self):
        """处理谷歌镜头拆分"""
        target_google_node = None
        video_node = None
        
        # Determine nodes based on selection
        if self.selected_node:
            if "谷歌剧本" in getattr(self.selected_node, 'node_title', ''):
                target_google_node = self.selected_node
                # Find connected video node
                if hasattr(target_google_node, 'input_sockets'):
                    for socket in target_google_node.input_sockets:
                        for conn in socket.connections:
                            if conn.source_socket:
                                src = conn.source_socket.parent_node
                                if "视频" in getattr(src, 'node_title', ''):
                                    video_node = src
                                    break
                        if video_node: break
            elif "视频" in getattr(self.selected_node, 'node_title', ''):
                video_node = self.selected_node
                # Find connected google node (pick first)
                if hasattr(video_node, 'output_sockets'):
                    for socket in video_node.output_sockets:
                        for conn in socket.connections:
                            if conn.target_socket:
                                dst = conn.target_socket.parent_node
                                if "谷歌剧本" in getattr(dst, 'node_title', ''):
                                    target_google_node = dst
                                    break
                        if target_google_node: break
        
        if not target_google_node or not video_node:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "提示", "请确保谷歌剧本节点与视频节点已连接")
            return
            
        video_path = getattr(video_node, "video_path", None)
        if not video_path or not os.path.exists(video_path):
             from PySide6.QtWidgets import QMessageBox
             QMessageBox.warning(self, "提示", "视频节点未加载视频")
             return
             
        # Collect timecodes
        timecode_data = [] # (row_idx, timecode_str)
        table = target_google_node.table
        for row in range(table.rowCount()):
            item = table.item(row, 1) # Column 1 is Timecode
            if item and item.text().strip():
                timecode_data.append((row, item.text().strip()))
        
        if not timecode_data:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "提示", "谷歌剧本中没有时间码数据")
            return
            
        # 弹出设置对话框
        from lingdongchaifen import GoogleSplitDialog
        dialog = GoogleSplitDialog(video_path, len(timecode_data), self)
        if dialog.exec() != QDialog.Accepted:
            return
            
        output_dir = dialog.out_edit.text().strip()
        ffmpeg_path = dialog.ffmpeg_edit.text().strip()
            
        # Start splitting
        from lingdonggugechaifen import GoogleVideoSplitter
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        self.google_splitter = GoogleVideoSplitter(video_path, output_dir, timecode_data, ffmpeg_path=ffmpeg_path)
        self.google_splitter.finished_with_data.connect(lambda success, msg, results: self.on_google_split_finished(success, msg, results, target_google_node))
        self.google_splitter.start()
        
        # Show progress (optional, maybe update button text)
        self.google_split_action.setText("正在拆分...")
        self.google_split_action.setEnabled(False)

    def on_google_split_finished(self, success, msg, results, node):
        self.google_split_action.setText("📷 谷歌镜头拆分")
        self.google_split_action.setEnabled(True)
        
        if not success:
            if "未检测到FFmpeg" in msg:
                from PySide6.QtWidgets import QMessageBox, QFileDialog
                reply = QMessageBox.critical(self, "错误", 
                    f"{msg}\n\n是否手动指定FFmpeg路径？",
                    QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    file_path, _ = QFileDialog.getOpenFileName(self, "选择FFmpeg可执行文件", "", "Executables (*.exe);;All Files (*)")
                    if file_path:
                        self._save_ffmpeg_path(file_path)
                        QMessageBox.information(self, "提示", "FFmpeg路径已保存，请重新点击“谷歌镜头拆分”按钮。")
            else:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "错误", msg)
            return
            
        # Update table
        from PySide6.QtWidgets import QTableWidgetItem
        from PySide6.QtGui import QIcon
        from PySide6.QtCore import QSize
        
        table = node.table
        
        # === 动态查找或创建图片列 ===
        headers = []
        for c in range(table.columnCount()):
            item = table.horizontalHeaderItem(c)
            headers.append(item.text() if item else "")
            
        target_start_header = "开始帧"
        target_end_header = "结束帧"
        
        start_col = -1
        end_col = -1
        
        # 1. 查找现有列
        if target_start_header in headers:
            start_col = headers.index(target_start_header)
        if target_end_header in headers:
            end_col = headers.index(target_end_header)
            
        # 2. 如果没找到，追加新列
        # 策略：如果存在"备注"列，尝试加在备注后面？或者直接加在最后？
        # 用户要求："在现有的谷歌节点中备注后面新增"
        # 简单起见，且为了保证不覆盖，我们直接追加到表格末尾
        
        if start_col == -1:
            table.insertColumn(table.columnCount())
            start_col = table.columnCount() - 1
            table.setHorizontalHeaderItem(start_col, QTableWidgetItem(target_start_header))
            
        if end_col == -1:
            table.insertColumn(table.columnCount())
            end_col = table.columnCount() - 1
            table.setHorizontalHeaderItem(end_col, QTableWidgetItem(target_end_header))

        table.setIconSize(QSize(140, 80))
        
        for item in results:
            row = item['row']
            start_img = item['start_img']
            end_img = item['end_img']
            
            # Helper to set image item
            def set_img_item(col, img_path):
                if img_path and os.path.exists(img_path):
                    table_item = QTableWidgetItem()
                    table_item.setIcon(QIcon(img_path))
                    table_item.setToolTip(img_path)
                    table_item.setData(Qt.UserRole, img_path) # Store path
                    table.setItem(row, col, table_item)
                    table.setRowHeight(row, 90)
            
            if start_img:
                set_img_item(start_col, start_img)
            if end_img:
                set_img_item(end_col, end_img)
        
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "完成", f"已提取 {len(results)} 组镜头图片")

    def on_video_split_clicked(self):
        """处理视频拆分按钮点击"""
        if not self.selected_node:
            return
            
        # 获取视频路径
        video_path = getattr(self.selected_node, "video_path", None)
        if not video_path:
            QMessageBox.warning(self, "错误", "无法获取视频路径，请确保已加载视频。")
            return
            
        # 打开拆分对话框
        dialog = VideoSplitDialog(video_path, self)
        if dialog.exec() == QDialog.Accepted:
            # 获取生成的文件列表
            generated_files = dialog.generated_files
            if generated_files:
                scene = self.selected_node.scene()
                if not scene:
                    return
                    
                # 计算起始位置（在视频节点右侧）
                # 注意：pos()返回的是场景坐标
                start_x = self.selected_node.pos().x() + self.selected_node.boundingRect().width() + 50
                start_y = self.selected_node.pos().y()
                
                # 检查拆分模式
                is_multi_mode = False
                if hasattr(dialog, 'radio_multi_node') and dialog.radio_multi_node.isChecked():
                    is_multi_mode = True
                
                if is_multi_mode:
                    # 多图模式：创建一个节点，包含所有图片
                    try:
                        # 过滤图片文件
                        image_files = [f for f in generated_files if os.path.splitext(f)[1].lower() in ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp']]
                        
                        if image_files:
                            # 创建图片节点
                            node = ImageNode(start_x, start_y)
                            scene.addItem(node)
                            
                            # 开启多图模式
                            node.is_group_mode = True
                            node.group_btn.setDefaultTextColor(QColor("#00bfff"))
                            
                            # 加载所有图片
                            node.image_paths = image_files
                            node.current_index = 0
                            
                            # 显示第一张
                            node.load_current_image()
                            node.update_group_ui()
                            
                            print(f"[视频拆分] 创建多图节点: {len(image_files)} 张图片")
                        else:
                            print("[视频拆分] 未找到图片文件")
                            
                    except Exception as e:
                        print(f"[视频拆分] 创建多图节点失败: {e}")
                else:
                    # 单图模式：每个文件一个节点
                    for i, file_path in enumerate(generated_files):
                        # 简单的网格布局：每行5个
                        row = i // 5
                        col = i % 5
                        
                        x = start_x + col * 280  # 假设节点宽度约250 + 间距
                        y = start_y + row * 280
                        
                        try:
                            # 检查文件扩展名
                            ext = os.path.splitext(file_path)[1].lower()
                            
                            if ext in ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp']:
                                # 创建图片节点
                                node = ImageNode(x, y)
                                scene.addItem(node)
                                node.load_image(file_path)
                                print(f"[视频拆分] 创建图片节点: {file_path}")
                            elif ext in ['.mp4', '.avi', '.mov', '.mkv', '.wmv']:
                                # 创建视频节点
                                node = VideoNode(x, y)
                                scene.addItem(node)
                                node.load_video(file_path)
                                print(f"[视频拆分] 创建视频节点: {file_path}")
                            else:
                                print(f"[视频拆分] 未知文件类型，跳过: {file_path}")
                                
                        except Exception as e:
                            print(f"[视频拆分] 创建节点失败: {e}")

    
    def on_storyboard_clicked(self):
        """剧本一键分镜按钮点击 - 支持连接节点的智能分镜"""
        # 获取当前选择的模型信息
        provider = self.provider_combo.currentText()
        model = self.model_combo.currentText()
        
        print(f"[工作台] 点击剧本一键分镜")
        print(f"[工作台] 当前选择: Provider={provider}, Model={model}")
        
        # 检查是否有选中的节点
        if not self.selected_node:
            self.output_text.setHtml("""
                <div style='color: #ff4444; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>❌ 错误</p>
                    <p style='font-size: 12px; margin-top: 10px;'>未选中文字节点</p>
                </div>
            """)
            return
        
        # 获取文字节点的完整文本
        script_text = ""
        if hasattr(self.selected_node, 'full_text'):
            script_text = self.selected_node.full_text
        elif hasattr(self.selected_node, 'content_text'):
            script_text = self.selected_node.content_text.toPlainText()
        
        if not script_text or script_text == "双击输入文字...":
            self.output_text.setHtml("""
                <div style='color: #ff4444; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>❌ 错误</p>
                    <p style='font-size: 12px; margin-top: 10px;'>文字节点内容为空</p>
                </div>
            """)
            return
        
        # ⭐ 检查是否连接到表格节点，获取自定义表头
        target_table_node = None
        custom_headers = None
        
        if hasattr(self.selected_node, 'output_sockets'):
            for output_socket in self.selected_node.output_sockets:
                for connection in output_socket.connections:
                    if connection.target_socket:
                        target_node = connection.target_socket.parent_node
                        # 检查是否是表格节点
                        if hasattr(target_node, 'headers') and hasattr(target_node, 'table_data'):
                            target_table_node = target_node
                            custom_headers = target_node.headers if hasattr(target_node, 'headers') else None
                            
                            # 特殊处理：如果是谷歌剧本节点
                            if hasattr(target_node, 'node_title') and "谷歌剧本" in target_node.node_title:
                                # 检查是否是默认表头，如果是，则升级为详细分镜表头
                                default_8_cols = ["镜号", "时间码", "景别", "画面内容", "台词/音效", "备注", "开始帧", "结束帧"]
                                if custom_headers == default_8_cols:
                                    print(f"[智能分镜] 检测到谷歌剧本节点（默认表头），自动切换为详细分镜表头")
                                    full_headers = ["镜号", "时间码", "景别", "画面内容", "人物", "人物关系/构图", "地点/环境", "运镜", "台词/音效", "备注"]
                                    target_node.headers = full_headers
                                    custom_headers = full_headers
                                
                                # 旧逻辑兼容：如果仍然是包含开始帧/结束帧的表头（未被上面的逻辑覆盖），则忽略最后两列
                                elif custom_headers and len(custom_headers) >= 8:
                                    if len(custom_headers) > 6 and custom_headers[6] == "开始帧" and custom_headers[7] == "结束帧":
                                        print(f"[智能分镜] 检测到谷歌剧本节点，自动忽略图片列，仅使用前6列生成")
                                        custom_headers = custom_headers[:6]
                                    
                            print(f"[智能分镜] 检测到连接的表格节点")
                            if custom_headers:
                                print(f"[智能分镜] 使用自定义表头: {custom_headers}")
                            break
                if target_table_node:
                    break
        
        # ⚠️ 必须连接到表格节点才能执行分镜
        if not target_table_node:
            self.output_text.setHtml("""
                <div style='color: #ff9800; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>⚠️ 需要连接表格节点</p>
                    <p style='font-size: 12px; margin-top: 10px;'>
                        请先将文字节点的输出连接到表格节点<br/>
                        一键分镜会将结果输出到连接的表格中
                    </p>
                </div>
            """)
            return
        
        # 保存目标表格节点供后续使用
        self.target_table_node = target_table_node
        self.custom_headers = custom_headers
        
        # 显示处理中提示
        header_info = ""
        if custom_headers:
            header_info = f"<br/>表格格式: {', '.join(custom_headers)}"
        
        self.output_text.setHtml(f"""
            <div style='color: #00bfff; padding: 15px; text-align: center;'>
                <p style='font-size: 14px; font-weight: bold;'>🎬 正在分析剧本...</p>
                <p style='font-size: 12px; color: #888; margin-top: 10px;'>
                    使用 {provider} / {model}<br/>
                    生成分镜脚本表格{header_info}
                </p>
            </div>
        """)
        
        # 禁用按钮
        self.storyboard_action.setEnabled(False)
        
        # 调用AI生成分镜
        self.generate_storyboard(script_text, custom_headers)
    
    def on_generate_prompt_clicked(self):
        """生成绘图提示词按钮点击 - 为分镜脚本的每一行生成中英文绘图提示词"""
        # 获取当前选择的模型信息
        provider = self.provider_combo.currentText()
        model = self.model_combo.currentText()
        
        print(f"[生成提示词] 点击生成绘图提示词")
        print(f"[生成提示词] 当前选择: Provider={provider}, Model={model}")
        
        # 检查是否有选中的分镜节点
        if not self.selected_node:
            self.output_text.setHtml("""
                <div style='color: #ff4444; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>❌ 错误</p>
                    <p style='font-size: 12px; margin-top: 10px;'>未选中分镜脚本节点</p>
                </div>
            """)
            return
        
        # 检查节点是否有表格数据
        if not hasattr(self.selected_node, 'table_data') or not self.selected_node.table_data:
            self.output_text.setHtml("""
                <div style='color: #ff9800; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>⚠️ 提示</p>
                    <p style='font-size: 12px; margin-top: 10px;'>分镜脚本表格为空<br/>请先生成或添加分镜内容</p>
                </div>
            """)
            return
        
        # 检查表格是否已经有提示词列
        if DrawingPromptGenerator.check_prompts_exist(self.selected_node):
            self.output_text.setHtml("""
                <div style='color: #ff9800; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>⚠️ 提示</p>
                    <p style='font-size: 12px; margin-top: 10px;'>表格已包含提示词列<br/>如需重新生成，请先删除现有提示词列</p>
                </div>
            """)
            return
        
        # 显示处理中提示
        row_count = len(self.selected_node.table_data)
        self.output_text.setHtml(f"""
            <div style='color: #9d5cff; padding: 15px; text-align: center;'>
                <p style='font-size: 14px; font-weight: bold;'>🎨 正在生成绘图提示词...</p>
                <p style='font-size: 12px; color: #888; margin-top: 10px;'>
                    使用 {provider} / {model}<br/>
                    为 {row_count} 个镜头生成中英文提示词
                </p>
            </div>
        """)
        
        # 禁用菜单按钮
        self.toolbox_btn.setEnabled(False)
        
        # 调用AI生成提示词
        self.generate_drawing_prompts()
    
    def generate_drawing_prompts(self):
        """为分镜脚本表格生成中英文绘图提示词 - 使用lingdongPrompt模块"""
        # 获取当前用户选择的provider和model
        provider = self.provider_combo.currentText()
        model = self.model_combo.currentText()
        
        # 验证模型选择
        if not provider or not model or model.startswith("⚠️"):
            self.output_text.setHtml("""
                <div style='color: #ff4444; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>❌ 错误</p>
                    <p style='font-size: 12px; margin-top: 10px;'>请先选择有效的模型</p>
                </div>
            """)
            self.toolbox_btn.setEnabled(True)
            return
        
        # 获取表格数据和表头
        table_data = self.selected_node.table_data
        headers = self.selected_node.headers if hasattr(self.selected_node, 'headers') else []
        
        # 创建提示词生成器
        generator = DrawingPromptGenerator(self.config_file)
        
        # 定义回调函数
        callbacks = {
            'on_batch_completed': self.on_batch_completed,
            'on_progress': self.on_prompt_progress,
            'on_completed': self.on_all_prompts_completed,
            'on_error': self.on_prompts_error
        }
        
        try:
            # 启动生成任务
            self.batch_prompt_worker = generator.generate_prompts(
                provider, model, table_data, headers,
                batch_size=5,  # 每批5行
                callbacks=callbacks
            )
        except Exception as e:
            self.output_text.setHtml(f"""
                <div style='color: #ff4444; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>❌ 错误</p>
                    <p style='font-size: 12px; margin-top: 10px;'>{str(e)}</p>
                </div>
            """)
            self.toolbox_btn.setEnabled(True)
    
    def on_batch_completed(self, batch_num, batch_prompts):
        """单个批次完成"""
        print(f"[生成提示词] 批次 {batch_num} 处理完成")
    
    def on_prompt_progress(self, current, total):
        """更新进度显示"""
        provider = self.provider_combo.currentText()
        model = self.model_combo.currentText()
        progress = int((current / total) * 100)
        
        self.output_text.setHtml(f"""
            <div style='color: #9d5cff; padding: 15px; text-align: center;'>
                <p style='font-size: 14px; font-weight: bold;'>🎨 正在生成绘图提示词...</p>
                <p style='font-size: 12px; color: #888; margin-top: 10px;'>
                    使用 {provider} / {model}<br/>
                    进度: {current}/{total} ({progress}%)
                </p>
                <div style='width: 80%; height: 8px; background: #2a2a2a; border-radius: 4px; margin: 15px auto;'>
                    <div style='width: {progress}%; height: 100%; background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); border-radius: 4px; transition: width 0.3s;'></div>
                </div>
            </div>
        """)
    
    def on_all_prompts_completed(self, all_prompts):
        """所有批次完成，更新表格 - 使用lingdongPrompt模块"""
        print(f"[生成提示词] 开始更新表格，共 {len(all_prompts)} 条提示词")
        
        try:
            # 使用DrawingPromptGenerator的静态方法更新表格
            success_count = DrawingPromptGenerator.update_table_with_prompts(
                self.selected_node, all_prompts
            )
            
            # 显示成功信息
            self.output_text.setHtml(f"""
                <div style='color: #00ff88; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>✅ 提示词生成完成</p>
                    <p style='font-size: 12px; color: #888; margin-top: 10px;'>
                        已为 {success_count} 个镜头生成中英文绘图提示词<br/>
                        表格已更新，新增"绘画提示词（CN）"和"绘画提示词（EN）"两列
                    </p>
                </div>
            """)
            
            # 重新启用按钮
            self.toolbox_btn.setEnabled(True)
        
        except Exception as e:
            error_msg = f"更新表格失败: {str(e)}"
            print(f"[生成提示词] {error_msg}")
            self.output_text.setHtml(f"""
                <div style='color: #ff4444; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>❌ 错误</p>
                    <p style='font-size: 12px; margin-top: 10px;'>{error_msg}</p>
                </div>
            """)
            self.toolbox_btn.setEnabled(True)
    
    def on_prompts_error(self, error_msg):
        """提示词生成错误"""
        print(f"[生成提示词] 错误: {error_msg}")
        self.output_text.setHtml(f"""
            <div style='color: #ff4444; padding: 15px; text-align: center;'>
                <p style='font-size: 14px; font-weight: bold;'>❌ 生成失败</p>
                <p style='font-size: 12px; margin-top: 10px;'>{error_msg}</p>
            </div>
        """)
        self.toolbox_btn.setEnabled(True)
    
    def on_generate_draft_clicked(self):
        """生成草稿按钮点击 - 调用图片API生成图片"""
        # 获取用户选择的图片API
        from PySide6.QtCore import QSettings
        settings = QSettings('GhostOS', 'App')
        image_api = settings.value("api/image_provider", "BANANA")
        
        print(f"[生成草稿] 点击生成草稿(图片)")
        print(f"[生成草稿] 使用图片API: {image_api}")
        
        # 检查是否有选中的节点
        if not self.selected_node:
            self.output_text.setHtml("""
                <div style='color: #ff4444; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>❌ 错误</p>
                    <p style='font-size: 12px; margin-top: 10px;'>未选中分镜脚本节点或谷歌剧本节点</p>
                </div>
            """)
            return
        
        # 判断节点类型
        is_storyboard = hasattr(self.selected_node, 'table_data') and self.selected_node.table_data
        is_google_script = hasattr(self.selected_node, 'table') and hasattr(self.selected_node.table, 'rowCount')
        
        # 检查节点是否有表格数据
        has_data = False
        row_count = 0
        
        if is_storyboard:
            row_count = len(self.selected_node.table_data)
            has_data = row_count > 0
        elif is_google_script:
            row_count = self.selected_node.table.rowCount()
            has_data = row_count > 0
            
        if not has_data:
            self.output_text.setHtml("""
                <div style='color: #ff9800; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>⚠️ 提示</p>
                    <p style='font-size: 12px; margin-top: 10px;'>表格为空<br/>请先生成或添加内容</p>
                </div>
            """)
            return
        
        # 显示处理中提示
        self.output_text.setHtml(f"""
            <div style='color: #9d5cff; padding: 15px; text-align: center;'>
                <p style='font-size: 14px; font-weight: bold;'>🎨 开始生成图片...</p>
                <p style='font-size: 12px; color: #888; margin-top: 10px;'>
                    使用 {image_api}<br/>
                    共 {row_count} 个镜头，从镜头1开始逐张生成
                </p>
                <p style='font-size: 11px; color: #666; margin-top: 10px;'>
                    💡 每张图片生成后会立即显示在画布上<br/>
                    📊 图片路径将保存到表格的"草稿"列
                </p>
            </div>
        """)
        
        # 禁用菜单按钮
        self.toolbox_btn.setEnabled(False)
        
        # 针对谷歌剧本节点：确保存在"草稿"列，且位于"备注"之后
        if is_google_script:
            try:
                table = self.selected_node.table
                headers = [table.horizontalHeaderItem(c).text() if table.horizontalHeaderItem(c) else "" for c in range(table.columnCount())]
                
                if "草稿" not in headers:
                    # 直接添加到最后一列
                    insert_idx = table.columnCount()
                    
                    table.insertColumn(insert_idx)
                    table.setHorizontalHeaderItem(insert_idx, QTableWidgetItem("草稿"))
                    table.setColumnWidth(insert_idx, 200)
                    
                    # 初始化空单元格
                    for r in range(table.rowCount()):
                        if not table.item(r, insert_idx):
                            table.setItem(r, insert_idx, QTableWidgetItem(""))
                            
                    print(f"[生成草稿] 已在谷歌剧本节点添加'草稿'列，索引: {insert_idx}")
            except Exception as e:
                print(f"[生成草稿] 添加列失败: {e}")
        
        # 调用图片生成
        self.generate_draft_content(image_api)
    
    def generate_draft_content(self, image_api):
        """生成图片 - 使用lingdongDraft模块"""
        
        table_data = []
        headers = []
        
        # 根据节点类型提取数据
        if hasattr(self.selected_node, 'table_data'):
            # 分镜脚本节点
            table_data = self.selected_node.table_data
            headers = self.selected_node.headers if hasattr(self.selected_node, 'headers') else []
        elif hasattr(self.selected_node, 'table'):
            # 谷歌剧本节点
            table = self.selected_node.table
            # 提取表头
            for c in range(table.columnCount()):
                item = table.horizontalHeaderItem(c)
                headers.append(item.text() if item else "")
            
            # 提取数据
            for r in range(table.rowCount()):
                row_data = []
                for c in range(table.columnCount()):
                    item = table.item(r, c)
                    row_data.append(item.text() if item else "")
                table_data.append(row_data)
        
        # 创建图片生成器
        generator = DraftGenerator(self.config_file)
        
        # 定义回调函数
        callbacks = {
            'on_image_completed': self.on_draft_image_completed,
            'on_progress': self.on_draft_progress,
            'on_completed': self.on_draft_completed,
            'on_error': self.on_draft_error
        }
        
        try:
            # 启动生成任务
            self.draft_worker = generator.generate_draft(
                image_api, table_data, headers,
                callbacks=callbacks
            )
        except Exception as e:
            self.output_text.setHtml(f"""
                <div style='color: #ff4444; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>❌ 错误</p>
                    <p style='font-size: 12px; margin-top: 10px;'>{str(e)}</p>
                </div>
            """)
            self.toolbox_btn.setEnabled(True)
    
    def on_draft_image_completed(self, shot_number, image_path, prompt):
        """单张图片生成完成 - 立即回显并更新表格"""
        print(f"[生成草稿] 镜头 {shot_number} 完成: {image_path}")
        
        try:
            # 1. 更新表格数据 - 在"草稿"列中添加图片路径
            row_idx = shot_number - 1  # 行索引从0开始
            
            # 处理分镜脚本节点
            if hasattr(self.selected_node, 'table_data'):
                if hasattr(self.selected_node, 'headers'):
                    # 检查是否已有"草稿"列
                    if "草稿" not in self.selected_node.headers:
                        # 在表头末尾添加"草稿"列
                        self.selected_node.headers.append("草稿")
                        print(f"[生成草稿] 添加新列: 草稿")
                        
                        # 为所有行添加空数据
                        for row in self.selected_node.table_data:
                            row.append("")
                        
                        # 更新列宽配置
                        if hasattr(self.selected_node, 'column_widths'):
                            self.selected_node.column_widths.append(250)  # 图片列宽度250
                    
                    # 找到"草稿"列的索引
                    img_col_idx = self.selected_node.headers.index("草稿") - 1  # 减1因为第一列是镜号
                    
                    # 更新对应行的数据
                    if row_idx < len(self.selected_node.table_data):
                        if img_col_idx < len(self.selected_node.table_data[row_idx]):
                            self.selected_node.table_data[row_idx][img_col_idx] = image_path
                        else:
                            # 扩展行数据
                            while len(self.selected_node.table_data[row_idx]) <= img_col_idx:
                                self.selected_node.table_data[row_idx].append("")
                            self.selected_node.table_data[row_idx][img_col_idx] = image_path
                        
                        print(f"[生成草稿] 已更新表格: 行{shot_number}, 列'草稿'")
                
                # 刷新表格显示
                if hasattr(self.selected_node, 'refresh_table'):
                    self.selected_node.refresh_table()
                    
            # 处理谷歌剧本节点
            elif hasattr(self.selected_node, 'table'):
                table = self.selected_node.table
                
                # 查找或创建"草稿"列
                draft_col_idx = -1
                for c in range(table.columnCount()):
                    item = table.horizontalHeaderItem(c)
                    if item and item.text() == "草稿":
                        draft_col_idx = c
                        break
                
                if draft_col_idx == -1:
                    # 添加新列 (作为兜底，通常在开始时已添加)
                    draft_col_idx = table.columnCount()
                    table.insertColumn(draft_col_idx)
                    table.setHorizontalHeaderItem(draft_col_idx, QTableWidgetItem("草稿"))
                    table.setColumnWidth(draft_col_idx, 200)
                
                # 更新对应单元格
                if row_idx < table.rowCount():
                    item = table.item(row_idx, draft_col_idx)
                    if not item:
                        item = QTableWidgetItem()
                        table.setItem(row_idx, draft_col_idx, item)
                    
                    # 设置路径文本和提示
                    item.setText(image_path)
                    item.setData(Qt.UserRole, image_path)  # 保存路径到UserRole，方便双击打开
                    item.setToolTip(f"提示词: {prompt}\n路径: {image_path}")
                    
                    # 显示图片预览
                    if os.path.exists(image_path):
                        try:
                            pixmap = QPixmap(image_path)
                            if not pixmap.isNull():
                                # 缩放图片以适应单元格
                                scaled_pixmap = pixmap.scaled(180, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                                item.setData(Qt.DecorationRole, scaled_pixmap)
                                
                                # 自动调整行高以显示图片
                                if table.rowHeight(row_idx) < 120:
                                    table.setRowHeight(row_idx, 120)
                        except Exception as img_err:
                            print(f"[生成草稿] 图片加载失败: {img_err}")
                            
                    print(f"[生成草稿] 已更新谷歌剧本: 行{shot_number}, 列'草稿'")

            # 2. 立即创建图片节点显示（逐图回显）
            if self.selected_node:
                base_x = self.selected_node.x() + self.selected_node.rect().width() + 50
                base_y = self.selected_node.y() + (shot_number - 1) * 280
                
                # 创建图片节点
                img_node = ImageNode(base_x, base_y)
                
                # 加载图片
                img_node.load_image(image_path)
                
                # 添加到场景
                if hasattr(self, 'canvas_view') and self.canvas_view:
                    if hasattr(self.canvas_view, 'scene'):
                        # 检查是方法还是属性
                        scene = self.canvas_view.scene() if callable(self.canvas_view.scene) else self.canvas_view.scene
                        if scene:
                            scene.addItem(img_node)
                        else:
                            print(f"[生成草稿] 错误: canvas_view.scene 为空")
                    else:
                        print(f"[生成草稿] 错误: canvas_view 没有 scene 属性")
                else:
                    print(f"[生成草稿] 错误: 找不到 canvas_view")
                
                print(f"[生成草稿] 已创建图片节点: {image_path}")
                
                # 强制更新画布显示
                self.canvas_view.viewport().update()
        
        except Exception as e:
            print(f"[生成草稿] 创建图片节点失败: {e}")
            import traceback
            traceback.print_exc()
    
    def on_draft_progress(self, current, total):
        """更新图片生成进度 - 显示当前正在生成的镜头"""
        from PySide6.QtCore import QSettings
        settings = QSettings('GhostOS', 'GhostOS')
        image_api = settings.value("api/image_provider", "BANANA")
        progress = int((current / total) * 100)
        
        self.output_text.setHtml(f"""
            <div style='color: #9d5cff; padding: 15px; text-align: center;'>
                <p style='font-size: 14px; font-weight: bold;'>🎨 正在生成图片...</p>
                <p style='font-size: 12px; color: #888; margin-top: 10px;'>
                    使用 {image_api}<br/>
                    正在生成第 {current}/{total} 张图片 (镜头 {current})
                </p>
                <div style='width: 80%; height: 8px; background: #2a2a2a; border-radius: 4px; margin: 15px auto;'>
                    <div style='width: {progress}%; height: 100%; background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); border-radius: 4px; transition: width 0.3s;'></div>
                </div>
                <p style='font-size: 11px; color: #666; margin-top: 5px;'>
                    💡 图片将逐张显示在画布右侧
                </p>
            </div>
        """)
    
    def on_draft_completed(self, all_images):
        """图片生成完成"""
        print(f"[生成草稿] 全部完成，成功生成 {len(all_images)} 张图片")
        
        # 显示成功信息
        self.output_text.setHtml(f"""
            <div style='color: #00ff88; padding: 15px; text-align: center;'>
                <p style='font-size: 14px; font-weight: bold;'>✅ 图片生成完成</p>
                <p style='font-size: 12px; color: #888; margin-top: 10px;'>
                    成功生成 {len(all_images)} 张图片<br/>
                    已创建图片节点显示在画布上
                </p>
            </div>
        """)
        
        # 重新启用按钮
        self.toolbox_btn.setEnabled(True)
    
    def on_draft_error(self, error_msg):
        """图片生成错误"""
        print(f"[生成草稿] 错误: {error_msg}")
        self.output_text.setHtml(f"""
            <div style='color: #ff4444; padding: 15px; text-align: center;'>
                <p style='font-size: 14px; font-weight: bold;'>❌ 生成失败</p>
                <p style='font-size: 12px; margin-top: 10px;'>{error_msg}</p>
            </div>
        """)
        self.toolbox_btn.setEnabled(True)
    
    def on_generate_people_clicked(self, style):
        """生成人物按钮点击 - 已移除"""
        self.output_text.setHtml(f"""
            <div style='color: #ff4444; padding: 15px; text-align: center;'>
                <p style='font-size: 14px; font-weight: bold;'>功能已移除</p>
                <p style='font-size: 12px; margin-top: 10px;'>人物角色节点功能已被移除。</p>
            </div>
        """)
    
    def on_generate_all_people(self, style):
        """生成所有人物的提示词 - 已移除"""
        self.output_text.setHtml(f"""
            <div style='color: #ff4444; padding: 15px; text-align: center;'>
                <p style='font-size: 14px; font-weight: bold;'>功能已移除</p>
                <p style='font-size: 12px; margin-top: 10px;'>人物角色节点功能已被移除。</p>
            </div>
        """)

    
    def _extract_content_context(self, node=None):
        """提取节点内容上下文（支持分镜表格和文本文档）"""
        target_node = node if node else self.selected_node
        if not target_node:
            return ""
            
        # 1. 如果是分镜表格节点
        if hasattr(target_node, 'table_data'):
            headers = target_node.headers if hasattr(target_node, 'headers') else []
            table_data = target_node.table_data
            
            # 构建分镜表格的文本描述
            context_parts = []
            context_parts.append("=== 分镜脚本 ===\n")
            
            for row_idx, row in enumerate(table_data):
                shot_info = []
                for col_idx, value in enumerate(row):
                    if col_idx < len(headers):
                        shot_info.append(f"{headers[col_idx]}: {value}")
                    else:
                        shot_info.append(str(value))
                
                context_parts.append(f"镜头 {row_idx + 1}:\n" + "\n".join(shot_info))
                context_parts.append("")  # 空行分隔
            
            return "\n".join(context_parts)
            
        # 2. 如果是文字节点
        content = ""
        if hasattr(target_node, 'full_text'):
            content = target_node.full_text
        elif hasattr(target_node, 'text_edit'):
            content = target_node.text_edit.toPlainText()
        elif hasattr(target_node, 'text_content'):
            content = target_node.text_content
            
        if content:
            return f"=== 文档内容 ===\n\n{content}"
            
        return ""
    
    def generate_people_from_storyboard(self, style, people_names, storyboard_context):
        """根据分镜脚本生成人物设定 - 已移除"""
        self.output_text.setHtml(f"""
            <div style='color: #ff4444; padding: 15px; text-align: center;'>
                <p style='font-size: 14px; font-weight: bold;'>功能已移除</p>
                <p style='font-size: 12px; margin-top: 10px;'>人物角色节点功能已被移除。</p>
            </div>
        """)

    def generate_single_person_prompt(self, style, person_name, context):
        """为单个人物生成提示词
        
        Args:
            style: "真实" 或 "动漫"
            person_name: 人物名称
            context: 上下文内容
        """
        from PySide6.QtCore import QThread, Signal
        import requests
        import os
        import json
        import sys
        
        # 获取当前用户选择的provider和model
        provider = self.provider_combo.currentText()
        model = self.model_combo.currentText()
        
        # 读取对话API配置
        app_root = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(app_root, 'json', 'talk_api_config.json')
        
        api_key = ''
        api_url = ''
        
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    api_config = json.load(f)
                
                provider_lower = provider.lower()
                if 'gemini' in provider_lower:
                    provider_key = 'gemini_api_key'
                else:
                    provider_key = f'{provider_lower}_api_key'
                
                api_key = api_config.get(provider_key, '')
                api_url = api_config.get(f'{provider_lower}_api_url', '')
        except Exception as e:
            print(f"[生成人物] 读取配置失败: {e}")
            self._on_people_error(f"读取API配置失败: {str(e)}")
            return
        
        if not api_key:
            self._on_people_error(f"{provider} 的API Key未配置<br/>请在设置中配置对话API密钥")
            return
        
        # 创建生成线程
        class SinglePersonWorker(QThread):
            finished = Signal(dict)  # 返回单个人物数据
            error = Signal(str)
            
            def __init__(self, provider, model, api_key, base_url, style, person_name, context):
                super().__init__()
                self.provider = provider
                self.model = model
                self.api_key = api_key
                self.base_url = base_url
                self.style = style
                self.person_name = person_name
                self.context = context

                # Register to global registry
                from PySide6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    if not hasattr(app, '_active_single_person_workers'):
                        app._active_single_person_workers = []
                    app._active_single_person_workers.append(self)
                self.finished.connect(self._cleanup_worker)

            def _cleanup_worker(self):
                from PySide6.QtWidgets import QApplication
                app = QApplication.instance()
                if app and hasattr(app, '_active_single_person_workers'):
                    if self in app._active_single_person_workers:
                        app._active_single_person_workers.remove(self)
                self.deleteLater()
            def run(self):
                try:
                    # 构建系统提示词 - 强调基于完整分镜脚本生成
                    system_prompt = f"""你是专业的角色设计师。我会提供完整的分镜脚本，请根据脚本中的所有信息为指定人物生成AI绘画提示词。

风格：{self.style}
目标人物：{self.person_name}

任务：
1. 仔细阅读提供的完整分镜脚本内容
2. 分析脚本中关于「{self.person_name}」的所有描述信息（外貌、性格、服装、场景等）
3. 综合所有镜头中的信息，生成一个统一的、详细的AI绘画提示词（英文）
4. 提示词要适合{"真实摄影风格" if self.style == "真实" else "动漫插画风格"}

必须严格按照以下JSON格式输出：
```json
{{
  "人物名称": "{self.person_name}",
  "人物提示词": "{"英文摄影风格提示词，如：photorealistic portrait of a young woman in her 20s, long black hair, professional business suit, confident expression, detailed facial features, studio lighting, 8K, high quality" if self.style == "真实" else "英文动漫风格提示词，如：anime character design, young girl with long black hair, vibrant blue eyes, school uniform, cheerful expression, detailed illustration, full body, clean line art"}"
}}
```

提示词要求：
{"- 真实风格：包含 photorealistic portrait, detailed facial features, studio lighting, professional photography, 8K 等关键词" if self.style == "真实" else "- 动漫风格：包含 anime character design, detailed illustration, vibrant colors, clean line art 等关键词"}
- 基于分镜脚本中的所有相关描述
- 必须包含外貌、服装、姿态、表情等完整描述
- 长度80-150词
- 必须是英文
- 如果脚本中信息不足，基于剧情背景合理推测"""
                    
                    # 构建用户消息 - 包含完整分镜脚本
                    user_message = f"""以下是完整的分镜脚本内容：

{self.context}

========================================

请根据以上分镜脚本的所有内容，为人物「{self.person_name}」生成AI绘画提示词（{self.style}风格）。

要求：
1. 仔细阅读分镜脚本中所有镜头的内容
2. 提取并整合关于「{self.person_name}」的所有描述信息
3. 生成的提示词要符合脚本设定和剧情背景
4. 如果脚本中关于该人物的描述不够详细，请根据剧情合理推测
5. 只输出JSON格式，不要其他文字"""
                    
                    # 调用API
                    if self.provider.lower() in ['gemini', 'banana', 'banana2']:
                        result = self._call_gemini_api(system_prompt, user_message)
                    else:
                        result = self._call_openai_api(system_prompt, user_message)
                    
                    # 解析结果
                    character = self._parse_result(result)
                    
                    if character:
                        self.finished.emit(character)
                    else:
                        self.error.emit("解析返回结果失败")
                        
                except Exception as e:
                    self.error.emit(str(e))
            
            def _call_openai_api(self, system_prompt, user_message):
                """调用OpenAI兼容API"""
                base = self.base_url.rstrip('/')
                if base.endswith('/v1'):
                    url = f"{base}/chat/completions"
                else:
                    url = f"{base}/v1/chat/completions"
                
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                }
                
                data = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "temperature": 0.7
                }
                
                response = requests.post(url, headers=headers, json=data, timeout=120)
                response.raise_for_status()
                result = response.json()
                return result['choices'][0]['message']['content']
            
            def _call_gemini_api(self, system_prompt, user_message):
                """调用Gemini API"""
                url = f"{self.base_url.rstrip('/')}/v1beta/models/{self.model}:generateContent"
                
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key
                }
                
                data = {
                    "contents": [{
                        "parts": [{
                            "text": f"{system_prompt}\n\n{user_message}"
                        }]
                    }],
                    "generationConfig": {
                        "temperature": 0.7
                    }
                }
                
                response = requests.post(url, headers=headers, json=data, timeout=120)
                response.raise_for_status()
                result = response.json()
                return result['candidates'][0]['content']['parts'][0]['text']
            
            def _parse_result(self, result_text):
                """解析API返回的JSON"""
                import re
                
                # 提取JSON部分
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', result_text, re.DOTALL)
                if not json_match:
                    json_match = re.search(r'\{.*?\}', result_text, re.DOTALL)
                
                if json_match:
                    json_str = json_match.group(1) if '```' in result_text else json_match.group(0)
                    character = json.loads(json_str)
                    
                    # 验证必需字段
                    if "人物名称" in character and "人物提示词" in character:
                        return character
                
                return None
        
        # 创建并启动线程
        self.single_person_worker = SinglePersonWorker(provider, model, api_key, api_url, style, person_name, context)
        self.single_person_worker.finished.connect(lambda char: self._on_single_person_completed(char, person_name))
        self.single_person_worker.error.connect(self._on_people_error)
        self.single_person_worker.start()
    
    def _on_single_person_completed(self, character, person_name):
        """单个人物生成完成"""
        print(f"[生成人物] 成功为 {person_name} 生成提示词")
        
        # 显示成功信息
        self.output_text.setHtml(f"""
            <div style='color: #00ff88; padding: 15px; text-align: center;'>
                <p style='font-size: 14px; font-weight: bold;'>✅ 生成成功</p>
                <p style='font-size: 12px; color: #888; margin-top: 10px;'>
                    已根据分镜脚本为 {person_name} 生成提示词<br/>
                    提示词已添加到人物节点表格
                </p>
            </div>
        """)
        
        # 查找或更新人物节点
        if self.selected_node and hasattr(self.selected_node, 'data_rows'):
            # 查找是否已存在该人物
            found = False
            for i, row in enumerate(self.selected_node.data_rows):
                if len(row) > 1 and row[1] == person_name:
                    # 更新现有行
                    self.selected_node.data_rows[i] = [
                        str(i + 1),
                        character.get("人物名称", person_name),
                        character.get("人物提示词", "")
                    ]
                    found = True
                    break
            
            if not found:
                # 添加新行
                new_index = len(self.selected_node.data_rows) + 1
                self.selected_node.data_rows.append([
                    str(new_index),
                    character.get("人物名称", person_name),
                    character.get("人物提示词", "")
                ])
            
            # 重建表格
            if hasattr(self.selected_node, '_create_table'):
                self.selected_node._create_table()
            
            print(f"[生成人物] 已更新人物节点数据")
        
        # 重新启用按钮
        self.toolbox_btn.setEnabled(True)
    
    def generate_storyboard(self, script_text, custom_headers=None):
        """生成分镜脚本表格 - 支持自定义表头"""
        from PySide6.QtCore import QThread, Signal
        import requests
        
        # 获取当前用户选择的provider和model
        provider = self.provider_combo.currentText()
        model = self.model_combo.currentText()
        
        # 验证模型选择
        if not provider or not model:
            self.output_text.setHtml("""
                <div style='color: #ff4444; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>❌ 错误</p>
                    <p style='font-size: 12px; margin-top: 10px;'>请先选择模型类型和具体模型</p>
                </div>
            """)
            self.storyboard_action.setEnabled(True)
            return
        
        # 检查模型是否可用
        if model.startswith("⚠️"):
            self.output_text.setHtml(f"""
                <div style='color: #ff4444; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>❌ 错误</p>
                    <p style='font-size: 12px; margin-top: 10px;'>当前选择的模型不可用，请重新选择</p>
                </div>
            """)
            self.storyboard_action.setEnabled(True)
            return
        
        # 读取API配置
        if not os.path.exists(self.config_file):
            self.output_text.setHtml("""
                <div style='color: #ff4444; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>❌ 错误</p>
                    <p style='font-size: 12px; margin-top: 10px;'>未找到API配置文件，请先在设置中配置API</p>
                </div>
            """)
            self.storyboard_action.setEnabled(True)
            return
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                api_config = json.load(f)
        except Exception as e:
            self.output_text.setHtml(f"""
                <div style='color: #ff4444; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>❌ 错误</p>
                    <p style='font-size: 12px; margin-top: 10px;'>读取API配置失败: {str(e)}</p>
                </div>
            """)
            self.storyboard_action.setEnabled(True)
            return
        
        # 从扁平化配置中读取API Key
        api_key_name = f'{provider.lower()}_api_key'
        api_key = api_config.get(api_key_name, '')
        
        if not api_key:
            self.output_text.setHtml(f"""
                <div style='color: #ff4444; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>❌ 错误</p>
                    <p style='font-size: 12px; margin-top: 10px;'>{provider} 的API Key未配置<br/>请在设置中配置对话API密钥</p>
                </div>
            """)
            self.storyboard_action.setEnabled(True)
            return
        
        # 获取API URL（处理末尾斜杠，避免重复路径）
        if provider == "Hunyuan":
            base_url = api_config.get('hunyuan_api_url', 'https://api.vectorengine.ai')
            api_url = f"{base_url.rstrip('/')}/v1/chat/completions"
        else:
            base_url = api_config.get('api_url', 'https://api.vectorengine.ai/v1')
            # 如果base_url已包含/v1，则只添加/chat/completions
            if base_url.rstrip('/').endswith('/v1'):
                api_url = f"{base_url.rstrip('/')}/chat/completions"
            else:
                api_url = f"{base_url.rstrip('/')}/v1/chat/completions"
        
        print(f"[剧本分镜] 使用模型: {provider} / {model}")
        print(f"[剧本分镜] API URL: {api_url}")
        
        # ---------------------------------------------------------
        # 检查时间码限制配置 (仅针对谷歌剧本节点)
        # ---------------------------------------------------------
        time_constraint = ""
        is_google_node = False
        if hasattr(self, 'target_table_node') and self.target_table_node:
             if hasattr(self.target_table_node, 'node_title') and "谷歌剧本" in self.target_table_node.node_title:
                 is_google_node = True
        
        if is_google_node:
            try:
                from guge_time import TimeCodeConfigWindow
                time_config = TimeCodeConfigWindow.get_config()
                if time_config.get("enabled", False):
                    seconds = time_config.get("seconds", 15)
                    time_constraint = f"严格按照每{seconds}秒一个镜头进行切分（忽略剧情段落，强制按时间分割）。\n"
                    print(f"[剧本分镜] 启用时间码限制: {seconds}秒 (谷歌剧本节点)")
            except ImportError:
                # print("[剧本分镜] 无法加载时间码模块 (guge_time.py)")
                pass
            except Exception as e:
                print(f"[剧本分镜] 读取时间码配置失败: {e}")
        # ---------------------------------------------------------

        # ⭐ 根据自定义表头构建系统提示词
        if custom_headers:
            # 使用连接的表格节点的表头
            headers_str = " | ".join(custom_headers)
            system_prompt = f"""{time_constraint}你是一个专业的影视分镜师。请根据提供的剧本内容，生成详细的分镜脚本表格。

要求：
1. 严格按照以下表格格式输出，使用Markdown表格
2. 表格列必须完全按照此顺序：{headers_str}
3. 不要添加任何多余的说明文字，只输出表格
4. 如果表头包含"镜号"、"镜头号"或"序号"，从1开始递增
5. 如果表头包含"时间码"或"Time Code"，必须是时间段格式：MM:SS-MM:SS（例如：00:00-00:05）。
   - 严禁使用单个时间点！
   - 必须包含开始时间和结束时间，中间用短横线连接。
6. 如果表头包含"景别"，使用：远景、全景、中景、近景、特写等
7. 如果表头包含"运镜"，必须使用完整的镜头描述：
   - 固定镜头（静止不动的镜头）
   - 推移镜头（镜头向前推进靠近主体）
   - 拉远镜头（镜头向后拉远离主体）
   - 摇移镜头（镜头左右或上下摇动）
   - 平移镜头（镜头水平移动跟随或展示场景）
   - 跟随镜头（镜头跟随人物或物体移动）
   - 升降镜头（镜头垂直升降）
   - 环绕镜头（镜头围绕主体旋转）
   - 手持镜头（手持拍摄产生晃动感）
   - 航拍镜头（无人机或高空俯拍）
8. 如果表头包含"备注"，内容要简短精炼（3-5个字），只标注关键信息，如：转场、重点、情绪点等
9. 根据剧本内容合理划分镜头，每个重要动作或对话为一个镜头
10. 填充所有表格列，不要遗漏任何列

请直接输出Markdown表格："""
            print(f"[智能分镜] 使用自定义表头: {headers_str}")
        else:
            # 使用默认表头
            system_prompt = f"""{time_constraint}你是一个专业的影视分镜师。请根据提供的剧本内容，生成详细的分镜脚本表格。

要求：
1. 严格按照以下表格格式输出，使用Markdown表格
2. 表格列：镜号 | 时间码 | 景别 | 画面内容 | 人物 | 人物关系/构图 | 地点/环境 | 运镜 | 音效/台词 | 备注
3. 不要添加任何多余的说明文字，只输出表格
4. 镜号从1开始递增
5. 时间码必须是时间段格式：MM:SS-MM:SS（例如：00:00-00:05）。
   - 严禁使用单个时间点（如 00:00:05）！
   - 必须包含开始时间和结束时间，中间用短横线连接。
   - 根据剧本内容预估每个镜头的时长。
6. 景别使用：远景、全景、中景、近景、特写等
7. 运镜必须使用完整的镜头描述：
   - 固定镜头（静止不动的镜头）
   - 推移镜头（镜头向前推进靠近主体）
   - 拉远镜头（镜头向后拉远离主体）
   - 摇移镜头（镜头左右或上下摇动）
   - 平移镜头（镜头水平移动跟随或展示场景）
   - 跟随镜头（镜头跟随人物或物体移动）
   - 升降镜头（镜头垂直升降）
   - 环绕镜头（镜头围绕主体旋转）
   - 手持镜头（手持拍摄产生晃动感）
   - 航拍镜头（无人机或高空俯拍）
8. 备注列内容要简短精炼（3-5个字），只标注关键信息，如：转场、重点、情绪点、高潮等
9. 根据剧本内容合理划分镜头，每个重要动作或对话为一个镜头

请直接输出Markdown表格："""
        
        # 检查额外参数设置 (简化地点 / 强制角色检测)
        extra_prompt_prefix = ""
        try:
            from gugejuben_map_setting import MapSettingDialog
            
            # 强制角色检测 (在最前面加入)
            if hasattr(MapSettingDialog, 'is_force_char_detection_enabled') and MapSettingDialog.is_force_char_detection_enabled():
                 extra_prompt_prefix += "请提供完整的人物角色名称，不要遗漏角色人物\n"
                 print("[剧本分镜] 启用强制角色检测")

            # 简化地点模式
            if MapSettingDialog.is_simplified_mode_enabled():
                extra_prompt_prefix += "请简化地点，尽量不要产生王座，王座前，同一场景请不要使用多个地点名字。\n"
                print("[剧本分镜] 启用简化地点模式")
        except ImportError:
            pass

        # 构建用户消息
        user_message = f"{extra_prompt_prefix}以下是剧本内容：\n\n{script_text}\n\n请生成分镜脚本表格。"
        
        # 保存自定义表头供后续使用
        self.current_custom_headers = custom_headers
        
        # 创建StoryboardWorker线程
        class StoryboardWorker(QThread):
            """分镜生成工作线程"""
            response_received = Signal(str)
            error_occurred = Signal(str)
            finished = Signal()
            
            def __init__(self, provider, api_url, api_key, model, system_prompt, user_message):
                super().__init__()
                self.provider = provider
                self.api_url = api_url
                self.api_key = api_key
                self.model = model
                self.system_prompt = system_prompt
                self.user_message = user_message

                # 注册到全局引用列表，防止被垃圾回收
                from PySide6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    if not hasattr(app, '_active_storyboard_workers_ld'):
                        app._active_storyboard_workers_ld = []
                    app._active_storyboard_workers_ld.append(self)
                self.finished.connect(self._cleanup_worker)

            def _cleanup_worker(self):
                """清理 worker 引用"""
                from PySide6.QtWidgets import QApplication
                app = QApplication.instance()
                if app and hasattr(app, '_active_storyboard_workers_ld'):
                    if self in app._active_storyboard_workers_ld:
                        app._active_storyboard_workers_ld.remove(self)
                self.deleteLater()
            
            def run(self):
                try:
                    headers = {
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {self.api_key}'
                    }
                    
                    payload = {
                        'model': self.model,
                        'messages': [
                            {'role': 'system', 'content': self.system_prompt},
                            {'role': 'user', 'content': self.user_message}
                        ],
                        'stream': False
                    }
                    
                    response = requests.post(
                        self.api_url,
                        headers=headers,
                        json=payload,
                        timeout=120
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        content = result['choices'][0]['message']['content']
                        self.response_received.emit(content)
                    else:
                        self.error_occurred.emit(f"API请求失败: {response.status_code} - {response.text}")
                
                except Exception as e:
                    self.error_occurred.emit(f"请求异常: {str(e)}")
                
                finally:
                    self.finished.emit()
        
        # 创建并启动线程
        self.storyboard_worker = StoryboardWorker(
            provider, api_url, api_key, model,
            system_prompt, user_message
        )
        self.storyboard_worker.response_received.connect(self.on_storyboard_received)
        self.storyboard_worker.error_occurred.connect(self.on_storyboard_error)
        self.storyboard_worker.finished.connect(self.on_storyboard_finished)
        self.storyboard_worker.start()
        
        print(f"[剧本分镜] 开始生成，使用模型: {provider}/{model}")
    
    def on_storyboard_received(self, content):
        """分镜生成成功 - 解析表格并输出到连接的节点或创建新节点"""
        print(f"[剧本分镜] 生成成功，长度: {len(content)}")
        
        # 智能判断是否需要保留第一列（镜号列）
        # 对于谷歌剧本节点，我们需要保留AI生成的镜号列，因为它不支持自动生成镜号
        keep_first_col = False
        if hasattr(self, 'target_table_node') and self.target_table_node:
             # 检查是否是谷歌剧本节点
             # 1. 优先检查节点标题
             if hasattr(self.target_table_node, 'node_title') and self.target_table_node.node_title == "谷歌剧本":
                 keep_first_col = True
                 print("[智能分镜] 检测到谷歌剧本节点（通过标题），将保留AI生成的镜号列")
             # 2. 备选：通过表头特征判断
             elif hasattr(self.target_table_node, 'headers') and len(self.target_table_node.headers) >= 8:
                 h = self.target_table_node.headers
                 # 谷歌节点特征：第1列是镜号
                 if h[0] == "镜号":
                     # 旧版特征：第7列是开始帧
                     if len(h) >= 7 and (h[6] == "开始帧" or "Start Frame" in h[6]):
                          keep_first_col = True
                          print("[智能分镜] 检测到谷歌节点（旧版表头），将保留AI生成的镜号列")
                     # 新版10列特征：包含"地点/环境"等
                     elif len(h) == 10 and h[9] == "备注":
                          keep_first_col = True
                          print("[智能分镜] 检测到谷歌节点（新版表头），将保留AI生成的镜号列")

        # 解析Markdown表格
        table_data = self.parse_markdown_table(content, self.current_custom_headers, keep_first_col=keep_first_col)
        
        if not table_data:
            self.output_text.setHtml("""
                <div style='color: #ff4444; padding: 15px; text-align: center;'>
                    <p style='font-size: 14px; font-weight: bold;'>❌ 解析失败</p>
                    <p style='font-size: 12px; margin-top: 10px;'>无法解析生成的表格数据</p>
                </div>
            """)
            return
        
        # ⭐ 如果连接到表格节点，直接更新该节点
        if hasattr(self, 'target_table_node') and self.target_table_node:
            print(f"[智能分镜] 更新连接的表格节点，共 {len(table_data)} 行")
            # 如果有自定义表头，更新节点的表头
            if self.current_custom_headers:
                # 检查是否是谷歌剧本节点的局部更新（原节点8列，生成6列）
                is_google_partial = False
                if hasattr(self.target_table_node, 'headers') and len(self.target_table_node.headers) == 8:
                    if len(self.current_custom_headers) == 6:
                        # 检查前6列是否匹配（可选，或者直接信任长度）
                        if "开始帧" in self.target_table_node.headers and "开始帧" not in self.current_custom_headers:
                            is_google_partial = True
                            print("[智能分镜] 检测到谷歌节点局部更新，保留原表头和图片列")
                
                if not is_google_partial:
                    self.target_table_node.headers = self.current_custom_headers
                    # 重新计算列宽
                    num_cols = len(self.current_custom_headers)
                    if num_cols == 2:
                        self.target_table_node.column_widths = [60, 400]
                    elif num_cols == 3:
                        self.target_table_node.column_widths = [60, 300, 300]
                    elif num_cols <= 5:
                        base_width = 150
                        self.target_table_node.column_widths = [60] + [base_width] * (num_cols - 1)
                    else:
                        base_width = 120
                        self.target_table_node.column_widths = [60] + [base_width] * (num_cols - 1)
                    print(f"[智能分镜] 已更新表格表头为: {self.current_custom_headers}")
            
            self.target_table_node.set_table_data(table_data)
            
            # 显示成功提示
            self.output_text.setHtml(f"""
                <div style='padding: 10px;'>
                    <div style='background-color: rgba(0, 255, 136, 0.1); padding: 10px; border-radius: 6px; margin-bottom: 15px;'>
                        <p style='color: #00ff88; font-size: 14px; font-weight: bold; margin: 0;'>✅ 分镜脚本生成成功</p>
                        <p style='color: #888; font-size: 11px; margin-top: 5px;'>已更新连接的表格节点，共 {len(table_data)} 行数据</p>
                    </div>
                </div>
            """)
            
            self._auto_generate_prompts_after_storyboard(self.target_table_node)
        else:
            # 没有连接表格，在画布上创建新表格节点
            table_node = self.create_table_node_on_canvas(table_data, self.current_custom_headers)
            
            # 显示成功提示
            self.output_text.setHtml(f"""
                <div style='padding: 10px;'>
                    <div style='background-color: rgba(0, 255, 136, 0.1); padding: 10px; border-radius: 6px; margin-bottom: 15px;'>
                        <p style='color: #00ff88; font-size: 14px; font-weight: bold; margin: 0;'>✅ 分镜脚本生成成功</p>
                        <p style='color: #888; font-size: 11px; margin-top: 5px;'>已在画布上创建表格节点，共 {len(table_data)} 个镜头</p>
                    </div>
                </div>
            """)
            
            self._auto_generate_prompts_after_storyboard(table_node)
    
    def _auto_generate_prompts_after_storyboard(self, table_node):
        if not table_node:
            return
        self.selected_node = table_node
        self.on_generate_prompt_clicked()
    
    def parse_markdown_table(self, markdown_text, custom_headers=None, keep_first_col=False):
        """解析Markdown表格为二维数组
        
        Args:
            markdown_text: Markdown表格文本
            custom_headers: 自定义表头列表，如果提供则按此解析
            keep_first_col: 是否强制保留第一列（不自动去除镜号列）
        
        Returns:
            list: 二维数组，不包含表头行，是否去除第一列取决于表头是否包含镜号
        """
        lines = markdown_text.strip().split('\n')
        table_data = []
        
        print(f"[解析表格] 开始解析，总行数: {len(lines)}")
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line or not '|' in line:
                continue
            
            # 跳过分隔行（|---|---|）
            if line.replace('|', '').replace('-', '').replace(' ', '').replace(':', '') == '':
                print(f"[解析表格] 第{i+1}行: 跳过分隔行")
                continue
            
            # 解析表格行
            cells = [cell.strip() for cell in line.split('|')[1:-1]]  # 去掉首尾空元素
            
            if not cells:
                print(f"[解析表格] 第{i+1}行: 空行，跳过")
                continue
            
            # 调试：打印每一行的列数和内容
            print(f"[解析表格] 第{i+1}行: {len(cells)}列 - {cells[:3]}...")  # 只打印前3列预览
            
            # 所有行（包括表头）都保存为数据
            table_data.append(cells)
        
        if not table_data or len(table_data) < 2:
            print(f"[解析表格] ❌ 表格数据不足，总行数: {len(table_data)}")
            return []
        
        # 移除表头行（第一行）
        header_row = table_data[0]
        data_rows = table_data[1:]
        
        print(f"[解析表格] ✓ 原始表头: {header_row}")
        print(f"[解析表格] ✓ 数据行数: {len(data_rows)}")
        
        # ⭐ 智能判断是否需要去除第一列（镜号列）
        # 检查第一列是否是镜号相关的列名
        first_col_name = header_row[0].lower() if header_row else ""
        should_remove_first_col = False
        
        if not keep_first_col:
            should_remove_first_col = any(keyword in first_col_name for keyword in 
                                         ['镜号', '序号', '镜头', 'shot', 'no', 'num', '编号'])
        
        if should_remove_first_col:
            print(f"[解析表格] ✓ 检测到镜号列 '{header_row[0]}'，将去除第一列")
        else:
            print(f"[解析表格] ✓ 第一列 '{header_row[0]}' 不是镜号列，保留所有列")
        
        # 处理数据行
        processed_data = []
        for idx, row in enumerate(data_rows):
            if should_remove_first_col:
                # 去除第一列（镜号）
                if len(row) > 1:
                    new_row = row[1:]
                    processed_data.append(new_row)
                    print(f"[解析表格] 数据行{idx+1}: 原始{len(row)}列 → 去除镜号后{len(new_row)}列")
                else:
                    print(f"[解析表格] ⚠️ 数据行{idx+1}: 列数不足，原始{len(row)}列，保留原样")
                    processed_data.append(row)
            else:
                # 保留所有列
                processed_data.append(row)
                print(f"[解析表格] 数据行{idx+1}: 保留所有{len(row)}列")
        
        if custom_headers:
            print(f"[解析表格] 使用自定义表头: {custom_headers}")
            # 验证数据列数是否匹配（自定义表头通常包含镜号列，所以数据应该是表头-1列）
            expected_cols = len(custom_headers) - 1 if should_remove_first_col else len(custom_headers)
            if processed_data and len(processed_data[0]) != expected_cols:
                print(f"[解析表格] ⚠️ 警告：数据列数({len(processed_data[0])}) 与预期({expected_cols})不匹配")
        
        print(f"[解析表格] ✓ 最终处理: {len(processed_data)}行数据")
        if processed_data:
            print(f"[解析表格] ✓ 每行列数: {len(processed_data[0])}列")
        
        return processed_data
    
    def create_table_node_on_canvas(self, table_data, custom_headers=None):
        """在画布上创建表格节点 - 智能命名（分镜脚本、分镜脚本1、分镜脚本2...）
        
        Args:
            table_data: 表格数据
            custom_headers: 自定义表头（可选）
        """
        # 获取选中文字节点的位置，在其右侧创建表格
        if self.selected_node:
            node_pos = self.selected_node.pos()
            # 在文字节点右侧350像素处创建表格
            table_x = node_pos.x() + 350
            table_y = node_pos.y()
        else:
            # 如果没有选中节点，在画布中心创建
            table_x = 0
            table_y = 0
        
        # 智能生成节点名称（检查已存在的名称）
        table_name = self.generate_unique_table_name()
        
        # 创建表格节点，传递自定义表头
        table_node = StoryboardNode(table_x, table_y, table_data, table_name, custom_headers)
        
        # 通过main_page访问画布
        if hasattr(self, 'main_page') and self.main_page and hasattr(self.main_page, 'canvas'):
            self.main_page.canvas.scene.addItem(table_node)
            if custom_headers:
                print(f"[剧本分镜] 已在画布上创建表格节点 '{table_name}'，使用自定义表头: {custom_headers}，位置: ({table_x}, {table_y})")
            else:
                print(f"[剧本分镜] 已在画布上创建表格节点 '{table_name}'，位置: ({table_x}, {table_y})")
        else:
            print("[剧本分镜] 错误：无法访问画布")
        
        self.selected_node = table_node
        return table_node
    
    def generate_unique_table_name(self):
        """生成唯一的表格名称（分镜脚本、分镜脚本1、分镜脚本2...）"""
        if not hasattr(self, 'main_page') or not self.main_page or not hasattr(self.main_page, 'canvas'):
            return "分镜脚本"
        
        canvas = self.main_page.canvas
        existing_names = set()
        
        # 收集画布上所有表格节点的名称
        for item in canvas.scene.items():
            if hasattr(item, 'original_table_name'):
                existing_names.add(item.original_table_name)
        
        # 检查"分镜脚本"是否已存在
        if "分镜脚本" not in existing_names:
            return "分镜脚本"
        
        # 查找最小的可用数字后缀
        counter = 1
        while f"分镜脚本{counter}" in existing_names:
            counter += 1
        
        return f"分镜脚本{counter}"
    
    def on_storyboard_error(self, error_msg):
        """分镜生成失败"""
        print(f"[剧本分镜] 生成失败: {error_msg}")
        self.output_text.setHtml(f"""
            <div style='color: #ff4444; padding: 15px; text-align: center;'>
                <p style='font-size: 14px; font-weight: bold;'>❌ 生成失败</p>
                <p style='font-size: 12px; margin-top: 10px;'>{error_msg}</p>
            </div>
        """)
    
    def on_storyboard_finished(self):
        """分镜生成完成"""
        print("[剧本分镜] 处理完成")
        self.storyboard_action.setEnabled(True)


# ==================== 画布底部工具栏 ====================
class CanvasBottomToolbar(QFrame):
    """画布底部工具栏 - 浮动工具面板"""
    
    node_added = Signal(str)  # 节点添加信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LingdongAgentPage")
        self.collapsed = False
        self._tool_buttons = []
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        # 统一宽度为54px（32px按钮 + 左右各11px边距），确保折叠/展开时按钮位置绝对不动
        self.setFixedWidth(54)
        self.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
                border-radius: 0px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 10, 11, 10)
        layout.setSpacing(8)
        
        # 折叠按钮（位于顶部）
        self.toggle_btn = QPushButton("⟨")
        self.toggle_btn.setToolTip("折叠/展开工具栏")
        self.toggle_btn.setFixedSize(32, 32)  # 匹配折叠后工具栏宽度
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(52,168,83,0.08);
                color: #34A853;
                border: 1px solid rgba(52,168,83,0.3);
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(52,168,83,0.16);
            }
            QPushButton:pressed {
                background-color: rgba(52,168,83,0.24);
            }
        """)
        self.toggle_btn.clicked.connect(self._toggle_collapse)
        layout.addWidget(self.toggle_btn, 0, Qt.AlignHCenter)
        
        # 按钮配置
        buttons = [
            ("文字", "T", "text"),
            ("图片", "🖼", "image"),
            ("视频", "▶", "video"),
            # ("人物", "👤", "people"),
            # ("表格", "⊞", "table"),
            # ("一致性人物", "🔨", "consistent_person"),
            ("剧本人物", "👤", "script_character"),
            ("谷歌剧本", "G", "google_script"),
            ("导演", "🎬", "director"),
            ("地点", "📍", "location"),
            ("清理", "🧹", "cleaning"),
            ("分析", "🤖", "gemini_analyze"),
            # ("视频员工", "📺", "video_boss"),  # 已隐藏
            ("抽卡", "🎰", "gacha"),
        ]
        
        for label, icon, node_type in buttons:
            btn = self.create_tool_button(icon, label)
            btn.clicked.connect(lambda checked, nt=node_type: self.on_add_node(nt))
            layout.addWidget(btn, 0, Qt.AlignHCenter)
            self._tool_buttons.append(btn)
        layout.addStretch(1)
    
    def create_tool_button(self, icon, label):
        """创建工具按钮"""
        btn = QPushButton()
        btn.setFixedSize(32, 32)
        btn.setToolTip(label)
        btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #5f6368;
                border: 1px solid transparent;
                border-radius: 8px;
                font-size: 15px;
            }
            QPushButton:hover {
                background-color: rgba(52, 168, 83, 0.1);
                color: #34A853;
                border: 1px solid rgba(52, 168, 83, 0.3);
            }
            QPushButton:pressed {
                background-color: rgba(52, 168, 83, 0.2);
            }
        """)
        btn.setText(icon)
        return btn
    
    def _toggle_collapse(self):
        """折叠/展开工具栏"""
        self.collapsed = not self.collapsed
        self._apply_collapse_state()
    
    def _apply_collapse_state(self):
        try:
            # 不再改变宽度和边距，确保按钮位置绝对固定
            if self.collapsed:
                self.toggle_btn.setText("⟩")
            else:
                self.toggle_btn.setText("⟨")
            
            for b in self._tool_buttons:
                b.setVisible(not self.collapsed)
            
            # 强制更新几何形状
            self.adjustSize()
            self.update()
        except Exception:
            pass
    
    def on_add_node(self, node_type):
        """添加节点"""
        print(f"[工具栏] 请求添加 {node_type} 节点")
        self.node_added.emit(node_type)


# ==================== 画布右下角缩放控制 ====================
class CanvasZoomControl(QFrame):
    """画布右下角缩放控制"""
    
    zoom_in = Signal()
    zoom_out = Signal()
    zoom_reset = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        # 增加宽度以容纳说明书按钮 + 案例库按钮
        self.setFixedSize(180, 44) 
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 240);
                border: 1px solid rgba(52, 168, 83, 0.15);
                border-radius: 22px;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)
        
        # 案例库占位符 (34x32)
        self.case_placeholder = QWidget()
        self.case_placeholder.setFixedSize(34, 32)
        self.case_placeholder.setStyleSheet("background: transparent;")
        layout.addWidget(self.case_placeholder)

        # 缩放控制按钮（排序：+ - ⟳）
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedSize(34, 32)
        zoom_in_btn.setStyleSheet(self.get_zoom_btn_style())
        zoom_in_btn.clicked.connect(self.zoom_in.emit)
        layout.addWidget(zoom_in_btn)
        
        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setFixedSize(34, 32)
        zoom_out_btn.setStyleSheet(self.get_zoom_btn_style())
        zoom_out_btn.clicked.connect(self.zoom_out.emit)
        layout.addWidget(zoom_out_btn)
        
        zoom_reset_btn = QPushButton("⟳")
        zoom_reset_btn.setFixedSize(34, 32)
        zoom_reset_btn.setStyleSheet(self.get_zoom_btn_style())
        zoom_reset_btn.clicked.connect(self.zoom_reset.emit)
        layout.addWidget(zoom_reset_btn)
    
    def get_zoom_btn_style(self):
        """缩放按钮样式"""
        return """
            QPushButton {
                background-color: #ffffff;
                color: #34A853;
                border: 1px solid rgba(52, 168, 83, 0.3);
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e6f4ea;
                border: 1px solid rgba(52, 168, 83, 0.5);
            }
            QPushButton:pressed {
                background-color: #c8e6c9;
            }
        """


# ==================== 主界面 ====================
class LingdongAgentPage(QWidget):
    """灵动智能体主界面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 主内容区 - 水平分割
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #e0e0e0;
                width: 1px;
            }
        """)
        
        # 左侧：画布容器（用于叠加浮动工具栏）
        self.canvas_container = QWidget()
        self.canvas_container.setStyleSheet("background-color: #ffffff;")
        
        # 为画布容器设置布局
        container_layout = QVBoxLayout(self.canvas_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # 无限画布
        self.canvas = InfiniteCanvasView()
        # 将主界面引用附加到场景对象，以便节点可以访问
        self.canvas.scene.main_page = self
        container_layout.addWidget(self.canvas)
        try:
            self.canvas.load_canvas_state()
        except Exception:
            pass
        
        # 底部工具栏（浮动在画布上方）
        self.bottom_toolbar = CanvasBottomToolbar(self.canvas.viewport())
        self.bottom_toolbar.node_added.connect(self.canvas.add_node)
        self.bottom_toolbar.hide()  # 初始隐藏
        
        # 右下角缩放控制（浮动在画布上方）
        self.zoom_control = CanvasZoomControl(self.canvas.viewport())
        self.zoom_control.zoom_in.connect(self.canvas.zoom_in)
        self.zoom_control.zoom_out.connect(self.canvas.zoom_out)
        self.zoom_control.zoom_reset.connect(self.canvas.clear_canvas)  # ⟳ 按钮清空画布
        self.zoom_control.hide()  # 初始隐藏
        
        # 案例管理挂件（浮动在画布右上角）
        self.case_manager = CaseManagerWidget(self.canvas.viewport(), canvas_view=self.canvas)
        # 连接导演节点请求信号
        self.case_manager.director_node_requested.connect(lambda: self.canvas.add_node("director"))
        self.case_manager.hide() # 初始隐藏
        
        # 工作台显示/隐藏按钮（浮动在画布右上角）
        self.workbench_toggle_btn = WorkbenchToggleButton(self.canvas.viewport())
        self.workbench_toggle_btn.toggled_visibility.connect(self.toggle_workbench)
        self.workbench_toggle_btn.hide() # 初始隐藏

        # 资料库按钮和面板（浮动在画布右上角）
        self.library_panel = LibraryPanel(self.canvas.viewport())
        self.library_panel.hide()
        self.library_toggle_btn = LibraryToggleButton(self.canvas.viewport())
        self.library_toggle_btn.hide()
        self.library_toggle_btn.toggled_visibility.connect(self.toggle_library_panel)
        self.library_panel.visibility_changed.connect(self.library_toggle_btn.sync_from_panel)
        
        # 定位浮动元素
        QTimer.singleShot(100, self.position_floating_elements)
        try:
            self.canvas.viewport().installEventFilter(self)
        except Exception:
            pass
        
        self.main_splitter.addWidget(self.canvas_container)
        
        # 右侧：工作台
        self.workbench = WorkbenchPanel()
        self.main_splitter.addWidget(self.workbench)
        self.workbench.hide() # 默认隐藏工作台
        
        # 将主界面引用传递给工作台，以便访问画布
        self.workbench.main_page = self
        self.workbench.canvas_view = self.canvas
        
        # 连接画布节点选中信号到工作台
        self.canvas.node_selected.connect(self.on_node_selected)
        
        # 连接画布点击信号，用于隐藏模型配置
        self.canvas.canvas_clicked.connect(self.on_canvas_clicked)
        
        # 设置初始分割比例 (画布:工作台 = 8:2)
        self.main_splitter.setStretchFactor(0, 8)
        self.main_splitter.setStretchFactor(1, 2)
        
        layout.addWidget(self.main_splitter)
        
        # print("[灵动智能体] 界面初始化完成")

    def save_canvas_state(self, file_path=None):
        """保存画布状态"""
        if hasattr(self, 'canvas'):
            self.canvas.save_canvas_state(file_path)
    
    def on_node_selected(self, node):
        """节点选中回调"""
        # 保存当前选中的节点
        self.selected_node = node
        
        if node and hasattr(node, 'node_title'):
            # 检查是否是分镜脚本节点（通过标题或table_data属性）
            is_storyboard = (any(keyword in node.node_title for keyword in ["分镜", "Storyboard", "脚本", "表格"]) or 
                           hasattr(node, 'table_data'))
            
            if "文字" in node.node_title or "Text" in node.node_title:
                # 选中文字节点，显示剧本一键分镜按钮
                self.workbench.show_storyboard_button()
                self.workbench.hide_generate_prompt_button()
                # 传递选中的节点到工作台
                self.workbench.set_selected_node(node)
            elif is_storyboard:
                # 选中分镜脚本节点，显示生成内容菜单（包含提示词和草稿）
                self.workbench.hide_storyboard_button()
                self.workbench.show_generate_prompt_button()
                # 先传递选中的节点到工作台（必须在调用更新方法之前）
                self.workbench.set_selected_node(node)
                # 然后更新菜单项可见性（需要依赖selected_node）
                self.workbench._update_people_menu_visibility()
            elif "人物" in node.node_title or node.node_title == "人物角色":
                # 选中人物节点，检查是否有连接的内容节点
                self.workbench.hide_storyboard_button()
                # 检查是否有上游连接（分镜或文档节点）
                if self.workbench._find_upstream_content_node(node):
                    # 有连接，显示生成内容菜单（包含人物生成选项）
                    self.workbench.show_generate_prompt_button()
                    # 更新人物生成菜单项的可见性
                    self.workbench._update_people_menu_visibility()
                else:
                    # 无连接，隐藏菜单
                    self.workbench.hide_generate_prompt_button()
                # 传递选中的节点到工作台
                self.workbench.set_selected_node(node)
                self.workbench.hide_generate_image_button()
            elif "视频" in node.node_title:
                self.workbench.hide_storyboard_button()
                self.workbench.hide_generate_prompt_button()
                self.workbench.hide_generate_image_button()
                self.workbench.set_selected_node(node)
                self.workbench._update_google_split_btn_visibility(node)
            elif "谷歌剧本" in node.node_title:
                self.workbench.hide_storyboard_button()
                self.workbench.hide_generate_prompt_button()
                self.workbench.hide_generate_image_button()
                self.workbench.set_selected_node(node)
                self.workbench._update_google_split_btn_visibility(node)
            else:
                # 选中其他节点，隐藏所有按钮
                self.workbench.hide_storyboard_button()
                self.workbench.hide_generate_prompt_button()
                self.workbench.set_selected_node(None)
                self.workbench.hide_generate_image_button()
                if hasattr(self.workbench, 'google_split_action'):
                    self.workbench.google_split_action.setVisible(False)
        else:
            # 没有选中节点，隐藏所有按钮
            self.workbench.hide_storyboard_button()
            self.workbench.hide_generate_prompt_button()
            self.workbench.set_selected_node(None)
            self.workbench.hide_generate_image_button()
            if hasattr(self.workbench, 'google_split_action'):
                self.workbench.google_split_action.setVisible(False)
    
    
    def on_canvas_clicked(self):
        """画布点击回调 - 隐藏模型配置区域"""
        self.workbench.hide_config_frame()

    def toggle_workbench(self, visible):
        """切换工作台显示/隐藏"""
        self.workbench.setVisible(visible)
        # 重新定位浮动元素，因为canvas viewport大小变了
        QTimer.singleShot(10, self.position_floating_elements)

    def toggle_library_panel(self, visible):
        if hasattr(self, 'library_panel'):
            if visible:
                self.library_panel.show_panel()
            else:
                self.library_panel.hide_panel()

    def showEvent(self, event):
        """界面显示时，显示浮动元素"""
        super().showEvent(event)
        if hasattr(self, 'bottom_toolbar'):
            QTimer.singleShot(50, self._show_floating_elements)
    
    def hideEvent(self, event):
        """界面隐藏时，隐藏浮动元素"""
        super().hideEvent(event)
        if hasattr(self, 'bottom_toolbar'):
            self.bottom_toolbar.hide()
        if hasattr(self, 'zoom_control'):
            self.zoom_control.hide()
        if hasattr(self, 'case_manager'):
            self.case_manager.hide()
        if hasattr(self, 'workbench_toggle_btn'):
            self.workbench_toggle_btn.hide()
        if hasattr(self, 'library_panel'):
            self.library_panel.hide()
        if hasattr(self, 'library_toggle_btn'):
            self.library_toggle_btn.hide()
    
    def _show_floating_elements(self):
        """显示浮动元素"""
        if hasattr(self, 'bottom_toolbar'):
            self.position_floating_elements()
            try:
                self.bottom_toolbar.raise_()
                self.zoom_control.raise_()
                if hasattr(self, 'case_manager'):
                    self.case_manager.raise_()
                if hasattr(self, 'workbench_toggle_btn'):
                    self.workbench_toggle_btn.raise_()
                if hasattr(self, 'library_panel'):
                    self.library_panel.raise_()
                if hasattr(self, 'library_toggle_btn'):
                    self.library_toggle_btn.raise_()
            except Exception:
                pass
            self.bottom_toolbar.show()
            self.zoom_control.show()
            if hasattr(self, 'case_manager'):
                self.case_manager.show()
            if hasattr(self, 'workbench_toggle_btn'):
                self.workbench_toggle_btn.show()
            if hasattr(self, 'library_toggle_btn'):
                self.library_toggle_btn.show()
    
    def position_floating_elements(self):
        """定位浮动元素：底部工具栏和缩放控制"""
        if not hasattr(self, 'canvas') or not hasattr(self, 'canvas_container'):
            return
        
        canvas_rect = self.canvas.viewport().rect()
        cw = max(0, canvas_rect.width())
        ch = max(0, canvas_rect.height())
        
        # 定位工具栏到左侧红色区域：紧靠左上角顶端
        toolbar_x = 0
        toolbar_y = 0
        # 边界收敛，避免超出容器导致显示不全（主要是防止画布极小时的异常）
        if cw > self.bottom_toolbar.width() + 40:
             toolbar_x = 0
        if ch > self.bottom_toolbar.height() + 40:
             toolbar_y = 0
        
        try:
            self.bottom_toolbar.move(toolbar_x, toolbar_y)
            self.bottom_toolbar.raise_()
            self.bottom_toolbar.show()  # 确保工具栏显示
        except Exception:
            pass
        
        # 定位缩放控制：右下角，距右边20像素，距底部20像素
        zoom_x = cw - self.zoom_control.width() - 20
        zoom_y = ch - self.zoom_control.height() - 20
        zoom_x = max(10, min(zoom_x, cw - self.zoom_control.width() - 10))
        zoom_y = max(10, min(zoom_y, ch - self.zoom_control.height() - 10))
        try:
            self.zoom_control.move(zoom_x, zoom_y)
            self.zoom_control.raise_()
            self.zoom_control.show()  # 确保缩放控制显示
        except Exception:
            pass

        # 定位案例管理：位于缩放控制内部占位符位置
        if hasattr(self, 'case_manager'):
            # 占位符在 CanvasZoomControl 内部的位置: x=10, y=6
            # 绝对位置:
            target_x = zoom_x + 10
            target_y = zoom_y + 6
            target_h = 32 # 占位符高度
            
            # 对齐逻辑：保持左下角一致 (因为图标在底部左侧)
            # case_x = target_x
            # case_y + case_h = target_y + target_h  =>  case_y = target_y + target_h - case_h
            
            case_x = target_x
            case_y = target_y + target_h - self.case_manager.height()
            
            try:
                self.case_manager.move(case_x, case_y)
                self.case_manager.raise_()
                self.case_manager.show()
            except Exception:
                pass

        # 定位工作台切换按钮：右上角
        if hasattr(self, 'workbench_toggle_btn'):
            btn_y = 10
            btn_spacing = 8
            btn_x = cw - self.workbench_toggle_btn.width() - 10
            if hasattr(self, 'library_toggle_btn'):
                btn_x = cw - self.workbench_toggle_btn.width() - self.library_toggle_btn.width() - 10 - btn_spacing
            try:
                self.workbench_toggle_btn.move(btn_x, btn_y)
                self.workbench_toggle_btn.raise_()
                self.workbench_toggle_btn.show()
            except Exception:
                pass

        if hasattr(self, 'library_toggle_btn'):
            btn_y = 10
            btn_x = cw - self.library_toggle_btn.width() - 10
            try:
                self.library_toggle_btn.move(btn_x, btn_y)
                self.library_toggle_btn.raise_()
                self.library_toggle_btn.show()
            except Exception:
                pass

        if hasattr(self, 'library_panel'):
            panel_w = self.library_panel.width()
            panel_h = self.library_panel.height()
            panel_x = cw - panel_w - 20
            panel_y = 48
            panel_x = max(10, min(panel_x, cw - panel_w - 10))
            panel_y = max(10, min(panel_y, ch - panel_h - 10))
            try:
                self.library_panel.move(panel_x, panel_y)
                if self.library_panel.isVisible():
                    self.library_panel.raise_()
            except Exception:
                pass

    def eventFilter(self, obj, event):
        try:
            if hasattr(self, 'canvas') and obj == self.canvas.viewport():
                if event.type() in (QEvent.Resize, QEvent.Move):
                    self.position_floating_elements()
        except Exception:
            pass
        try:
            return super().eventFilter(obj, event)
        except Exception:
            return False
    
    def resizeEvent(self, event):
        """窗口大小改变时重新定位浮动元素"""
        super().resizeEvent(event)
        if hasattr(self, 'bottom_toolbar') and self.isVisible():
            QTimer.singleShot(10, self.position_floating_elements)


# ==================== 测试代码 ====================
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    
    # 创建主窗口
    window = LingdongAgentPage()
    window.setWindowTitle("灵动智能体 - 无限画布工作空间")
    window.setGeometry(100, 100, 1400, 900)
    window.setStyleSheet("background-color: #ffffff;")
    window.show()
    
    sys.exit(app.exec())
