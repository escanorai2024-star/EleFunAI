
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QLineEdit, QTextEdit, QScrollArea, 
                             QFileDialog, QGraphicsProxyWidget, QFrame, QDialog, QListWidget, QInputDialog, QMessageBox, QMenu, QApplication, QGroupBox, QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView, QGraphicsItem, QGraphicsPixmapItem, QGraphicsDropShadowEffect)
from PySide6.QtCore import Qt, Signal, QSize, QThread, QSettings, QTimer, QRectF, QPointF, QPoint
from PySide6.QtGui import QColor, QBrush, QPixmap, QIcon, QPainter, QAction, QCursor, QPen, QPolygonF
import os
import shutil
import json
import time
import base64
import requests
from chakan import ImageViewerDialog
from didianeditor import LocationEditorDialog, DetailTextEdit
from mapfujiazhi1 import LocationExtraManager
from mapstyle import MapStyleDialog, MapStyleManager
import mapshengcheng
from didian_diejia import OverlayGenerator
from database_save import AssetLibraryStore
import didian_duqu

# 简单的SVG图标 - 地点图标
SVG_LOCATION_ICON = """<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" fill="#5f6368"/></svg>"""
SVG_STYLE_ICON = """<svg xmlns="http://www.w3.org/2000/svg" height="24" viewBox="0 -960 960 960" width="24" fill="white"><path d="M200-120q-33 0-56.5-23.5T120-200v-560q0-33 23.5-56.5T200-840h560q33 0 56.5 23.5T840-760v560q0 33-23.5 56.5T760-120H200Zm0-80h560v-560H200v560Zm40-80h480L570-480 450-320l-90-120-120 160Zm-40 80v-560 560Z"/></svg>"""


def save_location_to_library(name, prompt, image_path):
    try:
        if not image_path or not os.path.exists(image_path):
            return
        store = AssetLibraryStore()
        store.add_scene_record(name or "", prompt or "", image_path)
    except Exception as e:
        print(f"[地点资料库] 保存地点图片失败: {e}")

