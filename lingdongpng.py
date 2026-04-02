"""
灵动智能体 - 图片节点模块
支持双击上传图片，显示图片预览和尺寸信息
"""

import os
import sys
import shutil
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem, QGraphicsPixmapItem,
    QFileDialog, QMenu, QInputDialog, QApplication, QDialog, QVBoxLayout, QLabel, QSizePolicy
)
from PySide6.QtCore import Qt, QRectF, QTimer, QMimeData, QUrl, QPoint, QSettings
from PySide6.QtGui import QFont, QColor, QPixmap, QPainter, QPen, QBrush, QDrag, QAction

# 导入高级图片查看器
from daoyan_fenjingtu import ImageViewerDialog as AdvancedImageViewer

# 导入召唤魔法模块
from lingdongmofa import MagicDialog, MagicConfig



class ImageViewerDialog(QDialog):
    """简易图片查看器"""
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("查看图片")
        self.resize(800, 600)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background-color: #1e1e1e;")
        
        self.pixmap = QPixmap(image_path)
        if not self.pixmap.isNull():
            self.update_image()
            
        layout.addWidget(self.label)
        
    def update_image(self):
        if not self.pixmap.isNull():
            scaled = self.pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.label.setPixmap(scaled)

    def resizeEvent(self, event):
        self.update_image()
        super().resizeEvent(event)



# SVG图标定义
SVG_IMAGE_ICON = '''<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2"/>
<circle cx="8.5" cy="8.5" r="1.5" fill="currentColor"/>
<path d="M3 16l5-5 3 3 5-5 5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
</svg>'''


