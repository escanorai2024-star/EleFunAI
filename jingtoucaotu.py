import os
import sys
import json
from PySide6.QtCore import Qt, QSettings, QCoreApplication
from PySide6.QtWidgets import QTableWidgetItem, QMessageBox

class LensSketchGenerator:
    """镜头草图生成器"""
    def __init__(self, node):
        self.node = node
        self.table = node.table
        self.worker = None

    def start(self):
        """开始生成镜头草图"""
        # 1. 确保存在"镜头草图"列
        target_col = self.ensure_column("镜头草图")
        
        # 2. 获取提示词
        prompts = self.get_prompts()
        if not prompts:
            # 尝试查找父窗口
            view = self.node.scene().views()[0] if self.node.scene() and self.node.scene().views() else None
            QMessageBox.warning(view, "提示", "未找到有效的'绘画提示词(CN)'或内容为空。\n请先使用二创员工生成提示词。")
            return

        # 3. 启动生成
        self.start_generation(prompts, target_col)

    def ensure_column(self, header_text):
        """确保列存在，返回列索引"""
        for c in range(self.table.columnCount()):
            item = self.table.horizontalHeaderItem(c)
            if item and item.text() == header_text:
                return c
        
        # 添加新列
        col = self.table.columnCount()
        self.table.insertColumn(col)
        self.table.setHorizontalHeaderItem(col, QTableWidgetItem(header_text))
        self.table.setColumnWidth(col, 200)
        return col

    def get_prompts(self):
        """获取所有行的提示词"""
        # 寻找提示词(CN)列
        cn_col = -1
        for c in range(self.table.columnCount()):
            header = self.table.horizontalHeaderItem(c).text()
            if "提示词(CN)" in header or "提示词（CN）" in header or "绘画提示词(CN)" in header or "绘画提示词（CN）" in header:
                cn_col = c
                break
        
        if cn_col == -1:
            print("[镜头草图] 未找到提示词(CN)列")
            return []
            
        prompts = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, cn_col)
            if item:
                text = item.text().strip()
                if text:
                    prompts.append((r, text))
        
        print(f"[镜头草图] 找到 {len(prompts)} 个提示词")
        return prompts

    def start_generation(self, prompts, target_col):
        """启动生成任务"""
        # 准备数据: [row, col, prompt, source_image]
        data_rows = []
        for r, prompt in prompts:
            # col 参数这里用于回调定位，我们传入 target_col
            data_rows.append([r, target_col, prompt, None])
        
        if not data_rows:
            return

        # 获取API配置
        settings = QSettings("GhostOS", "App")
        image_api = settings.value("api/image_provider", "BANANA")
        
        # 获取配置文件路径
        app_root = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        # 处理可能的 __file__ 不存在的情况 (在某些打包环境中)
        if not os.path.exists(app_root):
             app_root = os.getcwd()

        config_file = ""
        if image_api == "BANANA":
            config_file = os.path.join(app_root, "json", "gemini.json")
        elif image_api == "BANANA2":
            config_file = os.path.join(app_root, "json", "gemini30.json")
        elif image_api == "Midjourney":
             # MJ 配置通常在 MJ.py 中处理，或者也有 json
             # 这里假设 PeopleImageGenerationWorker 会处理
             pass
        
        print(f"[镜头草图] 启动生成: API={image_api}, Count={len(data_rows)}")

        # 延迟导入以避免循环引用
        from lingdonggooglejuben import PeopleImageGenerationWorker
        
        # 创建并启动 Worker
        self.worker = PeopleImageGenerationWorker(image_api, config_file, data_rows)
        self.worker.output_dir = "lens_sketch_images" # 专用目录
        self.worker.image_completed.connect(self.on_image_completed)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()
        
        # 防止 worker 被垃圾回收
        self.node.lens_sketch_worker = self.worker

    def on_image_completed(self, row_idx_1based, image_path, prompt):
        """图片生成完成回调"""
        try:
            from PySide6.QtGui import QIcon
            
            # row_idx 是 1-based (Worker 内部逻辑)
            # 但我们需要检查 PeopleImageGenerationWorker 是怎么传回的
            # 查看 lingdonggooglejuben.py: self.image_completed.emit(row_idx + 1, image_path, prompt)
            # 确实是 1-based
            
            # 但 wait, PeopleImageGenerationWorker 的 data_rows 包含了 [row, col, prompt, source]
            # 它的 generate_single_image 用的是 loop index + 1 作为 shot_number
            # image_completed emit 的也是 row_idx + 1
            
            # 我们需要找回原始的 row index
            # Worker 的 data_rows 顺序与我们传入的一致吗？是的。
            # 所以 index-1 对应 data_rows[index-1]
            
            worker_idx = row_idx_1based - 1
            if worker_idx < 0 or worker_idx >= len(self.worker.data_rows):
                print(f"[镜头草图] 索引越界: {worker_idx}")
                return
                
            original_data = self.worker.data_rows[worker_idx]
            target_row = original_data[0]
            target_col = original_data[1]
            
            print(f"[镜头草图] 图片完成: {image_path} -> ({target_row}, {target_col})")
            
            # 更新表格
            item = self.table.item(target_row, target_col)
            if not item:
                item = QTableWidgetItem()
                self.table.setItem(target_row, target_col, item)
            
            item.setText("") # 不显示文字
            item.setToolTip(image_path)
            item.setData(Qt.UserRole, image_path)
            item.setIcon(QIcon(image_path))
            
            # 调整行高以显示图片
            self.table.setRowHeight(target_row, 100)
            
        except Exception as e:
            print(f"[镜头草图] 回调错误: {e}")
            traceback.print_exc()

    def on_worker_finished(self):
        print("[镜头草图] 所有任务完成")
        self.worker = None
