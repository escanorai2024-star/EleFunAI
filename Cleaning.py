
import os
from PySide6.QtWidgets import QGraphicsTextItem, QGraphicsItem
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from lingdongconnect import ConnectableNode, DataType
try:
    from lingdongTXT import TextEditDialog
except ImportError:
    # Fallback if lingdongTXT is not available or TextEditDialog is not exported
    from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout, QLabel
    class TextEditDialog(QDialog):
        def __init__(self, text="", parent=None):
            super().__init__(parent)
            self.edited_text = text
            self.setup_ui()
        
        def setup_ui(self):
            self.setWindowTitle("编辑清理关键词")
            self.setMinimumSize(400, 300)
            layout = QVBoxLayout(self)
            self.text_edit = QTextEdit()
            self.text_edit.setPlainText(self.edited_text)
            layout.addWidget(self.text_edit)
            btn = QPushButton("确定")
            btn.clicked.connect(self.accept)
            layout.addWidget(btn)

# Cleaning Icon (Broom)
SVG_CLEANING_ICON = """<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M19.38 4.64L19.38 4.64C19.5703 4.82827 19.6775 5.08544 19.6775 5.355C19.6775 5.62456 19.5703 5.88173 19.38 6.07L10.9 14.55C10.7117 14.7403 10.4545 14.8475 10.185 14.8475C9.91544 14.8475 9.65827 14.7403 9.47 14.55L9.47 14.55C9.28033 14.3617 9.17316 14.1046 9.17316 13.835C9.17316 13.5654 9.28033 13.3083 9.47 13.12L17.95 4.64C18.1383 4.45033 18.3954 4.34316 18.665 4.34316C18.9346 4.34316 19.1917 4.45033 19.38 4.64ZM4 20H8L16 12L12 8L4 16V20Z" fill="#ffcc00"/>
</svg>"""

