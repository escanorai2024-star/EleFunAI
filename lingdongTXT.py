"""
灵动智能体 - 文字节点模块
支持单击编辑的文字节点
"""

from PySide6.QtWidgets import (
    QGraphicsTextItem, QMenu, QInputDialog, QDialog, 
    QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout, QLabel
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor


# SVG图标定义
SVG_TEXT_ICON = '''<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M4 7h16M12 7v13m-5 0h10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
</svg>'''


class TextEditDialog(QDialog):
    """大型文本编辑对话框"""
    
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.edited_text = text
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        self.setWindowTitle("编辑文字节点")
        self.setMinimumSize(700, 500)
        self.setStyleSheet("""
            QDialog {
                background-color: #0a0a0a;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 标题
        title = QLabel("📝 编辑文字内容")
        title.setStyleSheet("""
            color: #00bfff;
            font-size: 18px;
            font-weight: bold;
            padding-bottom: 10px;
        """)
        layout.addWidget(title)
        
        # 文本编辑区域
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(self.edited_text)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a1a;
                color: #e0e0e0;
                border: 2px solid #2a2a2a;
                border-radius: 8px;
                padding: 15px;
                font-size: 14px;
                font-family: "Microsoft YaHei", "微软雅黑", sans-serif;
                line-height: 1.6;
            }
            QTextEdit:focus {
                border: 2px solid #00bfff;
            }
        """)
        self.text_edit.setFont(QFont("Microsoft YaHei", 11))
        layout.addWidget(self.text_edit, 1)
        
        # 字符统计
        self.char_count_label = QLabel()
        self.update_char_count()
        self.char_count_label.setStyleSheet("""
            color: #888888;
            font-size: 11px;
            padding: 5px 0;
        """)
        layout.addWidget(self.char_count_label)
        
        # 连接文本改变信号
        self.text_edit.textChanged.connect(self.update_char_count)
        
        # 按钮栏
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        # 清空按钮
        clear_btn = QPushButton("🗑 清空")
        clear_btn.setFixedHeight(40)
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                color: #888888;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 0 20px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                color: #ff6666;
                border: 1px solid #ff6666;
            }
            QPushButton:pressed {
                background-color: #ff6666;
                color: #000000;
            }
        """)
        clear_btn.clicked.connect(self.text_edit.clear)
        button_layout.addWidget(clear_btn)
        
        button_layout.addStretch()
        
        # 取消按钮
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedHeight(40)
        cancel_btn.setFixedWidth(100)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                color: #888888;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                color: #e0e0e0;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        # 确定按钮
        ok_btn = QPushButton("✓ 确定")
        ok_btn.setFixedHeight(40)
        ok_btn.setFixedWidth(100)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #00ff88;
                color: #000000;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00cc6f;
            }
            QPushButton:pressed {
                background-color: #009955;
            }
        """)
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
        
        # 设置焦点到文本框
        self.text_edit.setFocus()
        
        # 移动光标到末尾
        cursor = self.text_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.text_edit.setTextCursor(cursor)
    
    def update_char_count(self):
        """更新字符统计"""
        text = self.text_edit.toPlainText()
        char_count = len(text)
        line_count = text.count('\n') + 1 if text else 0
        self.char_count_label.setText(f"字符数: {char_count} | 行数: {line_count}")
    
    def accept(self):
        """确定按钮 - 保存文本"""
        self.edited_text = self.text_edit.toPlainText()
        super().accept()
    
    def get_text(self):
        """获取编辑后的文本"""
        return self.text_edit.toPlainText()


