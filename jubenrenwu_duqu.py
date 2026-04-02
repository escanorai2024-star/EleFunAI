from PySide6.QtWidgets import QApplication, QMessageBox
from database_save import AssetLibraryStore, LibraryPanel, AssetThumbnail
from jubenrenwu_duqu_xuanze import ImageSelectionDialog
import os

def read_from_library(character_row):
    """
    从资料库读取同名人物图片。
    逻辑：
    1. 如果资料库面板中有【选中】且【同名】的图片，直接使用（最高优先级）。
    2. 如果没有选中项，则搜索资料库中所有同名图片：
       - 0个：提示未找到。
       - 1个：直接使用。
       - 多个：弹出选择窗口。
    """
    name = character_row.name_edit.toPlainText().strip()
    if not name:
        QMessageBox.warning(character_row, "提示", "请先填写人物名称")
        return

    # 1. 尝试查找资料库面板中选中的同名项 (Fast Path)
    found_path = None
    app = QApplication.instance()
    for widget in app.topLevelWidgets():
        panels = widget.findChildren(LibraryPanel)
        if isinstance(widget, LibraryPanel):
            panels.append(widget)
        
        for panel in panels:
            thumbnails = panel.findChildren(AssetThumbnail)
            for thumb in thumbnails:
                if thumb.is_selected and thumb.asset_name == name:
                    if thumb.image_path and os.path.exists(thumb.image_path):
                        found_path = thumb.image_path
                        print(f"[ReadLibrary] Found selected matching asset: {name}")
                        break
            if found_path: break
        if found_path: break

    if found_path:
        character_row.set_image(found_path)
        return

    # 2. 如果没找到选中的，搜集所有同名候选 (Multipath Fallback)
    print(f"[ReadLibrary] No selected match found, searching database for: {name}")
    store = AssetLibraryStore()
    assets = store.list_assets("people")
    
    candidates = []
    seen_paths = set()
    
    for asset in assets:
        if asset.get("name") == name:
            path = asset.get("path")
            if path and os.path.exists(path) and path not in seen_paths:
                candidates.append(path)
                seen_paths.add(path)
    
    if not candidates:
        QMessageBox.information(character_row, "提示", f"资料库中未找到名为“{name}”的人物图片")
        return
        
    if len(candidates) == 1:
        character_row.set_image(candidates[0])
        print(f"[ReadLibrary] Auto-set single match: {candidates[0]}")
    else:
        # 多个匹配，弹出选择框
        dlg = ImageSelectionDialog(character_row, name, candidates)
        if dlg.exec():
            if dlg.selected_path:
                character_row.set_image(dlg.selected_path)
