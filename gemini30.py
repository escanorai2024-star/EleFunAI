from __future__ import annotations
from typing import List, Tuple, Optional
import os, sys, json, base64, io
import urllib.request, urllib.error

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout, QPushButton, QComboBox, QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage

DEFAULT_BASE_URL = 'https://yunwu.ai/v1beta'
DEFAULT_MODEL = 'gemini-3-pro-image-preview'

def _get_app_root() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _json_path(*parts: str) -> str:
    return os.path.join(_get_app_root(), 'json', *parts)

def get_config() -> dict:
    cfg = {
        'api_key': '',
        'base_url': DEFAULT_BASE_URL,
        'model': DEFAULT_MODEL,
        'size': '1:1',
        'resolution': '1K',
        'quality': '80',
    }
    try:
        p = _json_path('gemini30.json')
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f) or {}
            for k in cfg.keys():
                v = data.get(k)
                if isinstance(v, str) and v.strip():
                    cfg[k] = v.strip()
    except Exception:
        pass
    return cfg

def _compress_image_to_base64(path: str, max_w: int = 1280, quality: int = 85) -> Optional[tuple[str, str]]:
    try:
        from PySide6.QtGui import QImage
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        img = QImage(path)
        if img.isNull():
            with open(path, 'rb') as f:
                raw = f.read()
            mt = _guess_mime(path)
            return mt, base64.b64encode(raw).decode('utf-8')
        w, h = img.width(), img.height()
        if w > max_w:
            img = img.scaled(max_w, int(h * (max_w / w)), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        img.save(buf, 'JPG', quality=quality)
        data = bytes(QByteArray(buf.data()))
        if len(data) > 2 * 1024 * 1024:
            buf.close(); buf = QBuffer(); buf.open(QIODevice.WriteOnly)
            img.save(buf, 'JPG', quality=max(60, quality - 10))
            data = bytes(QByteArray(buf.data()))
        return 'image/jpeg', base64.b64encode(data).decode('utf-8')
    except Exception:
        return None

def _guess_mime(path: str) -> str:
    import mimetypes
    return mimetypes.guess_type(path)[0] or 'image/jpeg'

def generate_image_preview(prompt: str, refs: List[str], parent=None) -> Tuple[bool, Optional[QPixmap], str]:
    cfg = get_config()
    api_key = cfg.get('api_key', '').strip()
    base_url = (cfg.get('base_url') or DEFAULT_BASE_URL).strip().rstrip('/')
    model = (cfg.get('model') or DEFAULT_MODEL).strip()
    size = cfg.get('size', '1:1')
    resolution = cfg.get('resolution', '1K')
    quality = cfg.get('quality', '80')
    if not api_key:
        return False, None, '缺少 API Key'
    url = f"{base_url}/models/{model}:generateContent"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }
    # parts顺序：图片在前，文本在后
    parts: List[dict] = []
    for p in refs:
        try:
            if not p or not os.path.exists(p):
                continue
            res = _compress_image_to_base64(p)
            if not res:
                continue
            mt, data = res
            parts.append({'inlineData': {'mimeType': mt, 'data': data}})
        except Exception:
            continue
    parts.append({'text': prompt or '生成一张图片'})

    # generationConfig 对齐 X/new_api_client.py
    img_cfg = {
        'aspectRatio': size,
        'imageSize': resolution,
        'jpegQuality': int(quality) if str(quality).isdigit() else 80,
    }
    body = {
        'contents': [{'role': 'user', 'parts': parts}],
        'generationConfig': {
            'responseModalities': ['IMAGE', 'TEXT'],
            'imageConfig': img_cfg,
            'temperature': 0.5,
        }
    }

    # 使用 requests，并根据分辨率调整超时与重试
    try:
        import requests
        timeout_map = {'1K': 240, '2K': 480, '4K': 600}
        timeout = timeout_map.get(resolution, 600)
        max_retries = 2
        last_error = None
        payload = json.dumps(body, ensure_ascii=False)
        for r in range(max_retries):
            try:
                s = requests.Session()
                s.trust_env = False
                resp = s.post(url, data=payload.encode('utf-8'), headers=headers, timeout=timeout, proxies={'http': None, 'https': None})
                ct = (resp.headers.get('Content-Type') or '').lower()
                # 非JSON直接尝试图片解码
                if ct.startswith('image/'):
                    raw = resp.content
                    img = QImage.fromData(raw)
                    if img.isNull():
                        return False, None, '图片数据无效'
                    return True, QPixmap.fromImage(img), 'ok'
                # JSON路径
                try:
                    obj = resp.json()
                except Exception:
                    txt = resp.text[:300] if resp.text else ''
                    return False, None, f'响应解析失败: {txt}'
                pm = _extract_image_pixmap(obj)
                if pm is not None:
                    return True, pm, 'ok'
                # 未返回图片时给出摘要
                preview = ''
                try:
                    preview = json.dumps(obj, ensure_ascii=False)[:300]
                except Exception:
                    preview = str(obj)[:300]
                return False, None, f'未返回图片: {preview}'
            except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
                last_error = e
                if r < max_retries - 1:
                    continue
                return False, None, f'连接错误: {str(e)[:200]}'
            except requests.exceptions.Timeout:
                return False, None, '请求超时：图片生成耗时过长或网络不稳定'
            except Exception as e:
                last_error = e
                if r < max_retries - 1:
                    continue
                return False, None, f'异常: {str(e)[:200]}'
    except Exception as e:
        # 回退到 urllib（保持原逻辑，但延长超时）
        try:
            data = json.dumps(body).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as resp:
                txt = resp.read().decode('utf-8', errors='ignore')
            try:
                obj = json.loads(txt)
            except Exception:
                return False, None, '响应解析失败'
            pm = _extract_image_pixmap(obj)
            if pm is not None:
                return True, pm, 'ok'
            return False, None, '未返回图片'
        except Exception as e2:
            return False, None, f'异常: {str(e2)[:200]}'

