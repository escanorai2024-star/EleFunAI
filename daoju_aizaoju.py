from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication
import os
import base64
import json
import http.client
import ssl
from urllib.parse import urlparse
import re

class ScenePromptWorker(QThread):
    success = Signal(str)
    error = Signal(str)
    debug = Signal(str)

    def __init__(self, provider, model, api_key, api_url, hunyuan_api_url, image_path):
        super().__init__()
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.api_url = api_url
        self.hunyuan_api_url = hunyuan_api_url
        self.image_path = image_path

        # Register to global registry to prevent GC
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_scene_prompt_workers'):
                app._active_scene_prompt_workers = []
            app._active_scene_prompt_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        """Clean up worker from global registry"""
        app = QApplication.instance()
        if app and hasattr(app, '_active_scene_prompt_workers'):
            if self in app._active_scene_prompt_workers:
                app._active_scene_prompt_workers.remove(self)
        self.deleteLater()

    def run(self):
        try:
            base_url = self.hunyuan_api_url if self.provider == "Hunyuan" else self.api_url
            parsed = urlparse(base_url)
            host = parsed.netloc or parsed.path.split('/')[0]
            scheme = parsed.scheme or 'https'
            
            if scheme == 'https':
                context = ssl.create_default_context()
                conn = http.client.HTTPSConnection(host, context=context, timeout=25)
            else:
                conn = http.client.HTTPConnection(host, timeout=25)
            
            endpoint = "/v1/chat/completions"
            
            with open(self.image_path, 'rb') as f:
                image_b64 = base64.b64encode(f.read()).decode('utf-8')
            
            ext = os.path.splitext(self.image_path)[1].lower()
            mime_type = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp', '.gif': 'image/gif'}.get(ext, 'image/jpeg')
            
            content = [
                {"type": "text", "text": "只返回一句中文的简短提示词，描述图中场景及其关键细节，不要附加任何解释、结构或前后缀，只输出描述文本。"},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}}
            ]
            
            payload = {"model": self.model, "messages": [{"role": "user", "content": content}], "max_tokens": 256}
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.debug.emit(f"provider={self.provider}, model={self.model}, url={base_url}{endpoint}, image={os.path.basename(self.image_path)}, body={len(body)}B")
            
            conn.request("POST", endpoint, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            conn.close()
            
            if resp.status != 200:
                try:
                    err_text = data.decode('utf-8')[:300]
                except Exception:
                    err_text = str(data)[:300]
                self.error.emit(f"生成失败 ({resp.status}): {err_text}")
                return
            
            try:
                j = json.loads(data.decode('utf-8'))
                result_text = ""
                if isinstance(j, dict) and j.get("choices"):
                    msg = j["choices"][0].get("message", {})
                    content = msg.get("content")
                    if isinstance(content, str):
                        result_text = content.strip()
                    elif isinstance(content, list):
                        parts = []
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "text":
                                parts.append(c.get("text",""))
                        result_text = "\n".join(parts).strip()
                
                if not result_text and isinstance(j, dict):
                    result_text = (j.get("output","") or j.get("response","") or "").strip()
            except Exception:
                try:
                    result_text = data.decode('utf-8').strip()
                except Exception:
                    result_text = ""
            
            if not result_text:
                self.error.emit("未获取到有效的提示词内容。")
                return
            
            try:
                lines = [l.strip() for l in result_text.splitlines() if l.strip()]
                cand = lines[0] if lines else result_text.strip()
                # 清理常见的前缀
                cand = re.sub(r'^(成功|提示词|下面是|以下是|你可以|这是|描述|关于这张图片|场景)[：:]\s*', '', cand, flags=re.IGNORECASE)
                cand = re.sub(r'^(AI|用户)[：:]\s*', '', cand, flags=re.IGNORECASE)
                cand = cand.strip('“”"').strip()
                if len(cand) > 200:
                    cand = cand[:200].strip()
            except Exception:
                cand = result_text.strip()
                
            self.success.emit(cand)
            
        except Exception as e:
            self.error.emit(str(e))
