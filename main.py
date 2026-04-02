import sys
import os
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QHBoxLayout, QVBoxLayout, QToolButton, QLineEdit, QMessageBox, QSizePolicy
)
from PySide6.QtCore import Qt, QSize, QUrl, QTimer, Signal, QObject, QEvent
import threading
from setting import SettingsDialog
from photo import PhotoPage
from about import AboutPage
try:
    from AIagent import AIAgentPage
except Exception:
    AIAgentPage = None
import traceback

try:
    from lingdong import LingdongAgentPage
except Exception:
    LingdongAgentPage = None
    lingdong_import_error = traceback.format_exc()
else:
    lingdong_import_error = None
from video import VideoPage
try:
    from GGGComics import GGGComicsPage
except Exception:
    GGGComicsPage = None
from fenjing_main import StoryboardPanel
from sora_jiaoseku import SoraCharacterPage
from PySide6.QtGui import QIcon, QPixmap, QPainter, QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QSvgWidget
# from mainHistory import HomePage  # Removed
from Legalterms import ensure_terms_agreed


def svg_widget(svg_str, size=18):
    w = QSvgWidget()
    w.load(bytearray(svg_str, 'utf-8'))
    w.setFixedSize(size, size)
    return w

def svg_icon(svg_str, size=18):
    renderer = QSvgRenderer(bytearray(svg_str, 'utf-8'))
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()
    return QIcon(pix)


