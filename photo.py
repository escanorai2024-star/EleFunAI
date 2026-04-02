from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QFrame, QLabel, QPushButton,
    QTextEdit, QFileDialog, QListWidget, QListWidgetItem, QMenu,
    QSpinBox, QColorDialog, QComboBox, QSlider, QListView, QDialog,
    QProgressBar, QLineEdit, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QSize, QTimer, QEvent, QUrl, QMimeData, QFileSystemWatcher, QBuffer, QIODevice
from PySide6.QtGui import QPixmap, QIcon, QAction, QColor, QGuiApplication, QShortcut, QKeySequence
import ctypes
import time
from huaban import HuabanCanvas, Toolbar, PaintIconButton
from PySide6.QtCore import QSettings
import socket
import urllib.parse
from Layers import LayersPanel
import os
import subprocess
from pathlib import Path
import glob
import threading
import base64
import json
import urllib.request
import urllib.error
from datetime import datetime
from Agemini import get_config as gemini_get_config
from gemini30 import get_config as gemini30_get_config
from pngloading import GenerationDialog


class PhotoPage(QWidget):
    """
    按照示意图的图片创作工作区：
    - 左侧蓝色工具栏（含橡皮擦），中间红色面板区域（画板），右侧图层区域。
    - 顶端：参考图上传区域（若干缩略图） + 右侧提示词输入白色框与确定按钮。
    - 底部：生成图片区域（最近生成的5张，从左到右显示）。
    - 当点击"确定"时，读取设置里的图片API并触发占位调用。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PhotoPage")
        # 语言与翻译表
        self._lang_code = 'zh'
        self._i18n = self._get_i18n(self._lang_code)
        self.refs: list[str] = []  # 参考图路径
        self.recent_images: list[QPixmap] = []
        # 最近生成区最大数量设为 9，达到9张后生成第10张时清空重新开始
        self.recent_capacity: int = 9
        self._recent_cycle_index: int = 0  # 超过容量后按此索引循环替换

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 左侧：蓝色工具栏
        self.canvas = HuabanCanvas()
        # 连接画板上传到参考图的信号
        if hasattr(self.canvas, 'upload_to_ref_requested'):
             self.canvas.upload_to_ref_requested.connect(self.add_to_reference_from_layer)
             
        self.toolbar = Toolbar(self.canvas, parent=self)  # 显式传递 PhotoPage 作为父窗口
        root.addWidget(self.toolbar, stretch=0)

        # 中间：主区域（顶端上传+提示词，中间画板，底部最近生成）
        center = QFrame()
        center.setAttribute(Qt.WA_StyledBackground, True)
        center.setStyleSheet("background: #ffffff;")
        center_l = QVBoxLayout(center)
        center_l.setContentsMargins(0, 0, 0, 0)
        center_l.setSpacing(0)

        # 顶端条：左侧参考图上传（四个"+"按钮），右侧提示词输入白色框
        top_bar = QFrame()
        top_bar.setObjectName('TopBar')
        top_bar.setMinimumHeight(110)
        tb_l = QHBoxLayout(top_bar)
        tb_l.setContentsMargins(16, 8, 16, 8)
        tb_l.setSpacing(12)

        # 参考图上传缩略图区（四个"+"，点击各自上传，右键删除）
        thumb_bar = QFrame()
        th_l = QHBoxLayout(thumb_bar)
        th_l.setContentsMargins(0, 0, 0, 0)
        th_l.setSpacing(10)
        self.ref_buttons = []
        self.refs = [None, None, None, None]
        for i in range(4):
            btn = QPushButton('+')
            btn.setFixedSize(80, 60)
            btn.setStyleSheet('''
                QPushButton { background:#ffffff; color:#333333; border:1px dashed #d1d1d6; border-radius:8px; font-size:20px; }
                QPushButton:hover { background:#f2f2f7; border-color:#34A853; color:#34A853; }
            ''')
            btn.clicked.connect(lambda _, idx=i: self._add_reference_slot(idx))
            # 右键菜单：删除参考图
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, idx=i: self._ref_context_menu(idx, pos))
            self.ref_buttons.append(btn)
            th_l.addWidget(btn)

        # 右侧：提示词输入白色框 + 确定
        prompt_bar = QFrame(objectName='PromptPanel')
        # 统一卡片风格与阴影
        prompt_bar.setStyleSheet('#PromptPanel{ background:#ffffff; border:1px solid #e0e0e0; border-radius:12px; }')
        pp_shadow = QGraphicsDropShadowEffect(prompt_bar)
        pp_shadow.setBlurRadius(14)
        pp_shadow.setOffset(0, 2)
        from PySide6.QtGui import QColor as _QColor
        pp_shadow.setColor(_QColor(0,0,0,40))
        prompt_bar.setGraphicsEffect(pp_shadow)
        pb_l = QVBoxLayout(prompt_bar)
        pb_l.setContentsMargins(12, 10, 12, 10)
        pb_l.setSpacing(8)
        # 删除标题"图片描述"，仅保留输入框与按钮
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText(self._i18n['prompt_placeholder'])
        self.prompt_edit.setFixedHeight(72)
        self.prompt_edit.setStyleSheet('QTextEdit{ background:#f8f9fa; color:#202124; border:1px solid #dadce0; border-radius:8px; padding:8px 10px; font-size:14px; } QTextEdit:focus{ border:1px solid #4CAF50; background:#ffffff; }')
        self.btn_confirm = QPushButton(self._i18n['confirm'])
        self.btn_confirm.setMinimumWidth(80)
        self.btn_confirm.setFixedHeight(40)
        self.btn_confirm.clicked.connect(self._confirm_prompt)
        # 添加右键菜单支持
        self.btn_confirm.setContextMenuPolicy(Qt.CustomContextMenu)
        self.btn_confirm.customContextMenuRequested.connect(self._show_confirm_context_menu)
        row.addWidget(self.prompt_edit, stretch=1)
        row.addWidget(self.btn_confirm, stretch=0, alignment=Qt.AlignTop)
        pb_l.addLayout(row)

        tb_l.addWidget(thumb_bar, stretch=0)
        tb_l.addWidget(prompt_bar, stretch=1)

        # 中间画板区域（白色背景）
        self.canvas_wrap = QFrame()
        self.canvas_wrap.setObjectName('CanvasWrap')
        self.canvas_wrap.setAttribute(Qt.WA_StyledBackground, True)
        cw_l = QVBoxLayout(self.canvas_wrap)
        cw_l.setContentsMargins(16, 12, 16, 12)
        cw_l.setSpacing(8)

        # 工具设置条（位于红色区域）
        tool_settings = QFrame(objectName='ToolSettings')
        ts_l = QHBoxLayout(tool_settings)
        ts_l.setContentsMargins(8, 6, 8, 6)
        ts_l.setSpacing(8)
        # 画笔大小（滑块，1-100，默认10）
        self.lbl_brush_size = QLabel(self._i18n['brush_size'])
        ts_l.addWidget(self.lbl_brush_size)
        self.slider_brush = QSlider(Qt.Horizontal)
        self.slider_brush.setRange(1, 100)
        self.slider_brush.setValue(10)
        self.slider_brush.valueChanged.connect(lambda v: setattr(self.canvas, 'brush_size', v))
        self.slider_brush.setFixedWidth(160)
        ts_l.addWidget(self.slider_brush)
        # 颜色调色板（常用色 + 更多）
        self.lbl_color = QLabel(self._i18n['color'])
        ts_l.addWidget(self.lbl_color)
        for hex_color in ['#ffffff', '#000000', '#ff3b30', '#0f5bf1', '#34c759']:
            btn = QPushButton()
            btn.setFixedSize(24, 24)
            btn.setStyleSheet(f'background:{hex_color}; border:1px solid #d1d1d6; border-radius:4px;')
            btn.clicked.connect(lambda _, c=hex_color: setattr(self.canvas, 'brush_color', QColor(c)))
            ts_l.addWidget(btn)
        self.btn_more_colors = QPushButton(self._i18n['more_colors'])
        self.btn_more_colors.clicked.connect(self._pick_color)
        ts_l.addWidget(self.btn_more_colors)

        # 吸管工具已移动至左侧工具栏，此处不再放置按钮

        ts_l.addSpacing(12)
        # 画板尺寸预设比例下拉
        self.lbl_ratio = QLabel(self._i18n['canvas_ratio'])
        ts_l.addWidget(self.lbl_ratio)
        self.combo_ratio = QComboBox()
        self.combo_ratio.addItems(['16:9', '9:16', '1:1', '4:3', '3:4', '21:9'])
        self.combo_ratio.currentIndexChanged.connect(self._apply_canvas_size)
        ts_l.addWidget(self.combo_ratio)
        self.btn_apply_ratio = QPushButton(self._i18n['apply'])
        self.btn_apply_ratio.clicked.connect(self._apply_canvas_size)
        ts_l.addWidget(self.btn_apply_ratio)

        cw_l.addWidget(tool_settings)
        # 画板 + 快捷区并排
        canvas_row = QFrame()
        cr_l = QHBoxLayout(canvas_row)
        cr_l.setContentsMargins(0, 0, 0, 0)
        cr_l.setSpacing(12)
        # 画板居中
        cr_l.addWidget(self.canvas, stretch=1, alignment=Qt.AlignCenter)

        # 快捷区：PS/AN/AE（每行2列、无间距、顶端开始；背景与边框移除）
        self.quick_panel = QFrame(objectName='QuickPanel')
        
        # 添加阴影
        qp_shadow = QGraphicsDropShadowEffect(self.quick_panel)
        qp_shadow.setBlurRadius(15)
        qp_shadow.setColor(QColor(0, 0, 0, 20))
        qp_shadow.setOffset(0, 2)
        self.quick_panel.setGraphicsEffect(qp_shadow)
        
        self.quick_panel.setStyleSheet('#QuickPanel { background: transparent; border: none; } QToolButton{border:none;background:transparent;padding:6px;margin:0;border-radius:10px;} QToolButton:hover{background:rgba(52,199,89,0.15);} QToolButton:pressed{background:rgba(52,199,89,0.25);}')
        qp_l = QGridLayout(self.quick_panel)
        qp_l.setContentsMargins(0, 0, 0, 0)
        qp_l.setSpacing(0)
        self.quick_panel.setFixedWidth(120)

        def make_adobe_icon(tag: str) -> QIcon:
            """绘制接近 Adobe 风格的矢量图标：白色圆角底 + 品牌色字母，适应白色主题。"""
            size = 48
            pm = QPixmap(size, size)
            pm.fill(Qt.transparent)
            from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing, True)
            brand = {
                'ps': {'fg': '#001E36', 'text': 'Ps'}, # Ps brand color is usually blue, but here we use dark blue for text? Or keep original fg?
                'ae': {'fg': '#470F6F', 'text': 'Ae'}, # Ae is purple
                'an': {'fg': '#D84606', 'text': 'An'}, # An is orange
                'bl': {'fg': '#E87D0D', 'text': 'Bl'}, # Blender orange
                'kr': {'fg': '#3DAEE9', 'text': 'Kr'}, # Krita blue
                'cta': {'fg': '#5BC3F5', 'text': 'CTA'}, # CTA blue
            }
            # Use original logic but override colors for white theme
            # Original logic: 'ps': {'bg': '#001E36', 'fg': '#31A8FF', 'text': 'Ps'}
            # We want white bg, and 'fg' or 'bg' color for text? 
            # Usually Adobe icons are: Dark Box + Colored Text (2 letters).
            # To match "white theme", maybe: White Box + Colored Text?
            # Let's use the original 'fg' (the bright color) for the text, and white for bg.
            
            brand_colors = {
                'ps': '#31A8FF',
                'ae': '#CF9FFF',
                'an': '#FF7C1F',
                'bl': '#FF8C00',
                'kr': '#FF5CA9',
                'cta': '#FF6A00',
            }
            # Default fallback
            color_code = brand_colors.get(tag, '#333333')
            text_str = tag.upper()
            if tag in ['ps', 'ae', 'an', 'bl', 'kr', 'cta']:
                 # Re-map text if needed, but tag.upper() is mostly fine, except 'CTA'
                 if tag == 'cta': text_str = 'CTA'
                 elif tag == 'ps': text_str = 'Ps'
                 elif tag == 'ae': text_str = 'Ae'
                 elif tag == 'an': text_str = 'An'
                 elif tag == 'bl': text_str = 'Bl'
                 elif tag == 'kr': text_str = 'Kr'
            
            bg = QColor('#ffffff')
            fg = QColor(color_code)
            
            rect = pm.rect()
            p.setBrush(QBrush(bg))
            # Add a light border
            p.setPen(QPen(QColor('#e0e0e0'), 1))
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 10, 10)
            
            p.setPen(fg)
            # 字体略加粗并居中
            font = QFont('Segoe UI', 20, QFont.DemiBold)
            font.setLetterSpacing(QFont.PercentageSpacing, 100)
            p.setFont(font)
            p.drawText(rect, Qt.AlignCenter, text_str)
            p.end()
            return QIcon(pm)

        from PySide6.QtWidgets import QToolButton
        # 按每行2列排列：PS/AN → AE/BL → KR/CTA
        self.btn_ps = QToolButton(text='Ps')
        self.btn_ps.setIcon(make_adobe_icon('ps'))
        self.btn_ps.setIconSize(QSize(48, 48))
        self.btn_ps.setFixedSize(QSize(48, 48))
        self.btn_ps.setAutoRaise(True)
        self.btn_ps.setFocusPolicy(Qt.NoFocus)
        self.btn_ps.setToolTip(self._i18n['send_to_photoshop'])
        self.btn_ps.clicked.connect(self._send_to_photoshop)
        qp_l.addWidget(self.btn_ps, 0, 0)

        self.btn_an = QToolButton(text='An')
        self.btn_an.setIcon(make_adobe_icon('an'))
        self.btn_an.setIconSize(QSize(48, 48))
        self.btn_an.setFixedSize(QSize(48, 48))
        self.btn_an.setAutoRaise(True)
        self.btn_an.setFocusPolicy(Qt.NoFocus)
        self.btn_an.setToolTip(self._i18n['send_to_animate'])
        self.btn_an.clicked.connect(lambda: self._send_canvas_to_app('an'))
        qp_l.addWidget(self.btn_an, 0, 1)

        self.btn_ae = QToolButton(text='Ae')
        self.btn_ae.setIcon(make_adobe_icon('ae'))
        self.btn_ae.setIconSize(QSize(48, 48))
        self.btn_ae.setFixedSize(QSize(48, 48))
        self.btn_ae.setAutoRaise(True)
        self.btn_ae.setFocusPolicy(Qt.NoFocus)
        self.btn_ae.setToolTip(self._i18n['send_to_after_effects'])
        self.btn_ae.clicked.connect(lambda: self._send_canvas_to_app('ae'))
        qp_l.addWidget(self.btn_ae, 1, 0)

        # Blender 快捷按钮
        self.btn_bl = QToolButton(text='Bl')
        self.btn_bl.setIcon(make_adobe_icon('bl'))
        self.btn_bl.setIconSize(QSize(48, 48))
        self.btn_bl.setFixedSize(QSize(48, 48))
        self.btn_bl.setAutoRaise(True)
        self.btn_bl.setFocusPolicy(Qt.NoFocus)
        self.btn_bl.setToolTip(self._i18n['send_to_blender'])
        self.btn_bl.clicked.connect(self._start_blender_capture)
        qp_l.addWidget(self.btn_bl, 1, 1)

        # 新增：Krita、CTA5 按钮
        self.btn_kr = QToolButton(text='Kr')
        self.btn_kr.setIcon(make_adobe_icon('kr'))
        self.btn_kr.setIconSize(QSize(48, 48))
        self.btn_kr.setFixedSize(QSize(48, 48))
        self.btn_kr.setAutoRaise(True)
        self.btn_kr.setFocusPolicy(Qt.NoFocus)
        self.btn_kr.setToolTip(self._i18n['send_to_krita'])
        self.btn_kr.clicked.connect(self._send_to_krita)
        qp_l.addWidget(self.btn_kr, 2, 0)

        self.btn_cta = QToolButton(text='CTA')
        self.btn_cta.setIcon(make_adobe_icon('cta'))
        self.btn_cta.setIconSize(QSize(48, 48))
        self.btn_cta.setFixedSize(QSize(48, 48))
        self.btn_cta.setAutoRaise(True)
        self.btn_cta.setFocusPolicy(Qt.NoFocus)
        self.btn_cta.setToolTip(self._i18n['send_to_cartoon_animator'])
        self.btn_cta.clicked.connect(lambda: self._send_canvas_to_app('cta'))
        qp_l.addWidget(self.btn_cta, 2, 1)
        # 顶端开始：增加下方伸展项以压顶
        qp_l.setRowStretch(3, 1)

        cr_l.addWidget(self.quick_panel, stretch=0)

        cw_l.addWidget(canvas_row, stretch=1)

        # 初次进入页面时默认应用比例（具体触发在 MainWindow 中）
        QTimer.singleShot(0, self._apply_canvas_size)

        # 监听容器尺寸变化，首次进入创建页后按容器可用区域应用尺寸
        self._initial_canvas_applied = False
        self.canvas_wrap.installEventFilter(self)

        # 底部绿色条：最近生成的图片预览（可按百分比精确控制高度）
        bottom_bar = QFrame()
        bottom_bar.setObjectName('BottomBar')
        # 初始高度仅作占位，后续按百分比自适应
        bottom_bar.setFixedHeight(240)
        bb_l = QHBoxLayout(bottom_bar)
        bb_l.setContentsMargins(16, 14, 16, 14)
        bb_l.setSpacing(14)
        self.recent_list = RecentListWidget()
        self.recent_list.setViewMode(QListWidget.IconMode)
        self.recent_list.setFlow(QListView.LeftToRight)
        self.recent_list.setWrapping(False)  # 单行显示，避免超出红框高度
        self.recent_list.setMovement(QListView.Static)
        self.recent_list.setIconSize(QSize(120, 120))
        self.recent_list.setResizeMode(QListWidget.Adjust)
        self.recent_list.setSpacing(8)
        self.recent_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.recent_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.recent_list.setFixedHeight(200)
        # 预设栅格尺寸，后续根据高度自适应更新
        self.recent_list.setGridSize(QSize(136, 136))
        # 左键在程序内预览图片；右键菜单发送到画板
        self.recent_list.itemClicked.connect(self._open_recent)
        self.recent_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.recent_list.customContextMenuRequested.connect(self._recent_context_menu)
        bb_l.addWidget(self.recent_list, stretch=1)
        # 取消右侧空白拉伸，使缩略图区域与右侧图层栏对齐

        center_l.addWidget(top_bar)
        center_l.addWidget(self.canvas_wrap, stretch=1)
        center_l.addWidget(bottom_bar)

        # 按百分比控制 bottom 区域高度所需的引用与默认比例
        self.center = center
        self.bottom_bar = bottom_bar
        self.bottom_percent = 0.18  # 默认占 center 高度的 18%，贴近红框
        self.bottom_rows_target = 1   # 单行显示
        # 监听 center 尺寸变化以实时应用百分比高度
        self.center.installEventFilter(self)

        root.addWidget(center, stretch=1)

        # 右侧：图层区域改为 LayersPanel（迁移至 Layers.py）
        self.layers_panel = LayersPanel(self.canvas)
        root.addWidget(self.layers_panel, stretch=0)

        # 初始化 Blender 集成
        try:
            from fastblender import BlenderIntegration
            self._blender_integration = BlenderIntegration(self.layers_panel)
        except Exception as e:
            print(f'[FastBlender] 初始化失败: {e}', flush=True)
            self._blender_integration = None
        
        # 初始化 Krita 集成
        try:
            from krita import KritaIntegration
            self._krita_integration = KritaIntegration(self)
        except Exception as e:
            print(f'[Krita] 初始化失败: {e}', flush=True)
            self._krita_integration = None
        
        # 初始化 Photoshop 集成
        try:
            from ps import PhotoshopIntegration
            self._ps_integration = PhotoshopIntegration(self)
        except Exception as e:
            print(f'[Photoshop] 初始化失败: {e}', flush=True)
            self._ps_integration = None

        # 连接画板选区右键"魔法生成"信号
        try:
            if hasattr(self.canvas, 'magic_generate_requested'):
                self.canvas.magic_generate_requested.connect(self._on_canvas_magic_generate)
            if hasattr(self.canvas, 'smart_generate_requested'):
                self.canvas.smart_generate_requested.connect(self._on_canvas_smart_generate)
            if hasattr(self.canvas, 'smart_edit_requested'):
                self.canvas.smart_edit_requested.connect(self._on_canvas_smart_edit)
            if hasattr(self.canvas, 'smart_region_edit_requested'):
                self.canvas.smart_region_edit_requested.connect(self._on_canvas_smart_region_edit)
            if hasattr(self.canvas, 'smart_replace_requested'):
                self.canvas.smart_replace_requested.connect(self._on_canvas_smart_replace)
        except Exception:
            pass

        # 首次进入创建页时，自动添加一个名为"默认"的图层并设为当前绘制图层
        try:
            if not self.canvas.layers:
                self.layers_panel.add_blank_named_layer('默认')
        except Exception:
            pass

        # 恢复参考图持久化记录
        try:
            self._restore_references()
        except Exception:
            pass

        # 撤销快捷键：Ctrl+Z
        try:
            self.shortcut_undo = QShortcut(QKeySequence('Ctrl+Z'), self)
            self.shortcut_undo.activated.connect(self._undo_canvas)
        except Exception:
            pass

        self.setStyleSheet(
            """
            #TopBar { background:#f5f5f7; border-bottom: 1px solid #e0e0e0; }
            #CanvasWrap { background: qradialgradient(cx:0.5, cy:0.5, radius:0.92, fx:0.5, fy:0.5, stop:0 #ffffff, stop:0.6 #f2f4f7, stop:1 #e6eaef); }
            #ToolSettings { background:#ffffff; border:1px solid #e0e0e0; border-radius:8px; }
            #QuickPanel { background:#ffffff; border:1px solid #e0e0e0; border-radius:12px; }
            #BottomBar { background:#f5f5f7; border-top: 1px solid #e0e0e0; }
            #RightLayers { background:#ffffff; color:#333333; border-left: 1px solid #e0e0e0; }
            QListWidget { background:#ffffff; color:#333333; border:1px solid #e0e0e0; border-radius:8px; }
            QListWidget::item { border-radius: 4px; padding: 4px; }
            QListWidget::item:selected { background: rgba(52, 199, 89, 0.2); color: #333333; border: 1px solid rgba(52, 199, 89, 0.5); }
            QListWidget::item:hover { background: rgba(0, 0, 0, 0.05); }
            QPushButton { background:#ffffff; color:#333333; border:1px solid #d1d1d6; border-radius:6px; padding:6px 12px; }
            QPushButton:hover { background:#f2f2f7; border-color:#34c759; color:#34c759; }
            QPushButton:pressed { background:rgba(52, 199, 89, 0.2); border-color:#34c759; }
            #PromptPanel { background:#ffffff; border:1px solid #e0e0e0; border-radius:10px; }
            QTextEdit { background:#ffffff; color:#333333; border:1px solid #e0e0e0; border-radius:8px; selection-background-color: #34c759; selection-color: #ffffff; }
            QLabel { color:#333333; font-weight: 500; }
            QSlider::groove:horizontal { border: 1px solid #d1d1d6; height: 4px; background: #e5e5ea; margin: 0px; border-radius: 2px; }
            QSlider::handle:horizontal { background: #ffffff; border: 1px solid #d1d1d6; width: 16px; height: 16px; margin: -7px 0; border-radius: 8px; }
            QSlider::handle:horizontal:hover { border-color: #34c759; }
            QComboBox { background: #ffffff; color: #333333; border: 1px solid #d1d1d6; border-radius: 6px; padding: 4px; }
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow { image: none; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 5px solid #666666; margin-right: 6px; }
            """
        )

        # 首次进入时按百分比应用一次底部区域高度
        QTimer.singleShot(0, self._apply_bottom_area_size)

    def _undo_canvas(self):
        try:
            self.canvas.undo()
            # 同步右侧图层UI
            self.layers_panel.sync_from_canvas()
        except Exception:
            pass

    def _add_reference_slot(self, index: int):
        path, _ = QFileDialog.getOpenFileName(self, '选择参考图', '', 'Images (*.png *.jpg *.jpeg *.bmp)')
        if not path:
            return
        self.refs[index] = path
        btn = self.ref_buttons[index]
        pix = QPixmap(path).scaled(btn.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        btn.setText('')
        btn.setIcon(QIcon(pix))
        btn.setIconSize(btn.size())
        btn.setToolTip(path)
        # 持久化更新
        try:
            self._persist_references()
        except Exception:
            pass

    def _show_confirm_context_menu(self, pos):
        """智能生成按钮的右键菜单"""
        menu = QMenu(self)
        
        act_normal = menu.addAction('智能生成（正常模式）')
        act_smart_edit = menu.addAction('智能修改（仅修改选区）')
        
        act_normal.triggered.connect(self._confirm_prompt)
        act_smart_edit.triggered.connect(self._confirm_smart_edit)
        
        menu.exec(self.btn_confirm.mapToGlobal(pos))
    
    def _confirm_smart_edit(self):
        """智能修改：只修改画板上现有的绿色选区内容"""
        try:
            from PySide6.QtWidgets import QMessageBox
            from PySide6.QtCore import QSettings
            
            # 读取提示词
            prompt = self.prompt_edit.toPlainText().strip()
            if not prompt:
                QMessageBox.warning(self, '提示词为空', '请输入修改提示词')
                return
            
            # 检查画板是否有选区
            if not hasattr(self.canvas, 'selection_rect') or self.canvas.selection_rect is None:
                QMessageBox.warning(self, '未找到选区', '请先使用自动选区工具点击物体，生成绿色选区')
                return
            
            rect = self.canvas.selection_rect
            mask = getattr(self.canvas, 'selection_mask', None)
            
            if mask is None:
                QMessageBox.warning(self, '选区无效', '未找到有效的选区遮罩')
                return
            
            self._debug('[智能修改] 开始处理...')
            self._debug(f'[智能修改] 选区范围: {rect.x()},{rect.y()} {rect.width()}x{rect.height()}')
            self._debug(f'[智能修改] 用户提示词: {prompt}')
            
            # 获取画板合成图
            composite_img = self.canvas._composite_to_image()
            composite_pix = QPixmap.fromImage(composite_img)
            
            # 创建带绿色高亮的参考图
            reference_pix = self._create_reference_image(composite_pix, rect, mask)
            
            # 保存参考图到临时文件
            try:
                from pathlib import Path
                import tempfile
                temp_dir = Path(tempfile.gettempdir())
                ref_path = temp_dir / 'smart_edit_reference.png'
                reference_pix.save(str(ref_path), 'PNG')
                self._debug(f'[智能修改] 参考图已保存: {ref_path}')
                
                # 设置为参考图
                if not hasattr(self, 'refs') or not isinstance(self.refs, list):
                    self.refs = [None, None, None, None]
                while len(self.refs) < 4:
                    self.refs.append(None)
                self.refs[3] = str(ref_path)
                
                self._debug(f'[智能修改] 参考图已设置为 refs[3]')
            except Exception as e:
                self._debug(f'[智能修改] 保存参考图失败: {e}')
            
            # 保存智能修改上下文
            try:
                self._smart_edit_mode = True
                self._smart_rect = rect
                self._smart_mask = mask
                self._smart_original_pix = composite_pix
            except Exception:
                pass
            
            # 构建完整提示词：强调只修改绿色选区
            combined_prompt = f"{prompt}。重要：请只修改图中绿色半透明高亮区域内的物体，保持其他区域（包括背景）完全不变。"
            
            provider = QSettings('GhostOS', 'App').value('api/image_provider', 'Gemini')
            
            self._debug(f'[智能修改] 完整提示词: {combined_prompt}')
            self._debug(f'[智能修改] 使用API提供方: {provider}')
            
            # 更新状态
            try:
                self._update_conn_status('智能修改中...', 'loading')
            except Exception:
                pass
            
            # 发起生成
            self._dispatch_generate(combined_prompt, provider)
            
        except Exception as e:
            self._debug(f'[智能修改] 错误: {e}')
            import traceback
            self._debug(traceback.format_exc())
            QMessageBox.warning(self, '智能修改失败', f'处理失败：{str(e)}')

    def _confirm_prompt(self):
        # 兼容 QTextEdit：读取纯文本
        prompt = self.prompt_edit.toPlainText().strip()
        if not prompt:
            return
        provider = QSettings('GhostOS', 'App').value('api/image_provider', 'Gemini')
        # Debug：记录用户输入与提供方
        try:
            self._debug(f"confirm: provider={provider}, prompt_len={len(prompt)}")
            # 追加：在 DEBUG 输出中包含提示词（截断避免过长）
            snippet = (prompt[:200] + ('...' if len(prompt) > 200 else ''))
            self._debug(f"prompt: {snippet}")
        except Exception:
            pass
        # 在左下角状态区域提示开始生成
        try:
            self._update_conn_status('开始生成…', 'loading')
        except Exception:
            pass
        # 不弹出生成进度窗口，直接异步生成并将结果写入底部"最近生成"区域
        self._dispatch_generate(prompt, provider)

    def _on_canvas_magic_generate(self, rect):
        """在选区右键触发魔法生成：弹出提示词输入窗，组合隐藏输入并发起生成。"""
        # 弹窗收集提示词
        adv_flag = False
        try:
            adv_flag = getattr(self.canvas, '_adv_magic_pending', False)
        except Exception:
            adv_flag = False
        dlg = QDialog(self)
        dlg.setWindowTitle('高级魔法生成' if adv_flag else '魔法生成')
        dlg.setMinimumWidth(400)
        lay = QVBoxLayout(dlg)
        lbl = QLabel('请输入提示词：')
        lay.addWidget(lbl)
        inp = QTextEdit()
        inp.setPlaceholderText('描述你想要生成的内容...')
        inp.setFixedHeight(80)
        inp.setStyleSheet('QTextEdit{ background:#f8f9fa; color:#202124; border:1px solid #dadce0; border-radius:8px; padding:8px 10px; font-size:14px; } QTextEdit:focus{ border:1px solid #4CAF50; background:#ffffff; }')
        lay.addWidget(inp)
        # 隐藏输入框，预置为"修改绿色方框内的内容"
        hidden = QLineEdit('修改绿色方框内的内容')
        hidden.setVisible(False)
        lay.addWidget(hidden)
        row = QHBoxLayout()
        btn_ok = QPushButton('确定')
        btn_cancel = QPushButton('取消')
        row.addWidget(btn_ok)
        row.addWidget(btn_cancel)
        lay.addLayout(row)
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok.clicked.connect(dlg.accept)
        if not dlg.exec():
            return
        user_prompt = (inp.toPlainText() or '').strip()
        # 组合用户提示词与隐藏提示
        combined = (user_prompt + ('，' if user_prompt else '') + hidden.text()).strip()
        provider = QSettings('GhostOS', 'App').value('api/image_provider', 'Gemini')
        # 记录 ROI（不展示进度对话框）
        try:
            self._roi_rect = rect
            self._magic_mode = True
            adv = bool(adv_flag)
            try:
                setattr(self.canvas, '_adv_magic_pending', False)
            except Exception:
                pass
            self._magic_advanced = adv
        except Exception:
            pass
        # 发起生成
        self._dispatch_generate(combined, provider)

    def _on_canvas_smart_region_edit(self, rect):
        """智能区域修改：从画板右键矩形选区触发，只修改矩形区域内容
        
        与智能修改的关键区别：
        - 智能修改：使用自动选区工具（SAM模型）生成不规则遮罩
        - 智能区域修改：使用矩形框选，遮罩为整个矩形区域
        
        共同点：都提交完整画布图 + 带绿色遮罩的参考图到API
        """
        try:
            from PySide6.QtGui import QImage, QPainter
            from PySide6.QtWidgets import QMessageBox
            from PySide6.QtCore import QSettings
            
            # 弹出提示词输入窗
            dlg = QDialog(self)
            dlg.setWindowTitle('智能区域修改')
            dlg.setMinimumWidth(400)
            lay = QVBoxLayout(dlg)
            
            # 说明标签
            info_lbl = QLabel('请输入修改提示词，AI将只修改框选的绿色矩形区域内容，保持其他区域不变')
            info_lbl.setWordWrap(True)
            info_lbl.setStyleSheet("color: #666; font-size: 11px; padding: 8px;")
            lay.addWidget(info_lbl)
            
            # 提示词输入
            lbl = QLabel('提示词：')
            lay.addWidget(lbl)
            inp = QTextEdit()
            inp.setPlaceholderText('描述你想要的修改...')
            inp.setFixedHeight(80)
            inp.setStyleSheet('QTextEdit{ background:#f8f9fa; color:#202124; border:1px solid #dadce0; border-radius:8px; padding:8px 10px; font-size:14px; } QTextEdit:focus{ border:1px solid #4CAF50; background:#ffffff; }')
            lay.addWidget(inp)
            
            # 按钮
            row = QHBoxLayout()
            btn_ok = QPushButton('开始修改')
            btn_cancel = QPushButton('取消')
            row.addWidget(btn_ok)
            row.addWidget(btn_cancel)
            lay.addLayout(row)
            
            btn_cancel.clicked.connect(dlg.reject)
            btn_ok.clicked.connect(dlg.accept)
            
            if not dlg.exec():
                return
            
            user_prompt = (inp.toPlainText() or '').strip()
            if not user_prompt:
                QMessageBox.warning(self, '提示词为空', '请输入修改提示词')
                return
            
            # 获取画板合成图（完整画布）
            composite_img = self.canvas._composite_to_image()
            composite_pix = QPixmap.fromImage(composite_img)
            
            # 检查选区
            if rect is None:
                QMessageBox.warning(self, '选区无效', '未找到有效的选区')
                return
            
            self._debug('[智能区域修改] 开始处理...')
            self._debug(f'[智能区域修改] 画布尺寸: {composite_pix.width()}x{composite_pix.height()}')
            self._debug(f'[智能区域修改] 选区范围: {rect.x()},{rect.y()} {rect.width()}x{rect.height()}')
            self._debug(f'[智能区域修改] 用户提示词: {user_prompt}')
            
            # 创建矩形区域的遮罩（全选矩形内的所有像素）
            import numpy as np
            mask_h = rect.height()
            mask_w = rect.width()
            # 创建全True的遮罩，表示整个矩形区域都需要修改
            region_mask = np.ones((mask_h, mask_w), dtype=bool)
            
            self._debug(f'[智能区域修改] 遮罩尺寸: {mask_w}x{mask_h}')
            
            # 创建带绿色半透明矩形高亮的参考图（完整画布 + 绿色遮罩）
            # 这个参考图会和完整画布一起提交给API
            reference_pix = self._create_reference_image_for_rect(composite_pix, rect)
            
            # 将参考图保存到临时文件，并设置为第4张参考图
            try:
                from pathlib import Path
                import tempfile
                temp_dir = Path(tempfile.gettempdir())
                ref_path = temp_dir / 'smart_region_edit_reference.png'
                reference_pix.save(str(ref_path), 'PNG')
                self._debug(f'[智能区域修改] 参考图（带绿色遮罩）已保存: {ref_path}')
                
                # 将参考图设置为第4张参考图（refs[3]），供 Gemini 作为 sketch 使用
                if not hasattr(self, 'refs') or not isinstance(self.refs, list):
                    self.refs = [None, None, None, None]
                while len(self.refs) < 4:
                    self.refs.append(None)
                self.refs[3] = str(ref_path)
                
                self._debug(f'[智能区域修改] 参考图已设置为 refs[3]')
            except Exception as e:
                self._debug(f'[智能区域修改] 保存参考图失败: {e}')
            
            # 保存智能区域修改上下文（使用与智能修改相同的标记）
            # 这样在 _on_generate_done 中会走相同的处理逻辑
            try:
                self._smart_edit_mode = True
                self._smart_rect = rect
                self._smart_mask = region_mask
                self._smart_original_pix = composite_pix
                self._debug(f'[智能区域修改] 已保存上下文: smart_edit_mode=True')
            except Exception as e:
                self._debug(f'[智能区域修改] 保存上下文失败: {e}')
            
            # 构建完整提示词：明确指出参考图位置和要求
            combined_prompt = f"""请根据参考图（带有绿色半透明矩形标记的图片）进行修改：

**修改要求**：
1. 只修改绿色矩形区域内的内容为：{user_prompt}
2. 参考图中绿色矩形标记仅用于指示修改区域，请在最终结果中移除绿色标记
3. 修改后的内容必须与周围环境自然融合，确保：
   - 光照方向和强度一致
   - 色调和饱和度匹配
   - 边缘无缝衔接，无明显分界线
   - 透视角度与整体画面协调
4. 绿色矩形外的所有区域（人物、背景、物体等）保持完全不变
5. 保持原图的整体艺术风格、氛围和质感
6. 最终效果应该看起来像原本就存在的场景，而不是后期合成"""
            
            provider = QSettings('GhostOS', 'App').value('api/image_provider', 'Gemini')
            
            self._debug(f'[智能区域修改] 完整提示词: {combined_prompt}')
            self._debug(f'[智能区域修改] 使用API提供方: {provider}')
            self._debug(f'[智能区域修改] 提交内容: 完整画布图 + 带绿色遮罩的参考图')
            
            # 更新状态
            try:
                self._update_conn_status('智能区域修改中...', 'loading')
            except Exception:
                pass
            
            # 发起生成（会提交完整画布 + refs[3]参考图到API）
            self._dispatch_generate(combined_prompt, provider)
            
        except Exception as e:
            self._debug(f'[智能区域修改] 错误: {e}')
            import traceback
            self._debug(traceback.format_exc())
            QMessageBox.warning(self, '智能区域修改失败', f'处理失败：{str(e)}')
    
    def _create_reference_image_for_rect(self, base_pix: QPixmap, rect) -> QPixmap:
        """创建带绿色半透明矩形高亮的参考图，用于智能区域修改"""
        try:
            from PySide6.QtGui import QImage, QPainter, QColor
            
            # 复制基础图
            result = base_pix.copy()
            
            # 在上面绘制半透明绿色矩形
            painter = QPainter(result)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.fillRect(rect, QColor(52, 199, 89, 100))  # 绿色半透明
            painter.end()
            
            return result
            
        except Exception as e:
            self._debug(f'[智能区域修改] 创建参考图失败: {e}')
            return base_pix

    def _on_canvas_smart_edit(self, rect, mask):
        """智能修改：从画板右键触发，弹出提示词输入窗，只修改选区内容"""
        try:
            from PySide6.QtGui import QImage, QPainter
            from PySide6.QtWidgets import QMessageBox
            from PySide6.QtCore import QSettings
            
            # 弹出提示词输入窗
            dlg = QDialog(self)
            dlg.setWindowTitle('智能修改')
            dlg.setMinimumWidth(400)
            lay = QVBoxLayout(dlg)
            
            # 说明标签
            info_lbl = QLabel('请输入修改提示词，AI将只修改绿色选区内的内容，保持其他区域不变')
            info_lbl.setWordWrap(True)
            info_lbl.setStyleSheet("color: #666; font-size: 11px; padding: 8px;")
            lay.addWidget(info_lbl)
            
            # 提示词输入
            lbl = QLabel('提示词：')
            lay.addWidget(lbl)
            inp = QTextEdit()
            inp.setPlaceholderText('描述你想要的修改...')
            inp.setFixedHeight(80)
            inp.setStyleSheet('QTextEdit{ background:#f8f9fa; color:#202124; border:1px solid #dadce0; border-radius:8px; padding:8px 10px; font-size:14px; } QTextEdit:focus{ border:1px solid #4CAF50; background:#ffffff; }')
            lay.addWidget(inp)
            
            # 按钮
            row = QHBoxLayout()
            btn_ok = QPushButton('开始修改')
            btn_cancel = QPushButton('取消')
            row.addWidget(btn_ok)
            row.addWidget(btn_cancel)
            lay.addLayout(row)
            
            btn_cancel.clicked.connect(dlg.reject)
            btn_ok.clicked.connect(dlg.accept)
            
            if not dlg.exec():
                return
            
            user_prompt = (inp.toPlainText() or '').strip()
            if not user_prompt:
                QMessageBox.warning(self, '提示词为空', '请输入修改提示词')
                return
            
            # 获取画板合成图
            composite_img = self.canvas._composite_to_image()
            composite_pix = QPixmap.fromImage(composite_img)
            
            # 提取选区内容和遮罩
            if mask is None or rect is None:
                QMessageBox.warning(self, '选区无效', '未找到有效的选区遮罩')
                return
            
            self._debug('[智能修改] 开始处理...')
            self._debug(f'[智能修改] 选区范围: {rect.x()},{rect.y()} {rect.width()}x{rect.height()}')
            self._debug(f'[智能修改] 用户提示词: {user_prompt}')
            
            # 创建带绿色高亮的参考图，帮助AI理解选区位置
            reference_pix = self._create_reference_image(composite_pix, rect, mask)
            
            # 将参考图保存到临时文件，并设置为第4张参考图
            try:
                from pathlib import Path
                import tempfile
                temp_dir = Path(tempfile.gettempdir())
                ref_path = temp_dir / 'smart_edit_reference.png'
                reference_pix.save(str(ref_path), 'PNG')
                self._debug(f'[智能修改] 参考图已保存: {ref_path}')
                
                # 将参考图设置为第4张参考图（refs[3]），供 Gemini 作为 sketch 使用
                if not hasattr(self, 'refs') or not isinstance(self.refs, list):
                    self.refs = [None, None, None, None]
                while len(self.refs) < 4:
                    self.refs.append(None)
                self.refs[3] = str(ref_path)
                
                self._debug(f'[智能修改] 参考图已设置为 refs[3]')
            except Exception as e:
                self._debug(f'[智能修改] 保存参考图失败: {e}')
            
            # 保存智能修改上下文
            try:
                self._smart_edit_mode = True
                self._smart_rect = rect
                self._smart_mask = mask
                self._smart_original_pix = composite_pix
            except Exception:
                pass
            
            # 构建完整提示词：明确指出参考图位置和要求
            combined_prompt = f"""请根据参考图（带有绿色半透明高亮区域的图片）进行修改：

**修改要求**：
1. 只修改绿色高亮区域内的物体为：{user_prompt}
2. 参考图中绿色高亮标记仅用于指示修改区域，请在最终结果中移除绿色标记
3. 修改后的内容必须与周围环境自然融合，确保：
   - 光照方向和强度一致
   - 色调和饱和度匹配
   - 边缘无缝衔接，无明显分界线
   - 透视角度与整体画面协调
4. 绿色高亮区域外的所有内容（人物、背景、物体等）保持完全不变
5. 保持原图的整体艺术风格、氛围和质感
6. 最终效果应该看起来像原本就存在的场景，而不是后期合成"""
            
            provider = QSettings('GhostOS', 'App').value('api/image_provider', 'Gemini')
            
            self._debug(f'[智能修改] 完整提示词: {combined_prompt}')
            self._debug(f'[智能修改] 使用API提供方: {provider}')
            
            # 更新状态
            try:
                self._update_conn_status('智能修改中...', 'loading')
            except Exception:
                pass
            
            # 发起生成
            self._dispatch_generate(combined_prompt, provider)
            
        except Exception as e:
            self._debug(f'[智能修改] 错误: {e}')
            import traceback
            self._debug(traceback.format_exc())
            QMessageBox.warning(self, '智能修改失败', f'处理失败：{str(e)}')

    def _on_canvas_smart_generate(self, rect, mask):
        """智能生成：基于选区遮罩进行局部编辑，只修改选中的物体"""
        try:
            from PySide6.QtGui import QImage, QPainter
            from PySide6.QtWidgets import QMessageBox
            
            # 弹出提示词输入窗
            dlg = QDialog(self)
            dlg.setWindowTitle('智能生成')
            dlg.setMinimumWidth(400)
            lay = QVBoxLayout(dlg)
            
            # 说明标签
            info_lbl = QLabel('请输入修改提示词（例如：换一件红色衣服、改成夜晚场景）')
            info_lbl.setWordWrap(True)
            info_lbl.setStyleSheet("color: #666; font-size: 11px; padding: 8px;")
            lay.addWidget(info_lbl)
            
            # 提示词输入
            lbl = QLabel('提示词：')
            lay.addWidget(lbl)
            inp = QTextEdit()
            inp.setPlaceholderText('描述你想要的修改...')
            inp.setFixedHeight(80)
            inp.setStyleSheet('QTextEdit{ background:#f8f9fa; color:#202124; border:1px solid #dadce0; border-radius:8px; padding:8px 10px; font-size:14px; } QTextEdit:focus{ border:1px solid #4CAF50; background:#ffffff; }')
            lay.addWidget(inp)
            
            # 按钮
            row = QHBoxLayout()
            btn_ok = QPushButton('生成')
            btn_cancel = QPushButton('取消')
            row.addWidget(btn_ok)
            row.addWidget(btn_cancel)
            lay.addLayout(row)
            
            btn_cancel.clicked.connect(dlg.reject)
            btn_ok.clicked.connect(dlg.accept)
            
            if not dlg.exec():
                return
            
            user_prompt = (inp.toPlainText() or '').strip()
            if not user_prompt:
                QMessageBox.warning(self, '提示词为空', '请输入修改提示词')
                return
            
            # 获取画板合成图
            composite_img = self.canvas._composite_to_image()
            composite_pix = QPixmap.fromImage(composite_img)
            
            # 提取选区内容和遮罩
            if mask is None or rect is None:
                QMessageBox.warning(self, '选区无效', '未找到有效的选区遮罩')
                return
            
            self._debug('[智能生成] 开始处理...')
            self._debug(f'[智能生成] 选区范围: {rect.x()},{rect.y()} {rect.width()}x{rect.height()}')
            
            # 创建带绿色高亮的参考图，帮助AI理解选区位置
            reference_pix = self._create_reference_image(composite_pix, rect, mask)
            
            # 将参考图保存到临时文件，并设置为第4张参考图
            try:
                from pathlib import Path
                import tempfile
                temp_dir = Path(tempfile.gettempdir())
                ref_path = temp_dir / 'smart_gen_reference.png'
                reference_pix.save(str(ref_path), 'PNG')
                self._debug(f'[智能生成] 参考图已保存: {ref_path}')
                
                # 将参考图设置为第4张参考图（refs[3]），供 Gemini 作为 sketch 使用
                if not hasattr(self, 'refs') or not isinstance(self.refs, list):
                    self.refs = [None, None, None, None]
                while len(self.refs) < 4:
                    self.refs.append(None)
                self.refs[3] = str(ref_path)
                
                self._debug(f'[智能生成] 参考图已设置为 refs[3]')
            except Exception as e:
                self._debug(f'[智能生成] 保存参考图失败: {e}')
            
            # 保存智能生成上下文
            try:
                self._smart_rect = rect
                self._smart_mask = mask
                self._smart_mode = True
                self._smart_original_pix = composite_pix  # 保存原图用于合成
            except Exception:
                pass
            
            # 构建提示词：强调只修改选中区域，保持背景不变
            combined_prompt = f"{user_prompt}。重要：请只修改图中绿色半透明高亮区域内的物体，保持其他区域（包括背景）完全不变。背景颜色必须与原图一致。"
            
            provider = QSettings('GhostOS', 'App').value('api/image_provider', 'Gemini')
            
            self._debug(f'[智能生成] 提示词: {combined_prompt}')
            
            # 发起生成
            self._dispatch_generate(combined_prompt, provider)
            
        except Exception as e:
            self._debug(f'[智能生成] 错误: {e}')
            import traceback
            self._debug(traceback.format_exc())
            QMessageBox.warning(self, '智能生成失败', f'处理失败：{str(e)}')

    def _create_reference_image(self, base_pix: QPixmap, rect, mask) -> QPixmap:
        """创建带绿色高亮的参考图，帮助AI理解选区位置"""
        try:
            from PySide6.QtGui import QImage
            import numpy as np
            
            # 复制基础图
            result = base_pix.copy()
            
            # 转换为可编辑的图像
            img = result.toImage().convertToFormat(QImage.Format_RGBA8888)
            w, h = img.width(), img.height()
            
            # 获取像素数据
            ptr = img.bits()
            if hasattr(ptr, 'setsize'):
                ptr.setsize(img.sizeInBytes())
            arr = np.frombuffer(ptr, dtype=np.uint8).reshape(h, w, 4).copy()
            
            # 绘制绿色半透明遮罩
            x_start = rect.x()
            y_start = rect.y()
            
            green_color = np.array([52, 199, 89, 100], dtype=np.uint8)  # RGBA
            
            mask_h = len(mask)
            mask_w = len(mask[0]) if mask_h > 0 else 0
            
            for dy in range(mask_h):
                for dx in range(mask_w):
                    if mask[dy][dx]:
                        orig_x = x_start + dx
                        orig_y = y_start + dy
                        
                        if 0 <= orig_x < w and 0 <= orig_y < h:
                            # 混合颜色（alpha叠加）
                            orig_pixel = arr[orig_y, orig_x]
                            alpha = green_color[3] / 255.0
                            
                            arr[orig_y, orig_x, 0] = int(orig_pixel[0] * (1 - alpha) + green_color[0] * alpha)
                            arr[orig_y, orig_x, 1] = int(orig_pixel[1] * (1 - alpha) + green_color[1] * alpha)
                            arr[orig_y, orig_x, 2] = int(orig_pixel[2] * (1 - alpha) + green_color[2] * alpha)
            
            # 转换回 QPixmap
            bytes_per_line = 4 * w
            result_img = QImage(arr.tobytes(), w, h, bytes_per_line, QImage.Format_RGBA8888)
            result_pix = QPixmap.fromImage(result_img.copy())
            
            self._debug(f'[参考图] 创建完成，尺寸: {result_pix.width()}x{result_pix.height()}')
            
            return result_pix
            
        except Exception as e:
            self._debug(f'[参考图] 创建失败: {e}')
            return base_pix

    def _on_canvas_smart_replace(self, rect, mask):
        """智能替换：上传图片，调用AI将其智能融合到选区内"""
        try:
            from PySide6.QtGui import QImage, QPainter, QPixmap
            from PySide6.QtWidgets import QMessageBox, QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFileDialog
            from PySide6.QtCore import Qt
            
            # 弹出对话框：上传图片
            dlg = QDialog(self)
            dlg.setWindowTitle('智能替换')
            dlg.setMinimumWidth(450)
            lay = QVBoxLayout(dlg)
            
            # 说明标签
            info_lbl = QLabel('上传图片，AI将智能地将其融合到绿色选区内，保持其他区域不变')
            info_lbl.setWordWrap(True)
            info_lbl.setStyleSheet("color: #666; font-size: 11px; padding: 8px;")
            lay.addWidget(info_lbl)
            
            # 上传图片（必须）
            lay.addWidget(QLabel('选择图片：'))
            upload_row = QHBoxLayout()
            file_label = QLabel('未选择文件')
            file_label.setStyleSheet("color: #999; padding: 5px;")
            upload_row.addWidget(file_label)
            btn_browse = QPushButton('浏览...')
            upload_row.addWidget(btn_browse)
            lay.addLayout(upload_row)
            
            # 用于存储选择的文件路径
            selected_file = {'path': None}
            
            def on_browse():
                file_path, _ = QFileDialog.getOpenFileName(
                    dlg,
                    '选择图片',
                    '',
                    'Images (*.png *.jpg *.jpeg *.bmp *.webp)'
                )
                if file_path:
                    selected_file['path'] = file_path
                    from pathlib import Path
                    file_label.setText(Path(file_path).name)
                    file_label.setStyleSheet("color: #333; padding: 5px;")
            
            btn_browse.clicked.connect(on_browse)
            
            # 按钮
            btn_row = QHBoxLayout()
            btn_ok = QPushButton('开始替换')
            btn_cancel = QPushButton('取消')
            btn_row.addWidget(btn_ok)
            btn_row.addWidget(btn_cancel)
            lay.addLayout(btn_row)
            
            btn_cancel.clicked.connect(dlg.reject)
            btn_ok.clicked.connect(dlg.accept)
            
            if not dlg.exec():
                return
            
            # 检查是否选择了文件
            if not selected_file['path']:
                QMessageBox.warning(self, '未选择图片', '请选择要替换的图片')
                return
            
            # 加载用户上传的图片
            upload_pix = QPixmap(selected_file['path'])
            
            if upload_pix.isNull():
                QMessageBox.warning(self, '图片加载失败', '无法加载选择的图片')
                return
            
            self._debug('[智能替换] 开始处理...')
            self._debug(f'[智能替换] 选区范围: {rect.x()},{rect.y()} {rect.width()}x{rect.height()}')
            self._debug(f'[智能替换] 上传图片尺寸: {upload_pix.width()}x{upload_pix.height()}')
            
            # 获取画板合成图
            composite_img = self.canvas._composite_to_image()
            composite_pix = QPixmap.fromImage(composite_img)
            
            # 提取选区内容和遮罩
            if mask is None or rect is None:
                QMessageBox.warning(self, '选区无效', '未找到有效的选区遮罩')
                return
            
            # 创建遮罩图片（绿色选区）
            mask_img = QImage(composite_pix.size(), QImage.Format_ARGB32)
            mask_img.fill(Qt.transparent)
            
            painter = QPainter(mask_img)
            painter.setCompositionMode(QPainter.CompositionMode_Source)
            
            # 绘制绿色遮罩
            from PySide6.QtGui import QColor
            painter.setBrush(QColor(0, 255, 0, 180))  # 半透明绿色
            painter.setPen(Qt.NoPen)
            
            # 使用mask数组绘制选区
            import numpy as np
            if isinstance(mask, np.ndarray):
                for y in range(mask.shape[0]):
                    for x in range(mask.shape[1]):
                        if mask[y, x]:
                            painter.drawPoint(rect.x() + x, rect.y() + y)
            else:
                # 如果mask不是ndarray，直接绘制整个矩形
                painter.drawRect(rect)
            
            painter.end()
            mask_pix = QPixmap.fromImage(mask_img)
            
            self._debug('[智能替换] 遮罩图片已创建')
            
            # 调用AI API进行智能替换
            self._debug('[智能替换] 调用AI API...')
            
            result_pix = self._call_ai_smart_replace(
                composite_pix,
                upload_pix,
                mask_pix,
                rect
            )
            
            if result_pix is not None and not result_pix.isNull():
                # 添加到画板作为新图层
                layer_name = '智能替换'
                
                lid = getattr(self.canvas, 'add_image_layer_at', lambda _p, _n, _x, _y, _s: None)(
                    result_pix,
                    layer_name,
                    0,  # x=0
                    0,  # y=0
                    True  # show_thumb=True，显示缩略图
                )
                
                self._debug(f'[智能替换] 已添加图层到画板')
                
                # 同步图层面板
                try:
                    self.layers_panel.sync_from_canvas()
                except Exception:
                    pass
                
                # 更新状态
                try:
                    self._update_conn_status('智能替换成功', 'success')
                except Exception:
                    pass
                
                QMessageBox.information(self, '替换成功', 'AI已完成智能替换')
            else:
                QMessageBox.warning(self, '替换失败', 'AI处理失败，请重试')
                
        except Exception as e:
            self._debug(f'[智能替换] 错误: {e}')
            import traceback
            self._debug(traceback.format_exc())
            QMessageBox.warning(self, '智能替换失败', f'处理失败：{str(e)}')

    def _call_ai_smart_replace(self, composite_pix: QPixmap, upload_pix: QPixmap, mask_pix: QPixmap, rect) -> QPixmap:
        """
        调用AI进行智能替换：将上传的图片智能融合到选区内
        
        Args:
            composite_pix: 原始画布图片
            upload_pix: 用户上传的图片
            mask_pix: 绿色遮罩图片（标识选区）
            rect: 选区矩形范围
            
        Returns:
            AI生成的融合后图片，如果失败返回None
        """
        try:
            from PySide6.QtCore import QSettings
            from PySide6.QtWidgets import QMessageBox, QProgressDialog
            import tempfile
            from pathlib import Path
            import threading
            
            self._debug('[智能替换] 准备调用AI API...')
            
            # 保存图片到临时文件
            temp_dir = Path(tempfile.gettempdir())
            
            # 保存原始画布图（作为基础参考）
            base_path = temp_dir / 'smart_replace_base.png'
            composite_pix.save(str(base_path), 'PNG')
            self._debug(f'[智能替换] 基础图已保存: {base_path}')
            
            # 保存遮罩图（带绿色选区标识）
            mask_path = temp_dir / 'smart_replace_mask.png'
            mask_pix.save(str(mask_path), 'PNG')
            self._debug(f'[智能替换] 遮罩图已保存: {mask_path}')
            
            # 保存上传的图片
            upload_path = temp_dir / 'smart_replace_upload.png'
            upload_pix.save(str(upload_path), 'PNG')
            self._debug(f'[智能替换] 上传图已保存: {upload_path}')
            
            # 设置参考图
            if not hasattr(self, 'refs') or not isinstance(self.refs, list):
                self.refs = [None, None, None, None, None]
            while len(self.refs) < 5:
                self.refs.append(None)
            
            # refs[3] = 遮罩图（带绿色选区标识）
            self.refs[3] = str(mask_path)
            # refs[4] = 用户上传的图片
            self.refs[4] = str(upload_path)
            
            self._debug('[智能替换] 参考图已设置: refs[3]=遮罩图, refs[4]=上传图')
            
            # 构建提示词
            prompt = "将上传的图片（第二张参考图）智能地替换到绿色选中区域（第一张参考图的绿色半透明区域），保持其他区域样貌完全不变。要求：1) 融合自然，边缘平滑 2) 保持原图背景和未选中区域完全不变 3) 上传图片的内容要完整融入绿色选区内"
            
            self._debug(f'[智能替换] 提示词: {prompt}')
            
            # 获取API提供方
            provider = QSettings('GhostOS', 'App').value('api/image_provider', 'Gemini')
            self._debug(f'[智能替换] 使用API提供方: {provider}')
            
            # 显示进度对话框
            progress_dlg = QProgressDialog('AI正在处理智能替换...', '取消', 0, 0, self)
            progress_dlg.setWindowTitle('智能替换')
            progress_dlg.setWindowModality(Qt.WindowModal)
            progress_dlg.setMinimumDuration(0)
            progress_dlg.setValue(0)
            
            # 结果容器
            result_holder = {'pixmap': None, 'success': False, 'message': '', 'done': False}
            
            def worker():
                """后台线程调用AI"""
                try:
                    self._debug('[智能替换] 工作线程开始...')
                    
                    # 调用AI生成
                    if (provider or '').lower().startswith('gemini30'):
                        ok, pix, msg = self._generate_with_gemini30(prompt, progress=None)
                    elif (provider or '').lower().startswith('gemini'):
                        ok, pix, msg = self._generate_with_gemini(prompt, progress=None)
                    else:
                        ok, pix, msg = self._generate_with_gemini(prompt, progress=None)
                    
                    result_holder['success'] = ok
                    result_holder['pixmap'] = pix
                    result_holder['message'] = msg or ''
                    
                    self._debug(f'[智能替换] AI返回: ok={ok}, msg={msg}')
                    
                except Exception as e:
                    self._debug(f'[智能替换] 工作线程异常: {e}')
                    import traceback
                    self._debug(traceback.format_exc())
                    result_holder['success'] = False
                    result_holder['message'] = str(e)
                finally:
                    result_holder['done'] = True
                    # 关闭进度对话框
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, progress_dlg.close)
            
            # 启动工作线程
            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            
            # 等待完成（阻塞UI）
            progress_dlg.exec()
            
            # 等待线程完成（最多5秒）
            thread.join(timeout=5.0)
            
            if result_holder['success'] and result_holder['pixmap']:
                self._debug('[智能替换] 返回AI生成的图片')
                return result_holder['pixmap']
            else:
                self._debug(f'[智能替换] AI处理失败: {result_holder["message"]}')
                QMessageBox.warning(self, 'AI处理失败', f'智能替换失败: {result_holder["message"]}')
                return None
                
        except Exception as e:
            self._debug(f'[智能替换] 调用AI异常: {e}')
            import traceback
            self._debug(traceback.format_exc())
            QMessageBox.warning(self, '智能替换异常', f'处理过程出错: {str(e)}')
            return None

    def _apply_direct_replace_with_mask(self, base_pix: QPixmap, replace_pix: QPixmap, rect, mask) -> QPixmap:
        """
        直接替换：将上传图片按照遮罩直接替换到画布
        
        Args:
            base_pix: 原始画布图片
            replace_pix: 替换的图片（已缩放到选区大小）
            rect: 选区矩形范围
            mask: 二维布尔数组，True表示选区内
            
        Returns:
            合成后的完整画布图片
        """
        try:
            from PySide6.QtGui import QImage
            import numpy as np
            
            canvas_w = base_pix.width()
            canvas_h = base_pix.height()
            
            self._debug(f'[直接替换] 画板尺寸: {canvas_w}x{canvas_h}')
            self._debug(f'[直接替换] 选区范围: ({rect.x()},{rect.y()}) {rect.width()}x{rect.height()}')
            self._debug(f'[直接替换] 替换图片尺寸: {replace_pix.width()}x{replace_pix.height()}')
            
            # 复制基础图
            result_pix = base_pix.copy()
            
            # 转换为可编辑的图像
            result_img = result_pix.toImage().convertToFormat(QImage.Format_RGBA8888)
            result_ptr = result_img.bits()
            if hasattr(result_ptr, 'setsize'):
                result_ptr.setsize(result_img.sizeInBytes())
            result_arr = np.frombuffer(result_ptr, dtype=np.uint8).reshape(canvas_h, canvas_w, 4).copy()
            
            # 转换替换图片
            replace_img = replace_pix.toImage().convertToFormat(QImage.Format_RGBA8888)
            replace_w, replace_h = replace_img.width(), replace_img.height()
            replace_ptr = replace_img.bits()
            if hasattr(replace_ptr, 'setsize'):
                replace_ptr.setsize(replace_img.sizeInBytes())
            replace_arr = np.frombuffer(replace_ptr, dtype=np.uint8).reshape(replace_h, replace_w, 4).copy()
            
            # 根据遮罩合成
            x_start = rect.x()
            y_start = rect.y()
            
            replaced_count = 0
            mask_h = len(mask)
            mask_w = len(mask[0]) if mask_h > 0 else 0
            
            # 遍历遮罩区域
            for dy in range(mask_h):
                for dx in range(mask_w):
                    if mask[dy][dx]:
                        # 画布绝对坐标
                        canvas_x = x_start + dx
                        canvas_y = y_start + dy
                        
                        # 替换图片中的相对坐标
                        replace_x = dx
                        replace_y = dy
                        
                        # 检查坐标是否有效
                        if (0 <= canvas_x < canvas_w and 0 <= canvas_y < canvas_h and
                            0 <= replace_x < replace_w and 0 <= replace_y < replace_h):
                            
                            pixel = replace_arr[replace_y, replace_x]
                            
                            # Alpha 混合
                            if pixel[3] > 0:  # 有不透明像素
                                alpha = pixel[3] / 255.0
                                orig_pixel = result_arr[canvas_y, canvas_x]
                                
                                # 混合颜色
                                result_arr[canvas_y, canvas_x, 0] = int(orig_pixel[0] * (1 - alpha) + pixel[0] * alpha)
                                result_arr[canvas_y, canvas_x, 1] = int(orig_pixel[1] * (1 - alpha) + pixel[1] * alpha)
                                result_arr[canvas_y, canvas_x, 2] = int(orig_pixel[2] * (1 - alpha) + pixel[2] * alpha)
                                result_arr[canvas_y, canvas_x, 3] = max(orig_pixel[3], pixel[3])
                                
                                replaced_count += 1
            
            self._debug(f'[直接替换] 替换了 {replaced_count} 个像素')
            
            # 转换回 QPixmap
            bytes_per_line = 4 * canvas_w
            final_img = QImage(result_arr.tobytes(), canvas_w, canvas_h, bytes_per_line, QImage.Format_RGBA8888)
            final_pix = QPixmap.fromImage(final_img.copy())
            
            return final_pix
            
        except Exception as e:
            self._debug(f'[直接替换] 失败: {e}')
            import traceback
            self._debug(traceback.format_exc())
            return None

    def _show_generation_dialog(self, prompt: str, provider: str):
        try:
            if getattr(self, '_gen_dialog', None) is None:
                self._gen_dialog = GenerationDialog(self)
            dlg = self._gen_dialog
            dlg.set_status('开始生成…')
            dlg.log.clear()
            dlg.append_log(f"提供方：{provider}")
            dlg.append_log(f"提示词：{prompt[:80]}{'...' if len(prompt)>80 else ''}")
            dlg.btn_close.setEnabled(False)
            dlg.bar.setRange(0, 0)
            dlg.show()
        except Exception:
            pass

    def _dispatch_generate(self, prompt: str, provider: str):
        def worker():
            try:
                try:
                    self._debug('worker: start')
                    self._debug(f"worker: provider route={provider}")
                    # 追加：工作线程开始时记录提示词（截断避免过长）
                    w_snippet = (prompt[:200] + ('...' if len(prompt) > 200 else ''))
                    self._debug(f"worker: prompt: {w_snippet}")
                except Exception:
                    pass
                # 首次进度上报也通过主线程，避免跨线程UI更新
                self._report_progress('准备请求…')
                # 判断顺序很重要：先判断更具体的 gemini30/banana2，再判断通用的 gemini/banana
                if (provider or '').lower() in ('gemini30', 'gemini 3.0', 'banana2'):
                    ok, pix, msg = self._generate_with_gemini30(prompt, progress=self._report_progress)
                elif (provider or '').lower().startswith('gemini30'):
                    ok, pix, msg = self._generate_with_gemini30(prompt, progress=self._report_progress)
                elif (provider or '').lower().startswith('banana2'):
                    ok, pix, msg = self._generate_with_gemini30(prompt, progress=self._report_progress)
                elif (provider or '').lower().startswith('gemini'):
                    ok, pix, msg = self._generate_with_gemini(prompt, progress=self._report_progress)
                elif (provider or '').lower().startswith('banana'):
                    # BANANA（对应 Gemini 2.5）
                    ok, pix, msg = self._generate_with_gemini(prompt, progress=self._report_progress)
                elif provider in ('即梦', 'jimeng'):
                    # 临时回退：使用 Gemini 管道替代即梦生成，避免"开发中"提示阻断流程
                    ok, pix, msg = self._generate_with_gemini(prompt, progress=self._report_progress)
                elif (provider or '').strip().lower() == 'midjourney':
                    ok, pix, msg = self._generate_with_midjourney(prompt, progress=self._report_progress)
                else:
                    ok, pix, msg = False, None, '未知提供方'
                try:
                    self._debug(f"worker: finished ok={ok}, msg={msg}")
                except Exception:
                    pass
            except Exception as e:
                ok, pix, msg = False, None, '出现未捕获异常'
                try:
                    import traceback
                    self._debug('worker: exception\n' + traceback.format_exc())
                except Exception:
                    pass
            # 回到主线程处理结果：指定接收者 self，确保在 UI 线程执行
            try:
                self._debug('worker: schedule result to UI thread')
            except Exception:
                pass
            QTimer.singleShot(0, self, lambda: self._on_generate_done(prompt, provider, ok, pix, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _generate_with_gemini30(self, prompt: str, progress=None) -> tuple[bool, QPixmap | None, str]:
        """调用 BANANA2 (gemini-3-pro-image-preview) 生成图片，返回 (ok, QPixmap, message)。"""
        try:
            cfg = gemini30_get_config()
            api_key = (cfg.get('api_key') or '').strip()
            base_url = (cfg.get('base_url') or '').strip().strip(' ,`')
            model = (cfg.get('model') or 'gemini-3-pro-image-preview').strip()
            
            # ⭐ 在界面上显示正在使用的模型
            try:
                win = self.window()
                if win and hasattr(win, 'set_connection_text'):
                    win.set_connection_text(f'BANANA2 - {model}', 'loading')
            except Exception:
                pass
            
            try:
                self._debug(f"gemini30 cfg: base_url={base_url}, model={model}")
            except Exception:
                pass
            
            if not api_key or not base_url:
                err_msg = '配置不完整：缺少 API Key 或 Base URL'
                try:
                    self._debug(f"[gemini30] ❌ {err_msg}")
                    self._debug(f"[gemini30]   - api_key存在: {bool(api_key)}")
                    self._debug(f"[gemini30]   - base_url存在: {bool(base_url)}")
                except Exception:
                    pass
                if progress:
                    try:
                        progress(err_msg)
                    except Exception:
                        pass
                return False, None, 'BANANA2 配置不完整'
            
            # 验证API密钥格式
            try:
                if len(api_key) < 20:
                    self._debug(f"[gemini30] ⚠️ API密钥似乎太短: {len(api_key)} 字符")
                else:
                    self._debug(f"[gemini30] ✅ API密钥长度: {len(api_key)} 字符")
                self._debug(f"[gemini30] ✅ Base URL: {base_url}")
                self._debug(f"[gemini30] ✅ Model: {model}")
            except Exception:
                pass
            
            # 构造请求（参考云雾 API 文档）
            # 1) 获取分辨率和质量配置
            resolution = cfg.get('resolution', '1K')
            quality_str = cfg.get('quality', '80')
            
            # 将质量字符串转换为整数
            try:
                quality = int(quality_str)
                # 限制在 0-100 范围内
                quality = max(0, min(100, quality))
            except Exception:
                quality = 80
            
            # 根据分辨率设置宽高
            resolution_map = {
                '1K': 1024,
                '2K': 2048,
                '4K': 4096,
            }
            base_size = resolution_map.get(resolution, 1024)
            
            # 2) 解析当前比例并计算实际宽高
            try:
                ar_text = self.combo_ratio.currentText()
                w_str, h_str = ar_text.split(':')
                rw, rh = int(w_str), int(h_str)
                
                # 根据比例调整宽高
                if rw == rh:
                    # 正方形
                    width, height = base_size, base_size
                elif rw > rh:
                    # 横向（如 16:9）
                    width = base_size
                    height = int(base_size * rh / rw)
                else:
                    # 纵向（如 9:16）
                    width = int(base_size * rw / rh)
                    height = base_size
            except Exception:
                width, height = base_size, base_size
            
            try:
                self._debug(f"resolution={resolution}, quality={quality}, width={width}, height={height}")
            except Exception:
                pass

            # 2) 收集输入图片（如果有参考图）
            def _scale_image(qimg, max_dim: int) -> 'QImage':
                try:
                    w = qimg.width()
                    h = qimg.height()
                    if w <= 0 or h <= 0:
                        return qimg
                    if max(w, h) <= max_dim:
                        return qimg
                    from PySide6.QtCore import Qt as _Qt
                    return qimg.scaled(max_dim, max_dim, _Qt.KeepAspectRatio, _Qt.SmoothTransformation)
                except Exception:
                    return qimg

            def qimage_to_base64_jpeg(qimg, max_dim: int = 1024, quality: int = 90):
                try:
                    qimg2 = _scale_image(qimg, max_dim)
                    buf = QBuffer()
                    buf.open(QIODevice.WriteOnly)
                    qimg2.save(buf, 'JPEG', quality)
                    data = bytes(buf.data())
                    buf.close()
                    return base64.b64encode(data).decode('ascii')
                except Exception:
                    return None

            # 收集参考图和画板图片（与 gemini 方法保持一致）
            input_image_parts = []
            try:
                # 1) 优先使用第4张参考图作为草图（与 gemini 行为一致）
                sketch_added = False
                if isinstance(getattr(self, 'refs', None), list) and len(self.refs) >= 4:
                    ref4 = self.refs[3]
                    if ref4:
                        from PySide6.QtGui import QImage
                        img = QImage(ref4)
                        if not img.isNull():
                            b64 = qimage_to_base64_jpeg(img, max_dim=1024)
                            if b64:
                                input_image_parts.append({
                                    'inline_data': {
                                        'mime_type': 'image/jpeg',
                                        'data': b64
                                    }
                                })
                                sketch_added = True
                                try:
                                    self._debug("[gemini30] 使用第4张参考图作为草图")
                                except Exception:
                                    pass
                
                # 2) 如果没有第4张参考图，使用当前画板合成作为草图
                if not sketch_added:
                    try:
                        from PySide6.QtGui import QImage
                        qimg = self.canvas._composite_to_image() if hasattr(self.canvas, '_composite_to_image') else None
                        if qimg is not None and not qimg.isNull():
                            b64 = qimage_to_base64_jpeg(qimg, max_dim=1024)
                            if b64:
                                input_image_parts.append({
                                    'inline_data': {
                                        'mime_type': 'image/jpeg',
                                        'data': b64
                                    }
                                })
                                sketch_added = True
                                try:
                                    self._debug("[gemini30] 使用画板合成图作为草图")
                                except Exception:
                                    pass
                    except Exception as e:
                        try:
                            self._debug(f"[gemini30] 获取画板图片失败: {e}")
                        except Exception:
                            pass
                
                # 3) 添加其他参考图（前3张）作为风格参考
                if isinstance(getattr(self, 'refs', None), list):
                    from PySide6.QtGui import QImage
                    for i in range(3):  # 只使用前3张
                        ref_path = self.refs[i] if i < len(self.refs) else None
                        if not ref_path:
                            continue
                        img = QImage(ref_path)
                        if img.isNull():
                            continue
                        b64 = qimage_to_base64_jpeg(img, max_dim=1024)
                        if b64:
                            input_image_parts.append({
                                'inline_data': {
                                    'mime_type': 'image/jpeg',
                                    'data': b64
                                }
                            })
                            try:
                                self._debug(f"[gemini30] 添加参考图{i+1}作为风格参考")
                            except Exception:
                                pass
            except Exception as e:
                try:
                    self._debug(f"[gemini30] 收集参考图失败: {e}")
                except Exception:
                    pass

            # 3) 组织 parts（按照云雾 API 文档格式）
            parts = []
            txt = (prompt or '').strip()
            
            # 添加提示词
            parts.append({'text': txt if txt else 'Generate an image'})
            
            # 添加所有输入图片
            for img_part in input_image_parts:
                parts.append(img_part)
            
            try:
                self._debug(f"parts: text_len={len(txt)}, input_images_count={len(input_image_parts)}")
            except Exception:
                pass

            # 4) 构造请求体（包含分辨率和清晰度参数）（不使用QTimer）
            if progress:
                try:
                    progress('发送请求…')
                except Exception:
                    pass
            
            endpoint = base_url.rstrip('/') + f"/models/{model}:generateContent"
            
            # 构造请求体
            # 根据 Google Gemini API 官方文档 (https://ai.google.dev/gemini-api/docs/image-generation)
            # 正确格式：responseModalities + imageConfig (不是 imageGenerationConfig!)
            
            gen_cfg = {
                'responseModalities': ['IMAGE']
            }
            
            # imageConfig - 图片配置（注意字段名！）
            # 根据官方文档，使用 imageConfig 而不是 imageGenerationConfig
            image_config = {
                'aspectRatio': f"{rw}:{rh}",  # 比例格式：字符串 "16:9"
            }
            
            # Gemini 3.0 Pro Image Preview 支持的参数：
            # - aspectRatio: 宽高比（字符串）
            # - imageSize: 分辨率大小 "1K", "2K", "4K" ⭐ 关键参数
            # - numberOfImages: 生成图片数量
            # - includeRAIOutput: 是否包含安全评分
            # - personGeneration: 人物生成设置
            
            # ⭐ 关键：设置分辨率 imageSize（Gemini30 支持此参数）
            image_config['imageSize'] = resolution  # "1K", "2K", "4K"
            image_config['numberOfImages'] = 1
            
            try:
                self._debug(f"[gemini30] 设置 imageConfig.imageSize = {resolution}")
            except Exception:
                pass
            
            gen_cfg['imageConfig'] = image_config
            
            payload = {
                'contents': [
                    {
                        'role': 'user',
                        'parts': parts
                    }
                ],
                'generationConfig': gen_cfg
            }
            
            try:
                self._debug(f"Request: resolution={resolution}, aspectRatio={rw}:{rh}")
                self._debug(f"generationConfig: {json.dumps(gen_cfg, ensure_ascii=False)}")
            except Exception:
                pass
            
            data = json.dumps(payload).encode('utf-8')
            try:
                self._debug(f"POST {endpoint} bytes={len(data)}")
                self._debug(f"Request payload: width={width}, height={height}, quality={quality}")
            except Exception:
                pass
            
            # 使用 Bearer Token 认证
            req = urllib.request.Request(
                endpoint,
                data=data,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json, image/*'
                }
            )
            
            # 发送请求（参考 new_api_client.py 的做法）
            # 4K图片需要更长的超时时间：1K=240秒, 2K=480秒, 4K=600秒（10分钟）
            timeout_map = {'1K': 240, '2K': 480, '4K': 600}
            timeout_seconds = timeout_map.get(resolution, 600)
            
            try:
                self._debug(f'[gemini30] 请求超时设置: {timeout_seconds}秒 (分辨率: {resolution})')
            except Exception:
                pass
            
            # 进度提示：开始发送请求（不使用QTimer，因为在worker线程中）
            if progress:
                try:
                    progress(f'正在发送请求到API（4K图片生成需要5-10分钟）...')
                except Exception:
                    pass
            
            # 使用 requests 库替代 urllib（更好的JSON支持）
            try:
                import requests
                
                try:
                    self._debug(f'[gemini30] 开始导入requests库并创建session...')
                except Exception:
                    pass
                
                # 使用Session保持连接
                session = requests.Session()
                session.keep_alive = False  # 禁用keep-alive避免连接问题
                session.trust_env = False  # 不信任环境变量（避免代理问题）
                
                try:
                    self._debug(f'[gemini30] 开始POST请求到: {endpoint}')
                    self._debug(f'[gemini30] 请求数据大小: {len(data)} 字节')
                except Exception:
                    pass
                
                # 进度提示：正在等待API响应（不使用QTimer）
                if progress:
                    try:
                        progress(f'等待API响应（预计{timeout_seconds//60}分钟）...')
                    except Exception:
                        pass
                
                response = session.post(
                    endpoint,
                    json=json.loads(data.decode('utf-8')),
                    headers={
                        'Authorization': f'Bearer {api_key}',
                        'Content-Type': 'application/json',
                        'Accept': 'application/json, image/*'
                    },
                    timeout=timeout_seconds,
                    stream=False,  # 不使用流式传输
                    proxies={'http': None, 'https': None}  # 明确禁用代理
                )
                
                content_type = response.headers.get('Content-Type', '')
                
                try:
                    self._debug(f'[gemini30] ✅ POST请求返回，状态码: {response.status_code}')
                    self._debug(f'[gemini30] Content-Type: {content_type}')
                    self._debug(f'[gemini30] 响应大小: {len(response.content)} 字节')
                except Exception:
                    pass
                
                # 进度提示：收到响应（不使用QTimer）
                if progress:
                    try:
                        progress('收到API响应，正在处理...')
                    except Exception:
                        pass
            except requests.exceptions.Timeout:
                err_msg = f'请求超时（{timeout_seconds}秒），4K图片生成时间过长'
                try:
                    self._debug(f'[gemini30] ❌ {err_msg}')
                except Exception:
                    pass
                if progress:
                    QTimer.singleShot(0, lambda: self._report_progress(err_msg))
                return False, None, err_msg
            except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
                err_msg = f'连接错误（网络不稳定）: {str(e)[:200]}'
                try:
                    self._debug(f'[gemini30] ❌ {err_msg}')
                except Exception:
                    pass
                if progress:
                    QTimer.singleShot(0, lambda: self._report_progress(err_msg))
                return False, None, err_msg
            except ImportError as e:
                # requests库未安装
                err_msg = 'requests库未安装，请运行: pip install requests'
                try:
                    self._debug(f'[gemini30] ❌ {err_msg}')
                except Exception:
                    pass
                if progress:
                    QTimer.singleShot(0, lambda: self._report_progress(err_msg))
                return False, None, err_msg
            except Exception as e:
                err_msg = f'请求失败: {str(e)[:200]}'
                try:
                    self._debug(f'[gemini30] ❌ {err_msg}')
                    import traceback
                    self._debug(f'[gemini30] 异常堆栈:\n{traceback.format_exc()}')
                except Exception:
                    pass
                if progress:
                    QTimer.singleShot(0, lambda: self._report_progress(err_msg))
                return False, None, err_msg

            # 5) 解析响应
            if progress:
                QTimer.singleShot(0, lambda: self._report_progress('解析响应…'))
            
            # 检查是否直接返回二进制图片
            if 'image/' in content_type.lower():
                try:
                    from PySide6.QtGui import QImage, QPixmap
                    
                    # 修复 iCCP 警告：禁用 Qt 的颜色配置文件警告
                    import os
                    old_qt_logging = os.environ.get('QT_LOGGING_RULES', '')
                    os.environ['QT_LOGGING_RULES'] = 'qt.gui.imageio.warning=false'
                    
                    img = QImage.fromData(response.content)
                    
                    # 恢复原始日志设置
                    if old_qt_logging:
                        os.environ['QT_LOGGING_RULES'] = old_qt_logging
                    else:
                        os.environ.pop('QT_LOGGING_RULES', None)
                    
                    if not img.isNull():
                        pix = QPixmap.fromImage(img)
                        try:
                            self._debug(f"✓ API返回图片尺寸: {img.width()}x{img.height()} (请求: {width}x{height})")
                        except Exception:
                            pass
                        if progress:
                            try:
                                progress('完成')
                            except Exception:
                                pass
                        return True, pix, 'ok'
                except Exception as e:
                    try:
                        self._debug(f"解析直接返回的图片失败: {e}")
                    except Exception:
                        pass
            
            # 否则解析 JSON 响应（使用 requests 的 json() 方法，更好的支持大JSON）
            try:
                try:
                    self._debug(f'[gemini30] 开始解析JSON响应，内容长度: {len(response.content)} 字节')
                except Exception:
                    pass
                
                # 使用 requests 的 json() 方法，性能更好
                resp_json = response.json()
                
                # 提取图片 URL 或 base64 数据
                candidates = resp_json.get('candidates', [])
                if not candidates:
                    return False, None, '响应中没有图片数据'
                
                # 遍历 parts 查找图片
                for candidate in candidates:
                    content = candidate.get('content', {})
                    parts_list = content.get('parts', [])
                    
                    for part in parts_list:
                        # 检查 inline_data
                        inline = part.get('inline_data') or part.get('inlineData')
                        if inline:
                            mime_type = inline.get('mime_type') or inline.get('mimeType')
                            data_b64 = inline.get('data')
                            
                            if data_b64 and 'image/' in (mime_type or ''):
                                try:
                                    img_bytes = base64.b64decode(data_b64)
                                    from PySide6.QtGui import QImage, QPixmap
                                    
                                    # 修复 iCCP 警告：禁用 Qt 的颜色配置文件警告
                                    import os
                                    old_qt_logging = os.environ.get('QT_LOGGING_RULES', '')
                                    os.environ['QT_LOGGING_RULES'] = 'qt.gui.imageio.warning=false'
                                    
                                    img = QImage.fromData(img_bytes)
                                    
                                    # 恢复原始日志设置
                                    if old_qt_logging:
                                        os.environ['QT_LOGGING_RULES'] = old_qt_logging
                                    else:
                                        os.environ.pop('QT_LOGGING_RULES', None)
                                    
                                    if not img.isNull():
                                        pix = QPixmap.fromImage(img)
                                        try:
                                            self._debug(f"✓ API返回图片尺寸: {img.width()}x{img.height()} (请求: {width}x{height})")
                                        except Exception:
                                            pass
                                        if progress:
                                            try:
                                                progress('完成')
                                            except Exception:
                                                pass
                                        return True, pix, 'ok'
                                except Exception as e:
                                    try:
                                        self._debug(f"Failed to decode base64 image: {e}")
                                    except Exception:
                                        pass
                
                return False, None, '未找到有效的图片数据'
                
            except (json.JSONDecodeError, ValueError) as e:
                err_msg = f'JSON解析失败: {str(e)[:200]}'
                try:
                    # 打印响应前200字符用于调试
                    preview = response.text[:200] if hasattr(response, 'text') else str(response.content[:200])
                    self._debug(f"[gemini30] Failed to parse response: {e}")
                    self._debug(f"[gemini30] 响应内容预览: {preview}")
                except Exception:
                    pass
                if progress:
                    try:
                        progress(err_msg)
                    except Exception:
                        pass
                return False, None, err_msg
            except Exception as e:
                err_msg = f'解析响应失败: {str(e)[:200]}'
                try:
                    self._debug(f"[gemini30] 解析响应异常: {e}")
                except Exception:
                    pass
                if progress:
                    try:
                        progress(err_msg)
                    except Exception:
                        pass
                return False, None, err_msg
                
        except Exception as e:
            try:
                self._debug(f'Gemini 3.0 生成异常: {e}')
                import traceback
                self._debug(traceback.format_exc())
            except Exception:
                pass
            return False, None, f'BANANA2 生成异常: {str(e)[:100]}'

    def _generate_with_midjourney(self, prompt: str, progress=None):
        """
        调用 VectorEngine Midjourney API 生成图片
        API文档: https://vectorengine.apifox.cn/api-349239131
        
        完整流程：
        1. 如有参考图，先上传图片获取Discord URL (api-349239130)
        2. 提交Imagine任务 (api-349239131)
        3. 轮询查询任务状态 (api-349239132)
        4. 下载生成的图片
        """
        try:
            if progress:
                progress('Midjourney: 提交任务…')
            from PySide6.QtCore import QSettings
            import os, json, base64, re, time, mimetypes
            import urllib.request, urllib.error
            
            # 1. 加载配置
            s = QSettings('GhostOS', 'App')
            api_key = s.value('providers/midjourney/api_key', '') or ''
            base_url = s.value('providers/midjourney/base_url', '') or ''
            
            # 2. 从配置文件读取（备用）
            if not base_url.startswith('http'):
                try:
                    app_root = os.path.dirname(os.sys.executable) if getattr(os.sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
                    for cfg_file in ['midjourney.json', 'mj.json']:
                        cfg_path = os.path.join(app_root, 'json', cfg_file)
                        if os.path.exists(cfg_path):
                            with open(cfg_path, 'r', encoding='utf-8') as f:
                                cfg = json.load(f)
                                api_key = cfg.get('api_key', api_key)
                                base_url = cfg.get('base_url', base_url)
                                if api_key and base_url:
                                    break
                except Exception as e:
                    self._debug(f'[MJ] 读取配置文件错误: {e}')
                    
            # 3. 验证和格式化 base_url
            self._debug(f'[MJ] 原始配置 - API Key长度: {len(api_key) if api_key else 0}, Base URL: {base_url}')
            
            try:
                base_url = (base_url or '').strip().replace('`', '').rstrip(',')
                if base_url and not re.match(r'^https?://', base_url, re.I):
                    base_url = 'https://' + base_url.lstrip('/')
                base_url = base_url.rstrip('/')
                self._debug(f'[MJ] 格式化后 Base URL: {base_url}')
            except Exception as e:
                self._debug(f'[MJ] URL格式化错误: {e}')
                return False, None, 'Midjourney 配置错误：Base URL 格式不正确'
            
            # 4. 验证配置
            if not api_key or not base_url:
                self._debug(f'[MJ] 配置验证失败 - API Key存在: {bool(api_key)}, Base URL存在: {bool(base_url)}')
                return False, None, 'Midjourney 未配置：请在设置中填写 API Key 与 Base URL（例如: https://api.vectorengine.ai）'
            
            # 5. 验证提示词
            if not prompt or not prompt.strip():
                self._debug(f'[MJ] 提示词验证失败: prompt={prompt}')
                return False, None, 'Midjourney 错误: 提示词不能为空'
            
            # 预处理提示词
            prompt = prompt.strip()
            
            # 检查提示词是否包含中文，给出提示
            has_chinese = any('\u4e00' <= char <= '\u9fff' for char in prompt)
            if has_chinese:
                self._debug(f'[MJ] 警告: 提示词包含中文字符，MidJourney推荐使用英文提示词以获得更好效果')
            
            # 移除提示词中的特殊字符（保留MJ参数）
            # MidJourney 支持的参数格式: --v 6, --ar 16:9 等
            self._debug(f'[MJ] 原始提示词: {prompt}')
            
            self._debug(f'[MJ] ========== 开始MJ生成 ==========')
            self._debug(f'[MJ] Base URL: {base_url}')
            self._debug(f'[MJ] API Key: {api_key[:10]}...{api_key[-5:] if len(api_key) > 15 else ""}')
            self._debug(f'[MJ] Prompt: {prompt[:100]}{"..." if len(prompt) > 100 else ""}')
            
            # 6. 准备请求头
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }
            self._debug(f'[MJ] 请求头已准备: Content-Type=application/json, Authorization=Bearer ***')
            
            # 7. 处理参考图（如果有）
            base64_array = []
            refs = getattr(self, 'refs', []) or []
            
            if refs:
                if progress:
                    progress('Midjourney: 上传参考图...')
                
                from PySide6.QtGui import QImage
                from PySide6.QtCore import QBuffer, QByteArray, QIODevice
                
                for ref_path in refs:
                    try:
                        if not ref_path or not os.path.exists(ref_path):
                            continue
                        
                        # 获取MIME类型
                        mime_type = mimetypes.guess_type(ref_path)[0] or 'image/jpeg'
                        
                        # 读取并处理图片
                        img = QImage(ref_path)
                        if img.isNull():
                            self._debug(f'[MJ] 跳过无效图片: {ref_path}')
                            continue
                        
                        # 调整尺寸（MJ建议不超过1280px）
                        if img.width() > 1280 or img.height() > 1280:
                            img = img.scaled(1280, 1280, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        
                        # 转换为JPEG并压缩
                        buf = QBuffer()
                        buf.open(QIODevice.WriteOnly)
                        img.save(buf, 'JPEG', quality=85)
                        img_data = bytes(QByteArray(buf.data()))
                        buf.close()
                        
                        # Base64编码
                        b64_str = base64.b64encode(img_data).decode('utf-8')
                        base64_array.append(f'data:{mime_type};base64,{b64_str}')
                        
                        self._debug(f'[MJ] 已处理参考图: {ref_path} ({len(b64_str)} bytes)')
                        
                    except Exception as e:
                        self._debug(f'[MJ] 处理参考图失败 {ref_path}: {e}')
                        continue
                
                # 如果有参考图，先上传到Discord（api-349239130）
                if base64_array:
                    try:
                        upload_url = f'{base_url}/mj/submit/upload-discord-images'
                        upload_payload = {'base64Array': base64_array}
                        
                        self._debug(f'[MJ] 上传 {len(base64_array)} 张参考图到Discord')
                        
                        req = urllib.request.Request(
                            upload_url,
                            data=json.dumps(upload_payload).encode('utf-8'),
                            headers=headers,
                            method='POST'
                        )
                        
                        with urllib.request.urlopen(req, timeout=30) as response:
                            upload_resp = response.read().decode('utf-8')
                            self._debug(f'[MJ] 上传响应: {upload_resp[:200]}')
                            
                    except Exception as e:
                        self._debug(f'[MJ] 上传参考图警告: {e}')
                        # 继续执行，不中断流程
            
            # 8. 提交Imagine任务（api-349239131）
            if progress:
                progress('Midjourney: 提交生成任务...')
            
            imagine_url = f'{base_url}/mj/submit/imagine'
            
            # 根据API文档构建请求体
            # 文档示例: {"base64Array": [], "notifyHook": "", "prompt": "cat", "state": "", "botType": "MID_JOURNEY"}
            payload = {
                'botType': 'MID_JOURNEY',  # 必填，固定值
                'prompt': prompt.strip(),
                'base64Array': base64_array,  # 空数组也要传
                'notifyHook': '',
                'state': ''
            }
            
            self._debug(f'[MJ] ========== 提交Imagine任务 ==========')
            self._debug(f'[MJ] Imagine URL: {imagine_url}')
            self._debug(f'[MJ] 参考图数量: {len(base64_array)}')
            self._debug(f'[MJ] API Key前10位: {api_key[:10] if len(api_key) > 10 else api_key}')
            
            # 打印payload（隐藏base64内容）
            payload_debug = payload.copy()
            if payload_debug.get('base64Array'):
                payload_debug['base64Array'] = [f'<base64 image {i+1}, {len(b64)} chars>' for i, b64 in enumerate(payload['base64Array'])]
            self._debug(f'[MJ] Payload: {json.dumps(payload_debug, ensure_ascii=False, indent=2)}')
            
            try:
                self._debug(f'[MJ] 正在发送POST请求...')
                
                # 序列化payload
                payload_json = json.dumps(payload, ensure_ascii=False)
                payload_bytes = payload_json.encode('utf-8')
                self._debug(f'[MJ] Payload JSON: {payload_json}')
                self._debug(f'[MJ] Payload大小: {len(payload_bytes)} bytes')
                
                # 打印完整的请求信息用于调试
                self._debug(f'[MJ] 完整请求信息:')
                self._debug(f'[MJ]   URL: {imagine_url}')
                self._debug(f'[MJ]   Method: POST')
                self._debug(f'[MJ]   Content-Type: {headers.get("Content-Type")}')
                self._debug(f'[MJ]   Authorization: Bearer {api_key[:20]}...{api_key[-10:] if len(api_key) > 30 else ""}')
                
                req = urllib.request.Request(
                    imagine_url,
                    data=payload_bytes,
                    headers=headers,
                    method='POST'
                )
                
                self._debug(f'[MJ] 请求已创建，准备发送...')
                
                with urllib.request.urlopen(req, timeout=30) as response:
                    self._debug(f'[MJ] 收到响应，HTTP状态码: {response.status}')
                    resp_text = response.read().decode('utf-8')
                    self._debug(f'[MJ] 响应原文: {resp_text}')
                    
                    resp_data = json.loads(resp_text)
                    self._debug(f'[MJ] 解析后的响应: code={resp_data.get("code")}, description={resp_data.get("description")}')
                    
                    # 根据API文档，响应格式为：
                    # {code: 1, description: "Submit success", result: "taskId", properties: {...}}
                    if resp_data.get('code') != 1:
                        error_msg = resp_data.get('description', '未知错误')
                        self._debug(f'[MJ] 提交失败: code={resp_data.get("code")}, error={error_msg}')
                        return False, None, f'Midjourney 提交失败: {error_msg}'
                    
                    task_id = resp_data.get('result')
                    if not task_id:
                        self._debug(f'[MJ] 错误: 响应中没有result字段，完整响应: {resp_data}')
                        return False, None, 'Midjourney 错误: 未返回任务ID'
                    
                    self._debug(f'[MJ] ✓ 任务提交成功，任务ID: {task_id}')
                    
            except urllib.error.HTTPError as e:
                error_body = e.read().decode('utf-8', errors='ignore')
                self._debug(f'[MJ] ❌ HTTP错误 {e.code}')
                self._debug(f'[MJ] 错误响应体: {error_body}')
                
                # 特殊处理常见错误
                if e.code == 400:
                    self._debug(f'[MJ] 400错误通常表示: 请求格式错误或服务不可用')
                elif e.code == 401:
                    self._debug(f'[MJ] 401错误: API Key无效或未授权')
                    return False, None, 'Midjourney API Key无效，请检查配置'
                elif e.code == 403:
                    self._debug(f'[MJ] 403错误: 没有访问权限，可能需要开通MidJourney服务')
                    return False, None, 'Midjourney 服务未开通或无权限'
                elif e.code == 429:
                    self._debug(f'[MJ] 429错误: 请求过于频繁')
                    return False, None, 'Midjourney 请求过于频繁，请稍后再试'
                
                try:
                    error_data = json.loads(error_body)
                    error_msg = error_data.get('description', error_data.get('message', f'HTTP {e.code}'))
                    error_code = error_data.get('code', '')
                    error_type = error_data.get('type', '')
                    
                    self._debug(f'[MJ] 解析后的错误: code={error_code}, type={error_type}, msg={error_msg}')
                    
                    # 针对 all_retries_failed 错误给出具体建议
                    if 'all_retries_failed' in error_msg:
                        self._debug(f'[MJ] all_retries_failed 错误原因分析:')
                        self._debug(f'[MJ]   1. VectorEngine无法连接到上游Discord服务')
                        self._debug(f'[MJ]   2. 您的API Key可能没有MidJourney权限')
                        self._debug(f'[MJ]   3. MidJourney服务可能暂时不可用')
                        self._debug(f'[MJ]   4. 账户余额不足或配额已用完')
                        self._debug(f'[MJ] 建议:')
                        self._debug(f'[MJ]   - 登录VectorEngine控制台检查服务状态')
                        self._debug(f'[MJ]   - 确认API Key有MidJourney权限')
                        self._debug(f'[MJ]   - 检查账户余额和配额')
                        self._debug(f'[MJ]   - 联系VectorEngine技术支持')
                        return False, None, f'Midjourney服务暂时不可用（上游连接失败）\n请检查: 1)API Key权限 2)账户余额 3)服务状态'
                    
                except Exception as parse_err:
                    error_msg = f'HTTP {e.code}'
                    self._debug(f'[MJ] 无法解析错误响应: {parse_err}')
                
                return False, None, f'Midjourney 提交失败: {error_msg}'
            except Exception as e:
                self._debug(f'[MJ] ❌ 提交异常: {type(e).__name__}: {str(e)}')
                import traceback
                tb = traceback.format_exc()
                self._debug(f'[MJ] 完整堆栈:\n{tb}')
                return False, None, f'Midjourney 提交失败: {str(e)}'
            
            # 9. 轮询任务状态（api-349239132）
            if progress:
                progress('Midjourney: 等待生成...')
            
            query_url = f'{base_url}/mj/task/{task_id}/fetch'
            max_polls = 120  # 最多轮询120次（约10分钟，MJ生成较慢）
            poll_interval = 5  # 每5秒轮询一次
            
            for poll_count in range(max_polls):
                try:
                    time.sleep(poll_interval)
                    
                    req = urllib.request.Request(query_url, headers=headers)
                    with urllib.request.urlopen(req, timeout=15) as response:
                        resp_text = response.read().decode('utf-8')
                        resp_data = json.loads(resp_text)
                        
                        # 根据API文档，直接返回任务对象
                        status = resp_data.get('status')
                        progress_str = resp_data.get('progress', '')
                        
                        if progress:
                            progress(f'Midjourney: 生成中... {progress_str} ({poll_count + 1}/{max_polls})')
                        
                        self._debug(f'[MJ] 轮询 {poll_count + 1}: status={status}, progress={progress_str}')
                        
                        if status == 'SUCCESS':
                            # 任务成功，获取图片URL
                            image_url = resp_data.get('imageUrl')
                            if not image_url:
                                return False, None, 'Midjourney 错误: 未返回图片URL'
                            
                            self._debug(f'[MJ] 图片URL: {image_url}')
                            
                            # 下载图片
                            if progress:
                                progress('Midjourney: 下载图片...')
                            
                            try:
                                img_req = urllib.request.Request(image_url)
                                with urllib.request.urlopen(img_req, timeout=30) as img_response:
                                    img_data = img_response.read()
                                    
                                    from PySide6.QtGui import QImage, QPixmap
                                    from PySide6.QtCore import QByteArray
                                    
                                    qimg = QImage()
                                    qimg.loadFromData(QByteArray(img_data))
                                    
                                    if qimg.isNull():
                                        return False, None, 'Midjourney 错误: 图片加载失败'
                                    
                                    pix = QPixmap.fromImage(qimg)
                                    self._debug(f'[MJ] 图片下载成功: {pix.width()}x{pix.height()}')
                                    
                                    if progress:
                                        progress('Midjourney: 生成完成')
                                    
                                    return True, pix, 'Midjourney 生成成功'
                                    
                            except Exception as e:
                                self._debug(f'[MJ] 下载图片失败: {str(e)}')
                                return False, None, f'Midjourney 下载图片失败: {str(e)}'
                        
                        elif status == 'FAILURE' or status == 'FAIL':
                            fail_reason = resp_data.get('failReason', '未知原因')
                            return False, None, f'Midjourney 任务失败: {fail_reason}'
                        
                        elif status in ('NOT_START', 'SUBMITTED', 'IN_PROGRESS', 'PENDING', 'RUNNING'):
                            # 继续等待
                            continue
                        
                        else:
                            self._debug(f'[MJ] 未知状态: {status}')
                            continue
                            
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        # 任务可能还未创建，继续等待
                        self._debug(f'[MJ] 轮询 {poll_count + 1}: 任务尚未准备好 (404)')
                        continue
                    else:
                        self._debug(f'[MJ] 轮询HTTP错误: {e.code}')
                        continue
                except Exception as e:
                    self._debug(f'[MJ] 轮询异常: {str(e)}')
                    # 继续尝试
                    continue
            
            # 超时
            return False, None, f'Midjourney 超时: 任务在 {max_polls * poll_interval // 60} 分钟后仍未完成'
            
        except Exception as e:
            self._debug(f'[MJ] 意外错误: {str(e)}')
            import traceback
            self._debug(traceback.format_exc())
            return False, None, f'Midjourney 错误: {str(e)}'

    def _on_generate_done(self, prompt: str, provider: str, ok: bool, pix: QPixmap | None, msg: str | None):
        try:
            self._debug(f"on_done: enter ok={ok}, pix_null={True if (pix is None or pix.isNull()) else False}")
        except Exception:
            pass
        roi = None
        magic = False
        adv = False
        smart = False  # 智能生成模式
        smart_edit = False  # 智能修改模式
        smart_rect = None
        smart_mask = None
        try:
            roi = getattr(self, '_roi_rect', None)
            magic = getattr(self, '_magic_mode', False)
            adv = getattr(self, '_magic_advanced', False)
            smart = getattr(self, '_smart_mode', False)
            smart_edit = getattr(self, '_smart_edit_mode', False)
            smart_rect = getattr(self, '_smart_rect', None)
            smart_mask = getattr(self, '_smart_mask', None)
        except Exception:
            roi = None
        try:
            self._roi_rect = None
            self._magic_mode = False
            self._magic_advanced = False
            self._smart_mode = False
            self._smart_edit_mode = False
            self._smart_rect = None
            self._smart_mask = None
        except Exception:
            pass
        dlg = getattr(self, '_gen_dialog', None)
        if not ok or pix is None or pix.isNull():
            if dlg:
                dlg.set_error(msg or '生成失败')
                if not magic and not smart and not smart_edit:
                    dlg.append_log('将回退为占位图…')
            try:
                self._update_conn_status(msg or '生成失败', 'error')
            except Exception:
                pass
            if not magic and not smart and not smart_edit:
                mock = self._make_mock_pix(prompt, provider)
                path = self._save_and_append_recent(mock)
                try:
                    if path:
                        self._debug(f"saved placeholder: {path}")
                except Exception:
                    pass
                if dlg:
                    if path:
                        dlg.append_log(f"已保存占位图：{path}")
            if dlg:
                dlg.finish(False)
            return
        
        # 智能生成模式：基于遮罩合成，生成完整画布尺寸的图层
        if smart and smart_rect is not None and smart_mask is not None:
            try:
                self._debug('[智能生成] 开始处理生成结果...')
                
                # 0. 先保存API返回的原始分辨率图片到历史记录（1K/2K/4K）
                original_pix = pix  # 保存原始图片引用
                self._debug(f'[智能生成] API返回的原始分辨率: {original_pix.width()}x{original_pix.height()}')
                try:
                    saved_path = self._save_and_append_recent(original_pix)
                    if saved_path:
                        self._debug(f'[智能生成] 已保存原始分辨率图片到历史记录: {saved_path}')
                        self._add_to_history(saved_path, original_pix)
                    else:
                        self._debug('[智能生成] 保存原始分辨率图片到历史记录失败')
                except Exception as e:
                    self._debug(f'[智能生成] 添加原始分辨率图片到历史记录失败: {e}')
                
                # 1. 将生成的图片缩放到画板尺寸（用于图层显示）
                canvas_w = self.canvas.paint_layer.width()
                canvas_h = self.canvas.paint_layer.height()
                
                self._debug(f'[智能生成] 生成图尺寸: {pix.width()}x{pix.height()}, 画板尺寸: {canvas_w}x{canvas_h}')
                
                scaled_pix = pix.scaled(
                    canvas_w, 
                    canvas_h, 
                    Qt.IgnoreAspectRatio, 
                    Qt.SmoothTransformation
                )
                
                # 2. 对完整画布尺寸的生成图进行抠图（不裁剪）
                matted_full = None
                try:
                    self._debug('[智能生成] 开始自动抠图（完整画布）...')
                    from BiRefNet import BiRefNetMatting
                    mat = BiRefNetMatting(debug_sink=lambda m: self._debug(m))
                    
                    matted_result = mat.matting(scaled_pix)
                    
                    if matted_result is not None and not matted_result.isNull():
                        matted_full = matted_result
                        self._debug(f'[智能生成] 抠图完成，尺寸 {matted_full.width()}x{matted_full.height()}')
                    else:
                        self._debug('[智能生成] 抠图失败，使用原图')
                        matted_full = scaled_pix
                except Exception as e:
                    self._debug(f'[智能生成] 抠图异常: {e}，使用原图')
                    import traceback
                    self._debug(traceback.format_exc())
                    matted_full = scaled_pix
                
                # 3. 直接使用抠图后的完整人物（不使用遮罩限制显示范围）
                # 关键：遮罩只用于告诉 AI 修改哪个区域，不用于限制显示
                result_pix = matted_full
                
                if result_pix is not None and not result_pix.isNull():
                    # 5. 将完整画布尺寸的结果作为新图层添加
                    layer_name = '智能生成'
                    
                    lid = getattr(self.canvas, 'add_image_layer_at', lambda _p, _n, _x, _y, _s: None)(
                        result_pix,  # 完整画布尺寸
                        layer_name, 
                        0,  # x=0，从画布左上角开始
                        0,  # y=0
                        True  # show_thumb=True，显示缩略图
                    )
                    
                    self._debug(f'[智能生成] 已添加图层到画板，尺寸 {result_pix.width()}x{result_pix.height()}')
                    
                    # 6. 同步图层面板
                    try:
                        self.layers_panel.sync_from_canvas()
                    except Exception:
                        pass
                    
                    # 7. 更新状态（原始分辨率图片已在步骤0保存）
                    try:
                        self._update_conn_status('智能生成成功', 'success')
                    except Exception:
                        pass
                    
                    # 9. 完成并返回（不继续执行后续代码）
                    if dlg:
                        dlg.finish(True)
                    return
                else:
                    self._debug('[智能生成] 合成结果无效')
                    
            except Exception as e:
                self._debug(f'[智能生成] 处理异常: {e}')
                import traceback
                self._debug(traceback.format_exc())
            
            # 智能生成失败，也要返回，避免保存到"最近生成"
            if dlg:
                dlg.set_error('智能生成处理失败')
                dlg.finish(False)
            try:
                self._update_conn_status('智能生成失败', 'error')
            except Exception:
                pass
            return
        
        # 智能修改模式：只修改选区内容，返回完整画布图片（不抠图）
        if smart_edit and smart_rect is not None and smart_mask is not None:
            try:
                self._debug('[智能修改] 开始处理生成结果...')
                self._debug(f'[智能修改] pix是否为空: {pix is None or pix.isNull()}')
                
                # 0. 先保存API返回的原始分辨率图片到历史记录（1K/2K/4K）
                original_pix = pix  # 保存原始图片引用
                self._debug(f'[智能修改] API返回的原始分辨率: {original_pix.width()}x{original_pix.height()}')
                try:
                    saved_path = self._save_and_append_recent(original_pix)
                    if saved_path:
                        self._debug(f'[智能修改] 已保存原始分辨率图片到历史记录: {saved_path}')
                        self._add_to_history(saved_path, original_pix)
                    else:
                        self._debug('[智能修改] 保存原始分辨率图片到历史记录失败')
                except Exception as e:
                    self._debug(f'[智能修改] 添加原始分辨率图片到历史记录失败: {e}')
                
                # 1. 将AI生成的图片缩放到画板尺寸（用于图层显示）
                canvas_w = self.canvas.paint_layer.width()
                canvas_h = self.canvas.paint_layer.height()
                
                self._debug(f'[智能修改] 生成图尺寸: {pix.width()}x{pix.height()}, 画板尺寸: {canvas_w}x{canvas_h}')
                
                scaled_pix = pix.scaled(
                    canvas_w, 
                    canvas_h, 
                    Qt.IgnoreAspectRatio, 
                    Qt.SmoothTransformation
                )
                
                self._debug(f'[智能修改] 缩放后尺寸: {scaled_pix.width()}x{scaled_pix.height()}')
                
                # 2. 直接使用AI返回的图片，不进行抠图处理
                result_pix = scaled_pix
                
                self._debug(f'[智能修改] 准备添加图层，图片尺寸: {result_pix.width()}x{result_pix.height()}')
                
                if result_pix is not None and not result_pix.isNull():
                    # 3. 保存图片到临时文件用于调试
                    try:
                        from pathlib import Path
                        import tempfile
                        temp_dir = Path(tempfile.gettempdir())
                        debug_path = temp_dir / 'smart_edit_result_debug.png'
                        result_pix.save(str(debug_path), 'PNG')
                        self._debug(f'[智能修改] 调试图片已保存: {debug_path}')
                    except Exception as e:
                        self._debug(f'[智能修改] 保存调试图片失败: {e}')
                    
                    # 4. 将完整画布尺寸的结果作为新图层添加
                    layer_name = '智能修改'
                    
                    self._debug('[智能修改] 调用 add_image_layer_at...')
                    
                    lid = self.canvas.add_image_layer_at(
                        result_pix,
                        layer_name, 
                        0,  # x=0
                        0,  # y=0
                        True  # show_thumb=True
                    )
                    
                    self._debug(f'[智能修改] 已添加图层到画板，图层ID: {lid}, 尺寸: {result_pix.width()}x{result_pix.height()}')
                    
                    # 5. 强制刷新画板
                    try:
                        self.canvas.update()
                        self._debug('[智能修改] 画板已刷新')
                    except Exception as e:
                        self._debug(f'[智能修改] 刷新画板失败: {e}')
                    
                    # 6. 同步图层面板
                    try:
                        self.layers_panel.sync_from_canvas()
                        self._debug('[智能修改] 图层面板已同步')
                    except Exception as e:
                        self._debug(f'[智能修改] 同步图层面板失败: {e}')
                    
                    # 7. 更新状态（原始分辨率图片已在步骤0保存）
                    try:
                        self._update_conn_status('智能修改成功', 'success')
                    except Exception:
                        pass
                    
                    # 9. 显示成功消息
                    try:
                        QMessageBox.information(self, '智能修改成功', f'已添加新图层"{layer_name}"到画板')
                    except Exception:
                        pass
                    
                    # 10. 完成并返回
                    if dlg:
                        dlg.finish(True)
                    return
                else:
                    self._debug('[智能修改] 结果无效：result_pix为空')
                    
            except Exception as e:
                self._debug(f'[智能修改] 处理异常: {e}')
                import traceback
                self._debug(traceback.format_exc())
            
            # 智能修改失败，返回
            if dlg:
                dlg.set_error('智能修改处理失败')
                dlg.finish(False)
            try:
                self._update_conn_status('智能修改失败', 'error')
            except Exception:
                pass
            
            QMessageBox.warning(self, '智能修改失败', '处理失败，请查看调试信息')
            return
        
        # ROI 模式：仅修改方框内内容，并将返回图裁剪为方框区域
        if roi is not None and pix is not None and not pix.isNull():
            try:
                cw = self.canvas.paint_layer.width()
                ch = self.canvas.paint_layer.height()
                
                # 重要修改：不要强制缩放到画板尺寸，保持原始高质量
                # 只裁剪对应的 ROI 区域，不改变分辨率
                # 计算缩放比例以匹配 ROI 区域
                roi_w = roi.width()
                roi_h = roi.height()
                
                # 如果生成的图片比画板大，按比例计算需要裁剪的区域
                # 否则直接使用原图
                if pix.width() > cw or pix.height() > ch:
                    # 按画板尺寸缩放图片以便裁剪正确的区域
                    spix = pix.scaled(cw, ch, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    cropped = spix.copy(roi)
                else:
                    # 图片尺寸小于等于画板，直接裁剪
                    cropped = pix.copy(roi) if roi.width() <= pix.width() and roi.height() <= pix.height() else pix
                
                try:
                    self._debug(f'ROI 模式：原图 {pix.width()}x{pix.height()}, 画板 {cw}x{ch}, ROI {roi_w}x{roi_h}, 裁剪后 {cropped.width()}x{cropped.height()}')
                except Exception:
                    pass
                if adv:
                    try:
                        self._debug('高级魔法生成：自动抠图开始')
                    except Exception:
                        pass
                    try:
                        self._debug('高级魔法生成：准备调用 BiRefNet 抠图')
                        from BiRefNet import BiRefNetMatting
                        mat = BiRefNetMatting(debug_sink=lambda m: self._debug(m))
                        res = mat.matting(cropped)
                        if res is not None and not res.isNull():
                            cropped = res
                            try:
                                self._debug(f'高级魔法生成：抠图完成，结果尺寸 {cropped.width()}x{cropped.height()}')
                            except Exception:
                                pass
                        else:
                            try:
                                self._debug('高级魔法生成：抠图失败，使用原裁剪图（不启用兜底抠图）')
                            except Exception:
                                pass
                    except Exception:
                        try:
                            self._debug('高级魔法生成：抠图异常，使用原裁剪图（不启用兜底抠图）')
                        except Exception:
                            pass
                else:
                    try:
                        self._debug('未进入高级模式：跳过抠图')
                    except Exception:
                        pass
                path = None if magic else self._save_and_append_recent(cropped)
                try:
                    self.layers_panel.sync_from_canvas()
                except Exception:
                    pass
                try:
                    layer_name = '高级魔法生成' if adv else '魔法生成'
                    x0, y0 = roi.x(), roi.y()
                    lid = getattr(self.canvas, 'add_image_layer_at', lambda _p, _n, _x, _y, _s: None)(cropped, layer_name, x0, y0, False)
                    try:
                        self._debug(f'{layer_name}：已叠加到画板 ({x0},{y0}) 尺寸 {cropped.width()}x{cropped.height()}')
                    except Exception:
                        pass
                    try:
                        self.layers_panel.sync_from_canvas()
                    except Exception:
                        pass
                except Exception:
                    path = path
            except Exception:
                path = self._save_and_append_recent(pix)
        else:
            # 非 ROI 模式：移除强制缩放逻辑，保持原图质量
            # 重要修改：不再将生成的高分辨率图片缩小到固定尺寸
            # 直接使用 API 返回的原始分辨率
            try:
                pw, ph = pix.width(), pix.height()
                self._debug(f"非 ROI 模式：保持原图尺寸 {pw}x{ph}，不进行缩放")
            except Exception:
                pass
            
            # 移除旧的 size_map 缩放逻辑
            # 旧代码会将 4K 图片缩小到 1792x1024 等固定尺寸
            # 现在直接使用原图
            if adv:
                try:
                    self._debug('高级魔法生成：自动抠图开始')
                except Exception:
                    pass
                try:
                    self._debug('高级魔法生成：准备调用 BiRefNet 抠图')
                    from BiRefNet import BiRefNetMatting
                    mat = BiRefNetMatting(debug_sink=lambda m: self._debug(m))
                    res = mat.matting(pix)
                    if res is not None and not res.isNull():
                        pix = res
                        try:
                            self._debug(f'高级魔法生成：抠图完成，结果尺寸 {pix.width()}x{pix.height()}')
                        except Exception:
                            pass
                    else:
                        try:
                            self._debug('高级魔法生成：抠图失败，使用原图（不启用兜底抠图）')
                        except Exception:
                            pass
                except Exception:
                    try:
                        self._debug('高级魔法生成：抠图异常，使用原图（不启用兜底抠图）')
                    except Exception:
                        pass
                path = None
            else:
                path = self._save_and_append_recent(pix)
        try:
            if path:
                self._debug(f"saved image: {path}")
            # 按你的要求：不自动推送到画板，仅保存在"最近生成"区域
        except Exception:
            pass
        if dlg:
            if path:
                dlg.append_log(f"已保存图片：{path}")
            dlg.finish(True)
        try:
            self._update_conn_status('生成成功，已保存图片', 'success')
        except Exception:
            pass

    def _apply_smart_mask_with_matting(self, matted_full: QPixmap, rect, mask) -> QPixmap | None:
        """
        智能生成合成：将抠图后的完整生成图合成到画布
        
        Args:
            matted_full: 抠图后的完整画布尺寸图片（完整人物，已去除背景）
            rect: 选区矩形范围（仅用于日志）
            mask: 二维布尔数组，True表示选区内（画板绝对坐标）
            
        Returns:
            完整画布尺寸的合成图（只在遮罩区域显示新内容，其他区域显示原画布）
        """
        try:
            from PySide6.QtGui import QImage, QPainter
            import numpy as np
            
            # 获取原始画板合成图
            original_img = self.canvas._composite_to_image()
            canvas_w = original_img.width()
            canvas_h = original_img.height()
            
            self._debug(f'[智能合成] 画板尺寸: {canvas_w}x{canvas_h}')
            self._debug(f'[智能合成] 选区范围: ({rect.x()},{rect.y()}) {rect.width()}x{rect.height()}')
            self._debug(f'[智能合成] 抠图内容尺寸: {matted_full.width()}x{matted_full.height()}')
            
            # 创建完整画布尺寸的透明图层
            result_pix = QPixmap(canvas_w, canvas_h)
            result_pix.fill(Qt.transparent)
            
            # 转换抠图内容为图像（完整画布尺寸）
            matted_img = matted_full.toImage().convertToFormat(QImage.Format_RGBA8888)
            matted_w, matted_h = matted_img.width(), matted_img.height()
            matted_ptr = matted_img.bits()
            if hasattr(matted_ptr, 'setsize'):
                matted_ptr.setsize(matted_img.sizeInBytes())
            matted_arr = np.frombuffer(matted_ptr, dtype=np.uint8).reshape(matted_h, matted_w, 4).copy()
            
            # 转换结果图为数组
            result_img = result_pix.toImage().convertToFormat(QImage.Format_RGBA8888)
            result_ptr = result_img.bits()
            if hasattr(result_ptr, 'setsize'):
                result_ptr.setsize(result_img.sizeInBytes())
            result_arr = np.frombuffer(result_ptr, dtype=np.uint8).reshape(canvas_h, canvas_w, 4).copy()
            
            # 获取原图数组（用于非遮罩区域）
            orig_img = original_img.convertToFormat(QImage.Format_RGBA8888)
            orig_ptr = orig_img.bits()
            if hasattr(orig_ptr, 'setsize'):
                orig_ptr.setsize(orig_img.sizeInBytes())
            orig_arr = np.frombuffer(orig_ptr, dtype=np.uint8).reshape(canvas_h, canvas_w, 4).copy()
            
            # 根据遮罩合成
            replaced_count = 0
            mask_h = len(mask)
            mask_w = len(mask[0]) if mask_h > 0 else 0
            
            # 遍历整个画布
            for y in range(canvas_h):
                for x in range(canvas_w):
                    # 检查是否在遮罩范围内
                    if y < mask_h and x < mask_w and mask[y][x]:
                        # 在遮罩内：使用抠图后的完整内容（完整人物）
                        # 因为 matted_full 是完整画布尺寸，直接使用相同坐标
                        if y < matted_h and x < matted_w:
                            pixel = matted_arr[y, x]
                            # 只有当像素不是完全透明时才替换
                            if pixel[3] > 0:  # alpha > 0
                                result_arr[y, x] = pixel
                                replaced_count += 1
                            else:
                                # 抠图后是透明的，保留原背景（不是黑色）
                                result_arr[y, x] = orig_arr[y, x]
                        else:
                            # 超出抠图范围，使用原画布内容
                            result_arr[y, x] = orig_arr[y, x]
                    else:
                        # 不在遮罩内：使用原画布内容
                        result_arr[y, x] = orig_arr[y, x]
            
            self._debug(f'[智能合成] 替换了 {replaced_count} 个像素')
            
            # 转换回 QPixmap
            bytes_per_line = 4 * canvas_w
            final_img = QImage(
                result_arr.tobytes(), 
                canvas_w, 
                canvas_h, 
                bytes_per_line, 
                QImage.Format_RGBA8888
            )
            final_pix = QPixmap.fromImage(final_img.copy())
            
            self._debug(f'[智能合成] 合成完成，结果尺寸: {final_pix.width()}x{final_pix.height()}')
            
            return final_pix
            
        except Exception as e:
            self._debug(f'[智能合成] 异常: {e}')
            import traceback
            self._debug(traceback.format_exc())
            return None

    def _apply_smart_mask(self, generated_pix: QPixmap, rect, mask) -> QPixmap | None:
        """
        智能生成合成：将生成的图片与原画板合成，只替换遮罩区域
        
        Args:
            generated_pix: AI生成的新图片
            rect: 选区矩形范围
            mask: 二维布尔数组，True表示选区内（坐标系：画板绝对坐标）
            
        Returns:
            合成后的完整画板图片
        """
        try:
            from PySide6.QtGui import QImage, QPainter
            import numpy as np
            
            # 获取原始画板合成图
            original_img = self.canvas._composite_to_image()
            canvas_w = original_img.width()
            canvas_h = original_img.height()
            
            self._debug(f'[智能合成] 画板尺寸: {canvas_w}x{canvas_h}')
            self._debug(f'[智能合成] 选区范围: ({rect.x()},{rect.y()}) {rect.width()}x{rect.height()}')
            self._debug(f'[智能合成] 生成图尺寸: {generated_pix.width()}x{generated_pix.height()}')
            
            # 将生成的图片缩放到画板大小（保持完整画面，用于提取对应区域）
            scaled_gen = generated_pix.scaled(
                canvas_w, 
                canvas_h, 
                Qt.IgnoreAspectRatio, 
                Qt.SmoothTransformation
            )
            
            # 转换为 numpy 数组进行像素级操作
            # 原图
            orig_qimg = original_img.convertToFormat(QImage.Format_RGBA8888)
            orig_w, orig_h = orig_qimg.width(), orig_qimg.height()
            orig_ptr = orig_qimg.bits()
            if hasattr(orig_ptr, 'setsize'):
                orig_ptr.setsize(orig_qimg.sizeInBytes())
            orig_arr = np.frombuffer(orig_ptr, dtype=np.uint8).reshape(orig_h, orig_w, 4).copy()
            
            # 生成图
            gen_qimg = scaled_gen.toImage().convertToFormat(QImage.Format_RGBA8888)
            gen_w, gen_h = gen_qimg.width(), gen_qimg.height()
            gen_ptr = gen_qimg.bits()
            if hasattr(gen_ptr, 'setsize'):
                gen_ptr.setsize(gen_qimg.sizeInBytes())
            gen_arr = np.frombuffer(gen_ptr, dtype=np.uint8).reshape(gen_h, gen_w, 4).copy()
            
            # 创建输出数组（复制原图）
            result_arr = orig_arr.copy()
            
            # 根据遮罩替换像素
            # mask 的坐标系是画板绝对坐标（0-based）
            mask_h = len(mask)
            mask_w = len(mask[0]) if mask_h > 0 else 0
            
            replaced_count = 0
            for y in range(mask_h):
                for x in range(mask_w):
                    # 检查是否在遮罩内
                    if mask[y][x]:
                        # 检查是否在画板范围内
                        if x < 0 or x >= orig_w or y < 0 or y >= orig_h:
                            continue
                        
                        # 检查生成图对应位置
                        if x < gen_w and y < gen_h:
                            # 替换像素（使用生成图的像素）
                            result_arr[y, x] = gen_arr[y, x]
                            replaced_count += 1
            
            self._debug(f'[智能合成] 替换了 {replaced_count} 个像素')
            
            # 转换回 QPixmap
            bytes_per_line = 4 * orig_w
            result_img = QImage(
                result_arr.tobytes(), 
                orig_w, 
                orig_h, 
                bytes_per_line, 
                QImage.Format_RGBA8888
            )
            result_pix = QPixmap.fromImage(result_img.copy())
            
            self._debug(f'[智能合成] 合成完成，结果尺寸: {result_pix.width()}x{result_pix.height()}')
            
            return result_pix
            
        except Exception as e:
            self._debug(f'[智能合成] 异常: {e}')
            import traceback
            self._debug(traceback.format_exc())
            return None

    def _fallback_matting(self, pix: QPixmap) -> QPixmap:
        try:
            from PySide6.QtGui import QImage
            import numpy as np
            qimg = pix.toImage().convertToFormat(QImage.Format_RGBA8888)
            w, h = qimg.width(), qimg.height()
            ptr = qimg.constBits()
            if hasattr(ptr, 'setsize'):
                ptr.setsize(qimg.sizeInBytes())
            arr = np.frombuffer(ptr, dtype=np.uint8).reshape(h, w, 4)
            rgb = arr[:, :, :3].astype(np.float32)
            edges = np.concatenate([rgb[0, :, :], rgb[h - 1, :, :], rgb[:, 0, :], rgb[:, w - 1, :]], axis=0)
            bg = edges.mean(axis=0)
            dist = np.linalg.norm(rgb - bg, axis=2)
            m = float(np.percentile(dist, 95))
            m = m if m > 1e-3 else 1.0
            alpha = np.clip((dist / m) * 255.0, 0, 255).astype(np.uint8)
            out = np.dstack([arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], alpha])
            bytes_per_line = 4 * w
            out_img = QImage(out.tobytes(), w, h, bytes_per_line, QImage.Format_RGBA8888)
            return QPixmap.fromImage(out_img.copy())
        except Exception:
            return pix

    def _save_and_append_recent(self, pix: QPixmap) -> str | None:
        # 保存到 JPG 目录
        path_str = None
        try:
            jpg_dir = Path(__file__).resolve().parent / 'JPG'
            jpg_dir.mkdir(exist_ok=True)
            filename = datetime.now().strftime('%Y%m%d-%H%M%S') + '.jpg'
            save_path = jpg_dir / filename
            # 不再添加水印
            wm_pix = pix
            wm_pix.save(str(save_path), 'JPEG')
            path_str = str(save_path)
            
            # 添加到历史记录
            self._add_to_history(path_str, pix)
        except Exception:
            pass

        # 更新最近列表
        size = self.recent_list.iconSize()
        grid = self.recent_list.gridSize()
        try:
            self._debug(
                f"recent_list before: count={self.recent_list.count()}, icon={size.width()}x{size.height()}, grid={grid.width()}x{grid.height()}, list_h={self.recent_list.height()}, pix={pix.width()}x{pix.height()}"
            )
        except Exception:
            pass
        thumb = wm_pix.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        # 如果已经达到容量上限（9张），清空列表重新开始
        if self.recent_list.count() >= self.recent_capacity:
            self.recent_list.clear()
            self._recent_cycle_index = 0
            try:
                self._debug(f"recent_list cleared: reached capacity {self.recent_capacity}, starting fresh")
            except Exception:
                pass
        
        # 添加新图片
        item = QListWidgetItem(QIcon(thumb), '')
        if path_str:
            item.setData(Qt.UserRole, path_str)
            try:
                item.setToolTip(path_str)
            except Exception:
                pass
        self.recent_list.addItem(item)
        added_idx = self.recent_list.count() - 1
        try:
            # 主动刷新显示
            self.recent_list.viewport().update()
            self.recent_list.update()
            self._debug(f"recent_list after: count={self.recent_list.count()}, last_idx={added_idx}")
        except Exception:
            pass
        return path_str

    def _report_progress(self, text: str):
        dlg = getattr(self, '_gen_dialog', None)
        # 确保所有UI更新在主线程执行，避免跨线程卡顿或无响应
        def apply():
            try:
                if dlg:
                    dlg.append_log(text)
                    dlg.set_status(text)
                # 同步到主窗口左下角"已连接"区域（直接调用，避免嵌套定时导致丢失）
                win = self.window()
                if win and hasattr(win, 'set_connection_text'):
                    win.set_connection_text(text, 'loading')
            except Exception:
                pass
        QTimer.singleShot(0, apply)

    def _generate_with_gemini(self, prompt: str, progress=None) -> tuple[bool, QPixmap | None, str]:
        """调用 BANANA 生成图片，返回 (ok, QPixmap, message)。失败时 pix 为 None。"""
        try:
            cfg = gemini_get_config()
            api_key = (cfg.get('api_key') or '').strip()
            base_url = (cfg.get('base_url') or '').strip().strip(' ,`')
            model = (cfg.get('model') or 'gemini-2.5-flash-image').strip().strip(' ,`')
            
            # ⭐ 在界面上显示正在使用的模型
            try:
                win = self.window()
                if win and hasattr(win, 'set_connection_text'):
                    win.set_connection_text(f'BANANA - {model}', 'loading')
            except Exception:
                pass
            
            try:
                self._debug(f"gemini cfg: base_url={base_url}, model={model}")
            except Exception:
                pass
            if not api_key or not base_url:
                if progress:
                    QTimer.singleShot(0, lambda: self._report_progress('配置不完整：缺少 API Key 或 Base URL'))
                return False, None, 'Gemini 配置不完整'
            # 构造请求（对齐 web/image/image.html 的 Banana 调用）
            # 1) 解析当前比例，映射尺寸
            try:
                ar_text = self.combo_ratio.currentText()
                w_str, h_str = ar_text.split(':')
                rw, rh = int(w_str), int(h_str)
                ar = f"{rw}:{rh}"
            except Exception:
                ar = None
            size_map = {
                '1:1': { 'width': 1024, 'height': 1024 },
                '16:9': { 'width': 1792, 'height': 1024 },
                '9:16': { 'width': 1024, 'height': 1792 },
                '4:3': { 'width': 1344, 'height': 1008 },
                '3:4': { 'width': 1008, 'height': 1344 },
            }
            try:
                self._debug(f"aspect_ratio={ar}, size={size_map.get(ar)}")
            except Exception:
                pass

            # 2) 收集草图/参考图（优先第4张参考图；否则使用当前画板合成）
            def _scale_image(qimg, max_dim: int) -> 'QImage':
                try:
                    w = qimg.width()
                    h = qimg.height()
                    if w <= 0 or h <= 0:
                        return qimg
                    if max(w, h) <= max_dim:
                        return qimg
                    from PySide6.QtCore import Qt as _Qt
                    return qimg.scaled(max_dim, max_dim, _Qt.KeepAspectRatio, _Qt.SmoothTransformation)
                except Exception:
                    return qimg

            def qimage_to_base64_png(qimg, max_dim: int = 1024):
                try:
                    qimg2 = _scale_image(qimg, max_dim)
                    buf = QBuffer()
                    buf.open(QIODevice.WriteOnly)
                    qimg2.save(buf, 'PNG')
                    data = bytes(buf.data())
                    buf.close()
                    return base64.b64encode(data).decode('ascii')
                except Exception:
                    return None

            def qimage_to_base64_jpeg(qimg, max_dim: int = 768, quality: int = 85):
                try:
                    qimg2 = _scale_image(qimg, max_dim)
                    buf = QBuffer()
                    buf.open(QIODevice.WriteOnly)
                    qimg2.save(buf, 'JPEG', quality)
                    data = bytes(buf.data())
                    buf.close()
                    return base64.b64encode(data).decode('ascii')
                except Exception:
                    return None

            sketch_part = None
            try:
                ref4 = None
                if isinstance(getattr(self, 'refs', None), list) and len(self.refs) >= 4:
                    ref4 = self.refs[3]
                if ref4:
                    from PySide6.QtGui import QImage
                    img = QImage(ref4)
                    if not img.isNull():
                        b64 = qimage_to_base64_png(img, max_dim=1024)
                        if b64:
                            sketch_part = { 'inlineData': { 'mimeType': 'image/png', 'data': b64 } }
                if not sketch_part:
                    # 使用当前画板合成作为草图
                    qimg = self.canvas._composite_to_image() if hasattr(self.canvas, '_composite_to_image') else None
                    if qimg is not None and not qimg.isNull():
                        b64 = qimage_to_base64_png(qimg, max_dim=1024)
                        if b64:
                            sketch_part = { 'inlineData': { 'mimeType': 'image/png', 'data': b64 } }
            except Exception:
                sketch_part = None

            style_parts = []
            try:
                if isinstance(getattr(self, 'refs', None), list):
                    from PySide6.QtGui import QImage
                    # 处理 refs[0], refs[1], refs[2] 作为风格参考
                    for i in (0, 1, 2):
                        p = self.refs[i] if i < len(self.refs) else None
                        if not p:
                            continue
                        img = QImage(p)
                        if img.isNull():
                            continue
                        # 参考图使用 JPEG 有损压缩以降低请求体积
                        b64 = qimage_to_base64_jpeg(img, max_dim=768, quality=85)
                        if b64:
                            style_parts.append({ 'inlineData': { 'mimeType': 'image/jpeg', 'data': b64 } })
                    
                    # 处理 refs[4]（智能替换上传的图片）作为重要的风格/内容参考
                    if len(self.refs) >= 5:
                        p = self.refs[4]
                        if p:
                            img = QImage(p)
                            if not img.isNull():
                                # 用户上传的图片使用 PNG 保持质量
                                b64 = qimage_to_base64_png(img, max_dim=1024)
                                if b64:
                                    # 插入到 style_parts 的开头，让 AI 优先考虑
                                    style_parts.insert(0, { 'inlineData': { 'mimeType': 'image/png', 'data': b64 } })
                                    try:
                                        self._debug('[Gemini] 已添加 refs[4] (用户上传图片) 到请求')
                                    except Exception:
                                        pass
            except Exception as e:
                try:
                    self._debug(f'[Gemini] 处理参考图失败: {e}')
                except Exception:
                    pass
                style_parts = []

            # ROI：若存在选区，裁剪当前画板合成图作为"目标区域参考"
            roi_part = None
            try:
                roi = getattr(self, '_roi_rect', None)
                if roi is not None:
                    qimg_all = self.canvas._composite_to_image() if hasattr(self.canvas, '_composite_to_image') else None
                    if qimg_all is not None and not qimg_all.isNull():
                        # 约束选区在图像范围内
                        rx = max(0, roi.x() - 2)
                        ry = max(0, roi.y() - 2)
                        rw = max(1, min(roi.width() + 4, qimg_all.width() - rx))
                        rh = max(1, min(roi.height() + 4, qimg_all.height() - ry))
                        from PySide6.QtCore import QRect as _QRect
                        clip = qimg_all.copy(_QRect(rx, ry, rw, rh))
                        b64 = qimage_to_base64_png(clip, max_dim=768)
                        if b64:
                            roi_part = { 'inlineData': { 'mimeType': 'image/png', 'data': b64 } }
            except Exception:
                roi_part = None

            # 3) 组织 parts
            parts = []
            txt = (prompt or '').strip()
            parts.append({ 'text': txt if txt else '生成一张图片' })
            if roi_part:
                parts.append({ 'text': '请只修改绿色方框内的区域，以下为裁剪的目标区域参考：' })
                parts.append(roi_part)
            if sketch_part:
                parts.append({ 'text': '请依据这张草图进行主要构图与元素布局：' })
                parts.append(sketch_part)
            if style_parts:
                # 检查是否有用户上传的图片（refs[4]）
                has_upload = False
                try:
                    if isinstance(getattr(self, 'refs', None), list) and len(self.refs) >= 5 and self.refs[4]:
                        has_upload = True
                except Exception:
                    pass
                
                if has_upload and len(style_parts) > 0:
                    # 第一张是用户上传的图片，特别说明
                    parts.append({ 'text': '以下是需要融合的主要内容图片，请将其智能融合到草图的绿色区域内：' })
                    parts.append(style_parts[0])
                    # 其余是风格参考
                    if len(style_parts) > 1:
                        parts.append({ 'text': '以下是风格/细节参考图：' })
                        parts.extend(style_parts[1:])
                else:
                    # 没有上传图片，全部作为风格参考
                    parts.append({ 'text': '以下是风格/细节参考图：' })
                    parts.extend(style_parts)
            try:
                self._debug(f"parts: roi={'yes' if roi_part else 'no'}, sketch={'yes' if sketch_part else 'no'}, style_count={len(style_parts)}, text_len={len(txt)}")
            except Exception:
                pass

            # 4) generationConfig：指定输出为图片与输出比例
            # 注意：官方 API 不接受对图片使用 responseMimeType（仅限文本类：text/plain 等）
            # 因此这里只设置 responseModalities，并通过 imageConfig 传递宽高比
            gen_cfg = { 'responseModalities': ['IMAGE'] }
            if ar:
                gen_cfg['imageConfig'] = { 'aspectRatio': ar }
            try:
                self._debug(f"gen_cfg: {json.dumps(gen_cfg, ensure_ascii=False)}")
            except Exception:
                pass

            if progress:
                QTimer.singleShot(0, lambda: self._report_progress('发送请求…'))
            
            # 根据 base_url 决定认证方式
            # 如果是云雾 API (yunwu.ai)，使用 Bearer token；否则使用 URL 参数
            use_bearer_auth = 'yunwu.ai' in base_url.lower()
            if use_bearer_auth:
                endpoint = base_url.rstrip('/') + f"/models/{model}:generateContent"
                auth_headers = {
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json, image/*'
                }
            else:
                endpoint = base_url.rstrip('/') + f"/models/{model}:generateContent?key={api_key}"
                auth_headers = {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json, image/*'
                }
            
            payload = {
                'contents': [{ 'role': 'user', 'parts': parts }],
                'generationConfig': gen_cfg,
                # 尝试提示只输出图片
                'systemInstruction': { 'role': 'system', 'parts': [ { 'text': '只输出图片，不要文本描述。' } ] }
            }
            data = json.dumps(payload).encode('utf-8')
            try:
                self._debug(f"POST {endpoint} bytes={len(data)}, use_bearer={use_bearer_auth}")
            except Exception:
                pass
            req = urllib.request.Request(
                endpoint,
                data=data,
                headers=auth_headers
            )
            # 第一次尝试：完整负载，较短超时
            timed_out = False
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    content_type = resp.headers.get('Content-Type', '')
                    resp_data = resp.read()
            except urllib.error.URLError as e:
                timed_out = 'timed out' in str(e).lower() or isinstance(getattr(e, 'reason', None), socket.timeout)
                if not timed_out:
                    raise
                try:
                    self._debug("request timed out; retrying without style refs and longer timeout…")
                except Exception:
                    pass
                # 回退：移除参考图，仅保留提示词与草图，减小请求体积
                lean_parts = []
                if txt:
                    lean_parts.append({ 'text': txt })
                if roi_part:
                    lean_parts.append({ 'text': '请只修改绿色方框内的区域，以下为裁剪的目标区域参考：' })
                    lean_parts.append(roi_part)
                if sketch_part:
                    lean_parts.append({ 'text': '请依据这张草图进行主要构图与元素布局：' })
                    lean_parts.append(sketch_part)
                lean_payload = {
                    'contents': [{ 'role': 'user', 'parts': lean_parts }],
                    'generationConfig': gen_cfg,
                    'systemInstruction': { 'role': 'system', 'parts': [ { 'text': '只输出图片，不要文本描述。' } ] }
                }
                lean_data = json.dumps(lean_payload).encode('utf-8')
                try:
                    self._debug(f"POST {endpoint} (lean) bytes={len(lean_data)}")
                except Exception:
                    pass
                req2 = urllib.request.Request(
                    endpoint,
                    data=lean_data,
                    headers=auth_headers
                )
                with urllib.request.urlopen(req2, timeout=90) as resp:
                    content_type = resp.headers.get('Content-Type', '')
                    resp_data = resp.read()
            except urllib.error.HTTPError as e:
                # 对部分聚合服务（如 vectorengine.ai）进行路径/负载适配回退
                code = getattr(e, 'code', 0)
                host = ''
                try:
                    host = urllib.parse.urlparse(base_url).hostname or ''
                except Exception:
                    pass
                should_adapter = ('vectorengine.ai' in host) and (code in (400, 401, 403, 404, 409, 422, 429))
                if not should_adapter:
                    raise
                try:
                    self._debug(f"HTTP {code} on primary route; trying vectorengine responses adapter…")
                except Exception:
                    pass
                # 构造 OpenAI Responses 风格回退
                base = base_url.rstrip('/')
                if base.endswith('/v1'):
                    alt_endpoint = base + '/responses'
                else:
                    alt_endpoint = base + '/v1/responses'

                # 组装 responses 风格 input 内容
                def _make_contents_for_responses():
                    items = []
                    if txt:
                        items.append({ 'type': 'input_text', 'text': txt })
                    # ROI
                    try:
                        roi = getattr(self, '_roi_rect', None)
                        if roi is not None:
                            # 已在主路由构造了 roi_part，这里重建一次以避免闭包引用问题
                            qimg_all = self.canvas._composite_to_image() if hasattr(self.canvas, '_composite_to_image') else None
                            if qimg_all is not None and not qimg_all.isNull():
                                rx = max(0, roi.x())
                                ry = max(0, roi.y())
                                rw = max(1, min(roi.width(), qimg_all.width() - rx))
                                rh = max(1, min(roi.height(), qimg_all.height() - ry))
                                from PySide6.QtCore import QRect as _QRect
                                clip = qimg_all.copy(_QRect(rx, ry, rw, rh))
                                b64 = qimage_to_base64_png(clip, max_dim=768)
                                if b64:
                                    items.append({ 'type': 'input_text', 'text': '请只修改绿色方框内的区域，以下为裁剪的目标区域参考：' })
                                    items.append({ 'type': 'input_image', 'image_data': b64, 'mime_type': 'image/png' })
                    except Exception:
                        pass
                    # 草图
                    if sketch_part and isinstance(sketch_part, dict):
                        inline = sketch_part.get('inlineData') or {}
                        b64 = inline.get('data')
                        mt = inline.get('mimeType') or 'image/png'
                        if b64:
                            items.append({ 'type': 'input_image', 'image_data': b64, 'mime_type': mt })
                    # 参考图
                    for sp in style_parts or []:
                        try:
                            inline = sp.get('inlineData') or {}
                            b64 = inline.get('data')
                            mt = inline.get('mimeType') or 'image/jpeg'
                            if b64:
                                items.append({ 'type': 'input_image', 'image_data': b64, 'mime_type': mt })
                        except Exception:
                            continue
                    return items

                input_item = { 'role': 'user', 'content': _make_contents_for_responses() }
                # aspect ratio 映射
                img_obj = { 'format': 'png' }
                if ar:
                    img_obj['aspect_ratio'] = ar
                alt_payload = {
                    'model': model,
                    'input': [ input_item ],
                    'modalities': ['IMAGE'],
                    'image': img_obj
                }
                alt_data = json.dumps(alt_payload).encode('utf-8')
                try:
                    self._debug(f"POST {alt_endpoint} (adapter) bytes={len(alt_data)}")
                except Exception:
                    pass
                headers = {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
                # 许多聚合使用 Bearer 鉴权
                if api_key:
                    headers['Authorization'] = f"Bearer {api_key}"
                req3 = urllib.request.Request(alt_endpoint, data=alt_data, headers=headers)
                with urllib.request.urlopen(req3, timeout=90) as resp:
                    content_type = resp.headers.get('Content-Type', '')
                    resp_data = resp.read()
            try:
                self._debug(f"response: ct={content_type}, bytes={len(resp_data) if isinstance(resp_data,(bytes,bytearray)) else 'n/a'}")
            except Exception:
                pass
            if progress:
                QTimer.singleShot(0, lambda: self._report_progress(f"解析响应… Content-Type={content_type or '未知'}, bytes={len(resp_data) if isinstance(resp_data,(bytes,bytearray)) else 'n/a'}"))

            # 情况 A：直接返回二进制图片（部分代理或实现可能如此）
            if content_type.startswith('image/') or (content_type == '' and resp_data and resp_data[:8] in (b'\x89PNG\r\n\x1a\n',)):
                if progress:
                    QTimer.singleShot(0, lambda: self._report_progress('解码图片（二进制）…'))
                try:
                    self._debug(f"decode binary image bytes={len(resp_data)}")
                except Exception:
                    pass
                from PySide6.QtGui import QImage
                img = QImage.fromData(resp_data)
                if img.isNull():
                    return False, None, '图片数据无效'
                return True, QPixmap.fromImage(img), 'ok'

            # 情况 B：JSON 返回，解析 base64
            text = resp_data.decode('utf-8', errors='ignore') if isinstance(resp_data, (bytes, bytearray)) else resp_data
            obj = None
            try:
                obj = json.loads(text)
                try:
                    self._debug(f"json parsed; top-keys={list(obj.keys())[:6]}")
                    # 额外输出模型版本/响应ID/用量与提示词反馈，便于排查
                    mv = obj.get('modelVersion')
                    rid = obj.get('responseId')
                    usage = obj.get('usageMetadata') or {}
                    pfb = obj.get('promptFeedback') or {}
                    if mv or rid:
                        self._debug(f"modelVersion={mv}, responseId={rid}")
                    if usage:
                        self._debug(f"usage={usage}")
                    if pfb:
                        self._debug(f"promptFeedback={pfb}")
                    # 列出首个候选的各 part 类型
                    cands_preview = obj.get('candidates') or []
                    if cands_preview:
                        c0 = cands_preview[0] or {}
                        cont = c0.get('content') or {}
                        parts_preview = cont.get('parts') or []
                        kinds = []
                        for p in parts_preview[:6]:
                            if isinstance(p, dict):
                                if 'inlineData' in p or 'inline_data' in p:
                                    kinds.append('inlineData')
                                elif 'fileData' in p or 'file_data' in p:
                                    kinds.append('fileData')
                                elif 'media' in p:
                                    kinds.append('media')
                                elif 'text' in p:
                                    val = (p.get('text') or '')
                                    kinds.append(f"text:{str(val)[:30]}")
                                else:
                                    kinds.append('other')
                            else:
                                kinds.append(type(p).__name__)
                        if kinds:
                            self._debug(f"candidate[0].parts={kinds}")
                except Exception:
                    pass
            except Exception:
                # 兼容 data:URL 直接返回
                if isinstance(text, str) and text.startswith('data:image/'):
                    try:
                        prefix, b64 = text.split(',', 1)
                        raw = base64.b64decode(b64)
                        from PySide6.QtGui import QImage
                        img = QImage.fromData(raw)
                        if img.isNull():
                            return False, None, '图片数据无效'
                        return True, QPixmap.fromImage(img), 'ok'
                    except Exception:
                        return False, None, '响应无法解析'
                # 记录无法解析的响应长度与前200字符，便于排查
                if progress:
                    QTimer.singleShot(0, lambda: self._report_progress(f"响应非JSON，前200字节：{text[:200] if isinstance(text,str) else '二进制'}"))
                return False, None, '响应不是JSON且非图片'

            # 解析 JSON 中的第一张图片（inlineData/inline_data/fileData/media）
            b64 = None
            try:
                cands = obj.get('candidates') or []
                for c in cands:
                    content = c.get('content') or {}
                    for part in content.get('parts') or []:
                        inline = part.get('inlineData') or {}
                        if 'data' in inline:
                            b64 = inline['data']
                            try:
                                self._debug('found inlineData.base64')
                            except Exception:
                                pass
                            break
                        inline2 = part.get('inline_data') or {}
                        if 'data' in inline2:
                            b64 = inline2['data']
                            try:
                                self._debug('found inline_data.base64')
                            except Exception:
                                pass
                            break
                        # 文件引用：尝试下载 fileUri
                        filed = part.get('fileData') or part.get('file_data') or {}
                        file_uri = filed.get('fileUri') or filed.get('file_uri')
                        if file_uri:
                            try:
                                if progress:
                                    QTimer.singleShot(0, lambda: self._report_progress('下载文件URI…'))
                                with urllib.request.urlopen(file_uri, timeout=60) as fresp:
                                    fr_ct = fresp.headers.get('Content-Type','')
                                    fr_bytes = fresp.read()
                                try:
                                    self._debug(f"fileUri fetched: ct={fr_ct}, bytes={len(fr_bytes)}")
                                except Exception:
                                    pass
                                # 优先直接用下载的二进制
                                if fr_ct.startswith('image/') or (fr_bytes and fr_bytes[:8] in (b'\x89PNG\r\n\x1a\n',)):
                                    raw = fr_bytes
                                    from PySide6.QtGui import QImage
                                    img = QImage.fromData(raw)
                                    if not img.isNull():
                                        return True, QPixmap.fromImage(img), 'ok'
                            except Exception:
                                pass
                        # media 对象：可能携带 base64 数据
                        media = part.get('media') or {}
                        if isinstance(media, dict):
                            mdata = media.get('data') or None
                            if mdata:
                                b64 = mdata
                                try:
                                    self._debug('found media.data base64')
                                except Exception:
                                    pass
                                break
                    if b64:
                        break
            except Exception:
                pass
            if not b64:
                # 如果存在安全拦截或其他反馈，直接输出
                try:
                    pfb = obj.get('promptFeedback') or {}
                    br = pfb.get('blockReason') or pfb.get('block_reason')
                    if br:
                        self._report_progress(f"安全拦截：{br}")
                        self._debug(f"安全拦截：{br}")
                except Exception:
                    pass
                # 兼容多种代理/开放平台的字段：
                # OpenAI风格：choices[].message.content[].image_url.url / b64_json
                try:
                    choices = obj.get('choices') or []
                    for ch in choices:
                        msg = (ch.get('message') or {})
                        content = msg.get('content') or []
                        if isinstance(content, list):
                            for part in content:
                                data = part.get('image_url', {}).get('url') if isinstance(part, dict) else None
                                if data:
                                    # 下载URL
                                    with urllib.request.urlopen(data, timeout=60) as fresp:
                                        raw = fresp.read()
                                    try:
                                        self._debug(f"alt url fetched: bytes={len(raw)}")
                                    except Exception:
                                        pass
                                    from PySide6.QtGui import QImage
                                    img = QImage.fromData(raw)
                                    if not img.isNull():
                                        return True, QPixmap.fromImage(img), 'ok'
                                b64json = part.get('b64_json') if isinstance(part, dict) else None
                                if b64json:
                                    b64 = b64json
                                    try:
                                        self._debug('found b64_json base64')
                                    except Exception:
                                        pass
                                    break
                        if b64:
                            break
                except Exception:
                    pass
            if not b64:
                # 顶层或常见包装字段
                b64 = (
                    obj.get('data') or
                    obj.get('image_base64') or
                    (obj.get('images',[{}])[0].get('base64') if isinstance(obj.get('images'), list) and obj.get('images') else None) or
                    (obj.get('output',[{}])[0].get('data') if isinstance(obj.get('output'), list) and obj.get('output') else None)
                )
            try:
                if not b64:
                    self._debug('no image field found in JSON')
            except Exception:
                pass
            if not b64:
                # 再尝试一次：强化提示只返回图片
                try:
                    self._debug('retry: request with force-image instruction')
                except Exception:
                    pass
                parts2 = [ { 'text': (prompt or '').strip() + '\n只生成图片，不要文本。' } ]
                if sketch_part:
                    parts2.append({ 'text': '请依据这张草图进行主要构图与元素布局：' })
                    parts2.append(sketch_part)
                if style_parts:
                    parts2.append({ 'text': '以下是风格/细节参考图：' })
                    parts2.extend(style_parts)
                payload2 = {
                    'contents': [{ 'role': 'user', 'parts': parts2 }],
                    'generationConfig': gen_cfg,
                    'systemInstruction': { 'role': 'system', 'parts': [ { 'text': '只输出图片，不要文本描述。' } ] }
                }
                data2 = json.dumps(payload2).encode('utf-8')
                try:
                    self._debug(f"POST {endpoint} (retry) bytes={len(data2)}")
                except Exception:
                    pass
                req2 = urllib.request.Request(
                    endpoint,
                    data=data2,
                    headers={ 'Content-Type': 'application/json', 'Accept': 'application/json, image/*' }
                )
                with urllib.request.urlopen(req2, timeout=60) as resp2:
                    ct2 = resp2.headers.get('Content-Type', '')
                    data2 = resp2.read()
                try:
                    self._debug(f"response(retry): ct={ct2}, bytes={len(data2) if isinstance(data2,(bytes,bytearray)) else 'n/a'}")
                except Exception:
                    pass
                if ct2.startswith('image/') or (ct2 == '' and data2 and data2[:8] in (b'\x89PNG\r\n\x1a\n',)):
                    from PySide6.QtGui import QImage
                    img2 = QImage.fromData(data2)
                    if not img2.isNull():
                        return True, QPixmap.fromImage(img2), 'ok'
                # 解析 JSON 二次返回
                try:
                    obj2 = json.loads(data2.decode('utf-8', errors='ignore'))
                except Exception:
                    obj2 = None
                if isinstance(obj2, dict):
                    try:
                        cands = obj2.get('candidates') or []
                        for c in cands:
                            content = c.get('content') or {}
                            for part in content.get('parts') or []:
                                inline = part.get('inlineData') or {}
                                if 'data' in inline:
                                    b64 = inline['data']
                                    self._debug('retry: found inlineData.base64')
                                    break
                            if b64:
                                break
                    except Exception:
                        pass
            if not b64:
                if progress:
                    QTimer.singleShot(0, lambda: self._report_progress(f"未找到图片字段，响应摘要：{json.dumps(obj)[:200]}"))
                return False, None, '未返回图片数据'
            if progress:
                QTimer.singleShot(0, lambda: self._report_progress('解码图片…'))
            try:
                self._debug(f"decode base64 length={len(b64) if isinstance(b64,str) else 'n/a'}")
            except Exception:
                pass
            raw = base64.b64decode(b64)
            from PySide6.QtGui import QImage
            img = QImage.fromData(raw)
            if img.isNull():
                return False, None, '图片数据无效'
            return True, QPixmap.fromImage(img), 'ok'
        except urllib.error.HTTPError as e:
            # 读取并输出错误响应体，便于定位 400/4xx 具体原因
            try:
                body = e.read() if hasattr(e, 'read') else b''
                preview = ''
                if isinstance(body, (bytes, bytearray)):
                    preview = body.decode('utf-8', errors='ignore')[:500]
                if preview:
                    try:
                        self._debug(f"HTTP {e.code} body: {preview}")
                    except Exception:
                        pass
            except Exception:
                pass
            return False, None, f'HTTP {e.code}'
        except Exception as e:
            return False, None, str(e)

    def _update_conn_status(self, text: str, kind: str = 'normal'):
        """将状态文本同步到主窗口左下角的连接区域。"""
        try:
            win = self.window()
            if win and hasattr(win, 'set_connection_text'):
                QTimer.singleShot(0, lambda: win.set_connection_text(text, kind))
        except Exception:
            pass

    def _debug(self, text: str):
        """统一调试输出：打印到控制台、追加到生成日志，并同步到左下角状态。"""
        try:
            msg = f"[DEBUG] {text}"
            print(msg)
        except Exception:
            pass
        try:
            dlg = getattr(self, '_gen_dialog', None)
            if dlg:
                dlg.append_log(f"<span style='color:#9ca3af;'>{text}</span>")
        except Exception:
            pass
        try:
            win = self.window()
            if win and hasattr(win, 'set_connection_text'):
                win.set_connection_text(text, 'normal')
        except Exception:
            pass

    def _mock_generate(self, prompt: str, provider: str):
        # 生成占位图：用提示词和 provider 拼接生成一张文本图，并保存到列表
        from PySide6.QtGui import QPainter, QColor
        pix = QPixmap(256, 256)
        pix.fill(Qt.black)
        p = QPainter(pix)
        p.setPen(QColor(255, 255, 255))
        p.drawText(10, 30, f"{provider}")
        p.drawText(10, 60, f"{prompt[:20]}")
        p.end()
        self._save_and_append_recent(pix)

    def _make_mock_pix(self, prompt: str, provider: str) -> QPixmap:
        from PySide6.QtGui import QPainter, QColor
        pix = QPixmap(256, 256)
        pix.fill(Qt.black)
        p = QPainter(pix)
        p.setPen(QColor(255, 255, 255))
        p.drawText(10, 30, f"{provider}")
        p.drawText(10, 60, f"{prompt[:20]}")
        p.end()
        return pix

    def _add_to_history(self, path: str, pix: QPixmap):
        """添加图片到历史记录"""
        try:
            # 获取主窗口的历史面板
            win = self.window()
            if win and hasattr(win, 'history_panel'):
                # 获取提示词
                prompt = (self.prompt_edit.toPlainText() or '').strip() or 'image generation'
                metadata = {
                    'prompt': prompt,
                    'resolution': f'{pix.width()}x{pix.height()}'
                }
                win.history_panel.add_record(
                    record_type='image',
                    path=path,
                    thumbnail=path,  # 图片本身就是缩略图
                    metadata=metadata
                )
                print('[PHOTO] 已添加到历史记录', flush=True)
        except Exception as e:
            print(f'[PHOTO] 添加历史记录失败: {e}', flush=True)

    def _open_recent(self, item: QListWidgetItem):
        """在程序内打开图片预览对话框，右上角显示图片尺寸"""
        path = item.data(Qt.UserRole)
        if not path:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle('图片预览')
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(0, 0, 0, 0)
        
        # 创建容器widget用于放置图片和尺寸标签
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        pix = QPixmap(path)
        
        # 尺寸标签（绝对定位在右上角）
        size_label = QLabel(container)
        size_label.setStyleSheet("""
            QLabel {
                background: rgba(0, 0, 0, 0.75);
                color: #ffffff;
                padding: 8px 12px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
            }
        """)
        
        if pix.isNull():
            label.setText('无法加载图片')
            size_label.hide()
        else:
            # 初始缩放适配窗口，保持比例
            label.setPixmap(pix.scaled(960, 540, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            
            # 显示图片原始尺寸
            img_w = pix.width()
            img_h = pix.height()
            size_label.setText(f'{img_w} × {img_h}')
            size_label.adjustSize()
            
        container_layout.addWidget(label)
        lay.addWidget(container)
        
        # 将尺寸标签定位到右上角
        def position_size_label():
            if not size_label.isVisible():
                return
            # 定位到容器右上角，留出边距
            margin = 12
            x = container.width() - size_label.width() - margin
            y = margin
            size_label.move(x, y)
            size_label.raise_()  # 确保在最上层
        
        # 监听容器大小改变事件
        container.resizeEvent = lambda event: (
            QWidget.resizeEvent(container, event),
            position_size_label()
        )

        # 右键菜单：保存图片（本地化）
        label.setContextMenuPolicy(Qt.CustomContextMenu)
        def _on_context_menu(pos):
            menu = QMenu(dlg)
            act_save = QAction(self._i18n.get('save_image_ellipsis', '保存图片…'), dlg)
            def _do_save():
                if pix.isNull():
                    return
                dpath, _ = QFileDialog.getSaveFileName(
                    dlg,
                    self._i18n.get('save_image', '保存图片'),
                    os.path.expanduser('~'),
                    self._i18n.get('file_types', 'PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg);;所有文件 (*.*)')
                )
                if dpath:
                    # 根据扩展名选择保存格式；若无扩展名默认PNG
                    ext = os.path.splitext(dpath)[1].lower()
                    if not ext:
                        dpath = dpath + '.png'
                    try:
                        pix.save(dpath)
                        # 简单提示：更新窗口标题
                        dlg.setWindowTitle(f'图片预览（已保存到：{dpath}）')
                    except Exception:
                        pass
            act_save.triggered.connect(_do_save)
            menu.addAction(act_save)
            menu.exec_(label.mapToGlobal(pos))
        label.customContextMenuRequested.connect(_on_context_menu)

        dlg.resize(980, 600)
        
        # 显示对话框后定位尺寸标签
        QTimer.singleShot(50, position_size_label)
        
        dlg.exec_()

    def _recent_context_menu(self, pos):
        item = self.recent_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        act_send = QAction(self._i18n['send_to_canvas'], self)
        menu.addAction(act_send)
        # 发送到 Photoshop（与画板按钮行为一致，复用桥接文件与回传逻辑）
        act_ps = QAction(self._i18n['send_to_photoshop'], self)
        menu.addAction(act_ps)
        # 发送到剪映：将文件URL放入剪贴板，便于在剪映中粘贴导入
        act_capcut = QAction(self._i18n['send_to_capcut'], self)
        menu.addAction(act_capcut)
        # 抠图功能（使用 BiRefNet 模型）
        act_matting = QAction('抠图', self)
        menu.addAction(act_matting)
        # 保存图片
        act_save = QAction(self._i18n.get('save_image', '保存图片'), self)
        menu.addAction(act_save)
        action = menu.exec_(self.recent_list.mapToGlobal(pos))
        if action == act_send:
            path = item.data(Qt.UserRole)
            if not path:
                return
            pix = QPixmap(path)
            if pix.isNull():
                return
            self.layers_panel.add_layer_pixmap(pix, self._i18n['generated_image'], sync_to_canvas=True)
            try:
                it = self.layers_panel.list.item(self.layers_panel.list.count() - 1)
                if it is not None:
                    self.layers_panel.list.setCurrentItem(it)
            except Exception:
                pass
        elif action == act_ps:
            path = item.data(Qt.UserRole)
            if not path:
                return
            self._send_image_to_app('ps', path)
        elif action == act_capcut:
            path = item.data(Qt.UserRole)
            if not path:
                return
            self._send_to_capcut(path)
        elif action == act_matting:
            # 抠图功能
            path = item.data(Qt.UserRole)
            if not path:
                return
            self._do_matting(path)
        elif action == act_save:
            path = item.data(Qt.UserRole)
            if not path:
                return
            self._save_recent_image(path)

    def _ref_context_menu(self, index: int, pos):
        # 右键菜单：提交到画板 / 抠图 / 删除参考图（当槽已有图片时）
        btn = self.ref_buttons[index]
        menu = QMenu(self)
        if self.refs[index]:
            # 提交到画板
            act_submit = QAction(self._i18n['submit_to_canvas'], self)
            act_submit.triggered.connect(lambda: self._submit_reference_to_canvas(index))
            menu.addAction(act_submit)
            
            # 抠图功能
            act_matting = QAction('抠图', self)
            act_matting.triggered.connect(lambda: self._do_reference_matting(index))
            menu.addAction(act_matting)
            
            menu.addSeparator()
        act_del = QAction(self._i18n['delete_reference'], self)
        act_del.triggered.connect(lambda: self._remove_reference(index))
        menu.addAction(act_del)
        menu.popup(btn.mapToGlobal(pos))

    def _remove_reference(self, index: int):
        self.refs[index] = None
        btn = self.ref_buttons[index]
        btn.setText('+')
        btn.setIcon(QIcon())
        btn.setToolTip('')
        # 持久化更新
        try:
            self._persist_references()
        except Exception:
            pass

    def _persist_references(self):
        """将四个参考图路径持久化到 QSettings。"""
        s = QSettings('GhostOS', 'App')
        s.beginGroup('refs')
        try:
            for i in range(4):
                val = self.refs[i] or ''
                s.setValue(f'slot{i}', val)
        finally:
            s.endGroup()

    def add_to_reference_from_layer(self, pix: QPixmap):
        """从图层接收图片并添加到参考图区域的第一个空闲插槽"""
        if pix is None or pix.isNull():
            return
        
        # 查找第一个空闲插槽
        free_index = None
        for i in range(4):
            if self.refs[i] is None:
                free_index = i
                break
        
        # 如果没有空闲插槽，使用第一个插槽并覆盖
        if free_index is None:
            free_index = 0
        
        # 将图片保存到临时目录
        import tempfile
        from datetime import datetime
        temp_dir = Path(tempfile.gettempdir()) / 'GhostOS_References'
        temp_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        temp_path = temp_dir / f'layer_ref_{timestamp}.png'
        
        # 保存图片
        pix.save(str(temp_path), 'PNG')
        
        # 添加到参考图插槽
        path = str(temp_path)
        self.refs[free_index] = path
        btn = self.ref_buttons[free_index]
        thumb = pix.scaled(btn.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        btn.setText('')
        btn.setIcon(QIcon(thumb))
        btn.setIconSize(btn.size())
        btn.setToolTip(path)
        
        # 持久化更新
        try:
            self._persist_references()
        except Exception:
            pass

    def _persist_references(self):
        """将四个参考图路径持久化到 QSettings。"""
        s = QSettings('GhostOS', 'App')
        s.beginGroup('refs')
        try:
            for i in range(4):
                val = self.refs[i] or ''
                s.setValue(f'slot{i}', val)
        finally:
            s.endGroup()

    def _persist_prompt(self):
        """将提示词持久化到 QSettings。"""
        s = QSettings('GhostOS', 'App')
        val = self.prompt_edit.toPlainText()
        s.setValue('creation_prompt', val)

    def _restore_prompt(self):
        """恢复提示词。"""
        s = QSettings('GhostOS', 'App')
        val = s.value('creation_prompt', '')
        if val and isinstance(val, str):
            self.prompt_edit.setPlainText(val)

    def _restore_references(self):
        """恢复参考图路径并刷新缩略图显示。不存在的路径自动忽略。"""
        s = QSettings('GhostOS', 'App')
        s.beginGroup('refs')
        try:
            loaded = []
            for i in range(4):
                val = s.value(f'slot{i}', '')
                val = val if isinstance(val, str) else ''
                if val and os.path.exists(val):
                    self.refs[i] = val
                    btn = self.ref_buttons[i]
                    pix = QPixmap(val).scaled(btn.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    btn.setText('')
                    btn.setIcon(QIcon(pix))
                    btn.setIconSize(btn.size())
                    btn.setToolTip(val)
                else:
                    self.refs[i] = None
                    btn = self.ref_buttons[i]
                    btn.setText('+')
                    btn.setIcon(QIcon())
                    btn.setToolTip('')
                loaded.append(self.refs[i])
        finally:
            s.endGroup()

    def set_language(self, code: str):
        """设置语言并更新创建页所有可见文本。"""
        if code not in ('zh', 'en'):
            code = 'zh'
        self._lang_code = code
        self._i18n = self._get_i18n(code)
        # 顶部输入与按钮
        self.prompt_edit.setPlaceholderText(self._i18n['prompt_placeholder'])
        self.btn_confirm.setText(self._i18n['confirm'])
        # 中部工具设置
        self.lbl_brush_size.setText(self._i18n['brush_size'])
        self.lbl_color.setText(self._i18n['color'])
        self.btn_more_colors.setText(self._i18n['more_colors'])
        self.lbl_ratio.setText(self._i18n['canvas_ratio'])
        self.btn_apply_ratio.setText(self._i18n['apply'])
        # 快捷区提示语
        self.btn_ps.setToolTip(self._i18n['send_to_photoshop'])
        self.btn_an.setToolTip(self._i18n['send_to_animate'])
        self.btn_ae.setToolTip(self._i18n['send_to_after_effects'])
        self.btn_kr.setToolTip(self._i18n['send_to_krita'])
        self.btn_cta.setToolTip(self._i18n['send_to_cartoon_animator'])
        # 画布与工具栏、图层面板联动
        try:
            self.canvas.set_language(code)
            self.toolbar.set_language(code)
            self.layers_panel.set_language(code)
        except Exception:
            pass

    def _get_i18n(self, code: str) -> dict:
        zh = {
            'prompt_placeholder': '请输入您的提示词，使用英文。',
            'confirm': '确定',
            'brush_size': '画笔大小',
            'color': '颜色',
            'more_colors': '更多颜色',
            'canvas_ratio': '画板比例',
            'apply': '应用',
            'send_to_photoshop': '发送到 Photoshop',
            'send_to_animate': '发送到 Animate',
            'send_to_after_effects': '发送到 After Effects',
            'send_to_blender': '发送到 Blender',
            'send_to_krita': '发送到 Krita',
            'send_to_cartoon_animator': '发送到 Cartoon Animator 5',
            'send_to_canvas': '发送到画板',
            'send_to_capcut': '发送到剪映',
            'send_to_photoshop': '发送到 Photoshop',
            'generated_image': '生成图',
            'submit_to_canvas': '提交到画板',
            'delete_reference': '删除参考图',
            'save_image': '保存图片',
            'save_image_ellipsis': '保存图片…',
            'file_types': 'PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg);;所有文件 (*.*)'
        }
        en = {
            'prompt_placeholder': 'Describe the image you want in detail...\n\nExample:\nAn orange kitten under cherry blossoms, spring sunlight through petals, Japanese garden background, high-quality photography, soft light, warm atmosphere',
            'confirm': 'Confirm',
            'brush_size': 'Brush Size',
            'color': 'Color',
            'more_colors': 'More colors',
            'canvas_ratio': 'Canvas Ratio',
            'apply': 'Apply',
            'send_to_photoshop': 'Send to Photoshop',
            'send_to_animate': 'Send to Animate',
            'send_to_after_effects': 'Send to After Effects',
            'send_to_blender': 'Send to Blender',
            'send_to_krita': 'Send to Krita',
            'send_to_cartoon_animator': 'Send to Cartoon Animator 5',
            'send_to_canvas': 'Send to Canvas',
            'send_to_capcut': 'Send to CapCut',
            'send_to_photoshop': 'Send to Photoshop',
            'generated_image': 'Generated Image',
            'submit_to_canvas': 'Submit to Canvas',
            'delete_reference': 'Delete Reference',
            'save_image': 'Save Image',
            'save_image_ellipsis': 'Save Image…',
            'file_types': 'PNG Images (*.png);;JPEG Images (*.jpg *.jpeg);;All Files (*.*)'
        }
        return zh if code == 'zh' else en

    def _pick_color(self):
        color = QColorDialog.getColor(parent=self, title='选择颜色')
        if color.isValid():
            self.canvas.brush_color = color

    def _submit_reference_to_canvas(self, index: int):
        path = self.refs[index]
        if not path:
            return
        pix = QPixmap(path)
        if pix.isNull():
            return
        self.layers_panel.add_layer_pixmap(pix, f'参考图{index+1}', sync_to_canvas=True)
        try:
            it = self.layers_panel.list.item(self.layers_panel.list.count() - 1)
            if it is not None:
                self.layers_panel.list.setCurrentItem(it)
        except Exception:
            pass
        # 同步保存到 Temp 文件夹
        try:
            from pathlib import Path
            from datetime import datetime
            temp_dir = Path(__file__).resolve().parent / 'Temp'
            temp_dir.mkdir(exist_ok=True)
            filename = datetime.now().strftime('%Y%m%d-%H%M%S') + f'-ref{index+1}.png'
            save_path = temp_dir / filename
            pix.save(str(save_path), 'PNG')
        except Exception:
            pass

    def _send_to_capcut(self, path: str):
        """尝试将图片发送到剪映：复制文件到剪贴板，并将剪映窗口置前发送 Ctrl+V。
        说明：剪映未公开导入接口，若其素材区支持粘贴，则可导入；否则需手动拖拽。
        """
        try:
            md = QMimeData()
            url = QUrl.fromLocalFile(path)
            md.setUrls([url])
            md.setText(path)
            QGuiApplication.clipboard().setMimeData(md)
        except Exception:
            return

        # 枚举窗口，寻找标题包含"剪映"或"CapCut"的窗口
        user32 = ctypes.windll.user32
        titles: list[str] = []

        EnumWindows = user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)

        def get_title(hwnd):
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            return buf.value

        target_hwnd = None
        def callback(hwnd, lparam):
            nonlocal target_hwnd
            title = get_title(hwnd)
            if title:
                titles.append(title)
                if ('剪映' in title) or ('CapCut' in title):
                    target_hwnd = hwnd
                    return False  # stop
            return True

        EnumWindows(EnumWindowsProc(callback), 0)

        if target_hwnd:
            # 置前并尝试打开导入对话框后粘贴路径回车
            try:
                user32.ShowWindow(target_hwnd, 5)  # SW_SHOW
                user32.SetForegroundWindow(target_hwnd)
                time.sleep(0.35)
                KEYEVENTF_KEYUP = 0x0002
                VK_CONTROL = 0x11
                VK_V = 0x56
                VK_I = 0x49
                VK_O = 0x4F
                VK_RETURN = 0x0D

                # 首选 Ctrl+I（很多版本的剪映为"导入媒体"快捷键）
                user32.keybd_event(VK_CONTROL, 0, 0, 0)
                user32.keybd_event(VK_I, 0, 0, 0)
                time.sleep(0.05)
                user32.keybd_event(VK_I, 0, KEYEVENTF_KEYUP, 0)
                user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
                time.sleep(0.4)

                # 粘贴路径
                user32.keybd_event(VK_CONTROL, 0, 0, 0)
                user32.keybd_event(VK_V, 0, 0, 0)
                time.sleep(0.05)
                user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
                user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

                # 回车确认
                time.sleep(0.15)
                user32.keybd_event(VK_RETURN, 0, 0, 0)
                time.sleep(0.05)
                user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)

                # 兜底：若未出现导入框，尝试 Ctrl+O
                time.sleep(0.4)
                user32.keybd_event(VK_CONTROL, 0, 0, 0)
                user32.keybd_event(VK_O, 0, 0, 0)
                time.sleep(0.05)
                user32.keybd_event(VK_O, 0, KEYEVENTF_KEYUP, 0)
                user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
                time.sleep(0.35)
                user32.keybd_event(VK_CONTROL, 0, 0, 0)
                user32.keybd_event(VK_V, 0, 0, 0)
                time.sleep(0.05)
                user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
                user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
                time.sleep(0.15)
                user32.keybd_event(VK_RETURN, 0, 0, 0)
                time.sleep(0.05)
                user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
            except Exception:
                pass
        else:
            # 若未找到窗口，只复制到剪贴板，提示用户打开剪映并粘贴
            try:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(self, '未检测到剪映窗口', '已复制图片文件到剪贴板，请打开剪映并在素材区粘贴导入。')
            except Exception:
                pass

    def _save_recent_image(self, source_path: str):
        """保存生成后的图片到用户指定位置"""
        try:
            # 获取原文件扩展名
            _, ext = os.path.splitext(source_path)
            if not ext:
                ext = '.png'
            
            # 打开文件保存对话框
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                '保存图片',
                os.path.join(os.path.expanduser('~'), f'image{ext}'),
                f'Image Files (*{ext} *.png *.jpg *.jpeg);;All Files (*.*)'
            )
            
            if save_path:
                # 读取源图片并保存到目标位置
                pix = QPixmap(source_path)
                if not pix.isNull():
                    pix.save(save_path)
        except Exception:
            pass

    def _do_matting(self, image_path: str):
        """
        对指定图片进行抠图（使用 BiRefNet 模型）
        
        Args:
            image_path: 图片文件路径
        """
        try:
            self._debug(f'[抠图] 开始处理: {image_path}')
            
            # 加载图片
            input_pixmap = QPixmap(image_path)
            if input_pixmap.isNull():
                self._debug('[抠图] 图片加载失败')
                return
            
            self._debug(f'[抠图] 图片尺寸: {input_pixmap.width()}x{input_pixmap.height()}')
            
            # 导入 BiRefNet 模块
            try:
                from BiRefNet import process_matting
            except ImportError as e:
                self._debug(f'[抠图] 无法导入 BiRefNet 模块: {e}')
                return
            
            # 处理抠图
            result_pixmap = process_matting(input_pixmap, parent=self)
            
            if result_pixmap is None:
                self._debug('[抠图] 抠图被取消或失败')
                return
            
            self._debug('[抠图] 抠图成功，准备保存...')
            
            # 保存抠图结果到 JPG/matting 目录
            matting_dir = Path(__file__).resolve().parent / 'JPG' / 'matting'
            matting_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成文件名
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            save_path = matting_dir / f'{timestamp}-matting.png'
            
            # 保存为 PNG 格式以保留透明度
            result_pixmap.save(str(save_path), 'PNG')
            
            self._debug(f'[抠图] 已保存到: {save_path}')
            
            # 添加到最近生成区域
            size = self.recent_list.iconSize()
            thumb = result_pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            # 如果已达到容量上限，清空重新开始
            if self.recent_list.count() >= self.recent_capacity:
                self.recent_list.clear()
                self._recent_cycle_index = 0
                self._debug('[抠图] 最近列表已满，清空重新开始')
            
            # 添加新图片
            item = QListWidgetItem(QIcon(thumb), '')
            item.setData(Qt.UserRole, str(save_path))
            item.setToolTip(f'{save_path}\n(抠图结果)')
            self.recent_list.addItem(item)
            
            self._debug('[抠图] 已添加到最近生成区域')
            
            # 弹出提示
            try:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(
                    self,
                    '抠图完成',
                    f'抠图成功！\n已保存到：{save_path}'
                )
            except Exception:
                pass
            
        except Exception as e:
            self._debug(f'[抠图] 异常: {e}')
            import traceback
            self._debug(traceback.format_exc())

    def _do_reference_matting(self, index: int):
        """
        对参考图进行抠图（使用 BiRefNet 模型），并替换参考图
        
        Args:
            index: 参考图槽位索引 (0-3)
        """
        try:
            # 获取参考图路径
            ref_path = self.refs[index]
            if not ref_path:
                self._debug('[抠图-参考图] 参考图槽位为空')
                return
            
            self._debug(f'[抠图-参考图] 开始处理参考图{index+1}: {ref_path}')
            
            # 加载图片
            input_pixmap = QPixmap(ref_path)
            if input_pixmap.isNull():
                self._debug('[抠图-参考图] 图片加载失败')
                return
            
            self._debug(f'[抠图-参考图] 图片尺寸: {input_pixmap.width()}x{input_pixmap.height()}')
            
            # 导入 BiRefNet 模块
            try:
                from BiRefNet import process_matting
            except ImportError as e:
                self._debug(f'[抠图-参考图] 无法导入 BiRefNet 模块: {e}')
                return
            
            # 处理抠图
            result_pixmap = process_matting(input_pixmap, parent=self)
            
            if result_pixmap is None:
                self._debug('[抠图-参考图] 抠图被取消或失败')
                return
            
            self._debug('[抠图-参考图] 抠图成功，准备替换参考图...')
            
            # 保存抠图结果到 JPG/matting 目录
            matting_dir = Path(__file__).resolve().parent / 'JPG' / 'matting'
            matting_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成文件名
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            save_path = matting_dir / f'{timestamp}-matting-ref{index+1}.png'
            
            # 保存为 PNG 格式以保留透明度
            result_pixmap.save(str(save_path), 'PNG')
            
            self._debug(f'[抠图-参考图] 已保存到: {save_path}')
            
            # 替换参考图
            self.refs[index] = str(save_path)
            
            # 更新参考图按钮显示
            btn = self.ref_buttons[index]
            size = btn.iconSize()
            thumb = result_pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            btn.setIcon(QIcon(thumb))
            btn.setText('')
            
            self._debug(f'[抠图-参考图] 已替换参考图{index+1}')
            
            # 弹出提示
            try:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(
                    self,
                    '抠图完成',
                    f'抠图成功！已替换参考图{index+1}'
                )
            except Exception:
                pass
            
        except Exception as e:
            self._debug(f'[抠图-参考图] 异常: {e}')
            import traceback
            self._debug(traceback.format_exc())

    def _apply_canvas_size(self):
        # 读取下拉比例，如 16:9
        text = self.combo_ratio.currentText()
        try:
            w_str, h_str = text.split(':')
            rw, rh = int(w_str), int(h_str)
        except Exception:
            rw, rh = 16, 9
        ratio = rw / rh

        # 计算在 CanvasWrap 中可用空间，确保不占用顶部/底部/左侧区域
        margin_left, margin_top, margin_right, margin_bottom = 16, 12, 16, 12
        available_w = max(200, self.canvas_wrap.width() - (margin_left + margin_right))
        tool_h = 0
        if self.canvas_wrap.layout() and self.canvas_wrap.layout().count() > 0:
            tool_h = self.canvas_wrap.layout().itemAt(0).widget().height() or self.canvas_wrap.layout().itemAt(0).widget().sizeHint().height()
        available_h = max(200, self.canvas_wrap.height() - (margin_top + margin_bottom) - tool_h)

        # 在可用空间内按比例尽量放大
        fit_w = available_w
        fit_h = fit_w / ratio
        if fit_h > available_h:
            fit_h = available_h
            fit_w = fit_h * ratio

        self.canvas.resize_canvas(int(fit_w), int(fit_h))

    def set_bottom_area_percent(self, percent: float):
        """设置底部生成区域占 center 高度的百分比，范围 0.1~0.8。"""
        try:
            p = float(percent)
        except Exception:
            return
        # 约束在合理范围，避免过小或遮挡画板
        p = max(0.1, min(p, 0.8))
        self.bottom_percent = p
        self._apply_bottom_area_size()

    def _apply_bottom_area_size(self):
        """按照 bottom_percent 计算并应用底部区域高度，单行显示缩略图以贴合红框。"""
        if not hasattr(self, 'center') or not hasattr(self, 'bottom_bar'):
            return
        ch = self.center.height()
        if ch <= 0:
            return
        bottom_h = max(110, int(ch * self.bottom_percent))
        self.bottom_bar.setFixedHeight(bottom_h)
        # 同步缩略图列表高度和图标尺寸：单行显示
        # 与布局边距保持一致（top/bottom 各 14）
        list_h = max(72, bottom_h - (14 + 14))
        self.recent_list.setFixedHeight(list_h)
        spacing = self.recent_list.spacing() or 8
        rows = 1
        grid_h = max(64, int(list_h / rows))
        icon_size = max(48, grid_h - spacing)
        self.recent_list.setIconSize(QSize(icon_size, icon_size))
        self.recent_list.setGridSize(QSize(icon_size + spacing * 2, grid_h))

    def apply_default_ratio(self):
        """进入创建页时，每次都将初始画板设置为 16:9。"""
        idx = self.combo_ratio.findText('16:9')
        if idx >= 0:
            self.combo_ratio.setCurrentIndex(idx)
        self._apply_canvas_size()

    def eventFilter(self, obj, event):
        if obj is self.canvas_wrap and event.type() == QEvent.Resize:
            # 第一次拿到有效尺寸时，按照当前比例填充到可用区域
            if not self._initial_canvas_applied and self.canvas_wrap.width() > 0 and self.canvas_wrap.height() > 0:
                self._initial_canvas_applied = True
                self._apply_canvas_size()
        # center 尺寸变化时，按百分比精确调整底部区域高度
        if obj is getattr(self, 'center', None) and event.type() == QEvent.Resize:
            self._apply_bottom_area_size()
        return super().eventFilter(obj, event)

    # —— 快捷区：跨应用桥接 ——
    
    def _send_canvas_to_app(self, app: str):
        """保存画板到临时桥接文件，打开对应外部应用，并监听保存回传。
        注意：PS 和 Krita 已迁移到独立模块，此方法仅处理 AE/AN/CTA 等其他应用。
        """
        try:
            base = Path(__file__).resolve().parent / 'Temp'
            base.mkdir(exist_ok=True)
            bridge_path = base / f'bridge_{app}.png'
            
            # 其他应用导出整画板
            self.canvas.render_to_pixmap().save(str(bridge_path), 'PNG')
            
            # 监听该文件变化
            if not hasattr(self, '_bridge_watcher'):
                self._bridge_watcher = QFileSystemWatcher(self)
                self._bridge_watcher.fileChanged.connect(self._on_bridge_file_changed)
                self._bridge_map = {}
            
            self._bridge_map[str(bridge_path)] = {'app': app, 'origin': 'canvas', 'lid': None}
            self._bridge_watcher.addPath(str(bridge_path))
            
            # 打开外部程序并传入桥接图片路径
            exe = self._get_app_exe(app)
            if exe:
                import subprocess
                subprocess.Popen([exe, str(bridge_path)], shell=False)
            else:
                print(f'[Bridge] 未找到 {app.upper()} 程序，请在设置中配置。', flush=True)
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, self._i18n.get('tip', '提示'), f'{app.upper()} 程序路径未设置\n请先在设置中配置')
        except Exception as e:
            print(f'[Bridge] 桥接失败: {e}', flush=True)
            import traceback
            traceback.print_exc()
    
    def _send_to_photoshop(self):
        """发送到 Photoshop 编辑"""
        if not hasattr(self, '_ps_integration') or self._ps_integration is None:
            print('[Photoshop] Photoshop 集成未初始化', flush=True)
            try:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, '提示', 'Photoshop 集成初始化失败\n请重启应用')
            except Exception:
                pass
            return
        
        # 调用 Photoshop 集成发送图层
        self._ps_integration.send_to_photoshop()
    
    def _send_to_krita(self):
        """发送到 Krita 编辑"""
        if not hasattr(self, '_krita_integration') or self._krita_integration is None:
            print('[Krita] Krita 集成未初始化', flush=True)
            try:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, '提示', 'Krita 集成初始化失败\n请重启应用')
            except Exception:
                pass
            return
        
        # 调用 Krita 集成发送图层
        self._krita_integration.send_to_krita()
    
    def _start_blender_capture(self):
        """启动 Blender 实时捕获"""
        if not hasattr(self, '_blender_integration') or self._blender_integration is None:
            print('[FastBlender] Blender 集成未初始化', flush=True)
            try:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, '提示', 'Blender 集成初始化失败\n请重启应用')
            except Exception:
                pass
            return
        
        # 获取 Blender 程序路径
        exe = self._get_app_exe('bl')
        
        # 启动 Blender 实时捕获
        success = self._blender_integration.start_blender(exe)
        
        if not success:
            try:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, '提示', '启动 Blender 失败\n请确保已正确配置 Blender 路径')
            except Exception:
                pass
    
    def _get_app_exe(self, app: str) -> str | None:
        """获取应用程序路径（从设置或手动选择）
        注意：PS 和 Krita 已迁移到独立模块，此方法仅处理 AE/AN/CTA/BL 等其他应用。
        """
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QFileDialog
        settings = QSettings('YourCompany', 'GhostOS')
        key = f'app_{app}'
        path = settings.value(key, '')
        if path and Path(path).exists():
            return path
        # 未配置或路径无效，提示用户手动选择
        title = {'ae': '选择 After Effects 程序', 'an': '选择 Animate 程序', 'cta': '选择 Cartoon Animator 5 程序', 'bl': '选择 Blender 程序'}.get(app, '选择程序')
        path, _ = QFileDialog.getOpenFileName(self, title, '', 'Executable (*.exe)')
        if path:
            settings.setValue(key, path)
            return path
        return None

    def _on_bridge_file_changed(self, changed_path: str):
        """外部应用保存后，回传到画板并更新图层。"""
        try:
            bridge_info = getattr(self, '_bridge_map', {}).get(changed_path, {})
            if not bridge_info:
                return
            
            app = bridge_info.get('app', '')
            origin = bridge_info.get('origin', 'canvas')
            lid = bridge_info.get('lid', None)
            
            print(f'[Bridge] 文件变化: {changed_path}', flush=True)
            print(f'[Bridge] 应用: {app}, 来源: {origin}, 图层ID: {lid}', flush=True)
            
            # 重新加入监听（部分应用保存会替换文件导致监听失效）
            QTimer.singleShot(300, lambda: self._bridge_watcher.addPath(changed_path))
            # 延迟尝试读取，避免文件仍在写入锁定
            self._schedule_load_bridge(changed_path, app, origin=origin, lid=lid, attempts=5, delay_ms=250)
        except Exception as e:
            print(f'[Bridge] 文件变化处理失败: {e}', flush=True)
            import traceback
            traceback.print_exc()

    def _on_bridge_dir_changed(self, dir_path: str):
        """目录变化时检查各桥接文件是否被更新。"""
        try:
            for path, bridge_info in getattr(self, '_bridge_map', {}).items():
                try:
                    if not isinstance(bridge_info, dict):
                        continue
                    
                    mtime = os.path.getmtime(path)
                    last = getattr(self, '_bridge_last_mtime', {}).get(path, 0)
                    if mtime > last:
                        if not hasattr(self, '_bridge_last_mtime'):
                            self._bridge_last_mtime = {}
                        self._bridge_last_mtime[path] = mtime
                        
                        app = bridge_info.get('app', '')
                        origin = bridge_info.get('origin', 'canvas')
                        lid = bridge_info.get('lid', None)
                        
                        self._schedule_load_bridge(path, app, origin=origin, lid=lid, attempts=5, delay_ms=250)
                except Exception:
                    continue
        except Exception:
            pass

    def _schedule_load_bridge(self, path: str, app: str, origin: str = 'canvas', lid: int = None, attempts: int = 3, delay_ms: int = 250):
        """多次延迟尝试加载桥接文件，提高对外部写入的兼容性。"""
        def try_once():
            nonlocal attempts  # 必须在使用前声明
            try:
                pix = QPixmap(path)
                if not pix.isNull():
                    print(f'[Bridge] 成功加载桥接文件: {path} ({pix.width()}x{pix.height()})', flush=True)
                    
                    # 若来源为选中图层：回写到原图层并更新图层面板缩略图
                    if origin == 'active_layer' and lid is not None:
                        print(f'[Bridge] 更新图层 ID={lid}', flush=True)
                        ok = False
                        try:
                            ok = getattr(self.canvas, 'update_layer_pixmap_by_id', lambda _lid, _pix: False)(lid, pix)
                        except Exception as e:
                            print(f'[Bridge] 更新画布图层失败: {e}', flush=True)
                            ok = False
                        
                        # 更新LayersPanel中的缩略图
                        try:
                            if hasattr(self, 'layers_panel') and hasattr(self.layers_panel, 'list'):
                                size = self.layers_panel.list.iconSize()
                                thumb = pix.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation) if size.isValid() else pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                                cnt = self.layers_panel.list.count()
                                for i in range(cnt):
                                    it = self.layers_panel.list.item(i)
                                    if it and it.data(Qt.UserRole) == lid:
                                        it.setIcon(QIcon(thumb))
                                        print(f'[Bridge] ✓ 已更新图层面板缩略图 (索引={i})', flush=True)
                                        break
                                self.layers_panel.list.viewport().update()
                                self.layers_panel.list.update()
                        except Exception as e:
                            print(f'[Bridge] 更新图层面板缩略图失败: {e}', flush=True)
                        
                        if ok:
                            print(f'[Bridge] ✓ 图层更新成功', flush=True)
                            return
                        else:
                            print(f'[Bridge] ⚠️  图层更新失败，将添加为新图层', flush=True)
                    
                    # 默认行为：添加为新图层
                    label = {'ae': '来自AE', 'an': '来自AN', 'cta': '来自CTA', 'bl': '来自Blender'}.get(app, '外部回传')
                    print(f'[Bridge] 添加新图层: {label}', flush=True)
                    self.layers_panel.add_layer_pixmap(pix, label)
                    print(f'[Bridge] ✓ 新图层添加成功', flush=True)
                    return
                else:
                    print(f'[Bridge] ⚠️  加载的图片为空', flush=True)
            except Exception as e:
                print(f'[Bridge] 加载桥接文件失败 (尝试 {4-attempts}/3): {e}', flush=True)
            
            # 失败则递减重试
            attempts -= 1
            if attempts > 0:
                QTimer.singleShot(delay_ms, try_once)
            else:
                print(f'[Bridge] ❌ 加载失败，已达最大重试次数', flush=True)
        
        QTimer.singleShot(delay_ms, try_once)

    # 图层右键菜单等逻辑已迁移到 LayersPanel
class RecentListWidget(QListWidget):
    """支持拖拽导出文件到外部（如剪映）"""
    def __init__(self, parent=None):
        super().__init__(parent)
        # 仅作为拖拽源，避免内部移动/重排影响
        from PySide6.QtWidgets import QAbstractItemView
        self.setDragEnabled(True)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def mimeData(self, items):
        md = QMimeData()
        urls = []
        for it in items:
            path = it.data(Qt.UserRole)
            if path:
                urls.append(QUrl.fromLocalFile(path))
        # 同时提供文本路径，增强外部程序兼容性
        if urls:
            md.setUrls(urls)
            md.setText("\n".join([u.toLocalFile() for u in urls]))
        return md

    def startDrag(self, supportedActions):
        # 使用文件URL启动外部拖拽，优先复制动作
        sel = self.selectedItems()
        if not sel:
            return
        md = self.mimeData(sel)
        if not md or (not md.hasUrls() and not md.hasText()):
            return
        from PySide6.QtGui import QDrag
        drag = QDrag(self)
        drag.setMimeData(md)
        # 提供缩略图作为拖拽预览
        try:
            it = sel[0]
            icon = it.icon()
            if not icon.isNull():
                pm = icon.pixmap(self.iconSize())
                drag.setPixmap(pm)
        except Exception:
            pass
        drag.exec(Qt.CopyAction)
