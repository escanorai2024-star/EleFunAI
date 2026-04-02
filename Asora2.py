from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout, QPushButton, QComboBox, QWidget, QMessageBox
from PySide6.QtCore import Qt, QSettings, Signal
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
    """获取sora2.json配置文件路径"""
    json_dir = os.path.join(_get_app_root(), 'json')
    os.makedirs(json_dir, exist_ok=True)
    return os.path.join(json_dir, 'sora2.json')


def load_config():
    """从json/sora2.json读取配置，如果不存在则返回默认值"""
    try:
        json_path = _get_json_path()
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f'[Sora2] 读取配置文件失败: {e}', flush=True)
    
    # 返回默认配置
    return {
        'api_key': '',
        'base_url': 'https://api.vectorengine.ai',
        'model': 'sora-2-all',
        'orientation': 'landscape',
        'size': 'large',
        'width': '',
        'height': '',
        'duration': '15',
        'watermark': 'false'
    }


def save_config(config):
    """保存配置到json/sora2.json"""
    try:
        json_path = _get_json_path()
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f'[Sora2] 配置已保存到: {json_path}', flush=True)
        return True
    except Exception as e:
        print(f'[Sora2] 保存配置文件失败: {e}', flush=True)
        return False


class ConfigDialog(QDialog):
    # 定义信号用于线程安全的消息框显示
    _test_result_signal = Signal(bool, str)  # (success, message)
    
    def __init__(self, parent=None, language='zh'):
        super().__init__(parent)
        self._lang = language
        
        # 多语言文本
        self._texts = {
            'zh': {
                'title': 'Sora2 配置',
                'base_url': 'Base URL',
                'token_placeholder': '输入 Bearer Token',
                'model': '模型',
                'orientation': '方向',
                'resolution_size': '分辨率大小',
                'width_placeholder': '宽度，如1920',
                'height_placeholder': '高度，如1080',
                'duration': '时长（秒）',
                'watermark': '水印',
                'test': '测试连接',
                'cancel': '取消',
                'save': '保存',
                'test_title': '测试连接',
                'fill_base_url': '请填写 Base URL',
                'fill_token': '请填写 Authorization Token',
                'connection_ok': '连接正常',
                'task_id': '任务ID',
                'test_warning': '提示: 这是一个测试任务，可能会产生费用',
                'response': '响应',
                'auth_failed': '鉴权失败',
                'check_token': '请检查 Token 是否有效',
                'request_format_error': '请求格式错误',
                'possible_reasons': '可能的原因：1. API参数不正确 2. Base URL配置错误 3. API版本不兼容',
                'endpoint_reachable': '端点可达，但返回',
                'network_unreachable': '网络不可达或请求失败：',
                'save_success': '保存成功',
                'save_failed': '保存失败',
                'config_saved': 'Sora2 配置已保存到: json/sora2.json，生成视频时将自动使用此配置文件',
                'config_save_failed': '配置文件保存失败，请检查文件权限'
            },
            'en': {
                'title': 'Sora2 Configuration',
                'base_url': 'Base URL',
                'token_placeholder': 'Enter Bearer Token',
                'model': 'Model',
                'orientation': 'Orientation',
                'resolution_size': 'Resolution Size',
                'width_placeholder': 'Width, e.g. 1920',
                'height_placeholder': 'Height, e.g. 1080',
                'duration': 'Duration (seconds)',
                'watermark': 'Watermark',
                'test': 'Test Connection',
                'cancel': 'Cancel',
                'save': 'Save',
                'test_title': 'Test Connection',
                'fill_base_url': 'Please fill in Base URL',
                'fill_token': 'Please fill in Authorization Token',
                'connection_ok': 'Connection OK',
                'task_id': 'Task ID',
                'test_warning': 'Note: This is a test task and may incur charges',
                'response': 'Response',
                'auth_failed': 'Authentication Failed',
                'check_token': 'Please check if Token is valid',
                'request_format_error': 'Request Format Error',
                'possible_reasons': 'Possible reasons: 1. Incorrect API parameters 2. Wrong Base URL configuration 3. API version incompatible',
                'endpoint_reachable': 'Endpoint reachable, but returned',
                'network_unreachable': 'Network unreachable or request failed:',
                'save_success': 'Save Successful',
                'save_failed': 'Save Failed',
                'config_saved': 'Sora2 configuration saved to: json/sora2.json. This config file will be used automatically when generating videos',
                'config_save_failed': 'Failed to save config file, please check file permissions'
            }
        }
        
        self.t = self._texts.get(self._lang, self._texts['zh'])
        self.setWindowTitle(self.t['title'])
        # 使用可调整大小的窗口，提供更大的初始尺寸与最小尺寸
        self.resize(680, 560)
        self.setMinimumSize(520, 420)
        
        # 连接信号到槽函数
        self._test_result_signal.connect(self._show_test_result)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Base URL
        layout.addWidget(QLabel(self.t['base_url']))
        self.base_url = QLineEdit()
        self.base_url.setPlaceholderText("https://api.vectorengine.ai")
        layout.addWidget(self.base_url)

        # Authorization Token (API Key)
        layout.addWidget(QLabel("Authorization Token"))
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText(self.t['token_placeholder'])
        layout.addWidget(self.api_key)

        # 模型
        layout.addWidget(QLabel(self.t['model']))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["sora-2-all", "sora-2-pro-all"])
        layout.addWidget(self.model_combo)

        # 方向
        layout.addWidget(QLabel(self.t['orientation']))
        self.orientation_combo = QComboBox()
        self.orientation_combo.addItems(["portrait", "landscape"])
        self.orientation_combo.setCurrentText("landscape")
        layout.addWidget(self.orientation_combo)

        # 分辨率大小（含自定义尺寸）
        layout.addWidget(QLabel(self.t['resolution_size']))
        self.size_combo = QComboBox()
        self.size_combo.addItems(["small", "medium", "large", "custom"])
        self.size_combo.setCurrentText("large")
        layout.addWidget(self.size_combo)
        # 自定义宽高容器
        self.custom_wh = QWidget()
        wh_row = QHBoxLayout(self.custom_wh)
        wh_row.setContentsMargins(0, 0, 0, 0)
        wh_row.setSpacing(8)
        self.width_edit = QLineEdit(); self.width_edit.setPlaceholderText(self.t['width_placeholder'])
        self.height_edit = QLineEdit(); self.height_edit.setPlaceholderText(self.t['height_placeholder'])
        wh_row.addWidget(self.width_edit)
        wh_row.addWidget(self.height_edit)
        layout.addWidget(self.custom_wh)

        # 时长
        layout.addWidget(QLabel(self.t['duration']))
        self.duration_combo = QComboBox()
        self.duration_combo.addItems(["15", "25"])
        self.duration_combo.setCurrentText("15")
        layout.addWidget(self.duration_combo)

        # 水印
        layout.addWidget(QLabel(self.t['watermark']))
        self.watermark_combo = QComboBox()
        self.watermark_combo.addItems(["false", "true"])
        self.watermark_combo.setCurrentText("false")
        layout.addWidget(self.watermark_combo)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btn_test = QPushButton(self.t['test'])
        btn_test.clicked.connect(self._test_connection)
        btn_cancel = QPushButton(self.t['cancel'])
        btn_ok = QPushButton(self.t['save'])
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self.accept)
        btns.addWidget(btn_test)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

        # 优先从json/sora2.json读取配置，如果不存在则从QSettings读取（兼容旧版）
        config = load_config()
        
        # 如果JSON配置为空，尝试从QSettings迁移
        s = QSettings("GhostOS", "App")
        if not config.get('api_key'):
            config['api_key'] = s.value("providers/sora2/api_key", "")
        if not config.get('base_url') or config['base_url'] == 'https://api.vectorengine.ai':
            stored_url = s.value("providers/sora2/base_url", "https://api.vectorengine.ai")
            if stored_url:
                config['base_url'] = stored_url
        
        # 应用配置到界面
        self.api_key.setText(config.get('api_key', ''))
        self.base_url.setText(config.get('base_url', 'https://api.vectorengine.ai'))
        self.model_combo.setCurrentText(str(config.get('model', 'sora-2-all')))
        self.orientation_combo.setCurrentText(str(config.get('orientation', 'landscape')))
        self.size_combo.setCurrentText(str(config.get('size', 'large')))
        self.width_edit.setText(str(config.get('width', '')))
        self.height_edit.setText(str(config.get('height', '')))
        self.duration_combo.setCurrentText(str(config.get('duration', '15')))
        self.watermark_combo.setCurrentText(str(config.get('watermark', 'false')))

        # 自定义尺寸显示逻辑
        def _toggle_custom(index):
            self.custom_wh.setVisible(self.size_combo.currentText() == "custom")
            if self.size_combo.currentText() == "custom":
                o = self.orientation_combo.currentText() or "landscape"
                if not self.width_edit.text() and not self.height_edit.text():
                    if o == "landscape":
                        self.width_edit.setText("1920"); self.height_edit.setText("1080")
                    else:
                        self.width_edit.setText("1080"); self.height_edit.setText("1920")
        self.size_combo.currentIndexChanged.connect(_toggle_custom)
        self.custom_wh.setVisible(self.size_combo.currentText() == "custom")

        self.setStyleSheet(
            """
            QDialog { background: #1a1b1d; color: #dfe3ea; font-size:14px; }
            QLabel { color: #dfe3ea; }
            QLineEdit, QComboBox { background: #0c0d0e; color: #ffffff; border: 1px solid #2a2d31; border-radius: 6px; padding: 6px; }
            QPushButton { background: #0c0d0e; color: #cfd3da; border: 1px solid #2a2d31; border-radius: 6px; padding: 6px 12px; }
            QPushButton:hover { background: #181c22; }
            """
        )
    
    def _show_test_result(self, success: bool, message: str):
        """显示测试结果（在主线程中执行）"""
        if success:
            QMessageBox.information(self, self.t['test_title'], message)
        else:
            if '401' in message or '403' in message or self.t['auth_failed'] in message:
                QMessageBox.warning(self, self.t['test_title'], message)
            else:
                QMessageBox.critical(self, self.t['test_title'], message)

    def _test_connection(self):
        base = (self.base_url.text() or '').strip()
        token = (self.api_key.text() or '').strip()
        if not base:
            QMessageBox.warning(self, self.t['test_title'], self.t['fill_base_url'])
            return
        if not token:
            QMessageBox.warning(self, self.t['test_title'], self.t['fill_token'])
            return
        # 修改为使用 POST 请求创建测试任务，而不是查询一个不存在的ID
        url = base.rstrip('/ ,') + '/v1/video/create'
        
        def worker():
            try:
                print(f'[测试连接] 正在连接: {url}', flush=True)
                # 使用最小的有效请求体进行测试
                test_payload = {
                    'model': 'sora-2-all',
                    'prompt': 'test connection',
                    'orientation': 'landscape',
                    'size': 'small',
                    'duration': 15,
                    'watermark': True
                }
                req = urllib.request.Request(
                    url, 
                    data=json.dumps(test_payload).encode('utf-8'),
                    headers={
                        'Content-Type': 'application/json',
                        'Accept': 'application/json', 
                        'Authorization': 'Bearer ' + token
                    }, 
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=8) as r:
                    txt = r.read().decode('utf-8')
                try:
                    j = json.loads(txt)
                except Exception:
                    j = { 'raw': txt }
                # 检查是否成功创建任务
                task_id = j.get('id') or j.get('task_id')
                if task_id:
                    msg = f'{self.t["connection_ok"]}\nHTTP 200\n{self.t["task_id"]}: {task_id}\n{self.t["test_warning"]}'
                else:
                    msg = f'{self.t["connection_ok"]}\nHTTP 200\n{self.t["response"]}: ' + (json.dumps(j, ensure_ascii=False)[:200] + ('...' if len(json.dumps(j))>200 else ''))
                print(f'[测试连接] 成功', flush=True)
                self._test_result_signal.emit(True, msg)
            except urllib.error.HTTPError as e:
                # HTTP错误也说明网络可达，根据状态码提示鉴权或端点问题
                detail = ''
                try:
                    detail = e.read().decode('utf-8')
                except Exception:
                    detail = ''
                if e.code in (401, 403):
                    msg = f'{self.t["auth_failed"]}（HTTP {e.code})\n{self.t["check_token"]}\n{self.t["response"]}: ' + (detail[:200] + ('...' if len(detail)>200 else ''))
                    print(f'[测试连接] 失败: 鉴权错误 {e.code}', flush=True)
                    self._test_result_signal.emit(False, msg)
                elif e.code == 400:
                    msg = f'{self.t["request_format_error"]}（HTTP 400）\n{self.t["possible_reasons"]}\n\n{self.t["response"]}: ' + (detail[:200] + ('...' if len(detail)>200 else ''))
                    print(f'[测试连接] HTTP 400 - 详情: {detail[:500]}', flush=True)
                    self._test_result_signal.emit(False, msg)
                else:
                    msg = f'{self.t["endpoint_reachable"]} HTTP {e.code}\n{self.t["response"]}: ' + (detail[:200] + ('...' if len(detail)>200 else ''))
                    print(f'[测试连接] HTTP {e.code}', flush=True)
                    self._test_result_signal.emit(True, msg)
            except Exception as e:
                msg = self.t['network_unreachable'] + str(e)
                print(f'[测试连接] 异常: {e}', flush=True)
                self._test_result_signal.emit(False, msg)
        
        import threading
        threading.Thread(target=worker, daemon=True).start()

    def accept(self):
        # 准备配置数据
        config = {
            'api_key': self.api_key.text(),
            'base_url': (self.base_url.text() or "").strip(),
            'model': self.model_combo.currentText(),
            'orientation': self.orientation_combo.currentText(),
            'size': self.size_combo.currentText(),
            'width': self.width_edit.text(),
            'height': self.height_edit.text(),
            'duration': self.duration_combo.currentText(),
            'watermark': self.watermark_combo.currentText()
        }
        
        # 保存到json/sora2.json
        if save_config(config):
            QMessageBox.information(self, self.t['save_success'], self.t['config_saved'])
        else:
            QMessageBox.warning(self, self.t['save_failed'], self.t['config_save_failed'])
        
        # 同时保存到QSettings（保持向后兼容）
        s = QSettings("GhostOS", "App")
        s.setValue("providers/sora2/api_key", config['api_key'])
        s.setValue("providers/sora2/base_url", config['base_url'])
        s.setValue("providers/sora2/model", config['model'])
        s.setValue("providers/sora2/orientation", config['orientation'])
        s.setValue("providers/sora2/size", config['size'])
        s.setValue("providers/sora2/width", config['width'])
        s.setValue("providers/sora2/height", config['height'])
        s.setValue("providers/sora2/duration", config['duration'])
        s.setValue("providers/sora2/watermark", config['watermark'])
        
        super().accept()