def _extract_image_pixmap(resp_obj: dict) -> Optional[QPixmap]:
    try:
        cands = resp_obj.get('candidates') or []
        for c in cands:
            content = c.get('content') or {}
            parts = content.get('parts') or []
            for pr in parts:
                # inlineData / inline_data
                d = pr.get('inlineData') or pr.get('inline_data') or None
                if isinstance(d, dict):
                    data_b64 = d.get('data') or d.get('imageData')
                    if data_b64:
                        raw = base64.b64decode(data_b64)
                        img = QImage.fromData(raw)
                        if not img.isNull():
                            return QPixmap.fromImage(img)
                # media.data
                media = pr.get('media') or {}
                mdata = media.get('data')
                if mdata:
                    try:
                        raw = base64.b64decode(mdata)
                        img = QImage.fromData(raw)
                        if not img.isNull():
                            return QPixmap.fromImage(img)
                    except Exception:
                        pass
                # fileData.fileUri
                filed = pr.get('fileData') or pr.get('file_data') or {}
                file_uri = filed.get('fileUri') or filed.get('file_uri')
                if file_uri:
                    try:
                        with urllib.request.urlopen(file_uri, timeout=60) as fresp:
                            raw = fresp.read()
                        img = QImage.fromData(raw)
                        if not img.isNull():
                            return QPixmap.fromImage(img)
                    except Exception:
                        pass
        return None
    except Exception:
        return None

