"""
灵动智能体 - 词语优化模块
通过AI模型优化用户输入的提示词
"""

import json
import requests
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QTextEdit, QPushButton, QComboBox, QLineEdit, QMessageBox
)


class WordOptimizeThread(QThread):
    """词语优化线程"""
    
    finished = Signal(str)  # 优化完成信号，返回优化后的文本
    error = Signal(str)     # 错误信号
    
    def __init__(self, text, provider, model, api_key, api_url, hunyuan_api_url, parent=None):
        super().__init__(parent)
        self.text = text
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.api_url = api_url
        self.hunyuan_api_url = hunyuan_api_url

        # Register to global registry to prevent GC
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_word_optimize_workers'):
                app._active_word_optimize_workers = []
            app._active_word_optimize_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        """Clean up worker from global registry"""
        app = QApplication.instance()
        if app and hasattr(app, '_active_word_optimize_workers'):
            if self in app._active_word_optimize_workers:
                app._active_word_optimize_workers.remove(self)
        self.deleteLater()
    
    def run(self):
        """执行词语优化"""
        try:
            optimize_prompt = f"{self.text}\n\n请帮我将我输入的提示词进行优化，然后返回"
            
            # 根据provider选择API地址
            if self.provider == "Hunyuan":
                base_url = self.hunyuan_api_url
            else:
                base_url = self.api_url
            
            # 发送API请求
            response = self._call_api(base_url, optimize_prompt)
            
            if response:
                self.finished.emit(response)
            else:
                self.error.emit("优化失败：未收到有效响应")
        
        except Exception as e:
            self.error.emit(f"优化失败：{str(e)}")
    
    def _call_api(self, base_url, prompt):
        """调用AI API"""
        try:
            # 构建请求
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "stream": False,
                "temperature": 0.7,
                "max_tokens": 2000
            }
            
            # 发送请求
            b = base_url.strip()
            bl = b.lower()
            if bl.endswith('/v1'):
                b = b[: bl.rfind('/v1')]
            while b.endswith('/') or b.endswith(','):
                b = b[:-1]
            url = f"{b}/v1/chat/completions"
            response = None
            for i in range(2):
                try:
                    response = requests.post(url, headers=headers, json=payload, timeout=(10, 60))
                    response.raise_for_status()
                    break
                except requests.exceptions.Timeout:
                    if i == 1:
                        raise
                except requests.exceptions.ConnectionError:
                    if i == 1:
                        raise
            if response is None:
                import http.client, ssl
                from urllib.parse import urlparse
                parsed = urlparse(url)
                host = parsed.netloc or parsed.path.split('/')[0]
                context = ssl.create_default_context()
                conn = http.client.HTTPSConnection(host, context=context, timeout=60)
                conn.request('POST', '/v1/chat/completions', json.dumps(payload), headers)
                res = conn.getresponse()
                body = res.read().decode('utf-8')
                if res.status != 200:
                    import requests as _rq
                    r = _rq.models.Response()
                    r._content = body.encode('utf-8')
                    r.status_code = res.status
                    raise requests.exceptions.HTTPError(response=r)
                data = json.loads(body)
                if "choices" in data and len(data["choices"]) > 0:
                    content = data["choices"][0]["message"]["content"]
                    content = content.strip().strip('"').strip("'").strip()
                    return content
                return None
            
            # 解析响应
            data = response.json()
            
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"]["content"]
                # 清理响应（去除可能的引号或多余空白）
                content = content.strip().strip('"').strip("'").strip()
                return content
            
            return None
        
        except requests.exceptions.Timeout:
            raise Exception("请求超时，请检查网络连接")
        except requests.exceptions.ConnectionError:
            raise Exception("无法连接到API服务器")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise Exception("API密钥无效，请检查配置")
            elif e.response.status_code == 429:
                raise Exception("请求过于频繁，请稍后再试")
            else:
                raise Exception(f"HTTP错误 {e.response.status_code}")
        except json.JSONDecodeError:
            raise Exception("API返回数据格式错误")
        except Exception as e:
            raise Exception(f"API调用失败：{str(e)}")


def optimize_word(text, provider, model, api_key, api_url="https://manju.chat", 
                 hunyuan_api_url="https://api.vectorengine.ai", callback=None, error_callback=None):
    """
    优化词语的便捷函数
    
    Args:
        text: 需要优化的文本
        provider: 模型提供商
        model: 具体模型
        api_key: API密钥
        api_url: API地址（默认）
        hunyuan_api_url: Hunyuan API地址
        callback: 成功回调函数
        error_callback: 错误回调函数
    
    Returns:
        WordOptimizeThread: 线程对象
    """
    thread = WordOptimizeThread(text, provider, model, api_key, api_url, hunyuan_api_url)
    
    if callback:
        thread.finished.connect(callback)
    if error_callback:
        thread.error.connect(error_callback)
    
    return thread
