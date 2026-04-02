import os
import sys
from PySide6.QtCore import Qt, QSettings, QObject, Signal
from PySide6.QtWidgets import QMessageBox, QApplication, QTableWidgetItem
from daoyan_fenjingtu import StoryboardDialog
from daoyan_image1toimage2 import ImageToImageWorker
from daoyan_tupian_fujiatishici import AdditionalImagePromptManager


def _get_google_node(node):
    if not hasattr(node, "input_sockets") or not node.input_sockets:
        QMessageBox.warning(None, "提示", "未找到输入接口")
        return None
    socket = node.input_sockets[0]
    if not socket.connections:
        QMessageBox.warning(None, "提示", "请先连接谷歌剧本节点！")
        return None
    connection = socket.connections[0]
    if not connection or not connection.source_socket:
        QMessageBox.warning(None, "提示", "连接无效或源节点未找到！")
        return None
    google_node = connection.source_socket.parent_node
    if not hasattr(google_node, "node_title") or "谷歌剧本" not in google_node.node_title:
        QMessageBox.warning(None, "提示", "连接的节点不是谷歌剧本节点！")
        return None
    return google_node


def _get_previous_ref_image(node, row):
    prev_row = row - 1
    prev_item = node.table.item(prev_row, 6)
    prev_images = []
    if prev_item:
        data = prev_item.data(Qt.UserRole)
        if data and isinstance(data, list):
            prev_images = data
    if not prev_images:
        QMessageBox.warning(None, "提示", "上一镜没有分镜图，无法参考。")
        return None
    ref_image = None
    for img in reversed(prev_images):
        if img and isinstance(img, str) and os.path.exists(img):
            ref_image = img
            break
    if not ref_image:
        QMessageBox.warning(None, "提示", "上一镜没有有效的分镜图文件。")
        return None
    return ref_image


def _get_shot_text(table, row):
    item_shot = table.item(row, 0)
    if item_shot:
        return item_shot.text()
    return str(row + 1)


def _collect_target_rows(node, start_row):
    row_count = node.table.rowCount()
    targets = []
    for r in range(start_row, row_count):
        targets.append(r)
    return targets


def _find_prompt_column(google_node):
    prompt_col_idx = -1
    table = google_node.table
    for c in range(table.columnCount()):
        header = table.horizontalHeaderItem(c)
        if not header:
            continue
        text = header.text()
        if ("提示词" in text and "CN" in text) or ("Painting Prompt" in text and "CN" in text):
            prompt_col_idx = c
            break
    return prompt_col_idx


def _extract_paths(data):
    paths = []
    if not data:
        return paths
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                if "path" in item:
                    paths.append(item["path"])
            elif isinstance(item, str):
                paths.append(item)
    elif isinstance(data, str):
        paths.append(data)
    return paths


def _collect_aux_images(node, row):
    images = []
    item_char = node.table.item(row, 3)
    if item_char:
        images.extend(_extract_paths(item_char.data(Qt.UserRole)))
    item_prop = node.table.item(row, 4)
    if item_prop:
        images.extend(_extract_paths(item_prop.data(Qt.UserRole)))
    item_scene = node.table.item(row, 5)
    if item_scene:
        images.extend(_extract_paths(item_scene.data(Qt.UserRole)))
    images = list(
        dict.fromkeys(
            [p for p in images if p and isinstance(p, str) and os.path.exists(p)]
        )
    )
    return images


def _build_prompt_for_row(node, google_node, row, prompt_col_idx):
    google_prompt = ""
    if row < google_node.table.rowCount():
        item_p = google_node.table.item(row, prompt_col_idx)
        if item_p:
            google_prompt = item_p.text()
    item_img_prompt = node.table.item(row, 7)
    director_img_prompt = item_img_prompt.text() if item_img_prompt else ""
    main_prompt = director_img_prompt if director_img_prompt.strip() else google_prompt
    item_studio = node.table.item(row, 2)
    studio_text = item_studio.text() if item_studio else ""
    combined = f"{main_prompt}\n{studio_text}".strip()
    return combined


