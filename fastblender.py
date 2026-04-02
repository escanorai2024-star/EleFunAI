"""
Blender 实时捕获模块
功能：启动 Blender，实时捕获 3D 视口内容并传送到画板的专用图层
"""

import subprocess
import socket
import threading
import time
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtGui import QPixmap, QImage


class BlenderCapture(QObject):
    """Blender 实时捕获器（Socket 模式）"""
    
    # 信号：接收到新的图像数据
    image_received = Signal(QPixmap)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._socket = None
        self._thread = None
        self._running = False
        self._process = None
        
    def start(self, blender_exe: str = None):
        """启动 Blender 并开始监听
        
        Args:
            blender_exe: Blender 可执行文件路径，如果为 None 则尝试自动查找
        """
        if self._running:
            print('[FastBlender] 已在运行中', flush=True)
            return False
            
        # 查找 Blender 程序
        if not blender_exe:
            blender_exe = self._find_blender()
            
        if not blender_exe:
            print('[FastBlender] 未找到 Blender 程序', flush=True)
            return False
            
        try:
            # 启动 Blender
            print(f'[FastBlender] 启动 Blender: {blender_exe}', flush=True)
            self._process = subprocess.Popen([blender_exe], shell=False)
            print(f'[FastBlender] Blender 已启动, PID={self._process.pid}', flush=True)
            
            # 延迟 5 秒后尝试连接（等待 Blender 启动并加载插件）
            print('[FastBlender] 等待 5 秒后尝试连接...', flush=True)
            print('[FastBlender] 提示：请在 Blender 中安装插件并点击"启动服务器"', flush=True)
            QTimer.singleShot(5000, self._connect)
            
            return True
            
        except Exception as e:
            print(f'[FastBlender] 启动失败: {e}', flush=True)
            return False
    
    def stop(self):
        """停止捕获"""
        self._running = False
        
        # 关闭 socket
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        
        # 等待线程结束
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        
        # 关闭 Blender 进程（可选）
        # if self._process:
        #     try:
        #         self._process.terminate()
        #     except Exception:
        #         pass
        
        print('[FastBlender] 已停止', flush=True)
    
    def _find_blender(self) -> str:
        """自动查找 Blender 程序"""
        import os
        import glob
        
        pf = os.environ.get('ProgramFiles', r'C:\Program Files')
        pf86 = os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')
        
        candidates = []
        for root in [pf, pf86]:
            candidates += glob.glob(os.path.join(root, 'Blender Foundation', 'Blender*', 'blender.exe'))
        
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0]
        
        return None
    
    def _connect(self):
        """连接到 Blender 插件服务器"""
        if not hasattr(self, '_connect_attempts'):
            self._connect_attempts = 0
            
        try:
            print('[FastBlender] 尝试连接到 Blender 插件...', flush=True)
            
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(3)  # 减少超时时间
            self._socket.connect(('localhost', 9999))
            
            # 连接成功，取消阻塞模式（设置为非阻塞或长超时）
            self._socket.settimeout(30)  # 设置较长的超时时间
            
            print('[FastBlender] ✓ 连接成功！开始接收 3D 视口数据...', flush=True)
            self._connect_attempts = 0  # 重置重试计数
            
            # 启动接收线程
            self._running = True
            self._thread = threading.Thread(target=self._receive_loop, daemon=True)
            self._thread.start()
            
        except ConnectionRefusedError:
            self._connect_attempts += 1
            if self._connect_attempts <= 3:
                print(f'[FastBlender] 等待 Blender 插件启动... ({self._connect_attempts}/3)', flush=True)
                QTimer.singleShot(5000, self._connect)
            else:
                print('[FastBlender] ⚠ 无法连接到 Blender 插件', flush=True)
                print('[FastBlender] 请在 Blender 中安装插件并点击"启动服务器"', flush=True)
                # 停止重试，但保持程序运行
            
        except Exception as e:
            self._connect_attempts += 1
            if self._connect_attempts <= 3:
                print(f'[FastBlender] 连接中... ({self._connect_attempts}/3)', flush=True)
                QTimer.singleShot(5000, self._connect)
            else:
                print(f'[FastBlender] ⚠ 连接失败: {e}', flush=True)
    
    def _receive_loop(self):
        """接收图像数据的循环（在独立线程中运行）"""
        print('[FastBlender] 接收线程已启动', flush=True)
        first_image = True
        
        try:
            while self._running:
                try:
                    # 接收图像尺寸（4 字节整数）
                    size_data = self._recv_exact(4)
                    if not size_data:
                        break
                    
                    import struct
                    img_size = struct.unpack('!I', size_data)[0]
                    
                    if img_size == 0 or img_size > 100 * 1024 * 1024:  # 最大 100MB
                        print(f'[FastBlender] ⚠ 无效的图像尺寸: {img_size} bytes', flush=True)
                        break
                    
                    # 接收图像数据
                    img_data = self._recv_exact(img_size)
                    if not img_data:
                        break
                    
                    # 转换为 QPixmap
                    qimg = QImage()
                    qimg.loadFromData(img_data)
                    
                    if not qimg.isNull():
                        pixmap = QPixmap.fromImage(qimg)
                        # 发送信号
                        self.image_received.emit(pixmap)
                        
                        if first_image:
                            print(f'[FastBlender] ✓ 首帧接收成功: {pixmap.width()}x{pixmap.height()}', flush=True)
                            first_image = False
                    
                except socket.timeout:
                    # Socket 超时是正常的，继续等待下一帧
                    continue
                except Exception as e:
                    if self._running:
                        print(f'[FastBlender] ⚠ 接收错误: {e}', flush=True)
                    break
                
        except Exception as e:
            if self._running:
                print(f'[FastBlender] ⚠ 接收循环异常: {e}', flush=True)
        finally:
            print('[FastBlender] 接收循环已停止', flush=True)
            self._running = False
    
    def _recv_exact(self, n: int) -> bytes:
        """接收指定字节数的数据"""
        data = b''
        while len(data) < n:
            chunk = self._socket.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data