class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('BANANA2 (Gemini 3.0) 配置')
        self.setFixedSize(520, 540)  # 增加高度以容纳模型选择
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)
        
        # API 密钥
        lay.addWidget(QLabel('API 密钥 (Token):'))
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        lay.addWidget(self.api_key)
        
        # Base URL
        lay.addWidget(QLabel('Base URL:'))
        self.base_url = QLineEdit()
        self.base_url.setPlaceholderText(DEFAULT_BASE_URL)
        lay.addWidget(self.base_url)
        
        # 模型选择（新增 - 参考 new_api_client.py）
        lay.addWidget(QLabel('模型选择:'))
        self.model = QComboBox()
        self.model.addItems([
            'gemini-3-pro-image-preview',  # 默认
            'gemini-2.5-flash-image',
            'gemini-2.0-flash-exp'
        ])
        lay.addWidget(self.model)
        
        # 输出比例
        lay.addWidget(QLabel('输出比例:'))
        self.size = QComboBox()
        self.size.addItems(['1:1','16:9','9:16','4:3','3:4'])
        lay.addWidget(self.size)
        
        # 分辨率
        lay.addWidget(QLabel('分辨率:'))
        self.resolution = QComboBox()
        self.resolution.addItems(['1K','2K','4K'])
        lay.addWidget(self.resolution)
        
        # 清晰度
        lay.addWidget(QLabel('清晰度 (JPEG 质量):'))
        self.quality = QComboBox()
        self.quality.addItems(['60','80','95','100'])
        lay.addWidget(self.quality)
        
        # 按钮
        row = QHBoxLayout()
        row.addStretch(1)
        b1 = QPushButton('测试连接')
        b2 = QPushButton('保存')
        b3 = QPushButton('关闭')
        b1.clicked.connect(self._test)
        b2.clicked.connect(self._save)
        b3.clicked.connect(self.close)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addWidget(b3)
        lay.addLayout(row)
        
        self.setStyleSheet('QDialog{background:#1a1b1d;color:#dfe3ea;} QLabel{color:#dfe3ea;} QLineEdit,QComboBox{background:#0c0d0e;color:#ffffff;border:1px solid #2a2d31;border-radius:6px;padding:6px;} QPushButton{background:#0c0d0e;color:#cfd3da;border:1px solid #2a2d31;border-radius:6px;padding:6px 12px;} QPushButton:hover{background:#181c22;}')
        self._load()

    def _load(self):
        cfg = get_config()
        self.api_key.setText(cfg.get('api_key',''))
        self.base_url.setText(cfg.get('base_url', DEFAULT_BASE_URL))
        
        def set_combo(cb: QComboBox, val: str):
            i = cb.findText(val)
            if i >= 0:
                cb.setCurrentIndex(i)
        
        # 加载模型配置（新增）
        set_combo(self.model, cfg.get('model', DEFAULT_MODEL))
        set_combo(self.size, cfg.get('size','1:1'))
        set_combo(self.resolution, cfg.get('resolution','1K'))
        set_combo(self.quality, str(cfg.get('quality','80')))

    def _test(self):
        """测试API连接 - 参考 new_api_client.py 的实现"""
        api_key = self.api_key.text().strip()
        base_url = (self.base_url.text().strip() or DEFAULT_BASE_URL).rstrip('/')
        model = self.model.currentText()  # 使用用户选择的模型
        
        if not api_key:
            QMessageBox.critical(self, '测试连接', '缺少 API Key')
            return
        
        # 使用 generateContent 端点测试（参考 new_api_client.py）
        url = f"{base_url}/models/{model}:generateContent"
        
        try:
            import requests
            
            # 构造测试请求（最小化payload）
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }
            
            payload = {
                'contents': [{'parts': [{'text': 'test'}]}],
                'generationConfig': {'responseModalities': ['TEXT']}
            }
            
            print(f"[BANANA2配置] 测试URL: {url}")
            print(f"[BANANA2配置] 测试模型: {model}")
            
            # 创建session并禁用代理（参考 new_api_client.py）
            session = requests.Session()
            session.trust_env = False  # 不使用系统代理
            
            response = session.post(
                url,
                json=payload,
                headers=headers,
                timeout=10,
                proxies={'http': None, 'https': None}
            )
            
            print(f"[BANANA2配置] 响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                QMessageBox.information(
                    self, 
                    '测试连接', 
                    f'✅ 连接成功\n\n模型: {model}\n端点: {base_url}\n\n可以正常使用！'
                )
            else:
                error_text = response.text[:300] if response.text else ''
                print(f"[BANANA2配置] 错误响应: {error_text}")
                QMessageBox.critical(
                    self, 
                    '测试连接', 
                    f'❌ HTTP {response.status_code}\n\n模型: {model}\n\n错误信息:\n{error_text}'
                )
        
        except ImportError:
            # 如果没有 requests 库，回退到 urllib
            print("[BANANA2配置] requests未安装，使用urllib")
            try:
                # 使用 POST 请求测试 generateContent 端点
                test_payload = {
                    'contents': [{'parts': [{'text': 'test'}]}],
                    'generationConfig': {'responseModalities': ['TEXT']}
                }
                data = json.dumps(test_payload).encode('utf-8')
                
                req = urllib.request.Request(url, data=data, method='POST')
                req.add_header('Authorization', f'Bearer {api_key}')
                req.add_header('Content-Type', 'application/json')
                
                with urllib.request.urlopen(req, timeout=10) as resp:
                    code = getattr(resp, 'status', 200)
                
                if 200 <= code < 300:
                    QMessageBox.information(
                        self, 
                        '测试连接', 
                        f'✅ 连接成功（urllib模式）\n\n模型: {model}\n\n建议安装requests库以获得更好的性能'
                    )
                else:
                    QMessageBox.critical(self, '测试连接', f'❌ HTTP {code}')
                    
            except urllib.error.HTTPError as e:
                try:
                    txt = e.read().decode('utf-8', errors='ignore')
                except Exception:
                    txt = str(e)
                print(f"[BANANA2配置] urllib错误: {e.code}, {txt[:200]}")
                QMessageBox.critical(self, '测试连接', f'❌ HTTP {e.code}\n\n{txt[:180]}')
            except Exception as e:
                print(f"[BANANA2配置] urllib异常: {e}")
                QMessageBox.critical(self, '测试连接', f'❌ {str(e)[:180]}')
        
        except requests.exceptions.Timeout:
            QMessageBox.critical(self, '测试连接', '❌ 请求超时\n\n请检查:\n1. 网络连接\n2. Base URL是否正确\n3. 是否需要代理')
        except requests.exceptions.ConnectionError as e:
            print(f"[BANANA2配置] 连接错误: {e}")
            QMessageBox.critical(self, '测试连接', f'❌ 连接失败\n\n请检查:\n1. Base URL: {base_url}\n2. 网络连接\n3. 防火墙设置\n\n错误: {str(e)[:100]}')
        except Exception as e:
            print(f"[BANANA2配置] 测试异常: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, '测试连接', f'❌ {str(e)[:180]}')

    def _save(self):
        """保存配置 - 包含模型选择"""
        cfg = {
            'api_key': self.api_key.text().strip(),
            'base_url': (self.base_url.text().strip() or DEFAULT_BASE_URL).rstrip('/'),
            'model': self.model.currentText(),  # 保存用户选择的模型
            'size': self.size.currentText(),
            'resolution': self.resolution.currentText(),
            'quality': self.quality.currentText(),
        }
        try:
            path = _json_path('gemini30.json')
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            
            print(f"[BANANA2配置] 已保存配置:")
            print(f"  - 模型: {cfg['model']}")
            print(f"  - Base URL: {cfg['base_url']}")
            print(f"  - 分辨率: {cfg['resolution']}")
            print(f"  - 比例: {cfg['size']}")
            print(f"  - 质量: {cfg['quality']}")
            
            QMessageBox.information(
                self, 
                '保存成功', 
                f'✅ 配置已保存\n\n模型: {cfg["model"]}\n分辨率: {cfg["resolution"]}\n比例: {cfg["size"]}\n\n配置文件:\n{path}'
            )
        except Exception as e:
            print(f"[BANANA2配置] 保存失败: {e}")
            QMessageBox.critical(self, '保存失败', f'❌ {str(e)[:200]}')
