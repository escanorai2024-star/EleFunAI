from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout, QPushButton, QMessageBox, QComboBox
from PySide6.QtGui import QIntValidator
from PySide6.QtCore import Qt, QSettings, QTimer
import urllib.request
import urllib.error
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
    """获取jimeng.json配置文件路径"""
    json_dir = os.path.join(_get_app_root(), 'json')
    os.makedirs(json_dir, exist_ok=True)
    return os.path.join(json_dir, 'jimeng.json')


def load_config():
    """从json/jimeng.json读取配置，如果不存在则返回默认值"""
    try:
        json_path = _get_json_path()
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config
    except Exception as e:
        print(f'[Jimeng] 读取配置文件失败: {e}', flush=True)
    
    return {
        'api_key': '',
        'base_url': '',
        'model': 'jimeng-video-3.0',
        'aspect_ratio': '16:9',
        'duration': '10',
        'size': '1080P'
    }


def save_config(config):
    """保存配置到json/jimeng.json"""
    try:
        json_path = _get_json_path()
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f'[Jimeng] 配置已保存到: {json_path}', flush=True)
        return True
    except Exception as e:
        print(f'[Jimeng] 保存配置文件失败: {e}', flush=True)
        return False


class ConfigDialog(QDialog):
    def __init__(self, parent=None, language='zh'):
        super().__init__(parent)
        self._lang = language
        
        # 多语言文本
        self._texts = {
            'zh': {
                'title': '即梦 (Jimeng) 配置',
                'api_key': 'API Key:',
                'base_url': 'Base URL:',
                'model': '模型:',
                'aspect_ratio': '画幅比例:',
                'size': '分辨率 (清晰度):',
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
                'size_label': '分辨率',
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
                'config_saved': '即梦配置已保存到:\njson/jimeng.json\n\n生成视频时将自动使用此配置文件',
                'config_save_failed': '配置文件保存失败，请检查文件权限'
            },
            'en': {
                'title': 'Jimeng Configuration',
                'api_key': 'API Key:',
                'base_url': 'Base URL:',
                'model': 'Model:',
                'aspect_ratio': 'Aspect Ratio:',
                'size': 'Resolution (Size):',
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
                'size_label': 'Resolution',
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
                'config_saved': 'Jimeng configuration saved to:\njson/jimeng.json\n\nThis config file will be used automatically when generating videos',
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
        self.lbl_size = QLabel(self.t['size'])
        self.lbl_duration = QLabel(self.t['duration'])
        
        layout.addWidget(self.lbl_api_key)
        self.api_key = QLineEdit()
        layout.addWidget(self.api_key)

        layout.addWidget(self.lbl_base_url)
        self.base_url = QLineEdit()
        layout.addWidget(self.base_url)

        layout.addWidget(self.lbl_model)
        self.model = QLineEdit()
        self.model.setPlaceholderText("jimeng-video-3.0")
        layout.addWidget(self.model)

        layout.addWidget(self.lbl_aspect_ratio)
        self.aspect_ratio = QComboBox()
        # 参考 API 文档支持的比例
        self.aspect_ratio.addItems(["16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "9:21"])
        layout.addWidget(self.aspect_ratio)

        layout.addWidget(self.lbl_size)
        self.size = QComboBox()
        self.size.addItems(["1080P", "720P"])
        layout.addWidget(self.size)

        layout.addWidget(self.lbl_duration)
        self.duration = QLineEdit()
        self.duration.setPlaceholderText("10")
        self.duration.setValidator(QIntValidator(1, 120, self))
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

        # 优先从json/jimeng.json读取配置
        config = load_config()
        
        # 应用配置到界面
        self.api_key.setText(config.get('api_key', ''))
        self.base_url.setText(config.get('base_url', ''))
        self.model.setText(config.get('model', 'jimeng-video-3.0'))
        self.aspect_ratio.setCurrentText(str(config.get('aspect_ratio', '16:9')))
        self.size.setCurrentText(str(config.get('size', '1080P')))
        self.duration.setText(str(config.get('duration', '5')))

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
            endpoint = base + '/video/create'
        else:
            endpoint = base + '/v1/video/create'
        
        model = self.model.text() or "jimeng-video-3.0"
        # 参考 jimeng_provider.py 的模型映射逻辑
        if model in ("jimeng-videos", "jimeng-video", "jimeng_video", "jimeng-v3"):
            model = "jimeng-video-3.0"
            
        ratio = self.aspect_ratio.currentText()
        size = self.size.currentText()
        try:
            dval = int(self.duration.text()) if self.duration.text() else 10
        except Exception:
            dval = 10
            
        payload = {
            'model': model,
            'prompt': 'video',
            'aspect_ratio': ratio,
            'size': size,
            'images': [],
            'duration': dval
        }
        
        try:
            print(f"[JIMENG TEST] base= `{base}`  | token_len={len(token)}", flush=True)
            print(f"[JIMENG TEST] endpoint= `{endpoint}`", flush=True)
            print(f"[JIMENG TEST] payload= {json.dumps(payload, ensure_ascii=False)}", flush=True)
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
                print(f"[JIMENG TEST] -> POST `{endpoint}`", flush=True)
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
                # 增加超时时间到 120s，参考 jimeng_provider.py
                with urllib.request.urlopen(req, timeout=120) as r:
                    status = getattr(r, 'status', 200)
                    headers = {}
                    try:
                        headers = dict(r.headers.items())
                    except Exception:
                        headers = {}
                    txt = r.read().decode('utf-8')
                    try:
                        print(f"[JIMENG TEST] <- HTTP {status}", flush=True)
                    except Exception:
                        pass
                
                try:
                    j = json.loads(txt)
                except Exception:
                    j = {'raw': txt}
                
                task_id = j.get('id') or j.get('task_id')
                
                # 构建更清晰的返回信息
                msg_parts = [f'{self.t["connection_success"]}\n']
                msg_parts.append(f'{self.t["status_code"]}: HTTP {status}')
                msg_parts.append(f'{self.t["model_label"]}: {model}')
                msg_parts.append(f'{self.t["ratio_label"]}: {ratio}')
                msg_parts.append(f'{self.t["duration_label"]}: {dval}{self.t["seconds"]}')
                
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
                
                print(f"[JIMENG TEST] HTTP Error {e.code}: {e.reason}", flush=True)
                print(f"[JIMENG TEST] Error Detail: {detail}", flush=True)

                if e.code in (401, 403):
                    msg = f'{self.t["auth_failed"]} (HTTP {e.code})\n\n{self.t["check_api_key"]}'
                    show_box('warn', msg)
                else:
                    msg = f'{self.t["request_failed"]} (HTTP {e.code})'
                    if detail:
                         msg += f'\n\n{self.t["response"]}: {detail[:500]}' # 增加显示长度
                    show_box('crit', msg)
            except Exception as e:
                msg = f'{self.t["network_failed"]}\n\n{self.t["error"]}: {str(e)}\n\n{self.t["check_network"]}'
                show_box('crit', msg)
        threading.Thread(target=worker, daemon=True).start()

    def accept(self):
        # 保存前再次检查
        base = (self.base_url.text() or "").strip()
        token = (self.api_key.text() or "").strip()
        
        if base.startswith("sk-"):
             QMessageBox.warning(self, self.t['title'], "Base URL 不能以 'sk-' 开头，这看起来像是 API Key。\n请修正后再保存。")
             return

        try:
            d = int(self.duration.text()) if self.duration.text() else 10
        except Exception:
            d = 10
        
        model = self.model.text() or "jimeng-video-3.0"
        # 参考 jimeng_provider.py 的模型映射逻辑
        if model in ("jimeng-videos", "jimeng-video", "jimeng_video", "jimeng-v3"):
            model = "jimeng-video-3.0"

        config = {
            'api_key': self.api_key.text(),
            'base_url': self.base_url.text(),
            'model': model,
            'aspect_ratio': self.aspect_ratio.currentText(),
            'size': self.size.currentText(),
            'duration': str(d)
        }
        
        if save_config(config):
            QMessageBox.information(self, self.t['save_success'], self.t['config_saved'])
            super().accept()
        else:
            QMessageBox.warning(self, self.t['save_failed'], self.t['config_save_failed'])
