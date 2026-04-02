"""
Krita 集成模块
提供与 Krita 的桥接功能：
- 发送当前图层到 Krita 编辑
- 监听 Krita 保存，自动回传到画板
"""

import os
import subprocess
from pathlib import Path
from PySide6.QtWidgets import QWidget, QFileDialog
from PySide6.QtCore import QFileSystemWatcher, QTimer, QSettings, Qt
from PySide6.QtGui import QPixmap, QIcon


class KritaIntegration:
    """Krita 集成管理器"""
    
    def __init__(self, photo_page):
        """
        初始化 Krita 集成
        
        Args:
            photo_page: PhotoPage 实例，用于访问画布和图层
        """
        self.photo_page = photo_page
        self._bridge_watcher = None
        self._bridge_map = {}  # 存储桥接文件信息 {path: {'origin': str, 'lid': int}}
        self._bridge_last_mtime = {}
        
        # 确保临时目录存在
        self.temp_dir = Path(__file__).resolve().parent / 'Temp'
        self.temp_dir.mkdir(exist_ok=True)
        
        # print('[Krita] 集成已初始化', flush=True)
    
    def send_to_krita(self):
        """发送当前选中图层到 Krita 编辑"""
        try:
            # 获取 Krita 程序路径
            krita_exe = self._get_krita_exe()
            if not krita_exe:
                # print('[Krita] 未配置 Krita 程序路径', flush=True)
                return
            
            # 获取当前选中图层
            canvas = getattr(self.photo_page, 'canvas', None)
            if not canvas:
                # print('[Krita] 无法访问画布', flush=True)
                return
            
            # 获取选中图层ID和内容
            try:
                lid = getattr(canvas, 'get_active_layer_id', lambda: None)()
            except Exception:
                lid = None
            
            if lid is None:
                # print('[Krita] 未选择图层', flush=True)
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self.photo_page, 
                    '提示', 
                    '请先选择一个图层\n\n如果没有图层，请先生成或添加图片到画板'
                )
                return
            
            # 获取图层内容
            try:
                pix = getattr(canvas, 'get_active_layer_pixmap', lambda: None)()
            except Exception:
                pix = None
            
            if pix is None or pix.isNull():
                # print('[Krita] 无法获取图层内容', flush=True)
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self.photo_page, '提示', '选中的图层内容为空')
                return
            
            # 保存到桥接文件
            bridge_path = self.temp_dir / 'bridge_krita.png'
            if not pix.save(str(bridge_path), 'PNG'):
                # print('[Krita] 保存桥接文件失败', flush=True)
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self.photo_page, '错误', '无法保存临时文件')
                return
            
            # print(f'[Krita] 已保存桥接文件: {bridge_path}', flush=True)
            # print(f'[Krita] 图层ID: {lid}, 尺寸: {pix.width()}x{pix.height()}', flush=True)
            
            # 存储桥接信息
            self._bridge_map[str(bridge_path)] = {
                'origin': 'active_layer',
                'lid': lid
            }
            
            # 启动文件监听
            if not self._bridge_watcher:
                self._bridge_watcher = QFileSystemWatcher()
                self._bridge_watcher.fileChanged.connect(self._on_bridge_file_changed)
            
            # 添加文件监听
            if str(bridge_path) in self._bridge_watcher.files():
                self._bridge_watcher.removePath(str(bridge_path))
            self._bridge_watcher.addPath(str(bridge_path))
            
            # print(f'[Krita] 已添加文件监听: {bridge_path}', flush=True)
            
            # 启动 Krita
            try:
                subprocess.Popen([krita_exe, str(bridge_path)], shell=False)
                # print(f'[Krita] ✓ 已启动 Krita: {krita_exe}', flush=True)
                # print(f'[Krita] 💡 请在 Krita 中编辑图片，保存后将自动回传到画板', flush=True)
            except Exception as e:
                # print(f'[Krita] ❌ 启动 Krita 失败: {e}', flush=True)
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.critical(self.photo_page, '错误', f'无法启动 Krita：\n{str(e)}')
        
        except Exception as e:
            # print(f'[Krita] 发送到 Krita 失败: {e}', flush=True)
            import traceback
            traceback.print_exc()
    
    def _get_krita_exe(self) -> str | None:
        """获取 Krita 程序路径（从设置或手动选择）"""
        settings = QSettings('YourCompany', 'GhostOS')
        key = 'app_kr'
        path = settings.value(key, '')
        
        if path and Path(path).exists():
            return path
        
        # 未配置或路径无效，提示用户手动选择
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self.photo_page,
            '配置 Krita',
            'Krita 程序路径未设置\n\n是否现在选择 Krita 程序？',
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            path, _ = QFileDialog.getOpenFileName(
                self.photo_page,
                '选择 Krita 程序',
                '',
                'Executable (*.exe)'
            )
            if path:
                settings.setValue(key, path)
                # print(f'[Krita] 已保存程序路径: {path}', flush=True)
                return path
        
        return None
    
    def _on_bridge_file_changed(self, changed_path: str):
        """桥接文件变化时的回调（Krita 保存了文件）"""
        try:
            bridge_info = self._bridge_map.get(changed_path, {})
            if not bridge_info:
                # print(f'[Krita] 文件变化但无桥接信息: {changed_path}', flush=True)
                return
            
            origin = bridge_info.get('origin', 'canvas')
            lid = bridge_info.get('lid', None)
            
            # print(f'[Krita] 检测到文件变化: {changed_path}', flush=True)
            # print(f'[Krita] 来源: {origin}, 图层ID: {lid}', flush=True)
            
            # 重新加入监听（Krita 保存会替换文件导致监听失效）
            QTimer.singleShot(500, lambda: self._re_watch(changed_path))
            
            # 延迟加载文件（避免文件正在写入）
            self._schedule_load_bridge(changed_path, origin, lid, attempts=5, delay_ms=300)
        
        except Exception as e:
            # print(f'[Krita] 文件变化处理失败: {e}', flush=True)
            import traceback
            traceback.print_exc()
    
    def _re_watch(self, path: str):
        """重新添加文件监听"""
        try:
            if self._bridge_watcher and path not in self._bridge_watcher.files():
                self._bridge_watcher.addPath(path)
                # print(f'[Krita] 重新添加文件监听: {path}', flush=True)
        except Exception:
            pass
    
    def _schedule_load_bridge(self, path: str, origin: str, lid: int, attempts: int = 5, delay_ms: int = 300):
        """延迟尝试加载桥接文件（多次重试以应对文件锁定）"""
        def try_once():
            nonlocal attempts
            try:
                # 尝试加载图片
                pix = QPixmap(path)
                if not pix.isNull():
                    # print(f'[Krita] ✓ 成功加载桥接文件: {pix.width()}x{pix.height()}', flush=True)
                    
                    # 更新原图层
                    if origin == 'active_layer' and lid is not None:
                        self._update_layer(lid, pix)
                    else:
                        # 添加为新图层
                        self._add_new_layer(pix)
                    
                    return
                else:
                    # print(f'[Krita] ⚠️  加载的图片为空', flush=True)
                    pass
            
            except Exception as e:
                # print(f'[Krita] 加载失败 (剩余重试: {attempts-1}): {e}', flush=True)
                pass
            
            # 递减重试
            attempts -= 1
            if attempts > 0:
                QTimer.singleShot(delay_ms, try_once)
            else:
                # print(f'[Krita] ❌ 加载失败，已达最大重试次数', flush=True)
                pass
        
        # 首次延迟调用
        QTimer.singleShot(delay_ms, try_once)
    
    def _update_layer(self, lid: int, pix: QPixmap):
        """更新指定图层的内容"""
        try:
            canvas = getattr(self.photo_page, 'canvas', None)
            if not canvas:
                # print('[Krita] 无法访问画布', flush=True)
                return
            
            # 更新画布图层
            ok = False
            try:
                update_func = getattr(canvas, 'update_layer_pixmap_by_id', None)
                if update_func:
                    ok = update_func(lid, pix)
            except Exception as e:
                # print(f'[Krita] 更新画布图层失败: {e}', flush=True)
                pass
            
            if not ok:
                # print(f'[Krita] ⚠️  画布图层更新失败，将添加为新图层', flush=True)
                self._add_new_layer(pix)
                return
            
            # print(f'[Krita] ✓ 已更新画布图层 ID={lid}', flush=True)
            
            # 更新图层面板缩略图
            try:
                layers_panel = getattr(self.photo_page, 'layers_panel', None)
                if layers_panel and hasattr(layers_panel, 'list'):
                    size = layers_panel.list.iconSize()
                    if size.isValid():
                        thumb = pix.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    else:
                        thumb = pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    
                    # 查找对应的列表项
                    cnt = layers_panel.list.count()
                    for i in range(cnt):
                        it = layers_panel.list.item(i)
                        if it and it.data(Qt.UserRole) == lid:
                            it.setIcon(QIcon(thumb))
                            # print(f'[Krita] ✓ 已更新图层面板缩略图 (索引={i})', flush=True)
                            break
                    
                    # 刷新显示
                    layers_panel.list.viewport().update()
                    layers_panel.list.update()
            
            except Exception as e:
                # print(f'[Krita] 更新图层面板缩略图失败: {e}', flush=True)
                pass
            
            # print(f'[Krita] ✅ 图层更新完成！', flush=True)
        
        except Exception as e:
            # print(f'[Krita] 更新图层失败: {e}', flush=True)
            import traceback
            traceback.print_exc()
    
    def _add_new_layer(self, pix: QPixmap):
        """添加为新图层"""
        try:
            layers_panel = getattr(self.photo_page, 'layers_panel', None)
            if not layers_panel:
                # print('[Krita] 无法访问图层面板', flush=True)
                return
            
            # 添加新图层
            layers_panel.add_layer_pixmap(pix, '来自Krita', sync_to_canvas=True)
            # print(f'[Krita] ✓ 已添加新图层: 来自Krita ({pix.width()}x{pix.height()})', flush=True)
        
        except Exception as e:
            # print(f'[Krita] 添加新图层失败: {e}', flush=True)
            import traceback
            traceback.print_exc()
