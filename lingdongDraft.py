"""
灵动智能体 - 图片生成模块 (生成草稿)
支持为分镜脚本的每个镜头根据提示词生成图片

功能：
1. 读取分镜脚本表格的"绘画提示词（EN）"列
2. 调用用户选择的图片生成API（BANANA / BANANA2 / Midjourney）
3. 为每个镜头生成对应的图片
4. 将生成的图片保存到项目目录
5. 在画布上创建图片节点展示生成的图片
6. 逐个处理，实时显示进度

图片生成规则：
- 使用"绘画提示词（EN）"列的内容作为提示词
- 如果没有EN提示词，使用"绘画提示词（CN）"列
- 如果都没有，提示用户先生成绘画提示词
- 支持多种图片API的调用
"""

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, 
    QMessageBox, QComboBox, QProgressBar, QLabel
)
import requests
import json
import os
import base64
from datetime import datetime


class ImageGenerationWorker(QThread):
    """图片生成工作线程 - 逐个生成图片"""
    image_completed = Signal(int, str, str)  # 行号, 图片路径, 提示词
    all_completed = Signal(list)  # 所有图片信息 [(行号, 路径, 提示词), ...]
    error_occurred = Signal(str)
    progress_updated = Signal(int, int)  # 当前进度, 总数
    
    def __init__(self, image_api, config_file, table_data, headers):
        super().__init__()
        self.image_api = image_api  # "BANANA" / "BANANA2" / "Midjourney"
        self.config_file = config_file
        self.table_data = table_data
        self.headers = headers
        self.all_images = []
        self.output_dir = "frame"  # 输出目录

        # Register to global registry to prevent GC
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_draft_image_workers'):
                app._active_draft_image_workers = []
            app._active_draft_image_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        """Clean up worker from global registry"""
        app = QApplication.instance()
        if app and hasattr(app, '_active_draft_image_workers'):
            if self in app._active_draft_image_workers:
                app._active_draft_image_workers.remove(self)
        self.deleteLater()
    
    def run(self):
        try:
            # 确保输出目录存在
            os.makedirs(self.output_dir, exist_ok=True)
            
            # 查找提示词列索引
            en_prompt_idx = -1
            cn_prompt_idx = -1
            general_prompt_idx = -1
            
            for i, header in enumerate(self.headers):
                if "绘画提示词（EN）" in header or "绘画提示词(EN)" in header:
                    en_prompt_idx = i - 1  # 减1因为第一列是镜号
                elif "绘画提示词（CN）" in header or "绘画提示词(CN)" in header:
                    cn_prompt_idx = i - 1
                elif "绘画提示词" == header or "提示词" == header:
                    # 谷歌剧本节点的提示词列
                    # 注意：谷歌剧本节点的table_data构造方式可能不同
                    # 如果是谷歌剧本，通常我们构造的table_data与headers是一一对应的
                    # 但为了兼容这里的逻辑，我们需要确认lingdong.py中是如何构造的
                    # 假设lingdong.py中构造的table_data包含了所有列
                    general_prompt_idx = i
                elif "画面内容" == header and general_prompt_idx < 0:
                    # 谷歌剧本节点的画面内容列 (作为提示词回退选项)
                    general_prompt_idx = i
            
            print(f"[DEBUG] EN提示词列索引: {en_prompt_idx}")
            print(f"[DEBUG] CN提示词列索引: {cn_prompt_idx}")
            print(f"[DEBUG] 通用提示词列索引: {general_prompt_idx}")
            
            if en_prompt_idx < 0 and cn_prompt_idx < 0 and general_prompt_idx < 0:
                self.error_occurred.emit("未找到绘画提示词列，请先生成绘画提示词")
                return
            
            # 优先使用中文提示词，其次英文，最后通用提示词
            prompt_idx = -1
            if cn_prompt_idx >= 0:
                prompt_idx = cn_prompt_idx
            elif en_prompt_idx >= 0:
                prompt_idx = en_prompt_idx
            else:
                prompt_idx = general_prompt_idx
            
            total_rows = len(self.table_data)
            
            # ⭐ 显示详细的启动信息
            print(f"\n{'='*60}")
            print(f"[图片生成] 启动图片生成任务")
            print(f"{'='*60}")
            print(f"[图片生成] 选择的API: {self.image_api}")
            print(f"[图片生成] 总镜头数: {total_rows}")
            print(f"[图片生成] 提示词列索引: {prompt_idx}")
            print(f"[图片生成] 输出目录: {self.output_dir}")
            
            # 读取并显示模型配置
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    api_config = json.load(f)
                
                if self.image_api == "BANANA":
                    # ⭐ 从 gemini.json 读取 BANANA 配置
                    gemini_config_path = os.path.join('json', 'gemini.json')
                    if not os.path.exists(gemini_config_path) and self.config_file:
                        gemini_config_path = os.path.join(os.path.dirname(self.config_file), 'json', 'gemini.json')
                    
                    if os.path.exists(gemini_config_path):
                        with open(gemini_config_path, 'r', encoding='utf-8') as f:
                            g_cfg = json.load(f)
                        model = g_cfg.get('model', 'gemini-2.0-flash-exp')
                        print(f"[图片生成] BANANA 模型 (from gemini.json): {model}")
                    else:
                        model = api_config.get('gemini_model', 'gemini-2.0-flash-exp')
                        print(f"[图片生成] BANANA 模型 (from api_config): {model}")
                elif self.image_api == "BANANA2":
                    # ⭐ 从 gemini30.json 读取 BANANA2 配置
                    gemini30_config_path = os.path.join(os.path.dirname(self.config_file), 'gemini30.json')
                    if os.path.exists(gemini30_config_path):
                        with open(gemini30_config_path, 'r', encoding='utf-8') as f:
                            g30_cfg = json.load(f)
                        model = g30_cfg.get('model', 'gemini-3-pro-image-preview')
                        resolution = g30_cfg.get('resolution', '1K')
                        aspect_ratio = g30_cfg.get('size', '16:9')
                        quality = g30_cfg.get('quality', '80')
                        print(f"[图片生成] BANANA2 模型: {model}")
                        print(f"[图片生成] BANANA2 分辨率: {resolution}")
                        print(f"[图片生成] BANANA2 宽高比: {aspect_ratio}")
                        print(f"[图片生成] BANANA2 JPEG质量: {quality}")
                    else:
                        print(f"[图片生成] BANANA2 配置文件不存在: {gemini30_config_path}")
            except Exception as e:
                print(f"[图片生成] 读取配置失败: {e}")
            
            print(f"{'='*60}\n")
            
            # 逐个生成图片
            for row_idx, row_data in enumerate(self.table_data):
                # 获取提示词
                if prompt_idx >= len(row_data):
                    print(f"[图片生成] 镜头 {row_idx + 1} 没有提示词，跳过")
                    continue
                
                prompt = str(row_data[prompt_idx]).strip()
                if not prompt:
                    print(f"[图片生成] 镜头 {row_idx + 1} 提示词为空，跳过")
                    continue
                
                print(f"\n{'='*60}")
                print(f"[图片生成] 正在生成第 {row_idx + 1}/{total_rows} 张图片")
                print(f"[图片生成] 镜头编号: {row_idx + 1}")
                print(f"[图片生成] 使用API: {self.image_api}")
                print(f"[图片生成] 提示词: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
                print(f"{'='*60}")
                
                # 调用图片生成API
                image_path = self.generate_single_image(row_idx + 1, prompt)
                
                if image_path:
                    self.all_images.append((row_idx + 1, image_path, prompt))
                    try:
                        self.image_completed.emit(row_idx + 1, image_path, prompt)
                    except Exception as emit_error:
                        print(f"[图片生成] 信号发送失败(image_completed): {emit_error}")
                
                # 更新进度
                try:
                    self.progress_updated.emit(row_idx + 1, total_rows)
                except Exception as emit_error:
                    print(f"[图片生成] 信号发送失败(progress_updated): {emit_error}")
            
            print(f"\n[图片生成] 全部完成，成功生成 {len(self.all_images)} 张图片")
            try:
                self.all_completed.emit(self.all_images)
            except Exception as emit_error:
                print(f"[图片生成] 信号发送失败(all_completed): {emit_error}")
        
        except Exception as e:
            error_msg = f"生成失败: {str(e)}"
            print(f"[图片生成] {error_msg}")
            import traceback
            traceback.print_exc()
            try:
                self.error_occurred.emit(error_msg)
            except Exception as emit_error:
                print(f"[图片生成] 信号发送失败(error_occurred): {emit_error}")
    
    def generate_single_image(self, shot_number, prompt):
        """生成单张图片
        
        Args:
            shot_number: 镜头号
            prompt: 提示词
            
        Returns:
            str: 图片保存路径，失败返回None
        """
        try:
            # 加载API配置
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    api_config = json.load(f)
            except Exception as config_error:
                print(f"[图片生成] 配置文件读取失败: {config_error}")
                import traceback
                traceback.print_exc()
                return None
            
            # 根据选择的API调用不同的生成方法
            if self.image_api == "BANANA":
                return self.generate_with_gemini25(shot_number, prompt, api_config)
            elif self.image_api == "BANANA2":
                return self.generate_with_gemini30(shot_number, prompt, api_config)
            elif self.image_api == "Midjourney":
                return self.generate_with_midjourney(shot_number, prompt, api_config)
            else:
                print(f"[图片生成] 不支持的API: {self.image_api}")
                return None
        
        except Exception as e:
            print(f"[图片生成] 镜头 {shot_number} 生成失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def generate_with_gemini25(self, shot_number, prompt, api_config):
        """使用 BANANA 生成图片"""
        try:
            # ⭐ 优先从 gemini.json 读取配置
            api_key = ''
            api_url = ''
            model = ''
            
            gemini_config_path = os.path.join('json', 'gemini.json')
            if not os.path.exists(gemini_config_path) and self.config_file:
                 gemini_config_path = os.path.join(os.path.dirname(self.config_file), 'json', 'gemini.json')
            
            if os.path.exists(gemini_config_path):
                 try:
                     with open(gemini_config_path, 'r', encoding='utf-8') as f:
                         g_cfg = json.load(f)
                     api_key = g_cfg.get('api_key', '')
                     api_url = g_cfg.get('base_url', 'https://generativelanguage.googleapis.com/v1beta')
                     model = g_cfg.get('model', 'gemini-2.0-flash-exp')
                 except Exception as e:
                     print(f"[BANANA] 读取 gemini.json 失败: {e}")

            # 如果 gemini.json 未配置或读取失败，回退到 api_config
            if not api_key:
                api_key = api_config.get('gemini_api_key', '')
            if not api_url:
                api_url = api_config.get('gemini_api_url', 'https://generativelanguage.googleapis.com/v1beta')
            if not model:
                model = api_config.get('gemini_model', 'gemini-2.0-flash-exp')

            if not api_key:
                raise Exception("BANANA API Key未配置")
            
            # 构建请求
            url = f"{api_url}/models/{model}:generateContent?key={api_key}"
            
            # 调试信息
            print(f"[BANANA] 使用模型: {model}")
            print(f"[BANANA] API地址: {api_url}")
            print(f"[BANANA] 请求URL: {url}")
            
            headers = {
                'Content-Type': 'application/json'
            }
            
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt}
                    ]
                }],
                "generationConfig": {
                    "response_modalities": ["IMAGE"],
                    "temperature": 1.0,
                    "imageConfig": {
                        "aspectRatio": "16:9",
                        "imageSize": "1K"
                    }
                }
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=300)
            
            if response.status_code == 200:
                try:
                    result = response.json()
                except Exception as json_error:
                    print(f"[BANANA] JSON解析失败: {json_error}")
                    import traceback
                    traceback.print_exc()
                    raise Exception(f"响应JSON解析失败: {str(json_error)}")
                
                # 解析返回的图片数据
                if 'candidates' in result and len(result['candidates']) > 0:
                    parts = result['candidates'][0].get('content', {}).get('parts', [])
                    
                    for part in parts:
                        # 兼容 snake_case and camelCase
                        image_data = None
                        if 'inline_data' in part:
                            image_data = part['inline_data'].get('data', '')
                        elif 'inlineData' in part:
                            image_data = part['inlineData'].get('data', '')
                            
                        if image_data:
                            try:
                                # 保存图片
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                filename = f"shot_{shot_number:03d}_{timestamp}.jpg"
                                filepath = os.path.join(self.output_dir, filename)
                                
                                # 解码并保存
                                image_bytes = base64.b64decode(image_data)
                                with open(filepath, 'wb') as f:
                                    f.write(image_bytes)
                                
                                print(f"[图片生成] 镜头 {shot_number} 成功: {filepath} (模型: {model})")
                                return filepath
                            except Exception as save_error:
                                print(f"[BANANA] 图片保存失败: {save_error}")
                                import traceback
                                traceback.print_exc()
                                continue
                
                # 如果没有找到图片，打印完整响应以供调试
                print(f"[BANANA] 生成失败，未找到图片候选。完整响应: {json.dumps(result, ensure_ascii=False)[:1000]}")
                if 'error' in result:
                     raise Exception(f"API返回错误: {result['error'].get('message', '未知错误')}")
                
                raise Exception("返回数据中未找到图片")
            else:
                error_text = response.text[:1000] if hasattr(response, 'text') else 'Unknown error'
                print(f"[BANANA] API请求失败: {response.status_code}, 响应: {error_text}")
                raise Exception(f"API错误 {response.status_code}: {error_text}")
        
        except Exception as e:
            print(f"[BANANA] 生成失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def generate_with_gemini30(self, shot_number, prompt, api_config):
        """使用 BANANA2 生成图片"""
        try:
            # ⭐ 从 gemini30.json 读取 BANANA2 专属配置
            gemini30_config = {}
            try:
                gemini30_config_path = os.path.join(os.path.dirname(self.config_file), 'gemini30.json')
                if os.path.exists(gemini30_config_path):
                    with open(gemini30_config_path, 'r', encoding='utf-8') as f:
                        gemini30_config = json.load(f)
                    print(f"[BANANA2] 成功加载配置文件: {gemini30_config_path}")
                else:
                    print(f"[BANANA2] 配置文件不存在，使用默认值: {gemini30_config_path}")
            except Exception as cfg_error:
                print(f"[BANANA2] 配置文件读取失败: {cfg_error}")
            
            # API密钥 - 优先使用 gemini30.json，其次是 api_config.json
            api_key = gemini30_config.get('api_key', '') or api_config.get('gemini30_api_key', api_config.get('gemini_api_key', ''))
            if not api_key:
                raise Exception("BANANA2 API Key未配置，请在设置中配置 BANANA2")
            
            # Base URL - 优先使用 gemini30.json
            api_url = gemini30_config.get('base_url', '') or api_config.get('gemini30_api_url', 'https://generativelanguage.googleapis.com/v1beta')
            api_url = api_url.rstrip('/')
            
            # ⭐ 模型名称 - 从 gemini30.json 读取
            model = gemini30_config.get('model', 'gemini-3-pro-image-preview')
            
            # 打印模型信息到控制台（便于调试）
            print(f"[BANANA2] 镜头 {shot_number} - 使用模型: {model}")
            
            url = f"{api_url}/models/{model}:generateContent?key={api_key}"
            
            headers = {
                'Content-Type': 'application/json'
            }
            
            # ⭐ 从 gemini30.json 读取图片生成参数
            resolution = gemini30_config.get('resolution', '1K')  # "1K", "2K", "4K"
            aspect_ratio = gemini30_config.get('size', '16:9')  # 宽高比（gemini30.json中字段名为size）
            quality_str = gemini30_config.get('quality', '80')
            
            # 将质量字符串转换为整数
            try:
                quality = int(quality_str)
                quality = max(0, min(100, quality))
            except Exception:
                quality = 80
            
            print(f"[BANANA2] 使用模型: {model}")
            print(f"[BANANA2] API地址: {api_url}")
            print(f"[BANANA2] 分辨率: {resolution}, 宽高比: {aspect_ratio}, JPEG质量: {quality}")
            print(f"[BANANA2] 请求URL: {url}")
            
            # 构造请求体
            # 根据 Google Gemini API 官方文档和 new_api_client.py 的实现
            # 正确格式：responseModalities + imageConfig
            
            # imageConfig - 图片配置
            # BANANA2 Pro Image Preview 支持的参数：
            # - aspectRatio: 宽高比（字符串）"16:9", "1:1", "9:16" 等
            # - imageSize: 分辨率大小 "1K", "2K", "4K" ⭐ 关键参数
            # - jpegQuality: JPEG质量 0-100
            # - numberOfImages: 生成图片数量
            image_config = {
                'aspectRatio': aspect_ratio,
                'imageSize': resolution,  # ⭐ 关键：设置分辨率
                'jpegQuality': quality,
                'numberOfImages': 1
            }
            
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt}
                    ]
                }],
                "generationConfig": {
                    "responseModalities": ["IMAGE", "TEXT"],  # ⭐ 注意大小写
                    "imageConfig": image_config,
                    "temperature": 0.5  # 参考 gemini30.py
                }
            }
            
            print(f"[BANANA2] imageConfig: {image_config}")
            
            # 根据分辨率设置超时时间（参考 new_api_client.py 第420行）
            timeout_map = {"1K": 240, "2K": 480, "4K": 600}
            timeout = timeout_map.get(resolution, 600)
            print(f"[BANANA2] 超时设置: {timeout}秒")
            
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
            
            if response.status_code == 200:
                try:
                    result = response.json()
                except Exception as json_error:
                    print(f"[BANANA2] JSON解析失败: {json_error}")
                    import traceback
                    traceback.print_exc()
                    raise Exception(f"响应JSON解析失败: {str(json_error)}")
                
                # 解析返回的图片数据
                if 'candidates' in result and len(result['candidates']) > 0:
                    candidate = result['candidates'][0]
                    
                    if 'content' in candidate and 'parts' in candidate['content']:
                        parts = candidate['content']['parts']
                        
                        for part in parts:
                            # 检查多种可能的图片字段名（兼容不同API版本）
                            image_field = None
                            if 'inlineData' in part:
                                image_field = 'inlineData'
                            elif 'inline_data' in part:
                                image_field = 'inline_data'
                            
                            if image_field:
                                try:
                                    image_obj = part[image_field]
                                    image_data = image_obj.get('data', '')
                                    
                                    if not image_data:
                                        print(f"[BANANA2] 警告: 图片数据为空")
                                        continue
                                    
                                    # 保存图片
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    filename = f"shot_{shot_number:03d}_{timestamp}_{resolution}.jpg"
                                    filepath = os.path.join(self.output_dir, filename)
                                    
                                    # 解码并保存
                                    image_bytes = base64.b64decode(image_data)
                                    with open(filepath, 'wb') as f:
                                        f.write(image_bytes)
                                    
                                    print(f"[图片生成] 镜头 {shot_number} 成功: {filepath} (模型: {model}, 分辨率: {resolution})")
                                    return filepath
                                except Exception as save_error:
                                    print(f"[BANANA2] 图片保存失败: {save_error}")
                                    import traceback
                                    traceback.print_exc()
                                    continue
                
                raise Exception("返回数据中未找到图片")
            else:
                error_text = response.text[:500] if hasattr(response, 'text') else 'Unknown error'
                raise Exception(f"API错误 {response.status_code}: {error_text}")
        
        except Exception as e:
            print(f"[BANANA2] 生成失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def generate_with_midjourney(self, shot_number, prompt, api_config):
        """使用 Midjourney 生成图片"""
        try:
            api_key = api_config.get('midjourney_api_key', '')
            api_url = api_config.get('midjourney_api_url', '')
            
            if not api_key or not api_url:
                raise Exception("Midjourney API配置未完成")
            
            # Midjourney API调用（这里需要根据实际的MJ API接口调整）
            # 示例：假设使用第三方MJ API服务
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }
            
            payload = {
                'prompt': prompt,
                'aspect_ratio': '16:9'  # 默认宽屏比例
            }
            
            # 提交生成任务
            response = requests.post(api_url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                task_id = result.get('task_id') or result.get('id')
                
                if not task_id:
                    raise Exception("未获取到任务ID")
                
                # 轮询检查任务状态
                max_retries = 60  # 最多等待5分钟
                for i in range(max_retries):
                    import time
                    time.sleep(5)  # 每5秒检查一次
                    
                    status_url = f"{api_url}/status/{task_id}"
                    status_resp = requests.get(status_url, headers=headers, timeout=30)
                    
                    if status_resp.status_code == 200:
                        status_result = status_resp.json()
                        status = status_result.get('status')
                        
                        if status == 'completed':
                            image_url = status_result.get('image_url') or status_result.get('url')
                            
                            if image_url:
                                # 下载图片
                                img_response = requests.get(image_url, timeout=60)
                                
                                if img_response.status_code == 200:
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    filename = f"shot_{shot_number:03d}_{timestamp}.png"
                                    filepath = os.path.join(self.output_dir, filename)
                                    
                                    with open(filepath, 'wb') as f:
                                        f.write(img_response.content)
                                    
                                    print(f"[图片生成] 镜头 {shot_number} 成功: {filepath}")
                                    return filepath
                        
                        elif status == 'failed':
                            raise Exception("生成失败")
                
                raise Exception("生成超时")
            else:
                raise Exception(f"API错误 {response.status_code}: {response.text[:200]}")
        
        except Exception as e:
            print(f"[Midjourney] 生成失败: {e}")
            return None


class DraftGenerator:
    """图片生成器 (生成草稿)"""
    
    def __init__(self, config_file='api_config.json'):
        """初始化生成器
        
        Args:
            config_file: API配置文件路径
        """
        self.config_file = config_file
        self.worker = None
    
    def generate_draft(self, image_api, table_data, headers, callbacks=None):
        """生成图片（草稿）
        
        Args:
            image_api: 图片API ("BANANA" / "BANANA2" / "Midjourney")
            table_data: 表格数据（二维列表）
            headers: 表头列表
            callbacks: 回调函数字典，包含：
                - on_image_completed: 单张图片完成回调 (row_idx, image_path, prompt)
                - on_progress: 进度更新回调 (current, total)
                - on_completed: 全部完成回调 (all_images)
                - on_error: 错误回调 (error_msg)
        
        Returns:
            ImageGenerationWorker: 工作线程对象
        """
        print(f"[图片生成] 使用API: {image_api}")
        
        # 创建工作线程
        self.worker = ImageGenerationWorker(
            image_api, self.config_file, table_data, headers
        )
        
        # 连接回调函数
        if callbacks:
            if 'on_image_completed' in callbacks:
                self.worker.image_completed.connect(callbacks['on_image_completed'])
            if 'on_progress' in callbacks:
                self.worker.progress_updated.connect(callbacks['on_progress'])
            if 'on_completed' in callbacks:
                self.worker.all_completed.connect(callbacks['on_completed'])
            if 'on_error' in callbacks:
                self.worker.error_occurred.connect(callbacks['on_error'])
        
        # 启动线程
        self.worker.start()
        
        return self.worker
