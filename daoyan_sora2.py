import os
import json
import time
import base64
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import traceback
from PySide6.QtCore import QThread, Signal, QSettings
from Asora2 import load_config as load_sora2_config
import Hailuo02

class Sora2Worker(QThread):
    # Signals
    video_completed = Signal(int, str, str, str, str)  # row_idx, video_path, shot_number, video_url, task_id
    video_failed = Signal(int, str)     # row_idx, error_msg
    all_completed = Signal()
    progress_updated = Signal(int, int)  # current, total
    log_signal = Signal(str)

    def __init__(self, api_type, tasks, output_dir, parent=None):
        super().__init__(parent)
        self.api_type = api_type
        self.tasks = tasks  # List of dict: {row_idx, prompt, image_path, shot_number}
        self.output_dir = output_dir
        self.running = True
        
        # Load Config
        self.config = self._load_api_config()

        # Register to global registry to prevent GC
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_sora_workers'):
                app._active_sora_workers = []
            app._active_sora_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app and hasattr(app, '_active_sora_workers'):
            if self in app._active_sora_workers:
                app._active_sora_workers.remove(self)
        self.deleteLater()

    def _load_api_config(self):
        config = {}
        try:
            if self.api_type == 'Sora2':
                # Load from json/sora2.json first
                try:
                    config = load_sora2_config()
                    print(f"[Sora2Worker] Loaded config from sora2.json: {config}")
                except Exception as e:
                    print(f"[Sora2Worker] Failed to load sora2.json, falling back to QSettings: {e}")
                    # Fallback to QSettings if needed (mimic video.py behavior)
                    s = QSettings('GhostOS', 'App')
                    config = {
                        'base_url': s.value('providers/sora2/base_url', 'https://api.vectorengine.ai'),
                        'api_key': s.value('providers/sora2/api_key', ''),
                        'model': s.value('providers/sora2/model', 'sora-2'),
                        'orientation': s.value('providers/sora2/orientation', 'landscape'),
                        'duration': s.value('providers/sora2/duration', '15'),
                        'watermark': s.value('providers/sora2/watermark', 'true'),
                        'size': s.value('providers/sora2/size', 'large'),
                        'width': s.value('providers/sora2/width', ''),
                        'height': s.value('providers/sora2/height', '')
                    }
            elif self.api_type in ['Wan2.5', '万象2.5']:
                # Assume wan25.json or similar logic. For now, try to load wan25.json if exists
                # or use QSettings. Since I don't have Awan25.py, I'll check QSettings
                s = QSettings('GhostOS', 'App')
                config = {
                    'base_url': s.value('providers/wan25/base_url', ''),
                    'api_key': s.value('providers/wan25/api_key', ''),
                    # Add other fields as needed
                }
                # Also try to find a json file if possible
                app_root = os.path.dirname(os.path.abspath(__file__))
                json_path = os.path.join(app_root, 'json', 'wan25.json')
                if os.path.exists(json_path):
                     with open(json_path, 'r', encoding='utf-8') as f:
                         config.update(json.load(f))
            elif self.api_type in ['Jimeng', '即梦', 'jimeng']:
                # Load from json/jimeng.json
                app_root = os.path.dirname(os.path.abspath(__file__))
                json_path = os.path.join(app_root, 'json', 'jimeng.json')
                
                # Default empty config
                config = {}
                
                if os.path.exists(json_path):
                    try:
                        with open(json_path, 'r', encoding='utf-8') as f:
                            config = json.load(f)
                        print(f"[Sora2Worker] Loaded config from jimeng.json: {config}")
                    except Exception as e:
                        print(f"[Sora2Worker] Failed to load jimeng.json: {e}")
                
                # Fallback or merge with QSettings if needed (though Jimeng usually uses json)
                if not config.get('api_key'):
                    s = QSettings('GhostOS', 'App')
                    # Jimeng settings might not be in QSettings if exclusively using json, 
                    # but check legacy paths if any.
                    # Based on video.py, it prefers json.
                    pass
            elif self.api_type in ['Hailuo 02', '海螺02', 'Hailuo02', 'hailuo02', 'hailuo']:
                # Load from json/hailuo02.json using shared helper
                try:
                    config = Hailuo02.load_config()
                    print(f"[Sora2Worker] Loaded config from hailuo02.json: {config}")
                except Exception as e:
                    self.log_signal.emit(f"❌ 海螺02配置加载失败: {e}")
                    traceback.print_exc()

        except Exception as e:
            self.log_signal.emit(f"❌ 配置加载失败: {e}")
            traceback.print_exc()
        
        return config

    def run(self):
        self.log_signal.emit(f"=== 视频生成任务开始 ===")
        self.log_signal.emit(f"任务总数: {len(self.tasks)}")
        self.log_signal.emit(f"API类型: {self.api_type}")
        
        if not self.config.get('api_key'):
             self.log_signal.emit("❌ 错误: 未配置API Key，请在设置面板中配置。")
             return

        # Ensure output dir
        os.makedirs(self.output_dir, exist_ok=True)

        for i, task in enumerate(self.tasks):
            if not self.running: break
            try:
                self.process_task(task)
                self.progress_updated.emit(i + 1, len(self.tasks))
            except Exception as e:
                self.log_signal.emit(f"❌ 任务 {i+1} (镜头 {task.get('shot_number')}) 失败: {e}")
                self.video_failed.emit(task['row_idx'], str(e))
                traceback.print_exc()
        
        self.log_signal.emit("=== 视频生成任务结束 ===")
        self.all_completed.emit()

    def process_task(self, task):
        row_idx = task['row_idx']
        prompt = task['prompt']
        image_path = task.get('image_path')
        shot_number = task.get('shot_number', f'shot_{row_idx}')
        
        self.log_signal.emit(f"正在处理镜头 {shot_number}...")
        
        base_url = self.config.get('base_url', 'https://api.vectorengine.ai').rstrip('/')
        api_key = self.config.get('api_key', '')
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        images_payload = []
        if image_path and os.path.exists(image_path):
            try:
                with open(image_path, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                    # Determine mime type
                    ext = os.path.splitext(image_path)[1].lower()
                    mime = "image/png"
                    if ext in ['.jpg', '.jpeg']: mime = "image/jpeg"
                    elif ext == '.webp': mime = "image/webp"
                    
                    data_uri = f"data:{mime};base64,{encoded_string}"
                    images_payload.append(data_uri)
            except Exception as e:
                self.log_signal.emit(f"⚠️ 读取图片失败: {e}")

        if not images_payload:
            self.log_signal.emit(f"⚠️ 警告: 没有有效的参考图，将进行纯文生视频。")

        model = self.config.get('model', 'sora-2')
        hailuo_types = ['Hailuo 02', '海螺02', 'Hailuo02', 'hailuo02', 'hailuo']
        
        if self.api_type in ['Jimeng', '即梦', 'jimeng']:
            ratio = self.config.get('aspect_ratio', '16:9')
            size = self.config.get('size', '1080P')
            duration = int(self.config.get('duration', 5))
            
            payload = {
                "model": model,
                "prompt": prompt,
                "aspect_ratio": ratio,
                "size": size,
                "duration": duration,
                "images": []
            }
            if images_payload:
                payload['images'] = images_payload
        else:
            orientation = self.config.get('orientation', 'landscape')
            duration = int(self.config.get('duration', 15))
            watermark = str(self.config.get('watermark', 'false')).lower() in ('true', '1', 'yes')
            size = self.config.get('size', 'large')
            
            payload = {
                "model": model,
                "prompt": prompt,
                "orientation": orientation,
                "duration": duration,
                "watermark": watermark,
                "size": size
            }
            
            if images_payload:
                payload['images'] = images_payload
            
            if size == 'custom':
                try:
                    w = int(self.config.get('width', 1920))
                    h = int(self.config.get('height', 1080))
                    payload['width'] = w
                    payload['height'] = h
                    del payload['size']
                except:
                    payload['size'] = 'large'

        resp_data = None
        if self.api_type in hailuo_types:
            hailuo_model = self.config.get('model', 'MiniMax-Hailuo-02')
            ratio = self.config.get('aspect_ratio', '16:9')
            duration_raw = self.config.get('duration', '10')
            try:
                d = int(str(duration_raw))
                if d not in (6, 10):
                    d = 10
            except Exception:
                d = 10
            hailuo_payload = {
                'base_url': base_url,
                'api_key': api_key,
                'model': hailuo_model,
                'prompt': prompt,
                'aspect_ratio': ratio,
                'duration': d
            }
            if len(images_payload) >= 1:
                hailuo_payload['first_frame_image'] = images_payload[0]
            if len(images_payload) >= 2:
                hailuo_payload['last_frame_image'] = images_payload[1]
            self.log_signal.emit(f"提交任务到海螺02: {base_url}")
            resp_data = Hailuo02.create_task(hailuo_payload)
            if not resp_data or resp_data.get('error'):
                msg = ''
                if resp_data:
                    msg = resp_data.get('message') or resp_data.get('error') or ''
                raise Exception(f"海螺02任务创建失败: {msg}")
        else:
            if base_url.endswith('/v1'):
                create_url = f"{base_url}/video/create"
            else:
                create_url = f"{base_url}/v1/video/create"
            self.log_signal.emit(f"提交任务到: {create_url}")
            try:
                resp = requests.post(create_url, headers=headers, json=payload, timeout=60)
                resp.raise_for_status()
                resp_data = resp.json()
            except Exception as e:
                raise Exception(f"API请求失败: {e}")

        task_id = resp_data.get('id') or resp_data.get('task_id')
        if not task_id:
            raise Exception(f"未获取到任务ID: {resp_data}")
            
        self.log_signal.emit(f"任务已创建, ID: {task_id}, 等待生成中...")

        video_url = None
        start_time = time.time()
        timeout = 1200 # 20 minutes timeout
        last_status = "unknown"
        last_response = {}
        
        if self.api_type in hailuo_types:
            succ = {'success', 'succeeded', 'finished', 'completed', 'done'}
            fail = {'fail', 'failed', 'error', 'cancelled', 'canceled', 'timeout'}
            while time.time() - start_time < timeout:
                if not self.running:
                    return
                time.sleep(5)
                try:
                    raw = Hailuo02.query_task(task_id, {'base_url': base_url, 'api_key': api_key})
                    if raw and not raw.get('error'):
                        data_obj = raw.get('data') or {}
                        inner = data_obj.get('data') or {}
                        status_val = inner.get('status') or data_obj.get('status') or ''
                        progress_val = data_obj.get('progress') or inner.get('progress')
                        file_obj = inner.get('file') or {}
                        url_out = file_obj.get('download_url') or file_obj.get('backup_download_url')
                        file_id = file_obj.get('file_id') or inner.get('file_id') or data_obj.get('file_id')
                        base_resp = inner.get('base_resp') or data_obj.get('base_resp') or raw.get('base_resp')
                    else:
                        msg = ''
                        if raw:
                            msg = raw.get('message') or raw.get('error') or ''
                        status_val = 'failed'
                        progress_val = None
                        url_out = None
                        file_id = None
                        base_resp = {'status_msg': msg}
                    status = str(status_val or 'pending').lower()
                    if status != last_status:
                        self.log_signal.emit(f"任务状态更新: {status}")
                        last_status = status
                    print(f"[Sora2Worker] Polling Hailuo02 task {task_id}: {status}")
                    if status in succ:
                        video_url = url_out
                        if not video_url:
                            print(f"[Sora2Worker] ⚠️ Status success but URL not found. Response: {raw}")
                            continue
                        break
                    if status in fail:
                        raise Exception(f"任务状态: {status} - {base_resp}")
                except Exception as e:
                    print(f"Polling error (Hailuo02): {e}")
                    continue
        else:
            while time.time() - start_time < timeout:
                if not self.running: return
                
                time.sleep(5)
                
                try:
                    if base_url.endswith('/v1'):
                        query_url = f"{base_url}/video/query?id={task_id}"
                    else:
                        query_url = f"{base_url}/v1/video/query?id={task_id}"

                    q_resp = requests.get(query_url, headers=headers, timeout=30)
                    if q_resp.status_code != 200:
                        msg = f"轮询失败: {q_resp.status_code} - {q_resp.text}"
                        print(f"[Sora2Worker] {msg}")
                        self.log_signal.emit(f"⚠️ {msg}")
                        continue
                        
                    q_data = q_resp.json()
                    status = str(q_data.get('status') or q_data.get('task_status') or 'pending').lower()
                    
                    if status != last_status:
                        self.log_signal.emit(f"任务状态更新: {status}")
                        last_status = status
                    
                    print(f"[Sora2Worker] Polling task {task_id}: {status}")

                    if status in ['succeeded', 'success', 'finished', 'completed', 'done']:
                        video_url = self._extract_video_url(q_data)
                        if not video_url:
                            print(f"[Sora2Worker] ⚠️ Status success but URL not found. Response: {q_data}")
                            continue
                        break
                    elif status in ['failed', 'error', 'cancelled', 'canceled']:
                        raise Exception(f"任务状态: {status} - {q_data}")
                    
                except Exception as e:
                    print(f"Polling error: {e}")
                    continue
        
        if not video_url:
            raise Exception(f"生成超时或未获取到视频URL (Last Status: {last_status})")

        # 4. Download Video
        self.log_signal.emit(f"生成成功，正在下载视频: {video_url}")
        
        # Sanitize filename
        safe_name = "".join([c for c in shot_number if c.isalnum() or c in (' ', '-', '_')]).strip()
        if not safe_name: safe_name = f"shot_{row_idx}"
        
        # Add timestamp/task_id to avoid overwrite and support multiple variants
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        task_suffix = task_id[-6:] if task_id else str(int(time.time()))
        
        video_filename = f"{safe_name}_{timestamp}_{task_suffix}.mp4"
        save_path = os.path.join(self.output_dir, video_filename)
        
        try:
            # 增加超时时间到120秒，并忽略SSL证书验证
            with requests.get(video_url, stream=True, timeout=120, verify=False) as r:
                r.raise_for_status()
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
        except Exception as e:
            raise Exception(f"下载视频失败: {e}")
            
        self.log_signal.emit(f"视频已保存: {save_path}")
        self.video_completed.emit(row_idx, save_path, shot_number, video_url, task_id)

    def _extract_video_url(self, j: dict) -> str:
        # Mimic video.py _extract_video_url
        # Check top-level keys first
        for c in ['result_url', 'video_url', 'url']:
            u = j.get(c)
            if isinstance(u, str) and u.startswith('http'):
                return u

        # Check nested objects
        for k in ['result', 'data', 'output', 'outputs']:
            v = j.get(k)
            if not v: continue
            
            # If it's a dict
            if isinstance(v, dict):
                for c in ['url', 'video_url']:
                    u = v.get(c)
                    if isinstance(u, str) and u.startswith('http'):
                        return u
            
            # If it's a list (take the first one)
            elif isinstance(v, list) and len(v) > 0:
                first = v[0]
                if isinstance(first, dict):
                    for c in ['url', 'video_url']:
                        u = first.get(c)
                        if isinstance(u, str) and u.startswith('http'):
                            return u
                elif isinstance(first, str) and first.startswith('http'):
                    return first
                    
        return None
