
import sys
import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, 
    QHeaderView, QHBoxLayout, QGraphicsProxyWidget, QApplication, QMessageBox, QMenu,
    QPushButton, QAbstractItemView
)
from PySide6.QtCore import Qt, QRectF, QPoint, QTimer, QSize
from PySide6.QtGui import QColor, QBrush, QPen, QPainter, QMouseEvent
from lingdongconnect import ConnectableNode, DataType
from lingdongvideo import VideoPlayerWindow
from chouka_quanju import GlobalViewWindow

class GachaNodeFactory:
    """抽卡节点工厂类"""
    
    @staticmethod
    def create_node(CanvasNode):
        """动态创建GachaNode类，继承自CanvasNode"""
        
        class VideoCirclesWidget(QWidget):
            """显示视频圆圈的自定义控件"""
            def __init__(self, video_paths, on_selection_change=None, on_delete_request=None, parent=None):
                super().__init__(parent)
                self.video_paths = video_paths
                self.pending_count = 0  # 新增：等待中的视频数量
                self.selected_index = -1  # -1表示未选中
                self.circle_radius = 18
                self.spacing = 14
                self.setMouseTracking(True)
                # self.setFixedHeight(60)  # 移除固定高度，允许随行高调整，保持垂直居中
                self.player_window = None # 保持引用
                self.on_selection_change = on_selection_change
                self.on_delete_request = on_delete_request

            def set_video_paths(self, video_paths):
                """更新视频列表并通知布局更新"""
                # 去重: 保持顺序
                seen = set()
                unique_paths = []
                for p in video_paths:
                    if p not in seen:
                        seen.add(p)
                        unique_paths.append(p)
                self.video_paths = unique_paths
                self.updateGeometry()
                self.update()

            def sizeHint(self):
                """返回建议的大小"""
                # 包含等待中的视频
                total_count = len(self.video_paths) + self.pending_count
                width = total_count * (self.circle_radius * 2 + self.spacing) + 20
                return QSize(width, 60)

            def contextMenuEvent(self, event):
                """右键菜单"""
                # Determine which circle was clicked
                x = event.pos().x()
                diameter = self.circle_radius * 2
                unit_width = diameter + self.spacing
                
                clicked_index = -1
                total_count = len(self.video_paths) + self.pending_count
                
                for i in range(total_count):
                    center_x = i * unit_width + self.circle_radius + 5
                    if abs(x - center_x) <= self.circle_radius:
                        clicked_index = i
                        break
                
                # 只能删除已存在的视频
                if clicked_index != -1 and clicked_index < len(self.video_paths):
                    menu = QMenu(self)
                    delete_action = menu.addAction("删除此视频")
                    action = menu.exec(event.globalPos())
                    
                    if action == delete_action:
                        path = self.video_paths[clicked_index]
                        if self.on_delete_request:
                            self.on_delete_request(clicked_index, path)

            def paintEvent(self, event):
                painter = QPainter(self)
                painter.setRenderHint(QPainter.Antialiasing)
                
                total_count = len(self.video_paths) + self.pending_count
                
                for i in range(total_count):
                    x = i * (self.circle_radius * 2 + self.spacing) + self.circle_radius + 5
                    y = self.height() / 2
                    
                    if i < len(self.video_paths):
                        # 现有视频：选中为绿色，否则为灰色
                        if i == self.selected_index:
                            color = QColor("#4CAF50")  # Green
                        else:
                            color = QColor("#BDBDBD")  # Gray
                    else:
                        # 等待中的视频：红色
                        color = QColor("#F44336") # Red
                        
                    painter.setBrush(QBrush(color))
                    painter.setPen(Qt.NoPen)
                    painter.drawEllipse(QPoint(int(x), int(y)), self.circle_radius, self.circle_radius)

            def mousePressEvent(self, event: QMouseEvent):
                if event.button() != Qt.LeftButton:
                    return
                
                x = event.pos().x()
                # 计算点击了哪个圆圈
                diameter = self.circle_radius * 2
                unit_width = diameter + self.spacing
                
                # 简单的碰撞检测
                # 只允许点击已存在的视频
                for i in range(len(self.video_paths)):
                    center_x = i * unit_width + self.circle_radius + 5
                    if abs(x - center_x) <= self.circle_radius:
                        # 更新选中状态
                        if self.selected_index != i:
                            self.selected_index = i
                            self.update()  # 重绘
                        
                        # 无论是切换还是再次点击，都通知上层处理（播放或全局观看）
                        if self.on_selection_change:
                            self.on_selection_change(i)
                        
                        return
                        
            def play_video(self, path):
                if os.path.exists(path):
                    try:
                        # 如果已有窗口且可见，先关闭或复用
                        if self.player_window and self.player_window.isVisible():
                            self.player_window.close()
                            
                        # 使用内置播放器
                        self.player_window = VideoPlayerWindow(path)
                        self.player_window.show()
                    except Exception as e:
                        print(f"播放视频失败: {e}")
                else:
                    print(f"视频文件不存在: {path}")

        class GachaNode(ConnectableNode, CanvasNode):
            """抽卡节点 - 显示分镜对应的多版本视频"""
            
            def __init__(self, x, y):
                print("Initializing GachaNode...")
                self.disable_auto_sockets = True
                CanvasNode.__init__(self, x, y, 950, 400, "抽卡节点", None)
                ConnectableNode.__init__(self)
                
                self.node_title = "抽卡节点"
                
                # 设置样式
                if hasattr(self, 'set_header_color'):
                    self.set_header_color("#FF9800") # Orange header
                
                # 添加输入接口，连接导演节点
                self.add_input_socket(DataType.ANY, "输入(导演)")
                
                # 内部UI
                self.setup_ui()
                
                # 导演节点数据缓存
                self.director_shots = []
                self.is_connected = False # 连接状态
                
                # 选中的视频记录 {shot_num: index}
                self.selections = {}
                self.load_selections()
                
                # 记录正在生成的镜头 {shot_num}
                self.pending_shots = set()
                
                self.load_data()
                print("GachaNode initialized.")
                
                # 定时刷新数据（可选）
                self.timer = QTimer()
                self.timer.timeout.connect(self.check_connection_and_refresh)
                self.timer.start(1000) # 每1秒检查连接和刷新

            def load_selections(self):
                """加载选中状态"""
                try:
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    json_path = os.path.join(base_dir, 'json', 'chouka.json')
                    if os.path.exists(json_path):
                        with open(json_path, 'r', encoding='utf-8') as f:
                            self.selections = json.load(f)
                except Exception as e:
                    print(f"Failed to load chouka.json: {e}")

            def save_selections(self):
                """保存选中状态"""
                try:
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    json_dir = os.path.join(base_dir, 'json')
                    os.makedirs(json_dir, exist_ok=True)
                    json_path = os.path.join(json_dir, 'chouka.json')
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(self.selections, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"Failed to save chouka.json: {e}")

            def toggle_global_view(self, checked):
                """切换全局观看模式"""
                self.global_view_enabled = checked
                if not checked and hasattr(self, 'current_global_window') and self.current_global_window:
                    self.current_global_window.close()
                    self.current_global_window = None

            def open_global_view(self, shot_num, current_index):
                """打开全局观看窗口"""
                # 如果窗口已存在且是同一个镜头，则更新
                if hasattr(self, 'current_global_window') and self.current_global_window:
                    if self.current_global_window.shot_num == shot_num:
                        self.current_global_window.update_selection(current_index)
                        self.current_global_window.raise_()
                        self.current_global_window.activateWindow()
                        return
                    else:
                        self.current_global_window.close()
                
                # 获取视频数据
                if shot_num in self.data:
                    video_paths = self.data[shot_num]
                    if not isinstance(video_paths, list):
                        video_paths = [video_paths]
                    
                    # 过滤不存在的视频文件，保持与UI一致
                    video_paths = [p for p in video_paths if os.path.exists(p)]
                    
                    # 再次去重，确保与UI一致
                    seen = set()
                    unique_paths = []
                    for p in video_paths:
                        if p not in seen:
                            seen.add(p)
                            unique_paths.append(p)
                    video_paths = unique_paths
                    
                    # 创建窗口
                    self.current_global_window = GlobalViewWindow(shot_num, video_paths, current_index)
                    self.current_global_window.selection_changed.connect(lambda idx: self.on_global_selection_changed(shot_num, idx))
                    self.current_global_window.show()

            def on_global_selection_changed(self, shot_num, index):
                """全局窗口选择变更回调"""
                # 更新本地数据
                self.selections[str(shot_num)] = index
                self.save_selections()
                self.notify_director_selection_change(shot_num)
                
                # 更新抽卡节点UI
                for row in range(self.table.rowCount()):
                    item = self.table.item(row, 0)
                    if item and item.text() == str(shot_num):
                        circles_widget = self.table.cellWidget(row, 1)
                        if circles_widget:
                            # 更新圆圈选中状态
                            circles_widget.selected_index = index
                            circles_widget.update()
                            
                            # 确保路径存在
                            if 0 <= index < len(circles_widget.video_paths):
                                path = circles_widget.video_paths[index]
                                # 如果之前没有在播放，或者用户希望同步播放，可以调用
                                # circles_widget.play_video(path) 
                                # 但用户只说"抽卡节点的视频版本会显示绿色"，没说要同步播放
                                # 通常圆圈点击会播放，但这里是从外部同步回来，也许不需要弹窗播放
                                pass
                        break

            def on_circle_selected(self, shot_num, index):
                """圆圈被选中时的回调"""
                # 检查全局观看模式
                if getattr(self, 'global_view_enabled', False):
                    self.open_global_view(shot_num, index)
                else:
                    # 单屏模式：手动触发播放
                    # 找到对应的 VideoCirclesWidget 并播放
                    display_shot = str(shot_num)
                    if display_shot == "shot_1":
                        display_shot = "1"
                        
                    for row in range(self.table.rowCount()):
                        item = self.table.item(row, 0)
                        if item and item.text() == display_shot:
                            widget = self.table.cellWidget(row, 1)
                            if widget and 0 <= index < len(widget.video_paths):
                                widget.play_video(widget.video_paths[index])
                            break
                
                self.selections[str(shot_num)] = index
                self.save_selections()
                self.notify_director_selection_change(shot_num)
                
                # 如果全局窗口已打开，同步更新
                if hasattr(self, 'current_global_window') and self.current_global_window:
                    if self.current_global_window.shot_num == shot_num:
                        self.current_global_window.update_selection(index)

            def notify_director_selection_change(self, shot_num):
                """通知导演节点更新选择"""
                if not hasattr(self, 'input_sockets'): return
                
                for socket in self.input_sockets:
                    if socket.label == "输入(导演)":
                        for connection in socket.connections:
                            # connection.source_socket is the other end (Output)
                            other_socket = connection.source_socket
                            if other_socket and other_socket.parent_node:
                                director_node = other_socket.parent_node
                                if hasattr(director_node, 'refresh_cinema_cell'):
                                    director_node.refresh_cinema_cell(shot_num)

            def on_circle_deleted(self, shot_num, index, path):
                """处理视频删除"""
                print(f"[抽卡节点] 请求删除视频: 镜头{shot_num}, index {index}, path {path}")
                
                # 1. 删除物理文件
                if os.path.exists(path):
                    try:
                        os.remove(path)
                        print(f"[抽卡节点] 已删除文件: {path}")
                    except Exception as e:
                        print(f"[抽卡节点] 删除文件失败: {e}")
                
                # 2. 尝试通知导演节点删除
                director_notified = self.notify_director_video_deleted(shot_num, path)
                
                # 3. 如果没有连接导演节点，我们需要自己更新 JSON
                if not director_notified:
                    self.delete_from_json_local(shot_num, path)
                    # 立即刷新本地显示
                    self.load_data()
            
            def notify_director_video_deleted(self, shot_num, path):
                """通知导演节点删除视频"""
                if not hasattr(self, 'input_sockets'): return False
                
                found = False
                for socket in self.input_sockets:
                    if socket.label == "输入(导演)":
                        for connection in socket.connections:
                            other_socket = connection.source_socket
                            if other_socket and other_socket.parent_node:
                                director_node = other_socket.parent_node
                                if hasattr(director_node, 'handle_video_deleted'):
                                    director_node.handle_video_deleted(shot_num, path)
                                    found = True
                return found

            def delete_from_json_local(self, shot_num, path):
                """本地删除JSON中的视频记录"""
                try:
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    json_path = os.path.join(base_dir, 'JSON', 'daoyan_TV_VIDEO_SAVE.JSON')
                    if not os.path.exists(json_path):
                        return
                        
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 查找并删除
                    target_shot = str(shot_num).lower().replace('shot_', '').replace('镜头', '').strip()
                    
                    # 遍历查找匹配的键
                    found_key = None
                    if str(shot_num) in data:
                        found_key = str(shot_num)
                    else:
                        for k in data.keys():
                            if str(k).lower().replace('shot_', '').replace('镜头', '').strip() == target_shot:
                                found_key = k
                                break
                    
                    if found_key:
                        paths = data[found_key]
                        if isinstance(paths, list):
                            if path in paths:
                                paths.remove(path)
                                # 如果列表为空，是否删除键？保留键比较安全
                        elif isinstance(paths, str):
                             if paths == path:
                                 del data[found_key]
                        
                        # 保存
                        with open(json_path, 'w', encoding='utf-8') as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        print(f"[抽卡节点] 已从JSON移除视频: {path}")
                        
                except Exception as e:
                    print(f"[抽卡节点] 本地更新JSON失败: {e}")

            def setup_ui(self):
                # 创建代理部件
                widget = QWidget()
                layout = QVBoxLayout(widget)
                layout.setContentsMargins(0, 0, 0, 0)
                
                # 顶部控制栏
                top_bar = QWidget()
                top_layout = QHBoxLayout(top_bar)
                top_layout.setContentsMargins(5, 5, 5, 5)
                
                self.global_view_btn = QPushButton("全局观看")
                self.global_view_btn.setCheckable(True)
                self.global_view_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #555; 
                        color: white;
                        border-radius: 4px;
                        padding: 5px 10px;
                    }
                    QPushButton:checked {
                        background-color: #4CAF50;
                    }
                """)
                self.global_view_btn.clicked.connect(self.toggle_global_view)
                
                top_layout.addStretch()
                top_layout.addWidget(self.global_view_btn)
                
                layout.addWidget(top_bar)
                
                # 表格
                self.table = QTableWidget()
                self.table.setColumnCount(2)
                self.table.setHorizontalHeaderLabels(["镜头号", "视频版本"])
                
                # 镜头号列固定宽度
                self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
                self.table.setColumnWidth(0, 80)
                
                # 视频版本列根据内容调整
                self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
                self.table.horizontalHeader().setStretchLastSection(True)
                
                # 优化滚动体验，防止 embedded widget 错位
                self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
                self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
                
                self.table.verticalHeader().setVisible(False)
                
                # 样式
                self.table.setStyleSheet("""
                    QTableWidget {
                        border: none;
                        background-color: #ffffff;
                        gridline-color: #f0f0f0;
                    }
                    QHeaderView::section {
                        background-color: #f5f5f5;
                        padding: 5px;
                        border: none;
                        border-bottom: 1px solid #d0d0d0;
                    }
                """)
                
                layout.addWidget(self.table)
                
                # 添加到节点
                self.proxy_widget = QGraphicsProxyWidget(self)
                self.proxy_widget.setWidget(widget)
                self.proxy_widget.setPos(0, 50) # 标题栏下方，稍微留出空隙
                self.proxy_widget.resize(self.rect().width(), self.rect().height() - 50)

            def setRect(self, *args):
                """更新几何形状时调整子部件大小"""
                super().setRect(*args)
                if hasattr(self, 'proxy_widget'):
                    self.proxy_widget.resize(self.rect().width(), self.rect().height() - 50)
            
            def receive_data(self, data, data_type):
                """接收上游节点的数据"""
                # 收到数据意味着肯定有连接
                self.is_connected = True
                
                if data_type == DataType.VIDEO:
                    if isinstance(data, str):
                        # 处理状态信号
                        if data.startswith("PENDING:"):
                            shot_num = data.split(":", 1)[1].strip()
                            # 规范化：去除 "shot_" 前缀，兼容 "shot_2" 和 "2"
                            display_shot_num = shot_num
                            if display_shot_num.startswith("shot_"):
                                display_shot_num = display_shot_num[5:] # remove "shot_"
                            
                            # 记录到 pending_shots，防止刷新后消失
                            self.pending_shots.add(display_shot_num)
                            
                            found = False
                            # 找到对应的 VideoCirclesWidget 并增加 pending_count
                            for row in range(self.table.rowCount()):
                                item = self.table.item(row, 0)
                                # 比较时也尝试规范化表格中的文本
                                if item:
                                    row_text = item.text()
                                    # Normalize row text
                                    norm_row_text = row_text
                                    if norm_row_text.startswith("shot_"):
                                        norm_row_text = norm_row_text[5:]
                                    
                                    if norm_row_text == display_shot_num or row_text == shot_num:
                                        widget = self.table.cellWidget(row, 1)
                                        if widget:
                                            widget.pending_count += 1
                                            widget.updateGeometry()
                                            widget.update()
                                            found = True
                                        break
                            
                            # 如果没找到（新镜头），需要临时添加一行
                            if not found:
                                print(f"[抽卡节点] 新镜头 {display_shot_num} 开始生成，添加临时行")
                                row = self.table.rowCount()
                                self.table.insertRow(row)
                                
                                item_shot = QTableWidgetItem(display_shot_num)
                                item_shot.setTextAlignment(Qt.AlignCenter)
                                self.table.setItem(row, 0, item_shot)
                                
                                # 创建空的 widget 但带有 pending_count
                                circles_widget = VideoCirclesWidget(
                                    [], 
                                    on_selection_change=lambda idx, s=display_shot_num: self.on_circle_selected(s, idx),
                                    on_delete_request=lambda idx, p, s=display_shot_num: self.on_circle_deleted(s, idx, p)
                                )
                                circles_widget.pending_count = 1
                                self.table.setCellWidget(row, 1, circles_widget)
                                self.table.resizeColumnToContents(1)
                            
                            return

                        elif data.startswith("FINISHED:"):
                            shot_num = data.split(":", 1)[1]
                            # 规范化
                            display_shot_num = shot_num
                            if display_shot_num.startswith("shot_"):
                                display_shot_num = display_shot_num[5:]

                            # 从 pending_shots 移除
                            if display_shot_num in self.pending_shots:
                                self.pending_shots.remove(display_shot_num)
                            
                            # 找到对应的 VideoCirclesWidget 并减少 pending_count
                            for row in range(self.table.rowCount()):
                                item = self.table.item(row, 0)
                                if item:
                                    row_text = item.text().strip()
                                    # Normalize row text
                                    norm_row_text = row_text
                                    if norm_row_text.startswith("shot_"):
                                        norm_row_text = norm_row_text[5:]
                                    
                                    if norm_row_text == display_shot_num or row_text == shot_num:
                                        widget = self.table.cellWidget(row, 1)
                                        if widget and widget.pending_count > 0:
                                            widget.pending_count -= 1
                                        break
                            
                            # 刷新数据以显示新生成的视频
                            self.load_data()
                            return

                    # print(f"[抽卡节点] 收到视频数据推送，立即刷新...")
                    # 无论收到的是单个路径还是列表，都触发重新加载
                    # 因为导演节点在推送前已经保存了 JSON
                    self.load_data()
            
            def check_connection_and_refresh(self):
                """检查连接状态并刷新数据"""
                # 检查输入接口是否有连接
                has_connection = False
                director_shots = []
                connected_director_id = None
                
                if self.input_sockets and self.input_sockets[0].connections:
                    conn = self.input_sockets[0].connections[0]
                    if conn and conn.source_socket:
                        source_node = conn.source_socket.parent_node
                        # 检查是否是导演节点 (通过类名或标题)
                        if "DirectorNode" in source_node.__class__.__name__ or "导演" in source_node.node_title:
                            has_connection = True
                            
                            # 获取导演节点ID，用于隔离数据读取
                            if hasattr(source_node, 'node_id'):
                                connected_director_id = source_node.node_id
                                
                            # 获取导演节点的镜头数据
                            # 导演节点通常是一个 QTableWidget 在内部
                            if hasattr(source_node, 'table'):
                                rows = source_node.table.rowCount()
                                for r in range(rows):
                                    item = source_node.table.item(r, 0) # 镜头号列
                                    if item:
                                        director_shots.append(item.text())
                                    else:
                                        # 如果是自动生成的，可能是数字
                                        director_shots.append(str(r + 1))
                
                # 更新连接状态
                self.is_connected = has_connection
                self.connected_director_id = connected_director_id

                # 如果连接状态改变或数据改变，重新加载
                if has_connection:
                    # 更新导演节点数据
                    if self.director_shots != director_shots:
                        self.director_shots = director_shots
                    
                    # 始终刷新数据以检测视频变化
                    self.load_data()
                else:
                    # 如果断开连接，清空数据
                    if self.director_shots:
                        self.director_shots = []
                    
                    # 刷新以显示空状态
                    self.load_data()

            def load_data(self):
                """加载JSON数据"""
                # 如果未连接，保持初始状态（清空）
                if not hasattr(self, 'is_connected') or not self.is_connected:
                    self.table.setRowCount(0)
                    if hasattr(self, 'pending_shots'):
                        self.pending_shots.clear()
                    return

                try:
                    # 使用当前文件所在目录来定位JSON文件
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    
                    # 根据连接的导演节点ID选择正确的文件
                    json_filename = 'daoyan_TV_VIDEO_SAVE.JSON'
                    if hasattr(self, 'connected_director_id') and self.connected_director_id is not None:
                        json_filename = f'daoyan_TV_VIDEO_SAVE_{self.connected_director_id}.JSON'
                        
                    json_path = os.path.join(base_dir, 'JSON', json_filename)
                    
                    if not os.path.exists(json_path):
                        # print(f"JSON file not found: {json_path}")
                        # 如果文件不存在，也应该显示导演节点的空壳（如果有）
                        if self.director_shots:
                            pass # Continue to render empty slots
                        else:
                            return
                        raw_data = {} # Empty data
                    else:
                        with open(json_path, 'r', encoding='utf-8') as f:
                            raw_data = json.load(f)
                    
                    # 1. 数据清洗与合并
                    clean_data = {}
                    data_dirty = False
                    
                    for key, val in raw_data.items():
                        # 规范化键名
                        norm_key = str(key)
                        if norm_key.startswith("shot_"):
                            norm_key = norm_key[5:]
                            data_dirty = True
                        
                        # 确保值是列表
                        videos = val
                        if not isinstance(videos, list):
                            videos = [videos]
                            
                        if norm_key in clean_data:
                            # 合并并去重
                            existing_videos = clean_data[norm_key]
                            # 使用set去重，但保持顺序
                            seen = set(existing_videos)
                            for v in videos:
                                if v not in seen:
                                    existing_videos.append(v)
                                    seen.add(v)
                            # 如果发生了合并，说明原始数据中有分散的记录（如既有shot_1又有1）
                            data_dirty = True
                        else:
                            clean_data[norm_key] = videos

                    # 2. 如果数据脏了（进行了合并或重命名），回写JSON
                    if data_dirty:
                        try:
                            with open(json_path, 'w', encoding='utf-8') as f:
                                json.dump(clean_data, f, ensure_ascii=False, indent=2)
                            print("[抽卡节点] 已自动修复并合并JSON中的重复镜头号 (shot_X -> X)")
                        except Exception as e:
                            print(f"[抽卡节点] 自动修复JSON失败: {e}")

                    self.data = clean_data # 保存数据引用
                    data = clean_data
                    
                    # 排序键
                    def sort_key(k):
                        s = str(k).lower().replace('shot_', '').replace('镜头', '').strip()
                        if s.isdigit():
                            return int(s)
                        return float('inf')

                    # 总是显示所有 JSON 中的数据
                    # 之前的逻辑是只显示导演节点有的，但这导致新生成的镜头（导演节点尚未刷新）无法显示
                    # 且本项目 JSON 通常只包含当前项目的视频
                    
                    # 自动清理 pending_shots：如果视频已存在于 data 中
                    pending_to_remove = []
                    for shot in self.pending_shots:
                        # data 键已经规范化
                        if shot in data:
                             paths = data[shot]
                             if not isinstance(paths, list):
                                 paths = [paths]
                             # 只有当确实存在有效视频文件时才移除 pending
                             if any(os.path.exists(p) for p in paths):
                                 pending_to_remove.append(shot)
                    
                    for shot in pending_to_remove:
                        self.pending_shots.remove(shot)

                    # 合并 JSON 数据和 pending_shots
                    all_keys = set(data.keys())
                    all_keys.update(self.pending_shots)
                    
                    # 合并导演节点的数据
                    if self.director_shots:
                        for shot in self.director_shots:
                            s = str(shot)
                            # 规范化 shot_1 -> 1，与其他逻辑保持一致
                            if s.startswith("shot_"):
                                s = s[5:]
                            all_keys.add(s)
                    
                    sorted_keys = sorted(all_keys, key=sort_key)
                    
                    # 只有当行数或内容改变时才刷新表格，避免重置选中状态
                    # 简单比较：行数是否一致，且每行的镜头号是否一致
                    needs_update = False
                    if self.table.rowCount() != len(sorted_keys):
                        needs_update = True
                    else:
                        for row, key in enumerate(sorted_keys):
                            item = self.table.item(row, 0)
                            
                            expected_text = str(key)
                            if expected_text.startswith("shot_"):
                                expected_text = expected_text[5:]
                                
                            if not item or item.text() != expected_text:
                                needs_update = True
                                break
                    
                    if not needs_update:
                        # 即使不需要重建表格，也可能需要更新圆圈（如果有新视频生成或Pending状态变化）
                        data_changed = False
                        for row, shot_num in enumerate(sorted_keys):
                            # 获取视频列表（如果 shot_num 仅在 pending 中，则为空列表）
                            video_paths = data.get(shot_num, [])
                            if not isinstance(video_paths, list):
                                video_paths = [video_paths]
                            
                            # 过滤不存在的视频文件
                            video_paths = [p for p in video_paths if os.path.exists(p)]
                            
                            current_widget = self.table.cellWidget(row, 1)
                            if current_widget:
                                # 如果视频列表变了，更新它
                                if current_widget.video_paths != video_paths:
                                    current_widget.set_video_paths(video_paths)
                                    data_changed = True
                                
                                # 更新 pending 状态
                                # Normalize shot_num for pending check
                                norm_shot = str(shot_num)
                                if norm_shot.startswith("shot_"):
                                    norm_shot = norm_shot[5:]
                                
                                expected_pending = 1 if norm_shot in self.pending_shots else 0
                                if current_widget.pending_count != expected_pending:
                                    current_widget.pending_count = expected_pending
                                    current_widget.updateGeometry()
                                    current_widget.update()
                                    data_changed = True
                        
                        if data_changed:
                            self.table.resizeColumnToContents(1)
                            self.table.resizeRowsToContents()
                        return

                    self.table.setRowCount(len(sorted_keys))
                    
                    for row, shot_num in enumerate(sorted_keys):
                        # 镜头号
                        display_text = str(shot_num)
                        if display_text == "shot_1":
                            display_text = "1"
                            
                        item_shot = QTableWidgetItem(display_text)
                        item_shot.setTextAlignment(Qt.AlignCenter)
                        self.table.setItem(row, 0, item_shot)
                        
                        # 视频圆圈
                        video_paths = data.get(shot_num, [])
                        if not isinstance(video_paths, list):
                            video_paths = [video_paths]
                        
                        # 过滤不存在的视频文件
                        video_paths = [p for p in video_paths if os.path.exists(p)]
                        
                        # 去重
                        seen = set()
                        unique_paths = []
                        for p in video_paths:
                            if p not in seen:
                                seen.add(p)
                                unique_paths.append(p)
                        video_paths = unique_paths
                        
                        circles_widget = VideoCirclesWidget(
                            video_paths, 
                            on_selection_change=lambda idx, s=shot_num: self.on_circle_selected(s, idx),
                            on_delete_request=lambda idx, p, s=shot_num: self.on_circle_deleted(s, idx, p)
                        )
                        
                        # 设置 pending 状态
                        if str(shot_num) in self.pending_shots:
                            circles_widget.pending_count = 1
                            
                        # 尝试恢复选中状态 (支持规范化匹配)
                        norm_shot = str(shot_num)
                        if norm_shot.startswith("shot_"):
                            norm_shot = norm_shot[5:]
                        
                        # 1. 精确匹配
                        if str(shot_num) in self.selections:
                            circles_widget.selected_index = self.selections[str(shot_num)]
                        else:
                            # 2. 规范化匹配
                            for k, v in self.selections.items():
                                norm_k = str(k)
                                if norm_k.startswith("shot_"):
                                    norm_k = norm_k[5:]
                                
                                if norm_k == norm_shot:
                                    circles_widget.selected_index = v
                                    break
                            
                        self.table.setCellWidget(row, 1, circles_widget)
                    
                    # 调整列宽以适应内容
                    self.table.resizeColumnToContents(1)
                    self.table.resizeRowsToContents()
                        
                except Exception as e:
                    print(f"抽卡节点加载数据失败: {e}")

            def paint(self, painter, option, widget=None):
                """绘制节点背景"""
                super().paint(painter, option, widget)
                # 可以在这里添加额外的绘制逻辑

        return GachaNode