class LocationNode:
    """地点/环境节点"""
    
    @staticmethod
    def create_node(CanvasNode):
        """动态创建LocationNode类，继承自CanvasNode"""
        
        class HoverLabel(QLabel):
            """支持鼠标悬停预览的Label"""
            hover_entered = Signal(str, QPoint)
            hover_left = Signal()

            def __init__(self, parent=None):
                super().__init__(parent)
                self.image_path = None
                # 开启鼠标追踪
                # self.setMouseTracking(True) 

            def enterEvent(self, event):
                # if self.image_path:
                #     # 使用 QCursor.pos() 获取全局坐标
                #     self.hover_entered.emit(self.image_path, QCursor.pos())
                super().enterEvent(event)

            def leaveEvent(self, event):
                # self.hover_left.emit()
                super().leaveEvent(event)

        class LocationRowWidget(QWidget):
            """单个地点行控件"""
            image_changed = Signal(str)
            gen_image_requested = Signal(object)
            gen_overlay_requested = Signal(object)
            hover_preview_requested = Signal(str, QPoint) # path, global_pos
            
            def __init__(self, parent=None):
                super().__init__(parent)
                self.image_path = None
                self.setup_ui()
                
            def setup_ui(self):
                layout = QHBoxLayout(self)
                layout.setContentsMargins(0, 5, 0, 5)
                layout.setSpacing(10)
                
                # 0. 状态按钮 (⭕)
                self.status_btn = QPushButton()
                self.status_btn.setFixedSize(24, 24)
                self.status_btn.setCheckable(True)
                self.status_btn.setChecked(True) # 默认开启
                self.status_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                self.status_btn.clicked.connect(self.update_status_style)
                self.update_status_style()

                # 1. 地点名称 (左侧)
                self.name_edit = DetailTextEdit()
                self.name_edit.setReadOnly(True)
                self.name_edit.setPlaceholderText("地点名称")
                self.name_edit.setFixedHeight(60)
                self.name_edit.setStyleSheet("""
                    QTextEdit {
                        border: 1px solid #e0e0e0;
                        border-radius: 8px;
                        background-color: #f8f9fa;
                        padding: 8px;
                        font-size: 14px;
                        color: #333;
                    }
                    QTextEdit:focus {
                        border: 2px solid #1a73e8;
                        background-color: #ffffff;
                    }
                """)
                self.name_edit.doubleClicked.connect(self.open_edit_dialog)
                self.name_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                self.name_edit.customContextMenuRequested.connect(lambda pos: self.show_text_menu(self.name_edit, pos))
                
                # 2. 环境描述/提示词 (中间)
                self.prompt_edit = DetailTextEdit()
                self.prompt_edit.setReadOnly(True)
                self.prompt_edit.setPlaceholderText("环境描述/提示词...")
                self.prompt_edit.setFixedHeight(60)
                self.prompt_edit.setStyleSheet("""
                    QTextEdit {
                        border: 1px solid #e0e0e0;
                        border-radius: 8px;
                        background-color: #f8f9fa;
                        padding: 8px;
                        font-size: 13px;
                        color: #555;
                    }
                    QTextEdit:focus {
                        border: 2px solid #1a73e8;
                        background-color: #ffffff;
                    }
                """)
                self.prompt_edit.doubleClicked.connect(self.open_edit_dialog)
                self.prompt_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                self.prompt_edit.customContextMenuRequested.connect(lambda pos: self.show_text_menu(self.prompt_edit, pos))
                
                # 3. 地点参考图 (右侧)
                self.image_label = HoverLabel()
                self.image_label.setFixedSize(80, 60)
                self.image_label.setStyleSheet("""
                    QLabel {
                        border: 2px dashed #cccccc;
                        border-radius: 8px;
                        background-color: #f1f3f4;
                        color: #888888;
                        font-size: 12px;
                    }
                    QLabel:hover {
                        background-color: #e8f0fe;
                        border-color: #1a73e8;
                        color: #1a73e8;
                    }
                """)
                self.image_label.setAlignment(Qt.AlignCenter)
                self.image_label.setText("点击上传\\n地点参考图")
                self.image_label.setCursor(Qt.CursorShape.PointingHandCursor)
                
                # 启用点击事件和右键菜单
                self.image_label.mousePressEvent = self.upload_image
                self.image_label.setAcceptDrops(True)
                self.image_label.dragEnterEvent = self.image_drag_enter
                self.image_label.dropEvent = self.image_drop
                self.image_label.setContextMenuPolicy(Qt.CustomContextMenu)
                self.image_label.customContextMenuRequested.connect(self.show_context_menu)
                
                # 清除按钮 (X)
                self.clear_btn = QPushButton("×", self.image_label)
                self.clear_btn.setFixedSize(16, 16) # 稍微小一点因为图片框比较小 (80x60)
                self.clear_btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(255, 0, 0, 0.7);
                        color: white;
                        border-radius: 8px;
                        font-weight: bold;
                        border: none;
                        padding-bottom: 2px;
                        font-size: 10px;
                    }
                    QPushButton:hover {
                        background-color: rgba(255, 0, 0, 0.9);
                    }
                """)
                # 放在右上角
                self.clear_btn.move(60, 4) # 80 width - 16 btn - 4 margin
                self.clear_btn.hide()
                self.clear_btn.clicked.connect(self.delete_image)

                # 4. 叠加图 (上传)
                self.overlay_label = HoverLabel()
                self.overlay_label.setFixedSize(80, 60)
                self.overlay_label.setStyleSheet(self.image_label.styleSheet())
                self.overlay_label.setAlignment(Qt.AlignCenter)
                self.overlay_label.setText("叠加参考")
                self.overlay_label.setCursor(Qt.CursorShape.PointingHandCursor)
                
                self.overlay_label.mousePressEvent = self.upload_overlay_image
                self.overlay_label.setAcceptDrops(True)
                self.overlay_label.dragEnterEvent = self.overlay_drag_enter
                self.overlay_label.dropEvent = self.overlay_drop
                self.overlay_label.setContextMenuPolicy(Qt.CustomContextMenu)
                self.overlay_label.customContextMenuRequested.connect(self.show_overlay_context_menu)
                self.overlay_path = None
                
                layout.addWidget(self.status_btn, 0)
                layout.addWidget(self.name_edit, 1)
                layout.addWidget(self.prompt_edit, 2)
                layout.addWidget(self.image_label, 0)
                layout.addWidget(self.overlay_label, 0)
                
            
            def show_text_menu(self, editor, pos):
                menu = QMenu(editor)
                act_clear = QAction("清空", editor)
                act_clear.triggered.connect(editor.clear)
                menu.addAction(act_clear)
                menu.exec(editor.mapToGlobal(pos))

            def update_status_style(self):
                is_on = self.status_btn.isChecked()
                # 开启绿色 (#4CAF50), 关闭红色 (#F44336)
                color = "#4CAF50" if is_on else "#F44336"
                self.status_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {color};
                        border: 2px solid {color};
                        border-radius: 12px;
                        color: white;
                        font-weight: bold;
                    }}
                """)

            def open_edit_dialog(self, editor):
                """打开编辑对话框"""
                text = editor.toPlainText()
                # 使用 didianeditor 中的 LocationEditorDialog
                # 传入 None 作为父窗口，避免在 QGraphicsProxyWidget 中出现输入法/焦点问题
                dialog = LocationEditorDialog(text, None)
                dialog.setWindowFlags(Qt.Window) # 强制作为独立窗口
                dialog.setAttribute(Qt.WA_DeleteOnClose)
                
                # 调整标题
                if editor == self.name_edit:
                    dialog.setWindowTitle("📝 编辑地点名称")
                else:
                    dialog.setWindowTitle("📝 编辑环境描述")
                
                # 隐藏字符统计中的行数信息（如果是单行编辑习惯的话），
                # 但 LocationEditorDialog 默认显示 "字符数: X | 行数: Y"
                # 这里我们保持默认即可，因为它是多行文本框

                if dialog.exec():
                    editor.setText(dialog.edited_text)
                
            def upload_image(self, event):
                if event.button() == Qt.LeftButton:
                    if self.image_path and os.path.exists(self.image_path):
                        dialog = ImageViewerDialog(self.image_path, self)
                        dialog.show()
                        self._image_viewer = dialog
                    else:
                        file_path, _ = QFileDialog.getOpenFileName(
                            self, "选择地点参考图", "", "Images (*.png *.jpg *.jpeg *.bmp)"
                        )
                        if file_path:
                            self.set_image(file_path)

            def image_drag_enter(self, event):
                md = event.mimeData()
                if md.hasUrls():
                    event.acceptProposedAction()
                else:
                    event.ignore()

            def image_drop(self, event):
                md = event.mimeData()
                for url in md.urls():
                    path = url.toLocalFile()
                    if path and path.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")):
                        self.set_image(path)
                        event.acceptProposedAction()
                        break

            def delete_image(self):
                self.image_path = None
                self.image_label.image_path = None
                self.image_label.clear()
                self.image_label.setText("点击上传\\n地点参考图")
                self.clear_btn.hide()
                self.image_changed.emit("")

            def send_to_canvas(self):
                if not self.image_path or not os.path.exists(self.image_path):
                    return

                try:
                    # 尝试找到场景
                    scene = None
                    # 方法1: 通过代理部件
                    proxy = self.graphicsProxyWidget()
                    if proxy:
                        scene = proxy.scene()
                    
                    # 方法2: 全局查找
                    if not scene:
                        for w in QApplication.topLevelWidgets():
                            if w.__class__.__name__ == 'LingDong' and hasattr(w, 'scene'):
                                scene = w.scene
                                break
                    
                    if not scene:
                        print("无法找到场景")
                        return

                    # 获取 CanvasNode 类
                    CanvasNodeClass = None
                    for item in scene.items():
                         if hasattr(item, 'node_title') and hasattr(item, 'icon_svg'):
                             for base in item.__class__.__bases__:
                                 if base.__name__ == 'CanvasNode':
                                     CanvasNodeClass = base
                                     break
                             if CanvasNodeClass: break
                    
                    # 如果找不到，尝试从 lingdong 模块获取
                    if not CanvasNodeClass:
                         import sys
                         if 'lingdong' in sys.modules:
                             CanvasNodeClass = sys.modules['lingdong'].CanvasNode

                    if CanvasNodeClass:
                        from lingdongpng import ImageNode as ImageNodeFactory
                        ImageNodeClass = ImageNodeFactory.create_image_node(CanvasNodeClass)
                        
                        # 放在当前视图中心
                        view = scene.views()[0]
                        center = view.mapToScene(view.viewport().rect().center())
                        
                        node = ImageNodeClass(center.x(), center.y())
                        node.load_image(self.image_path)
                        scene.addItem(node)
                        node.setSelected(True)
                        print(f"已发送图片到画板: {self.image_path}")
                except Exception as e:
                    print(f"发送到画板失败: {e}")

            def show_context_menu(self, pos):
                menu = QMenu(self)

                # 读取资料库
                action_read_lib = QAction("📂 读取资料库", self)
                action_read_lib.triggered.connect(lambda: didian_duqu.read_from_library(self))
                menu.addAction(action_read_lib)
                menu.addSeparator()

                if self.image_path:
                    delete_action = QAction("🗑️ 删除图片", self)
                    delete_action.triggered.connect(self.delete_image)
                    menu.addAction(delete_action)

                    send_to_canvas_action = QAction("🎨 发送到画板", self)
                    send_to_canvas_action.triggered.connect(self.send_to_canvas)
                    menu.addAction(send_to_canvas_action)

                    menu.addSeparator()
                generate_overlay_action = QAction("🖼️ 产生叠加图", self)
                generate_overlay_action.triggered.connect(self.request_overlay_generation)
                menu.addAction(generate_overlay_action)
                generate_image_action = QAction("🎨 产生图片", self)
                generate_image_action.triggered.connect(self.request_image_generation)
                menu.addAction(generate_image_action)
                save_action = QAction("💾 保存图片", self)
                save_action.triggered.connect(self.save_image)
                menu.addAction(save_action)
                menu.exec(self.image_label.mapToGlobal(pos))

            def request_image_generation(self):
                self.gen_image_requested.emit(self)

            def request_overlay_generation(self):
                self.gen_overlay_requested.emit(self)

            def set_image(self, path):
                if path and os.path.exists(path):
                    self.image_path = path
                    self.image_label.image_path = path
                    pixmap = QPixmap(path)
                    scaled_pixmap = pixmap.scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.image_label.clear()
                    self.image_label.setPixmap(scaled_pixmap)
                    self.clear_btn.show()
                    self.image_changed.emit(path)
                    name = self.name_edit.toPlainText().strip()
                    prompt = self.prompt_edit.toPlainText().strip()
                    save_location_to_library(name, prompt, path)
                else:
                    self.image_label.setText("加载失败")
                    self.image_label.image_path = None

            def save_image(self):
                if self.image_path and os.path.exists(self.image_path):
                    default_name = os.path.basename(self.image_path)
                    dest, _ = QFileDialog.getSaveFileName(self, "保存图片", default_name, "Images (*.png *.jpg *.jpeg *.bmp)")
                    if dest:
                        try:
                            shutil.copyfile(self.image_path, dest)
                        except Exception:
                            pass
                else:
                    dest, _ = QFileDialog.getSaveFileName(self, "保存图片", "", "Images (*.png *.jpg *.jpeg *.bmp)")
                    if dest:
                        pixmap = self.image_label.pixmap()
                        if pixmap:
                            pixmap.save(dest)

            def upload_overlay_image(self, event):
                if event.button() == Qt.LeftButton:
                    if self.overlay_path and os.path.exists(self.overlay_path):
                        dialog = ImageViewerDialog(self.overlay_path, self)
                        dialog.show()
                        self._overlay_viewer = dialog
                    else:
                        file_path, _ = QFileDialog.getOpenFileName(
                            self, "选择叠加参考图", "", "Images (*.png *.jpg *.jpeg *.bmp)"
                        )
                        if file_path:
                            self.set_overlay_image(file_path)

            def overlay_drag_enter(self, event):
                md = event.mimeData()
                if md.hasUrls():
                    event.acceptProposedAction()
                else:
                    event.ignore()

            def overlay_drop(self, event):
                md = event.mimeData()
                for url in md.urls():
                    path = url.toLocalFile()
                    if path and path.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")):
                        self.set_overlay_image(path)
                        event.acceptProposedAction()
                        break

            def delete_overlay_image(self):
                self.overlay_path = None
                self.overlay_label.image_path = None
                self.overlay_label.clear()
                self.overlay_label.setText("叠加参考")
                # self.image_changed.emit("") # 不需要触发主图变化信号

            def show_overlay_context_menu(self, pos):
                menu = QMenu(self)
                if self.overlay_path:
                    delete_action = QAction("🗑️ 删除叠加图", self)
                    delete_action.triggered.connect(self.delete_overlay_image)
                    menu.addAction(delete_action)
                save_action = QAction("💾 保存图片", self)
                save_action.triggered.connect(self.save_overlay_image)
                menu.addAction(save_action)
                menu.exec(self.overlay_label.mapToGlobal(pos))

            def set_overlay_image(self, path):
                if path and os.path.exists(path):
                    self.overlay_path = path
                    self.overlay_label.image_path = path
                    pixmap = QPixmap(path)
                    scaled_pixmap = pixmap.scaled(self.overlay_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.overlay_label.setPixmap(scaled_pixmap)
                else:
                    self.overlay_label.image_path = None
            
            def save_overlay_image(self):
                if self.overlay_path and os.path.exists(self.overlay_path):
                    default_name = os.path.basename(self.overlay_path)
                    dest, _ = QFileDialog.getSaveFileName(self, "保存图片", default_name, "Images (*.png *.jpg *.jpeg *.bmp)")
                    if dest:
                        try:
                            shutil.copyfile(self.overlay_path, dest)
                        except Exception:
                            pass
                else:
                    dest, _ = QFileDialog.getSaveFileName(self, "保存图片", "", "Images (*.png *.jpg *.jpeg *.bmp)")
                    if dest:
                        pixmap = self.overlay_label.pixmap()
                        if pixmap:
                            pixmap.save(dest)

            def get_data(self):
                return {
                    "name": self.name_edit.toPlainText().strip(),
                    "prompt": self.prompt_edit.toPlainText().strip(),
                    "image": self.image_path,
                    "overlay": self.overlay_path,
                    "is_active": self.status_btn.isChecked()
                }

            def set_data(self, name, prompt, image_path=None, overlay_path=None, is_active=True):
                self.name_edit.setText(name)
                self.prompt_edit.setText(prompt)
                if image_path:
                    self.set_image(image_path)
                if overlay_path:
                    self.set_overlay_image(overlay_path)
                self.status_btn.setChecked(is_active)
                self.update_status_style()
        
        class LocationResizeHandle(QGraphicsItem):
            """自定义地点节点缩放手柄 (蓝色三角形)"""
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
                    
                # 绘制蓝色三角形
                painter.setPen(QPen(QColor("#00bfff"), 2))
                painter.setBrush(QBrush(QColor("#00bfff")))
                
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
                new_width = max(200, self.start_rect.width() + diff.x())
                new_height = max(100, self.start_rect.height() + diff.y())
                
                self.parent_node.setRect(0, 0, new_width, new_height)
                if hasattr(self.parent_node, 'expanded_height'):
                    self.parent_node.expanded_height = new_height
                
                self.update_position()
                
            def update_position(self):
                rect = self.parent_node.rect()
                self.setPos(rect.width() - self.handle_size, rect.height() - self.handle_size)

        # 导入连接系统
        from lingdongconnect import ConnectableNode, DataType, SocketType

        class LocationNode(ConnectableNode, CanvasNode):
            def __init__(self, x, y):
                # 初始化 CanvasNode
                CanvasNode.__init__(self, x, y, 950, 600, "地点/环境节点", SVG_LOCATION_ICON)
                # 初始化 ConnectableNode
                ConnectableNode.__init__(self)
                
                # 替换默认的 ResizeHandle
                if hasattr(self, 'resize_handle'):
                    # 移除旧的 handle
                    if self.resize_handle.scene():
                        self.resize_handle.scene().removeItem(self.resize_handle)
                    self.resize_handle.setParentItem(None)
                
                # 使用自定义的 LocationResizeHandle
                self.resize_handle = LocationResizeHandle(self)
                
                # 添加输入接口 (DataType.TABLE)
                self.add_input_socket(DataType.TABLE, "剧本数据")
                
                self.is_resizing = False
                
                self.setup_ui()
                self.rows = []
                self.worker = None
                self.style_ref_image_path = None

            def update_preview(self, path, global_pos):
                """更新预览图片显示"""
                # 初始化预览项
                if not hasattr(self, 'preview_item'):
                    self.preview_item = QGraphicsPixmapItem()
                    self.preview_item.setZValue(2000) # 确保在最顶层
                    # 添加阴影
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
                # global_pos 是全局坐标
                
                # 1. Global -> Widget (Container)
                widget_pos = self.container.mapFromGlobal(global_pos)
                
                # 2. Widget -> Scene
                scene_pos = self.proxy_widget.mapToScene(QPointF(widget_pos))
                
                # 偏移一点，避免遮挡鼠标
                x = scene_pos.x() + 20
                y = scene_pos.y() + 20
                
                self.preview_item.setPos(x, y)

            def setup_ui(self):
                # 创建主容器
                self.container = QWidget()
                self.container.setAttribute(Qt.WA_TranslucentBackground) # 透明背景，确保标题可见
                self.layout = QVBoxLayout(self.container)
                self.layout.setContentsMargins(15, 50, 15, 15)
                self.layout.setSpacing(10)
                
                # --- 顶部工具栏 (查看地址等) ---
                top_bar_layout = QHBoxLayout()
                top_bar_layout.setContentsMargins(0, 0, 0, 0)
                top_bar_layout.addStretch()
                
                self.view_address_btn = QPushButton("查看")
                self.view_address_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                self.view_address_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #607D8B; 
                        color: white; 
                        border: none; 
                        border-radius: 4px; 
                        padding: 5px 10px; 
                        font-weight: bold;
                        font-family: "Microsoft YaHei";
                    }
                    QPushButton:hover { background-color: #546E7A; }
                """)
                self.view_address_btn.clicked.connect(self.view_all_addresses)
                top_bar_layout.addWidget(self.view_address_btn)
                
                self.extra_manager = LocationExtraManager(self)
                self.fujiazhi_btn = self.extra_manager.setup_ui(self.container)
                top_bar_layout.addWidget(self.fujiazhi_btn)

                self.fast_gen_btn = QPushButton("⚡ 快速生成")
                self.fast_gen_btn.clicked.connect(self.fast_generate)
                self.fast_gen_btn.setStyleSheet("""
                    QPushButton { background-color: #FF9800; color: white; border: none; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
                    QPushButton:hover { background-color: #F57C00; }
                """)
                top_bar_layout.addWidget(self.fast_gen_btn)
                
                
                self.layout.addLayout(top_bar_layout)
                
                # 表头 (对齐下列内容)
                header_widget = QWidget()
                header_layout = QHBoxLayout(header_widget)
                header_layout.setContentsMargins(0, 0, 0, 0)
                header_layout.setSpacing(10)
                
                # 占位符 (对应状态按钮 24px)
                label_status = QLabel("")
                label_status.setFixedSize(24, 24)
                
                label1 = QLabel("地点名称")
                label1.setAlignment(Qt.AlignCenter)
                label1.setStyleSheet("font-weight: bold; color: #555;")
                
                label2 = QLabel("环境描述/提示词")
                label2.setAlignment(Qt.AlignCenter)
                label2.setStyleSheet("font-weight: bold; color: #555;")
                
                label3 = QLabel("地点参考图")
                label3.setAlignment(Qt.AlignCenter)
                label3.setFixedWidth(80)
                label3.setStyleSheet("font-weight: bold; color: #555;")

                label4 = QLabel("叠加图")
                label4.setAlignment(Qt.AlignCenter)
                label4.setFixedWidth(80)
                label4.setStyleSheet("font-weight: bold; color: #555;")

                header_layout.addWidget(label_status, 0)
                header_layout.addWidget(label1, 1)
                header_layout.addWidget(label2, 2)
                header_layout.addWidget(label3, 0)
                header_layout.addWidget(label4, 0)
                
                self.layout.addWidget(header_widget)
                
                # 滚动区域
                self.scroll_area = QScrollArea()
                self.scroll_area.setWidgetResizable(True)
                self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid #ddd; background-color: white; border-radius: 4px; }")
                
                self.scroll_content = QWidget()
                self.scroll_layout = QVBoxLayout(self.scroll_content)
                self.scroll_layout.setSpacing(10)
                self.scroll_layout.addStretch()
                
                self.scroll_area.setWidget(self.scroll_content)
                self.layout.addWidget(self.scroll_area)
                
                # 让滚动区域和内容忽略鼠标按下事件，以便事件传递给 LocationNode (CanvasNode)
                # 这样用户点击列表背景时可以拖动节点，双击时可以触发 LocationNode 的 mouseDoubleClickEvent
                self.scroll_area.viewport().mousePressEvent = lambda e: e.ignore()
                self.scroll_content.mousePressEvent = lambda e: e.ignore()
                
                # 工具栏 (按钮对齐)
                toolbar_layout = QHBoxLayout()
                toolbar_layout.setSpacing(10)
                
                self.refresh_btn = QPushButton("🔄 刷新地点列表")
                self.refresh_btn.clicked.connect(self.refresh_locations)
                self.refresh_btn.setStyleSheet("""
                    QPushButton { background-color: #4CAF50; color: white; border: none; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
                    QPushButton:hover { background-color: #45a049; }
                """)
                
                self.gen_prompt_btn = QPushButton("✨ 生成提示词")
                self.gen_prompt_btn.clicked.connect(self.generate_prompts)
                self.gen_prompt_btn.setStyleSheet("""
                    QPushButton { background-color: #2196F3; color: white; border: none; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
                    QPushButton:hover { background-color: #1976D2; }
                """)
                
                self.gen_image_btn = QPushButton("🖼️ 生成图片")
                self.gen_image_btn.clicked.connect(self.generate_images)
                self.gen_image_btn.setMinimumWidth(80)
                self.gen_image_btn.setStyleSheet("""
                    QPushButton { background-color: #9C27B0; color: white; border: none; border-radius: 4px; padding: 6px 2px; font-weight: bold; }
                    QPushButton:hover { background-color: #7B1FA2; }
                """)

                self.gen_overlay_btn = QPushButton("🎨 生成叠加图")
                self.gen_overlay_btn.clicked.connect(self.start_overlay_generation)
                self.gen_overlay_btn.setMinimumWidth(80)
                self.gen_overlay_btn.setStyleSheet("""
                    QPushButton { background-color: #E91E63; color: white; border: none; border-radius: 4px; padding: 6px 2px; font-weight: bold; }
                    QPushButton:hover { background-color: #C2185B; }
                """)

                toolbar_layout.addWidget(self.refresh_btn, 1)
                toolbar_layout.addWidget(self.gen_prompt_btn, 2)
                toolbar_layout.addWidget(self.gen_image_btn, 1)
                toolbar_layout.addWidget(self.gen_overlay_btn, 1)
                toolbar_layout.addWidget(self.gen_image_btn, 0)
                
                self.layout.addLayout(toolbar_layout)
                
                # 设置代理控件
                self.proxy_widget = QGraphicsProxyWidget(self)
                self.proxy_widget.setWidget(self.container)
                self.proxy_widget.setPos(0, 0)
                self.proxy_widget.resize(950, 600)
                # 初始调整容器尺寸
                self.container.resize(950, 600)
                
                # 确保折叠按钮在最上层
                if hasattr(self, 'toggle_btn'):
                    self.toggle_btn.setZValue(100)



            def setRect(self, *args):
                super().setRect(*args)
                rect = self.rect()
                if hasattr(self, 'proxy_widget'):
                    self.proxy_widget.setGeometry(0, 0, rect.width(), rect.height())
                # 显式调整容器大小以防止错位
                if hasattr(self, 'container'):
                    self.container.resize(int(rect.width()), int(rect.height()))

            def mousePressEvent(self, event):
                print("debug")
                super().mousePressEvent(event)

            def mouseDoubleClickEvent(self, event):
                """双击事件 - 打开编辑对话框"""
                if event.button() == Qt.MouseButton.LeftButton:
                    # 不再在节点空白区域双击时弹出“查看全部地点”编辑窗口
                    # 仅保留单元格的双击编辑，以及通过“查看”按钮打开
                    event.ignore()
                else:
                    super().mouseDoubleClickEvent(event)
            
            def contextMenuEvent(self, event):
                menu = QMenu()
                act_clear = menu.addAction("清空")
                chosen = menu.exec(event.screenPos().toPoint())
                if chosen == act_clear:
                    self.clear_locations()
                    event.accept()

            def view_all_addresses(self):
                """查看/编辑所有地址信息"""
                # 收集当前所有地址信息
                names = []
                # 保持现有顺序
                for row_widget in self.rows:
                    data = row_widget.get_data()
                    if data['name']:
                        names.append(data['name'])
                
                # 使用 didianeditor 中的 LocationEditorDialog
                current_text = "，".join(names)
                # 传入 None 作为父窗口，避免在 QGraphicsProxyWidget 中出现输入法/焦点问题
                dialog = LocationEditorDialog(current_text, None)
                dialog.setWindowFlags(Qt.Window) # 强制作为独立窗口
                dialog.setAttribute(Qt.WA_DeleteOnClose)
                
                if dialog.exec():
                    # 保存更改
                    text = dialog.edited_text.strip()
                    if not text:
                        new_names = []
                    else:
                        # 支持中文逗号和英文逗号
                        text = text.replace("，", ",")
                        new_names = [name.strip() for name in text.split(",") if name.strip()]
                    
                    self.update_location_list(new_names)

            def get_input_data(self):
                """从输入接口获取数据"""
                if not self.input_sockets:
                    return None
                    
                # 获取第一个输入接口的数据
                # 调用父类 ConnectableNode 的方法
                return super().get_input_data(0)
            
            def clear_locations(self):
                while self.scroll_layout.count() > 1:
                    item = self.scroll_layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()
                self.rows = []

            def refresh_locations(self):
                """刷新地点列表"""
                data = self.get_input_data()
                if not data:
                    # self.status_label.setText("未获取到数据，请检查连接...")
                    return
                
                if not isinstance(data, list):
                    # self.status_label.setText("数据格式错误")
                    return
                
                # 查找地点列
                location_keys = ["地点", "环境", "场景", "Location", "Scene", "Environment", "地点/环境"]
                target_key = None
                
                # 检查第一行数据以确定键名
                if len(data) > 0:
                    first_row = data[0]
                    for key in location_keys:
                        if key in first_row:
                            target_key = key
                            break
                    
                    # 如果没找到，尝试按索引猜测（通常是第6或7列）
                    if not target_key:
                        # 假设 GoogleScriptNode 返回的数据包含索引键
                        if 6 in first_row: target_key = 6
                        elif "6" in first_row: target_key = "6"
                
                if not target_key:
                    # self.status_label.setText("未找到'地点/环境'相关列")
                    return
                
                # 提取地点并去重 (保留顺序)
                locations = []
                seen = set()
                for row in data:
                    loc = row.get(target_key, "").strip()
                    if loc and loc not in seen:
                        seen.add(loc)
                        locations.append(loc)
                
                if not locations:
                    # self.status_label.setText("未找到任何地点数据")
                    return
                
                self.update_location_list(locations)
                # self.status_label.setText(f"已加载 {len(locations)} 个地点")

            def update_location_list(self, locations):
                """更新UI列表"""
                # 清除旧数据
                # 注意：我们要保留现有的输入（如果地点名匹配）
                current_data = {}
                for row_widget in self.rows:
                    data = row_widget.get_data()
                    if data["name"]:
                        current_data[data["name"]] = data
                
                # 清空布局
                while self.scroll_layout.count() > 1: # 保留最后的stretch
                    item = self.scroll_layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()
                self.rows = []
                
                # 添加新行
                for loc in locations:
                    row = LocationRowWidget()
                    
                    # 恢复已有数据
                    if loc in current_data:
                        saved = current_data[loc]
                        row.set_data(
                            saved["name"], 
                            saved["prompt"], 
                            saved["image"], 
                            saved.get("overlay", None),
                            saved.get("is_active", True)
                        )
                    else:
                        row.set_data(loc, "", None, None, True)
                    
                    self.scroll_layout.insertWidget(self.scroll_layout.count()-1, row)
                    self.rows.append(row)
                    try:
                        row.gen_image_requested.connect(lambda r=row: self.generate_image_for_row(r))
                        row.gen_overlay_requested.connect(lambda r=row: self.generate_overlay_for_row(r))
                        row.hover_preview_requested.connect(self.update_preview)
                    except Exception:
                        pass

                # 检查并应用已连接的清理节点
                try:
                    # 遍历输入接口（通常只有一个，但支持扩展）
                    if hasattr(self, 'input_sockets'):
                        for socket in self.input_sockets:
                            if hasattr(socket, 'connections'):
                                for connection in socket.connections:
                                    # 找到连接的源节点（清理节点）
                                    if connection.source_socket and connection.source_socket.parent_node:
                                        source_node = connection.source_socket.parent_node
                                        # 如果源节点是清理节点（通过方法签名判断，避免循环引用）
                                        if hasattr(source_node, 'clean_node') and hasattr(source_node, 'cleaning_text'):
                                            source_node.clean_node(self)
                except Exception as e:
                    print(f"[LocationNode] Auto-cleaning failed: {e}")

            # 已移除“完成”列及其右键菜单相关逻辑，单行重新生成功能一并取消

            def fast_generate(self):
                """快速生成：自动使用上次风格生成提示词，完成后自动生成图片"""
                self.generate_prompts(fast_mode=True)

            def generate_prompts(self, fast_mode=False):
                """调用工作台所选模型（对话API），根据剧本信息生成中文场景提示词"""
                print("debug")
                self.gen_prompt_btn.setText("⏳")
                self.gen_prompt_btn.setEnabled(False)
                from PySide6.QtCore import QCoreApplication
                QCoreApplication.processEvents()
                try:
                    style_choice = ""
                    style_text = ""
                    
                    if fast_mode:
                        mgr = MapStyleManager()
                        styles, selected, style_prompts = mgr.load()
                        style_choice = selected
                        style_text = style_prompts.get(selected, "")
                        try:
                            _mgr = MapStyleManager()
                            txt_styles, txt_prompts = _mgr.load_txt()
                            if style_choice in txt_prompts and txt_prompts.get(style_choice, "").strip():
                                style_text = txt_prompts[style_choice]
                        except Exception:
                            pass
                        if not style_text:
                            style_text = "请生成偏向动漫/动画气质、画面夸张、色彩饱和、构图简洁的中文提示词。"
                    else:
                        dlg = MapStyleDialog(self.container)
                        if dlg.exec():
                            style_choice, style_text = dlg.get_style()
                            try:
                                _mgr = MapStyleManager()
                                txt_styles, txt_prompts = _mgr.load_txt()
                                if style_choice in txt_prompts and txt_prompts.get(style_choice, "").strip():
                                    style_text = txt_prompts[style_choice]
                            except Exception:
                                pass
                        else:
                            self.gen_prompt_btn.setText("✨ 生成提示词")
                            self.gen_prompt_btn.setEnabled(True)
                            return
                    # 1) 获取剧本输入数据
                    data = self.get_input_data()
                    if not data or not isinstance(data, list) or len(data) == 0:
                        QMessageBox.warning(None, "提示", "未获取到剧本数据，请先连接剧本节点")
                        return
                    
                    # 2) 提取需要生成的地点列表（无论开启还是关闭，都生成提示词）
                    locations = []
                    for row in self.rows:
                        # 不再检查状态灯是否开启
                        name = row.name_edit.toPlainText().strip()
                        if name:
                            locations.append(name)
                    
                    if not locations:
                        QMessageBox.warning(None, "提示", "列表中没有有效的地点名称")
                        return
                    
                    # 3) 构建“剧本全部内容”上下文（优先字段 + 其余字段）
                    priority_fields = [
                        "镜号","镜头号","Shot No","Shot",
                        "时间码","Timecode","Time",
                        "景别","Shot Size","Size",
                        "画面内容","Content","Description",
                        "人物","Character","Role","Name",
                        "人物关系/构图","人物关系","构图","Relation","Composition",
                        "地点/环境","地点","环境","Location","Environment","Place",
                        "运镜","Camera Movement","Camera",
                        "音效/台词","音效","台词","Sound","Dialogue","Audio",
                        "备注","Remark","Note"
                    ]
                    lines = []
                    for i, row in enumerate(data):
                        processed = {}
                        used = set()
                        for key in priority_fields:
                            if key in row:
                                val = str(row.get(key, "")).strip()
                                if val:
                                    processed[key] = val
                                    used.add(key)
                        for k, v in row.items():
                            if k in used: 
                                continue
                            if str(k).startswith("_"):
                                continue
                            val = str(v).strip()
                            if val:
                                processed[k] = val
                        if processed:
                            line_str = " | ".join([f"{k}: {v}" for k, v in processed.items()])
                            lines.append(f"行{i+1}: {line_str}")
                    script_context = "\n".join(lines)
                    
                    # 4) 读取工作台所选模型与API配置
                    cfg_dir = os.path.join(os.path.dirname(__file__), "json")
                    lingdong_cfg_path = os.path.join(cfg_dir, "lingdong.json")
                    talk_cfg_path = os.path.join(cfg_dir, "talk_api_config.json")
                    
                    provider = None
                    model = None
                    try:
                        if os.path.exists(lingdong_cfg_path):
                            with open(lingdong_cfg_path, "r", encoding="utf-8") as f:
                                ling_cfg = json.load(f)
                                provider = ling_cfg.get("last_provider")
                                model = ling_cfg.get("last_model")
                    except Exception as e:
                        print(f"[LocationNode] 读取 lingdong.json 失败: {e}")
                    
                    if not provider or not model:
                        QMessageBox.warning(None, "提示", "请先在工作台选择模型（提供商与模型）")
                        return
                    
                    try:
                        with open(talk_cfg_path, "r", encoding="utf-8") as f:
                            talk_cfg = json.load(f)
                    except Exception as e:
                        QMessageBox.critical(None, "错误", f"读取对话API配置失败: {e}")
                        return
                    
                    api_key = talk_cfg.get(f"{provider.lower()}_api_key", "")
                    api_url = talk_cfg.get("api_url", "https://manju.chat")
                    hunyuan_api_url = talk_cfg.get("hunyuan_api_url", "https://api.vectorengine.ai")
                    if not api_key:
                        QMessageBox.warning(None, "提示", f"未配置 {provider} 的API Key")
                        return
                    
                    # 5) 构建请求消息（要求返回JSON映射：地点 -> 中文场景提示词）
                    system_prompt = (
                        "你是影视分镜场景提示词生成专家。"
                        "根据提供的剧本内容，为给定的每个地点名称生成中文的场景提示词。"
                        "每条提示词建议包含氛围、光影、镜头语言、关键环境要素，长度不超过80字。"
                        "只输出一个JSON对象，键为地点名称，值为对应的中文提示词，不要包含多余说明。"
                    )
                    _final_style_text = style_text
                    _use_txt = False
                    try:
                        _mgr2 = MapStyleManager()
                        _txt_styles, _txt_prompts = _mgr2.load_txt()
                        if style_choice in _txt_prompts and _txt_prompts.get(style_choice, "").strip():
                            _final_style_text = _txt_prompts[style_choice].strip()
                            _use_txt = True
                    except Exception:
                        _use_txt = False
                    if _use_txt:
                        user_prompt = (
                            f"{_final_style_text}\n\n"
                            f"剧本内容：\n{script_context}\n\n"
                            "请为下列地点逐一生成中文提示词（不超过80字，包含氛围/光影/镜头语言/环境要素）：\n"
                            + "\n".join([f"- {loc}" for loc in locations]) +
                            "\n\n只输出JSON对象。"
                        )
                    else:
                        user_prompt = (
                            f"风格：{style_choice}\n{style_text}\n\n"
                            f"剧本内容：\n{script_context}\n\n"
                            "请为下列地点逐一生成中文提示词（不超过80字，包含氛围/光影/镜头语言/环境要素）：\n"
                            + "\n".join([f"- {loc}" for loc in locations]) +
                            "\n\n只输出JSON对象。"
                        )
                    
                    # 6) 规范化API地址为 /v1/chat/completions
                    base_url = hunyuan_api_url if provider == "Hunyuan" else api_url
                    b = base_url.strip()
                    bl = b.lower()
                    if bl.endswith("/v1"):
                        b = b[: b.rfind("/v1")]
                    while b.endswith("/") or b.endswith(","):
                        b = b[:-1]
                    url = f"{b}/v1/chat/completions"
                    
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    }
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "仅返回JSON对象，不要任何解释或额外文字。"},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": 0.7,
                        "max_tokens": 4096,
                        "stream": False
                    }
                    
                    # Debug: 输出所有发送给API的信息（屏蔽Key）
                    masked_key = (api_key[:4] + "..." + api_key[-4:]) if api_key and len(api_key) > 8 else "****"
                    debug_info = {
                        "provider": provider,
                        "model": model,
                        "url": url,
                        "headers": {"Authorization": f"Bearer {masked_key}", "Content-Type": "application/json", "Accept": "application/json"},
                        "payload": payload,
                        "style_choice": style_choice,
                        "style_text": style_text,
                        "locations": locations
                    }
                    print(f"[LocationNode] Prompt API Debug: {json.dumps(debug_info, ensure_ascii=False)[:4000]}")
                    
                    # 7) 异步调用API，避免卡顿
                    class LocationPromptWorker(QThread):
                        finished = Signal(dict)
                        error = Signal(str)
                        def __init__(self, url, headers, payload):
                            super().__init__()
                            self.url = url
                            self.headers = headers
                            self.payload = payload

                            # 注册到全局引用列表，防止被垃圾回收
                            from PySide6.QtWidgets import QApplication
                            app = QApplication.instance()
                            if app:
                                if not hasattr(app, '_active_location_prompt_workers'):
                                    app._active_location_prompt_workers = []
                                app._active_location_prompt_workers.append(self)
                            self.finished.connect(self._cleanup_worker)

                        def _cleanup_worker(self):
                            """清理 worker 引用"""
                            from PySide6.QtWidgets import QApplication
                            app = QApplication.instance()
                            if app and hasattr(app, '_active_location_prompt_workers'):
                                if self in app._active_location_prompt_workers:
                                    app._active_location_prompt_workers.remove(self)
                            self.deleteLater()
                        def run(self):
                            try:
                                resp = requests.post(self.url, headers=self.headers, json=self.payload, timeout=(20, 120))
                                resp.raise_for_status()
                                data_json = resp.json()
                                content = ""
                                if "choices" in data_json and data_json["choices"]:
                                    content = data_json["choices"][0]["message"].get("content", "") or ""
                                # 清理 Markdown 代码块
                                if "```json" in content:
                                    content = content.split("```json")[1].split("```")[0]
                                elif "```" in content:
                                    content = content.split("```")[1].split("```")[0]
                                content = content.strip().strip('"').strip("'").strip()
                                mapping = {}
                                try:
                                    mapping = json.loads(content)
                                except Exception:
                                    for line in content.splitlines():
                                        if ":" in line:
                                            k, v = line.split(":", 1)
                                            k = k.strip(" -：:").strip()
                                            v = v.strip()
                                            if k and v:
                                                mapping[k] = v
                                self.finished.emit(mapping)
                            except Exception as e:
                                self.error.emit(str(e))
                    
                    # 8) 在线程完成后更新UI
                    def on_finished(mapping):
                        success = False
                        try:
                            if not mapping:
                                QMessageBox.warning(None, "提示", "模型未返回有效的提示词数据")
                                return
                            updated = 0
                            for row in self.rows:
                                # 即使是红色状态，也更新提示词
                                name = row.name_edit.toPlainText().strip()
                                if name and name in mapping:
                                    row.prompt_edit.setText(mapping.get(name, "").strip())
                                    updated += 1
                            if updated == 0:
                                found_keys = ", ".join(list(mapping.keys())[:10])
                                current_locs = [row.name_edit.toPlainText().strip() for row in self.rows]
                                msg = f"没有匹配到任何地点名称的提示词。\n\n当前节点中的地点: {current_locs}\n\nAPI返回的地点键(前10个): {found_keys}\n\n请检查API返回的地点名称是否与节点中的一致。"
                                QMessageBox.warning(None, "提示", msg)
                            
                            success = True
                            try:
                                MapStyleManager().save_result(style_choice, style_text, mapping)
                            except Exception:
                                pass
                        finally:
                            self.gen_prompt_btn.setText("✨ 生成提示词")
                            self.gen_prompt_btn.setEnabled(True)
                            try:
                                self._prompt_worker = None
                            except Exception:
                                pass
                            
                            if fast_mode and success:
                                QTimer.singleShot(500, self.generate_images)
                    
                    def on_error(err):
                        QMessageBox.critical(None, "错误", f"提示词生成失败：{err}")
                        self.gen_prompt_btn.setText("✨ 生成提示词")
                        self.gen_prompt_btn.setEnabled(True)
                        try:
                            self._prompt_worker = None
                        except Exception:
                            pass
                    
                    try:
                        self._prompt_worker = LocationPromptWorker(url, headers, payload)
                        try:
                            self._prompt_worker.setParent(self.container)
                        except Exception:
                            pass
                        self._prompt_worker.finished.connect(on_finished)
                        self._prompt_worker.error.connect(on_error)
                        self._prompt_worker.start()
                    except Exception as e:
                        QMessageBox.critical(None, "错误", f"无法启动生成线程：{e}")
                
                except Exception as e:
                    QMessageBox.critical(None, "错误", f"生成提示词时出现异常：{e}")
                    self.gen_prompt_btn.setText("✨ 生成提示词")
                    self.gen_prompt_btn.setEnabled(True)

            def generate_images(self):
                """生成图片"""
                tasks = []
                for row in self.rows:
                    data = row.get_data()
                    # 检查：必须有名称、提示词，且状态为激活（绿色）
                    if data["name"] and data["prompt"] and data.get("is_active", True):
                        prompt = data["prompt"]
                        if getattr(self, "extra_enabled", True) and getattr(self, "extra_words", ""):
                            prompt = f"{self.extra_words} {prompt}".strip()
                        if getattr(self, "style_ref_image_path", None):
                            prompt = f"{prompt} 请参考参考图的画风风格生成图片".strip()
                        tasks.append((data["name"], prompt))
                
                if not tasks:
                    QMessageBox.warning(None, "提示", "没有可生成的任务（请检查地点名称、提示词是否完整，以及左侧状态灯是否开启）")
                    return
                
                # 提示用户开始生成
                print(f"[LocationNode] Starting generation for {len(tasks)} tasks")
                from PySide6.QtCore import QCoreApplication
                self.gen_image_btn.setText("⏳")
                self.gen_image_btn.setEnabled(False)
                QCoreApplication.processEvents()
                
                # 使用 mapshengcheng.MapImageGenerator
                try:
                    self.worker = mapshengcheng.MapImageGenerator(tasks)
                    self.worker.progress.connect(self.update_gen_status)
                    self.worker.image_generated.connect(self.on_image_generated)
                    self.worker.finished_all.connect(self.on_images_finished)
                    self.worker.error_occurred.connect(self.on_images_error)
                    self.worker.debug_info.connect(lambda msg: print(f"[MapGen Debug] {msg}"))
                    self.worker.start()
                except Exception as e:
                    self.on_images_error(str(e))

            def update_gen_status(self, msg):
                self.gen_image_btn.setText(msg)

            def on_image_generated(self, name, path):
                """图片生成回调"""
                for row in self.rows:
                    if row.name_edit.toPlainText().strip() == name:
                        row.set_image(path)
                        # Remove break to handle duplicate names correctly
                        # break
            
            def on_images_finished(self, count):
                self.gen_image_btn.setText("🖼️ 生成图片")
                self.gen_image_btn.setEnabled(True)
            
            def on_images_error(self, e):
                self.gen_image_btn.setText("🖼️ 生成图片")
                self.gen_image_btn.setEnabled(True)
                QMessageBox.warning(None, "生成错误", f"发生错误：{e}")

            def start_overlay_generation(self):
                """开始生成叠加图"""
                tasks = []
                for i, row in enumerate(self.rows):
                    data = row.get_data()
                    # 只有当:
                    # 1. 状态开启
                    # 2. 有提示词
                    # 3. 有参考图(overlay_path)
                    # 时才生成
                    if data['is_active'] and data['prompt'] and data['overlay']:
                        tasks.append({
                            "id": i,
                            "name": data.get('name', ''),
                            "prompt": data['prompt'],
                            "ref_image": data['overlay']
                        })
                        row.image_label.setText("生成中...")
                
                if not tasks:
                    QMessageBox.information(None, "提示", "没有需要生成的任务。\n请确保行状态开启，且有提示词和叠加参考图。")
                    return
                
                try:
                    print("[地点叠加图] DEBUG 任务汇总:", json.dumps([{
                        "id": t["id"],
                        "name": t.get("name", ""),
                        "prompt_len": len(t["prompt"]),
                        "ref_image": t["ref_image"]
                    } for t in tasks], ensure_ascii=False))
                except Exception:
                    pass
                
                self.gen_overlay_btn.setEnabled(False)
                self.gen_overlay_btn.setText("生成中...")
                
                self.overlay_worker = OverlayGenerator(tasks)
                self.overlay_worker.image_generated.connect(self.on_overlay_generated)
                try:
                    self.overlay_worker.error_occurred.connect(self.on_overlay_error)
                except Exception:
                    pass
                self.overlay_worker.finished_all.connect(self.on_overlay_finished)
                self.overlay_worker.start()

            def generate_image_for_row(self, row):
                data = row.get_data()
                name = data.get("name", "").strip()
                prompt = data.get("prompt", "").strip()
                if not name or not prompt or not data.get("is_active", True):
                    QMessageBox.warning(None, "提示", "请检查地点名称、提示词是否完整，以及左侧状态灯是否开启")
                    return
                if getattr(self, "extra_enabled", True) and getattr(self, "extra_words", ""):
                    prompt = f"{self.extra_words} {prompt}".strip()
                if getattr(self, "style_ref_image_path", None):
                    prompt = f"{prompt} 请参考参考图的画风风格生成图片".strip()
                try:
                    tasks = [(name, prompt)]
                    from PySide6.QtCore import QCoreApplication
                    row.image_label.setText("生成中...")
                    QCoreApplication.processEvents()
                    
                    # 获取风格参考图路径
                    style_ref_path = getattr(self, "style_ref_image_path", None)
                    print(f"[地点节点] DEBUG: 准备生成，风格参考图路径: {style_ref_path}")
                    
                    self.worker = mapshengcheng.MapImageGenerator(tasks, style_ref_path=style_ref_path)
                    self.worker.image_generated.connect(lambda n, p, r=row: r.set_image(p))
                    self.worker.finished_all.connect(lambda c, r=row: r.image_label.setText(""))
                    self.worker.error_occurred.connect(lambda e, r=row: r.image_label.setText("生成失败"))
                    self.worker.start()
                except Exception as e:
                    QMessageBox.critical(None, "错误", f"生成失败：{e}")

            def generate_overlay_for_row(self, row):
                data = row.get_data()
                name = data.get("name", "").strip()
                prompt = data.get("prompt", "").strip()
                ref_img = data.get("overlay")
                if not data.get("is_active", True) or not prompt or not ref_img:
                    QMessageBox.information(None, "提示", "请确保行状态开启，且有提示词和叠加参考图。")
                    return
                try:
                    idx = self.rows.index(row)
                except ValueError:
                    idx = name or 0
                try:
                    row.image_label.setText("生成中...")
                    tasks = [{"id": idx, "name": name, "prompt": prompt, "ref_image": ref_img}]
                    self.overlay_worker = OverlayGenerator(tasks)
                    self.overlay_worker.image_generated.connect(self.on_overlay_generated)
                    try:
                        self.overlay_worker.error_occurred.connect(self.on_overlay_error)
                    except Exception:
                        pass
                    self.overlay_worker.finished_all.connect(self.on_overlay_finished)
                    self.overlay_worker.start()
                except Exception as e:
                    QMessageBox.critical(None, "错误", f"生成失败：{e}")

            def on_overlay_generated(self, row_id, filepath):
                print(f"[地点叠加图] DEBUG 回调: row_id={row_id}, filepath={filepath}")
                # 优先按索引匹配
                try:
                    idx = int(row_id)
                    if 0 <= idx < len(self.rows):
                        print(f"[地点叠加图] DEBUG 按索引匹配成功: idx={idx}")
                        self.rows[idx].set_image(filepath)
                        return
                except Exception:
                    pass
                # 退回按名称匹配
                try:
                    name_key = str(row_id).strip()
                    print(f"[地点叠加图] DEBUG 尝试按名称匹配: {name_key}")
                    for row in self.rows:
                        if row.name_edit.toPlainText().strip() == name_key:
                            print("[地点叠加图] DEBUG 按名称匹配成功")
                            row.set_image(filepath)
                            return
                    print("[地点叠加图] DEBUG 未找到匹配行")
                except Exception as e:
                    print(f"[地点叠加图] DEBUG 匹配异常: {e}")
            
            def on_overlay_error(self, msg):
                try:
                    # msg format like "<row_id> 生成失败: <reason>"
                    row_id_part = str(msg).split(" ")[0]
                    idx = int(row_id_part)
                    if 0 <= idx < len(self.rows):
                        self.rows[idx].image_label.setText("生成失败")
                except:
                    pass

            def on_overlay_finished(self, count):
                self.gen_overlay_btn.setEnabled(True)
                self.gen_overlay_btn.setText("🎨 生成叠加图")
                QMessageBox.information(None, "完成", f"已完成 {count} 张叠加图生成")

            def get_node_data(self):
                """获取节点数据用于序列化"""
                rows_data = []
                for row in self.rows:
                    rows_data.append(row.get_data())
                return {
                    "location_rows": rows_data,
                    "style_ref_image": getattr(self, "style_ref_image_path", None)
                }

            def load_node_data(self, data):
                """从序列化数据加载"""
                if "location_rows" in data:
                    rows_data = data["location_rows"]
                    
                    # 清空现有行
                    while self.scroll_layout.count() > 1:
                        item = self.scroll_layout.takeAt(0)
                        if item.widget():
                            item.widget().deleteLater()
                    self.rows = []
                    
                    # 重建行
                    for row_data in rows_data:
                        row = LocationRowWidget()
                        row.set_data(
                            row_data.get("name", ""),
                            row_data.get("prompt", ""),
                            row_data.get("image", None),
                            row_data.get("overlay", None),
                            row_data.get("is_active", True)
                        )
                        self.scroll_layout.insertWidget(self.scroll_layout.count()-1, row)
                        self.rows.append(row)
                
                # 不再从节点数据加载附加值配置，改用全局配置
                # self.extra_words = data.get("extra_words", "")
                # self.extra_enabled = data.get("extra_enabled", True)
                # 重新加载一次全局配置以确保正确
                if hasattr(self, 'extra_manager'):
                    self.extra_manager.load_config()
                
            def on_socket_connected(self, socket, connection):
                """当接口连接时自动刷新"""
                if socket.socket_type == SocketType.INPUT:
                    QTimer.singleShot(500, self.refresh_locations)
            
        return LocationNode
