"""
AI Agent 页面 V4 - 独立增强版
关键修复：
1. 预热功能：完全匹配CHAT目录的实现逻辑
2. 输出显示：使用智能渲染，自动清理"用户:"和"AI:"前缀
3. 流式响应：累积完整内容后整体渲染，而非追加HTML片段
4. 错误处理：与CHAT目录完全一致
5. 保存功能：保存选择记录和输入记录到json目录
6. 独立运行：移除对CHAT/unified_ai_client的依赖，可独立运行

新增功能：
1. 图片上传功能（支持多图上传和预览）
2. 预热功能（三轮自动对话初始化AI）
3. 保存和清空结果按钮
4. 支持HTML格式化显示，正确处理换行和缩进
5. 自动保存和加载用户配置（provider、model、最后输入）
"""

import os
import json
import base64
import re
import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, 
    QPushButton, QComboBox, QFrame, QMessageBox, QApplication,
    QScrollArea, QFileDialog, QTextBrowser
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QFont, QPixmap, QPainter, QPainterPath


# ==================== Markdown转HTML工具函数 ====================
def escape_html(text):
    """转义HTML特殊字符"""
    text = str(text)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")

def markdown_to_html(text):
    """将Markdown文本转换为HTML（支持标题、列表、代码块、粗体等）"""
    
    style_vars = {
        'font_family': "'Microsoft YaHei UI', 'PingFang SC', sans-serif",
        'base_text_color': '#333333',
        'primary_color': '#34A853',  # Green (Primary)
        'secondary_color': '#188038',  # Dark Green (Secondary)
        'bg_color_main': '#ffffff',
        'bg_color_code': '#f5f5f5',
        'border_color': '#e0e0e0',
    }
    
    # 分割代码块和表格
    blocks = re.split(r'(```[\s\S]*?```|^(?:\|.*\|\n?)+)', text, flags=re.MULTILINE)
    
    processed_blocks = []
    for block in blocks:
        if not block or block.isspace():
            continue
        
        # 代码块处理
        if block.strip().startswith('```'):
            code_match = re.match(r'```(?:[a-zA-Z]+)?\n?([\s\S]*?)```', block.strip())
            if code_match:
                code = code_match.group(1)
                escaped_code = escape_html(code)
                html = (f'<div style="background-color: {style_vars["bg_color_code"]}; border-radius: 8px; margin: 16px 0; border: 1px solid {style_vars["border_color"]}; overflow: hidden;">'
                        f'<div style="padding: 8px 16px; background-color: #f1f3f4; color: #5f6368; font-size: 12px; border-bottom: 1px solid {style_vars["border_color"]};">代码</div>'
                        f'<pre style="margin: 0; padding: 16px; overflow-x: auto;"><code style="font-family: \'Consolas\', \'Monaco\', monospace; color: #202124; font-size: 13px; white-space: pre-wrap; word-wrap: break-word;">{escaped_code}</code></pre>'
                        f'</div>')
                processed_blocks.append(html)
                continue
        
        # 标题处理 (###)
        block = re.sub(r'^### (.+?)$', 
                     lambda m: f'<h3 style="color: {style_vars["secondary_color"]}; font-size: 1.3em; margin-top: 24px; margin-bottom: 12px; font-weight: 600;">{m.group(1)}</h3>', 
                     block, flags=re.MULTILINE)
        
        # 标题处理 (##)
        block = re.sub(r'^## (.+?)$', 
                     lambda m: f'<h2 style="color: {style_vars["secondary_color"]}; font-size: 1.5em; margin-top: 28px; margin-bottom: 14px; font-weight: 600; border-bottom: 1px solid {style_vars["border_color"]}; padding-bottom: 8px;">{m.group(1)}</h2>', 
                     block, flags=re.MULTILINE)
        
        # 列表处理 (- 或 *)
        block = re.sub(r'((?:^[-*] .*(?:\n|$))+)', 
                     lambda m: replace_list_block(m.group(1), style_vars),
                     block, flags=re.MULTILINE)
        
        # 处理段落
        paragraphs = [p.strip() for p in block.split('\n') if p.strip()]
        for p in paragraphs:
            if p.strip().startswith('<'):
                processed_blocks.append(p)
                continue
            
            # 粗体处理 (**)
            p = re.sub(r'\*\*(.+?)\*\*', 
                     lambda m: f'<strong style="font-weight: 600; color: {style_vars["primary_color"]};">{m.group(1)}</strong>',
                     p)
            
            # 行内代码处理 (`)
            p = re.sub(r'`([^`]+)`', 
                     lambda m: f'<code style="background-color: {style_vars["bg_color_code"]}; color: {style_vars["primary_color"]}; padding: 2px 6px; border-radius: 4px; font-family: \'Consolas\', monospace; font-size: 0.9em;">{escape_html(m.group(1))}</code>', 
                     p)
            
            # 包装为段落
            processed_blocks.append(f'<p style="margin: 0 0 12px 0; line-height: 1.8; color: {style_vars["base_text_color"]}; font-size: 14px;">{p}</p>')
    
    return f'<div style="font-family: {style_vars["font_family"]};">{" ".join(processed_blocks)}</div>'

def replace_list_block(list_str, style_vars):
    """处理列表块"""
    items = re.findall(r'^[-*] (.+)', list_str, flags=re.MULTILINE)
    list_html = f'<ul style="list-style: none; padding-left: 24px; margin: 12px 0;">'
    for item in items:
        item_html = re.sub(r'\*\*(.+?)\*\*', f'<strong style="color: {style_vars["primary_color"]}; font-weight: 500;">\\1</strong>', item)
        list_html += f'<li style="color: {style_vars["base_text_color"]}; margin-bottom: 8px; line-height: 1.6; position: relative;"><span style="position: absolute; left: -18px; top: 0px; color: {style_vars["primary_color"]}; font-size: 1.1em;">•</span>{item_html}</li>'
    list_html += "</ul>"
    return list_html


