from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QLineEdit, QPushButton, QSizePolicy, QFileDialog, QMenu, QSlider, QStyle, QMessageBox, QGraphicsDropShadowEffect, QComboBox, QToolButton, QListWidget, QTextEdit, QAbstractItemView, QListWidgetItem
)
from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap, QPainter, QPainterPath, QPen, QColor
from PySide6.QtCore import QSettings, QLocale
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
import json
import urllib.request
import urllib.error
import urllib.parse
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import threading
from video_history_utils import load_history, add_to_history, clear_history
import Hailuo02

class HistoryItemWidget(QWidget):
    def __init__(self, path, time, prompt, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)
        
        # Left: Icon + Info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        info_layout.setContentsMargins(0, 0, 0, 0)
        
        from pathlib import Path
        name = Path(path).name
        
        # Name
        self.name_label = QLabel(f"🎬 {name}")
        self.name_label.setStyleSheet("font-weight: bold; color: #333;")
        self.name_label.setToolTip(path)
        info_layout.addWidget(self.name_label)
        
        # Prompt
        if prompt:
            self.prompt_label = QLabel(prompt)
            self.prompt_label.setStyleSheet("color: #666; font-size: 11px;")
            self.prompt_label.setWordWrap(False)
            # Elide text if too long
            font_metrics = self.prompt_label.fontMetrics()
            elided_text = font_metrics.elidedText(prompt, Qt.ElideRight, 300) # Estimate width
            self.prompt_label.setText(elided_text)
            self.prompt_label.setToolTip(prompt)
            info_layout.addWidget(self.prompt_label)
        
        layout.addLayout(info_layout, stretch=1)
        
        # Right: Time
        self.time_label = QLabel(time)
        self.time_label.setStyleSheet("color: #888; font-size: 11px;")
        self.time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        layout.addWidget(self.time_label)

class HistoryPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: white; border-radius: 12px; border: 1px solid #e0e0e0;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Title
        title = QLabel("历史记录")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #333; border: none;")
        layout.addWidget(title)

        # List Widget
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget { border: none; background: transparent; }
            QListWidget::item { border-bottom: 1px solid #f0f0f0; }
            QListWidget::item:hover { background: #f5f5f5; }
            QListWidget::item:selected { background: #e3f2fd; }
        """)
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.setFocusPolicy(Qt.NoFocus)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.list_widget)
        
        self.refresh_history()

    def refresh_history(self):
        self.list_widget.clear()
        history = load_history()
        for item in history:
            path = item.get('path', '')
            time = item.get('time', '')
            prompt = item.get('prompt', '')
            
            # Create widget
            widget = HistoryItemWidget(path, time, prompt)
            
            # Create list item
            list_item = QListWidgetItem(self.list_widget)
            list_item.setSizeHint(widget.sizeHint())
            list_item.setData(Qt.UserRole, path)
            
            # Add to list
            self.list_widget.setItemWidget(list_item, widget)

    def add_record(self, path, prompt=""):
        add_to_history(path, prompt)
        self.refresh_history()
        
    def _on_item_double_clicked(self, item):
        path = item.data(Qt.UserRole)
        if path:
            try:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            except Exception:
                pass

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        action_clear = menu.addAction("清空历史记录")
        action_clear.triggered.connect(self._clear_history)
        menu.exec(self.list_widget.mapToGlobal(pos))

    def _clear_history(self):
        try:
            clear_history()
        except Exception:
            pass
        self.refresh_history()

class DebugPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: white; border-radius: 12px; border: 1px solid #e0e0e0;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Title
        title = QLabel("调试信息")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #333; border: none;")
        layout.addWidget(title)

        # Text Edit
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("""
            QTextEdit { border: none; background: #f8f9fa; font-family: Consolas, Monaco, monospace; font-size: 12px; color: #333; padding: 8px; border-radius: 6px; }
        """)
        layout.addWidget(self.text_edit)

    def log(self, message):
        self.text_edit.append(message)
        # Scroll to bottom
        sb = self.text_edit.verticalScrollBar()
        sb.setValue(sb.maximum())


class ImagePreview(QLabel):
    def __init__(self, text: str, border_color: str = '#E53935', parent=None):
        super().__init__(parent)
        self._pix = None
        self._label_text = text
        self._border_color = QColor(border_color)
        self.setAlignment(Qt.AlignCenter)
        self.setText(self._label_text)
        self.setAttribute(Qt.WA_Hover)
        self.setStyleSheet('QLabel{ background:#fafafa; border-radius:12px; color:#5f6368; font-size:20px; font-weight:700; padding:6px; }'
                           'QLabel:hover{ background:#f7f8f9; }')

    def set_pixmap(self, pix: QPixmap | None):
        self._pix = pix if isinstance(pix, QPixmap) and not pix.isNull() else None
        if self._pix:
            self.setText('')
        else:
            self.setText(self._label_text)
        self.update()

    def clear_pixmap(self):
        self._pix = None
        self.setText(self._label_text)
        self.update()

    def set_border_color(self, color_hex: str):
        self._border_color = QColor(color_hex)
        self.update()

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform, True)
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, 12, 12)
        painter.fillPath(path, QColor('#fafafa'))
        painter.setClipPath(path)
        if isinstance(self._pix, QPixmap):
            scaled = self._pix.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            sx = max(0, (scaled.width() - w) // 2)
            sy = max(0, (scaled.height() - h) // 2)
            painter.drawPixmap(0, 0, scaled, sx, sy, w, h)
        else:
            super().paintEvent(event)
        painter.setClipPath(QPainterPath())
        pen = QPen(self._border_color)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)


class VideoPage(QWidget):
    """
    AI影片页面：上方红色提示词输入区，下方蓝色视频生成区域。
    生成逻辑参考 web/video/video.html 的 VectorEngine Sora 与万象2.5。
    """
    
    # 定义信号用于线程安全的 UI 更新
    _status_signal = Signal(str, str)  # (message, kind)
    _video_url_signal = Signal(str)  # video_url
    _task_created_signal = Signal(dict)  # poll_info: {base, token, id, provider}
    _poll_result_signal = Signal(str, object)  # (provider, response_dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("VideoPage")
        self._setup_ui()
        # 语言：默认从设置读取，未设置则英文
        try:
            s = QSettings('GhostOS', 'App')
            lang_raw = str(s.value('i18n/language', 'en-US'))
            self._lang_code = 'zh' if lang_raw.startswith('zh') else 'en'
        except Exception:
            self._lang_code = 'en'
        self._i18n = self._get_i18n(self._lang_code)
        self._apply_language()
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(5000)
        self._poll_timer.timeout.connect(self._poll_once)
        self._current_poll = None  # dict: {base, token, id, provider}
        self._poll_busy = False
        # 选中的首帧/尾帧图片（Data URL base64）
        self._first_image_b64 = None
        self._last_image_b64 = None
        # 当前视频URL和本地路径（用于右键分镜）
        self._video_url = None
        self._current_local_path = None
        # 来自分镜的生成结果不进入左侧预览区
        self._suppress_left_preview_on_next_video = False
        
        # 连接信号到槽函数
        self._status_signal.connect(self._update_status)
        self._video_url_signal.connect(self._show_video_url)
        self._task_created_signal.connect(self._on_task_created)
        self._poll_result_signal.connect(self._on_poll_result)

    def _setup_ui(self):
        # 左侧为视频与提示词的列，右侧为分镜黄框区域
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 16, 16, 16)
        root.setSpacing(0)

        # 顶部：模型选择（参考图2）
        model_panel = QFrame(objectName='ModelPanel')
        model_panel.setStyleSheet(
            '#ModelPanel{ background:#ffffff; border:1px solid #e0e0e0; border-radius:12px; }'
        )
        mp_shadow = QGraphicsDropShadowEffect(model_panel)
        mp_shadow.setBlurRadius(12)
        mp_shadow.setOffset(0, 2)
        from PySide6.QtGui import QColor as _QColor
        mp_shadow.setColor(_QColor(0, 0, 0, 35))
        model_panel.setGraphicsEffect(mp_shadow)
        mp_l = QHBoxLayout(model_panel)
        mp_l.setContentsMargins(16, 12, 16, 12)
        mp_l.setSpacing(12)
        lbl_model = QLabel('选择模型')
        lbl_model.setStyleSheet('color:#3C4043; font-weight:600; padding-right:8px;')
        self.combo_model = QComboBox()
        self.combo_model.addItems(['Sora 2', '万象 2.5', '即梦 (Jimeng)'])
        self.combo_model.setFixedHeight(36)
        self.combo_model.setStyleSheet(
            'QComboBox{ background:#ffffff; color:#202124; border:1px solid #dadce0; border-radius:8px; padding:6px 10px; }'
            'QComboBox:hover{ border:1px solid #4CAF50; }'
            'QComboBox::drop-down{ border:none; }'
        )
        # 初始化与设置同步
        try:
            s = QSettings('GhostOS', 'App')
            raw = str(s.value('api/video_provider', 'Sora2') or 'Sora2').strip().lower()
            if 'sora' in raw:
                idx = 0
            elif 'jimeng' in raw or '即梦' in raw:
                idx = 2
            else:
                idx = 1
            self.combo_model.setCurrentIndex(idx)
        except Exception:
            pass
        def _on_model_changed(idx):
            try:
                s = QSettings('GhostOS', 'App')
                if idx == 0:
                    val = 'Sora2'
                elif idx == 1:
                    val = 'Wan25'
                else:
                    val = 'Jimeng'
                s.setValue('api/video_provider', val)
            except Exception:
                pass
        self.combo_model.currentIndexChanged.connect(_on_model_changed)
        mp_l.addWidget(lbl_model)
        mp_l.addWidget(self.combo_model, stretch=1)
        
        # 中部：提示词输入（红色框）
        prompt_panel = QFrame(objectName='PromptPanel')
        prompt_panel.setStyleSheet(
            '#PromptPanel{'
            ' background:#ffffff;'
            ' border:1px solid #e0e0e0;'
            ' border-radius:12px;'
            ' }'
        )
        # 卡片阴影（更轻更柔）
        pp_shadow = QGraphicsDropShadowEffect(prompt_panel)
        pp_shadow.setBlurRadius(14)
        pp_shadow.setOffset(0, 2)
        from PySide6.QtGui import QColor as _QColor
        pp_shadow.setColor(_QColor(0, 0, 0, 40))
        prompt_panel.setGraphicsEffect(pp_shadow)
        pp_l = QVBoxLayout(prompt_panel)
        pp_l.setContentsMargins(16, 12, 16, 12)
        pp_l.setSpacing(8)
        self.prompt_edit = QLineEdit()
        self.prompt_edit.setPlaceholderText('请输入您的提示词，使用英文。')
        self.prompt_edit.setStyleSheet(
            'QLineEdit{ background:#f8f9fa; color:#202124; border:1px solid #dadce0; border-radius:8px; padding:8px 12px; font-size:14px; }'
            'QLineEdit:focus{ border:1px solid #4CAF50; background:#ffffff; }'
            'QLineEdit::placeholder{ color:#5f6368; }'
        )
        self.prompt_edit.setFixedHeight(40)
        # 顶部行：提示词 + 生成按钮
        row_top = QHBoxLayout()
        row_top.setContentsMargins(0, 0, 0, 0)
        row_top.setSpacing(12)
        self.btn_generate = QPushButton('生成')
        self.btn_generate.setFixedWidth(96)
        self.btn_generate.setStyleSheet(
            'QPushButton{ height:40px; background:#4CAF50; color:#ffffff; border:none; border-radius:8px; font-weight:600; }'
            'QPushButton:hover{ background:#43A047; }'
        )
        try:
            self.btn_generate.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        except Exception:
            pass
        self.btn_generate.clicked.connect(self._on_generate_clicked)
        row_top.addWidget(self.prompt_edit, stretch=1)
        row_top.addWidget(self.btn_generate, stretch=0, alignment=Qt.AlignVCenter)
        quick_actions = QHBoxLayout()
        quick_actions.setContentsMargins(0, 0, 0, 0)
        quick_actions.setSpacing(8)
        def _mk_round_tool(text):
            b = QToolButton()
            b.setText(text)
            b.setFixedSize(36, 36)
            b.setStyleSheet('QToolButton{ background:#f1f3f4; color:#202124; border:none; border-radius:18px; } QToolButton:hover{ background:#e6f4ea; color:#1E8E3E; }')
            return b
        self.btn_mic = _mk_round_tool('🎤')
        self.btn_gallery = _mk_round_tool('🖼️')
        self.btn_template = _mk_round_tool('📋')
        self.btn_clear = _mk_round_tool('🧹')
        quick_actions.addWidget(self.btn_mic)
        quick_actions.addWidget(self.btn_gallery)
        quick_actions.addWidget(self.btn_template)
        quick_actions.addWidget(self.btn_clear)
        quick_actions.addStretch(1)
        self.btn_clear.clicked.connect(lambda: self.prompt_edit.clear())
        # 上传/预览行（放大红/蓝框，可点击选择）放到独立卡片
        upload_panel = QFrame(objectName='UploadPanel')
        upload_panel.setStyleSheet('#UploadPanel{ background:#ffffff; border:1px solid #e0e0e0; border-radius:12px; }')
        up_shadow = QGraphicsDropShadowEffect(upload_panel)
        up_shadow.setBlurRadius(12)
        up_shadow.setOffset(0, 2)
        up_shadow.setColor(_QColor(0, 0, 0, 35))
        upload_panel.setGraphicsEffect(up_shadow)
        up_l = QHBoxLayout(upload_panel)
        up_l.setContentsMargins(16, 12, 16, 12)
        up_l.setSpacing(16)
        # 预览标签（大尺寸红/蓝上传框）
        self.preview_first = ImagePreview('首帧图 ＋', border_color='#E53935')
        self.preview_last = ImagePreview('尾帧图 ＋', border_color='#4CAF50')
        self.preview_first.setFixedSize(160, 80)
        self.preview_last.setFixedSize(160, 80)
        self.preview_first.setAlignment(Qt.AlignCenter)
        self.preview_last.setAlignment(Qt.AlignCenter)
        self.preview_first.setStyleSheet('QLabel{ background:#fafafa; border-radius:12px; color:#5f6368; font-size:20px; font-weight:700; padding:6px; } QLabel:hover{ background:#f7f8f9; }')
        self.preview_last.setStyleSheet('QLabel{ background:#fafafa; border-radius:12px; color:#5f6368; font-size:20px; font-weight:700; padding:6px; } QLabel:hover{ background:#f7f8f9; }')
        # 点击上传 / 右键清空
        self.preview_first.setToolTip('左键上传首帧图 | 右键清空')
        self.preview_last.setToolTip('左键上传尾帧图 | 右键清空')
        self.preview_first.mousePressEvent = lambda e: self._handle_image_click(e, 'first')
        self.preview_last.mousePressEvent = lambda e: self._handle_image_click(e, 'last')
        # 启用右键菜单
        self.preview_first.setContextMenuPolicy(Qt.CustomContextMenu)
        self.preview_last.setContextMenuPolicy(Qt.CustomContextMenu)
        # 统一卡片尺寸与留白
        self.preview_first.setFixedSize(180, 90)
        self.preview_last.setFixedSize(180, 90)
        up_l.addWidget(self.preview_first)
        up_l.addWidget(self.preview_last)

        # 添加到面板（仅保留提示词+生成行）
        pp_l.addLayout(row_top)
        pp_l.addLayout(quick_actions)
        # 固定宽度，允许高度自适应，避免裁剪
        # prompt_panel.setFixedWidth(560)
        prompt_panel.setMinimumHeight(150)
        prompt_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # 下方：视频生成区域（蓝色框）
        result_panel = QFrame(objectName='ResultPanel')
        result_panel.setStyleSheet(
            '#ResultPanel{'
            ' background:#ffffff;'
            ' border:1px solid #e0e0e0;'
            ' border-radius:12px;'
            ' }'
        )
        # 卡片阴影（更轻更柔）
        rp_shadow = QGraphicsDropShadowEffect(result_panel)
        rp_shadow.setBlurRadius(14)
        rp_shadow.setOffset(0, 2)
        rp_shadow.setColor(_QColor(0, 0, 0, 40))
        result_panel.setGraphicsEffect(rp_shadow)
        rp_l = QVBoxLayout(result_panel)
        rp_l.setContentsMargins(12, 12, 12, 12)
        rp_l.setSpacing(10)
        self.status_label = QLabel('就绪')
        
        # 视频播放器组件
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet('background: #000000; border-radius: 8px;')
        self.video_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.video_widget.customContextMenuRequested.connect(self._show_video_context_menu)
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(1.0)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        # 循环播放开关：加载视频时开启，清空视频时关闭
        self._should_loop = False
        try:
            self.media_player.mediaStatusChanged.connect(self._on_media_status)
            self.media_player.errorOccurred.connect(self._on_media_error)
        except Exception:
            pass
        
        # 默认提示文本（视频加载前显示）
        self.video_placeholder = QLabel('创建任务后将在此显示视频预览')
        self.video_placeholder.setAlignment(Qt.AlignCenter)
        self.video_placeholder.setStyleSheet('color: #5f6368; font-size: 14px;')
        
        # 视频区域容器（可以切换显示占位符或视频播放器）
        self.video_container = QWidget()
        self.video_container.setStyleSheet('background:#ffffff; border-radius:8px;')
        video_container_layout = QVBoxLayout(self.video_container)
        video_container_layout.setContentsMargins(0, 0, 0, 0)
        video_container_layout.addWidget(self.video_placeholder)
        video_container_layout.addWidget(self.video_widget)
        self.video_widget.hide()  # 初始隐藏视频播放器

        # 中央播放控制覆盖层（位于视频区域中间）
        from PySide6.QtWidgets import QHBoxLayout as _QHBox
        self.center_controls = QWidget(self.video_container)
        cc_layout = _QHBox(self.center_controls)
        cc_layout.setContentsMargins(0, 0, 0, 0)
        cc_layout.setSpacing(8)
        # 播放/暂停按钮位于视频区域中间（初始禁用，加载视频后启用）
        self.btn_play = QPushButton('播放', self.center_controls)
        self.btn_play.setEnabled(False)
        self.btn_play.setStyleSheet('QPushButton{ height:32px; padding:0 16px; border-radius:18px; border:1px solid #dadce0; background:#ffffff; color:#202124; } QPushButton:hover{ background:#f1f3f4; }')
        self.btn_play.clicked.connect(self._play_video)
        try:
            self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        except Exception:
            pass
        self.btn_pause = QPushButton('暂停', self.center_controls)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setStyleSheet('QPushButton{ height:32px; padding:0 16px; border-radius:18px; border:1px solid #dadce0; background:#ffffff; color:#202124; } QPushButton:hover{ background:#f1f3f4; }')
        self.btn_pause.clicked.connect(self._pause_video)
        try:
            self.btn_pause.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        except Exception:
            pass
        cc_layout.addWidget(self.btn_play)
        cc_layout.addWidget(self.btn_pause)
        # 默认隐藏居中控件，改为使用底部按钮行的播放/暂停
        self.center_controls.hide()
        try:
            # 强制控件位于视频层之上
            self.center_controls.raise_()
            try:
                self.video_widget.stackUnder(self.center_controls)
            except Exception:
                pass
        except Exception:
            pass
        # 初始定位到中心
        try:
            self._position_overlay_center()
        except Exception:
            pass

        # 底部居中进度条覆盖层（初始隐藏，加载视频后显示）
        self.progress_slider = QSlider(Qt.Horizontal, self.video_container)
        self.progress_slider.setRange(0, 0)
        self.progress_slider.setStyleSheet('QSlider{ background: transparent; }QSlider::groove:horizontal{ height:6px; background:#e0e0e0; border-radius:3px; }QSlider::handle:horizontal{ background:#34A853; width:12px; margin:-4px 0; border-radius:6px; }QSlider::sub-page:horizontal{ background:#34A853; border-radius:3px; }')
        self.progress_slider.hide()
        try:
            self.progress_slider.raise_()
            try:
                self.video_widget.stackUnder(self.progress_slider)
            except Exception:
                pass
        except Exception:
            pass
        try:
            self.media_player.positionChanged.connect(self._on_position_changed)
            self.media_player.durationChanged.connect(self._on_duration_changed)
            self.progress_slider.sliderMoved.connect(lambda v: self.media_player.setPosition(int(v)))
        except Exception:
            pass
        
        # 底部按钮行：左侧播放/暂停，右侧上传/下载
        button_row = QHBoxLayout()
        button_row.setSpacing(12)
        
        # 底部播放/暂停按钮（与右侧按钮高度一致）
        self.btn_play_row = QPushButton('播放')
        self.btn_play_row.setEnabled(False)
        self.btn_play_row.setStyleSheet('QPushButton{ height:28px; padding:0 12px; border-radius:8px; border:1px solid #dadce0; background:#ffffff; color:#202124; } QPushButton:hover{ background:#f1f3f4; }')
        self.btn_play_row.clicked.connect(self._play_video)
        try:
            self.btn_play_row.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        except Exception:
            pass
        
        self.btn_pause_row = QPushButton('暂停')
        self.btn_pause_row.setEnabled(False)
        self.btn_pause_row.setStyleSheet('QPushButton{ height:28px; padding:0 12px; border-radius:8px; border:1px solid #dadce0; background:#ffffff; color:#202124; } QPushButton:hover{ background:#f1f3f4; }')
        self.btn_pause_row.clicked.connect(self._pause_video)
        try:
            self.btn_pause_row.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        except Exception:
            pass
        
        self.btn_upload = QPushButton('上传视频')
        self.btn_upload.setStyleSheet('QPushButton{ height:28px; padding:0 12px; border-radius:8px; border:1px solid #dadce0; background:#ffffff; color:#202124; } QPushButton:hover{ background:#f1f3f4; }')
        self.btn_upload.clicked.connect(self._upload_video)
        
        self.btn_open = QPushButton('下载视频')
        self.btn_open.setStyleSheet('QPushButton{ height:28px; padding:0 12px; border-radius:8px; border:1px solid #dadce0; background:#ffffff; color:#202124; } QPushButton:hover{ background:#f1f3f4; }')
        self.btn_open.setEnabled(False)
        self.btn_open.clicked.connect(self._open_video)
        try:
            self.btn_upload.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        except Exception:
            pass
        try:
            self.btn_open.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        except Exception:
            pass
        
        # 左右分组：左侧播放控制，右侧上传/下载
        button_row.addWidget(self.btn_play_row)
        button_row.addWidget(self.btn_pause_row)
        button_row.addStretch(1)
        button_row.addWidget(self.btn_upload)
        button_row.addWidget(self.btn_open)
        
        rp_l.addWidget(self.status_label)
        rp_l.addWidget(self.video_container, stretch=1)
        rp_l.addLayout(button_row)
        # 固定宽度，最小高度，自适应
        # result_panel.setFixedWidth(560)
        result_panel.setMinimumHeight(380)
        result_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        # 左上角列容器，精确控制间距，避免出现过大间隙
        column = QFrame()
        column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        col = QVBoxLayout(column)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)
        # 布局顺序：模型选择 → 上传首/尾帧 → 视频区域 → 提示词输入
        col.addWidget(model_panel)
        col.addWidget(upload_panel)
        col.addWidget(result_panel, stretch=1)
        col.addWidget(prompt_panel)
        root.addWidget(column, stretch=1)
        
        # 右侧信息栏（历史记录 + 调试信息）
        right_column = QWidget()
        right_column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        r_col_layout = QVBoxLayout(right_column)
        r_col_layout.setContentsMargins(0, 0, 0, 0)
        r_col_layout.setSpacing(12)

        self.history_panel = HistoryPanel()
        self.debug_panel = DebugPanel()

        # 历史记录占大部分高度 (stretch=3), 调试信息占小部分 (stretch=1)
        r_col_layout.addWidget(self.history_panel, stretch=3)
        r_col_layout.addWidget(self.debug_panel, stretch=1)

        root.addWidget(right_column, stretch=1)

    def log_message(self, msg: str):
        """记录日志到调试面板并打印"""
        print(msg, flush=True)
        if hasattr(self, 'debug_panel'):
            # 在主线程更新UI
            QTimer.singleShot(0, lambda: self.debug_panel.log(msg))

    def _update_status(self, text: str, kind: str = 'normal'):
        """更新状态文本（线程安全）"""
        self.status_label.setText(text)
        color = {'normal': '#5f6368', 'loading': '#f59e0b', 'success': '#34A853', 'error': '#d93025'}.get(kind, '#5f6368')
        self.status_label.setStyleSheet(f'color:{color};')
        # 同步到主窗口左下角"已连接"区域
        try:
            win = self.window()
            if win and hasattr(win, 'set_connection_text'):
                win.set_connection_text(text, kind)
        except Exception:
            pass

    def set_language(self, code: str):
        """设置语言代码（'zh' 或 'en'），更新视频页所有可见文本。"""
        if code not in ('zh', 'en'):
            code = 'en'
        self._lang_code = code
        self._i18n = self._get_i18n(code)
        self._apply_language()

    def _get_i18n(self, code: str) -> dict:
        zh = {
            'prompt_placeholder': '请输入您的提示词，使用英文。',
            'generate': '生成',
            'first_label': '首帧图 ＋',
            'last_label': '尾帧图 ＋',
            'first_tip': '左键上传首帧图 | 右键清空',
            'last_tip': '左键上传尾帧图 | 右键清空',
            'ready': '就绪',
            'video_placeholder': '创建任务后将在此显示视频预览',
            'upload_video': '上传视频',
            'play': '播放',
            'pause': '暂停',
            'open_in_browser': '下载视频',
            'task_created': '任务创建成功，开始轮询进度… (ID: {id})',
            'gen_success': '生成成功 ✓',
            'task_failed_prefix': '任务失败',
            'generating_pct': '生成中... {pct}%',
            'generating_state': '生成中... ({state})',
            'use_wan': '使用 万象2.5 API 生成…',
            'use_sora': '使用 Sora2 API 生成…',
            'creating_task': '创建视频任务中...',
            'connecting_api': '正在连接API...',
            'connecting_wan_api': '正在连接万象2.5 API...',
            'query_failed_prefix': '查询失败：',
            'no_url_notice': '生成成功但未返回视频URL',
            'open_in_browser_notice': '视频加载失败，请点击下方按钮在浏览器中打开',
            'pick_image_title': '选择图片',
            'pick_video_title': '选择视频文件',
            'tooltip_clear_suffix': ' | 右键清空',
            'cleared_first': '已清空首帧图片',
            'cleared_last': '已清空尾帧图片',
            'picked_first': '已选择首帧图片',
            'picked_last': '已选择尾帧图片',
            'pick_image_failed_prefix': '图片选择失败：',
            'sora_base_required': '请在设置里填写 Sora2 Base URL',
            'sora_key_required': '请在设置里填写 Sora2 API Key',
            'wan_base_required': '请在设置里填写 万象2.5 Base URL',
            'wan_key_required': '请在设置里填写 万象2.5 API Key',
            'loaded_local_video_prefix': '已加载本地视频: ',
            'video_load_failed_prefix': '视频加载失败: ',
            'menu_clear_video': '清空视频',
            'menu_generate_frames': '自动分镜',
            'cleared_video': '已清空视频',
            'create_failed_prefix': '创建失败: ',
            'http_error_prefix': 'HTTP错误: ',
            'network_error_prefix': '网络错误: ',
            'url_error_prefix': 'URL错误: ',
            'exception_prefix': '异常: ',
            'direct_url_success': '生成成功（直出URL）',
        }
        en = {
            'prompt_placeholder': 'Enter a prompt',
            'generate': 'Generate',
            'first_label': 'First Frame +',
            'last_label': 'Last Frame +',
            'first_tip': 'Left click to upload first frame | Right click to clear',
            'last_tip': 'Left click to upload last frame | Right click to clear',
            'ready': 'Ready',
            'video_placeholder': 'Video preview will appear here after task is created',
            'upload_video': 'Upload Video',
            'play': 'Play',
            'pause': 'Pause',
            'open_in_browser': 'Download Video',
            'task_created': 'Task created, start polling… (ID: {id})',
            'gen_success': 'Generated ✓',
            'task_failed_prefix': 'Task failed',
            'generating_pct': 'Generating... {pct}%',
            'generating_state': 'Generating... ({state})',
            'use_wan': 'Generating via WanXiang 2.5 API…',
            'use_sora': 'Generating via Sora2 API…',
            'creating_task': 'Creating video task...',
            'connecting_api': 'Connecting to API...',
            'connecting_wan_api': 'Connecting to WanXiang 2.5 API...',
            'query_failed_prefix': 'Query failed: ',
            'no_url_notice': 'Generated successfully but no video URL returned',
            'open_in_browser_notice': 'Video failed to load. Click below to open in browser',
            'pick_image_title': 'Select Image',
            'pick_video_title': 'Select Video File',
            'tooltip_clear_suffix': ' | Right click to clear',
            'cleared_first': 'First frame image cleared',
            'cleared_last': 'Last frame image cleared',
            'picked_first': 'First frame image selected',
            'picked_last': 'Last frame image selected',
            'pick_image_failed_prefix': 'Image selection failed: ',
            'sora_base_required': 'Please set Sora2 Base URL in Settings',
            'sora_key_required': 'Please set Sora2 API Key in Settings',
            'wan_base_required': 'Please set WanXiang 2.5 Base URL in Settings',
            'wan_key_required': 'Please set WanXiang 2.5 API Key in Settings',
            'loaded_local_video_prefix': 'Loaded local video: ',
            'video_load_failed_prefix': 'Video load failed: ',
            'menu_clear_video': 'Clear Video',
            'menu_generate_frames': 'Generate Storyboard',
            'cleared_video': 'Video cleared',
            'create_failed_prefix': 'Create failed: ',
            'http_error_prefix': 'HTTP Error: ',
            'network_error_prefix': 'Network Error: ',
            'url_error_prefix': 'URL Error: ',
            'exception_prefix': 'Exception: ',
            'direct_url_success': 'Generated successfully (direct URL)',
        }
        return zh if code == 'zh' else en

    def _apply_language(self):
        # 顶部输入与按钮
        self.prompt_edit.setPlaceholderText(self._i18n['prompt_placeholder'])
        self.btn_generate.setText(self._i18n['generate'])
        # 上传预览框与提示
        self.preview_first.setText(self._i18n['first_label'])
        self.preview_last.setText(self._i18n['last_label'])
        self.preview_first.setToolTip(self._i18n['first_tip'])
        self.preview_last.setToolTip(self._i18n['last_tip'])
        # 状态与占位、按钮
        self.status_label.setText(self._i18n['ready'])
        self.video_placeholder.setText(self._i18n['video_placeholder'])
        self.btn_upload.setText(self._i18n['upload_video'])
        # 播放控制按钮文案（居中覆盖层）
        if hasattr(self, 'btn_play'):
            self.btn_play.setText(self._i18n['play'])
        if hasattr(self, 'btn_pause'):
            self.btn_pause.setText(self._i18n['pause'])
        # 底部播放控制按钮文案
        if hasattr(self, 'btn_play_row'):
            self.btn_play_row.setText(self._i18n['play'])
        if hasattr(self, 'btn_pause_row'):
            self.btn_pause_row.setText(self._i18n['pause'])
        self.btn_open.setText(self._i18n['open_in_browser'])

    def _position_overlay_center(self):
        """将中心播放控件定位在视频容器正中"""
        try:
            p = self.video_container
            if not p or not hasattr(self, 'center_controls'):
                return
            w = self.center_controls.sizeHint().width()
            h = self.center_controls.sizeHint().height()
            x = max(0, (p.width() - w) // 2)
            y = max(0, (p.height() - h) // 2)
            self.center_controls.move(x, y)
            try:
                self.center_controls.raise_()
            except Exception:
                pass
        except Exception:
            pass

    def _position_progress_overlay(self):
        """将进度条定位在视频容器底部居中"""
        try:
            p = self.video_container
            s = getattr(self, 'progress_slider', None)
            if not p or not s:
                return
            width = max(200, int(p.width() * 0.7))
            s.resize(width, 18)
            x = max(0, (p.width() - width) // 2)
            y = max(0, p.height() - s.height() - 12)
            s.move(x, y)
            try:
                s.raise_()
            except Exception:
                pass
        except Exception:
            pass

    def resizeEvent(self, event):
        try:
            super().resizeEvent(event)
        except Exception:
            pass
        try:
            self._position_overlay_center()
        except Exception:
            pass
        try:
            self._position_progress_overlay()
        except Exception:
            pass
    
    def _on_task_created(self, poll_info: dict):
        """任务创建成功的回调（在主线程中执行）"""
        task_id = poll_info.get('id', '')
        self._current_poll = poll_info
        self._update_status(self._i18n['task_created'].format(id=task_id), 'success')
        self._poll_timer.start()
    
    def _on_poll_result(self, provider: str, response: object):
        """轮询结果的回调（在主线程中执行）"""
        if provider == 'sora2':
            self._handle_sora2_poll(response)
        elif provider == 'wan25':
            self._handle_wan25_poll(response)
        elif provider == 'jimeng':
            self._handle_jimeng_poll(response)
        elif provider == 'hailuo02':
            self._handle_hailuo02_poll(response)

    def _debug(self, text: str):
        """统一调试输出到控制台并同步到左下角状态。"""
        try:
            print('[DEBUG]', text, flush=True)
        except Exception:
            pass
    
    def _handle_sora2_poll(self, j: dict):
        """处理 Sora2 轮询结果"""
        if not j:
            return
        status = str(j.get('status') or j.get('data', {}).get('status') or j.get('state') or 'pending').lower()
        
        # 修复：正确处理 progress 为 0 的情况，并尝试多种字段获取进度
        prog = j.get('progress')
        if prog is None:
            # 尝试从 data 字段获取
            data_obj = j.get('data')
            if isinstance(data_obj, dict):
                prog = data_obj.get('progress')
        
        if prog is None:
            # 尝试其他常见字段
            prog = j.get('percentage') or j.get('percent')
        
        # 只在进度变化时打印日志，减少冗余输出
        if not hasattr(self, '_last_progress') or self._last_progress != prog:
            self._last_progress = prog
            try:
                self._debug(f"poll(sora2): status={status} progress={prog if prog is not None else 'n/a'}")
            except Exception:
                pass
        
        succ = {'succeeded','success','finished','completed','done'}
        fail = {'failed','error','cancelled','canceled'}
        
        if status in succ:
            self._poll_timer.stop()
            p = self._current_poll
            url = self._extract_video_url(j) or p['base'] + '/v1/video/content?id=' + urllib.parse.quote(p['id'])
            
            # 来自分镜重组时不在左侧预览区播放
            if not self._suppress_left_preview_on_next_video:
                self._show_video_url(url)
            self._suppress_left_preview_on_next_video = False
            
            self._update_status('生成完成', 'success')
            self.log_message(f'[VIDEO] 生成完成！视频URL: {url}')
            # 添加到历史记录
            prompt = self._current_poll.get('prompt', '') if self._current_poll else ''
            self._add_to_history(url, prompt)
        elif status in fail:
            self._poll_timer.stop()
            error_msg = j.get('error') or j.get('message') or self._i18n['task_failed_prefix']
            self._update_status(f"{self._i18n['task_failed_prefix']}: {error_msg}", 'error')
            self.log_message(f'[VIDEO] 任务失败: {error_msg}')
        else:
            # 显示进度百分比
            if prog is not None:
                self._update_status(self._i18n['generating_pct'].format(pct=prog), 'loading')
            else:
                self._update_status(self._i18n['generating_state'].format(state=status), 'loading')
    
    def _handle_wan25_poll(self, result: dict):
        """处理万象2.5轮询结果"""
        if not result:
            return
        
        status_raw = result.get('status', 'pending')
        url_out = result.get('url', None)
        
        succ = {'succeeded','success','finished','completed','done'}
        fail = {'failed','error','cancelled','canceled'}
        
        if status_raw in succ:
            self._poll_timer.stop()
            try:
                self._video_url_signal.emit(url_out)
            except Exception:
                pass
            if not self._suppress_left_preview_on_next_video:
                self._show_video_url(url_out)
            self._suppress_left_preview_on_next_video = False
            # 任务完成
            self._update_status('已完成', 'success')
            self.log_message(f'[VIDEO] 万象2.5生成完成！视频URL: {url_out}')
            # 添加到历史记录
            prompt = self._current_poll.get('prompt', '') if self._current_poll else ''
            self._add_to_history(url_out, prompt)
        elif status_raw in fail:
            self._poll_timer.stop()
            error_msg = result.get('error') or self._i18n['task_failed_prefix']
            self._update_status(f"{self._i18n['task_failed_prefix']}: {error_msg}", 'error')
            self.log_message(f'[VIDEO] 万象2.5任务失败: {error_msg}')
        else:
            self._update_status(self._i18n['generating_state'].format(state=status_raw), 'loading')

    def _handle_jimeng_poll(self, result: dict):
        """处理即梦轮询结果"""
        if not result:
            return
        
        status_raw = result.get('status', 'pending')
        url_out = result.get('url', None)
        
        succ = {'succeeded','success','finished','completed','done'}
        fail = {'failed','error','cancelled','canceled'}
        
        if status_raw in succ:
            self._poll_timer.stop()
            try:
                self._video_url_signal.emit(url_out)
            except Exception:
                pass
            if not self._suppress_left_preview_on_next_video:
                self._show_video_url(url_out)
            self._suppress_left_preview_on_next_video = False
            # 任务完成
            self._update_status('已完成', 'success')
            self.log_message(f'[VIDEO] 即梦生成完成！视频URL: {url_out}')
            # 添加到历史记录
            prompt = self._current_poll.get('prompt', '') if self._current_poll else ''
            self._add_to_history(url_out, prompt)
        elif status_raw in fail:
            self._poll_timer.stop()
            error_msg = result.get('error') or self._i18n['task_failed_prefix']
            self._update_status(f"{self._i18n['task_failed_prefix']}: {error_msg}", 'error')
            self.log_message(f'[VIDEO] 即梦任务失败: {error_msg}')
        else:
            self._update_status(self._i18n['generating_state'].format(state=status_raw), 'loading')

    def _normalize_base(self, base: str) -> str:
        """清理 Base URL：去掉首尾空格、尾部斜杠与逗号，并移除末尾 /v1。"""
        b = (base or '').strip()
        # 依次移除常见的尾随符号
        while b.endswith('/') or b.endswith(',') or b.endswith('；') or b.endswith('，'):
            b = b[:-1]
        # 规范化：若以 /v1 结尾则移除，避免后续路径出现 /v1/alibailian/... 等重复前缀
        try:
            if b.lower().endswith('/v1'):
                b = b[: b.lower().rfind('/v1')]
                # 再次去掉尾随符号
                while b.endswith('/') or b.endswith(',') or b.endswith('；') or b.endswith('，'):
                    b = b[:-1]
        except Exception:
            pass
        return b
        try:
            win = self.window()
            if win and hasattr(win, 'set_connection_text'):
                win.set_connection_text(text, 'normal')
        except Exception:
            pass

    # 仅依据系统语言判定是否为简体中文环境（zh-CN/zh-Hans）
    def _is_china_region(self) -> bool:
        try:
            # Qt 系统语言
            qloc = QLocale.system()
            q_name = str(qloc.name()).strip().lower()  # 例如 zh_cn
            try:
                q_uilangs = [str(x).strip().lower().replace('-', '_') for x in qloc.uiLanguages()]
            except Exception:
                q_uilangs = []
            if q_name.startswith('zh_cn') or any(('zh_hans' in x) or ('zh_cn' in x) for x in q_uilangs):
                return True
            # Python locale 作为回退
            import locale
            loc = locale.getdefaultlocale()
            if loc and isinstance(loc, tuple):
                loc0 = str(loc[0] or '').strip().lower().replace('-', '_')
                if loc0 in ('zh_cn', 'zh_hans') or loc0.startswith('zh_cn'):
                    return True
        except Exception:
            pass
        return False

    # 移除文件级水印处理逻辑

    def _resolve_provider(self) -> str:
        """根据设置面板选择返回标准化的提供商标识：'sora2', 'wan25' 或 'jimeng'。"""
        s = QSettings('GhostOS', 'App')
        raw = str(s.value('api/video_provider', 'Sora2') or 'Sora2').strip().lower()
        # 统一映射，兼容多种写法
        if any(x in raw for x in ['wan', '万象', 'alibaba', 'wan2.5']):
            return 'wan25'
        if any(x in raw for x in ['jimeng', '即梦']):
            return 'jimeng'
        if any(x in raw for x in ['hailuo', '海螺']):
            return 'hailuo02'
        return 'sora2'

    def _on_generate_clicked(self):
        prompt = (self.prompt_edit.text() or '').strip() or 'make animate'
        provider = self._resolve_provider()
        try:
            self._debug(f"video: provider={provider}, prompt_len={len(prompt)}")
        except Exception:
            pass
        # 根据设置面板选择自动调用对应API，并在状态栏附带 IP
        if provider == 'wan25':
            self._update_status(f"{self._i18n['use_wan']}", 'loading')
            self._generate_wan25(prompt)
        elif provider == 'jimeng':
            self._update_status(f"Using Jimeng Video", 'loading')
            self._generate_jimeng(prompt)
        elif provider == 'hailuo02':
            self._update_status(f"Using Hailuo02 Video", 'loading')
            self._generate_hailuo02(prompt)
        else:
            self._update_status(f"{self._i18n['use_sora']}", 'loading')
            self._generate_sora2(prompt)

    def _handle_image_click(self, event, which: str):
        """处理图片预览框的点击事件：左键上传，右键清空"""
        if event.button() == Qt.LeftButton:
            self._pick_image(which)
        elif event.button() == Qt.RightButton:
            self._clear_image(which)
    
    def _clear_image(self, which: str):
        """清空选中的图片"""
        if which == 'first':
            self._first_image_b64 = None
            self.preview_first.clear_pixmap()
            self.preview_first.setToolTip(self._i18n['first_tip'])
            self._update_status(self._i18n['cleared_first'], 'normal')
        else:
            self._last_image_b64 = None
            self.preview_last.clear_pixmap()
            self.preview_last.setToolTip(self._i18n['last_tip'])
            self._update_status(self._i18n['cleared_last'], 'normal')

    def _pick_image(self, which: str):
        # 选择图片并存储为 Data URL base64
        path, _ = QFileDialog.getOpenFileName(self, self._i18n['pick_image_title'], '', 'Images (*.png *.jpg *.jpeg *.webp)')
        if not path:
            return
        try:
            import base64, os
            with open(path, 'rb') as f:
                data = f.read()
            ext = os.path.splitext(path)[1].lower()
            mime = 'image/png'
            if ext in ('.jpg', '.jpeg'):
                mime = 'image/jpeg'
            elif ext == '.webp':
                mime = 'image/webp'
            b64 = base64.b64encode(data).decode('utf-8')
            data_url = f'data:{mime};base64,{b64}'
            # 设置预览
            pix = QPixmap()
            pix.loadFromData(data)
            if which == 'first':
                self._first_image_b64 = data_url
                if not pix.isNull():
                    self.preview_first.set_pixmap(pix)
                    self.preview_first.setToolTip(f"{os.path.basename(path)}{self._i18n['tooltip_clear_suffix']}")
                self._update_status(self._i18n['picked_first'], 'success')
            else:
                self._last_image_b64 = data_url
                if not pix.isNull():
                    self.preview_last.set_pixmap(pix)
                    self.preview_last.setToolTip(f"{os.path.basename(path)}{self._i18n['tooltip_clear_suffix']}")
                self._update_status(self._i18n['picked_last'], 'success')
        except Exception as e:
            self._update_status(self._i18n['pick_image_failed_prefix'] + str(e), 'error')

    # --- Sora2 ---
    def _generate_sora2(self, prompt: str):
        # 优先从json/sora2.json读取配置
        try:
            from Asora2 import load_config
            config = load_config()
            base = self._normalize_base(config.get('base_url', 'https://api.vectorengine.ai') or '')
            token = (config.get('api_key', '') or '').strip()
            model = str(config.get('model', 'sora-2') or 'sora-2')
            orientation = str(config.get('orientation', 'landscape') or 'landscape')
            size_val = str(config.get('size', 'large') or 'large')
            duration_raw = config.get('duration', '15')
            try:
                duration = int(str(duration_raw))
                if duration not in (15, 25):
                    duration = 15
            except Exception:
                duration = 15
            watermark_raw = str(config.get('watermark', 'false') or 'false').lower()
            watermark = (watermark_raw in ('true','1','yes'))
            width_val = str(config.get('width', '') or '').strip()
            height_val = str(config.get('height', '') or '').strip()
            print(f'[Sora2] 从json/sora2.json读取配置: model={model}, orientation={orientation}, size={size_val}', flush=True)
        except Exception as e:
            # 如果读取JSON失败，回退到QSettings
            print(f'[Sora2] 从json读取配置失败，使用QSettings: {e}', flush=True)
            s = QSettings('GhostOS', 'App')
            base = self._normalize_base(s.value('providers/sora2/base_url', 'https://api.vectorengine.ai') or '')
            token = (s.value('providers/sora2/api_key', '') or '').strip()
            model = str(s.value('providers/sora2/model', 'sora-2') or 'sora-2')
            orientation = str(s.value('providers/sora2/orientation', 'landscape') or 'landscape')
            size_val = str(s.value('providers/sora2/size', 'large') or 'large')
            duration_raw = s.value('providers/sora2/duration', '15')
            try:
                duration = int(str(duration_raw))
                if duration not in (15, 25):
                    duration = 15
            except Exception:
                duration = 15
            watermark_raw = str(s.value('providers/sora2/watermark', 'true') or 'true').lower()
            watermark = (watermark_raw in ('true','1','yes'))
            width_val = str(s.value('providers/sora2/width', '') or '').strip()
            height_val = str(s.value('providers/sora2/height', '') or '').strip()
        if not base:
            self._update_status(self._i18n['sora_base_required'], 'error'); return
        if not token:
            self._update_status(self._i18n['sora_key_required'], 'error'); return
        payload = {
            'model': model,
            'orientation': orientation,
            'duration': duration,
            # 与 web/video/video.html 保持一致：watermark 为布尔值
            'watermark': watermark,
            'prompt': prompt,
        }
        # 注入首/尾帧图片（按顺序）
        imgs = []
        if self._first_image_b64:
            imgs.append(self._first_image_b64)
            print(f'[VIDEO] 添加首帧图，大小: {len(self._first_image_b64)} 字符', flush=True)
        if self._last_image_b64:
            imgs.append(self._last_image_b64)
            print(f'[VIDEO] 添加尾帧图，大小: {len(self._last_image_b64)} 字符', flush=True)
        
        if imgs:
            # 根据API文档，SORA-2的images参数支持：
            # 1. HTTPS URL（推荐）
            # 2. Data URI格式：data:image/png;base64,... （完整格式，包含前缀）
            # 注意：API文档明确说明Base64方案使用完整Data URI，不是纯Base64
            payload['images'] = imgs  # 直接使用Data URI格式
            print(f'[VIDEO] 总共发送 {len(imgs)} 张参考图', flush=True)
            print(f'[VIDEO] 参考图格式: Data URI (data:image/...;base64,...)', flush=True)
            print(f'[VIDEO] ⚠️ 注意：', flush=True)
            print(f'[VIDEO]   1. 确保使用 model="sora-2" (仅此模型支持图生视频)', flush=True)
            print(f'[VIDEO]   2. Base64图片可能影响性能，建议使用公开HTTPS URL', flush=True)
            print(f'[VIDEO]   3. 图片会按顺序作为关键帧驱动视频生成', flush=True)
        if size_val == 'custom':
            try:
                w = int(width_val); h = int(height_val)
                # 合理范围校验
                if not (256 <= w <= 3840 and 256 <= h <= 3840):
                    raise ValueError('invalid size')
                payload['width'] = w; payload['height'] = h
            except Exception:
                # 回退到 large
                payload['size'] = 'large'
        else:
            payload['size'] = size_val
        url = base + '/v1/video/create'
        self._update_status(self._i18n['creating_task'], 'loading')
        def worker():
            try:
                try:
                    imgs_cnt = len(payload.get('images', []))
                    wm = 'true' if payload.get('watermark') else 'false'
                    # 打印完整payload结构（隐藏base64数据）
                    payload_debug = payload.copy()
                    if 'images' in payload_debug and payload_debug['images']:
                        payload_debug['images'] = [f"<base64_data_{i+1}_len={len(img)}>" for i, img in enumerate(payload_debug['images'])]
                    print(f'[VIDEO] 完整请求payload: {json.dumps(payload_debug, ensure_ascii=False)}', flush=True)
                    self._debug(f"create(sora2): url={url} | model={model} | orientation={orientation} | size={payload.get('size') or (str(payload.get('width'))+'x'+str(payload.get('height'))) } | duration={duration} | watermark={wm} | prompt_len={len(prompt)} | images={imgs_cnt}")
                except Exception as e:
                    print(f'[VIDEO] 调试信息生成失败: {e}', flush=True)
                
                print(f'[VIDEO] 正在发送请求到: {url}', flush=True)
                self._status_signal.emit(self._i18n['connecting_api'], 'loading')
                
                req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                             headers={'Content-Type': 'application/json', 'Accept': 'application/json', 'Authorization': 'Bearer ' + token},
                                             method='POST')
                
                print(f'[VIDEO] 等待服务器响应...', flush=True)
                with urllib.request.urlopen(req, timeout=120) as r:
                    print(f'[VIDEO] 收到响应，状态码: {r.status}', flush=True)
                    txt = r.read().decode('utf-8')
                    print(f'[VIDEO] 响应长度: {len(txt)} 字节', flush=True)
                
                try:
                    resp = json.loads(txt)
                except Exception as parse_err:
                    print(f'[VIDEO] JSON解析失败: {parse_err}', flush=True)
                    print(f'[VIDEO] 原始响应: {txt[:1000]}', flush=True)
                    resp = {'raw': txt}
                
                try:
                    self._debug('create(sora2): resp=' + (txt[:500] + ('...' if len(txt) > 500 else '')))
                    # 检查响应中是否有关于图片的信息
                    if 'image' in txt.lower() or 'picture' in txt.lower():
                        print(f'[VIDEO] ⚠️ API响应中包含图片相关信息，请查看上方响应', flush=True)
                except Exception:
                    pass
                
                task_id = resp.get('id') or resp.get('task_id')
                print(f'[VIDEO] 提取任务ID: {task_id}', flush=True)
                
                # 检查API是否返回了关于参考图的警告
                if resp.get('warning') or resp.get('warnings'):
                    warnings = resp.get('warning') or resp.get('warnings')
                    print(f'[VIDEO] ⚠️ API警告: {warnings}', flush=True)
                
                if not task_id:
                    error_msg = resp.get('error') or resp.get('message') or '未获取到任务ID'
                    print(f'[VIDEO] 错误: {error_msg}', flush=True)
                    print(f'[VIDEO] 完整响应: {json.dumps(resp, ensure_ascii=False)}', flush=True)
                    self._status_signal.emit(self._i18n['create_failed_prefix'] + str(error_msg), 'error')
                    return
                
                # 发送信号，在主线程中处理
                print(f'[VIDEO] 任务创建成功，ID: {task_id}', flush=True)
                poll_info = {'base': base, 'token': token, 'id': task_id, 'provider': 'sora2', 'prompt': prompt}
                self._task_created_signal.emit(poll_info)
                
            except urllib.error.HTTPError as e:
                error_detail = ''
                try:
                    error_detail = e.read().decode('utf-8')
                except Exception:
                    pass
                error_msg = f'HTTP {e.code}: {e.reason}'
                if error_detail:
                    try:
                        error_json = json.loads(error_detail)
                        error_msg += f' - {error_json.get("error") or error_json.get("message") or error_detail[:200]}'
                    except Exception:
                        error_msg += f' - {error_detail[:200]}'
                print(f'[VIDEO] HTTP错误: {error_msg}', flush=True)
                self._status_signal.emit(self._i18n['create_failed_prefix'] + str(error_msg), 'error')
                
            except urllib.error.URLError as e:
                error_msg = f"{self._i18n['network_error_prefix']}{e.reason}"
                print(f'[VIDEO] URL错误: {error_msg}', flush=True)
                self._status_signal.emit(self._i18n['create_failed_prefix'] + str(error_msg), 'error')
                
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                print(f"[VIDEO] {self._i18n['exception_prefix']}{e}", flush=True)
                print(f'[VIDEO] 堆栈跟踪:\n{error_trace}', flush=True)
                self._status_signal.emit(self._i18n['create_failed_prefix'] + str(e), 'error')
                
        threading.Thread(target=worker, daemon=True).start()

    def _poll_once(self):
        p = self._current_poll
        if not p or self._poll_busy:
            return
        self._poll_busy = True
        def worker():
            try:
                if p['provider'] == 'sora2':
                    q_url = p['base'] + '/v1/video/query?id=' + urllib.parse.quote(p['id'])
                    # 只在首次轮询时打印URL，减少冗余日志
                    if not hasattr(self, '_poll_logged'):
                        self._poll_logged = True
                        try:
                            self._debug(f"poll(sora2): {q_url}")
                        except Exception:
                            pass
                    req = urllib.request.Request(q_url, headers={'Accept': 'application/json', 'Authorization': 'Bearer ' + p['token']}, method='GET')
                    with urllib.request.urlopen(req, timeout=60) as r:
                        txt = r.read().decode('utf-8')
                    try:
                        j = json.loads(txt)
                    except Exception:
                        j = {'raw': txt}
                    # 使用信号发送结果
                    self._poll_result_signal.emit('sora2', j)
                    
                elif p['provider'] == 'wan25':
                    candidates = [
                        p['base'] + '/alibailian/api/v1/services/aigc/video-generation/video-query?task_id=' + urllib.parse.quote(p['id']),
                        p['base'] + '/alibailian/api/v1/services/aigc/video-generation/query?task_id=' + urllib.parse.quote(p['id']),
                        p['base'] + '/v1/video/query?id=' + urllib.parse.quote(p['id'])
                    ]
                    j_ok = None; url_out = None; status_raw = None
                    for u in candidates:
                        try:
                            self._debug(f"poll(wan25): {u}")
                            req = urllib.request.Request(u, headers={'Accept': 'application/json', 'Authorization': 'Bearer ' + p['token']}, method='GET')
                            with urllib.request.urlopen(req, timeout=20) as r:
                                j = json.loads(r.read().decode('utf-8'))
                            raw = str(j.get('output', {}).get('task_status') or j.get('task_status') or j.get('status') or 'pending').lower()
                            status_raw = raw
                            succ = {'succeeded','success','finished','completed','done'}
                            fail = {'failed','error','cancelled','canceled'}
                            if raw in succ:
                                j_ok = j
                                url_out = j.get('output', {}).get('video_url') or j.get('video_url') or j.get('result', {}).get('url') or j.get('url')
                                break
                            elif raw in fail:
                                j_ok = j
                                break
                        except Exception:
                            continue
                    # 使用信号发送结果
                    result = {'status': status_raw or 'pending', 'url': url_out}
                    self._poll_result_signal.emit('wan25', result)

                elif p['provider'] == 'jimeng':
                    q_url = p['base'] + '/jimeng/query/videos?id=' + urllib.parse.quote(p['id'])
                    # 只在首次轮询时打印URL
                    if not hasattr(self, '_poll_logged'):
                        self._poll_logged = True
                        try:
                            self._debug(f"poll(jimeng): {q_url}")
                        except Exception:
                            pass
                    req = urllib.request.Request(q_url, headers={'Accept': 'application/json', 'Authorization': 'Bearer ' + p['token']}, method='GET')
                    with urllib.request.urlopen(req, timeout=60) as r:
                        txt = r.read().decode('utf-8')
                    try:
                        j = json.loads(txt)
                    except Exception:
                        j = {'raw': txt}
                    
                    status = j.get('status', 'pending')
                    url_out = j.get('video_url')
                    
                    result = {'status': status, 'url': url_out}
                    if j.get('error'):
                        result['error'] = j.get('error')
                        
                    self._poll_result_signal.emit('jimeng', result)
                    
                elif p['provider'] == 'hailuo02':
                    extra = {'base_url': p['base'], 'api_key': p['token']}
                    if not hasattr(self, '_poll_logged'):
                        self._poll_logged = True
                        try:
                            self._debug(f"poll(hailuo02): id={p['id']}")
                        except Exception:
                            pass
                    raw = Hailuo02.query_task(p['id'], extra)
                    result = {}
                    if raw and not raw.get('error'):
                        data_obj = raw.get('data') or {}
                        inner = data_obj.get('data') or {}
                        status_val = inner.get('status') or data_obj.get('status') or ''
                        progress_val = data_obj.get('progress') or inner.get('progress')
                        file_obj = inner.get('file') or {}
                        url_out = file_obj.get('download_url') or file_obj.get('backup_download_url')
                        file_id = file_obj.get('file_id') or inner.get('file_id') or data_obj.get('file_id')
                        base_resp = inner.get('base_resp') or data_obj.get('base_resp') or raw.get('base_resp')
                        result = {
                            'status': status_val,
                            'progress': progress_val,
                            'url': url_out,
                            'file_id': file_id,
                            'base_resp': base_resp,
                        }
                    else:
                        msg = ''
                        if raw:
                            msg = raw.get('message') or raw.get('error') or ''
                        result = {'status': 'failed', 'error': msg}
                    self._poll_result_signal.emit('hailuo02', result)
                    
            except Exception as e:
                self._status_signal.emit(self._i18n['query_failed_prefix'] + str(e), 'error')
            finally:
                self._poll_busy = False
        threading.Thread(target=worker, daemon=True).start()

    def _generate_jimeng(self, prompt: str):
        # 优先从json/jimeng.json读取配置
        try:
            import json, os
            config = {}
            if os.path.exists('json/jimeng.json'):
                with open('json/jimeng.json', 'r', encoding='utf-8') as f:
                    config = json.load(f)
            
            base = self._normalize_base(config.get('base_url', '') or '')
            token = (config.get('api_key', '') or '').strip()
            model = str(config.get('model', 'jimeng-video-3.0') or 'jimeng-video-3.0')
            # 参考 jimeng_provider.py 的模型映射逻辑
            if model in ("jimeng-videos", "jimeng-video", "jimeng_video", "jimeng-v3"):
                model = "jimeng-video-3.0"
            ratio = str(config.get('aspect_ratio', '16:9') or '16:9')
            duration = int(config.get('duration', '5') or 5)
            size = str(config.get('size', '1080P') or '1080P')
            
            print(f'[Jimeng] 从json/jimeng.json读取配置: model={model}, ratio={ratio}, duration={duration}', flush=True)
        except Exception as e:
            print(f'[Jimeng] 读取配置失败: {e}', flush=True)
            base = ''
            token = ''
        
        if not base:
            self._update_status('请先在设置中配置即梦 API 地址', 'error'); return
        if not token:
            self._update_status('请先在设置中配置即梦 API Key', 'error'); return
            
        if base.startswith('sk-'):
            self._update_status('即梦 Base URL 配置错误：不能以 sk- 开头，请检查是否误填了 API Key', 'error')
            return
            
        payload = {
            'model': model,
            'prompt': prompt,
            'aspect_ratio': ratio,
            'size': size,
            'images': [],
            'duration': duration
        }
        
        if self._first_image_b64:
            # 尝试放入 images 数组
            payload['images'].append(self._first_image_b64)
            print(f'[Jimeng] 使用首帧图 (添加到 images 数组)', flush=True)
        
        # 参考 Vector Engine API: POST /v1/video/create
        # 如果 base 已经包含 /v1，则拼接 /video/create；否则拼接 /v1/video/create
        base = base.rstrip('/ ,')
        if base.endswith('/v1'):
            url = base + '/video/create'
        else:
            url = base + '/v1/video/create'
            
        self._update_status(self._i18n['creating_task'], 'loading')
        
        def worker():
            try:
                print(f'[VIDEO] 正在发送请求到: {url}', flush=True)
                print(f'[VIDEO] 请求载荷: {json.dumps(payload, ensure_ascii=False)}', flush=True)
                self._status_signal.emit(self._i18n['connecting_api'], 'loading')
                
                req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                             headers={'Content-Type': 'application/json', 'Accept': 'application/json', 'Authorization': 'Bearer ' + token},
                                             method='POST')
                
                with urllib.request.urlopen(req, timeout=120) as r:
                    txt = r.read().decode('utf-8')
                
                print(f'[VIDEO] 响应内容: {txt}', flush=True)
                
                resp = json.loads(txt)
                task_id = resp.get('id') or resp.get('task_id')
                
                if not task_id:
                    error_msg = resp.get('error') or resp.get('message') or '未获取到任务ID'
                    self._status_signal.emit(self._i18n['create_failed_prefix'] + str(error_msg), 'error')
                    return
                
                print(f'[VIDEO] 任务创建成功，ID: {task_id}', flush=True)
                poll_info = {'base': base, 'token': token, 'id': task_id, 'provider': 'jimeng', 'prompt': prompt}
                self._task_created_signal.emit(poll_info)
            
            except urllib.error.HTTPError as e:
                detail = ''
                try:
                    detail = e.read().decode('utf-8')
                except Exception:
                    detail = ''
                print(f"[VIDEO] Jimeng HTTP Error {e.code}: {e.reason}", flush=True)
                print(f"[VIDEO] Error Detail: {detail}", flush=True)
                self._status_signal.emit(f"HTTP Error {e.code}: {detail[:200]}", 'error')
                
            except Exception as e:
                print(f"[VIDEO] Jimeng error: {e}", flush=True)
                self._status_signal.emit(self._i18n['create_failed_prefix'] + str(e), 'error')
                
        threading.Thread(target=worker, daemon=True).start()

    def _generate_hailuo02(self, prompt: str):
        # 优先从json/hailuo02.json读取配置
        try:
            config = Hailuo02.load_config()
            base = self._normalize_base(config.get('base_url', '') or '')
            token = (config.get('api_key', '') or '').strip()
            model = str(config.get('model', 'MiniMax-Hailuo-02') or 'MiniMax-Hailuo-02')
            ratio = str(config.get('aspect_ratio', '16:9') or '16:9')
            duration_raw = config.get('duration', '10') or '10'
            try:
                duration = int(str(duration_raw))
                if duration not in (6, 10):
                    duration = 10
            except Exception:
                duration = 10
            
            print(f'[Hailuo02] 从json/hailuo02.json读取配置: model={model}, ratio={ratio}, duration={duration}', flush=True)
        except Exception as e:
            print(f'[Hailuo02] 读取配置失败: {e}', flush=True)
            base = ''
            token = ''
        
        if not base:
            self._update_status('请先在设置中配置海螺02 Base URL', 'error'); return
        if not token:
            self._update_status('请先在设置中配置海螺02 API Key', 'error'); return
            
        if base.startswith('sk-'):
            self._update_status('海螺02 Base URL 配置错误：不能以 sk- 开头，请检查是否误填了 API Key', 'error')
            return
            
        payload = {
            'base_url': base,
            'api_key': token,
            'model': model,
            'prompt': prompt,
            'aspect_ratio': ratio,
            'duration': duration,
        }
        
        if self._first_image_b64:
            payload['first_frame_image'] = self._first_image_b64
            print(f'[Hailuo02] 使用首帧图', flush=True)
        
        if self._last_image_b64:
            payload['last_frame_image'] = self._last_image_b64
            print(f'[Hailuo02] 使用尾帧图', flush=True)
            
        self._update_status(self._i18n['creating_task'], 'loading')
        
        def worker():
            try:
                print(f'[VIDEO] 正在创建海螺02任务...', flush=True)
                self._status_signal.emit(self._i18n['connecting_api'], 'loading')
                
                resp = Hailuo02.create_task(payload)
                print(f'[VIDEO] 海螺02响应: {json.dumps(resp, ensure_ascii=False)}', flush=True)
                
                if resp.get('error'):
                    msg = resp.get('message', 'Unknown Error')
                    self._status_signal.emit(self._i18n['create_failed_prefix'] + str(msg), 'error')
                    return

                task_id = resp.get('id') or resp.get('task_id')
                
                if not task_id:
                    error_msg = resp.get('message') or '未获取到任务ID'
                    self._status_signal.emit(self._i18n['create_failed_prefix'] + str(error_msg), 'error')
                    return
                
                print(f'[VIDEO] 任务创建成功，ID: {task_id}', flush=True)
                poll_info = {'base': base, 'token': token, 'id': task_id, 'provider': 'hailuo02', 'prompt': prompt}
                self._task_created_signal.emit(poll_info)
                
            except Exception as e:
                print(f"[VIDEO] Hailuo02 error: {e}", flush=True)
                self._status_signal.emit(self._i18n['create_failed_prefix'] + str(e), 'error')
                
        threading.Thread(target=worker, daemon=True).start()

    def _handle_hailuo02_poll(self, result: dict):
        """处理海螺02轮询结果"""
        if not result:
            return
        
        if result.get('error'):
             self._poll_timer.stop()
             self._update_status(f"{self._i18n['task_failed_prefix']}: {result.get('message')}", 'error')
             return

        status_raw = str(result.get('status', 'queued') or 'queued').lower()
        progress = result.get('progress')
        succ = {'success', 'succeeded', 'finished', 'completed', 'done'}
        fail = {'fail', 'failed', 'error', 'cancelled', 'canceled', 'timeout'}
        
        if status_raw in succ:
            self._poll_timer.stop()
            file_id = result.get('file_id')
            url_out = result.get('url') or result.get('video_url')
            if url_out:
                self._update_status('生成完成', 'success')
                self.log_message(f'[VIDEO] 海螺02生成完成！视频URL: {url_out}')
                if not self._suppress_left_preview_on_next_video:
                    self._show_video_url(url_out)
                self._suppress_left_preview_on_next_video = False
                
                # 添加到历史记录
                prompt = self._current_poll.get('prompt', '') if self._current_poll else ''
                self._add_to_history(url_out, prompt)
            else:
                 self._update_status('生成完成但未找到视频链接', 'error')
                 self.log_message(f'[VIDEO] 完整响应: {json.dumps(result)}')

        elif status_raw in fail:
            self._poll_timer.stop()
            error_msg = result.get('base_resp', {}).get('status_msg') or 'Task Failed'
            self._update_status(f"{self._i18n['task_failed_prefix']}: {error_msg}", 'error')
        else:
            if progress:
                self._update_status(self._i18n['generating_pct'].format(pct=progress), 'loading')
            else:
                self._update_status(self._i18n['generating_state'].format(state=status_raw), 'loading')

    def _extract_video_url(self, j: dict) -> str | None:
        for k in ['result', 'data']:
            v = j.get(k) or {}
            for c in ['url', 'video_url']:
                u = v.get(c)
                if isinstance(u, str) and u.startswith('http'):
                    return u
        for c in ['result_url', 'video_url', 'url']:
            u = j.get(c)
            if isinstance(u, str) and u.startswith('http'):
                return u
        return None

    def _show_video_url(self, url: str | None):
        if not url:
            self.video_placeholder.setText(self._i18n['no_url_notice'])
            self.video_placeholder.show()
            self.video_widget.hide()
            self.btn_open.setEnabled(False)
            return
        
        # 保存URL
        self._video_url = url
        self.btn_open.setEnabled(True)
        
        # 隐藏占位符，显示视频播放器
        self.video_placeholder.hide()
        self.video_widget.show()
        
        # 加载视频（不自动循环，不自动播放，交给“播放”按钮）
        try:
            self.media_player.setSource(QUrl(url))
            self._should_loop = False
            # 启用底部播放控制
            try:
                if hasattr(self, 'btn_play_row'):
                    self.btn_play_row.setEnabled(True)
                if hasattr(self, 'btn_pause_row'):
                    self.btn_pause_row.setEnabled(True)
            except Exception:
                pass
            # 隐藏居中覆盖层
            try:
                self.center_controls.hide()
            except Exception:
                pass
            try:
                self.progress_slider.show()
                self._position_progress_overlay()
            except Exception:
                pass
            self.log_message(f'[VIDEO] 已加载视频: {url}')
            # 自动播放一次
            try:
                self.media_player.play()
                self.log_message(f'[VIDEO] 自动播放视频')
            except Exception as e:
                self.log_message(f'[VIDEO] 自动播放失败: {e}')
        except Exception as e:
            self.log_message(f'[VIDEO] 播放视频失败: {e}')
            # 如果播放失败，显示链接
            self.video_widget.hide()
            self.video_placeholder.show()
            self.video_placeholder.setText(self._i18n['open_in_browser_notice'])
            try:
                self.center_controls.hide()
            except Exception:
                pass
            try:
                self.progress_slider.hide()
            except Exception:
                pass

    def _upload_video(self):
        """上传本地视频并在预览区播放"""
        path, _ = QFileDialog.getOpenFileName(
            self, 
            self._i18n['pick_video_title'], 
            '', 
            'Videos (*.mp4 *.avi *.mov *.mkv *.webm *.flv);;All Files (*.*)'
        )
        if not path:
            return
        
        try:
            # 显示视频播放器
            self.video_placeholder.hide()
            self.video_widget.show()
            
            # 加载本地视频（自动播放一次）
            self.media_player.setSource(QUrl.fromLocalFile(path))
            self._should_loop = False
            # 启用底部播放控制
            try:
                if hasattr(self, 'btn_play_row'):
                    self.btn_play_row.setEnabled(True)
                if hasattr(self, 'btn_pause_row'):
                    self.btn_pause_row.setEnabled(True)
            except Exception:
                pass
            # 隐藏居中覆盖层
            try:
                self.center_controls.hide()
            except Exception:
                pass
            try:
                self.progress_slider.show()
                self._position_progress_overlay()
            except Exception:
                pass
            
            self._update_status(self._i18n['loaded_local_video_prefix'] + str(path), 'success')
            print(f'[VIDEO] 已加载本地视频: {path}', flush=True)
            # 自动播放一次
            try:
                self.media_player.play()
                print(f'[VIDEO] 自动播放视频', flush=True)
            except Exception as e:
                print(f'[VIDEO] 自动播放失败: {e}', flush=True)
            
            # 保存路径以便在浏览器中打开
            self._video_url = path
            # 记录当前本地路径，供右键自动分镜使用
            self._current_local_path = path
            self.btn_open.setEnabled(True)
            
        except Exception as e:
            self._update_status(f'视频加载失败: {str(e)}', 'error')
            print(f'[VIDEO] 加载本地视频失败: {e}', flush=True)

    def _show_video_context_menu(self, pos):
        """显示视频右键菜单"""
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        clear_action = menu.addAction(self._i18n['menu_clear_video'])
        action = menu.exec(self.video_widget.mapToGlobal(pos))
        if action == clear_action:
            self._clear_video()

    def _clear_video(self):
        """清空当前视频"""
        try:
            self.media_player.stop()
            self.media_player.setSource(QUrl())
            self._should_loop = False
            self.video_widget.hide()
            self.video_placeholder.show()
            self.video_placeholder.setText(self._i18n['video_placeholder'])
            self._video_url = None
            self.btn_open.setEnabled(False)
            # 清空后禁用播放控制
            if hasattr(self, 'btn_play'):
                self.btn_play.setEnabled(False)
            if hasattr(self, 'btn_pause'):
                self.btn_pause.setEnabled(False)
            if hasattr(self, 'btn_play_row'):
                self.btn_play_row.setEnabled(False)
            if hasattr(self, 'btn_pause_row'):
                self.btn_pause_row.setEnabled(False)
            try:
                self.center_controls.hide()
            except Exception:
                pass
            try:
                self.progress_slider.hide()
            except Exception:
                pass
            self._update_status(self._i18n['cleared_video'], 'normal')
            print('[VIDEO] 视频已清空', flush=True)
        except Exception as e:
            print(f'[VIDEO] 清空视频失败: {e}', flush=True)

    def _on_position_changed(self, pos: int):
        try:
            if hasattr(self, 'progress_slider'):
                self.progress_slider.setValue(int(pos))
        except Exception:
            pass

    def _on_duration_changed(self, dur: int):
        try:
            if hasattr(self, 'progress_slider'):
                self.progress_slider.setRange(0, int(dur))
        except Exception:
            pass

    def _on_media_status(self, status):
        """媒体状态回调：不再自动循环播放。"""
        try:
            from PySide6.QtMultimedia import QMediaPlayer as _QMP
            self.log_message(f'[VIDEO] Media Status Changed: {status}')
            if status == _QMP.MediaStatus.EndOfMedia:
                # 结束后保持停止，由用户点击“播放”重新开始
                self.log_message('[VIDEO] 播放结束（不循环）')
        except Exception:
            pass

    def _on_media_error(self, error, error_string):
        """媒体播放错误回调"""
        try:
            self.log_message(f'[VIDEO] MediaPlayer Error: {error} - {error_string}')
            self._update_status(f"播放出错: {error_string}", 'error')
            # 弹窗提示用户
            QMessageBox.warning(self, "播放错误", f"无法播放视频：\n{error_string}\n(Error Code: {error})")
        except Exception:
            pass

    def _play_video(self):
        try:
            if self.media_player is not None:
                from PySide6.QtMultimedia import QMediaPlayer as _QMP
                self.log_message(f'[VIDEO] Requesting Play. Current State: {self.media_player.playbackState()}, Status: {self.media_player.mediaStatus()}')
                
                # 如果播放已结束，重置进度到开头
                if self.media_player.mediaStatus() == _QMP.MediaStatus.EndOfMedia:
                    self.media_player.setPosition(0)
                    
                self.media_player.play()
        except Exception as e:
            self.log_message(f'[VIDEO] 播放失败: {e}')

    def _pause_video(self):
        try:
            if self.media_player is not None:
                self.log_message(f'[VIDEO] Requesting Pause. Current State: {self.media_player.playbackState()}')
                self.media_player.pause()
        except Exception as e:
            self.log_message(f'[VIDEO] 暂停失败: {e}')

    def _add_to_history(self, url: str, prompt: str = ""):
        """添加视频到历史记录"""
        try:
            # 先将视频下载保存到根目录的 video 文件夹
            local_path = None
            try:
                local_path = self._save_video_locally(url)
            except Exception as _e:
                self.log_message(f'[VIDEO] 保存到本地失败: {_e}')

            # 获取主窗口的历史面板
            if hasattr(self, 'history_panel'):
                self.history_panel.add_record(local_path or url, prompt)
                self.log_message('[VIDEO] 已添加到历史记录')
        except Exception as e:
            self.log_message(f'[VIDEO] 添加历史记录失败: {e}')

    def _save_video_locally(self, url: str, dest_path: str | None = None) -> str | None:
        """将生成的视频保存到项目根目录的 video 文件夹，返回本地路径。

        如果无法保存则返回 None。
        """
        try:
            if not isinstance(url, str) or not url:
                return None
            # 仅处理 http/https 的远程 URL；本地路径直接返回副本路径
            is_remote = url.startswith('http://') or url.startswith('https://')
            from pathlib import Path
            from datetime import datetime
            root_dir = Path(__file__).resolve().parent
            now = datetime.now()
            date_dir = f"{now.year}-{now.month}-{now.day}"
            video_dir = root_dir / 'video' / date_dir
            video_dir.mkdir(parents=True, exist_ok=True)

            ts = now.strftime('%Y%m%d-%H%M%S')
            # 从 URL 猜测后缀
            ext = 'mp4'
            try:
                import urllib.parse as _up
                parsed = _up.urlparse(url)
                name = Path(parsed.path).name
                if '.' in name:
                    suf = name.split('.')[-1].lower()
                    if len(suf) <= 5:
                        ext = suf
            except Exception:
                pass
            filename = f'{ts}.{ext}'
            out_path = Path(dest_path) if dest_path else (video_dir / filename)

            if is_remote:
                temp_path = out_path
                
                # 增加重试机制：最多尝试3次
                max_retries = 3
                download_success = False
                
                # 使用 requests 替代 urllib 以获得更好的 SSL/TLS 兼容性和连接稳定性
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                
                for attempt in range(max_retries):
                    try:
                        self.log_message(f'[VIDEO] 下载尝试 {attempt + 1}/{max_retries}: {url[:80]}...')
                        # 增加超时时间到300秒，verify=False 忽略 SSL 错误
                        with requests.get(url, headers=headers, stream=True, timeout=300, verify=False) as r:
                            r.raise_for_status()
                            with open(temp_path, 'wb') as f:
                                total_size = 0
                                for chunk in r.iter_content(chunk_size=8192):
                                    if chunk:
                                        f.write(chunk)
                                        total_size += len(chunk)
                        
                        self.log_message(f'[VIDEO] 下载完成: {total_size} 字节 -> {temp_path}')
                        download_success = True
                        break
                    except Exception as retry_err:
                        self.log_message(f'[VIDEO] 下载失败 (尝试 {attempt + 1}/{max_retries}): {retry_err}')
                        if attempt < max_retries - 1:
                            import time
                            wait_time = (attempt + 1) * 2  # 递增等待：2秒、4秒、6秒
                            self.log_message(f'[VIDEO] 等待 {wait_time} 秒后重试...')
                            time.sleep(wait_time)
                        else:
                            raise  # 最后一次失败则抛出
                
                if not download_success:
                    self.log_message('[VIDEO] 所有下载尝试均失败')
                    return None
                return str(out_path)
            else:
                # 如果传入的是本地路径，尝试复制到 video 目录
                import shutil
                src = Path(url)
                if src.exists():
                    shutil.copy2(src, out_path)
                    self.log_message(f'[VIDEO] 已复制本地视频到: {out_path}')
                    return str(out_path)
            return None
        except Exception as e:
            self.log_message(f'[VIDEO] 本地保存异常: {e}')
            return None

    def _open_video(self):
        """原“在浏览器中打开”按钮改为下载：
        - 远程URL：默认保存到项目 `video/` 目录
        - 本地文件：打开所在目录选中该文件
        """
        url = getattr(self, '_video_url', None)
        if not url:
            return
        
        try:
            # 直接使用类内部的保存方法，不再依赖 video2FA
            local_path = self._save_video_locally(url)
            
            if local_path:
                # 添加到历史记录
                if hasattr(self, 'history_panel'):
                    self.history_panel.add_record(local_path)
                    
                # 下载成功后立即播放本地文件
                try:
                    self.media_player.setSource(QUrl.fromLocalFile(local_path))
                    self._should_loop = False
                    # 不自动播放，由用户控制
                    if hasattr(self, 'btn_play'):
                        self.btn_play.setEnabled(True)
                    if hasattr(self, 'btn_pause'):
                        self.btn_pause.setEnabled(True)
                    try:
                        self.center_controls.show()
                        self._position_overlay_center()
                    except Exception:
                        pass
                    # 记录当前本地路径用于右键自动分镜，并同步 _video_url
                    self._current_local_path = local_path
                    self._video_url = local_path
                except Exception as e:
                    self.log_message(f'[VIDEO] 播放下载后视频失败: {e}')
                
                # 弹出提示并打开 video 目录
                try:
                    QMessageBox.information(self, '提示', '已保存到video目录')
                except Exception:
                    pass
                
                try:
                    from pathlib import Path
                    import platform, subprocess, os
                    if platform.system() == 'Windows':
                        subprocess.run(['explorer', '/select,', local_path])
                    elif platform.system() == 'Darwin':
                        subprocess.run(['open', '-R', local_path])
                    else:
                        folder = str(Path(local_path).parent)
                        subprocess.run(['xdg-open', folder])
                except Exception:
                    pass
                
                # UI 状态与额外 debug 概览
                self._update_status('已完成', 'success')
            else:
                self._update_status('下载失败', 'error')
        except Exception as e:
            self.log_message(f'[VIDEO] 下载失败: {e}')
            self._update_status('下载失败', 'error')

    # --- Wan2.5 ---
    def _generate_wan25(self, prompt: str):
        # 优先从json/wan25.json读取配置
        try:
            from Awan25 import load_config
            config = load_config()
            base = self._normalize_base(config.get('base_url', '') or '')
            token = (config.get('api_key', '') or '').strip()
            model = (config.get('model', 'wan2.5-i2v-preview') or 'wan2.5-i2v-preview')
            resolution = str(config.get('resolution', '1080P') or '1080P')
            duration_raw = config.get('duration', '10')
            try:
                duration = int(str(duration_raw))
            except Exception:
                duration = 10
            pe_raw = str(config.get('prompt_extend', 'true')).strip().lower()
            wm_raw = str(config.get('watermark', 'true')).strip().lower()
            au_raw = str(config.get('audio', 'true')).strip().lower()
            prompt_extend = pe_raw in ('true','1','yes','on')
            watermark = wm_raw in ('true','1','yes','on')
            audio = au_raw in ('true','1','yes','on')
            print(f'[Wan25] 从json/wan25.json读取配置: model={model}, resolution={resolution}, duration={duration}', flush=True)
        except Exception as e:
            # 如果读取JSON失败，回退到QSettings
            print(f'[Wan25] 从json读取配置失败，使用QSettings: {e}', flush=True)
            s = QSettings('GhostOS', 'App')
            base = self._normalize_base(s.value('providers/wan25/base_url', 'https://api.vectorengine.ai') or '')
            token = (s.value('providers/wan25/api_key', '') or '').strip()
            model = (s.value('providers/wan25/model', 'wan2.5-i2v-preview') or 'wan2.5-i2v-preview')
            resolution = str(s.value('providers/wan25/resolution', '1080P') or '1080P')
            duration_raw = s.value('providers/wan25/duration', 10)
            try:
                duration = int(str(duration_raw))
            except Exception:
                duration = 10
            pe_raw = str(s.value('providers/wan25/prompt_extend', 'true') or 'true').strip().lower()
            wm_raw = str(s.value('providers/wan25/watermark', 'true') or 'true').strip().lower()
            au_raw = str(s.value('providers/wan25/audio', 'true') or 'true').strip().lower()
            prompt_extend = pe_raw in ('true','1','yes','on')
            watermark = wm_raw in ('true','1','yes','on')
            audio = au_raw in ('true','1','yes','on')
        
        if not base:
            self._update_status('请在设置里填写 万象2.5 Base URL', 'error'); return
        if not token:
            self._update_status('请在设置里填写 万象2.5 API Key', 'error'); return
        
        payload = {
            'model': model,
            'input': { 'prompt': prompt },
            'parameters': { 'resolution': resolution, 'duration': duration, 'prompt_extend': prompt_extend, 'watermark': watermark, 'audio': audio }
        }
        # 附带参考帧（若选择了首帧/尾帧），便于调试观察是否发送
        # 与 web 保持一致：万象2.5仅支持单张首帧，通过 img_url 字段传入
        img_url = None
        if self._first_image_b64:
            img_url = self._first_image_b64
        elif self._last_image_b64:
            img_url = self._last_image_b64
        if img_url:
            payload['input']['img_url'] = img_url
        url = base + '/alibailian/api/v1/services/aigc/video-generation/video-synthesis'
        self._update_status('正在创建万象2.5任务…', 'loading')
        def worker():
            try:
                try:
                    self._debug(f"create(wan25): url={url} | model={model} | resolution={payload.get('parameters',{}).get('resolution')} | duration={payload.get('parameters',{}).get('duration')} | prompt_extend={payload.get('parameters',{}).get('prompt_extend')} | watermark={payload.get('parameters',{}).get('watermark')} | audio={payload.get('parameters',{}).get('audio')} | prompt_len={len(prompt)} | img_set={'yes' if img_url else 'no'}")
                except Exception:
                    pass
                
                print(f'[VIDEO] 正在发送万象2.5请求到: {url}', flush=True)
                self._status_signal.emit('正在连接万象2.5 API...', 'loading')
                
                req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                             headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token},
                                             method='POST')
                
                print(f'[VIDEO] 等待万象2.5服务器响应...', flush=True)
                with urllib.request.urlopen(req, timeout=120) as r:
                    print(f'[VIDEO] 收到响应，状态码: {r.status}', flush=True)
                    txt = r.read().decode('utf-8')
                    print(f'[VIDEO] 响应长度: {len(txt)} 字节', flush=True)
                
                try:
                    j = json.loads(txt)
                except Exception as parse_err:
                    print(f'[VIDEO] JSON解析失败: {parse_err}', flush=True)
                    print(f'[VIDEO] 原始响应: {txt[:1000]}', flush=True)
                    j = {'raw': txt}
                
                try:
                    self._debug('create(wan25): resp=' + (txt[:500] + ('...' if len(txt) > 500 else '')))
                except Exception:
                    pass
                
                task_id = j.get('output', {}).get('task_id') or j.get('task_id') or ''
                direct = j.get('output', {}).get('video_url') or j.get('video_url') or j.get('url')
                
                print(f'[VIDEO] 任务ID: {task_id}, 直出URL: {direct}', flush=True)
                
                if direct and isinstance(direct, str):
                    print(f'[VIDEO] 获得直出视频URL: {direct}', flush=True)
                    self._video_url_signal.emit(direct)
                    self._status_signal.emit('生成成功（直出URL）', 'success')
                    return
                    
                if not task_id:
                    error_msg = j.get('error') or j.get('message') or j.get('output', {}).get('message') or '未获取到任务ID'
                    print(f'[VIDEO] 错误: {error_msg}', flush=True)
                    print(f'[VIDEO] 完整响应: {json.dumps(j, ensure_ascii=False)}', flush=True)
                    self._status_signal.emit(f'创建失败: {error_msg}', 'error')
                    return
                
                # 发送信号，在主线程中处理
                print(f'[VIDEO] 万象2.5任务创建成功，ID: {task_id}', flush=True)
                poll_info = {'base': base, 'token': token, 'id': task_id, 'provider': 'wan25', 'prompt': prompt}
                self._task_created_signal.emit(poll_info)
                
            except urllib.error.HTTPError as e:
                error_detail = ''
                try:
                    error_detail = e.read().decode('utf-8')
                except Exception:
                    pass
                error_msg = f'HTTP {e.code}: {e.reason}'
                if error_detail:
                    try:
                        error_json = json.loads(error_detail)
                        error_msg += f' - {error_json.get("error") or error_json.get("message") or error_detail[:200]}'
                    except Exception:
                        error_msg += f' - {error_detail[:200]}'
                print(f'[VIDEO] HTTP错误: {error_msg}', flush=True)
                self._status_signal.emit(f'创建失败: {error_msg}', 'error')
                
            except urllib.error.URLError as e:
                error_msg = f'网络错误: {e.reason}'
                print(f'[VIDEO] URL错误: {error_msg}', flush=True)
                self._status_signal.emit(f'创建失败: {error_msg}', 'error')
                
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                print(f'[VIDEO] 异常: {e}', flush=True)
                print(f'[VIDEO] 堆栈跟踪:\n{error_trace}', flush=True)
                self._status_signal.emit(f'创建失败: {str(e)}', 'error')
                
        threading.Thread(target=worker, daemon=True).start()
