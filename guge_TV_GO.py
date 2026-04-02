
import sys
import os
import json
from PySide6.QtWidgets import (
    QGraphicsProxyWidget, QWidget, QVBoxLayout, 
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QHBoxLayout, QGraphicsItem, QStyledItemDelegate,
    QGraphicsPixmapItem, QMessageBox, QMenu, QFileDialog, QApplication,
    QInputDialog, QGridLayout, QDialog
)
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QPoint, QSettings, QMimeData, QUrl, QEvent, QThread, Signal
from daoyan_fenjingtu import StoryboardDialog, StoryboardWorker, ImageViewerDialog
from daoyan_image1toimage2 import ImageToImageWorker
from daoyan_zhuizong_aibot import run_auto_track_storyboard_generation
from daoyan_sora2 import Sora2Worker
# 导入优化Worker
from sora2_tishici import OptimizationWorker
# 导入设置对话框
from daoyan_setting import DirectorSettingDialog
from daoyan_fujia_tishici import get_additional_prompt, open_additional_prompt_dialog
from daoyan_tupian_fujiatishici import open_additional_image_prompt_dialog, AdditionalImagePromptManager
from daoyan_tishici_JPG import create_expand_button, toggle_image_prompt_column, update_image_prompt_column
from daoyan_changjing_change import change_scene_image
# 导入Sora人物@模式
from daoyan_youhua import SoraCharacterMappingDialog, SoraCharacterMappingManager
from daoyan_duotuxianshi_sceen import MultiStoryboardDialog
from PySide6.QtGui import QColor, QBrush, QPen, QPixmap, QPolygonF, QPainter, QCursor, QDrag, QFont, QFontMetrics
from textEDITgoogle import open_edit_dialog_for_item, TextEditDialog
from lingdongconnect import DataType, SocketType
from sora_jiaoseku import CreateCharacterThread, save_character
from daoyan_chaijiantools import CropDialog
from daoyan_huaban_boss import DirectorArtboardDialog

from daoyan_jianying_video_move import DraggableVideoWidget
from daoyan_bofang import DirectorVideoPlayer

