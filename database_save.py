import os
import json
import shutil

from PySide6.QtCore import Qt, QSize, QPoint, QPointF, Signal
from PySide6.QtGui import QPixmap, QCursor, QDrag, QMouseEvent, QPainter, QColor, QBrush, QPen, QFont, QIcon, QGuiApplication, QTransform, QLinearGradient, QPalette, QPainterPath, QImage, QRegion, QPolygonF, QCursor
from PySide6.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QScrollArea,
    QGridLayout,
    QSizePolicy,
    QApplication,
)
from PySide6.QtCore import QMimeData, QUrl


class AssetLibraryStore:
    def __init__(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(base_dir, "data")
        self.categories = {
            "people": {
                "dir": os.path.join(self.data_dir, "people"),
                "json": os.path.join(self.data_dir, "people.json"),
            },
            "items": {
                "dir": os.path.join(self.data_dir, "items"),
                "json": os.path.join(self.data_dir, "items.json"),
            },
            "scene": {
                "dir": os.path.join(self.data_dir, "scene"),
                "json": os.path.join(self.data_dir, "scene.json"),
            },
        }
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir, exist_ok=True)
        for info in self.categories.values():
            if not os.path.exists(info["dir"]):
                os.makedirs(info["dir"], exist_ok=True)
            if not os.path.exists(info["json"]):
                with open(info["json"], "w", encoding="utf-8") as f:
                    json.dump([], f, ensure_ascii=False, indent=2)

    def _load(self, key):
        info = self.categories[key]
        try:
            with open(info["json"], "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
        return []

    def _save(self, key, items):
        info = self.categories[key]
        try:
            with open(info["json"], "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def list_assets(self, key):
        data = self._load(key)
        result = []
        for entry in data:
            path = entry.get("path") if isinstance(entry, dict) else entry
            if not path:
                continue
            if not os.path.isabs(path):
                path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
            if os.path.exists(path):
                item = {"path": path}
                if isinstance(entry, dict):
                    name = entry.get("name")
                    prompt = entry.get("prompt")
                    if name:
                        item["name"] = name
                    if prompt:
                        item["prompt"] = prompt
                result.append(item)
        return result

    def add_people_record(self, name, prompt, image_path):
        key = "people"
        if not image_path or not os.path.exists(image_path):
            return
        info = self.categories.get(key)
        if not info:
            return
        items = self._load(key)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path = image_path
        try:
            abs_image = os.path.abspath(image_path)
            abs_base = os.path.abspath(base_dir)
            if os.path.commonprefix([abs_image, abs_base]) == abs_base:
                path = os.path.relpath(abs_image, abs_base)
            else:
                path = abs_image
        except Exception:
            path = image_path

        updated = False
        for entry in items:
            if isinstance(entry, dict) and entry.get("path") == path:
                entry["name"] = name or entry.get("name", "")
                entry["prompt"] = prompt or entry.get("prompt", "")
                updated = True
                break
        if not updated:
            items.append(
                {
                    "path": path,
                    "name": name or "",
                    "prompt": prompt or "",
                }
            )
        self._save(key, items)

    def add_scene_record(self, name, prompt, image_path):
        key = "scene"
        if not image_path or not os.path.exists(image_path):
            return
        info = self.categories.get(key)
        if not info:
            return
        items = self._load(key)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path = image_path
        try:
            abs_image = os.path.abspath(image_path)
            abs_base = os.path.abspath(base_dir)
            if os.path.commonprefix([abs_image, abs_base]) == abs_base:
                path = os.path.relpath(abs_image, abs_base)
            else:
                path = abs_image
        except Exception:
            path = image_path

        updated = False
        for entry in items:
            if isinstance(entry, dict) and entry.get("path") == path:
                entry["name"] = name or entry.get("name", "")
                entry["prompt"] = prompt or entry.get("prompt", "")
                updated = True
                break
        if not updated:
            items.append(
                {
                    "path": path,
                    "name": name or "",
                    "prompt": prompt or "",
                }
            )
        self._save(key, items)

    def add_assets(self, key, file_paths):
        if not file_paths:
            return
        info = self.categories[key]
        items = self._load(key)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        for src in file_paths:
            if not src:
                continue
            if not os.path.exists(src):
                continue
            ext = os.path.splitext(src)[1].lower()
            if ext not in [".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"]:
                continue
            name = os.path.basename(src)
            dest_dir = info["dir"]
            dest = os.path.join(dest_dir, name)
            base_name, ext = os.path.splitext(name)
            idx = 1
            while os.path.exists(dest):
                dest = os.path.join(dest_dir, f"{base_name}_{idx}{ext}")
                idx += 1
            try:
                shutil.copy2(src, dest)
            except Exception:
                continue
            rel = os.path.relpath(dest, base_dir)
            items.append({"path": rel})
        self._save(key, items)

    def remove_asset(self, key, path):
        info = self.categories[key]
        items = self._load(key)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        new_items = []
        for entry in items:
            p = entry.get("path") if isinstance(entry, dict) else entry
            if p == path:
                continue
            new_items.append(entry)
        self._save(key, new_items)
        abs_path = path
        if not os.path.isabs(abs_path):
            abs_path = os.path.join(base_dir, abs_path)
        if abs_path.startswith(info["dir"]) and os.path.exists(abs_path):
            try:
                os.remove(abs_path)
            except Exception:
                pass


class AssetThumbnail(QFrame):
    def __init__(self, category, asset, store: AssetLibraryStore, parent=None):
        super().__init__(parent)
        self.category = category
        if isinstance(asset, dict):
            self.image_path = asset.get("path")
            self.asset_name = asset.get("name", "")
            self.asset_prompt = asset.get("prompt", "")
        else:
            self.image_path = asset
            self.asset_name = ""
            self.asset_prompt = ""
        self.store = store
        self.drag_start_pos = None
        self.is_selected = False
        self.setFixedSize(96, 96)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.update_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setFixedSize(80, 72)
        self.image_label.setStyleSheet(
            """
            QLabel {
                background-color: transparent;
                border: none;
            }
            """
        )
        pixmap = QPixmap(self.image_path) if self.image_path else QPixmap()
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        self.image_label.setPixmap(pixmap)
        layout.addWidget(self.image_label, 0, Qt.AlignCenter)

        self.name_label = QLabel()
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setFixedHeight(16)
        self.name_label.setStyleSheet(
            """
            QLabel {
                color: #ffffff;
                font-size: 11px;
                background-color: rgba(0, 0, 0, 120);
                border-radius: 8px;
                border: none;
            }
            """
        )
        if self.asset_name:
            self.name_label.setText(self.asset_name)
        layout.addWidget(self.name_label, 0, Qt.AlignCenter)

        if self.asset_name or self.asset_prompt:
            tip_parts = []
            if self.asset_name:
                tip_parts.append(f"人物: {self.asset_name}")
            if self.asset_prompt:
                tip_parts.append(f"提示词: {self.asset_prompt}")
            self.setToolTip("\n".join(tip_parts))

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(4)
        btn_layout.addStretch(1)
        self.delete_btn = QPushButton("✕")
        self.delete_btn.setFixedSize(18, 18)
        self.delete_btn.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(244,67,54,180);
                color: #ffffff;
                border: none;
                border-radius: 9px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(229,57,53,220);
            }
            """
        )
        self.delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(self.delete_btn, 0, Qt.AlignRight | Qt.AlignBottom)
        layout.addLayout(btn_layout)

    def _on_delete(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        rel = self.image_path
        if os.path.isabs(rel):
            try:
                rel = os.path.relpath(self.image_path, base_dir)
            except Exception:
                pass
        self.store.remove_asset(self.category, rel)
        parent_layout = self.parentWidget().layout() if self.parentWidget() else None
        if parent_layout:
            parent_layout.removeWidget(self)
        self.deleteLater()

    def update_style(self):
        """更新组件样式"""
        if self.is_selected:
            # 选中状态 - 仅保留外围绿色边框
            self.setStyleSheet(
                """
                QFrame {
                    background-color: rgba(255,255,255,10);
                    border-radius: 10px;
                    border: 2px solid #00E676;
                }
                """
            )
        else:
            # 默认状态
            self.setStyleSheet(
                """
                QFrame {
                    background-color: rgba(255,255,255,10);
                    border-radius: 10px;
                    border: 1px solid rgba(255,255,255,40);
                }
                """
            )

    def set_selected(self, selected: bool):
        """设置选中状态"""
        self.is_selected = selected
        self.update_style()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if not (event.buttons() & Qt.LeftButton):
            return
        if not self.drag_start_pos:
            return
        if (event.pos() - self.drag_start_pos).manhattanLength() < 6:
            return
        if not self.image_path or not os.path.exists(self.image_path):
            return
        drag = QDrag(self)
        mime_data = QMimeData()
        url = QUrl.fromLocalFile(self.image_path)
        mime_data.setUrls([url])
        mime_data.setData("application/x-ghost-library-image", b"1")
        drag.setMimeData(mime_data)
        pixmap = self.image_label.pixmap()
        if pixmap and not pixmap.isNull():
            drag.setPixmap(pixmap)
            drag.setHotSpot(pixmap.rect().center())
        drag.exec_(Qt.CopyAction)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            # 1. 切换选中状态
            if self.is_selected:
                # 如果已经是选中状态，再次点击取消选中
                self.set_selected(False)
            else:
                # 如果未选中，则选中自己，并取消其他同名图片的选中状态
                self.set_selected(True)
                
                # 遍历父容器中的其他 AssetThumbnail 组件
                if self.parentWidget():
                    siblings = self.parentWidget().findChildren(AssetThumbnail)
                    for sibling in siblings:
                        if sibling is not self and sibling.asset_name == self.asset_name:
                             sibling.set_selected(False)
            
                # 2. 只有在选中时才执行自动同步逻辑
                if self.asset_name:
                    # 确定目标节点关键词
                    target_keyword = ""
                    if self.category == "scene":
                        target_keyword = "地点"
                    elif self.category == "people":
                        target_keyword = "人物"
                    
                    if target_keyword:
                        app = QApplication.instance()
                        found = False
                        for widget in app.topLevelWidgets():
                            # 宽松检查：查找任何具有 'scene' 属性的窗口
                            if hasattr(widget, 'scene'):
                                scene = widget.scene
                                if not scene:
                                    continue
                                    
                                for item in scene.items():
                                    if not hasattr(item, 'node_title'):
                                        continue
                                    if target_keyword not in item.node_title:
                                        continue

                                    candidate_rows = []

                                    # 1) 直接从节点属性中获取行列表（地点节点: rows，人物节点: character_rows）
                                    if hasattr(item, 'rows'):
                                        candidate_rows.extend(
                                            [r for r in getattr(item, 'rows') or [] if hasattr(r, 'name_edit')]
                                        )
                                    if hasattr(item, 'character_rows'):
                                        candidate_rows.extend(
                                            [r for r in getattr(item, 'character_rows') or [] if hasattr(r, 'name_edit')]
                                        )

                                    # 2) 通过 proxy_widget 在内部 QWidget 树中查找行控件
                                    if hasattr(item, 'proxy_widget') and item.proxy_widget.widget():
                                        from PySide6.QtWidgets import QWidget

                                        widgets = item.proxy_widget.widget().findChildren(QWidget)
                                        for child in widgets:
                                            if hasattr(child, 'name_edit') and hasattr(child, 'set_image'):
                                                candidate_rows.append(child)

                                    for row in candidate_rows:
                                        row_name = ""
                                        try:
                                            if hasattr(row, 'name_edit') and hasattr(row.name_edit, 'toPlainText'):
                                                row_name = row.name_edit.toPlainText().strip()
                                        except Exception:
                                            continue

                                        if row_name == self.asset_name:
                                            # 直接覆盖，不需要检查 row 是否已有图片
                                            if hasattr(row, 'set_image'):
                                                # 确保路径存在
                                                if self.image_path and os.path.exists(self.image_path):
                                                    row.set_image(self.image_path)
                                                    print(f"[Library] Auto-synced {self.asset_name} to node row.")
                                                    found = True
                                                    break
                                    if found:
                                        break
                        
                        if found:
                            # 如果同步成功，可以保持高亮或做其他处理
                            pass
        
        super().mouseReleaseEvent(event)


class LibraryToggleButton(QPushButton):
    toggled_visibility = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(32, 32)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self._visible = False
        self._update_style()
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self):
        self._visible = not self._visible
        self._update_style()
        self.toggled_visibility.emit(self._visible)

    def _update_style(self):
        if self._visible:
            text = "库"
        else:
            text = "库"
        self.setText(text)
        self.setToolTip("资料库")
        self.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(0,0,0,180);
                color: #ffffff;
                border-radius: 16px;
                border: 1px solid rgba(255,255,255,60);
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(33,33,33,220);
            }
            QPushButton:pressed {
                background-color: rgba(0,0,0,230);
            }
            """
        )

    def sync_from_panel(self, visible):
        self._visible = visible
        self._update_style()


