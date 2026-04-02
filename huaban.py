from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QGridLayout, QMenu, QFileDialog, QInputDialog
from PySide6.QtGui import QPainter, QPixmap, QPen, QColor, QMouseEvent, QPainterPath, QBrush, QIcon, QCursor
from PySide6.QtCore import Qt, QPoint, QSize, QRect, Signal


class DoubleClickLabel(QLabel):
    """支持双击编辑的标签"""
    double_clicked = Signal()
    
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
    
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)
 


class HuabanCanvas(QWidget):
    # 选区右键触发信号（携带矩形区域）
    magic_generate_requested = Signal(QRect)
    # 智能生成信号（携带矩形区域和遮罩）
    smart_generate_requested = Signal(QRect, object)  # (rect, mask)
    # 智能修改信号（携带矩形区域和遮罩）
    smart_edit_requested = Signal(QRect, object)  # (rect, mask)
    # 智能区域修改信号（携带矩形区域）
    smart_region_edit_requested = Signal(QRect)  # (rect)
    # 智能替换信号（携带矩形区域和遮罩）
    smart_replace_requested = Signal(QRect, object)  # (rect, mask)
    # 画板尺寸改变信号
    size_changed = Signal(int, int)  # (width, height)
    # 请求自适应缩放信号
    auto_fit_requested = Signal()
    # 上传到参考图信号
    upload_to_ref_requested = Signal(QPixmap)
    """
    简易画板：支持画笔与橡皮擦。
    - 红色背景作为面板区域视觉参照。
    - 采用 QPixmap 作为缓冲，鼠标拖拽绘制。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # 语言代码与翻译表（用于默认图层名称）
        self._lang_code = 'zh'
        self._i18n = self._get_i18n(self._lang_code)
        # 允许更小尺寸，便于预设比例缩放
        self.setMinimumSize(200, 200)
        # 画板背景改为白色
        self.bg_color = QColor(255, 255, 255)
        # 绘制层（笔刷/橡皮擦）单独存储，便于与图层叠加控制
        self.paint_layer = QPixmap(1200, 800)
        self.paint_layer.fill(Qt.transparent)
        # 图层列表：每项为 dict {pix:QPixmap, x:int, y:int, enabled:bool, name:str}
        self.layers: list[dict] = []
        # 图层唯一ID序列
        self._layer_seq: int = 0
        # 当前激活的绘制图层ID（None 表示未选择，回退到 paint_layer）
        self._active_layer_id: int | None = None
        self.last_pos: QPoint | None = None
        # 工具：none | brush | eraser | move | rect_select | magic_wand | bucket | eyedropper | auto_select
        self.tool = 'none'
        # 默认使用黑色，避免在白色背景上不可见
        self.brush_color = QColor(0, 0, 0)
        self.brush_size = 10
        self.eraser_size = 20
        # 选择状态与移动状态
        self._rect_select_active = False
        self._sel_rect_start: QPoint | None = None
        self._sel_rect_current: QPoint | None = None
        self.selection_rect: QRect | None = None
        self.selection_mask = None  # 可选：QImage (Alpha8)，由魔术棒生成
        self._move_last_pos: QPoint | None = None
        # 变换/缩放：句柄尺寸与拖拽状态
        self._transform_handle_size: int = 8
        self._resize_handle: str | None = None  # tl,tr,bl,br,l,r,t,b
        self._resize_start_rect: QRect | None = None
        self._resize_start_pix: QPixmap | None = None
        self._resize_start_pos: QPoint | None = None
        self._resize_keep_ratio: bool = False
        # 接受拖拽（从缩略图、系统或其它程序拖入图片/文件）
        self.setAcceptDrops(True)
        # 初始使用系统光标
        self._last_cursor_kind = 'none'
        # 历史栈用于撤销
        self._history: list[dict] = []
        self._history_limit: int = 30
        # 允许接收键盘事件
        self.setFocusPolicy(Qt.StrongFocus)
        # 高级魔法生成标记
        self._adv_magic_pending: bool = False
        # 缩放比例（用于显示缩放，不影响实际像素）
        self._zoom_scale: float = 1.0

    def set_tool(self, tool: str):
        self.tool = tool
        # 工具切换时更新光标显示
        self._update_cursor()

    def paintEvent(self, event):
        p = QPainter(self)
        
        # 应用缩放变换
        if self._zoom_scale != 1.0:
            p.scale(self._zoom_scale, self._zoom_scale)
        
        p.fillRect(QRect(0, 0, self.paint_layer.width(), self.paint_layer.height()), self.bg_color)
        # 先画绘制层
        p.drawPixmap(0, 0, self.paint_layer)
        # 再叠加启用的图层
        for layer in self.layers:
            if layer.get('enabled', True):
                p.drawPixmap(layer.get('x', 0), layer.get('y', 0), layer['pix'])
        
        # 绘制自动选区的绿色半透明遮罩（人物轮廓高亮）
        if self.selection_mask is not None:
            from PySide6.QtGui import QImage
            # 创建绿色半透明覆盖层
            w = len(self.selection_mask[0]) if self.selection_mask else 0
            h = len(self.selection_mask) if self.selection_mask else 0
            
            if w > 0 and h > 0:
                # 创建一个图像来存储遮罩
                overlay_img = QImage(w, h, QImage.Format_ARGB32)
                overlay_img.fill(Qt.transparent)
                
                # 将遮罩转换为图像（批量处理更高效）
                green_color = QColor(52, 168, 83, 100).rgba()  # 绿色，alpha=100
                for y in range(h):
                    for x in range(w):
                        if self.selection_mask[y][x]:  # 如果该像素在选区内
                            overlay_img.setPixel(x, y, green_color)
                
                # 转换为 QPixmap 并绘制
                overlay = QPixmap.fromImage(overlay_img)
                p.drawPixmap(0, 0, overlay)
        
        # 在移动工具下，为当前激活图层绘制蓝色变换框与句柄
        if self.tool == 'move' and self._active_layer_id is not None:
            al = self._get_active_layer()
            if al is not None:
                rect = QRect(al.get('x', 0), al.get('y', 0), al['pix'].width(), al['pix'].height())
                pen = QPen(QColor('#34A853'), 1, Qt.SolidLine)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawRect(rect)
                # 画8个句柄（角点与边中点）
                hs = self._transform_handle_size
                handles = self._calc_handle_rects(rect, hs)
                p.setBrush(QBrush(QColor('#34A853')))
                for r in handles.values():
                    p.drawRect(r)
        # 绘制矩形选择的绿色边缘（满足"自动产生绿色边缘"的需求）
        if self.selection_rect is not None and self.tool != 'auto_select':
            # 检查是否处于智能区域修改模式
            smart_region_mode = getattr(self, '_smart_region_edit_mode', False)
            
            if smart_region_mode and self.tool == 'rect_select':
                # 智能区域修改模式：绘制半透明绿色遮罩
                p.fillRect(self.selection_rect, QColor(52, 199, 89, 100))  # 绿色半透明填充
            
            # 绘制绿色边框
            pen = QPen(QColor('#34c759'), 2, Qt.SolidLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.selection_rect)
        p.end()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton:
            return
        pos = self._scale_pos(event.position().toPoint())
        if self.tool in ('brush', 'eraser'):
            # 开始一笔前记录历史
            self._push_history()
            self.last_pos = pos
            self._draw_to(pos)
        elif self.tool == 'move':
            # 若点中变换句柄，进入缩放模式；否则移动
            al = self._get_active_layer()
            if al is not None:
                rect = QRect(al.get('x', 0), al.get('y', 0), al['pix'].width(), al['pix'].height())
                handle = self._hit_test_handle(pos, rect, self._transform_handle_size)
                if handle is not None:
                    self._push_history()
                    self._resize_handle = handle
                    self._resize_start_rect = QRect(rect)
                    self._resize_start_pix = al['pix'].copy()
                    self._resize_start_pos = pos
                    return
            # 开始移动前记录历史
            self._push_history()
            self._move_last_pos = pos
        elif self.tool == 'rect_select':
            self._rect_select_active = True
            self._sel_rect_start = pos
            self._sel_rect_current = pos
            self.selection_rect = QRect(pos, QSize(1, 1))
            self.selection_mask = None  # 清除自动选区遮罩
            self.update()
        elif self.tool == 'magic_wand':
            self.selection_mask = None  # 清除自动选区遮罩
            self._wand_select(pos)
            self.update()
        elif self.tool == 'auto_select':
            self._auto_select(pos)
            self.update()
        elif self.tool == 'bucket':
            # 填充前记录历史
            self._push_history()
            self._bucket_fill(pos)
            self.update()
        elif self.tool == 'eyedropper':
            color = self._sample_color(pos)
            if color is not None:
                self.brush_color = color
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = self._scale_pos(event.position().toPoint())
        if self.tool in ('brush', 'eraser'):
            if self.last_pos is not None:
                self._draw_line(self.last_pos, pos)
                self.last_pos = pos
        elif self.tool == 'move':
            # 缩放优先
            if self._resize_handle is not None and self._active_layer_id is not None:
                self._perform_resize_drag(pos)
                self.update()
            elif self._move_last_pos is not None and self._active_layer_id is not None:
                dx = pos.x() - self._move_last_pos.x()
                dy = pos.y() - self._move_last_pos.y()
                for layer in self.layers:
                    if layer.get('id') == self._active_layer_id:
                        layer['x'] = layer.get('x', 0) + dx
                        layer['y'] = layer.get('y', 0) + dy
                        break
                self._move_last_pos = pos
                self.update()
            # 根据悬停位置更新光标（句柄显示方向）
            if self._active_layer_id is not None:
                al = self._get_active_layer()
                if al is not None:
                    rect = QRect(al.get('x', 0), al.get('y', 0), al['pix'].width(), al['pix'].height())
                    self._update_move_cursor(pos, rect)
        elif self.tool == 'rect_select' and self._rect_select_active and self._sel_rect_start is not None:
            self._sel_rect_current = pos
            x0, y0 = self._sel_rect_start.x(), self._sel_rect_start.y()
            x1, y1 = pos.x(), pos.y()
            self.selection_rect = QRect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
            self.update()
        # 跟随鼠标更新光标（考虑画笔/橡皮大小可能变化）
        if self.tool in ('brush', 'eraser'):
            self._update_cursor()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.last_pos = None
        if self.tool == 'move':
            self._move_last_pos = None
            self._resize_handle = None
            self._resize_start_rect = None
            self._resize_start_pix = None
            self._resize_start_pos = None
        if self.tool == 'rect_select':
            self._rect_select_active = False

    def enterEvent(self, event):
        # 进入画板区域时，按当前工具显示自定义光标
        self._update_cursor()
        super().enterEvent(event)

    def leaveEvent(self, event):
        # 离开画板区域时恢复系统光标
        self.unsetCursor()
        self._last_cursor_kind = 'none'
        super().leaveEvent(event)

    def dragEnterEvent(self, event):
        md = event.mimeData()
        if md.hasUrls() or md.hasImage():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        md = event.mimeData()
        # 优先处理本地文件路径
        if md.hasUrls():
            for url in md.urls():
                path = url.toLocalFile()
                if path:
                    self.add_image_layer(path)
                    event.acceptProposedAction()
                    return
        # 其次尝试图像数据
        if md.hasImage():
            img = md.imageData()
            try:
                if isinstance(img, QPixmap):
                    self.add_image_layer(img)
                else:
                    from PySide6.QtGui import QImage
                    if isinstance(img, QImage):
                        self.add_image_layer(QPixmap.fromImage(img))
            except Exception:
                pass
            event.acceptProposedAction()

    def contextMenuEvent(self, event):
        # 右键菜单：在画板区域提供"清空画板"，并在满足条件时提供"魔法生成"和"翻面"
        pos = event.pos()
        menu = QMenu(self)
        act_clear = menu.addAction('清空画板')
        act_magic = None
        act_magic_adv = None
        act_smart = None  # 智能生成
        act_smart_edit = None  # 智能修改
        act_smart_replace = None  # 智能替换
        act_smart_region_edit = None  # 智能区域修改
        act_flip_h = None
        act_flip_v = None
        rect = self.selection_rect
        
        # 检查是否处于智能区域修改模式
        smart_region_mode = getattr(self, '_smart_region_edit_mode', False)
        
        # 根据工具类型显示不同的菜单项
        if self.tool == 'auto_select' and rect is not None and rect.contains(pos) and self.selection_mask is not None:
            # 自动选区工具：显示智能生成、智能修改和智能替换
            act_smart = menu.addAction('智能生成')
            act_smart_edit = menu.addAction('智能修改')
            act_smart_replace = menu.addAction('智能替换')
        elif self.tool in ('rect_select', 'magic_wand') and rect is not None and rect.contains(pos):
            # 检查是否处于智能区域修改模式
            if smart_region_mode and self.tool == 'rect_select':
                # 智能区域修改模式：显示智能区域修改选项
                act_smart_region_edit = menu.addAction('智能区域修改')
            else:
                # 普通模式：矩形选区和魔术棒显示魔法生成
                act_magic = menu.addAction('魔法生成')
                act_magic_adv = menu.addAction('高级魔法生成')
        
        # 如果有激活的图层，添加翻转选项
        if self._active_layer_id is not None:
            menu.addSeparator()
            act_flip_h = menu.addAction('水平翻转')
            act_flip_v = menu.addAction('垂直翻转')
            
        menu.addSeparator()
        act_upload_ref = menu.addAction('上传到参考图')
        
        chosen = menu.exec(event.globalPos())
        if chosen is act_clear:
            try:
                # 将当前状态推入历史，支持撤销
                self._push_history()
                # 清空绘制层与所有图层、选区状态
                self.paint_layer.fill(Qt.transparent)
                self.layers = []
                self._active_layer_id = None
                self.selection_rect = None
                self.selection_mask = None
                self.update()
            except Exception:
                pass
        elif chosen == act_upload_ref:
            try:
                img = self._composite_to_image()
                if not img.isNull():
                     self.upload_to_ref_requested.emit(QPixmap.fromImage(img))
            except Exception:
                pass
        elif act_magic is not None and chosen is act_magic:
            try:
                self._adv_magic_pending = False
                self.magic_generate_requested.emit(rect)
            except Exception:
                pass
        elif act_magic_adv is not None and chosen is act_magic_adv:
            try:
                self._adv_magic_pending = True
                self.magic_generate_requested.emit(rect)
            except Exception:
                pass
        elif act_smart is not None and chosen is act_smart:
            try:
                # 发射智能生成信号，传递选区矩形和遮罩
                self.smart_generate_requested.emit(rect, self.selection_mask)
            except Exception:
                pass
        elif act_smart_edit is not None and chosen is act_smart_edit:
            try:
                # 发射智能修改信号，传递选区矩形和遮罩
                self.smart_edit_requested.emit(rect, self.selection_mask)
            except Exception:
                pass
        elif act_smart_replace is not None and chosen is act_smart_replace:
            try:
                # 发射智能替换信号，传递选区矩形和遮罩
                self.smart_replace_requested.emit(rect, self.selection_mask)
            except Exception:
                pass
        elif act_smart_region_edit is not None and chosen is act_smart_region_edit:
            try:
                # 发射智能区域修改信号，传递选区矩形
                self.smart_region_edit_requested.emit(rect)
            except Exception:
                pass
        elif act_flip_h is not None and chosen is act_flip_h:
            try:
                self._flip_active_layer(horizontal=True)
            except Exception:
                pass
        elif act_flip_v is not None and chosen is act_flip_v:
            try:
                self._flip_active_layer(horizontal=False)
            except Exception:
                pass

    def _draw_to(self, pos: QPoint):
        # 优先将绘制输出到当前选中的图层，并考虑图层偏移
        target, offx, offy = self._get_active_target()
        # 将鼠标坐标转换为图层局部坐标，避免偏移
        local = QPoint(pos.x() - offx, pos.y() - offy)
        painter = QPainter(target)
        if self.tool == 'eraser':
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            pen = QPen(Qt.transparent, self.eraser_size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        else:
            pen = QPen(self.brush_color, self.brush_size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPoint(local)
        painter.end()
        self.update()

    def _draw_line(self, p1: QPoint, p2: QPoint):
        # 优先将绘制输出到当前选中的图层，并考虑图层偏移
        target, offx, offy = self._get_active_target()
        local1 = QPoint(p1.x() - offx, p1.y() - offy)
        local2 = QPoint(p2.x() - offx, p2.y() - offy)
        painter = QPainter(target)
        if self.tool == 'eraser':
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            pen = QPen(Qt.transparent, self.eraser_size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        else:
            pen = QPen(self.brush_color, self.brush_size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(local1, local2)
        painter.end()
        self.update()

    def _update_cursor(self):
        """根据当前工具与尺寸更新光标图案，确保锚点为鼠标中心。"""
        kind = self.tool
        if kind == 'none':
            if self._last_cursor_kind != 'none':
                self.unsetCursor()
                self._last_cursor_kind = 'none'
            return
        if kind in ('move',):
            # 默认移动光标；具体方向在 mouseMoveEvent 中依据句柄命中更新
            self.setCursor(Qt.SizeAllCursor)
            self._last_cursor_kind = 'move'
            return
        if kind in ('rect_select', 'magic_wand', 'bucket', 'eyedropper', 'auto_select'):
            self.setCursor(Qt.CrossCursor)
            self._last_cursor_kind = kind
            return
        # brush/eraser 自定义光标
        size = max(8, self.brush_size if kind == 'brush' else self.eraser_size)
        pm_size = size + 6
        pix = QPixmap(pm_size, pm_size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing, True)
        center = pm_size // 2
        radius = size // 2
        if kind == 'eraser':
            p.setPen(QPen(QColor('#ffffff'), 2))
            p.setBrush(Qt.NoBrush)
            side = size
            rect_top_left = QPoint(center - side // 2, center - side // 2)
            p.drawRect(rect_top_left.x(), rect_top_left.y(), side, side)
        else:
            p.setPen(QPen(QColor('#31A8FF'), 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPoint(center, center), radius, radius)
        p.setPen(QPen(QColor('#ffffff'), 1))
        p.drawLine(center - 2, center, center + 2, center)
        p.drawLine(center, center - 2, center, center + 2)
        p.end()
        cursor = QCursor(pix, center, center)
        self.setCursor(cursor)
        self._last_cursor_kind = kind

    def keyPressEvent(self, event):
        # Ctrl+Z 撤销
        if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_Z:
            self.undo()
            event.accept()
            return
        # Shift 等比缩放
        if event.key() == Qt.Key_Shift:
            self._resize_keep_ratio = True
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Shift:
            self._resize_keep_ratio = False
        super().keyReleaseEvent(event)

    # ---------- 变换/缩放辅助 ----------
    def _get_active_layer(self) -> dict | None:
        if self._active_layer_id is None:
            return None
        for layer in self.layers:
            if layer.get('id') == self._active_layer_id:
                return layer
        return None

    def _calc_handle_rects(self, rect: QRect, size: int) -> dict:
        hs = max(6, int(size))
        half = hs // 2
        cx = rect.center().x()
        cy = rect.center().y()
        points = {
            'tl': QPoint(rect.left(), rect.top()),
            'tr': QPoint(rect.right(), rect.top()),
            'bl': QPoint(rect.left(), rect.bottom()),
            'br': QPoint(rect.right(), rect.bottom()),
            'l': QPoint(rect.left(), cy),
            'r': QPoint(rect.right(), cy),
            't': QPoint(cx, rect.top()),
            'b': QPoint(cx, rect.bottom()),
        }
        rects = {}
        for k, pt in points.items():
            rects[k] = QRect(pt.x() - half, pt.y() - half, hs, hs)
        return rects

    def _hit_test_handle(self, pos: QPoint, rect: QRect, size: int) -> str | None:
        for k, r in self._calc_handle_rects(rect, size).items():
            if r.contains(pos):
                return k
        return None

    def _update_move_cursor(self, pos: QPoint, rect: QRect):
        h = self._hit_test_handle(pos, rect, self._transform_handle_size)
        if h in ('tl', 'br'):
            self.setCursor(Qt.SizeFDiagCursor)
        elif h in ('tr', 'bl'):
            self.setCursor(Qt.SizeBDiagCursor)
        elif h in ('l', 'r'):
            self.setCursor(Qt.SizeHorCursor)
        elif h in ('t', 'b'):
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.setCursor(Qt.SizeAllCursor)

    def _perform_resize_drag(self, pos: QPoint):
        al = self._get_active_layer()
        if al is None or self._resize_handle is None or self._resize_start_rect is None or self._resize_start_pix is None:
            return
        start = self._resize_start_rect
        dx = pos.x() - (self._resize_start_pos.x() if self._resize_start_pos else pos.x())
        dy = pos.y() - (self._resize_start_pos.y() if self._resize_start_pos else pos.y())
        # 根据句柄计算新的宽高（默认拖拽方向增量）
        new_w = start.width()
        new_h = start.height()
        handle = self._resize_handle
        if handle in ('br',):
            new_w = max(10, start.width() + dx)
            new_h = max(10, start.height() + dy)
            new_x = start.left()
            new_y = start.top()
        elif handle in ('tl',):
            new_w = max(10, start.width() - dx)
            new_h = max(10, start.height() - dy)
            new_x = start.right() - new_w
            new_y = start.bottom() - new_h
        elif handle in ('tr',):
            new_w = max(10, start.width() + dx)
            new_h = max(10, start.height() - dy)
            new_x = start.left()
            new_y = start.bottom() - new_h
        elif handle in ('bl',):
            new_w = max(10, start.width() - dx)
            new_h = max(10, start.height() + dy)
            new_x = start.right() - new_w
            new_y = start.top()
        elif handle == 'l':
            new_w = max(10, start.width() - dx)
            new_h = start.height()
            new_x = start.right() - new_w
            new_y = start.top()
        elif handle == 'r':
            new_w = max(10, start.width() + dx)
            new_h = start.height()
            new_x = start.left()
            new_y = start.top()
        elif handle == 't':
            new_w = start.width()
            new_h = max(10, start.height() - dy)
            new_x = start.left()
            new_y = start.bottom() - new_h
        elif handle == 'b':
            new_w = start.width()
            new_h = max(10, start.height() + dy)
            new_x = start.left()
            new_y = start.top()
        else:
            return

        # 等比缩放
        if self._resize_keep_ratio and start.height() > 0:
            ratio = start.width() / start.height()
            # 依据主方向调整（取更大的改变量）
            if handle in ('l','r','tl','tr','bl','br'):
                new_h = max(10, int(new_w / ratio))
                # 修正锚点对应的 y
                if handle in ('tl','tr'):
                    new_y = start.bottom() - new_h
                elif handle in ('bl','br'):
                    new_y = start.top()
            else:
                new_w = max(10, int(new_h * ratio))
                if handle in ('t'):
                    new_x = start.left()
                elif handle in ('b'):
                    new_x = start.left()

        # 真正缩放像素并更新位置
        scaled = self._resize_start_pix.scaled(new_w, new_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        al['pix'] = scaled
        al['x'] = new_x
        al['y'] = new_y

    def resize_canvas(self, width: int, height: int):
        """调整画板尺寸，保留已有内容到新尺寸"""
        width = max(100, int(width))
        height = max(100, int(height))
        old_w, old_h = self.paint_layer.width(), self.paint_layer.height()
        new_paint = QPixmap(width, height)
        new_paint.fill(Qt.transparent)
        p = QPainter(new_paint)
        # 将旧绘制层按目标大小缩放填充，避免改变比例导致内容只占左上角
        try:
            scaled_paint = self.paint_layer.scaled(width, height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(0, 0, scaled_paint)
        except Exception:
            p.drawPixmap(0, 0, self.paint_layer)
        p.end()
        self.paint_layer = new_paint
        # 缩放每个图层以适配新尺寸（保持居中位置逻辑）
        for layer in self.layers:
            src_orig = layer.get('orig') or layer.get('pix')
            kind = layer.get('kind', 'image')
            if kind == 'blank':
                scaled = QPixmap(width, height)
                scaled.fill(Qt.transparent)
                layer['pix'] = scaled
                layer['x'] = 0
                layer['y'] = 0
            else:
                if src_orig.width() <= width and src_orig.height() <= height:
                    scaled = src_orig
                else:
                    scaled = src_orig.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                layer['pix'] = scaled
                layer['x'] = (width - scaled.width()) // 2
                layer['y'] = (height - scaled.height()) // 2
        # 根据缩放比例调整显示尺寸
        scaled_w = int(width * self._zoom_scale)
        scaled_h = int(height * self._zoom_scale)
        self.setFixedSize(scaled_w, scaled_h)
        self.update()
        
        # 发射尺寸改变信号
        try:
            self.size_changed.emit(width, height)
        except Exception:
            pass

    def add_image_layer(self, img: QPixmap | str, name: str | None = None) -> int | None:
        """添加图像为图层，缩放图片以适应画板尺寸。支持路径或 QPixmap。返回图层ID。"""
        # 添加图层前记录历史
        self._push_history()
        src = QPixmap(img) if isinstance(img, str) else img
        if src.isNull():
            return None
        
        img_w, img_h = src.width(), src.height()
        canvas_w, canvas_h = self.paint_layer.width(), self.paint_layer.height()
        
        try:
            print(f'[画板] 上传图片：{img_w}x{img_h}，画板尺寸：{canvas_w}x{canvas_h}', flush=True)
        except Exception:
            pass
        
        # 计算图片如何适应画板（保持宽高比，缩放到画板内）
        if img_w != canvas_w or img_h != canvas_h:
            # 计算缩放比例（保持宽高比，适应画板）
            scale_w = canvas_w / img_w if img_w > 0 else 1.0
            scale_h = canvas_h / img_h if img_h > 0 else 1.0
            scale = min(scale_w, scale_h)  # 取较小的比例，确保图片完全显示在画板内
            
            # 缩放图片
            new_w = int(img_w * scale)
            new_h = int(img_h * scale)
            scaled = src.scaled(new_w, new_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            # 居中放置
            x = (canvas_w - new_w) // 2
            y = (canvas_h - new_h) // 2
            
            try:
                print(f'[画板] 图片缩放至：{new_w}x{new_h}，位置：({x}, {y})', flush=True)
            except Exception:
                pass
        else:
            # 尺寸相同，不需要缩放
            scaled = src
            x = 0
            y = 0
        
        lid = self._layer_seq
        self._layer_seq += 1
        self.layers.append({'id': lid, 'pix': scaled, 'orig': src, 'x': x, 'y': y, 'enabled': True, 'name': name or self._i18n.get('layer', '图层'), 'kind': 'image', 'show_thumb': True})
        self.update()
        
        # 触发自适应缩放显示
        try:
            if hasattr(self, 'auto_fit_requested'):
                self.auto_fit_requested.emit()
        except Exception:
            pass
        
        return lid

    def add_image_layer_at(self, img: QPixmap, name: str | None, x: int, y: int, show_thumb: bool = True) -> int | None:
        src = img
        if src is None or src.isNull():
            return None
        lid = self._layer_seq
        self._layer_seq += 1
        self.layers.append({'id': lid, 'pix': src, 'orig': src, 'x': int(x), 'y': int(y), 'enabled': True, 'name': name or self._i18n.get('layer', '图层'), 'kind': 'image', 'show_thumb': bool(show_thumb)})
        self.update()
        return lid

    def add_blank_layer(self, name: str | None = None) -> int:
        # 添加空白层前记录历史
        self._push_history()
        w, h = self.paint_layer.width(), self.paint_layer.height()
        pix = QPixmap(w, h)
        pix.fill(Qt.transparent)
        lid = self._layer_seq
        self._layer_seq += 1
        self.layers.append({'id': lid, 'pix': pix, 'x': 0, 'y': 0, 'enabled': True, 'name': name or self._i18n.get('blank_layer', '空白层'), 'kind': 'blank'})
        # 默认将新建图层设为当前绘制目标
        self._active_layer_id = lid
        self.update()
        return lid

    def remove_layer(self, index: int):
        if 0 <= index < len(self.layers):
            self._push_history()
            del self.layers[index]
            self.update()

    def remove_layer_by_id(self, lid: int):
        for i, layer in enumerate(self.layers):
            if layer.get('id') == lid:
                self._push_history()
                del self.layers[i]
                self.update()
                return

    def set_layer_enabled(self, index: int, enabled: bool):
        if 0 <= index < len(self.layers):
            self._push_history()
            self.layers[index]['enabled'] = enabled
            self.update()

    def set_layer_enabled_by_id(self, lid: int, enabled: bool):
        for layer in self.layers:
            if layer.get('id') == lid:
                self._push_history()
                layer['enabled'] = enabled
                self.update()
                return

    def reorder_layers(self, new_order_indices: list[int]):
        if len(new_order_indices) != len(self.layers):
            return
        self._push_history()
        self.layers = [self.layers[i] for i in new_order_indices]
        self.update()

    def reorder_layers_by_ids(self, ids: list[int]):
        if len(ids) != len(self.layers):
            return
        self._push_history()
        id_to_layer = {layer.get('id'): layer for layer in self.layers}
        self.layers = [id_to_layer[i] for i in ids if i in id_to_layer]
        self.update()

    def set_active_layer_by_id(self, lid: int):
        """设置当前绘制图层为指定ID。"""
        for layer in self.layers:
            if layer.get('id') == lid:
                self._active_layer_id = lid
                return

    def _get_active_target(self):
        """返回(绘制目标pixmap, 目标偏移x, 目标偏移y)。选中图层则返回其pix与位置，否则返回paint_layer与(0,0)。"""
        if self._active_layer_id is not None:
            for layer in self.layers:
                if layer.get('id') == self._active_layer_id:
                    return layer['pix'], layer.get('x', 0), layer.get('y', 0)
        return self.paint_layer, 0, 0

    # ---------- 取样、填充与选择 ----------
    def _composite_to_image(self) -> 'QImage':
        from PySide6.QtGui import QImage
        w, h = self.paint_layer.width(), self.paint_layer.height()
        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.drawPixmap(0, 0, self.paint_layer)
        for layer in self.layers:
            if layer.get('enabled', True):
                p.drawPixmap(layer.get('x', 0), layer.get('y', 0), layer['pix'])
        p.end()
        return img

    def _sample_color(self, pos: QPoint) -> QColor | None:
        from PySide6.QtGui import QImage
        img = self._composite_to_image()
        x, y = pos.x(), pos.y()
        if 0 <= x < img.width() and 0 <= y < img.height():
            c = QColor(img.pixel(x, y))
            return c
        return None

    def _bucket_fill(self, pos: QPoint, tolerance: int = 20):
        target_pix, offx, offy = self._get_active_target()
        if target_pix is self.paint_layer:
            # 没有选择图层则直接在绘制层上填充
            offx = 0
            offy = 0
        x, y = pos.x() - offx, pos.y() - offy
        if x < 0 or y < 0 or x >= target_pix.width() or y >= target_pix.height():
            return
        from PySide6.QtGui import QImage
        img = target_pix.toImage().convertToFormat(QImage.Format_ARGB32)
        seed = QColor(img.pixel(x, y))
        new = self.brush_color
        if seed == new:
            return
        w, h = img.width(), img.height()
        visited = [[False]*w for _ in range(h)]
        def similar(c1: QColor, c2: QColor) -> bool:
            return (abs(c1.red() - c2.red()) <= tolerance and
                    abs(c1.green() - c2.green()) <= tolerance and
                    abs(c1.blue() - c2.blue()) <= tolerance and
                    abs(c1.alpha() - c2.alpha()) <= tolerance)
        from collections import deque
        q = deque()
        q.append((x, y))
        visited[y][x] = True
        new_rgba = new.rgba()
        while q:
            cx, cy = q.popleft()
            img.setPixel(cx, cy, new_rgba)
            for nx, ny in ((cx-1, cy), (cx+1, cy), (cx, cy-1), (cx, cy+1)):
                if 0 <= nx < w and 0 <= ny < h and not visited[ny][nx]:
                    if similar(QColor(img.pixel(nx, ny)), seed):
                        visited[ny][nx] = True
                        q.append((nx, ny))
        target_pix.convertFromImage(img)

    def _wand_select(self, pos: QPoint, tolerance: int = 20):
        from PySide6.QtGui import QImage
        img = self._composite_to_image()
        x, y = pos.x(), pos.y()
        if x < 0 or y < 0 or x >= img.width() or y >= img.height():
            return
        seed = QColor(img.pixel(x, y))
        w, h = img.width(), img.height()
        visited = [[False]*w for _ in range(h)]
        from collections import deque
        def similar(c1: QColor, c2: QColor) -> bool:
            return (abs(c1.red() - c2.red()) <= tolerance and
                    abs(c1.green() - c2.green()) <= tolerance and
                    abs(c1.blue() - c2.blue()) <= tolerance and
                    abs(c1.alpha() - c2.alpha()) <= tolerance)
        q = deque()
        q.append((x, y))
        visited[y][x] = True
        minx = maxx = x
        miny = maxy = y
        while q:
            cx, cy = q.popleft()
            minx = min(minx, cx); maxx = max(maxx, cx)
            miny = min(miny, cy); maxy = max(maxy, cy)
            for nx, ny in ((cx-1, cy), (cx+1, cy), (cx, cy-1), (cx, cy+1)):
                if 0 <= nx < w and 0 <= ny < h and not visited[ny][nx]:
                    if similar(QColor(img.pixel(nx, ny)), seed):
                        visited[ny][nx] = True
                        q.append((nx, ny))
        # 只记录边界矩形作为可视反馈（快速实现）
        self.selection_rect = QRect(minx, miny, maxx - minx + 1, maxy - miny + 1)

    def _auto_select(self, pos: QPoint):
        """
        自动选区工具：使用 BiRefNet AI 模型识别整张图，然后通过洪水填充提取点击位置的单个对象
        点击切换选区状态：第一次点击显示绿色半透明，再次点击清除选区
        
        Args:
            pos: 用户点击的位置
        """
        try:
            from PySide6.QtGui import QImage
            from PySide6.QtWidgets import QMessageBox, QApplication
            
            # 如果已经有选区，点击任意位置清除选区
            if self.selection_mask is not None:
                self.selection_mask = None
                self.selection_rect = None
                self.update()
                return
            
            # 显示处理提示
            QApplication.setOverrideCursor(Qt.WaitCursor)
            
            # 获取画板合成图
            img = self._composite_to_image()
            composite_pixmap = QPixmap.fromImage(img)
            
            # 转换为 PIL Image 供 BiRefNet 使用
            try:
                from PIL import Image
                import io
                
                # QPixmap -> QImage -> bytes -> PIL.Image
                qimg = composite_pixmap.toImage().convertToFormat(QImage.Format_RGB888)
                buffer = qimg.bits().tobytes()
                pil_img = Image.frombytes('RGB', (qimg.width(), qimg.height()), buffer)
                
            except Exception as e:
                QApplication.restoreOverrideCursor()
                QMessageBox.warning(self, '格式转换失败', f'无法转换图像格式：{e}')
                return
            
            # 调用 BiRefNet 模型获取遮罩
            try:
                self._debug('[自动选区] 调用 BiRefNet 模型识别人物...')
                from tools.birefnet_runner import remove_bg_birefnet
                
                # 获取抠图结果（带 alpha 通道）
                result_pil = remove_bg_birefnet(pil_img)
                
                if result_pil is None:
                    QApplication.restoreOverrideCursor()
                    QMessageBox.warning(self, '识别失败', 'BiRefNet 模型处理失败')
                    return
                
                self._debug('[自动选区] BiRefNet 处理完成')
                
            except ImportError as e:
                QApplication.restoreOverrideCursor()
                QMessageBox.warning(
                    self,
                    '模型缺失',
                    f'无法导入 BiRefNet 模块，自动选区功能不可用。\n\n'
                    f'错误：{e}\n\n'
                    f'请确保已安装必要的依赖：\n'
                    f'- torch\n'
                    f'- torchvision\n'
                    f'- PIL\n'
                    f'- transformers'
                )
                return
            except Exception as e:
                QApplication.restoreOverrideCursor()
                QMessageBox.warning(self, '处理失败', f'BiRefNet 处理失败：{e}')
                return
            
            # 将 PIL Image 的 alpha 通道转换为遮罩
            try:
                import numpy as np
                from collections import deque
                
                # 获取 alpha 通道
                if result_pil.mode == 'RGBA':
                    alpha_channel = np.array(result_pil.split()[3])
                else:
                    # 如果没有 alpha 通道，转换为灰度图
                    alpha_channel = np.array(result_pil.convert('L'))
                
                w, h = result_pil.size
                x, y = pos.x(), pos.y()
                
                # 检查点击位置是否在画板范围内
                if x < 0 or y < 0 or x >= w or y >= h:
                    QApplication.restoreOverrideCursor()
                    QMessageBox.information(self, '点击位置无效', '请点击画板内的人物或物体')
                    return
                
                # 检查点击位置是否在前景区域（alpha > 30）
                if alpha_channel[y, x] <= 30:
                    QApplication.restoreOverrideCursor()
                    QMessageBox.information(self, '未检测到对象', '点击位置没有识别到物体，请点击人物或物体的主体部分')
                    return
                
                self._debug(f'[自动选区] 点击位置: ({x}, {y}), alpha值: {alpha_channel[y, x]}')
                
                # 从点击位置开始洪水填充，提取连续的前景区域
                mask = [[False] * w for _ in range(h)]
                visited = [[False] * w for _ in range(h)]
                
                queue = deque()
                queue.append((x, y))
                visited[y][x] = True
                mask[y][x] = True
                
                minx, miny = x, y
                maxx, maxy = x, y
                pixel_count = 0
                
                # 洪水填充算法（四向扩散）
                while queue:
                    cx, cy = queue.popleft()
                    pixel_count += 1
                    
                    # 更新边界
                    minx = min(minx, cx)
                    maxx = max(maxx, cx)
                    miny = min(miny, cy)
                    maxy = max(maxy, cy)
                    
                    # 检查四个方向
                    for nx, ny in [(cx-1, cy), (cx+1, cy), (cx, cy-1), (cx, cy+1)]:
                        if 0 <= nx < w and 0 <= ny < h and not visited[ny][nx]:
                            visited[ny][nx] = True
                            # 如果邻居像素也在前景区域，加入队列
                            if alpha_channel[ny, nx] > 30:
                                queue.append((nx, ny))
                                mask[ny][nx] = True
                
                QApplication.restoreOverrideCursor()
                
                # 检查是否选中了有效区域
                if pixel_count < 10:
                    QMessageBox.information(
                        self,
                        '选区太小',
                        f'识别到的区域太小（{pixel_count}像素），可能未正确选中物体'
                    )
                    self.selection_mask = None
                    self.selection_rect = None
                    return
                
                # 保存遮罩用于绘制
                self.selection_mask = mask
                
                # 同时设置选区矩形用于右键菜单判断
                self.selection_rect = QRect(minx, miny, maxx - minx + 1, maxy - miny + 1)
                
                self._debug(f'[自动选区] 识别成功，选中 {pixel_count} 个像素，范围: ({minx},{miny}) -> ({maxx},{maxy})')
                    
            except Exception as e:
                QApplication.restoreOverrideCursor()
                QMessageBox.warning(self, '遮罩处理失败', f'处理遮罩时出错：{e}')
                self.selection_mask = None
                self.selection_rect = None
                
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, '自动选区失败', f'处理失败：{str(e)}')
            self.selection_mask = None
            self.selection_rect = None
    
    def _debug(self, msg: str):
        """调试输出（如果需要）"""
        print(f'[DEBUG] {msg}', flush=True)

    # ---------- 合并与撤销 ----------
    def merge_layers_by_ids(self, ids: list[int]) -> tuple[int, QPixmap] | None:
        if not ids or len(ids) < 2:
            return None
        # 记录历史以支持撤销
        self._push_history()
        w, h = self.paint_layer.width(), self.paint_layer.height()
        out = QPixmap(w, h)
        out.fill(Qt.transparent)
        painter = QPainter(out)
        # 保持原叠放顺序，按 self.layers 顺序合成被选中的层
        order_ids = [layer.get('id') for layer in self.layers if layer.get('id') in ids]
        for layer in self.layers:
            lid = layer.get('id')
            if lid in order_ids:
                painter.drawPixmap(layer.get('x', 0), layer.get('y', 0), layer['pix'])
        painter.end()
        # 插入位置取所选图层中最靠上的索引（视觉最底）
        indices = [i for i, l in enumerate(self.layers) if l.get('id') in ids]
        insert_at = min(indices) if indices else len(self.layers)
        # 删除原图层
        self.layers = [l for l in self.layers if l.get('id') not in ids]
        # 新建合并层
        new_lid = self._layer_seq
        self._layer_seq += 1
        merged = {'id': new_lid, 'pix': out, 'x': 0, 'y': 0, 'enabled': True, 'name': self._i18n.get('merged_layer', '合并层'), 'kind': 'image'}
        self.layers.insert(insert_at, merged)
        self._active_layer_id = new_lid
        self.update()
        return new_lid, out

    def _snapshot(self) -> dict:
        # 深拷贝当前状态
        snap_layers = []
        for l in self.layers:
            snap_layers.append({
                'id': l.get('id'),
                'pix': l['pix'].copy(),
                'x': l.get('x', 0),
                'y': l.get('y', 0),
                'enabled': l.get('enabled', True),
                'name': l.get('name'),
                'kind': l.get('kind', 'image')
            })
        return {
            'paint': self.paint_layer.copy(),
            'layers': snap_layers,
            'active': self._active_layer_id,
        }

    def _push_history(self):
        try:
            snap = self._snapshot()
            self._history.append(snap)
            if len(self._history) > self._history_limit:
                self._history.pop(0)
        except Exception:
            pass

    def undo(self):
        if not self._history:
            return
        state = self._history.pop()
        try:
            self.paint_layer = state.get('paint').copy()
            self.layers = []
            for l in state.get('layers', []):
                self.layers.append({
                    'id': l.get('id'),
                    'pix': l['pix'].copy(),
                    'x': l.get('x', 0),
                    'y': l.get('y', 0),
                    'enabled': l.get('enabled', True),
                    'name': l.get('name'),
                    'kind': l.get('kind', 'image')
                })
            self._active_layer_id = state.get('active')
            self.update()
        except Exception:
            pass

    def keyPressEvent(self, event):
        # Ctrl+Z 撤销
        if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_Z:
            self.undo()
            event.accept()
            return
        super().keyPressEvent(event)

    def render_to_pixmap(self) -> QPixmap:
        """合成当前画板与所有启用图层为单个 QPixmap，用于导出/桥接。"""
        w, h = self.paint_layer.width(), self.paint_layer.height()
        out = QPixmap(w, h)
        # 导出使用透明背景，满足"画板是透明图层"的要求
        out.fill(Qt.transparent)
        p = QPainter(out)
        # 将绘制层也叠加到导出结果（若当前绘制直接输出到图层，该层仍参与叠加）
        p.drawPixmap(0, 0, self.paint_layer)
        for layer in self.layers:
            if layer.get('enabled', True):
                p.drawPixmap(layer.get('x', 0), layer.get('y', 0), layer['pix'])
        p.end()
        return out

    # —— 选中图层导出/更新接口 ——
    def get_active_layer_id(self) -> int | None:
        """返回当前选中图层ID；若无选中则返回None。"""
        return self._active_layer_id

    def get_active_layer_pixmap(self) -> QPixmap | None:
        """返回当前选中图层的像素内容副本；若无选中则返回None。"""
        if self._active_layer_id is None:
            return None
        for layer in self.layers:
            if layer.get('id') == self._active_layer_id:
                return layer['pix'].copy()
        return None

    def update_layer_pixmap_by_id(self, lid: int, new_pix: QPixmap) -> bool:
        """用新的像素内容替换指定ID图层，返回是否成功。"""
        if new_pix is None or new_pix.isNull():
            return False
        for layer in self.layers:
            if layer.get('id') == lid:
                try:
                    self._push_history()
                except Exception:
                    pass
                layer['pix'] = new_pix.copy()
                self.update()
                return True
        return False

    def _show_auto_select_menu(self, pos):
        """自动选区工具的右键菜单"""
        menu = QMenu(self)
        
        # 检查当前是否已启用智能区域修改模式
        region_edit_mode = getattr(self.canvas, '_smart_region_edit_mode', False)
        
        if region_edit_mode:
            act_disable = menu.addAction('✓ 智能区域修改（已启用）')
            act_disable.triggered.connect(self._disable_smart_region_edit)
        else:
            act_enable = menu.addAction('启用智能区域修改')
            act_enable.triggered.connect(self._enable_smart_region_edit)
        
        menu.exec(self.btn_auto_select.mapToGlobal(pos))
    
    def _enable_smart_region_edit(self):
        """启用智能区域修改模式"""
        try:
            # 设置画板为智能区域修改模式
            self.canvas._smart_region_edit_mode = True
            
            # 自动切换到矩形框选工具
            self.btn_rect.setChecked(True)
            # 取消其他按钮
            for btn in [self.btn_brush, self.btn_eraser, self.btn_move, self.btn_wand, 
                       self.btn_auto_select, self.btn_bucket, self.btn_dropper]:
                btn.setChecked(False)
            
            # 设置画板工具为矩形框选
            self.canvas.set_tool('rect_select')
            
            # 显示提示
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                '智能区域修改已启用',
                '现在可以使用矩形框选工具选择区域，右键选区选择"智能区域修改"进行修改。\n\n要退出此模式，请再次右键自动选区工具。'
            )
            
        except Exception as e:
            print(f'启用智能区域修改失败: {e}')
    
    def _disable_smart_region_edit(self):
        """禁用智能区域修改模式"""
        try:
            self.canvas._smart_region_edit_mode = False
            
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, '已退出', '智能区域修改模式已关闭')
            
        except Exception as e:
            print(f'禁用智能区域修改失败: {e}')

    def set_language(self, code: str):
        """设置语言代码（'zh' 或 'en'），仅影响默认图层名称等。"""
        if code not in ('zh', 'en'):
            code = 'zh'
        self._lang_code = code
        self._i18n = self._get_i18n(code)

    def _flip_active_layer(self, horizontal: bool = True):
        """翻转当前激活的图层
        
        Args:
            horizontal: True为水平翻转，False为垂直翻转
        """
        if self._active_layer_id is None:
            return
        
        al = self._get_active_layer()
        if al is None:
            return
        
        # 记录历史以支持撤销
        self._push_history()
        
        # 获取原始pixmap
        original_pix = al['pix']
        
        # 创建变换后的pixmap
        from PySide6.QtGui import QTransform
        transform = QTransform()
        if horizontal:
            # 水平翻转：沿垂直轴镜像
            transform.scale(-1, 1)
        else:
            # 垂直翻转：沿水平轴镜像
            transform.scale(1, -1)
        
        # 应用变换
        flipped_pix = original_pix.transformed(transform, Qt.SmoothTransformation)
        
        # 更新图层的pixmap
        al['pix'] = flipped_pix
        
        # 刷新显示
        self.update()

    def set_zoom_scale(self, scale: float):
        """设置缩放比例（用于显示缩放）"""
        self._zoom_scale = max(0.1, min(2.0, scale))
        # 根据缩放比例调整widget的显示尺寸
        base_w = self.paint_layer.width()
        base_h = self.paint_layer.height()
        new_w = int(base_w * self._zoom_scale)
        new_h = int(base_h * self._zoom_scale)
        self.setFixedSize(new_w, new_h)
        self.update()

    def get_zoom_scale(self) -> float:
        """获取当前缩放比例"""
        return self._zoom_scale

    def _scale_pos(self, pos: QPoint) -> QPoint:
        """将屏幕坐标转换为画板内部坐标（考虑缩放）"""
        if self._zoom_scale == 1.0:
            return pos
        x = int(pos.x() / self._zoom_scale)
        y = int(pos.y() / self._zoom_scale)
        return QPoint(x, y)

    def _get_i18n(self, code: str) -> dict:
        zh = {
            'layer': '图层',
            'blank_layer': '空白层',
            'merged_layer': '合并层',
        }
        en = {
            'layer': 'Layer',
            'blank_layer': 'Blank Layer',
            'merged_layer': 'Merged Layer',
        }
        return zh if code == 'zh' else en


class Toolbar(QWidget):
    """左侧蓝色工具栏，包含画笔、橡皮擦、移动、矩形、魔棒、修复、油漆桶等工具，每行2个。"""
    def __init__(self, canvas: HuabanCanvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.setFixedWidth(120)
        self.setObjectName('BlueBar')
        self.setAttribute(Qt.WA_StyledBackground, True)  # Ensure background color is painted
        self.setStyleSheet("background: #f5f5f7; border-right: 1px solid #e0e0e0;")
        self._lang_code = 'zh'
        self._i18n = self._get_i18n(self._lang_code)

        # 使用垂直布局作为主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 8)
        main_layout.setSpacing(8)

        # 顶部：工具按钮区域
        tool_widget = QWidget()
        grid = QGridLayout(tool_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)

        self.title = QLabel('工具栏')
        self.title.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        grid.addWidget(self.title, 0, 0, 1, 2)

        # 使用代码生成位图图标的按钮（不依赖外部资源）
        self.btn_brush = PaintIconButton('brush', '画笔')
        self.btn_eraser = PaintIconButton('eraser', '橡皮擦')
        self.btn_move = PaintIconButton('move', '移动')
        self.btn_rect = PaintIconButton('rect', '矩形框选')
        self.btn_wand = PaintIconButton('wand', '魔术棒')
        self.btn_auto_select = PaintIconButton('auto_select', '自动选区')
        self.btn_bucket = PaintIconButton('bucket', '油漆桶')
        self.btn_dropper = PaintIconButton('eyedropper', '吸管')

        for b in (self.btn_brush, self.btn_eraser, self.btn_move, self.btn_rect, self.btn_wand, self.btn_auto_select, self.btn_bucket, self.btn_dropper):
            b.setCheckable(True)

        buttons = [self.btn_brush, self.btn_eraser, self.btn_move, self.btn_rect, self.btn_wand, self.btn_auto_select, self.btn_bucket, self.btn_dropper]

        def select_tool(kind: str, btn: QPushButton):
            # 互斥勾选
            for b in buttons:
                if b is not btn:
                    b.setChecked(False)
            if btn.isChecked():
                self.canvas.set_tool({'brush':'brush','eraser':'eraser','move':'move','rect':'rect_select','wand':'magic_wand','auto':'auto_select','bucket':'bucket','dropper':'eyedropper'}[kind])
            else:
                self.canvas.set_tool('none')

        self.btn_brush.clicked.connect(lambda: select_tool('brush', self.btn_brush))
        self.btn_eraser.clicked.connect(lambda: select_tool('eraser', self.btn_eraser))
        self.btn_move.clicked.connect(lambda: select_tool('move', self.btn_move))
        self.btn_rect.clicked.connect(lambda: select_tool('rect', self.btn_rect))
        self.btn_wand.clicked.connect(lambda: select_tool('wand', self.btn_wand))
        self.btn_auto_select.clicked.connect(lambda: select_tool('auto', self.btn_auto_select))
        # 自动选区按钮添加右键菜单
        self.btn_auto_select.setContextMenuPolicy(Qt.CustomContextMenu)
        self.btn_auto_select.customContextMenuRequested.connect(self._show_auto_select_menu)
        
        self.btn_bucket.clicked.connect(lambda: select_tool('bucket', self.btn_bucket))
        self.btn_dropper.clicked.connect(lambda: select_tool('dropper', self.btn_dropper))

        # 每行两个
        grid.addWidget(self.btn_brush, 1, 0)
        grid.addWidget(self.btn_eraser, 1, 1)
        grid.addWidget(self.btn_move, 2, 0)
        grid.addWidget(self.btn_rect, 2, 1)
        grid.addWidget(self.btn_wand, 3, 0)
        grid.addWidget(self.btn_auto_select, 3, 1)
        grid.addWidget(self.btn_bucket, 4, 0)
        grid.addWidget(self.btn_dropper, 4, 1)
        
        # 将工具按钮区域添加到主布局
        main_layout.addWidget(tool_widget, stretch=0)

        # 中间分隔符
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background: #e0e0e0; min-height: 1px; max-height: 1px;")
        main_layout.addWidget(separator)

        # 底部：画板尺寸调整区域
        size_widget = QWidget()
        size_widget.setObjectName('SizePanel')
        size_layout = QVBoxLayout(size_widget)
        size_layout.setContentsMargins(8, 8, 8, 8)
        size_layout.setSpacing(6)

        # 标题
        size_title = QLabel(self._i18n['canvas_size'])
        size_title.setAlignment(Qt.AlignLeft)
        size_title.setStyleSheet("color: #333333; font-weight: bold;")
        size_layout.addWidget(size_title)

        # 当前尺寸显示
        self.size_display = QLabel('1200 × 800')
        self.size_display.setAlignment(Qt.AlignCenter)
        self.size_display.setStyleSheet("""
            color: #333333; 
            background: #ffffff; 
            padding: 8px; 
            border: 1px solid #d1d1d6;
            border-radius: 4px;
            font-size: 13px;
        """)
        size_layout.addWidget(self.size_display)

        # 宽度输入
        width_row = QHBoxLayout()
        width_row.setSpacing(4)
        width_label = QLabel(self._i18n['width'] + ':')
        width_label.setStyleSheet("color: #333333; font-size: 11px;")
        width_label.setFixedWidth(25)
        from PySide6.QtWidgets import QLineEdit
        self.width_input = QLineEdit('1200')
        self.width_input.setFixedHeight(24)
        self.width_input.setStyleSheet("""
            QLineEdit {
                background: #ffffff; 
                color: #333333; 
                border: 1px solid #d1d1d6; 
                border-radius: 4px;
                padding: 2px 4px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 1px solid #34c759;
            }
        """)
        width_row.addWidget(width_label)
        width_row.addWidget(self.width_input)
        size_layout.addLayout(width_row)

        # 高度输入
        height_row = QHBoxLayout()
        height_row.setSpacing(4)
        height_label = QLabel(self._i18n['height'] + ':')
        height_label.setStyleSheet("color: #333333; font-size: 11px;")
        height_label.setFixedWidth(25)
        self.height_input = QLineEdit('800')
        self.height_input.setFixedHeight(24)
        self.height_input.setStyleSheet("""
            QLineEdit {
                background: #ffffff; 
                color: #333333; 
                border: 1px solid #d1d1d6; 
                border-radius: 4px;
                padding: 2px 4px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 1px solid #34c759;
            }
        """)
        height_row.addWidget(height_label)
        height_row.addWidget(self.height_input)
        size_layout.addLayout(height_row)

        # 应用按钮
        self.btn_apply_size = QPushButton(self._i18n['apply'])
        self.btn_apply_size.setFixedHeight(26)
        self.btn_apply_size.setStyleSheet("""
            QPushButton {
                background: #ffffff; 
                color: #333333; 
                border: 1px solid #d1d1d6; 
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #f2f2f7;
                border: 1px solid #34c759;
            }
            QPushButton:pressed {
                background: rgba(52, 199, 89, 0.2);
            }
        """)
        self.btn_apply_size.clicked.connect(self._apply_canvas_size)
        size_layout.addWidget(self.btn_apply_size)

        # 分隔线
        zoom_separator = QFrame()
        zoom_separator.setFrameShape(QFrame.HLine)
        zoom_separator.setStyleSheet("background: #e0e0e0; min-height: 1px; max-height: 1px;")
        size_layout.addWidget(zoom_separator)

        # 缩放比例标题
        zoom_title = QLabel(self._i18n.get('zoom', '缩放比例'))
        zoom_title.setAlignment(Qt.AlignLeft)
        zoom_title.setStyleSheet("color: #333333; font-weight: bold;")
        size_layout.addWidget(zoom_title)

        # 当前缩放比例显示（支持双击编辑）
        self.zoom_display = DoubleClickLabel('100%')
        self.zoom_display.setAlignment(Qt.AlignCenter)
        self.zoom_display.setStyleSheet("""
            color: #333333; 
            background: #ffffff; 
            padding: 8px; 
            border: 1px solid #d1d1d6;
            border-radius: 4px;
            font-size: 13px;
        """)
        self.zoom_display.setToolTip('双击可输入缩放比例')
        self.zoom_display.double_clicked.connect(self._on_zoom_display_double_clicked)
        size_layout.addWidget(self.zoom_display)

        # 缩放滑块
        from PySide6.QtWidgets import QSlider
        zoom_slider_row = QHBoxLayout()
        zoom_slider_row.setSpacing(4)
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(10, 200)  # 10% - 200%
        self.zoom_slider.setValue(100)
        self.zoom_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #d1d1d6;
                height: 6px;
                background: #e5e5ea;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                border: 1px solid #d1d1d6;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #34c759;
                border-color: #34c759;
            }
        """)
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        zoom_slider_row.addWidget(self.zoom_slider)
        size_layout.addLayout(zoom_slider_row)

        # 自适应按钮（全宽显示）
        btn_fit = QPushButton(self._i18n.get('fit', '自适应'))
        btn_fit.setFixedHeight(28)
        btn_fit.setStyleSheet("""
            QPushButton {
                background: #ffffff; 
                color: #333333; 
                border: 1px solid #d1d1d6; 
                border-radius: 4px;
                font-size: 11px;
                padding: 4px;
            }
            QPushButton:hover {
                background: #f2f2f7;
                border: 1px solid #34c759;
            }
            QPushButton:pressed {
                background: rgba(52, 199, 89, 0.2);
            }
        """)
        btn_fit.clicked.connect(self._fit_zoom)
        size_layout.addWidget(btn_fit)
        
        # 3D按钮（新增）
        btn_3d = QPushButton('3D')
        btn_3d.setFixedHeight(36)
        btn_3d.setStyleSheet("""
            QPushButton {
                background: #ffffff; 
                color: #333333; 
                border: 1px solid #d1d1d6; 
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
                padding: 6px;
            }
            QPushButton:hover {
                background: #f2f2f7;
                border: 1px solid #34c759;
                color: #34c759;
            }
            QPushButton:pressed {
                background: rgba(52, 199, 89, 0.2);
            }
        """)
        btn_3d.setToolTip('打开3D工作空间 (类似Blender)')
        btn_3d.clicked.connect(self._open_3d_workspace)
        size_layout.addWidget(btn_3d)
        
        # 动作库按钮（新增）
        btn_pose_library = QPushButton('动作库')
        btn_pose_library.setFixedHeight(36)
        btn_pose_library.setStyleSheet("""
            QPushButton {
                background: #ffffff; 
                color: #333333; 
                border: 1px solid #d1d1d6; 
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
                padding: 6px;
            }
            QPushButton:hover {
                background: #f2f2f7;
                border: 1px solid #34c759;
                color: #34c759;
            }
            QPushButton:pressed {
                background: rgba(52, 199, 89, 0.2);
            }
        """)
        btn_pose_library.setToolTip('打开动作库管理窗口\n管理动作参考图片')
        btn_pose_library.clicked.connect(self._open_pose_library)
        size_layout.addWidget(btn_pose_library)

        # 添加尺寸调整区域到主布局
        main_layout.addWidget(size_widget, stretch=0)
        
        # 底部弹性空间
        main_layout.addStretch(1)

        self.setStyleSheet(
            """
            #BlueBar { background: #f0f2f5; color: #333333; border-right: 1px solid #e0e0e0; }
            QPushButton { background: #ffffff; border: 1px solid #d1d1d6; border-radius: 6px; padding: 6px; }
            QPushButton:hover { background: #f2f2f7; border-color: #b0b0b5; }
            /* 选中态：绿色系 */
            QPushButton:checked { background: rgba(52, 199, 89, 0.2); border-color: #34c759; color: #000000; }
            QPushButton:checked:hover { background: rgba(52, 199, 89, 0.3); }
            QLabel { color: #333333; }
            """
        )

        # 初始关闭工具
        for b in (self.btn_brush, self.btn_eraser, self.btn_move, self.btn_rect, self.btn_wand, self.btn_bucket, self.btn_dropper):
            b.setChecked(False)
        self.canvas.set_tool('none')
        
        # 连接画板尺寸改变信号
        self.canvas.size_changed.connect(self._on_canvas_size_changed)
        
        # 连接自适应缩放请求信号
        self.canvas.auto_fit_requested.connect(self._fit_zoom)
        
        # 更新画板尺寸显示
        self._update_size_display()

    def _on_canvas_size_changed(self, width: int, height: int):
        """画板尺寸改变时更新显示"""
        self._update_size_display()

    def _on_zoom_changed(self, value: int):
        """缩放滑块改变时更新显示和画板缩放"""
        self.zoom_display.setText(f'{value}%')
        self._apply_zoom(value)

    def _on_zoom_display_double_clicked(self):
        """双击缩放显示区域，弹出输入框"""
        try:
            # 获取当前缩放比例
            current_zoom = self.zoom_slider.value()
            
            # 弹出输入对话框
            zoom_value, ok = QInputDialog.getInt(
                self,
                self._i18n.get('zoom_input_title', '输入缩放比例'),
                self._i18n.get('zoom_input_label', '缩放比例 (10-200):'),
                current_zoom,  # 当前值
                10,  # 最小值
                200,  # 最大值
                1  # 步进
            )
            
            # 如果用户点击确定，应用新的缩放比例
            if ok:
                self.zoom_slider.setValue(zoom_value)
                print(f'[画板] 用户输入缩放比例: {zoom_value}%', flush=True)
                
        except Exception as e:
            print(f'[画板] 输入缩放比例失败: {e}', flush=True)

    def _set_zoom(self, zoom_percent: int):
        """设置指定的缩放比例"""
        self.zoom_slider.setValue(zoom_percent)

    def _apply_zoom(self, zoom_percent: int):
        """应用缩放到画板"""
        try:
            scale = zoom_percent / 100.0
            self.canvas.set_zoom_scale(scale)
            print(f'[画板] 缩放比例: {zoom_percent}%', flush=True)
        except Exception as e:
            print(f'[画板] 应用缩放失败: {e}', flush=True)

    def _fit_zoom(self):
        """自适应缩放：根据画板尺寸自动计算合适的缩放比例，使画板完整显示在可视区域"""
        try:
            # 获取画板的实际尺寸（像素）
            canvas_w = self.canvas.paint_layer.width()
            canvas_h = self.canvas.paint_layer.height()
            
            # 获取可用的显示区域尺寸
            parent = self.canvas.parent()
            if parent:
                # 预留边距
                margin = 60
                available_w = parent.width() - margin
                available_h = parent.height() - margin
                
                # 计算需要的缩放比例（取宽高中较小的比例，确保完全显示）
                scale_w = available_w / canvas_w if canvas_w > 0 else 1.0
                scale_h = available_h / canvas_h if canvas_h > 0 else 1.0
                scale = min(scale_w, scale_h, 2.0)  # 最大200%
                
                # 转换为百分比并应用
                zoom_percent = max(10, min(200, int(scale * 100)))
                self.zoom_slider.setValue(zoom_percent)
                
                print(f'[画板] 自适应缩放: 画板{canvas_w}x{canvas_h} -> {zoom_percent}% (显示区域: {available_w}x{available_h})', flush=True)
            else:
                # 如果没有父容器，默认100%
                self.zoom_slider.setValue(100)
                print(f'[画板] 自适应缩放: 未找到父容器，使用100%', flush=True)
        except Exception as e:
            print(f'[画板] 自适应缩放失败: {e}', flush=True)
    
    def _open_3d_workspace(self):
        """打开3D工作空间"""
        try:
            # 导入3D模块
            import importlib.util
            import os
            
            # 获取3D.py的路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            module_path = os.path.join(current_dir, '3D.py')
            
            if not os.path.exists(module_path):
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, '错误', '3D.py 文件不存在！\n请确保3D.py在当前目录下。')
                return
            
            # 动态加载3D模块
            spec = importlib.util.spec_from_file_location("ThreeD", module_path)
            three_d_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(three_d_module)
            
            # 获取主窗口尺寸
            main_window = self.window()
            if main_window:
                window_size = main_window.size()
                window_pos = main_window.pos()
            else:
                window_size = None
                window_pos = None
            
            # 创建并显示3D窗口
            self.window_3d = three_d_module.ThreeDWindow(self)
            
            # 获取 PhotoPage 实例（Toolbar 的父窗口）
            photo_page = self.parent()
            if photo_page is not None:
                self.window_3d.photo_page = photo_page
                print(f'[画板] PhotoPage已设置到3D窗口: {type(photo_page).__name__}', flush=True)
            else:
                print('[画板] 警告: 无法获取PhotoPage实例', flush=True)
            
            # 设置与主窗口相同的尺寸和位置
            if window_size:
                self.window_3d.resize(window_size)
            if window_pos:
                self.window_3d.move(window_pos)
            
            self.window_3d.show()
            
            print(f'[画板] 3D工作空间已打开，尺寸: {window_size}', flush=True)
            
        except Exception as e:
            print(f'[画板] 打开3D工作空间失败: {e}', flush=True)
            import traceback
            traceback.print_exc()
            
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, '错误', f'无法打开3D工作空间：\n{str(e)}')
    
    def _open_pose_library(self):
        """打开动作库管理窗口"""
        try:
            # 导入动作库模块
            from dongzuoku import PoseLibraryWindow
            
            # 获取 PhotoPage 实例（Toolbar 的父窗口）
            photo_page = self.parent()
            if photo_page is None:
                print('[画板] 错误: 无法获取PhotoPage实例', flush=True)
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, '错误', '无法获取画板页面实例！')
                return
            
            print(f'[画板] 获取到PhotoPage: {type(photo_page).__name__}', flush=True)
            
            # 创建并显示动作库窗口，传递 PhotoPage 作为父窗口
            if not hasattr(self, 'pose_library_window') or self.pose_library_window is None:
                self.pose_library_window = PoseLibraryWindow(photo_page)
            
            self.pose_library_window.show()
            self.pose_library_window.raise_()
            self.pose_library_window.activateWindow()
            
            print('[画板] 动作库窗口已打开', flush=True)
            
        except Exception as e:
            print(f'[画板] 打开动作库失败: {e}', flush=True)
            import traceback
            traceback.print_exc()
            
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, '错误', f'无法打开动作库：\n{str(e)}')
                
        except Exception as e:
            print(f'[画板] 自适应缩放失败: {e}', flush=True)

    def _apply_canvas_size(self):
        """应用用户输入的画板尺寸"""
        try:
            width = int(self.width_input.text())
            height = int(self.height_input.text())
            
            # 验证尺寸范围
            if width < 100 or width > 8192:
                print(f'[画板] 宽度超出范围 (100-8192): {width}', flush=True)
                return
            if height < 100 or height > 8192:
                print(f'[画板] 高度超出范围 (100-8192): {height}', flush=True)
                return
            
            # 调整画板尺寸
            print(f'[画板] 用户调整尺寸: {width}x{height}', flush=True)
            self.canvas.resize_canvas(width, height)
            
            # 更新显示
            self._update_size_display()
            
        except ValueError:
            print('[画板] 尺寸格式错误，请输入数字', flush=True)
        except Exception as e:
            print(f'[画板] 调整尺寸失败: {e}', flush=True)

    def _update_size_display(self):
        """更新画板尺寸显示"""
        try:
            w = self.canvas.paint_layer.width()
            h = self.canvas.paint_layer.height()
            self.size_display.setText(f'{w} × {h}')
            self.width_input.setText(str(w))
            self.height_input.setText(str(h))
        except Exception:
            pass

    def _show_auto_select_menu(self, pos):
        """自动选区工具的右键菜单"""
        menu = QMenu(self)
        
        # 检查当前是否已启用智能区域修改模式
        region_edit_mode = getattr(self.canvas, '_smart_region_edit_mode', False)
        
        if region_edit_mode:
            act_disable = menu.addAction('✓ 智能区域修改（已启用）')
            act_disable.triggered.connect(self._disable_smart_region_edit)
        else:
            act_enable = menu.addAction('启用智能区域修改')
            act_enable.triggered.connect(self._enable_smart_region_edit)
        
        menu.exec(self.btn_auto_select.mapToGlobal(pos))
    
    def _enable_smart_region_edit(self):
        """启用智能区域修改模式"""
        try:
            # 设置画板为智能区域修改模式
            self.canvas._smart_region_edit_mode = True
            
            # 自动切换到矩形框选工具
            self.btn_rect.setChecked(True)
            # 取消其他按钮
            for btn in [self.btn_brush, self.btn_eraser, self.btn_move, self.btn_wand, 
                       self.btn_auto_select, self.btn_bucket, self.btn_dropper]:
                btn.setChecked(False)
            
            # 设置画板工具为矩形框选
            self.canvas.set_tool('rect_select')
            
            # 显示提示
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                '智能区域修改已启用',
                '现在可以使用矩形框选工具选择区域，右键选区选择"智能区域修改"进行修改。\n\n要退出此模式，请再次右键自动选区工具。'
            )
            
        except Exception as e:
            print(f'启用智能区域修改失败: {e}')
    
    def _disable_smart_region_edit(self):
        """禁用智能区域修改模式"""
        try:
            self.canvas._smart_region_edit_mode = False
            
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, '已退出', '智能区域修改模式已关闭')
            
        except Exception as e:
            print(f'禁用智能区域修改失败: {e}')

    def set_language(self, code: str):
        """设置语言代码（'zh' 或 'en'），更新标题与工具提示。"""
        if code not in ('zh', 'en'):
            code = 'zh'
        self._lang_code = code
        self._i18n = self._get_i18n(code)
        self.title.setText(self._i18n['toolbar'])
        self.btn_brush.setToolTip(self._i18n['brush'])
        self.btn_eraser.setToolTip(self._i18n['eraser'])
        self.btn_move.setToolTip(self._i18n['move'])
        self.btn_rect.setToolTip(self._i18n['rect'])
        self.btn_wand.setToolTip(self._i18n['wand'])
        self.btn_auto_select.setToolTip(self._i18n['auto_select'])
        self.btn_bucket.setToolTip(self._i18n['bucket'])
        self.btn_dropper.setToolTip(self._i18n['eyedropper'])
        
        # 更新画板尺寸区域的文本
        try:
            size_widget = self.findChild(QWidget, 'SizePanel')
            if size_widget:
                # 更新标题
                for child in size_widget.findChildren(QLabel):
                    if 'bold' in child.styleSheet():
                        child.setText(self._i18n['canvas_size'])
                        break
                # 更新按钮
                if hasattr(self, 'btn_apply_size'):
                    self.btn_apply_size.setText(self._i18n['apply'])
        except Exception:
            pass

    def _get_i18n(self, code: str) -> dict:
        zh = {
            'toolbar': '工具栏',
            'brush': '画笔',
            'eraser': '橡皮擦',
            'move': '移动',
            'rect': '矩形框选',
            'wand': '魔术棒',
            'auto_select': '自动选区',
            'bucket': '油漆桶',
            'eyedropper': '吸管',
            'canvas_size': '画板尺寸',
            'width': '宽',
            'height': '高',
            'apply': '应用',
            'zoom': '缩放比例',
            'fit': '自适应',
            'zoom_input_title': '输入缩放比例',
            'zoom_input_label': '缩放比例 (10-200):',
        }
        en = {
            'toolbar': 'Tools',
            'brush': 'Brush',
            'eraser': 'Eraser',
            'move': 'Move',
            'rect': 'Rect Select',
            'wand': 'Magic Wand',
            'auto_select': 'Auto Select',
            'bucket': 'Paint Bucket',
            'eyedropper': 'Eyedropper',
            'canvas_size': 'Canvas Size',
            'width': 'W',
            'height': 'H',
            'apply': 'Apply',
            'zoom': 'Zoom',
            'fit': 'Fit',
            'zoom_input_title': 'Input Zoom',
            'zoom_input_label': 'Zoom (10-200):',
        }
        return zh if code == 'zh' else en

    def _toggle_brush(self, btn_brush: QPushButton):
        # 点击画笔：开启则置为 brush；再次点击关闭置为 none
        if btn_brush.isChecked():
            self.canvas.set_tool('brush')
        else:
            self.canvas.set_tool('none')

    def _toggle_eraser(self, btn_eraser: QPushButton, btn_brush: QPushButton):
        # 点击橡皮擦：开启则置为 eraser；再次点击关闭置为 none
        if btn_eraser.isChecked():
            self.canvas.set_tool('eraser')
            # 橡皮擦开启时，关闭画笔按钮的勾选
            if btn_brush.isChecked():
                btn_brush.setChecked(False)
        else:
            self.canvas.set_tool('none')