class BlenderIntegration:
    """Blender 集成管理器（简化版，用于 photo.py）"""
    
    def __init__(self, layers_panel):
        """
        Args:
            layers_panel: 图层面板实例
        """
        self.layers_panel = layers_panel
        self.capture = BlenderCapture()
        self.capture.image_received.connect(self._on_image_received)
        self._blender_layer_index = None
        self._first_image = True
        
    def start_blender(self, blender_exe: str = None):
        """启动 Blender 实时捕获"""
        success = self.capture.start(blender_exe)
        if success:
            print('[FastBlender] Blender 实时捕获已启动', flush=True)
            # 显示安装提示
            self._show_plugin_tip()
        return success
    
    def stop_blender(self):
        """停止 Blender 实时捕获"""
        self.capture.stop()
        self._blender_layer_index = None
        self._first_image = True
    
    def _on_image_received(self, pixmap: QPixmap):
        """处理接收到的图像"""
        if pixmap.isNull():
            return
        
        try:
            from PySide6.QtGui import QIcon
            from PySide6.QtCore import Qt
            
            # 首次接收：创建新图层
            if self._first_image or self._blender_layer_index is None:
                self.layers_panel.add_layer_pixmap(pixmap, 'Blender 3D', sync_to_canvas=True)
                self._blender_layer_index = self.layers_panel.list.count() - 1
                self._first_image = False
                
                # 选中该图层
                try:
                    item = self.layers_panel.list.item(self._blender_layer_index)
                    if item:
                        self.layers_panel.list.setCurrentItem(item)
                except Exception:
                    pass
                
                print('[FastBlender] 已创建 Blender 图层', flush=True)
            else:
                # 后续接收：更新现有图层
                try:
                    item = self.layers_panel.list.item(self._blender_layer_index)
                    if item:
                        # 更新缩略图
                        thumb = pixmap.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        item.setIcon(QIcon(thumb))
                        
                        # 更新原始 pixmap 数据
                        item.setData(Qt.UserRole + 1, pixmap)
                        
                        # 如果有画布图层 ID，更新画布
                        lid = item.data(Qt.UserRole)
                        if lid is not None and hasattr(self.layers_panel.canvas, 'update_layer_pixmap_by_id'):
                            self.layers_panel.canvas.update_layer_pixmap_by_id(lid, pixmap)
                        
                        # 刷新画布
                        if self.layers_panel.canvas:
                            self.layers_panel.canvas.update()
                    else:
                        # 图层不存在，重新创建
                        print('[FastBlender] 图层不存在，重新创建', flush=True)
                        self._blender_layer_index = None
                        self._first_image = True
                        
                except Exception as e:
                    print(f'[FastBlender] 更新图层失败: {e}', flush=True)
                    self._blender_layer_index = None
                    self._first_image = True
                    
        except Exception as e:
            print(f'[FastBlender] 处理图像失败: {e}', flush=True)
    
    def _show_plugin_tip(self):
        """显示插件安装提示"""
        try:
            from PySide6.QtWidgets import QMessageBox
            
            addon_path = Path(__file__).resolve().parent / 'blender_addon'
            
            QMessageBox.information(
                None,
                'Blender 实时捕获 - 插件安装说明',
                f'📌 重要提示：\n\n'
                f'本功能需要在 Blender 中安装服务端插件。\n\n'
                f'请按照以下步骤操作：\n\n'
                f'1. 在 Blender 中：Edit > Preferences > Add-ons\n'
                f'2. 点击 "Install..." 按钮\n'
                f'3. 选择文件：{addon_path}\\ghost_os_server.py\n'
                f'4. 启用插件后，按 N 键打开侧边栏\n'
                f'5. 在 "Ghost OS" 标签页点击 "启动服务器"\n\n'
                f'详细说明请查看：{addon_path}\\安装说明.txt\n\n'
                f'提示：服务器启动后，本软件会自动连接并接收 3D 视口内容。',
                QMessageBox.Ok
            )
        except Exception as e:
            print(f'[FastBlender] 显示提示失败: {e}', flush=True)
