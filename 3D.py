"""
3D控制系统 - 三区域工作空间
红色区域：3D显示视口（带XYZ操控球）
黄色区域：顶部导入工具栏
蓝色区域：左侧工具面板
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QMainWindow, QPushButton,
    QLabel, QFileDialog, QMessageBox, QScrollArea, QColorDialog, QInputDialog, QMenu,
    QDialog, QSlider, QGridLayout
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QRect
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QPainterPath, QPixmap, QImage
import math
import numpy as np
import json
import os
import sys


class Model3D:
    """3D模型数据类"""
    def __init__(self, name, model_type="mannequin", file_path=None):
        self.name = name
        self.type = model_type  # mannequin 或 fbx
        self.x = 0
        self.y = 0
        self.z = 0  # Z轴位置
        self.rotation_y = 0  # Y轴旋转角度（度）
        self.scale = 1.0
        self.selected = False
        self.show_gizmo = False  # 是否显示XYZ控制器
        self.color = QColor(255, 100, 100)  # 默认红色
        self.file_path = file_path  # FBX文件路径
        self.mesh_data = None  # 网格数据
        self.thumbnail = None  # 缩略图
        
        # 如果是FBX，尝试加载
        if model_type == "fbx" and file_path:
            self.load_fbx(file_path)
    
    def load_fbx(self, file_path):
        """加载FBX文件"""
        try:
            print(f'[Model3D] ========== 开始加载FBX ==========', flush=True)
            print(f'[Model3D] 文件路径: {file_path}', flush=True)
            
            import os
            if not os.path.exists(file_path):
                print(f'[Model3D] ❌ 文件不存在!', flush=True)
                return
            
            file_size = os.path.getsize(file_path)
            print(f'[Model3D] 文件大小: {file_size / 1024:.2f} KB', flush=True)
            
            # 方法1: 尝试使用trimesh (推荐)
            try:
                print('[Model3D] 尝试方法1: trimesh.load()...', flush=True)
                import trimesh
                
                # force='mesh' 强制作为网格加载
                mesh = trimesh.load(file_path, force='mesh', process=False)
                
                print(f'[Model3D] trimesh加载结果类型: {type(mesh)}', flush=True)
                
                # 处理Scene对象
                if isinstance(mesh, trimesh.Scene):
                    print(f'[Model3D] 检测到Scene对象，包含 {len(mesh.geometry)} 个几何体', flush=True)
                    # 合并所有几何体
                    meshes = [m for m in mesh.geometry.values()]
                    if meshes:
                        mesh = trimesh.util.concatenate(meshes)
                        print(f'[Model3D] 已合并几何体', flush=True)
                
                if hasattr(mesh, 'vertices') and hasattr(mesh, 'faces'):
                    vertices = mesh.vertices
                    faces = mesh.faces
                    print(f'[Model3D] ✓ trimesh加载成功!', flush=True)
                    print(f'[Model3D]   - 顶点数: {len(vertices)}', flush=True)
                    print(f'[Model3D]   - 面数: {len(faces)}', flush=True)
                    print(f'[Model3D]   - 边界: {mesh.bounds}', flush=True)
                    
                    self.mesh_data = {
                        'vertices': vertices,
                        'faces': faces,
                        'bounds': mesh.bounds
                    }
                    print(f'[Model3D] ========== FBX加载完成 ==========', flush=True)
                    return
                else:
                    print(f'[Model3D] ⚠️  mesh对象缺少vertices或faces属性', flush=True)
                    
            except ImportError as e:
                print(f'[Model3D] trimesh未安装: {e}', flush=True)
                print(f'[Model3D] 提示: 运行 pip install trimesh 安装库', flush=True)
            except Exception as e:
                print(f'[Model3D] trimesh加载失败: {e}', flush=True)
                import traceback
                traceback.print_exc()
            
            # 方法2: 尝试使用pywavefront (支持多种格式)
            try:
                print('[Model3D] 尝试方法2: pywavefront...', flush=True)
                import pywavefront
                scene = pywavefront.Wavefront(file_path, collect_faces=True)
                
                # 提取顶点和面
                vertices = []
                faces = []
                for name, material in scene.materials.items():
                    vertices.extend(material.vertices)
                    faces.extend(material.faces)
                
                if vertices:
                    import numpy as np
                    vertices_array = np.array(vertices).reshape(-1, 3)
                    print(f'[Model3D] ✓ pywavefront加载成功!', flush=True)
                    print(f'[Model3D]   - 顶点数: {len(vertices_array)}', flush=True)
                    
                    self.mesh_data = {
                        'vertices': vertices_array,
                        'faces': faces,
                        'bounds': None
                    }
                    print(f'[Model3D] ========== FBX加载完成 ==========', flush=True)
                    return
                    
            except ImportError:
                print(f'[Model3D] pywavefront未安装', flush=True)
            except Exception as e:
                print(f'[Model3D] pywavefront加载失败: {e}', flush=True)
            
            # 方法3: 尝试使用FBX SDK (fbx库)
            try:
                print('[Model3D] 尝试方法3: fbx库...', flush=True)
                import fbx
                
                manager = fbx.FbxManager.Create()
                scene = fbx.FbxScene.Create(manager, "myScene")
                importer = fbx.FbxImporter.Create(manager, "")
                
                if importer.Initialize(file_path, -1):
                    importer.Import(scene)
                    print(f'[Model3D] ✓ FBX SDK加载成功!', flush=True)
                    
                    # 提取网格数据
                    root_node = scene.GetRootNode()
                    vertices = []
                    
                    def extract_mesh(node):
                        if node.GetNodeAttribute():
                            attribute = node.GetNodeAttribute()
                            if attribute.GetAttributeType() == fbx.FbxNodeAttribute.eMesh:
                                mesh = node.GetMesh()
                                for i in range(mesh.GetControlPointsCount()):
                                    point = mesh.GetControlPointAt(i)
                                    vertices.append([point[0], point[1], point[2]])
                        
                        for i in range(node.GetChildCount()):
                            extract_mesh(node.GetChild(i))
                    
                    extract_mesh(root_node)
                    
                    if vertices:
                        import numpy as np
                        vertices_array = np.array(vertices)
                        print(f'[Model3D]   - 顶点数: {len(vertices_array)}', flush=True)
                        
                        self.mesh_data = {
                            'vertices': vertices_array,
                            'faces': None,
                            'bounds': None
                        }
                        print(f'[Model3D] ========== FBX加载完成 ==========', flush=True)
                        return
                        
            except ImportError:
                print(f'[Model3D] fbx SDK未安装', flush=True)
            except Exception as e:
                print(f'[Model3D] fbx SDK加载失败: {e}', flush=True)
            
            # 所有方法都失败
            print(f'[Model3D] ========== 所有加载方法均失败 ==========', flush=True)
            print(f'[Model3D] 请安装以下库之一:', flush=True)
            print(f'[Model3D]   pip install trimesh', flush=True)
            print(f'[Model3D]   pip install pywavefront', flush=True)
            print(f'[Model3D] 将使用占位符显示', flush=True)
            
            # 标记为已尝试加载但失败
            self.mesh_data = {'status': 'failed', 'path': file_path}
            
        except Exception as e:
            print(f'[Model3D] ❌ 严重错误: {e}', flush=True)
            import traceback
            traceback.print_exc()


class Viewport3D(QWidget):
    """红色区域 - 3D显示视口"""
    
    model_added = Signal(str)
    model_selected = Signal(object)  # 人偶选中信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(800, 600)
        self.setMouseTracking(True)
        
        # 存储加载的模型
        self.models = []
        
        # 工具面板引用
        self.tools_panel = None
        
        # 3D窗口引用（用于访问photo_page）
        self.window_3d = None
        
        # 当前视角 - 3D透视视角
        self.current_view = "perspective"
        self.camera_angle_x = 25  # 相机俯仰角（度）
        self.camera_angle_y = 35  # 相机偏航角（度）
        self.camera_distance = 500  # 相机距离
        self.camera_focus_x = 0  # 相机焦点X坐标
        self.camera_focus_y = 0  # 相机焦点Y坐标
        self.camera_focus_z = 0  # 相机焦点Z坐标
        
        # 显示设置
        self.show_grid = True  # 是否显示网格线条
        
        # 拖动状态
        self.dragging_model = None
        self.dragging_gizmo = None  # 拖动的控制器轴（'x', 'y', 'z'）
        self.drag_start_pos = None
        self.camera_dragging = False  # 相机拖动状态
        
        # 当前人偶颜色
        self.current_mannequin_color = QColor(255, 100, 100)  # 默认红色
        
        # 按键状态
        self.g_key_pressed = False  # G键移动模式
        self.r_key_pressed = False  # R键旋转模式
        self.s_key_pressed = False  # S键缩放模式
        self.t_key_pressed = False  # T键是否按下（兼容旧功能）
        self.rotating_model = None  # 正在旋转的模型
        self.transform_start_pos = None  # 变换起始位置
        
        # 区域截图状态
        self.capturing_region = False
        self.capture_start = None
        self.capture_end = None
        
        # 拍照框状态
        self.photo_frame_visible = False  # 拍照框是否可见
        self.photo_frame_rect = QRect(100, 100, 600, 400)  # 默认拍照框
        self.dragging_frame_corner = None  # 拖动的角 ('tl', 'tr', 'bl', 'br')
        self.dragging_frame_edge = None  # 拖动的边 ('t', 'b', 'l', 'r')
        self.frame_drag_start = None  # 拖动起始位置
        
        # 鼠标悬停的模型（用于滚轮缩放）
        self.hovered_model = None
        
        # 视角球状态
        self.view_orb_dragging = False
        self.selected_model_for_view = None  # 当前选中查看的模型
    
    def resizeEvent(self, event):
        """窗口大小改变"""
        super().resizeEvent(event)
    
    def change_view(self, view):
        """改变视角"""
        self.current_view = view
        # 根据视角调整相机角度
        if view == "front":
            self.camera_angle_x = 0
            self.camera_angle_y = 0
        elif view == "right":
            self.camera_angle_x = 0
            self.camera_angle_y = 90
        elif view == "top":
            self.camera_angle_x = 90
            self.camera_angle_y = 0
        else:  # perspective
            self.camera_angle_x = 25
            self.camera_angle_y = 35
        self.update()
    
    def toggle_grid(self):
        """切换网格显示"""
        self.show_grid = not self.show_grid
        self.update()
        print(f'[3D视口] 网格线条: {"显示" if self.show_grid else "隐藏"}', flush=True)
    
    def set_mannequin_color(self, color):
        """设置当前人偶颜色"""
        self.current_mannequin_color = color
        # 更新所有选中的人偶颜色
        for model in self.models:
            if model.show_gizmo and model.type == "mannequin":
                model.color = color
        self.update()
        print(f'[3D视口] 设置人偶颜色: {color.name()}', flush=True)
    
    def keyPressEvent(self, event):
        """键盘按下事件 - Blender风格操作"""
        if event.isAutoRepeat():
            return
        
        # G键 - 移动模式（Grab）
        if event.key() == Qt.Key_G:
            # 获取选中的模型
            selected = [m for m in self.models if m.show_gizmo]
            if selected:
                self.g_key_pressed = True
                self.transform_start_pos = QCursor.pos()
                self.setCursor(Qt.SizeAllCursor)
                print('[3D视口] G键 - 移动模式激活（移动鼠标后点击确认，右键取消）', flush=True)
        
        # R键 - 旋转模式（Rotate）
        elif event.key() == Qt.Key_R:
            selected = [m for m in self.models if m.show_gizmo]
            if selected:
                self.r_key_pressed = True
                self.transform_start_pos = QCursor.pos()
                self.setCursor(Qt.CrossCursor)
                print('[3D视口] R键 - 旋转模式激活（移动鼠标后点击确认，右键取消）', flush=True)
        
        # S键 - 缩放模式（Scale）
        elif event.key() == Qt.Key_S:
            selected = [m for m in self.models if m.show_gizmo]
            if selected:
                self.s_key_pressed = True
                self.transform_start_pos = QCursor.pos()
                self.setCursor(Qt.SizeVerCursor)
                print('[3D视口] S键 - 缩放模式激活（移动鼠标后点击确认，右键取消）', flush=True)
        
        # T键 - 兼容旧的旋转模式
        elif event.key() == Qt.Key_T:
            self.t_key_pressed = True
            self.setCursor(Qt.CrossCursor)
            print('[3D视口] T键按下 - 旋转模式', flush=True)
        
        # ESC键 - 取消所有变换模式
        elif event.key() == Qt.Key_Escape:
            self.cancel_transform()
        
        super().keyPressEvent(event)
    
    def keyReleaseEvent(self, event):
        """键盘释放事件"""
        if event.key() == Qt.Key_T and not event.isAutoRepeat():
            self.t_key_pressed = False
            self.rotating_model = None
            self.setCursor(Qt.ArrowCursor)
            print('[3D视口] T键释放 - 退出旋转模式', flush=True)
        super().keyReleaseEvent(event)
    
    def cancel_transform(self):
        """取消所有变换模式"""
        self.g_key_pressed = False
        self.r_key_pressed = False
        self.s_key_pressed = False
        self.transform_start_pos = None
        self.setCursor(Qt.ArrowCursor)
        print('[3D视口] 取消变换模式', flush=True)
    
    def confirm_transform(self):
        """确认变换"""
        if self.g_key_pressed:
            print('[3D视口] 确认移动', flush=True)
        elif self.r_key_pressed:
            print('[3D视口] 确认旋转', flush=True)
        elif self.s_key_pressed:
            print('[3D视口] 确认缩放', flush=True)
        
        # 重置所有变换状态
        self.g_key_pressed = False
        self.r_key_pressed = False
        self.s_key_pressed = False
        self.transform_start_pos = None
        self.setCursor(Qt.ArrowCursor)
    
    def mousePressEvent(self, event):
        """鼠标按下 - Blender风格交互"""
        click_pos = event.pos()
        
        # 左键点击
        if event.button() == Qt.LeftButton:
            # 如果拍照框可见，检查是否点击了拍照框的角或边
            if self.photo_frame_visible:
                corner = self.check_frame_corner_click(click_pos)
                if corner:
                    self.dragging_frame_corner = corner
                    self.frame_drag_start = click_pos
                    self.setCursor(self.get_corner_cursor(corner))
                    print(f'[3D视口] 拖动拍照框角: {corner}', flush=True)
                    return
                
                edge = self.check_frame_edge_click(click_pos)
                if edge:
                    self.dragging_frame_edge = edge
                    self.frame_drag_start = click_pos
                    self.setCursor(self.get_edge_cursor(edge))
                    print(f'[3D视口] 拖动拍照框边: {edge}', flush=True)
                    return
            
            # G/R/S变换模式下，左键确认变换
            if self.g_key_pressed or self.r_key_pressed or self.s_key_pressed:
                self.confirm_transform()
                return
            
            # T键按下时，点击模型开始旋转
            if self.t_key_pressed:
                for model in self.models:
                    model_pos = self.get_model_screen_position(model)
                    if self.is_point_near_model(click_pos, model_pos):
                        self.rotating_model = model
                        self.drag_start_pos = click_pos
                        print(f'[3D视口] 开始旋转模型: {model.name}', flush=True)
                        return
            
            # Ctrl键按下时，开始区域截图
            if event.modifiers() & Qt.ControlModifier:
                self.capturing_region = True
                self.capture_start = click_pos
                self.capture_end = click_pos
                self.setCursor(Qt.CrossCursor)
                print('[3D视口] 开始区域截图', flush=True)
                return
            
            # 检查是否点击了控制器（XYZ轴）
            for model in self.models:
                if model.show_gizmo:
                    gizmo_axis = self.check_gizmo_click(model, click_pos)
                    if gizmo_axis:
                        self.dragging_gizmo = gizmo_axis
                        self.dragging_model = model
                        self.drag_start_pos = click_pos
                        self.setCursor(Qt.ClosedHandCursor)
                        print(f'[3D视口] 拖动 {gizmo_axis.upper()} 轴移动人偶', flush=True)
                        return
            
            # 检查是否点击了视角球
            if self.check_view_orb_click(click_pos):
                return
            
            # 检查是否点击了模型
            for model in self.models:
                model_pos = self.get_model_screen_position(model)
                if self.is_point_near_model(click_pos, model_pos):
                    # 选中模型并显示控制器
                    for m in self.models:
                        m.show_gizmo = False
                    model.show_gizmo = True
                    self.selected_model_for_view = model
                    
                    # 通知工具面板显示人偶属性
                    self.model_selected.emit(model)
                    if self.tools_panel:
                        self.tools_panel.show_model_properties(model)
                    
                    print(f'[3D视口] 选中模型: {model.name}，显示XYZ控制器', flush=True)
                    self.update()
                    return
            
            # 点击空白处，取消所有选择
            for m in self.models:
                m.show_gizmo = False
            self.selected_model_for_view = None
            
            # 通知工具面板隐藏人偶属性
            if self.tools_panel:
                self.tools_panel.hide_model_properties()
            
            self.update()
        
        # 中键拖动 - 旋转相机视角（Blender风格）
        elif event.button() == Qt.MiddleButton:
            self.camera_dragging = True
            self.drag_start_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            print('[3D视口] 中键旋转视角', flush=True)
        
        # 右键点击
        elif event.button() == Qt.RightButton:
            # G/R/S变换模式下，右键取消变换
            if self.g_key_pressed or self.r_key_pressed or self.s_key_pressed:
                self.cancel_transform()
                return
            
            # 右键点击模型显示菜单
            for model in self.models:
                model_pos = self.get_model_screen_position(model)
                if self.is_point_near_model(click_pos, model_pos):
                    self.show_model_context_menu(model, event.globalPos())
                    return
            
            # 右键拖动也可以旋转相机（兼容性）
            self.camera_dragging = True
            self.drag_start_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
    
    def mouseMoveEvent(self, event):
        """鼠标移动 - Blender风格变换"""
        # 拖动拍照框角
        if self.dragging_frame_corner and self.frame_drag_start:
            delta = event.pos() - self.frame_drag_start
            self.resize_frame_by_corner(self.dragging_frame_corner, delta)
            self.frame_drag_start = event.pos()
            self.update()
            return
        
        # 拖动拍照框边
        if self.dragging_frame_edge and self.frame_drag_start:
            delta = event.pos() - self.frame_drag_start
            self.resize_frame_by_edge(self.dragging_frame_edge, delta)
            self.frame_drag_start = event.pos()
            self.update()
            return
        
        # 如果拍照框可见，更新鼠标样式
        if self.photo_frame_visible and not self.dragging_frame_corner and not self.dragging_frame_edge:
            corner = self.check_frame_corner_click(event.pos())
            if corner:
                self.setCursor(self.get_corner_cursor(corner))
                return
            
            edge = self.check_frame_edge_click(event.pos())
            if edge:
                self.setCursor(self.get_edge_cursor(edge))
                return
            
            self.setCursor(Qt.ArrowCursor)
        
        # G键移动模式
        if self.g_key_pressed and self.transform_start_pos:
            selected = [m for m in self.models if m.show_gizmo]
            if selected:
                delta = event.pos() - QPoint(self.width() // 2, self.height() // 2)
                for model in selected:
                    model.x = delta.x() * 2
                    model.z = -delta.y() * 2
                self.update()
                return
        
        # R键旋转模式
        if self.r_key_pressed and self.transform_start_pos:
            selected = [m for m in self.models if m.show_gizmo]
            if selected:
                delta = event.pos() - QPoint(self.width() // 2, self.height() // 2)
                for model in selected:
                    model.rotation_y = delta.x() * 0.5
                self.update()
                return
        
        # S键缩放模式
        if self.s_key_pressed and self.transform_start_pos:
            selected = [m for m in self.models if m.show_gizmo]
            if selected:
                delta = event.pos() - QPoint(self.width() // 2, self.height() // 2)
                scale_factor = 1.0 + (delta.x() + delta.y()) * 0.001
                for model in selected:
                    model.scale = max(0.3, min(3.0, scale_factor))
                self.update()
                return
        
        # 视角球拖动
        if self.view_orb_dragging and self.drag_start_pos and self.selected_model_for_view:
            delta = event.pos() - self.drag_start_pos
            self.camera_angle_y += delta.x() * 0.8
            self.camera_angle_x += delta.y() * 0.8
            self.camera_angle_x = max(-89, min(89, self.camera_angle_x))
            self.drag_start_pos = event.pos()
            self.update()
        
        # T键旋转模型
        elif self.rotating_model and self.drag_start_pos:
            delta = event.pos() - self.drag_start_pos
            self.rotating_model.rotation_y += delta.x() * 0.5
            self.drag_start_pos = event.pos()
            self.update()
        
        # 区域截图
        elif self.capturing_region and self.capture_start:
            self.capture_end = event.pos()
            self.update()
        
        # 拖动XYZ控制器轴
        elif self.dragging_model and self.dragging_gizmo and self.drag_start_pos:
            delta = event.pos() - self.drag_start_pos
            
            if self.dragging_gizmo == 'x':
                self.dragging_model.x += delta.x() * 2
            elif self.dragging_gizmo == 'y':
                self.dragging_model.z -= delta.y() * 2
            elif self.dragging_gizmo == 'z':
                self.dragging_model.y += delta.y() * 2
            
            self.drag_start_pos = event.pos()
            
            # 实时更新工具面板显示
            if self.tools_panel and self.tools_panel.selected_model == self.dragging_model:
                self.tools_panel.update_model_display()
            
            self.update()
        
        # 旋转相机（中键或右键）
        elif self.camera_dragging and self.drag_start_pos:
            delta = event.pos() - self.drag_start_pos
            self.camera_angle_y += delta.x() * 0.5
            self.camera_angle_x += delta.y() * 0.5
            self.camera_angle_x = max(-89, min(89, self.camera_angle_x))
            self.drag_start_pos = event.pos()
            self.current_view = "custom"
            self.update()
    
    def mouseReleaseEvent(self, event):
        """鼠标释放 - 结束拖动"""
        if event.button() == Qt.LeftButton:
            # 释放拍照框拖动
            if self.dragging_frame_corner or self.dragging_frame_edge:
                self.dragging_frame_corner = None
                self.dragging_frame_edge = None
                self.frame_drag_start = None
                self.setCursor(Qt.ArrowCursor)
                self.update()
                return
            
            # 完成区域截图
            if self.capturing_region:
                self.capture_region_screenshot()
                self.capturing_region = False
                self.capture_start = None
                self.capture_end = None
                self.setCursor(Qt.ArrowCursor)
                self.update()
                return
            
            if self.view_orb_dragging:
                self.view_orb_dragging = False
            
            if self.rotating_model:
                print(f'[3D视口] 旋转模型 {self.rotating_model.name} 到 {self.rotating_model.rotation_y:.1f}°', flush=True)
                self.rotating_model = None
            
            if self.dragging_model:
                print(f'[3D视口] 移动模型 {self.dragging_model.name} 到 ({self.dragging_model.x}, {self.dragging_model.y}, {self.dragging_model.z})', flush=True)
            
            self.dragging_model = None
            self.dragging_gizmo = None
            self.drag_start_pos = None
            if not self.t_key_pressed:
                self.setCursor(Qt.ArrowCursor)
        elif event.button() == Qt.RightButton:
            self.camera_dragging = False
            self.drag_start_pos = None
            self.setCursor(Qt.ArrowCursor)
    
    def wheelEvent(self, event):
        """鼠标滚轮 - 放大/缩小人偶"""
        delta = event.angleDelta().y()
        mouse_pos = event.position().toPoint()
        
        # 检查鼠标是否在某个模型上
        for model in self.models:
            model_pos = self.get_model_screen_position(model)
            if self.is_point_near_model(mouse_pos, model_pos):
                # 缩放模型
                scale_delta = 0.1 if delta > 0 else -0.1
                model.scale = max(0.3, min(3.0, model.scale + scale_delta))
                print(f'[3D视口] 缩放模型 {model.name}: {model.scale:.1f}x', flush=True)
                self.update()
                # 自动保存场景状态
                main_window = self.window()
                if hasattr(main_window, 'save_scene_state'):
                    main_window.save_scene_state()
                return
        
        # 如果没有模型在鼠标下，缩放相机
        self.camera_distance -= delta * 0.5
        self.camera_distance = max(200, min(1000, self.camera_distance))
        self.update()
    
    def get_model_screen_position(self, model):
        """获取模型的屏幕位置（3D投影）"""
        px, py, pz = self.project_3d(model.x, model.z, model.y)
        return QPointF(px, py)
    
    def check_gizmo_click(self, model, click_pos):
        """检查是否点击了控制器的某个轴"""
        if not model.show_gizmo:
            return None
        
        base_x, base_y, base_z = model.x, model.z, model.y
        gizmo_length = 80
        
        # 检查X轴（红色）
        x_end = self.project_3d(base_x + gizmo_length, base_y, base_z)
        if self.is_point_near_line(click_pos, self.project_3d(base_x, base_y, base_z)[:2], x_end[:2], 10):
            return 'x'
        
        # 检查Y轴（绿色）
        y_end = self.project_3d(base_x, base_y + gizmo_length, base_z)
        if self.is_point_near_line(click_pos, self.project_3d(base_x, base_y, base_z)[:2], y_end[:2], 10):
            return 'y'
        
        # 检查Z轴（蓝色）
        z_end = self.project_3d(base_x, base_y, base_z + gizmo_length)
        if self.is_point_near_line(click_pos, self.project_3d(base_x, base_y, base_z)[:2], z_end[:2], 10):
            return 'z'
        
        return None
    
    def is_point_near_line(self, point, line_start, line_end, threshold):
        """检查点是否靠近线段"""
        px, py = point.x(), point.y()
        x1, y1 = line_start
        x2, y2 = line_end
        
        # 点到线段的距离
        line_len = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        if line_len == 0:
            return False
        
        dist = abs((y2 - y1) * px - (x2 - x1) * py + x2 * y1 - y2 * x1) / line_len
        return dist <= threshold
    
    def is_point_near_model(self, point, model_pos):
        """检测点是否在模型附近"""
        dist = math.sqrt((point.x() - model_pos.x()) ** 2 + (point.y() - model_pos.y()) ** 2)
        return dist <= 60  # 检测范围
    
    def check_view_orb_click(self, point):
        """检查是否点击了视角球"""
        if not self.selected_model_for_view:
            return False
        
        orb_center = self.get_view_orb_position()
        dist = math.sqrt((point.x() - orb_center[0]) ** 2 + (point.y() - orb_center[1]) ** 2)
        
        if dist <= 50:  # 视角球半径
            self.view_orb_dragging = True
            self.drag_start_pos = point
            self.setCursor(Qt.ClosedHandCursor)
            print(f'[3D视口] 开始拖动视角球', flush=True)
            return True
        return False
    
    def get_view_orb_position(self):
        """获取视角球位置（右上角）"""
        margin = 100
        return (self.width() - margin, margin)
    
    def check_frame_corner_click(self, point):
        """检查是否点击了拍照框的角"""
        if not self.photo_frame_visible:
            return None
        
        corner_size = 15  # 角的检测区域大小
        rect = self.photo_frame_rect
        
        # 左上角
        if abs(point.x() - rect.left()) <= corner_size and abs(point.y() - rect.top()) <= corner_size:
            return 'tl'
        # 右上角
        if abs(point.x() - rect.right()) <= corner_size and abs(point.y() - rect.top()) <= corner_size:
            return 'tr'
        # 左下角
        if abs(point.x() - rect.left()) <= corner_size and abs(point.y() - rect.bottom()) <= corner_size:
            return 'bl'
        # 右下角
        if abs(point.x() - rect.right()) <= corner_size and abs(point.y() - rect.bottom()) <= corner_size:
            return 'br'
        
        return None
    
    def check_frame_edge_click(self, point):
        """检查是否点击了拍照框的边"""
        if not self.photo_frame_visible:
            return None
        
        edge_threshold = 10  # 边的检测阈值
        rect = self.photo_frame_rect
        
        # 顶边
        if abs(point.y() - rect.top()) <= edge_threshold and rect.left() < point.x() < rect.right():
            return 't'
        # 底边
        if abs(point.y() - rect.bottom()) <= edge_threshold and rect.left() < point.x() < rect.right():
            return 'b'
        # 左边
        if abs(point.x() - rect.left()) <= edge_threshold and rect.top() < point.y() < rect.bottom():
            return 'l'
        # 右边
        if abs(point.x() - rect.right()) <= edge_threshold and rect.top() < point.y() < rect.bottom():
            return 'r'
        
        return None
    
    def get_corner_cursor(self, corner):
        """获取角的鼠标样式"""
        if corner in ('tl', 'br'):
            return Qt.SizeFDiagCursor
        elif corner in ('tr', 'bl'):
            return Qt.SizeBDiagCursor
        return Qt.ArrowCursor
    
    def get_edge_cursor(self, edge):
        """获取边的鼠标样式"""
        if edge in ('t', 'b'):
            return Qt.SizeVerCursor
        elif edge in ('l', 'r'):
            return Qt.SizeHorCursor
        return Qt.ArrowCursor
    
    def resize_frame_by_corner(self, corner, delta):
        """通过拖动角来调整拍照框大小"""
        rect = self.photo_frame_rect
        
        if corner == 'tl':
            # 左上角：调整左边和顶边
            rect.setLeft(rect.left() + delta.x())
            rect.setTop(rect.top() + delta.y())
        elif corner == 'tr':
            # 右上角：调整右边和顶边
            rect.setRight(rect.right() + delta.x())
            rect.setTop(rect.top() + delta.y())
        elif corner == 'bl':
            # 左下角：调整左边和底边
            rect.setLeft(rect.left() + delta.x())
            rect.setBottom(rect.bottom() + delta.y())
        elif corner == 'br':
            # 右下角：调整右边和底边
            rect.setRight(rect.right() + delta.x())
            rect.setBottom(rect.bottom() + delta.y())
        
        # 确保最小尺寸
        if rect.width() < 100:
            if corner in ('tl', 'bl'):
                rect.setLeft(rect.right() - 100)
            else:
                rect.setRight(rect.left() + 100)
        
        if rect.height() < 100:
            if corner in ('tl', 'tr'):
                rect.setTop(rect.bottom() - 100)
            else:
                rect.setBottom(rect.top() + 100)
        
        self.photo_frame_rect = rect
    
    def resize_frame_by_edge(self, edge, delta):
        """通过拖动边来调整拍照框大小"""
        rect = self.photo_frame_rect
        
        if edge == 't':
            # 顶边
            new_top = rect.top() + delta.y()
            if rect.bottom() - new_top >= 100:
                rect.setTop(new_top)
        elif edge == 'b':
            # 底边
            new_bottom = rect.bottom() + delta.y()
            if new_bottom - rect.top() >= 100:
                rect.setBottom(new_bottom)
        elif edge == 'l':
            # 左边
            new_left = rect.left() + delta.x()
            if rect.right() - new_left >= 100:
                rect.setLeft(new_left)
        elif edge == 'r':
            # 右边
            new_right = rect.right() + delta.x()
            if new_right - rect.left() >= 100:
                rect.setRight(new_right)
        
        self.photo_frame_rect = rect
    
    def show_model_context_menu(self, model, pos):
        """显示模型右键菜单"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #ffffff;
                color: #333333;
                border: 1px solid #e0e0e0;
                padding: 5px;
                border-radius: 6px;
            }
            QMenu::item {
                padding: 8px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: rgba(52, 199, 89, 0.1);
                color: #34c759;
            }
        """)
        
        # 旋转人偶
        rotate_action = menu.addAction("🔄 旋转人偶")
        rotate_action.triggered.connect(lambda: self.show_rotation_dialog(model))
        
        # 修改名称
        rename_action = menu.addAction("✏️ 修改标签")
        rename_action.triggered.connect(lambda: self.rename_model(model))
        
        # 重置大小
        reset_scale_action = menu.addAction("↔️ 重置大小")
        reset_scale_action.triggered.connect(lambda: self.reset_model_scale(model))
        
        # 删除模型
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ 删除模型")
        delete_action.triggered.connect(lambda: self.delete_model(model))
        
        menu.exec(pos)
    
    def show_rotation_dialog(self, model):
        """显示旋转调整对话框 - 实时预览版"""
        dialog = RotationDialog(model, self, self)
        result = dialog.exec()
        # 对话框已经实时更新了旋转，这里只需要记录
        if result:
            print(f'[3D视口] 确认旋转角度: {model.rotation_y:.1f}°', flush=True)
        else:
            print(f'[3D视口] 取消旋转', flush=True)
        self.update()
    
    def rename_model(self, model):
        """重命名模型"""
        new_name, ok = QInputDialog.getText(
            self, 
            "修改标签", 
            "请输入新的标签名称:", 
            text=model.name
        )
        if ok and new_name:
            old_name = model.name
            model.name = new_name
            print(f'[3D视口] 重命名模型: {old_name} → {new_name}', flush=True)
            self.update()
    
    def reset_model_scale(self, model):
        """重置模型大小"""
        model.scale = 1.0
        print(f'[3D视口] 重置模型 {model.name} 大小', flush=True)
        self.update()
    
    def delete_model(self, model):
        """删除模型"""
        if model in self.models:
            self.models.remove(model)
            print(f'[3D视口] 删除模型: {model.name}', flush=True)
            self.update()
    
    def capture_region_screenshot(self):
        """截取指定区域"""
        if not self.capture_start or not self.capture_end:
            return
        
        # 计算区域
        x1 = min(self.capture_start.x(), self.capture_end.x())
        y1 = min(self.capture_start.y(), self.capture_end.y())
        x2 = max(self.capture_start.x(), self.capture_end.x())
        y2 = max(self.capture_start.y(), self.capture_end.y())
        
        width = x2 - x1
        height = y2 - y1
        
        if width < 10 or height < 10:
            print('[3D视口] 区域太小，取消截图', flush=True)
            return
        
        # 截取区域
        pixmap = self.grab(QRect(x1, y1, width, height))
        
        # 保存文件
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        
        # 确保JPG/3D目录存在
        try:
            import sys
            if getattr(sys, 'frozen', False):
                app_root = os.path.dirname(sys.executable)
            else:
                app_root = os.path.dirname(os.path.abspath(__file__))
            
            jpg_3d_dir = os.path.join(app_root, 'JPG', '3D')
            os.makedirs(jpg_3d_dir, exist_ok=True)
            
            # 完整保存路径
            save_path = os.path.join(jpg_3d_dir, filename)
        except Exception as e:
            print(f'[3D视口] 创建保存目录失败: {e}，将保存到当前目录', flush=True)
            save_path = filename
        
        # 保存文件
        save_success = pixmap.save(save_path)
        
        # 上传到图层与画板
        upload_success = False
        if self.window_3d and self.window_3d.photo_page is not None:
            try:
                # 获取PhotoPage的图层面板和画布
                layers_panel = getattr(self.window_3d.photo_page, 'layers_panel', None)
                canvas = getattr(layers_panel, 'canvas', None) if layers_panel else None
                
                if layers_panel is not None and canvas is not None:
                    # 获取画布尺寸
                    canvas_w = canvas.paint_layer.width()
                    canvas_h = canvas.paint_layer.height()
                    
                    # 图层名称
                    layer_name = f"3D区域截图 {timestamp}"
                    
                    print(f'[3D视口] 原始截图尺寸: {pixmap.width()}x{pixmap.height()}', flush=True)
                    print(f'[3D视口] 画布尺寸: {canvas_w}x{canvas_h}', flush=True)
                    
                    # 创建一个与画布同尺寸的透明图层
                    from PySide6.QtGui import QPixmap as QPixmapImport
                    layer_pixmap = QPixmapImport(canvas_w, canvas_h)
                    layer_pixmap.fill(Qt.transparent)
                    
                    # 将截图绘制到图层中心
                    from PySide6.QtGui import QPainter
                    painter = QPainter(layer_pixmap)
                    
                    # 计算居中位置
                    x_offset = (canvas_w - pixmap.width()) // 2
                    y_offset = (canvas_h - pixmap.height()) // 2
                    
                    painter.drawPixmap(x_offset, y_offset, pixmap)
                    painter.end()
                    
                    print(f'[3D视口] 截图位置: ({x_offset}, {y_offset})', flush=True)
                    
                    # 添加到画布和图层面板
                    from PySide6.QtCore import Qt as QtCore
                    lid = canvas.add_image_layer_at(layer_pixmap, layer_name, 0, 0, show_thumb=True)
                    
                    if lid is not None:
                        # 同步到图层面板
                        layers_panel.add_layer_pixmap(layer_pixmap, layer_name, sync_to_canvas=False)
                        
                        # 更新最后添加的图层的 canvas layer ID
                        if layers_panel.list.count() > 0:
                            item = layers_panel.list.item(layers_panel.list.count() - 1)
                            item.setData(QtCore.UserRole, lid)
                        
                        upload_success = True
                        print(f'[3D视口] ✓ 截图已添加到画布图层: {layer_name}', flush=True)
                    
                else:
                    print(f'[3D视口] ⚠️  未找到图层面板或画布', flush=True)
            except Exception as e:
                print(f'[3D视口] ❌ 上传到图层失败: {e}', flush=True)
                import traceback
                traceback.print_exc()
        else:
            print(f'[3D视口] ⚠️  PhotoPage引用未设置', flush=True)
        
        # 显示结果消息
        if save_success:
            msg = f"📷 区域截图已保存到:\nJPG/3D/{filename}\n\n截图尺寸: {pixmap.width()}x{pixmap.height()}"
            if upload_success:
                msg += f"\n\n✓ 已添加到画布图层"
            else:
                msg += f"\n\n⚠️  未上传到图层（PhotoPage未连接）"
            
            print(f'[3D视口] ✓ 区域截图已保存: JPG/3D/{filename}', flush=True)
            QMessageBox.information(self, "截图成功", msg)
        else:
            print(f'[3D视口] ❌ 截图保存失败', flush=True)
            QMessageBox.warning(self, "截图失败", "无法保存截图文件")
    
    def paintEvent(self, event):
        """绘制3D视口"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 纯白色背景
        painter.fillRect(self.rect(), QColor(255, 255, 255))
        
        # 绘制网格（如果启用）- 3D透视网格
        if self.show_grid:
            self.draw_3d_grid(painter)
        
        # 绘制模型
        self.draw_models(painter)
        
        # 绘制拍照框（如果可见）
        if self.photo_frame_visible:
            self.draw_photo_frame(painter)
        
        # 如果没有模型，显示提示
        if not self.models:
            painter.setPen(QColor(120, 120, 120))
            font = QFont("Microsoft YaHei", 14)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter, 
                           "3D 视口\n\n从左侧工具箱添加人偶\n滚轮放大缩小 | 中键旋转视角\nG键移动 | R键旋转 | S键缩放")
    
    def project_3d(self, x, y, z):
        """3D到2D透视投影（修正版）- 支持相机焦点偏移"""
        # 将坐标转换为相对于相机焦点的坐标
        x_rel = x - self.camera_focus_x
        y_rel = y - self.camera_focus_y
        z_rel = z - self.camera_focus_z
        
        # 相机参数
        rad_x = math.radians(self.camera_angle_x)
        rad_y = math.radians(self.camera_angle_y)
        
        # 旋转变换（绕Y轴和X轴）- 相机坐标系变换
        # 先绕Y轴旋转（水平旋转）
        cos_y = math.cos(rad_y)
        sin_y = math.sin(rad_y)
        x_rot = x_rel * cos_y - z_rel * sin_y
        z_rot = x_rel * sin_y + z_rel * cos_y
        
        # 再绕X轴旋转（垂直旋转）
        cos_x = math.cos(rad_x)
        sin_x = math.sin(rad_x)
        y_rot = y_rel * cos_x - z_rot * sin_x
        z_final = y_rel * sin_x + z_rot * cos_x
        
        # 透视投影 - 防止除零和负深度
        depth = self.camera_distance + z_final
        if depth <= 10:  # 防止物体太靠近相机
            depth = 10
        
        scale = self.camera_distance / depth
        
        # 转换到屏幕坐标（中心点对齐）
        screen_x = int(self.width() / 2 + x_rot * scale)
        screen_y = int(self.height() / 2 - y_rot * scale)
        
        return screen_x, screen_y, z_final
    
    def draw_3d_grid(self, painter):
        """绘制3D透视网格（修正版）- 网格线固定在地面，不受缩放影响"""
        # 使用透明灰色线条
        painter.setPen(QPen(QColor(150, 150, 150, 80), 1))  # 透明度80/255
        
        # 网格参数 - 使用固定的世界坐标
        grid_size = 500  # 增大网格范围
        grid_step = 50
        ground_y = -100  # 地面固定高度（世界Y坐标）
        
        # 绘制地面网格（XZ平面，Y固定）
        # X方向的网格线（沿着世界Z轴延伸）
        for i in range(-grid_size, grid_size + 1, grid_step):
            # 在世界坐标系中，X固定，Z从-grid_size到+grid_size
            x1, y1, z1 = self.project_3d(i, ground_y, -grid_size)
            x2, y2, z2 = self.project_3d(i, ground_y, grid_size)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))
        
        # Z方向的网格线（沿着世界X轴延伸）
        for i in range(-grid_size, grid_size + 1, grid_step):
            # 在世界坐标系中，Z固定，X从-grid_size到+grid_size
            x1, y1, z1 = self.project_3d(-grid_size, ground_y, i)
            x2, y2, z2 = self.project_3d(grid_size, ground_y, i)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))
    
    def draw_photo_frame(self, painter):
        """绘制拍照框（红色可调整框）"""
        rect = self.photo_frame_rect
        
        # 绘制半透明红色填充
        painter.setBrush(QBrush(QColor(255, 50, 50, 30)))
        painter.setPen(Qt.NoPen)
        painter.drawRect(rect)
        
        # 绘制红色边框
        painter.setPen(QPen(QColor(255, 50, 50), 3, Qt.SolidLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)
        
        # 绘制虚线指示（四条虚线指向四个角）
        painter.setPen(QPen(QColor(255, 50, 50), 2, Qt.DashLine))
        
        # 左上角虚线
        painter.drawLine(rect.left() - 30, rect.top(), rect.left(), rect.top())
        painter.drawLine(rect.left(), rect.top() - 30, rect.left(), rect.top())
        
        # 右上角虚线
        painter.drawLine(rect.right(), rect.top() - 30, rect.right(), rect.top())
        painter.drawLine(rect.right() + 30, rect.top(), rect.right(), rect.top())
        
        # 左下角虚线
        painter.drawLine(rect.left() - 30, rect.bottom(), rect.left(), rect.bottom())
        painter.drawLine(rect.left(), rect.bottom() + 30, rect.left(), rect.bottom())
        
        # 右下角虚线
        painter.drawLine(rect.right(), rect.bottom() + 30, rect.right(), rect.bottom())
        painter.drawLine(rect.right() + 30, rect.bottom(), rect.right(), rect.bottom())
        
        # 绘制四个角的控制点（红色圆圈）
        painter.setPen(QPen(QColor(255, 50, 50), 2))
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        
        corner_size = 10
        # 左上角
        painter.drawEllipse(rect.left() - corner_size // 2, rect.top() - corner_size // 2, corner_size, corner_size)
        # 右上角
        painter.drawEllipse(rect.right() - corner_size // 2, rect.top() - corner_size // 2, corner_size, corner_size)
        # 左下角
        painter.drawEllipse(rect.left() - corner_size // 2, rect.bottom() - corner_size // 2, corner_size, corner_size)
        # 右下角
        painter.drawEllipse(rect.right() - corner_size // 2, rect.bottom() - corner_size // 2, corner_size, corner_size)
        
        # 绘制四条边的中点控制点
        # 顶边中点
        painter.drawEllipse(rect.center().x() - corner_size // 2, rect.top() - corner_size // 2, corner_size, corner_size)
        # 底边中点
        painter.drawEllipse(rect.center().x() - corner_size // 2, rect.bottom() - corner_size // 2, corner_size, corner_size)
        # 左边中点
        painter.drawEllipse(rect.left() - corner_size // 2, rect.center().y() - corner_size // 2, corner_size, corner_size)
        # 右边中点
        painter.drawEllipse(rect.right() - corner_size // 2, rect.center().y() - corner_size // 2, corner_size, corner_size)
        
        # 显示拍照框尺寸信息
        painter.setPen(QColor(255, 50, 50))
        font = QFont("Microsoft YaHei", 10, QFont.Bold)
        painter.setFont(font)
        
        size_text = f"{rect.width()} x {rect.height()}"
        text_rect = painter.fontMetrics().boundingRect(size_text)
        
        # 在框的顶部中间显示尺寸
        text_x = rect.center().x() - text_rect.width() // 2
        text_y = rect.top() - 10
        
        # 绘制背景
        painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
        painter.setPen(Qt.NoPen)
        painter.drawRect(text_x - 5, text_y - text_rect.height() - 2, text_rect.width() + 10, text_rect.height() + 4)
        
        # 绘制文字
        painter.setPen(QColor(255, 50, 50))
        painter.drawText(text_x, text_y, size_text)
        
        # 提示文字
        hint_text = "拖动角或边调整大小"
        painter.setPen(QColor(255, 50, 50))
        painter.setFont(QFont("Microsoft YaHei", 9))
        painter.drawText(rect.left(), rect.bottom() + 20, hint_text)
    

    
    def draw_models(self, painter):
        """绘制模型"""
        for model in self.models:
            # 绘制选中高亮（红色描边）
            if model.show_gizmo:
                self.draw_selection_outline(painter, model)
            
            if model.type == "mannequin":
                self.draw_mannequin(painter, model)
            elif model.type == "fbx":
                self.draw_fbx(painter, model)
    
    def draw_selection_outline(self, painter, model):
        """绘制选中模型的红色描边"""
        # 在模型周围绘制地面圆圈
        base_x, base_y, base_z = model.x, model.z, model.y
        
        points = []
        for angle in range(0, 360, 15):
            rad = math.radians(angle)
            x = base_x + 70 * math.cos(rad)
            z = base_z + 70 * math.sin(rad)
            px, py, pz = self.project_3d(x, base_y - 80, z)
            points.append((int(px), int(py)))
        
        painter.setPen(QPen(QColor(255, 50, 50), 3, Qt.SolidLine))
        for i in range(len(points)):
            x1, y1 = points[i]
            x2, y2 = points[(i + 1) % len(points)]
            painter.drawLine(x1, y1, x2, y2)
    
    def draw_mannequin(self, painter, model):
        """绘制改进的3D人形人偶（更加逼真）"""
        # 3D空间位置
        base_x = model.x
        base_y = model.z  # 垂直高度
        base_z = model.y  # 深度
        scale = model.scale * 100
        rotation = model.rotation_y  # Y轴旋转
        
        # 使用模型自己的颜色
        body_color = model.color
        head_color = model.color.lighter(115)
        limb_color = model.color.darker(105)
        
        # 定义人偶尺寸（比例更真实的人形）
        head_radius = 12 * scale / 100
        neck_height = 8 * scale / 100
        torso_width = 22 * scale / 100
        torso_height = 35 * scale / 100
        torso_depth = 15 * scale / 100
        
        leg_width = 8 * scale / 100
        leg_height = 40 * scale / 100
        leg_depth = 8 * scale / 100
        
        arm_width = 6 * scale / 100
        arm_length = 38 * scale / 100
        arm_depth = 6 * scale / 100
        
        ground_y = -85 * scale / 100
        
        # 旋转辅助函数
        def rotate_point(x, z, angle):
            rad = math.radians(angle)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)
            new_x = x * cos_a - z * sin_a
            new_z = x * sin_a + z * cos_a
            return new_x, new_z
        
        # 1. 绘制腿部（两条腿）
        leg_y = ground_y + leg_height / 2
        leg_spacing = torso_width / 4
        
        # 左腿
        lx, lz = rotate_point(-leg_spacing, 0, rotation)
        self.draw_3d_box_rotated(painter, base_x + lx, base_y + leg_y, base_z + lz,
                        leg_width, leg_height, leg_depth, rotation,
                        limb_color, limb_color.darker(120))
        
        # 右腿
        rx, rz = rotate_point(leg_spacing, 0, rotation)
        self.draw_3d_box_rotated(painter, base_x + rx, base_y + leg_y, base_z + rz,
                        leg_width, leg_height, leg_depth, rotation,
                        limb_color, limb_color.darker(120))
        
        # 2. 绘制躯干（身体）
        torso_y = ground_y + leg_height + torso_height / 2
        rx, rz = rotate_point(0, 0, rotation)
        self.draw_3d_box_rotated(painter, base_x + rx, base_y + torso_y, base_z + rz,
                        torso_width, torso_height, torso_depth, rotation,
                        body_color, body_color.darker(115))
        
        # 3. 绘制手臂（两条手臂）
        arm_y = ground_y + leg_height + torso_height - arm_length / 3
        arm_offset_x = torso_width / 2 + arm_width / 2
        
        # 左臂
        lx, lz = rotate_point(-arm_offset_x, 0, rotation)
        self.draw_3d_box_rotated(painter, base_x + lx, base_y + arm_y, base_z + lz,
                        arm_width, arm_length, arm_depth, rotation,
                        limb_color, limb_color.darker(120))
        
        # 右臂
        rx, rz = rotate_point(arm_offset_x, 0, rotation)
        self.draw_3d_box_rotated(painter, base_x + rx, base_y + arm_y, base_z + rz,
                        arm_width, arm_length, arm_depth, rotation,
                        limb_color, limb_color.darker(120))
        
        # 4. 绘制颈部
        neck_y = ground_y + leg_height + torso_height + neck_height / 2
        rx, rz = rotate_point(0, 0, rotation)
        self.draw_3d_box_rotated(painter, base_x + rx, base_y + neck_y, base_z + rz,
                        head_radius * 0.7, neck_height, head_radius * 0.7, rotation,
                        body_color.darker(105), body_color.darker(125))
        
        # 5. 绘制头部（球形，用立方体近似）
        head_y = ground_y + leg_height + torso_height + neck_height + head_radius
        rx, rz = rotate_point(0, 0, rotation)
        self.draw_3d_box_rotated(painter, base_x + rx, base_y + head_y, base_z + rz,
                        head_radius * 2, head_radius * 2, head_radius * 2, rotation,
                        head_color, head_color.darker(115))
        
        # 6. 绘制眼睛（两个眼睛）
        eye_y_offset = head_radius * 0.3  # 眼睛在头部偏上位置
        eye_x_spacing = head_radius * 0.5  # 两眼间距
        eye_z_forward = head_radius * 1.1  # 眼睛在脸部前方
        eye_radius = head_radius * 0.25  # 眼睛大小
        
        # 左眼
        left_eye_x, left_eye_z = rotate_point(-eye_x_spacing, eye_z_forward, rotation)
        left_eye_screen_x, left_eye_screen_y, _ = self.project_3d(
            base_x + left_eye_x, 
            base_y + head_y + eye_y_offset, 
            base_z + left_eye_z
        )
        
        # 右眼
        right_eye_x, right_eye_z = rotate_point(eye_x_spacing, eye_z_forward, rotation)
        right_eye_screen_x, right_eye_screen_y, _ = self.project_3d(
            base_x + right_eye_x, 
            base_y + head_y + eye_y_offset, 
            base_z + right_eye_z
        )
        
        # 绘制眼睛（白色眼球 + 黑色瞳孔）
        painter.setPen(Qt.NoPen)
        
        # 左眼
        painter.setBrush(QBrush(QColor(255, 255, 255)))  # 白色眼球
        painter.drawEllipse(QPointF(left_eye_screen_x, left_eye_screen_y), 
                          eye_radius * 1.2, eye_radius * 1.2)
        painter.setBrush(QBrush(QColor(50, 50, 50)))  # 黑色瞳孔
        painter.drawEllipse(QPointF(left_eye_screen_x, left_eye_screen_y), 
                          eye_radius * 0.7, eye_radius * 0.7)
        
        # 右眼
        painter.setBrush(QBrush(QColor(255, 255, 255)))  # 白色眼球
        painter.drawEllipse(QPointF(right_eye_screen_x, right_eye_screen_y), 
                          eye_radius * 1.2, eye_radius * 1.2)
        painter.setBrush(QBrush(QColor(50, 50, 50)))  # 黑色瞳孔
        painter.drawEllipse(QPointF(right_eye_screen_x, right_eye_screen_y), 
                          eye_radius * 0.7, eye_radius * 0.7)
        
        # 绘制XYZ控制器（如果显示）
        if model.show_gizmo:
            self.draw_gizmo(painter, base_x, base_y, base_z)
        
        # 名称标签
        label_y_offset = head_y + head_radius * 1.5
        label_x, label_y, label_z = self.project_3d(base_x, base_y + label_y_offset, base_z)
        painter.setPen(QColor(80, 80, 80))
        font = QFont("Microsoft YaHei", 10, QFont.Bold)
        painter.setFont(font)
        painter.drawText(int(label_x - 50), int(label_y), 100, 20, Qt.AlignCenter, model.name)
    
    def draw_3d_box_rotated(self, painter, cx, cy, cz, width, height, depth, rotation_y, color, edge_color):
        """绘制带Y轴旋转的3D立方体"""
        hw, hh, hd = width / 2, height / 2, depth / 2
        
        # 8个顶点（相对于中心）
        local_vertices = [
            (-hw, -hh, -hd),  # 0: 左下前
            (hw, -hh, -hd),   # 1: 右下前
            (hw, hh, -hd),    # 2: 右上前
            (-hw, hh, -hd),   # 3: 左上前
            (-hw, -hh, hd),   # 4: 左下后
            (hw, -hh, hd),    # 5: 右下后
            (hw, hh, hd),     # 6: 右上后
            (-hw, hh, hd),    # 7: 左上后
        ]
        
        # 应用Y轴旋转
        rad = math.radians(rotation_y)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        
        rotated_vertices = []
        for x, y, z in local_vertices:
            # Y轴旋转
            rx = x * cos_a - z * sin_a
            rz = x * sin_a + z * cos_a
            rotated_vertices.append((cx + rx, cy + y, cz + rz))
        
        # 投影顶点
        projected = [self.project_3d(*v) for v in rotated_vertices]
        
        # 6个面（按深度排序）
        faces = [
            ([0, 1, 2, 3], color.lighter(110)),  # 前面
            ([4, 5, 6, 7], color.darker(120)),   # 后面
            ([0, 1, 5, 4], color.darker(130)),   # 底面
            ([3, 2, 6, 7], color.lighter(105)),  # 顶面
            ([0, 3, 7, 4], color.darker(110)),   # 左面
            ([1, 2, 6, 5], color.lighter(100)),  # 右面
        ]
        
        # 按平均深度排序（远近法）
        face_depths = []
        for indices, _ in faces:
            avg_z = sum(projected[i][2] for i in indices) / len(indices)
            face_depths.append(avg_z)
        
        sorted_faces = sorted(zip(faces, face_depths), key=lambda x: x[1], reverse=True)
        
        # 绘制面
        for (indices, face_color), _ in sorted_faces:
            points = [QPointF(projected[i][0], projected[i][1]) for i in indices]
            path = QPainterPath()
            path.moveTo(points[0])
            for p in points[1:]:
                path.lineTo(p)
            path.closeSubpath()
            
            painter.setBrush(QBrush(face_color))
            painter.setPen(QPen(edge_color, 1))
            painter.drawPath(path)
    
    def draw_3d_box(self, painter, cx, cy, cz, width, height, depth, color, edge_color):
        """绘制3D立方体"""
        hw, hh, hd = width / 2, height / 2, depth / 2
        
        # 8个顶点
        vertices = [
            (cx - hw, cy - hh, cz - hd),  # 0: 左下前
            (cx + hw, cy - hh, cz - hd),  # 1: 右下前
            (cx + hw, cy + hh, cz - hd),  # 2: 右上前
            (cx - hw, cy + hh, cz - hd),  # 3: 左上前
            (cx - hw, cy - hh, cz + hd),  # 4: 左下后
            (cx + hw, cy - hh, cz + hd),  # 5: 右下后
            (cx + hw, cy + hh, cz + hd),  # 6: 右上后
            (cx - hw, cy + hh, cz + hd),  # 7: 左上后
        ]
        
        # 投影顶点
        projected = [self.project_3d(*v) for v in vertices]
        
        # 6个面（按深度排序）
        faces = [
            ([0, 1, 2, 3], color.lighter(110)),  # 前面
            ([4, 5, 6, 7], color.darker(120)),   # 后面
            ([0, 1, 5, 4], color.darker(130)),   # 底面
            ([3, 2, 6, 7], color.lighter(105)),  # 顶面
            ([0, 3, 7, 4], color.darker(110)),   # 左面
            ([1, 2, 6, 5], color.lighter(100)),  # 右面
        ]
        
        # 按平均深度排序（远近法）
        face_depths = []
        for indices, _ in faces:
            avg_z = sum(projected[i][2] for i in indices) / len(indices)
            face_depths.append(avg_z)
        
        sorted_faces = sorted(zip(faces, face_depths), key=lambda x: x[1], reverse=True)
        
        # 绘制面
        for (indices, face_color), _ in sorted_faces:
            points = [QPointF(projected[i][0], projected[i][1]) for i in indices]
            path = QPainterPath()
            path.moveTo(points[0])
            for p in points[1:]:
                path.lineTo(p)
            path.closeSubpath()
            
            painter.setBrush(QBrush(face_color))
            painter.setPen(QPen(edge_color, 1))
            painter.drawPath(path)
    
    def draw_3d_cylinder(self, painter, cx, cy, cz, radius, height, color, edge_color):
        """绘制3D圆柱体"""
        segments = 12
        
        # 顶部圆
        top_points = []
        for i in range(segments):
            angle = 2 * math.pi * i / segments
            x = cx + radius * math.cos(angle)
            z = cz + radius * math.sin(angle)
            px, py, pz = self.project_3d(x, cy + height / 2, z)
            top_points.append((px, py, pz))
        
        # 底部圆
        bottom_points = []
        for i in range(segments):
            angle = 2 * math.pi * i / segments
            x = cx + radius * math.cos(angle)
            z = cz + radius * math.sin(angle)
            px, py, pz = self.project_3d(x, cy - height / 2, z)
            bottom_points.append((px, py, pz))
        
        # 绘制侧面
        for i in range(segments):
            next_i = (i + 1) % segments
            
            points = [
                QPointF(bottom_points[i][0], bottom_points[i][1]),
                QPointF(bottom_points[next_i][0], bottom_points[next_i][1]),
                QPointF(top_points[next_i][0], top_points[next_i][1]),
                QPointF(top_points[i][0], top_points[i][1]),
            ]
            
            path = QPainterPath()
            path.moveTo(points[0])
            for p in points[1:]:
                path.lineTo(p)
            path.closeSubpath()
            
            brightness = 90 + (i % 2) * 20
            face_color = color.lighter(brightness)
            painter.setBrush(QBrush(face_color))
            painter.setPen(QPen(edge_color, 1))
            painter.drawPath(path)
        
        # 绘制顶部圆盘
        top_polygon = [QPointF(p[0], p[1]) for p in top_points]
        path = QPainterPath()
        path.moveTo(top_polygon[0])
        for p in top_polygon[1:]:
            path.lineTo(p)
        path.closeSubpath()
        painter.setBrush(QBrush(color.lighter(120)))
        painter.setPen(QPen(edge_color, 1))
        painter.drawPath(path)
    
    def draw_3d_sphere(self, painter, cx, cy, cz, radius, color):
        """绘制3D球体（简化为椭圆）"""
        px, py, pz = self.project_3d(cx, cy, cz)
        
        # 根据深度调整大小
        scale = self.camera_distance / (self.camera_distance + pz) if (self.camera_distance + pz) > 0 else 0.5
        r = int(radius * scale)
        
        # 渐变效果（光照）
        gradient_color = color.lighter(130)
        painter.setBrush(QBrush(gradient_color))
        painter.setPen(QPen(color.darker(120), 1))
        painter.drawEllipse(px - r, py - r, r * 2, r * 2)
    
    def draw_gizmo(self, painter, base_x, base_y, base_z):
        """绘制XYZ控制器"""
        gizmo_length = 80
        arrow_size = 15
        
        # 原点
        ox, oy, oz = self.project_3d(base_x, base_y, base_z)
        
        # X轴（红色）
        x_end = self.project_3d(base_x + gizmo_length, base_y, base_z)
        painter.setPen(QPen(QColor(255, 50, 50), 4))
        painter.drawLine(int(ox), int(oy), int(x_end[0]), int(x_end[1]))
        # 箭头
        painter.setBrush(QBrush(QColor(255, 50, 50)))
        painter.drawEllipse(int(x_end[0] - arrow_size / 2), int(x_end[1] - arrow_size / 2), arrow_size, arrow_size)
        painter.setFont(QFont("Arial", 12, QFont.Bold))
        painter.drawText(int(x_end[0]) + 10, int(x_end[1]) + 5, "X")
        
        # Y轴（绿色）
        y_end = self.project_3d(base_x, base_y + gizmo_length, base_z)
        painter.setPen(QPen(QColor(50, 255, 50), 4))
        painter.drawLine(int(ox), int(oy), int(y_end[0]), int(y_end[1]))
        painter.setBrush(QBrush(QColor(50, 255, 50)))
        painter.drawEllipse(int(y_end[0] - arrow_size / 2), int(y_end[1] - arrow_size / 2), arrow_size, arrow_size)
        painter.drawText(int(y_end[0]) + 10, int(y_end[1]) + 5, "Y")
        
        # Z轴（蓝色）
        z_end = self.project_3d(base_x, base_y, base_z + gizmo_length)
        painter.setPen(QPen(QColor(50, 50, 255), 4))
        painter.drawLine(int(ox), int(oy), int(z_end[0]), int(z_end[1]))
        painter.setBrush(QBrush(QColor(50, 50, 255)))
        painter.drawEllipse(int(z_end[0] - arrow_size / 2), int(z_end[1] - arrow_size / 2), arrow_size, arrow_size)
        painter.drawText(int(z_end[0]) + 10, int(z_end[1]) + 5, "Z")
    
    def draw_mini_map(self, painter):
        """绘制左上角场景缩略图"""
        map_width = 200
        map_height = 150
        margin = 10
        
        # 绘制缩略图背景
        painter.setPen(QPen(QColor(100, 100, 100), 2))
        painter.setBrush(QBrush(QColor(30, 30, 30, 200)))
        painter.drawRect(margin, margin, map_width, map_height)
        
        # 标题
        painter.setPen(QColor(200, 200, 200))
        painter.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        painter.drawText(margin + 5, margin + 15, "场景预览")
        
        # 绘制网格
        painter.setPen(QPen(QColor(60, 60, 60), 1))
        grid_step = 25
        for i in range(0, map_width, grid_step):
            painter.drawLine(margin + i, margin + 25, margin + i, margin + map_height)
        for i in range(25, map_height, grid_step):
            painter.drawLine(margin, margin + i, margin + map_width, margin + i)
        
        # 绘制模型位置（俯视图）
        center_x = margin + map_width / 2
        center_y = margin + map_height / 2
        scale_factor = 0.15  # 缩放因子
        
        for model in self.models:
            # 计算缩略图位置
            mini_x = center_x + model.x * scale_factor
            mini_y = center_y + model.y * scale_factor
            
            # 绘制模型点
            if model.show_gizmo:
                # 选中的模型用红色
                painter.setBrush(QBrush(QColor(255, 50, 50)))
                painter.setPen(QPen(QColor(255, 100, 100), 2))
                painter.drawEllipse(int(mini_x - 6), int(mini_y - 6), 12, 12)
            else:
                # 未选中用白色
                painter.setBrush(QBrush(model.color))
                painter.setPen(QPen(QColor(150, 150, 150), 1))
                painter.drawEllipse(int(mini_x - 4), int(mini_y - 4), 8, 8)
            
            # 绘制名称
            painter.setPen(QColor(200, 200, 200))
            painter.setFont(QFont("Microsoft YaHei", 7))
            painter.drawText(int(mini_x + 8), int(mini_y + 3), model.name)
        
        # 绘制相机方向指示
        cam_arrow_len = 20
        cam_x = center_x
        cam_y = margin + map_height - 15
        angle_rad = math.radians(self.camera_angle_y)
        end_x = cam_x + cam_arrow_len * math.sin(angle_rad)
        end_y = cam_y - cam_arrow_len * math.cos(angle_rad)
        
        painter.setPen(QPen(QColor(100, 200, 255), 2))
        painter.drawLine(int(cam_x), int(cam_y), int(end_x), int(end_y))
        painter.setBrush(QBrush(QColor(100, 200, 255)))
        painter.drawEllipse(int(end_x - 3), int(end_y - 3), 6, 6)
        
        painter.setFont(QFont("Microsoft YaHei", 7))
        painter.drawText(int(cam_x - 20), int(cam_y + 12), "相机")
    
    def draw_view_orb(self, painter):
        """绘制右上角视角球"""
        orb_x, orb_y = self.get_view_orb_position()
        orb_radius = 50
        
        # 绘制背景圆
        painter.setPen(QPen(QColor(80, 80, 80), 2))
        painter.setBrush(QBrush(QColor(40, 40, 40, 220)))
        painter.drawEllipse(int(orb_x - orb_radius), int(orb_y - orb_radius), 
                           orb_radius * 2, orb_radius * 2)
        
        # 绘制3D坐标轴参考（迷你版）
        axis_len = 30
        
        # 根据当前相机角度计算轴的方向
        rad_x = math.radians(self.camera_angle_x)
        rad_y = math.radians(self.camera_angle_y)
        
        # X轴（红色）
        x_dir_x = math.cos(rad_y) * axis_len
        x_dir_y = -math.sin(rad_y) * axis_len * math.cos(rad_x)
        painter.setPen(QPen(QColor(255, 80, 80), 3))
        painter.drawLine(int(orb_x), int(orb_y), 
                        int(orb_x + x_dir_x), int(orb_y + x_dir_y))
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        painter.drawText(int(orb_x + x_dir_x + 5), int(orb_y + x_dir_y + 5), "X")
        
        # Y轴（绿色，向上）
        y_dir_y = -axis_len * math.sin(rad_x)
        painter.setPen(QPen(QColor(80, 255, 80), 3))
        painter.drawLine(int(orb_x), int(orb_y), 
                        int(orb_x), int(orb_y + y_dir_y))
        painter.drawText(int(orb_x + 5), int(orb_y + y_dir_y - 5), "Y")
        
        # Z轴（蓝色）
        z_dir_x = -math.sin(rad_y) * axis_len
        z_dir_y = -math.cos(rad_y) * axis_len * math.cos(rad_x)
        painter.setPen(QPen(QColor(80, 80, 255), 3))
        painter.drawLine(int(orb_x), int(orb_y), 
                        int(orb_x + z_dir_x), int(orb_y + z_dir_y))
        painter.drawText(int(orb_x + z_dir_x + 5), int(orb_y + z_dir_y + 5), "Z")
        
        # 中心点
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawEllipse(int(orb_x - 4), int(orb_y - 4), 8, 8)
        
        # 标题
        painter.setPen(QColor(200, 200, 200))
        painter.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        painter.drawText(int(orb_x - 35), int(orb_y - orb_radius - 10), "视角控制")
        
        # 提示文字
        painter.setFont(QFont("Microsoft YaHei", 8))
        painter.drawText(int(orb_x - 30), int(orb_y + orb_radius + 15), "拖动旋转")
    
    def draw_fbx(self, painter, model):
        """绘制FBX模型"""
        pos = self.get_model_screen_position(model)
        center_x = int(pos.x())
        center_y = int(pos.y())
        
        # 如果被选中，绘制高亮边框
        if model.selected:
            painter.setPen(QPen(QColor(255, 255, 0), 3, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(center_x - 60, center_y - 80, 120, 160)
        
        # 如果有网格数据，尝试绘制
        if model.mesh_data and 'vertices' in model.mesh_data and model.mesh_data['vertices'] is not None:
            self.draw_mesh(painter, model, center_x, center_y)
        else:
            # 默认显示：绘制简化的人形轮廓表示FBX模型
            self.draw_fbx_placeholder(painter, center_x, center_y, model.name)
        
        # 名称标签
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Microsoft YaHei", 10)
        painter.setFont(font)
        painter.drawText(center_x - 60, center_y + 90, 120, 20, 
                        Qt.AlignCenter, model.name)
    
    def draw_mesh(self, painter, model, center_x, center_y):
        """绘制网格数据"""
        try:
            vertices = model.mesh_data['vertices']
            
            if vertices is None or len(vertices) == 0:
                print(f'[3D视口] 顶点数据为空', flush=True)
                self.draw_fbx_placeholder(painter, center_x, center_y, model.name)
                return
            
            print(f'[3D视口] 开始绘制网格: {len(vertices)} 个顶点', flush=True)
            
            # 计算边界框
            import numpy as np
            vertices_array = np.array(vertices)
            
            min_coords = vertices_array.min(axis=0)
            max_coords = vertices_array.max(axis=0)
            
            # 计算尺寸
            size_x = max_coords[0] - min_coords[0]
            size_y = max_coords[1] - min_coords[1] if vertices_array.shape[1] > 1 else 1
            size_z = max_coords[2] - min_coords[2] if vertices_array.shape[1] > 2 else 1
            
            max_size = max(size_x, size_y, size_z, 0.001)
            
            # 缩放到合适大小（目标高度约100像素）
            scale_factor = 100 / max_size
            
            print(f'[3D视口] 模型尺寸: {size_x:.2f} x {size_y:.2f} x {size_z:.2f}', flush=True)
            print(f'[3D视口] 缩放系数: {scale_factor:.2f}', flush=True)
            
            # 计算中心点
            center = (min_coords + max_coords) / 2
            
            # 绘制边界框
            painter.setPen(QPen(QColor(100, 200, 255), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            box_width = int(size_x * scale_factor)
            box_height = int(size_y * scale_factor)
            painter.drawRect(
                center_x - box_width // 2,
                center_y - box_height // 2,
                box_width,
                box_height
            )
            
            # 绘制顶点
            painter.setPen(QPen(QColor(100, 200, 255), 1))
            painter.setBrush(QBrush(QColor(150, 220, 255)))
            
            # 控制绘制的顶点数量以提高性能
            max_points = 500
            step = max(1, len(vertices) // max_points)
            
            points_drawn = 0
            for i in range(0, len(vertices), step):
                v = vertices[i]
                # 转换到屏幕坐标
                x = int(center_x + (v[0] - center[0]) * scale_factor)
                y = int(center_y - (v[1] - center[1]) * scale_factor)  # Y轴反转
                
                # 绘制点
                painter.drawEllipse(x - 1, y - 1, 3, 3)
                points_drawn += 1
            
            print(f'[3D视口] ✓ 成功绘制 {points_drawn} 个顶点', flush=True)
            
            # 绘制面（如果有）
            if 'faces' in model.mesh_data and model.mesh_data['faces'] is not None:
                faces = model.mesh_data['faces']
                painter.setPen(QPen(QColor(80, 160, 200), 1))
                
                # 只绘制一部分面
                max_faces = 100
                face_step = max(1, len(faces) // max_faces)
                
                for i in range(0, min(len(faces), max_faces * face_step), face_step):
                    face = faces[i]
                    if len(face) >= 3:
                        # 绘制三角形的边
                        for j in range(3):
                            v1_idx = face[j]
                            v2_idx = face[(j + 1) % 3]
                            
                            if v1_idx < len(vertices) and v2_idx < len(vertices):
                                v1 = vertices[v1_idx]
                                v2 = vertices[v2_idx]
                                
                                x1 = int(center_x + (v1[0] - center[0]) * scale_factor)
                                y1 = int(center_y - (v1[1] - center[1]) * scale_factor)
                                x2 = int(center_x + (v2[0] - center[0]) * scale_factor)
                                y2 = int(center_y - (v2[1] - center[1]) * scale_factor)
                                
                                painter.drawLine(x1, y1, x2, y2)
            
        except Exception as e:
            print(f'[3D视口] ❌ 绘制网格失败: {e}', flush=True)
            import traceback
            traceback.print_exc()
            # 回退到占位符
            self.draw_fbx_placeholder(painter, center_x, center_y, model.name)
    
    def draw_fbx_placeholder(self, painter, center_x, center_y, name):
        """绘制FBX占位符（3D人形轮廓）"""
        # 使用类似的3D投影方法绘制占位符
        # 简化处理：直接在2D位置绘制
        painter.setPen(QPen(QColor(100, 150, 255), 3))
        painter.setBrush(QBrush(QColor(80, 120, 200, 150)))
        
        # 头部
        painter.drawEllipse(center_x - 15, center_y - 70, 30, 30)
        
        # 身体（梯形）
        body_points = [
            QPointF(center_x - 20, center_y - 35),
            QPointF(center_x + 20, center_y - 35),
            QPointF(center_x + 25, center_y + 20),
            QPointF(center_x - 25, center_y + 20)
        ]
        body_path = QPainterPath()
        body_path.moveTo(body_points[0])
        for p in body_points[1:]:
            body_path.lineTo(p)
        body_path.closeSubpath()
        painter.drawPath(body_path)
        
        # 手臂
        painter.drawLine(center_x - 20, center_y - 30, center_x - 40, center_y + 10)
        painter.drawLine(center_x + 20, center_y - 30, center_x + 40, center_y + 10)
        
        # 腿
        painter.drawLine(center_x - 15, center_y + 20, center_x - 20, center_y + 70)
        painter.drawLine(center_x + 15, center_y + 20, center_x + 20, center_y + 70)
        
        # FBX标识
        painter.setPen(QColor(255, 255, 100))
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        painter.drawText(center_x - 20, center_y - 5, 40, 20, Qt.AlignCenter, "FBX")
    
    def add_model(self, model_name, model_type="mannequin", file_path=None):
        """添加模型到视口"""
        model = Model3D(model_name, model_type, file_path)
        # 自动分散位置
        index = len(self.models)
        model.x = (index % 3 - 1) * 150
        model.y = (index // 3) * 200
        model.z = -80  # 默认在地面上
        # 设置当前颜色
        model.color = QColor(self.current_mannequin_color)
        self.models.append(model)
        self.model_added.emit(model_name)
        self.update()
        print(f'[3D视口] 已添加模型: {model_name} (类型: {model_type})', flush=True)


class RotationDialog(QDialog):
    """360度旋转调整对话框 - 实时预览版"""
    
    def __init__(self, model, viewport, parent=None):
        super().__init__(parent)
        self.model = model
        self.viewport = viewport  # 3D视口引用，用于实时更新
        self.original_rotation = model.rotation_y  # 保存原始角度，用于取消
        self.setWindowTitle(f"旋转 - {model.name}")
        self.setModal(True)
        self.resize(400, 220)
        self.init_ui()
    
    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题
        title = QLabel(f"调整 {self.model.name} 的旋转角度")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #333333;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # 提示信息
        hint = QLabel("拖动滑块可实时预览旋转效果")
        hint.setStyleSheet("font-size: 11px; color: #888888;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)
        
        # 当前角度显示
        self.angle_label = QLabel(f"当前角度: {self.model.rotation_y:.1f}°")
        self.angle_label.setStyleSheet("font-size: 13px; color: #4a9eff; font-weight: bold;")
        self.angle_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.angle_label)
        
        # 旋转滑块
        slider_layout = QHBoxLayout()
        
        label_0 = QLabel("0°")
        label_0.setStyleSheet("font-size: 11px; color: #888888;")
        slider_layout.addWidget(label_0)
        
        self.rotation_slider = QSlider(Qt.Horizontal)
        self.rotation_slider.setMinimum(0)
        self.rotation_slider.setMaximum(360)
        self.rotation_slider.setValue(int(self.model.rotation_y))
        self.rotation_slider.setTickPosition(QSlider.TicksBelow)
        self.rotation_slider.setTickInterval(45)
        self.rotation_slider.valueChanged.connect(self.on_slider_changed)
        self.rotation_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px;
                background: #e0e0e0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #4a9eff;
                border: 2px solid #3a7edf;
                width: 20px;
                margin: -6px 0;
                border-radius: 10px;
            }
            QSlider::handle:horizontal:hover {
                background: #5aaaff;
            }
        """)
        slider_layout.addWidget(self.rotation_slider)
        
        label_360 = QLabel("360°")
        label_360.setStyleSheet("font-size: 11px; color: #888888;")
        slider_layout.addWidget(label_360)
        
        layout.addLayout(slider_layout)
        
        # 快速角度按钮
        quick_layout = QGridLayout()
        quick_layout.setSpacing(10)
        
        angles = [
            ("正面 0°", 0),
            ("右侧 90°", 90),
            ("背面 180°", 180),
            ("左侧 270°", 270)
        ]
        
        for i, (text, angle) in enumerate(angles):
            btn = QPushButton(text)
            btn.setStyleSheet("""
                QPushButton {
                    background: #f0f0f0;
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    padding: 8px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background: #e0e0e0;
                    border: 1px solid #4a9eff;
                }
                QPushButton:pressed {
                    background: #d0d0d0;
                }
            """)
            btn.clicked.connect(lambda checked, a=angle: self.set_angle(a))
            quick_layout.addWidget(btn, i // 2, i % 2)
        
        layout.addLayout(quick_layout)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedWidth(100)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #f0f0f0;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 8px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #e0e0e0;
            }
        """)
        cancel_btn.clicked.connect(self.on_cancel)
        button_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("确定")
        ok_btn.setFixedWidth(100)
        ok_btn.setStyleSheet("""
            QPushButton {
                background: #4a9eff;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #3a8eef;
            }
            QPushButton:pressed {
                background: #2a7edf;
            }
        """)
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
        
        # 设置对话框样式
        self.setStyleSheet("""
            QDialog {
                background: white;
            }
        """)
    
    def on_slider_changed(self, value):
        """滑块值改变 - 实时更新人偶旋转"""
        self.angle_label.setText(f"当前角度: {value}°")
        
        # 实时更新模型旋转
        self.model.rotation_y = float(value)
        
        # 实时更新视口显示
        if self.viewport:
            self.viewport.update()
        
        # 更新工具面板显示
        if self.viewport and self.viewport.tools_panel:
            self.viewport.tools_panel.update_model_display()
        
        print(f'[旋转对话框] 实时更新旋转角度: {value}°', flush=True)
    
    def set_angle(self, angle):
        """设置快速角度"""
        self.rotation_slider.setValue(angle)
    
    def on_cancel(self):
        """取消 - 恢复原始角度"""
        self.model.rotation_y = self.original_rotation
        
        # 更新视口显示
        if self.viewport:
            self.viewport.update()
        
        # 更新工具面板显示
        if self.viewport and self.viewport.tools_panel:
            self.viewport.tools_panel.update_model_display()
        
        print(f'[旋转对话框] 取消旋转，恢复到: {self.original_rotation:.1f}°', flush=True)
        self.reject()
    
    def get_rotation(self):
        """获取旋转角度"""
        return float(self.rotation_slider.value())


class ImportToolbar(QWidget):
    """黄色区域 - 工具栏"""
    
    toggle_grid_signal = Signal()
    take_photo_signal = Signal()
    clear_scene_signal = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.grid_visible = True
        self.init_ui()
    
    def init_ui(self):
        """初始化UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)
        
        # 标题
        title = QLabel("3D工具")
        title.setStyleSheet("color: #333333; font-size: 14px; font-weight: bold;")
        layout.addWidget(title)
        
        # 关闭线条按钮
        self.btn_toggle_grid = QPushButton("🔲 关闭线条")
        self.btn_toggle_grid.setStyleSheet("""
            QPushButton {
                background: #ffffff;
                color: #333333;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #f5f5f7;
                border: 1px solid #d0d0d0;
            }
            QPushButton:pressed {
                background: #e5e5e5;
            }
        """)
        self.btn_toggle_grid.clicked.connect(self.toggle_grid)
        layout.addWidget(self.btn_toggle_grid)
        
        # 拍照按钮
        self.btn_take_photo = QPushButton("📷 拍照")
        self.btn_take_photo.setStyleSheet("""
            QPushButton {
                background: #34c759;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #30b753;
            }
            QPushButton:pressed {
                background: #2da84e;
            }
        """)
        self.btn_take_photo.clicked.connect(self.take_photo)
        layout.addWidget(self.btn_take_photo)
        
        # 清空按钮
        self.btn_clear_scene = QPushButton("🗑️ 清空")
        self.btn_clear_scene.setStyleSheet("""
            QPushButton {
                background: #ffffff;
                color: #ff3b30;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #fff0f0;
                border: 1px solid #ffcccc;
            }
            QPushButton:pressed {
                background: #ffe0e0;
            }
        """)
        self.btn_clear_scene.clicked.connect(self.clear_scene)
        layout.addWidget(self.btn_clear_scene)
        
        layout.addStretch()
        
        # 设置背景色
        self.setStyleSheet("""
            QWidget {
                background: #ffffff;
                border-bottom: 1px solid #e0e0e0;
            }
        """)
        self.setFixedHeight(50)
    
    def toggle_grid(self):
        """切换网格显示"""
        self.grid_visible = not self.grid_visible
        self.btn_toggle_grid.setText("🔲 关闭线条" if self.grid_visible else "🔳 显示线条")
        self.toggle_grid_signal.emit()
    
    def take_photo(self):
        """拍照"""
        self.take_photo_signal.emit()
    
    def clear_scene(self):
        """清空场景"""
        self.clear_scene_signal.emit()



class ToolsPanel(QWidget):
    """蓝色区域 - 工具面板"""
    
    mannequin_added = Signal()
    color_changed = Signal(QColor)
    model_selected = Signal(object)  # 选中人偶信号
    model_updated = Signal(object)  # 人偶属性更新信号
    model_deleted = Signal(object)  # 删除人偶信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_color = QColor(255, 100, 100)  # 默认红色
        self.viewport = None  # 3D视口引用
        self.selected_model = None  # 当前选中的人偶
        self.init_ui()
    
    def init_ui(self):
        """初始化UI"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: #ffffff; }")
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignTop)
        
        # 标题
        title = QLabel("工具箱")
        title.setStyleSheet("color: #333333; font-size: 14px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # 分隔线
        separator = QWidget()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background: #e0e0e0;")
        layout.addWidget(separator)
        
        # 添加人偶按钮
        btn_add_mannequin = QPushButton("🚶 添加人偶")
        btn_add_mannequin.setStyleSheet("""
            QPushButton {
                background: #ffffff;
                color: #34c759;
                border: 1px solid #34c759;
                border-radius: 6px;
                padding: 15px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #34c759;
                color: #ffffff;
            }
            QPushButton:pressed {
                background: #2da84e;
            }
        """)
        btn_add_mannequin.setMinimumHeight(60)
        btn_add_mannequin.clicked.connect(self.add_mannequin)
        layout.addWidget(btn_add_mannequin)
        
        # 人偶说明
        desc = QLabel("点击添加基础人偶模型\n到3D视口中")
        desc.setStyleSheet("color: #888888; font-size: 11px;")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # 分隔线
        separator2 = QWidget()
        separator2.setFixedHeight(1)
        separator2.setStyleSheet("background: #e0e0e0;")
        layout.addWidget(separator2)
        
        # ============ 人偶属性编辑区域（初始隐藏）============
        self.model_editor = QWidget()
        editor_layout = QVBoxLayout(self.model_editor)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)
        
        # 标题
        editor_title = QLabel("人偶属性")
        editor_title.setStyleSheet("color: #333333; font-size: 12px; font-weight: bold;")
        editor_title.setAlignment(Qt.AlignCenter)
        editor_layout.addWidget(editor_title)
        
        # 名称
        name_label = QLabel("名称（双击修改）")
        name_label.setStyleSheet("color: #888888; font-size: 10px;")
        editor_layout.addWidget(name_label)
        
        self.name_display = QLabel("人偶 #1")
        self.name_display.setStyleSheet("""
            QLabel {
                background: #f5f5f5;
                color: #333333;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
            }
        """)
        self.name_display.setAlignment(Qt.AlignCenter)
        self.name_display.mouseDoubleClickEvent = self.edit_name
        editor_layout.addWidget(self.name_display)
        
        # 旋转角度
        rotation_label = QLabel("旋转角度（双击修改）")
        rotation_label.setStyleSheet("color: #888888; font-size: 10px;")
        editor_layout.addWidget(rotation_label)
        
        self.rotation_display = QLabel("0°")
        self.rotation_display.setStyleSheet("""
            QLabel {
                background: #f5f5f5;
                color: #333333;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
            }
        """)
        self.rotation_display.setAlignment(Qt.AlignCenter)
        self.rotation_display.mouseDoubleClickEvent = self.edit_rotation
        editor_layout.addWidget(self.rotation_display)
        
        # 人偶大小
        size_label = QLabel("人偶大小（双击修改）")
        size_label.setStyleSheet("color: #888888; font-size: 10px;")
        editor_layout.addWidget(size_label)
        
        self.size_display = QLabel("1.0")
        self.size_display.setStyleSheet("""
            QLabel {
                background: #f5f5f5;
                color: #333333;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
            }
        """)
        self.size_display.setAlignment(Qt.AlignCenter)
        self.size_display.mouseDoubleClickEvent = self.edit_size
        editor_layout.addWidget(self.size_display)
        
        # 颜色选择器
        color_label = QLabel("人偶颜色（双击修改）")
        color_label.setStyleSheet("color: #888888; font-size: 10px;")
        editor_layout.addWidget(color_label)
        
        # 当前颜色预览
        self.model_color_preview = QPushButton()
        self.model_color_preview.setFixedHeight(40)
        self.model_color_preview.mouseDoubleClickEvent = self.edit_model_color
        editor_layout.addWidget(self.model_color_preview)
        
        # 快速选择颜色
        preset_label = QLabel("快速选择")
        preset_label.setStyleSheet("color: #888888; font-size: 10px;")
        preset_label.setAlignment(Qt.AlignCenter)
        editor_layout.addWidget(preset_label)
        
        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(5)
        
        preset_colors = [
            QColor(255, 100, 100),  # 红色（默认）
            QColor(255, 255, 255),  # 白色
            QColor(100, 150, 255),  # 蓝色
            QColor(100, 255, 100),  # 绿色
            QColor(255, 200, 100),  # 黄色
        ]
        
        for color in preset_colors:
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color.name()};
                    border: 1px solid #d1d1d6;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border: 1px solid #333333;
                }}
            """)
            btn.clicked.connect(lambda checked, c=color: self.set_model_color(c))
            preset_layout.addWidget(btn)
        
        editor_layout.addLayout(preset_layout)
        
        # ============ 视角切换工具 ============
        view_separator = QWidget()
        view_separator.setFixedHeight(1)
        view_separator.setStyleSheet("background: #e0e0e0;")
        editor_layout.addWidget(view_separator)
        
        view_title = QLabel("📷 视角切换")
        view_title.setStyleSheet("color: #333333; font-size: 12px; font-weight: bold;")
        view_title.setAlignment(Qt.AlignCenter)
        editor_layout.addWidget(view_title)
        
        view_desc = QLabel("以人偶为中心切换视角")
        view_desc.setStyleSheet("color: #888888; font-size: 10px;")
        view_desc.setAlignment(Qt.AlignCenter)
        editor_layout.addWidget(view_desc)
        
        # 视角按钮网格
        view_grid = QGridLayout()
        view_grid.setSpacing(5)
        
        # 定义视角按钮
        view_buttons = [
            ("👤 正面特写", 0, 0, 2, "front_close"),
            ("🙂 正面全身", 1, 0, 1, "front_full"),
            ("📐 侧面", 1, 1, 1, "side"),
            ("🔄 背面", 2, 0, 1, "back"),
            ("🦅 俯视", 2, 1, 1, "top"),
        ]
        
        for text, row, col, colspan, view_type in view_buttons:
            btn = QPushButton(text)
            btn.setStyleSheet("""
                QPushButton {
                    background: #ffffff;
                    color: #333333;
                    border: 1px solid #d1d1d6;
                    border-radius: 4px;
                    padding: 8px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background: #f2f2f7;
                    border: 1px solid #34c759;
                    color: #34c759;
                }
                QPushButton:pressed {
                    background: rgba(52, 199, 89, 0.2);
                }
            """)
            btn.clicked.connect(lambda checked, vt=view_type: self.switch_view(vt))
            view_grid.addWidget(btn, row, col, 1, colspan)
        
        editor_layout.addLayout(view_grid)
        
        # 分隔线
        view_separator2 = QWidget()
        view_separator2.setFixedHeight(1)
        view_separator2.setStyleSheet("background: #e0e0e0;")
        editor_layout.addWidget(view_separator2)
        
        # 删除人偶按钮
        btn_delete = QPushButton("🗑️ 删除人偶")
        btn_delete.setStyleSheet("""
            QPushButton {
                background: #ffffff;
                color: #ff3b30;
                border: 1px solid #ff3b30;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #fff0f0;
            }
            QPushButton:pressed {
                background: #ffe0e0;
            }
        """)
        btn_delete.clicked.connect(self.delete_selected_model)
        editor_layout.addWidget(btn_delete)
        
        self.model_editor.setVisible(False)  # 初始隐藏
        layout.addWidget(self.model_editor)
        
        # ============ 默认颜色选择区域 ============
        self.default_color_panel = QWidget()
        default_layout = QVBoxLayout(self.default_color_panel)
        default_layout.setContentsMargins(0, 0, 0, 0)
        default_layout.setSpacing(8)
        
        # 颜色选择器标题
        color_label2 = QLabel("默认人偶颜色")
        color_label2.setStyleSheet("color: #333333; font-size: 12px; font-weight: bold;")
        color_label2.setAlignment(Qt.AlignCenter)
        default_layout.addWidget(color_label2)
        
        # 颜色预览按钮
        self.btn_color_preview = QPushButton()
        self.btn_color_preview.setFixedHeight(40)
        self.update_color_preview()
        self.btn_color_preview.clicked.connect(self.choose_color)
        default_layout.addWidget(self.btn_color_preview)
        
        # 预设颜色
        preset_label2 = QLabel("快速选择")
        preset_label2.setStyleSheet("color: #888888; font-size: 10px;")
        preset_label2.setAlignment(Qt.AlignCenter)
        default_layout.addWidget(preset_label2)
        
        # 预设颜色按钮布局
        preset_layout2 = QHBoxLayout()
        preset_layout2.setSpacing(5)
        
        for color in preset_colors:
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color.name()};
                    border: 1px solid #d1d1d6;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border: 1px solid #333333;
                }}
            """)
            btn.clicked.connect(lambda checked, c=color: self.set_color(c))
            preset_layout2.addWidget(btn)
        
        default_layout.addLayout(preset_layout2)
        
        layout.addWidget(self.default_color_panel)
        
        # 使用说明
        usage = QLabel("• 左键点击人偶显示属性\n• 双击属性可编辑")
        usage.setStyleSheet("color: #888888; font-size: 10px;")
        usage.setAlignment(Qt.AlignCenter)
        usage.setWordWrap(True)
        layout.addWidget(usage)
        
        layout.addStretch()
        
        scroll.setWidget(container)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)
        
        self.setFixedWidth(200)
        self.setStyleSheet("""
            QWidget {
                background: #f0f2f5;
                border-right: 1px solid #e0e0e0;
            }
        """)
    
    def add_mannequin(self):
        """添加人偶到视口"""
        print('[工具面板] 添加人偶', flush=True)
        self.mannequin_added.emit()
    
    def choose_color(self):
        """打开颜色选择对话框"""
        color = QColorDialog.getColor(self.current_color, self, "选择人偶颜色")
        if color.isValid():
            self.set_color(color)
    
    def set_color(self, color):
        """设置默认颜色"""
        self.current_color = color
        self.update_color_preview()
        self.color_changed.emit(color)
        print(f'[工具面板] 设置默认颜色: {color.name()}', flush=True)
    
    def update_color_preview(self):
        """更新默认颜色预览"""
        self.btn_color_preview.setStyleSheet(f"""
            QPushButton {{
                background: {self.current_color.name()};
                border: 1px solid #d1d1d6;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                border: 1px solid #34c759;
            }}
        """)
        self.btn_color_preview.setText(f"当前颜色: {self.current_color.name()}")
    
    def show_model_properties(self, model):
        """显示人偶属性编辑区"""
        self.selected_model = model
        
        # 隐藏默认颜色面板，显示属性编辑器
        self.default_color_panel.setVisible(False)
        self.model_editor.setVisible(True)
        
        # 更新显示
        self.update_model_display()
        
        print(f'[工具面板] 显示人偶属性: {model.name}', flush=True)
    
    def hide_model_properties(self):
        """隐藏人偶属性编辑区"""
        self.selected_model = None
        
        # 显示默认颜色面板，隐藏属性编辑器
        self.default_color_panel.setVisible(True)
        self.model_editor.setVisible(False)
        
        print(f'[工具面板] 隐藏人偶属性', flush=True)
    
    def update_model_display(self):
        """更新人偶属性显示"""
        if self.selected_model is None:
            return
        
        # 更新名称
        self.name_display.setText(self.selected_model.name)
        
        # 更新旋转角度
        rotation = int(self.selected_model.rotation_y) % 360
        self.rotation_display.setText(f"{rotation}°")
        
        # 更新人偶大小
        size = self.selected_model.scale
        self.size_display.setText(f"{size:.2f}")
        
        # 更新颜色预览
        color = self.selected_model.color
        self.model_color_preview.setStyleSheet(f"""
            QPushButton {{
                background: {color.name()};
                border: 1px solid #d1d1d6;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                border: 1px solid #34c759;
            }}
        """)
        self.model_color_preview.setText(f"颜色: {color.name()}")
    
    def edit_name(self, event):
        """双击编辑名称"""
        if self.selected_model is None:
            return
        
        new_name, ok = QInputDialog.getText(
            self, 
            "修改名称", 
            "请输入新的名称:", 
            text=self.selected_model.name
        )
        
        if ok and new_name:
            self.selected_model.name = new_name
            self.update_model_display()
            self.model_updated.emit(self.selected_model)
            if self.viewport:
                self.viewport.update()
            print(f'[工具面板] 修改名称: {new_name}', flush=True)
    
    def edit_rotation(self, event):
        """双击编辑旋转角度"""
        if self.selected_model is None:
            return
        
        current_rotation = int(self.selected_model.rotation_y) % 360
        
        new_rotation, ok = QInputDialog.getInt(
            self, 
            "修改旋转角度", 
            "请输入旋转角度 (0-360):", 
            value=current_rotation,
            min=0,
            max=360
        )
        
        if ok:
            self.selected_model.rotation_y = float(new_rotation)
            self.update_model_display()
            self.model_updated.emit(self.selected_model)
            if self.viewport:
                self.viewport.update()
            print(f'[工具面板] 修改旋转角度: {new_rotation}°', flush=True)
    
    def edit_size(self, event):
        """双击编辑人偶大小"""
        if self.selected_model is None:
            return
        
        current_size = self.selected_model.scale
        
        new_size, ok = QInputDialog.getDouble(
            self, 
            "修改人偶大小", 
            "请输入人偶大小 (0.1-10.0):", 
            value=current_size,
            min=0.1,
            max=10.0,
            decimals=2
        )
        
        if ok:
            self.selected_model.scale = new_size
            self.update_model_display()
            self.model_updated.emit(self.selected_model)
            if self.viewport:
                self.viewport.update()
            print(f'[工具面板] 修改人偶大小: {new_size:.2f}', flush=True)
    
    def edit_model_color(self, event):
        """双击编辑人偶颜色"""
        if self.selected_model is None:
            return
        
        color = QColorDialog.getColor(self.selected_model.color, self, "选择人偶颜色")
        if color.isValid():
            self.set_model_color(color)
    
    def set_model_color(self, color):
        """设置当前人偶颜色"""
        if self.selected_model is None:
            return
        
        self.selected_model.color = color
        self.update_model_display()
        self.model_updated.emit(self.selected_model)
        if self.viewport:
            self.viewport.update()
        print(f'[工具面板] 设置人偶颜色: {color.name()}', flush=True)
    
    def delete_selected_model(self):
        """删除选中的人偶"""
        if self.selected_model is None:
            return
        
        # 确认删除
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, 
            "确认删除", 
            f"确定要删除人偶 '{self.selected_model.name}' 吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.model_deleted.emit(self.selected_model)
            self.hide_model_properties()
            print(f'[工具面板] 删除人偶: {self.selected_model.name}', flush=True)
    
    def switch_view(self, view_type):
        """切换视角 - 围绕人偶旋转相机"""
        if self.selected_model is None or self.viewport is None:
            return
        
        model = self.selected_model
        
        # 设置相机焦点到人偶位置（相机将围绕这个点旋转）
        self.viewport.camera_focus_x = model.x
        self.viewport.camera_focus_y = model.z  # 注意：model.z是垂直高度
        self.viewport.camera_focus_z = model.y  # 注意：model.y是深度
        
        # 根据视角类型调整相机角度和距离
        if view_type == "front_close":
            # 正面特写：距离近，稍微俯视，聚焦头部
            self.viewport.camera_angle_x = 10  # 稍微俯视
            self.viewport.camera_angle_y = 0   # 正面
            self.viewport.camera_distance = 200 * model.scale  # 距离较近
            print(f'[视角切换] 正面特写 (焦点={model.x:.0f},{model.z:.0f},{model.y:.0f}, 角度X={self.viewport.camera_angle_x}°, 角度Y={self.viewport.camera_angle_y}°, 距离={self.viewport.camera_distance:.0f})', flush=True)
            
        elif view_type == "front_full":
            # 正面全身：距离适中，看到全身
            self.viewport.camera_angle_x = 0   # 水平视角
            self.viewport.camera_angle_y = 0   # 正面
            self.viewport.camera_distance = 400 * model.scale
            print(f'[视角切换] 正面全身 (焦点={model.x:.0f},{model.z:.0f},{model.y:.0f}, 角度X={self.viewport.camera_angle_x}°, 角度Y={self.viewport.camera_angle_y}°, 距离={self.viewport.camera_distance:.0f})', flush=True)
            
        elif view_type == "side":
            # 侧面：从人偶左侧观看
            self.viewport.camera_angle_x = 0   # 水平视角
            self.viewport.camera_angle_y = -90 # 左侧
            self.viewport.camera_distance = 400 * model.scale
            print(f'[视角切换] 侧面视角 (焦点={model.x:.0f},{model.z:.0f},{model.y:.0f}, 角度X={self.viewport.camera_angle_x}°, 角度Y={self.viewport.camera_angle_y}°, 距离={self.viewport.camera_distance:.0f})', flush=True)
            
        elif view_type == "back":
            # 背面：从人偶后方观看
            self.viewport.camera_angle_x = 0   # 水平视角
            self.viewport.camera_angle_y = 180 # 背面
            self.viewport.camera_distance = 400 * model.scale
            print(f'[视角切换] 背面视角 (焦点={model.x:.0f},{model.z:.0f},{model.y:.0f}, 角度X={self.viewport.camera_angle_x}°, 角度Y={self.viewport.camera_angle_y}°, 距离={self.viewport.camera_distance:.0f})', flush=True)
            
        elif view_type == "top":
            # 俯视：从正上方观看
            self.viewport.camera_angle_x = 70  # 大角度俯视
            self.viewport.camera_angle_y = 0   # 正面方向
            self.viewport.camera_distance = 500 * model.scale
            print(f'[视角切换] 俯视视角 (焦点={model.x:.0f},{model.z:.0f},{model.y:.0f}, 角度X={self.viewport.camera_angle_x}°, 角度Y={self.viewport.camera_angle_y}°, 距离={self.viewport.camera_distance:.0f})', flush=True)
        
        # 更新视口显示
        self.viewport.update()





class ThreeDWindow(QMainWindow):
    """3D控制主窗口"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("3D Workspace - Ghost OS")
        self.resize(1200, 800)
        self.setWindowFlags(Qt.Window)
        self.photo_page = None  # 用于存储PhotoPage引用
        
        self.init_ui()
        self.apply_stylesheet()
        self.connect_signals()
    
    def init_ui(self):
        """初始化UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 黄色区域
        self.import_toolbar = ImportToolbar()
        main_layout.addWidget(self.import_toolbar)
        
        # 内容区域
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # 蓝色区域
        self.tools_panel = ToolsPanel()
        content_layout.addWidget(self.tools_panel)
        
        # 红色区域
        self.viewport = Viewport3D()
        content_layout.addWidget(self.viewport, 1)
        
        # 建立双向引用
        self.viewport.tools_panel = self.tools_panel
        self.tools_panel.viewport = self.viewport
        self.viewport.window_3d = self  # 添加viewport到window的引用
        
        main_layout.addLayout(content_layout, 1)
    
    def connect_signals(self):
        """连接信号"""
        self.import_toolbar.toggle_grid_signal.connect(self.viewport.toggle_grid)
        self.import_toolbar.take_photo_signal.connect(self.take_viewport_photo)
        self.tools_panel.mannequin_added.connect(self.on_mannequin_added)
        self.tools_panel.color_changed.connect(self.viewport.set_mannequin_color)
        
        # 连接工具面板信号
        self.tools_panel.model_deleted.connect(self.on_model_deleted)
        self.viewport.model_selected.connect(self.tools_panel.show_model_properties)
    
    def on_mannequin_added(self):
        """处理添加人偶"""
        mannequin_count = sum(1 for m in self.viewport.models if m.type == "mannequin")
        mannequin_name = f"人偶 #{mannequin_count + 1}"
        self.viewport.add_model(mannequin_name, "mannequin")
        # 自动保存场景状态
        self.save_scene_state()
    
    def on_model_deleted(self, model):
        """处理删除人偶"""
        if model in self.viewport.models:
            self.viewport.models.remove(model)
            self.viewport.update()
            print(f'[3D窗口] 已删除人偶: {model.name}', flush=True)
            # 自动保存场景状态
            self.save_scene_state()
    
    def take_viewport_photo(self):
        """拍摄3D视口照片并上传到图层与画板"""
        from datetime import datetime
        from PySide6.QtCore import QCoreApplication
        
        # 如果拍照框未显示，则显示拍照框
        if not self.viewport.photo_frame_visible:
            self.viewport.photo_frame_visible = True
            self.viewport.update()
            print('[3D窗口] 显示拍照框，请调整拍照区域', flush=True)
            QMessageBox.information(self, "拍照模式", "拍照框已显示！\n\n请拖动角或边调整拍照区域\n调整完成后再次点击拍照按钮进行拍照")
            return
        
        # 如果拍照框已显示，则进行拍照
        rect = self.viewport.photo_frame_rect
        
        # 临时隐藏拍照框（不要拍进红色框）
        self.viewport.photo_frame_visible = False
        self.viewport.update()
        
        # 强制刷新UI，确保拍照框被隐藏
        QCoreApplication.processEvents()
        
        # 截取拍照框区域（此时红色框已隐藏）
        pixmap = self.viewport.grab(rect)
        
        # 生成文件名和图层名称
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"photo_3d_{timestamp}.png"
        layer_name = f"3D照片_{timestamp}"
        
        # 确保JPG/3D目录存在
        try:
            import sys
            if getattr(sys, 'frozen', False):
                app_root = os.path.dirname(sys.executable)
            else:
                app_root = os.path.dirname(os.path.abspath(__file__))
            
            jpg_3d_dir = os.path.join(app_root, 'JPG', '3D')
            os.makedirs(jpg_3d_dir, exist_ok=True)
            
            # 完整保存路径
            save_path = os.path.join(jpg_3d_dir, filename)
            print(f'[3D窗口] 保存路径: {save_path}', flush=True)
        except Exception as e:
            print(f'[3D窗口] 创建保存目录失败: {e}，将保存到当前目录', flush=True)
            save_path = filename
        
        # 保存文件
        save_success = pixmap.save(save_path)
        
        # 上传到图层与画板
        upload_success = False
        if self.photo_page is not None:
            try:
                # 获取PhotoPage的图层面板和画布
                layers_panel = getattr(self.photo_page, 'layers_panel', None)
                canvas = getattr(layers_panel, 'canvas', None) if layers_panel else None
                
                if layers_panel is not None and canvas is not None:
                    # 获取画布尺寸
                    canvas_w = canvas.paint_layer.width()
                    canvas_h = canvas.paint_layer.height()
                    
                    # 缩放图片以填满整个画布（拉伸方式，不保持宽高比）
                    scaled_pixmap = pixmap.scaled(canvas_w, canvas_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    
                    print(f'[3D窗口] 原始照片尺寸: {pixmap.width()}x{pixmap.height()}', flush=True)
                    print(f'[3D窗口] 画布尺寸: {canvas_w}x{canvas_h}', flush=True)
                    print(f'[3D窗口] 填充后尺寸: {scaled_pixmap.width()}x{scaled_pixmap.height()}', flush=True)
                    
                    # 使用 add_image_layer_at 直接添加，完全填充画布
                    # 不使用 add_layer_pixmap，因为它会通过 add_image_layer 再次缩放
                    from PySide6.QtCore import Qt as QtCore
                    
                    # 直接添加到画布的图层，位置 (0,0)，完全覆盖
                    lid = canvas.add_image_layer_at(scaled_pixmap, layer_name, 0, 0, show_thumb=True)
                    
                    if lid is not None:
                        # 同步到图层面板
                        layers_panel.add_layer_pixmap(scaled_pixmap, layer_name, sync_to_canvas=False)
                        
                        # 更新最后添加的图层的 canvas layer ID
                        if layers_panel.list.count() > 0:
                            item = layers_panel.list.item(layers_panel.list.count() - 1)
                            item.setData(QtCore.UserRole, lid)
                        
                        upload_success = True
                        print(f'[3D窗口] ✓ 照片已完全填充画布: {layer_name}', flush=True)
                    
                    # 关闭3D窗口的网格线条
                    if self.viewport.show_grid:
                        self.viewport.toggle_grid()
                        self.import_toolbar.grid_visible = False
                        self.import_toolbar.btn_toggle_grid.setText("🔳 显示线条")
                        print('[3D窗口] ✓ 已自动关闭3D网格线条', flush=True)
                    
                else:
                    print(f'[3D窗口] ⚠️  未找到图层面板或画布', flush=True)
            except Exception as e:
                print(f'[3D窗口] ❌ 上传到图层失败: {e}', flush=True)
                import traceback
                traceback.print_exc()
        else:
            print(f'[3D窗口] ⚠️  PhotoPage引用未设置', flush=True)
        
        # 拍照框保持隐藏状态（不再显示）
        # 用户下次点击拍照按钮会重新显示
        
        # 显示结果消息
        if save_success:
            msg = f"📷 照片已保存到:\nJPG/3D/{filename}\n\n原始尺寸: {pixmap.width()}x{pixmap.height()}"
            if upload_success:
                msg += f"\n\n✓ 已完全填充整个画布"
                msg += f"\n✓ 已自动关闭网格线条"
            else:
                msg += f"\n\n⚠️  未上传到图层（PhotoPage未连接）"
            
            print(f'[3D窗口] ✓ 照片已保存: JPG/3D/{filename}（不含红色框）', flush=True)
            QMessageBox.information(self, "拍照成功", msg)
        else:
            print(f'[3D窗口] ❌ 照片保存失败', flush=True)
            QMessageBox.warning(self, "拍照失败", "无法保存照片文件")
    
    def apply_stylesheet(self):
        """应用样式"""
        self.setStyleSheet("""
            QMainWindow {
                background: #f5f5f7;
            }
        """)
    
    def get_scene_state_path(self):
        """获取场景状态JSON文件路径"""
        try:
            if getattr(sys, 'frozen', False):
                app_root = os.path.dirname(sys.executable)
            else:
                app_root = os.path.dirname(os.path.abspath(__file__))
            
            json_dir = os.path.join(app_root, 'json')
            os.makedirs(json_dir, exist_ok=True)
            return os.path.join(json_dir, '3d_scene_state.json')
        except Exception as e:
            print(f'[3D窗口] 获取场景状态路径失败: {e}', flush=True)
            return None
    
    def save_scene_state(self):
        """保存3D场景状态到JSON"""
        try:
            state_path = self.get_scene_state_path()
            if not state_path:
                return
            
            # 收集所有模型数据
            models_data = []
            for model in self.viewport.models:
                model_dict = {
                    'name': model.name,
                    'type': model.type,
                    'x': model.x,
                    'y': model.y,
                    'z': model.z,
                    'rotation_y': model.rotation_y,
                    'scale': model.scale,
                    'color': {
                        'r': model.color.red(),
                        'g': model.color.green(),
                        'b': model.color.blue()
                    },
                    'file_path': model.file_path
                }
                models_data.append(model_dict)
            
            # 收集相机状态
            camera_data = {
                'distance': self.viewport.camera_distance,
                'angle_x': self.viewport.camera_angle_x,
                'angle_y': self.viewport.camera_angle_y,
                'focus_x': self.viewport.camera_focus_x,
                'focus_y': self.viewport.camera_focus_y,
                'focus_z': self.viewport.camera_focus_z
            }
            
            # 完整场景状态
            scene_state = {
                'models': models_data,
                'camera': camera_data,
                'grid_visible': self.viewport.show_grid
            }
            
            # 保存到JSON
            with open(state_path, 'w', encoding='utf-8') as f:
                json.dump(scene_state, f, ensure_ascii=False, indent=2)
            
            print(f'[3D窗口] ✓ 场景状态已保存: {len(models_data)} 个模型', flush=True)
        except Exception as e:
            print(f'[3D窗口] ❌ 保存场景状态失败: {e}', flush=True)
            import traceback
            traceback.print_exc()
    
    def load_scene_state(self):
        """从JSON加载3D场景状态"""
        try:
            state_path = self.get_scene_state_path()
            if not state_path or not os.path.exists(state_path):
                print('[3D窗口] 没有找到历史场景状态', flush=True)
                return
            
            with open(state_path, 'r', encoding='utf-8') as f:
                scene_state = json.load(f)
            
            # 清空现有模型（但不保存状态，避免循环）
            self.viewport.models.clear()
            
            # 恢复模型
            models_data = scene_state.get('models', [])
            for model_dict in models_data:
                model = Model3D(
                    name=model_dict['name'],
                    model_type=model_dict['type'],
                    file_path=model_dict.get('file_path')
                )
                model.x = model_dict['x']
                model.y = model_dict['y']
                model.z = model_dict['z']
                model.rotation_y = model_dict['rotation_y']
                model.scale = model_dict['scale']
                
                # 恢复颜色
                color_dict = model_dict.get('color', {'r': 255, 'g': 100, 'b': 100})
                model.color = QColor(
                    color_dict.get('r', 255),
                    color_dict.get('g', 100),
                    color_dict.get('b', 100)
                )
                
                self.viewport.models.append(model)
            
            # 恢复相机状态
            camera_data = scene_state.get('camera', {})
            self.viewport.camera_distance = camera_data.get('distance', 500)
            self.viewport.camera_angle_x = camera_data.get('angle_x', 20)
            self.viewport.camera_angle_y = camera_data.get('angle_y', 0)
            self.viewport.camera_focus_x = camera_data.get('focus_x', 0)
            self.viewport.camera_focus_y = camera_data.get('focus_y', 0)
            self.viewport.camera_focus_z = camera_data.get('focus_z', 0)
            
            # 恢复网格显示状态
            grid_visible = scene_state.get('grid_visible', True)
            if self.viewport.show_grid != grid_visible:
                self.viewport.toggle_grid()
                self.import_toolbar.grid_visible = grid_visible
                self.import_toolbar.btn_toggle_grid.setText("🔲 关闭线条" if grid_visible else "🔳 显示线条")
            
            # 刷新显示
            self.viewport.update()
            
            print(f'[3D窗口] ✓ 场景状态已加载: {len(models_data)} 个模型', flush=True)
        except Exception as e:
            print(f'[3D窗口] ❌ 加载场景状态失败: {e}', flush=True)
            import traceback
            traceback.print_exc()
    
    def clear_scene(self):
        """清空场景并删除历史记录"""
        reply = QMessageBox.question(
            self,
            "清空场景",
            "确定要清空所有模型和历史记录吗？\n此操作不可恢复！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 清空所有模型
            self.viewport.models.clear()
            
            # 删除历史记录文件
            try:
                state_path = self.get_scene_state_path()
                if state_path and os.path.exists(state_path):
                    os.remove(state_path)
                    print('[3D窗口] ✓ 历史记录已删除', flush=True)
            except Exception as e:
                print(f'[3D窗口] ⚠️  删除历史记录失败: {e}', flush=True)
            
            # 重置相机
            self.viewport.camera_distance = 500
            self.viewport.camera_angle_x = 20
            self.viewport.camera_angle_y = 0
            self.viewport.camera_focus_x = 0
            self.viewport.camera_focus_y = 0
            self.viewport.camera_focus_z = 0
            
            # 隐藏工具面板的属性编辑器
            if hasattr(self.tools_panel, 'hide_model_properties'):
                self.tools_panel.hide_model_properties()
            
            # 刷新显示
            self.viewport.update()
            
            print('[3D窗口] ✓ 场景已清空', flush=True)
            QMessageBox.information(self, "清空完成", "场景和历史记录已全部清空！")
    
    def showEvent(self, event):
        """窗口显示时自动加载历史记录"""
        super().showEvent(event)
        # 延迟加载，确保UI完全初始化
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, self.load_scene_state)
