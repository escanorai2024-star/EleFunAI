import os
import sys
import json
import base64
import requests
import time
import traceback
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton, QMessageBox, QTableWidgetItem
from PySide6.QtCore import QBuffer, QIODevice, QByteArray, Qt, QSettings, QThread, Signal, QObject
from PySide6.QtGui import QImage, QPixmap, QIcon
from PySide6.QtWidgets import QApplication

# Try to import gemini30 for helper functions
try:
    import gemini30
except ImportError:
    gemini30 = None

class ImageGenerationWorker(QThread):
    progress = Signal(int, int, str)  # row, col, status
    image_generated = Signal(int, int, str)  # row, col, image_path
    error_occurred = Signal(int, int, str)  # row, col, error_msg
    log_message = Signal(str)
    finished_all = Signal()

    def __init__(self, tasks, api_provider, parent=None):
        super().__init__(parent)
        self.tasks = tasks
        self.api_provider = api_provider
        self.stopped = False

        # Register to global registry to prevent GC
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_image_generation_workers_2chuang'):
                app._active_image_generation_workers_2chuang = []
            app._active_image_generation_workers_2chuang.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        """Clean up worker from global registry"""
        app = QApplication.instance()
        if app and hasattr(app, '_active_image_generation_workers_2chuang'):
            if self in app._active_image_generation_workers_2chuang:
                app._active_image_generation_workers_2chuang.remove(self)
        self.deleteLater()

    def run(self):
        self.log_message.emit(f"开始处理 {len(self.tasks)} 个任务，使用 API: {self.api_provider}")
        
        for task in self.tasks:
            if self.stopped:
                break
                
            row = task['row']
            col = task['col']
            prompt = task['prompt']
            refs = task['refs']
            suffix = task['suffix']
            
            self.progress.emit(row, col, "⏳")
            
            try:
                if self.api_provider == "BANANA":
                    self._generate_banana(prompt, refs, suffix, row, col)
                elif self.api_provider == "Midjourney":
                    self._generate_midjourney(prompt, refs, suffix, row, col)
                else:
                    # Default to BANANA2 (Gemini 3.0)
                    self._generate_banana2(prompt, refs, suffix, row, col)
            except Exception as e:
                err_msg = f"生成失败: {str(e)}"
                self.log_message.emit(err_msg)
                self.error_occurred.emit(row, col, "❌")
                traceback.print_exc() # Still print to console for debugging
                
        self.finished_all.emit()

    def stop(self):
        self.stopped = True

    def save_image(self, data, suffix, row, col):
        try:
            output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_output")
            os.makedirs(output_dir, exist_ok=True)
            
            filename = f"2chuang_{int(time.time())}{suffix}.png"
            path = os.path.join(output_dir, filename)
            
            if isinstance(data, (bytes, bytearray)):
                with open(path, "wb") as f:
                    f.write(data)
            else:
                 self.log_message.emit("错误: save_image 接收到非 bytes 数据")
                 return
                
            self.log_message.emit(f"图片已保存: {path}")
            self.image_generated.emit(row, col, path)
            
        except Exception as e:
            self.log_message.emit(f"保存图片失败: {e}")
            self.error_occurred.emit(row, col, "Save Error")

    def _generate_banana(self, prompt, image_paths, suffix, row, col):
        """Gemini 2.0 (BANANA)"""
        self.log_message.emit("[Gemini 2.0] 开始生成...")
        try:
            settings = QSettings("GhostOS", "App")
            api_key = settings.value("providers/gemini/api_key", "")
            base_url = settings.value("providers/gemini/base_url", "")
            model = settings.value("providers/gemini/model", "")
            
            if not api_key:
                config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'json', 'gemini.json')
                if os.path.exists(config_path):
                     with open(config_path, 'r', encoding='utf-8') as f:
                        cfg = json.load(f)
                        api_key = cfg.get('api_key', '')
                        if not base_url: base_url = cfg.get('base_url', '')
                        if not model: model = cfg.get('model', '')

            if not base_url: base_url = 'https://generativelanguage.googleapis.com/v1beta'
            if not model: model = 'gemini-2.0-flash-exp'
            
            base_url = base_url.rstrip('/')
            model = model.strip()
            
            if not api_key:
                self.log_message.emit("错误: API Key未配置 (Gemini)")
                self.error_occurred.emit(row, col, "No Key")
                return

            url = f"{base_url}/models/{model}:generateContent?key={api_key}"
            
            parts = [{'text': prompt}]
            
            for p in image_paths:
                if not p or not os.path.exists(p):
                    continue
                
                try:
                    with open(p, "rb") as image_file:
                        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                        
                        mime_type = "image/jpeg"
                        ext = os.path.splitext(p)[1].lower()
                        if ext == '.png': mime_type = "image/png"
                        elif ext == '.webp': mime_type = "image/webp"
                        
                        parts.append({
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": encoded_string
                            }
                        })
                        self.log_message.emit(f"添加参考图: {os.path.basename(p)}")
                except Exception as e:
                    self.log_message.emit(f"读取图片失败: {e}")

            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "response_modalities": ["IMAGE"],
                    "temperature": 1.0,
                    "imageConfig": {"aspectRatio": "1:1", "imageSize": "1K"}
                }
            }
            
            self.log_message.emit(f"发送请求到: {url}")
            resp = requests.post(url, json=payload, timeout=120)
            
            if resp.status_code == 200:
                result = resp.json()
                if 'candidates' in result and result['candidates']:
                    parts = result['candidates'][0].get('content', {}).get('parts', [])
                    for part in parts:
                        image_data = part.get('inline_data', {}).get('data') or part.get('inlineData', {}).get('data')
                        if image_data:
                            self.log_message.emit(f"收到图片数据")
                            self.save_image(base64.b64decode(image_data), suffix, row, col)
                            return
                self.log_message.emit(f"未在响应中找到图片数据: {resp.text[:200]}")
                self.error_occurred.emit(row, col, "No Image")
            else:
                self.log_message.emit(f"API请求失败: {resp.status_code} {resp.text}")
                self.error_occurred.emit(row, col, f"HTTP {resp.status_code}")

        except Exception as e:
            self.log_message.emit(f"BANANA 生成异常: {e}")
            self.error_occurred.emit(row, col, "Exception")
            traceback.print_exc()

    def _generate_midjourney(self, prompt, image_paths, suffix, row, col):
        """Midjourney"""
        self.log_message.emit("[Midjourney] 开始生成...")
        try:
            settings = QSettings("GhostOS", "App")
            api_key = settings.value("providers/midjourney/api_key", "")
            base_url = settings.value("providers/midjourney/base_url", "")
            
            if not api_key or not base_url:
                config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'json', 'mj.json')
                if os.path.exists(config_path):
                    with open(config_path, 'r', encoding='utf-8') as f:
                        cfg = json.load(f)
                        if not api_key: api_key = cfg.get('api_key', '')
                        if not base_url: base_url = cfg.get('base_url', '')

            base_url = (base_url or '').rstrip('/')
            
            if not api_key or not base_url:
                self.log_message.emit("错误: MJ API Key或Base URL未配置")
                self.error_occurred.emit(row, col, "Config Err")
                return

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }
            
            base64_array = []
            for p in image_paths:
                if not p or not os.path.exists(p): continue
                try:
                    with open(p, "rb") as image_file:
                        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                        ext = os.path.splitext(p)[1].lower().replace('.', '')
                        if ext == 'jpg': ext = 'jpeg'
                        data_uri = f"data:image/{ext};base64,{encoded_string}"
                        base64_array.append(data_uri)
                except Exception as e:
                    self.log_message.emit(f"图片读取失败: {e}")

            submit_url = f"{base_url}/mj/submit/imagine"
            payload = {
                'prompt': prompt, 
                'base64Array': base64_array,
                'notifyHook': "",
                'state': ""
            }
            
            self.log_message.emit(f"提交任务到: {submit_url}")
            resp = requests.post(submit_url, headers=headers, json=payload, timeout=30)
            if resp.status_code != 200:
                self.log_message.emit(f"提交失败: {resp.text}")
                self.error_occurred.emit(row, col, "Submit Fail")
                return
                
            task_id = resp.json().get('result') or resp.json().get('taskId')
            if not task_id:
                self.log_message.emit(f"未获取到Task ID: {resp.text}")
                self.error_occurred.emit(row, col, "No TaskID")
                return
                
            self.log_message.emit(f"任务ID: {task_id}，开始轮询...")
            
            fetch_url = f"{base_url}/mj/task/{task_id}/fetch"
            for i in range(60): # 5 mins
                if self.stopped: break
                time.sleep(5)
                try:
                    r = requests.get(fetch_url, headers=headers, timeout=30)
                    if r.status_code == 200:
                        rj = r.json()
                        status = rj.get('status')
                        if status == 'SUCCESS':
                            img_url = rj.get('imageUrl')
                            if img_url:
                                self.log_message.emit(f"下载图片: {img_url}")
                                ir = requests.get(img_url, timeout=60)
                                if ir.status_code == 200:
                                    self.save_image(ir.content, suffix, row, col)
                                    return
                        elif status == 'FAILURE':
                            self.log_message.emit(f"MJ任务失败: {rj.get('failReason')}")
                            self.error_occurred.emit(row, col, "MJ Fail")
                            return
                except Exception as e:
                    self.log_message.emit(f"轮询异常: {e}")
            self.log_message.emit("MJ任务超时")
            self.error_occurred.emit(row, col, "Timeout")

        except Exception as e:
            self.log_message.emit(f"MJ 生成异常: {e}")
            self.error_occurred.emit(row, col, "Exception")
            traceback.print_exc()

    def _generate_banana2(self, prompt, image_paths, suffix, row, col):
        """Gemini 3.0 (BANANA2)"""
        self.log_message.emit("[Gemini 3.0] 开始生成...")
        try:
            if gemini30:
                cfg = gemini30.get_config()
            else:
                # Fallback manual config load if gemini30 not available
                cfg = {}
                # ... simple load ...
            
            api_key = cfg.get('api_key', '')
            base_url = (cfg.get('base_url') or 'https://yunwu.ai/v1beta').strip().rstrip('/')
            model = (cfg.get('model') or 'gemini-3-pro-image-preview').strip()
            
            self.log_message.emit(f"Model: {model}, Base URL: {base_url}")
            
            if not api_key:
                self.log_message.emit("错误: API Key未配置")
                self.error_occurred.emit(row, col, "No Key")
                return

            url = f"{base_url}/models/{model}:generateContent"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }
            
            parts = []
            for p in image_paths:
                if not p or not os.path.exists(p):
                    self.log_message.emit(f"警告: 图片不存在 {p}")
                    continue
                
                # Use gemini30 helper if available, or manual compression
                if gemini30:
                    res = gemini30._compress_image_to_base64(p)
                    if res:
                        mt, data = res
                        parts.append({'inlineData': {'mimeType': mt, 'data': data}})
                        self.log_message.emit(f"添加参考图: {os.path.basename(p)}")
                    else:
                        self.log_message.emit(f"错误: 图片压缩失败 {p}")
                else:
                    # Manual fallback
                    try:
                        with open(p, "rb") as f:
                            encoded = base64.b64encode(f.read()).decode('utf-8')
                            parts.append({'inlineData': {'mimeType': 'image/jpeg', 'data': encoded}})
                    except Exception as e:
                        self.log_message.emit(f"手动读取图片失败: {e}")
            
            parts.append({'text': prompt})
            
            img_cfg = {
                'aspectRatio': cfg.get('size', '1:1'),
                'imageSize': cfg.get('resolution', '1K'),
                'jpegQuality': int(cfg.get('quality', '80')),
            }
            
            body = {
                'contents': [{'role': 'user', 'parts': parts}],
                'generationConfig': {
                    'responseModalities': ['IMAGE', 'TEXT'],
                    'imageConfig': img_cfg,
                    'temperature': 0.5,
                }
            }
            
            self.log_message.emit("发送HTTP请求...")
            start_time = time.time()
            
            payload = json.dumps(body)
            resp = requests.post(url, data=payload, headers=headers, timeout=120)
            
            elapsed = time.time() - start_time
            self.log_message.emit(f"耗时: {elapsed:.2f}s, 状态码: {resp.status_code}")
            
            if resp.status_code != 200:
                self.log_message.emit(f"错误响应: {resp.text[:500]}")
                self.error_occurred.emit(row, col, f"HTTP {resp.status_code}")
                return

            try:
                ct = resp.headers.get('Content-Type', '').lower()
                if ct.startswith('image/'):
                    self.log_message.emit(f"收到直接图片响应")
                    self.save_image(resp.content, suffix, row, col)
                    return

                obj = resp.json()
                
                # Try to extract base64 from JSON manually to avoid QPixmap in thread
                # gemini30._extract_image_pixmap returns QPixmap, we want bytes
                
                found_data = None
                
                # Manual extraction logic based on gemini30 structure
                cands = obj.get('candidates') or []
                for c in cands:
                    content = c.get('content') or {}
                    parts_resp = content.get('parts') or []
                    for pr in parts_resp:
                        d = pr.get('inlineData') or pr.get('inline_data') or None
                        if isinstance(d, dict):
                            data_b64 = d.get('data') or d.get('imageData')
                            if data_b64:
                                found_data = base64.b64decode(data_b64)
                                break
                        
                        media = pr.get('media') or {}
                        mdata = media.get('data')
                        if mdata:
                            found_data = base64.b64decode(mdata)
                            break
                            
                    if found_data: break
                
                if found_data:
                    self.log_message.emit("成功从JSON提取图片数据")
                    self.save_image(found_data, suffix, row, col)
                else:
                    self.log_message.emit("未能在JSON中找到图片数据")
                    self.log_message.emit(f"JSON dump: {json.dumps(obj, ensure_ascii=False)[:300]}")
                    self.error_occurred.emit(row, col, "No Image Data")

            except Exception as e:
                self.log_message.emit(f"解析响应异常: {str(e)}")
                self.error_occurred.emit(row, col, "Parse Err")

        except Exception as e:
            self.log_message.emit(f"Gemini 3.0 生成异常: {e}")
            self.error_occurred.emit(row, col, "Exception")
            traceback.print_exc()


