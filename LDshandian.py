
import os
import json
import time
import base64
import requests
from PySide6.QtCore import QThread, Signal, QSettings
from PySide6.QtWidgets import QApplication

class LightningWorker(QThread):
    """
    闪电生成工作线程
    1. 调用对话API优化提示词
    2. 调用绘图API生成图片
    """
    prompt_updated = Signal(str)      # 提示词更新信号
    image_updated = Signal(str)       # 图片路径更新信号
    finished_task = Signal()          # 任务完成信号
    error_occurred = Signal(str)      # 错误信号

    def __init__(self, original_prompt, chat_config, image_config, image_provider, style_ref_path=None):
        super().__init__()
        self.original_prompt = original_prompt
        self.chat_config = chat_config
        self.image_config = image_config
        self.image_provider = image_provider
        self.style_ref_path = style_ref_path
        self._stopped = False

        # Register to global registry to prevent GC
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_lightning_workers'):
                app._active_lightning_workers = []
            app._active_lightning_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        app = QApplication.instance()
        if app and hasattr(app, '_active_lightning_workers'):
            if self in app._active_lightning_workers:
                app._active_lightning_workers.remove(self)
        self.deleteLater()

    def stop(self):
        self._stopped = True

    def run(self):
        try:
            # 1. 优化提示词 (已禁用，直接使用原提示词)
            # new_prompt = None
            # try:
            #     new_prompt = self.optimize_prompt(self.original_prompt)
            # except Exception as e:
            #     print(f"[Lightning] Prompt optimization failed: {e}. Using original prompt.")
            #     new_prompt = self.original_prompt
            
            # 直接使用原提示词
            new_prompt = self.original_prompt
            
            if self._stopped: return
            
            # self.prompt_updated.emit(new_prompt) # 不再需要更新提示词，因为没有改变
            
            # 2. 生成图片 (Image API)
            image_path = self.generate_image(new_prompt)
            if self._stopped: return
            
            if image_path:
                self.image_updated.emit(image_path)
            
            self.finished_task.emit()

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(str(e))

    def optimize_prompt(self, original_prompt):
        """调用对话API优化提示词"""
        print(f"[Lightning] Optimizing prompt: {original_prompt[:50]}...")
        
        try:
            api_key = self.chat_config.get('api_key')
            base_url = self.chat_config.get('base_url')
            model = self.chat_config.get('model')
            
            if not api_key or not base_url:
                print("[Lightning] Chat API config missing. Using original prompt.")
                return original_prompt

            # 构造请求
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            
            system_prompt = "你是一个专业的AI绘画提示词优化师。请根据用户提供的原始提示词，优化并重写一段适用于AI绘画的高质量英文提示词。直接输出提示词内容，不要包含任何解释或其他文字。"
            
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Original prompt: {original_prompt}\n\nPlease optimize this for image generation."}
                ],
                "temperature": 0.7,
                "max_tokens": 1024
            }
            
            # 处理API URL (适配 /v1/chat/completions)
            url = base_url.rstrip('/')
            if url.endswith('/chat/completions'):
                pass
            elif url.endswith('/v1'):
                url += '/chat/completions'
            else:
                url += '/v1/chat/completions'
            
            print(f"[Lightning] Chat Request to: {url}")
            
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            
            if resp.status_code == 429:
                print(f"[Lightning] 429 Too Many Requests. Using original prompt.")
                return original_prompt
                
            resp.raise_for_status()
            
            data = resp.json()
            content = ""
            if 'choices' in data and len(data['choices']) > 0:
                content = data['choices'][0]['message']['content']
            
            if not content:
                return original_prompt
                
            return content.strip()
            
        except Exception as e:
            print(f"[Lightning] Chat API Error: {e}. Using original prompt.")
            return original_prompt

    def generate_image(self, prompt):
        """调用绘图API生成图片"""
        print(f"[Lightning] Generating image with prompt: {prompt[:50]}...")
        if self.style_ref_path:
             print(f"[Lightning] Using style reference image: {self.style_ref_path}")
        
        image_data = None
        if self.image_provider == "Midjourney":
            if self.style_ref_path:
                print("[Lightning] Warning: Midjourney provider does not support direct image upload for style reference yet.")
            image_data = self.generate_mj(prompt)
        elif self.image_provider in ["BANANA", "BANANA2"]:
            image_data = self.generate_gemini(prompt)
        else:
            raise Exception(f"不支持的图片API: {self.image_provider}")
            
        if image_data:
            # 保存图片
            output_dir = os.path.join(os.getcwd(), "jpg", "people")
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                
            filename = f"lightning_{int(time.time())}.png"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, "wb") as f:
                f.write(image_data)
                
            return filepath
        return None

    def generate_mj(self, prompt):
        # 复用 MJ 生成逻辑
        api_key = self.image_config.get('api_key')
        base_url = self.image_config.get('base_url')
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        submit_url = f"{base_url}/mj/submit/imagine"
        payload = {"prompt": prompt}
        
        resp = requests.post(submit_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        
        task_id = resp.json().get('result')
        if not task_id:
             raise Exception("MJ未返回Task ID")
             
        # Poll
        fetch_url = f"{base_url}/mj/task/{task_id}/fetch"
        start_time = time.time()
        while time.time() - start_time < 600:
            if self._stopped: return None
            time.sleep(3)
            try:
                r = requests.get(fetch_url, headers=headers, timeout=30)
                if r.status_code == 200:
                    d = r.json()
                    if d.get('status') == 'SUCCESS':
                        img_url = d.get('imageUrl')
                        return requests.get(img_url, timeout=60).content
                    elif d.get('status') == 'FAILURE':
                        raise Exception(f"MJ失败: {d.get('failReason')}")
            except Exception:
                pass
        raise Exception("MJ生成超时")

    def generate_gemini(self, prompt):
        # 复用 Gemini 生成逻辑
        api_key = self.image_config.get('api_key')
        base_url = self.image_config.get('base_url')
        model = self.image_config.get('model', 'gemini-2.5-flash-image') # Default
        
        # 修正 url 拼接
        if not base_url.endswith('/'):
            base_url += '/'
        
        # 注意：这里的 base_url 通常是 https://generativelanguage.googleapis.com/v1beta
        # 或者用户填写的代理地址。
        # 标准格式: {base_url}/models/{model}:generateContent
        
        # 如果 base_url 包含了 /models/..., 需要处理
        # 简单处理：假设 base_url 是 host/v1beta
        
        url = f"{base_url}models/{model}:generateContent"
        # 如果 base_url 已经包含 models，则不重复
        if "models" in base_url:
             url = f"{base_url}:generateContent"

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        parts = [{"text": prompt}]

        # 处理风格参考图
        if self.style_ref_path and os.path.exists(self.style_ref_path):
            try:
                print(f"[Lightning] Uploading style reference image: {self.style_ref_path}")
                
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
                
                print("[Lightning] Style reference image attached successfully.")
            except Exception as e:
                print(f"[Lightning] Failed to upload style reference image: {e}")
        
        payload = {
            "contents": [{"parts": parts}]
        }
        
        if "gemini-3" in model or "pro-image" in model:
             payload["generationConfig"] = {
                 "responseModalities": ["IMAGE"],
                 "imageConfig": {"imageSize": "1K", "numberOfImages": 1}
             }

        resp = requests.post(url, headers=headers, json=payload, timeout=300)
        resp.raise_for_status()
        
        if 'image/' in resp.headers.get('Content-Type', ''):
            return resp.content
            
        data = resp.json()
        
        # 解析 Base64
        if 'candidates' in data:
            for cand in data['candidates']:
                if 'content' in cand and 'parts' in cand['content']:
                    for part in cand['content']['parts']:
                        if 'inlineData' in part:
                            return base64.b64decode(part['inlineData']['data'])
                            
        raise Exception("Gemini未返回图片数据")