class CleaningNode:
    """清理节点工厂类"""
    
    @staticmethod
    def create_node(CanvasNode):
        """动态创建CleaningNode类，继承自CanvasNode"""
        
        class CleaningNodeImpl(ConnectableNode, CanvasNode):
            def __init__(self, x, y):
                CanvasNode.__init__(self, x, y, 200, 120, "清理节点", SVG_CLEANING_ICON)
                ConnectableNode.__init__(self)
                
                self.cleaning_text = ""
                self.backup_data = {}  # Store original text: {id(node): data}
                
                # Sockets
                self.add_input_socket(DataType.ANY, "输入")
                self.add_output_socket(DataType.ANY, "输出(清理)")
                
                # UI - Display the cleaning keywords
                self.content_text = QGraphicsTextItem(self)
                self.content_text.setDefaultTextColor(QColor("#ffcc00"))
                self.content_text.setFont(QFont("Microsoft YaHei", 10))
                self.content_text.setPlainText("双击设置\n清理关键词")
                self.content_text.setPos(15, 50)
                
                # Style adjustment
                self.set_header_color("#ffcc00")
                
                # Load saved text
                self.load_from_file()
                
            def get_file_path(self):
                base_dir = os.path.dirname(os.path.abspath(__file__))
                txt_dir = os.path.join(base_dir, "txt")
                if not os.path.exists(txt_dir):
                    os.makedirs(txt_dir)
                return os.path.join(txt_dir, "qingli.txt")

            def save_to_file(self):
                try:
                    path = self.get_file_path()
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(self.cleaning_text)
                except Exception as e:
                    print(f"Error saving cleaning text: {e}")

            def load_from_file(self):
                try:
                    path = self.get_file_path()
                    if os.path.exists(path):
                        with open(path, "r", encoding="utf-8") as f:
                            self.cleaning_text = f.read().strip()
                        self.update_display()
                except Exception as e:
                    print(f"Error loading cleaning text: {e}")

            def update_display(self):
                """Update the display text based on cleaning_text"""
                display_text = self.cleaning_text
                if len(display_text) > 20:
                    display_text = display_text[:20] + "..."
                if not display_text:
                    display_text = "双击设置\n清理关键词"
                self.content_text.setPlainText(display_text)

            def set_header_color(self, color_hex):
                # Attempt to set header color if supported by CanvasNode
                # This is a best-effort visual enhancement
                pass

            def mouseDoubleClickEvent(self, event):
                """Double click to edit keywords"""
                if event.button() == Qt.MouseButton.LeftButton:
                    # Use existing dialog or simple fallback
                    dialog = TextEditDialog(self.cleaning_text)
                    if dialog.exec():
                        # Restore original text for all currently connected nodes before changing keyword
                        self.restore_connected_nodes()
                        
                        # Update text
                        if hasattr(dialog, 'text_edit'):
                            self.cleaning_text = dialog.text_edit.toPlainText().strip()
                        
                        # Update display
                        if hasattr(self, "update_display"):
                            self.update_display()
                        
                        # Save to file
                        self.save_to_file()
                        
                        # Trigger cleaning immediately
                        self.perform_cleaning()
                        
                super().mouseDoubleClickEvent(event)

            def _capture_node_state(self, node):
                """Capture the current text state of a node"""
                state = {}
                
                # Check for rows (LocationNode or ScriptCharacterNode)
                rows = getattr(node, "rows", None)
                if rows is None:
                    rows = getattr(node, "character_rows", None)
                
                if rows and isinstance(rows, list):
                    state['type'] = 'rows_based' # Unified type
                    state['rows'] = {}
                    for row in rows:
                        row_data = {}
                        if hasattr(row, "name_edit") and hasattr(row.name_edit, "toPlainText"):
                            row_data['name'] = row.name_edit.toPlainText()
                        if hasattr(row, "prompt_edit") and hasattr(row.prompt_edit, "toPlainText"):
                            row_data['prompt'] = row.prompt_edit.toPlainText()
                        state['rows'][id(row)] = row_data
                
                # Check for table (GoogleScriptNode)
                elif hasattr(node, "table") and hasattr(node.table, "rowCount") and hasattr(node.table, "columnCount"):
                    state['type'] = 'table'
                    table_data = []
                    for r in range(node.table.rowCount()):
                        row_data = []
                        for c in range(node.table.columnCount()):
                            item = node.table.item(r, c)
                            row_data.append(item.text() if item else "")
                        table_data.append(row_data)
                    state['data'] = table_data
                    
                else:
                    state['type'] = 'generic'
                    if hasattr(node, "text") and isinstance(node.text, str):
                        state['text'] = node.text
                    elif hasattr(node, "content_text") and isinstance(node.content_text, QGraphicsTextItem):
                        state['content_text'] = node.content_text.toPlainText()
                return state

            def _restore_node_state(self, node):
                """Restore the node state from backup"""
                node_id = id(node)
                if node_id not in self.backup_data:
                    return
                
                state = self.backup_data[node_id]
                
                if state['type'] == 'rows_based' or state['type'] == 'location': # Handle legacy 'location' type too
                    rows = getattr(node, "rows", None)
                    if rows is None:
                        rows = getattr(node, "character_rows", None)
                        
                    if rows and isinstance(rows, list):
                        row_states = state['rows']
                        for row in rows:
                            if id(row) in row_states:
                                data = row_states[id(row)]
                                # Temporarily disable read-only to restore
                                name_ro = False
                                prompt_ro = False
                                
                                if 'name' in data and hasattr(row, "name_edit"):
                                    if hasattr(row.name_edit, "isReadOnly") and row.name_edit.isReadOnly():
                                        name_ro = True
                                        row.name_edit.setReadOnly(False)
                                    row.name_edit.setText(data['name'])
                                    if name_ro:
                                        row.name_edit.setReadOnly(True)
                                        
                                if 'prompt' in data and hasattr(row, "prompt_edit"):
                                    if hasattr(row.prompt_edit, "isReadOnly") and row.prompt_edit.isReadOnly():
                                        prompt_ro = True
                                        row.prompt_edit.setReadOnly(False)
                                    row.prompt_edit.setText(data['prompt'])
                                    if prompt_ro:
                                        row.prompt_edit.setReadOnly(True)
                                        
                elif state['type'] == 'table':
                    if hasattr(node, "table") and hasattr(node.table, "rowCount"):
                        data = state['data']
                        # Restore cell by cell
                        for r, row_data in enumerate(data):
                            if r < node.table.rowCount():
                                for c, text in enumerate(row_data):
                                    if c < node.table.columnCount():
                                        item = node.table.item(r, c)
                                        if item:
                                            item.setText(text)
                                        else:
                                            # Should not happen usually as items are created, but safe to ignore if missing
                                            pass
                                            
                else:
                    # Generic restoration
                    if 'text' in state and hasattr(node, "text"):
                        node.text = state['text']
                        if hasattr(node, "update_content"): node.update_content()
                        if hasattr(node, "content_text") and isinstance(node.content_text, QGraphicsTextItem):
                            node.content_text.setPlainText(state['text'])
                    elif 'content_text' in state and hasattr(node, "content_text"):
                        node.content_text.setPlainText(state['content_text'])
                        if hasattr(node, "text"): node.text = state['content_text']
                
                del self.backup_data[node_id]
            
            def restore_connected_nodes(self):
                """Restore text for all connected nodes"""
                for socket in self.output_sockets:
                    for connection in socket.connections:
                        target_socket = connection.target_socket
                        if target_socket:
                            node = target_socket.parent_node
                            self._restore_node_state(node)

            def on_socket_connected(self, socket, connection):
                """Callback when a socket is connected"""
                # Only care about output socket connections (A -> B)
                if socket in self.output_sockets:
                    target_socket = connection.target_socket
                    if target_socket:
                        target_node = target_socket.parent_node
                        self.clean_node(target_node)

            def on_socket_disconnected(self, socket, connection):
                """Callback when a socket is disconnected"""
                if socket in self.output_sockets:
                    target_socket = connection.target_socket
                    if target_socket:
                        target_node = target_socket.parent_node
                        self._restore_node_state(target_node)
            
            def perform_cleaning(self):
                """Clean all connected nodes"""
                if not self.cleaning_text:
                    return
                
                for socket in self.output_sockets:
                    for connection in socket.connections:
                        target_socket = connection.target_socket
                        if target_socket:
                            target_node = target_socket.parent_node
                            self.clean_node(target_node)
                            
            def clean_node(self, node):
                """Remove keywords from a specific node"""
                if not self.cleaning_text:
                    return
                
                # Backup state before cleaning
                node_id = id(node)
                if node_id not in self.backup_data:
                    self.backup_data[node_id] = self._capture_node_state(node)
                    
                # 1. Special handling for LocationNode (which has rows of widgets)
                if hasattr(node, "rows") and isinstance(node.rows, list):
                    self._clean_rows(node.rows)
                    return

                # 2. Special handling for ScriptCharacterNode (which has character_rows)
                if hasattr(node, "character_rows") and isinstance(node.character_rows, list):
                    self._clean_rows(node.character_rows)
                    return

                # 3. Special handling for GoogleScriptNode (which has table)
                if hasattr(node, "table") and hasattr(node.table, "rowCount") and hasattr(node.table, "columnCount"):
                    self._clean_table(node.table)
                    return

                # 4. Identify where the text is stored
                text_content = ""
                attr_name = None
                is_qgraphics_text = False
                
                # Check common attributes
                if hasattr(node, "text") and isinstance(node.text, str):
                    text_content = node.text
                    attr_name = "text"
                elif hasattr(node, "content_text") and isinstance(node.content_text, QGraphicsTextItem):
                    text_content = node.content_text.toPlainText()
                    attr_name = "content_text"
                    is_qgraphics_text = True
                
                # 5. Perform cleaning
                if text_content and self.cleaning_text in text_content:
                    new_text = text_content.replace(self.cleaning_text, "")
                    
                    # 6. Update node
                    if attr_name == "text":
                        node.text = new_text
                        # If node has update method
                        if hasattr(node, "update_content"):
                            node.update_content()
                        # Sync with UI if exists
                        if hasattr(node, "content_text") and isinstance(node.content_text, QGraphicsTextItem):
                            node.content_text.setPlainText(new_text)
                            
                    elif attr_name == "content_text":
                        node.content_text.setPlainText(new_text)
                        # Sync with internal state if exists
                        if hasattr(node, "text"):
                            node.text = new_text

            def _clean_rows(self, rows):
                """Helper to clean rows (LocationNode or ScriptCharacterNode)"""
                for row in rows:
                    # Clean name_edit
                    if hasattr(row, "name_edit") and hasattr(row.name_edit, "toPlainText"):
                        text = row.name_edit.toPlainText()
                        if self.cleaning_text in text:
                            # Temporarily disable read-only to modify
                            name_ro = False
                            if hasattr(row.name_edit, "isReadOnly") and row.name_edit.isReadOnly():
                                name_ro = True
                                row.name_edit.setReadOnly(False)
                                
                            new_text = text.replace(self.cleaning_text, "")
                            row.name_edit.setText(new_text)
                            
                            if name_ro:
                                row.name_edit.setReadOnly(True)
                            
                    # Clean prompt_edit
                    if hasattr(row, "prompt_edit") and hasattr(row.prompt_edit, "toPlainText"):
                        text = row.prompt_edit.toPlainText()
                        if self.cleaning_text in text:
                            # Temporarily disable read-only to modify
                            prompt_ro = False
                            if hasattr(row.prompt_edit, "isReadOnly") and row.prompt_edit.isReadOnly():
                                prompt_ro = True
                                row.prompt_edit.setReadOnly(False)
                                
                            new_text = text.replace(self.cleaning_text, "")
                            row.prompt_edit.setText(new_text)
                            
                            if prompt_ro:
                                row.prompt_edit.setReadOnly(True)

            def _clean_table(self, table):
                """Helper to clean table (GoogleScriptNode)"""
                for r in range(table.rowCount()):
                    for c in range(table.columnCount()):
                        item = table.item(r, c)
                        if item:
                            text = item.text()
                            if self.cleaning_text in text:
                                new_text = text.replace(self.cleaning_text, "")
                                item.setText(new_text)

        return CleaningNodeImpl
