import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QGraphicsProxyWidget, QLineEdit, QTextEdit, QPlainTextEdit, QTableWidget, QAbstractItemView, QListWidget, QTreeWidget, QSpinBox

def is_input_widget(widget):
    """
    判断一个QWidget是否是输入型控件。
    如果是输入型控件，Delete键通常应该由控件自己处理（删除文本），而不是删除节点。
    """
    if not widget:
        return False
        
    # 1. 文本输入类
    if isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox)):
        return True
        
    # 2. 列表/树/表格类
    # 只有当它们处于编辑状态，或者用户真的在操作内部条目时，才视为输入
    # 但为了安全起见，通常如果焦点在这些复杂的控件里，我们倾向于不删除节点，除非用户显式选中了节点本身
    if isinstance(widget, (QTableWidget, QListWidget, QTreeWidget)):
        # 检查是否处于编辑状态
        if widget.state() != QAbstractItemView.NoState:
            return True
        # 如果有当前选中的单元格/行，Delete通常意味着清空内容或删除行，而不是删除整个节点
        if widget.selectedItems() or widget.selectedIndexes():
            return True
            
    return False

def handle_delete(view, event):
    """
    处理删除按键事件。
    
    参数:
        view: InfiniteCanvasView 实例
        event: QKeyEvent
        
    返回:
        bool: True 表示已处理删除操作，False 表示未处理
    """
    # 1. 检查是否是删除键
    # 用户反馈：Backspace不应删除节点，仅 Delete 键触发删除
    if event.key() != Qt.Key.Key_Delete:
        return False
        
    # Debug信息
    print(f"[Delete] Key Pressed: {event.key()}")
    
    # 2. 获取焦点信息
    focus_item = view.scene.focusItem()
    app_focus_widget = QApplication.focusWidget()
    
    # 确定当前实际拥有焦点的QWidget
    current_widget = app_focus_widget
    
    # 如果焦点在GraphicsProxyWidget上，尝试获取其内部的QWidget
    if focus_item and isinstance(focus_item, QGraphicsProxyWidget):
        if not current_widget:
            current_widget = focus_item.widget()
    
    print(f"[Delete] Focus Widget: {current_widget.__class__.__name__ if current_widget else 'None'}")
    
    # 3. 判断是否应该拦截删除
    # 如果焦点在输入控件中，且该控件正在工作，我们不应该删除节点
    if is_input_widget(current_widget):
        print("[Delete] Ignored: Widget is capturing input.")
        return False
        
    # 4. 获取选中的图形项
    selected_items = view.scene.selectedItems()
    
    # 特殊情况处理：如果selectedItems为空，但焦点在某个节点的子部件上（且不是输入状态）
    # 我们可能希望删除该父节点（这是一个激进的策略，视用户需求而定）
    # 这里暂时保持保守：必须显式选中节点
    
    if not selected_items:
        print("[Delete] Ignored: No items selected.")
        return False
        
    print(f"[Delete] Processing deletion for {len(selected_items)} items...")
    
    # 5. 执行删除逻辑
    # 记录撤销操作
    deleted_items_record = []
    items_to_remove = []
    
    # 预处理：区分连接线和节点
    # 注意：为了解耦，我们通过鸭子类型或类名字符串来判断
    
    # 先收集要删除的连接线
    for item in selected_items:
        item_type = item.__class__.__name__
        
        # 判断是否是连接线
        if item_type == "Connection" or hasattr(item, "source_socket"):
            # 记录连接线信息
            deleted_items_record.append({
                'type': 'connection',
                'connection': item,
                'source_socket': getattr(item, 'source_socket', None),
                'target_socket': getattr(item, 'target_socket', None)
            })
            items_to_remove.append(item)
            
    # 再收集要删除的节点（及其关联的连接线）
    for item in selected_items:
        if item in items_to_remove:
            continue
            
        # 判断是否是节点 (CanvasNode及其子类)
        # 通常节点会有 sockets 列表或者 input_sockets/output_sockets
        if hasattr(item, "input_sockets") or hasattr(item, "output_sockets") or hasattr(item, "node_title"):
            # 这是一个节点
            
            # 1. 收集该节点关联的所有连接线
            node_connections = []
            sockets = []
            if hasattr(item, "input_sockets"): sockets.extend(item.input_sockets)
            if hasattr(item, "output_sockets"): sockets.extend(item.output_sockets)
            
            for socket in sockets:
                # socket.connections 可能是列表
                if hasattr(socket, "connections"):
                    for conn in socket.connections[:]: # 复制列表
                        # 记录关联连接线
                        node_connections.append({
                            'source_socket': getattr(conn, 'source_socket', None),
                            'target_socket': getattr(conn, 'target_socket', None)
                        })
                        # 确保连接线也被移除
                        if conn not in items_to_remove:
                            items_to_remove.append(conn)
            
            # 2. 记录节点信息
            deleted_items_record.append({
                'type': 'node',
                'node': item,
                'position': item.pos(),
                'connections': node_connections
            })
            items_to_remove.append(item)
    
    # 6. 实际执行移除
    if not items_to_remove:
        return False
        
    # 使用 view.connection_manager 移除连接线
    # 使用 view.scene 移除节点
    
    conn_mgr = getattr(view, "connection_manager", None)
    
    for item in items_to_remove:
        item_type = item.__class__.__name__
        
        if item_type == "Connection" or hasattr(item, "source_socket"):
            if conn_mgr:
                conn_mgr.remove_connection(item)
            else:
                # Fallback if no manager
                view.scene.removeItem(item)
        else:
            view.scene.removeItem(item)
            
    print(f"[Delete] Successfully removed {len(items_to_remove)} items.")
    
    # 7. 保存到撤销栈
    if hasattr(view, "save_undo_operation") and deleted_items_record:
        view.save_undo_operation('delete', deleted_items_record)
        
    return True