class AutoTrackSequenceManager(QObject):
    finished = Signal()
    progress_updated = Signal(str)

    def __init__(self, node, task_configs, initial_ref_image, batch_count, image_api, config_file):
        super().__init__()
        self.node = node
        self.task_configs = task_configs
        self.current_ref_image = initial_ref_image
        self.batch_count = batch_count
        self.image_api = image_api
        self.config_file = config_file
        self.current_idx = 0
        self.current_worker = None

    def start(self):
        self.process_next()

    def process_next(self):
        if self.current_idx >= len(self.task_configs):
            self.progress_updated.emit("自动追踪任务已全部完成！")
            QMessageBox.information(None, "提示", "自动追踪任务全部完成！")
            self.finished.emit()
            return

        config = self.task_configs[self.current_idx]
        
        # 3. 发送进度信号
        total = len(self.task_configs)
        current = self.current_idx + 1
        msg = f"🎯 正在自动追踪: {current}/{total} (镜头 {config['shot_number']}) - 模式: {config['mode']}"
        self.progress_updated.emit(msg)
        
        # Build tasks for this step
        # The first image is the reference image from previous step
        final_images = [self.current_ref_image] + config['aux_images']
        
        task_base = {
            "row_idx": config['row_idx'],
            "prompt": config['prompt'],
            "additional_prompt": config['additional_prompt'],
            "images": final_images,
            "mode": config['mode'],
            "shot_number": config['shot_number'],
        }

        tasks = []
        for _ in range(self.batch_count):
            tasks.append(dict(task_base))

        # Update loading state
        item = self.node.table.item(config['row_idx'], 6)
        if not item:
            item = QTableWidgetItem()
            self.node.table.setItem(config['row_idx'], 6, item)
        item.setData(Qt.UserRole + 2, "loading")
        self.node.table.viewport().update()

        # Create worker
        self.current_worker = ImageToImageWorker(
            self.image_api, self.config_file, tasks, os.path.join("jpg", "storyboard_output"), parent=None
        )
        
        # Manage worker lifecycle
        app = QApplication.instance()
        if not hasattr(app, "_active_img2img_workers"):
            app._active_img2img_workers = []
        app._active_img2img_workers.append(self.current_worker)
        
        self.current_worker.image_completed.connect(self.on_image_completed)
        self.current_worker.task_failed.connect(self.node.handle_storyboard_error)
        self.current_worker.error_occurred.connect(lambda err: print(f"Error: {err}"))
        self.current_worker.finished.connect(self.on_step_finished)
        
        self.current_worker.start()

    def on_image_completed(self, row_idx, path, prompt, shot_number):
        # Update UI
        self.node.update_storyboard_cell(row_idx, path, prompt, shot_number)
        # Update reference image for next step
        self.current_ref_image = path

    def on_step_finished(self):
        # Cleanup current worker
        if self.current_worker:
            app = QApplication.instance()
            if hasattr(app, "_active_img2img_workers") and self.current_worker in app._active_img2img_workers:
                app._active_img2img_workers.remove(self.current_worker)
            self.current_worker.deleteLater()
            self.current_worker = None
        
        # Move to next step
        self.current_idx += 1
        self.process_next()


def run_auto_track_storyboard_generation(node, row):
    if row <= 0:
        QMessageBox.warning(None, "提示", "第一行无法自动追踪（无上一镜）。")
        return
    google_node = _get_google_node(node)
    if not google_node:
        return
    ref_image = _get_previous_ref_image(node, row)
    if not ref_image:
        return
    dialog = StoryboardDialog(node.container)
    dialog.load_settings()
    if not dialog.exec():
        return
    selected_mode = dialog.selection
    
    # 收集从当前行开始直到末尾的所有行
    target_rows = _collect_target_rows(node, row)
    
    if not target_rows:
        QMessageBox.warning(None, "提示", "未找到需要自动追踪的行。")
        return
    prompt_col_idx = _find_prompt_column(google_node)
    if prompt_col_idx == -1:
        QMessageBox.warning(None, "提示", "未找到提示词列(CN)。")
        return
    additional_img_prompt = AdditionalImagePromptManager().load_prompt()
    
    # Pre-calculate configs
    task_configs = []
    for r in target_rows:
        combined_prompt = _build_prompt_for_row(node, google_node, r, prompt_col_idx)
        if not combined_prompt:
            continue
        aux_images = _collect_aux_images(node, r)
        shot_text = _get_shot_text(node.table, r)
        
        config = {
            "row_idx": r,
            "prompt": combined_prompt,
            "additional_prompt": additional_img_prompt,
            "aux_images": aux_images,
            "mode": selected_mode,
            "shot_number": shot_text
        }
        task_configs.append(config)

    if not task_configs:
        QMessageBox.warning(None, "提示", "没有可生成的自动追踪任务。")
        return

    batch_count = getattr(node, "storyboard_batch_count", 1)
    if batch_count < 1:
        batch_count = 1
        
    settings = QSettings("GhostOS", "App")
    image_api = settings.value("api/image_provider", "BANANA")
    app_root = (
        os.path.dirname(sys.executable)
        if getattr(sys, "frozen", False)
        else os.path.dirname(os.path.abspath(__file__))
    )
    config_file = ""
    if image_api == "BANANA":
        config_file = os.path.join(app_root, "json", "gemini.json")
    elif image_api == "BANANA2":
        config_file = os.path.join(app_root, "json", "gemini30.json")
    elif image_api == "Midjourney":
        config_file = os.path.join(app_root, "json", "mj.json")
        
    # Create and start manager
    manager = AutoTrackSequenceManager(node, task_configs, ref_image, batch_count, image_api, config_file)
    node.auto_track_manager = manager # Keep reference
    
    if hasattr(node, 'update_auto_track_status'):
        manager.progress_updated.connect(node.update_auto_track_status)
        
    manager.start()
    
    QMessageBox.information(None, "提示", "已启动自动追踪分镜生成任务（顺序模式）！")
