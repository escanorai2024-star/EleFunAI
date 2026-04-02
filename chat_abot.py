from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QAction, QCursor
from PySide6.QtCore import Qt

class ChatNodeContextManager:
    """聊天节点上下文管理器
    
    负责提取画布中的导演节点和谷歌剧本节点数据，
    并提供给工作台作为聊天上下文。
    """
    
    def __init__(self):
        pass

    def get_available_nodes(self, scene):
        """获取场景中所有可用的内容节点（导演节点、谷歌剧本节点）"""
        nodes = []
        if not scene:
            return nodes
            
        for item in scene.items():
            # 检查是否有 node_title 属性
            if not hasattr(item, 'node_title'):
                continue
                
            title = item.node_title
            
            # 识别节点类型
            if "导演" in title or "Director" in title:
                nodes.append({
                    "type": "director",
                    "name": title,
                    "node": item
                })
            elif "谷歌剧本" in title or "Google Script" in title:
                nodes.append({
                    "type": "google_script",
                    "name": title,
                    "node": item
                })
                
        # 按名称排序
        nodes.sort(key=lambda x: x["name"])
        return nodes

    def extract_node_content(self, node):
        """提取节点内容"""
        content = ""
        try:
            # 检查是否有 table 属性 (QTableWidget)
            if hasattr(node, 'table'):
                table = node.table
                rows = table.rowCount()
                cols = table.columnCount()
                
                # 获取表头
                headers = []
                for c in range(cols):
                    header_item = table.horizontalHeaderItem(c)
                    headers.append(header_item.text() if header_item else f"Column {c}")
                
                content += " | ".join(headers) + "\n"
                content += "-" * (len(content) * 2) + "\n"
                
                # 获取行数据
                for r in range(rows):
                    row_data = []
                    for c in range(cols):
                        item = table.item(r, c)
                        text = item.text() if item else ""
                        row_data.append(text)
                    content += " | ".join(row_data) + "\n"
                    
            elif hasattr(node, 'full_text'): # 文本节点
                content = node.full_text
            
            # 附加信息
            node_type = "未知节点"
            if hasattr(node, 'node_title'):
                content = f"【节点名称】: {node.node_title}\n【节点内容】:\n{content}"
                
        except Exception as e:
            content = f"提取数据失败: {str(e)}"
            
        return content

    def create_context_menu(self, workbench, button_pos):
        """创建上下文菜单"""
        # 获取场景
        scene = None
        if hasattr(workbench, 'canvas_view') and workbench.canvas_view:
            scene = workbench.canvas_view.scene
        elif hasattr(workbench, 'main_page') and workbench.main_page and hasattr(workbench.main_page, 'canvas'):
            scene = workbench.main_page.canvas.scene
            
        if not scene:
            return

        nodes = self.get_available_nodes(scene)
        
        menu = QMenu(workbench)
        menu.setStyleSheet("""
            QMenu {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 20px;
                border-radius: 4px;
                color: #333333;
            }
            QMenu::item:selected {
                background-color: #f5f5f5;
                color: #1a73e8;
            }
        """)
        
        if not nodes:
            action = QAction("当前画布无可用剧本节点", menu)
            action.setEnabled(False)
            menu.addAction(action)
        else:
            # 分类显示
            director_nodes = [n for n in nodes if n['type'] == 'director']
            google_nodes = [n for n in nodes if n['type'] == 'google_script']
            
            if director_nodes:
                menu.addSection("🎬 导演节点")
                for n in director_nodes:
                    action = QAction(f"@{n['name']}", menu)
                    action.triggered.connect(lambda checked, node=n['node']: self._on_node_selected(workbench, node))
                    menu.addAction(action)
                    
            if google_nodes:
                if director_nodes:
                    menu.addSeparator()
                menu.addSection("📝 谷歌剧本")
                for n in google_nodes:
                    action = QAction(f"@{n['name']}", menu)
                    action.triggered.connect(lambda checked, node=n['node']: self._on_node_selected(workbench, node))
                    menu.addAction(action)

        menu.exec(button_pos)

    def _on_node_selected(self, workbench, node):
        """当选择了节点"""
        content = self.extract_node_content(node)
        
        # 使用工作台的新方法添加上下文标签
        if hasattr(workbench, 'add_context_tag'):
            workbench.add_context_tag(node.node_title, content)
            print(f"[ChatAbot] 已添加节点上下文标签: {node.node_title}")
        else:
            # 降级处理 (兼容旧代码)
            if not hasattr(workbench, 'current_context_content') or not workbench.current_context_content:
                workbench.current_context_content = content
                workbench.current_context_title = node.node_title
            else:
                workbench.current_context_content += "\n\n" + content
                workbench.current_context_title += f" & {node.node_title}"
            
            if hasattr(workbench, 'text_input'):
                workbench.text_input.setPlaceholderText(f"已引用 {workbench.current_context_title}，请输入您的问题...")

