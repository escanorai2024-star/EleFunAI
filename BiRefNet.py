"""
BiRefNet 抠图模块
功能：基于 BiRefNet 模型进行图像抠图（背景移除）
- 使用 tools/birefnet_runner.py 中的完整实现
- 自动使用 Hugging Face 缓存或本地权重
- 支持从 QPixmap 进行抠图
"""

import os
import sys
import warnings
from pathlib import Path
from typing import Optional

# 过滤 timm 库的弃用警告
warnings.filterwarnings('ignore', category=FutureWarning, module='timm')

from PySide6.QtWidgets import QMessageBox, QApplication
from PySide6.QtGui import QPixmap, QImage

def _ensure_site_paths():
    try:
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        paths = []
        paths.append(os.path.join(base_dir, '.venv', 'Lib', 'site-packages'))
        try:
            import site
            for p in site.getsitepackages():
                paths.append(p)
            paths.append(site.getusersitepackages())
        except Exception:
            pass
        try:
            bp = getattr(sys, 'base_prefix', sys.prefix)
            paths.append(os.path.join(bp, 'Lib', 'site-packages'))
        except Exception:
            pass
        for p in paths:
            if isinstance(p, str) and os.path.isdir(p) and p not in sys.path:
                sys.path.insert(0, p)
    except Exception:
        pass

_ensure_site_paths()

