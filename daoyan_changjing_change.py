import os
from PySide6.QtWidgets import QFileDialog


def change_scene_image(director_node, row):
    item_shot = director_node.table.item(row, 0)
    shot_num = item_shot.text().strip() if item_shot and item_shot.text() else str(row + 1)
    file_path, _ = QFileDialog.getOpenFileName(
        director_node.proxy_widget.widget() if hasattr(director_node, "proxy_widget") else None,
        "选择场景图片",
        "",
        "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)",
    )
    if not file_path:
        return
    name = os.path.splitext(os.path.basename(file_path))[0]
    data = [{"path": file_path, "name": name}]
    director_node.set_cell_images(row, 5, data)
    if not hasattr(director_node, "scene_paths") or not isinstance(director_node.scene_paths, dict):
        director_node.scene_paths = {}
    director_node.scene_paths[shot_num] = file_path
    if hasattr(director_node, "save_scene_paths"):
        director_node.save_scene_paths()
    print(f"[导演节点] 更换镜头 {shot_num} 的场景图片: {file_path}")

