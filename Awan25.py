from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout, QPushButton, QMessageBox, QComboBox, QCheckBox
from PySide6.QtGui import QIntValidator
from PySide6.QtCore import Qt, QSettings, QTimer
import urllib.request
import urllib.error
import json
import os
import sys


def _get_app_root():
    """获取应用根目录，兼容EXE打包后的情况"""
    if getattr(sys, 'frozen', False):
        # 打包成EXE后，使用可执行文件所在目录
        return os.path.dirname(sys.executable)
    else:
        # 开发环境，使用脚本所在目录
        return os.path.dirname(os.path.abspath(__file__))


def _get_json_path():
    """获取wan25.json配置文件路径"""
    json_dir = os.path.join(_get_app_root(), 'json')
    os.makedirs(json_dir, exist_ok=True)
    return os.path.join(json_dir, 'wan25.json')


def load_config():
    """从json/wan25.json读取配置，如果不存在则返回默认值"""
    try:
        json_path = _get_json_path()
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 确保水印默认为开启状态
                if 'watermark' not in config or config['watermark'] == 'false':
                    config['watermark'] = 'true'
                return config
    except Exception as e:
        print(f'[Wan25] 读取配置文件失败: {e}', flush=True)
    
    # 返回默认配置（水印默认开启）
    return {
        'api_key': '',
        'base_url': '',
        'model': '',
        'resolution': '1080P',
        'duration': '10',
        'prompt_extend': 'true',
        'watermark': 'true',
        'audio': 'true'
    }


def save_config(config):
    """保存配置到json/wan25.json"""
    try:
        json_path = _get_json_path()
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f'[Wan25] 配置已保存到: {json_path}', flush=True)
        return True
    except Exception as e:
        print(f'[Wan25] 保存配置文件失败: {e}', flush=True)
        return False