class TextNode:
    """文字节点 - 支持单击编辑
    
    注意：这个类需要继承自CanvasNode，在导入时会动态继承
    """
    
    @staticmethod
    def create_text_node(CanvasNode):
        """动态创建TextNode类，继承自CanvasNode"""
        
        class TextNodeImpl(CanvasNode):
            """文字节点实现 - 支持单击编辑、自动调整大小、缩放"""
            
            def __init__(self, x, y):
                super().__init__(x, y, 200, 150, "文字", SVG_TEXT_ICON)
                
                # 最小和最大尺寸
                self.min_width = 150
                self.min_height = 100
                self.max_width = 800
                self.max_height = 1200
                
                # 画布显示字数限制（只影响显示，不限制存储）
                self.display_limit = 500  # 画布最多显示500字
                
                # 完整文本内容（无限制）
                self.full_text = ""
                
                # 缩放控制
                self.is_resizing = False
                self.resize_start_pos = None
                self.resize_start_rect = None
                self.scale_factor = 1.0
                
                # 添加字数显示标签（右上角）
                self.char_count_label = QGraphicsTextItem(self)
                self.char_count_label.setPlainText("0字")
                self.char_count_label.setDefaultTextColor(QColor("#888888"))
                self.char_count_label.setFont(QFont("Microsoft YaHei", 8))
                self.char_count_label.setPos(120, 8)
                
                # 添加"更多内容"提示标签
                self.more_text_label = QGraphicsTextItem(self)
                self.more_text_label.setPlainText("")
                self.more_text_label.setDefaultTextColor(QColor("#00bfff"))
                self.more_text_label.setFont(QFont("Microsoft YaHei", 8))
                self.more_text_label.setVisible(False)
                
                # 添加文本编辑区域（用于画布显示）
                self.content_text = QGraphicsTextItem(self)
                self.content_text.setPlainText("双击输入文字...")
                self.content_text.setDefaultTextColor(QColor("#202124")) # 浅色模式深色文字
                self.content_text.setFont(QFont("Microsoft YaHei", 9))
                self.content_text.setPos(10, 50)
                self.content_text.setTextWidth(180)
                
                # 初始设置为不可编辑（画布上只显示，编辑需要双击打开对话框）
                self.content_text.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
                self.content_text.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                
                # 设置为可编辑
                self.editable_text = self.content_text
                self.is_editing = False
            
            def setRect(self, *args):
                """重写setRect以在大小改变时更新文本显示"""
                super().setRect(*args)
                # 更新显示（裁剪文本）
                self.update_display()

            def update_display(self):
                """更新画布显示内容（只显示前500字，并根据节点大小裁剪）"""
                if not self.full_text or self.full_text == "双击输入文字...":
                    self.char_count_label.setPlainText("0字")
                    self.char_count_label.setDefaultTextColor(QColor("#888888"))
                    self.more_text_label.setVisible(False)
                    return
                
                # 获取总字数
                total_chars = len(self.full_text)
                
                # 更新字数显示
                self.char_count_label.setPlainText(f"{total_chars}字")
                self.char_count_label.setDefaultTextColor(QColor("#888888"))
                
                # 获取当前节点尺寸
                current_width = self.rect().width()
                current_height = self.rect().height()
                
                # 计算可用于显示文本的高度（减去标题栏和底部边距）
                available_height = current_height - 70  # 50(标题) + 20(底部边距)
                
                # 设置文本宽度
                self.content_text.setTextWidth(current_width - 20)
                
                # 判断是否需要截断显示
                if total_chars > self.display_limit:
                    # 只显示前500字
                    display_text = self.full_text[:self.display_limit]
                else:
                    # 显示全部内容
                    display_text = self.full_text
                
                # 设置文本
                self.content_text.setPlainText(display_text)
                
                # 再次确保文本宽度（setPlainText可能重置）
                self.content_text.setTextWidth(current_width - 20)
                
                # 检查文本高度是否超出可用空间
                text_height = self.content_text.boundingRect().height()
                
                if text_height > available_height:
                    # 文本太长，需要按高度裁剪
                    # 使用二分法找到合适的字数
                    truncated_text = self.truncate_text_by_height(display_text, current_width - 20, available_height)
                    self.content_text.setPlainText(truncated_text)
                    self.content_text.setTextWidth(current_width - 20)
                    
                    # 显示"更多内容"提示
                    if total_chars > self.display_limit:
                        remaining_chars = total_chars - self.display_limit
                    else:
                        remaining_chars = total_chars - len(truncated_text)
                    
                    self.more_text_label.setPlainText(f"...（还有{remaining_chars}字，双击查看全部）")
                    self.more_text_label.setVisible(True)
                    
                    print(f"[文字节点] 按高度裁剪，显示{len(truncated_text)}字，总共{total_chars}字")
                elif total_chars > self.display_limit:
                    # 按字数限制显示
                    remaining_chars = total_chars - self.display_limit
                    self.more_text_label.setPlainText(f"...（还有{remaining_chars}字，双击查看全部）")
                    self.more_text_label.setVisible(True)
                    print(f"[文字节点] 显示前{self.display_limit}字，总共{total_chars}字")
                else:
                    # 完整显示
                    self.more_text_label.setVisible(False)
                
                # 更新字数和提示标签位置
                self.update_labels_position()
            
            def truncate_text_by_height(self, text, width, max_height):
                """根据高度裁剪文本，使用二分法"""
                if not text:
                    return ""
                
                # 创建临时文本项用于测量
                from PySide6.QtWidgets import QGraphicsTextItem
                temp_text = QGraphicsTextItem()
                temp_text.setFont(QFont("Microsoft YaHei", 9))
                temp_text.setTextWidth(width)
                
                # 二分查找合适的字数
                left, right = 0, len(text)
                result = ""
                
                while left <= right:
                    mid = (left + right) // 2
                    temp_text.setPlainText(text[:mid])
                    height = temp_text.boundingRect().height()
                    
                    if height <= max_height:
                        result = text[:mid]
                        left = mid + 1
                    else:
                        right = mid - 1
                
                return result
            
            def update_labels_position(self):
                """更新标签位置"""
                rect = self.rect()
                
                # 更新字数标签位置（右上角）
                label_width = self.char_count_label.boundingRect().width()
                self.char_count_label.setPos(rect.width() - label_width - 10, 8)
                
                # 更新"更多内容"提示位置（底部居中）
                if self.more_text_label.isVisible():
                    # 设置文本宽度，确保不超出节点边界
                    self.more_text_label.setTextWidth(rect.width() - 20)
                    
                    more_width = self.more_text_label.boundingRect().width()
                    more_height = self.more_text_label.boundingRect().height()
                    self.more_text_label.setPos(
                        10,  # 左对齐，留10px边距
                        rect.height() - more_height - 10
                    )
            
            def auto_resize(self):
                """根据文本内容自动调整节点大小"""
                text = self.content_text.toPlainText()
                if not text or text == "双击输入文字...":
                    return
                
                # 如果正在缩放，不自动调整大小
                if self.is_resizing:
                    return
                
                # 计算文本所需的尺寸
                doc = self.content_text.document()
                doc_size = doc.size()
                
                # 计算新尺寸（文本高度 + 顶部标题区域 + 内边距 + 底部提示区域）
                extra_height = 100 if self.more_text_label.isVisible() else 80
                new_width = max(self.min_width, min(doc_size.width() + 30, self.max_width))
                new_height = max(self.min_height, min(doc_size.height() + extra_height, self.max_height))
                
                # 更新节点矩形
                old_rect = self.rect()
                if abs(old_rect.width() - new_width) > 10 or abs(old_rect.height() - new_height) > 10:
                    self.setRect(0, 0, new_width, new_height)
                    
                    # 更新文本宽度
                    self.content_text.setTextWidth(new_width - 20)
                    
                    # 更新标签位置
                    self.update_labels_position()
                    
                    print(f"[文字节点] 自动调整大小: {new_width:.0f}×{new_height:.0f}")
            
            def mousePressEvent(self, event):
                """鼠标按下 - 右下角拖动缩放"""
                if event.button() == Qt.MouseButton.LeftButton:
                    local_pos = event.pos()
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
                
                # 其他情况正常处理（拖动节点等）
                super().mousePressEvent(event)
            
            def mouseDoubleClickEvent(self, event):
                """双击事件 - 打开编辑对话框"""
                if event.button() == Qt.MouseButton.LeftButton:
                    self.open_edit_dialog()
                    event.accept()
                    return
                
                super().mouseDoubleClickEvent(event)
            
            def mouseMoveEvent(self, event):
                """鼠标移动 - 缩放节点"""
                if self.is_resizing:
                    delta = event.pos() - self.resize_start_pos
                    
                    # 计算新尺寸
                    new_width = max(self.min_width, min(self.resize_start_rect.width() + delta.x(), self.max_width))
                    new_height = max(self.min_height, min(self.resize_start_rect.height() + delta.y(), self.max_height))
                    
                    # 更新节点矩形
                    self.setRect(0, 0, new_width, new_height)
                    
                    # 实时更新显示（裁剪文本以适应新尺寸）
                    if self.full_text:
                        # 临时禁用自动调整，避免冲突
                        old_resizing = self.is_resizing
                        self.is_resizing = True
                        self.update_display()
                        self.is_resizing = old_resizing
                    else:
                        # 没有内容时只更新文本宽度
                        self.content_text.setTextWidth(new_width - 20)
                        self.update_labels_position()
                    
                    event.accept()
                    return
                
                super().mouseMoveEvent(event)
            
            def mouseReleaseEvent(self, event):
                """鼠标释放 - 结束缩放"""
                if self.is_resizing:
                    self.is_resizing = False
                    self.resize_start_pos = None
                    self.resize_start_rect = None
                    
                    # 缩放结束后，重新裁剪文本以适应新尺寸
                    if self.full_text:
                        self.update_display()
                    
                    print(f"[文字节点] 缩放完成: {self.rect().width():.0f}×{self.rect().height():.0f}")
                    event.accept()
                    return
                
                super().mouseReleaseEvent(event)
            
            def open_edit_dialog(self):
                """打开编辑对话框 - 编辑完整文本，显示全部字体"""
                # 创建编辑对话框，显示全部文字
                dialog = TextEditDialog(self.full_text if self.full_text else "")
                
                # 设置窗口更大，适合显示全部内容
                dialog.setMinimumSize(900, 700)
                
                # 显示对话框
                if dialog.exec():
                    # 获取编辑后的文本
                    new_text = dialog.edited_text
                    
                    # 更新完整文本
                    self.full_text = new_text
                    
                    # 更新画布显示（只显示前500字）
                    self.update_display()
                    
                    print(f"[文字节点] 文本已更新，总字数: {len(new_text)}")
            
            def paint(self, painter, option, widget):
                """自定义绘制 - 添加缩放指示"""
                super().paint(painter, option, widget)
                
                # 绘制右下角缩放指示器（当鼠标悬停或正在缩放时）
                if self.isSelected() or self.is_resizing:
                    from PySide6.QtGui import QPen, QColor, QPolygonF
                    from PySide6.QtCore import QPointF
                    rect = self.rect()
                    painter.setPen(QPen(QColor("#00bfff"), 2))
                    # 绘制右下角小三角形
                    points = [
                        rect.bottomRight() + QPointF(-15, 0),
                        rect.bottomRight() + QPointF(0, -15),
                        rect.bottomRight()
                    ]
                    painter.drawPolygon(QPolygonF(points))
            
            def contextMenuEvent(self, event):
                """右键菜单 - 编辑文字"""
                from PySide6.QtWidgets import QMenu
                menu = QMenu()
                menu.setStyleSheet("""
                    QMenu {
                        background-color: #1a1a1a;
                        color: #e0e0e0;
                        border: 1px solid #2a2a2a;
                        border-radius: 6px;
                        padding: 5px;
                    }
                    QMenu::item {
                        padding: 8px 25px;
                        border-radius: 4px;
                    }
                    QMenu::item:selected {
                        background-color: #00bfff;
                        color: #000000;
                    }
                """)
                
                act_edit = menu.addAction("📝 编辑文字")
                chosen = menu.exec(event.screenPos())
                
                if chosen is act_edit:
                    # 打开编辑对话框
                    self.open_edit_dialog()
                    event.accept()
                    return
                
                super().contextMenuEvent(event)
        
        return TextNodeImpl
