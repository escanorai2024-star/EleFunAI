"""
灵动智能体 - 谷歌剧本节点模块
支持上传谷歌剧本txt文件，并分行显示
"""

import os
import sys
import traceback
import csv
import io
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsProxyWidget, QTableWidget, QTableWidgetItem,
    QFileDialog, QHeaderView, QWidget, QVBoxLayout, QLabel, QAbstractItemView,
    QMenu, QApplication, QStyledItemDelegate
)
from PySide6.QtCore import Qt, QRectF, QMimeData, QUrl, QPoint, QTimer, QSettings, QSize
from PySide6.QtGui import QColor, QFont, QBrush, QDrag, QPixmap, QPainter, QAction, QIcon

# 导入图片查看器
from lingdongpng import ImageViewerDialog
# 导入召唤魔法模块
from lingdongmofa import MagicDialog, MagicConfig
# from lingdongTXT import TextEditDialog # 移除旧引用
from textEDITgoogle import handle_google_table_double_click, open_edit_dialog_for_item

import json
import base64
import requests
import time
from datetime import datetime
from PySide6.QtCore import QThread, Signal

class PeopleImageGenerationWorker(QThread):
    """人物图片生成工作线程 - 逐个生成图片"""
    image_completed = Signal(int, str, str)  # 行号(1-based), 图片路径, 提示词
    all_completed = Signal(list)  # 所有图片信息
    error_occurred = Signal(str)
    progress_updated = Signal(int, int)  # 当前进度, 总数
    
    def __init__(self, image_api, config_file, data_rows):
        super().__init__()
        self.image_api = image_api  # "BANANA" / "BANANA2" / "Midjourney"
        self.config_file = config_file
        self.data_rows = data_rows
        self.all_images = []
        self.output_dir = os.path.join(os.getcwd(), "jpg", "people")

        # Register to global registry to prevent GC
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_people_workers'):
                app._active_people_workers = []
            app._active_people_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        app = QApplication.instance()
        if app and hasattr(app, '_active_people_workers'):
            if self in app._active_people_workers:
                app._active_people_workers.remove(self)
        self.deleteLater()
        
    def run(self):
        try:
            # 确保输出目录存在
            os.makedirs(self.output_dir, exist_ok=True)
            
            total_rows = len(self.data_rows)
            # 人物提示词在第3列 (索引2)
            prompt_idx = 2
            
            print(f"\n{'='*60}")
            print(f"[人物图片生成] 启动任务")
            print(f"[人物图片生成] API: {self.image_api}")
            print(f"[人物图片生成] 配置文件: {self.config_file}")
            print(f"[人物图片生成] 总数: {total_rows}")
            
            # 读取配置
            api_config = {}
            if self.config_file and os.path.exists(self.config_file):
                try:
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        api_config = json.load(f)
                except Exception as e:
                    print(f"[人物图片生成] 读取配置失败: {e}")

            # 逐个生成
            for i, row_data in enumerate(self.data_rows):
                row_idx = i  # 0-based index
                
                # 获取提示词
                if prompt_idx >= len(row_data):
                    continue
                    
                prompt = str(row_data[prompt_idx]).strip()
                if not prompt:
                    continue
                
                print(f"[人物图片生成] 正在生成第 {row_idx + 1}/{total_rows} 张")
                
                # 获取源图片路径 (如果有)
                source_image_path = None
                if len(row_data) > 3:
                    source_image_path = row_data[3]
                
                # 生成图片
                image_path = self.generate_single_image(row_idx + 1, prompt, api_config, source_image_path)
                
                if image_path:
                    self.all_images.append((row_idx + 1, image_path, prompt))
                    self.image_completed.emit(row_idx + 1, image_path, prompt)
                
                self.progress_updated.emit(row_idx + 1, total_rows)
                
            self.all_completed.emit(self.all_images)
            
        except Exception as e:
            error_msg = f"生成失败: {str(e)}"
            print(f"[人物图片生成] 错误: {error_msg}")
            traceback.print_exc()
            self.error_occurred.emit(error_msg)

    def generate_single_image(self, shot_number, prompt, api_config, source_image_path=None):
        """生成单张图片"""
        try:
            if self.image_api == "BANANA":
                return self.generate_with_gemini25(shot_number, prompt, api_config, source_image_path)
            elif self.image_api == "BANANA2":
                return self.generate_with_gemini30(shot_number, prompt, api_config, source_image_path)
            elif self.image_api == "Midjourney":
                return self.generate_with_midjourney(shot_number, prompt, api_config, source_image_path)
            return None
        except Exception as e:
            print(f"[人物图片生成] 生成失败: {e}")
            return None

    def generate_with_gemini25(self, shot_number, prompt, api_config, source_image_path=None):
        """使用 BANANA (Gemini 2.0 Flash) 生成"""
        try:
            # api_config 已经是 gemini.json 的内容
            api_key = api_config.get('api_key', '')
            api_url = api_config.get('base_url', 'https://generativelanguage.googleapis.com/v1beta')
            model = api_config.get('model', 'gemini-2.0-flash-exp')

            if not api_key:
                print("[BANANA] API Key未配置")
                return None
            
            url = f"{api_url}/models/{model}:generateContent?key={api_key}"
            
            parts = [{"text": prompt}]
            
            # 如果有源图片，添加到输入中
            if source_image_path and os.path.exists(source_image_path):
                try:
                    with open(source_image_path, "rb") as image_file:
                        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                        
                        # 简单的MIME类型推断
                        mime_type = "image/jpeg"
                        ext = os.path.splitext(source_image_path)[1].lower()
                        if ext == '.png': mime_type = "image/png"
                        elif ext == '.webp': mime_type = "image/webp"
                        
                        parts.append({
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": encoded_string
                            }
                        })
                    print(f"[BANANA] 已添加参考图片: {source_image_path}")
                except Exception as e:
                    print(f"[BANANA] 读取参考图片失败: {e}")
            
            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "response_modalities": ["IMAGE"],
                    "temperature": 1.0,
                    "imageConfig": {"aspectRatio": "16:9", "imageSize": "1K"}
                }
            }
            
            # Debug: 打印完整的 payload
            print(f"[BANANA] Debug Payload:")
            try:
                # 复制 payload 以避免修改原数据，将 base64 数据截断打印以免刷屏
                debug_payload = json.loads(json.dumps(payload))
                if 'contents' in debug_payload:
                    for content in debug_payload['contents']:
                        if 'parts' in content:
                            for part in content['parts']:
                                if 'inline_data' in part and 'data' in part['inline_data']:
                                    part['inline_data']['data'] = "[BASE64_IMAGE_DATA_TRUNCATED]"
                print(json.dumps(debug_payload, indent=2, ensure_ascii=False))
            except Exception as e:
                print(f"[BANANA] Debug Payload Error: {e}")

            response = requests.post(url, json=payload, timeout=300)
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result and result['candidates']:
                    parts = result['candidates'][0].get('content', {}).get('parts', [])
                    for part in parts:
                        image_data = part.get('inline_data', {}).get('data') or part.get('inlineData', {}).get('data')
                        if image_data:
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename = f"people_{shot_number:03d}_{timestamp}.jpg"
                            filepath = os.path.join(self.output_dir, filename)
                            with open(filepath, 'wb') as f:
                                f.write(base64.b64decode(image_data))
                            return filepath
            else:
                print(f"[BANANA] 请求失败: {response.status_code} {response.text}")
            return None
        except Exception as e:
            print(f"[BANANA] Error: {e}")
            return None

    def generate_with_gemini30(self, shot_number, prompt, api_config, source_image_path=None):
        """使用 BANANA2 (Gemini 3.0 Pro) 生成"""
        try:
            # api_config 已经是 gemini30.json 的内容
            api_key = api_config.get('api_key', '')
            if not api_key:
                print("[BANANA2] API Key未配置")
                return None
                
            api_url = api_config.get('base_url', 'https://generativelanguage.googleapis.com/v1beta')
            api_url = api_url.rstrip('/')
            model = api_config.get('model', 'gemini-3-pro-image-preview')
            
            url = f"{api_url}/models/{model}:generateContent?key={api_key}"
            
            image_config = {
                'aspectRatio': api_config.get('size', '16:9'),
                'imageSize': api_config.get('resolution', '1K'),
                'jpegQuality': int(api_config.get('quality', '80')),
                'numberOfImages': 1
            }
            
            parts = [{"text": prompt}]
            
            # 如果有源图片，添加到输入中
            if source_image_path and os.path.exists(source_image_path):
                try:
                    with open(source_image_path, "rb") as image_file:
                        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                        
                        # 简单的MIME类型推断
                        mime_type = "image/jpeg"
                        ext = os.path.splitext(source_image_path)[1].lower()
                        if ext == '.png': mime_type = "image/png"
                        elif ext == '.webp': mime_type = "image/webp"
                        
                        parts.append({
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": encoded_string
                            }
                        })
                    print(f"[BANANA2] 已添加参考图片: {source_image_path}")
                except Exception as e:
                    print(f"[BANANA2] 读取参考图片失败: {e}")

            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "responseModalities": ["IMAGE", "TEXT"],
                    "imageConfig": image_config,
                    "temperature": 0.5
                }
            }
            
            # Debug: 打印完整的 payload
            print(f"[BANANA2] Debug Payload:")
            try:
                # 复制 payload 以避免修改原数据，将 base64 数据截断打印以免刷屏
                debug_payload = json.loads(json.dumps(payload))
                if 'contents' in debug_payload:
                    for content in debug_payload['contents']:
                        if 'parts' in content:
                            for part in content['parts']:
                                if 'inline_data' in part and 'data' in part['inline_data']:
                                    part['inline_data']['data'] = "[BASE64_IMAGE_DATA_TRUNCATED]"
                print(json.dumps(debug_payload, indent=2, ensure_ascii=False))
            except Exception as e:
                print(f"[BANANA2] Debug Payload Error: {e}")

            response = requests.post(url, json=payload, timeout=600)
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result and result['candidates']:
                    candidate = result['candidates'][0]
                    parts = candidate.get('content', {}).get('parts', [])
                    for part in parts:
                        image_data = part.get('inline_data', {}).get('data') or part.get('inlineData', {}).get('data')
                        if image_data:
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename = f"people_{shot_number:03d}_{timestamp}_{image_config['imageSize']}.jpg"
                            filepath = os.path.join(self.output_dir, filename)
                            with open(filepath, 'wb') as f:
                                f.write(base64.b64decode(image_data))
                            return filepath
            else:
                print(f"[BANANA2] 请求失败: {response.status_code} {response.text}")
            return None
        except Exception as e:
            print(f"[BANANA2] Error: {e}")
            return None

    def generate_with_midjourney(self, shot_number, prompt, api_config, source_image_path=None):
        """使用 Midjourney 生成"""
        try:
            # api_config 已经是 mj.json 的内容
            api_key = api_config.get('api_key', '')
            api_url = api_config.get('base_url', '')
            
            if not api_key or not api_url:
                print("[Midjourney] API Key或Base URL未配置")
                return None
            
            # 去除末尾斜杠，并适配可能的后缀
            api_url = api_url.rstrip('/')
            # 假设用户填写的Base URL是 https://api.example.com/v1
            # 我们需要构造 /imagine 和 /status/taskId
            
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }
            
            # 准备base64图片数据
            base64_array = []
            if source_image_path and os.path.exists(source_image_path):
                try:
                    with open(source_image_path, "rb") as image_file:
                        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                        # 尝试构建 Data URI
                        ext = os.path.splitext(source_image_path)[1].lower().replace('.', '')
                        if ext == 'jpg': ext = 'jpeg'
                        data_uri = f"data:image/{ext};base64,{encoded_string}"
                        base64_array.append(data_uri)
                        print(f"[Midjourney] 已添加参考图片(Base64): {source_image_path}")
                except Exception as e:
                    print(f"[Midjourney] 读取参考图片失败: {e}")

            # 这里假设是 GoAPI 或类似的 MJ Proxy 接口格式
            # 提交任务
            imagine_url = f"{api_url}/mj/submit/imagine"
            # 尝试多种常见路径
            paths_to_try = ["/mj/submit/imagine", "/submit/imagine", "/imagine"]
            
            task_id = None
            
            for path in paths_to_try:
                try:
                    current_url = f"{api_url}{path}"
                    if path.startswith("http"): # 如果用户填写的base_url已经包含了完整路径
                         current_url = path
                    
                    payload = {
                        'prompt': f"{prompt} --ar 16:9",
                        'base64Array': base64_array,
                        'notifyHook': "",
                        'state': ""
                    }
                    
                    # Debug: 打印完整的 payload
                    print(f"[Midjourney] Debug Payload:")
                    try:
                        # 复制 payload 以避免修改原数据，将 base64 数据截断打印以免刷屏
                        debug_payload = json.loads(json.dumps(payload))
                        if 'base64Array' in debug_payload:
                            debug_payload['base64Array'] = [f"{item[:30]}...[BASE64_IMAGE_DATA_TRUNCATED]" for item in debug_payload['base64Array']]
                        print(json.dumps(debug_payload, indent=2, ensure_ascii=False))
                    except Exception as e:
                        print(f"[Midjourney] Debug Payload Error: {e}")

                    print(f"[Midjourney] 尝试提交任务: {current_url}")
                    resp = requests.post(current_url, headers=headers, json=payload, timeout=30)
                    
                    if resp.status_code == 200:
                        res_json = resp.json()
                        task_id = res_json.get('result') or res_json.get('taskId') or res_json.get('id')
                        if task_id:
                            break
                except:
                    continue
            
            if not task_id:
                print(f"[Midjourney] 提交任务失败，无法获取Task ID")
                return None
                
            print(f"[Midjourney] 任务已提交，Task ID: {task_id}")
            
            # 轮询状态
            # 通常查询路径是 /mj/task/{id}/fetch 或 /task/{id}/fetch
            fetch_paths = ["/mj/task/{id}/fetch", "/task/{id}/fetch", "/status/{id}"]
            
            max_retries = 60 # 5分钟
            for i in range(max_retries):
                time.sleep(5)
                
                for path in fetch_paths:
                    fetch_url = f"{api_url}{path.format(id=task_id)}"
                    try:
                        resp = requests.get(fetch_url, headers=headers, timeout=30)
                        if resp.status_code == 200:
                            res_json = resp.json()
                            status = res_json.get('status')
                            
                            if status == 'SUCCESS' or status == 'completed':
                                image_url = res_json.get('imageUrl') or res_json.get('url')
                                if image_url:
                                    # 下载图片
                                    img_resp = requests.get(image_url, timeout=60)
                                    if img_resp.status_code == 200:
                                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                        filename = f"people_{shot_number:03d}_{timestamp}_mj.png"
                                        filepath = os.path.join(self.output_dir, filename)
                                        with open(filepath, 'wb') as f:
                                            f.write(img_resp.content)
                                        return filepath
                            elif status == 'FAILURE' or status == 'failed':
                                print(f"[Midjourney] 任务失败: {res_json.get('failReason')}")
                                return None
                            # IN_PROGRESS, SUBMITTED 等待
                            break # 成功获取状态，跳出路径循环，继续等待
                    except:
                        pass
                        
            print("[Midjourney] 任务超时")
            return None
            
        except Exception as e:
            print(f"[Midjourney] Error: {e}")
            return None
