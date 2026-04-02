"""
灵动智能体 - 二创员工模块
用于处理谷歌剧本节点的批量图片生成
"""

import os
import sys
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog, QMenu
from PySide6.QtGui import QAction, QCursor
from PySide6.QtCore import QSettings, Qt

from lingdongmofa import MagicDialog, MagicConfig


def batch_magic_handler(node):
    """处理二创员工点击事件"""
    # 获取保存的提示词
    prompts = MagicConfig.load_prompts()
    
    # 创建菜单
    menu = QMenu()
    menu.setStyleSheet("""
        QMenu {
            background-color: #ffffff;
            border: 1px solid #dcdcdc;
            border-radius: 8px;
            padding: 5px;
        }
        QMenu::item {
            padding: 8px 25px;
            border-radius: 4px;
            font-family: "Microsoft YaHei";
            font-size: 14px;
            color: #333333;
        }
        QMenu::item:selected {
            background-color: #f0f0f0;
            color: #6200EE;
        }
    """)
    
    # 添加风林火山选项
    has_valid_prompt = False
    for i, prompt_data in enumerate(prompts):
        if isinstance(prompt_data, dict):
            name = prompt_data.get("name", f"提示词 {i+1}")
            content = prompt_data.get("content", "")
        else:
            name = f"提示词 {i+1}"
            content = str(prompt_data)
            
        action_text = f"⚡ {name}"
        action = QAction(action_text, menu)
        
        if content:
            action.setToolTip(content[:100])
            # 直接连接到确认执行函数
            action.triggered.connect(lambda checked, n=name, c=content: confirm_and_run_batch(node, n, c))
            has_valid_prompt = True
        else:
            action.setText(f"{name} (空)")
            action.setEnabled(False)
            
        menu.addAction(action)
        
    if not has_valid_prompt:
        no_prompt_action = QAction("没有可用的提示词，请先在右键菜单中设置", menu)
        no_prompt_action.setEnabled(False)
        menu.addAction(no_prompt_action)

    # 在鼠标位置显示菜单
    menu.exec(QCursor.pos())

def confirm_and_run_batch(node, prompt_name, prompt_content):
    """确认并执行批量生成"""
    reply = QMessageBox.question(
        QApplication.activeWindow(),
        "二创员工确认",
        f"即将使用【{prompt_name}】对所有图片列进行生成。\n\n"
        f"提示词预览: {prompt_content[:100]}...\n\n"
        "这将覆盖现有的图片生成任务，确定继续吗？",
        QMessageBox.Yes | QMessageBox.No
    )
    
    if reply == QMessageBox.Yes:
        run_batch_generation(node, prompt_content)

def run_batch_generation(node, prompt):
    """执行批量生成"""
    table = node.table
    row_count = table.rowCount()
    col_count = table.columnCount()
    
    # 收集需要生成的任务
    tasks = []
    
    # 获取API配置 (参考 lingdonggooglejuben.py)
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
        QMessageBox.warning(None, "配置缺失", f"找不到API配置文件: {config_file}\n请在主界面设置中配置API。")
        return

    # 动态查找 "开始帧" 和 "结束帧" 列
    target_cols = []
    for c in range(col_count):
        header_item = table.horizontalHeaderItem(c)
        if header_item:
            header_text = header_item.text().strip()
            if header_text in ["开始帧", "结束帧"]:
                target_cols.append(c)
    
    # 如果没找到，尝试默认的 6, 7 (兼容旧逻辑)
    if not target_cols:
         if col_count > 7:
             target_cols = [6, 7]
    
    for row in range(row_count):
        for col in target_cols:
            if col < col_count:
                # 获取原图路径作为参考 (如果存在)
                source_image_path = None
                item = table.item(row, col)
                if item:
                    # 检查是否有自定义提示词 (UserRole + 1)
                    # 如果有自定义提示词，则跳过二创员工
                    custom_prompt = item.data(Qt.UserRole + 1)
                    if custom_prompt and str(custom_prompt).strip():
                        print(f"[二创员工] 跳过行 {row} 列 {col}: 存在自定义提示词")
                        continue

                    # 尝试获取UserRole路径
                    user_role_path = item.data(Qt.UserRole)
                    if user_role_path and isinstance(user_role_path, str) and os.path.exists(user_role_path):
                        source_image_path = user_role_path
                    else:
                        text_path = item.text().strip()
                        if text_path:
                            if os.path.exists(text_path):
                                source_image_path = text_path
                            elif hasattr(table, 'script_dir') and table.script_dir:
                                try_path = os.path.join(table.script_dir, text_path)
                                if os.path.exists(try_path):
                                    source_image_path = try_path
                
                # 添加到任务列表: [row, col, prompt, source_image_path]
                # 注意：Worker 期望的格式通常是 [..., prompt, source_path]
                # 这里我们需要适配 node.on_magic_generation_completed 的回调逻辑
                # 回调使用 index 来反推 row。但这里我们是批量，可能无法简单用 index-1 = row
                # 因为一行可能有2个任务 (开始帧/结束帧)
                
                # 重新查看 lingdonggooglejuben.py 的回调逻辑:
                # row_idx = index - 1
                # item = self.table.item(row_idx, col) 
                # 它的回调逻辑似乎假设一次只生成一个，或者顺序对应。
                # 如果我们一次性提交所有任务，我们需要确保回调能正确找到对应的单元格。
                
                # 让我们看看 lingdonggooglejuben.py 的 trigger_magic_generation
                # 它创建 worker 时传入 data_rows = [[row, col, prompt, source_image_path]]
                # 它的回调 on_magic_generation_completed(index, image_path, prompt)
                # 里面用 row_idx = index - 1
                # 并且取出了 row, col = self.magic_worker.data_rows[row_idx][0], self.magic_worker.data_rows[row_idx][1]
                
                # 所以只要我们构造的 data_rows 包含 [row, col, prompt, source_image_path]
                # 并且复用 node 的回调逻辑，应该就没问题。
                
                tasks.append([row, col, prompt, source_image_path])
                
                # 更新UI状态
                if item:
                    item.setText("⏳ 等待生成...")

    if not tasks:
        QMessageBox.information(None, "提示", "没有找到需要生成的列 (列索引 6, 7)。")
        return

    print(f"[二创员工] 准备生成 {len(tasks)} 个任务")
    
    # 停止旧的 worker (如果存在)
    if hasattr(node, 'magic_worker') and node.magic_worker:
        if node.magic_worker.isRunning():
            node.magic_worker.terminate()
            node.magic_worker.wait()
    
    # 创建并启动新的 Worker
    # 注意：PeopleImageGenerationWorker 接受 data_rows
    from lingdonggooglejuben import PeopleImageGenerationWorker
    node.magic_worker = PeopleImageGenerationWorker(image_api, config_file, tasks)
    node.magic_worker.output_dir = "image_node_gen"
    
    # 连接信号
    # 我们直接连接到 node 的回调，因为 node 的回调已经处理了从 data_rows 获取 row/col 的逻辑
    node.magic_worker.image_completed.connect(node.on_magic_generation_completed)
    node.magic_worker.finished.connect(node.on_magic_worker_finished)
    
    node.magic_worker.start()
    
    # 更新状态栏
    try:
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, 'set_connection_text'):
                widget.set_connection_text(f"二创员工启动: {len(tasks)} 个任务", 'loading')
                break
    except Exception as e:
        print(f"Update connection status error: {e}")