class ConfigDialog(QDialog):
    def __init__(self, parent=None, language='zh'):
        super().__init__(parent)
        self._lang = language
        
        # 多语言文本
        self._texts = {
            'zh': {
                'title': 'Wan2.5 配置',
                'api_key': 'API Key:',
                'base_url': 'Base URL:',
                'model': '模型:',
                'resolution': '分辨率:',
                'duration': '时长 (秒):',
                'prompt_extend': '启用提示词扩展',
                'watermark': '添加水印',
                'audio': '启用音频',
                'test': '测试连接',
                'cancel': '取消',
                'save': '保存',
                'test_title': '测试连接',
                'fill_base_url': '请填写 Base URL',
                'fill_api_key': '请填写 API Key',
                'connection_success': '✓ 连接成功！',
                'status_code': '状态码',
                'model_label': '模型',
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
                'config_saved': '万象2.5 配置已保存到:\njson/wan25.json\n\n生成视频时将自动使用此配置文件',
                'config_save_failed': '配置文件保存失败，请检查文件权限',
                'watermark_locked': '测试阶段，水印无法取消'
            },
            'en': {
                'title': 'Wan2.5 Configuration',
                'api_key': 'API Key:',
                'base_url': 'Base URL:',
                'model': 'Model:',
                'resolution': 'Resolution:',
                'duration': 'Duration (seconds):',
                'prompt_extend': 'Enable Prompt Extension',
                'watermark': 'Add Watermark',
                'audio': 'Enable Audio',
                'test': 'Test Connection',
                'cancel': 'Cancel',
                'save': 'Save',
                'test_title': 'Test Connection',
                'fill_base_url': 'Please fill in Base URL',
                'fill_api_key': 'Please fill in API Key',
                'connection_success': '✓ Connection Successful!',
                'status_code': 'Status Code',
                'model_label': 'Model',
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
                'config_saved': 'Wan2.5 configuration saved to:\njson/wan25.json\n\nThis config file will be used automatically when generating videos',
                'config_save_failed': 'Failed to save config file, please check file permissions',
                'watermark_locked': 'Watermark cannot be disabled during testing phase'
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
        layout.addWidget(self.model)

        layout.addWidget(self.lbl_resolution)
        self.resolution = QComboBox()
        self.resolution.addItems(["720P", "1080P", "2K", "4K"])
        layout.addWidget(self.resolution)

        layout.addWidget(self.lbl_duration)
        self.duration = QLineEdit()
        self.duration.setPlaceholderText("10")
        self.duration.setValidator(QIntValidator(1, 120, self))
        layout.addWidget(self.duration)

        self.prompt_extend = QCheckBox(self.t['prompt_extend'])
        self.watermark = QCheckBox(self.t['watermark'])
        self.audio = QCheckBox(self.t['audio'])
        
        # 水印复选框点击时的处理
        self.watermark.clicked.connect(self._on_watermark_clicked)
        
        layout.addWidget(self.prompt_extend)
        layout.addWidget(self.watermark)
        layout.addWidget(self.audio)

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

        # 优先从json/wan25.json读取配置，如果不存在则从QSettings读取（兼容旧版）
        config = load_config()
        
        # 如果JSON配置为空，尝试从QSettings迁移
        s = QSettings("GhostOS", "App")
        if not config.get('api_key'):
            config['api_key'] = s.value("providers/wan25/api_key", "")
        if not config.get('base_url'):
            config['base_url'] = s.value("providers/wan25/base_url", "")
        if not config.get('model'):
            config['model'] = s.value("providers/wan25/model", "")
        
        # 应用配置到界面
        self.api_key.setText(config.get('api_key', ''))
        self.base_url.setText(config.get('base_url', ''))
        self.model.setText(config.get('model', ''))
        self.resolution.setCurrentText(str(config.get('resolution', '1080P')))
        self.duration.setText(str(config.get('duration', '10')))
        
        # 处理布尔值配置（水印强制开启）
        pe_raw = str(config.get('prompt_extend', 'true')).strip().lower()
        wm_raw = str(config.get('watermark', 'true')).strip().lower()
        au_raw = str(config.get('audio', 'true')).strip().lower()
        self.prompt_extend.setChecked(pe_raw in ("true", "1", "yes", "on"))
        # 水印强制开启，不允许关闭
        self.watermark.setChecked(True)
        self.audio.setChecked(au_raw in ("true", "1", "yes", "on"))

        self.setStyleSheet(
            """
            QDialog { background: #1a1b1d; color: #dfe3ea; }
            QLineEdit { background: #0c0d0e; color: #ffffff; border: 1px solid #2a2d31; border-radius: 6px; padding: 6px; }
            QComboBox { background: #0c0d0e; color: #ffffff; border: 1px solid #2a2d31; border-radius: 6px; padding: 6px; }
            QCheckBox { color: #dfe3ea; }
            QPushButton { background: #0c0d0e; color: #cfd3da; border: 1px solid #2a2d31; border-radius: 6px; padding: 6px 12px; }
            QPushButton:hover { background: #181c22; }
            """
        )

    def _on_watermark_clicked(self, checked):
        """处理水印复选框点击事件，强制保持勾选状态"""
        if not checked:
            # 如果用户尝试取消勾选，弹出提示并恢复勾选状态
            QMessageBox.information(self, self.t['title'], self.t['watermark_locked'])
            # 强制恢复勾选状态
            self.watermark.setChecked(True)

    def _test_connection(self):
        s = QSettings("GhostOS", "App")
        base = (self.base_url.text() or s.value("providers/wan25/base_url", "") or "").strip()
        token = (self.api_key.text() or s.value("providers/wan25/api_key", "") or "").strip()
        if not base:
            parent = self if self.isVisible() else None
            QMessageBox.warning(parent, self.t['test_title'], self.t['fill_base_url'])
            return
        if not token:
            parent = self if self.isVisible() else None
            QMessageBox.warning(parent, self.t['test_title'], self.t['fill_api_key'])
            return
        # 规范化 Base，避免重复 /v1 尾缀导致路径错误
        base = base.rstrip('/ ,')
        btrim = base.rstrip('/')
        if btrim.endswith('/v1'):
            try:
                # 去掉末尾的 /v1 以与实际视频生成端点对齐
                base = btrim[: btrim.rfind('/v1')]
            except Exception:
                base = btrim
        # 与生成逻辑一致，使用 video-synthesis 端点做最小化 POST
        endpoint = base + '/alibailian/api/v1/services/aigc/video-generation/video-synthesis'
        # 构造最小负载，使用当前配置的模型与参数
        model = (self.model.text() or s.value("providers/wan25/model", "wan2.5-i2v-preview") or "wan2.5-i2v-preview")
        resolution = self.resolution.currentText() or str(s.value('providers/wan25/resolution', '1080P') or '1080P')
        try:
            dval = int(self.duration.text()) if self.duration.text() else int(str(s.value('providers/wan25/duration', 10)))
        except Exception:
            dval = 10
        payload = {
            'model': model,
            'input': { 'prompt': 'test-connection ping' },
            'parameters': {
                'resolution': resolution,
                'duration': dval,
                'prompt_extend': bool(self.prompt_extend.isChecked()),
                'watermark': bool(self.watermark.isChecked()),
                'audio': bool(self.audio.isChecked())
            }
        }
        try:
            print(f"[WAN25 TEST] base= `{base}`  | token_len={len(token)}", flush=True)
            print(f"[WAN25 TEST] endpoint= `{endpoint}`", flush=True)
            print(f"[WAN25 TEST] payload= {json.dumps(payload, ensure_ascii=False)}", flush=True)
        except Exception:
            pass
        def worker():
            # 封装统一弹窗显示，确保父对话框不可见时也能弹出
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
            import traceback
            try:
                print(f"[WAN25 TEST] -> POST `{endpoint}`", flush=True)
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
                with urllib.request.urlopen(req, timeout=20) as r:
                    status = getattr(r, 'status', 200)
                    headers = {}
                    try:
                        headers = dict(r.headers.items())
                    except Exception:
                        headers = {}
                    txt = r.read().decode('utf-8')
                    try:
                        print(f"[WAN25 TEST] <- HTTP {status} | headers={json.dumps(headers, ensure_ascii=False)[:300]}", flush=True)
                        print(f"[WAN25 TEST] resp_len={len(txt)} | body_head={txt[:400]}", flush=True)
                    except Exception:
                        pass
                try:
                    j = json.loads(txt)
                except Exception:
                    j = {'raw': txt}
                task_id = (
                    j.get('task_id') or j.get('id') or
                    (j.get('data', {}) if isinstance(j.get('data', {}), dict) else {}).get('task_id')
                )
                
                # 构建更清晰的返回信息
                msg_parts = [f'{self.t["connection_success"]}\n']
                msg_parts.append(f'{self.t["status_code"]}: HTTP {status}')
                msg_parts.append(f'{self.t["model_label"]}: {model}')
                msg_parts.append(f'{self.t["resolution_label"]}: {resolution}')
                msg_parts.append(f'{self.t["duration_label"]}: {dval}{self.t["seconds"]}')
                
                if task_id:
                    msg_parts.append(f'{self.t["task_id"]}: {task_id}')
                
                # 尝试解析响应中的关键信息
                if 'output' in j:
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
                hdrs = {}
                try:
                    if hasattr(e, 'headers') and e.headers:
                        hdrs = dict(e.headers.items())
                except Exception:
                    hdrs = {}
                try:
                    print(f"[WAN25 TEST] HTTPError code={e.code} reason={getattr(e,'reason', '')} url= `{endpoint}`", flush=True)
                    print(f"[WAN25 TEST] headers={json.dumps(hdrs, ensure_ascii=False)[:300]}", flush=True)
                    print(f"[WAN25 TEST] body_head={detail[:400]}", flush=True)
                except Exception:
                    pass
                # 鉴权错误：明确提示Key问题
                if e.code in (401, 403):
                    msg = f'{self.t["auth_failed"]} (HTTP {e.code})\n\n{self.t["check_api_key"]}'
                    if detail:
                        try:
                            err_json = json.loads(detail)
                            if 'message' in err_json:
                                msg += f'\n\n{self.t["error_info"]}: {err_json["message"]}'
                        except:
                            if len(detail) > 0:
                                msg += f'\n\n{self.t["response"]}: {detail[:200]}'
                    show_box('warn', msg)
                else:
                    msg = f'{self.t["request_failed"]} (HTTP {e.code})'
                    if detail:
                        try:
                            err_json = json.loads(detail)
                            if 'message' in err_json:
                                msg += f'\n\n{self.t["error_info"]}: {err_json["message"]}'
                            elif 'error' in err_json:
                                msg += f'\n\n{self.t["error"]}: {err_json["error"]}'
                        except:
                            if len(detail) > 0:
                                msg += f'\n\n{self.t["response"]}: {detail[:200]}'
                    show_box('crit', msg)
            except Exception as e:
                try:
                    print(f"[WAN25 TEST] Exception: {e}", flush=True)
                    print(traceback.format_exc(), flush=True)
                except Exception:
                    pass
                msg = f'{self.t["network_failed"]}\n\n{self.t["error"]}: {str(e)}\n\n{self.t["check_network"]}'
                show_box('crit', msg)
        import threading
        threading.Thread(target=worker, daemon=True).start()

    def accept(self):
        # 准备配置数据
        try:
            d = int(self.duration.text()) if self.duration.text() else 10
        except Exception:
            d = 10
        
        config = {
            'api_key': self.api_key.text(),
            'base_url': self.base_url.text(),
            'model': self.model.text(),
            'resolution': self.resolution.currentText(),
            'duration': str(d),
            'prompt_extend': 'true' if self.prompt_extend.isChecked() else 'false',
            'watermark': 'true',  # 强制保存为true，测试阶段水印无法取消
            'audio': 'true' if self.audio.isChecked() else 'false'
        }
        
        # 保存到json/wan25.json
        if save_config(config):
            QMessageBox.information(self, self.t['save_success'], self.t['config_saved'])
        else:
            QMessageBox.warning(self, self.t['save_failed'], self.t['config_save_failed'])
        
        # 同时保存到QSettings（保持向后兼容）
        s = QSettings("GhostOS", "App")
        s.setValue("providers/wan25/api_key", config['api_key'])
        s.setValue("providers/wan25/base_url", config['base_url'])
        s.setValue("providers/wan25/model", config['model'])
        s.setValue("providers/wan25/resolution", config['resolution'])
        s.setValue("providers/wan25/duration", d)
        s.setValue("providers/wan25/prompt_extend", self.prompt_extend.isChecked())
        s.setValue("providers/wan25/watermark", True)  # 强制保存为True
        s.setValue("providers/wan25/audio", self.audio.isChecked())
        
        super().accept()