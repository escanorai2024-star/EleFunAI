
import os
import json
import time
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QFrame, QScrollArea, QInputDialog, QMessageBox, QMenu
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QPoint
from PySide6.QtGui import QIcon, QCursor, QAction

class CaseManagerWidget(QWidget):
    """
    案例管理挂件 - 位于画布右上角
    鼠标悬停显示保存的案例列表，支持快照保存和恢复
    """
    restore_requested = Signal(dict) # 请求恢复案例，传递案例数据
    save_requested = Signal()        # 请求保存当前状态
    director_node_requested = Signal() # 请求创建导演节点

    def __init__(self, parent=None, canvas_view=None):
        super().__init__(parent)
        self.canvas_view = canvas_view
        self.json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "json", "hComfyUI.json")
        self.is_expanded = False
        self.case_count = 0
        self.setup_ui()
        self.load_cases()

    def setup_ui(self):
        self.setAttribute(Qt.WA_StyledBackground, True)
        
        # 定义样式
        self.collapsed_style = """
            #Container {
                background-color: #ffffff;
                color: #34A853;
                border: 1px solid rgba(52, 168, 83, 0.3);
                border-radius: 8px;
            }
        """
        self.expanded_style = """
            #Container {
                background-color: rgba(255, 255, 255, 240);
                border: 1px solid #ddd;
                border-radius: 8px;
            }
        """

        # 主布局
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        # 改为底部对齐，适应放置在屏幕底部的情况
        self.layout.setAlignment(Qt.AlignBottom | Qt.AlignRight)

        # 容器 - 用于包含图标和展开的列表
        self.container = QFrame()
        self.container.setObjectName("Container")
        self.container.setStyleSheet(self.collapsed_style)
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(5, 5, 5, 5)
        self.container_layout.setSpacing(5)

        # 顶部图标区域 (始终显示)
        self.header_area = QWidget()
        self.header_layout = QHBoxLayout(self.header_area)
        self.header_layout.setContentsMargins(5, 5, 5, 5)
        self.header_layout.setSpacing(10)

        self.icon_label = QLabel("📁")
        self.icon_label.setStyleSheet("font-size: 16px;")
        self.title_label = QLabel("案例库")
        self.title_label.setStyleSheet("font-weight: bold; color: #333;")
        self.title_label.hide() # 默认隐藏标题

        self.header_layout.addWidget(self.icon_label)
        self.header_layout.addWidget(self.title_label)
        self.header_layout.addStretch()

        self.container_layout.addWidget(self.header_area)

        # 保存按钮
        self.save_btn = QPushButton("📸 快照保存")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #34A853;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2d8f45;
            }
        """)
        self.save_btn.clicked.connect(self.request_save_snapshot)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #eee;")

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none; background: transparent;")
        
        self.cases_widget = QWidget()
        self.cases_layout = QVBoxLayout(self.cases_widget)
        self.cases_layout.setContentsMargins(0, 0, 0, 0)
        self.cases_layout.setSpacing(2)
        self.cases_layout.setAlignment(Qt.AlignTop)
        
        self.scroll_area.setWidget(self.cases_widget)

        parent = self.parent() if self.parent() is not None else self
        self.popup = QFrame(parent)
        self.popup.setObjectName("CasePopup")
        self.popup.setStyleSheet(self.expanded_style)
        self.popup_layout = QVBoxLayout(self.popup)
        self.popup_layout.setContentsMargins(5, 5, 5, 5)
        self.popup_layout.setSpacing(5)

        # 关闭按钮区域
        self.close_btn_area = QWidget()
        self.close_btn_layout = QHBoxLayout(self.close_btn_area)
        self.close_btn_layout.setContentsMargins(5, 0, 0, 0)
        self.close_btn_layout.setSpacing(0)
        
        # 添加标题到弹窗顶部
        self.popup_title = QLabel("案例库")
        self.popup_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #333;")
        self.close_btn_layout.addWidget(self.popup_title)
        
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #999;
                border: none;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #ff4444;
                background-color: #f0f0f0;
                border-radius: 12px;
            }
        """)
        self.close_btn.clicked.connect(self.collapse_ui)
        
        self.close_btn_layout.addStretch()
        self.close_btn_layout.addWidget(self.close_btn)
        
        self.popup_layout.addWidget(self.close_btn_area)
        self.popup_layout.addWidget(self.save_btn)
        self.popup_layout.addWidget(line)
        self.popup_layout.addWidget(self.scroll_area)
        self.popup.hide()

        self.layout.addWidget(self.container)
        self.setFixedSize(34, 32)

    def load_cases(self):
        """加载案例列表"""
        # 清空现有列表
        while self.cases_layout.count():
            item = self.cases_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not os.path.exists(self.json_path):
            return

        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                cases = data.get("cases", [])
                self.case_count = len(cases)
                
                # 按时间倒序排列
                cases.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

                if not cases:
                    empty_label = QLabel("暂无案例")
                    empty_label.setAlignment(Qt.AlignCenter)
                    empty_label.setStyleSheet("color: #999; padding: 10px;")
                    self.cases_layout.addWidget(empty_label)
                    return

                for case in cases:
                    self.add_case_item(case)

        except Exception as e:
            print(f"加载案例失败: {e}")

    def add_case_item(self, case):
        """添加案例列表项"""
        item_widget = QWidget()
        item_layout = QHBoxLayout(item_widget)
        item_layout.setContentsMargins(5, 5, 5, 5)
        
        name_label = QLabel(case.get("name", "未命名"))
        name_label.setStyleSheet("font-weight: bold;")

        restore_btn = QPushButton("恢复")
        restore_btn.setCursor(Qt.PointingHandCursor)
        restore_btn.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                border: none;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
        """)
        restore_btn.clicked.connect(lambda: self.restore_case(case))

        rename_btn = QPushButton("改名")
        rename_btn.setCursor(Qt.PointingHandCursor)
        rename_btn.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                border: none;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
        """)
        rename_btn.clicked.connect(lambda: self.rename_case(case))

        delete_btn = QPushButton("删除")
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffecec;
                color: #ff4444;
                border: none;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ffcccc;
            }
        """)
        delete_btn.clicked.connect(lambda: self.delete_case(case))

        item_layout.addWidget(name_label)
        item_layout.addStretch()
        item_layout.addWidget(restore_btn)
        item_layout.addWidget(rename_btn)
        item_layout.addWidget(delete_btn)

        # 鼠标悬停高亮
        item_widget.setAttribute(Qt.WA_StyledBackground, True)
        item_widget.setStyleSheet(".QWidget:hover { background-color: #f5f5f5; border-radius: 4px; }")

        self.cases_layout.addWidget(item_widget)

    def mousePressEvent(self, event):
        """点击切换展开/收起状态"""
        # 如果是收起状态，点击任意位置展开
        if not self.is_expanded:
            self.is_expanded = True
            self.expand_ui()
            event.accept()
            return

        # 如果是展开状态，点击头部区域（图标）收起
        # 注意：子控件（如按钮）的点击事件会被子控件消费，不会传到这里
        if self.header_area.geometry().contains(event.pos()):
            self.is_expanded = False
            self.collapse_ui()
            event.accept()
            return
            
        super().mousePressEvent(event)

    # def enterEvent(self, event):
    #     """鼠标移入展开"""
    #     self.is_expanded = True
    #     self.expand_ui()
    #     super().enterEvent(event)

    # def leaveEvent(self, event):
    #     """鼠标移出收起"""
    #     # 稍微延迟收起，防止误操作
    #     QTimer.singleShot(100, self.check_leave)
    #     super().leaveEvent(event)

    # def check_leave(self):
    #     if not self.underMouse():
    #         self.is_expanded = False
    #         self.collapse_ui()

    def expand_ui(self):
        base_height = 200
        per_case = 36
        max_height = 800
        target_height = base_height + self.case_count * per_case
        popup_height = min(max_height, target_height)
        popup_width = 250

        self.container.setStyleSheet(self.expanded_style)
        # self.title_label.show() # 不在按钮中显示标题，避免挤占图标位置

        parent = self.popup.parentWidget() or self
        try:
            # 获取Header左上角全局坐标 (确保在上方显示)
            header_top_left_global = self.header_area.mapToGlobal(self.header_area.rect().topLeft())
            
            # X轴：右对齐 (Header右边缘 - Popup宽度)
            popup_x = header_top_left_global.x() + self.header_area.width() - popup_width
            
            # Y轴：在Header上方 (Header上边缘 - Popup高度 - 间距)
            popup_y = header_top_left_global.y() - popup_height - 5
            
            top_left_in_parent = parent.mapFromGlobal(QPoint(popup_x, popup_y))
            self.popup.setGeometry(top_left_in_parent.x(), top_left_in_parent.y(), popup_width, popup_height)
        except Exception:
            parent_rect = parent.rect()
            x = max(0, parent_rect.width() - popup_width - 10)
            y = max(0, parent_rect.top() + 40)
            self.popup.setGeometry(x, y, popup_width, popup_height)

        self.popup.show()
        try:
            self.popup.raise_()
        except Exception:
            pass

    def collapse_ui(self):
        self.container.setStyleSheet(self.collapsed_style)
        self.title_label.hide()
        self.popup.hide()

    def rename_case(self, case):
        """重命名案例"""
        old_name = case.get("name", "")
        new_name, ok = QInputDialog.getText(self, "重命名案例", "请输入新的案例名称:", text=old_name)
        if ok and new_name and new_name != old_name:
            try:
                # 读取现有数据
                data = {"cases": []}
                if os.path.exists(self.json_path):
                    with open(self.json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                
                # 更新名称
                for item in data.get("cases", []):
                    if item.get("id") == case.get("id"):
                        item["name"] = new_name
                        break
                
                # 写入文件
                with open(self.json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                # 刷新列表
                self.load_cases()
                QMessageBox.information(self, "成功", "案例重命名成功！")
                
            except Exception as e:
                QMessageBox.warning(self, "错误", f"重命名失败: {str(e)}")

    def request_save_snapshot(self):
        """请求保存快照"""
        if self.canvas_view:
            # 弹出输入框获取案例名称
            name, ok = QInputDialog.getText(self, "保存案例", "请输入案例名称:")
            if ok and name:
                self.save_snapshot(name)

    def save_snapshot(self, name):
        """执行保存逻辑"""
        try:
            # 获取画布数据
            canvas_data = self.canvas_view.get_canvas_state()
            
            new_case = {
                "id": str(int(time.time())),
                "name": name,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "data": canvas_data
            }

            # 读取现有数据
            data = {"cases": []}
            
            # 确保存储目录存在
            os.makedirs(os.path.dirname(self.json_path), exist_ok=True)
            
            if os.path.exists(self.json_path):
                try:
                    with open(self.json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except:
                    pass
            
            if "cases" not in data:
                data["cases"] = []
                
            data["cases"].append(new_case)

            # 写入文件
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 刷新列表
            self.load_cases()
            QMessageBox.information(self, "成功", "案例保存成功！")

        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存失败: {str(e)}")

    def restore_case(self, case):
        """恢复案例"""
        try:
            canvas_data = case.get("data")
            if canvas_data and self.canvas_view:
                # 确认对话框
                reply = QMessageBox.question(self, "确认恢复", 
                                           f"确定要恢复案例 '{case.get('name')}' 吗？\n当前画布未保存的内容将丢失。",
                                           QMessageBox.Yes | QMessageBox.No)
                
                if reply == QMessageBox.Yes:
                    self.canvas_view.load_canvas_state_from_data(canvas_data)
                    QMessageBox.information(self, "成功", "案例恢复成功！")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"恢复失败: {str(e)}")

    def delete_case(self, case_to_delete):
        """删除案例"""
        reply = QMessageBox.question(self, "确认删除", 
                                   f"确定要删除案例 '{case_to_delete.get('name')}' 吗？",
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            try:
                if os.path.exists(self.json_path):
                    with open(self.json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    data["cases"] = [c for c in data.get("cases", []) if c.get("id") != case_to_delete.get("id")]
                    
                    with open(self.json_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    
                    self.load_cases()
            except Exception as e:
                QMessageBox.warning(self, "错误", f"删除失败: {str(e)}")
