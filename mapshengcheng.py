import sys
import os
import json
import time
import requests
import base64
from PySide6.QtCore import QObject, Signal, QThread, QSettings
from PySide6.QtWidgets import QApplication

# Import config helpers
try:
    import Agemini
except ImportError:
    Agemini = None
try:
    import Agemini30
except ImportError:
    Agemini30 = None

def _json_path(*parts: str) -> str:
    # Helper to find json path
    if getattr(sys, 'frozen', False):
        root = os.path.dirname(sys.executable)
    else:
        root = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(root, "json", *parts)

class MapImageGenerator(QThread):
    progress = Signal(str)
    image_generated = Signal(str, str) # name, filepath
    finished_all = Signal(int)
    error_occurred = Signal(str)
    debug_info = Signal(str) # For workbench display

    def __init__(self, tasks, style_ref_path=None, parent=None):
        """
        tasks: list of (name, prompt) tuples
        style_ref_path: path to style reference image (optional)
        """
        super().__init__(parent)
        self.tasks = tasks
        self.style_ref_path = style_ref_path
        self.stopped = False
        self.config = {}
        self.provider = "BANANA"

        # Register to global registry to prevent GC
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_map_workers'):
                app._active_map_workers = []
            app._active_map_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        """Clean up worker from global registry"""
        app = QApplication.instance()
        if app and hasattr(app, '_active_map_workers'):
            if self in app._active_map_workers:
                app._active_map_workers.remove(self)
        self.deleteLater()
        
    def run(self):
        # 1. Determine API Provider and Config
        settings = QSettings("GhostOS", "App")
        provider_raw = settings.value("api/image_provider", "BANANA")
        
        provider = "BANANA"
        p_str = str(provider_raw).lower()
        if "midjourney" in p_str:
            provider = "Midjourney"
        elif "banana2" in p_str or "gemini 3" in p_str or "gemini3" in p_str:
            provider = "BANANA2"
        elif "banana" in p_str or "gemini" in p_str:
            provider = "BANANA"
            
        self.debug_info.emit(f"Selected API Provider: {provider} (Raw: {provider_raw})")
        
        # Load Config
        self.config = {}
        if provider == "BANANA":
            if Agemini:
                self.config = Agemini.get_config()
            else:
                self.error_occurred.emit("Agemini module not found")
                return
        elif provider == "BANANA2":
            if Agemini30:
                self.config = Agemini30.get_config()
            else:
                self.error_occurred.emit("Agemini30 module not found")
                return
        elif provider == "Midjourney":
            # Load mj.json manually
            mj_path = _json_path("mj.json")
            if os.path.exists(mj_path):
                try:
                    with open(mj_path, 'r', encoding='utf-8') as f:
                        self.config = json.load(f)
                except Exception as e:
                    self.error_occurred.emit(f"Failed to load mj.json: {e}")
                    return
            else:
                # Fallback to QSettings
                self.config = {
                    "api_key": settings.value("providers/midjourney/api_key", ""),
                    "base_url": settings.value("providers/midjourney/base_url", "")
                }
        
        self.provider = provider
        
        # Output directory
        output_dir = os.path.join(os.getcwd(), "jpg", "scene")
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except Exception as e:
                self.error_occurred.emit(f"Failed to create output directory: {e}")
                return

        count = 0
        for i, (name, prompt) in enumerate(self.tasks):
            if self.stopped: break
            
            self.progress.emit(f"正在生成 {name}")
            self.debug_info.emit(f"Starting generation for {name} with prompt length {len(prompt)}")
            
            try:
                image_data = None
                if self.provider == "Midjourney":
                    image_data = self.generate_mj(prompt)
                elif self.provider in ["BANANA", "BANANA2"]:
                    image_data = self.generate_gemini(prompt)
                
                if image_data:
                    # Save image
                    filename = f"{name}_{int(time.time())}.png"
                    # Sanitize filename
                    filename = "".join([c for c in filename if c.isalpha() or c.isdigit() or c in "._-"]).strip()
                    filepath = os.path.join(output_dir, filename)
                    
                    with open(filepath, "wb") as f:
                        f.write(image_data)
                        
                    self.image_generated.emit(name, filepath)
                    self.debug_info.emit(f"Successfully generated {name}: {filepath}")
                    count += 1
                else:
                    self.error_occurred.emit(f"{name} 生成失败: 未获取到图片数据")
                    self.debug_info.emit(f"Failed to generate {name}: No data returned")
                    
            except Exception as e:
                self.error_occurred.emit(f"{name} 错误: {str(e)}")
                self.debug_info.emit(f"Exception for {name}: {str(e)}")
                
        self.finished_all.emit(count)

    def stop(self):
        self.stopped = True

    def generate_mj(self, prompt):
        api_key = self.config.get('api_key')
        base_url = self.config.get('base_url')
        
        # 获取配置中的比例，默认为 16:9
        size_ratio = self.config.get('size', '16:9')
        
        if self.style_ref_path:
             msg = f"Midjourney 暂不支持自动上传风格参考图: {self.style_ref_path} (已忽略，仅通过提示词传递风格)"
             print(f"[MapImageGenerator] DEBUG: {msg}")
             self.debug_info.emit(msg)
        
        if not api_key or not base_url:
            raise Exception("Midjourney API配置不完整")

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        # 1. Submit
        submit_url = f"{base_url}/mj/submit/imagine"
        payload = {"prompt": f"{prompt} --ar {size_ratio}"} # 使用配置的比例
        
        # Debug: 打印发送给 API 的数据
        debug_msg = f"[MJ API Request] URL: {submit_url}, Payload: {json.dumps(payload, ensure_ascii=False)}"
        print(debug_msg)
        self.debug_info.emit(debug_msg)
        
        resp = requests.post(submit_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        
        res_json = resp.json()
        task_id = res_json.get('result') or res_json.get('taskId') or res_json.get('id')
        
        if not task_id:
            raise Exception("未返回 Task ID")
            
        # 2. Poll
        fetch_url = f"{base_url}/mj/task/{task_id}/fetch"
        start_time = time.time()
        while time.time() - start_time < 600: # 10 mins timeout
            if self.stopped: return None
            time.sleep(5)
            try:
                resp = requests.get(fetch_url, headers=headers, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get('status')
                    if status == 'SUCCESS':
                        image_url = data.get('imageUrl')
                        if image_url:
                            # Download
                            img_resp = requests.get(image_url, timeout=60)
                            return img_resp.content
                    elif status == 'FAILURE':
                        raise Exception(f"MJ 任务失败: {data.get('failReason')}")
            except Exception as e:
                print(f"Polling error: {e}")
                pass
        raise Exception("生成超时")

    def generate_gemini(self, prompt):
        api_key = self.config.get('api_key')
        base_url = self.config.get('base_url')
        model = self.config.get('model', 'gemini-2.0-flash-exp')
        
        # 获取配置中的比例，默认为 1:1
        size_ratio = self.config.get('size', '1:1')
        # 获取分辨率
        resolution = self.config.get('resolution', '1K')

        if not api_key:
             raise Exception("Gemini API Key 未配置")

        url = f"{base_url}/models/{model}:generateContent"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        parts = [{"text": f"High quality landscape painting, detailed environment concept art: {prompt}"}]

        # 处理风格参考图
        if self.style_ref_path and os.path.exists(self.style_ref_path):
            try:
                msg = f"正在上传风格参考图: {self.style_ref_path}"
                print(f"[MapImageGenerator] DEBUG: {msg}")
                self.debug_info.emit(msg)
                
                with open(self.style_ref_path, "rb") as f:
                    img_bytes = f.read()
                    b64_data = base64.b64encode(img_bytes).decode('utf-8')
                    
                    mime_type = "image/jpeg"
                    if self.style_ref_path.lower().endswith(".png"):
                        mime_type = "image/png"
                    elif self.style_ref_path.lower().endswith(".webp"):
                        mime_type = "image/webp"
                        
                    parts.insert(0, {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": b64_data
                        }
                    })
                
                msg = "风格参考图上传并附加成功"
                print(f"[MapImageGenerator] DEBUG: {msg}")
                self.debug_info.emit(msg)
            except Exception as e:
                msg = f"风格参考图上传失败: {e}"
                print(f"[MapImageGenerator] ERROR: {msg}")
                self.debug_info.emit(msg)
        else:
             if self.style_ref_path:
                 msg = f"未找到风格参考图文件: {self.style_ref_path}"
                 print(f"[MapImageGenerator] DEBUG: {msg}")
                 self.debug_info.emit(msg)
        
        payload = {
            "contents": [{
                "parts": parts
            }]
        }
        
        if "gemini-3" in model or "pro-image" in model:
             payload["generationConfig"] = {
                 "responseModalities": ["IMAGE"],
                 "imageConfig": {
                     "imageSize": resolution,
                     "numberOfImages": 1,
                     "aspectRatio": size_ratio
                 }
             }

        # Debug: 打印发送给 API 的数据
        debug_info = {
            "url": url,
            "model": model,
            "payload": payload
        }
        debug_msg = f"[Gemini API Request] {json.dumps(debug_info, ensure_ascii=False)}"
        print(debug_msg)
        self.debug_info.emit(debug_msg)

        resp = requests.post(url, headers=headers, json=payload, timeout=300)
        resp.raise_for_status()
        
        if 'image/' in resp.headers.get('Content-Type', ''):
             return resp.content

        data = resp.json()
        
        try:
            if 'candidates' in data and data['candidates']:
                for candidate in data['candidates']:
                    if 'content' in candidate and 'parts' in candidate['content']:
                        for part in candidate['content']['parts']:
                            if 'inlineData' in part:
                                b64_data = part['inlineData']['data']
                                return base64.b64decode(b64_data)
            
            error_details = []
            if 'candidates' in data and data['candidates']:
                for i, cand in enumerate(data['candidates']):
                    finish_reason = cand.get('finishReason', 'UNKNOWN')
                    error_details.append(f"Cand {i}: Reason={finish_reason}")
            
            if error_details:
                 raise Exception(f"未找到图片数据。详情: {'; '.join(error_details)}")
                 
        except Exception as e:
            if "未找到图片数据" in str(e):
                raise e
            pass
            
        raise Exception(f"无法解析 Gemini 响应: {str(data)[:200]}...")
