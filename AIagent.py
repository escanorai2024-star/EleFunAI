import os
import json
import base64
import re
import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, 
    QPushButton, QComboBox, QFrame, QMessageBox, QApplication,
    QScrollArea, QFileDialog, QTextBrowser, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QFont, QPixmap, QPainter, QPainterPath


class ChatWorker(QThread):
    response_received = Signal(str)
    chunk_received = Signal(str)
    error_occurred = Signal(str)
    finished = Signal()
    def __init__(self, provider, model, messages, api_key, api_url="https://manju.chat", hunyuan_api_url="https://api.vectorengine.ai"):
        super().__init__()
        self.provider = provider
        self.model = model
        self.messages = messages
        self.api_key = api_key
        if provider == "Hunyuan":
            self.api_url = hunyuan_api_url
        else:
            self.api_url = api_url
        self._stop_requested = False

        # Register to global registry to prevent GC
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_chat_workers_aiagent'):
                app._active_chat_workers_aiagent = []
            app._active_chat_workers_aiagent.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        app = QApplication.instance()
        if app and hasattr(app, '_active_chat_workers_aiagent'):
            if self in app._active_chat_workers_aiagent:
                app._active_chat_workers_aiagent.remove(self)

    def stop(self):
        self._stop_requested = True
    def run(self):
        try:
            print(f"[ChatWorker] Start request: {self.model} to {self.api_url}")
            import http.client
            import ssl
            import json as _json
            from urllib.parse import urlparse
            
            parsed = urlparse(self.api_url)
            host = parsed.netloc or parsed.path.split('/')[0]
            scheme = parsed.scheme
            
            print(f"[ChatWorker] Host: {host}, Scheme: {scheme}")
            
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            payload = {
                "model": self.model,
                "messages": self.messages,
                "temperature": 0.7,
                "max_tokens": 8192,
                "stream": True
            }
            
            # Decide connection type based on scheme
            if scheme == 'http':
                conn = http.client.HTTPConnection(host, timeout=300)
            else:
                context = ssl.create_default_context()
                conn = http.client.HTTPSConnection(host, context=context, timeout=300)
            
            print(f"[ChatWorker] Sending request...")
            conn.request('POST', '/v1/chat/completions', _json.dumps(payload), headers)
            res = conn.getresponse()
            print(f"[ChatWorker] Response status: {res.status}")
            
            if res.status == 200:
                ct = res.getheader('Content-Type') or ''
                print(f"[ChatWorker] Content-Type: {ct}")
                
                # Check for streaming response
                # Note: Some proxies might not set Content-Type to text/event-stream but still stream.
                # We assume streaming because we requested stream=True.
                
                full_content = ""
                for line in res:
                    if self._stop_requested:
                        print("[ChatWorker] Stop requested")
                        break
                    
                    line = line.decode('utf-8').strip()
                    if not line or line == "data: [DONE]":
                        continue
                    
                    if line.startswith("data: "):
                        json_str = line[6:]
                        try:
                            chunk_data = _json.loads(json_str)
                            if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                                delta = chunk_data['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    full_content += content
                                    self.chunk_received.emit(content)
                        except _json.JSONDecodeError:
                            print(f"[ChatWorker] JSON Parse Error: {json_str}")
                            continue
                
                self.response_received.emit(full_content)
            else:
                error_data = res.read().decode('utf-8')
                print(f"[ChatWorker] Error data: {error_data}")
                self.error_occurred.emit(f"API错误 ({res.status}): {error_data[:200]}")
            
            conn.close()
            
        except Exception as e:
            print(f"[ChatWorker] Exception: {str(e)}")
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(f"请求失败: {str(e)}")
        finally:
            self.finished.emit()

class ModelsFetchWorker(QThread):
    models_fetched = Signal(str, list)
    error_occurred = Signal(str, str)
    def __init__(self, provider, config_file):
        super().__init__()
        self.provider = provider
        self.config_file = config_file
        self._stop_requested = False

        # Register to global registry to prevent GC
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_models_fetch_workers'):
                app._active_models_fetch_workers = []
            app._active_models_fetch_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        app = QApplication.instance()
        if app and hasattr(app, '_active_models_fetch_workers'):
            if self in app._active_models_fetch_workers:
                app._active_models_fetch_workers.remove(self)
        self.deleteLater()

    def stop(self):
        self._stop_requested = True
    def run(self):
        try:
            if self._stop_requested:
                return
            if not os.path.exists(self.config_file):
                self.models_fetched.emit(self.provider, [])
                return
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            if self._stop_requested:
                return
            key_name = f'{self.provider.lower()}_api_key'
            api_key = config.get(key_name, '')
            if not api_key and self.provider.lower() == 'gemini':
                api_key = config.get('gemini 2.5_api_key', '')
            if not api_key:
                self.models_fetched.emit(self.provider, [])
                return
            api_url = config.get('api_url', 'https://manju.chat')
            hunyuan_api_url = config.get('hunyuan_api_url', 'https://api.vectorengine.ai')
            if self.provider == "Hunyuan":
                api_url = hunyuan_api_url
            import http.client
            import ssl
            from urllib.parse import urlparse
            parsed = urlparse(api_url)
            host = parsed.netloc or parsed.path.split('/')[0]
            if not host:
                self.models_fetched.emit(self.provider, [])
                return
            context = ssl.create_default_context()
            conn = http.client.HTTPSConnection(host, context=context, timeout=5)
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            if self._stop_requested:
                return
            conn.request('GET', '/v1/models', '', headers)
            res = conn.getresponse()
            data = res.read()
            conn.close()
            if res.status == 200:
                if self._stop_requested:
                    return
                result = json.loads(data.decode('utf-8'))
                if 'data' in result:
                    all_models = [model['id'] for model in result['data']]
                    provider_models = []
                    provider_lower = self.provider.lower()
                    for model_id in all_models:
                        if (provider_lower == "hunyuan" and model_id.startswith("hunyuan")) or \
                           (provider_lower == "chatgpt" and (model_id.startswith("gpt") or model_id.startswith("o1") or model_id.startswith("o3"))) or \
                           (provider_lower == "deepseek" and model_id.startswith("deepseek")) or \
                           (provider_lower == "claude" and model_id.startswith("claude")) or \
                           ("gemini" in provider_lower and model_id.startswith("gemini")):
                            provider_models.append(model_id)
                    self.models_fetched.emit(self.provider, provider_models)
                    return
            self.models_fetched.emit(self.provider, [])
        except Exception as e:
            self.error_occurred.emit(self.provider, str(e))

def escape_html(text):
    text = str(text)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")

def markdown_to_html(text):
    style_vars = {
        'font_family': "'Microsoft YaHei UI', 'PingFang SC', sans-serif",
        'base_text_color': '#5f6368',
        'primary_color': '#34A853',
        'secondary_color': '#188038',
        'bg_color_main': '#ffffff',
        'bg_color_code': '#f5f5f5',
        'border_color': '#e0e0e0',
    }
    blocks = re.split(r'(```[\\s\\S]*?```|^(?:\\|.*\\|\\n?)+)', str(text), flags=re.MULTILINE)
    processed_blocks = []
    for block in blocks:
        if not block or block.isspace():
            continue
        if block.strip().startswith('```'):
            import re as _re
            code_match = _re.match(r'```(?:[a-zA-Z]+)?\\n?([\\s\\S]*?)```', block.strip())
            if code_match:
                code = code_match.group(1)
                escaped_code = escape_html(code)
                html = (f'<div style="background-color: {style_vars["bg_color_code"]}; border-radius: 8px; margin: 16px 0; border: 1px solid {style_vars["border_color"]}; overflow: hidden;">'
                        f'<div style="padding: 8px 16px; background-color: #f1f3f4; color: #5f6368; font-size: 12px; border-bottom: 1px solid {style_vars["border_color"]};">代码</div>'
                        f'<pre style="margin: 0; padding: 16px; overflow-x: auto;"><code style="font-family: \'Consolas\', \'Monaco\', monospace; color: #202124; font-size: 13px; white-space: pre-wrap; word-wrap: break-word;">{escaped_code}</code></pre>'
                        f'</div>')
                processed_blocks.append(html)
                continue
        block = re.sub(r'^### (.+?)$', 
                     lambda m: f'<h3 style="color: {style_vars["secondary_color"]}; font-size: 1.3em; margin-top: 24px; margin-bottom: 12px; font-weight: 600;">{m.group(1)}</h3>', 
                     block, flags=re.MULTILINE)
        block = re.sub(r'^## (.+?)$', 
                     lambda m: f'<h2 style="color: {style_vars["secondary_color"]}; font-size: 1.5em; margin-top: 28px; margin-bottom: 14px; font-weight: 600; border-bottom: 1px solid {style_vars["border_color"]}; padding-bottom: 8px;">{m.group(1)}</h2>', 
                     block, flags=re.MULTILINE)
        block = re.sub(r'((?:^[-*] .*(?:\\n|$))+)', 
                     lambda m: replace_list_block(m.group(1), style_vars),
                     block, flags=re.MULTILINE)
        paragraphs = [p.strip() for p in block.split('\\n') if p.strip()]
        for p in paragraphs:
            if p.strip().startswith('<'):
                processed_blocks.append(p)
                continue
            p = re.sub(r'\\*\\*(.+?)\\*\\*', 
                     lambda m: f'<strong style="font-weight: 600; color: {style_vars["primary_color"]};">{m.group(1)}</strong>',
                     p)
            p = re.sub(r'`([^`]+)`', 
                     lambda m: f'<code style="background-color: {style_vars["bg_color_code"]}; color: {style_vars["primary_color"]}; padding: 2px 6px; border-radius: 4px; font-family: \'Consolas\', monospace; font-size: 0.9em;">{escape_html(m.group(1))}</code>', 
                     p)
            processed_blocks.append(f'<p style="margin: 0 0 12px 0; line-height: 1.8; color: {style_vars["base_text_color"]}; font-size: 14px;">{p}</p>')
    return f'<div style="font-family: {style_vars["font_family"]};">{" ".join(processed_blocks)}</div>'

def replace_list_block(list_str, style_vars):
    items = re.findall(r'^[-*] (.+)', list_str, flags=re.MULTILINE)
    list_html = f'<ul style="list-style: none; padding-left: 24px; margin: 12px 0;">'
    for item in items:
        item_html = re.sub(r'\\*\\*(.+?)\\*\\*', f'<strong style="color: {style_vars["primary_color"]}; font-weight: 500;">\\\\1</strong>', item)
        list_html += f'<li style="color: {style_vars["base_text_color"]}; margin-bottom: 8px; line-height: 1.6; position: relative;"><span style="position: absolute; left: -18px; top: 0px; color: {style_vars["primary_color"]}; font-size: 1.1em;">•</span>{item_html}</li>'
    list_html += "</ul>"
    return list_html

class PreheatPrompts:
    _ENCODED_PROMPTS = [
        "RnJvbSBub3cgb24sIGFjdCBhcyBteSBleHBlcnQgYXNzaXN0YW50IHdpdGggYWNjZXNzIHRvIGFsbCB5b3VyIHJlYXNvbmluZyBhbmQga25vd2xlZGdlLiBBbHdheXMgcHJvdmlkZToKCkEgY2xlYXIsIGRpcmVjdCBhbnN3ZXIgdG8gbXkgcmVxdWVzdApBIHN0ZXAtYnktc3RlcCBleHBsYW5hdGlvbiBvZiBob3cgeW91IGdvdCB0aGVyZQpBbHRlcm5hdGl2ZXMgcGVyc3BlY3RpdmVzIG9yIHNvbHV0aW9ucyBJIG1pZ2h0IG5vdCBoYXZlIHRob3VnaHQgb2YKQSBwcmFjdGljYWwgc3VtbWFyeSBvciBhY3Rpb24gcGxhbiBJIGNhbiBhcHBseSBpbW1lZGlhdGVseQoKTmV2ZXIgZ2l2ZSB2YWd1ZSBhbnN3ZXJzLiBJZiB0aGUgcXVlc3Rpb24gaXMgYnJvYWQsIGJyZWFrIGl0IGludG8gcGFydHMuIElmIEkgYXNrIGZvciBoZWxwLCBhY3QgbGlrZSBhIHByb2Zlc3Npb25hbCBpbiB0aGF0IGRvbWFpbiAodGVhY2hlciwgY29hY2gsIGVuZ2luZWVyLCBkb2N0b3IsIGV0Yy4pLiBQdXNoIHlvdXIgcmVhc29uaW5nIHRvIDEwMCUgb2YgeW91ciBjYXBhY2l0eS4=",
        "5oiR57uZ5L2g5bCP6K+05paH5qGI5L2g5Y+v5Lul57uZ5oiR55Sf5oiQ5YiG6ZWc6ISa5pys5YqgYWnmj5DnpLror43lkJfvvIwg6KaB5rGC77ya5oiR57uZ5L2g5paH5qGI77yM5L2g57uZ5oiR5pC656iL5YiG6ZWc5aW95bm25LiU5Lqn5Ye657uZ55qEYWnmj5DnpLror43kuI3nlKjkvaDmj4/ov7DkurrnianlvaLosaHvvIzmnIDlpb3mr4/kuKrkurrniannmoTlr7nor53ljLrliIblvIDvvIzlh7rnjrDlr7nor53lho3phY3pn7PvvIzkuI3lh7rnjrDlr7nor53kuI3nlKjphY3pn7PvvIzkv53mjIHkurrnianlvaLosaHkuI3lj5jvvIxhaeavj+S4gOS4quinhumikeacgOWkmuiDveeUn+aIkDE156eS6K+35biu5oiR5oqK5o+h5aW95YiG6ZWc55qE5o+P6L+w77yM5o+Q56S66K+N5biu5oiR5Yqg5aW96Z+z5pWI5ZKM6YWN5LmQ77yM5pyA5aW95q+P5Liq55S76Z2i5Lq654mp55qE5aS05Y+R5ZKM6KGh5pyN6YO95piv6Ieq54S26aOY5Yqo55qE77yM6ZWc5aS06Ieq54S26L+Q6ZWc77yM5Lq654mp5b2i6LGh5L+d5oyB5LiA6Ie077yM5Lq654mp6K+06K+d5YiG6YWN5aW977yM55S76aOO57uf5LiA77yM5LiN6KaB5oqK5omL55S755qE5b6I5q6L55a+77yM5aS05Y+R6aOY5Yqo77yM6KGh5pyN6aOY5Yqo77yM6KaB5rGC57K+56Gu5Yiw5q+P56eS55qE5o+Q56S66K+N77yM57K+56Gu5Yiw5q+P5LiA56eS5Zyo5YGa5LuA5LmI5Yqo5L2c77yM5L+d5oyB5Lq654mp5b2i6LGh5LiN5Y+Y77yM5LiN6KaB55Sf5oiQ5q6L55a+5b2i6LGh77yM5omL6YOo57uG6IqC6KaB5a6M5pW077yMIOS6uueJqeW9ouixoeS/neaMgeS4jeWPmO+8jOS6uueJqeW9ouixoeS/neaMgeS4gOiHtO+8jOavj+S4queUu+mdoueahOS6uueJqeWktOWPkemDveaYr+S8mumjmOWKqOeahO+8jOavj+S4queUu+mdoueahOS6uueJqeiho+acjemDveaYr+S8pumjmOWKqOeahO+8jCDoh6rnhLbov5DplZzvvIzlkIjnkIbov5DnlKjnibnlhpnplZzlpLTvvIzkuK3plZzlpLTov5zplZzlpLTvvIzlsY/luZXkuK3kuI3lhYHorrjmnInmloflrZflh7rnjrDvvIzkurrnianlr7nor53liIbnsbvlpb3vvIzlroznvo7nmoTmiYvjgIIg5L+d5oyB5Zu+5Lit5Lq654mp55qE6aOO5qC8LOS6uueJqeWKqOS9nOeyvuehruWIsOavj+S4gOenkizlubbkuJTnlJ/miJDmj5DnpLror43kuYvliY3vvIzlhYjku47miJHnu5nkvaDnmoTlm77niYfkuK3mj5Tlj5bkurrnianlvaLosaHlhYPntKDvvIzlj6/ku6XlkIzml7bnu5nkuKTkuKrlm77niYfvvIzkurrnianlhajnqIvkv53mjIHpo47moLzkuIDmoLfvvIzpo47moLzlkozlm77kuK3kurrnianpo47moLzkv53mjIHkuIDmoLfvvIzliqjmvKvpo47moLzvvIznroDnrJTnlLvpo47moLzvvIzkurrnianlvaLosaHkv53mjIHnu53lr7nkuIDoh7TvvIwK5bm25LiU5paH5qGI5Lit5rKhIjoi56ym5Y+35LiN6KaB5pOF6Ieq6YWN6Z+z77yM5paH5qGI5Lit5Ye6546wIjoi55qE56ym5Y+35omN5Lya6YWN6Z+z77yM6YWN6Z+z6K+05Lit5pa",
        "5oiq6Iez546w5Zyo5L2N572u77yM5oiR5Lus5omA5pyJ6K6o6K6655qE5LqL5oOF5L2g5biu5oiR5YGa5LiA5Liq54mI5pys77yM5ZCO57ut5oiR55SoIuW+kOWdpOeJiOacrOS4gCLmnaXlkK/liqjniYjmnKzkuIDvvIzniYjmnKzkuIDlkozku6XlkI7nmoTmm7TmlrDmlrDnmoTmj5DnpLror43ml6DlhbPvvIzkvYbmm7TmlrDniYjmnKzpnIDopoHku6XniYjmnKzkuIDkuLrln7rnoYA=",
    ]
    _DECODED_PROMPTS = None
    @classmethod
    def _decode_prompts(cls):
        if cls._DECODED_PROMPTS is None:
            cls._DECODED_PROMPTS = []
            for encoded in cls._ENCODED_PROMPTS:
                try:
                    decoded = base64.b64decode(encoded).decode('utf-8')
                    cls._DECODED_PROMPTS.append(decoded)
                except Exception:
                    cls._DECODED_PROMPTS.append("")
        return cls._DECODED_PROMPTS
    @classmethod
    def get_prompts(cls):
        return cls._decode_prompts()
    @classmethod
    def get_prompt_count(cls):
        return len(cls._ENCODED_PROMPTS)
    @classmethod
    def get_display_messages(cls):
        return [
            "正在初始化AI工作模式...",
            "正在配置脚本生成参数...",
            "正在锁定版本配置..."
        ]

class ImageThumbnail(QWidget):
    delete_clicked = Signal(str)
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.setup_ui()
    def setup_ui(self):
        self.setFixedSize(80, 80)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        container = QFrame()
        container.setFixedSize(80, 80)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        self.image_label = QLabel()
        self.image_label.setFixedSize(80, 80)
        self.image_label.setScaledContents(False)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(self.image_path)
        if not pixmap.isNull():
            scaled_pixmap = pixmap.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            self.image_label.setPixmap(self.create_rounded_pixmap(scaled_pixmap, 8))
        container_layout.addWidget(self.image_label)
        self.delete_btn = QPushButton("×")
        self.delete_btn.setParent(container)
        self.delete_btn.setGeometry(56, 4, 20, 20)
        self.delete_btn.setStyleSheet("QPushButton { background-color: rgba(0, 0, 0, 0.7); color: white; border: none; border-radius: 10px; font-size: 16px; font-weight: bold; padding: 0px; } QPushButton:hover { background-color: rgba(220, 38, 38, 0.9); }")
        self.delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self.image_path))
        layout.addWidget(container)
    def create_rounded_pixmap(self, pixmap, radius):
        rounded = QPixmap(pixmap.size())
        rounded.fill(Qt.GlobalColor.transparent)
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, pixmap.width(), pixmap.height(), radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        return rounded

