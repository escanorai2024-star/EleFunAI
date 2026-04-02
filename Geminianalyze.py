
import os
import json
import base64
import requests
import traceback
import ssl
import math
from requests.adapters import HTTPAdapter
try:
    from urllib3.util.ssl_ import create_urllib3_context
except ImportError:
    from requests.packages.urllib3.util.ssl_ import create_urllib3_context

# Lazy import handling for OpenCV to avoid top-level conflicts and capture errors in GUI
CV2_IMPORT_ERROR = None
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except Exception as e:
    CV2_IMPORT_ERROR = str(e)
    CV2_AVAILABLE = False

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QTextEdit, QFileDialog, 
    QGraphicsProxyWidget, QMessageBox, QApplication
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont

from lingdongconnect import ConnectableNode, DataType

class CustomSSLAdapter(HTTPAdapter):
    """
    A custom SSL adapter to allow legacy renegotiation and lower security level
    to fix SSLEOFError with some servers.
    """
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context()
        try:
            # Lower security level to allow more ciphers
            context.set_ciphers('DEFAULT@SECLEVEL=1')
            # Option to allow legacy renegotiation if supported by OpenSSL version
            if hasattr(ssl, 'OP_LEGACY_SERVER_CONNECT'):
                context.options |= ssl.OP_LEGACY_SERVER_CONNECT
        except Exception:
            pass
        kwargs['ssl_context'] = context
        return super(CustomSSLAdapter, self).init_poolmanager(*args, **kwargs)

