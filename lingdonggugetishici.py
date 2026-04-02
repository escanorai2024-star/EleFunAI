
from PySide6.QtWidgets import QTableWidgetItem, QMessageBox

def add_prompt_column(node):
    """
    为谷歌剧本节点添加“提示词”列
    """
    table = node.table
    
    # 检查是否已存在 "提示词" 列
    prompt_col_index = -1
    for c in range(table.columnCount()):
        header_item = table.horizontalHeaderItem(c)
        if header_item and header_item.text() == "提示词":
            prompt_col_index = c
            break
            
    if prompt_col_index != -1:
        # 如果已存在，提示一下或者什么都不做
        # QMessageBox.information(None, "提示", "已存在【提示词】列。")
        return
        
    # 添加新列
    current_col_count = table.columnCount()
    table.insertColumn(current_col_count)
    table.setHorizontalHeaderItem(current_col_count, QTableWidgetItem("提示词"))
    table.setColumnWidth(current_col_count, 200) # 设置宽一点
    
    # 确保所有行都有该列的item
    for r in range(table.rowCount()):
        if not table.item(r, current_col_count):
            item = QTableWidgetItem("")
            table.setItem(r, current_col_count, item)
            
    # 自动滚动到新列
    table.scrollToItem(table.item(0, current_col_count))