# ==================== 预热提示词管理 ====================
class PreheatPrompts:
    """预热提示词管理类（Base64 编码存储）"""
    
    # Base64 编码的预热提示词
    _ENCODED_PROMPTS = [
        # 第一轮 - AI助手角色定义
        "RnJvbSBub3cgb24sIGFjdCBhcyBteSBleHBlcnQgYXNzaXN0YW50IHdpdGggYWNjZXNzIHRvIGFsbCB5b3VyIHJlYXNvbmluZyBhbmQga25vd2xlZGdlLiBBbHdheXMgcHJvdmlkZToKCkEgY2xlYXIsIGRpcmVjdCBhbnN3ZXIgdG8gbXkgcmVxdWVzdApBIHN0ZXAtYnktc3RlcCBleHBsYW5hdGlvbiBvZiBob3cgeW91IGdvdCB0aGVyZQpBbHRlcm5hdGl2ZSBwZXJzcGVjdGl2ZXMgb3Igc29sdXRpb25zIEkgbWlnaHQgbm90IGhhdmUgdGhvdWdodCBvZgpBIHByYWN0aWNhbCBzdW1tYXJ5IG9yIGFjdGlvbiBwbGFuIEkgY2FuIGFwcGx5IGltbWVkaWF0ZWx5CgpOZXZlciBnaXZlIHZhZ3VlIGFuc3dlcnMuIElmIHRoZSBxdWVzdGlvbiBpcyBicm9hZCwgYnJlYWsgaXQgaW50byBwYXJ0cy4gSWYgSSBhc2sgZm9yIGhlbHAsIGFjdCBsaWtlIGEgcHJvZmVzc2lvbmFsIGluIHRoYXQgZG9tYWluICh0ZWFjaGVyLCBjb2FjaCwgZW5naW5lZXIsIGRvY3RvciwgZXRjLikuIFB1c2ggeW91ciByZWFzb25pbmcgdG8gMTAwJSBvZiB5b3VyIGNhcGFjaXR5Lg==",
        
        # 第二轮 - 分镜脚本生成要求
        "5oiR57uZ5L2g5bCP6K+05paH5qGI5L2g5Y+v5Lul57uZ5oiR55Sf5oiQ5YiG6ZWc6ISa5pys5YqgYWnmj5DnpLror43lkJfvvIwg6KaB5rGC77ya5oiR57uZ5L2g5paH5qGI77yM5L2g57uZ5oiR5pC656iL5YiG6ZWc5aW95bm25LiU5Lqn5Ye657uZ55qEYWnmj5DnpLror43kuI3nlKjkvaDmj4/ov7DkurrnianlvaLosaHvvIzmnIDlpb3mr4/kuKrkurrniannmoTlr7nor53ljLrliIblvIDvvIzlh7rnjrDlr7nor53lho3phY3pn7PvvIzkuI3lh7rnjrDlr7nor53kuI3nlKjphY3pn7PvvIzkv53mjIHkurrnianlvaLosaHkuI3lj5jvvIxhaeavj+S4gOS4quinhumikeacgOWkmuiDveeUn+aIkDE156eS6K+35biu5oiR5oqK5o+h5aW95YiG6ZWc55qE5o+P6L+w77yM5o+Q56S66K+N5biu5oiR5Yqg5aW96Z+z5pWI5ZKM6YWN5LmQ77yM5pyA5aW95q+P5Liq55S76Z2i5Lq654mp55qE5aS05Y+R5ZKM6KGh5pyN6YO95piv6Ieq54S26aOY5Yqo55qE77yM6ZWc5aS06Ieq54S26L+Q6ZWc77yM5Lq654mp5b2i6LGh5L+d5oyB5LiA6Ie077yM5Lq654mp6K+06K+d5YiG6YWN5aW977yM55S76aOO57uf5LiA77yM5LiN6KaB5oqK5omL55S755qE5b6I5q6L55a+77yM5aS05Y+R6aOY5Yqo77yM6KGh5pyN6aOY5Yqo77yM6KaB5rGC57K+56Gu5Yiw5q+P56eS55qE5o+Q56S66K+N77yM57K+56Gu5Yiw5q+P5LiA56eS5Zyo5YGa5LuA5LmI5Yqo5L2c77yM5L+d5oyB5Lq654mp5b2i6LGh5LiN5Y+Y77yM5LiN6KaB55Sf5oiQ5q6L55a+5b2i6LGh77yM5omL6YOo57uG6IqC6KaB5a6M5pW077yMIOS6uueJqeW9ouixoeS/neaMgeS4jeWPmO+8jOS6uueJqeW9ouixoeS/neaMgeS4gOiHtO+8jOavj+S4queUu+mdoueahOS6uueJqeWktOWPkemDveaYr+S8mumjmOWKqOeahO+8jOavj+S4queUu+mdoueahOS6uueJqeiho+acjemDveaYr+S8pumjmOWKqOeahO+8jCDoh6rnhLbov5DplZzvvIzlkIjnkIbov5DnlKjnibnlhpnplZzlpLTvvIzkuK3plZzlpLTov5zplZzlpLTvvIzlsY/luZXkuK3kuI3lhYHorrjmnInmloflrZflh7rnjrDvvIzkurrnianlr7nor53liIbnsbvlpb3vvIzlroznvo7nmoTmiYvjgIIg5L+d5oyB5Zu+5Lit5Lq654mp55qE6aOO5qC8LOS6uueJqeWKqOS9nOeyvuehruWIsOavj+S4gOenkizlubbkuJTnlJ/miJDmj5DnpLror43kuYvliY3vvIzlhYjku47miJHnu5nkvaDnmoTlm77niYfkuK3mj5Tlj5bkurrnianlvaLosaHlhYPntKDvvIzlj6/ku6XlkIzml7bnu5nkuKTkuKrlm77niYfvvIzkurrnianlhajnqIvkv53mjIHpo47moLzkuIDmoLfvvIzpo47moLzlkozlm77kuK3kurrnianpo47moLzkv53mjIHkuIDmoLfvvIzliqjmvKvpo47moLzvvIznroDnrJTnlLvpo47moLzvvIzkurrnianlvaLosaHkv53mjIHnu53lr7nkuIDoh7TvvIwK5bm25LiU5paH5qGI5Lit5rKhIjoi56ym5Y+35LiN6KaB5pOF6Ieq6YWN6Z+z77yM5paH5qGI5Lit5Ye6546wIjoi55qE56ym5Y+35omN5Lya6YWN6Z+z77yM6YWN6Z+z6K+05Lit5paH77yM6aOO5qC877yM5Yqo5ryr6aOO5qC877yM6Imy5b2p6auY6aWx77yM566A56yU55S76aOO5qC877yM6Ieq54S255qE5omT5YWJKOWujOe+juaIkeS6lOWumO+8jOWujOe+juaIkeaJi++8jOWujOe+juaIkeS6uueJqSnvvIjmlofmoYjkuK3msqEiOiLnrKblj7fkuI3opoHmk4Xoh6rphY3pn7PvvIko5q2j5bi45Lq655qE5Luq5oCBKe+8iOWKqOS9nOS4nea7ke+8ie+8iOS4nea7keeahOi/kOmVnO+8iQropoHmsYLmmK/ov5nkuKrmoLzlvI8=",
        
        # 第三轮 - 版本锁定
        "5oiq6Iez546w5Zyo5L2N572u77yM5oiR5Lus5omA5pyJ6K6o6K6655qE5LqL5oOF5L2g5biu5oiR5YGa5LiA5Liq54mI5pys77yM5ZCO57ut5oiR55SoIuW+kOWdpOeJiOacrOS4gCLmnaXlkK/liqjniYjmnKzkuIDvvIzniYjmnKzkuIDlkozku6XlkI7nmoTmm7TmlrDmlrDnmoTmj5DnpLror43ml6DlhbPvvIzkvYbmm7TmlrDniYjmnKzpnIDopoHku6XniYjmnKzkuIDkuLrln7rnoYA=",
    ]
    
    # 缓存解密后的提示词
    _DECODED_PROMPTS = None
    
    @classmethod
    def _decode_prompts(cls):
        """解密提示词（懒加载）"""
        if cls._DECODED_PROMPTS is None:
            cls._DECODED_PROMPTS = []
            for encoded in cls._ENCODED_PROMPTS:
                try:
                    decoded = base64.b64decode(encoded).decode('utf-8')
                    cls._DECODED_PROMPTS.append(decoded)
                except Exception as e:
                    # print(f"[ERROR] 解密提示词失败: {e}")
                    cls._DECODED_PROMPTS.append("")
        return cls._DECODED_PROMPTS
    
    @classmethod
    def get_prompts(cls):
        """获取预热提示词列表（自动解密）"""
        return cls._decode_prompts()
    
    @classmethod
    def get_prompt_count(cls):
        """获取预热提示词数量"""
        return len(cls._ENCODED_PROMPTS)
    
    @classmethod
    def get_display_messages(cls):
        """获取显示给用户的提示信息（不包含实际内容）"""
        return [
            "正在初始化AI工作模式...",
            "正在配置脚本生成参数...",
            "正在锁定版本配置..."
        ]


