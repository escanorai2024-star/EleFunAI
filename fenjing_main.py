import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path
import os
import shutil

_FFMPEG_PATH: str | None = None

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
    QSizePolicy, QPushButton, QFileDialog, QGridLayout, QApplication, QSlider, QMenu, QLineEdit, QComboBox, QDialog
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtCore import QUrl


def _find_ffmpeg() -> str:
    """Return the ffmpeg executable path.
    
    Priority:
    1) `./ffmpeg/ffmpeg.exe` (Windows) or `./ffmpeg/ffmpeg`
    2) `./ffmpeg.exe` or `./ffmpeg` in root
    3) PATH lookup
    """
    global _FFMPEG_PATH
    if _FFMPEG_PATH:
        return _FFMPEG_PATH
    root = Path(os.getcwd())
    candidates = [
        root / 'ffmpeg' / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'),
        root / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'),
    ]
    for c in candidates:
        if c.exists():
            _FFMPEG_PATH = str(c)
            return _FFMPEG_PATH
    exe = 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'
    found = shutil.which(exe) or exe
    _FFMPEG_PATH = found
    return _FFMPEG_PATH


def split_scenes_ffmpeg(input_path: str, out_dir: Path, threshold: float = 0.2, max_frames: int | None = None) -> list[Path]:
    """Use FFmpeg scene detection to extract key frames.

    Args:
        input_path: Video file path.
        out_dir: Directory to write frames (created if missing).
        threshold: Scene change threshold (0.2 requested).
        max_frames: Optional cap on number of exported frames.

    Returns:
        List of frame image paths (ordered).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    # Clean any previous content in target dir
    for p in sorted(out_dir.glob('scene-*.jpg')):
        try:
            p.unlink()
        except Exception:
            pass

    ffmpeg = _find_ffmpeg()
    # Build select filter with threshold and vfr extraction
    # Important: do NOT wrap with quotes when using subprocess(list) on Windows.
    # Use escaped comma to avoid splitting filter chain at the select arg.
    # Example: select=gt(scene\,0.2),scale=640:-1
    vf = f"select=gt(scene\\,{threshold}),scale=640:-1"
    output_pattern = str(out_dir / 'scene-%04d.jpg')

    cmd = [
        ffmpeg,
        '-hide_banner', '-loglevel', 'warning', '-y',
        '-i', input_path,
        '-vf', vf,
        '-vsync', 'vfr',
        output_pattern,
    ]

    print(f'[FRAME] 执行FFmpeg命令...', flush=True)
    print(f'[FRAME] 输入视频: {input_path}', flush=True)
    print(f'[FRAME] 输出目录: {out_dir}', flush=True)
    print(f'[FRAME] 滤镜参数: {vf}', flush=True)
    
    try:
        # 在 Windows 下隐藏 FFmpeg 的控制台窗口
        startup = None
        creation_flags = 0
        try:
            if os.name == 'nt':
                startup = subprocess.STARTUPINFO()
                startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startup.wShowWindow = subprocess.SW_HIDE
                creation_flags |= subprocess.CREATE_NO_WINDOW
        except Exception:
            startup = None
            creation_flags = 0

        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            startupinfo=startup,
            creationflags=creation_flags,
        )
        if result.stdout:
            print(f'[FRAME] FFmpeg标准输出: {result.stdout}', flush=True)
        if result.stderr:
            print(f'[FRAME] FFmpeg警告/信息: {result.stderr}', flush=True)
    except subprocess.CalledProcessError as e:
        print(f'[FRAME] FFmpeg 场景检测失败: {e}', flush=True)
        if hasattr(e, 'stderr') and e.stderr:
            print(f'[FRAME] 错误详情: {e.stderr}', flush=True)
        if hasattr(e, 'stdout') and e.stdout:
            print(f'[FRAME] 输出详情: {e.stdout}', flush=True)
        return []

    frames = sorted(out_dir.glob('scene-*.jpg'))
    if max_frames is not None and len(frames) > max_frames:
        frames = frames[:max_frames]
    return frames


class StoryboardPanel(QWidget):
    """Right-side storyboard panel that shows scene-split images.

    All code is placed in this file as requested.
    """
    # Emit when a frame is clicked (path)
    frame_clicked = Signal(str)

    def __init__(self, parent=None, threshold: float = 0.2):
        super().__init__(parent)
        self.threshold = threshold
        self._frames: list[Path] = []
        # 改为每行一张
        self._columns = 1
        self._thumb_w = 140
        self._thumb_h = 80
        # 记录当前视频路径，用于阈值调整时重新生成
        self._current_video_path: str | None = None
        # 引用宿主 VideoPage
        self._host = parent if parent and parent.__class__.__name__ == 'VideoPage' else None
        # 收集每个分镜生成的视频URL
        self._video_urls: list[str] = []
        # 播放器对话框引用，避免被垃圾回收
        self._player_dialogs: list[QDialog] = []
        self._build_ui()

    def _on_split_video_clicked(self):
        """Open file dialog to select a video and split it."""
        path, _ = QFileDialog.getOpenFileName(
            self, 
            "选择视频", 
            '', 
            'Videos (*.mp4 *.avi *.mov *.mkv *.webm *.flv);;All Files (*.*)'
        )
        if path:
            self.generate_from_local(path)

    def _build_ui(self):
        self.setObjectName('StoryboardPanel')
        self.setStyleSheet('#StoryboardPanel{ background:#ffffff; }')
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        header = QHBoxLayout()
        self.title = QLabel('分镜 (场景检测)')
        self.title.setStyleSheet('color:#3C4043; font-weight:600;')
        header.addWidget(self.title)
        header.addStretch(1)
        # 拆分视频按钮
        self.btn_split_video = QPushButton('拆分视频')
        self.btn_split_video.setStyleSheet('QPushButton{ height:24px; padding:0 10px; border-radius:6px; border:1px solid #dadce0; background:#ffffff; color:#202124; } QPushButton:hover{ background:#f1f3f4; }')
        self.btn_split_video.clicked.connect(self._on_split_video_clicked)
        header.addWidget(self.btn_split_video)
        # 下载分镜（原“下载全部”改名）
        self.btn_download = QPushButton('下载分镜图')
        self.btn_download.setStyleSheet('QPushButton{ height:24px; padding:0 10px; border-radius:6px; border:1px solid #dadce0; background:#ffffff; color:#202124; } QPushButton:hover{ background:#f1f3f4; }')
        self.btn_download.setEnabled(False)
        self.btn_download.clicked.connect(self.download_all_frames)
        header.addWidget(self.btn_download)
        # 新增：下载全部视频
        self.btn_download_videos = QPushButton('下载全部视频')
        self.btn_download_videos.setStyleSheet('QPushButton{ height:24px; padding:0 10px; border-radius:6px; border:1px solid #dadce0; background:#ffffff; color:#202124; } QPushButton:hover{ background:#f1f3f4; }')
        self.btn_download_videos.setEnabled(False)
        self.btn_download_videos.clicked.connect(self.download_all_videos)
        header.addWidget(self.btn_download_videos)
        self.btn_clear = QPushButton('清空')
        self.btn_clear.setStyleSheet('QPushButton{ height:24px; padding:0 10px; border-radius:6px; border:1px solid #dadce0; background:#ffffff; color:#202124; } QPushButton:hover{ background:#f1f3f4; }')
        self.btn_clear.clicked.connect(self.clear)
        header.addWidget(self.btn_clear)
        root.addLayout(header)

        # 添加阈值调整区域
        threshold_layout = QHBoxLayout()
        threshold_layout.setSpacing(8)
        
        threshold_label = QLabel('数值:')
        threshold_label.setStyleSheet('color:#3C4043; font-size:12px;')
        threshold_layout.addWidget(threshold_label)
        
        # 创建滑块，范围从10到50（代表0.1到0.5）
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setMinimum(10)
        self.threshold_slider.setMaximum(50)
        self.threshold_slider.setValue(int(self.threshold * 100))
        self.threshold_slider.setStyleSheet('QSlider::groove:horizontal{ height:6px; background:#e0e0e0; border-radius:3px; }QSlider::handle:horizontal{ background:#f59e0b; width:14px; margin:-4px 0; border-radius:7px; }QSlider::sub-page:horizontal{ background:#f59e0b; border-radius:3px; }')
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        threshold_layout.addWidget(self.threshold_slider, stretch=1)
        
        # 显示当前阈值数值
        self.threshold_value_label = QLabel(f'{self.threshold:.1f}')
        self.threshold_value_label.setStyleSheet('color:#f59e0b; font-weight:600; font-size:12px; min-width:30px;')
        threshold_layout.addWidget(self.threshold_value_label)
        
        root.addLayout(threshold_layout)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setStyleSheet('QScrollArea{ border:0; background:#ffffff; }')
        self.content = QWidget()
        self.content.setStyleSheet('background:#ffffff;')
        self.grid = QVBoxLayout(self.content)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.grid.setSpacing(8)
        self.grid.setAlignment(Qt.AlignTop)
        # 显式绑定布局，避免某些系统下未显示子控件的问题
        self.content.setLayout(self.grid)
        self.scroll.setWidget(self.content)
        # 允许内容横向自适应扩展，避免右侧控件被遮挡
        try:
            from PySide6.QtWidgets import QSizePolicy
            self.content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        except Exception:
            pass
        root.addWidget(self.scroll, stretch=1)

        self.setMinimumSize(QSize(300, 360))
        # 允许在右侧区域水平/垂直扩展，确保有足够空间呈现缩略图
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def _on_threshold_changed(self, value: int):
        """阈值滑块变化回调，自动重新生成分镜"""
        self.threshold = value / 100.0
        self.threshold_value_label.setText(f'{self.threshold:.1f}')
        print(f'[FRAME] 阈值已调整为: {self.threshold}', flush=True)
        
        # 如果有当前视频，自动重新生成分镜
        if self._current_video_path:
            print(f'[FRAME] 使用新阈值重新生成分镜...', flush=True)
            self.generate_from_local(self._current_video_path)

    def clear(self):
        # 完整清空：既清UI也清数据（供"清空"按钮使用）
        self._frames = []
        self._current_video_path = None  # 清空视频路径
        self._video_urls = []
        self._clear_grid()
        try:
            self.btn_download.setEnabled(False)
        except Exception:
            pass
        try:
            self.btn_download_videos.setEnabled(False)
        except Exception:
            pass

    def _clear_grid(self):
        # 仅清理UI网格子控件，不触及数据列表（供渲染/占位使用）
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

    def _show_processing(self, text: str = '处理中…'):
        """在面板中显示处理中占位，告知用户正在生成。"""
        self._clear_grid()
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet('QLabel{ color:#f59e0b; background:#ffffff; border:2px solid #f59e0b; border-radius:6px; padding:20px; }')
        self.grid.addWidget(lbl)
        try:
            self.content.adjustSize()
            self.content.update()
        except Exception:
            pass

    def _add_frame_thumb(self, img_path: Path, is_first: bool = False, is_last: bool = False):
        row_item = QFrame()
        row_item_l = QHBoxLayout(row_item)
        row_item_l.setContentsMargins(0, 0, 0, 0)
        row_item_l.setSpacing(12)
        # 左侧：分镜缩略图
        lbl = QLabel()
        lbl.setFixedSize(self._thumb_w, self._thumb_h)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet('QLabel{ background:#f1f3f4; border-radius:6px; }')
        try:
            lbl.setMouseTracking(True)
        except Exception:
            pass
        try:
            pix_raw = QPixmap(str(img_path))
            if pix_raw.isNull():
                print(f'[FRAME] 调试: 缩略图加载失败 -> {img_path}', flush=True)
                raise RuntimeError('Pixmap is null')
            pix = pix_raw.scaled(self._thumb_w, self._thumb_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl.setPixmap(pix)
            print(f'[FRAME] 调试: 缩略图已渲染 -> {img_path.name}', flush=True)
        except Exception:
            # 保持灰色背景占位，不显示文字
            lbl.setStyleSheet('QLabel{ background:#f1f3f4; border-radius:6px; }')
            print(f'[FRAME] 调试: 使用空占位 -> {img_path.name}', flush=True)
        def on_click(event):
            try:
                from PySide6.QtCore import Qt as _Qt
                if event.button() == _Qt.LeftButton:
                    self.frame_clicked.emit(str(img_path))
                # 右键不再弹出预览，交由自定义菜单处理
            except Exception:
                self.frame_clicked.emit(str(img_path))
        lbl.mousePressEvent = on_click
        # 首尾帧：添加绿色半透明遮罩，悬停时显示
        if is_first or is_last:
            overlay = QLabel(lbl)
            overlay.setStyleSheet('QLabel{ background-color: rgba(52,199,89,56); border-radius:6px; }')
            overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            overlay.setGeometry(0, 0, self._thumb_w, self._thumb_h)
            try:
                overlay.raise_()
            except Exception:
                pass
            overlay.hide()
            def _enter(_e):
                overlay.show()
            def _leave(_e):
                overlay.hide()
            lbl.enterEvent = _enter
            lbl.leaveEvent = _leave
        try:
            lbl.setContextMenuPolicy(Qt.CustomContextMenu)
            def _on_context_menu(pos):
                try:
                    menu = QMenu(self)
                    act_upload = menu.addAction('上传到参考图')
                    act_delete = menu.addAction('删除分镜')
                    act_replace = menu.addAction('替换分镜')
                    def _do_upload():
                        try:
                            win = self.window()
                            photo = getattr(win, 'photo_page', None)
                            if photo and hasattr(photo, 'add_to_reference_from_layer'):
                                pix_to_add = QPixmap(str(img_path))
                                if not pix_to_add.isNull():
                                    photo.add_to_reference_from_layer(pix_to_add)
                                    print(f"[FRAME] 已上传到参考图: {img_path}", flush=True)
                                else:
                                    print(f"[FRAME] 上传失败: 图片无法加载 -> {img_path}", flush=True)
                            else:
                                base_dir = Path(os.getcwd()) / 'JPG'
                                try:
                                    base_dir.mkdir(parents=True, exist_ok=True)
                                except Exception:
                                    pass
                                dst = base_dir / img_path.name
                                try:
                                    shutil.copy2(img_path, dst)
                                    print(f"[FRAME] 已复制到参考图库: {dst}", flush=True)
                                except Exception as e:
                                    print(f"[FRAME] 上传失败: 复制到参考图库异常 -> {e}", flush=True)
                        except Exception as e:
                            print(f"[FRAME] 上传失败: 异常 -> {e}", flush=True)
                    def _do_delete():
                        try:
                            try:
                                os.remove(str(img_path))
                                print(f"[FRAME] 已删除文件: {img_path}", flush=True)
                            except Exception:
                                pass
                            try:
                                self._frames = [p for p in self._frames if str(p) != str(img_path)]
                            except Exception:
                                pass
                            self._render_frames()
                        except Exception as e:
                            print(f"[FRAME] 删除分镜异常: {e}", flush=True)
                    def _do_replace():
                        try:
                            from PySide6.QtWidgets import QFileDialog
                            new_path, _ = QFileDialog.getOpenFileName(self, '选择替换图片', os.getcwd(), 'Images (*.png *.jpg *.jpeg *.webp)')
                            if not new_path:
                                return
                            try:
                                shutil.copy2(new_path, img_path)
                                print(f"[FRAME] 已替换分镜: {img_path} <- {new_path}", flush=True)
                            except Exception:
                                try:
                                    idx = [str(p) for p in self._frames].index(str(img_path))
                                    self._frames[idx] = Path(new_path)
                                except Exception:
                                    pass
                            self._render_frames()
                        except Exception as e:
                            print(f"[FRAME] 替换分镜异常: {e}", flush=True)
                    act_upload.triggered.connect(_do_upload)
                    act_delete.triggered.connect(_do_delete)
                    act_replace.triggered.connect(_do_replace)
                    menu.exec(lbl.mapToGlobal(pos))
                except Exception as e:
                    print(f"[FRAME] 右键菜单异常: {e}", flush=True)
            lbl.customContextMenuRequested.connect(_on_context_menu)
        except Exception:
            pass
        row_item_l.addWidget(lbl, stretch=0)
        # 右侧：三联红框控件
        ctrl = QFrame()
        ctrl_l = QHBoxLayout(ctrl)
        ctrl_l.setContentsMargins(0, 0, 0, 0)
        ctrl_l.setSpacing(12)
        # 提示词框
        prompt_box = QFrame()
        prompt_box.setStyleSheet('QFrame{ background:#ffffff; border-radius:8px; }')
        pb_l = QVBoxLayout(prompt_box)
        pb_l.setContentsMargins(8, 8, 8, 8)
        pb_l.setSpacing(4)
        prompt = QLineEdit()
        prompt.setPlaceholderText('请输入提示词')
        prompt.setStyleSheet('QLineEdit{ background:#f1f3f4; color:#202124; border:1px solid #e0e0e0; border-radius:6px; padding:4px 8px; font-size:12px; }')
        prompt.setFixedHeight(26)
        prompt_box.setFixedSize(180, 60)
        pb_l.addWidget(prompt)
        # API框
        api_box = QFrame()
        api_box.setStyleSheet('QFrame{ background:#ffffff; border-radius:8px; }')
        ab_l = QVBoxLayout(api_box)
        ab_l.setContentsMargins(8, 8, 8, 8)
        ab_l.setSpacing(4)
        combo = QComboBox()
        combo.addItems(['Sora2', '万象2.5'])
        combo.setStyleSheet('QComboBox{ background:#f1f3f4; color:#202124; border:1px solid #e0e0e0; border-radius:6px; padding:2px 6px; }')
        api_box.setFixedSize(120, 60)
        ab_l.addWidget(combo)
        # 视频框
        video_box = QFrame()
        video_box.setStyleSheet('QFrame{ background:#ffffff; border-radius:8px; }')
        vb_l = QVBoxLayout(video_box)
        vb_l.setContentsMargins(8, 8, 8, 8)
        vb_l.setSpacing(6)
        gen_btn = QPushButton('视频重组')
        gen_btn.setFixedHeight(28)
        gen_btn.setMinimumWidth(96)
        gen_btn.setStyleSheet('QPushButton{ height:28px; background:#00ffa3; color:#002b1e; border:1px solid #00ffa3; border-radius:8px; font-weight:600; padding:0 10px; } QPushButton:hover{ background:#19e58f; border-color:#19e58f; }')
        video_box.setFixedSize(140, 110)
        vb_l.addWidget(gen_btn)
        # 始终呈现“播放/下载”按钮，初始禁用，待有URL后启用
        play_ctx = {'url': None}
        btn_play = QPushButton('播放')
        btn_play.setEnabled(False)
        btn_play.setFixedHeight(28)
        btn_play.setMinimumWidth(80)
        btn_play.setStyleSheet('QPushButton{ height:28px; background:#34A853; color:#ffffff; border:1px solid #34A853; border-radius:8px; padding:0 10px; } QPushButton:hover{ background:#2e8b46; }')
        btn_down = QPushButton('下载')
        btn_down.setEnabled(False)
        btn_down.setFixedHeight(28)
        btn_down.setMinimumWidth(80)
        btn_down.setStyleSheet('QPushButton{ height:28px; background:#10b981; color:#002b1e; border:1px solid #10b981; border-radius:8px; padding:0 10px; } QPushButton:hover{ background:#0ea37a; }')
        def _play_btn():
            u = play_ctx['url']
            if not (isinstance(u, str) and u.startswith('http')):
                print('[STORYBOARD] 播放取消：暂无URL', flush=True)
                return
            try:
                # 弹出独立播放器窗口
                dlg = QDialog(self)
                dlg.setWindowTitle('播放')
                lay = QVBoxLayout(dlg)
                vw = QVideoWidget()
                vw.setStyleSheet('background:#000')
                mp = QMediaPlayer(dlg)
                ao = QAudioOutput(dlg)
                mp.setAudioOutput(ao)
                mp.setVideoOutput(vw)
                lay.addWidget(vw)
                mp.setSource(QUrl(u))
                mp.play()
                dlg.resize(640, 360)
                dlg.show()
                self._player_dialogs.append(dlg)
            except Exception as e:
                print(f"[STORYBOARD] 播放失败: {e}", flush=True)
        def _down_btn():
            u = play_ctx['url']
            if not (isinstance(u, str) and u.startswith('http')):
                print('[STORYBOARD] 下载取消：暂无URL', flush=True)
                return
            try:
                from PySide6.QtWidgets import QFileDialog
                import urllib.request
                target_dir = QFileDialog.getExistingDirectory(self, '选择保存目录')
                if not target_dir:
                    return
                name = Path(u.split('?')[0]).name or 'video.mp4'
                dst = Path(target_dir) / name
                print(f"[STORYBOARD] 下载视频: {u} -> {dst}", flush=True)
                urllib.request.urlretrieve(u, str(dst))
            except Exception as e:
                print(f"[STORYBOARD] 下载失败: {e}", flush=True)
        btn_play.clicked.connect(_play_btn)
        btn_down.clicked.connect(_down_btn)
        vb_l.addWidget(btn_play)
        vb_l.addWidget(btn_down)
        def _do_generate():
            try:
                prov = combo.currentText()
                text = (prompt.text() or '').strip() or 'make animate'
                host = self._host
                if host is None:
                    p = self.parent()
                    while p is not None and p.__class__.__name__ != 'VideoPage':
                        p = p.parent()
                    host = p
                if host is None:
                    print('[FRAME] 生成取消：未找到 VideoPage', flush=True)
                    return
                try:
                    gen_btn.setEnabled(False)
                    gen_btn.setText('生成中…')
                except Exception:
                    pass
                try:
                    print(f"[STORYBOARD] 生成开始: 帧={Path(img_path).name} provider={prov} prompt_len={len(text)}", flush=True)
                except Exception:
                    pass
                try:
                    def _on_video_url(url: str, gen=gen_btn, btn_p=btn_play, btn_d=btn_down, ctx=play_ctx):
                        try:
                            print(f"[STORYBOARD] 生成完成: 帧={Path(img_path).name} url={url}", flush=True)
                        except Exception:
                            pass
                        try:
                            if url:
                                if url not in self._video_urls:
                                    self._video_urls.append(url)
                                    if len(self._video_urls) > 0:
                                        self.btn_download_videos.setEnabled(True)
                        except Exception:
                            pass
                        try:
                            ctx['url'] = url
                            try:
                                gen.setEnabled(True)
                                gen.setText('视频重组')
                            except Exception:
                                pass
                            try:
                                btn_p.setEnabled(True)
                                btn_d.setEnabled(True)
                            except Exception:
                                pass
                        except Exception as e:
                            print(f"[STORYBOARD] 更新播放/下载按钮失败: {e}", flush=True)
                    host._video_url_signal.connect(_on_video_url)
                except Exception:
                    pass
                # 临时将分镜图作为API首帧，仅用于本次请求，不更新左侧首帧预览
                temp_first = None
                try:
                    import base64
                    with open(str(img_path), 'rb') as f:
                        data = f.read()
                    ext = os.path.splitext(str(img_path))[-1].lower()
                    mime = 'image/png'
                    if ext in ('.jpg', '.jpeg'):
                        mime = 'image/jpeg'
                    elif ext == '.webp':
                        mime = 'image/webp'
                    b64 = base64.b64encode(data).decode('utf-8')
                    temp_first = f'data:{mime};base64,{b64}'
                    print(f"[STORYBOARD] 临时首帧注入: len={len(temp_first)}", flush=True)
                except Exception as e:
                    print(f"[STORYBOARD] 临时首帧生成失败: {e}", flush=True)
                if prov == '万象2.5':
                    try:
                        host._update_status(host._i18n.get('use_wan', '使用 万象2.5 API 生成…'), 'loading')
                    except Exception:
                        pass
                    prev = getattr(host, '_first_image_b64', None)
                    try:
                        try:
                            host._suppress_storyboard_on_next_video = True
                        except Exception:
                            pass
                        try:
                            host._suppress_left_preview_on_next_video = True
                        except Exception:
                            pass
                        if temp_first:
                            host._first_image_b64 = temp_first
                        host._generate_wan25(text)
                    finally:
                        try:
                            host._first_image_b64 = prev
                        except Exception:
                            pass
                else:
                    try:
                        host._update_status(host._i18n.get('use_sora', '使用 Sora2 API 生成…'), 'loading')
                    except Exception:
                        pass
                    prev = getattr(host, '_first_image_b64', None)
                    try:
                        try:
                            host._suppress_storyboard_on_next_video = True
                        except Exception:
                            pass
                        try:
                            host._suppress_left_preview_on_next_video = True
                        except Exception:
                            pass
                        if temp_first:
                            host._first_image_b64 = temp_first
                        host._generate_sora2(text)
                    finally:
                        try:
                            host._first_image_b64 = prev
                        except Exception:
                            pass
                # 保持为按钮布局，无文字标签
                try:
                    print(f"[STORYBOARD] 已提交API请求: 帧={Path(img_path).name}", flush=True)
                except Exception:
                    pass
                # 兜底：轮询 VideoPage 的 _video_url，当出现时立即将“待生成”改为“播放/下载”
                try:
                    from PySide6.QtCore import QTimer
                    timer = QTimer(self)
                    timer.setInterval(800)
                    def _tick(btn_p=btn_play, btn_d=btn_down, ctx=play_ctx):
                        try:
                            u = getattr(host, '_last_storyboard_url', None) or getattr(host, '_video_url', None)
                            if isinstance(u, str) and u.startswith('http'):
                                timer.stop(); timer.deleteLater()
                                # 执行与信号回调一致的UI替换逻辑
                                ctx['url'] = u
                                try:
                                    gen_btn.setEnabled(True)
                                    gen_btn.setText('视频重组')
                                except Exception:
                                    pass
                                try:
                                    btn_p.setEnabled(True)
                                    btn_d.setEnabled(True)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    timer.timeout.connect(_tick)
                    timer.start()
                except Exception:
                    pass
            except Exception as e:
                print(f'[FRAME] 视频重组异常: {e}', flush=True)
        gen_btn.clicked.connect(_do_generate)
        ctrl_l.addWidget(prompt_box, stretch=0)
        ctrl_l.addWidget(api_box, stretch=0)
        ctrl_l.addWidget(video_box, stretch=0)
        row_item_l.addWidget(ctrl, stretch=1)
        self.grid.addWidget(row_item)

    def generate_from_local(self, video_path: str):
        """Generate storyboard frames from a local video path and render UI."""
        if not video_path:
            return
        try:
            # 记录当前视频路径，用于阈值调整时重新生成
            self._current_video_path = video_path
            
            # 先显示"处理中"，再进行耗时的 FFmpeg 处理
            self._show_processing('处理中…')
            try:
                QApplication.processEvents()
            except Exception:
                pass
            root = Path(os.getcwd())
            frames_root = root / 'frame'
            vid = Path(video_path)
            out_dir = frames_root / (vid.stem + '-scenes')
            frames = split_scenes_ffmpeg(str(vid), out_dir, threshold=self.threshold)
            self._frames = frames
            self._render_frames()
            try:
                self.btn_download.setEnabled(bool(self._frames))
            except Exception:
                pass
            print(f'[FRAME] 分镜生成完成: {len(frames)} 张 -> {out_dir}', flush=True)
        except Exception as e:
            print(f'[FRAME] 分镜生成异常: {e}', flush=True)

    def download_all_frames(self):
        """让用户选择目录并将所有分镜帧复制到该目录。"""
        # 若没有分镜帧则不进行任何操作
        if not self._frames:
            print('[FRAME] 下载取消: 当前没有分镜帧', flush=True)
            return
        try:
            target_dir = QFileDialog.getExistingDirectory(self, '选择保存目录')
        except Exception as e:
            print(f'[FRAME] 下载失败: 无法打开目录选择器 -> {e}', flush=True)
            return
        if not target_dir:
            print('[FRAME] 下载取消: 用户未选择目录', flush=True)
            return
        dst = Path(target_dir)
        try:
            dst.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f'[FRAME] 下载失败: 无法创建目录 -> {e}', flush=True)
            return
        total = len(self._frames)
        copied = 0
        for src in self._frames:
            try:
                shutil.copy2(src, dst / Path(src).name)
                copied += 1
            except Exception as e:
                print(f'[FRAME] 下载警告: 无法复制 {src} -> {e}', flush=True)
        print(f'[FRAME] 下载完成: {copied}/{total} 张 -> {dst}', flush=True)

    def download_all_videos(self):
        """下载所有已生成的视频到软件所在的 video 目录。"""
        urls = [u for u in self._video_urls if isinstance(u, str) and u]
        if not urls:
            print('[FRAME] 下载视频取消: 当前没有已生成的视频URL', flush=True)
            return
        root = Path(os.getcwd())
        from datetime import datetime
        now = datetime.now()
        date_dir = f"{now.year}-{now.month}-{now.day}"
        target_dir = root / 'video' / date_dir
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f'[FRAME] 下载视频失败: 无法创建 video 目录 -> {e}', flush=True)
            return
        import urllib.request
        saved = 0
        for i, url in enumerate(urls, start=1):
            try:
                # 生成文件名
                name = Path(url.split('?')[0]).name
                if not name:
                    name = f'video_{i}.mp4'
                dst = target_dir / name
                print(f'[FRAME] 下载视频: {url} -> {dst}', flush=True)
                urllib.request.urlretrieve(url, str(dst))
                saved += 1
            except Exception as e:
                print(f'[FRAME] 下载视频警告: {url} -> {e}', flush=True)
        print(f'[FRAME] 下载视频完成: {saved}/{len(urls)} 个 -> {target_dir}', flush=True)

    def generate_from_url(self, url: str):
        """Download to temp and generate frames. The temp file is deleted afterwards."""
        if not url:
            return
        import urllib.request
        try:
            # URL 下载与生成也先提示"处理中"
            self._show_processing('处理中…')
            try:
                QApplication.processEvents()
            except Exception:
                pass
            fd, tmp_path = tempfile.mkstemp(suffix='.mp4')
            os.close(fd)
            print(f'[FRAME] 正在临时下载视频以进行分镜: {url}', flush=True)
            urllib.request.urlretrieve(url, tmp_path)
            try:
                self.generate_from_local(tmp_path)
            finally:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
        except Exception as e:
            print(f'[FRAME] 从URL生成分镜失败: {e}', flush=True)

    def _render_frames(self):
        print('[FRAME] 调试: 进入 _render_frames()', flush=True)
        # 只清UI，不清数据，避免清空后 self._frames 变为 []
        self._clear_grid()
        # 如果没有分镜帧，显示提示文本，避免空白界面误解
        if not self._frames:
            print('[FRAME] 调试: 当前无分镜帧，显示"处理中…"占位', flush=True)
            lbl = QLabel('处理中…')
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet('color:#9aa0a6;')
            self.grid.addWidget(lbl)
            self.content.update()
            return
        frames = self._frames[:30]
        print(f'[FRAME] 调试: 开始渲染缩略图，共 {len(frames)} 张', flush=True)
        total = len(frames)
        for i, p in enumerate(frames):
            self._add_frame_thumb(p, is_first=(i == 0), is_last=(i == total - 1))
        
        # 添加底部弹簧，确保内容顶对齐
        self.grid.addStretch(1)

        # 刷新滚动内容确保立即可见
        try:
            self.content.adjustSize()
            self.content.update()
            print(f'[FRAME] 调试: 网格子控件数量 {self.grid.count()}', flush=True)
            # 强制刷新一次，避免生成后仍显示空白
            try:
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()
            except Exception:
                pass
        except Exception:
            pass
