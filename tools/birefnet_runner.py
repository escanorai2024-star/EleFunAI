import os
import sys
from typing import Optional, Union


def _ensure_site_paths():
    try:
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.dirname(__file__))
        paths = []
        paths.append(os.path.join(base, '.venv', 'Lib', 'site-packages'))
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

def _ensure_repo_on_path():
    """尝试将本地 BiRefNet 源码目录加入 sys.path。
    期望目录：tools/third_party/BiRefNet
    """
    repo_dir = os.path.join(os.path.dirname(__file__), 'third_party', 'BiRefNet')
    if os.path.isdir(repo_dir) and repo_dir not in sys.path:
        sys.path.insert(0, repo_dir)


def _models_home() -> str:
    """返回软件根目录下的 models 目录（可执行/开发模式通用）。

    - 开发模式：工程根目录下 `models`
    - 打包后一体化运行：EXE 同级目录下 `models`
    """
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        # tools/ -> 工程根目录
        base = os.path.dirname(os.path.dirname(__file__))
    models_dir = os.path.join(base, 'models')
    try:
        os.makedirs(models_dir, exist_ok=True)
    except Exception:
        pass
    return models_dir


def _to_image(input_obj):
    from PIL import Image
    # 允许传入路径或 PIL.Image
    if hasattr(input_obj, 'size') and hasattr(input_obj, 'mode'):
        return input_obj
    return Image.open(str(input_obj)).convert('RGB')


def remove_bg_birefnet(input_obj: Union[str, object], weights_path: Optional[str] = None, device: Optional[str] = None):
    """使用 BiRefNet 去背景，返回带透明通道的 PIL.Image。

    优先使用本地源码 `models.birefnet` + 本地权重；若不可用，自动回退到
    Hugging Face Transformers `ZhengPeng7/BiRefNet` 在线权重，并将权重缓存到
    软件根目录的 `models/hf_cache` 下，避免重复下载。
    输入既可为文件路径，也可为 PIL.Image。
    """
    try:
        from PIL import Image
        import numpy as np
        import torch
        from torchvision import transforms
    except Exception:
        _ensure_site_paths()
        try:
            from PIL import Image
            import numpy as np
            import torch
            from torchvision import transforms
        except Exception as e:
            print(f"[DEBUG] [BiRefNet] 依赖缺失: {e}", flush=True)
            return None

    # 输入归一化为 PIL.Image
    img = _to_image(input_obj)
    w, h = img.size

    # 设备选择
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")

    # 预处理（标准 1024x1024）
    tfm = transforms.Compose([
        transforms.Resize((1024, 1024)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    x = tfm(img)[None, ...].to(device)

    # 构建模型：先尝试本地源码与权重，否则回退到 HF
    model = None
    try:
        _ensure_repo_on_path()
        from models.birefnet import BiRefNet
        model = BiRefNet()
        wp = weights_path or os.environ.get('BIRENET_WEIGHTS')
        if wp is None:
            # 统一本地权重文件保存到软件根目录 models 下
            wp = os.path.join(_models_home(), 'birefnet_general.pth')
        if not os.path.exists(wp):
            raise FileNotFoundError("缺少本地权重，转用 HuggingFace")
        state = torch.load(wp, map_location=device)
        if isinstance(state, dict) and 'state_dict' in state:
            state = state['state_dict']
        model.load_state_dict(state, strict=False)
    except Exception:
        # Hugging Face 回退：权重缓存到 models/hf_cache，避免重复下载
        from transformers import AutoModelForImageSegmentation
        hf_cache_dir = os.path.join(_models_home(), 'hf_cache')
        try:
            os.makedirs(hf_cache_dir, exist_ok=True)
        except Exception:
            pass
        # 统一并清理缓存相关环境变量，避免使用系统旧变量导致路径分散/警告
        try:
            os.environ.pop('TRANSFORMERS_CACHE', None)  # 旧变量，会触发弃用警告
        except Exception:
            pass
        os.environ.setdefault('HF_HOME', hf_cache_dir)
        os.environ.setdefault('HUGGINGFACE_HUB_CACHE', hf_cache_dir)

        # 若本地已存在 BiRefNet 缓存，则启用完全离线加载，避免网络访问与重复下载
        local_files_only = False
        try:
            if os.path.isdir(hf_cache_dir):
                entries = os.listdir(hf_cache_dir)
                has_birefnet = any('ZhengPeng7--BiRefNet' in e for e in entries)
                local_files_only = bool(has_birefnet)
        except Exception:
            pass

        try:
            model = AutoModelForImageSegmentation.from_pretrained(
                'ZhengPeng7/BiRefNet', trust_remote_code=True, cache_dir=hf_cache_dir, local_files_only=local_files_only
            )
        except AttributeError as ae:
            # 常见报错：'NoneType' object has no attribute 'endswith'
            # 多源于 Transformers 在解析权重文件名时拿到了 None（缓存不完整/损坏）。
            raise RuntimeError(
                f"BiRefNet 加载失败：{ae}. 可能是缓存不完整或损坏，请清理 {hf_cache_dir} 后重试。"
            )

    model.to(device)
    model.eval()

    with torch.no_grad():
        out = model(x)

    # 取掩码（兼容多种输出结构）
    def _to_mask_tensor(o):
        if isinstance(o, torch.Tensor):
            return o
        if isinstance(o, (list, tuple)) and len(o) > 0:
            return _to_mask_tensor(o[-1])
        if isinstance(o, dict):
            for k in ('pred', 'mask', 'out', 'saliency'):
                if k in o:
                    return _to_mask_tensor(o[k])
        raise ValueError("无法解析 BiRefNet 输出为掩码")

    mask = _to_mask_tensor(out)
    if mask.dim() == 4:
        mask = mask.squeeze(0)
    if mask.dim() == 3:
        mask = mask.squeeze(0)
    mask = torch.sigmoid(mask)
    mask_np = np.clip(mask.detach().cpu().numpy(), 0.0, 1.0)

    # 调整大小到原图
    try:
        import cv2
        resized = cv2.resize(mask_np, (w, h), interpolation=cv2.INTER_LINEAR)
    except Exception:
        pil_mask = Image.fromarray((mask_np * 255).astype(np.uint8))
        resized = np.array(pil_mask.resize((w, h), Image.BILINEAR)) / 255.0

    # 组合 RGBA
    rgba = np.dstack([np.array(img), (resized * 255).astype(np.uint8)])
    return Image.fromarray(rgba, mode='RGBA')