class VideoAnalysisWorker(QThread):
    """Worker thread for Gemini Video Analysis to avoid freezing UI"""
    log_signal = Signal(str)
    result_signal = Signal(object)
    finished_signal = Signal()
    
    def __init__(self, api_key, api_url, video_path, headers):
        super().__init__()
        self.api_key = api_key
        self.api_url = api_url
        self.video_path = video_path
        self.headers = headers
        
        # Register to global registry to prevent GC
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_gemini_workers'):
                app._active_gemini_workers = []
            app._active_gemini_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        app = QApplication.instance()
        if app and hasattr(app, '_active_gemini_workers'):
            if self in app._active_gemini_workers:
                app._active_gemini_workers.remove(self)
        self.deleteLater()
        
    def extract_frames(self, video_path, interval_seconds=2.0, max_frames=200):
        """Extract keyframes from video at set intervals and return frames + timecodes + duration"""
        frames = []
        timecodes = []
        duration_info = "Unknown duration"
        
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return [], [], duration_info
            
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            
            # Calculate duration
            if fps > 0 and total_frames > 0:
                duration_sec = total_frames / fps
                mins = int(duration_sec // 60)
                secs = int(duration_sec % 60)
                duration_info = f"{mins:02d}:{secs:02d}"
            
            if total_frames <= 0 or fps <= 0:
                # Fallback if frame count is unknown: read until end
                return [], [], duration_info
            
            # Calculate step based on interval
            step = int(fps * interval_seconds)
            if step < 1: step = 1
            
            count = 0
            for i in range(0, total_frames, step):
                if count >= max_frames:
                    break
                    
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Resize to reduce size (max 512px width for better compression)
                h, w = frame.shape[:2]
                if w > 512:
                    ratio = 512 / w
                    new_h = int(h * ratio)
                    frame = cv2.resize(frame, (512, new_h))
                
                # Encode as JPEG with lower quality (60) to save space
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
                frame_b64 = base64.b64encode(buffer).decode('utf-8')
                frames.append(frame_b64)
                
                # Calculate timecode for this frame
                current_sec = i / fps
                tc_min = int(current_sec // 60)
                tc_sec = int(current_sec % 60)
                timecodes.append(f"{tc_min:02d}:{tc_sec:02d}")
                
                count += 1
            
            cap.release()
            return frames, timecodes, duration_info
        except Exception as e:
            # Re-raise to be caught by caller
            raise e

    def run(self):
        try:
            self.log_signal.emit(f"DEBUG: Starting analysis thread for {self.video_path}")
            
            # 1. Read Video File
            self.log_signal.emit("DEBUG: Reading video file...")
            file_size = os.path.getsize(self.video_path)
            self.log_signal.emit(f"DEBUG: Video file size: {file_size} bytes")
            
            use_frames = False
            video_base64 = ""
            extracted_frames = []
            frame_timecodes = []
            video_duration = "Unknown"

            # Threshold: 20MB. If larger, try frame extraction if cv2 available
            if file_size > 20 * 1024 * 1024: 
                # Re-check availability or try lazy import if not already available
                global CV2_AVAILABLE, CV2_IMPORT_ERROR
                if not CV2_AVAILABLE:
                    try:
                        import cv2
                        import numpy as np
                        CV2_AVAILABLE = True
                        CV2_IMPORT_ERROR = None
                        self.log_signal.emit("DEBUG: OpenCV lazy import successful.")
                    except Exception as e:
                        CV2_IMPORT_ERROR = str(e)
                        self.log_signal.emit(f"WARNING: OpenCV lazy import failed: {e}")

                if CV2_AVAILABLE:
                    self.log_signal.emit("DEBUG: Video > 20MB. Extracting keyframes to reduce payload size...")
                    try:
                        # Increased sampling rate (1.0s) and max frames (300) for better accuracy
                        extracted_frames, frame_timecodes, video_duration = self.extract_frames(self.video_path, interval_seconds=1.0, max_frames=300)
                        if extracted_frames:
                            use_frames = True
                            self.log_signal.emit(f"DEBUG: Extracted {len(extracted_frames)} frames. Duration: {video_duration}")
                        else:
                            self.log_signal.emit("WARNING: Frame extraction returned no frames. Falling back to full upload.")
                    except Exception as e:
                         self.log_signal.emit(f"WARNING: Frame extraction failed: {e}. Falling back to full upload.")
                else:
                    self.log_signal.emit(f"WARNING: Video > 20MB but OpenCV not available. Error: {CV2_IMPORT_ERROR}. Attempting full upload (may fail).")


            if not use_frames:
                try:
                    with open(self.video_path, "rb") as video_file:
                        video_data = video_file.read()
                        video_base64 = base64.b64encode(video_data).decode('utf-8')
                    self.log_signal.emit(f"DEBUG: Video read successfully.")
                except Exception as e:
                    self.log_signal.emit(f"ERROR: Failed to read video file: {e}")
                    return

            # 2. Construct Prompt
            headers_str = ", ".join(self.headers)
            
            duration_context = ""
            timecode_map = ""
            if use_frames and video_duration != "Unknown":
                duration_context = f"The video duration is approximately {video_duration}. These are {len(extracted_frames)} keyframes extracted at 2-second intervals."
                # Build timecode map string
                tc_entries = []
                for idx, tc in enumerate(frame_timecodes):
                    tc_entries.append(f"Image {idx+1}: {tc}")
                timecode_map = "Frame Timecodes:\n" + ", ".join(tc_entries)
            
            base_prompt = (
                f"Please analyze this {'video' if not use_frames else 'sequence of keyframes from a video'} and extract information to populate a table with the following columns: {headers_str}.\n"
                f"{duration_context}\n"
                f"{timecode_map}\n"
                f"Specific requirements for columns:\n"
                f"- '时间码' (Timecode): Use the provided 'Frame Timecodes' map to determine the exact start and end time for each scene/shot. Format: 'MM:SS-MM:SS'.\n"
                f"- '台词/音效' (Dialogue/Sound): Transcribe ALL visible subtitles found in the frames. Look closely at each frame. If no subtitles are visible, leave empty. DO NOT invent dialogue.\n"
                f"- '运镜' (Camera Movement): Use professional terms (e.g., Pan, Tilt, Zoom In/Out, Static, Tracking, Dolly).\n"
                f"- '画面内容' (Visual Content): Describe the action and scene in detail.\n"
                f"Return the result ONLY as a raw JSON array of objects, where each object represents a row and keys correspond to the columns.\n"
                f"IMPORTANT: Do not include any explanation, thinking process, or markdown formatting like ```json. Just output the raw JSON."
            )
            self.log_signal.emit(f"DEBUG: Prompt constructed: {base_prompt[:100]}...")

            # 3. Prepare Request
            base_url = self.api_url.rstrip('/')
            
            # Detect VectorEngine or similar services that might be configured with /v1 but support Google Native
            # User specifically requested to follow VectorEngine docs which use Google Native format
            is_vectorengine = "vectorengine" in base_url
            
            if base_url.endswith("/v1") and not is_vectorengine:
                # OpenAI-compatible Mode (Generic)
                self.log_signal.emit("DEBUG: Detected OpenAI-compatible endpoint (ends with /v1). Switching to OpenAI format.")
                target_url = f"{base_url}/chat/completions"
                
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                }
                
                content_list = [{"type": "text", "text": base_prompt}]
                
                if use_frames:
                    # Add frames as images
                    for frame_b64 in extracted_frames:
                        content_list.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{frame_b64}",
                                "detail": "low" # Use low detail to save tokens/bandwidth if supported
                            }
                        })
                else:
                    # Add full video
                    content_list.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:video/mp4;base64,{video_base64}"
                        }
                    })

                payload = {
                    "model": "gemini-2.5-pro", 
                    "messages": [
                        {
                            "role": "user",
                            "content": content_list
                        }
                    ],
                    "max_tokens": 4096,
                    "stream": False
                }
                
            else:
                # Google Native Mode (Default or VectorEngine)
                if is_vectorengine and base_url.endswith("/v1"):
                    # Fix base URL for VectorEngine if user entered /v1
                    base_url = base_url[:-3]
                    self.log_signal.emit("DEBUG: Detected VectorEngine with /v1. Switching to Google Native format as per docs.")
                
                target_url = f"{base_url}/v1beta/models/gemini-3-pro-preview?key={self.api_key}"
                self.log_signal.emit(f"DEBUG: Using Google Native Endpoint: {target_url}")
                
                headers = {
                    "Content-Type": "application/json"
                }
                
                parts = []
                if use_frames:
                     for frame_b64 in extracted_frames:
                         parts.append({
                             "inline_data": {
                                 "mime_type": "image/jpeg",
                                 "data": frame_b64
                             }
                         })
                     parts.append({"text": base_prompt})
                else:
                    parts = [
                        {
                            "inline_data": {
                                "mime_type": "video/mp4",
                                "data": video_base64
                            }
                        },
                        {
                            "text": base_prompt
                        }
                    ]

                payload = {
                    "contents": [{
                        "role": "user",
                        "parts": parts
                    }]
                }
            
            self.log_signal.emit(f"DEBUG: Sending request to {target_url}...")
            
            # Add User-Agent to mimic a browser/standard client
            headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            
            # Explicitly disable proxies to avoid system proxy interference (common cause of SSLEOFError)
            proxies = {"http": None, "https": None}
            
            # Create a session with robust SSL handling
            session = requests.Session()
            session.proxies.update(proxies)
            session.headers.update(headers)
            
            # Mount custom adapter for https
            try:
                adapter = CustomSSLAdapter()
                session.mount("https://", adapter)
            except Exception as e:
                self.log_signal.emit(f"WARNING: Failed to mount custom SSL adapter: {e}")
            
            try:
                # Increased timeout to 600s for large video analysis
                response = session.post(target_url, json=payload, timeout=600)
            except requests.exceptions.SSLError as e:
                self.log_signal.emit(f"WARNING: SSL Error encountered. Retrying with verify=False... ({e})")
                try:
                    import urllib3
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                    # Retry with verify=False using a FRESH request (bypassing session/adapter issues)
                    # Also ensure proxies are explicitly disabled for this request
                    response = requests.post(
                        target_url, 
                        json=payload, 
                        headers=headers,
                        timeout=600, 
                        verify=False,
                        proxies={"http": None, "https": None}
                    )
                except Exception as e2:
                    self.log_signal.emit(f"ERROR: Retry with verify=False failed: {e2}")
                    return
            except Exception as e:
                self.log_signal.emit(f"ERROR: Request failed: {e}")
                return

            self.log_signal.emit(f"DEBUG: Response Status Code: {response.status_code}")
            # self.log_signal.emit(f"DEBUG: Response Content: {response.text}") # Too long
            
            if response.status_code == 200:
                result = response.json()
                text_content = ""
                
                # Parse based on structure
                if "candidates" in result:
                    # Google Native structure
                    try:
                        parts = result['candidates'][0].get('content', {}).get('parts', [])
                        text_chunks = []
                        for p in parts:
                            t = p.get('text')
                            if t:
                                text_chunks.append(t)
                        text_content = "\n".join(text_chunks)
                    except:
                         self.log_signal.emit(f"ERROR: Unexpected Google response format: {result}")
                elif "choices" in result:
                    # OpenAI structure
                    try:
                        text_content = result['choices'][0]['message']['content']
                    except:
                        self.log_signal.emit(f"ERROR: Unexpected OpenAI response format: {result}")
                else:
                    self.log_signal.emit(f"ERROR: Unknown response format: {result}")
                    return

                self.log_signal.emit("DEBUG: Parsed text content from response.")
                
                # Robust JSON Extraction
                text_content = text_content.strip()
                
                # 1. Remove markdown code blocks if present
                if "```json" in text_content:
                    # Find the content inside ```json ... ```
                    try:
                        start = text_content.find("```json") + 7
                        end = text_content.rfind("```")
                        if end > start:
                            text_content = text_content[start:end].strip()
                    except:
                        pass
                elif "```" in text_content:
                     try:
                        start = text_content.find("```") + 3
                        end = text_content.rfind("```")
                        if end > start:
                            text_content = text_content[start:end].strip()
                     except:
                        pass
                
                # 2. Heuristic extraction: Look for outer-most brackets if not clean
                try:
                    # If it doesn't start with [ or {, try to find them
                    if not (text_content.startswith('[') or text_content.startswith('{')):
                        p1 = text_content.find('[')
                        p2 = text_content.find('{')
                        start = -1
                        if p1 != -1 and p2 != -1:
                            start = min(p1, p2)
                        elif p1 != -1:
                            start = p1
                        elif p2 != -1:
                            start = p2
                        
                        if start != -1:
                            # Find corresponding end
                            # We need to determine if we matched [ or {
                            is_array = (text_content[start] == '[')
                            end = text_content.rfind(']' if is_array else '}')
                            if end != -1 and end > start:
                                text_content = text_content[start:end+1]
                except Exception as e:
                     self.log_signal.emit(f"WARNING: Heuristic JSON extraction failed: {e}")

                try:
                    json_data = json.loads(text_content)
                    self.result_signal.emit(json_data)
                    self.log_signal.emit("DEBUG: Analysis successful. Data parsed.")
                except json.JSONDecodeError as e:
                     self.log_signal.emit(f"ERROR: Failed to parse JSON content: {e}\nContent: {text_content[:200]}...")
                     try:
                         hdrs = self.headers if isinstance(self.headers, list) else []
                         row = {}
                         target_content_header = None
                         for h in hdrs:
                             if h == "画面内容" or h.lower() in ("content", "description"):
                                 target_content_header = h
                                 break
                         if not target_content_header and hdrs:
                             target_content_header = hdrs[0]
                         if target_content_header:
                             row[target_content_header] = text_content.strip()
                         if "备注" in hdrs:
                             row["备注"] = "模型返回非JSON文本，已按文本填充"
                         # Ensure at least one field exists
                         if not row and text_content.strip():
                             row = {"画面内容": text_content.strip()}
                         self.result_signal.emit([row])
                         self.log_signal.emit("DEBUG: Fallback: emitted single-row text content to target table.")
                     except Exception as e2:
                         self.log_signal.emit(f"ERROR: Fallback row emission failed: {e2}")
            else:
                self.log_signal.emit(f"ERROR: API Request Failed: {response.text}")
                
        except Exception as e:
            self.log_signal.emit(f"ERROR: Unexpected error in worker: {traceback.format_exc()}")
        finally:
            self.finished_signal.emit()

