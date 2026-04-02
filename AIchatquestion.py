import re

class NodeDataExtractor:
    """Helper class to extract data from different node types."""
    
    @staticmethod
    def extract_data(node):
        """
        Extracts data from a given node based on its type.
        Returns a formatted string description of the node's content.
        """
        node_title = getattr(node, 'node_title', 'Unknown Node')
        
        # Handle Google Script Node
        if "谷歌剧本" in node_title:
            return NodeDataExtractor._extract_google_script(node)
        
        # Handle Director Node
        elif "导演节点" in node_title:
            return NodeDataExtractor._extract_director_node(node)
            
        # Handle Video Node (fallback or specific)
        elif "视频" in node_title:
            return NodeDataExtractor._extract_video_node(node)
            
        # Default fallback
        return f"Node: {node_title} (No specific data extraction implemented)"

    @staticmethod
    def _extract_google_script(node):
        """Extracts data from GoogleScriptNode table."""
        if not hasattr(node, 'table'):
            return f"Node: {getattr(node, 'node_title', 'Google Script')} (No table found)"
            
        table = node.table
        rows = table.rowCount()
        cols = table.columnCount()
        
        data_str = [f"\n--- Data from {getattr(node, 'node_title', 'Google Script')} ---"]
        
        # Get headers
        headers = []
        for c in range(cols):
            item = table.horizontalHeaderItem(c)
            headers.append(item.text() if item else f"Col {c}")
        data_str.append(" | ".join(headers))
        
        # Get rows
        for r in range(rows):
            row_data = []
            for c in range(cols):
                item = table.item(r, c)
                text = item.text() if item else ""
                row_data.append(text)
            data_str.append(" | ".join(row_data))
            
        return "\n".join(data_str)

    @staticmethod
    def _extract_director_node(node):
        """Extracts data from DirectorNode (video paths, prompts, etc)."""
        if hasattr(node, 'table'):
            table = node.table
            rows = table.rowCount()
            cols = table.columnCount()
            
            data_str = [f"\n--- Data from {getattr(node, 'node_title', 'Director Node')} ---"]
            
             # Get headers
            headers = []
            for c in range(cols):
                item = table.horizontalHeaderItem(c)
                headers.append(item.text() if item else f"Col {c}")
            data_str.append(" | ".join(headers))

            for r in range(rows):
                row_data = []
                for c in range(cols):
                    item = table.item(r, c)
                    # Check for cell widget (video)
                    widget = table.cellWidget(r, c)
                    if widget:
                        if hasattr(widget, 'video_paths'): # GridVideoWidget
                             row_data.append(f"[Videos: {len(widget.video_paths)}]")
                        elif hasattr(widget, 'video_path'):
                             row_data.append(f"[Video: {widget.video_path}]")
                        else:
                             row_data.append("[Widget]")
                    else:
                        text = item.text() if item else ""
                        row_data.append(text)
                data_str.append(" | ".join(row_data))
            return "\n".join(data_str)
            
        return f"Node: {getattr(node, 'node_title', 'Director Node')} (Complex structure, summary only)"

    @staticmethod
    def _extract_video_node(node):
        """Extracts data from VideoNode."""
        info = [f"\n--- Data from {getattr(node, 'node_title', 'Video Node')} ---"]
        if hasattr(node, 'video_path') and node.video_path:
            info.append(f"Video Path: {node.video_path}")
        return "\n".join(info)

def process_user_message(text, scene):
    """
    Scans text for @NodeName patterns, finds corresponding nodes in the scene,
    extracts their data, and appends it to the text.
    
    Args:
        text (str): User input text.
        scene (QGraphicsScene): The scene containing nodes.
        
    Returns:
        str: Enhanced text with node data.
    """
    if not scene:
        return text
        
    # Regex to find @... (assuming node titles don't contain spaces for simplicity, 
    # or we capture until a space/punctuation. But user said "@导演节点#1" which might have spaces if not careful,
    # but usually # indicates ID. Let's try to capture reasonable characters)
    # The user example: "@导演节点" or "@剧本节点#1".
    # We will look for @ followed by non-whitespace characters.
    mentions = re.findall(r'@(\S+)', text)
    
    if not mentions:
        return text
        
    context_data = []
    
    # Iterate over all items in scene to find matches
    # This is O(N*M) but N (nodes) and M (mentions) are small.
    scene_items = scene.items()
    
    for mention in mentions:
        found = False
        for item in scene_items:
            # We look for nodes with node_title
            if hasattr(item, 'node_title'):
                title = item.node_title
                # Check for exact match or close match? 
                # User said "@导演节点#2", if title is "导演节点#2", it matches.
                # If user types "@导演节点", and there are multiple? 
                # We will assume exact string match for now as per user instruction examples.
                if title == mention:
                    data = NodeDataExtractor.extract_data(item)
                    context_data.append(data)
                    found = True
                    break # Stop searching for this mention once found
        
        if not found:
            # Optional: Warning if node not found? Or just ignore.
            # print(f"Warning: Node '@{mention}' not found in scene.")
            pass

    if context_data:
        # Append context to the text
        text += "\n\n" + "\n".join(context_data)
        
    return text
