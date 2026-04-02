
import os
import sys
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QLabel, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
                               QGraphicsRectItem, QMessageBox, QWidget)
from PySide6.QtGui import QPixmap, QColor, QPen, QPainter, QImage, QBrush
from PySide6.QtCore import Qt, QRectF, Signal, QPointF, QSize

class CropRectItem(QGraphicsRectItem):
    """可调整大小的裁剪框"""
    def __init__(self, rect=QRectF(0, 0, 100, 100), parent=None):
        super().__init__(rect, parent)
        self.setFlags(QGraphicsRectItem.ItemIsMovable | 
                      QGraphicsRectItem.ItemIsSelectable | 
                      QGraphicsRectItem.ItemSendsGeometryChanges)
        self.setPen(QPen(QColor(255, 255, 255), 1, Qt.DashLine))
        self.setBrush(QBrush(QColor(255, 255, 255, 50)))
        self.setAcceptHoverEvents(True)
        self.handle_size = 20
        self.handles = {}
        self.update_handles()
        self.current_handle = None
        self.mouse_press_pos = None
        self.mouse_press_rect = None

    def update_handles(self):
        r = self.rect()
        self.handles = {
            'tl': QRectF(r.left(), r.top(), self.handle_size, self.handle_size),
            'tr': QRectF(r.right() - self.handle_size, r.top(), self.handle_size, self.handle_size),
            'bl': QRectF(r.left(), r.bottom() - self.handle_size, self.handle_size, self.handle_size),
            'br': QRectF(r.right() - self.handle_size, r.bottom() - self.handle_size, self.handle_size, self.handle_size),
        }

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        # 绘制手柄
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 120, 215))
        self.update_handles()
        for handle in self.handles.values():
            painter.drawRect(handle)

    def hoverMoveEvent(self, event):
        pos = event.pos()
        cursor = Qt.ArrowCursor
        for handle_name, rect in self.handles.items():
            if rect.contains(pos):
                if handle_name in ['tl', 'br']:
                    cursor = Qt.SizeFDiagCursor
                else:
                    cursor = Qt.SizeBDiagCursor
                break
        self.setCursor(cursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        self.mouse_press_pos = event.pos()
        self.mouse_press_rect = self.rect()
        self.current_handle = None
        for handle_name, rect in self.handles.items():
            if rect.contains(event.pos()):
                self.current_handle = handle_name
                break
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.current_handle:
            # 调整大小
            diff = event.pos() - self.mouse_press_pos
            rect = self.mouse_press_rect
            new_rect = QRectF(rect)
            
            if self.current_handle == 'tl':
                new_rect.setTopLeft(rect.topLeft() + diff)
            elif self.current_handle == 'tr':
                new_rect.setTopRight(rect.topRight() + diff)
            elif self.current_handle == 'bl':
                new_rect.setBottomLeft(rect.bottomLeft() + diff)
            elif self.current_handle == 'br':
                new_rect.setBottomRight(rect.bottomRight() + diff)
            
            self.setRect(new_rect.normalized())
            self.update_handles()
        else:
            super().mouseMoveEvent(event)

class CropDialog(QDialog):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("裁剪工具")
        # Ensure minimum size to avoid "tadpole" look
        self.setMinimumSize(800, 600)
        self.resize(1200, 900) 
        
        # Force window flags to ensure top-level behavior
        self.setWindowFlags(Qt.Window | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        
        self.setWindowState(Qt.WindowMaximized) 
        self.image_path = image_path
        self.cropped_pixmap = None
        
        layout = QVBoxLayout(self)
        
        # 顶部工具栏
        toolbar = QHBoxLayout()
        self.btn_crop = QPushButton("裁剪并保存")
        self.btn_crop.clicked.connect(self.do_crop)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        
        toolbar.addStretch()
        toolbar.addWidget(self.btn_crop)
        toolbar.addWidget(self.btn_cancel)
        layout.addLayout(toolbar)
        
        # 视图
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        layout.addWidget(self.view)
        
        # 加载图片
        self.load_image()

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, 'pixmap_item'):
            self.view.fitInView(self.pixmap_item, Qt.KeepAspectRatio)

    def load_image(self):
        if not os.path.exists(self.image_path):
            QMessageBox.critical(self, "错误", "图片文件不存在")
            self.reject()
            return
            
        self.pixmap = QPixmap(self.image_path)
        self.pixmap_item = QGraphicsPixmapItem(self.pixmap)
        self.scene.addItem(self.pixmap_item)
        
        # 默认裁剪框
        rect_size = min(self.pixmap.width(), self.pixmap.height()) * 0.8
        cx = (self.pixmap.width() - rect_size) / 2
        cy = (self.pixmap.height() - rect_size) / 2
        self.crop_rect = CropRectItem(QRectF(cx, cy, rect_size, rect_size))
        self.scene.addItem(self.crop_rect)
        
        self.view.setSceneRect(self.pixmap.rect())

    def do_crop(self):
        # 获取裁剪区域（相对于图片）
        rect = self.crop_rect.rect()
        # 考虑crop_rect在场景中的位置（如果它被移动了）
        pos = self.crop_rect.pos()
        final_rect = QRectF(pos.x() + rect.x(), pos.y() + rect.y(), rect.width(), rect.height())
        
        # 转换为整数坐标
        x = int(final_rect.x())
        y = int(final_rect.y())
        w = int(final_rect.width())
        h = int(final_rect.height())
        
        # 裁剪
        cropped = self.pixmap.copy(x, y, w, h)
        
        # 保存回原路径（或者保存为新文件并返回）
        # 这里直接覆盖原文件，或者保存为 _cropped 版本
        # 根据用户需求："返回原来的分镜图位置进行替换"
        # 建议覆盖或者更新引用。这里我们覆盖原文件。
        
        try:
            cropped.save(self.image_path)
            self.cropped_pixmap = cropped
            QMessageBox.information(self, "成功", "裁剪完成")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败: {e}")

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    # 测试
    # dialog = CropDialog("path/to/image.png")
    # dialog.exec()