class GeminiAnalyzeNodeFactory:
    @staticmethod
    def create_node(CanvasNode):
        class GeminiAnalyzeNode(ConnectableNode, CanvasNode):
            def __init__(self, x, y):
                CanvasNode.__init__(self, x, y, 240, 300, "Gemini分析", "")
                ConnectableNode.__init__(self)
                
                # Sockets
                self.add_input_socket(DataType.ANY, "输入")
                self.add_output_socket(DataType.TABLE, "输出(剧本)")
                
                # UI Components
                self.video_path = None
                self.setup_ui()
                
                # Load Config
                self.api_key = ""
                self.api_url = ""
                self.load_api_config()
                
            def setup_ui(self):
                # Main Widget
                self.widget = QWidget()
                self.widget.setStyleSheet("background-color: transparent;")
                layout = QVBoxLayout(self.widget)
                layout.setContentsMargins(10, 40, 10, 10)
                
                # Upload Button
                self.upload_btn = QPushButton("📄 上传视频")
                self.upload_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #4CAF50; 
                        color: white;
                        border-radius: 5px;
                        padding: 8px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #45a049;
                    }
                """)
                self.upload_btn.clicked.connect(self.select_video)
                layout.addWidget(self.upload_btn)
                
                # Path Label
                self.path_label = QLabel("未选择视频")
                self.path_label.setStyleSheet("color: #aaaaaa; font-size: 10px;")
                self.path_label.setWordWrap(True)
                layout.addWidget(self.path_label)
                
                # Log Area
                self.log_area = QTextEdit()
                self.log_area.setReadOnly(True)
                self.log_area.setStyleSheet("""
                    QTextEdit {
                        background-color: #222222;
                        color: #00ff00;
                        font-family: Consolas, monospace;
                        font-size: 10px;
                        border: 1px solid #444;
                        border-radius: 4px;
                    }
                """)
                self.log_area.setLineWrapMode(QTextEdit.NoWrap)  # Disable line wrapping for cleaner log view
                self.log_area.setPlaceholderText("DEBUG Log will appear here...")
                layout.addWidget(self.log_area)

                # Copy Button
                self.copy_btn = QPushButton("📋 复制日志")
                self.copy_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #555555; 
                        color: white;
                        border-radius: 3px;
                        padding: 5px;
                        font-size: 10px;
                    }
                    QPushButton:hover {
                        background-color: #666666;
                    }
                """)
                self.copy_btn.clicked.connect(self.copy_log)
                layout.addWidget(self.copy_btn)
                
                self.proxy_widget = QGraphicsProxyWidget(self)
                self.proxy_widget.setWidget(self.widget)
                self.proxy_widget.setPos(0, 0)
                self.proxy_widget.resize(self.rect().width(), self.rect().height())
                
            def setRect(self, *args):
                super().setRect(*args)
                if hasattr(self, 'proxy_widget'):
                    self.proxy_widget.resize(self.rect().width(), self.rect().height())

            def select_video(self):
                file_path, _ = QFileDialog.getOpenFileName(
                    None, "选择视频", "", "Video Files (*.mp4 *.avi *.mov *.mkv)"
                )
                if file_path:
                    self.video_path = file_path
                    self.path_label.setText(os.path.basename(file_path))
                    self.log(f"DEBUG: Video selected: {file_path}")
            
            def copy_log(self):
                clipboard = QApplication.clipboard()
                clipboard.setText(self.log_area.toPlainText())
                self.log("DEBUG: Log copied to clipboard.")

            def log(self, message):
                self.log_area.append(message)
                # Auto scroll
                sb = self.log_area.verticalScrollBar()
                sb.setValue(sb.maximum())
                
            def load_api_config(self):
                try:
                    # Try to load from json/talk_api_config.json
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    json_path = os.path.join(base_dir, "json", "talk_api_config.json")
                    
                    if os.path.exists(json_path):
                        with open(json_path, 'r', encoding='utf-8') as f:
                            config = json.load(f)
                            self.api_url = config.get("api_url", "https://manju.chat")
                            self.log(f"DEBUG: Config loaded. URL: {self.api_url}")
                            self.log(f"DEBUG: Available keys in config: {list(config.keys())}")
                            
                            # talkAPI.py saves keys as "{provider.lower()}_api_key"
                            target_key_name = "gemini 2.5_api_key"
                            self.api_key = config.get(target_key_name, "")
                            
                            if self.api_key:
                                self.log(f"DEBUG: API Key found for Gemini 2.5 (Key length: {len(self.api_key)})")
                            else:
                                self.log(f"WARNING: API Key '{target_key_name}' not found or empty in config!")
                                # Fallback: try looking for keys containing 'gemini'
                                for k, v in config.items():
                                    if 'gemini' in k.lower() and 'api_key' in k.lower() and v:
                                        self.api_key = v
                                        self.log(f"DEBUG: Fallback - Found alternative key in '{k}'")
                                        break
                    else:
                        self.log("ERROR: Config file not found!")
                except Exception as e:
                    self.log(f"ERROR: Failed to load config: {e}")

            def on_socket_connected(self, socket, connection):
                """Handle connection event"""
                # Check if we are connecting TO a GoogleScriptNode
                if socket in self.output_sockets:
                    target_socket = connection.target_socket
                    if target_socket:
                        target_node = target_socket.parent_node
                        # Identify GoogleScriptNode by title or table attribute
                        if "谷歌" in target_node.node_title or hasattr(target_node, "table"):
                            self.log("DEBUG: Connected to Google Script Node.")
                            self.trigger_analysis(target_node)
                        else:
                            self.log(f"DEBUG: Connected to {target_node.node_title}, but expected Google Script Node.")

            def trigger_analysis(self, target_node):
                # Reload config to ensure we have the latest key
                self.load_api_config()
                
                if not self.video_path:
                    self.log("ERROR: No video selected. Please upload a video first.")
                    return
                if not self.api_key:
                    self.log("ERROR: No API Key configured. Please check Settings.")
                    return
                
                # Get Headers
                headers = []
                if hasattr(target_node, "table"):
                    for c in range(target_node.table.columnCount()):
                        item = target_node.table.horizontalHeaderItem(c)
                        headers.append(item.text() if item else f"Col {c}")
                
                if not headers:
                    self.log("ERROR: Could not retrieve headers from target node.")
                    return
                
                # Auto-upgrade headers if they match the old format
                old_headers = ["镜号", "时间码", "景别", "画面内容", "台词/音效", "备注", "开始帧", "结束帧"]
                if headers == old_headers:
                    self.log("DEBUG: Detected old headers. Upgrading target node to new format...")
                    new_headers = ["镜号", "时间码", "景别", "画面内容", "人物", "人物关系/构图", "地点/环境", "运镜", "台词/音效", "备注"]
                    if hasattr(target_node, "headers"):
                        try:
                            target_node.headers = new_headers
                            headers = new_headers
                            self.log("DEBUG: Headers upgraded successfully.")
                        except Exception as e:
                            self.log(f"WARNING: Could not upgrade headers: {e}")

                self.log(f"DEBUG: Target Headers: {headers}")
                
                # Start Worker
                self.worker = VideoAnalysisWorker(self.api_key, self.api_url, self.video_path, headers)
                self.worker.log_signal.connect(self.log)
                self.worker.result_signal.connect(lambda data: self.update_target_node(target_node, data))
                self.worker.start()
                
            def update_target_node(self, target_node, data):
                """Update the Google Script Node with analysis results"""
                if not hasattr(target_node, "table"):
                    self.log("ERROR: Target node has no table.")
                    return
                
                try:
                    headers = []
                    for c in range(target_node.table.columnCount()):
                        item = target_node.table.horizontalHeaderItem(c)
                        headers.append(item.text() if item else f"Col {c}")
                    
                    def normalize_to_rows(obj, hdrs):
                        if isinstance(obj, list):
                            return obj
                        if isinstance(obj, dict):
                            if "data" in obj and isinstance(obj["data"], list):
                                return obj["data"]
                            if "rows" in obj and isinstance(obj["rows"], list):
                                return obj["rows"]
                            vals = [v for v in obj.values() if isinstance(v, dict)]
                            if vals:
                                return vals
                            row = {}
                            for h in hdrs:
                                if h in obj:
                                    row[h] = obj[h]
                            if row:
                                return [row]
                            return []
                        return []
                    
                    rows = normalize_to_rows(data, headers)
                    self.log(f"DEBUG: Updating target table with {len(rows)} rows...")
                    
                    if len(rows) > 0 and isinstance(rows[0], dict):
                        self.log(f"DEBUG: Data sample (first row keys): {list(rows[0].keys())}")

                    # Clear existing data? Maybe not, just append or overwrite?
                    # Let's clear for now to show fresh results
                    target_node.table.setRowCount(0)
                    
                    self.log(f"DEBUG: Table Headers: {headers}")

                    for row_idx, row_obj in enumerate(rows):
                        target_node.table.insertRow(row_idx)
                        
                        for col_idx, header in enumerate(headers):
                            # Try to find value by header name with fallback strategies
                            val = ""
                            if isinstance(row_obj, dict):
                                val = row_obj.get(header, "")
                            else:
                                val = str(row_obj)
                            
                            # Fallback 1: Case-insensitive match
                            if not val:
                                if isinstance(row_obj, dict):
                                    for k, v in row_obj.items():
                                        if k.strip().lower() == header.strip().lower():
                                            val = v
                                            break
                            
                            # Fallback 2: Partial match (e.g. "人物" in "人物(Character)")
                            if not val:
                                if isinstance(row_obj, dict):
                                    for k, v in row_obj.items():
                                        if header in k or k in header:
                                            val = v
                                            break

                            if not val:
                                # debug specific missing keys for first row
                                if row_idx == 0:
                                    # self.log(f"DEBUG: Could not find value for header '{header}' in row keys: {list(row_obj.keys())}")
                                    pass
                            
                            from PySide6.QtWidgets import QTableWidgetItem
                            item = QTableWidgetItem(str(val))
                            target_node.table.setItem(row_idx, col_idx, item)
                            
                    self.log("DEBUG: Table updated successfully!")
                    
                    # Ensure table is visible and hint is hidden
                    if hasattr(target_node, "table") and hasattr(target_node, "hint_label"):
                         target_node.table.setVisible(True)
                         target_node.hint_label.setVisible(False)
                         if hasattr(target_node, "batch_magic_btn"):
                             target_node.batch_magic_btn.setVisible(True)
                         self.log("DEBUG: Forced table visibility on target node.")
                    
                except Exception as e:
                    self.log(f"ERROR: Failed to update table: {e}")
                    self.log(traceback.format_exc())

        return GeminiAnalyzeNode
