from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout, QPushButton, QMessageBox, QComboBox
from PySide6.QtGui import QIntValidator
from PySide6.QtCore import Qt, QSettings, QTimer
import urllib.request
import urllib.error
import urllib.parse
import json
import os
import sys
import threading


def _get_app_root():
    """获取应用根目录，兼容EXE打包后的情况"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def _get_json_path():
    """获取hailuo02.json配置文件路径"""
    json_dir = os.path.join(_get_app_root(), 'json')
    os.makedirs(json_dir, exist_ok=True)
    return os.path.join(json_dir, 'hailuo02.json')


def load_config():
    """从json/hailuo02.json读取配置，如果不存在则返回默认值"""
    try:
        json_path = _get_json_path()
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config
    except Exception as e:
        print(f'[Hailuo02] 读取配置文件失败: {e}', flush=True)
    
    return {
        'api_key': '',
        'base_url': '',
        'model': 'MiniMax-Hailuo-02',
        'aspect_ratio': '16:9',
        'resolution': '1080P',
        'duration': '10'
    }


def save_config(config):
    """保存配置到json/hailuo02.json"""
    try:
        json_path = _get_json_path()
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f'[Hailuo02] 配置已保存到: {json_path}', flush=True)
        return True
    except Exception as e:
        print(f'[Hailuo02] 保存配置文件失败: {e}', flush=True)
        return False


class ConfigDialog(QDialog):
    def __init__(self, parent=None, language='zh'):
        super().__init__(parent)
        self._lang = language
        
        # 多语言文本
        self._texts = {
            'zh': {
                'title': '海螺02 (Hailuo) 配置',
                'api_key': 'API Key:',
                'base_url': 'Base URL:',
                'model': '模型:',
                'aspect_ratio': '画幅比例:',
                'resolution': '分辨率 (Resolution):',
                'duration': '时长 (秒):',
                'test': '测试连接',
                'cancel': '取消',
                'save': '保存',
                'test_title': '测试连接',
                'fill_base_url': '请填写 Base URL',
                'fill_api_key': '请填写 API Key',
                'connection_success': '✓ 连接成功！',
                'status_code': '状态码',
                'model_label': '模型',
                'ratio_label': '画幅比例',
                'resolution_label': '分辨率',
                'duration_label': '时长',
                'seconds': '秒',
                'task_id': '任务ID',
                'server_ok': '✓ 服务端响应正常，可以开始生成视频',
                'message': '消息',
                'auth_failed': '✗ 鉴权失败',
                'check_api_key': '请检查 API Key 是否正确',
                'error_info': '错误信息',
                'response': '响应',
                'request_failed': '✗ 请求失败',
                'error': '错误',
                'network_failed': '✗ 网络连接失败',
                'check_network': '请检查网络连接和 Base URL 是否正确',
                'save_success': '保存成功',
                'save_failed': '保存失败',
                'config_saved': '海螺02配置已保存到:\njson/hailuo02.json\n\n生成视频时将自动使用此配置文件',
                'config_save_failed': '配置文件保存失败，请检查文件权限'
            },
            'en': {
                'title': 'Hailuo02 Configuration',
                'api_key': 'API Key:',
                'base_url': 'Base URL:',
                'model': 'Model:',
                'aspect_ratio': 'Aspect Ratio:',
                'resolution': 'Resolution:',
                'duration': 'Duration (seconds):',
                'test': 'Test Connection',
                'cancel': 'Cancel',
                'save': 'Save',
                'test_title': 'Test Connection',
                'fill_base_url': 'Please fill in Base URL',
                'fill_api_key': 'Please fill in API Key',
                'connection_success': '✓ Connection Successful!',
                'status_code': 'Status Code',
                'model_label': 'Model',
                'ratio_label': 'Aspect Ratio',
                'resolution_label': 'Resolution',
                'duration_label': 'Duration',
                'seconds': 'seconds',
                'task_id': 'Task ID',
                'server_ok': '✓ Server response OK, ready to generate videos',
                'message': 'Message',
                'auth_failed': '✗ Authentication Failed',
                'check_api_key': 'Please check if API Key is correct',
                'error_info': 'Error Info',
                'response': 'Response',
                'request_failed': '✗ Request Failed',
                'error': 'Error',
                'network_failed': '✗ Network Connection Failed',
                'check_network': 'Please check network connection and Base URL',
                'save_success': 'Save Successful',
                'save_failed': 'Save Failed',
                'config_saved': 'Hailuo02 configuration saved to:\njson/hailuo02.json\n\nThis config file will be used automatically when generating videos',
                'config_save_failed': 'Failed to save config file, please check file permissions'
            }
        }
        
        self.t = self._texts.get(self._lang, self._texts['zh'])
        self.setWindowTitle(self.t['title'])
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 创建标签
        self.lbl_api_key = QLabel(self.t['api_key'])
        self.lbl_base_url = QLabel(self.t['base_url'])
        self.lbl_model = QLabel(self.t['model'])
        self.lbl_aspect_ratio = QLabel(self.t['aspect_ratio'])
        self.lbl_resolution = QLabel(self.t['resolution'])
        self.lbl_duration = QLabel(self.t['duration'])
        
        layout.addWidget(self.lbl_api_key)
        self.api_key = QLineEdit()
        layout.addWidget(self.api_key)

        layout.addWidget(self.lbl_base_url)
        self.base_url = QLineEdit()
        layout.addWidget(self.base_url)

        layout.addWidget(self.lbl_model)
        self.model = QLineEdit()
        self.model.setPlaceholderText("MiniMax-Hailuo-02")
        layout.addWidget(self.model)

        layout.addWidget(self.lbl_aspect_ratio)
        self.aspect_ratio = QComboBox()
        # 参考 API 文档支持的比例 (Assuming similar to Jimeng/Standard)
        self.aspect_ratio.addItems(["16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "9:21"])
        layout.addWidget(self.aspect_ratio)

        layout.addWidget(self.lbl_resolution)
        self.resolution = QComboBox()
        self.resolution.addItems(["1080P", "720P"])
        layout.addWidget(self.resolution)

        layout.addWidget(self.lbl_duration)
        self.duration = QComboBox()
        self.duration.addItems(["6", "10"])
        layout.addWidget(self.duration)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btn_test = QPushButton(self.t['test'])
        btn_cancel = QPushButton(self.t['cancel'])
        btn_ok = QPushButton(self.t['save'])
        btn_test.clicked.connect(self._test_connection)
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self.accept)
        btns.addWidget(btn_test)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

        # 优先从json/hailuo02.json读取配置
        config = load_config()
        
        # 应用配置到界面
        self.api_key.setText(config.get('api_key', ''))
        self.base_url.setText(config.get('base_url', ''))
        self.model.setText(config.get('model', 'MiniMax-Hailuo-02'))
        self.aspect_ratio.setCurrentText(str(config.get('aspect_ratio', '16:9')))
        self.resolution.setCurrentText(str(config.get('resolution', '1080P')))
        duration_val = str(config.get('duration', '10'))
        if duration_val not in ('6', '10'):
            duration_val = '10'
        idx = self.duration.findText(duration_val)
        if idx >= 0:
            self.duration.setCurrentIndex(idx)

        self.setStyleSheet(
            """
            QDialog { background: #1a1b1d; color: #dfe3ea; }
            QLineEdit { background: #0c0d0e; color: #ffffff; border: 1px solid #2a2d31; border-radius: 6px; padding: 6px; }
            QComboBox { background: #0c0d0e; color: #ffffff; border: 1px solid #2a2d31; border-radius: 6px; padding: 6px; }
            QPushButton { background: #0c0d0e; color: #cfd3da; border: 1px solid #2a2d31; border-radius: 6px; padding: 6px 12px; }
            QPushButton:hover { background: #181c22; }
            """
        )

    def _test_connection(self):
        base = (self.base_url.text() or "").strip()
        token = (self.api_key.text() or "").strip()
        if not base:
            parent = self if self.isVisible() else None
            QMessageBox.warning(parent, self.t['test_title'], self.t['fill_base_url'])
            return
        if not token:
            parent = self if self.isVisible() else None
            QMessageBox.warning(parent, self.t['test_title'], self.t['fill_api_key'])
            return
            
        base = base.rstrip('/ ,')
        if base.endswith('/v1'):
            root = base[:-3]
        else:
            root = base
        endpoint = root + '/minimax/v1/video_generation'
        
        model = self.model.text() or "MiniMax-Hailuo-02"
        ratio = self.aspect_ratio.currentText()
        resolution = self.resolution.currentText()
        try:
            dval = int(self.duration.currentText() or "10")
        except Exception:
            dval = 10
        if dval not in (6, 10):
            dval = 10
            
        # Minimax/Hailuo payload
        payload = {
            'model': model,
            'prompt': 'video', # 测试 prompt
            'aspect_ratio': ratio,
            # 'resolution': resolution, # Minimax 这里的参数可能不同，暂且保留
            # Minimax 实际上可能不需要 resolution，而是根据 ratio
            # 但 VectorEngine 可能做了封装。Jimeng 有 size。
            # 我们保留它，多余的参数通常会被忽略
            'duration': dval
        }
        
        try:
            print(f"[HAILUO02 TEST] base= `{base}`  | token_len={len(token)}", flush=True)
            print(f"[HAILUO02 TEST] endpoint= `{endpoint}`", flush=True)
            print(f"[HAILUO02 TEST] payload= {json.dumps(payload, ensure_ascii=False)}", flush=True)
        except Exception:
            pass
            
        def worker():
            def show_box(kind: str, text: str):
                try:
                    parent = self if getattr(self, 'isVisible', lambda: False)() else None
                except Exception:
                    parent = None
                if kind == 'info':
                    QTimer.singleShot(0, lambda: QMessageBox.information(parent, self.t['test_title'], text))
                elif kind == 'warn':
                    QTimer.singleShot(0, lambda: QMessageBox.warning(parent, self.t['test_title'], text))
                else:
                    QTimer.singleShot(0, lambda: QMessageBox.critical(parent, self.t['test_title'], text))
            try:
                print(f"[HAILUO02 TEST] -> POST `{endpoint}`", flush=True)
            except Exception:
                pass
            try:
                req = urllib.request.Request(
                    endpoint,
                    data=json.dumps(payload).encode('utf-8'),
                    headers={
                        'Accept': 'application/json',
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + token
                    },
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=120) as r:
                    status = getattr(r, 'status', 200)
                    txt = r.read().decode('utf-8')
                    try:
                        print(f"[HAILUO02 TEST] <- HTTP {status}", flush=True)
                    except Exception:
                        pass
                
                try:
                    j = json.loads(txt)
                except Exception:
                    j = {'raw': txt}
                
                task_id = j.get('id') or j.get('task_id')
                
                msg_parts = [f'{self.t["connection_success"]}\n']
                msg_parts.append(f'{self.t["status_code"]}: HTTP {status}')
                msg_parts.append(f'{self.t["model_label"]}: {model}')
                
                if task_id:
                    msg_parts.append(f'{self.t["task_id"]}: {task_id}')
                    msg_parts.append(f'\n{self.t["server_ok"]}')
                elif 'message' in j:
                    msg_parts.append(f'{self.t["message"]}: {j.get("message")}')
                
                msg = '\n'.join(msg_parts)
                show_box('info', msg)
            except urllib.error.HTTPError as e:
                detail = ''
                try:
                    detail = e.read().decode('utf-8')
                except Exception:
                    detail = ''
                
                print(f"[HAILUO02 TEST] HTTP Error {e.code}: {e.reason}", flush=True)
                print(f"[HAILUO02 TEST] Error Detail: {detail}", flush=True)

                if e.code in (401, 403):
                    msg = f'{self.t["auth_failed"]} (HTTP {e.code})\n\n{self.t["check_api_key"]}'
                    show_box('warn', msg)
                else:
                    msg = f'{self.t["request_failed"]} (HTTP {e.code})'
                    if detail:
                         msg += f'\n\n{self.t["response"]}: {detail[:500]}'
                    show_box('crit', msg)
            except Exception as e:
                msg = f'{self.t["network_failed"]}\n\n{self.t["error"]}: {str(e)}\n\n{self.t["check_network"]}'
                show_box('crit', msg)
        threading.Thread(target=worker, daemon=True).start()

    def accept(self):
        base = (self.base_url.text() or "").strip()
        token = (self.api_key.text() or "").strip()
        
        if base.startswith("sk-"):
             QMessageBox.warning(self, self.t['title'], "Base URL 不能以 'sk-' 开头，这看起来像是 API Key。\n请修正后再保存。")
             return

        try:
            d = int(self.duration.currentText() or "10")
        except Exception:
            d = 10
        if d not in (6, 10):
            d = 10
        
        config = {
            'api_key': self.api_key.text().strip(),
            'base_url': self.base_url.text().strip(),
            'model': self.model.text() or 'MiniMax-Hailuo-02',
            'aspect_ratio': self.aspect_ratio.currentText(),
            'resolution': self.resolution.currentText(),
            'duration': str(d)
        }
        
        if save_config(config):
            QMessageBox.information(self, self.t['save_success'], self.t['config_saved'])
            super().accept()
        else:
            QMessageBox.warning(self, self.t['save_failed'], self.t['config_save_failed'])


def create_task(payload: dict) -> dict:
    """
    创建海螺02视频生成任务
    payload: {
        'base_url': str,
        'api_key': str,
        'model': str,
        'prompt': str,
        'aspect_ratio': str,
        'duration': int,
        'first_frame_image': str (optional, base64 data url),
        'last_frame_image': str (optional, base64 data url)
    }
    """
    base_url = (payload.get('base_url') or '').rstrip('/')
    api_key = payload.get('api_key') or ''
    
    if base_url.endswith('/v1'):
        root = base_url[:-3]
    else:
        root = base_url
    url = f"{root}/minimax/v1/video_generation"

    # 构造请求体
    body = {
        "model": payload.get("model", "MiniMax-Hailuo-02"),
        "prompt": payload.get("prompt", ""),
        "duration": int(payload.get("duration", 6)),
        "aspect_ratio": payload.get("aspect_ratio", "16:9"),
    }
    
    # 添加首尾帧支持
    if payload.get("first_frame_image"):
        body["first_frame_image"] = payload["first_frame_image"]
    if payload.get("last_frame_image"):
        body["last_frame_image"] = payload["last_frame_image"]

    print(f"[Hailuo02] POST {url}", flush=True)
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': f'Bearer {api_key}'
            },
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode('utf-8'))
            return data
    except urllib.error.HTTPError as e:
        print(f"[Hailuo02] HTTP Error {e.code}: {e.reason}", flush=True)
        try:
            err_body = e.read().decode('utf-8')
            print(f"[Hailuo02] Error Body: {err_body}", flush=True)
            return {"error": True, "message": f"HTTP {e.code}: {e.reason}", "details": err_body}
        except:
            return {"error": True, "message": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        print(f"[Hailuo02] Connection Error: {e}", flush=True)
        return {"error": True, "message": str(e)}


def query_task(task_id: str, extra: dict = None) -> dict:
    """
    查询任务状态
    extra: { 'base_url': ..., 'api_key': ... }
    """
    extra = extra or {}
    base_url = (extra.get('base_url') or '').rstrip('/')
    api_key = extra.get('api_key') or ''
    
    if base_url.endswith('/v1'):
        root = base_url[:-3]
    else:
        root = base_url
    url = f"{root}/minimax/v1/query/video_generation?task_id={urllib.parse.quote(str(task_id))}"
        
    try:
        req = urllib.request.Request(
            url,
            headers={
                'Accept': 'application/json',
                'Authorization': f'Bearer {api_key}'
            },
            method='GET'
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode('utf-8'))
            return data
    except urllib.error.HTTPError as e:
        return {"error": True, "message": f"HTTP {e.code}"}
    except Exception as e:
        return {"error": True, "message": str(e)}