class MenuItem(QFrame):
    def __init__(self, text, svg, key=None):
        super().__init__()
        self.setObjectName("MenuItem")
        h = QHBoxLayout(self)
        # 增加高度和内边距，使菜单更舒展
        h.setContentsMargins(12, 0, 12, 0)
        h.setSpacing(12)
        self._svg = svg  # 保存原始SVG内容
        self.icon_widget = svg_widget(svg, 24)  # 稍微增大图标
        self.label = QLabel(text)
        self.label.setObjectName("MenuText")
        h.addWidget(self.icon_widget) # 移除 AlignLeft，由布局控制
        h.addWidget(self.label)
        h.setAlignment(Qt.AlignLeft) # 默认左对齐
        self.setFixedHeight(44)  # 增加高度到 44px
        # _text 作为点击分发的稳定键值，独立于显示语言
        self._text = key or text
        self._display_text = text
        self.setProperty("selected", False)
        self.setProperty("collapsed", False)

    def set_selected(self, selected: bool):
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        
        # 选中时图标变绿
        if selected:
            colored_svg = self._svg.replace('stroke="#5f6368"', 'stroke="#1E8E3E"')
            self.icon_widget.load(bytearray(colored_svg, 'utf-8'))
        else:
            self.icon_widget.load(bytearray(self._svg, 'utf-8'))

    def set_display_text(self, text: str):
        self._display_text = text
        self.label.setText(text)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 向上查找主窗口并分发点击事件
            p = self.parent()
            while p and not hasattr(p, 'on_menu_clicked'):
                p = p.parent()
            if p and hasattr(p, 'on_menu_clicked'):
                p.on_menu_clicked(self._text)

    def set_collapsed(self, collapsed: bool):
        self.setProperty("collapsed", collapsed)
        self.label.setVisible(not collapsed)
        
        if collapsed:
            # 折叠时居中显示图标
            self.layout().setContentsMargins(0, 0, 0, 0)
            self.layout().setAlignment(Qt.AlignCenter)
        else:
            # 展开时左对齐
            self.layout().setContentsMargins(12, 0, 12, 0)
            self.layout().setAlignment(Qt.AlignLeft)
        
        self.style().unpolish(self)
        self.style().polish(self)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # 改为无边框窗口，顶部自定义黑色窗体
        self.setWindowTitle("Ghost Uncle AI - 鬼叔AI")
        self.setMinimumSize(1200, 700)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self._drag_pos = None
        self._maximized = False
        self.sidebar_collapsed = True

        root = QWidget()
        self.setCentralWidget(root)
        root_l = QVBoxLayout(root)
        root_l.setContentsMargins(0, 0, 0, 0)
        root_l.setSpacing(0)

        # 顶端黑色栏（品牌，不含"+ 新增"，右侧仅窗口控制）
        top = QFrame(objectName="Top")
        top.setFixedHeight(48)
        top_l = QHBoxLayout(top)
        top_l.setContentsMargins(16, 6, 16, 6)
        top_l.setSpacing(12)
        # LOGO图片
        logo_label = QLabel()
        logo_label.setFixedSize(32, 32)
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")
        if os.path.exists(logo_path):
            logo_pixmap = QPixmap(logo_path)
            logo_label.setPixmap(logo_pixmap.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand = QLabel("Ghost Uncle AI - 鬼叔AI")
        brand.setObjectName("Brand")
        # 左侧：徽标 + 文案 + 新增
        left_top = QWidget()
        left_top_l = QHBoxLayout(left_top)
        left_top_l.setContentsMargins(0, 0, 0, 0)
        left_top_l.setSpacing(10)
        left_top_l.addWidget(logo_label)
        left_top_l.addWidget(brand)
        top_l.addWidget(left_top, stretch=0)
        
        top_l.addStretch(1)
        # 顶栏右侧功能按钮（设置 + 登录）
        right_tools = QWidget()
        rt_l = QHBoxLayout(right_tools)
        rt_l.setContentsMargins(0, 0, 0, 0)
        rt_l.setSpacing(12)
        # BUG 按钮：使用矢量图标并跳转到 Issues（放在设置左侧）
        # 黑色/深灰色图标适配白色顶栏
        svg_bug = (
            '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
            '<rect x="8" y="8" width="8" height="10" rx="4" fill="none" stroke="#444" stroke-width="2"/>'
            '<line x1="4" y1="12" x2="8" y2="12" stroke="#444" stroke-width="2"/>'
            '<line x1="16" y1="12" x2="20" y2="12" stroke="#444" stroke-width="2"/>'
            '<line x1="6" y1="6" x2="9" y2="9" stroke="#444" stroke-width="2"/>'
            '<line x1="18" y1="6" x2="15" y2="9" stroke="#444" stroke-width="2"/>'
            '<line x1="6" y1="20" x2="9" y2="17" stroke="#444" stroke-width="2"/>'
            '<line x1="18" y1="20" x2="15" y2="17" stroke="#444" stroke-width="2"/>'
            '</svg>'
        )
        # 在 BUG 左侧加入版本文字（与 Ghost OS AI 字体一致）
        self.lbl_version = QLabel("Version:0.6.0 26-1-18")
        self.lbl_version.setObjectName("TopVersion")
        rt_l.addWidget(self.lbl_version)
        
        self.btn_help = QToolButton()
        self.btn_help.setObjectName("TopBtn")
        self.btn_help.setFixedSize(32, 32)
        self.btn_help.setIcon(svg_icon(svg_bug, 18))
        self.btn_help.setIconSize(QSize(18, 18))
        self.btn_help.setToolTip("BUG")
        self.btn_help.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/guijiaosir/AItools/issues")))
        rt_l.addWidget(self.btn_help)
        # 设置按钮：点击弹出设置窗口
        self.btn_settings = QToolButton(text="⚙")
        self.btn_settings.setObjectName("TopBtn")
        self.btn_settings.setFixedSize(32, 32)
        self.btn_settings.clicked.connect(self._open_settings)
        rt_l.addWidget(self.btn_settings)
        # 登录按钮：SVG矢量图标
        svg_user = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="8" r="4" fill="none" stroke="#444" stroke-width="2"/><path d="M4 20c0-4 4-6 8-6s8 2 8 6" fill="none" stroke="#444" stroke-width="2"/></svg>'
        self.btn_login = QToolButton()
        self.btn_login.setObjectName("TopBtn")
        self.btn_login.setFixedSize(32, 32)
        self.btn_login.setIcon(svg_icon(svg_user, 18))
        self.btn_login.setIconSize(QSize(18, 18))
        self.btn_login.clicked.connect(self._open_login)
        rt_l.addWidget(self.btn_login)
        top_l.addWidget(right_tools)
        # 右侧仅保留窗口最小化/最大化/关闭
        self.btn_min = QToolButton(text="—")
        self.btn_min.setObjectName("WinCtl")
        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_max = QToolButton(text="▢")
        self.btn_max.setObjectName("WinCtl")
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close = QToolButton(text="×")
        self.btn_close.setObjectName("WinCtl")
        self.btn_close.clicked.connect(self.close)
        for b in [self.btn_min, self.btn_max, self.btn_close]:
            top_l.addWidget(b)
        # 允许拖拽移动窗口
        top.mousePressEvent = self._top_mouse_press
        top.mouseMoveEvent = self._top_mouse_move

        # 中心区域：左菜单栏 + 中间欢迎内容
        center = QFrame(objectName="Center")
        center_l = QHBoxLayout(center)
        center_l.setContentsMargins(0, 0, 0, 0)
        center_l.setSpacing(0)

        # 左侧菜单栏（白色矢量图标 + 文本）
        left = QFrame(objectName="Left")
        left.setFixedWidth(60 if self.sidebar_collapsed else 220)
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 8, 0, 8)
        left_l.setSpacing(0)
        self.left_panel = left

        # 左侧顶部：折叠按钮置于"创建"之上靠右
        left_header = QFrame(objectName="LeftHeader")
        lh_l = QHBoxLayout(left_header)
        lh_l.setContentsMargins(8, 4, 8, 4)
        lh_l.setSpacing(6)
        lh_l.addStretch(1)
        self.btn_fold = QToolButton(text="≫")
        self.btn_fold.setObjectName("FoldBtn")
        self.btn_fold.setFixedSize(28, 28)
        self.btn_fold.clicked.connect(self._toggle_sidebar)
        lh_l.addWidget(self.btn_fold)
        left_l.addWidget(left_header)

        # 简易线性深灰色图标（SVG 字符串）适配白色主题
        # Create: Image/Picture icon
        svg_folder = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="none" stroke="#5f6368" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>'
        # Video: Play Circle icon
        svg_wand = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="none" stroke="#5f6368" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polygon points="10 8 16 12 10 16 10 8"></polygon></svg>'
        # Agent: CPU/Chip icon
        svg_box = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="none" stroke="#5f6368" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect><rect x="9" y="9" width="6" height="6"></rect><line x1="9" y1="1" x2="9" y2="4"></line><line x1="15" y1="1" x2="15" y2="4"></line><line x1="9" y1="20" x2="9" y2="23"></line><line x1="15" y1="20" x2="15" y2="23"></line><line x1="20" y1="9" x2="23" y2="9"></line><line x1="20" y1="15" x2="23" y2="15"></line><line x1="1" y1="9" x2="4" y2="9"></line><line x1="1" y1="15" x2="4" y2="15"></line></svg>'
        # Connected: Zap icon
        self.svg_flash_raw = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="none" stroke="#5f6368" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>'
        svg_grid = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M3 3h8v8H3zM13 3h8v8h-8zM3 13h8v8H3zM13 13h8v8h-8z" fill="none" stroke="#5f6368" stroke-width="2"/></svg>'
        # About: Info icon
        svg_cube = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="none" stroke="#5f6368" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>'
        svg_gallery = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect x="3" y="4" width="18" height="14" rx="2" ry="2" fill="none" stroke="#5f6368" stroke-width="2"/><circle cx="8" cy="10" r="2" fill="none" stroke="#5f6368" stroke-width="2"/><path d="M5 16l5-4 4 3 5-5" fill="none" stroke="#5f6368" stroke-width="2"/></svg>'
        # Scene-split icon for 快速分镜
        svg_scene_split = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="none" stroke="#5f6368" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4v16M20 4v16M12 4v16M4 12h16"></path></svg>'
        # User icon for Sora2 Character Library
        svg_user = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="none" stroke="#5f6368" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>'

        # 先添加前六项菜单
        items_top = [
            ("创建", svg_folder),
            ("视频", svg_wand),
            ("灵动智能体", svg_box),
            ("sora2角色库", svg_user),
            ("快速分镜", svg_scene_split),
        ]
        custom_item = ("关于我们", svg_cube)
        self.menu_items = []
        for text, svg in items_top:
            item = MenuItem(text, svg, key=text)
            item.set_collapsed(self.sidebar_collapsed)
            item.installEventFilter(self)
            self.menu_items.append(item)
            left_l.addWidget(item)
            if text == "创建":
                item.set_selected(True)
        
        self.conn_panel = QFrame()
        conn_l = QHBoxLayout(self.conn_panel)
        if self.sidebar_collapsed:
            conn_l.setContentsMargins(0, 8, 0, 8)
            conn_l.setAlignment(Qt.AlignCenter)
        else:
            conn_l.setContentsMargins(12, 8, 12, 8)
            conn_l.setAlignment(Qt.AlignLeft)
        conn_l.setSpacing(10)
        conn_l.addWidget(svg_widget(self.svg_flash_raw, 16))
        self.conn_status = QLabel("已连接")
        self.conn_status.setObjectName("ConnStatus")
        conn_l.addWidget(self.conn_status)
        self.conn_status.setVisible(not self.sidebar_collapsed)
        
        left_l.addStretch(1)
        
        custom = MenuItem(*custom_item, key=custom_item[0])
        custom.set_collapsed(self.sidebar_collapsed)
        custom.installEventFilter(self)
        self.menu_items.append(custom)
        left_l.addWidget(custom)
        left_l.addWidget(self.conn_panel)

        # 中间欢迎文案 + 历史记录面板 (已移除历史记录)
        middle = QFrame(objectName="Middle")
        mid_l = QVBoxLayout(middle)
        mid_l.setContentsMargins(24, 40, 24, 24)
        mid_l.setSpacing(20)
        
        welcome = QLabel("欢迎使用 鬼叔AI，guest")
        welcome.setObjectName("Welcome")
        mid_l.addWidget(welcome, alignment=Qt.AlignLeft | Qt.AlignTop)
        
        # self.home_page = HomePage()
        # mid_l.addWidget(self.home_page, alignment=Qt.AlignLeft | Qt.AlignTop)
        mid_l.addStretch(1)

        center_l.addWidget(left)
        center_l.addWidget(middle)
        self.center_layout = center_l
        self.middle = middle
        # 悬停时临时展开左侧栏以显示文字
        self._hover_expand_active = False
        left.installEventFilter(self)

        root_l.addWidget(top)
        root_l.addWidget(center)

        self.setStyleSheet(self._style())
        
        self.photo_page = PhotoPage()
        self.video_page = VideoPage()
        self.fenjing_page = StoryboardPanel(self)
        self.sora_char_page = SoraCharacterPage(self)
        self.about_page = AboutPage()
        self.comics_page = GGGComicsPage() if GGGComicsPage else None
        
        # Heavy pages - initialized later in load_heavy_pages
        self.aiagent_page = None 
        self.lingdong_page = None
        
        try:
            self._apply_language_from_settings()
        except Exception:
            pass
        
        try:
            self._start_geo_detection()
        except Exception:
            self._is_cn_mainland = None

    def load_heavy_pages(self, progress_callback=None):
        """Initialize heavy pages with progress feedback"""
        # Load AIAgentPage（对话模式改为按需懒加载，这里不再预加载）
        
        # Load LingdongAgentPage
        if LingdongAgentPage:
            if progress_callback:
                progress_callback(70, "正在加载灵动工作台画布...")
            try:
                self.lingdong_page = LingdongAgentPage()
            except Exception as e:
                print(f"Error loading LingdongAgentPage: {e}")
                QMessageBox.critical(self, "错误", f"灵动工作台初始化失败:\n{str(e)}\n\n{traceback.format_exc()}")
        elif lingdong_import_error:
            QMessageBox.critical(self, "加载错误", f"灵动智能体模块无法加载:\n{lingdong_import_error}")
        
        if progress_callback:
            progress_callback(90, "准备就绪...")


    def closeEvent(self, event):
        """窗口关闭事件 - 保存数据"""
        try:
            if self.lingdong_page:
                self.lingdong_page.save_canvas_state()
        except Exception as e:
            print(f"Error saving canvas state: {e}")

        try:
            if hasattr(self, 'photo_page') and self.photo_page:
                self.photo_page._persist_prompt()
        except Exception as e:
            print(f"Error saving photo page prompt: {e}")

        event.accept()

    def _switch_center(self, widget: QWidget):
        """仅在右侧区域显示指定的 widget，确保不会同时加载其它页面。"""
        for w in [self.middle, self.photo_page, self.video_page, self.fenjing_page, self.sora_char_page, self.about_page, self.comics_page, self.aiagent_page, self.lingdong_page]:
            if w is None:
                continue
            # 如果是当前要显示的 widget，跳过移除操作（避免不必要的 reparent/reload）
            if w == widget:
                continue
                
            try:
                self.center_layout.removeWidget(w)
            except Exception:
                pass
            try:
                w.setParent(None)
            except Exception:
                pass
        
        if widget is not None:
            # 只有当 widget 不在 layout 中时才添加
            if self.center_layout.indexOf(widget) == -1:
                self.center_layout.addWidget(widget)
            widget.show()

    def _on_agent_open_comics(self, text: str):
        """接收 AI Agent 的请求，切换到 GGGComics 页面。"""
        try:
            if getattr(self, 'comics_page', None):
                self._switch_center(self.comics_page)
                if text:
                    try:
                        self.comics_page.show_code(text)
                    except Exception:
                        pass
            else:
                self._switch_center(self.middle)
        except Exception:
            pass

    def set_connection_text(self, text: str, kind: str = 'normal'):
        """更新左下角连接状态文本，用于显示生成过程的输出信息。"""
        try:
            self.conn_status.setText(text or "")
            color_map = {
                'normal': '#5f6368',
                'loading': '#f59e0b',
                'success': '#22c55e',
                'error': '#ef4444',
            }
            color = color_map.get(kind, '#5f6368')
            self.conn_status.setStyleSheet(f"color: {color};")
            
            # Update icon color
            icon_color_map = {
                'normal': '#5f6368',
                'loading': '#22c55e', # Green for working
                'success': '#22c55e', # Green
                'error': '#ef4444',   # Red
            }
            icon_color = icon_color_map.get(kind, '#5f6368')
            
            if hasattr(self, 'svg_flash_raw') and self.conn_panel and self.conn_panel.layout():
                # Replace stroke color
                new_svg = self.svg_flash_raw.replace('stroke="#5f6368"', f'stroke="{icon_color}"')
                
                # Get QSvgWidget from conn_panel layout (first item)
                layout = self.conn_panel.layout()
                if layout.count() > 0:
                    widget = layout.itemAt(0).widget()
                    if isinstance(widget, QSvgWidget):
                        widget.load(bytearray(new_svg, 'utf-8'))
                        
        except Exception as e:
            # print(f"Error updating connection status: {e}")
            pass

    def _open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            self.selected_image_api = getattr(dlg, 'selected_image_api', None)
            self.selected_video_api = getattr(dlg, 'selected_video_api', None)
            
            try:
                self._apply_language_from_settings()
            except Exception:
                pass

    def _open_login(self):
        QMessageBox.information(self, "登录", "登录入口待接入。")

    def _style(self):
        return """
        QMainWindow { background: #f8f9fa; }
        
        /* 顶部栏：纯白背景，底部微弱阴影 */
        #Top { 
            background: #ffffff; 
            border-bottom: 1px solid #f0f0f0;
        }
        
        #Brand { color: #202124; font-size: 18px; font-weight: 600; font-family: 'Segoe UI', sans-serif; letter-spacing: 0.5px; }
        #TopVersion { color: #5f6368; font-size: 12px; margin-right: 10px; background: #f1f3f4; padding: 4px 8px; border-radius: 6px; }
        
        #UpdateBanner { background: #E8F5E9; color: #1E8E3E; border: 1px solid #C8E6C9; border-radius: 16px; padding: 4px 12px; font-size: 13px; }
        #UpdateBanner:hover { background: #C8E6C9; }
        
        #Center { background: #f8f9fa; }
        
        /* 左侧菜单：纯白背景，右侧微弱边框 */
        #Left { 
            background: #ffffff; 
            border-right: 1px solid #f0f0f0;
        }
        
        #MenuItem { 
            background: transparent;
            color: #5f6368; 
            border-radius: 22px; 
            margin: 4px 12px; 
            padding-left: 0px;
            border: none;
        }
        #MenuItem:hover { 
            background: #f1f3f4; 
            color: #202124; 
        }
        #MenuItem[selected="true"] {
            background: #e8f5e9; 
            color: #1e8e3e;
        }
        #MenuItem[collapsed="true"] {
            margin: 4px 8px;
            padding-left: 0px;
            border-radius: 22px;
        }
        
        #MenuText { color: #5f6368; font-size: 14px; font-weight: 500; font-family: 'Segoe UI', sans-serif; }
        #MenuItem[selected="true"] #MenuText {
            color: #1e8e3e;
            font-weight: 600;
        }
        
        #Separator { background: #e0e0e0; }
        
        /* 中间内容区域：卡片式设计 */
        #Middle, #PhotoPage, #VideoPage, #AboutPage, #AIAgentPage, #LingdongAgentPage, #GGGComicsPage { 
            background: #ffffff; 
            border-radius: 16px;
            margin: 16px; 
            border: 1px solid #f0f0f0;
        }

        #VideoPage { margin-left: 0px; }
        
        #Welcome { color: #202124; font-size: 28px; font-weight: 400; margin-bottom: 24px; font-family: 'Segoe UI', sans-serif; }
        #ConnStatus { color: #4CAF50; font-size: 12px; font-weight: 500; }
        
        #HistoryContainer { background: white; border: 1px solid #e0e0e0; border-radius: 12px; }
        
        /* 顶部按钮 */
        #TopBtn { background: transparent; color: #5f6368; border: none; border-radius: 20px; font-size: 18px; }
        #TopBtn:hover { background: #f1f3f4; color: #202124; }
        
        #LeftHeader { border-bottom: none; }
        #FoldBtn { 
            background: transparent; 
            color: #5f6368; 
            border: none; 
            border-radius: 14px; 
        }
        #FoldBtn:hover { background: #f1f3f4; color: #202124; }
        
        /* 窗口控制按钮 */
        #WinCtl { background: transparent; color: #5f6368; border: none; font-size: 14px; width: 46px; height: 32px; border-radius: 0px; }
        #WinCtl:hover { background: #e0e0e0; color: #202124; }
        #WinCtl#btn_close:hover { background: #d93025; color: white; }
        """

    def _toggle_max(self):
        if not self._maximized:
            self.showMaximized()
        else:
            self.showNormal()
        self._maximized = not self._maximized

    def _top_mouse_press(self, event):
        if event.button() == Qt.LeftButton and not self._maximized:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _top_mouse_move(self, event):
        if self._drag_pos and not self._maximized and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def _toggle_sidebar(self):
        self.sidebar_collapsed = not self.sidebar_collapsed
        for item in getattr(self, 'menu_items', []):
            item.set_collapsed(self.sidebar_collapsed)
        # 清除悬停临时展开状态
        self._hover_expand_active = False
            
        # 同样处理连接状态文本的显示/隐藏
        if hasattr(self, 'conn_status'):
            self.conn_status.setVisible(not self.sidebar_collapsed)
            
        if hasattr(self, 'conn_panel'):
            if self.sidebar_collapsed:
                self.conn_panel.layout().setContentsMargins(0, 8, 0, 8)
                self.conn_panel.layout().setAlignment(Qt.AlignCenter)
            else:
                self.conn_panel.layout().setContentsMargins(12, 8, 12, 8)
                self.conn_panel.layout().setAlignment(Qt.AlignLeft)
            
        if self.sidebar_collapsed:
            self.left_panel.setFixedWidth(60)
            self.btn_fold.setText("≫")
            self.btn_fold.setToolTip("当前状态：已折叠")
            try:
                print("DEBUG: 侧栏切换 -> 已折叠")
            except Exception:
                pass
        else:
            self.left_panel.setFixedWidth(220)
            self.btn_fold.setText("≪")
            self.btn_fold.setToolTip("当前状态：已展开")
            try:
                print("DEBUG: 侧栏切换 -> 已展开")
            except Exception:
                pass

    def eventFilter(self, obj, event):
        if obj == self.btn_fold and event.type() == QEvent.Enter:
            state = "已折叠" if self.sidebar_collapsed else "已展开"
            print(f"DEBUG: 鼠标悬停在折叠按钮上 - 当前状态: {state}")
        return super().eventFilter(obj, event)

    def on_menu_clicked(self, text: str):
        try:
            print(f"DEBUG: Menu clicked: {text}")
            # 更新菜单选中状态
            for item in getattr(self, 'menu_items', []):
                item.set_selected(item._text == text)

            # 根据菜单切换工作区：创建 / 视频 / 关于我们 / 其它返回欢迎页
            if text == "创建":
                self._switch_center(self.photo_page)
                
                try:
                    self.photo_page.apply_default_ratio()
                except Exception:
                    pass
            elif text == "视频":
                self._switch_center(self.video_page)
            elif text == "灵动智能体":
                if self.lingdong_page:
                    self._switch_center(self.lingdong_page)
                else:
                    self._switch_center(self.middle)
            elif text == "sora2角色库":
                print("DEBUG: Switching to SoraCharacterPage")
                self._switch_center(self.sora_char_page)
            elif text == "快速分镜":
                self._switch_center(self.fenjing_page)
            elif text == "关于我们":
                try:
                    self._ensure_about_cn_if_mainland()
                except Exception:
                    pass
                self._switch_center(self.about_page)
            else:
                self._switch_center(self.middle)
        except Exception as e:
            print(f"ERROR in on_menu_clicked: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")

    def _apply_language_from_settings(self):
        from PySide6.QtCore import QSettings, QLocale
        s = QSettings("GhostOS", "App")
        raw = s.value("i18n/language", "")
        
        if not raw:
            lang_code = "en-US"
            s.setValue("i18n/language", lang_code)
        else:
            lang_code = str(raw)
            
            if lang_code not in ("zh-CN", "en-US"):
                lang_code = "en-US"
                s.setValue("i18n/language", lang_code)
        code = self._resolve_language_code(lang_code)
        self._set_language(code)

    def _resolve_language_code(self, lang_code: str) -> str:
        return lang_code if str(lang_code) in ("zh-CN", "en-US") else "en-US"

    def _set_language(self, code: str):
        zh = {
            "创建": "创建",
            "视频": "视频",
            "灵动智能体": "灵动智能体",
            "sora2角色库": "Sora2 角色库",
            "快速分镜": "快速分镜",
            "关于我们": "关于我们",
            "已连接": "已连接",
            "welcome": "欢迎使用 鬼叔AI，guest",
        }
        en = {
            "创建": "Create",
            "视频": "Video",
            "灵动智能体": "Smart Agent",
            "sora2角色库": "Sora2 Characters",
            "快速分镜": "Quick Storyboard",
            "关于我们": "About Us",
            "已连接": "Connected",
            "welcome": "Welcome to Ghost Uncle AI, guest",
        }
        dic = zh if code.startswith("zh") else en
        # 更新菜单显示文本
        for item in getattr(self, 'menu_items', []):
            key = getattr(item, '_text', '')
            if key in dic:
                item.set_display_text(dic[key])
        
        try:
            self.conn_status.setText(dic["已连接"])
        except Exception:
            pass
        
        try:
            # 中间第一个控件是欢迎语标签
            for i in range(self.middle.layout().count()):
                w = self.middle.layout().itemAt(i).widget()
                if isinstance(w, QLabel) and w.objectName() == "Welcome":
                    w.setText(dic["welcome"])
                    break
        except Exception:
            pass
        
        try:
            lang_code = 'zh' if code.startswith('zh') else 'en'
            if hasattr(self, 'photo_page') and self.photo_page:
                self.photo_page.set_language(lang_code)
            if hasattr(self, 'about_page') and self.about_page:
                self.about_page.set_language(lang_code)
            if hasattr(self, 'video_page') and self.video_page:
                self.video_page.set_language(lang_code)
            
            if hasattr(self, 'home_page') and self.home_page:
                self.home_page.set_language(lang_code)
        except Exception:
            pass

    def _start_geo_detection(self):
        """异步检测是否为中国大陆 IP。"""
        # 延迟 3 秒后再开始检测，避免启动时占用网络资源
        QTimer.singleShot(3000, self._delayed_geo_detection)

    def _delayed_geo_detection(self):
        try:
            self._is_cn_mainland = None
            t = threading.Thread(target=self._detect_cn_mainland, daemon=True)
            t.start()
        except Exception:
            self._is_cn_mainland = None

    def _detect_cn_mainland(self):
        try:
            import urllib.request, json
            endpoints = [
                ('http://ip-api.com/json/?fields=status,countryCode', lambda raw: isinstance(raw, dict) and raw.get('status') == 'success' and raw.get('countryCode') == 'CN'),
                ('https://ipapi.co/country/', lambda raw: isinstance(raw, str) and raw.strip() == 'CN'),
                ('https://ipinfo.io/json', lambda raw: isinstance(raw, dict) and raw.get('country') == 'CN'),
                ('http://pv.sohu.com/cityjson?ie=utf-8', lambda raw: isinstance(raw, str) and ('"cname":"中国"' in raw or '中国' in raw)),
            ]
            for url, check in endpoints:
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'GhostOS/1.0'})
                    with urllib.request.urlopen(req, timeout=1.5) as resp:
                        txt = resp.read().decode('utf-8', errors='ignore')
                    try:
                        data = json.loads(txt)
                    except Exception:
                        data = txt
                    if check(data):
                        self._is_cn_mainland = True
                        return
                except Exception:
                    pass
            self._is_cn_mainland = False
        except Exception:
            self._is_cn_mainland = None

    def _ensure_about_cn_if_mainland(self):
        """在点击"关于我们"时，若为中国大陆 IP，则强制中文页面与菜单项。"""
        is_cn = getattr(self, '_is_cn_mainland', None)
        # 若尚未有结果，同步快速检测一次（短超时，避免阻塞过久）
        if is_cn is None:
            try:
                self._detect_cn_mainland()
            except Exception:
                is_cn = False
            is_cn = getattr(self, '_is_cn_mainland', False)
        if is_cn:
            try:
                if hasattr(self, 'about_page'):
                    self.about_page.set_language('zh')
                
                for item in getattr(self, 'menu_items', []):
                    if getattr(item, '_text', '') == '关于我们':
                        item.set_display_text('关于我们')
                        break
            except Exception:
                pass