# 批量魔法处理函数 -> 二创员工处理函数
def perform_batch_generation(node, prompt_template):
    """执行批量生成"""
    from PySide6.QtWidgets import QMessageBox, QTableWidgetItem
    
    # 1. 检查是否有选中行
    selected_rows = set()
    for item in node.table.selectedItems():
        selected_rows.add(item.row())
        
    target_rows = sorted(list(selected_rows))
    
    # 2. 如果没有选中行，询问是否处理所有行
    if not target_rows:
        reply = QMessageBox.question(
            None, 
            "二创员工", 
            "当前未选中任何行，是否对所有行生成提示词？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.No:
            return
        target_rows = range(node.table.rowCount())
        
    if not target_rows:
        QMessageBox.information(None, "提示", "表格为空，无法生成。")
        return
        
    # 3. 检查/创建提示词(CN)列
    magic_col_index = -1
    target_header = "提示词(CN)"
    for c in range(node.table.columnCount()):
        header_item = node.table.horizontalHeaderItem(c)
        if header_item and header_item.text() == target_header:
            magic_col_index = c
            break
    
    if magic_col_index == -1:
        magic_col_index = node.table.columnCount()
        node.table.insertColumn(magic_col_index)
        node.table.setHorizontalHeaderItem(magic_col_index, QTableWidgetItem(target_header))
        node.table.setColumnWidth(magic_col_index, 300)

    # 4. 获取提示词模版
    # 优先使用中文提示词 (content 通常为中文/原始提示词)
    template_content = prompt_template.get("content")
    # 如果中文为空，尝试使用英文
    if not template_content:
        template_content = prompt_template.get("content_en")
    
    if not template_content:
         QMessageBox.warning(None, "提示", f"提示词 '{prompt_template.get('name')}' 内容为空，请先设置。")
         return

    # 5. 开始批量处理
    count = 0
    for row in target_rows:
        # 填充
        node.table.setItem(row, magic_col_index, QTableWidgetItem(template_content))
        count += 1
        
    QMessageBox.information(None, "完成", f"已为 {count} 个镜头生成提示词(CN)！(使用模板: {prompt_template.get('name')})")

def batch_magic_handler(node):
    """处理二创员工按钮点击"""
    from PySide6.QtWidgets import QMessageBox, QMenu
    from PySide6.QtGui import QCursor, QAction
    from lingdongmofa import MagicConfig, BatchMagicSettingsDialog
    
    # 弹出菜单选择操作
    menu = QMenu()
    
    # 1. 设置提示词
    settings_action = menu.addAction("⚙️ 设置提示词模版 (风林火山)")
    
    menu.addSeparator()
    
    # 2. 批量生成选项
    menu.addAction(QAction("⚡ 二创员工 (请选择提示词):", menu, enabled=False))
    
    prompts = MagicConfig.load_prompts()
    
    for prompt in prompts:
        name = prompt.get("name", "未命名")
        content_en = prompt.get("content_en", "")
        
        # 显示名称
        display_name = f"   {name}"
        if content_en:
             display_name += f" ({content_en[:15]}...)"
        
        action = menu.addAction(display_name)
        action.triggered.connect(lambda checked, p=prompt: perform_batch_generation(node, p))

    # 在鼠标位置显示菜单
    action = menu.exec(QCursor.pos())
    
    if action == settings_action:
        # 打开设置对话框
        dialog = BatchMagicSettingsDialog(node.scene().views()[0] if node.scene() else None)
        dialog.exec()

# 导入提示词列模块
try:
    from lingdonggugetishici import add_prompt_column
except ImportError:
    print("Warning: lingdonggugetishici module not found")
    def add_prompt_column(node):
        print("add_prompt_column not available")

class DragTableWidget(QTableWidget):
    """支持拖拽图片的表格控件"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._drag_start_item = None
        self.drag_start_pos = None
        self.script_dir = None  # 用于解析相对路径
        self.node = None  # 引用父节点
        
        # 连接双击信号，替代mouseDoubleClickEvent以确保在代理控件中能稳定触发
        self.cellDoubleClicked.connect(self.on_cell_double_clicked)

    def contextMenuEvent(self, event):
        """右键菜单 - 召唤魔法"""
        item = self.itemAt(event.pos())
        if not item:
            super().contextMenuEvent(event)
            return

        # 创建菜单
        menu = QMenu(self)
        
        # 1. 基础操作
        copy_action = QAction("📄 复制内容", menu)
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(item.text()))
        menu.addAction(copy_action)
        
        menu.addSeparator()

        # 2. 魔法操作
        # 判断当前列类型
        # 0=镜号, 1=时间码, 2=景别, 3=画面内容, 4=台词/音效, 5=备注, 6=开始帧, 7=结束帧
        col = item.column()
        is_image_col = col in [6, 7]
        
        if is_image_col:
            # === 图片列逻辑 ===
            
            # 召唤魔法动作
            magic_action = QAction("🔮 召唤魔法", menu)
            # 传递当前行和列，以及初始tab索引0 (风)
            magic_action.triggered.connect(lambda: self.open_magic_dialog(item.row(), item.column(), 0))
            menu.addAction(magic_action)
            
            # 添加保存的提示词作为快捷选项
            try:
                prompts = MagicConfig.load_prompts()
                if prompts:
                    menu.addSeparator()
                    menu.addAction(QAction("快捷施法:", menu, enabled=False))
                    
                    for i, prompt_data in enumerate(prompts):
                        # 处理字典格式或旧的字符串格式
                        if isinstance(prompt_data, dict):
                            name = prompt_data.get("name", f"提示词 {i+1}")
                            content = prompt_data.get("content", "")
                        else:
                            name = f"提示词 {i+1}"
                            content = str(prompt_data)
                        
                        # 显示名称，Tooltip显示内容
                        display_text = name
                        action = QAction(f"✨ {display_text}", menu)
                        if content:
                            action.setToolTip(content[:200])

                        # 点击直接生成图片
                        if self.node:
                            action.triggered.connect(lambda checked, c=content, r=item.row(), col=item.column(): 
                                self.node.trigger_magic_generation(c, r, col))
                            menu.addAction(action)
            except Exception as e:
                print(f"Error loading magic prompts: {e}")
                
            # 检查是否有图片，如果有，添加生成图片节点选项
            img_path = item.text().strip()
            user_role_path = item.data(Qt.UserRole)
            if user_role_path and isinstance(user_role_path, str) and os.path.exists(user_role_path):
                img_path = user_role_path
            elif img_path and not os.path.isabs(img_path) and self.script_dir:
                try_path = os.path.join(self.script_dir, img_path)
                if os.path.exists(try_path):
                    img_path = try_path
            
            if img_path and os.path.exists(img_path):
                menu.addSeparator()
                create_node_action = QAction("🖼️ 生成图片节点", menu)
                create_node_action.triggered.connect(lambda: self.node.create_image_node(img_path))
                menu.addAction(create_node_action)

        else:
            # === 文本列逻辑 ===
            # 允许使用当前文本生成图片到开始帧/结束帧
            text_content = item.text().strip()
            if text_content:
                menu.addAction(QAction("🎨以此文本生成图片:", menu, enabled=False))
                
                gen_start = QAction("   👉 生成到 [开始帧]", menu)
                gen_start.triggered.connect(lambda: self.node.trigger_magic_generation(text_content, item.row(), 6))
                menu.addAction(gen_start)
                
                gen_end = QAction("   👉 生成到 [结束帧]", menu)
                gen_end.triggered.connect(lambda: self.node.trigger_magic_generation(text_content, item.row(), 7))
                menu.addAction(gen_end)
                
                # 同时也允许调用快捷提示词（追加模式？）
                # 暂时先只提供直接生成，避免菜单过长

        menu.exec(event.globalPos())

    def edit_item_prompt(self, item):
        """编辑单元格的自定义提示词"""
        from PySide6.QtWidgets import QInputDialog
        
        # 获取当前提示词 (UserRole + 1)
        current_prompt = item.data(Qt.UserRole + 1) or ""
        
        text, ok = QInputDialog.getMultiLineText(
            self,
            "编辑提示词",
            "请输入该图片的专属提示词（设置后将跳过二创员工）：",
            current_prompt
        )
        
        if ok:
            # 保存提示词
            item.setData(Qt.UserRole + 1, text.strip())
            
            # 更新Tooltip
            if text.strip():
                item.setToolTip(f"自定义提示词:\n{text.strip()}")
                # 可以考虑改变背景色或添加标记，这里暂时只更新Tooltip
            else:
                item.setToolTip("")

    def get_row_content(self, row):
        """获取指定行的文本内容（用于上下文）"""
        if row < 0 or row >= self.rowCount():
            return ""
        
        # 获取关键列：景别(2), 画面内容(3), 台词(4), 备注(5)
        shot = self.item(row, 0).text() if self.item(row, 0) else ""
        view = self.item(row, 2).text() if self.item(row, 2) else ""
        content = self.item(row, 3).text() if self.item(row, 3) else ""
        dialogue = self.item(row, 4).text() if self.item(row, 4) else ""
        note = self.item(row, 5).text() if self.item(row, 5) else ""
        
        return f"镜号:{shot} | 景别:{view} | 画面:{content} | 台词:{dialogue} | 备注:{note}"

    def open_magic_dialog(self, row, col, initial_index=0):
        """打开召唤魔法对话框"""
        # 获取当前图片路径（如果存在）
        item = self.item(row, col)
        if not item: return
        
        # 尝试获取图片路径
        file_path = None
        user_role_path = item.data(Qt.UserRole)
        if user_role_path and isinstance(user_role_path, str) and os.path.exists(user_role_path):
            file_path = user_role_path
        else:
            text_path = item.text().strip()
            if text_path and not os.path.isabs(text_path) and self.script_dir:
                try_path = os.path.join(self.script_dir, text_path)
                if os.path.exists(try_path):
                    file_path = try_path
            elif text_path and os.path.exists(text_path):
                file_path = text_path

        # 构建上下文信息
        context_info = ""
        try:
            prev_row = self.get_row_content(row - 1)
            curr_row = self.get_row_content(row)
            next_row = self.get_row_content(row + 1)
            
            context_info = f"上一镜: {prev_row}\n当前镜: {curr_row}\n下一镜: {next_row}"
        except Exception as e:
            print(f"Error getting context: {e}")

        # 打开对话框
        dialog = MagicDialog(file_path, QApplication.activeWindow(), context_info=context_info)
        if isinstance(initial_index, int):
            dialog.current_index = initial_index
            dialog.refresh_tabs()
        
        # 信号连接：当对话框保存提示词后，处理结果
        def on_prompts_saved():
             # 检查是否有名为"提示词(CN)"的列
            magic_col_index = -1
            target_header = "提示词(CN)"
            for c in range(self.columnCount()):
                header_item = self.horizontalHeaderItem(c)
                if header_item and header_item.text() == target_header:
                    magic_col_index = c
                    break
            
            # 如果没有，创建新列
            if magic_col_index == -1:
                magic_col_index = self.columnCount()
                self.insertColumn(magic_col_index)
                self.setHorizontalHeaderItem(magic_col_index, QTableWidgetItem(target_header))
                # 如果有node引用，同步更新headers属性（虽然通常是动态获取的）
                if self.node:
                    # 触发节点更新（如果需要）
                    pass

            # 获取当前生成的提示词（优先中文）
            # 或者更直接地，我们可以让MagicDialog在保存时发出信号，带上内容
            # 这里简单起见，重新加载配置
            try:
                prompts = MagicConfig.load_prompts()
                if prompts and len(prompts) > dialog.current_index:
                    prompt_data = prompts[dialog.current_index]
                    
                    # 优先使用中文提示词
                    content = ""
                    if isinstance(prompt_data, dict):
                        content = prompt_data.get("content", "")
                        if not content:
                            content = prompt_data.get("content_en", "")
                    else:
                        content = str(prompt_data)
                    
                    if content:
                        # 填充到当前行的魔法词列
                        self.setItem(row, magic_col_index, QTableWidgetItem(content))
                        # 自动调整列宽
                        self.resizeColumnToContents(magic_col_index)
                        if self.columnWidth(magic_col_index) > 300:
                             self.setColumnWidth(magic_col_index, 300)
            except Exception as e:
                print(f"Error updating magic word column: {e}")

        dialog.accepted.connect(on_prompts_saved)
        dialog.exec()

    def mousePressEvent(self, event):
        # 记录鼠标按下时的item
        # 尝试直接获取 (适用于viewport坐标)
        self._drag_start_item = self.itemAt(event.pos())
        
        # 如果失败，尝试映射坐标 (兼容旧逻辑)
        if not self._drag_start_item:
            viewport_pos = self.viewport().mapFrom(self, event.pos())
            self._drag_start_item = self.itemAt(viewport_pos)
        
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.pos()
            
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.drag_start_pos = None
        super().mouseReleaseEvent(event)

    def on_cell_double_clicked(self, row, column):
        """处理单元格双击信号"""
        # 委托给外部模块处理
        handle_google_table_double_click(self, row, column, self.script_dir, ImageViewerDialog)

    def open_edit_dialog(self, item):
        """打开文本编辑对话框"""
        open_edit_dialog_for_item(item, None)

    def mouseMoveEvent(self, event):
        if self.drag_start_pos and self._drag_start_item:
            # 动态检查是否可以拖拽
            item = self._drag_start_item
            col = item.column()
            
            # 检查表头
            header_text = self.horizontalHeaderItem(col).text() if self.horizontalHeaderItem(col) else ""
            is_image_col = header_text in ["开始帧", "结束帧", "草稿"]
            
            # 检查是否有图片数据
            user_role_path = item.data(Qt.UserRole)
            has_image_data = user_role_path and isinstance(user_role_path, str) and os.path.exists(user_role_path)
            
            # 检查文本是否像图片路径
            text = item.text().strip()
            looks_like_image = text and (text.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')))
            
            if is_image_col or has_image_data or looks_like_image:
                dist = (event.pos() - self.drag_start_pos).manhattanLength()
                if dist >= QApplication.startDragDistance():
                    # 确定最终路径
                    final_path = None
                    if has_image_data:
                        final_path = user_role_path
                    else:
                        # 尝试解析路径
                        if text and not os.path.isabs(text) and self.script_dir:
                            try_path = os.path.join(self.script_dir, text)
                            if os.path.exists(try_path):
                                final_path = try_path
                        elif text and os.path.exists(text):
                            final_path = text
                    
                    if final_path and os.path.exists(final_path):
                        event.accept()
                        self._perform_drag(final_path)
                        self.drag_start_pos = None
                        return

        super().mouseMoveEvent(event)

    def _perform_drag(self, file_path):
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(file_path)])
        drag.setMimeData(mime_data)
        
        # 尝试加载图片作为拖拽预览
        pixmap = QPixmap(file_path)
        if not pixmap.isNull():
            # 缩放图片以适应拖拽预览
            # 保持纵横比，最大尺寸 200x200
            pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            # 设置简单的拖拽视觉反馈 (回退)
            pixmap = QPixmap(120, 40)
            pixmap.fill(QColor(60, 60, 60, 200))
            painter = QPainter(pixmap)
            painter.setPen(QColor(255, 255, 255))
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "📄 图片文件")
            painter.end()
        
        drag.setPixmap(pixmap)
        # 设置热点在图片中心
        drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
        
        # 防止 QGraphicsItem::ungrabMouse 错误
        # 在开始拖拽前，如果可能，释放鼠标捕获
        # 注意：DragTableWidget 是 QWidget，不能直接调用 ungrabMouse
        # 需要通过 graphicsProxyWidget 获取代理项
        proxy = self.graphicsProxyWidget()
        if proxy and proxy.scene():
            grabber = proxy.scene().mouseGrabberItem()
            if grabber == proxy:
                proxy.ungrabMouse()
        
        drag.exec(Qt.CopyAction | Qt.MoveAction)

# SVG图标定义
SVG_GOOGLE_ICON = '''<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" stroke-width="2"/>
<path d="M14 2v6h6" stroke="currentColor" stroke-width="2"/>
<line x1="16" y1="13" x2="8" y2="13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
<line x1="16" y1="17" x2="8" y2="17" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
<line x1="10" y1="9" x2="8" y2="9" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
</svg>'''

class GoogleScriptNode:
    """谷歌剧本节点"""
    
    @staticmethod
    def create_node(CanvasNode):
        """动态创建GoogleScriptNode类，继承自CanvasNode"""
        
        class DynamicDelegate(QStyledItemDelegate):
            """动态调整字体和图标大小的代理"""
            def paint(self, painter, option, index):
                # 计算动态字体大小
                row_height = option.rect.height()
                # 基础行高40对应字体10，大行高按比例增加
                font_size = max(10, int(row_height / 3.5))
                
                option.font.setPixelSize(font_size)
                
                # 调整图标大小
                icon_size = int(row_height * 0.8)
                option.decorationSize = QSize(icon_size, icon_size)
                
                super().paint(painter, option, index)

        class GoogleScriptNodeImpl(CanvasNode):
            # 静态计数器
            instance_count = 0

            def __init__(self, x, y):
                # 更新计数器
                GoogleScriptNodeImpl.instance_count += 1
                self.node_id = GoogleScriptNodeImpl.instance_count
                
                super().__init__(x, y, 600, 400, f"谷歌剧本 #{self.node_id}", SVG_GOOGLE_ICON)
                
                # 设置背景色
                self.setBrush(QBrush(QColor("#ffffff")))
                
                # 创建代理部件容器
                self.proxy_widget = QGraphicsProxyWidget(self)
                self.proxy_widget.setZValue(10) # 确保在顶层，优先接收点击
                
                # 创建内部部件
                self.container = QWidget()
                self.container.setStyleSheet("background-color: transparent;")
                self.layout = QVBoxLayout(self.container)
                self.layout.setContentsMargins(10, 45, 10, 10) # 顶部预留给标题栏
                
                # 初始提示标签
                self.hint_label = QLabel("双击上传谷歌剧本TXT/CSV文件")
                self.hint_label.setStyleSheet("""
                    QLabel {
                        color: #333333; 
                        font-size: 16px; 
                        font-weight: bold;
                        background-color: transparent;
                    }
                """)
                self.hint_label.setAlignment(Qt.AlignCenter)
                self.layout.addWidget(self.hint_label)
                
                # 表格部件 (初始隐藏)
                self.table = DragTableWidget()
                self.table.node = self # 绑定节点引用
                self.table.setItemDelegate(DynamicDelegate(self.table)) # 设置动态代理
                self.table.setColumnCount(10)
                self.table.setHorizontalHeaderLabels(["镜号", "时间码", "景别", "画面内容", "人物", "人物关系/构图", "地点/环境", "运镜", "台词/音效", "备注"])
                
                # 表格样式 - 浅色模式
                self.table.setStyleSheet("""
                    QTableWidget {
                        background-color: #ffffff;
                        color: #202124;
                        gridline-color: #e0e0e0;
                        border: 1px solid #e0e0e0;
                        border-radius: 4px;
                        selection-background-color: #e8f0fe;
                        selection-color: #1967d2;
                    }
                    QHeaderView::section {
                        background-color: #f1f3f4;
                        color: #5f6368;
                        padding: 6px;
                        border: 1px solid #e0e0e0;
                        font-weight: bold;
                    }
                    QTableWidget::item {
                        padding: 5px;
                    }
                    QScrollBar:vertical {
                        border: none;
                        background: #f1f1f1;
                        width: 10px;
                        margin: 0px;
                    }
                    QScrollBar::handle:vertical {
                        background: #c1c1c1;
                        min-height: 20px;
                        border-radius: 5px;
                    }
                    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                        height: 0px;
                    }
                """)
                
                # 设置表格属性
                self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
                self.table.horizontalHeader().setStretchLastSection(True)
                
                # 启用垂直表头以支持调整行高 (用户请求)
                self.table.verticalHeader().setVisible(True)
                self.table.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
                self.table.verticalHeader().setDefaultSectionSize(40) # 默认行高
                self.table.verticalHeader().setFixedWidth(40) # 行号列宽度
                
                self.table.setShowGrid(True)
                # 修改触发器，禁用默认的双击编辑，以防止冲突，改用我们自定义的信号处理
                self.table.setEditTriggers(QAbstractItemView.EditKeyPressed) # 只允许按键编辑(F2)
                self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
                self.table.setVisible(False)
                
                # 设置列宽比例
                self.table.setColumnWidth(0, 50)  # 镜号
                self.table.setColumnWidth(1, 100) # 时间码
                self.table.setColumnWidth(2, 60)  # 景别
                self.table.setColumnWidth(3, 150) # 画面内容
                self.table.setColumnWidth(4, 80)  # 人物
                self.table.setColumnWidth(5, 120) # 人物关系/构图
                self.table.setColumnWidth(6, 100) # 地点/环境
                self.table.setColumnWidth(7, 80)  # 运镜
                self.table.setColumnWidth(8, 150) # 台词/音效
                self.table.setColumnWidth(9, 100) # 备注
                
                # 允许拖拽
                self.table.setDragEnabled(True)
                
                self.layout.addWidget(self.table)
                
                # 连接右键菜单
                self.table.setContextMenuPolicy(Qt.CustomContextMenu)
                self.table.customContextMenuRequested.connect(self.show_context_menu)
                
                # 连接表头右键菜单
                self.table.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
                self.table.horizontalHeader().customContextMenuRequested.connect(self.show_header_context_menu)
                
                self.proxy_widget.setWidget(self.container)
                self.proxy_widget.setPos(0, 0)
                
                # 初始化大小
                self.update_proxy_size()
                
                # 添加输出接口 (DataType.TABLE = 4)
                if hasattr(self, 'add_output_socket'):
                    self.add_output_socket(4, "剧本数据")
                
                # === 二创员工按钮 ===
                from PySide6.QtWidgets import QPushButton
                self.batch_magic_btn = QGraphicsProxyWidget(self)
                btn = QPushButton("⚡ 二创员工")
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #6200EE; 
                        color: white; 
                        border: none;
                        border-radius: 12px;
                        padding: 4px 12px;
                        font-family: "Microsoft YaHei";
                        font-weight: bold;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background-color: #3700B3;
                    }
                    QPushButton:pressed {
                        background-color: #000000;
                    }
                """)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                # Note: batch_magic_handler needs to be available in scope
                def on_batch_click(checked=False):
                    print("[谷歌剧本] 二创员工按钮被点击")
                    try:
                        batch_magic_handler(self)
                    except Exception as e:
                        error_msg = f"二创员工执行出错: {str(e)}"
                        print(f"[谷歌剧本] {error_msg}")
                        import traceback
                        traceback.print_exc()
                        from PySide6.QtWidgets import QMessageBox
                        QMessageBox.critical(None, "错误", error_msg)

                btn.clicked.connect(on_batch_click)
                self.batch_magic_btn.setWidget(btn)
                self.batch_magic_btn.setZValue(100) # Ensure it's on top
                self.batch_magic_btn.setVisible(False) # Initially hidden
                
                # === 查看表格按钮 ===
                self.view_table_btn = QGraphicsProxyWidget(self)
                view_btn = QPushButton("📊 查看表格")
                view_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #1a73e8; 
                        color: white; 
                        border: none;
                        border-radius: 12px;
                        padding: 4px 12px;
                        font-family: "Microsoft YaHei";
                        font-weight: bold;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background-color: #1557b0;
                    }
                    QPushButton:pressed {
                        background-color: #000000;
                    }
                """)
                view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                view_btn.clicked.connect(self.open_table_viewer)
                self.view_table_btn.setWidget(view_btn)
                self.view_table_btn.setZValue(100)
                self.view_table_btn.setVisible(False)

                # === 时间码设置按钮 ===
                self.time_code_btn = QGraphicsProxyWidget(self)
                time_btn = QPushButton("⏱️ 时间码")
                time_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #FBBC04; 
                        color: #202124; 
                        border: none;
                        border-radius: 12px;
                        padding: 4px 12px;
                        font-family: "Microsoft YaHei";
                        font-weight: bold;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background-color: #F9AB00;
                    }
                    QPushButton:pressed {
                        background-color: #E37400;
                    }
                """)
                time_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                time_btn.clicked.connect(self.open_time_config)
                self.time_code_btn.setWidget(time_btn)
                self.time_code_btn.setZValue(100)
                self.time_code_btn.setVisible(False)

                # === 地点设置按钮 ===
                self.map_setting_btn = QGraphicsProxyWidget(self)
                map_btn = QPushButton("🗺️ 参数设置")
                map_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #34A853; 
                        color: white; 
                        border: none;
                        border-radius: 12px;
                        padding: 4px 12px;
                        font-family: "Microsoft YaHei";
                        font-weight: bold;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background-color: #2D8E47;
                    }
                    QPushButton:pressed {
                        background-color: #206633;
                    }
                """)
                map_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                map_btn.clicked.connect(self.open_map_setting)
                self.map_setting_btn.setWidget(map_btn)
                self.map_setting_btn.setZValue(100)
                self.map_setting_btn.setVisible(False)

                # === 二创测试按钮 (用户自定义) ===
                self.second_creation_test_btn = QGraphicsProxyWidget(self)
                test_btn = QPushButton("🧪 二创测试")
                test_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #00BCD4; 
                        color: white; 
                        border: none;
                        border-radius: 12px;
                        padding: 4px 12px;
                        font-family: "Microsoft YaHei";
                        font-weight: bold;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background-color: #00ACC1;
                    }
                    QPushButton:pressed {
                        background-color: #006064;
                    }
                """)
                test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                test_btn.clicked.connect(self.on_second_creation_test_clicked)
                self.second_creation_test_btn.setWidget(test_btn)
                self.second_creation_test_btn.setZValue(100)
                self.second_creation_test_btn.setVisible(False)

                self.update_batch_btn_pos()

                # Initialize auto-cleaning
                self.clean_keywords = []
                self._is_cleaning = False
                self.load_clean_keywords()
                self.table.itemChanged.connect(self.on_table_item_changed)

            def load_clean_keywords(self):
                """Load clean keywords from JSON"""
                json_path = os.path.join(os.getcwd(), 'json', 'clean_juben.json')
                if os.path.exists(json_path):
                    try:
                        with open(json_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            self.clean_keywords = data.get("cleaning_words", [])
                            # Filter empty strings
                            self.clean_keywords = [k for k in self.clean_keywords if k and k.strip()]
                    except Exception as e:
                        print(f"Error loading clean keywords in node: {e}")
                else:
                    self.clean_keywords = []

            def on_table_item_changed(self, item):
                """Handle table item changes for auto-cleaning"""
                if self._is_cleaning or not self.clean_keywords:
                    return

                text = item.text()
                if not text:
                    return

                # Check if cleaning is needed
                needs_cleaning = False
                for kw in self.clean_keywords:
                    if kw in text:
                        needs_cleaning = True
                        break
                
                if needs_cleaning:
                    self._is_cleaning = True
                    try:
                        cleaned_text = text
                        for kw in self.clean_keywords:
                            if kw in cleaned_text:
                                cleaned_text = cleaned_text.replace(kw, "")
                        
                        if cleaned_text != text:
                            item.setText(cleaned_text)
                            # print(f"Auto-cleaned: '{text}' -> '{cleaned_text}'")
                    finally:
                        self._is_cleaning = False

            def on_second_creation_test_clicked(self):
                """点击二创测试按钮"""
                print(f"\n{'='*10} [Debug] 二创测试按钮被点击 {'='*10}")
                try:
                    import importlib
                    import sys
                    
                    module_name = "2chuangTest"
                    if module_name in sys.modules:
                        module = importlib.reload(sys.modules[module_name])
                    else:
                        module = importlib.import_module(module_name)
                        
                    tester = module.SecondCreationTester(self)
                    tester.run()
                except Exception as e:
                    print(f"Error running 2chuangTest: {e}")
                    import traceback
                    traceback.print_exc()
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(None, "错误", f"运行二创测试失败: {str(e)}")

            def trigger_second_creation_test(self, row, col):
                """触发单张图片的二创测试"""
                print(f"[谷歌剧本] 触发单张二创测试: row={row}, col={col}")
                try:
                    import importlib
                    import sys
                    
                    module_name = "2chuangTest"
                    if module_name in sys.modules:
                        module = importlib.reload(sys.modules[module_name])
                    else:
                        module = importlib.import_module(module_name)
                        
                    tester = module.SecondCreationTester(self)
                    if hasattr(tester, 'run_for_single_item'):
                        tester.run_for_single_item(row, col)
                    else:
                        from PySide6.QtWidgets import QMessageBox
                        QMessageBox.warning(None, "错误", "2chuangTest模块未找到run_for_single_item方法，请检查代码更新")
                except Exception as e:
                    print(f"Error running 2chuangTest single item: {e}")
                    import traceback
                    traceback.print_exc()
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(None, "错误", f"运行二创测试失败: {str(e)}")

            def open_map_setting(self):
                """打开地点设置窗口"""
                try:
                    from gugejuben_map_setting import MapSettingDialog
                    # 传递当前节点实例，以便在设置中执行清理等操作
                    dialog = MapSettingDialog(parent=None, node=self)
                    dialog.exec()
                except ImportError:
                    print("Error: Could not import MapSettingDialog from gugejuben_map_setting")
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(None, "错误", "无法加载地点设置模块(gugejuben_map_setting.py)")
                except Exception as e:
                    print(f"Error opening map setting: {e}")
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(None, "错误", f"打开地点设置失败: {str(e)}")


            def open_time_config(self):
                """打开时间码配置窗口"""
                try:
                    from guge_time import TimeCodeConfigWindow
                    config_win = TimeCodeConfigWindow()
                    config_win.exec()
                except ImportError:
                    print("Error: Could not import TimeCodeConfigWindow from guge_time")
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(None, "错误", "无法加载时间码模块(guge_time.py)")
                except Exception as e:
                    print(f"Error opening time config: {e}")
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(None, "错误", f"打开配置失败: {str(e)}")

            def set_table_data(self, data):
                """设置表格数据（兼容接口）"""
                self.table_data = data

            def get_output_data(self, socket_index):
                """获取输出数据"""
                # 收集表格数据
                rows = []
                if hasattr(self, 'table'):
                    # 获取表头
                    headers = []
                    for c in range(self.table.columnCount()):
                        item = self.table.horizontalHeaderItem(c)
                        headers.append(item.text() if item else f"Column {c}")
                    
                    # 获取行数据
                    for r in range(self.table.rowCount()):
                        row_data = {}
                        for c in range(self.table.columnCount()):
                            item = self.table.item(r, c)
                            text = item.text() if item else ""
                            # 使用表头作为键
                            header = headers[c] if c < len(headers) else f"Column {c}"
                            row_data[header] = text
                            # 同时提供索引访问
                            row_data[c] = text
                        
                        # 尝试智能识别特定列
                        # 1. 人物/角色
                        name = ""
                        for key in ["角色", "人物", "姓名", "Role", "Character", "Name"]:
                            if key in row_data and row_data[key]:
                                name = row_data[key]
                                break
                        row_data["_smart_name"] = name
                        rows.append(row_data)
                
                return rows

            @property
            def title_height(self):
                """兼容属性：标题栏高度"""
                return 40  # CanvasNode 默认标题栏高度大约是这个值

            @property
            def header_height(self):
                """兼容属性：表头高度"""
                if hasattr(self, 'table') and self.table.horizontalHeader():
                    return self.table.horizontalHeader().height()
                return 40

            @property
            def cell_height(self):
                """兼容属性：单元格高度"""
                # 估算值，或者取第一行的高度
                if hasattr(self, 'table') and self.table.rowCount() > 0:
                    return self.table.rowHeight(0)
                return 60
            
            def create_table(self):
                """兼容方法：刷新表格"""
                if hasattr(self, 'table'):
                    self.table.viewport().update()
                    self.update_proxy_size()
                    self.update_batch_btn_pos()

            @property
            def column_widths(self):
                """获取列宽"""
                return [self.table.columnWidth(i) for i in range(self.table.columnCount())]

            @column_widths.setter
            def column_widths(self, widths):
                """设置列宽"""
                if not widths:
                    return
                for i, width in enumerate(widths):
                    if i < self.table.columnCount():
                        self.table.setColumnWidth(i, width)

            @property
            def headers(self):
                """获取表头"""
                headers = []
                for i in range(self.table.columnCount()):
                    item = self.table.horizontalHeaderItem(i)
                    headers.append(item.text() if item else "")
                return headers

            @headers.setter
            def headers(self, value):
                """设置表头"""
                self.table.setColumnCount(len(value))
                self.table.setHorizontalHeaderLabels(value)
                # 更新列宽设置（如果是新版默认列）
                if value == ["镜号", "时间码", "景别", "画面内容", "人物", "人物关系/构图", "地点/环境", "运镜", "台词/音效", "备注"]:
                     self.table.setColumnWidth(0, 50)  # 镜号
                     self.table.setColumnWidth(1, 100) # 时间码
                     self.table.setColumnWidth(2, 60)  # 景别
                     self.table.setColumnWidth(3, 150) # 画面内容
                     self.table.setColumnWidth(4, 80)  # 人物
                     self.table.setColumnWidth(5, 120) # 人物关系/构图
                     self.table.setColumnWidth(6, 100) # 地点/环境
                     self.table.setColumnWidth(7, 80)  # 运镜
                     self.table.setColumnWidth(8, 150) # 台词/音效
                     self.table.setColumnWidth(9, 100) # 备注
                # 更新列宽设置（兼容旧版列）
                elif value == ["镜号", "时间码", "景别", "画面内容", "台词/音效", "备注", "开始帧", "结束帧"]:
                     self.table.setColumnWidth(0, 50)  # 镜号
                     self.table.setColumnWidth(1, 100) # 时间码
                     self.table.setColumnWidth(2, 60)  # 景别
                     self.table.setColumnWidth(3, 150) # 画面内容
                     self.table.setColumnWidth(4, 150) # 台词/音效
                     self.table.setColumnWidth(5, 100) # 备注
                     self.table.setColumnWidth(6, 60)  # 开始帧
                     self.table.setColumnWidth(7, 60)  # 结束帧

            @property
            def table_data(self):
                """获取表格数据"""
                data = []
                for r in range(self.table.rowCount()):
                    row = []
                    for c in range(self.table.columnCount()):
                        item = self.table.item(r, c)
                        row.append(item.text() if item else "")
                    data.append(row)
                return data

            @table_data.setter
            def table_data(self, value):
                """设置表格数据"""
                self.table.setRowCount(len(value))
                for r, row in enumerate(value):
                    for c, cell_value in enumerate(row):
                        if c < self.table.columnCount():
                            item = QTableWidgetItem(str(cell_value))
                            self.table.setItem(r, c, item)
                # 如果有数据，显示表格
                if value:
                    self.table.setVisible(True)
                    self.hint_label.setVisible(False)
                    self.update_proxy_size()

            @property
            def column_widths(self):
                """获取列宽"""
                return [self.table.columnWidth(i) for i in range(self.table.columnCount())]

            @column_widths.setter
            def column_widths(self, value):
                """设置列宽"""
                for i, width in enumerate(value):
                    if i < self.table.columnCount():
                        self.table.setColumnWidth(i, width)

            def update_batch_btn_pos(self):
                """更新右上角按钮位置"""
                width = self.rect().width()
                
                if hasattr(self, 'batch_magic_btn'):
                    # 批量魔法按钮位置 (靠右)
                    self.batch_magic_btn.setPos(width - 120, 10)
                    
                if hasattr(self, 'view_table_btn'):
                    # 查看表格按钮位置 (在批量魔法左侧)
                    self.view_table_btn.setPos(width - 230, 10)

                if hasattr(self, 'time_code_btn'):
                    # 时间码按钮位置 (在查看表格左侧)
                    self.time_code_btn.setPos(width - 340, 10)

                if hasattr(self, 'map_setting_btn'):
                    # 地点设置按钮位置 (在时间码左侧)
                    self.map_setting_btn.setPos(width - 450, 10)

                if hasattr(self, 'second_creation_test_btn'):
                    # 二创测试按钮 (在地点设置左侧)
                    self.second_creation_test_btn.setPos(width - 560, 10)

            def open_table_viewer(self):
                """打开内置网页查看表格"""
                try:
                    from gugejuben_IE import TableViewerWindow
                    # 如果窗口已存在且可见，则激活它
                    if hasattr(self, '_table_viewer_window') and self._table_viewer_window.isVisible():
                        self._table_viewer_window.raise_()
                        self._table_viewer_window.activateWindow()
                        # 更新内容
                        self._table_viewer_window.set_table_data(self.headers, self.table_data)
                        return

                    self._table_viewer_window = TableViewerWindow()
                    self._table_viewer_window.show()
                    # 传递数据
                    self._table_viewer_window.set_table_data(self.headers, self.table_data)
                except ImportError:
                    print("Error: Could not import TableViewerWindow from gugejuben_IE")
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(None, "错误", "无法加载内置浏览器模块(gugejuben_IE.py)")
                except Exception as e:
                    print(f"Error opening table viewer: {e}")
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(None, "错误", f"打开表格查看器失败: {str(e)}")

            def setRect(self, *args):
                """重写 setRect 以更新按钮位置"""
                super().setRect(*args)
                self.update_batch_btn_pos()

            def itemChange(self, change, value):
                """重写 itemChange 以处理选中状态"""
                if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
                    is_selected = bool(value)
                    if hasattr(self, 'batch_magic_btn'):
                        self.batch_magic_btn.setVisible(is_selected)
                    if hasattr(self, 'view_table_btn'):
                        self.view_table_btn.setVisible(is_selected)
                    if hasattr(self, 'time_code_btn'):
                        self.time_code_btn.setVisible(is_selected)
                    if hasattr(self, 'map_setting_btn'):
                        self.map_setting_btn.setVisible(is_selected)
                    if hasattr(self, 'second_creation_test_btn'):
                        # 检查是否有"开始帧"列
                        has_start_frame = "开始帧" in self.headers
                        self.second_creation_test_btn.setVisible(is_selected and has_start_frame)
                
                # 防止 QGraphicsItem::ungrabMouse 错误
                if change == QGraphicsItem.GraphicsItemChange.ItemSceneChange:
                    if value is None and self.scene():
                        grabber = self.scene().mouseGrabberItem()
                        if grabber and (grabber == self or self.isAncestorOf(grabber)):
                            grabber.ungrabMouse()

                return super().itemChange(change, value)
            
            def show_header_context_menu(self, pos):
                """显示表头右键菜单"""
                header = self.table.horizontalHeader()
                col_index = header.logicalIndexAt(pos)
                
                if col_index < 0:
                    return
                    
                menu = QMenu(header)
                menu.setStyleSheet("""
                    QMenu {
                        background-color: #ffffff;
                        color: #202124;
                        border: 1px solid #dcdcdc;
                        padding: 5px;
                    }
                    QMenu::item {
                        padding: 5px 20px;
                        border-radius: 4px;
                    }
                    QMenu::item:selected {
                        background-color: #e8f0fe;
                        color: #1967d2;
                    }
                """)
                
                # 获取列名
                col_item = self.table.horizontalHeaderItem(col_index)
                col_name = col_item.text() if col_item else f"Column {col_index}"
                
                # 删除列动作
                delete_action = QAction(f"🗑️ 删除列: {col_name}", menu)
                delete_action.triggered.connect(lambda: self.delete_column(col_index))
                menu.addAction(delete_action)
                
                menu.exec(header.mapToGlobal(pos))
                
            def delete_column(self, col_index):
                """删除指定列"""
                # 获取列名用于日志
                col_item = self.table.horizontalHeaderItem(col_index)
                col_name = col_item.text() if col_item else f"Column {col_index}"
                
                print(f"[谷歌剧本] 删除列: {col_name} (索引: {col_index})")
                self.table.removeColumn(col_index)

            def show_context_menu(self, pos):
                """显示右键菜单"""
                # pos 是相对于 self.table (widget) 的坐标
                global_pos = self.table.mapToGlobal(pos)
                viewport_pos = self.table.viewport().mapFromGlobal(global_pos)
                
                item = self.table.itemAt(viewport_pos)
                if not item: return
                
                # 视觉上选中该行/单元格，给予用户反馈
                self.table.setCurrentItem(item)
                
                col = self.table.column(item)
                
                # 动态检查是否为图片列 (开始帧/结束帧/草稿)
                header_text = self.table.horizontalHeaderItem(col).text()
                is_image_col = header_text in ["开始帧", "结束帧", "草稿"]
                
                # 或者检查该单元格是否包含图片路径 (UserRole)
                user_role_path = item.data(Qt.UserRole)
                has_image_data = user_role_path and isinstance(user_role_path, str)
                
                # 检查是否看起来像图片
                text = item.text().strip().lower()
                looks_like_image = text.endswith(('.png', '.jpg', '.jpeg'))
                
                menu = QMenu(self.table)
                menu.setStyleSheet("""
                    QMenu {
                        background-color: #ffffff;
                        color: #202124;
                        border: 1px solid #dcdcdc;
                        padding: 5px;
                    }
                    QMenu::item {
                        padding: 5px 20px;
                        border-radius: 4px;
                    }
                    QMenu::item:selected {
                        background-color: #e8f0fe;
                        color: #1967d2;
                    }
                    QMenu::separator {
                        height: 1px;
                        background: #e0e0e0;
                        margin: 4px 0px;
                    }
                """)
                
                # 0. 基础操作 - 复制
                copy_action = QAction("📄 复制内容", menu)
                copy_action.triggered.connect(lambda: QApplication.clipboard().setText(item.text()))
                menu.addAction(copy_action)
                menu.addSeparator()

                # 如果不是图片相关内容，直接显示菜单
                if not is_image_col and not has_image_data and not looks_like_image:
                     menu.exec(self.table.mapToGlobal(pos))
                     return
                
                # 获取路径 (可能为空)
                img_path = item.text().strip()
                # 尝试从UserRole获取 (用于Split生成的图片)
                user_role_path = item.data(Qt.UserRole)
                if user_role_path and isinstance(user_role_path, str) and os.path.exists(user_role_path):
                    img_path = user_role_path
                elif img_path and not os.path.isabs(img_path) and self.table.script_dir:
                    # 尝试解析相对路径
                    try_path = os.path.join(self.table.script_dir, img_path)
                    if os.path.exists(try_path):
                        img_path = try_path
                
                file_exists = img_path and os.path.exists(img_path)
                
                # 1. 生成图片节点 (仅当文件存在时)
                action_text = "🖼️ 生成图片节点 (在画布上)"
                if not file_exists:
                    action_text += " [文件不存在]"
                
                action_node = menu.addAction(action_text)
                if file_exists:
                    action_node.triggered.connect(lambda: self.create_image_node(img_path))
                else:
                    action_node.setEnabled(False)
                
                menu.addSeparator()

                # 2. 召唤魔法 (AI生成)
                magic_label = "🔮 召唤魔法 (AI生成)"
                if header_text == "草稿":
                    magic_label = "🔮 生成草稿 (AI生成)"
                
                magic_action = QAction(magic_label, menu)
                if header_text == "草稿":
                    magic_action.triggered.connect(lambda: self.generate_draft_image(item.row(), item.column()))
                else:
                    # 调用 table 的 open_magic_dialog
                    magic_action.triggered.connect(lambda: self.table.open_magic_dialog(item.row(), item.column()))
                menu.addAction(magic_action)

                # 二创测试 (单张)
                if header_text in ["开始帧", "结束帧"]:
                    test_action = QAction("🧪 二创测试", menu)
                    test_action.triggered.connect(lambda: self.trigger_second_creation_test(item.row(), item.column()))
                    menu.addAction(test_action)

                # 编辑提示词 (UserRole + 1)
                edit_prompt_action = QAction("✏️ 编辑提示词", menu)
                edit_prompt_action.triggered.connect(lambda: self.edit_item_prompt(item))
                menu.addAction(edit_prompt_action)

                # 3. 快捷施法
                try:
                    prompts = MagicConfig.load_prompts()
                    if prompts:
                        menu.addSeparator()
                        menu.addAction(QAction("✨ 快捷施法:", menu, enabled=False))
                        
                        for i, prompt_data in enumerate(prompts):
                            if isinstance(prompt_data, dict):
                                name = prompt_data.get("name", f"提示词 {i+1}")
                                content = prompt_data.get("content", "")
                            else:
                                name = f"提示词 {i+1}"
                                content = str(prompt_data)
                            
                            action = QAction(f"⚡ {name}", menu)
                            if content:
                                action.setToolTip(content[:200])
                                # 连接到 self.trigger_magic_generation
                                action.triggered.connect(lambda checked, c=content, r=item.row(), cl=item.column(): 
                                    self.trigger_magic_generation(c, r, cl))
                                menu.addAction(action)
                except Exception as e:
                    print(f"Error loading magic prompts: {e}")
                    
                menu.exec(self.table.mapToGlobal(pos))
            
            def generate_draft_image(self, row, col):
                """生成草稿图片"""
                print(f"[谷歌剧本] 开始生成草稿: row={row}, col={col}")
                
                # 寻找提示词
                prompt = ""
                # 优先顺序: 提示词(CN) > 提示词(EN) > 画面内容
                cn_col = -1
                en_col = -1
                content_col = -1
                
                for c in range(self.table.columnCount()):
                    header = self.table.horizontalHeaderItem(c).text().strip()
                    header_lower = header.lower()
                    
                    # 扩展匹配规则
                    if "提示词(CN)" in header or "提示词（CN）" in header or "绘画提示词(CN)" in header or "绘画提示词（CN）" in header or "prompt(cn)" in header_lower or "中文提示词" in header:
                        cn_col = c
                    elif "提示词(EN)" in header or "提示词（EN）" in header or "绘画提示词(EN)" in header or "绘画提示词（EN）" in header or "prompt(en)" in header_lower or "英文提示词" in header:
                        en_col = c
                    elif "画面内容" in header or "content" in header_lower:
                        content_col = c
                
                print(f"[谷歌剧本] 列检测结果: CN={cn_col}, EN={en_col}, Content={content_col}")
                
                if cn_col >= 0:
                    item = self.table.item(row, cn_col)
                    if item: prompt = item.text()
                    if prompt: print(f"[谷歌剧本] 找到中文提示词: {prompt[:20]}...")
                
                if not prompt and en_col >= 0:
                    item = self.table.item(row, en_col)
                    if item: prompt = item.text()
                    if prompt: print(f"[谷歌剧本] 找到英文提示词: {prompt[:20]}...")
                    
                if not prompt and content_col >= 0:
                    item = self.table.item(row, content_col)
                    if item: prompt = item.text()
                    if prompt: print(f"[谷歌剧本] 找到画面内容作为提示词: {prompt[:20]}...")
                
                if prompt:
                    # 使用专门的草稿目录，避免触发其他逻辑
                    self.trigger_magic_generation(prompt, row, col, output_subfolder="draft_images")
                else:
                    from PySide6.QtWidgets import QMessageBox
                    # 尝试查找合适的父窗口
                    view = self.scene().views()[0] if self.scene() and self.scene().views() else None
                    QMessageBox.warning(view, "提示", "未找到有效的提示词，请先生成或填写提示词。")

            def create_image_node(self, img_path):
                """创建图片节点"""
                # 获取场景
                scene = self.scene()
                if not scene: return
                
                # 查找主窗口引用 (用于调用lingdong.py中的功能)
                # 这是一个简化的查找方式，假设scene.views()[0]是GraphicsView，其parent是主窗口
                views = scene.views()
                if not views: return
                
                view = views[0]
                # 尝试找到包含 ImageNodeFactory 的环境
                # 这里我们直接创建 ImageNode，需要知道 ImageNode 的类定义
                # 但由于 GoogleScriptNode 是在 lingdonggooglejuben.py 中定义的，
                # 它可能无法直接访问 lingdong.py 中的 ImageNode 类。
                # 我们可以发送一个自定义事件或者使用 view 的方法
                
                # 计算新节点位置 (在当前节点右侧)
                pos = self.pos()
                new_x = pos.x() + self.rect().width() + 50
                new_y = pos.y()
                
                # 使用主界面的方法添加节点 (如果可行)
                # 假设 view.parent() 是 WorkbenchPanel 或类似，再往上是主窗口
                # 更稳健的方法是利用 scene 的 data 或者 item 的 data
                
                # 这里我们尝试直接在 scene 中添加 item
                # 为了解耦，我们最好触发一个信号，但在 CanvasNode 中添加信号比较麻烦
                # 我们可以尝试导入 lingdongpng
                
                try:
                    from lingdongpng import ImageNode as ImageNodeFactory
                    # 我们需要 CanvasNode 基类，但这里 self 就是 CanvasNode 的子类实例
                    # 我们可以获取 self.__class__.__bases__[0]
                    CanvasNodeClass = self.__class__.__bases__[0]
                    
                    ImageNodeClass = ImageNodeFactory.create_image_node(CanvasNodeClass)
                    image_node = ImageNodeClass(new_x, new_y)
                    image_node.load_image(img_path)
                    scene.addItem(image_node)
                    print(f"[谷歌剧本] 已召唤图片节点: {img_path}")
                except Exception as e:
                    print(f"[谷歌剧本] 召唤失败: {e}")
                    import traceback
                    traceback.print_exc()
                    from PySide6.QtWidgets import QMessageBox
                    # 尝试获取视图以显示消息框
                    view = self.scene().views()[0] if self.scene() and self.scene().views() else None
                    QMessageBox.critical(view, "召唤失败", f"无法创建图片节点:\n{str(e)}")

            def adjust_layout_to_size(self):
                """调整布局以适应尺寸 (始终显示6行)"""
                if not hasattr(self, 'table'): return
                
                # 当前节点高度
                current_height = self.rect().height()
                
                # 计算可用高度
                # 布局边距: Top=45, Bottom=10
                # 缓冲: 5
                # 表头高度
                header_height = self.table.horizontalHeader().height()
                if header_height <= 0: header_height = 35
                
                available_height = current_height - 55 - header_height - 5
                
                # 计算行高 (始终显示6行)
                row_height = max(30, int(available_height / 6))
                
                # 应用行高
                for row in range(self.table.rowCount()):
                    self.table.setRowHeight(row, row_height)

            def update_proxy_size(self):
                """更新代理部件大小以适应节点"""
                if hasattr(self, 'proxy_widget'):
                    self.proxy_widget.resize(self.rect().width(), self.rect().height())
                
                # 调整内部布局
                self.adjust_layout_to_size()
            
            def setRect(self, *args):
                """重写setRect以在大小改变时更新接口位置"""
                super().setRect(*args)
                self.update_proxy_size()
                # 这里假设CanvasNode会在调整大小时调用setRect，所以主要逻辑在setRect中
                
            def setRect(self, x, y, w, h):
                """重写setRect以同步更新代理部件大小"""
                super().setRect(x, y, w, h)
                self.update_proxy_size()
                
            def mouseDoubleClickEvent(self, event):
                """双击事件"""
                # 如果点击的是标题栏区域，交给父类处理（可能是折叠等操作）
                if event.pos().y() < 40:
                    super().mouseDoubleClickEvent(event)
                    return

                # 否则打开文件对话框
                file_path, _ = QFileDialog.getOpenFileName(
                    None, "选择谷歌剧本文件", "", "剧本文件 (*.txt *.csv);;文本文件 (*.txt);;CSV文件 (*.csv);;所有文件 (*)"
                )
                
                if file_path:
                    self.load_script(file_path)

            def trigger_magic_generation(self, prompt, row, col, output_subfolder="image_node_gen"):
                """触发魔法图片生成"""
                print(f"[谷歌剧本] 触发魔法生成: row={row}, col={col}, prompt={prompt[:20]}..., output={output_subfolder}")
                
                # 获取API配置 (使用与lingdongpng.py一致的配置)
                settings = QSettings("GhostOS", "App")
                image_api = settings.value("api/image_provider", "BANANA")
                
                app_root = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
                config_file = ""
                
                if image_api == "BANANA":
                    config_file = os.path.join(app_root, "json", "gemini.json")
                elif image_api == "BANANA2":
                    config_file = os.path.join(app_root, "json", "gemini30.json")
                elif image_api == "Midjourney":
                    config_file = os.path.join(app_root, "json", "mj.json")
                
                if not os.path.exists(config_file):
                    print(f"[谷歌剧本] 配置文件不存在: {config_file}")
                    from PySide6.QtWidgets import QMessageBox
                    view = self.scene().views()[0] if self.scene() and self.scene().views() else None
                    QMessageBox.warning(view, "配置缺失", f"找不到API配置文件: {config_file}\n请在主界面设置中配置API。")
                    return

                # 更新左侧闪电状态栏 (与lingdongpng.py一致)
                try:
                    for widget in QApplication.topLevelWidgets():
                        if hasattr(widget, 'set_connection_text'):
                            widget.set_connection_text(f"正在召唤魔法: {prompt[:15]}...", 'loading')
                            break
                except Exception as e:
                    print(f"Update connection status error: {e}")

                # 检查是否有原图作为参考
                source_image_path = None
                item = self.table.item(row, col)
                if item:
                    # 尝试获取UserRole路径
                    user_role_path = item.data(Qt.UserRole)
                    if user_role_path and isinstance(user_role_path, str) and os.path.exists(user_role_path):
                        source_image_path = user_role_path
                    else:
                        text_path = item.text().strip()
                        if text_path:
                            if os.path.exists(text_path):
                                source_image_path = text_path
                            elif self.table.script_dir:
                                try_path = os.path.join(self.table.script_dir, text_path)
                                if os.path.exists(try_path):
                                    source_image_path = try_path

                # Worker 期望 data_rows 中每行: [unused, unused, prompt, source_image_path]
                # 我们把 row, col 放在前两列，以便在回调中恢复
                data_rows = [[row, col, prompt, source_image_path]]
                
                # 创建并启动Worker
                self.magic_worker = PeopleImageGenerationWorker(image_api, config_file, data_rows)
                # 设置输出目录为 image_node_gen (与多图模式一致)
                self.magic_worker.output_dir = output_subfolder
                self.magic_worker.image_completed.connect(self.on_magic_generation_completed)
                self.magic_worker.finished.connect(self.on_magic_worker_finished)
                self.magic_worker.start()
                
                # 显示加载状态
                if item:
                    item.setText("🔮 生成中...")

            def on_magic_generation_completed(self, index, image_path, prompt):
                """魔法生成完成回调"""
                try:
                    # 更新左侧闪电状态栏
                    try:
                        for widget in QApplication.topLevelWidgets():
                            if hasattr(widget, 'set_connection_text'):
                                widget.set_connection_text("召唤魔法完成", 'success')
                                # 3秒后恢复正常状态
                                QTimer.singleShot(3000, lambda: widget.set_connection_text("已连接", 'normal'))
                                break
                    except Exception as e:
                        print(f"Update connection status error: {e}")

                    # Worker 回传的是 1-based 的 index
                    row_idx = index - 1 
                    if hasattr(self, 'magic_worker') and self.magic_worker and row_idx < len(self.magic_worker.data_rows):
                        original_data = self.magic_worker.data_rows[row_idx]
                        target_row = original_data[0]
                        target_col = original_data[1]
                        
                        print(f"[谷歌剧本] 图片生成成功: {image_path} -> ({target_row}, {target_col})")
                        
                        # 更新表格
                        item = self.table.item(target_row, target_col)
                        if not item:
                            item = QTableWidgetItem()
                            self.table.setItem(target_row, target_col, item)
                        
                        # 设置新图片
                        item.setText("")
                        item.setToolTip(image_path)
                        item.setData(Qt.UserRole, image_path)
                        item.setIcon(QIcon(image_path))
                        
                        # 调整布局
                        self.adjust_layout_to_size()
                        
                except Exception as e:
                    print(f"[谷歌剧本] 处理生成结果出错: {e}")
                    traceback.print_exc()

            def on_magic_worker_finished(self):
                """Worker 完成"""
                self.magic_worker = None
                    
            def load_script(self, file_path):
                """加载剧本文件"""
                try:
                    # 记录文件目录
                    self.table.script_dir = os.path.dirname(file_path)

                    content = ""
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                    except UnicodeDecodeError:
                        try:
                            with open(file_path, 'r', encoding='gbk') as f:
                                content = f.read()
                        except UnicodeDecodeError:
                            with open(file_path, 'r', encoding='gb18030', errors='ignore') as f:
                                content = f.read()
                    
                    rows = []
                    is_csv = file_path.lower().endswith('.csv')
                    
                    if is_csv:
                        # 使用 csv 模块解析
                        f = io.StringIO(content)
                        reader = csv.reader(f)
                        rows = list(reader)
                    else:
                        # 原有的 txt 解析逻辑
                        lines = content.strip().split('\n')
                        for line in lines:
                            line = line.strip()
                            if not line: continue
                            # 简单的逗号分割，如果是中文逗号也支持一下
                            line = line.replace('，', ',')
                            parts = line.split(',')
                            # 去除空格
                            parts = [p.strip() for p in parts]
                            rows.append(parts)

                    if not rows: return

                    # 预处理第一行以检测表头
                    first_row = rows[0]
                    # 去除BOM
                    if first_row and isinstance(first_row[0], str):
                         first_row[0] = first_row[0].strip().replace('\ufeff', '')
                    
                    # 检测是否有表头
                    possible_headers = ["镜号", "镜头号", "场号", "序号", "编号", "id", "ID"]
                    has_header = first_row and first_row[0] in possible_headers
                    
                    # 判断是“追加模式”还是“覆盖/新建模式”
                    # 如果表格已有数据，则默认为追加
                    is_appending = self.table.rowCount() > 0
                    
                    if not is_appending:
                        # === 初始化表格结构 ===
                        if has_header:
                            # 使用文件中的表头
                            col_count = len(first_row)
                            self.table.setColumnCount(col_count)
                            self.table.setHorizontalHeaderLabels(first_row)
                            rows = rows[1:] # 数据中移除表头
                        else:
                            # 恢复默认表头 (10列)
                            self.table.setColumnCount(10)
                            self.table.setHorizontalHeaderLabels(["镜号", "时间码", "景别", "画面内容", "人物", "人物关系/构图", "地点/环境", "运镜", "台词/音效", "备注"])
                        
                        self.table.setRowCount(0)
                    else:
                        # === 追加模式 ===
                        if has_header:
                            rows = rows[1:] # 仅仅移除文件中的表头行，不修改表格结构
                        # 不清空表格，直接追加
                        pass

                    # 切换显示
                    self.hint_label.setVisible(False)
                    self.table.setVisible(True)
                    
                    for row_data in rows:
                        self.table.insertRow(self.table.rowCount())
                        current_row = self.table.rowCount() - 1
                        
                        # 动态列数限制
                        current_col_count = self.table.columnCount()
                        
                        for col_idx, text in enumerate(row_data):
                            if col_idx >= current_col_count: break 
                            item = QTableWidgetItem(str(text).strip())
                            item.setToolTip(str(text).strip()) # 鼠标悬停显示完整内容
                            self.table.setItem(current_row, col_idx, item)
                            
                    print(f"[谷歌剧本] 已加载: {file_path}")
                    
                    # 调整布局以适应6行显示
                    self.adjust_layout_to_size()
                    
                except Exception as e:
                    print(f"[谷歌剧本] 加载失败: {e}")
                    from PySide6.QtWidgets import QMessageBox
                    # 注意：在QGraphicsView中弹出QMessageBox可能需要指定父窗口
                    # 这里简单打印，实际应用可能需要更友好的提示

        return GoogleScriptNodeImpl