class BiRefNetMatting:
    """BiRefNet 抠图核心类"""
    
    def __init__(self, debug_sink=None):
        """初始化 BiRefNet 抠图器"""
        self._sink = debug_sink
        self._debug('[BiRefNet] 初始化抠图器')
    
    def _debug(self, message: str):
        if callable(getattr(self, '_sink', None)):
            try:
                self._sink(message)
                return
            except Exception:
                pass
        print(f'[DEBUG] {message}', flush=True)
    
    def matting(self, input_image: QPixmap) -> Optional[QPixmap]:
        """
        对图像进行抠图
        
        Args:
            input_image: 输入的 QPixmap 图像
        
        Returns:
            抠图后的 QPixmap（背景透明），失败返回 None
        """
        try:
            _ensure_site_paths()
            self._debug('[BiRefNet] 开始抠图...')
            
            # 显示模型路径信息
            self._show_model_info()
            
            # 检查设备类型并给出性能提示
            try:
                import torch
                is_cuda = torch.cuda.is_available()
                device = "GPU (CUDA)" if is_cuda else "CPU"
                self._debug(f'[BiRefNet] 使用设备: {device}')
                if not is_cuda:
                    self._debug('[BiRefNet] ⚠️  当前使用 CPU 推理，处理速度较慢（约15-30秒）')
                    self._debug('[BiRefNet] 💡 提示: 安装 GPU 版 PyTorch 可大幅提升速度')
            except:
                pass
            
            # 导入依赖 - 让 birefnet_runner 自己处理导入
            self._debug('[BiRefNet] 导入 birefnet_runner...')
            from tools.birefnet_runner import remove_bg_birefnet
            self._debug('[BiRefNet] 成功导入 birefnet_runner')
            
            # 导入图像处理库 - 在 birefnet_runner 导入成功后再导入
            try:
                from PIL import Image
                import numpy as np
                self._debug(f'[BiRefNet] 依赖库检查完成')
            except ImportError as e:
                _ensure_site_paths()
                try:
                    from PIL import Image
                    import numpy as np
                    self._debug(f'[BiRefNet] 依赖库检查完成')
                except ImportError as e:
                    self._debug(f'[BiRefNet] 缺少依赖: {e}')
                    raise

            try:
                import torch
                import transformers
            except Exception:
                _ensure_site_paths()
                try:
                    import torch
                    import transformers
                except Exception:
                    pass
            
            # QPixmap -> QImage -> PIL Image (RGB)
            qimage = input_image.toImage()
            width = qimage.width()
            height = qimage.height()
            
            self._debug(f'[BiRefNet] 输入图像尺寸: {width}x{height}')
            
            qimage_rgb = qimage.convertToFormat(QImage.Format_RGB888)
            width = qimage_rgb.width()
            height = qimage_rgb.height()
            bpl = qimage_rgb.bytesPerLine()
            ptr = qimage_rgb.constBits()
            if hasattr(ptr, 'setsize'):
                ptr.setsize(qimage_rgb.sizeInBytes())
            buf = np.frombuffer(ptr, dtype=np.uint8)
            self._debug(f'[BiRefNet] QImage RGB size {width}x{height}, bpl={bpl}, bytes={qimage_rgb.sizeInBytes()}, buf={buf.size}')
            arr2d = buf.reshape(height, bpl)
            arr = arr2d[:, :width * 3].reshape(height, width, 3)
            pil_image_rgb = Image.fromarray(arr, 'RGB')
            
            self._debug('[BiRefNet] 调用 birefnet_runner 进行抠图...')
            self._debug('[BiRefNet] 正在处理中，请稍候...')
            
            # 调用 birefnet_runner 的抠图函数
            import time
            start_time = time.time()
            result_pil = remove_bg_birefnet(pil_image_rgb)
            elapsed = time.time() - start_time
            
            if result_pil is None:
                self._debug('[BiRefNet] birefnet_runner 返回 None')
                return None
            
            self._debug(f'[BiRefNet] 抠图成功！耗时: {elapsed:.2f} 秒')
            self._debug(f'[BiRefNet] 结果尺寸: {result_pil.size}, 模式: {result_pil.mode}')
            
            # PIL Image (RGBA) -> QPixmap（兼容新旧版本）
            if result_pil.mode != 'RGBA':
                result_pil = result_pil.convert('RGBA')
            
            arr_rgba = np.array(result_pil)
            h, w, c = arr_rgba.shape
            bytes_per_line = c * w
            
            # 使用 tobytes() 确保数据连续性
            qimage_result = QImage(arr_rgba.tobytes(), w, h, bytes_per_line, QImage.Format_RGBA8888)
            result_pixmap = QPixmap.fromImage(qimage_result.copy())
            
            self._debug('[BiRefNet] 抠图完成')
            return result_pixmap
            
        except ImportError as e:
            self._debug(f'[BiRefNet] 依赖缺失: {e}')
            msg = str(e)
            try:
                QMessageBox.warning(None, '依赖缺失', f'缺少依赖：{msg}\n请安装必要依赖后重试')
            except Exception:
                pass
            return None
        except Exception as e:
            self._debug(f'[BiRefNet] 抠图失败: {e}')
            import traceback
            self._debug(traceback.format_exc())
            return None
    
    def _show_model_info(self):
        """显示模型路径和状态信息"""
        try:
            import os
            
            # 获取项目根目录
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
            
            models_dir = os.path.join(base_dir, 'models')
            hf_cache_dir = os.path.join(models_dir, 'hf_cache')
            local_weights = os.path.join(models_dir, 'birefnet_general.pth')
            
            self._debug('=' * 60)
            self._debug('[BiRefNet] 模型路径信息：')
            self._debug(f'  项目根目录: {base_dir}')
            self._debug(f'  模型目录: {models_dir}')
            self._debug(f'  HF缓存目录: {hf_cache_dir}')
            self._debug(f'  本地权重路径: {local_weights}')
            
            # 检查本地权重
            if os.path.exists(local_weights):
                size_mb = os.path.getsize(local_weights) / (1024 * 1024)
                self._debug(f'  ✅ 本地权重存在: {size_mb:.2f} MB')
            else:
                self._debug(f'  ❌ 本地权重不存在，将使用 HF 模型')
            
            # 检查 HF 缓存
            if os.path.exists(hf_cache_dir):
                try:
                    entries = os.listdir(hf_cache_dir)
                    has_birefnet = any('ZhengPeng7--BiRefNet' in e for e in entries)
                    if has_birefnet:
                        birefnet_cache = [e for e in entries if 'ZhengPeng7--BiRefNet' in e][0]
                        cache_path = os.path.join(hf_cache_dir, birefnet_cache)
                        self._debug(f'  ✅ HF缓存存在: {cache_path}')
                        
                        # 检查模型文件
                        snapshots_dir = os.path.join(cache_path, 'snapshots')
                        if os.path.exists(snapshots_dir):
                            snapshot_list = os.listdir(snapshots_dir)
                            if snapshot_list:
                                snapshot_id = snapshot_list[0]
                                model_file = os.path.join(snapshots_dir, snapshot_id, 'model.safetensors')
                                if os.path.exists(model_file):
                                    size_mb = os.path.getsize(model_file) / (1024 * 1024)
                                    self._debug(f'  ✅ 模型文件: {model_file}')
                                    self._debug(f'     大小: {size_mb:.2f} MB')
                    else:
                        self._debug(f'  ❌ HF缓存目录存在但无 BiRefNet 模型，将在线下载')
                except Exception as e:
                    self._debug(f'  ⚠️  检查HF缓存时出错: {e}')
            else:
                self._debug(f'  ❌ HF缓存目录不存在，首次使用将在线下载')
            
            # 显示环境变量
            hf_home = os.environ.get('HF_HOME', '未设置')
            self._debug(f'  环境变量 HF_HOME: {hf_home}')
            
            self._debug('=' * 60)
            
        except Exception as e:
            self._debug(f'[BiRefNet] 显示模型信息失败: {e}')


