"""
动作库管理窗口
支持分组管理动作参考图片
数据保存在 JSON/pose_library.json
图片保存在 JSON/historyJPG/ 目录
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QScrollArea, QGridLayout,
    QLineEdit, QMessageBox, QFileDialog, QDialog, QDialogButtonBox,
    QFrame, QMenu
)
from PySide6.QtCore import Qt, Signal, QSize, QPointF
from PySide6.QtGui import QPixmap, QIcon, QImage, QAction, QPainter, QColor, QPen, QBrush, QPainterPath, QFont
import json
import os
import sys
import shutil
import numpy as np
from datetime import datetime


def create_vector_icon(icon_type, size=48, bg_color=None, fg_color=None):
    """创建矢量图标
    
    Args:
        icon_type: 图标类型 ('add', 'delete', 'edit', 'folder', 'image', 'camera')
        size: 图标尺寸
        bg_color: 背景色 (QColor或None)
        fg_color: 前景色 (QColor)
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    
    # 如果有背景色，绘制圆角矩形背景
    if bg_color:
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, size, size, size * 0.2, size * 0.2)
    
    # 设置前景色
    if fg_color:
        painter.setPen(QPen(fg_color, size * 0.08, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    else:
        painter.setPen(QPen(QColor("#ffffff"), size * 0.08, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    
    # 绘制不同类型的图标
    center = size / 2
    padding = size * 0.25
    
    if icon_type == 'add':
        # ➕ 加号
        painter.drawLine(int(center), int(padding), int(center), int(size - padding))
        painter.drawLine(int(padding), int(center), int(size - padding), int(center))
    
    elif icon_type == 'delete':
        # 🗑️ 垃圾桶
        # 顶部盖子
        painter.drawLine(int(padding * 0.8), int(padding * 1.2), int(size - padding * 0.8), int(padding * 1.2))
        # 主体
        path = QPainterPath()
        path.moveTo(padding, padding * 1.5)
        path.lineTo(padding, size - padding)
        path.lineTo(size - padding, size - padding)
        path.lineTo(size - padding, padding * 1.5)
        path.closeSubpath()
        painter.drawPath(path)
        # 竖线
        painter.drawLine(int(center), int(padding * 1.8), int(center), int(size - padding * 1.3))
        painter.drawLine(int(padding * 1.5), int(padding * 1.8), int(padding * 1.5), int(size - padding * 1.3))
        painter.drawLine(int(size - padding * 1.5), int(padding * 1.8), int(size - padding * 1.5), int(size - padding * 1.3))
    
    elif icon_type == 'edit':
        # ✏️ 铅笔
        path = QPainterPath()
        path.moveTo(size - padding * 0.8, padding * 0.8)
        path.lineTo(size - padding * 1.5, padding * 1.5)
        path.lineTo(padding * 1.2, size - padding * 0.8)
        path.lineTo(padding * 0.8, size - padding * 1.2)
        path.closeSubpath()
        painter.drawPath(path)
        # 笔尖
        painter.drawLine(int(padding * 0.8), int(size - padding * 1.2), int(padding), int(size - padding))
    
    elif icon_type == 'folder':
        # 📁 文件夹
        path = QPainterPath()
        path.moveTo(padding, padding * 1.5)
        path.lineTo(padding, size - padding)
        path.lineTo(size - padding, size - padding)
        path.lineTo(size - padding, padding * 2)
        path.lineTo(center, padding * 2)
        path.lineTo(center - padding * 0.5, padding * 1.5)
        path.closeSubpath()
        painter.drawPath(path)
    
    elif icon_type == 'image':
        # 🖼️ 图片
        painter.drawRoundedRect(int(padding), int(padding), int(size - padding * 2), int(size - padding * 2), size * 0.08, size * 0.08)
        # 山峰
        path = QPainterPath()
        path.moveTo(padding * 1.3, size - padding * 1.3)
        path.lineTo(center - padding * 0.3, center + padding * 0.2)
        path.lineTo(center + padding * 0.5, size - padding * 1.3)
        painter.drawPath(path)
        # 太阳
        painter.setBrush(QBrush(fg_color if fg_color else QColor("#ffffff")))
        painter.drawEllipse(int(size - padding * 2.5), int(padding * 1.5), int(padding * 0.8), int(padding * 0.8))
    
    elif icon_type == 'camera':
        # 📷 相机
        # 机身
        painter.drawRoundedRect(int(padding), int(padding * 1.5), int(size - padding * 2), int(size - padding * 2.5), size * 0.1, size * 0.1)
        # 取景器
        painter.drawRoundedRect(int(center - padding * 0.5), int(padding * 0.8), int(padding), int(padding * 0.5), size * 0.05, size * 0.05)
        # 镜头
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(int(center - padding), int(center - padding * 0.5), int(padding * 2), int(padding * 2))
        painter.drawEllipse(int(center - padding * 0.6), int(center - padding * 0.1), int(padding * 1.2), int(padding * 1.2))
    
    painter.end()
    return QIcon(pixmap)


class AddGroupDialog(QDialog):
    """添加/编辑分组对话框"""
    
    def __init__(self, parent=None, group_name=""):
        super().__init__(parent)
        self.setWindowTitle("分组名称" if not group_name else "编辑分组")
        self.setModal(True)
        self.resize(300, 120)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 标签
        label = QLabel("请输入分组名称：")
        label.setStyleSheet("color: #dfe3ea; font-size: 13px;")
        layout.addWidget(label)
        
        # 输入框
        self.input = QLineEdit()
        self.input.setText(group_name)
        self.input.setPlaceholderText("例如：站立姿势、坐姿、跑步...")
        self.input.setStyleSheet("""
            QLineEdit {
                background: #2a2a2a;
                color: #ffffff;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 8px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #4CAF50;
            }
        """)
        layout.addWidget(self.input)
        
        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 20px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #4a4a4a;
            }
        """)
        layout.addWidget(buttons)
        
        self.setStyleSheet("QDialog { background: #1a1a1a; }")
    
    def get_group_name(self):
        """获取输入的分组名称"""
        return self.input.text().strip()


class PoseCard(QFrame):
    """动作图片卡片"""
    
    delete_requested = Signal(str)  # 删除信号，传递图片路径
    pose_apply_requested = Signal(str)  # 应用姿势信号，传递图片路径
    
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.setObjectName("PoseCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(150, 180)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # 图片显示区域
        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(140, 140)
        self.thumbnail.setAlignment(Qt.AlignCenter)
        self.thumbnail.setStyleSheet("""
            QLabel {
                background: #0f0f10;
                border: 1px solid #2a2d31;
                border-radius: 6px;
            }
        """)
        
        # 加载缩略图
        self._load_thumbnail()
        
        # 文件名标签
        filename = os.path.basename(image_path)
        if len(filename) > 15:
            filename = filename[:12] + "..."
        
        self.name_label = QLabel(filename)
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setStyleSheet("color: #9aa0a6; font-size: 11px;")
        self.name_label.setWordWrap(True)
        
        layout.addWidget(self.thumbnail)
        layout.addWidget(self.name_label)
        
        # 样式
        self.setStyleSheet("""
            #PoseCard {
                background: #1a1a1a;
                border: 1px solid #2a2d31;
                border-radius: 8px;
            }
            #PoseCard:hover {
                background: #212225;
                border: 1px solid #4CAF50;
            }
        """)
    
    def _load_thumbnail(self):
        """加载缩略图"""
        if os.path.exists(self.image_path):
            pixmap = QPixmap(self.image_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.thumbnail.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.thumbnail.setPixmap(scaled)
            else:
                # 显示矢量占位图标 - 无法加载
                icon = create_vector_icon('image', size=64, fg_color=QColor("#9aa0a6"))
                self.thumbnail.setPixmap(icon.pixmap(64, 64))
        else:
            # 显示矢量占位图标 - 文件缺失
            icon = create_vector_icon('image', size=64, fg_color=QColor("#ef4444"))
            self.thumbnail.setPixmap(icon.pixmap(64, 64))
    
    def mousePressEvent(self, event):
        """点击应用动作姿势"""
        if event.button() == Qt.LeftButton:
            if os.path.exists(self.image_path):
                # 发送应用姿势信号
                self.pose_apply_requested.emit(self.image_path)
                print(f'[动作库] 应用姿势: {self.image_path}', flush=True)
        super().mousePressEvent(event)
    
    def contextMenuEvent(self, event):
        """右键菜单"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #2a2a2a;
                color: #ffffff;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 30px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background: #4CAF50;
            }
        """)
        
        # 应用姿势菜单项
        apply_action = menu.addAction("应用姿势")
        apply_action.setIcon(create_vector_icon('image', size=20, fg_color=QColor("#4CAF50")))
        
        # 查看原图菜单项
        view_action = menu.addAction("查看原图")
        view_action.setIcon(create_vector_icon('camera', size=20, fg_color=QColor("#9aa0a6")))
        
        # 删除菜单项
        delete_action = menu.addAction("删除")
        delete_action.setIcon(create_vector_icon('delete', size=20, fg_color=QColor("#ef4444")))
        
        action = menu.exec_(event.globalPos())
        
        if action == apply_action:
            # 应用姿势
            if os.path.exists(self.image_path):
                self.pose_apply_requested.emit(self.image_path)
                print(f'[动作库] 右键应用姿势: {self.image_path}', flush=True)
        
        elif action == view_action:
            # 查看原图
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            if os.path.exists(self.image_path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(self.image_path))
                print(f'[动作库] 查看原图: {self.image_path}', flush=True)
        
        elif action == delete_action:
            # 删除
            reply = QMessageBox.question(
                self,
                "确认删除",
                f"确定要删除这张图片吗？\n\n{os.path.basename(self.image_path)}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.delete_requested.emit(self.image_path)


class PoseLibraryWindow(QMainWindow):
    """动作库主窗口"""
    
    pose_apply_requested = Signal(str)  # 应用姿势信号，传递图片路径到PhotoPage
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("动作库管理")
        self.resize(900, 600)
        self.setWindowFlags(Qt.Window)
        
        # 数据路径
        self.data_file = self._get_data_path()
        self.image_dir = self._get_image_dir()
        
        # 当前选中的分组
        self.current_group = None
        
        # 加载数据
        self.data = self._load_data()
        
        self.init_ui()
        self.apply_stylesheet()
        
        # 如果有分组，默认选中第一个
        if self.data['groups']:
            self.group_list.setCurrentRow(0)
            self.current_group = self.data['groups'][0]['name']
            self._load_poses_for_group(self.current_group)
    
    def init_ui(self):
        """初始化UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 左侧：分组列表
        left_panel = self._create_left_panel()
        main_layout.addWidget(left_panel)
        
        # 右侧：图片网格
        right_panel = self._create_right_panel()
        main_layout.addWidget(right_panel, 1)
    
    def _create_left_panel(self):
        """创建左侧分组面板"""
        panel = QFrame()
        panel.setObjectName("LeftPanel")
        panel.setFixedWidth(220)
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # 标题
        title = QLabel("分组管理")
        title.setStyleSheet("color: #4CAF50; font-size: 14px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # 分隔线
        separator = QWidget()
        separator.setFixedHeight(2)
        separator.setStyleSheet("background: #4CAF50;")
        layout.addWidget(separator)
        
        # 分组列表
        self.group_list = QListWidget()
        self.group_list.setStyleSheet("""
            QListWidget {
                background: #0f0f10;
                border: 1px solid #2a2d31;
                border-radius: 4px;
                color: #ffffff;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #1a1a1a;
            }
            QListWidget::item:selected {
                background: #4CAF50;
            }
            QListWidget::item:hover {
                background: #2a2a2a;
            }
        """)
        self.group_list.currentRowChanged.connect(self._on_group_changed)
        layout.addWidget(self.group_list, 1)
        
        # 刷新分组列表
        self._refresh_group_list()
        
        # 按钮区域
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(8)
        
        # 添加分组按钮
        btn_add_group = QPushButton(" 新建分组")
        btn_add_group.setIcon(create_vector_icon('add', size=24, fg_color=QColor("#4a9e4a")))
        btn_add_group.setIconSize(QSize(24, 24))
        btn_add_group.setStyleSheet(self._get_button_style("#2a4a2a", "#4a9e4a"))
        btn_add_group.clicked.connect(self._add_group)
        btn_layout.addWidget(btn_add_group)
        
        # 重命名分组按钮
        btn_rename_group = QPushButton(" 重命名")
        btn_rename_group.setIcon(create_vector_icon('edit', size=24, fg_color=QColor("#4a7a9e")))
        btn_rename_group.setIconSize(QSize(24, 24))
        btn_rename_group.setStyleSheet(self._get_button_style("#2a3a4a", "#4a7a9e"))
        btn_rename_group.clicked.connect(self._rename_group)
        btn_layout.addWidget(btn_rename_group)
        
        # 删除分组按钮
        btn_delete_group = QPushButton(" 删除分组")
        btn_delete_group.setIcon(create_vector_icon('delete', size=24, fg_color=QColor("#9e4a4a")))
        btn_delete_group.setIconSize(QSize(24, 24))
        btn_delete_group.setStyleSheet(self._get_button_style("#4a2a2a", "#9e4a4a", "#5a3a3a"))
        btn_delete_group.clicked.connect(self._delete_group)
        btn_layout.addWidget(btn_delete_group)
        
        layout.addLayout(btn_layout)
        
        return panel
    
    def _create_right_panel(self):
        """创建右侧图片网格面板"""
        panel = QFrame()
        panel.setObjectName("RightPanel")
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # 顶部工具栏
        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(10)
        
        self.group_title = QLabel("请选择分组")
        self.group_title.setStyleSheet("color: #dfe3ea; font-size: 16px; font-weight: bold;")
        toolbar_layout.addWidget(self.group_title)
        
        toolbar_layout.addStretch()
        
        # 添加图片按钮
        btn_add_image = QPushButton(" 添加图片")
        btn_add_image.setIcon(create_vector_icon('camera', size=24, fg_color=QColor("#4a9e4a")))
        btn_add_image.setIconSize(QSize(24, 24))
        btn_add_image.setStyleSheet("""
            QPushButton {
                background: #2a4a2a;
                color: #ffffff;
                border: 1px solid #4a9e4a;
                border-radius: 4px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #3a5a3a;
                border: 1px solid #5aae5a;
            }
            QPushButton:pressed {
                background: #1a3a1a;
            }
        """)
        btn_add_image.clicked.connect(self._add_images)
        toolbar_layout.addWidget(btn_add_image)
        
        layout.addWidget(toolbar)
        
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea {
                background: #0f0f10;
                border: 1px solid #2a2d31;
                border-radius: 4px;
            }
            QScrollBar:vertical {
                background: #1a1a1a;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #3a3a3a;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #4a4a4a;
            }
        """)
        
        # 网格容器
        grid_container = QWidget()
        grid_container.setStyleSheet("background: #0f0f10;")
        self.grid_layout = QGridLayout(grid_container)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.grid_layout.setSpacing(15)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        scroll.setWidget(grid_container)
        layout.addWidget(scroll, 1)
        
        return panel
    
    def _get_button_style(self, bg_color, border_color, hover_bg_color=None):
        if not hover_bg_color:
            try:
                c = QColor(bg_color)
                hover_bg_color = c.lighter(115).name() if c.isValid() else bg_color
            except Exception:
                hover_bg_color = bg_color
        return f"""
            QPushButton {{
                background: {bg_color};
                color: #ffffff;
                border: 1px solid {border_color};
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
                text-align: left;
            }}
            QPushButton:hover {{
                background: {hover_bg_color};
                border: 1px solid {border_color};
            }}
            QPushButton:pressed {{
                background: {bg_color};
                border: 1px solid {border_color};
            }}
        """
    
    def _get_data_path(self):
        """获取数据文件路径"""
        try:
            if getattr(sys, 'frozen', False):
                app_root = os.path.dirname(sys.executable)
            else:
                app_root = os.path.dirname(os.path.abspath(__file__))
            
            json_dir = os.path.join(app_root, 'json')
            os.makedirs(json_dir, exist_ok=True)
            return os.path.join(json_dir, 'pose_library.json')
        except Exception as e:
            print(f'[动作库] 获取数据路径失败: {e}', flush=True)
            return 'pose_library.json'
    
    def _get_image_dir(self):
        """获取图片存储目录"""
        try:
            if getattr(sys, 'frozen', False):
                app_root = os.path.dirname(sys.executable)
            else:
                app_root = os.path.dirname(os.path.abspath(__file__))
            
            img_dir = os.path.join(app_root, 'json', 'historyJPG')
            os.makedirs(img_dir, exist_ok=True)
            return img_dir
        except Exception as e:
            print(f'[动作库] 创建图片目录失败: {e}', flush=True)
            return 'historyJPG'
    
    def _load_data(self):
        """加载数据"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f'[动作库] 加载数据: {len(data.get("groups", []))} 个分组', flush=True)
                return data
            except Exception as e:
                print(f'[动作库] 加载数据失败: {e}', flush=True)
        
        # 返回默认数据结构
        return {
            'groups': []
        }
    
    def _save_data(self):
        """保存数据"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            print(f'[动作库] 数据已保存: {len(self.data["groups"])} 个分组', flush=True)
        except Exception as e:
            print(f'[动作库] 保存数据失败: {e}', flush=True)
            QMessageBox.warning(self, "保存失败", f"无法保存数据：{e}")
    
    def _refresh_group_list(self):
        """刷新分组列表"""
        self.group_list.clear()
        folder_icon = create_vector_icon('folder', size=20, fg_color=QColor("#fbbf24"))
        for group in self.data['groups']:
            item = QListWidgetItem(f" {group['name']} ({len(group['images'])})")
            item.setIcon(folder_icon)
            self.group_list.addItem(item)
    
    def _on_group_changed(self, row):
        """分组切换"""
        if row >= 0 and row < len(self.data['groups']):
            self.current_group = self.data['groups'][row]['name']
            self.group_title.setText(f"分组：{self.current_group}")
            self._load_poses_for_group(self.current_group)
        else:
            self.current_group = None
            self.group_title.setText("请选择分组")
            self._clear_poses()
    
    def _load_poses_for_group(self, group_name):
        """加载指定分组的图片"""
        self._clear_poses()
        
        # 查找分组
        group_data = None
        for group in self.data['groups']:
            if group['name'] == group_name:
                group_data = group
                break
        
        if not group_data or not group_data['images']:
            # 显示空状态 - 使用矢量图标
            empty_widget = QWidget()
            empty_layout = QVBoxLayout(empty_widget)
            empty_layout.setAlignment(Qt.AlignCenter)
            
            # 矢量图标
            icon_label = QLabel()
            empty_icon = create_vector_icon('image', size=80, fg_color=QColor("#4a4a4a"))
            icon_label.setPixmap(empty_icon.pixmap(80, 80))
            icon_label.setAlignment(Qt.AlignCenter)
            empty_layout.addWidget(icon_label)
            
            # 文字提示
            placeholder = QLabel("暂无图片\n\n点击右上角「添加图片」按钮\n添加动作参考图")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #9aa0a6; font-size: 14px; padding: 20px;")
            empty_layout.addWidget(placeholder)
            
            self.grid_layout.addWidget(empty_widget, 0, 0, 1, 4, Qt.AlignCenter)
            return
        
        # 显示图片卡片（每行4个）
        for idx, image_path in enumerate(group_data['images']):
            row = idx // 4
            col = idx % 4
            
            card = PoseCard(image_path)
            card.delete_requested.connect(lambda path: self._delete_image(path))
            card.pose_apply_requested.connect(lambda path: self._apply_pose(path))
            self.grid_layout.addWidget(card, row, col)
        
        print(f'[动作库] 加载分组 [{group_name}]: {len(group_data["images"])} 张图片', flush=True)
    
    def _clear_poses(self):
        """清空图片显示"""
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def _add_group(self):
        """添加分组"""
        dialog = AddGroupDialog(self)
        if dialog.exec() == QDialog.Accepted:
            group_name = dialog.get_group_name()
            if not group_name:
                QMessageBox.warning(self, "无效输入", "分组名称不能为空！")
                return
            
            # 检查重名
            for group in self.data['groups']:
                if group['name'] == group_name:
                    QMessageBox.warning(self, "重名", f"分组「{group_name}」已存在！")
                    return
            
            # 添加新分组
            self.data['groups'].append({
                'name': group_name,
                'images': []
            })
            self._save_data()
            self._refresh_group_list()
            
            # 选中新分组
            self.group_list.setCurrentRow(len(self.data['groups']) - 1)
            
            print(f'[动作库] 新建分组: {group_name}', flush=True)
    
    def _rename_group(self):
        """重命名分组"""
        if not self.current_group:
            QMessageBox.warning(self, "未选择", "请先选择要重命名的分组！")
            return
        
        dialog = AddGroupDialog(self, self.current_group)
        if dialog.exec() == QDialog.Accepted:
            new_name = dialog.get_group_name()
            if not new_name:
                QMessageBox.warning(self, "无效输入", "分组名称不能为空！")
                return
            
            # 检查重名
            for group in self.data['groups']:
                if group['name'] == new_name and new_name != self.current_group:
                    QMessageBox.warning(self, "重名", f"分组「{new_name}」已存在！")
                    return
            
            # 重命名
            for group in self.data['groups']:
                if group['name'] == self.current_group:
                    group['name'] = new_name
                    break
            
            self._save_data()
            old_name = self.current_group
            self.current_group = new_name
            self._refresh_group_list()
            
            # 重新选中
            for i, group in enumerate(self.data['groups']):
                if group['name'] == new_name:
                    self.group_list.setCurrentRow(i)
                    break
            
            print(f'[动作库] 重命名分组: {old_name} -> {new_name}', flush=True)
    
    def _delete_group(self):
        """删除分组"""
        if not self.current_group:
            QMessageBox.warning(self, "未选择", "请先选择要删除的分组！")
            return
        
        # 查找分组
        group_data = None
        for group in self.data['groups']:
            if group['name'] == self.current_group:
                group_data = group
                break
        
        if not group_data:
            return
        
        # 确认删除
        msg = f"确定要删除分组「{self.current_group}」吗？"
        if group_data['images']:
            msg += f"\n\n此分组包含 {len(group_data['images'])} 张图片"
            msg += "\n图片文件将保留在磁盘上"
        
        reply = QMessageBox.question(
            self,
            "确认删除",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.data['groups'].remove(group_data)
            self._save_data()
            self._refresh_group_list()
            
            # 清空右侧显示
            self.current_group = None
            self._clear_poses()
            self.group_title.setText("请选择分组")
            
            print(f'[动作库] 删除分组: {group_data["name"]}', flush=True)
    
    def _add_images(self):
        """添加图片"""
        if not self.current_group:
            QMessageBox.warning(self, "未选择分组", "请先选择或创建一个分组！")
            return
        
        # 选择图片文件
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择动作参考图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
        )
        
        if not file_paths:
            return
        
        # 查找当前分组
        group_data = None
        for group in self.data['groups']:
            if group['name'] == self.current_group:
                group_data = group
                break
        
        if not group_data:
            return
        
        # 复制图片到 historyJPG 目录
        added_count = 0
        for src_path in file_paths:
            try:
                # 生成唯一文件名（时间戳 + 原文件名）
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S%f")
                ext = os.path.splitext(src_path)[1]
                filename = f"pose_{timestamp}{ext}"
                dest_path = os.path.join(self.image_dir, filename)
                
                # 复制文件
                shutil.copy2(src_path, dest_path)
                
                # 添加到数据
                group_data['images'].append(dest_path)
                added_count += 1
                
                print(f'[动作库] 添加图片: {filename}', flush=True)
            except Exception as e:
                print(f'[动作库] 添加图片失败 {src_path}: {e}', flush=True)
        
        if added_count > 0:
            self._save_data()
            self._refresh_group_list()
            self._load_poses_for_group(self.current_group)
            
            QMessageBox.information(
                self,
                "添加成功",
                f"成功添加 {added_count} 张图片到「{self.current_group}」！"
            )
    
    def _delete_image(self, image_path):
        """删除图片"""
        if not self.current_group:
            return
        
        # 查找当前分组
        group_data = None
        for group in self.data['groups']:
            if group['name'] == self.current_group:
                group_data = group
                break
        
        if not group_data or image_path not in group_data['images']:
            return
        
        # 从数据中移除
        group_data['images'].remove(image_path)
        self._save_data()
        self._refresh_group_list()
        self._load_poses_for_group(self.current_group)
        
        # 可选：删除物理文件
        # try:
        #     if os.path.exists(image_path):
        #         os.remove(image_path)
        #         print(f'[动作库] 删除文件: {image_path}', flush=True)
        # except Exception as e:
        #     print(f'[动作库] 删除文件失败: {e}', flush=True)
        
        print(f'[动作库] 从分组移除图片: {os.path.basename(image_path)}', flush=True)
    
    def _apply_pose(self, image_path):
        """应用姿势到画板 - 调用AI修改人物姿势"""
        try:
            from PySide6.QtCore import QSettings, QTimer, QRect
            from PySide6.QtWidgets import QMessageBox
            import threading
            
            print(f'[动作库] 🎯 开始应用姿势: {image_path}', flush=True)
            
            if not os.path.exists(image_path):
                print(f'[动作库] ❌ 文件不存在: {image_path}', flush=True)
                QMessageBox.warning(self, "文件不存在", "动作参考图不存在，请检查文件！")
                return
            
            # 获取父窗口（画板）
            parent_widget = self.parent()
            print(f'[动作库] 📌 父窗口: {parent_widget}', flush=True)
            print(f'[动作库] 📌 父窗口类型: {type(parent_widget).__name__}', flush=True)
            
            if not parent_widget:
                print('[动作库] ❌ 无法找到画板窗口', flush=True)
                QMessageBox.warning(self, "错误", "无法找到画板窗口！")
                return
            
            # 检查画板是否有内容
            has_canvas = hasattr(parent_widget, 'canvas')
            print(f'[动作库] 📌 是否有canvas属性: {has_canvas}', flush=True)
            
            if not has_canvas:
                print('[动作库] ❌ 画板没有canvas属性', flush=True)
                QMessageBox.warning(self, "画板为空", "请先在画板上绘制或生成图像！")
                return
            
            # 检查 canvas 是否有 _composite_to_image 方法
            has_composite = hasattr(parent_widget.canvas, '_composite_to_image')
            print(f'[动作库] 📌 canvas是否有_composite_to_image方法: {has_composite}', flush=True)
            
            if not has_composite:
                print('[动作库] ❌ canvas没有_composite_to_image方法', flush=True)
                QMessageBox.warning(self, "画板为空", "请先在画板上绘制或生成图像！")
                return
            
            # 获取画布合成图
            try:
                canvas_img = parent_widget.canvas._composite_to_image()
                canvas_pixmap = QPixmap.fromImage(canvas_img)
                print(f'[动作库] 📌 画布图像: {canvas_pixmap.width()}x{canvas_pixmap.height()}', flush=True)
            except Exception as e:
                print(f'[动作库] ❌ 获取画布图像失败: {e}', flush=True)
                QMessageBox.warning(self, "画板为空", "无法获取画板图像！")
                return
            
            if canvas_pixmap.isNull():
                print('[动作库] ❌ 画布为空', flush=True)
                QMessageBox.warning(self, "画板为空", "请先在画板上绘制或生成图像！")
                return
            
            # 检查是否有智能选区遮罩
            selection_mask = getattr(parent_widget.canvas, 'selection_mask', None)
            selection_rect = getattr(parent_widget.canvas, 'selection_rect', None)  # 修复：应该是 selection_rect 属性，不是 rect 方法
            
            print(f'[动作库] 📌 智能选区遮罩: {type(selection_mask).__name__ if selection_mask is not None else "None"}', flush=True)
            print(f'[动作库] 📌 智能选区矩形: {selection_rect}', flush=True)
            
            if selection_mask is not None:
                if isinstance(selection_mask, np.ndarray):
                    print(f'[动作库] 📌 遮罩数组形状: {selection_mask.shape}', flush=True)
                    print(f'[动作库] 📌 遮罩数组类型: {selection_mask.dtype}', flush=True)
                    print(f'[动作库] 📌 遮罩True像素数: {np.sum(selection_mask)}', flush=True)
                else:
                    print(f'[动作库] 📌 遮罩类型: {type(selection_mask)}', flush=True)
            
            if selection_mask is not None and selection_rect is not None:
                # 使用智能替换模式
                print('[动作库] ✅ 检测到智能选区，使用智能替换模式', flush=True)
                self._apply_pose_with_smart_replace(image_path, parent_widget, selection_rect, selection_mask)
            else:
                # 使用普通生成模式
                print('[动作库] ⚠️  未检测到智能选区，使用普通生成模式', flush=True)
                QMessageBox.information(
                    self,
                    "提示",
                    "未检测到智能选区！\n\n请先使用智能选区工具（🪄）框选人物，\n然后再点击动作库中的动作图片。"
                )
                return
            
        except Exception as e:
            print(f'[动作库] ❌ 应用姿势出错: {e}', flush=True)
            import traceback
            traceback.print_exc()
            
            QMessageBox.critical(
                self,
                "错误",
                f"应用姿势时出错：{str(e)}"
            )
    
    def _apply_pose_with_smart_replace(self, pose_image_path, parent_widget, rect, mask):
        """使用智能替换模式应用姿势
        
        Args:
            pose_image_path: 动作参考图路径
            parent_widget: PhotoPage实例
            rect: 选区矩形
            mask: 选区遮罩（二维布尔数组）
        """
        try:
            from PySide6.QtCore import QSettings, QTimer
            from PySide6.QtWidgets import QMessageBox
            from PySide6.QtGui import QPainter, QImage, QPixmap
            import threading
            from pathlib import Path
            import tempfile
            import shutil
            
            print(f'[动作库] 🎨 进入智能替换模式', flush=True)
            print(f'[动作库] 📌 动作图路径: {pose_image_path}', flush=True)
            print(f'[动作库] 📌 选区矩形: {rect}', flush=True)
            print(f'[动作库] 📌 遮罩类型: {type(mask).__name__}', flush=True)
            
            print(f'[动作库] 🎨 智能姿势替换 - 开始准备参考图...', flush=True)
            
            # 获取完整画布图像（使用 _composite_to_image）
            try:
                canvas_img = parent_widget.canvas._composite_to_image()
                canvas_pixmap = QPixmap.fromImage(canvas_img)
                print(f'[动作库] 📌 画布尺寸: {canvas_pixmap.width()}x{canvas_pixmap.height()}', flush=True)
            except Exception as e:
                print(f'[动作库] ❌ 获取画布图像失败: {e}', flush=True)
                QMessageBox.warning(self, "错误", f"无法获取画板图像：{str(e)}")
                return
            
            # 创建临时目录
            temp_dir = Path(tempfile.gettempdir())
            print(f'[动作库] 📌 临时目录: {temp_dir}', flush=True)
            
            # 1. 保存完整画布图（composite.png）
            composite_path = temp_dir / 'pose_composite.png'
            canvas_pixmap.save(str(composite_path), 'PNG')
            print(f'[动作库] ✅ 完整画布图已保存: {composite_path}', flush=True)
            
            # 2. 复制动作参考图到临时目录
            print(f'[动作库] 📌 复制动作参考图...', flush=True)
            pose_ref_path = temp_dir / f'pose_reference_{Path(pose_image_path).name}'
            shutil.copy2(pose_image_path, str(pose_ref_path))
            print(f'[动作库] ✅ 动作参考图已复制: {pose_ref_path}', flush=True)
            
            # 3. 设置refs数组（API需要的参考图）- 不包含绿色遮罩图
            # refs[3] 是最重要的：它会作为 sketch 草图提交给 Gemini API
            print(f'[动作库] 📌 设置refs数组...', flush=True)
            if not hasattr(parent_widget, 'refs') or not isinstance(parent_widget.refs, list):
                parent_widget.refs = [None, None, None, None]
                print(f'[动作库] 📌 创建新的refs数组', flush=True)
            while len(parent_widget.refs) < 4:
                parent_widget.refs.append(None)
            
            # 关键修改：提交给API的图片不包含绿色遮罩
            # 只使用完整画布图和动作参考图
            parent_widget.refs[0] = str(pose_ref_path)    # 动作参考图（第1张）
            parent_widget.refs[1] = str(composite_path)   # 完整画布图（第2张，无绿色遮罩）
            parent_widget.refs[2] = str(pose_ref_path)    # 动作参考图（第3张）
            parent_widget.refs[3] = str(pose_ref_path)    # 动作参考图（第4张，作为sketch）- 最重要！
            
            print(f'[动作库] ✅ refs已设置（不包含绿色遮罩）:', flush=True)
            print(f'[动作库]   - refs[0]: {Path(parent_widget.refs[0]).name} (动作参考图)', flush=True)
            print(f'[动作库]   - refs[1]: {Path(parent_widget.refs[1]).name} (完整画布-无遮罩)', flush=True)
            print(f'[动作库]   - refs[2]: {Path(parent_widget.refs[2]).name} (动作参考图)', flush=True)
            print(f'[动作库]   - refs[3]: {Path(parent_widget.refs[3]).name} (动作参考图-sketch) ⭐', flush=True)
            
            # 5. 保存遮罩信息到parent_widget，并设置智能修改模式标志
            parent_widget._smart_mask = mask
            parent_widget._smart_rect = rect
            parent_widget._smart_edit_mode = True  # 关键：标记为智能修改模式，生成完成后会添加图层
            
            print(f'[动作库] ✅ 已设置智能修改模式标志: _smart_edit_mode=True', flush=True)
            
            # 6. 构建提示词（不再提及绿色遮罩）
            prompt = f"""请根据参考动作图片（第1、3、4张图片）修改选区内的人物姿势：

**重要说明**：
- 第1张图片：目标动作姿势参考（请仔细观察并模仿这个姿势）
- 第2张图片：完整的原始画布，包含需要修改的人物
- 第3张图片：目标动作姿势参考（与第1张相同）
- 第4张图片：目标动作姿势参考（sketch草图，与第1张相同，最重要）

**核心任务**：
1. **仔细观察第1、3、4张参考图片**中人物的姿势、动作和身体各部位的位置关系
2. 将第2张图片中选中区域内的人物姿势**完全改为参考图中的姿势**
3. 必须保持人物的：
   - 外貌特征（脸型、发型、肤色等）
   - 服装和穿着风格
   - 整体画风和艺术风格
4. **只修改姿势和动作，不改变人物身份和外观**
5. 选区外的内容（背景、其他人物）保持完全不变
6. 确保修改后的姿势自然流畅，符合人体工学
7. 边缘融合自然，无明显拼接痕迹

**关键要求**：请准确还原参考图（第1、3、4张）中的动作姿势，同时保持人物的原有特征。"""
            
            # 7. 获取API提供方配置
            provider = QSettings('GhostOS', 'App').value('api/image_provider', 'Gemini')
            print(f'[动作库] 📌 API提供方: {provider}', flush=True)
            print(f'[动作库] 📌 提示词长度: {len(prompt)} 字符', flush=True)
            
            # 8. 更新状态显示
            if hasattr(parent_widget, '_update_conn_status'):
                try:
                    parent_widget._update_conn_status('应用姿势中...', 'loading')
                    print('[动作库] 📌 已更新状态显示', flush=True)
                except Exception as e:
                    print(f'[动作库] ⚠️  更新状态显示失败: {e}', flush=True)
            
            # 9. 直接调用 API 生成（在主线程中）
            if hasattr(parent_widget, '_dispatch_generate'):
                print('[动作库] 🚀 开始调用 _dispatch_generate...', flush=True)
                parent_widget._dispatch_generate(prompt, provider)
                print('[动作库] ✅ API 请求已发送！', flush=True)
                print('[动作库] 📌 等待生成完成...生成完成后会自动添加到图层区域', flush=True)
            else:
                print('[动作库] ❌ parent_widget 没有 _dispatch_generate 方法', flush=True)
                QMessageBox.warning(self, "功能不可用", "当前画板不支持AI生成功能！")
                return
            
        except Exception as e:
            print(f'[动作库] ❌ 智能姿势替换出错: {e}', flush=True)
            import traceback
            traceback.print_exc()
            
            QMessageBox.critical(
                self,
                "错误",
                f"智能姿势替换出错：{str(e)}"
            )
    
    def _create_reference_image_with_mask(self, base_pix, rect, mask):
        """创建带绿色遮罩的参考图
        
        Args:
            base_pix: 完整画布图
            rect: 选区矩形
            mask: 选区遮罩（二维布尔数组）
        
        Returns:
            QPixmap: 带绿色半透明遮罩的参考图
        """
        from PySide6.QtGui import QPainter, QColor
        import numpy as np
        
        # 创建副本
        result = QPixmap(base_pix.size())
        result.fill(Qt.transparent)
        
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing, True)
        
        # 绘制原图
        painter.drawPixmap(0, 0, base_pix)
        
        # 绘制绿色半透明遮罩
        green_with_alpha = QColor(0, 255, 0, 100)
        painter.setBrush(green_with_alpha)
        painter.setPen(Qt.NoPen)
        
        # 使用mask数组精确绘制
        if isinstance(mask, np.ndarray):
            mask_h = mask.shape[0]
            mask_w = mask.shape[1]
            
            for dy in range(mask_h):
                for dx in range(mask_w):
                    if mask[dy][dx]:
                        abs_x = rect.x() + dx
                        abs_y = rect.y() + dy
                        painter.fillRect(abs_x, abs_y, 1, 1, green_with_alpha)
        else:
            # 降级方案：绘制整个矩形
            painter.fillRect(rect, green_with_alpha)
        
        painter.end()
        
        return result
    
    def apply_stylesheet(self):
        """应用样式"""
        self.setStyleSheet("""
            QMainWindow {
                background: #1a1a1a;
            }
            #LeftPanel {
                background: #1a1a1a;
                border-right: 1px solid #2a2d31;
            }
            #RightPanel {
                background: #1a1a1a;
            }
        """)