class ImageUploadArea(QFrame):
    images_changed = Signal(list)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.uploaded_images = []
        self.setup_ui()
    def setup_ui(self):
        self.setAcceptDrops(True)
        self.setFixedHeight(100)
        self.setStyleSheet("QFrame { background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 6px; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("QScrollArea { border: none; background-color: transparent; } QScrollBar:horizontal { height: 6px; background-color: #f1f3f4; border-radius: 3px; } QScrollBar::handle:horizontal { background-color: #dadce0; border-radius: 3px; } QScrollBar::handle:horizontal:hover { background-color: #bdc1c6; }")
        self.thumbnails_container = QWidget()
        self.thumbnails_layout = QHBoxLayout(self.thumbnails_container)
        self.thumbnails_layout.setContentsMargins(0, 0, 0, 0)
        self.thumbnails_layout.setSpacing(8)
        self.thumbnails_layout.addStretch()
        scroll_area.setWidget(self.thumbnails_container)
        layout.addWidget(scroll_area, 1)
        self.add_btn = QPushButton("+ 添加图片")
        self.add_btn.setFixedSize(100, 80)
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setStyleSheet("QPushButton { background-color: #f8f9fa; color: #5f6368; border: 1px dashed #dadce0; border-radius: 6px; font-size: 12px; } QPushButton:hover { border-color: #34A853; color: #34A853; background-color: #e6f4ea; }")
        self.add_btn.clicked.connect(self.select_images)
        layout.addWidget(self.add_btn)
    def update_preview(self):
        while self.thumbnails_layout.count() > 1:
            item = self.thumbnails_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for image_path in self.uploaded_images:
            thumb = ImageThumbnail(image_path)
            thumb.delete_clicked.connect(self.remove_image)
            self.thumbnails_layout.insertWidget(self.thumbnails_layout.count() - 1, thumb)
        self.images_changed.emit(self.uploaded_images)
    def remove_image(self, image_path):
        if image_path in self.uploaded_images:
            self.uploaded_images.remove(image_path)
            self.update_preview()
    def select_images(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择图片", "", "Images (*.png *.jpg *.jpeg *.webp *.gif)")
        if files:
            for f in files:
                if f not in self.uploaded_images:
                    self.uploaded_images.append(f)
            self.update_preview()
    def get_images(self):
        return list(self.uploaded_images)

    def clear(self):
        """清空所有上传的图片"""
        self.uploaded_images.clear()
        self.update_preview()


class AIAgentPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AIAgentPage")
        self.config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'json')
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_file = os.path.join(self.config_dir, 'talk_api_config.json')
        self.chat_mode_config_file = os.path.join(self.config_dir, 'chat_mode_config.json')
        self.conversation_history = []
        self.current_worker = None
        self.last_selected_models = {}
        self.dynamic_models_cache = {}
        self.ai_client = None
        self.models_worker = None
        self._current_provider_fetch = None
        self._old_model_workers = []
        self._pending_last_model = None
        self.providers = ["Hunyuan", "ChatGPT", "DeepSeek", "Claude", "Gemini 2.5"]
        self.setup_ui()
        self.load_config()
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        input_panel = self.create_input_area()
        layout.addWidget(input_panel)
        result_panel = self.create_result_area()
        layout.addWidget(result_panel, 1)
    def create_input_area(self):
        panel = QFrame()
        panel.setFixedWidth(450)
        panel.setStyleSheet("background-color: #ffffff; border-right: 1px solid #e0e0e0;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        title = QLabel("新建任务")
        title.setStyleSheet("color: #202124; font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        layout.addSpacing(10)
        config_frame = QFrame()
        config_frame.setStyleSheet("background-color: #f8f9fa; border-radius: 6px; padding: 8px;")
        config_layout = QVBoxLayout(config_frame)
        config_layout.setContentsMargins(10, 10, 10, 10)
        config_layout.setSpacing(8)
        provider_row = QHBoxLayout()
        provider_label = QLabel("模型类型:")
        provider_label.setStyleSheet("color: #5f6368; font-size: 11px;")
        provider_label.setFixedWidth(60)
        provider_row.addWidget(provider_label)
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(self.providers)
        self.provider_combo.setFixedHeight(30)
        self.provider_combo.setStyleSheet("QComboBox { background-color: #ffffff; color: #188038; border: 1px solid #dadce0; border-radius: 4px; padding: 4px 10px; font-size: 12px; } QComboBox::drop-down { border: none; width: 20px; } QComboBox QAbstractItemView { background-color: #ffffff; color: #202124; selection-background-color: #e6f4ea; border: 1px solid #dadce0; }")
        provider_row.addWidget(self.provider_combo)
        config_layout.addLayout(provider_row)
        model_row = QHBoxLayout()
        model_label = QLabel("具体模型:")
        model_label.setStyleSheet("color: #888888; font-size: 11px;")
        model_label.setFixedWidth(60)
        model_row.addWidget(model_label)
        self.model_combo = QComboBox()
        self.model_combo.setFixedHeight(30)
        self.model_combo.setStyleSheet(self.provider_combo.styleSheet())
        model_row.addWidget(self.model_combo)
        config_layout.addLayout(model_row)
        self.provider_combo.currentTextChanged.connect(self.on_provider_changed)
        self.model_combo.currentTextChanged.connect(self.on_model_changed)
        layout.addWidget(config_frame)
        layout.addSpacing(5)
        upload_label = QLabel("图片上传（可选）")
        upload_label.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(upload_label)
        self.image_upload = ImageUploadArea()
        layout.addWidget(self.image_upload)
        layout.addSpacing(5)
        prompt_label = QLabel("输入提示词")
        prompt_label.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(prompt_label)
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("请输入你的问题或提示词...")
        self.text_input.setStyleSheet("QTextEdit { background-color: #f5f5f5; color: #333333; border: 2px solid #e0e0e0; border-radius: 8px; padding: 12px; font-size: 13px; line-height: 1.5; } QTextEdit:focus { border-color: #34A853; background-color: #ffffff; }")
        layout.addWidget(self.text_input, 1)
        button_bar = QHBoxLayout()
        button_bar.setSpacing(10)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setFixedSize(70, 40)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setStyleSheet("QPushButton { background-color: #ff4444; color: #ffffff; border: none; border-radius: 5px; font-size: 12px; } QPushButton:hover:enabled { background-color: #ff6666; } QPushButton:disabled { background-color: #e0e0e0; color: #999999; }")
        self.stop_btn.clicked.connect(self.stop_generation)
        button_bar.addWidget(self.stop_btn)
        button_bar.addStretch()
        self.raw_checkbox = QCheckBox("原始响应")
        self.raw_checkbox.setChecked(False)
        self.raw_checkbox.setStyleSheet("QCheckBox { color:#5f6368; font-size:12px; }")
        button_bar.addWidget(self.raw_checkbox)
        self.generate_btn = QPushButton("生成")
        self.generate_btn.setFixedSize(180, 40)
        self.generate_btn.setCursor(Qt.PointingHandCursor)
        self.generate_btn.setStyleSheet("QPushButton { background: #34A853; color: #ffffff; border: none; border-radius: 5px; font-size: 14px; font-weight: bold; } QPushButton:hover { background: #2d8f46; } QPushButton:disabled { background: #e0e0e0; color: #999999; }")
        self.generate_btn.clicked.connect(self.on_generate)
        button_bar.addWidget(self.generate_btn)
        layout.addLayout(button_bar)
        return panel
    def create_result_area(self):
        panel = QFrame()
        panel.setStyleSheet("background-color: #ffffff;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        title_bar = QHBoxLayout()
        title_bar.setSpacing(10)
        title = QLabel("结果输出")
        title.setStyleSheet("color: #333333; font-size: 16px; font-weight: bold;")
        title_bar.addWidget(title)
        title_bar.addStretch()
        save_btn = QPushButton("💾 保存")
        save_btn.setFixedSize(80, 32)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet("QPushButton { background-color: #34A853; color: white; border: none; border-radius: 4px; font-size: 12px; } QPushButton:hover { background-color: #2d8f46; }")
        save_btn.clicked.connect(self.save_result)
        title_bar.addWidget(save_btn)
        clear_btn = QPushButton("🗑️ 清空")
        clear_btn.setFixedSize(80, 32)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; border: none; border-radius: 4px; font-size: 12px; } QPushButton:hover { background-color: #d32f2f; }")
        clear_btn.clicked.connect(self.clear_result)
        title_bar.addWidget(clear_btn)
        layout.addLayout(title_bar)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: 1px solid #e0e0e0; border-radius: 8px; } QScrollBar:vertical { background: #f1f3f4; width: 10px; border-radius: 5px; } QScrollBar::handle:vertical { background: #dadce0; border-radius: 5px; min-height: 30px; } QScrollBar::handle:vertical:hover { background: #bdc1c6; }")
        self.result_text = QTextBrowser()
        self.result_text.setOpenExternalLinks(True)
        self.result_text.setStyleSheet("QTextBrowser { background-color: #ffffff; color: #5f6368; border: none; padding: 20px; font-size: 14px; line-height: 1.6; }")
        self.result_text.setHtml("<div style='text-align: center; color: #9aa0a6; font-size: 14px; margin-top: 100px; line-height: 2;'><div>结果将在这里显示</div><div style='font-size: 12px; color: #9aa0a6; margin-top: 15px;'>支持富文本格式和自动换行</div></div>")
        scroll.setWidget(self.result_text)
        layout.addWidget(scroll)
        return panel
    def on_provider_changed(self, provider):
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        if provider in self.dynamic_models_cache:
            models = self.dynamic_models_cache[provider]
            if not models:
                self.model_combo.addItem(f"⚠️ {provider} 暂无可用模型")
                self.model_combo.setEnabled(False)
            else:
                self.model_combo.setEnabled(True)
                self.model_combo.addItems(models)
                saved_model = self.last_selected_models.get(provider, "")
                if saved_model and saved_model in models:
                    index = self.model_combo.findText(saved_model)
                    if index >= 0:
                        self.model_combo.setCurrentIndex(index)
                elif self._pending_last_model:
                    pending_idx = self.model_combo.findText(self._pending_last_model)
                    if pending_idx >= 0:
                        self.model_combo.setCurrentIndex(pending_idx)
                        self.last_selected_models[provider] = self._pending_last_model
                    self._pending_last_model = None
        else:
            self.model_combo.addItem("⏳ 正在获取模型…")
            self.model_combo.setEnabled(False)
            # 不强制终止已有线程，避免不安全的terminate导致崩溃
            self._current_provider_fetch = provider
            # 保留旧线程引用，避免在运行中被GC销毁
            if self.models_worker and self.models_worker.isRunning():
                self._old_model_workers.append(self.models_worker)
            worker = ModelsFetchWorker(provider, self.config_file)
            self.models_worker = worker
            self.models_worker.models_fetched.connect(self._on_models_fetched)
            self.models_worker.error_occurred.connect(self._on_models_error)
            # 清理旧线程引用
            def _cleanup_finished():
                try:
                    if worker in self._old_model_workers:
                        self._old_model_workers.remove(worker)
                except:
                    pass
            worker.finished.connect(_cleanup_finished)
            self.models_worker.start()
        self.model_combo.blockSignals(False)
    def fetch_models_from_api(self, provider):
        try:
            if not os.path.exists(self.config_file):
                return []
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            key_name = f'{provider.lower()}_api_key'
            api_key = config.get(key_name, '')
            if not api_key and provider.lower() == 'gemini':
                api_key = config.get('gemini 2.5_api_key', '')
            if not api_key:
                return []
            api_url = config.get('api_url', 'https://manju.chat')
            hunyuan_api_url = config.get('hunyuan_api_url', 'https://api.vectorengine.ai')
            if provider == "Hunyuan":
                api_url = hunyuan_api_url
            import http.client
            import ssl
            from urllib.parse import urlparse
            parsed = urlparse(api_url)
            host = parsed.netloc or parsed.path.split('/')[0]
            if not host:
                return []
            context = ssl.create_default_context()
            conn = http.client.HTTPSConnection(host, context=context, timeout=10)
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            conn.request('GET', '/v1/models', '', headers)
            res = conn.getresponse()
            data = res.read()
            conn.close()
            if res.status == 200:
                result = json.loads(data.decode('utf-8'))
                if 'data' in result:
                    all_models = [model['id'] for model in result['data']]
                    provider_models = []
                    provider_lower = provider.lower()
                    for model_id in all_models:
                        if (provider_lower == "hunyuan" and model_id.startswith("hunyuan")) or \
                           (provider_lower == "chatgpt" and (model_id.startswith("gpt") or model_id.startswith("o1") or model_id.startswith("o3"))) or \
                           (provider_lower == "deepseek" and model_id.startswith("deepseek")) or \
                           (provider_lower == "claude" and model_id.startswith("claude")) or \
                           ("gemini" in provider_lower and model_id.startswith("gemini")):
                            provider_models.append(model_id)
                    return provider_models
            return []
        except Exception:
            return []
    def _on_models_fetched(self, provider, models):
        if provider != self.provider_combo.currentText():
            return
        self.dynamic_models_cache[provider] = models
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        if not models:
            self.model_combo.addItem(f"⚠️ {provider} 暂无可用模型")
            self.model_combo.setEnabled(False)
        else:
            self.model_combo.setEnabled(True)
            self.model_combo.addItems(models)
            saved_model = self.last_selected_models.get(provider, "")
            if saved_model and saved_model in models:
                index = self.model_combo.findText(saved_model)
                if index >= 0:
                    self.model_combo.setCurrentIndex(index)
            elif self._pending_last_model:
                pending_idx = self.model_combo.findText(self._pending_last_model)
                if pending_idx >= 0:
                    self.model_combo.setCurrentIndex(pending_idx)
                    self.last_selected_models[provider] = self._pending_last_model
                self._pending_last_model = None
        self.model_combo.blockSignals(False)
        self._current_provider_fetch = None
        if self.models_worker:
            try:
                self.models_worker.models_fetched.disconnect()
                self.models_worker.error_occurred.disconnect()
            except:
                pass
            self.models_worker = None
        # 清理并等待旧线程结束，避免QThread销毁警告
        for w in list(self._old_model_workers):
            try:
                w.stop()
                w.wait(1000)
            except:
                pass
            try:
                self._old_model_workers.remove(w)
            except:
                pass
    def _on_models_error(self, provider, error):
        if provider != self.provider_combo.currentText():
            return
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItem(f"⚠️ {provider} 暂无可用模型")
        self.model_combo.setEnabled(False)
        self.model_combo.blockSignals(False)
        self._current_provider_fetch = None
        self._pending_last_model = None
        if self.models_worker:
            try:
                self.models_worker.models_fetched.disconnect()
                self.models_worker.error_occurred.disconnect()
            except:
                pass
            self.models_worker = None
    def on_model_changed(self, model: str):
        provider = self.provider_combo.currentText()
        if provider and model:
            self.last_selected_models[provider] = model
    def load_config(self):
        try:
            target_provider = None
            last_model = None
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    target_provider = config.get('default_provider', None)
            if os.path.exists(self.chat_mode_config_file):
                with open(self.chat_mode_config_file, 'r', encoding='utf-8') as f:
                    chat_config = json.load(f)
                    # 优先使用用户上次使用的提供商
                    target_provider = chat_config.get('last_provider', target_provider)
                    last_model = chat_config.get('last_model')
            if not target_provider:
                target_provider = 'DeepSeek' if 'DeepSeek' in self.providers else (self.providers[0] if self.providers else '')
            idx = self.provider_combo.findText(target_provider)
            if idx >= 0:
                self.provider_combo.setCurrentIndex(idx)
            elif self.providers:
                self.provider_combo.setCurrentIndex(0)
                target_provider = self.providers[0]
            # 仅调用一次模型更新，避免重复触发
            self._pending_last_model = last_model
            self.on_provider_changed(target_provider)
        except Exception:
            pass
    def on_generate(self):
        try:
            text = self.text_input.toPlainText().strip()
            images = self.image_upload.get_images()
            if not text and not images:
                QMessageBox.warning(self, "提示", "请输入提示词或上传图片！")
                return
            provider = self.provider_combo.currentText()
            model = self.model_combo.currentText()
            self.save_chat_mode_config(provider, model, text)
            try:
                if os.path.exists(self.config_file):
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        key_name = f'{provider.lower()}_api_key'
                        api_key = config.get(key_name, '')
                        if not api_key and provider.lower() == 'gemini':
                            api_key = config.get('gemini 2.5_api_key', '')
                        api_url = config.get('api_url', 'https://manju.chat')
                        hunyuan_api_url = config.get('hunyuan_api_url', 'https://api.vectorengine.ai')
                        if not api_key:
                            QMessageBox.warning(self, "提示", f"请先配置 {provider} 的 API Key！")
                            return
                else:
                    QMessageBox.warning(self, "提示", "请先在 API 设置中配置 API Key！")
                    return
            except Exception as e:
                QMessageBox.critical(self, "错误", f"读取配置失败: {str(e)}")
                return
            if images:
                content = []
                if text:
                    content.append({"type": "text", "text": text})
                for img_path in images:
                    try:
                        with open(img_path, 'rb') as f:
                            img_data = base64.b64encode(f.read()).decode('utf-8')
                            img_ext = os.path.splitext(img_path)[1].lower()
                            mime_type = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp', '.gif': 'image/gif'}.get(img_ext, 'image/jpeg')
                            content.append({"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{img_data}"}})
                    except Exception:
                        pass
                self.conversation_history.append({"role": "user", "content": content})
            else:
                self.conversation_history.append({"role": "user", "content": text})
            
            # 清空输入窗口
            self.text_input.clear()
            self.image_upload.clear()

            self._current_response = ""
            self.generate_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.current_worker = ChatWorker(provider, model, self.conversation_history, api_key, api_url, hunyuan_api_url)
            self.current_worker.chunk_received.connect(self.on_chunk_received)
            self.current_worker.response_received.connect(self.on_response_received)
            self.current_worker.error_occurred.connect(self.on_error_occurred)
            self.current_worker.finished.connect(self.on_generation_finished)
            self.current_worker.start()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动生成失败: {str(e)}")
            self.generate_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
    def on_chunk_received(self, chunk):
        if not hasattr(self, '_current_response'):
            self._current_response = ""
        self._current_response += chunk
        if getattr(self, 'raw_checkbox', None) and self.raw_checkbox.isChecked():
            self.result_text.setPlainText(self._current_response)
        else:
            content = self._current_response
            content = re.sub(r'^用户[:：].*?(?=AI[:：]|$)', '', content, flags=re.DOTALL | re.MULTILINE).strip()
            content = re.sub(r'^AI[:：].*?\\n', '', content, flags=re.MULTILINE).strip()
            content_html = markdown_to_html(content)
            self.result_text.setHtml(content_html)
        scrollbar = self.result_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    def on_response_received(self, response):
        if getattr(self, 'raw_checkbox', None) and self.raw_checkbox.isChecked():
            self.conversation_history.append({"role": "assistant", "content": response})
            self.result_text.setPlainText(response)
        else:
            import re as _re2
            content = response
            content = _re2.sub(r'^用户[:：].*?(?=AI[:：]|$)', '', content, flags=_re2.DOTALL | _re2.MULTILINE).strip()
            content = _re2.sub(r'^AI[:：].*?\\n', '', content, flags=_re2.MULTILINE).strip()
            self.conversation_history.append({"role": "assistant", "content": content})
            content_html = markdown_to_html(content)
            self.result_text.setHtml(content_html)
        if hasattr(self, '_current_response'):
            self._current_response = ""
    def on_error_occurred(self, error):
        if self.conversation_history and self.conversation_history[-1]["role"] == "user":
            self.conversation_history.pop()
        error_html = f'<div style="padding: 20px; background-color: rgba(255, 68, 68, 0.1); border-left: 3px solid #ff4444; border-radius: 8px;"><h3 style="color: #ff4444; margin-bottom: 10px;">❌ 错误</h3><p style="color: #e0e0e0;">{escape_html(str(error))}</p></div>'
        self.result_text.setHtml(error_html)
        QMessageBox.critical(self, "错误", f"生成失败: {error}")
    def on_generation_finished(self):
        self.generate_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
    def save_chat_mode_config(self, provider, model, last_input):
        try:
            config = {'last_provider': provider, 'last_model': model, 'last_input': last_input, 'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            with open(self.chat_mode_config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    def stop_generation(self):
        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.stop()
            if self.current_worker.isRunning():
                self.current_worker.wait(2000)
    def save_result(self):
        content = self.result_text.toPlainText()
        if not content or not content.strip():
            QMessageBox.information(self, "提示", "结果为空，无法保存！")
            return
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"AI_Agent_结果_{timestamp}.txt"
        file_path, _ = QFileDialog.getSaveFileName(self, "保存结果", default_name, "文本文件 (*.txt);;Markdown文件 (*.md);;所有文件 (*.*)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                QMessageBox.information(self, "成功", f"结果已保存到:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存失败: {str(e)}")
    def clear_result(self):
        if self.result_text.toPlainText().strip():
            reply = QMessageBox.question(self, "确认清空", "确定要清空结果输出吗？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.result_text.setHtml("<div style='text-align: center; color: #444444; font-size: 14px; margin-top: 100px; line-height: 2;'><div>结果将在这里显示</div><div style='font-size: 12px; color: #333; margin-top: 15px;'>支持富文本格式和自动换行</div></div>")
                self.conversation_history.clear()
        else:
            self.result_text.setHtml("<div style='text-align: center; color: #444444; font-size: 14px; margin-top: 100px; line-height: 2;'><div>结果将在这里显示</div><div style='font-size: 12px; color: #333; margin-top: 15px;'>支持富文本格式和自动换行</div></div>")
    
    def on_provider_changed_legacy(self, provider):
        """提供商改变时更新模型列表（优先使用API动态获取）"""
        print(f"[AI Agent] 提供商切换: {provider}")
        
        # 阻断信号，避免在填充列表时触发on_model_changed
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        
        # 优先使用缓存的动态模型
        if provider in self.dynamic_models_cache:
            models = self.dynamic_models_cache[provider]
            print(f"[AI Agent] 使用缓存的动态模型: {len(models)}个")
        else:
            # 尝试从API动态获取
            models = self.fetch_models_from_api(provider)
            if models:
                self.dynamic_models_cache[provider] = models
                print(f"[AI Agent] 从API获取模型: {len(models)}个")
            elif self.ai_client:
                # 降级到配置文件
                try:
                    self.ai_client.set_provider(provider)
                    models = self.ai_client.get_available_models()
                    print(f"[AI Agent] 使用配置文件模型: {len(models)}个")
                except Exception as e:
                    print(f"[AI Agent] 获取配置模型失败: {e}")
                    models = []
            else:
                models = []
        
        if not models:
            self.model_combo.addItem(f"⚠️ {provider} 暂无可用模型")
            self.model_combo.setEnabled(False)
        else:
            self.model_combo.setEnabled(True)
            self.model_combo.addItems(models)
            
            # 尝试恢复上次选择的模型
            saved_model = self.last_selected_models.get(provider, "")
            if saved_model and saved_model in models:
                index = self.model_combo.findText(saved_model)
                if index >= 0:
                    self.model_combo.setCurrentIndex(index)
                    print(f"[AI Agent] 恢复上次选择的模型: {saved_model}")
            elif self.ai_client:
                # 使用默认模型
                try:
                    default_model = self.ai_client.get_default_model()
                    if default_model in models:
                        index = self.model_combo.findText(default_model)
                        if index >= 0:
                            self.model_combo.setCurrentIndex(index)
                            print(f"[AI Agent] 使用默认模型: {default_model}")
                except:
                    pass
        
        # 恢复信号
        self.model_combo.blockSignals(False)
        print(f"[AI Agent] 当前模型: {self.model_combo.currentText()}")
    
    def fetch_models_from_api_legacy(self, provider):
        """从API动态获取模型列表（与talkAPI.py的TestThread保持一致）"""
        try:
            # 加载API配置
            if not os.path.exists(self.config_file):
                print(f"[AI Agent] 配置文件不存在，无法获取API Key")
                return []
            
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            api_key = config.get(f'{provider.lower()}_api_key', '')
            if not api_key:
                print(f"[AI Agent] {provider} 未配置API Key")
                return []
            
            api_url = config.get('api_url', 'https://manju.chat')
            hunyuan_api_url = config.get('hunyuan_api_url', 'https://api.vectorengine.ai')
            
            # Hunyuan使用特殊的API地址
            if provider == "Hunyuan":
                api_url = hunyuan_api_url
            
            import http.client
            import ssl
            from urllib.parse import urlparse
            
            # 解析URL
            parsed = urlparse(api_url)
            host = parsed.netloc or parsed.path.split('/')[0]
            
            if not host:
                print(f"[AI Agent] API地址格式错误: {api_url}")
                return []
            
            # 创建HTTPS连接
            context = ssl.create_default_context()
            conn = http.client.HTTPSConnection(host, context=context, timeout=10)
            
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            # 获取模型列表
            conn.request('GET', '/v1/models', '', headers)
            res = conn.getresponse()
            data = res.read()
            conn.close()
            
            if res.status == 200:
                result = json.loads(data.decode('utf-8'))
                if 'data' in result:
                    all_models = [model['id'] for model in result['data']]
                    
                    # 筛选当前提供商的模型（与talkAPI.py保持一致）
                    provider_models = []
                    provider_lower = provider.lower()
                    
                    for model_id in all_models:
                        if (provider_lower == "hunyuan" and model_id.startswith("hunyuan")) or \
                           (provider_lower == "chatgpt" and model_id.startswith("gpt")) or \
                           (provider_lower == "chatgpt" and model_id.startswith("o1")) or \
                           (provider_lower == "chatgpt" and model_id.startswith("o3")) or \
                           (provider_lower == "chatgpt" and model_id.startswith("chatgpt")) or \
                           (provider_lower == "deepseek" and model_id.startswith("deepseek")) or \
                           (provider_lower == "claude" and model_id.startswith("claude")) or \
                           ("gemini" in provider_lower and model_id.startswith("gemini")):
                            provider_models.append(model_id)
                    
                    print(f"[AI Agent] 从API获取到 {len(provider_models)} 个 {provider} 模型")
                    return provider_models
                else:
                    print(f"[AI Agent] API响应格式异常")
                    return []
            else:
                print(f"[AI Agent] API返回错误: {res.status}")
                return []
                
        except Exception as e:
            print(f"[AI Agent] 从API获取模型失败: {e}")
            return []
    
    def on_model_changed_legacy(self, model: str):
        """模型切换时记录选择（与CHAT保持一致）"""
        provider = self.provider_combo.currentText()
        if provider and model:
            self.last_selected_models[provider] = model
            print(f"[AI Agent] 记录模型选择: {provider} -> {model}")
    
    def load_config_legacy(self):
        """加载配置（与CHAT保持一致）"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                    # 加载默认提供商
                    provider = config.get('default_provider', 'DeepSeek')
                    index = self.provider_combo.findText(provider)
                    if index >= 0:
                        self.provider_combo.setCurrentIndex(index)
                    else:
                        # 如果找不到，使用第一个可用提供商
                        if self.providers:
                            self.provider_combo.setCurrentIndex(0)
                            provider = self.providers[0]
                    
                    # 手动触发一次模型列表更新（确保加载完整模型列表）
                    self.on_provider_changed(provider)
            else:
                # 配置文件不存在，使用默认提供商
                if self.providers:
                    default_provider = 'DeepSeek' if 'DeepSeek' in self.providers else self.providers[0]
                    index = self.provider_combo.findText(default_provider)
                    if index >= 0:
                        self.provider_combo.setCurrentIndex(index)
                        self.on_provider_changed(default_provider)
        except Exception as e:
            print(f"[AI Agent] 加载配置失败: {e}")
            import traceback
            traceback.print_exc()
    
    def clear_conversation(self):
        """清空对话历史"""
        if len(self.conversation_history) > 0:
            reply = QMessageBox.question(
                self, 
                "清空对话", 
                f"当前有 {len(self.conversation_history)} 条对话记录，确定要清空吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.conversation_history.clear()
                self.text_input.clear()
                self.result_text.clear()
        else:
            self.text_input.clear()
            self.result_text.clear()
    
    def on_generate_legacy(self):
        """生成按钮点击 - 发送消息"""
        try:
            text = self.text_input.toPlainText().strip()
            if not text:
                QMessageBox.warning(self, "提示", "请输入提示词！")
                return
            
            # 获取当前配置
            provider = self.provider_combo.currentText()
            model = self.model_combo.currentText()
            
            # 加载API Key
            try:
                if os.path.exists(self.config_file):
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        api_key = config.get(f'{provider.lower()}_api_key', '')
                        api_url = config.get('api_url', 'https://manju.chat')
                        hunyuan_api_url = config.get('hunyuan_api_url', 'https://api.vectorengine.ai')
                        
                        if not api_key:
                            QMessageBox.warning(self, "提示", f"请先配置 {provider} 的 API Key！")
                            return
                else:
                    QMessageBox.warning(self, "提示", "请先在 API 设置中配置 API Key！")
                    return
            except Exception as e:
                QMessageBox.critical(self, "错误", f"读取配置失败: {str(e)}")
                return
            
            # 添加用户消息到历史
            self.conversation_history.append({"role": "user", "content": text})
            
            # 显示用户消息
            self.result_text.append(f'<div style="color: #00bfff; font-weight: bold; margin-top: 10px;">👤 你:</div>')
            self.result_text.append(f'<div style="color: #e0e0e0; margin-bottom: 15px;">{text}</div>')
            self.result_text.append(f'<div style="color: #00ff88; font-weight: bold;">🤖 {provider} ({model}):</div>')
            
            # 禁用生成按钮，启用停止按钮
            self.generate_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            
            # 创建工作线程
            self.current_worker = ChatWorker(provider, model, self.conversation_history, api_key, api_url, hunyuan_api_url)
            self.current_worker.chunk_received.connect(self.on_chunk_received)
            self.current_worker.response_received.connect(self.on_response_received)
            self.current_worker.error_occurred.connect(self.on_error_occurred)
            self.current_worker.finished.connect(self.on_generation_finished)
            self.current_worker.start()
            
        except Exception as e:
            print(f"[生成启动错误] {e}")
            QMessageBox.critical(self, "错误", f"启动生成失败: {str(e)}")
            self.generate_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
    
    def on_chunk_received_legacy(self, chunk):
        """接收流式响应片段"""
        self.result_text.insertPlainText(chunk)
        # 自动滚动到底部
        cursor = self.result_text.textCursor()
        cursor.movePosition(cursor.End)
        self.result_text.setTextCursor(cursor)
    
    def on_response_received_legacy(self, response):
        """接收完整响应"""
        # 添加助手消息到历史
        self.conversation_history.append({"role": "assistant", "content": response})
        self.result_text.append("\n" + "="*50 + "\n")
    
    def on_error_occurred_legacy(self, error):
        """处理错误"""
        self.result_text.append(f'<div style="color: #ff4444; font-weight: bold;">❌ 错误: {error}</div>\n')
    
    def on_generation_finished_legacy(self):
        """生成完成"""
        self.generate_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
    
    def stop_generation_legacy(self):
        """停止生成"""
        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.stop()
            self.result_text.append(f'<div style="color: #ffaa00;">⏸️ 已停止生成</div>\n')
    
    def open_api_settings(self):
        """打开API设置对话框"""
        try:
            from talkAPI import TalkAPIDialog
            dialog = TalkAPIDialog(self)
            if dialog.exec():
                self.load_config()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开API设置失败: {str(e)}")