class SecondCreationTester(QObject):
    def __init__(self, google_node):
        super().__init__(google_node.scene())
        self.node = google_node
        self.scene = google_node.scene()
        self.worker = None

    def _extract_image_path_from_item(self, item):
        if not item:
            return ""
        try:
            v = item.data(Qt.UserRole)
            if isinstance(v, str) and v.strip():
                return v.strip()
            if isinstance(v, list):
                for x in v:
                    if isinstance(x, str) and x.strip():
                        return x.strip()
                    if isinstance(x, dict):
                        for k in ("path", "image_path", "file", "filepath"):
                            y = x.get(k)
                            if isinstance(y, str) and y.strip():
                                return y.strip()
        except Exception:
            pass

        try:
            tt = item.toolTip()
            if isinstance(tt, str) and tt.strip():
                return tt.strip()
        except Exception:
            pass

        try:
            t = item.text()
            if isinstance(t, str) and t.strip():
                return t.strip()
        except Exception:
            pass

        return ""

    def get_user_prompt(self):
        settings = QSettings("GhostOS", "2chuang")
        history = settings.value("prompt_history", [])
        if not isinstance(history, list):
            history = []
        # Ensure history items are strings
        history = [str(h) for h in history if isinstance(h, (str, int))]

        prompt_dialog = QDialog()
        prompt_dialog.setWindowTitle("二创测试 - 设置提示词")
        prompt_dialog.setMinimumWidth(500)
        prompt_dialog.setMinimumHeight(400)
        layout = QVBoxLayout(prompt_dialog)
        
        # History Selection
        history_layout = QHBoxLayout()
        history_layout.addWidget(QLabel("历史记录:"))
        history_combo = QComboBox()
        history_combo.addItem("--- 选择历史记录 ---")
        history_combo.addItems(history)
        history_layout.addWidget(history_combo, 1) # Give combo more stretch
        layout.addLayout(history_layout)
        
        layout.addWidget(QLabel("请输入生成提示词:"))
        text_edit = QTextEdit()
        text_edit.setPlaceholderText("例如: A cinematic shot of a warrior...")
        
        # Set default text to latest history if available
        if history:
            text_edit.setText(history[0])
            
        # Connect combo change to text edit
        def on_history_change(index):
            if index > 0: # 0 is "--- Select ---"
                text_edit.setText(history_combo.itemText(index))
        history_combo.currentIndexChanged.connect(on_history_change)
        
        layout.addWidget(text_edit)
        
        btn = QPushButton("开始生成")
        btn.setMinimumHeight(40)
        btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; border-radius: 4px;")
        
        def on_accept():
            current_prompt = text_edit.toPlainText().strip()
            if current_prompt:
                # Update history: remove if exists, insert at top
                if current_prompt in history:
                    history.remove(current_prompt)
                history.insert(0, current_prompt)
                # Limit to 20
                while len(history) > 20:
                    history.pop()
                
                settings.setValue("prompt_history", history)
            prompt_dialog.accept()

        btn.clicked.connect(lambda: on_accept())
        layout.addWidget(btn)
        
        if prompt_dialog.exec() == QDialog.Accepted:
            return text_edit.toPlainText().strip()
        return None

    def _start_worker(self, tasks):
        if not tasks: return
        settings = QSettings("GhostOS", "App")
        api_provider = settings.value("api/image_provider", "BANANA2")
        print(f"[Debug] 启动 Worker, 任务数: {len(tasks)}, API: {api_provider}")
        
        self.worker = ImageGenerationWorker(tasks, api_provider, self)
        self.worker.progress.connect(self.on_progress)
        self.worker.image_generated.connect(self.on_image_generated)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.log_message.connect(self.on_log)
        self.worker.finished_all.connect(self.on_finished)
        self.worker.start()
        
        QMessageBox.information(None, "开始", "二创生成任务已在后台启动。\n请留意表格状态 (⏳) 和控制台输出。")

    def run_for_single_item(self, row, col):
        prompt = self.get_user_prompt()
        if not prompt: return
        
        # Identify columns
        table = self.node.table
        headers = [table.horizontalHeaderItem(c).text() if table.horizontalHeaderItem(c) else "" for c in range(table.columnCount())]
        
        try:
            start_col = headers.index("开始帧")
        except ValueError:
            QMessageBox.warning(None, "错误", "未找到【开始帧】列")
            return
            
        end_col = headers.index("结束帧") if "结束帧" in headers else -1
        
        char_col = -1
        for name in ["人物", "角色", "Name", "Character"]:
            if name in headers:
                char_col = headers.index(name)
                break
        
        # Build Task
        tasks = []
        
        # Get Paths
        start_item = table.item(row, start_col)
        start_path = self._extract_image_path_from_item(start_item)
        
        end_path = ""
        if end_col != -1:
            end_item = table.item(row, end_col)
            end_path = self._extract_image_path_from_item(end_item)
            
        # Get Character Ref
        char_name = ""
        if char_col != -1:
            c_item = table.item(row, char_col)
            if c_item: char_name = c_item.text().strip()
        char_path = self.find_character_image(char_name)
        
        refs = []
        if col == start_col:
            if not start_path:
                QMessageBox.warning(None, "提示", "选中的开始帧为空")
                return
            refs = [start_path]
            if char_path: refs.append(char_path)
            tasks.append({'row': row, 'col': col, 'prompt': prompt, 'refs': refs, 'suffix': f"_row{row}_start"})
            
        elif col == end_col:
            ref1 = start_path if start_path else end_path
            if not ref1:
                QMessageBox.warning(None, "提示", "没有可用的参考图 (开始帧为空)")
                return
            refs = [ref1]
            if char_path: refs.append(char_path)
            tasks.append({'row': row, 'col': col, 'prompt': prompt, 'refs': refs, 'suffix': f"_row{row}_end"})
            
        else:
            QMessageBox.warning(None, "提示", "请选择开始帧或结束帧列")
            return
            
        self._start_worker(tasks)

    def run(self):
        print("[Debug] SecondCreationTester.run() 开始执行")
        prompt = self.get_user_prompt()
        if prompt is None:
            print("[Debug] 用户取消了二创测试对话框")
            return
            
        print(f"[Debug] 用户确认提示词: {prompt}")
        if not prompt:
            print("[Debug] 提示词为空，取消操作")
            QMessageBox.warning(None, "提示", "提示词不能为空")
            return
        self.process_rows(prompt)

    def process_rows(self, prompt):
        # Find columns
        table = self.node.table
        headers = []
        for c in range(table.columnCount()):
            item = table.horizontalHeaderItem(c)
            headers.append(item.text() if item else "")
            
        print(f"[Debug] 表头检测: {headers}")

        try:
            start_frame_col = headers.index("开始帧")
        except ValueError:
            print("[Debug] 未找到【开始帧】列，无法进行二创测试")
            QMessageBox.warning(None, "错误", "未找到【开始帧】列，请检查剧本表头")
            return

        end_frame_col = -1
        if "结束帧" in headers:
            end_frame_col = headers.index("结束帧")
            
        char_col = -1
        # Support various column names for Character
        for possible_name in ["人物", "角色", "Name", "Character"]:
            if possible_name in headers:
                char_col = headers.index(possible_name)
                break
        
        print(f"\n{'='*20} 二创测试开始 {'='*20}")
        print(f"[Debug] 全局API提示词: {prompt}")
        
        tasks = []
        empty_rows_count = 0
        
        # Iterate rows to build tasks
        for row in range(table.rowCount()):
            # Get Start Frame Image
            start_frame_item = table.item(row, start_frame_col)
            start_frame_path = self._extract_image_path_from_item(start_frame_item)
            
            # Get Character Name
            char_name = ""
            if char_col != -1:
                char_item = table.item(row, char_col)
                char_name = char_item.text().strip() if char_item else ""
            
            # Find Character Node Image (Ref 2)
            char_image_path = self.find_character_image(char_name)
            
            # Check End Frame
            end_frame_item = None
            end_frame_path = ""
            if end_frame_col != -1:
                end_frame_item = table.item(row, end_frame_col)
                end_frame_path = self._extract_image_path_from_item(end_frame_item)

            if not start_frame_path and not end_frame_path:
                empty_rows_count += 1
                continue

            # 1. Process Start Frame
            if start_frame_path:
                refs = [start_frame_path]
                if char_image_path:
                    refs.append(char_image_path)
                
                tasks.append({
                    'row': row,
                    'col': start_frame_col,
                    'prompt': prompt,
                    'refs': refs,
                    'suffix': f"_row{row}_start"
                })

            # 2. Process End Frame
            ref1_path = start_frame_path if start_frame_path else end_frame_path
            
            if ref1_path and end_frame_col != -1: 
                refs = [ref1_path]
                if char_image_path:
                    refs.append(char_image_path)
                
                tasks.append({
                    'row': row,
                    'col': end_frame_col,
                    'prompt': prompt,
                    'refs': refs,
                    'suffix': f"_row{row}_end"
                })

        if not tasks:
             if empty_rows_count > 0:
                 QMessageBox.warning(None, "提示", f"未找到可处理的行。\n检测到 {empty_rows_count} 行数据，但【开始帧】和【结束帧】列均为空。\n请先在表格中填入图片路径。")
             else:
                 QMessageBox.warning(None, "提示", "表格为空或未找到可处理的行 (需包含图片路径)")
             return

        self._start_worker(tasks)

    def find_character_image(self, char_name):
        if not char_name:
            return None
        
        if not self.scene:
            return None

        # Search scene for character nodes
        for item in self.scene.items():
            # Strategy 1: Check ScriptCharacterNode (list of characters)
            if hasattr(item, "character_rows") and isinstance(item.character_rows, list):
                for row in item.character_rows:
                    if hasattr(row, "name_edit") and hasattr(row, "image_path"):
                        try:
                            row_name = row.name_edit.toPlainText().strip()
                            if row_name == char_name:
                                if row.image_path and os.path.exists(row.image_path):
                                    return row.image_path
                        except Exception:
                            continue

            # Strategy 2: Check generic nodes (title match)
            if not hasattr(item, "node_title"):
                continue
                
            title = item.node_title
            
            is_match = False
            if char_name == title:
                is_match = True
            elif char_name in title and ("人物" in title or "角色" in title):
                is_match = True
            
            if is_match:
                if hasattr(item, "image_path") and item.image_path:
                    return item.image_path
                
        return None

    def on_progress(self, row, col, status):
        table = self.node.table
        item = table.item(row, col)
        if item:
            # Show status in tooltip or temp text if cell is empty
            item.setToolTip(f"状态: {status}")
            # Optional: Visualize processing state (e.g., change background color temporarily)
            # For now, just print
            print(f"[UI] Row {row} Col {col} Status: {status}")
            
            # If item has no image yet, show status text
            if not self._extract_image_path_from_item(item):
                item.setText(status)

    def on_image_generated(self, row, col, path):
        print(f"[UI] 图片生成完成: {path}")
        table = self.node.table
        item = table.item(row, col)
        if not item:
            item = QTableWidgetItem()
            table.setItem(row, col, item)
            
        item.setData(Qt.UserRole, path)
        item.setToolTip(path)
        
        # Try to load thumbnail
        try:
            pix = QPixmap(path)
            if not pix.isNull():
                item.setIcon(QIcon(pix)) # Need QIcon import? Or just set data
                # Usually we set data or delegate handles it.
                # Assuming standard table usage:
                # If we want to show image, we might need to set it as icon or use a delegate.
                # The existing code seemed to use path as text or UserRole.
                pass
        except:
            pass
            
        # Update text to show filename (or clear it if using icon)
        item.setText(path)

    def on_error(self, row, col, msg):
        print(f"[UI] 错误: Row {row} Col {col} - {msg}")
        table = self.node.table
        item = table.item(row, col)
        if item:
            item.setToolTip(f"错误: {msg}")
            if not self._extract_image_path_from_item(item):
                item.setText("❌")

    def on_log(self, msg):
        print(f"[Worker] {msg}")

    def on_finished(self):
        print("[UI] 所有任务完成")
        QMessageBox.information(None, "完成", "所有二创生成任务已完成！")
        self.worker = None
        self.deleteLater()