class LibraryPanel(QFrame):
    visibility_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.store = AssetLibraryStore()
        self.current_category = "people"
        self.setWindowFlags(Qt.Widget | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(380, 430)
        self._setup_ui()
        self.refresh_assets()

    def _setup_ui(self):
        self.setStyleSheet(
            """
            QFrame {
                background-color: transparent;
            }
            QFrame#RootFrame {
                background-color: rgba(0,0,0,200);
                border-radius: 16px;
                border: 1px solid rgba(255,255,255,40);
            }
            QLabel#TitleLabel {
                color: #ffffff;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton#TabButton {
                background-color: transparent;
                color: #e0e0e0;
                border-radius: 12px;
                border: 1px solid transparent;
                padding: 4px 10px;
                font-size: 12px;
            }
            QPushButton#TabButton[selected="true"] {
                background-color: rgba(76,175,80,0.9);
                border-color: rgba(129,199,132,1);
                color: #ffffff;
            }
            QPushButton#TabButton:hover {
                background-color: rgba(255,255,255,0.1);
            }
            QPushButton#AddButton {
                background-color: rgba(255,255,255,0.12);
                border-radius: 12px;
                border: 1px solid rgba(255,255,255,40);
                color: #ffffff;
                padding: 4px 12px;
                font-size: 12px;
            }
            QPushButton#AddButton:hover {
                background-color: rgba(255,255,255,0.2);
            }
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        root = QFrame(objectName="RootFrame")
        outer.addWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        title = QLabel("资料库")
        title.setObjectName("TitleLabel")
        header.addWidget(title)
        header.addStretch(1)
        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(22, 22)
        self.btn_close.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                color: #ffffff;
                border: none;
                border-radius: 11px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(255,255,255,0.2);
            }
            """
        )
        self.btn_close.clicked.connect(self.hide_panel)
        header.addWidget(self.btn_close)
        layout.addLayout(header)

        tabs = QHBoxLayout()
        tabs.setContentsMargins(0, 0, 0, 0)
        tabs.setSpacing(6)
        self.tab_people = QPushButton("人物")
        self.tab_people.setObjectName("TabButton")
        self.tab_scene = QPushButton("场景")
        self.tab_scene.setObjectName("TabButton")
        self.tab_items = QPushButton("道具")
        self.tab_items.setObjectName("TabButton")
        tabs.addWidget(self.tab_people)
        tabs.addWidget(self.tab_scene)
        tabs.addWidget(self.tab_items)
        layout.addLayout(tabs)

        self.tab_people.clicked.connect(lambda: self.switch_category("people"))
        self.tab_items.clicked.connect(lambda: self.switch_category("items"))
        self.tab_scene.clicked.connect(lambda: self.switch_category("scene"))

        ctrl = QHBoxLayout()
        ctrl.setContentsMargins(0, 0, 0, 0)
        ctrl.setSpacing(6)
        ctrl.addStretch(1)
        self.btn_add = QPushButton("＋ 添加图片")
        self.btn_add.setObjectName("AddButton")
        self.btn_add.clicked.connect(self.add_images)
        ctrl.addWidget(self.btn_add)
        layout.addLayout(ctrl)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            """
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: rgba(255,255,255,20);
                width: 10px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(160,160,160,180);
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(190,190,190,220);
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                background: transparent;
                height: 0;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: rgba(255,255,255,20);
            }
            """
        )
        layout.addWidget(self.scroll, 1)

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 4, 0, 0)
        self.grid_layout.setHorizontalSpacing(6)
        self.grid_layout.setVerticalSpacing(6)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.grid_container.setStyleSheet("background-color: transparent;")
        self.scroll.viewport().setStyleSheet("background-color: transparent;")
        self.scroll.setWidget(self.grid_container)

        self.switch_category("people")

    def switch_category(self, key):
        self.current_category = key
        self.tab_people.setProperty("selected", "true" if key == "people" else "false")
        self.tab_items.setProperty("selected", "true" if key == "items" else "false")
        self.tab_scene.setProperty("selected", "true" if key == "scene" else "false")
        self.tab_people.style().unpolish(self.tab_people)
        self.tab_people.style().polish(self.tab_people)
        self.tab_items.style().unpolish(self.tab_items)
        self.tab_items.style().polish(self.tab_items)
        self.tab_scene.style().unpolish(self.tab_scene)
        self.tab_scene.style().polish(self.tab_scene)
        self.refresh_assets()

    def add_images(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)",
        )
        if not files:
            return
        self.store.add_assets(self.current_category, files)
        self.refresh_assets()

    def refresh_assets(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        assets = self.store.list_assets(self.current_category)
        row = 0
        col = 0
        for asset in assets:
            path = asset.get("path") if isinstance(asset, dict) else asset
            if not path:
                continue
            thumb = AssetThumbnail(self.current_category, asset, self.store, self.grid_container)
            self.grid_layout.addWidget(thumb, row, col)
            col += 1
            if col >= 3:
                col = 0
                row += 1
        self.grid_container.adjustSize()

    def show_panel(self):
        self.show()
        self.raise_()
        self.visibility_changed.emit(True)

    def hide_panel(self):
        self.hide()
        self.visibility_changed.emit(False)

