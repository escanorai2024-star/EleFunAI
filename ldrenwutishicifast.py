import requests
from PySide6.QtCore import QThread, Signal
import traceback

class PromptVariationWorker(QThread):
    """
    快速生成变体提示词工作线程
    """
    prompt_generated = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, original_prompt, chat_config):
        super().__init__()
        self.original_prompt = original_prompt
        self.chat_config = chat_config

        # Register to global registry to prevent GC
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_prompt_variation_workers'):
                app._active_prompt_variation_workers = []
            app._active_prompt_variation_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app and hasattr(app, '_active_prompt_variation_workers'):
            if self in app._active_prompt_variation_workers:
                app._active_prompt_variation_workers.remove(self)
        self.deleteLater()

    def run(self):
        try:
            print(f"[PromptVariation] Generating fine-tuned prompt for: {self.original_prompt[:50]}...")
            
            api_key = self.chat_config.get('api_key')
            base_url = self.chat_config.get('base_url')
            model = self.chat_config.get('model')
            
            if not api_key or not base_url:
                raise Exception("Chat API config missing (api_key or base_url)")

            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            
            # User instruction: "Please help me fine-tune this prompt based on the provided prompt."
            system_prompt = "You are a professional AI image generation prompt assistant. Please output ONLY the fine-tuned prompt without any explanations or additional text."
            user_content = f"Original prompt: {self.original_prompt}\n\nPlease help me fine-tune this prompt based on the provided prompt."
            
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "temperature": 0.7, # Slightly lower temperature for fine-tuning
                "max_tokens": 4096
            }
            
            # URL handling
            url = base_url.rstrip('/')
            if not url.endswith('/chat/completions'):
                if url.endswith('/v1'):
                    url += '/chat/completions'
                else:
                    url += '/v1/chat/completions'
            
            print(f"[PromptVariation] Request to: {url}")
            
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            
            try:
                resp.raise_for_status()
            except requests.exceptions.HTTPError as e:
                # Special handling for 429 Too Many Requests
                if e.response.status_code == 429:
                    raise Exception("API请求过于频繁(429)。请稍后(约1分钟)再试，或检查您的套餐配额。")
                
                # Try to get more info from response
                try:
                    err_json = resp.json()
                    if 'error' in err_json:
                        err_msg = err_json['error'].get('message', str(e))
                        raise Exception(f"API Error: {err_msg}")
                except:
                    pass
                raise e
            
            data = resp.json()
            # print(f"[DEBUG] Response data: {data}") # Debug logging
            
            content = ""
            if 'choices' in data and len(data['choices']) > 0:
                content = data['choices'][0]['message'].get('content', '')
            
            if content:
                self.prompt_generated.emit(content.strip())
            else:
                # 尝试获取推理内容以便调试
                reasoning = ""
                if 'choices' in data and len(data['choices']) > 0:
                    reasoning = data['choices'][0]['message'].get('reasoning_content', '')
                
                print(f"[ERROR] Full API response: {data}")
                
                error_detail = str(data)[:200]
                if reasoning:
                    error_detail += f"\n[Reasoning Content Truncated]: {reasoning[:200]}..."
                    
                raise Exception(f"API returned empty content. This usually happens when the model spends too many tokens on reasoning. Increased max_tokens should fix this.\nDetails: {error_detail}")
                
        except Exception as e:
            traceback.print_exc()
            error_msg = str(e)
            if not error_msg:
                error_msg = f"Unknown error ({type(e).__name__})"
            self.error_occurred.emit(error_msg)