class ImageNode:
    """图片节点 - 支持双击上传图片
    
    注意：这个类需要继承自CanvasNode，在导入时会动态继承
    """
    
    @staticmethod
    def create_image_node(CanvasNode):
        """动态创建ImageNode类，继承自CanvasNode"""
        
        class GridImageItem(QGraphicsPixmapItem):
            """网格图片项 - 支持点击和拖拽"""
            def __init__(self, pixmap, parent, index, callback):
                super().__init__(pixmap, parent)
                self.index = index
                self.callback = callback
                self.parent_node = parent
                self.drag_start_pos = None
                # 允许鼠标点击
                self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
                # 设置光标为手型
                self.setCursor(Qt.CursorShape.PointingHandCursor)

            def mousePressEvent(self, event):
                if event.button() == Qt.MouseButton.LeftButton:
                    self.drag_start_pos = event.pos()
                    event.accept()
                else:
                    super().mousePressEvent(event)

            def mouseMoveEvent(self, event):
                if not self.drag_start_pos:
                    return

                # 计算移动距离，判断是否为拖拽
                dist = (event.pos() - self.drag_start_pos).manhattanLength()
                if dist < QApplication.startDragDistance():
                    return

                # 获取图片路径
                if 0 <= self.index < len(self.parent_node.image_paths):
                    image_path = self.parent_node.image_paths[self.index]
                    
                    # 创建拖拽对象
                    drag = QDrag(event.widget())
                    mime_data = QMimeData()
                    
                    # 设置文件路径列表
                    url = QUrl.fromLocalFile(image_path)
                    mime_data.setUrls([url])
                    drag.setMimeData(mime_data)
                    
                    # 设置拖拽预览图
                    pixmap = self.pixmap().scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio)
                    drag.setPixmap(pixmap)
                    drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
                    
                    # 开始拖拽
                    drag.exec_(Qt.DropAction.CopyAction)
                    self.drag_start_pos = None

            def mouseReleaseEvent(self, event):
                # 如果是点击而不是拖拽
                if self.drag_start_pos:
                    self.callback(self.index)
                    self.drag_start_pos = None
                super().mouseReleaseEvent(event)

            def contextMenuEvent(self, event):
                """右键菜单 - 召唤魔法"""
                menu = QMenu()
                
                # 主召唤魔法动作
                magic_action = QAction("🔮 召唤魔法", menu)
                magic_action.triggered.connect(lambda: self.open_magic_dialog(0))
                menu.addAction(magic_action)

                # 删除图片动作
                delete_action = QAction("🗑️ 删除图片", menu)
                delete_action.triggered.connect(lambda: self.parent_node.delete_image(self.index))
                menu.addAction(delete_action)

                # 保存图片动作
                save_action = QAction("💾 保存图片", menu)
                if 0 <= self.index < len(self.parent_node.image_paths):
                    path = self.parent_node.image_paths[self.index]
                    save_action.triggered.connect(lambda: self.parent_node.save_image(path))
                menu.addAction(save_action)
                
                # 添加保存的提示词作为快捷选项
                try:
                    prompts = MagicConfig.load_prompts()
                    if prompts:
                        menu.addSeparator()
                        menu.addAction(QAction("快捷施法:", menu, enabled=False))
                        
                        for i, prompt_data in enumerate(prompts):
                            # 处理字典格式或旧的字符串格式
                            if isinstance(prompt_data, dict):
                                name = prompt_data.get("name", f"提示词 {i+1}")
                                content = prompt_data.get("content", "")
                            else:
                                name = f"提示词 {i+1}"
                                content = str(prompt_data)
                            
                            # 显示名称，Tooltip显示内容
                            display_text = name
                            action = QAction(f"✨ {display_text}", menu)
                            if content:
                                action.setToolTip(content[:200])

                            # 点击直接生成图片
                            action.triggered.connect(lambda checked, c=content: self.parent_node.trigger_magic_generation(c, self.parent_node.image_paths[self.index] if 0 <= self.index < len(self.parent_node.image_paths) else None))
                            menu.addAction(action)
                except Exception as e:
                    print(f"Error loading magic prompts: {e}")

                menu.exec(event.screenPos())

            def open_magic_dialog(self, initial_index=0):
                """打开召唤魔法对话框"""
                if 0 <= self.index < len(self.parent_node.image_paths):
                    image_path = self.parent_node.image_paths[self.index]
                    # 使用activeWindow作为父窗口，确保模态对话框正常显示
                    dialog = MagicDialog(image_path, QApplication.activeWindow())
                    if isinstance(initial_index, int):
                        dialog.current_index = initial_index
                        dialog.refresh_tabs()
                    dialog.exec()

        class MagicImageItem(QGraphicsPixmapItem):
            """支持召唤魔法的单图项"""
            def __init__(self, pixmap, parent, image_path):
                super().__init__(pixmap, parent)
                self.image_path = image_path
                self.parent_node = parent

            def contextMenuEvent(self, event):
                """右键菜单 - 召唤魔法"""
                menu = QMenu()
                
                # 主召唤魔法动作
                magic_action = QAction("🔮 召唤魔法", menu)
                magic_action.triggered.connect(lambda: self.open_magic_dialog(0))
                menu.addAction(magic_action)

                # 删除图片动作
                delete_action = QAction("🗑️ 删除图片", menu)
                # 单图模式下，使用 parent_node 的 current_index
                delete_action.triggered.connect(lambda: self.parent_node.delete_image(self.parent_node.current_index))
                menu.addAction(delete_action)

                # 保存图片动作
                save_action = QAction("💾 保存图片", menu)
                save_action.triggered.connect(lambda: self.parent_node.save_image(self.image_path))
                menu.addAction(save_action)
                
                # 添加保存的提示词作为快捷选项
                try:
                    prompts = MagicConfig.load_prompts()
                    if prompts:
                        menu.addSeparator()
                        menu.addAction(QAction("快捷施法:", menu, enabled=False))
                        
                        for i, prompt_data in enumerate(prompts):
                            # 处理字典格式或旧的字符串格式
                            if isinstance(prompt_data, dict):
                                name = prompt_data.get("name", f"提示词 {i+1}")
                                content = prompt_data.get("content", "")
                            else:
                                name = f"提示词 {i+1}"
                                content = str(prompt_data)
                            
                            # 显示名称，Tooltip显示内容
                            display_text = name
                            action = QAction(f"✨ {display_text}", menu)
                            if content:
                                action.setToolTip(content[:200])

                            # 点击直接生成图片
                            action.triggered.connect(lambda checked, c=content: self.parent_node.trigger_magic_generation(c, self.image_path))
                            menu.addAction(action)
                except Exception as e:
                    print(f"Error loading magic prompts: {e}")
                    
                menu.exec(event.screenPos())

            def open_magic_dialog(self, initial_index=0):
                """打开召唤魔法对话框"""
                if self.image_path:
                    # 使用activeWindow作为父窗口，确保模态对话框正常显示
                    dialog = MagicDialog(self.image_path, QApplication.activeWindow())
                    if isinstance(initial_index, int):
                        dialog.current_index = initial_index
                        dialog.refresh_tabs()
                    dialog.exec()

        class ImageNodeImpl(CanvasNode):
            """图片节点实现 - 支持双击上传图片、自由缩放"""
            
            def __init__(self, x, y):
                super().__init__(x, y, 250, 250, "图片", SVG_IMAGE_ICON)
                
                # 最小和最大尺寸
                self.min_width = 150
                self.min_height = 150
                self.max_width = 4000
                self.max_height = 4000
                
                # 缩放控制
                self.is_resizing = False
                self.resize_start_pos = None
                self.resize_start_rect = None
                
                # 图片数据
                self.image_path = None
                self.image_paths = []  # 多图列表
                self.current_index = 0  # 当前图片索引
                self.is_group_mode = False  # 是否开启多图模式
                self.pixmap = None
                self.image_width = 0
                self.image_height = 0
                
                # 图片预览区域
                self.preview_text = QGraphicsTextItem(self)
                self.preview_text.setPlainText("双击上传图片...")
                self.preview_text.setDefaultTextColor(QColor("#666666"))
                self.preview_text.setFont(QFont("Microsoft YaHei", 9))
                self.preview_text.setPos(60, 120)
                
                # 图片显示项（初始为None）
                self.image_item = None
                self.grid_items = []  # 平铺图片项列表
                self.viewers = [] # 图片查看器窗口列表
                
                # 尺寸信息文本（右上角）
                self.size_text = QGraphicsTextItem(self)
                self.size_text.setPlainText("")
                self.size_text.setDefaultTextColor(QColor("#00bfff"))
                self.size_text.setFont(QFont("Microsoft YaHei", 8, QFont.Weight.Bold))
                self.size_text.setPos(140, 8)  # 右上角位置
                self.size_text.setVisible(False)

                # 编组按钮（放在标题文字后方）
                self.group_btn = QGraphicsTextItem("📚", self)
                self.group_btn.setToolTip("开启/关闭多图模式")
                self.group_btn.setDefaultTextColor(QColor("#999999"))
                self.group_btn.setFont(QFont("Segoe UI Emoji", 12))
                
                # 计算位置：标题位置(50) + 标题宽度 + 间距
                title_width = self.title_text.boundingRect().width()
                self.group_btn.setPos(50 + title_width + 5, 8)
                self.group_btn.setZValue(10)  # 确保在顶层

                # 返回按钮（右上角，在编组按钮左侧）
                self.back_btn = QGraphicsTextItem("↩", self)
                self.back_btn.setToolTip("返回多图模式")
                self.back_btn.setDefaultTextColor(QColor("#00bfff"))
                self.back_btn.setFont(QFont("Segoe UI Emoji", 100, QFont.Weight.Bold))
                self.back_btn.setZValue(10)
                self.back_btn.setVisible(False)

                # 导航按钮（左）
                self.prev_btn = QGraphicsTextItem("❮", self)
                self.prev_btn.setDefaultTextColor(QColor("#00ff00")) # Green
                self.prev_btn.setFont(QFont("Arial", 100, QFont.Weight.Bold))
                self.prev_btn.setZValue(10)
                self.prev_btn.setVisible(False)
                
                # 导航按钮（右）
                self.next_btn = QGraphicsTextItem("❯", self)
                self.next_btn.setDefaultTextColor(QColor("#00ff00")) # Green
                self.next_btn.setFont(QFont("Arial", 100, QFont.Weight.Bold))
                self.next_btn.setZValue(10)
                self.next_btn.setVisible(False)
                
                # 索引指示器
                self.index_text = QGraphicsTextItem("", self)
                self.index_text.setDefaultTextColor(QColor("#ffffff"))
                self.index_text.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
                self.index_text.setZValue(10)
                self.index_text.setVisible(False)

            def trigger_magic_generation(self, prompt_content, source_image_path=None):
                """触发魔法生成图片"""
                if not prompt_content:
                    print("提示词为空")
                    return
                
                # 如果未提供源图片路径，尝试使用当前显示的图片
                if not source_image_path and self.image_path:
                    source_image_path = self.image_path

                # 获取API配置
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
                
                if not os.path.exists(config_file):
                    print(f"未找到配置文件: {config_file}")
                    return

                print(f"[图片节点] 开始生成图片: {prompt_content[:20]}...")
                
                # 更新左侧闪电状态栏
                try:
                    for widget in QApplication.topLevelWidgets():
                        if hasattr(widget, 'set_connection_text'):
                            widget.set_connection_text(f"正在召唤魔法: {prompt_content[:15]}...", 'loading')
                            break
                except Exception as e:
                    print(f"Update connection status error: {e}")
                
                # 构造数据行 [[0, 0, prompt, source_image_path]]
                data_rows = [[0, 0, prompt_content, source_image_path]]
                
                # 创建并启动生成线程
                from lingdonggooglejuben import PeopleImageGenerationWorker
                self.worker = PeopleImageGenerationWorker(image_api, config_file, data_rows)
                # 修改输出目录为 image_node_gen
                self.worker.output_dir = "image_node_gen" 
                self.worker.image_completed.connect(self.on_magic_generation_completed)
                self.worker.start()
            
            def on_magic_generation_completed(self, index, image_path, prompt):
                """生成完成回调"""
                print(f"[图片节点] 生成完成: {image_path}")
                
                # 更新左侧闪电状态栏
                try:
                    for widget in QApplication.topLevelWidgets():
                        if hasattr(widget, 'set_connection_text'):
                            widget.set_connection_text("召唤魔法完成", 'success')
                            # 3秒后恢复正常状态
                            QTimer.singleShot(3000, lambda: widget.set_connection_text("已连接", 'normal'))
                            break
                except Exception as e:
                    print(f"Update connection status error: {e}")

                # 确保在主线程更新UI - 创建新节点
                if self.scene():
                    try:
                        # 计算新节点位置 (在当前节点右侧 +50 像素)
                        new_x = self.pos().x() + self.rect().width() + 50
                        new_y = self.pos().y()
                        
                        # 创建新节点 (使用当前类，即 ImageNodeImpl)
                        new_node = self.__class__(new_x, new_y)
                        
                        # 添加到场景
                        self.scene().addItem(new_node)
                        
                        # 加载生成的图片
                        new_node.load_image(image_path)
                        
                        # 选中新节点
                        self.scene().clearSelection()
                        new_node.setSelected(True)
                        
                        print(f"[图片节点] 已创建新节点显示图片: {new_x}, {new_y}")
                    except Exception as e:
                        print(f"Error creating new node: {e}")
                        # 回退方案：如果在当前节点显示
                        self.load_image(image_path)
                else:
                    self.load_image(image_path)
            
            def mousePressEvent(self, event):
                """鼠标按下 - 检测缩放区域和按钮点击"""
                if event.button() == Qt.MouseButton.LeftButton:
                    local_pos = event.pos()
                    
                    # 检查是否点击编组按钮
                    if self.group_btn.sceneBoundingRect().contains(event.scenePos()):
                        self.toggle_group_mode()
                        event.accept()
                        return

                    # 检查是否点击返回按钮
                    if self.back_btn.isVisible() and self.back_btn.sceneBoundingRect().contains(event.scenePos()):
                        self.toggle_group_mode() # 返回其实就是切换模式
                        event.accept()
                        return
                        
                    # 检查导航按钮
                    if self.prev_btn.isVisible() and self.prev_btn.sceneBoundingRect().contains(event.scenePos()):
                        self.show_prev_image()
                        event.accept()
                        return
                        
                    if self.next_btn.isVisible() and self.next_btn.sceneBoundingRect().contains(event.scenePos()):
                        self.show_next_image()
                        event.accept()
                        return
                    
                    rect = self.rect()
                    
                    # 检查是否点击在右下角缩放区域（15x15像素）
                    resize_zone = 15
                    if (local_pos.x() > rect.width() - resize_zone and 
                        local_pos.y() > rect.height() - resize_zone):
                        self.is_resizing = True
                        self.resize_start_pos = local_pos
                        self.resize_start_rect = self.rect()
                        event.accept()
                        return
                
                super().mousePressEvent(event)
            
            def mouseMoveEvent(self, event):
                """鼠标移动 - 缩放节点"""
                if self.is_resizing:
                    delta = event.pos() - self.resize_start_pos
                    
                    # 计算新尺寸（保持正方形比例）
                    delta_size = max(delta.x(), delta.y())
                    new_size = max(self.min_width, min(self.resize_start_rect.width() + delta_size, self.max_width))
                    
                    # 更新节点矩形
                    self.setRect(0, 0, new_size, new_size)
                    
                    # 更新UI位置
                    self.update_ui_positions(new_size)
                    
                    # 更新接口位置和连接线
                    if hasattr(self, 'update_socket_positions'):
                        self.update_socket_positions()
                    if hasattr(self, 'update_connections'):
                        self.update_connections()
                    
                    # 重新加载图片以适应新尺寸
                    self.load_current_image()
                    
                    event.accept()
                    return
                
                super().mouseMoveEvent(event)
            
            def update_ui_positions(self, node_size=None):
                """更新UI元素位置"""
                if node_size is None:
                    node_size = self.rect().width()
                
                # 编组按钮 (位置固定在标题后，不需要随尺寸更新，或者在此处强制重置以防万一)
                title_width = self.title_text.boundingRect().width()
                self.group_btn.setPos(50 + title_width + 5, 8)

                # 返回按钮 - 放置在图片下方中央
                if self.back_btn.isVisible():
                    back_w = self.back_btn.boundingRect().width()
                    back_h = self.back_btn.boundingRect().height()
                    # 放置在底部稍微靠上一点的位置，避免被边缘遮挡
                    self.back_btn.setPos((node_size - back_w) / 2, node_size - back_h - 10)
                
                # 尺寸文本
                if self.size_text.isVisible():
                    text_width = self.size_text.boundingRect().width()
                    self.size_text.setPos(node_size - 10 - text_width, 8)
                
                # 导航按钮和索引
                if self.prev_btn.isVisible():
                    # 左侧垂直居中
                    self.prev_btn.setPos(10, (node_size - self.prev_btn.boundingRect().height()) / 2)
                    # 右侧垂直居中
                    self.next_btn.setPos(node_size - self.next_btn.boundingRect().width() - 10, 
                                       (node_size - self.next_btn.boundingRect().height()) / 2)
                    
                    idx_w = self.index_text.boundingRect().width()
                    self.index_text.setPos((node_size - idx_w)/2, node_size - 30)

            def mouseReleaseEvent(self, event):
                """鼠标释放 - 结束缩放"""
                if self.is_resizing:
                    self.is_resizing = False
                    self.resize_start_pos = None
                    self.resize_start_rect = None
                    print(f"[图片节点] 缩放完成: {self.rect().width():.0f}×{self.rect().height():.0f}")
                    event.accept()
                    return
                
                super().mouseReleaseEvent(event)
            
            def mouseDoubleClickEvent(self, event):
                """双击事件 - 打开文件对话框上传图片 或 打开已有图片"""
                if event.button() == Qt.MouseButton.LeftButton:
                    # 如果已有图片，双击打开当前图片
                    if self.image_paths and 0 <= self.current_index < len(self.image_paths):
                        try:
                            file_path = self.image_paths[self.current_index]
                            if os.path.exists(file_path):
                                # 使用内部查看器打开 (切换为高级查看器)
                                viewer = AdvancedImageViewer(file_path)
                                # 连接截图信号
                                viewer.screenshot_created.connect(self.on_screenshot_created)
                                
                                self.viewers.append(viewer)
                                viewer.finished.connect(lambda r, v=viewer: self.viewers.remove(v) if v in self.viewers else None)
                                viewer.show()
                                print(f"[图片节点] 打开图片: {file_path}")
                            else:
                                print(f"[图片节点] 文件不存在: {file_path}")
                        except Exception as e:
                            print(f"[图片节点] 打开图片失败: {e}")
                    else:
                        # 如果没有图片，双击上传
                        self.upload_image()
                    
                    event.accept()
                    return
                
                super().mouseDoubleClickEvent(event)

            def on_screenshot_created(self, path):
                """处理截图生成的新图片节点"""
                if not path or not os.path.exists(path):
                    return
                    
                scene = self.scene()
                if not scene:
                    return
                
                try:
                    # 创建新节点 (使用当前类)
                    new_node = self.__class__(self.x() + self.rect().width() + 50, self.y())
                    # 加载图片
                    new_node.load_image(path)
                    scene.addItem(new_node)
                    print(f"[图片节点] 截图创建新节点: {path}")
                    
                except Exception as e:
                    print(f"[图片节点] 创建截图节点失败: {e}")
            
            def delete_image(self, index):
                """删除指定索引的图片"""
                if 0 <= index < len(self.image_paths):
                    removed_path = self.image_paths.pop(index)
                    print(f"[图片节点] 删除图片: {removed_path}")
                    
                    # 调整当前索引
                    if self.current_index >= len(self.image_paths):
                        self.current_index = max(0, len(self.image_paths) - 1)
                    
                    # 如果删除后没有图片了
                    if not self.image_paths:
                        self.image_path = None
                        self.pixmap = None
                        
                        # 清除场景中的图片项
                        if self.image_item:
                            if self.scene():
                                self.scene().removeItem(self.image_item)
                            self.image_item = None
                        
                        for item in self.grid_items:
                            if self.scene():
                                self.scene().removeItem(item)
                        self.grid_items.clear()
                        
                        # 显示上传提示
                        self.preview_text.setVisible(True)
                        self.size_text.setVisible(False)
                        self.group_btn.setVisible(True) # 保持显示
                        self.back_btn.setVisible(False)
                        self.prev_btn.setVisible(False)
                        self.next_btn.setVisible(False)
                        self.index_text.setVisible(False)
                        
                        # 重置多图模式状态
                        self.is_group_mode = False
                        self.group_btn.setDefaultTextColor(QColor("#999999"))
                        
                        self.update_ui_positions()
                        
                        # 强制刷新
                        if self.scene():
                            self.scene().update()
                        self.update()
                    else:
                        # 重新加载显示
                        self.load_current_image()
                        # 更新UI（如索引文字）
                        self.update_group_ui()
                        
                        # 强制刷新
                        if self.scene():
                            self.scene().update()
                        self.update()

            def toggle_group_mode(self):
                """切换多图模式"""
                self.is_group_mode = not self.is_group_mode
                
                # 弹出提示
                if self.is_group_mode:
                    # QMessageBox.information(None, "提示", "已切换到多图模式")
                    self.group_btn.setDefaultTextColor(QColor("#00bfff")) # Blue
                    print("[图片节点] 开启多图模式")
                else:
                    # QMessageBox.information(None, "提示", "已切换到单图模式")
                    self.group_btn.setDefaultTextColor(QColor("#999999")) # Grey
                    print("[图片节点] 关闭多图模式")
                
                # 刷新显示
                self.load_current_image()

            def show_prev_image(self):
                if not self.image_paths: return
                self.current_index = (self.current_index - 1) % len(self.image_paths)
                self.load_current_image()
                
            def show_next_image(self):
                if not self.image_paths: return
                self.current_index = (self.current_index + 1) % len(self.image_paths)
                self.load_current_image()
                
            def load_current_image(self):
                if not self.image_paths: return
                
                # 如果是多图模式且有多张图片，显示网格
                if self.is_group_mode and len(self.image_paths) > 0:
                    self.load_grid_images()
                else:
                    # 单图模式或只有一张图
                    if 0 <= self.current_index < len(self.image_paths):
                        path = self.image_paths[self.current_index]
                        self.load_single_image(path)

            def load_grid_images(self):
                """渲染网格图片 - 自动调整节点大小以保证清晰度"""
                try:
                    # 清除单图
                    if self.image_item:
                        if self.scene():
                            self.scene().removeItem(self.image_item)
                        self.image_item = None
                    
                    # 清除旧网格
                    for item in self.grid_items:
                        if self.scene():
                            self.scene().removeItem(item)
                    self.grid_items.clear()
                    
                    # 隐藏提示文字
                    self.preview_text.setVisible(False)
                    
                    count = len(self.image_paths)
                    if count == 0: return

                    import math
                    # 计算网格行列
                    cols = math.ceil(math.sqrt(count))
                    rows = math.ceil(count / cols)
                    
                    # 预留空间
                    top_margin = 40
                    bottom_margin = 10
                    side_margin = 10
                    
                    # 设定最小单元格尺寸（保证图片不因太小而模糊）
                    MIN_CELL_SIZE = 400
                    
                    # 计算所需的最小内容区域尺寸
                    min_content_w = cols * MIN_CELL_SIZE
                    min_content_h = rows * MIN_CELL_SIZE
                    
                    # 计算所需的最小节点尺寸
                    required_node_w = min_content_w + (side_margin * 2)
                    required_node_h = min_content_h + top_margin + bottom_margin
                    
                    # 获取当前节点尺寸
                    current_w = self.rect().width()
                    current_h = self.rect().height()
                    
                    # 如果当前尺寸小于所需尺寸，自动扩大节点
                    new_w = max(current_w, required_node_w)
                    new_h = max(current_h, required_node_h)
                    
                    # 限制最大尺寸（避免过大）
                    MAX_AUTO_SIZE = 4000
                    new_w = min(new_w, MAX_AUTO_SIZE)
                    new_h = min(new_h, MAX_AUTO_SIZE)
                    
                    if new_w > current_w or new_h > current_h:
                        self.setRect(0, 0, new_w, new_h)
                        self.update_ui_positions(new_w)
                        
                        # 更新接口位置和连接线
                        if hasattr(self, 'update_socket_positions'):
                            self.update_socket_positions()
                        if hasattr(self, 'update_connections'):
                            self.update_connections()
                            
                        print(f"[图片节点] 自动调整大小至: {new_w:.0f}x{new_h:.0f}")

                    # 使用调整后的尺寸进行布局
                    node_size_w = self.rect().width()
                    node_size_h = self.rect().height()
                    
                    available_w = node_size_w - (side_margin * 2)
                    available_h = node_size_h - top_margin - bottom_margin
                    
                    cell_w = available_w / cols
                    cell_h = available_h / rows
                    
                    for i, path in enumerate(self.image_paths):
                        if i >= 99: break 
                        
                        row = i // cols
                        col = i % cols
                        
                        pixmap = QPixmap(path)
                        if pixmap.isNull(): continue
                        
                        # 缩放图片适应单元格（留一点间隙）
                        gap = 2
                        target_w = cell_w - gap * 2
                        target_h = cell_h - gap * 2
                        
                        if target_w <= 0 or target_h <= 0: continue
                        
                        scaled = pixmap.scaled(target_w, target_h, 
                                             Qt.AspectRatioMode.KeepAspectRatio, 
                                             Qt.TransformationMode.SmoothTransformation)
                        
                        # 使用自定义GridImageItem以支持点击
                        item = GridImageItem(scaled, self, i, self.on_grid_image_clicked)
                        item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
                        
                        # 居中放置
                        x = side_margin + col * cell_w + gap + (target_w - scaled.width()) / 2
                        y = top_margin + row * cell_h + gap + (target_h - scaled.height()) / 2
                        
                        item.setPos(x, y)
                        self.grid_items.append(item)
                    
                    # 更新UI状态
                    self.update_group_ui()
                    
                    # 更新尺寸信息为图片数量
                    self.size_text.setPlainText(f"共 {count} 张")
                    self.size_text.setVisible(True)
                    self.update_ui_positions()
                    
                except Exception as e:
                    print(f"[图片节点] 加载网格失败: {e}")

            def on_grid_image_clicked(self, index):
                """处理网格图片点击 - 切换到单图模式"""
                print(f"[图片节点] 点击网格图片索引: {index}")
                # 延迟执行以避免事件冲突
                QTimer.singleShot(0, lambda: self._switch_to_single_image(index))
            
            def _switch_to_single_image(self, index):
                """切换到单图模式的具体实现"""
                self.is_group_mode = False # 关闭多图模式
                self.current_index = index
                
                # 重置节点大小，避免从多图模式切换回来时尺寸过大
                current_w = self.rect().width()
                if current_w > 600:
                    self.setRect(0, 0, 600, 600)
                    self.update_ui_positions(600)
                    # 更新接口位置和连接线
                    if hasattr(self, 'update_socket_positions'):
                        self.update_socket_positions()
                    if hasattr(self, 'update_connections'):
                        self.update_connections()
                
                self.update_group_ui() # 更新按钮状态
                self.load_current_image() # 加载单张图片

            def update_group_ui(self):
                """更新多图UI状态"""
                count = len(self.image_paths)
                
                # Update group button color
                if self.is_group_mode:
                    self.group_btn.setDefaultTextColor(QColor("#00bfff")) # Blue
                else:
                    self.group_btn.setDefaultTextColor(QColor("#999999")) # Grey
                
                # 如果是多图模式（平铺），隐藏翻页按钮
                if self.is_group_mode and count > 1:
                    self.prev_btn.setVisible(False)
                    self.next_btn.setVisible(False)
                    self.index_text.setVisible(False)
                    self.back_btn.setVisible(False) # 多图模式不需要返回按钮
                    self.update_ui_positions()
                    return

                # 单图模式下显示翻页按钮
                if count > 1:
                    self.prev_btn.setVisible(True)
                    self.next_btn.setVisible(True)
                    self.index_text.setVisible(True)
                    self.index_text.setPlainText(f"{self.current_index + 1}/{count}")
                    self.back_btn.setVisible(True) # 单图模式且多张图片，显示返回按钮
                    
                    self.update_ui_positions()
                else:
                    self.prev_btn.setVisible(False)
                    self.next_btn.setVisible(False)
                    self.index_text.setVisible(False)
                    self.back_btn.setVisible(False)

            def upload_image(self):
                """上传图片"""
                if self.is_group_mode:
                    # 多图模式
                    file_paths, _ = QFileDialog.getOpenFileNames(
                        None,
                        "选择图片 (最多99张)",
                        "",
                        "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;所有文件 (*.*)"
                    )
                    
                    if file_paths:
                        # 限制数量
                        self.image_paths = file_paths[:99]
                        self.current_index = 0
                        print(f"[图片节点] 已加载 {len(self.image_paths)} 张图片")
                        self.load_current_image()
                else:
                    # 单图模式
                    file_path, _ = QFileDialog.getOpenFileName(
                        None,
                        "选择图片",
                        "",
                        "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;所有文件 (*.*)"
                    )
                    
                    if file_path:
                        self.image_paths = [file_path]
                        self.current_index = 0
                        self.load_image(file_path)
            
            def load_image(self, file_path):
                """加载图片（入口）"""
                try:
                    # 简单的列表管理逻辑
                    if file_path not in self.image_paths:
                        if not self.is_group_mode:
                            self.image_paths = [file_path]
                            self.current_index = 0
                        else:
                            self.image_paths.append(file_path)
                            self.current_index = len(self.image_paths) - 1
                    else:
                        self.current_index = self.image_paths.index(file_path)
                    
                    self.load_current_image()
                except Exception as e:
                    print(f"[图片节点] 加载图片出错: {e}")

            def load_single_image(self, file_path):
                """加载并显示单张图片"""
                try:
                    # 清除网格
                    for item in self.grid_items:
                        self.scene().removeItem(item)
                    self.grid_items.clear()

                    # 加载图片
                    self.pixmap = QPixmap(file_path)
                    
                    if self.pixmap.isNull():
                        print(f"[图片节点] 加载失败: {file_path}")
                        return
                    
                    # 保存图片路径和原始尺寸
                    self.image_path = file_path
                    self.image_width = self.pixmap.width()
                    self.image_height = self.pixmap.height()
                    
                    # 隐藏提示文字
                    self.preview_text.setVisible(False)
                    
                    # 计算缩放比例（保持宽高比，适应节点大小）
                    node_size = self.rect().width()
                    max_width = node_size - 20  # 留边距
                    max_height = node_size - 60  # 留空间给标题和尺寸
                    
                    scaled_pixmap = self.pixmap.scaled(
                        max_width, max_height,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    
                    # 如果已有图片项，先删除
                    if self.image_item:
                        if self.scene():
                            self.scene().removeItem(self.image_item)
                    
                    # 创建图片显示项
                    self.image_item = MagicImageItem(scaled_pixmap, self, file_path)
                    self.image_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
                    
                    # 居中显示图片
                    img_x = (node_size - scaled_pixmap.width()) / 2
                    img_y = 50 + (max_height - scaled_pixmap.height()) / 2
                    self.image_item.setPos(img_x, img_y)
                    
                    # 显示图片尺寸（右上角）
                    size_info = f"{self.image_width}×{self.image_height}"
                    self.size_text.setPlainText(size_info)
                    self.size_text.setVisible(True)
                    
                    # 更新UI位置和多图状态
                    self.update_ui_positions(node_size)
                    self.update_group_ui()
                    
                    print(f"[图片节点] 加载成功: {file_path}")
                    
                except Exception as e:
                    print(f"[图片节点] 加载图片出错: {e}")
            
            def paint(self, painter, option, widget):
                """自定义绘制 - 添加图片边框和缩放指示"""
                # 先调用父类绘制（背景和标题）
                super().paint(painter, option, widget)
                
                # 如果有图片，绘制图片边框
                if self.image_item and self.pixmap:
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    
                    # 获取图片位置和大小
                    img_rect = self.image_item.boundingRect()
                    img_pos = self.image_item.pos()
                    
                    # 绘制图片边框
                    border_rect = QRectF(
                        img_pos.x() - 2,
                        img_pos.y() - 2,
                        img_rect.width() + 4,
                        img_rect.height() + 4
                    )
                    
                    painter.setPen(QPen(QColor("#00bfff"), 1))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRoundedRect(border_rect, 4, 4)
                
                # 绘制右下角缩放指示器（当鼠标悬停或正在缩放时）
                if self.isSelected() or self.is_resizing:
                    from PySide6.QtCore import QPointF
                    from PySide6.QtGui import QPolygonF
                    rect = self.rect()
                    painter.setPen(QPen(QColor("#00bfff"), 2))
                    # 绘制右下角小三角形
                    points = [
                        rect.bottomRight() + QPointF(-15, 0),
                        rect.bottomRight() + QPointF(0, -15),
                        rect.bottomRight()
                    ]
                    painter.drawPolygon(QPolygonF(points))
            
            def get_image_info(self):
                """获取图片信息"""
                if self.image_path:
                    return {
                        'path': self.image_path,
                        'width': self.image_width,
                        'height': self.image_height,
                        'size': f"{self.image_width}×{self.image_height}"
                    }
                return None

            def save_image(self, image_path):
                """保存图片到本地"""
                if not image_path or not os.path.exists(image_path):
                    return
                
                # 获取原文件名
                file_name = os.path.basename(image_path)
                
                # 打开保存对话框
                save_path, _ = QFileDialog.getSaveFileName(
                    None,
                    "保存图片",
                    file_name,
                    "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;所有文件 (*.*)"
                )
                
                if save_path:
                    try:
                        shutil.copy2(image_path, save_path)
                        print(f"[图片节点] 图片已保存: {save_path}")
                    except Exception as e:
                        print(f"[图片节点] 保存图片失败: {e}")
        
        return ImageNodeImpl