class PaintIconButton(QPushButton):
    """生成位图并作为 Icon 显示，避免外部资源依赖"""
    def __init__(self, kind: str, tooltip: str = '', parent=None):
        super().__init__('', parent)
        self.kind = kind
        self.setToolTip(tooltip)
        # 提高可见度的最小尺寸
        self.setMinimumSize(44, 44)
        self._hover = False
        self.toggled.connect(self._update_icon)
        self._update_icon()

    def enterEvent(self, event):
        self._hover = True
        super().enterEvent(event)
        self._update_icon()

    def leaveEvent(self, event):
        self._hover = False
        super().leaveEvent(event)
        self._update_icon()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_icon()

    def _update_icon(self):
        # 减少内边距以增大图标
        margin = 8
        size = max(24, min(self.width(), self.height()) - margin)
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing, True)

        if self.isChecked():
            color = QColor('#34c759')
        elif self._hover:
            color = QColor('#34c759')
        else:
            color = QColor('#333333')

        pen = QPen(color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        rect = QRect(0, 0, size, size)

        if self.kind == 'brush':
            self._draw_brush(p, rect, color)
        elif self.kind == 'eraser':
            self._draw_eraser(p, rect, color)
        elif self.kind == 'move':
            self._draw_move(p, rect, color)
        elif self.kind == 'rect':
            self._draw_rect(p, rect, color)
        elif self.kind == 'wand':
            self._draw_wand(p, rect, color)
        elif self.kind == 'auto_select':
            self._draw_auto_select(p, rect, color)
        elif self.kind == 'bucket':
            self._draw_bucket(p, rect, color)
        elif self.kind == 'eyedropper':
            self._draw_dropper(p, rect, color)
        else:
            self._draw_brush(p, rect, color)

        p.end()
        self.setIcon(QIcon(pix))
        self.setIconSize(QSize(size, size))

    def _draw_brush(self, p: QPainter, rect: QRect, color: QColor):
        # 更像"画笔"的矢量：斜置手柄 + 金属箍 + 笔锋
        s = rect.width()
        cx, cy = rect.center().x(), rect.center().y()
        p.save()
        p.translate(cx, cy)
        p.rotate(-35)

        # 局部尺寸
        L = int(s * 0.60)   # 手柄长度
        W = max(2, int(s * 0.10))  # 手柄粗细
        ferrule_w = int(s * 0.24)  # 金属箍宽
        ferrule_h = max(W + 2, int(s * 0.16))
        tip_w = int(s * 0.30)      # 笔锋宽度
        tip_h = int(s * 0.18)

        # 手柄（圆头矩形的近似：两条平行线+端帽）
        p.setBrush(Qt.NoBrush)
        # 主轴横向，从左到右
        x0 = -L // 2
        x1 = x0 + L
        y0 = 0
        # 主轴线，使用已有圆角端
        p.drawLine(QPoint(x0, y0), QPoint(x1, y0))
        # 通过绘制与主轴平行的小线条，营造手柄厚度（视觉更粗）
        p.drawLine(QPoint(x0, y0 - W // 2), QPoint(x1, y0 - W // 2))
        p.drawLine(QPoint(x0, y0 + W // 2), QPoint(x1, y0 + W // 2))

        # 金属箍（靠近笔锋的短矩形）
        ferrule = QRect(x1 - ferrule_w, -ferrule_h // 2, ferrule_w, ferrule_h)
        p.fillRect(ferrule, color)
        p.drawRect(ferrule)

        # 笔锋（三角形填充）
        tip_left = QPoint(ferrule.right(), 0)
        tip = QPainterPath()
        tip.moveTo(tip_left)
        tip.lineTo(tip_left + QPoint(tip_w, -tip_h // 2))
        tip.lineTo(tip_left + QPoint(tip_w, tip_h // 2))
        tip.closeSubpath()
        p.fillPath(tip, QBrush(color))
        p.drawPath(tip)

        p.restore()

    def _draw_eraser(self, p: QPainter, rect: QRect, color: QColor):
        # 纯矢量"橡皮擦"图标：倾斜的长方体 + 底部分段
        s = rect.width()
        cx, cy = rect.center().x(), rect.center().y()
        p.save()
        p.translate(cx, cy)
        p.rotate(-25)
        w = int(s * 0.68)
        h = int(s * 0.40)
        body = QRect(-w // 2, -h // 2, w, h)
        # 主体填充+描边
        p.fillRect(body, color)
        p.drawRoundedRect(body, int(s * 0.08), int(s * 0.08))
        # 底部分段（橡皮底座）
        base_h = max(2, int(h * 0.28))
        base = QRect(body.left(), body.bottom() - base_h, w, base_h)
        p.setBrush(Qt.NoBrush)
        p.drawRect(base)
        p.restore()

    def _draw_move(self, p: QPainter, rect: QRect, color: QColor):
        s = rect.width()
        cx, cy = rect.center().x(), rect.center().y()
        p.save()
        p.setBrush(Qt.NoBrush)
        # 画十字与四向箭头
        p.drawLine(cx - s//4, cy, cx + s//4, cy)
        p.drawLine(cx, cy - s//4, cx, cy + s//4)
        # 箭头
        p.drawLine(cx + s//4, cy, cx + s//4 - 6, cy - 4)
        p.drawLine(cx + s//4, cy, cx + s//4 - 6, cy + 4)
        p.drawLine(cx - s//4, cy, cx - s//4 + 6, cy - 4)
        p.drawLine(cx - s//4, cy, cx - s//4 + 6, cy + 4)
        p.drawLine(cx, cy - s//4, cx - 4, cy - s//4 + 6)
        p.drawLine(cx, cy - s//4, cx + 4, cy - s//4 + 6)
        p.drawLine(cx, cy + s//4, cx - 4, cy + s//4 - 6)
        p.drawLine(cx, cy + s//4, cx + 4, cy + s//4 - 6)
        p.restore()

    def _draw_rect(self, p: QPainter, rect: QRect, color: QColor):
        s = rect.width()
        r = rect.adjusted(6, 6, -6, -6)
        dash = QPen(color, 2, Qt.DashLine)
        p.save()
        p.setPen(dash)
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)
        p.restore()

    def _draw_wand(self, p: QPainter, rect: QRect, color: QColor):
        s = rect.width()
        p.save()
        # 星形
        cx, cy = rect.center().x(), rect.center().y()
        p.drawLine(cx - 8, cy, cx + 8, cy)
        p.drawLine(cx, cy - 8, cx, cy + 8)
        p.drawLine(cx - 6, cy - 6, cx + 6, cy + 6)
        p.drawLine(cx + 6, cy - 6, cx - 6, cy + 6)
        # 手柄
        p.rotate(30)
        p.drawLine(cx - 12, cy + 12, cx + 12, cy - 12)
        p.restore()

    def _draw_auto_select(self, p: QPainter, rect: QRect, color: QColor):
        """绘制自动选区图标：AI风格的智能选择图标（人形轮廓+虚线边框）"""
        p.save()
        cx, cy = rect.center().x(), rect.center().y()
        s = rect.width()
        
        # 绘制简化的人形轮廓
        # 头部（圆形）
        head_radius = int(s * 0.12)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPoint(cx, cy - int(s * 0.18)), head_radius, head_radius)
        
        # 身体和四肢（简化线条）
        body_top = cy - int(s * 0.06)
        body_bottom = cy + int(s * 0.20)
        # 身体中线
        p.drawLine(cx, body_top, cx, body_bottom)
        
        # 手臂
        arm_y = cy
        arm_width = int(s * 0.22)
        p.drawLine(cx - arm_width, arm_y - 4, cx, arm_y)
        p.drawLine(cx + arm_width, arm_y - 4, cx, arm_y)
        
        # 腿部
        leg_width = int(s * 0.12)
        p.drawLine(cx, body_bottom, cx - leg_width, body_bottom + int(s * 0.12))
        p.drawLine(cx, body_bottom, cx + leg_width, body_bottom + int(s * 0.12))
        
        # 绘制虚线边框表示选区
        dash_pen = QPen(color, 2, Qt.DashLine)
        p.setPen(dash_pen)
        margin = int(s * 0.12)
        border_rect = QRect(cx - int(s * 0.32), cy - int(s * 0.32), 
                           int(s * 0.64), int(s * 0.64))
        p.drawRect(border_rect)
        
        p.restore()

    

    def _draw_bucket(self, p: QPainter, rect: QRect, color: QColor):
        p.save()
        cx, cy = rect.center().x(), rect.center().y()
        # 桶+滴
        body = QRect(cx-10, cy-6, 20, 12)
        p.drawRect(body)
        p.drawLine(cx-12, cy-8, cx-6, cy-6)
        p.drawEllipse(QRect(cx+12, cy, 6, 8))
        p.restore()

    def _draw_dropper(self, p: QPainter, rect: QRect, color: QColor):
        p.save()
        cx, cy = rect.center().x(), rect.center().y()
        p.rotate(-30)
        p.drawLine(cx-12, cy, cx+8, cy)
        p.drawEllipse(QRect(cx+8, cy-3, 6, 6))
        p.restore()