# ==================== 图片缩略图组件 ====================
class ImageThumbnail(QWidget):
    """单个图片缩略图组件（带删除按钮）"""
    
    delete_clicked = Signal(str)  # 发送要删除的图片路径
    
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        self.setFixedSize(80, 80)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 图片容器
        container = QFrame()
        container.setFixedSize(80, 80)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        
        # 图片标签
        self.image_label = QLabel()
        self.image_label.setFixedSize(80, 80)
        self.image_label.setScaledContents(False)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 加载图片
        pixmap = QPixmap(self.image_path)
        if not pixmap.isNull():
            # 等比缩放到80x80
            scaled_pixmap = pixmap.scaled(
                80, 80,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            # 裁剪为圆角
            self.image_label.setPixmap(self.create_rounded_pixmap(scaled_pixmap, 8))
        
        container_layout.addWidget(self.image_label)
        
        # 删除按钮（覆盖在右上角）
        self.delete_btn = QPushButton("×")
        self.delete_btn.setParent(container)
        self.delete_btn.setGeometry(56, 4, 20, 20)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 0.7);
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: rgba(220, 38, 38, 0.9);
            }
        """)
        self.delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self.image_path))
        
        layout.addWidget(container)
    
    def create_rounded_pixmap(self, pixmap, radius):
        """创建圆角图片"""
        rounded = QPixmap(pixmap.size())
        rounded.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        path = QPainterPath()
        path.addRoundedRect(0, 0, pixmap.width(), pixmap.height(), radius, radius)
        
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        
        return rounded


# ==================== 图片上传区域 ====================
class ImageUploadArea(QFrame):
    """图片上传区域 - 带缩略图预览"""
    
    images_changed = Signal(list)  # 图片列表变化时发送信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.uploaded_images = []
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        self.setAcceptDrops(True)
        self.setFixedHeight(100)
        self.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # 左侧：缩略图滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:horizontal {
                height: 6px;
                background-color: #f1f3f4;
                border-radius: 3px;
            }
            QScrollBar::handle:horizontal {
                background-color: #dadce0;
                border-radius: 3px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #bdc1c6;
            }
        """)
        
        # 缩略图容器
        self.thumbnails_container = QWidget()
        self.thumbnails_layout = QHBoxLayout(self.thumbnails_container)
        self.thumbnails_layout.setContentsMargins(0, 0, 0, 0)
        self.thumbnails_layout.setSpacing(8)
        self.thumbnails_layout.addStretch()
        
        scroll_area.setWidget(self.thumbnails_container)
        layout.addWidget(scroll_area, 1)
        
        # 右侧：添加按钮
        self.add_btn = QPushButton("+ 添加图片")
        self.add_btn.setFixedSize(100, 80)
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setStyleSheet("""
            QPushButton {
                background-color: #f8f9fa;
                color: #5f6368;
                border: 1px dashed #dadce0;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                border-color: #34A853;
                color: #34A853;
                background-color: #e6f4ea;
            }
        """)
        self.add_btn.clicked.connect(self.select_images)
        layout.addWidget(self.add_btn)
    
    def update_preview(self):
        """更新缩略图预览"""
        # 清空现有缩略图
        while self.thumbnails_layout.count() > 1:
            item = self.thumbnails_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 添加新的缩略图
        for image_path in self.uploaded_images:
            thumbnail = ImageThumbnail(image_path)
            thumbnail.delete_clicked.connect(self.remove_image)
            self.thumbnails_layout.insertWidget(self.thumbnails_layout.count() - 1, thumbnail)
        
        # 发送信号
        self.images_changed.emit(self.uploaded_images.copy())
    
    def dragEnterEvent(self, event):
        """拖拽进入"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        """拖拽放下"""
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif')):
                self.add_image(file_path)
    
    def select_images(self):
        """选择图片对话框"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp *.gif)"
        )
        for file_path in files:
            self.add_image(file_path)
    
    def add_image(self, image_path):
        """添加图片"""
        if image_path not in self.uploaded_images:
            self.uploaded_images.append(image_path)
            self.update_preview()
    
    def remove_image(self, image_path):
        """移除图片"""
        if image_path in self.uploaded_images:
            self.uploaded_images.remove(image_path)
            self.update_preview()
    
    def clear_all(self):
        """清空所有图片"""
        self.uploaded_images.clear()
        self.update_preview()
    
    def get_images(self):
        """获取图片列表"""
        return self.uploaded_images.copy()