class DirectorNode:
    """导演节点工厂类"""
    _node_counter = 0  # 类变量：节点计数器
    
    @staticmethod
    def create_node(CanvasNode):
        """动态创建DirectorNode类，继承自CanvasNode"""
        

        class GridVideoWidget(QWidget):
            """显示多视频的网格控件"""
            def __init__(self, video_paths, parent=None, director_node=None):
                super().__init__(parent)
                self.video_paths = video_paths
                self.director_node = director_node
                self.setup_ui()

            def setup_ui(self):
                layout = QGridLayout(self)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(2)
                
                for i, path in enumerate(self.video_paths):
                    if i >= 4:
                        break
                    
                    row = i // 2
                    col = i % 2
                    
                    if isinstance(path, dict) and path.get('status') == 'loading':
                        label = QLabel("生成中...")
                        label.setStyleSheet("background-color: #E8F5E9; color: #4CAF50; border: 1px dashed #81C784; font-weight: bold; font-family: 'Microsoft YaHei'; font-size: 10px;")
                        label.setAlignment(Qt.AlignCenter)
                        layout.addWidget(label, row, col)
                    elif path and isinstance(path, str) and os.path.exists(path):
                        widget = DraggableVideoWidget(path, director_node=self.director_node)
                        layout.addWidget(widget, row, col)
                    else:
                        label = QLabel("无效")
                        label.setStyleSheet("background-color: #f0f0f0; color: #999; border: 1px dashed #ccc; font-size: 10px;")
                        label.setAlignment(Qt.AlignCenter)
                        layout.addWidget(label, row, col)

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
                
                if index.column() == 6:
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
                
                for item in image_paths:
                    path = item
                    name = ""
                    if isinstance(item, dict):
                        path = item.get("path")
                        name = item.get("name", "")

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
                    
                    # 绘制名字标签
                    if name:
                        painter.save()
                        # 动态计算字体大小
                        font_size = max(8, int(available_height / 15))
                        font = QFont("Microsoft YaHei", font_size)
                        font.setBold(True)
                        painter.setFont(font)
                        fm = QFontMetrics(font)
                        
                        # 限制文字宽度不超过图片宽度
                        elided_name = fm.elidedText(name, Qt.ElideRight, int(scaled.width() - 4))
                        
                        text_rect = fm.boundingRect(elided_name)
                        text_height = text_rect.height() + 4
                        
                        # 背景区域 (底部)
                        bg_rect = QRectF(draw_x, draw_y + scaled.height() - text_height, scaled.width(), text_height)
                        
                        # 半透明背景
                        painter.setBrush(QBrush(QColor(0, 0, 0, 150)))
                        painter.setPen(Qt.NoPen)
                        painter.drawRect(bg_rect)
                        
                        # 文字
                        painter.setPen(QPen(QColor("white")))
                        painter.drawText(bg_rect, Qt.AlignCenter, elided_name)
                        
                        painter.restore()
                    
                    current_x += item_width + spacing
                    
                painter.restore()

            def paint_storyboard(self, painter, option, index):
                image_paths = index.data(Qt.UserRole)
                status = index.data(Qt.UserRole + 2)
                
                raw_paths = image_paths if image_paths and isinstance(image_paths, list) else []
                p1 = raw_paths[0] if len(raw_paths) > 0 else None
                p2 = raw_paths[1] if len(raw_paths) > 1 else None
                
                rect = option.rect
                rect.adjust(5, 5, -5, -5)
                
                painter.save()
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setRenderHint(QPainter.SmoothPixmapTransform)
                
                show_tail_mode = bool(self.node and hasattr(self.node, "show_tail_frame") and self.node.show_tail_frame)
                
                if show_tail_mode:
                    spacing = 4
                    total_w = rect.width()
                    slot_w = (total_w - spacing) / 2.0
                    if slot_w < 10:
                        slot_w = 10
                    
                    rect1 = QRectF(rect.left(), rect.top(), slot_w, rect.height())
                    rect2 = QRectF(rect.left() + slot_w + spacing, rect.top(), slot_w, rect.height())
                    
                    self.draw_slot(painter, rect1, p1, status)
                    self.draw_slot(painter, rect2, p2, status)
                    
                    painter.restore()
                    return
                
                paths = []
                if raw_paths:
                    paths = [p for p in raw_paths if p]
                count = len(paths)
                
                selected_index = index.data(Qt.UserRole + 3)
                if not isinstance(selected_index, int) or selected_index < 0 or selected_index >= count:
                    if count > 0:
                        selected_index = 0
                    else:
                        selected_index = 0
                
                path = paths[selected_index] if 0 <= selected_index < count else None
                main_rect = QRectF(rect.left(), rect.top(), rect.width(), rect.height())
                self.draw_slot(painter, main_rect, path, status)
                
                if count > 0:
                    max_buttons = min(count, 8)
                    btn_h = max(12, int(rect.height() / 8))
                    btn_w = btn_h
                    margin_x = 6
                    margin_y = 6
                    spacing = 4
                    
                    font = QFont("Microsoft YaHei", max(7, int(btn_h * 0.55)))
                    font.setBold(True)
                    painter.setFont(font)
                    
                    for idx in range(max_buttons):
                        row = 0 if idx < 4 else 1
                        col = idx if idx < 4 else idx - 4
                        x = rect.left() + margin_x + col * (btn_w + spacing)
                        y = rect.top() + margin_y + row * (btn_h + spacing)
                        btn_rect = QRectF(x, y, btn_w, btn_h)
                        
                        is_active = (idx == selected_index)
                        
                        bg_color = QColor("#42A5F5") if is_active else QColor(255, 255, 255, 230)
                        border_color = QColor("#1E88E5") if is_active else QColor("#9E9E9E")
                        text_color = QColor("#FFFFFF") if is_active else QColor("#424242")
                        
                        painter.setPen(QPen(border_color, 1.6))
                        painter.setBrush(QBrush(bg_color))
                        painter.drawRoundedRect(btn_rect, 5, 5)
                        
                        painter.setPen(text_color)
                        painter.drawText(btn_rect, Qt.AlignCenter, str(idx + 1))
                    
                    if count > 1:
                        multi_btn_h = max(btn_h, 16)
                        multi_btn_w = max(60, int(rect.width() * 0.5))
                        multi_x = rect.left() + (rect.width() - multi_btn_w) / 2
                        multi_y = rect.bottom() - multi_btn_h - margin_y
                        multi_rect = QRectF(multi_x, multi_y, multi_btn_w, multi_btn_h)
                        
                        painter.setPen(QPen(QColor("#388E3C"), 1.5))
                        painter.setBrush(QBrush(QColor(255, 255, 255, 235)))
                        painter.drawRoundedRect(multi_rect, 6, 6)
                        
                        painter.setPen(QColor("#388E3C"))
                        painter.drawText(multi_rect, Qt.AlignCenter, "多图显示")
                
                painter.restore()

            def draw_slot(self, painter, rect, path, status=None):
                # If loading, draw "生成中"
                if status == "loading":
                    painter.save()
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QBrush(QColor("#FFF3E0"))) # Light orange bg
                    painter.drawRoundedRect(rect, 4, 4)
                    
                    # Draw Text
                    font_size = max(10, int(min(rect.width(), rect.height()) / 6))
                    font = QFont("Microsoft YaHei", font_size)
                    font.setBold(True)
                    painter.setFont(font)
                    painter.setPen(QColor("#FF9800"))
                    painter.drawText(rect, Qt.AlignCenter, "生成中")
                    painter.restore()
                    return

                # If failed, draw "生成失败" in red
                if status == "failed":
                    painter.save()
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QBrush(QColor("#FFEBEE"))) # Light red bg
                    painter.drawRoundedRect(rect, 4, 4)
                    
                    # Draw Text
                    font_size = max(10, int(min(rect.width(), rect.height()) / 6))
                    font = QFont("Microsoft YaHei", font_size)
                    font.setBold(True)
                    painter.setFont(font)
                    painter.setPen(QColor("#F44336")) # Red
                    painter.drawText(rect, Qt.AlignCenter, "生成失败")
                    painter.restore()
                    return

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
                
                # 动态计算图标大小
                icon_size = max(16, int(min(rect.width(), rect.height()) / 5))
                half_size = icon_size / 2
                
                painter.drawLine(QPointF(center.x() - half_size, center.y()), QPointF(center.x() + half_size, center.y()))
                painter.drawLine(QPointF(center.x(), center.y() - half_size), QPointF(center.x(), center.y() + half_size))

            def open_multi_dialog(self, paths, model, index):
                if not paths:
                    return
                selected_index = index.data(Qt.UserRole + 3)
                if not isinstance(selected_index, int) or selected_index < 0 or selected_index >= len(paths):
                    selected_index = 0
                def on_select(idx):
                    model.setData(index, idx, Qt.UserRole + 3)
                dialog = MultiStoryboardDialog(paths, selected_index, parent=None, on_select=on_select)
                dialog.exec()

            def editorEvent(self, event, model, option, index):
                if index.column() == 6 and event.type() == QEvent.MouseButtonPress:
                    if hasattr(event, "button") and event.button() == Qt.LeftButton:
                        self.press_pos = event.pos()
                
                if index.column() == 6 and event.type() == QEvent.MouseButtonRelease:
                    if hasattr(event, "button") and event.button() == Qt.RightButton:
                        return super().editorEvent(event, model, option, index)
                    
                    if hasattr(event, "button") and event.button() == Qt.LeftButton:
                        if self.press_pos is not None:
                            move_distance = (event.pos() - self.press_pos).manhattanLength()
                            if move_distance >= QApplication.startDragDistance():
                                self.press_pos = None
                                return super().editorEvent(event, model, option, index)
                        
                        if self.node:
                            rect = option.rect
                            rect.adjust(5, 5, -5, -5)
                            
                            image_paths = index.data(Qt.UserRole)
                            raw_paths = image_paths if image_paths and isinstance(image_paths, list) else []
                            
                            show_tail_mode = bool(self.node and hasattr(self.node, "show_tail_frame") and self.node.show_tail_frame)
                            if show_tail_mode:
                                pos = event.pos()
                                spacing = 4
                                total_w = rect.width()
                                slot_w = (total_w - spacing) / 2.0
                                if slot_w < 10:
                                    slot_w = 10
                                
                                rect1 = QRectF(rect.left(), rect.top(), slot_w, rect.height())
                                rect2 = QRectF(rect.left() + slot_w + spacing, rect.top(), slot_w, rect.height())
                                
                                slot_index = 0
                                if rect2.contains(pos):
                                    slot_index = 1
                                
                                p = None
                                if len(raw_paths) > slot_index:
                                    p = raw_paths[slot_index]
                                
                                if not (p and os.path.exists(p)):
                                    self.node.upload_storyboard_image(index.row(), slot_index)
                                
                                self.press_pos = None
                                return True
                            
                            paths = []
                            if raw_paths:
                                paths = [p for p in raw_paths if p]
                            count = len(paths)
                            
                            if count > 0:
                                max_buttons = min(count, 8)
                                btn_h = max(12, int(rect.height() / 8))
                                btn_w = btn_h
                                margin_x = 6
                                margin_y = 6
                                spacing = 4
                                
                                pos = event.pos()
                                for idx in range(max_buttons):
                                    row = 0 if idx < 4 else 1
                                    col = idx if idx < 4 else idx - 4
                                    x = rect.left() + margin_x + col * (btn_w + spacing)
                                    y = rect.top() + margin_y + row * (btn_h + spacing)
                                    btn_rect = QRectF(x, y, btn_w, btn_h)
                                    if btn_rect.contains(pos):
                                        model.setData(index, idx, Qt.UserRole + 3)
                                        self.press_pos = None
                                        return True
                                
                                if count > 1:
                                    multi_btn_h = max(btn_h, 16)
                                    multi_btn_w = max(60, int(rect.width() * 0.5))
                                    multi_x = rect.left() + (rect.width() - multi_btn_w) / 2
                                    multi_y = rect.bottom() - multi_btn_h - margin_y
                                    multi_rect = QRectF(multi_x, multi_y, multi_btn_w, multi_btn_h)
                                    if multi_rect.contains(pos):
                                        self.open_multi_dialog(paths, model, index)
                                        self.press_pos = None
                                        return True
                            
                            selected_index = index.data(Qt.UserRole + 3)
                            if not isinstance(selected_index, int) or selected_index < 0 or selected_index >= count:
                                if count >= 2:
                                    show_tail = False
                                    if hasattr(self.node, "show_tail_frame"):
                                        show_tail = self.node.show_tail_frame
                                    selected_index = 1 if show_tail else 0
                                elif count == 1:
                                    selected_index = 0
                                else:
                                    selected_index = 0
                            
                            target_path = paths[selected_index] if 0 <= selected_index < count else None
                            
                            if not (target_path and os.path.exists(target_path)):
                                self.node.upload_storyboard_image(index.row(), selected_index or 0)
                            
                            self.press_pos = None
                            return True
                
                return super().editorEvent(event, model, option, index)

        class VideoDelegate(QStyledItemDelegate):
            """视频列代理，处理绘制和点击播放"""
            def __init__(self, parent=None, node=None):
                super().__init__(parent)
                self.node = node
                self.press_pos = None

            def paint(self, painter, option, index):
                super().paint(painter, option, index)
                
                # 检查加载状态
                status = index.data(Qt.UserRole + 2)
                if status == "loading":
                     painter.save()
                     rect = option.rect
                     painter.setPen(Qt.NoPen)
                     painter.setBrush(QBrush(QColor("#FFF3E0"))) # Light Orange bg
                     painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 4, 4)
                     
                     # 获取文本
                     text = index.data(Qt.DisplayRole)
                     
                     if text:
                         # 如果有文本，沙漏偏上，文本偏下
                         # Draw Hourglass
                         font_size = max(16, int(min(rect.width(), rect.height()) / 2.5))
                         font = QFont("Segoe UI Emoji", font_size)
                         painter.setFont(font)
                         painter.setPen(QColor("#FF9800")) # Orange
                         # 上半部分
                         top_rect = QRect(rect.left(), rect.top(), rect.width(), int(rect.height() * 0.6))
                         painter.drawText(top_rect, Qt.AlignCenter | Qt.AlignBottom, "⏳")
                         
                         # Draw Text
                         font = painter.font() # Reset to default font for text
                         # Use a standard font for text rendering
                         font.setFamily("Microsoft YaHei")
                         font.setPointSize(9)
                         font.setBold(True)
                         painter.setFont(font)
                         painter.setPen(QColor("#4CAF50")) # Green
                         # 下半部分
                         bottom_rect = QRect(rect.left(), rect.top() + int(rect.height() * 0.4), rect.width(), int(rect.height() * 0.6))
                         painter.drawText(bottom_rect, Qt.AlignCenter | Qt.AlignTop, text)
                     else:
                         # Only Hourglass
                         font_size = max(20, int(min(rect.width(), rect.height()) / 2))
                         font = QFont("Segoe UI Emoji", font_size)
                         painter.setFont(font)
                         painter.setPen(QColor("#FF9800")) # Orange
                         painter.drawText(rect, Qt.AlignCenter, "⏳")

                     painter.restore()
                     return

                video_path = index.data(Qt.UserRole)
                if video_path and os.path.exists(video_path):
                    painter.save()
                    rect = option.rect
                    
                    # 绘制按钮背景 (可选)
                    # btn_rect = rect.adjusted(5, 5, -5, -5)
                    # painter.setPen(Qt.NoPen)
                    # painter.setBrush(QColor("#F3E5F5"))
                    # painter.drawRoundedRect(btn_rect, 4, 4)
                    
                    # 绘制文字
                    painter.setPen(Qt.black)
                    font = painter.font()
                    # font.setBold(True)
                    painter.setFont(font)
                    painter.drawText(rect, Qt.AlignCenter, "▶️ 播放")
                    
                    painter.restore()

            def editorEvent(self, event, model, option, index):
                # 记录鼠标按下位置
                if event.type() == QEvent.MouseButtonPress:
                    if event.button() == Qt.LeftButton:
                        self.press_pos = event.pos()
                        return True
                
                # 处理拖拽 - 已移除
                # elif event.type() == QEvent.MouseMove:
                #     if self.press_pos and (event.buttons() & Qt.LeftButton):
                #         if (event.pos() - self.press_pos).manhattanLength() >= QApplication.startDragDistance():
                #             # 移除拖拽逻辑
                #             pass

                # 处理点击
                elif event.type() == QEvent.MouseButtonRelease:
                    if event.button() == Qt.LeftButton and self.press_pos:
                         # 如果没有发生拖拽
                         if (event.pos() - self.press_pos).manhattanLength() < QApplication.startDragDistance():
                            video_path = index.data(Qt.UserRole)
                            if video_path and os.path.exists(video_path):
                                self.play_video(video_path, index.row())
                            self.press_pos = None
                            return True
                
                return super().editorEvent(event, model, option, index)

            def play_video(self, video_path, row=-1):
                """播放视频"""
                if self.node and hasattr(self.node, 'is_fullscreen_mode') and self.node.is_fullscreen_mode:
                    if hasattr(self.node, 'fs_window'):
                        flags = self.node.fs_window.windowFlags()
                        if flags & Qt.WindowStaysOnTopHint:
                            self.node.fs_window.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
                            self.node.fs_window.showFullScreen()
                
                if not os.path.exists(video_path):
                    print(f"[导演节点] 视频文件不存在: {video_path}")
                    return
                
                try:
                    existing = getattr(self.node, "cinema_player_window", None) if self.node else None
                    if existing and existing.isVisible():
                        existing.close()
                except Exception:
                    pass
                
                try:
                    if self.node is not None:
                        self.node.cinema_player_window = DirectorVideoPlayer(video_path)
                        self.node.cinema_player_window.show()
                    else:
                        window = DirectorVideoPlayer(video_path)
                        window.show()
                    print(f"[导演节点] 使用内置播放器播放视频: {video_path}")
                except Exception as e:
                    print(f"[导演节点] 使用内置播放器播放视频失败: {e}")

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
                            if col in [3, 4, 5, 6]:
                                image_paths = item.data(Qt.UserRole)
                                if image_paths and isinstance(image_paths, list) and image_paths:
                                    if col == 6:
                                        selected_index = item.data(Qt.UserRole + 3)
                                        if not isinstance(selected_index, int) or selected_index < 0 or selected_index >= len(image_paths):
                                            selected_index = 0
                                        path = image_paths[selected_index]
                                        if isinstance(path, dict):
                                            path = path.get("path")
                                        self.hover_callback(path, event.pos())
                                    else:
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
                                            if isinstance(path, dict):
                                                path = path.get("path")
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
                # 3:人物, 4:道具, 5:场景, 6:分镜图
                if col not in [3, 4, 5, 6]: return
                
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
                    if isinstance(image_path, dict):
                        image_path = image_path.get("path")
                    
                    if not image_path:
                        return

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
                # 分配唯一节点ID
                DirectorNode._node_counter += 1
                self.node_id = DirectorNode._node_counter
                
                # 节点初始化: x, y, width, height, title, icon
                # Icon can be None or a custom SVG path
                super().__init__(x, y, 1050, 600, f"导演节点 #{self.node_id}", None)
                
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
                
                # 视频生成数量设置
                settings = QSettings("GhostOS", "App")
                self.video_gen_count = int(settings.value("director/video_gen_count", 1))
                # 批量分镜数量设置
                self.storyboard_batch_count = int(settings.value("director/storyboard_batch_count", 1))
                
                # 人物检测设置 (默认开启)
                self.char_detection_enabled = settings.value("director/char_detection_enabled", "true") == "true"
                # 剧本时间优化设置 (默认关闭)
                self.script_time_optimization_enabled = settings.value("director/script_time_optimization_enabled", "false") == "true"
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
                
                # 定时刷新数据
                self.timer = QTimer()
                self.timer.timeout.connect(self.update_data)
                self.timer.start(1000) # 每秒刷新一次
                
                # 加载分镜图路径缓存
                self.storyboard_paths = self.load_storyboard_paths()
                self.props_paths = self.load_props_paths()
                self.scene_paths = self.load_scene_paths()
                # 加载道具提示词缓存
                self.props_prompts = self.load_props_prompts()
                # 加载视频路径缓存
                self.video_paths = self.load_video_paths()
                # 加载视频元数据缓存
                self.video_metadata = self.load_video_metadata()
                
                # 加载手动编辑的动画片场缓存
                self.manual_studio_edits = self.load_manual_studio_edits()
                
                # 加载手动编辑的图片提示词缓存
                self.manual_image_prompts = self.load_manual_image_prompts()
                
                # 加载手动编辑的视频提示词缓存
                self.manual_video_prompts = self.load_manual_video_prompts()
                
                # 加载忽略的镜头缓存
                self.ignored_shots = self.load_ignored_shots()
                # 加载已删除人物缓存
                self.ignored_characters = self.load_ignored_characters()
                
                # 初始化Sora人物@模式管理器
                self.sora_mapping_manager = SoraCharacterMappingManager(self.node_id)
                
                # 加载视图设置
                self.load_view_settings()
                
                # 视频生成 Workers 列表 (支持并发)
                self.sora_workers = []
                
                # 分镜图生成 Workers 列表 (防止GC回收导致崩溃)
                self.storyboard_workers = []
                
                # 标记初始化状态，防止启动时重置数据
                self.is_initialized = False
                QTimer.singleShot(3000, lambda: setattr(self, 'is_initialized', True))

            def itemChange(self, change, value):
                if change == QGraphicsItem.ItemSceneHasChanged and value is None:
                     self.cleanup_workers()
                return super().itemChange(change, value)

            def cleanup_workers(self):
                """清理所有后台线程"""
                # Stop Storyboard Workers
                if hasattr(self, 'storyboard_workers'):
                    for worker in list(self.storyboard_workers):
                        try:
                            worker.running = False
                            if hasattr(worker, 'requestInterruption'):
                                worker.requestInterruption()
                            worker.quit()
                            worker.wait(100) # Wait briefly
                        except Exception as e:
                            print(f"[DirectorNode] Error cleaning up storyboard worker: {e}")
                    self.storyboard_workers.clear()
                
                # Stop Sora Workers
                if hasattr(self, 'sora_workers'):
                    for worker in list(self.sora_workers):
                        try:
                             if hasattr(worker, 'requestInterruption'):
                                worker.requestInterruption()
                             worker.quit()
                             worker.wait(100)
                        except Exception as e:
                             print(f"[DirectorNode] Error cleaning up sora worker: {e}")
                    self.sora_workers.clear()

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

                # 如果是输入接口连接 (通常是剧本数据)
                if socket.socket_type == SocketType.INPUT:
                    print(f"[DEBUG] Input socket connected. Refreshing data...")
                    
                    # 检查是否是谷歌剧本节点
                    if hasattr(target_node, 'node_title') and "谷歌剧本" in target_node.node_title:
                        # 只有在初始化完成后（即用户手动操作时）才重置数据
                        # 启动时的自动连接不应重置数据
                        if hasattr(self, 'is_initialized') and self.is_initialized:
                            print(f"[DEBUG] Connected to Google Script Node. Resetting Studio Edits...")
                            # 清空手动编辑缓存，以便重新加载原始剧本数据
                            self.manual_studio_edits = {}
                            
                            self.save_manual_studio_edits()
                        else:
                            print(f"[DEBUG] Connected to Google Script Node during initialization. Keeping existing Studio Edits.")
                    
                    # 延时一点时间确保连接完全建立
                    QTimer.singleShot(100, self.update_data)

                # 只有当视频输出接口连接时才处理
                if socket.data_type == DataType.VIDEO and socket.socket_type == SocketType.OUTPUT:
                    print(f"[DEBUG] Video output socket connected.")
                    print(f"[DEBUG] Director Node will NOT send data. Video Editor Node should read JSON directly.")
                    # 彻底移除此处的数据加载和发送逻辑，完全由接收端处理

            def load_view_settings(self):
                """加载视图设置 (JSON)"""
                try:
                    path = os.path.join(os.getcwd(), 'JSON', f'daoyan_view_settings_{self.node_id}.json')
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            settings = json.load(f)
                            
                        # 应用设置
                        # 1. 动画片场 (Index 2)
                        anime_visible = settings.get("anime_visible", False)
                        # 默认是隐藏的，如果记录为 True 则显示
                        # 注意: self.table 可能还未完全初始化，但 setColumnHidden 可以工作
                        # 默认情况: 初始代码中 anime_btn 显示 "📺 动画片场" (意味着隐藏)
                        # 我们需要在数据加载后再次确认列状态，但这里可以先设置 flag 或直接操作 table
                        
                        if anime_visible:
                            # 模拟点击展开，或直接设置
                            self.table.setColumnHidden(2, False)
                            if hasattr(self, 'anime_btn'):
                                self.anime_btn.setText("隐藏动画片场")
                                self.anime_btn.setStyleSheet(self.anime_btn.styleSheet().replace("#AB47BC", "#7B1FA2"))
                        else:
                            self.table.setColumnHidden(2, True)
                            if hasattr(self, 'anime_btn'):
                                self.anime_btn.setText("📺 动画片场")
                                self.anime_btn.setStyleSheet(self.anime_btn.styleSheet().replace("#7B1FA2", "#AB47BC"))
                        
                        # 2. 图片提示词 (Index 7)
                        # 这个列是动态添加的，所以我们需要调用 toggle_image_prompt_column 的逻辑
                        img_prompt_visible = settings.get("image_prompt_visible", False)
                        
                        # 延迟一点执行，确保 toggle_image_prompt_column 可用且 UI 就绪
                        if img_prompt_visible:
                            QTimer.singleShot(500, lambda: self.restore_image_prompt_column())
                            
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error loading view settings: {e}")

            def restore_image_prompt_column(self):
                """恢复图片提示词列显示"""
                try:
                    # 只有当它是隐藏的时候才切换（变为显示）
                    # 检查列是否存在
                    if self.table.columnCount() <= 7 or self.table.isColumnHidden(7):
                        toggle_image_prompt_column(self)
                except Exception as e:
                    print(f"Error restoring image prompt column: {e}")

            def save_view_settings(self):
                """保存视图设置 (JSON)"""
                try:
                    dir_path = os.path.join(os.getcwd(), 'JSON')
                    os.makedirs(dir_path, exist_ok=True)
                    path = os.path.join(dir_path, f'daoyan_view_settings_{self.node_id}.json')
                    
                    settings = {}
                    # 1. 动画片场
                    settings["anime_visible"] = not self.table.isColumnHidden(2)
                    
                    # 2. 图片提示词
                    # 检查列是否存在且显示
                    is_img_prompt_visible = False
                    if self.table.columnCount() > 7:
                        is_img_prompt_visible = not self.table.isColumnHidden(7)
                    settings["image_prompt_visible"] = is_img_prompt_visible
                    
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(settings, f, ensure_ascii=False, indent=2)
                        
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error saving view settings: {e}")

            def load_storyboard_paths(self):
                """加载分镜图路径缓存"""
                try:
                    path = os.path.join(os.getcwd(), 'JSON', f'daoyan_fenjing_paths_{self.node_id}.json')
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            return json.load(f)
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error loading storyboard paths: {e}")
                return {}

            def save_storyboard_paths(self):
                """保存分镜图路径缓存"""
                try:
                    dir_path = os.path.join(os.getcwd(), 'JSON')
                    os.makedirs(dir_path, exist_ok=True)
                    path = os.path.join(dir_path, f'daoyan_fenjing_paths_{self.node_id}.json')
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(self.storyboard_paths, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error saving storyboard paths: {e}")

            def load_props_paths(self):
                try:
                    path = os.path.join(os.getcwd(), 'JSON', f'daoyan_props_paths_{self.node_id}.json')
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            return json.load(f)
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error loading props paths: {e}")
                return {}

            def save_props_paths(self):
                try:
                    dir_path = os.path.join(os.getcwd(), 'JSON')
                    os.makedirs(dir_path, exist_ok=True)
                    path = os.path.join(dir_path, f'daoyan_props_paths_{self.node_id}.json')
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(self.props_paths, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error saving props paths: {e}")

            def load_scene_paths(self):
                try:
                    path = os.path.join(os.getcwd(), 'JSON', f'daoyan_scene_paths_{self.node_id}.json')
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            return json.load(f)
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error loading scene paths: {e}")
                return {}

            def save_scene_paths(self):
                try:
                    dir_path = os.path.join(os.getcwd(), 'JSON')
                    os.makedirs(dir_path, exist_ok=True)
                    path = os.path.join(dir_path, f'daoyan_scene_paths_{self.node_id}.json')
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(self.scene_paths, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error saving scene paths: {e}")

            def load_props_prompts(self):
                """加载道具提示词缓存"""
                try:
                    path = os.path.join(os.getcwd(), 'JSON', f'daoyan_props_prompts_{self.node_id}.json')
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            return json.load(f)
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error loading props prompts: {e}")
                return {}

            def save_props_prompts(self):
                """保存道具提示词缓存"""
                try:
                    dir_path = os.path.join(os.getcwd(), 'JSON')
                    os.makedirs(dir_path, exist_ok=True)
                    path = os.path.join(dir_path, f'daoyan_props_prompts_{self.node_id}.json')
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(self.props_prompts, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error saving props prompts: {e}")

            def load_video_paths(self):
                """加载视频路径缓存"""
                try:
                    path = os.path.join(os.getcwd(), 'JSON', f'daoyan_TV_VIDEO_SAVE_{self.node_id}.JSON')
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            # Normalize data to ensure all values are lists
                            normalized_data = {}
                            for k, v in data.items():
                                if isinstance(v, list):
                                    normalized_data[k] = v
                                elif isinstance(v, str):
                                    normalized_data[k] = [v]
                                else:
                                    normalized_data[k] = []
                            
                            print(f"[节点#{self.node_id}] Loaded {len(normalized_data)} video paths from {path}")
                            return normalized_data
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error loading video paths: {e}")
                return {}

            def save_video_paths(self):
                """保存视频路径缓存"""
                try:
                    dir_path = os.path.join(os.getcwd(), 'JSON')
                    print(f"[节点#{self.node_id}] Saving video paths to dir: {dir_path}")
                    os.makedirs(dir_path, exist_ok=True)
                    path = os.path.join(dir_path, f'daoyan_TV_VIDEO_SAVE_{self.node_id}.JSON')
                    print(f"[节点#{self.node_id}] Full save path: {path}")
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(self.video_paths, f, ensure_ascii=False, indent=2)
                    print(f"[节点#{self.node_id}] Successfully saved {len(self.video_paths)} entries to {path}")
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error saving video paths: {e}")

            def load_video_metadata(self):
                """加载视频元数据(URL, TaskID)"""
                try:
                    path = os.path.join(os.getcwd(), 'JSON', f'daoyan_TV_VIDEO_METADATA_{self.node_id}.JSON')
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            return json.load(f)
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error loading video metadata: {e}")
                return {}

            def save_video_metadata(self):
                """保存视频元数据"""
                try:
                    dir_path = os.path.join(os.getcwd(), 'JSON')
                    os.makedirs(dir_path, exist_ok=True)
                    path = os.path.join(dir_path, f'daoyan_TV_VIDEO_METADATA_{self.node_id}.JSON')
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(self.video_metadata, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error saving video metadata: {e}")
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(self.video_metadata, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"Error saving video metadata: {e}")

            def load_manual_studio_edits(self):
                """加载手动编辑的动画片场内容"""
                try:
                    path = os.path.join(os.getcwd(), 'JSON', f'daoyan_manual_edits_{self.node_id}.json')
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            return json.load(f)
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error loading manual studio edits: {e}")
                return {}

            def load_manual_image_prompts(self):
                """加载手动编辑的图片提示词缓存"""
                try:
                    path = os.path.join(os.getcwd(), 'JSON', f'daoyan_manual_image_prompts_{self.node_id}.json')
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            return json.load(f)
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error loading manual image prompts: {e}")
                return {}

            def save_manual_studio_edits(self):
                """保存手动编辑的动画片场内容"""
                try:
                    dir_path = os.path.join(os.getcwd(), 'JSON')
                    os.makedirs(dir_path, exist_ok=True)
                    path = os.path.join(dir_path, f'daoyan_manual_edits_{self.node_id}.json')
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(self.manual_studio_edits, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error saving manual studio edits: {e}")

            def save_manual_image_prompts(self):
                """保存手动编辑的图片提示词缓存"""
                try:
                    dir_path = os.path.join(os.getcwd(), 'JSON')
                    os.makedirs(dir_path, exist_ok=True)
                    path = os.path.join(dir_path, f'daoyan_manual_image_prompts_{self.node_id}.json')
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(self.manual_image_prompts, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error saving manual image prompts: {e}")

            def load_manual_video_prompts(self):
                """加载手动编辑的视频提示词缓存"""
                try:
                    path = os.path.join(os.getcwd(), 'JSON', f'daoyan_manual_video_prompts_{self.node_id}.json')
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            return json.load(f)
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error loading manual video prompts: {e}")
                return {}

            def save_manual_video_prompts(self):
                """保存手动编辑的视频提示词缓存"""
                try:
                    dir_path = os.path.join(os.getcwd(), 'JSON')
                    os.makedirs(dir_path, exist_ok=True)
                    path = os.path.join(dir_path, f'daoyan_manual_video_prompts_{self.node_id}.json')
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(self.manual_video_prompts, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error saving manual video prompts: {e}")

            def load_ignored_shots(self):
                """加载被忽略的镜头号"""
                try:
                    path = os.path.join(os.getcwd(), 'JSON', f'daoyan_ignored_shots_{self.node_id}.json')
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            return set(json.load(f))
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error loading ignored shots: {e}")
                return set()

            def save_ignored_shots(self):
                """保存被忽略的镜头号"""
                try:
                    dir_path = os.path.join(os.getcwd(), 'JSON')
                    os.makedirs(dir_path, exist_ok=True)
                    path = os.path.join(dir_path, f'daoyan_ignored_shots_{self.node_id}.json')
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(list(self.ignored_shots), f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error saving ignored shots: {e}")

            def load_ignored_characters(self):
                """加载已删除人物缓存"""
                try:
                    path = os.path.join(os.getcwd(), 'JSON', f'daoyan_ignored_characters_{self.node_id}.json')
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            raw = json.load(f)
                            result = {}
                            if isinstance(raw, dict):
                                for k, v in raw.items():
                                    if isinstance(v, list):
                                        result[str(k)] = set(str(x) for x in v)
                            return result
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error loading ignored characters: {e}")
                return {}

            def save_ignored_characters(self):
                """保存已删除人物缓存"""
                try:
                    dir_path = os.path.join(os.getcwd(), 'JSON')
                    os.makedirs(dir_path, exist_ok=True)
                    path = os.path.join(dir_path, f'daoyan_ignored_characters_{self.node_id}.json')
                    data = {}
                    if hasattr(self, 'ignored_characters') and isinstance(self.ignored_characters, dict):
                        for k, v in self.ignored_characters.items():
                            if isinstance(v, set):
                                data[str(k)] = sorted(list(v))
                            elif isinstance(v, list):
                                data[str(k)] = [str(x) for x in v]
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"[节点#{self.node_id}] Error saving ignored characters: {e}")

            def clear_ignored_character(self, shot_num, name):
                """清除指定镜头下已删除人物标记"""
                if not shot_num or not name:
                    return
                if not hasattr(self, 'ignored_characters') or not isinstance(self.ignored_characters, dict):
                    return
                entry = self.ignored_characters.get(shot_num)
                if not entry:
                    return
                changed = False
                if isinstance(entry, set):
                    if name in entry:
                        entry.discard(name)
                        changed = True
                elif isinstance(entry, list):
                    new_list = [x for x in entry if x != name]
                    if len(new_list) != len(entry):
                        self.ignored_characters[shot_num] = new_list
                        changed = True
                if changed:
                    self.save_ignored_characters()

            def delete_rows(self, rows):
                """删除指定的多行并添加到忽略列表"""
                if not rows:
                    return

                # 获取所有行的镜头号
                shot_nums = []
                for r in rows:
                    item_shot = self.table.item(r, 0)
                    if item_shot and item_shot.text():
                        shot_nums.append(item_shot.text())
                
                if not shot_nums:
                    return
                
                # 去重
                shot_nums = list(set(shot_nums))

                reply = QMessageBox.question(
                    None,
                    "确认删除",
                    f"确定要隐藏选中的 {len(shot_nums)} 个镜头吗？\n{', '.join(shot_nums[:5])}{'...' if len(shot_nums) > 5 else ''}\n(这将把它们添加到忽略列表，不再显示，但数据会保留)",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    for shot_num in shot_nums:
                        self.ignored_shots.add(shot_num)
                        
                        # 注释掉清除缓存的操作，以便恢复时可以找回数据
                        # if shot_num in self.storyboard_paths:
                        #     del self.storyboard_paths[shot_num]
                        # if shot_num in self.props_paths:
                        #     del self.props_paths[shot_num]
                        # if hasattr(self, 'props_prompts') and shot_num in self.props_prompts:
                        #      del self.props_prompts[shot_num]
                        # if shot_num in self.video_paths:
                        #     del self.video_paths[shot_num]
                        # if hasattr(self, 'video_metadata') and shot_num in self.video_metadata:
                        #     del self.video_metadata[shot_num]
                        # if shot_num in self.manual_studio_edits:
                        #     del self.manual_studio_edits[shot_num]
                        # if hasattr(self, 'manual_video_prompts') and shot_num in self.manual_video_prompts:
                        #     del self.manual_video_prompts[shot_num]
                    
                    # 批量保存
                    self.save_ignored_shots()
                    self.save_storyboard_paths()
                    self.save_props_paths()
                    if hasattr(self, 'props_prompts'): self.save_props_prompts()
                    self.save_video_paths()
                    if hasattr(self, 'video_metadata'): self.save_video_metadata()
                    self.save_manual_studio_edits()
                    if hasattr(self, 'manual_video_prompts'): self.save_manual_video_prompts()
                    
                    # 立即刷新
                    self.update_data()
                    print(f"[导演节点] 已忽略镜头 {shot_nums} 并清除缓存")

            def setup_ui(self):
                """设置节点内部UI"""
                self.proxy_widget = QGraphicsProxyWidget(self)
                self.proxy_widget.setZValue(10)
                
                self.container = QWidget()
                self.container.setStyleSheet("background-color: transparent;")
                self.layout = QVBoxLayout(self.container)
                self.layout.setContentsMargins(10, 45, 10, 10)
                
                # 状态标签 (用于显示自动追踪进度等)
                self.status_label = QLabel("")
                self.status_label.setStyleSheet("""
                    QLabel {
                        color: #D81B60;
                        font-size: 12px;
                        font-weight: bold;
                        margin-top: 5px;
                    }
                """)
                self.status_label.setVisible(False) # 默认隐藏
                # self.layout.addWidget(self.status_label) # Moved to bottom

                # 动漫按钮
                self.anime_btn = QPushButton("📺 动画片场", self.container)
                self.anime_btn.setFixedSize(110, 24)
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

                # 附加提示词按钮
                self.add_prompt_btn = QPushButton("➕ 附加视频提示词", self.container)
                self.add_prompt_btn.setFixedSize(120, 24)
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
                self.add_image_prompt_btn.setFixedSize(120, 24)
                self.add_image_prompt_btn.setCursor(Qt.PointingHandCursor)
                self.add_image_prompt_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #E91E63;
                        color: white;
                        border-radius: 4px;
                        font-weight: bold;
                        border: none;
                        font-family: "Microsoft YaHei";
                    }
                    QPushButton:hover {
                        background-color: #F06292;
                    }
                    QPushButton:pressed {
                        background-color: #C2185B;
                    }
                """)
                self.add_image_prompt_btn.clicked.connect(lambda: open_additional_image_prompt_dialog(None))

                # 展开图片提示词按钮
                self.expand_prompt_btn = create_expand_button(self)

                self.optimization_btn = QPushButton("🚀 剧本优化", self.container)
                self.optimization_btn.setFixedSize(110, 24)
                self.optimization_btn.setCursor(Qt.PointingHandCursor)
                self.optimization_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #3949AB;
                        color: #FFFFFF;
                        border-radius: 4px;
                        font-weight: bold;
                        border: none;
                        font-family: "Microsoft YaHei";
                    }
                    QPushButton:hover {
                        background-color: #5C6BC0;
                    }
                    QPushButton:pressed {
                        background-color: #283593;
                    }
                    QPushButton:disabled {
                        background-color: #9FA8DA;
                        color: #ECEFF1;
                    }
                """)
                self.optimization_btn.clicked.connect(self.on_optimization_clicked)

                # 设置按钮
                self.setting_btn = QPushButton("⚙️ 设置", self.container)
                self.setting_btn.setFixedSize(80, 24)
                self.setting_btn.setCursor(Qt.PointingHandCursor)
                self.setting_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #607D8B;
                        color: white;
                        border-radius: 4px;
                        font-weight: bold;
                        border: none;
                        font-family: "Microsoft YaHei";
                    }
                    QPushButton:hover {
                        background-color: #78909C;
                    }
                    QPushButton:pressed {
                        background-color: #455A64;
                    }
                """)
                self.setting_btn.clicked.connect(self.on_setting_clicked)

                # 全屏按钮
                self.fullscreen_btn = QPushButton("🗖 全屏", self.container)
                self.fullscreen_btn.setFixedSize(100, 24)
                self.fullscreen_btn.setCursor(Qt.PointingHandCursor)
                self.fullscreen_btn.setToolTip("全屏显示 / 恢复")
                self.fullscreen_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #607D8B;
                        color: white;
                        border-radius: 4px;
                        font-weight: bold;
                        border: none;
                        font-family: "Microsoft YaHei";
                        font-size: 14px;
                    }
                    QPushButton:hover {
                        background-color: #78909C;
                    }
                    QPushButton:pressed {
                        background-color: #455A64;
                    }
                """)
                self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)

                # 表格
                self.table = HoverTableWidget()
                self.table.hover_callback = self.update_preview # 绑定回调
                # 默认10列: 镜头号, 时间码, 动画片场, 人物, 道具, 场景, 分镜图, 图片提示词, 附加视频提示词, 电影院
                self.table.setColumnCount(10)
                self.table.setHorizontalHeaderLabels(["🎬 镜头号", "⏱ 时间码", "📺 动画片场", "👤 人物", "🛠️ 道具", "🏞️ 场景", "🖼️ 分镜图 🔴", "🎨 图片提示词", "📹 附加视频提示词", "🎥 电影院"])
                
                # 连接表头点击信号
                self.table.horizontalHeader().sectionClicked.connect(self.on_header_clicked)
                
                # 连接单元格修改信号 (用于捕获手动编辑)
                self.table.cellChanged.connect(self.on_cell_changed)
                
                # 默认隐藏"动画片场"列 和 "图片提示词"列 和 "附加视频提示词"列
                self.table.setColumnHidden(2, True)
                self.table.setColumnHidden(7, True)
                self.table.setColumnHidden(8, True)
                
                # 隐藏垂直表头
                self.table.verticalHeader().setVisible(False)
                # 交替行颜色
                self.table.setAlternatingRowColors(True)
                
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
                        width: 30px;
                        margin: 0px 0px 0px 0px;
                        border-radius: 15px;
                    }
                    QScrollBar::handle:vertical {
                        background: #CE93D8;
                        min-height: 30px;
                        border-radius: 15px;
                    }
                    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                        height: 0px;
                        width: 0px;
                    }
                """)
                
                self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
                self.table.horizontalHeader().setStretchLastSection(True)
                self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
                
                # 设置初始列宽
                self.table.setColumnWidth(0, 80)   # 镜头号 (放大)
                self.table.setColumnWidth(1, 140)  # 时间码 (放大)
                self.table.setColumnWidth(2, 350)  # 动画片场 (放大)
                self.table.setColumnWidth(3, 150)  # 人物 (放大)
                self.table.setColumnWidth(4, 150)  # 道具 (放大)
                self.table.setColumnWidth(5, 150)  # 场景 (放大)
                self.table.setColumnWidth(6, 180)  # 分镜图 (放大)
                self.table.setColumnWidth(7, 250)  # 图片提示词 (放大)
                self.table.setColumnWidth(8, 250)  # 附加视频提示词
                self.table.setColumnWidth(9, 200)  # 电影院
                
                # 设置图片列的代理
                self.table.setItemDelegateForColumn(3, ImageDelegate(self.table))
                self.table.setItemDelegateForColumn(4, ImageDelegate(self.table)) # 道具
                self.table.setItemDelegateForColumn(5, ImageDelegate(self.table)) # 场景
                self.table.setItemDelegateForColumn(6, ImageDelegate(self.table, node=self)) # 分镜图
                
                # 连接双击信号
                self.table.cellDoubleClicked.connect(self.on_cell_double_click)
                
                # 设置上下文菜单
                self.table.setContextMenuPolicy(Qt.CustomContextMenu)
                self.table.customContextMenuRequested.connect(self.on_table_context_menu)
                
                self.layout.addWidget(self.status_label) # Add status label at the top (below buttons)
                self.layout.addWidget(self.table)
                # self.layout.addWidget(self.status_label) # Moved to top
                
                self.proxy_widget.setWidget(self.container)
                self.proxy_widget.setGeometry(self.boundingRect())
                
            def update_auto_track_status(self, msg):
                """更新自动追踪状态显示"""
                if hasattr(self, 'status_label'):
                    self.status_label.setText(msg)
                    self.status_label.setVisible(True)
                    # 如果消息包含"完成"，3秒后隐藏
                    if "完成" in msg:
                        QTimer.singleShot(3000, lambda: self.status_label.setVisible(False))
            
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
                        # 获取编辑前的文本
                        old_text = item.text()
                        
                        # 打开编辑对话框
                        open_edit_dialog_for_item(item, None) # 传入None避免被遮挡
                        
                        # 检查文本是否发生变化
                        new_text = item.text()
                        if new_text != old_text:
                            # 获取当前镜头号
                            item_shot = self.table.item(row, 0)
                            shot_num = item_shot.text() if item_shot else str(row + 1)
                            
                            # 保存到缓存和文件
                            if shot_num:
                                self.manual_studio_edits[shot_num] = new_text
                                self.save_manual_studio_edits()
                                print(f"[导演节点] 已保存镜头 {shot_num} 的动画片场手动修改")
                
                # 道具 (index 4) - 编辑道具提示词
                elif column == 4:
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

                # 场景 (index 5) - 编辑地点节点提示词
                elif column == 5:
                    # 获取场景名称
                    item = self.table.item(row, column)
                    scene_name = item.text().strip() if item else ""
                    
                    if not scene_name:
                        return

                    # 查找对应的地点节点
                    target_widget = None
                    
                    # 遍历场景中的所有节点
                    if hasattr(self, 'scene') and self.scene():
                        items = self.scene().items()
                        for node in items:
                            if hasattr(node, 'node_title') and ("地点" in node.node_title or "环境" in node.node_title):
                                if hasattr(node, 'proxy_widget') and node.proxy_widget.widget():
                                    # 查找该节点下的行组件
                                    widgets = node.proxy_widget.widget().findChildren(QWidget)
                                    for child in widgets:
                                        if hasattr(child, 'get_data') and callable(child.get_data):
                                            try:
                                                data = child.get_data()
                                                if data.get('name', '').strip() == scene_name:
                                                    target_widget = child
                                                    break
                                            except:
                                                pass
                            if target_widget:
                                break
                    
                    if target_widget:
                        # 获取当前提示词
                        current_data = target_widget.get_data()
                        current_prompt = current_data.get('prompt', '')
                        
                        # 打开编辑对话框
                        dialog = TextEditDialog(current_prompt, None)
                        dialog.setWindowTitle(f"编辑地点提示词 - {scene_name}")
                        if dialog.exec():
                            new_prompt = dialog.get_text()
                            # 更新地点节点
                            if hasattr(target_widget, 'set_data'):
                                target_widget.set_data(
                                    current_data.get('name'),
                                    new_prompt,
                                    current_data.get('image'),
                                    current_data.get('overlay'),
                                    current_data.get('is_active')
                                )
                                print(f"[导演节点] 已更新地点 '{scene_name}' 的提示词")
                    else:
                        print(f"[导演节点] 未找到名称为 '{scene_name}' 的地点节点")

                # 图片提示词 (index 7) - 编辑图片提示词
                elif column == 7:
                    item = self.table.item(row, column)
                    if item:
                        old_text = item.text()
                        
                        # 打开编辑对话框
                        dialog = TextEditDialog(old_text, None)
                        dialog.setWindowTitle(f"编辑图片提示词 - 镜头 {row + 1}")
                        
                        if dialog.exec():
                            new_text = dialog.get_text()
                            if new_text != old_text:
                                item.setText(new_text)
                                
                                # 获取当前镜头号
                                item_shot = self.table.item(row, 0)
                                shot_num = item_shot.text() if item_shot else str(row + 1)
                                
                                # 保存到缓存
                                if shot_num:
                                    self.manual_image_prompts[shot_num] = new_text
                                    self.save_manual_image_prompts()
                                    print(f"[导演节点] 已保存镜头 {shot_num} 的图片提示词手动修改")
                    
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
                        if not hasattr(app, '_active_prop_prompt_workers'):
                            app._active_prop_prompt_workers = []
                        app._active_prop_prompt_workers.append(self)
                    self.finished.connect(self._cleanup_worker)

                def _cleanup_worker(self):
                    """清理 worker 引用"""
                    from PySide6.QtWidgets import QApplication
                    app = QApplication.instance()
                    if app and hasattr(app, '_active_prop_prompt_workers'):
                        if self in app._active_prop_prompt_workers:
                            app._active_prop_prompt_workers.remove(self)
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
                    item_prop = self.table.item(row, 4)
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
                    
                    # 更新表格显示
                    self.set_cell_images(row, 4, [file_path])
                    print(f"[导演节点] 上传镜头 {shot_num} 的道具图片: {file_path}")

            def upload_character_image(self, row):
                """上传人物图片"""
                # 获取当前镜头号
                item_shot = self.table.item(row, 0)
                shot_num = item_shot.text() if item_shot else str(row + 1)
                
                # 打开文件选择对话框
                file_path, _ = QFileDialog.getOpenFileName(
                    self.proxy_widget.widget() if hasattr(self, 'proxy_widget') else None,
                    "选择人物图片",
                    "",
                    "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
                )
                
                if file_path:
                    # 默认使用文件名作为人物名称
                    name = os.path.splitext(os.path.basename(file_path))[0]
                    
                    # 构造数据 - 替换现有内容
                    new_data = [{
                        "name": name,
                        "path": file_path
                    }]
                    
                    # 更新表格显示
                    self.set_cell_images(row, 3, new_data)
                    self.clear_ignored_character(shot_num, name)
                    print(f"[导演节点] 上传镜头 {shot_num} 的人物图片: {file_path}")
                
            def delete_character_image(self, row, index=None):
                """删除指定位置的人物图片，如果index为None则清空"""
                item_shot = self.table.item(row, 0)
                shot_num = item_shot.text().strip() if item_shot and item_shot.text() else str(row + 1)
                if not hasattr(self, 'ignored_characters') or not isinstance(self.ignored_characters, dict):
                    self.ignored_characters = {}
                item = self.table.item(row, 3)
                data = item.data(Qt.UserRole) if item else None
                if index is None:
                    names = []
                    if data and isinstance(data, list):
                        for entry in data:
                            if isinstance(entry, dict):
                                n = entry.get("name")
                                if n:
                                    names.append(str(n))
                    if shot_num and names:
                        current = self.ignored_characters.get(shot_num)
                        if isinstance(current, set):
                            current.update(names)
                        elif isinstance(current, list):
                            s = set(str(x) for x in current)
                            s.update(names)
                            current = s
                        else:
                            current = set(names)
                        self.ignored_characters[shot_num] = current
                        self.save_ignored_characters()
                    self.set_cell_images(row, 3, [])
                    return
                if not item or not data or not isinstance(data, list):
                    return
                removed_name = None
                if 0 <= index < len(data):
                    entry = data[index]
                    if isinstance(entry, dict):
                        removed_name = entry.get("name")
                    data.pop(index)
                    if shot_num and removed_name:
                        current = self.ignored_characters.get(shot_num)
                        if isinstance(current, set):
                            current.add(str(removed_name))
                        elif isinstance(current, list):
                            current = set(str(x) for x in current)
                            current.add(str(removed_name))
                        else:
                            current = {str(removed_name)}
                        self.ignored_characters[shot_num] = current
                        self.save_ignored_characters()
                    self.set_cell_images(row, 3, data)

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
                    QMessageBox.warning(None, "提示", "连接无效或源节点未找到！")
                    return
                    
                source_node = connection.source_socket.parent_node
                
                # 检查是否是谷歌剧本节点 (通过标题判断)
                if hasattr(source_node, 'node_title') and "谷歌剧本" in source_node.node_title:
                    self.read_google_script_data(source_node)
                else:
                    self.table.setRowCount(0)

            def setRect(self, *args):
                """重写setRect以在大小改变时更新内部控件"""
                super().setRect(*args)
                if hasattr(self, 'proxy_widget'):
                    self.proxy_widget.setGeometry(self.boundingRect())
                
                self.update_button_positions(self.rect().width())

                # 动态调整行高和列宽以适应大小
                self.adjust_layout_to_size()

            def update_button_positions(self, width):
                """更新顶部按钮位置"""
                # 重新计算按钮位置以避免重叠 (从右向左排列)
                # Fullscreen: width - 110 (w=100)
                # Anime: width - 230 (w=110) -> Gap 10px
                # Expand Prompt: width - 360 (w=120) -> Gap 10px
                # Storyboard: width - 470 (w=100) -> Gap 10px
                # Sora: width - 580 (w=100) -> Gap 10px
                # Add Prompt: width - 710 (w=120) -> Gap 10px
                # Add Image Prompt: width - 840 (w=120) -> Gap 10px

                if hasattr(self, 'fullscreen_btn'):
                    self.fullscreen_btn.move(width - 110, 8)

                if hasattr(self, 'anime_btn'):
                    self.anime_btn.move(width - 230, 8)
                
                if hasattr(self, 'expand_prompt_btn'):
                    self.expand_prompt_btn.move(width - 360, 8)

                if hasattr(self, 'storyboard_btn'):
                    self.storyboard_btn.move(width - 470, 8)
                
                if hasattr(self, 'sora_btn'):
                    self.sora_btn.move(width - 580, 8)

                if hasattr(self, 'add_prompt_btn'):
                    self.add_prompt_btn.move(width - 710, 8)

                if hasattr(self, 'add_image_prompt_btn'):
                    self.add_image_prompt_btn.move(width - 840, 8)

                if hasattr(self, 'optimization_btn'):
                    self.optimization_btn.move(width - 960, 8)

                if hasattr(self, 'setting_btn'):
                    self.setting_btn.move(width - 1050, 8)

            def on_setting_clicked(self):
                """打开设置对话框"""
                dialog = DirectorSettingDialog(
                    self.video_gen_count, 
                    self.char_detection_enabled,
                    self.container,
                    director_node=self,
                    script_time_optimization=self.script_time_optimization_enabled,
                    storyboard_count=self.storyboard_batch_count
                )
                if dialog.exec():
                    # 检查是否请求Sora人物@模式设置
                    if dialog.get_sora_mapping_requested():
                        print(f"[节点#{self.node_id}] 打开Sora人物@模式设置...")
                        self.open_sora_mapping_dialog()
                        # 重新打开设置对话框
                        QTimer.singleShot(100, self.on_setting_clicked)
                        return
                    
                    # 检查是否请求恢复镜头
                    if dialog.get_recover_requested():
                        print(f"[节点#{self.node_id}] 用户请求恢复镜头号...")
                        # 清空忽略列表
                        if hasattr(self, 'ignored_shots'):
                            self.ignored_shots.clear()
                            self.save_ignored_shots() # 保存清空后的状态
                        if hasattr(self, 'ignored_characters'):
                            self.ignored_characters.clear()
                            self.save_ignored_characters()
                        
                        # 强制刷新数据
                        self.update_data()
                        QMessageBox.information(None, "提示", "已恢复所有镜头并同步剧本数据。")
                        return

                    self.video_gen_count = dialog.get_count()
                    self.storyboard_batch_count = dialog.get_storyboard_count()
                    self.char_detection_enabled = dialog.get_char_detection()
                    self.script_time_optimization_enabled = dialog.get_script_time_optimization()
                    print(f"[节点#{self.node_id}] 设置更新 - 视频数量: {self.video_gen_count}, 分镜批量: {self.storyboard_batch_count}, 人物检测: {self.char_detection_enabled}, 时间优化: {self.script_time_optimization_enabled}")
                    
                    # 保存设置
                    settings = QSettings("GhostOS", "App")
                    settings.setValue("director/video_gen_count", self.video_gen_count)
                    settings.setValue("director/storyboard_batch_count", self.storyboard_batch_count)
                    settings.setValue("director/char_detection_enabled", "true" if self.char_detection_enabled else "false")
                    settings.setValue("director/script_time_optimization_enabled", "true" if self.script_time_optimization_enabled else "false")
            
            def open_sora_mapping_dialog(self):
                """打开Sora人物@模式设置对话框"""
                # 获取所有人物名称（从剧本数据中提取）
                character_names = self.extract_character_names()
                
                # 打开对话框
                dialog = SoraCharacterMappingDialog(
                    character_names,
                    self.sora_mapping_manager.mappings,
                    self.sora_mapping_manager.enabled,
                    None  # 设置为顶级窗口以避免输入焦点问题
                )
                
                if dialog.exec():
                    # 更新映射设置
                    mappings = dialog.get_mappings()
                    enabled = dialog.is_enabled()
                    self.sora_mapping_manager.update_settings(mappings, enabled)
                    
                    print(f"[节点#{self.node_id}] Sora人物@模式已更新 - 启用: {enabled}, 映射数: {len(mappings)}")
                    
                    # 刷新表格显示
                    self.update_data()
                    
                    QMessageBox.information(
                        self.container,
                        "设置成功",
                        f"Sora人物@模式已{'启用' if enabled else '关闭'}\n映射了 {len(mappings)} 个人物"
                    )
            
            def extract_character_names(self):
                """从剧本数据中提取所有人物名称"""
                character_names = set()
                
                # 从表格中提取
                for row in range(self.table.rowCount()):
                    # 人物列（第3列，index=3）
                    item = self.table.item(row, 3)
                    if item:
                        paths = item.data(Qt.UserRole)
                        if paths and isinstance(paths, list):
                            for path_data in paths:
                                if isinstance(path_data, dict):
                                    char_name = path_data.get('name')
                                    if char_name:
                                        character_names.add(char_name)
                
                # 也可以从剧本数据中提取
                if hasattr(self, 'current_script_data') and self.current_script_data:
                    shots = self.current_script_data.get('shots', [])
                    for shot in shots:
                        characters = shot.get('characters', [])
                        for char in characters:
                            if isinstance(char, dict):
                                char_name = char.get('name')
                                if char_name:
                                    character_names.add(char_name)
                            elif isinstance(char, str):
                                character_names.add(char)
                
                return sorted(list(character_names))


            def toggle_fullscreen(self):
                """切换全屏模式"""
                if hasattr(self, 'is_fullscreen_mode') and self.is_fullscreen_mode:
                    self.restore_from_fullscreen()
                else:
                    self.enter_fullscreen()
            
            def enter_fullscreen(self):
                """进入全屏模式"""
                if hasattr(self, 'is_fullscreen_mode') and self.is_fullscreen_mode:
                    return
                
                # 创建全屏窗口 (使用QWidget避免Esc关闭)
                self.fs_window = QWidget()
                self.fs_window.setWindowTitle("导演节点 - 全屏")
                # 设置窗口标志：无边框，置顶
                self.fs_window.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
                self.fs_window.setStyleSheet("background-color: white;")
                
                # 设置布局
                layout = QVBoxLayout(self.fs_window)
                layout.setContentsMargins(0, 0, 0, 0)
                
                # 将内容容器移动到全屏窗口
                self.proxy_widget.setWidget(None)
                layout.addWidget(self.container)
                
                # 启用水平滚动条
                self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                
                # 获取屏幕可用几何区域 (不包含任务栏)
                screen = QApplication.primaryScreen()
                available_rect = screen.availableGeometry()
                self.fs_window.setGeometry(available_rect)
                
                # 显示窗口 (使用 show 而不是 showFullScreen 以保留任务栏)
                self.fs_window.show()
                
                self.is_fullscreen_mode = True
                self.fullscreen_btn.setText("🔙 退出全屏") 
                self.fullscreen_btn.setToolTip("退出全屏")
                
                # 更新按钮位置
                def update_fullscreen_ui():
                    if hasattr(self, 'fs_window'):
                        self.update_button_positions(self.fs_window.width())
                        self.adjust_layout_to_size()
                        
                QTimer.singleShot(50, update_fullscreen_ui)
                
            def restore_from_fullscreen(self):
                """退出全屏模式"""
                if not hasattr(self, 'is_fullscreen_mode') or not self.is_fullscreen_mode:
                    return
                
                # 还原容器
                if hasattr(self, 'fs_window'):
                    # 从布局移除
                    self.fs_window.layout().removeWidget(self.container)
                    # 重新设置给 proxy
                    self.container.setParent(None) 
                    self.proxy_widget.setWidget(self.container)
                    
                    self.fs_window.close()
                    del self.fs_window
                
                # 恢复滚动条策略
                self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                
                self.is_fullscreen_mode = False
                self.fullscreen_btn.setText("🗖 全屏")
                self.fullscreen_btn.setToolTip("全屏显示 / 恢复")
                
                # 恢复布局
                self.setRect(self.rect())

            def adjust_layout_to_size(self):
                """根据当前节点大小调整表格行高和列宽"""
                if not hasattr(self, 'table'):
                    return

                # 基础尺寸
                # 0:镜号, 1:时间, 2:片场, 3:人物, 4:道具, 5:场景, 6:分镜, 7:图片提示词, 8:附加视频提示词, 9:视频
                base_col_widths = [80, 140, 350, 150, 150, 150, 180, 250, 250, 200]
                
                # 计算动态 base_width (只计算可见列)
                base_width = 0
                for col, width in enumerate(base_col_widths):
                    if col < self.table.columnCount() and not self.table.isColumnHidden(col):
                        base_width += width
                
                if base_width == 0: base_width = 1050 # Fallback
                
                # 判断是否全屏
                if hasattr(self, 'is_fullscreen_mode') and self.is_fullscreen_mode and hasattr(self, 'fs_window'):
                    current_width = self.fs_window.width()
                    current_height = self.fs_window.height()
                else:
                    current_width = self.rect().width()
                    current_height = self.rect().height()
                
                # 1. 调整列宽 (按比例)
                width_ratio = max(0.5, current_width / base_width) # 限制最小缩放
                for col, base_w in enumerate(base_col_widths):
                    if col < self.table.columnCount():
                        self.table.setColumnWidth(col, int(base_w * width_ratio))

                # 2. 调整行高 (始终显示4行)
                # 计算可用高度: 总高度 - 顶部边距(45) - 底部边距(10) - 表头高度(约35)
                # 稍微多减一点作为缓冲
                header_height = self.table.horizontalHeader().height()
                if header_height <= 0: header_height = 35 # 默认值
                
                available_height = current_height - 55 - header_height - 5 # 5px buffer
                
                # 确保最小行高
                row_height = max(140, int(available_height / 4))
                
                # 应用行高
                for row in range(self.table.rowCount()):
                    # 只有当该行有图片或者特殊列需要高行时才应用大行高
                    # 但为了保持一致性，如果用户希望"始终显示4行"，可能希望所有行都一致
                    # 之前的逻辑是 set_cell_images 里才设置行高
                    # 这里我们强制设置所有行
                    self.table.setRowHeight(row, row_height)
                
                # 记录当前行高供新行使用
                self.current_dynamic_row_height = row_height

                # 更新ImageDelegate的最大尺寸，使其随行高变化
                # 我们假设ImageDelegate会读取 current_dynamic_row_height 或者我们可以动态设置
                # 由于ImageDelegate是初始化时创建的，我们需要一种方式传递这个值
                # 最简单的方式是修改ImageDelegate的paint方法，或者在这里重新设置delegate属性(不推荐)
                # 或者给table设置一个动态属性
                self.table.setProperty("dynamic_row_height", row_height)

                # 3. 动态调整表格字体大小 (放大内部界面)
                font_size = max(9, int(current_height / 60)) 
                font = self.table.font()
                if font.pointSize() != font_size:
                    font.setPointSize(font_size)
                    self.table.setFont(font)
                    # 同时更新表头字体
                    header_font = self.table.horizontalHeader().font()
                    header_font.setPointSize(font_size)
                    self.table.horizontalHeader().setFont(header_font)

                # 强制更新表格视口和几何形状，确保 cellWidget (如视频控件) 位置正确
                self.table.updateGeometries()
                self.table.viewport().update()
            
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

            def get_script_characters(self):
                """获取所有剧本人物节点中的人物数据"""
                characters = []
                
                if not hasattr(self, 'scene') or not self.scene():
                    return characters
                    
                try:
                    nodes = [item for item in self.scene().items() if hasattr(item, 'node_title')]
                except:
                    return characters
                
                for node in nodes:
                    if "剧本人物" in node.node_title:
                         if hasattr(node, 'proxy_widget') and node.proxy_widget.widget():
                             widgets = node.proxy_widget.widget().findChildren(QWidget)
                             for child in widgets:
                                 if hasattr(child, 'get_data') and callable(child.get_data):
                                     try:
                                         data = child.get_data()
                                         # data: {name, prompt, image_path, ...}
                                         name = data.get('name', '').strip()
                                         image_path = data.get('image_path') or data.get('image')
                                         prompt = data.get('prompt', '')
                                         
                                         # 只要有名字和图片就认为是有效人物
                                         if name and image_path and os.path.exists(image_path):
                                             characters.append({
                                                 "name": name,
                                                 "path": image_path,
                                                 "prompt": prompt
                                             })
                                     except:
                                         pass
                return characters

            def add_character_from_script(self, row):
                """从剧本人物节点添加人物到指定行"""
                characters = self.get_script_characters()
                
                if not characters:
                    QMessageBox.warning(None, "提示", "未找到包含图片的剧本人物节点！\n请先创建剧本人物节点并上传图片。")
                    return
                
                # 创建菜单供选择
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
                        font-size: 14px;
                    }
                    QMenu::item:selected {
                        background-color: #F3E5F5;
                        color: #4A148C;
                    }
                """)
                
                # 添加人物选项
                for char in characters:
                    action = menu.addAction(f"👤 {char['name']}")
                    # 使用闭包捕获 char
                    action.triggered.connect(lambda checked=False, c=char: self._add_single_character(row, c))
                
                menu.exec(QCursor.pos())

            def _add_single_character(self, row, char_data):
                """添加单个人物到单元格"""
                item = self.table.item(row, 3) # 人物列是 3
                current_data = []
                if item:
                    data = item.data(Qt.UserRole)
                    if data and isinstance(data, list):
                        current_data = data
                
                # 构造新数据项
                new_item = {
                    "name": char_data["name"],
                    "path": char_data["path"]
                }
                
                # 检查是否已存在 (避免重复添加完全相同的人物)
                # 这里我们比较路径
                exists = False
                for existing in current_data:
                    existing_path = existing
                    if isinstance(existing, dict):
                        existing_path = existing.get("path")
                    
                    if existing_path == char_data["path"]:
                        exists = True
                        break
                
                if not exists:
                    current_data.append(new_item)
                    item_shot = self.table.item(row, 0)
                    shot_num = item_shot.text().strip() if item_shot and item_shot.text() else str(row + 1)
                    name = new_item.get("name")
                    if shot_num and name:
                        self.clear_ignored_character(shot_num, name)
                    self.set_cell_images(row, 3, current_data)

            def on_cell_changed(self, row, column):
                """当单元格内容修改时触发"""
                # 避免递归调用 (如果我们在代码中修改了单元格)
                # 注意：update_data 应该使用 blockSignals(True) 来避免触发此回调
                
                item = self.table.item(row, column)
                if not item: return
                
                new_text = item.text()
                
                # 获取镜号作为Key
                item_shot = self.table.item(row, 0)
                shot_num = item_shot.text() if item_shot else str(row + 1)
                
                # Column 2: 动画片场
                if column == 2:
                    if not hasattr(self, 'manual_studio_edits'):
                        self.manual_studio_edits = {}
                    
                    # 只有当内容确实不同时才保存，避免不必要的IO
                    if self.manual_studio_edits.get(shot_num) != new_text:
                        self.manual_studio_edits[shot_num] = new_text
                        self.save_manual_studio_edits()
                
                # Column 7: 图片提示词
                elif column == 7:
                    if not hasattr(self, 'manual_image_prompts'):
                        self.manual_image_prompts = {}
                        
                    if self.manual_image_prompts.get(shot_num) != new_text:
                        self.manual_image_prompts[shot_num] = new_text
                        self.save_manual_image_prompts()

                # Column 8: 附加视频提示词
                elif column == 8:
                    if not hasattr(self, 'manual_video_prompts'):
                        self.manual_video_prompts = {}
                        
                    if self.manual_video_prompts.get(shot_num) != new_text:
                        self.manual_video_prompts[shot_num] = new_text
                        self.save_manual_video_prompts()

            def read_google_script_data(self, google_node):
                """读取谷歌剧本节点数据"""
                # 预先扫描当前表格中的手动编辑数据 (特别是人物列)
                # Key: Shot ID (镜号), Value: Character Data List
                manual_char_map = {}
                try:
                    for r in range(self.table.rowCount()):
                        item_shot = self.table.item(r, 0)
                        item_char = self.table.item(r, 3)
                        if item_shot and item_char:
                            shot_id = item_shot.text().strip()
                            char_data = item_char.data(Qt.UserRole)
                            if shot_id and char_data and isinstance(char_data, list):
                                manual_char_map[shot_id] = char_data
                except:
                    pass

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

                # 过滤掉被忽略的镜头
                if not hasattr(self, 'ignored_shots'):
                    self.ignored_shots = set()
                    
                filtered_rows = []
                for row_data in rows:
                    shot_text = ""
                    if isinstance(row_data, dict):
                        shot_text = row_data.get("镜号", row_data.get(0, ""))
                    
                    if str(shot_text) not in self.ignored_shots:
                        filtered_rows.append(row_data)
                
                rows = filtered_rows
                self.current_script_rows = rows

                # 更新导演节点表格
                current_row_count = len(rows)
                if self.table.rowCount() != current_row_count:
                    self.table.setRowCount(current_row_count)
                
                # 暂停信号，避免 programmatic updates 触发 on_cell_changed 误判为手动编辑
                self.table.blockSignals(True)
                for r, row_data in enumerate(rows):
                    # 1. 镜号
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
                        
                    # 2. 时间码
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

                    # 2.5 动画片场 (Column 2) - 组合 画面内容+台词+地点
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
                    
                    # 获取道具提示词 (从缓存中读取)
                    prop_prompt = ""
                    if shot_text and hasattr(self, 'props_prompts') and shot_text in self.props_prompts:
                        prop_prompt = self.props_prompts[shot_text]

                    # 组合内容
                    studio_parts = []
                    if picture_content: studio_parts.append(f"【画面】{picture_content}")
                    if lines: studio_parts.append(f"【台词】{lines}")
                    if location: studio_parts.append(f"【地点】{location}")
                    if prop_prompt: studio_parts.append(f"【道具】{prop_prompt}")
                    
                    studio_text = "\n".join(studio_parts)
                    
                    # 检查是否有手动编辑的内容
                    if shot_text and shot_text in self.manual_studio_edits:
                        studio_text = self.manual_studio_edits[shot_text]
                    
                    # 应用Sora人物@模式映射（在顶部添加映射信息）
                    if hasattr(self, 'sora_mapping_manager') and self.sora_mapping_manager.enabled:
                        studio_text = self.sora_mapping_manager.apply_to_text(studio_text)
                    
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
                                else:
                                    # 如果关键词为空，是否清空全部？
                                    # 根据用户描述 "清理节点可以清楚动画片场的内容"，
                                    # 且清理节点默认提示是"双击设置"，
                                    # 这里我们假设如果连接了但没设置关键词，可能用户期望是清空全部？
                                    # 或者我们可以约定一个特殊关键词，或者默认行为。
                                    # 考虑到 "断开则恢复"，这里我们暂时实现为：
                                    # 如果有连接，且关键词为空(默认状态)，则不做改变(或者清空?)
                                    # 为了安全起见，仅当有关键词时才清理。
                                    # 除非用户明确想要 "Eraser" 模式。
                                    # 让我们尝试支持 "清空模式": 如果关键词是 "ALL" 或 "全部", 则清空。
                                    # 但根据 "清楚内容" 的语境，也许直接清空是用户的直觉。
                                    # 让我们做一个折中：如果检测到 CleaningNode，我们应用其 clean_text。
                                    pass
                                    
                            # 特殊逻辑：如果用户想要一键清空，可能会希望连接就清空。
                            # 但CleaningNode是设计来过滤的。
                            # 让我们再读一遍需求："清理节点可以清楚动画片场的内容"
                            # 也许是 "clear the content" (Wipe).
                            # 如果我把 cleaning_text 默认为空，那么连接后什么都不发生，用户会觉得坏了。
                            # 让我们实现：应用 replace。
                            pass

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

                    shot_key = str(shot_text).strip()
                    ignored_names = set()
                    if hasattr(self, 'ignored_characters') and isinstance(self.ignored_characters, dict):
                        val = self.ignored_characters.get(shot_key)
                        if isinstance(val, set):
                            ignored_names = val
                        elif isinstance(val, list):
                            ignored_names = set(str(x) for x in val)

                    # 3. 人物 (Column 3) - 支持多人物
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
                            if ignored_names and name in ignored_names:
                                continue
                            
                            # 精确匹配
                            if name in char_map:
                                char_image_paths.append({"path": char_map[name], "name": name})
                            else:
                                # 尝试模糊匹配 (如果名字包含在Map的Key中，或者Key包含名字)
                                # 比如 "幼年莱恩" 匹配 "莱恩" (需谨慎)
                                pass

                    # 自动人物检测 (从设置读取)
                    # 默认开启，若提示词中出现某人物名字且该人物未在列表中，自动添加
                    if getattr(self, 'char_detection_enabled', True):
                         if studio_text:
                             # 遍历所有已知人物
                             for char_name, char_path in char_map.items():
                                 if char_name and char_name in studio_text:
                                     if ignored_names and char_name in ignored_names:
                                         continue
                                     # 检查是否已经存在
                                     exists = False
                                     for existing in char_image_paths:
                                         if existing.get("name") == char_name:
                                             exists = True
                                             break
                                     if not exists:
                                         char_image_paths.append({"path": char_path, "name": char_name})
                    
                    # 合并手动编辑的人物数据
                    if shot_key in manual_char_map:
                        existing_data = manual_char_map[shot_key]
                        
                        # 辅助函数: 获取路径
                        def get_path(item):
                            if isinstance(item, dict): return item.get("path")
                            return item
                            
                        # 构建现有路径集合
                        existing_paths = set()
                        final_list = list(existing_data) # 优先保留现有数据
                        
                        for item in existing_data:
                            p = get_path(item)
                            if p: existing_paths.add(p)
                            
                        # 将脚本中新增的人物追加进去 (确保脚本要求的人物一定存在)
                        for char_item in char_image_paths:
                            p = char_item["path"]
                            if p not in existing_paths:
                                final_list.append(char_item)
                                existing_paths.add(p)
                        
                        char_image_paths = final_list

                    # 设置单元格图片 (传入列表)
                    self.set_cell_images(r, 3, char_image_paths)

                    # 4. 道具 (Column 4)
                    prop_text = ""
                    if isinstance(row_data, dict):
                         for key in ["道具", "物品", "Props", "Items"]:
                             if key in row_data:
                                 prop_text = row_data[key]
                                 break
                    
                    item_prop = self.table.item(r, 4)
                    if not item_prop:
                        item_prop = QTableWidgetItem(str(prop_text))
                        item_prop.setTextAlignment(Qt.AlignCenter)
                        self.table.setItem(r, 4, item_prop)
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
                        
                        current_item = self.table.item(r, 4)
                        should_update_prop = True
                        if current_item:
                            current_data = current_item.data(Qt.UserRole)
                            if current_data and isinstance(current_data, list) and len(current_data) > 0:
                                if current_data[0] == saved_prop_path:
                                    should_update_prop = False
                        
                        if should_update_prop and os.path.exists(saved_prop_path):
                            self.set_cell_images(r, 4, [saved_prop_path])
                    else:
                        # 确保清除无效图片
                        current_item = self.table.item(r, 4)
                        if current_item:
                             current_data = current_item.data(Qt.UserRole)
                             if current_data:
                                 self.set_cell_images(r, 4, [])

                    loc_text = ""
                    if isinstance(row_data, dict):
                        for key in ["地点/环境", "地点环境", "地点", "场景", "Location", "Scene", "Environment"]:
                            if key in row_data:
                                loc_text = row_data[key]
                                break
                    
                    loc_image_paths = []
                    if shot_text and hasattr(self, "scene_paths") and isinstance(self.scene_paths, dict):
                        saved_scene_path = self.scene_paths.get(str(shot_text))
                        if saved_scene_path and os.path.exists(saved_scene_path):
                            loc_name = os.path.splitext(os.path.basename(saved_scene_path))[0]
                            loc_image_paths.append({"path": saved_scene_path, "name": loc_name})
                    
                    if not loc_image_paths and loc_text:
                        loc_text = str(loc_text).strip()
                        if loc_text in loc_map:
                            loc_image_paths.append({"path": loc_map[loc_text], "name": loc_text})
                        else:
                            for loc_name, path in loc_map.items():
                                if loc_name in loc_text or loc_text in loc_name:
                                    loc_image_paths.append({"path": path, "name": loc_name})
                                    break 
                    
                    self.set_cell_images(r, 5, loc_image_paths)

                    # 7. 图片提示词 (Column 7)
                    update_image_prompt_column(self, r, row_data)
                    
                    # 6. 分镜图 (Column 6) - 从缓存恢复
                    # 只有当单元格为空或者需要更新时才设置，避免频繁IO检查
                    # 获取当前镜号
                    current_shot = shot_text # 使用之前获取的 shot_text
                    if current_shot and current_shot in self.storyboard_paths:
                        saved_data = self.storyboard_paths[current_shot]
                        
                        paths = []
                        if isinstance(saved_data, list):
                            paths = [p for p in saved_data if p]
                        else:
                             paths = [saved_data] if saved_data else []
                        
                        # 检查当前单元格内容
                        current_item = self.table.item(r, 6)
                        should_update = True
                        if current_item:
                            current_data = current_item.data(Qt.UserRole)
                            # 简单比较
                            if current_data == paths:
                                should_update = False
                        
                        if should_update:
                             final_paths = []
                             for p in paths:
                                 if p and os.path.exists(p):
                                     final_paths.append(p)
                             self.set_cell_images(r, 6, final_paths)

                    # 8. 视频 (Column 9) - 从缓存恢复
                    if current_shot and current_shot in self.video_paths:
                        video_path = self.video_paths[current_shot]
                        
                        # Check existence (support list or str)
                        has_video = False
                        if isinstance(video_path, list):
                            for p in video_path:
                                if p and os.path.exists(p):
                                    has_video = True
                                    break
                        elif video_path and isinstance(video_path, str) and os.path.exists(video_path):
                            has_video = True
                            
                        if has_video:
                            # 确保列存在
                            if self.table.columnCount() <= 9:
                                self.table.setColumnCount(10)
                                item = QTableWidgetItem("🎥 电影院")
                                item.setBackground(QColor("#AB47BC"))
                                item.setForeground(QColor("white"))
                                self.table.setHorizontalHeaderItem(9, item)
                                self.table.setColumnWidth(9, 200)
                                self.table.setItemDelegateForColumn(9, VideoDelegate(self.table, node=self))
                            
                            self.set_cinema_cell_ui(r, video_path)

                            # 恢复元数据
                            if current_shot in self.video_metadata:
                                meta = self.video_metadata[current_shot]
                                item = self.table.item(r, 9)
                                if item:
                                    item.setData(Qt.UserRole + 1, meta)
                                    # print(f"[DEBUG] Restored metadata for shot {current_shot}: {meta}")

                    # 9. 附加视频提示词 (Column 8) - 从缓存恢复
                    item_video_prompt = self.table.item(r, 8)
                    if not item_video_prompt:
                        item_video_prompt = QTableWidgetItem("")
                        self.table.setItem(r, 8, item_video_prompt)
                    
                    if current_shot and hasattr(self, 'manual_video_prompts'):
                        saved_video_prompt = self.manual_video_prompts.get(current_shot, "")
                        if saved_video_prompt and item_video_prompt.text() != saved_video_prompt:
                            item_video_prompt.setText(saved_video_prompt)
                
                self.table.blockSignals(False)

                # 检查是否全部完成并更新列
                self.check_completion_and_update_columns()
                
                # 强制调整布局以确保行高正确 (始终显示4行)
                # 使用QTimer确保在UI更新后执行
                self.adjust_layout_to_size()
                QTimer.singleShot(100, self.adjust_layout_to_size)

            def on_optimization_clicked(self):
                print("DEBUG: [DirectorNode] Optimization button clicked") # DEBUG
                try:
                    if not hasattr(self, 'current_script_rows'):
                        print("DEBUG: [DirectorNode] No current_script_rows attribute") # DEBUG
                        QMessageBox.warning(self.proxy_widget.widget(), "提示", "没有剧本数据！(Attribute Missing)\n请先连接谷歌剧本节点并确保有数据。")
                        return

                    if not self.current_script_rows:
                        print("DEBUG: [DirectorNode] current_script_rows is empty") # DEBUG
                        QMessageBox.warning(self.proxy_widget.widget(), "提示", "没有剧本数据！(Empty Data)\n请先连接谷歌剧本节点并确保有数据。")
                        return
                    
                    print(f"DEBUG: [DirectorNode] Found {len(self.current_script_rows)} rows of script data") # DEBUG
                    
                    # Check if already running
                    if hasattr(self, 'opt_worker') and self.opt_worker.isRunning():
                         print("DEBUG: [DirectorNode] Worker already running") # DEBUG
                         QMessageBox.information(self.proxy_widget.widget(), "提示", "优化任务正在进行中，请稍候。")
                         return

                    # Ask user for grid count
                    items = ["4 Grids", "6 Grids", "9 Grids"]
                    item, ok = QInputDialog.getItem(self.proxy_widget.widget(), "选择Grid数量", 
                                                "请选择每个镜头的Grid数量:", items, 1, False)
                    if not ok or not item:
                        return
                    
                    grid_count = int(item.split()[0])
                    print(f"DEBUG: [DirectorNode] Selected grid count: {grid_count}") # DEBUG

                    # Construct script content
                    print("DEBUG: [DirectorNode] Constructing script content...") # DEBUG
                    script_content = ""
                    for row in self.current_script_rows:
                        shot = ""
                        if isinstance(row, dict):
                             shot = row.get("镜号", row.get(0, ""))
                        
                        content = ""
                        dialogue = ""
                        location = ""
                        time_text = ""
                        
                        if isinstance(row, dict):
                            # Timecode
                            time_text = row.get("时间码", row.get(1, ""))
                            
                            # Content
                            for key in ["画面内容", "Picture Content", "Content"]:
                                if key in row: content = row[key]; break
                            # Dialogue
                            for key in ["台词/音效", "台词", "Lines", "Dialogue", "Sound"]:
                                if key in row: dialogue = row[key]; break
                            # Location
                            for key in ["地点/环境", "地点", "Location", "Environment", "Scene"]:
                                if key in row: location = row[key]; break
                        
                        script_content += f"[镜头{shot}]"
                        if time_text:
                            # 尝试解析总秒数，辅助AI分配
                            total_seconds = 5
                            try:
                                def parse_to_sec(t_str):
                                    t_str = t_str.strip()
                                    p = t_str.split(':')
                                    if len(p) >= 3: # HH:MM:SS or HH:MM:SS:FF
                                        return int(p[0]) * 3600 + int(p[1]) * 60 + int(p[2])
                                    elif len(p) == 2: # MM:SS
                                        return int(p[0]) * 60 + int(p[1])
                                    return 0

                                if '-' in time_text:
                                    t_parts = time_text.split('-')
                                    if len(t_parts) == 2:
                                        start_s = parse_to_sec(t_parts[0])
                                        end_s = parse_to_sec(t_parts[1])
                                        diff = end_s - start_s
                                        if diff > 0:
                                            total_seconds = diff
                                else:
                                    ts = parse_to_sec(time_text)
                                    if ts > 0:
                                        total_seconds = ts
                            except:
                                pass
                            script_content += f" (总时长: {time_text}) [TotalSeconds: {total_seconds}]"
                        else:
                            script_content += " (总时长: 00:00:05:00) [TotalSeconds: 5]"
                        script_content += "\n"
                        if location: script_content += f"地点: {location}\n"
                        if content: script_content += f"画面: {content}\n"
                        if dialogue: script_content += f"台词: {dialogue}\n"
                        script_content += "\n"
                    
                    print(f"DEBUG: [DirectorNode] Script content constructed (Length: {len(script_content)})") # DEBUG
                    
                    # Create and start worker
                    print("DEBUG: [DirectorNode] Initializing OptimizationWorker...") # DEBUG
                    # Pass None as parent to avoid TypeError (DirectorNodeImpl is not a QObject)
                    self.opt_worker = OptimizationWorker(
                        script_content, 
                        None, 
                        grid_count=grid_count,
                        time_optimization_enabled=self.script_time_optimization_enabled
                    )
                    self.opt_worker.optimization_completed.connect(self.handle_optimization_completed)
                    self.opt_worker.task_failed.connect(self.handle_optimization_failed)
                    self.opt_worker.log_signal.connect(lambda msg: print(f"[OptimizationWorker] {msg}"))
                    
                    print("DEBUG: [DirectorNode] Starting OptimizationWorker...") # DEBUG
                    self.opt_worker.start()
                    
                    self.optimization_btn.setEnabled(False)
                    self.optimization_btn.setText("⏳ 优化中...")
                    print("DEBUG: [DirectorNode] OptimizationWorker started successfully") # DEBUG
                
                except Exception as e:
                    print(f"DEBUG: [DirectorNode] Error in on_optimization_clicked: {e}") # DEBUG
                    import traceback
                    traceback.print_exc()
                    QMessageBox.critical(self.proxy_widget.widget(), "错误", f"启动优化失败:\n{str(e)}")
                
            def handle_optimization_completed(self, data):
                self.optimization_btn.setEnabled(True)
                self.optimization_btn.setText("🚀 剧本优化")
                
                count = 0
                for shot_num, content in data.items():
                    # Update manual edits
                    # Note: shot_num from API might need normalization (e.g. "1" vs "01")
                    # But our table uses what's in the first column.
                    # We should try to match flexibly if possible, but exact match is safer first.
                    
                    # Store directly in manual edits
                    self.manual_studio_edits[str(shot_num)] = content
                    count += 1
                    
                self.save_manual_studio_edits()
                
                # Refresh table
                self.update_data()
                
                QMessageBox.information(self.proxy_widget.widget(), "完成", f"已优化 {count} 个镜头！\n数据已更新到【动画片场】列。")
                
                # Ensure the column is visible
                self.table.setColumnHidden(2, False)

            def handle_optimization_failed(self, error_msg):
                self.optimization_btn.setEnabled(True)
                self.optimization_btn.setText("🚀 剧本优化")
                QMessageBox.warning(self.proxy_widget.widget(), "优化失败", f"错误信息：{error_msg}")

            def check_completion_and_update_columns(self):
                """更新列显示状态 (始终显示电影院列)"""
                row_count = self.table.rowCount()
                
                # 始终确保电影院列存在
                current_cols = self.table.columnCount()
                
                if current_cols <= 9:
                    # 记录之前的列数
                    old_cols = current_cols
                    
                    self.table.setColumnCount(10)
                    
                    # 如果之前没有第7列(图片提示词)，则新建后默认隐藏它，以免显示空白列
                    if old_cols <= 7:
                        self.table.setColumnHidden(7, True)
                        
                    item = QTableWidgetItem("🎥 电影院")
                    item.setBackground(QColor("#AB47BC"))
                    item.setForeground(QColor("white"))
                    self.table.setHorizontalHeaderItem(9, item)
                    self.table.setColumnWidth(9, 200)
                    self.table.setItemDelegateForColumn(9, VideoDelegate(self.table, node=self))
                    
                    # 初始化所有行的该列单元格，确保不为空
                    for r in range(row_count):
                        if not self.table.item(r, 9):
                            self.table.setItem(r, 9, QTableWidgetItem())
                
                # 恢复视频数据
                if hasattr(self, 'video_paths') and self.video_paths:
                    for r in range(row_count):
                        item_shot = self.table.item(r, 0)
                        shot_num = item_shot.text() if item_shot else str(r+1)
                        if shot_num in self.video_paths:
                            video_path = self.video_paths[shot_num]
                            
                            has_video = False
                            if isinstance(video_path, list):
                                for p in video_path:
                                    if p and isinstance(p, str) and os.path.exists(p):
                                        has_video = True
                                        break
                            elif video_path and isinstance(video_path, str) and os.path.exists(video_path):
                                has_video = True
                                
                            if has_video:
                                # 复用 UI 更新逻辑
                                self.set_cinema_cell_ui(r, video_path)

            def set_cell_images(self, row, col, image_paths):
                """在单元格中设置单张或多张图片"""
                # 确保是列表
                if isinstance(image_paths, str):
                    image_paths = [image_paths]
                
                # 对于分镜图列(6)，保留 None 值且不去重，保持位置
                if col == 6:
                    if not image_paths:
                        image_paths = [None, None]
                else:
                    # 去重并过滤空值
                    if image_paths:
                        # 如果是字典列表 (包含人物名称)，则不进行简单的去重
                        if len(image_paths) > 0 and isinstance(image_paths[0], dict):
                            pass
                        else:
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
                
                # 清除加载状态
                if col == 6:
                    item.setData(Qt.UserRole + 2, None)
                
                # 移除旧的 Widget (如果存在)
                self.table.removeCellWidget(row, col)
                
                # 设置行高
                # 只要有图片或者列是6(总是显示占位符)，就设置行高
                target_height = getattr(self, 'current_dynamic_row_height', 140)
                if image_paths or col == 6:
                    self.table.setRowHeight(row, target_height)


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
                            max_size = 800
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

                # 重新调整布局以适应列的变化
                self.adjust_layout_to_size()
                
                # 保存设置
                self.save_view_settings()

            def on_header_clicked(self, logical_index):
                """处理表头点击事件"""
                # 分镜图列 (Index 6)
                if logical_index == 6:
                    self.show_tail_frame = not self.show_tail_frame
                    
                    # 更新表头文字
                    header_item = self.table.horizontalHeaderItem(6)
                    if header_item:
                        indicator = "🟢" if self.show_tail_frame else "🔴"
                        header_item.setText(f"🖼️ 分镜图 {indicator}")
                    
                    # 强制刷新表格以更新 Delegate 绘制
                    self.table.viewport().update()

            def download_image(self, src_path):
                """下载图片到本地"""
                if not src_path or not os.path.exists(src_path):
                    return
                
                default_name = os.path.basename(src_path)
                dest_path, _ = QFileDialog.getSaveFileName(
                    self.container if hasattr(self, 'container') else None,
                    "保存图片",
                    default_name,
                    "Images (*.png *.jpg *.jpeg *.webp);;All Files (*)"
                )
                
                if dest_path:
                    try:
                        import shutil
                        shutil.copy2(src_path, dest_path)
                        QMessageBox.information(None, "完成", "图片已成功保存！")
                    except Exception as e:
                        QMessageBox.critical(None, "错误", f"保存失败: {e}")

            def on_table_context_menu(self, pos):
                """表格右键菜单"""
                # 隐藏预览图，避免遮挡
                if hasattr(self, 'preview_item') and self.preview_item:
                    self.preview_item.setVisible(False)

                # 坐标转换：pos 已经是 Viewport 坐标 (因为 QTableWidget 是 QAbstractScrollArea)
                # viewport_pos = self.table.viewport().mapFrom(self.table, pos)
                viewport_pos = pos
                item = self.table.itemAt(viewport_pos)
                
                col = item.column() if item else -1
                row = item.row() if item else -1
                
                # 如果 itemAt 返回空 (例如点击了空单元格)，尝试使用坐标计算
                if col == -1:
                    col = self.table.columnAt(viewport_pos.x())
                if row == -1:
                    row = self.table.rowAt(viewport_pos.y())
                
                print(f"[导演节点] 右键菜单: pos={pos}, viewport_pos={viewport_pos}, row={row}, col={col}")
                
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
                
                # 获取选中区域供后续使用
                selected_ranges = self.table.selectedRanges()
                
                # 计算选中的行集合
                selected_rows = set()
                if selected_ranges:
                    for r in selected_ranges:
                         for i in range(r.topRow(), r.bottomRow() + 1):
                             selected_rows.add(i)
                
                # 如果选中了多行，并且点击在选中范围内，允许批量删除（无论哪一列）
                action_delete_row = None
                if len(selected_rows) > 1 and row in selected_rows:
                     action_delete_row = menu.addAction(f"🗑️ 删除选中的 {len(selected_rows)} 行")
                     menu.addSeparator()
                # 否则，如果是镜头号列(0)，显示单行删除
                elif col == 0 and row >= 0:
                     action_delete_row = menu.addAction("🗑️ 删除此行")
                     menu.addSeparator()

                action_gen_this = None
                action_view_image = None
                action_clear = None
                action_clear_all_storyboards = None
                action_upload_image = None
                action_ai_prompt = None
                action_crop = None

                # 如果点击的是道具列(4)，添加上传图片选项
                if col == 3 and row >= 0:
                    # 人物列右键菜单
                    action_add_character = menu.addAction("👤 新增人物")
                    action_add_character.triggered.connect(lambda: self.add_character_from_script(row))
                    
                    action_upload_char = menu.addAction("📤 上传图片")
                    action_upload_char.triggered.connect(lambda: self.upload_character_image(row))
                    
                    # 获取当前数据
                    item = self.table.item(row, 3)
                    current_data = []
                    if item:
                         d = item.data(Qt.UserRole)
                         if isinstance(d, list):
                             current_data = d
                    
                    if current_data:
                        delete_menu = menu.addMenu("🗑️ 删除图片")
                        
                        # 如果有多个，显示单独删除选项
                        if len(current_data) > 0:
                            for i, char_data in enumerate(current_data):
                                name = "未知"
                                if isinstance(char_data, dict):
                                    name = char_data.get('name', f'图片{i+1}')
                                elif isinstance(char_data, str):
                                    name = f"图片{i+1}"
                                
                                action = delete_menu.addAction(f"删除 {name}")
                                action.triggered.connect(lambda checked=False, r=row, idx=i: self.delete_character_image(r, idx))
                            
                            delete_menu.addSeparator()
                        
                        action_clear = delete_menu.addAction("清空所有")
                        action_clear.triggered.connect(lambda: self.delete_character_image(row, None))
                    
                    menu.addSeparator()

                if col == 4 and row >= 0:
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

                if col == 5 and row >= 0:
                    action_change_scene = menu.addAction("📷 更换场景图片")
                    action_change_scene.triggered.connect(lambda: change_scene_image(self, row))
                    menu.addSeparator()

                # 如果点击的是分镜图列(6)，添加特定选项
                action_gen_storyboard_generic = None
                action_gen_sequential = None # 新增：连贯分镜
                action_auto_track = None
                
                if col == 6:
                    if row >= 0:
                        action_gen_this = menu.addAction("🎬 生成此分镜图")
                        
                        # 新增：连贯分镜选项 (仅当不是第一行时显示)
                        if row > 0:
                            action_gen_sequential = menu.addAction("🔄 追踪术")
                            action_auto_track = menu.addAction("⚡ 自动追踪")
                        
                        # 添加清空选项
                        if item:
                            data = item.data(Qt.UserRole)
                            
                            # Add Crop Tool
                            if data and isinstance(data, list) and len(data) > 0 and data[0] and os.path.exists(data[0]):
                                action_crop = menu.addAction("✂ 裁剪工具")
                                action_send_to_artboard = menu.addAction("🎨 发送到画板")
                                menu.addSeparator()

                            has_data = False
                            if data and isinstance(data, list):
                                 for p in data:
                                     if p and os.path.exists(p):
                                         has_data = True
                                         break
                            
                            if has_data:
                                # action_view_image = menu.addAction("🔍 查看大图") # 已移除
                                menu.addSeparator()
                                
                                # 下载选项
                                action_download_head = None
                                action_download_tail = None
                                
                                head_path = data[0] if len(data) > 0 else None
                                tail_path = data[1] if len(data) > 1 else None
                                
                                has_head = head_path and os.path.exists(head_path)
                                has_tail = tail_path and os.path.exists(tail_path)
                                
                                if has_head:
                                    label = "⬇️ 下载首帧" if has_tail else "⬇️ 下载分镜图"
                                    action_download_head = menu.addAction(label)
                                
                                if has_tail:
                                    action_download_tail = menu.addAction("⬇️ 下载尾帧")
                                
                                menu.addSeparator()
                                action_clear = menu.addAction("🗑️ 清空此行")
                    else:
                        # 如果点击的是表头或空白处，添加通用的生成选项
                        action_gen_storyboard_generic = menu.addAction("🎬 产生分镜图")

                    menu.addSeparator()
                    # 添加清空所有分镜图选项
                    action_clear_all_storyboards = menu.addAction("🗑️ 清空所有分镜图")
                    menu.addSeparator()
                
                action_gen_video = None
                action_clear_video = None
                action_clear_all_videos = None
                action_create_sora_char = None
                
                # 如果点击的是电影院列(8)
                if col == 9 and row >= 0:
                     # 显示镜头号
                     item_shot = self.table.item(row, 0)
                     shot_num = item_shot.text() if item_shot else str(row + 1)
                     action_lens_info = menu.addAction(f"镜头号{shot_num}*")
                     action_lens_info.setEnabled(False)
                     menu.addSeparator()

                     action_gen_video = menu.addAction("🎥 生成视频")
                     action_create_sora_char = menu.addAction("👤 创建Sora角色")
                     action_download_video = menu.addAction("⬇️ 下载视频")
                     action_clear_video = menu.addAction("🗑️ 清空此视频")
                     menu.addSeparator()
                     action_clear_all_videos = menu.addAction("🗑️ 清空全部视频")
                     menu.addSeparator()

                # action_gen_all = menu.addAction("🎬 生成所有分镜图")
                
                action = menu.exec(self.table.mapToGlobal(pos))
                
                if action_delete_row and action == action_delete_row:
                    if len(selected_rows) > 1 and row in selected_rows:
                        self.delete_rows(list(selected_rows))
                    else:
                        self.delete_rows([row])
                elif action_gen_this and action == action_gen_this:
                    self.open_storyboard_dialog(target_rows=[row])
                elif action_gen_sequential and action == action_gen_sequential:
                    # 运行连贯分镜生成
                    self.run_sequential_storyboard_generation(row)
                elif action_auto_track and action == action_auto_track:
                    run_auto_track_storyboard_generation(self, row)
                elif 'action_send_to_artboard' in locals() and action_send_to_artboard and action == action_send_to_artboard:
                    item = self.table.item(row, 6)
                    if item:
                        data = item.data(Qt.UserRole)
                        if data and len(data) > 0 and data[0] and os.path.exists(data[0]):
                            # 获取提示词
                            prompt = ""
                            # 1. 尝试从图片提示词列(7)获取
                            item_prompt = self.table.item(row, 7)
                            if item_prompt:
                                prompt = item_prompt.text().strip()
                            
                            # 2. 如果为空，尝试从Google脚本数据获取
                            if not prompt and hasattr(self, 'current_script_rows') and row < len(self.current_script_rows):
                                row_data = self.current_script_rows[row]
                                # 查找包含"提示词"和"CN"的key
                                for key in row_data:
                                    if isinstance(key, str) and "提示词" in key and "CN" in key:
                                        prompt = row_data[key]
                                        break
                                if not prompt:
                                     # 尝试 Painting Prompt
                                     for key in row_data:
                                         if isinstance(key, str) and "Painting Prompt" in key and "CN" in key:
                                             prompt = row_data[key]
                                             break

                            self.open_artboard(data[0], prompt, row)

                elif action_crop and action == action_crop:
                    item = self.table.item(row, 6)
                    if item:
                        data = item.data(Qt.UserRole)
                        if data and len(data) > 0 and data[0] and os.path.exists(data[0]):
                            # Pass None as parent to ensure it's a top-level window and sizing works correctly
                            dialog = CropDialog(data[0], None)
                            if dialog.exec() == 1: # Accepted
                                # Clear cache in delegate
                                delegate = self.table.itemDelegateForColumn(6)
                                if isinstance(delegate, ImageDelegate):
                                    if data[0] in delegate.cache:
                                        del delegate.cache[data[0]]
                                self.table.viewport().update()

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
                        
                        if col == 6 and shot_num in self.storyboard_paths:
                            del self.storyboard_paths[shot_num]
                            self.save_storyboard_paths()
                        elif col == 4 and shot_num in self.props_paths:
                            del self.props_paths[shot_num]
                            self.save_props_paths()
                        elif col == 5 and hasattr(self, "scene_paths") and isinstance(self.scene_paths, dict) and shot_num in self.scene_paths:
                            del self.scene_paths[shot_num]
                            if hasattr(self, "save_scene_paths"):
                                self.save_scene_paths()

                    # 检查完成状态 (可能需要隐藏电影院列)
                    self.check_completion_and_update_columns()
                
                elif action_gen_storyboard_generic and action == action_gen_storyboard_generic:
                    # 获取选中行号
                    rows = set()
                    if selected_ranges:
                        for r in selected_ranges:
                            for i in range(r.topRow(), r.bottomRow() + 1):
                                rows.add(i)
                    
                    target_rows = list(rows) if rows else None
                    self.open_storyboard_dialog(target_rows=target_rows)

                elif action_clear_all_storyboards and action == action_clear_all_storyboards:
                    # 清空所有分镜图
                    self.clear_all_storyboards()
                
                elif 'action_download_head' in locals() and action_download_head and action == action_download_head:
                    item = self.table.item(row, 6)
                    if item:
                        data = item.data(Qt.UserRole)
                        if data and len(data) > 0 and data[0] and os.path.exists(data[0]):
                            self.download_image(data[0])

                elif 'action_download_tail' in locals() and action_download_tail and action == action_download_tail:
                    item = self.table.item(row, 6)
                    if item:
                        data = item.data(Qt.UserRole)
                        if data and len(data) > 1 and data[1] and os.path.exists(data[1]):
                            self.download_image(data[1])
                
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

                elif action_clear_all_videos and action == action_clear_all_videos:
                     reply = QMessageBox.question(
                        None,
                        "确认清空",
                        "确定要清空所有视频吗？此操作不可撤销。",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                     if reply == QMessageBox.Yes:
                         self.clear_video_batch(range(self.table.rowCount()))
                
                elif 'action_download_video' in locals() and action_download_video and action == action_download_video:
                    # 尝试获取视频路径
                    video_path = None
                    
                    # 1. 优先尝试从控件获取当前选中的视频
                    widget = self.table.cellWidget(row, 9)
                    if widget and hasattr(widget, 'video_paths') and hasattr(widget, 'current_index'):
                        paths = widget.video_paths
                        idx = widget.current_index
                        if paths and isinstance(paths, list) and 0 <= idx < len(paths):
                            val = paths[idx]
                            if isinstance(val, str) and val:
                                video_path = val
                    
                    # 2. 如果没获取到，尝试从 Item Data 获取 (可能是单个字符串或列表)
                    if not video_path:
                        item = self.table.item(row, 9)
                        if item:
                            data = item.data(Qt.UserRole)
                            if isinstance(data, str) and data:
                                video_path = data
                            elif isinstance(data, list) and data:
                                # 默认取第一个有效路径
                                for p in data:
                                    if isinstance(p, str) and p:
                                        video_path = p
                                        break

                    if video_path and os.path.exists(video_path):
                        # 询问保存位置
                        default_name = os.path.basename(video_path)
                        dest_path, _ = QFileDialog.getSaveFileName(
                            self.container,
                            "保存视频",
                            default_name,
                            "MP4 Videos (*.mp4);;All Files (*)"
                        )
                        if dest_path:
                            try:
                                import shutil
                                shutil.copy2(video_path, dest_path)
                                QMessageBox.information(None, "完成", "视频已成功下载！")
                            except Exception as e:
                                QMessageBox.critical(None, "错误", f"下载失败: {e}")
                    else:
                         QMessageBox.warning(None, "提示", "未找到有效的视频文件。")

                # elif action == action_gen_all:
                #     self.open_storyboard_dialog(target_rows=None)

            def open_artboard(self, image_path, prompt=None, row_idx=None):
                """打开导演节点专用画板"""
                # 使用 self.proxy_widget.widget() 作为父窗口，确保对话框模态正确
                parent = self.proxy_widget.widget() if hasattr(self, 'proxy_widget') and self.proxy_widget else None
                
                def on_return_callback(new_path):
                    """当快捷画师请求返回图片到分镜图时回调"""
                    if row_idx is not None and new_path and os.path.exists(new_path):
                        print(f"[导演节点] 接收到快捷画师返回图片: {new_path} -> Row {row_idx}")
                        # 更新分镜图单元格
                        self.update_storyboard_cell(row_idx, new_path, prompt)
                        # 提示成功
                        from PySide6.QtWidgets import QMessageBox
                        # QMessageBox.information(parent, "提示", "已更新分镜图")
                        
                dialog = DirectorArtboardDialog(parent, image_path, prompt, on_return_callback)
                dialog.exec()

            def open_storyboard_dialog(self, target_rows=None):
                """打开分镜图生成对话框
                :param target_rows: 指定生成的行号列表，None表示生成所有行
                """
                print(f"[DEBUG] open_storyboard_dialog called. target_rows={target_rows}")

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
                    print("[DEBUG] Connection invalid or source socket missing")
                    QMessageBox.warning(None, "提示", "连接无效或源节点未找到！")
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
                    self.set_cell_images(r, 6, [])
                
                # 清空缓存
                self.storyboard_paths.clear()
                self.save_storyboard_paths()
                
                # 更新表格状态
                self.check_completion_and_update_columns()
                
                print("[导演节点] 已清空所有分镜图")
                QMessageBox.information(None, "完成", "所有分镜图已清空")

            def update_storyboard_cell(self, row_idx, image_path, prompt, shot_number=None):
                """分镜图生成完成回调，更新表格 - 使用 QTimer 确保主线程安全"""
                QTimer.singleShot(0, lambda: self._update_storyboard_cell_impl(row_idx, image_path, prompt, shot_number))

            def handle_storyboard_error(self, row_idx, error_msg):
                """分镜图生成失败回调"""
                QTimer.singleShot(0, lambda: self._handle_storyboard_error_impl(row_idx, error_msg))

            def _handle_storyboard_error_impl(self, row_idx, error_msg):
                try:
                    print(f"[ERROR] Storyboard generation failed for row {row_idx}: {error_msg}")
                    if row_idx < 0 or row_idx >= self.table.rowCount():
                        return
                    
                    item = self.table.item(row_idx, 6)
                    if not item:
                        item = QTableWidgetItem()
                        self.table.setItem(row_idx, 6, item)
                    
                    # Set failed status
                    item.setData(Qt.UserRole + 2, "failed")
                    item.setToolTip(f"生成失败: {error_msg}")
                    
                    # Force update
                    self.table.viewport().update()
                    
                except Exception as e:
                    print(f"[ERROR] _handle_storyboard_error_impl failed: {e}")

            def _update_storyboard_cell_impl(self, row_idx, image_path, prompt, shot_number=None):
                """分镜图生成完成回调，更新表格 (实现)"""
                try:
                    # 尝试根据 shot_number 修正 row_idx
                    if shot_number:
                         # 检查当前 row_idx 是否匹配
                         match = False
                         if 0 <= row_idx < self.table.rowCount():
                             item = self.table.item(row_idx, 0)
                             if item and item.text() == shot_number:
                                 match = True
                         
                         if not match:
                             print(f"[DEBUG] Row mismatch for shot {shot_number} at {row_idx}, searching...")
                             found = False
                             for r in range(self.table.rowCount()):
                                 item = self.table.item(r, 0)
                                 if item and item.text() == shot_number:
                                     row_idx = r
                                     found = True
                                     print(f"[DEBUG] Found shot {shot_number} at new row {row_idx}")
                                     break
                             
                                 if not found:
                                     print(f"[ERROR] Shot {shot_number} not found in table!")
                                     # 仍然保存到缓存
                                     # 针对批量生成逻辑，如果 count > 1，我们需要追加
                                     count = getattr(self, 'storyboard_batch_count', 1)
                                     if count > 1:
                                         current_list = self.storyboard_paths.get(shot_number, [])
                                         if not isinstance(current_list, list):
                                             current_list = [current_list] if current_list else []
                                         # 过滤 None 和 [None, None] 的情况
                                         current_list = [p for p in current_list if p]
                                         current_list.append(image_path)
                                         if len(current_list) > 8:
                                             current_list = current_list[-8:]
                                         self.storyboard_paths[shot_number] = current_list
                                     else:
                                         self.storyboard_paths[shot_number] = [image_path, None]
                                 
                                 self.save_storyboard_paths()
                                 return

                    if row_idx < 0 or row_idx >= self.table.rowCount():
                        return
                    
                    # 获取或创建分镜图单元格 (Col 6)
                    item = self.table.item(row_idx, 6)
                    if not item:
                        item = QTableWidgetItem()
                        self.table.setItem(row_idx, 6, item)
                    
                    # 检查是否为批量生成模式
                    count = getattr(self, 'storyboard_batch_count', 1)
                    
                    if count > 1:
                        # 批量模式：追加图片
                        old_data = item.data(Qt.UserRole)
                        current_paths = []
                        if old_data and isinstance(old_data, list):
                            # 过滤 None 值
                            current_paths = [p for p in old_data if p]
                        
                        if image_path and os.path.exists(image_path):
                            current_paths.append(image_path)
                            if len(current_paths) > 8:
                                current_paths = current_paths[-8:]
                            # 设置回去
                            item.setData(Qt.UserRole, current_paths)
                            item.setToolTip("")
                            item.setData(Qt.UserRole + 2, None)
                            item.setData(Qt.UserRole + 3, len(current_paths) - 1)
                    else:
                        # 默认模式：覆盖第一张 (Head)，保留第二张 (Tail)
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
                            item.setToolTip("")
                            
                            # 清除加载状态
                            item.setData(Qt.UserRole + 2, None)
                        
                    # 保存到缓存和文件
                    item_shot = self.table.item(row_idx, 0)
                    if item_shot:
                        shot_num = item_shot.text()
                        if shot_num:
                            # 重新获取最新数据以保存
                            final_data = item.data(Qt.UserRole)
                            self.storyboard_paths[shot_num] = final_data
                            self.save_storyboard_paths()
                    
                    # 强制刷新
                    self.table.viewport().update()
                    
                    # 检查是否全部完成
                    self.check_completion_and_update_columns()
                    
                except Exception as e:
                    print(f"[ERROR] update_storyboard_cell failed: {e}")
                    import traceback
                    traceback.print_exc()

            def on_storyboard_worker_finished(self):
                """分镜图生成线程完成回调"""
                worker = self.sender()
                # QApplication.restoreOverrideCursor()
                
                if worker in self.storyboard_workers:
                    self.storyboard_workers.remove(worker)
                    print(f"[Storyboard] Worker cleanup. Remaining: {len(self.storyboard_workers)}")
                
                # 安全删除
                worker.deleteLater()
            
            def on_sora_worker_finished(self):
                """视频生成线程完成回调"""
                worker = self.sender()
                
                if worker in self.sora_workers:
                    self.sora_workers.remove(worker)
                    print(f"[VideoGen] Worker cleanup. Remaining: {len(self.sora_workers)}")
                
                # 安全删除
                worker.deleteLater()

            def get_active_storyboard_image_info(self, row):
                item_sb = self.table.item(row, 6)
                if not item_sb:
                    return None, None
                data = item_sb.data(Qt.UserRole)
                if not data or not isinstance(data, list):
                    return None, None
                paths = [p for p in data if p]
                count = len(paths)
                if count == 0:
                    return None, None
                selected_index = item_sb.data(Qt.UserRole + 3)
                if not isinstance(selected_index, int) or selected_index < 0 or selected_index >= count:
                    if count >= 2:
                        show_tail = getattr(self, "show_tail_frame", False)
                        selected_index = 1 if show_tail else 0
                    else:
                        selected_index = 0
                path = None
                if 0 <= selected_index < count:
                    path = paths[selected_index]
                    if path and os.path.exists(path):
                        return path, selected_index
                for p in paths:
                    if p and os.path.exists(p):
                        return p, 0
                return None, None

            def get_active_storyboard_image_path(self, row):
                path, _ = self.get_active_storyboard_image_info(row)
                return path

            def generate_video_batch(self, rows):
                """批量生成视频"""
                if not rows: return
                
                # 获取生成数量
                gen_count = getattr(self, 'video_gen_count', 1)
                print(f"[电影院] 开始批量生成视频，涉及行数: {len(rows)}，每行生成数量: {gen_count}")

                # 获取API配置
                settings = QSettings("GhostOS", "App")
                api_provider = settings.value("api/video_provider", "Sora2")
                
                # === 获取谷歌剧本节点以提取内容提示词 ===
                google_node = None
                prompt_col_idx = -1
                
                if hasattr(self, 'input_sockets') and self.input_sockets:
                    socket = self.input_sockets[0]
                    if socket.connections:
                        connection = socket.connections[0]
                        if connection and connection.source_socket:
                            source_node = connection.source_socket.parent_node
                            if hasattr(source_node, 'node_title') and "谷歌剧本" in source_node.node_title:
                                google_node = source_node
                                
                                # 寻找提示词列
                                for c in range(google_node.table.columnCount()):
                                    header = google_node.table.horizontalHeaderItem(c)
                                    if header:
                                        header_text = header.text()
                                        if ("提示词" in header_text and "CN" in header_text) or \
                                           ("Painting Prompt" in header_text and "CN" in header_text):
                                            prompt_col_idx = c
                                            break
                
                if not google_node:
                    print("[VideoGen] 警告: 未连接谷歌剧本节点，只能使用动画片场提示词。")
                elif prompt_col_idx == -1:
                    print("[VideoGen] 警告: 在谷歌剧本节点中未找到 '提示词(CN)' 列。")

                # 获取全局附加视频提示词
                global_video_prompt = get_additional_prompt()
                if global_video_prompt:
                    print(f"[VideoGen] 加载全局附加视频提示词: {global_video_prompt}")

                # 准备任务桶，用于并发
                task_buckets = [[] for _ in range(gen_count)]
                has_tasks = False
                
                for r in rows:
                    image_path, sb_index = self.get_active_storyboard_image_info(r)
                    
                    if not image_path or not os.path.exists(image_path):
                        print(f"[VideoGen] 跳过第 {r+1} 行: 无分镜图")
                        continue

                    # === 构建完整提示词 ===
                    # 1. 动画片场 (Col 2) - 风格/环境
                    item_studio = self.table.item(r, 2)
                    studio_text = item_studio.text() if item_studio else ""
                    
                    # 2. 附加视频提示词 (Col 8) - 新增
                    item_video_prompt = self.table.item(r, 8)
                    video_prompt_text = item_video_prompt.text() if item_video_prompt else ""
                    
                    # 3. 组合提示词
                    # 用户要求: 附加视频提示词放在最前方，且不要原来的内容提示词
                    full_prompt = f"{video_prompt_text}\n{studio_text}".strip()
                    
                    # 4. 追加全局附加提示词
                    if global_video_prompt:
                        full_prompt = f"{full_prompt}\n{global_video_prompt}".strip()
                    
                    if not full_prompt:
                        print(f"[VideoGen] 跳过第 {r+1} 行: 无有效提示词 (缺少视频提示词或风格描述)")
                        continue
                    
                    # 镜头号
                    item_shot = self.table.item(r, 0)
                    shot_text = item_shot.text() if item_shot else str(r+1)
                    
                    # 准备任务
                    for i in range(gen_count):
                        task_buckets[i].append({
                            'row_idx': r,
                            'prompt': full_prompt,
                            'image_path': image_path,
                            'shot_number': shot_text
                        })
                        has_tasks = True

                    # Debug: 显示视频生成提示词
                    print(f"[VideoGen] 任务添加: 镜头 {shot_text}")
                    idx_display = 1
                    if isinstance(sb_index, int) and sb_index >= 0:
                        idx_display = sb_index + 1
                    print(f"[VideoGen] 行 {r+1} 使用分镜图编号: {idx_display}")
                    print(f"  - 图片: {image_path}")
                    print(f"  - 完整提示词: {full_prompt}")
                    
                    # 更新 UI 状态: 正在生成 (Col 9)
                    item = self.table.item(r, 9)
                    if not item:
                        item = QTableWidgetItem()
                        self.table.setItem(r, 9, item)
                    
                    # 移除现有的播放按钮（如果正在重新生成）
                    self.table.removeCellWidget(r, 9)
                    
                    # Store target count
                    item.setData(Qt.UserRole + 3, gen_count)
                    
                    # 设置生成中状态
                    status_text = "生成中..."
                    if gen_count > 1:
                        status_text = f"生成中 (0/{gen_count})"
                        # Show GridVideoWidget with placeholders immediately
                        display_list = [{'status': 'loading'}] * gen_count
                        self.set_cinema_cell_ui(r, display_list)
                        
                    item.setText(status_text)
                    item.setForeground(QColor("#4CAF50")) # Green
                    item.setData(Qt.UserRole + 2, "loading") # 设置加载状态
                    # Only update viewport if we didn't set a widget (single mode)
                    if gen_count == 1:
                        self.table.viewport().update()
                        
                    item.setToolTip("正在请求视频生成API...")
                    
                    # 清空该镜头的旧视频缓存
                    if shot_text in self.video_paths:
                         del self.video_paths[shot_text]
                         self.save_video_paths()
                
                if not has_tasks:
                    QMessageBox.warning(None, "提示", "所选行中没有符合生成条件的任务（需包含分镜图和提示词）。")
                    return
                
                app_root = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
                output_dir = os.path.join(app_root, "video")
                
                # 启动 Worker (支持并发)
                active_tasks = 0
                for i in range(gen_count):
                    tasks = task_buckets[i]
                    if tasks:
                        # 创建新 Worker
                        worker = Sora2Worker(api_provider, tasks, output_dir, parent=QApplication.instance())
                        worker.log_signal.connect(lambda msg: print(f"[VideoGen] {msg}"))
                        worker.video_completed.connect(self.update_cinema_cell)
                        worker.video_failed.connect(self.handle_video_error)
                        worker.finished.connect(self.on_sora_worker_finished)
                        
                        self.sora_workers.append(worker)
                        worker.start()
                        active_tasks += len(tasks)
                
                print(f"[导演节点] 已启动 {active_tasks} 个视频生成任务 ({api_provider})，并发 Worker 数: {gen_count}")

            def generate_video_for_row(self, r):
                """为指定行生成视频 (已弃用，保留兼容性，转发到 batch)"""
                self.generate_video_batch([r])

            def handle_video_error(self, row_idx, error_msg):
                """处理视频生成错误"""
                import datetime
                current_time = datetime.datetime.now().strftime("%H:%M:%S")
                print(f"[{current_time}] [VideoGen] Error at row {row_idx}: {error_msg}")

                if row_idx < 0 or row_idx >= self.table.rowCount():
                    return
                
                item = self.table.item(row_idx, 9)
                if not item:
                    item = QTableWidgetItem()
                    self.table.setItem(row_idx, 9, item)
                    
                # 移除可能存在的控件
                self.table.removeCellWidget(row_idx, 9)
                
                item.setText("生成失败")
                item.setForeground(QColor("red"))
                item.setToolTip(f"错误信息: {error_msg}")

            def on_sora2_clicked(self):
                """处理 SORA2 按钮点击事件"""
                row_count = self.table.rowCount()
                # 使用批量生成逻辑，传入所有行
                self.generate_video_batch(range(row_count))

            def get_connected_gacha_node(self):
                """获取连接的抽卡节点"""
                if not hasattr(self, 'output_sockets'):
                    return None
                    
                for socket in self.output_sockets:
                    # 查找连接到"视频输出"的接口
                    if socket.label == "视频输出":
                        for connection in socket.connections:
                            # connection.target_socket is the other end (Input)
                            other_socket = connection.target_socket
                            if other_socket and other_socket.parent_node:
                                node = other_socket.parent_node
                                if hasattr(node, 'node_title') and "抽卡节点" in node.node_title:
                                    return node
                return None

            def get_active_video_for_shot(self, shot_num):
                """获取指定镜头的当前选定视频"""
                # 1. 检查抽卡节点
                gacha_node = self.get_connected_gacha_node()
                if gacha_node and hasattr(gacha_node, 'selections'):
                    target_shot = self.normalize_shot_num(shot_num)
                    for k, v in gacha_node.selections.items():
                         if self.normalize_shot_num(k) == target_shot:
                             # Found selection index
                             paths = self.video_paths.get(shot_num)
                             if not paths: 
                                 # Try fuzzy match for paths
                                 for pk, pv in self.video_paths.items():
                                     if self.normalize_shot_num(pk) == target_shot:
                                         paths = pv
                                         break
                             
                             if paths and isinstance(paths, list) and 0 <= v < len(paths):
                                 return paths[v]
                
                # 2. 检查 UI 状态
                # Find row for shot_num
                row_idx = -1
                for r in range(self.table.rowCount()):
                    item = self.table.item(r, 0)
                    if item and self.normalize_shot_num(item.text()) == self.normalize_shot_num(shot_num):
                        row_idx = r
                        break
                
                if row_idx != -1:
                    widget = self.table.cellWidget(row_idx, 9)
                    if isinstance(widget, DraggableVideoWidget):
                         # If locked, use current index
                         if getattr(widget, 'lock_selection', False):
                             return widget.current_video_path
                
                # 3. 默认逻辑 (返回第一个或列表)
                if shot_num in self.video_paths:
                    val = self.video_paths[shot_num]
                    if isinstance(val, list) and val:
                        return val[0]
                    elif isinstance(val, str):
                        return val
                
                return None

            def get_current_selected_shot(self):
                """获取当前选中的镜头号"""
                row = self.table.currentRow()
                if row >= 0:
                    item = self.table.item(row, 0)
                    if item:
                        return item.text()
                return None



            def broadcast_video_change(self, shot_num, video_path):
                """广播视频变更到连接的节点"""
                # print(f"[导演节点] 广播视频变更: 镜头 {shot_num} -> {os.path.basename(video_path)}")
                if hasattr(self, 'output_sockets'):
                    for socket in self.output_sockets:
                        if socket.data_type == DataType.VIDEO:
                            for connection in socket.connections:
                                target_node = connection.target_socket.parent_node
                                if hasattr(target_node, 'on_director_video_change'):
                                     target_node.on_director_video_change(shot_num, video_path)

            def set_cinema_cell_ui(self, row_idx, video_path):
                """设置电影院单元格的 UI"""
                # 设置视频路径
                item = self.table.item(row_idx, 9)
                if not item:
                    item = QTableWidgetItem()
                    self.table.setItem(row_idx, 9, item)
                
                # 清除加载状态
                item.setData(Qt.UserRole + 2, None)
                
                # 获取镜号
                shot_num = str(row_idx + 1)
                item_shot = self.table.item(row_idx, 0)
                if item_shot:
                    shot_num = item_shot.text()

                # 检查抽卡节点
                gacha_node = self.get_connected_gacha_node()
                selected_index = 0
                lock_selection = False
                
                if gacha_node and hasattr(gacha_node, 'selections'):
                    # 尝试直接查找
                    if shot_num in gacha_node.selections:
                        selected_index = gacha_node.selections[shot_num]
                        lock_selection = True
                    else:
                        # 尝试模糊查找
                        target_shot = self.normalize_shot_num(shot_num)
                        for k, v in gacha_node.selections.items():
                            if self.normalize_shot_num(k) == target_shot:
                                selected_index = v
                                lock_selection = True
                                break
                    
                    if lock_selection:
                        # print(f"[导演节点] 应用抽卡节点选择: 镜头{shot_num} -> index {selected_index}")
                        pass
                
                # 检查当前控件是否无需更新
                current_widget = self.table.cellWidget(row_idx, 9)
                if isinstance(current_widget, DraggableVideoWidget):
                    # 比较路径是否一致
                    current_paths = current_widget.video_paths if isinstance(current_widget.video_paths, list) else [current_widget.video_paths]
                    new_paths = video_path if isinstance(video_path, list) else [video_path]
                    
                    if current_paths == new_paths:
                        # 路径一致，检查锁定状态
                        current_locked = getattr(current_widget, 'lock_selection', False)
                        
                        if lock_selection:
                            # 如果需要锁定，且当前已锁定且索引一致，则跳过
                            if current_locked and current_widget.current_index == selected_index:
                                return
                        else:
                            # 如果不需要锁定，且当前也未锁定，则跳过（保留用户当前的浏览位置）
                            if not current_locked:
                                return

                item.setText("")
                item.setToolTip(f"{video_path}")
                item.setData(Qt.UserRole, video_path) 
                
                # 统一使用 DraggableVideoWidget
                container = DraggableVideoWidget(
                    video_path, 
                    director_node=self,
                    initial_index=selected_index,
                    lock_selection=lock_selection,
                    on_video_change=lambda path, s=shot_num: self.broadcast_video_change(s, path)
                )
                
                self.table.setCellWidget(row_idx, 9, container)
                
                # 重新调整布局以适应可能的新列
                self.adjust_layout_to_size()

            def clear_video_batch(self, rows):
                """批量清空视频"""
                for r in rows:
                    # 清空单元格控件
                    self.table.removeCellWidget(r, 9)
                    item = self.table.item(r, 9)
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


            def normalize_shot_num(self, s):
                """标准化镜头号 (移除 shot_, 镜头 等前缀)"""
                return str(s).lower().replace('shot_', '').replace('镜头', '').strip()

            def refresh_cinema_cell(self, shot_num):
                """刷新指定镜头的电影院单元格"""
                target_shot = self.normalize_shot_num(shot_num)
                # print(f"[导演节点] 收到刷新请求: {shot_num} -> {target_shot}")
                
                for r in range(self.table.rowCount()):
                    item_shot = self.table.item(r, 0)
                    current_shot = str(r + 1)
                    if item_shot:
                        current_shot = item_shot.text()
                    
                    if self.normalize_shot_num(current_shot) == target_shot:
                        # print(f"[导演节点] 找到匹配行: {r}, 镜头: {current_shot}")
                        # 查找最新的视频数据
                        video_paths = []
                        # 尝试精确匹配
                        if current_shot in self.video_paths:
                            video_paths = self.video_paths[current_shot]
                        else:
                            # 尝试模糊匹配
                            for k, v in self.video_paths.items():
                                if self.normalize_shot_num(k) == target_shot:
                                    video_paths = v
                                    break
                        
                        self.set_cinema_cell_ui(r, video_paths)
                        break

            def handle_video_deleted(self, shot_num, video_path):
                """处理视频删除请求"""
                print(f"[导演节点] 收到视频删除请求: 镜头 {shot_num}, 路径 {video_path}")
                
                # 标准化镜头号查找
                target_shot = self.normalize_shot_num(shot_num)
                
                # 1. 更新数据缓存
                found_key = None
                if shot_num in self.video_paths:
                    found_key = shot_num
                else:
                    for k in self.video_paths:
                        if self.normalize_shot_num(k) == target_shot:
                            found_key = k
                            break
                
                if found_key:
                    paths = self.video_paths[found_key]
                    if isinstance(paths, list):
                        if video_path in paths:
                            paths.remove(video_path)
                            print(f"[导演节点] 已从缓存移除视频: {video_path}")
                            self.save_video_paths()
                            
                            # 2. 刷新 UI
                            self.refresh_cinema_cell(found_key)
                        else:
                            print(f"[导演节点] 警告: 视频路径不在缓存中: {video_path}")
                    else:
                        # 字符串情况 (旧数据)
                        if paths == video_path:
                            del self.video_paths[found_key]
                            self.save_video_paths()
                            self.refresh_cinema_cell(found_key)
                else:
                    print(f"[导演节点] 警告: 未找到镜头号对应的数据: {shot_num}")

            def update_cinema_cell(self, row_idx, video_path, shot_number=None, video_url=None, task_id=None):
                """视频生成完成回调，更新电影院列"""
                import datetime
                current_time = datetime.datetime.now().strftime("%H:%M:%S")
                print(f"[{current_time}] [电影院] 收到视频生成回调: 镜头={shot_number}, 行={row_idx}")
                print(f"  - 视频路径: {video_path}")
                print(f"  - URL: {video_url}")
                print(f"  - TaskID: {task_id}")
                
                # 1. 优先保存数据 (使用 shot_number)
                saved = False
                if shot_number:
                     if shot_number not in self.video_paths:
                         self.video_paths[shot_number] = []
                     
                     # 兼容旧数据 (如果是字符串，转为列表)
                     if isinstance(self.video_paths[shot_number], str):
                         self.video_paths[shot_number] = [self.video_paths[shot_number]]
                     
                     # 添加新视频
                     if video_path not in self.video_paths[shot_number]:
                         self.video_paths[shot_number].append(video_path)
                     
                     self.save_video_paths()
                     saved = True
                     
                     # 更新 video_path 为完整列表，以便 UI 显示
                     video_path = self.video_paths[shot_number]
                
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
                            
                            # Ensure list structure
                            if shot_num not in self.video_paths:
                                self.video_paths[shot_num] = []
                            if isinstance(self.video_paths[shot_num], str):
                                self.video_paths[shot_num] = [self.video_paths[shot_num]]
                            
                            if video_path not in self.video_paths[shot_num]:
                                self.video_paths[shot_num].append(video_path)
                                
                            self.save_video_paths()
                            
                            # Update video_path to the full list for UI display
                            video_path = self.video_paths[shot_num]
                
                # 5. 更新 UI
                # Check for target generation count to show placeholders
                item = self.table.item(row_idx, 9)
                display_data = video_path # Default to just the paths
                
                if item:
                    target_count = item.data(Qt.UserRole + 3)
                    if target_count and isinstance(target_count, int) and target_count > 1:
                        # If we have a target count, we might need to show placeholders
                        if isinstance(video_path, list) and len(video_path) < target_count:
                            display_data = list(video_path)
                            while len(display_data) < target_count:
                                display_data.append({'status': 'loading'})
                        elif isinstance(video_path, str):
                            # Should have been converted to list in Step 1/4, but just in case
                            display_data = [video_path]
                            while len(display_data) < target_count:
                                display_data.append({'status': 'loading'})

                self.set_cinema_cell_ui(row_idx, display_data)
                
                # Store Metadata for Sora Character creation
                if video_url and task_id:
                    item = self.table.item(row_idx, 9)
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
                        
                self.table.viewport().update()

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
                            
                            has_valid_video = False
                            if isinstance(video_path, list):
                                for p in video_path:
                                    if p and isinstance(p, str) and os.path.exists(p):
                                        has_valid_video = True
                                        break
                            elif video_path and isinstance(video_path, str) and os.path.exists(video_path):
                                has_valid_video = True
                                
                            if not has_valid_video:
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
                            
                            final_path = None
                            if isinstance(video_path, list):
                                for p in video_path:
                                    if p and isinstance(p, str) and os.path.exists(p):
                                        final_path = p
                                        break
                            elif video_path and isinstance(video_path, str) and os.path.exists(video_path):
                                final_path = video_path
                                
                            if final_path:
                                video_list.append(final_path)
                                print(f"[导演节点] 镜头 {shot_num}: {os.path.basename(final_path)}")
                
                print(f"[导演节点] 排序后的视频列表: 共 {len(video_list)} 个视频")
                return video_list

            def run_storyboard_generation(self, mode, google_node, target_rows=None):
                """执行分镜图生成"""
                print(f"[导演节点] 开始生成分镜图，模式: {mode}")
                
                try:
                    cursor_set = False
                    # 1. 获取谷歌节点提示词列索引
                    prompt_col_idx = -1
                    print(f"[DEBUG] Google Node: {google_node}, Table: {google_node.table}, Cols: {google_node.table.columnCount()}")
                    
                    # 加载附加图片提示词
                    img_prompt_manager = AdditionalImagePromptManager()
                    additional_img_prompt = img_prompt_manager.load_prompt()
                    if additional_img_prompt:
                        print(f"[导演节点] 加载附加图片提示词: {additional_img_prompt}")

                    for c in range(google_node.table.columnCount()):
                        header = google_node.table.horizontalHeaderItem(c)
                        if not header:
                            continue
                        header_text = header.text()
                        # 兼容多种写法：带空格、全角括号等
                        if ("提示词" in header_text and "CN" in header_text) or \
                           ("Painting Prompt" in header_text and "CN" in header_text):
                            prompt_col_idx = c
                            print(f"[DEBUG] Found prompt column at index {c}: {header_text}")
                            break
                    
                    if prompt_col_idx == -1:
                        print("[DEBUG] Prompt column not found!")
                        QMessageBox.warning(None, "提示", f"在谷歌剧本节点中未找到 '提示词(CN)' 相关列！\n请检查列名是否包含 '提示词' 和 'CN'。")
                        return

                    # 2. 收集任务数据
                    tasks = []
                    row_count = self.table.rowCount()
                    print(f"[DEBUG] Row count: {row_count}, Target rows: {target_rows}")
                    
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
                        
                        def extract_paths(data):
                            extracted = []
                            if data:
                                if isinstance(data, list):
                                    for item in data:
                                        if isinstance(item, dict):
                                            if "path" in item: extracted.append(item["path"])
                                        elif isinstance(item, str):
                                            extracted.append(item)
                                elif isinstance(data, str):
                                    extracted.append(data)
                            return extracted

                        # Character (Col 3)
                        item_char = self.table.item(r, 3)
                        if item_char:
                            images.extend(extract_paths(item_char.data(Qt.UserRole)))
                        
                        # Props (Col 4) - 添加道具图片作为参考图
                        item_prop = self.table.item(r, 4)
                        if item_prop:
                            images.extend(extract_paths(item_prop.data(Qt.UserRole)))
                            
                        # Scene (Col 5)
                        item_scene = self.table.item(r, 5)
                        if item_scene:
                            images.extend(extract_paths(item_scene.data(Qt.UserRole)))
                        
                        # 去重且过滤无效路径
                        images = list(dict.fromkeys([p for p in images if p and isinstance(p, str) and os.path.exists(p)]))
                        
                        # 获取谷歌节点对应的提示词
                        # 假设行号一一对应
                        google_prompt = ""
                        if r < google_node.table.rowCount():
                            item_p = google_node.table.item(r, prompt_col_idx)
                            if item_p:
                                google_prompt = item_p.text()

                        # 获取导演界面图片提示词 (Col 7)
                        item_img_prompt = self.table.item(r, 7)
                        director_img_prompt = item_img_prompt.text() if item_img_prompt else ""
                        
                        # 获取附加视频提示词 (Col 8)
                        item_video_prompt = self.table.item(r, 8)
                        video_prompt_text = item_video_prompt.text() if item_video_prompt else ""
                        
                        # 优先使用导演界面的图片提示词，如果没有则使用谷歌节点的提示词
                        main_prompt = director_img_prompt if director_img_prompt.strip() else google_prompt
                        
                        if not main_prompt and not studio_text:
                            print(f"[导演节点] 跳过第 {r+1} 行: 无提示词")
                            continue
                            
                        # 组合提示词
                        # 如果有道具提示词，将其放在最前面
                        prop_prompt = ""
                        if shot_text in self.props_prompts:
                            prop_prompt = self.props_prompts[shot_text]
                        
                        if prop_prompt:
                            combined_prompt = f"{prop_prompt}\n{main_prompt}\n{studio_text}".strip()
                        else:
                            combined_prompt = f"{main_prompt}\n{studio_text}".strip()
                        
                        # 如果有附加视频提示词 (Col 8)，先加上
                        if video_prompt_text:
                            combined_prompt = f"{video_prompt_text}\n{combined_prompt}".strip()
                        
                        # 如果有附加图片提示词，放在最前面 (最高优先级)
                        if additional_img_prompt:
                            combined_prompt = f"{additional_img_prompt}\n{combined_prompt}".strip()
                        
                        tasks.append({
                            'row_idx': r,
                            'prompt': combined_prompt,
                            'images': images,
                            'mode': mode,
                            'shot_number': shot_text
                        })
                        
                        # 设置加载状态
                        item = self.table.item(r, 6)
                        if not item:
                            item = QTableWidgetItem()
                            self.table.setItem(r, 6, item)
                        item.setData(Qt.UserRole + 2, "loading")
                    
                    print(f"[DEBUG] Collected {len(tasks)} tasks")
                    
                    if not tasks:
                        QMessageBox.warning(None, "提示", "没有可生成的任务（可能是缺少提示词或数据为空）。")
                        return

                    # 3. 启动 Worker
                    settings = QSettings("GhostOS", "App")
                    image_api = settings.value("api/image_provider", "BANANA")
                    print(f"[DEBUG] API Provider: {image_api}")
                    
                    app_root = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
                    config_file = ""
                    if image_api == "BANANA":
                        config_file = os.path.join(app_root, "json", "gemini.json")
                    elif image_api == "BANANA2":
                        config_file = os.path.join(app_root, "json", "gemini30.json")
                    elif image_api == "Midjourney":
                        config_file = os.path.join(app_root, "json", "mj.json")
                    
                    print(f"[DEBUG] Config file: {config_file}")
                    
                    self.storyboard_worker = StoryboardWorker(image_api, config_file, tasks, os.path.join("jpg", "storyboard_output"), parent=None)
                    
                    # === 终极修复：使用 QApplication 实例的自定义属性来持有 worker 引用 ===
                    # 这样可以确保 worker 与应用程序生命周期一致，彻底防止 GC 回收导致的崩溃
                    app = QApplication.instance()
                    if not hasattr(app, '_active_storyboard_workers'):
                        app._active_storyboard_workers = []
                    app._active_storyboard_workers.append(self.storyboard_worker)
                    
                    # 同时保留在本地列表中（双重保险）
                    self.storyboard_workers.append(self.storyboard_worker)
                    
                    self.storyboard_worker.log_signal.connect(lambda msg: print(f"[Storyboard] {msg}"))
                    self.storyboard_worker.error_occurred.connect(lambda err: QMessageBox.critical(None, "分镜图生成错误", err))
                    self.storyboard_worker.task_failed.connect(self.handle_storyboard_error)
                    self.storyboard_worker.image_completed.connect(self.update_storyboard_cell)
                    
                    # 移除等待光标，避免界面卡顿
                    # QApplication.setOverrideCursor(Qt.WaitCursor)
                    cursor_set = False
                    
                    # 定义清理函数
                    def cleanup_worker(worker=self.storyboard_worker):
                        print(f"[Cleanup] Cleaning up worker {worker}")
                        try:
                            # 从 app 全局列表移除
                            app = QApplication.instance()
                            if hasattr(app, '_active_storyboard_workers') and worker in app._active_storyboard_workers:
                                app._active_storyboard_workers.remove(worker)
                            # 从本地列表移除
                            if worker in self.storyboard_workers:
                                self.storyboard_workers.remove(worker)
                            # 触发 deleteLater
                            worker.deleteLater()
                        except Exception as e:
                            print(f"[Cleanup] Error: {e}")

                    # 连接 finished 信号到清理函数
                    self.storyboard_worker.finished.connect(cleanup_worker)
                    
                    self.storyboard_worker.start()
                    
                    # 非阻塞提示 (仅打印日志，避免阻塞UI)
                    print(f"[提示] 已启动 {len(tasks)} 个分镜图生成任务！")
                    # 如果需要反馈，可以在状态栏显示，或者使用非模态提示
                    # QMessageBox.information(None, "提示", ...) # 已移除以防止阻塞
                    
                except Exception as e:
                    if cursor_set:
                        QApplication.restoreOverrideCursor()
                    print(f"[ERROR] run_storyboard_generation failed: {e}")
                    import traceback
                    traceback.print_exc()
                    QMessageBox.critical(None, "错误", f"分镜图生成出错: {e}")

            def run_sequential_storyboard_generation(self, row):
                """运行连贯分镜生成 (参考上一镜)"""
                if row <= 0:
                    QMessageBox.warning(None, "提示", "第一行无法生成连贯分镜（无上一镜）。")
                    return

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
                    QMessageBox.warning(None, "提示", "连接无效或源节点未找到！")
                    return
                
                google_node = connection.source_socket.parent_node
                if not hasattr(google_node, 'node_title') or "谷歌剧本" not in google_node.node_title:
                    QMessageBox.warning(None, "提示", "连接的节点不是谷歌剧本节点！")
                    return

                # 2. 获取上一镜的分镜图
                prev_row = row - 1
                prev_item = self.table.item(prev_row, 6)
                prev_images = []
                if prev_item:
                    data = prev_item.data(Qt.UserRole)
                    if data and isinstance(data, list):
                        prev_images = data
                
                if not prev_images:
                    QMessageBox.warning(None, "提示", "上一镜没有分镜图，无法参考。")
                    return

                # 取最后一格 (寻找最后一个有效的图片路径)
                ref_image = None
                for img in reversed(prev_images):
                    if img and isinstance(img, str) and os.path.exists(img):
                        ref_image = img
                        break
                
                if not ref_image:
                    QMessageBox.warning(None, "提示", "上一镜没有有效的分镜图文件。")
                    return
                
                # 弹出分镜图生成选择面板
                dialog = StoryboardDialog(self.container)
                dialog.load_settings()
                if not dialog.exec():
                    return
                selected_mode = dialog.selection
                
                # 2.5 收集当前行的人物、道具、场景图片
                aux_images = []
                
                def extract_paths(data):
                    extracted = []
                    if data:
                        if isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict):
                                    if "path" in item: extracted.append(item["path"])
                                elif isinstance(item, str):
                                    extracted.append(item)
                        elif isinstance(data, str):
                            extracted.append(data)
                    return extracted

                # Character (Col 3)
                item_char = self.table.item(row, 3)
                if item_char:
                    aux_images.extend(extract_paths(item_char.data(Qt.UserRole)))
                
                # Props (Col 4)
                item_prop = self.table.item(row, 4)
                if item_prop:
                    aux_images.extend(extract_paths(item_prop.data(Qt.UserRole)))
                    
                # Scene (Col 5)
                item_scene = self.table.item(row, 5)
                if item_scene:
                    aux_images.extend(extract_paths(item_scene.data(Qt.UserRole)))
                
                # 去重且过滤无效路径
                aux_images = list(dict.fromkeys([p for p in aux_images if p and isinstance(p, str) and os.path.exists(p)]))
                
                print(f"[DEBUG] 收集到的辅助参考图 (人物/道具/场景): {aux_images}")
                
                # 3. 获取当前行的提示词
                # 寻找提示词列
                prompt_col_idx = -1
                for c in range(google_node.table.columnCount()):
                    header = google_node.table.horizontalHeaderItem(c)
                    if header:
                        header_text = header.text()
                        if ("提示词" in header_text and "CN" in header_text) or \
                           ("Painting Prompt" in header_text and "CN" in header_text):
                            prompt_col_idx = c
                            break
                
                if prompt_col_idx == -1:
                    QMessageBox.warning(None, "提示", "未找到提示词列(CN)。")
                    return

                # 获取提示词
                google_prompt = ""
                if row < google_node.table.rowCount():
                    item_p = google_node.table.item(row, prompt_col_idx)
                    if item_p:
                        google_prompt = item_p.text()
                
                # 获取导演界面图片提示词 (Col 7)
                item_img_prompt = self.table.item(row, 7)
                director_img_prompt = item_img_prompt.text() if item_img_prompt else ""
                
                main_prompt = director_img_prompt if director_img_prompt.strip() else google_prompt
                
                # 动画片场 (Prompt Context)
                item_studio = self.table.item(row, 2)
                studio_text = item_studio.text() if item_studio else ""
                
                combined_prompt = f"{main_prompt}\n{studio_text}".strip()
                
                # 获取附加图片提示词
                additional_img_prompt = AdditionalImagePromptManager().load_prompt()
                if additional_img_prompt:
                    print(f"[连贯分镜] 加载附加图片提示词: {additional_img_prompt}")
                    # combined_prompt = f"{additional_img_prompt}\n{combined_prompt}".strip()
                    # 改为不合并，而是作为独立参数传递，以便在Worker中精确控制位置
                
                # 4. 准备任务
                item_shot = self.table.item(row, 0)
                shot_text = item_shot.text() if item_shot else str(row+1)
                
                # 合并图片：上一镜分镜图作为第一张，后面跟辅助图
                final_images = [ref_image] + aux_images
                
                print(f"[DEBUG] === 连贯分镜生成任务 (Row {row}) ===")
                print(f"[DEBUG] 提示词:\n{combined_prompt}")
                print(f"[DEBUG] 附加提示词: {additional_img_prompt}")
                print(f"[DEBUG] 发送图片列表 ({len(final_images)} 张):")
                for i, img_path in enumerate(final_images):
                    role = "参考图1 (上一镜分镜)" if i == 0 else f"辅助参考图 {i}"
                    print(f"  [{i}] {role}: {img_path}")
                print("===========================================")
                
                task = {
                    'row_idx': row,
                    'prompt': combined_prompt,
                    'additional_prompt': additional_img_prompt, # 新增字段
                    'images': final_images, # 传入所有参考图
                    'mode': selected_mode,
                    'shot_number': shot_text
                }
                
                # 设置加载状态
                item = self.table.item(row, 6)
                if not item:
                    item = QTableWidgetItem()
                    self.table.setItem(row, 6, item)
                item.setData(Qt.UserRole + 2, "loading")
                self.table.viewport().update()
                
                # 5. 配置并启动 Worker
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
                
                # 实例化 ImageToImageWorker
                batch_count = getattr(self, "storyboard_batch_count", 1)
                if batch_count < 1:
                    batch_count = 1
                tasks = [dict(task) for _ in range(batch_count)]
                self.seq_storyboard_worker = ImageToImageWorker(
                    image_api,
                    config_file,
                    tasks,
                    os.path.join("jpg", "storyboard_output"),
                    parent=None,
                )
                
                # === 注册到全局 Application 防止 GC ===
                app = QApplication.instance()
                if not hasattr(app, '_active_img2img_workers'):
                    app._active_img2img_workers = []
                app._active_img2img_workers.append(self.seq_storyboard_worker)
                
                self.seq_storyboard_worker.log_signal.connect(lambda msg: print(f"[SeqStoryboard] {msg}"))
                self.seq_storyboard_worker.error_occurred.connect(lambda err: QMessageBox.critical(None, "生成错误", err))
                self.seq_storyboard_worker.task_failed.connect(self.handle_storyboard_error)
                # 复用 update_storyboard_cell 来更新界面
                self.seq_storyboard_worker.image_completed.connect(self.update_storyboard_cell)
                
                def cleanup_worker(worker=self.seq_storyboard_worker):
                    print(f"[Cleanup] Cleaning up sequential worker {worker}")
                    try:
                        app = QApplication.instance()
                        if hasattr(app, '_active_img2img_workers') and worker in app._active_img2img_workers:
                            app._active_img2img_workers.remove(worker)
                        worker.deleteLater()
                    except Exception as e:
                        print(f"[Cleanup] Error: {e}")

                self.seq_storyboard_worker.finished.connect(cleanup_worker)
                
                self.seq_storyboard_worker.start()
                QMessageBox.information(None, "提示", "已启动连贯分镜生成任务！")

            def create_sora_character(self, row):
                """创建Sora角色"""
                print(f"[CreateSoraChar] 开始创建角色 - 行号: {row}")
                item = self.table.item(row, 9)
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
