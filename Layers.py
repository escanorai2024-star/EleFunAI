from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QListWidget, QMenu, QHBoxLayout, QPushButton, QFileDialog
from PySide6.QtGui import QPixmap, QIcon, QAction, QPainter, QPen, QColor, QBrush
from PySide6.QtWidgets import QListWidgetItem
from PySide6.QtCore import Qt, QSize, QEvent


class LayersPanel(QFrame):
    """右侧图层面板：支持勾选启用、内部拖拽重排、加/删层。"""

    def __init__(self, canvas=None, parent=None):
        super().__init__(parent)
        self.setObjectName('RightLayers')
        self.setAttribute(Qt.WA_StyledBackground, True)  # Ensure background color is painted
        self.setStyleSheet("background: #ffffff; border-left: 1px solid #e0e0e0;")
        self.setFixedWidth(220)
        self.canvas = canvas

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self._lang_code = 'zh'
        self._i18n = self._get_i18n(self._lang_code)
        self.title = QLabel('图层')
        layout.addWidget(self.title)
        self.list = QListWidget()
        # 选中项半透明红色高亮（同时覆盖 hover）
        self.list.setStyleSheet(
            """
            QListWidget { background: #ffffff; border: none; outline: none; }
            QListWidget::item { padding: 4px; border-radius: 6px; margin: 2px 4px; color: #333333; }
            QListWidget::item:selected { background: rgba(52, 199, 89, 0.2); color: #000000; border: 1px solid rgba(52, 199, 89, 0.5); }
            QListWidget::item:selected:!active { background: rgba(52, 199, 89, 0.15); }
            QListWidget::item:hover { background: rgba(0, 0, 0, 0.05); }
            """
        )
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        # 支持Shift多选
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        # 允许内部拖拽重排
        self.list.setDragDropMode(QListWidget.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        # 拖拽重排后同步到画布
        try:
            self.list.model().rowsMoved.connect(self._on_rows_moved)
        except Exception:
            pass
        # 勾选启用/禁用
        self.list.itemChanged.connect(self._on_item_changed)
        # 选中项变化时，将画板的当前绘制图层切换到该项
        try:
            self.list.currentItemChanged.connect(self._on_selection_changed)
        except Exception:
            pass
        # 安装事件过滤器以捕获Delete键
        self.list.installEventFilter(self)
        layout.addWidget(self.list)

        # 底部工具栏：+、垃圾桶 与 上传按钮
        tools = QHBoxLayout()
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(10)
        btn_add = QPushButton('')
        btn_del = QPushButton('')
        btn_upload = QPushButton('')
        # 绘制简洁图标
        btn_add.setIcon(self._make_plus_icon())
        btn_del.setIcon(self._make_trash_icon())
        btn_upload.setIcon(self._make_upload_icon())
        btn_add.setIconSize(QSize(20, 20))
        btn_del.setIconSize(QSize(20, 20))
        btn_upload.setIconSize(QSize(20, 20))
        btn_add.setStyleSheet('QPushButton{border:none;background:transparent;padding:0;margin:0;border-radius:4px;} QPushButton:hover{background:rgba(52, 168, 83, 0.1);}')
        btn_del.setStyleSheet('QPushButton{border:none;background:transparent;padding:0;margin:0;border-radius:4px;} QPushButton:hover{background:rgba(52, 168, 83, 0.1);}')
        btn_upload.setStyleSheet('QPushButton{border:none;background:transparent;padding:0;margin:0;border-radius:4px;} QPushButton:hover{background:rgba(52, 168, 83, 0.1);}')
        btn_upload.setToolTip(self._i18n.get('upload_image', '上传图片'))
        btn_add.clicked.connect(self._add_blank_layer)
        btn_del.clicked.connect(self._delete_selected_layer)
        btn_upload.clicked.connect(self._upload_image)
        tools.addWidget(btn_add)
        tools.addWidget(btn_del)
        tools.addWidget(btn_upload)
        # 放到右侧稍靠内的位置
        tools.addStretch()
        layout.addLayout(tools)

    def add_layer_pixmap(self, pix: QPixmap, name: str, sync_to_canvas: bool = False):
        """添加一个图层缩略项（默认启用，可拖拽）。
        
        Args:
            pix: 图层的 QPixmap
            name: 图层名称
            sync_to_canvas: 是否立即同步到画板（默认 False，仅添加到图层列表）
        """
        if pix is None or pix.isNull():
            return
        thumb = pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        item = QListWidgetItem(name)
        item.setIcon(QIcon(thumb))
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        item.setCheckState(Qt.Checked)
        self.list.addItem(item)
        
        # 存储原始 pixmap 到 item 的自定义数据中（用于后续上传到画板）
        item.setData(Qt.UserRole + 1, pix)
        
        # 仅当 sync_to_canvas=True 时才同步到画板图层
        if sync_to_canvas and self.canvas is not None:
            lid = self.canvas.add_image_layer(pix, name)
            if lid is not None:
                item.setData(Qt.UserRole, lid)

    def _context_menu(self, pos):
        menu = QMenu(self)
        
        # 获取右键位置的项
        item = self.list.itemAt(pos)
        if item is None:
            item = self.list.currentItem()
        
        # 检查该图层是否已上传到画板
        has_canvas_layer = False
        if item is not None:
            lid = item.data(Qt.UserRole)
            has_canvas_layer = (lid is not None)
        
        # 保存图片（优先放在第一项）
        act_save = QAction('保存图片…', self)
        act_del = QAction(self._i18n.get('delete_layer', '删除图层'), self)
        # 合并图层（当选择>=2项可用）
        act_merge = QAction(self._i18n.get('merge_layers', '合并图层'), self)
        act_merge.setEnabled(len(self.list.selectedItems()) >= 2)
        # 发送到参考图
        act_send_to_ref = QAction(self._i18n.get('send_to_reference', '发送到参考图'), self)
        # 上传到画板（仅当图层未上传时显示）
        act_upload_to_canvas = None
        if not has_canvas_layer and item is not None:
            act_upload_to_canvas = QAction(self._i18n.get('upload_to_canvas', '上传到画板'), self)
        
        menu.addAction(act_save)
        if act_upload_to_canvas:
            menu.addAction(act_upload_to_canvas)
        menu.addAction(act_send_to_ref)
        menu.addSeparator()
        menu.addAction(act_del)
        menu.addAction(act_merge)
        
        act = menu.exec_(self.list.mapToGlobal(pos))
        
        if act == act_upload_to_canvas:
            # 上传图层到画板
            if item is not None:
                self._upload_layer_to_canvas(item)
        elif act == act_send_to_ref:
            # 找到右键位置对应的项
            item = self.list.itemAt(pos)
            if item is None:
                item = self.list.currentItem()
            if item is None:
                return
            self._send_layer_to_reference(item)
        elif act == act_save:
            # 找到右键位置对应的项；若无则回退当前项
            item = self.list.itemAt(pos)
            if item is None:
                item = self.list.currentItem()
            if item is None:
                return
            lid = item.data(Qt.UserRole)
            if lid is None or self.canvas is None:
                return
            # 在画布中查找对应图层的像素内容
            layer_pix = None
            for layer in getattr(self.canvas, 'layers', []):
                if layer.get('id') == lid:
                    layer_pix = layer.get('pix')
                    break
            if layer_pix is None or layer_pix.isNull():
                return
            # 选择保存路径（默认到项目的 JPG 目录）
            import os, datetime
            base_dir = os.path.join(os.getcwd(), 'JPG')
            os.makedirs(base_dir, exist_ok=True)
            ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
            default_path = os.path.join(base_dir, f'{ts}-layer.jpg')
            path, fmt = QFileDialog.getSaveFileName(self, '保存图片', default_path, 'JPEG (*.jpg *.jpeg);;PNG (*.png)')
            if not path:
                return
            # 根据扩展名选择格式
            ext = os.path.splitext(path)[1].lower()
            if ext in ('.png',):
                layer_pix.save(path, 'PNG')
            else:
                # 默认保存为JPEG
                layer_pix.save(path, 'JPG')
        elif act == act_del:
            # 支持多选批量删除；若无多选则删除右键项或当前项
            sels = self.list.selectedItems()
            if sels:
                rows = sorted([self.list.row(it) for it in sels], reverse=True)
                lids = []
                for it in sels:
                    lid = it.data(Qt.UserRole)
                    if lid is not None:
                        lids.append(lid)
                for r in rows:
                    self.list.takeItem(r)
                if self.canvas is not None:
                    for lid in lids:
                        self.canvas.remove_layer_by_id(lid)
            else:
                item = self.list.itemAt(pos)
                if item is None:
                    item = self.list.currentItem()
                if item is not None:
                    row = self.list.row(item)
                    it = self.list.takeItem(row)
                    if self.canvas is not None and it is not None:
                        lid = it.data(Qt.UserRole)
                        if lid is not None:
                            self.canvas.remove_layer_by_id(lid)
        elif act == act_merge:
            sels = self.list.selectedItems()
            if self.canvas is not None and sels and len(sels) >= 2:
                # 记录插入位置为所选中最靠前的行
                rows = sorted([self.list.row(it) for it in sels])
                insert_row = rows[0]
                ids = []
                for it in sels:
                    lid = it.data(Qt.UserRole)
                    if lid is not None:
                        ids.append(lid)
                res = self.canvas.merge_layers_by_ids(ids)
                if res is not None:
                    new_lid, new_pix = res
                    # 删除旧项
                    # 需从后往前删，避免索引移动
                    for r in reversed(rows):
                        self.list.takeItem(r)
                    # 插入合并后的列表项
                    thumb = new_pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    item = QListWidgetItem(self._i18n.get('merged_layer', '合并层'))
                    item.setIcon(QIcon(thumb))
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    item.setCheckState(Qt.Checked)
                    item.setData(Qt.UserRole, new_lid)
                    self.list.insertItem(insert_row, item)
                    self.list.setCurrentItem(item)

    def _on_item_changed(self, item: QListWidgetItem):
        enabled = item.checkState() == Qt.Checked
        if self.canvas is not None:
            lid = item.data(Qt.UserRole)
            if lid is not None:
                self.canvas.set_layer_enabled_by_id(lid, enabled)

    def _add_blank_layer(self):
        if self.canvas is not None:
            # 先在画布添加空白层
            name = self._i18n.get('blank_layer', '空白层')
            lid = self.canvas.add_blank_layer(name)
            # 在列表中显示一个透明缩略图占位
            w, h = self.canvas.paint_layer.width(), self.canvas.paint_layer.height()
            pix = QPixmap(w, h)
            pix.fill(Qt.transparent)
            thumb = pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            item = QListWidgetItem(self._i18n.get('blank_layer', '空白层'))
            item.setIcon(QIcon(thumb))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, lid)
            self.list.addItem(item)
            # 选中为当前绘制图层
            self.list.setCurrentItem(item)

    def _delete_selected_layer(self):
        sels = self.list.selectedItems()
        if sels:
            rows = sorted([self.list.row(it) for it in sels], reverse=True)
            lids = []
            for it in sels:
                lid = it.data(Qt.UserRole)
                if lid is not None:
                    lids.append(lid)
            for r in rows:
                self.list.takeItem(r)
            if self.canvas is not None:
                for lid in lids:
                    self.canvas.remove_layer_by_id(lid)
            return
        row = self.list.currentRow()
        if row >= 0:
            it = self.list.takeItem(row)
            if self.canvas is not None and it is not None:
                lid = it.data(Qt.UserRole)
                if lid is not None:
                    self.canvas.remove_layer_by_id(lid)

    def _on_selection_changed(self, current: QListWidgetItem, previous: QListWidgetItem | None):
        """当用户选择图层时，切换画板的绘制目标。"""
        if current is None or self.canvas is None:
            return
        lid = current.data(Qt.UserRole)
        if lid is not None:
            self.canvas.set_active_layer_by_id(lid)

    def set_language(self, code: str):
        """设置语言并更新标题与默认项文字。"""
        if code not in ('zh', 'en'):
            code = 'zh'
        self._lang_code = code
        self._i18n = self._get_i18n(code)
        self.title.setText(self._i18n.get('layers_title', '图层'))
        # 翻译现有默认项（匹配默认名）
        for i in range(self.list.count()):
            it = self.list.item(i)
            txt = it.text()
            if txt in ('空白层', 'Blank Layer'):
                it.setText(self._i18n.get('blank_layer', txt))
            elif txt in ('合并层', 'Merged Layer'):
                it.setText(self._i18n.get('merged_layer', txt))

    def _get_i18n(self, code: str) -> dict:
        zh = {
            'layers_title': '图层',
            'delete_layer': '删除图层',
            'merge_layers': '合并图层',
            'blank_layer': '空白层',
            'merged_layer': '合并层',
            'upload_image': '上传图片',
            'send_to_reference': '发送到参考图',
            'upload_to_canvas': '上传到画板',
        }
        en = {
            'layers_title': 'Layers',
            'delete_layer': 'Delete Layer',
            'merge_layers': 'Merge Layers',
            'blank_layer': 'Blank Layer',
            'merged_layer': 'Merged Layer',
            'upload_image': 'Upload Image',
            'send_to_reference': 'Send to Reference',
            'upload_to_canvas': 'Upload to Canvas',
        }
        return zh if code == 'zh' else en

    def add_blank_named_layer(self, name: str):
        """添加一个命名空白图层并选中。"""
        if self.canvas is None:
            return
        lid = self.canvas.add_blank_layer(name)
        w, h = self.canvas.paint_layer.width(), self.canvas.paint_layer.height()
        pix = QPixmap(w, h)
        pix.fill(Qt.transparent)
        thumb = pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        item = QListWidgetItem(name)
        item.setIcon(QIcon(thumb))
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        item.setCheckState(Qt.Checked)
        item.setData(Qt.UserRole, lid)
        self.list.addItem(item)
        self.list.setCurrentItem(item)

    def _on_rows_moved(self, parent, start, end, dest, row):
        # 拖拽重排后，按当前列表项顺序把ID同步到画布
        if self.canvas is None:
            return
        ids = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            lid = it.data(Qt.UserRole)
            if lid is not None:
                ids.append(lid)
        if ids:
            self.canvas.reorder_layers_by_ids(ids)

    def _make_plus_icon(self) -> QIcon:
        from PySide6.QtGui import QPainter, QPixmap, QPen, QColor
        pix = QPixmap(20, 20)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor('#666666'), 2)
        p.setPen(pen)
        p.drawRoundedRect(2, 2, 16, 16, 3, 3)
        p.drawLine(10, 5, 10, 15)
        p.drawLine(5, 10, 15, 10)
        p.end()
        return QIcon(pix)

    def _make_trash_icon(self) -> QIcon:
        pix = QPixmap(20, 20)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor('#666666'), 2)
        p.setPen(pen)
        # 盖子
        p.drawLine(6, 6, 14, 6)
        p.drawLine(8, 4, 12, 4)
        # 桶
        p.drawRoundedRect(6, 7, 8, 10, 2, 2)
        # 三条竖线
        p.drawLine(9, 9, 9, 15)
        p.drawLine(11, 9, 11, 15)
        p.drawLine(7, 9, 7, 15)
        p.end()
        return QIcon(pix)

    def _make_upload_icon(self) -> QIcon:
        """绘制上传图标（简洁矢量）：上箭头+托盘边框。"""
        pix = QPixmap(20, 20)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing, True)
        # 边框
        pen = QPen(QColor('#666666'), 2)
        p.setPen(pen)
        p.drawRoundedRect(2, 2, 16, 16, 3, 3)
        # 托盘
        p.drawLine(5, 13, 15, 13)
        p.drawLine(6, 12, 14, 12)
        # 箭头（向上）
        p.setPen(QPen(QColor('#34c759'), 2))
        p.drawLine(10, 6, 10, 11)
        p.drawLine(10, 6, 7, 9)
        p.drawLine(10, 6, 13, 9)
        p.end()
        return QIcon(pix)

    def _upload_image(self):
        """选择图片并添加为图层，同时导入到画板。"""
        try:
            path, _ = QFileDialog.getOpenFileName(self, self._i18n.get('upload_image', '上传图片'), '', 'Images (*.png *.jpg *.jpeg *.bmp)')
        except Exception:
            path = ''
        if not path:
            return
        from PySide6.QtGui import QPixmap as QPix
        pix = QPix(path)
        if pix.isNull():
            return
        import os
        name = os.path.basename(path)
        # 上传图片时需要同步到画板,实现联动效果
        self.add_layer_pixmap(pix, name, sync_to_canvas=True)
        # 选中新添加的项为当前图层
        try:
            it = self.list.item(self.list.count() - 1)
            if it is not None:
                self.list.setCurrentItem(it)
        except Exception:
            pass

    def eventFilter(self, obj, event):
        """事件过滤器：捕获Delete键删除选中图层"""
        if obj == self.list and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key_Delete:
                # 调用删除选中图层的方法
                self._delete_selected_layer()
                return True  # 事件已处理
        return super().eventFilter(obj, event)

    # ---------- 状态同步 ----------
    def sync_from_canvas(self):
        """从画布状态重建图层列表（用于撤销等操作后同步UI）。"""
        if self.canvas is None:
            return
        self.list.clear()
        for layer in self.canvas.layers:
            pix = layer.get('pix')
            name = layer.get('name') or '图层'
            enabled = layer.get('enabled', True)
            lid = layer.get('id')
            show_thumb = layer.get('show_thumb', True)
            if pix is None:
                continue
            item = QListWidgetItem(name)
            if show_thumb:
                thumb = pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                item.setIcon(QIcon(thumb))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.setCheckState(Qt.Checked if enabled else Qt.Unchecked)
            item.setData(Qt.UserRole, lid)
            self.list.addItem(item)

    def _send_layer_to_reference(self, item: QListWidgetItem):
        """将图层图片发送到参考图区域"""
        if item is None or self.canvas is None:
            return
        
        lid = item.data(Qt.UserRole)
        if lid is None:
            return
        
        # 在画布中查找对应图层的像素内容
        layer_pix = None
        for layer in getattr(self.canvas, 'layers', []):
            if layer.get('id') == lid:
                layer_pix = layer.get('pix')
                break
        
        if layer_pix is None or layer_pix.isNull():
            return
        
        # 查找父窗口中的 PhotoPage
        photo_page = None
        parent = self.parent()
        while parent is not None:
            if parent.__class__.__name__ == 'PhotoPage':
                photo_page = parent
                break
            parent = parent.parent()
        
        if photo_page is None:
            return
        
        # 调用 PhotoPage 的方法将图片添加到参考图
        if hasattr(photo_page, 'add_to_reference_from_layer'):
            photo_page.add_to_reference_from_layer(layer_pix)
    
    def _upload_layer_to_canvas(self, item: QListWidgetItem):
        """将图层上传到画板"""
        if item is None or self.canvas is None:
            return
        
        # 检查是否已经上传过
        lid = item.data(Qt.UserRole)
        if lid is not None:
            # 已经上传过，不需要重复上传
            return
        
        # 获取存储的原始 pixmap
        pix = item.data(Qt.UserRole + 1)
        if pix is None or pix.isNull():
            return
        
        # 上传到画板
        layer_name = item.text()
        new_lid = self.canvas.add_image_layer(pix, layer_name)
        if new_lid is not None:
            # 更新 item 的 lid 数据
            item.setData(Qt.UserRole, new_lid)
            print(f'[DEBUG] 图层 "{layer_name}" 已上传到画板', flush=True)