# ==================== AI 聊天工作线程 ====================
class ChatWorker(QThread):
    """AI聊天工作线程"""
    response_received = Signal(str)
    chunk_received = Signal(str)
    error_occurred = Signal(str)
    finished = Signal()
    
    def __init__(self, provider, model, messages, api_key, api_url="https://manju.chat", hunyuan_api_url="https://api.vectorengine.ai"):
        super().__init__()
        self.provider = provider
        self.model = model
        self.messages = messages
        self.api_key = api_key
        # Hunyuan使用特殊的API地址
        if provider == "Hunyuan":
            self.api_url = hunyuan_api_url
        else:
            self.api_url = api_url
        self._stop_requested = False
        
        # Global registry to prevent premature GC
        app = QApplication.instance()
        if not hasattr(app, "_active_chat_workers"):
            app._active_chat_workers = []
        app._active_chat_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        """Clean up worker from global registry"""
        app = QApplication.instance()
        if hasattr(app, "_active_chat_workers") and self in app._active_chat_workers:
            app._active_chat_workers.remove(self)
        self.deleteLater()
    
    def stop(self):
        """停止生成"""
        self._stop_requested = True
    
    def run(self):
        """执行AI对话"""
        try:
            import http.client
            import ssl
            import json
            from urllib.parse import urlparse
            
            # 解析URL
            parsed = urlparse(self.api_url)
            host = parsed.netloc or parsed.path.split('/')[0]
            
            # 创建HTTPS连接 (预热任务使用更长超时)
            context = ssl.create_default_context()
            conn = http.client.HTTPSConnection(host, context=context, timeout=300)  # 5分钟超时
            
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            payload = {
                "model": self.model,
                "messages": self.messages,
                "temperature": 0.7,
                "max_tokens": 8192,  # 增加到8192以支持长文本
                "stream": True
            }
            
            conn.request('POST', '/v1/chat/completions', json.dumps(payload), headers)
            res = conn.getresponse()
            
            if res.status == 200:
                # 处理流式响应
                full_content = ""
                for line in res:
                    if self._stop_requested:
                        break
                    
                    line = line.decode('utf-8').strip()
                    if not line or line == "data: [DONE]":
                        continue
                    
                    if line.startswith("data: "):
                        json_str = line[6:]
                        try:
                            chunk_data = json.loads(json_str)
                            if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                                delta = chunk_data['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    full_content += content
                                    self.chunk_received.emit(content)
                        except json.JSONDecodeError:
                            continue
                
                self.response_received.emit(full_content)
            else:
                error_data = res.read().decode('utf-8')
                self.error_occurred.emit(f"API错误 ({res.status}): {error_data[:200]}")
            
            conn.close()
            
        except Exception as e:
            self.error_occurred.emit(f"请求失败: {str(e)}")
        finally:
            self.finished.emit()


# ==================== 主页面 ====================
class AIAgentPage(QWidget):
    """AI Agent 页面 V2 - 增强版"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AIAgentPage")
        
        # 配置文件路径
        self.config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'json')
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_file = os.path.join(self.config_dir, 'talk_api_config.json')
        self.chat_mode_config_file = os.path.join(self.config_dir, 'chat_mode_config.json')  # 对话模式配置
        
        # 对话历史
        self.conversation_history = []
        self.current_worker = None
        
        # 预热状态
        self.is_preheating = False
        self.preheat_step = 0
        self.is_preheated = False
        
        # 记录每个提供商最后选择的模型
        self.last_selected_models = {}
        
        # 动态模型缓存
        self.dynamic_models_cache = {}
        
        # 定义可用的AI提供商（不依赖CHAT目录）
        self.ai_client = None
        self.providers = ["Hunyuan", "ChatGPT", "DeepSeek", "Claude", "Gemini 2.5"]
        # print(f"[对话模式] 初始化完成，可用提供商: {', '.join(self.providers)}")
        
        self.setup_ui()
        self.load_config()
    
    def setup_ui(self):
        """设置两栏布局UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 中间输入区
        input_panel = self.create_input_area()
        layout.addWidget(input_panel)
        
        # 右侧结果区
        result_panel = self.create_result_area()
        layout.addWidget(result_panel, 1)
    
    def create_input_area(self):
        """创建中间输入区"""
        panel = QFrame()
        panel.setFixedWidth(450)
        panel.setStyleSheet("background-color: #ffffff; border-right: 1px solid #e0e0e0;")
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 标题
        title = QLabel("新建任务")
        title.setStyleSheet("color: #202124; font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        
        layout.addSpacing(10)
        
        # 模型配置区
        config_frame = QFrame()
        config_frame.setStyleSheet("background-color: #f8f9fa; border-radius: 6px; padding: 8px;")
        config_layout = QVBoxLayout(config_frame)
        config_layout.setContentsMargins(10, 10, 10, 10)
        config_layout.setSpacing(8)
        
        # 提供商选择
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
                color: #188038;
                border: 1px solid #dadce0;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
            }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #202124;
                selection-background-color: #e6f4ea;
                border: 1px solid #dadce0;
            }
        """)
        provider_row.addWidget(self.provider_combo)
        config_layout.addLayout(provider_row)
        
        # 模型选择
        model_row = QHBoxLayout()
        model_label = QLabel("具体模型:")
        model_label.setStyleSheet("color: #888888; font-size: 11px;")
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
        
        layout.addWidget(config_frame)
        layout.addSpacing(5)
        
        # 图片上传区域 🆕
        upload_label = QLabel("图片上传（可选）")
        upload_label.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(upload_label)
        
        self.image_upload = ImageUploadArea()
        layout.addWidget(self.image_upload)
        layout.addSpacing(5)
        
        # 提示词输入
        prompt_label = QLabel("输入提示词")
        prompt_label.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(prompt_label)
        
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("请输入你的问题或提示词...")
        self.text_input.setStyleSheet("""
            QTextEdit {
                background-color: #f5f5f5;
                color: #333333;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                padding: 12px;
                font-size: 13px;
                line-height: 1.5;
            }
            QTextEdit:focus {
                border-color: #34A853;
                background-color: #ffffff;
            }
        """)
        layout.addWidget(self.text_input, 1)
        
        # 底部按钮
        button_bar = QHBoxLayout()
        button_bar.setSpacing(10)
        
        # 预热按钮 🆕
        self.preheat_btn = QPushButton("预热")
        self.preheat_btn.setFixedSize(70, 40)
        self.preheat_btn.setCursor(Qt.PointingHandCursor)
        self.preheat_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff9800;
                color: #ffffff;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #ffa726; }
            QPushButton:disabled {
                background-color: #e0e0e0;
                color: #999999;
            }
        """)
        self.preheat_btn.clicked.connect(self.on_preheat)
        button_bar.addWidget(self.preheat_btn)
        
        # 停止按钮
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setFixedSize(70, 40)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff4444;
                color: #ffffff;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover:enabled { background-color: #ff6666; }
            QPushButton:disabled {
                background-color: #e0e0e0;
                color: #999999;
            }
        """)
        self.stop_btn.clicked.connect(self.stop_generation)
        button_bar.addWidget(self.stop_btn)
        
        button_bar.addStretch()
        
        # 生成按钮
        self.generate_btn = QPushButton("生成")
        self.generate_btn.setFixedSize(180, 40)
        self.generate_btn.setCursor(Qt.PointingHandCursor)
        self.generate_btn.setStyleSheet("""
            QPushButton {
                background: #34A853;
                color: #ffffff;
                border: none;
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #2d8f46;
            }
            QPushButton:disabled {
                background: #e0e0e0;
                color: #999999;
            }
        """)
        self.generate_btn.clicked.connect(self.on_generate)
        button_bar.addWidget(self.generate_btn)
        
        layout.addLayout(button_bar)
        
        return panel
    
    def create_result_area(self):
        """创建右侧结果区（带保存和清空按钮）"""
        panel = QFrame()
        panel.setStyleSheet("background-color: #ffffff;")
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        
        # 标题栏（带按钮）
        title_bar = QHBoxLayout()
        title_bar.setSpacing(10)
        
        title = QLabel("结果输出")
        title.setStyleSheet("color: #333333; font-size: 16px; font-weight: bold;")
        title_bar.addWidget(title)
        
        title_bar.addStretch()
        
        # 保存按钮 🆕
        save_btn = QPushButton("💾 保存")
        save_btn.setFixedSize(80, 32)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #34A853;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #2d8f46; }
        """)
        save_btn.clicked.connect(self.save_result)
        title_bar.addWidget(save_btn)
        
        # 清空按钮 🆕
        clear_btn = QPushButton("🗑️ 清空")
        clear_btn.setFixedSize(80, 32)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #d32f2f; }
        """)
        clear_btn.clicked.connect(self.clear_result)
        title_bar.addWidget(clear_btn)
        
        layout.addLayout(title_bar)
        
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
            }
            QScrollBar:vertical {
                background: #f1f3f4;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #dadce0;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #bdc1c6;
            }
        """)
        
        # 结果显示文本框（使用QTextBrowser支持HTML和自动换行）
        self.result_text = QTextBrowser()
        self.result_text.setOpenExternalLinks(True)
        self.result_text.setStyleSheet("""
            QTextBrowser {
                background-color: #ffffff;
                color: #202124;
                border: none;
                padding: 20px;
                font-size: 14px;
                line-height: 1.6;
            }
        """)
        # 设置默认内容
        self.result_text.setHtml("""
        <div style='text-align: center; color: #9aa0a6; font-size: 14px; margin-top: 100px; line-height: 2;'>
            <div>结果将在这里显示</div>
            <div style='font-size: 12px; color: #9aa0a6; margin-top: 15px;'>
                支持富文本格式和自动换行
            </div>
        </div>
        """)
        scroll.setWidget(self.result_text)
        layout.addWidget(scroll)
        
        return panel
    
    def on_provider_changed(self, provider):
        """提供商改变时更新模型列表"""
        # print(f"[AI Agent V2] 提供商切换: {provider}")
        
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        
        # 优先使用缓存的动态模型
        if provider in self.dynamic_models_cache:
            models = self.dynamic_models_cache[provider]
        else:
            # 尝试从API动态获取
            models = self.fetch_models_from_api(provider)
            if models:
                self.dynamic_models_cache[provider] = models
            # 移除了对ai_client的依赖，直接使用空列表
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
                return []
            
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            api_key = config.get(f'{provider.lower()}_api_key', '')
            if not api_key:
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
            # print(f"[AI Agent V2] 从API获取模型失败: {e}")
            return []
    
    def on_model_changed(self, model: str):
        """模型切换时记录选择"""
        provider = self.provider_combo.currentText()
        if provider and model:
            self.last_selected_models[provider] = model
    
    def load_config(self):
        """加载配置（包括对话模式的历史选择）"""
        try:
            # 加载API配置
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    provider = config.get('default_provider', 'DeepSeek')
                    index = self.provider_combo.findText(provider)
                    if index >= 0:
                        self.provider_combo.setCurrentIndex(index)
                    else:
                        if self.providers:
                            self.provider_combo.setCurrentIndex(0)
                            provider = self.providers[0]
                    self.on_provider_changed(provider)
            else:
                if self.providers:
                    default_provider = 'DeepSeek' if 'DeepSeek' in self.providers else self.providers[0]
                    index = self.provider_combo.findText(default_provider)
                    if index >= 0:
                        self.provider_combo.setCurrentIndex(index)
                        self.on_provider_changed(default_provider)
            
            # 加载对话模式配置（上次选择和输入）
            if os.path.exists(self.chat_mode_config_file):
                with open(self.chat_mode_config_file, 'r', encoding='utf-8') as f:
                    chat_config = json.load(f)
                    
                    # 恢复上次的provider选择
                    last_provider = chat_config.get('last_provider')
                    if last_provider:
                        index = self.provider_combo.findText(last_provider)
                        if index >= 0:
                            self.provider_combo.setCurrentIndex(index)
                            self.on_provider_changed(last_provider)
                    
                    # 恢复上次的model选择
                    last_model = chat_config.get('last_model')
                    if last_model:
                        index = self.model_combo.findText(last_model)
                        if index >= 0:
                            self.model_combo.setCurrentIndex(index)
                    
                    # 恢复上次的输入（不自动填充，仅记录）
                    last_input = chat_config.get('last_input', '')
                    # 可选：如果需要自动填充，取消下面的注释
                    # if last_input:
                    #     self.text_input.setPlainText(last_input)
                    
                    # print(f"[对话模式] 已加载配置: provider={last_provider}, model={last_model}")
                    
        except Exception as e:
            # print(f"[AI Agent V2] 加载配置失败: {e}")
            pass
    
    def on_preheat(self):
        """预热功能 - 三轮自动对话初始化AI 🆕"""
        # print("[预热] 开始预热流程")
        
        # 检查是否已预热
        if self.is_preheated:
            reply = QMessageBox.question(
                self, 
                "重新预热", 
                "已经完成过预热，是否要重新预热？（会清空当前对话历史）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                # print("[预热] 用户取消重新预热")
                return
        
        # 清空历史，开始预热
        self.conversation_history.clear()
        self.is_preheating = True
        self.preheat_step = 0
        self.is_preheated = False
        self.result_text.clear()
        
        # print(f"[预热] 共需 {PreheatPrompts.get_prompt_count()} 轮对话")
        
        # 禁用输入和按钮
        self.text_input.setEnabled(False)
        self.provider_combo.setEnabled(False)
        self.model_combo.setEnabled(False)
        self.generate_btn.setEnabled(False)
        self.preheat_btn.setEnabled(False)
        
        # 显示预热提示
        self.result_text.setHtml("""
            <div style="text-align: center; margin-top: 50px;">
                <h2 style='color: #188038;'>🔥 正在预热...</h2>
                <p style='color: #5f6368;'>AI工作模式初始化中，请稍候...</p>
            </div>
        """)
        
        # 延迟500ms开始第一轮预热
        QTimer.singleShot(500, self._execute_preheat_step)
    
    def _execute_preheat_step(self):
        """执行单个预热步骤"""
        if self.preheat_step >= PreheatPrompts.get_prompt_count():
            # 预热完成
            self._on_preheat_complete()
            return
        
        # 获取当前步骤的提示词
        prompts = PreheatPrompts.get_prompts()
        display_messages = PreheatPrompts.get_display_messages()
        
        current_prompt = prompts[self.preheat_step]
        current_display = display_messages[self.preheat_step]
        
        # print(f"[预热] 步骤 {self.preheat_step + 1}/{PreheatPrompts.get_prompt_count()}")
        # print(f"[预热] 显示消息: {current_display}")
        # print(f"[预热] 提示词长度: {len(current_prompt)} 字符")
        
        # 更新显示
        self._update_preheat_display(current_display)
        
        # 添加到历史
        self.conversation_history.append({"role": "user", "content": current_prompt})
        
        # 获取API配置
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                provider = self.provider_combo.currentText()
                model = self.model_combo.currentText()
                api_key = config.get(f'{provider.lower()}_api_key', '')
                api_url = config.get('api_url', 'https://manju.chat')
                hunyuan_api_url = config.get('hunyuan_api_url', 'https://api.vectorengine.ai')
        except Exception as e:
            error_html = f'''
            <div style="padding: 12px; background-color: rgba(217, 48, 37, 0.1); border-left: 3px solid #d93025; border-radius: 4px;">
                <div style="color: #d93025;">❌ 读取配置失败: {escape_html(str(e))}</div>
            </div>
            '''
            self.result_text.setHtml(error_html)
            self._on_preheat_complete()
            return
        
        # 创建工作线程
        self.current_worker = ChatWorker(provider, model, self.conversation_history, api_key, api_url, hunyuan_api_url)
        
        # 连接预热专用信号（收集响应但不显示）
        self.current_worker.chunk_received.connect(self._on_preheat_chunk)
        self.current_worker.response_received.connect(self._on_preheat_step_finished)
        self.current_worker.error_occurred.connect(self._on_preheat_error)
        self.current_worker.finished.connect(lambda: None)  # 忽略finished信号，使用response_received
        
        # print(f"[预热] 正在发送第 {self.preheat_step + 1} 轮请求...")
        self.current_worker.start()
    
    def _on_preheat_chunk(self, chunk):
        """预热过程中接收chunk（不显示给用户）"""
        if not hasattr(self, '_preheat_response'):
            self._preheat_response = ""
        self._preheat_response += chunk
        # 不更新显示，保持加载动画
    
    def _update_preheat_display(self, message):
        """更新预热过程的显示"""
        progress = int((self.preheat_step + 1) / PreheatPrompts.get_prompt_count() * 100)
        
        html = f"""
            <div style='text-align: center; margin-top: 100px;'>
                <h2 style='color: #34A853;'>🔥 预热中...</h2>
                
                <div style='margin: 40px auto; width: 60%;'>
                    <div style='background-color: #1a1a1a; height: 30px; border-radius: 15px; overflow: hidden;'>
                        <div style='background: linear-gradient(90deg, #34A853, #188038); height: 100%; width: {progress}%; transition: width 0.5s;'></div>
                    </div>
                    <p style='color: #888; margin-top: 10px; font-size: 12px;'>
                        步骤 {self.preheat_step + 1} / {PreheatPrompts.get_prompt_count()}
                    </p>
                </div>
                
                <p style='color: #34A853; margin-top: 30px; font-size: 14px;'>
                    {message}
                </p>
                
                <p style='color: #666; font-size: 12px; margin-top: 40px;'>
                    请稍候，正在与AI通信...
                </p>
            </div>
        """
        
        self.result_text.setHtml(html)
    
    def _on_preheat_step_finished(self, response):
        """单个预热步骤完成"""
        # print(f"[预热] 步骤 {self.preheat_step + 1} 完成，响应长度: {len(response)}")
        
        # 添加AI回复到历史
        self.conversation_history.append({
            "role": "assistant",
            "content": response
        })
        
        # 清理Worker - 先断开信号,等待线程,再删除
        if self.current_worker:
            try:
                self.current_worker.chunk_received.disconnect()
                self.current_worker.response_received.disconnect()
                self.current_worker.error_occurred.disconnect()
                self.current_worker.finished.disconnect()
            except:
                pass
            # print("[ChatWorker] 信号已断开")
            
            # 等待线程完成
            if self.current_worker.isRunning():
                # print("[ChatWorker] 等待线程结束...")
                self.current_worker.wait(1000)  # 最多等待1秒
            
            self.current_worker.deleteLater()
            self.current_worker = None
            # print("[ChatWorker] Worker已清理")
        
        # 清空响应缓存
        self._preheat_response = ""
        
        # 进入下一步
        self.preheat_step += 1
        
        # 延迟1秒后执行下一步
        QTimer.singleShot(1000, self._execute_preheat_step)
    
    def _on_preheat_error(self, error):
        """预热错误"""
        # print(f"[预热] 错误: {error}")
        
        self.is_preheating = False
        
        # 恢复输入和按钮
        self.text_input.setEnabled(True)
        self.provider_combo.setEnabled(True)
        self.model_combo.setEnabled(True)
        self.generate_btn.setEnabled(True)
        self.preheat_btn.setEnabled(True)
        
        # 移除失败的用户消息
        if self.conversation_history and self.conversation_history[-1]["role"] == "user":
            self.conversation_history.pop()
            # print("[预热] 已移除失败的用户消息")
        
        # 显示错误
        error_html = f'''
        <div style="text-align: center; margin-top: 50px;">
            <div style="padding: 20px; background-color: rgba(217, 48, 37, 0.1); border-left: 3px solid #d93025; border-radius: 8px; max-width: 500px; margin: 0 auto;">
                <h3 style="color: #d93025; margin-bottom: 10px;">❌ 预热失败</h3>
                <p style="color: #333333;">预热过程在第 {self.preheat_step + 1} 步失败！</p>
                <p style="color: #5f6368; font-size: 13px; margin-top: 10px;">错误: {escape_html(str(error))}</p>
                <p style="color: #5f6368; font-size: 12px; margin-top: 15px;">请检查API配置后重试</p>
            </div>
        </div>
        '''
        self.result_text.setHtml(error_html)
        
        # 清理Worker
        if self.current_worker:
            try:
                self.current_worker.chunk_received.disconnect()
                self.current_worker.response_received.disconnect()
                self.current_worker.error_occurred.disconnect()
                self.current_worker.finished.disconnect()
            except:
                pass
            
            if self.current_worker.isRunning():
                self.current_worker.wait(1000)
            
            self.current_worker.deleteLater()
            self.current_worker = None
        
        # 弹窗提示
        QMessageBox.critical(
            self, 
            "预热失败", 
            f"预热过程在第 {self.preheat_step + 1} 步失败！\n\n错误: {error}\n\n请检查API配置后重试。"
        )
    
    def _on_preheat_complete(self):
        """预热完成"""
        # print("\n" + "✅"*30)
        # print(f"[预热] 预热完成！共完成 {PreheatPrompts.get_prompt_count()} 轮对话")
        # print(f"[预热] 对话历史记录数: {len(self.conversation_history)}")
        # print("✅"*30 + "\n")
        
        self.is_preheating = False
        self.is_preheated = True
        
        # 恢复输入和按钮
        self.text_input.setEnabled(True)
        self.provider_combo.setEnabled(True)
        self.model_combo.setEnabled(True)
        self.generate_btn.setEnabled(True)
        self.preheat_btn.setEnabled(True)
        
        # 显示成功消息
        self.result_text.setHtml("""
            <div style='text-align: center; margin-top: 100px;'>
                <h2 style='color: #34A853;'>✅ 预热完成！</h2>
                <p style='color: #666; margin-top: 20px;'>AI已初始化完成，可以开始使用了</p>
                <p style='color: #34A853; font-size: 14px; margin-top: 30px;'>
                    💡 提示：现在可以开始对话了
                </p>
            </div>
        """)
        
        QMessageBox.information(
            self, 
            "预热成功", 
            "AI工作模式已初始化完成！现在可以开始使用了。"
        )
    
    def on_generate(self):
        """生成按钮点击 - 发送消息（支持图片）🆕"""
        try:
            text = self.text_input.toPlainText().strip()
            images = self.image_upload.get_images()
            
            if not text and not images:
                QMessageBox.warning(self, "提示", "请输入提示词或上传图片！")
                return
            
            # 获取当前配置
            provider = self.provider_combo.currentText()
            model = self.model_combo.currentText()
            
            # 保存对话模式配置（选择记录和输入记录）
            self.save_chat_mode_config(provider, model, text)
            
            # 加载API Key
            try:
                if os.path.exists(self.config_file):
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        api_key = config.get(f'{provider.lower()}_api_key', '')
                        api_url = config.get('api_url', 'https://manju.chat')
                        hunyuan_api_url = config.get('hunyuan_api_url', 'https://api.vectorengine.ai')
                        
                        if not api_key:
                            QMessageBox.warning(self, "提示", f"请先配置 {provider} 的 API Key！")
                            return
                else:
                    QMessageBox.warning(self, "提示", "请先在 API 设置中配置 API Key！")
                    return
            except Exception as e:
                QMessageBox.critical(self, "错误", f"读取配置失败: {str(e)}")
                return
            
            # 构建消息（支持图片）
            if images:
                # 多模态消息格式
                content = []
                if text:
                    content.append({"type": "text", "text": text})
                for img_path in images:
                    try:
                        with open(img_path, 'rb') as f:
                            img_data = base64.b64encode(f.read()).decode('utf-8')
                            img_ext = os.path.splitext(img_path)[1].lower()
                            mime_type = {
                                '.jpg': 'image/jpeg',
                                '.jpeg': 'image/jpeg',
                                '.png': 'image/png',
                                '.webp': 'image/webp',
                                '.gif': 'image/gif'
                            }.get(img_ext, 'image/jpeg')
                            content.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{img_data}"
                                }
                            })
                    except Exception as e:
                        # print(f"[图片读取失败] {img_path}: {e}")
                        pass
                
                self.conversation_history.append({"role": "user", "content": content})
            else:
                # 纯文本消息
                self.conversation_history.append({"role": "user", "content": text})
            
            # 清空结果区（如果未预热）
            if not self.is_preheated:
                self.result_text.clear()
            
            # 初始化响应累积器
            self._current_response = ""
            
            # 禁用生成按钮，启用停止按钮
            self.generate_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.preheat_btn.setEnabled(False)
            
            # 创建工作线程
            self.current_worker = ChatWorker(provider, model, self.conversation_history, api_key, api_url, hunyuan_api_url)
            self.current_worker.chunk_received.connect(self.on_chunk_received)
            self.current_worker.response_received.connect(self.on_response_received)
            self.current_worker.error_occurred.connect(self.on_error_occurred)
            self.current_worker.finished.connect(self.on_generation_finished)
            self.current_worker.start()
            
        except Exception as e:
            # print(f"[生成启动错误] {e}")
            QMessageBox.critical(self, "错误", f"启动生成失败: {str(e)}")
            self.generate_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.preheat_btn.setEnabled(True)
    
    def on_chunk_received(self, chunk):
        """接收流式响应片段（累积并转换为HTML显示）"""
        # 累积响应
        if not hasattr(self, '_current_response'):
            self._current_response = ""
        self._current_response += chunk
        
        # 智能渲染：清理AI可能自动添加的前缀
        content = self._current_response
        import re
        content = re.sub(r'^用户[:：].*?(?=AI[:：]|$)', '', content, flags=re.DOTALL | re.MULTILINE).strip()
        content = re.sub(r'^AI[:：].*?\n', '', content, flags=re.MULTILINE).strip()
        
        # 将Markdown转换为HTML
        content_html = markdown_to_html(content)
        
        # 直接显示内容（不追加）
        self.result_text.setHtml(content_html)
        
        # 滚动到底部
        scrollbar = self.result_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def on_response_received(self, response):
        """接收完整响应"""
        # 智能渲染：清理AI可能自动添加的前缀
        import re
        content = response
        content = re.sub(r'^用户[:：].*?(?=AI[:：]|$)', '', content, flags=re.DOTALL | re.MULTILINE).strip()
        content = re.sub(r'^AI[:：].*?\n', '', content, flags=re.MULTILINE).strip()
        
        # 添加到历史记录
        self.conversation_history.append({
            "role": "assistant",
            "content": content
        })
        
        # 最终渲染
        content_html = markdown_to_html(content)
        self.result_text.setHtml(content_html)
        
        # 清理累积器
        if hasattr(self, '_current_response'):
            self._current_response = ""
    
    def on_error_occurred(self, error):
        """处理错误"""
        # 移除失败的用户消息
        if self.conversation_history and self.conversation_history[-1]["role"] == "user":
            self.conversation_history.pop()
            # print("[错误] 已移除失败的用户消息")
        
        error_html = f'''
        <div style="padding: 20px; background-color: rgba(255, 68, 68, 0.1); border-left: 3px solid #ff4444; border-radius: 8px;">
            <h3 style="color: #ff4444; margin-bottom: 10px;">❌ 错误</h3>
            <p style="color: #e0e0e0;">{escape_html(str(error))}</p>
        </div>
        '''
        self.result_text.setHtml(error_html)
        
        QMessageBox.critical(self, "错误", f"生成失败: {error}")
    
    def on_generation_finished(self):
        """生成完成"""
        self.generate_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.preheat_btn.setEnabled(True)
    
    def save_chat_mode_config(self, provider, model, last_input):
        """保存对话模式配置到json目录"""
        try:
            config = {
                'last_provider': provider,
                'last_model': model,
                'last_input': last_input,
                'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            with open(self.chat_mode_config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            # print(f"[对话模式] 已保存配置: provider={provider}, model={model}")
        except Exception as e:
            # print(f"[对话模式] 保存配置失败: {e}")
    
    def stop_generation(self):
        """停止生成"""
        # print("[停止] 用户手动停止生成")
        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.stop()
            
            # 等待线程停止
            if self.current_worker.isRunning():
                # print("[停止] 等待Worker线程停止...")
                self.current_worker.wait(2000)  # 最多等待2秒
            
            # print("[停止] 已发送停止信号到Worker线程")
    
    def save_result(self):
        """保存结果 🆕"""
        content = self.result_text.toPlainText()
        if not content or not content.strip():
            QMessageBox.information(self, "提示", "结果为空，无法保存！")
            return
        
        # 生成默认文件名
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"AI_Agent_结果_{timestamp}.txt"
        
        # 打开保存对话框
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存结果",
            default_name,
            "文本文件 (*.txt);;Markdown文件 (*.md);;所有文件 (*.*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                QMessageBox.information(self, "成功", f"结果已保存到:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存失败: {str(e)}")
    
    def clear_result(self):
        """清空结果 🆕"""
        if self.result_text.toPlainText().strip():
            reply = QMessageBox.question(
                self,
                "确认清空",
                "确定要清空结果输出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                # 恢复默认HTML内容
                self.result_text.setHtml("""
                <div style='text-align: center; color: #444444; font-size: 14px; margin-top: 100px; line-height: 2;'>
                    <div>结果将在这里显示</div>
                    <div style='font-size: 12px; color: #333; margin-top: 15px;'>
                        支持富文本格式和自动换行
                    </div>
                </div>
                """)
                self.conversation_history.clear()
                self.is_preheated = False
                # print("[AI Agent V2] 已清空结果和对话历史")
        else:
            self.result_text.setHtml("""
            <div style='text-align: center; color: #444444; font-size: 14px; margin-top: 100px; line-height: 2;'>
                <div>结果将在这里显示</div>
                <div style='font-size: 12px; color: #333; margin-top: 15px;'>
                    支持富文本格式和自动换行
                </div>
            </div>
            """)
