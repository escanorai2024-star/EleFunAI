
import sys
import os
import json
import time
import requests
import base64
from PySide6.QtCore import QThread, Signal, QSettings
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QComboBox, QProgressBar, QLineEdit, QDialog
)

# Import config helpers
try:
    import Agemini
except ImportError:
    Agemini = None
try:
    import Agemini30
except ImportError:
    Agemini30 = None

class OverlayGenerator(QThread):
    """
    Generates an image based on a prompt and a reference image (overlay).
    """
    progress = Signal(str)
    image_generated = Signal(str, str)  # row_id (or name), filepath
    finished_all = Signal(int)
    error_occurred = Signal(str)
    
    def __init__(self, tasks, parent=None):
        """
        tasks: list of dicts with keys:
            - id: str (identifier for the row/item)
            - prompt: str
            - ref_image: str (path to reference image)
        """
        super().__init__(parent)
        self.tasks = tasks
        self.stopped = False
        self.config = {}
        self.provider = "BANANA"

        # Register to global registry to prevent GC
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_overlay_generators'):
                app._active_overlay_generators = []
            app._active_overlay_generators.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        """Clean up worker from global registry"""
        app = QApplication.instance()
        if app and hasattr(app, '_active_overlay_generators'):
            if self in app._active_overlay_generators:
                app._active_overlay_generators.remove(self)
        self.deleteLater()
        
    def run(self):
        output_dir = os.path.join(os.getcwd(), "frame", "overlay_results")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

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
             self.error_occurred.emit("叠加图生成目前仅支持 Gemini (Banana) 模式")
             return
        
        self.provider = provider
        try:
            print("[地点叠加图] DEBUG 配置:", json.dumps({
                "provider": provider,
                "model": self.config.get("model"),
                "base_url": self.config.get("base_url"),
                "resolution": self.config.get("resolution"),
                "size": self.config.get("size")
            }, ensure_ascii=False))
        except Exception:
            pass
            
        count = 0
        for task in self.tasks:
            if self.stopped:
                break
                
            row_id = task.get('id')
            name = task.get('name')
            prompt = task.get('prompt')
            ref_image = task.get('ref_image')
            
            if not prompt or not ref_image:
                self.error_occurred.emit(f"{row_id}: 缺少提示词或参考图")
                continue
                
            self.progress.emit(f"正在生成: {row_id} ...")
            
            try:
                # Read reference image
                with open(ref_image, "rb") as f:
                    image_data = f.read()
                b64_image = base64.b64encode(image_data).decode('utf-8')
                
                # Generate using Gemini
                try:
                    print("[地点叠加图] DEBUG 发送Payload信息:", json.dumps({
                        "id": row_id,
                        "name": name,
                        "prompt_preview": prompt[:180],
                        "ref_image": ref_image,
                        "b64_size": len(b64_image)
                    }, ensure_ascii=False))
                except Exception:
                    pass
                result_data = self.generate_gemini(prompt, b64_image)
                
                if result_data:
                    filename = f"overlay_{row_id}_{int(time.time())}.png"
                    filepath = os.path.join(output_dir, filename)
            
                    with open(filepath, 'wb') as f_dst:
                        f_dst.write(result_data)
            
                    ident = str(name) if name else str(row_id)
                    try:
                        print("[地点叠加图] DEBUG 保存完成:", json.dumps({
                            "id": row_id,
                            "name": name,
                            "filepath": filepath,
                            "filesize": os.path.getsize(filepath)
                        }, ensure_ascii=False))
                    except Exception:
                        pass
                    self.image_generated.emit(ident, filepath)
                    count += 1
                else:
                    self.error_occurred.emit(f"{row_id} 生成失败: 无数据返回")
            
            except Exception as e:
                self.error_occurred.emit(f"{row_id} 生成失败: {str(e)}")
            
        self.finished_all.emit(count)
        
    def generate_gemini(self, prompt, b64_image):
        api_key = self.config.get('api_key')
        base_url = self.config.get('base_url')
        model = self.config.get('model', 'gemini-2.0-flash-exp')
        
        # Default config
        size_ratio = self.config.get('size', '1:1')
        resolution = self.config.get('resolution', '1K')

        if not api_key:
             raise Exception("Gemini API Key 未配置")

        url = f"{base_url}/models/{model}:generateContent"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        # Construct payload with Text + Image
        payload = {
            "contents": [{
                "parts": [
                    {"text": f"High quality landscape painting, detailed environment concept art based on this reference image: {prompt}"},
                    {
                        "inlineData": {
                            "mimeType": "image/png", # Assuming PNG/JPG, Gemini handles most common types
                            "data": b64_image
                        }
                    }
                ]
            }]
        }
        
        # Add generation config for image output if supported model
        # Note: Standard Gemini 1.5/2.0 might return text unless we ask for image if it's an image generation model?
        # Wait, is this "Image-to-Image" (modifying image) or "Multimodal Prompt -> New Image"?
        # Gemini 1.5 Pro/Flash are Multimodal Input -> Text Output.
        # Gemini Imagine/Imagen are Text -> Image.
        # DOES Gemini support Image+Text -> Image?
        # "Gemini 3" or "pro-image" might.
        # If the user is using a model that outputs IMAGES (like Imagen via Gemini API), the config structure is specific.
        
        if "gemini-3" in model or "pro-image" in model or "flash-image" in model:
             payload["generationConfig"] = {
                 "responseModalities": ["IMAGE"],
                 "imageConfig": {
                     "imageSize": resolution,
                     "numberOfImages": 1,
                     "aspectRatio": size_ratio
                 }
             }
        else:
            # Fallback for models that might not support explicit image generation config
            # But if it's a text model, it will return text description of the image.
            # The user wants an IMAGE.
            # The `mapshengcheng.py` uses `gemini-2.0-flash-exp` which seems to support image generation?
            # Or maybe `gemini-2.5-flash-image` (default in Agemini).
            pass

        # Debug
        # print(f"Sending request to {url}")

        try:
            masked = (api_key[:4] + "..." + api_key[-4:]) if api_key and isinstance(api_key, str) and len(api_key) >= 8 else "masked"
            print("[地点叠加图] DEBUG 请求信息:", json.dumps({
                "url": url,
                "headers": {"Authorization": f"Bearer {masked}", "Content-Type": "application/json"},
                "payload_keys": list(payload.keys())
            }, ensure_ascii=False))
        except Exception:
            pass
        resp = requests.post(url, headers=headers, json=payload, timeout=300)
        resp.raise_for_status()
        
        # Check for direct image content type (some proxies do this)
        if 'image/' in resp.headers.get('Content-Type', ''):
             try:
                 print("[地点叠加图] DEBUG 响应为原始图片:", json.dumps({
                     "status": resp.status_code,
                     "content_type": resp.headers.get('Content-Type'),
                     "length": len(resp.content)
                 }, ensure_ascii=False))
             except Exception:
                 pass
             return resp.content

        data = resp.json()
        try:
            print("[地点叠加图] DEBUG 响应JSON概要:", json.dumps({
                "status": resp.status_code,
                "keys": list(data.keys()) if isinstance(data, dict) else [],
                "preview": str(data)[:500]
            }, ensure_ascii=False))
        except Exception:
            pass
        
        # Parse Gemini Response
        try:
            if 'candidates' in data and data['candidates']:
                for candidate in data['candidates']:
                    if 'content' in candidate and 'parts' in candidate['content']:
                        for part in candidate['content']['parts']:
                            if 'inlineData' in part:
                                b64_data = part['inlineData']['data']
                                return base64.b64decode(b64_data)
            
            # If we got here, maybe it returned text instead of image?
            # If so, we can't use it as an image.
            error_details = []
            if 'candidates' in data and data['candidates']:
                for i, cand in enumerate(data['candidates']):
                    finish_reason = cand.get('finishReason', 'UNKNOWN')
                    error_details.append(f"Cand {i}: Reason={finish_reason}")
                    # Check if there is text content
                    if 'content' in cand and 'parts' in cand['content']:
                         for part in cand['content']['parts']:
                             if 'text' in part:
                                 error_details.append(f"Text: {part['text'][:50]}...")
            
            if error_details:
                 raise Exception(f"未找到图片数据。API返回可能是文本? 详情: {'; '.join(error_details)}")
                 
        except Exception as e:
            if "未找到图片数据" in str(e):
                raise e
            pass
            
        raise Exception(f"无法解析 Gemini 响应: {str(data)[:200]}...")

    def stop(self):
        self.stopped = True