def process_matting(input_pixmap: QPixmap, parent=None) -> Optional[QPixmap]:
    """
    处理图像抠图（使用 birefnet_runner）
    
    Args:
        input_pixmap: 输入图像
        parent: 父窗口
    
    Returns:
        抠图后的图像，失败返回 None
    """
    try:
        # 创建 BiRefNet 实例
        matting = BiRefNetMatting()
        
        # 执行抠图
        matting._debug('[主流程] 开始抠图处理...')
        result_pixmap = matting.matting(input_pixmap)
        
        if result_pixmap:
            matting._debug('[主流程] 抠图成功')
        else:
            matting._debug('[主流程] 抠图失败')
            if parent:
                QMessageBox.warning(
                    parent,
                    '抠图失败',
                    '抠图处理失败，请查看控制台日志了解详情。'
                )
        
        return result_pixmap
        
    except ImportError as e:
        # 缺少依赖模块
        error_msg = str(e)
        print(f'[ERROR] 缺少依赖: {error_msg}', flush=True)
        
        if parent:
            if 'PIL' in error_msg or 'Pillow' in error_msg:
                QMessageBox.critical(
                    parent,
                    '缺少依赖',
                    '缺少 Pillow 图像处理库！\n\n'
                    '请在命令行运行：\n'
                    'pip install Pillow\n\n'
                    '或者：\n'
                    'pip install Pillow numpy torch torchvision transformers'
                )
            elif 'numpy' in error_msg:
                QMessageBox.critical(
                    parent,
                    '缺少依赖',
                    '缺少 NumPy 库！\n\n'
                    '请在命令行运行：\n'
                    'pip install numpy'
                )
            elif 'torch' in error_msg:
                QMessageBox.critical(
                    parent,
                    '缺少依赖',
                    '缺少 PyTorch 库！\n\n'
                    '请在命令行运行：\n'
                    'pip install torch torchvision'
                )
            elif 'transformers' in error_msg:
                QMessageBox.critical(
                    parent,
                    '缺少依赖',
                    '缺少 Transformers 库！\n\n'
                    '请在命令行运行：\n'
                    'pip install transformers'
                )
            else:
                QMessageBox.critical(
                    parent,
                    '缺少依赖',
                    f'缺少必要的Python库：\n{error_msg}\n\n'
                    '请安装完整依赖：\n'
                    'pip install Pillow numpy torch torchvision transformers'
                )
        
        return None
        
    except Exception as e:
        print(f'[ERROR] 抠图流程异常: {e}', flush=True)
        import traceback
        traceback.print_exc()
        
        if parent:
            # 识别网络相关错误
            msg = str(e).lower()
            network_hints = ('network', 'connection', 'timed out', 'timeout', 'resolve', 'ssl', 'http', 'download')
            if any(h in msg for h in network_hints):
                QMessageBox.warning(parent, '错误', '网络错误，请检查网络连接')
            else:
                QMessageBox.critical(parent, '抠图异常', f'抠图过程发生异常：\n{str(e)}')
        
        return None


# 测试代码
if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # 测试抠图功能
    print('BiRefNet 抠图模块 - 使用 birefnet_runner')
    print('模型将自动从 Hugging Face 缓存加载或在线下载')
    
    matting = BiRefNetMatting()
    print('初始化完成')
    
    sys.exit(0)
