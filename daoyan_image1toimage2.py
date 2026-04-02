
import os
import json
import base64
import requests
import traceback
from datetime import datetime
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication

class ImageToImageWorker(QThread):
    # Signals
    image_completed = Signal(int, str, str, str) # row_idx, path, prompt, shot_number
    all_completed = Signal()
    progress_updated = Signal(int, int)
    log_signal = Signal(str) # For debug logging
    error_occurred = Signal(str) # For critical errors
    task_failed = Signal(int, str) # row_idx, error_msg
    
    def __init__(self, api_type, config_file, tasks, output_dir, parent=None, api_config_override=None):
        super().__init__(parent)
        self.api_type = api_type
        self.config_file = config_file
        self.tasks = tasks # List of dict: {row_idx, prompt, images: [], mode, shot_number}
        self.output_dir = output_dir
        self.api_config_override = api_config_override
        self.running = True
        
        # Register to global registry to prevent GC
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_img2img_workers'):
                app._active_img2img_workers = []
            app._active_img2img_workers.append(self)
        self.finished.connect(self._cleanup_worker)
        
    def _cleanup_worker(self):
        app = QApplication.instance()
        if app and hasattr(app, '_active_img2img_workers'):
            if self in app._active_img2img_workers:
                app._active_img2img_workers.remove(self)
        self.deleteLater()

    def run(self):
        try:
            self.log_signal.emit(f"=== 连贯分镜生成任务开始 ===")
            self.log_signal.emit(f"任务总数: {len(self.tasks)}")
            
            # Ensure output dir exists
            os.makedirs(self.output_dir, exist_ok=True)
            
            # Load config
            api_config = {}
            if self.api_config_override:
                api_config = self.api_config_override
            elif self.config_file and os.path.exists(self.config_file):
                try:
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        api_config = json.load(f)
                except Exception as e:
                    self.log_signal.emit(f"❌ 配置文件读取失败: {e}")
                    return
            else:
                 self.log_signal.emit(f"❌ 配置文件不存在且未提供覆盖配置")
                 return

            for i, task in enumerate(self.tasks):
                if not self.running or self.isInterruptionRequested():
                    self.log_signal.emit("⚠️ 任务被中断")
                    break
                try:
                    self.process_task(task, api_config)
                    self.progress_updated.emit(i + 1, len(self.tasks))
                except Exception as e:
                    self.log_signal.emit(f"❌ 任务 {i+1} 失败: {e}")
                    self.task_failed.emit(task['row_idx'], str(e))
                    traceback.print_exc()
                    
            self.log_signal.emit(f"=== 连贯分镜生成任务结束 ===")
            self.all_completed.emit()
        
        except Exception as e:
             self.log_signal.emit(f"❌ 线程运行出错: {e}")
             self.error_occurred.emit(f"线程运行出错: {str(e)}\n{traceback.format_exc()}")
             traceback.print_exc()

    def process_task(self, task, api_config):
        row_idx = task['row_idx']
        base_prompt = task['prompt']
        additional_prompt = task.get('additional_prompt', '') # 获取附加提示词
        images = task['images'] # Contains previous shot image
        shot_number = task.get('shot_number', row_idx + 1)
        mode = task.get('mode', '6-grid')
        
        # Construct specialized prompt
        instruction = ""
        
        # 检查开发测试模式
        try:
            from daoyan_setting_test import is_test_mode_enabled
            test_mode = is_test_mode_enabled()
        except ImportError:
            test_mode = False
            
        if mode == '9-grid':
            if test_mode:
                instruction = "提取参考图1最后一格（不要修改任何内容），作为九宫格的第二格，产生新的九宫格。"
            else:
                instruction = "提取参考图1最后一格（不要修改任何内容），作为九宫格的第一格，产生新的九宫格。"
        elif mode == '6-grid':
            if test_mode:
                instruction = "提取参考图1最后一格（不要修改任何内容），作为六宫格的第二格，产生新的六宫格。"
            else:
                instruction = "提取参考图1最后一格（不要修改任何内容），作为六宫格的第一格，产生新的六宫格。"
        elif mode == '4-grid':
            if test_mode:
                instruction = "提取参考图1最后一格（不要修改任何内容），作为四宫格的第二格，产生新的四宫格。"
            else:
                instruction = "提取参考图1最后一格（不要修改任何内容），作为四宫格的第一格，产生新的四宫格。"
        else:
            # default / single image
            instruction = "提取参考图1最后一格（不要修改任何内容），作为参考，产生新的一张分镜图。"
        
        # 构建最终提示词，附加提示词放在最前面
        prompt_parts = []
        
        # 用户要求将指令放在最前面
        prompt_parts.append(instruction)
        
        if additional_prompt:
            prompt_parts.append(additional_prompt)
        
        prompt_parts.append(f"\n{base_prompt}")
        
        final_prompt = "\n".join(prompt_parts)
            
        self.log_signal.emit(f"\n--- 处理第 {row_idx+1} 行 (镜头: {shot_number}) ---")
        self.log_signal.emit(f"模式: 连贯分镜 ({mode})")
        self.log_signal.emit(f"提示词: {final_prompt}")
        self.log_signal.emit(f"参考图片数: {len(images)}")
        for img in images:
             self.log_signal.emit(f"  - 图片: {img}")
        
        # Call API
        image_path = None
        if self.api_type == "BANANA":
            image_path = self.generate_with_gemini(shot_number, final_prompt, images, api_config, version="2.0")
        elif self.api_type == "BANANA2":
            image_path = self.generate_with_gemini(shot_number, final_prompt, images, api_config, version="3.0")
        
        if image_path:
            self.image_completed.emit(row_idx, image_path, final_prompt, shot_number)
            self.log_signal.emit(f"✅ 生成成功: {image_path}")
        else:
            self.log_signal.emit(f"❌ 生成失败")
            self.task_failed.emit(row_idx, "生成失败")

    def generate_with_gemini(self, shot_number, prompt, image_paths, api_config, version="2.0"):
        """使用 Gemini 生成"""
        try:
            api_key = api_config.get('api_key', '')
            api_url = api_config.get('base_url', 'https://generativelanguage.googleapis.com/v1beta')
            
            if version == "2.0":
                model = api_config.get('model', 'gemini-2.0-flash-exp')
            else:
                api_url = api_url.rstrip('/')
                model = api_config.get('model', 'gemini-3-pro-image-preview')

            if not api_key:
                self.log_signal.emit("API Key未配置")
                return None
            
            url = f"{api_url}/models/{model}:generateContent?key={api_key}"
            
            parts = [{"text": prompt}]
            
            # 添加源图片
            for img_path in image_paths:
                if img_path and os.path.exists(img_path):
                    try:
                        with open(img_path, "rb") as image_file:
                            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                            
                            mime_type = "image/jpeg"
                            ext = os.path.splitext(img_path)[1].lower()
                            if ext == '.png': mime_type = "image/png"
                            elif ext == '.webp': mime_type = "image/webp"
                            elif ext == '.jpg' or ext == '.jpeg': mime_type = "image/jpeg"
                            
                            parts.append({
                                "inline_data": {
                                    "mime_type": mime_type,
                                    "data": encoded_string
                                }
                            })
                            self.log_signal.emit(f"  [API] 已添加参考图片: {img_path}")
                    except Exception as e:
                        self.log_signal.emit(f"读取图片失败 {img_path}: {e}")
            
            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "response_modalities": ["IMAGE"],
                    "temperature": 1.0,
                    "imageConfig": {"aspectRatio": "16:9", "imageSize": "1K"}
                }
            }
            
            # Use requests
            self.log_signal.emit("发送请求中...")
            response = requests.post(url, json=payload, timeout=300)
            
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result and result['candidates']:
                    parts = result['candidates'][0].get('content', {}).get('parts', [])
                    for part in parts:
                        # Handle both inline_data and inlineData
                        image_data = part.get('inline_data', {}).get('data') or part.get('inlineData', {}).get('data')
                        if image_data:
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename = f"storyboard_seq_{shot_number}_{timestamp}.jpg"
                            filepath = os.path.join(self.output_dir, filename)
                            with open(filepath, 'wb') as f:
                                f.write(base64.b64decode(image_data))
                            return filepath
                else:
                    self.log_signal.emit(f"API返回了200但没有图片候选: {result}")
            else:
                self.log_signal.emit(f"请求失败: {response.status_code} {response.text}")
            
            return None
            
        except Exception as e:
            self.log_signal.emit(f"Generate Error: {e}")
            return None