def _get_app_root():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


import traceback

def exception_hook(exctype, value, tb):
    """全局异常处理器 - 防止程序崩溃"""
    # 保存错误日志
    try:
        log_dir = os.path.join(_get_app_root(), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f'error_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"时间: {datetime.now()}\n")
            f.write("=" * 80 + "\n")
            traceback.print_exception(exctype, value, tb, file=f)
            f.write("=" * 80 + "\n")
    except Exception:
        pass

def setup_env_and_config():
    sys.excepthook = exception_hook
    try:
        from PySide6.QtCore import QSettings
        import os, json
        s = QSettings('GhostOS', 'App')
        cfg_dir = os.path.join(_get_app_root(), 'json')
        cfg_path = os.path.join(cfg_dir, 'language.json')
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            lang = str(data.get('code') or data.get('language') or '').strip() or 'en-US'
        else:
            lang = 'en-US'
            try:
                os.makedirs(cfg_dir, exist_ok=True)
                with open(cfg_path, 'w', encoding='utf-8') as f:
                    json.dump({'code': lang}, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
        
        try:
            s.setValue('i18n/language', lang)
        except Exception:
            pass
    except Exception:
        pass

def start_main_window_from_login(loading_window=None):
    if loading_window and hasattr(loading_window, 'update_progress_manual'):
        loading_window.update_progress_manual(10, "正在检查环境配置...")
        
    setup_env_and_config()
    
    if not ensure_terms_agreed(None):
        return None

    if loading_window and hasattr(loading_window, 'update_progress_manual'):
        loading_window.update_progress_manual(30, "正在初始化主界面...")

    # Create window but don't show yet
    win = MainWindow()
    
    # Perform heavy loading if loading window is provided
    if loading_window and hasattr(loading_window, 'update_progress_manual'):
        win.load_heavy_pages(loading_window.update_progress_manual)
    else:
        # Fallback for direct launch
        win.load_heavy_pages(None)
        
    win.showMaximized()
    
    # 默认跳转到创建页面
    try:
        # 模拟点击"创建"菜单，确保界面和状态的一致性
        # 这将自动切换到 PhotoPage 并执行相关的初始化（如应用默认比例）
        win.on_menu_clicked("创建")
    except Exception:
        # 如果模拟点击失败，尝试直接切换
        try:
            if hasattr(win, 'photo_page'):
                win._switch_center(win.photo_page)
        except Exception:
            pass

    def _save_lingdong():
        try:
            if hasattr(win, 'lingdong_page') and win.lingdong_page and hasattr(win.lingdong_page, 'canvas'):
                win.lingdong_page.canvas.save_canvas_state()
        except Exception:
            pass

    app = QApplication.instance()
    if app:
        try:
            app.aboutToQuit.connect(_save_lingdong)
        except Exception:
            pass
            
    return win

def main():
    import sys
    sys.excepthook = exception_hook
    app = QApplication(sys.argv)
    
    win = start_main_window_from_login()
    
    if not win:
        sys.exit(0)
        
    sys.exit(app.exec())


if __name__ == "__main__":
    print("Please run os.py instead of main.py")
    # Optional: You could also launch os.py via subprocess if desired, 
    # but a message is safer to avoid infinite loops or confusion.
    # For a GUI app, a message box is better.
    app = QApplication(sys.argv)
    QMessageBox.warning(None, "Warning", "Please run os.py to start the application.")
    sys.exit(0)
