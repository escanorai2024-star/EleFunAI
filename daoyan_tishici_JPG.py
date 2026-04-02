import os
from PySide6.QtWidgets import QPushButton, QTableWidgetItem, QHeaderView
from PySide6.QtCore import Qt

def create_expand_button(director_node):
    """
    创建一个按钮用于展开/隐藏图片提示词列
    """
    btn = QPushButton("🖼️ 展开图片提示词", director_node.container)
    btn.setFixedSize(120, 24)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet("""
        QPushButton {
            background-color: #795548;
            color: white;
            border-radius: 4px;
            font-weight: bold;
            border: none;
            font-family: "Microsoft YaHei";
        }
        QPushButton:hover {
            background-color: #8D6E63;
        }
        QPushButton:pressed {
            background-color: #5D4037;
        }
    """)
    btn.clicked.connect(lambda: toggle_image_prompt_column(director_node))
    return btn

def toggle_image_prompt_column(director_node):
    """
    切换图片提示词列的显示/隐藏状态
    """
    # 图片提示词列是第7列 (索引从0开始)
    COLUMN_INDEX = 7
    
    # 检查当前列数，如果不足则增加
    if director_node.table.columnCount() <= COLUMN_INDEX:
        director_node.table.setColumnCount(COLUMN_INDEX + 1)
        
        # 更新表头
        current_headers = []
        for i in range(director_node.table.columnCount()):
            item = director_node.table.horizontalHeaderItem(i)
            if item:
                current_headers.append(item.text())
            else:
                current_headers.append("")
        
        if len(current_headers) > COLUMN_INDEX:
            current_headers[COLUMN_INDEX] = "🎨 图片提示词"
        else:
            current_headers.append("🎨 图片提示词")
            
        director_node.table.setHorizontalHeaderLabels(current_headers)
        director_node.table.setColumnWidth(COLUMN_INDEX, 250) # 设置较宽的宽度

    is_hidden = director_node.table.isColumnHidden(COLUMN_INDEX)
    director_node.table.setColumnHidden(COLUMN_INDEX, not is_hidden)
    
    # 更新按钮文字
    if hasattr(director_node, 'expand_prompt_btn'):
        if is_hidden: # 变为显示
            director_node.expand_prompt_btn.setText("🖼️ 收起图片提示词")
        else:
            director_node.expand_prompt_btn.setText("🖼️ 展开图片提示词")

    # 如果显示了列
    if is_hidden: # 之前是隐藏的，现在显示了
        # 移动列到动画片场(Index 2)右侧
        header = director_node.table.horizontalHeader()
        
        # 获取动画片场列的当前视觉位置
        anim_studio_visual_index = header.visualIndex(2)
        
        # 目标位置是动画片场列的下一个位置
        target_visual = anim_studio_visual_index + 1
        
        current_visual = header.visualIndex(COLUMN_INDEX)
        
        # 只有当不在目标位置时才移动
        if current_visual != target_visual:
            header.moveSection(current_visual, target_visual)

        print("[DirectorNode] Image Prompt column shown, refreshing data...")
        if hasattr(director_node, 'update_data'):
            director_node.update_data()
            
    # 保存设置
    if hasattr(director_node, 'save_view_settings'):
        director_node.save_view_settings()

def update_image_prompt_column(director_node, row_index, row_data):
    """
    更新指定行的图片提示词列
    """
    COLUMN_INDEX = 7
    
    # 如果列不存在，且没有被请求显示，我们暂时不添加数据以节省资源?
    # 不，为了保证数据就绪，如果有这一列（即使隐藏），我们也应该填入数据，
    # 这样用户展开时数据已经在那里了。
    
    if director_node.table.columnCount() <= COLUMN_INDEX:
        return

    prompt = ""
    if isinstance(row_data, dict):
        # 尝试多种可能的键名
        keys = ["绘画提示词（CN）", "绘画提示词(CN)", "Painting Prompt (CN)", "Painting Prompt", "绘画提示词", "提示词", "Prompt"]
        for key in keys:
            if key in row_data:
                val = row_data[key]
                if val:
                    prompt = str(val)
                break
    
    # Check for manual edits override
    if hasattr(director_node, 'manual_image_prompts'):
        shot_num = ""
        if isinstance(row_data, dict):
             shot_num = str(row_data.get("镜号", row_data.get(0, "")))
        
        # If empty, try table
        if not shot_num:
             item_shot = director_node.table.item(row_index, 0)
             if item_shot:
                 shot_num = item_shot.text()

        if shot_num and shot_num in director_node.manual_image_prompts:
            prompt = director_node.manual_image_prompts[shot_num]

    item = director_node.table.item(row_index, COLUMN_INDEX)
    if not item:
        item = QTableWidgetItem(prompt)
        item.setToolTip("双击编辑")
        director_node.table.setItem(row_index, COLUMN_INDEX, item)
    else:
        # 只有当内容不同时才更新，避免重绘闪烁
        if item.text() != prompt:
            item.setText(prompt)
            item.setToolTip("双击编辑")
