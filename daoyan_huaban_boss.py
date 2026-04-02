from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QFrame, QToolButton, QGridLayout, QWidget, QLineEdit, QMenu, QMessageBox, QHBoxLayout, QStyle
from PySide6.QtGui import QIcon, QPixmap, QAction
from PySide6.QtCore import Qt, QSize
from photo import PhotoPage
import os

class CompatiblePromptEdit(QLineEdit):
    """
    兼容 PhotoPage 接口的单行输入框，解决在 Dialog 中 QTextEdit 无法输入英文的问题。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)

    def toPlainText(self):
        return self.text()

    def setText(self, text):
        super().setText(text)
        
    def setPlainText(self, text):
        """兼容 QTextEdit 的 setPlainText 接口"""
        self.setText(text)
        
    def focusInEvent(self, event):
        super().focusInEvent(event)
        # 强行捕获键盘输入，防止被父窗口或全局快捷键抢占（解决英文输入被拦截问题）
        self.grabKeyboard()

    def focusOutEvent(self, event):
        # 失去焦点时释放键盘
        self.releaseKeyboard()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        """强制接收按键事件"""
        # 如果是 ESC，释放键盘并允许事件传播（以便关闭窗口）
        if event.key() == Qt.Key_Escape:
            self.releaseKeyboard()
            event.ignore()
            return
            
        super().keyPressEvent(event)

class DirectorArtboardDialog(QDialog):
    """
    导演节点专用画板对话框
    """
    def __init__(self, parent=None, image_path=None, prompt=None, on_return_callback=None):
        super().__init__(parent)
        self.setWindowTitle("快捷画师")
        self.resize(1400, 900)
        self.on_return_callback = on_return_callback
        # 设置为窗口模式，支持最小化/最大化/关闭
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        
        # 设置图标
        if os.path.exists("logo.ico"):
            from PySide6.QtGui import QIcon
            self.setWindowIcon(QIcon("logo.ico"))
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.photo_page = PhotoPage(self)
        layout.addWidget(self.photo_page)
        
        # 底部状态栏
        self.status_bar = QFrame()
        self.status_bar.setFixedHeight(30)
        self.status_bar.setStyleSheet("background: #f0f0f0; border-top: 1px solid #dcdcdc;")
        sb_layout = QHBoxLayout(self.status_bar)
        sb_layout.setContentsMargins(10, 0, 10, 0)
        
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #666; font-size: 12px;")
        sb_layout.addWidget(self.status_label)
        
        layout.addWidget(self.status_bar)
        
        # --- 针对用户反馈的界面优化 ---
        
        # 0. 替换提示词输入框为 QLineEdit (解决英文输入问题)
        self._replace_prompt_edit()
        
        # 1. 修改左上角“工具栏”标题为“快捷画师”
        if hasattr(self.photo_page, 'toolbar') and hasattr(self.photo_page.toolbar, 'title'):
            self.photo_page.toolbar.title.setText("快捷画师")
            # 稍微加大字号使其更像标题
            self.photo_page.toolbar.title.setStyleSheet("font-size: 16px; font-weight: bold; color: #333333; margin-bottom: 5px;")
            
        # 2. 优化右上角提示词窗口可见性 (解决“红色区域提示词窗口不见了”的问题)
        # 查找 PhotoPage 中的 PromptPanel
        prompt_panel = self.photo_page.findChild(QFrame, "PromptPanel")
        if prompt_panel:
            # 移除阴影 (阴影有时在某些层级下可能导致渲染不可见)
            prompt_panel.setGraphicsEffect(None)
            
            # 强制设置背景和边框，确保视觉可见
            prompt_panel.setStyleSheet('#PromptPanel{ background:#ffffff; border:1px solid #d1d1d6; border-radius:12px; }')
            
            # 在提示词框上方添加“提示词”标签，明确功能区
            panel_layout = prompt_panel.layout()
            if panel_layout:
                lbl_prompt = QLabel("提示词")
                lbl_prompt.setStyleSheet("color: #666666; font-size: 12px; font-weight: bold;")
                # 插入到最上方 (index 0)
                panel_layout.insertWidget(0, lbl_prompt)

        # -----------------------------
        
        if image_path and os.path.exists(image_path):
            self.load_image(image_path)
            
        if prompt:
            self.set_prompt(prompt)
            
        # 3. 添加快捷链接 (PS, Krita)
        self.inject_quick_links()

        # 接管 RecentList 的右键菜单
        if hasattr(self.photo_page, 'recent_list'):
            try:
                # 尝试断开原有连接
                self.photo_page.recent_list.customContextMenuRequested.disconnect()
            except Exception:
                pass
            # 连接自定义菜单
            self.photo_page.recent_list.customContextMenuRequested.connect(self._custom_recent_menu)

    def set_connection_text(self, text: str, status_type: str = 'loading'):
        """PhotoPage 调用的状态更新接口"""
        if hasattr(self, 'status_label'):
            self.status_label.setText(text)
            # 根据 status_type 改变样式
            if status_type == 'error':
                self.status_label.setStyleSheet("color: red; font-size: 12px;")
            else:
                self.status_label.setStyleSheet("color: #666; font-size: 12px;")

    def _custom_recent_menu(self, pos):
        """自定义生成图右键菜单"""
        if not hasattr(self.photo_page, 'recent_list'):
            return
            
        item = self.photo_page.recent_list.itemAt(pos)
        if not item:
            return
            
        menu = QMenu(self.photo_page.recent_list)
        
        # 1. 返回到分镜图 (新增)
        act_return = None
        if self.on_return_callback:
            # 添加向左箭头图标作为返回标识
            icon = self.style().standardIcon(QStyle.SP_ArrowBack)
            act_return = QAction(icon, "返回到分镜图", self)
            menu.addAction(act_return)
            menu.addSeparator()
            
        # 2. 发送到图片节点 (新增)
        act_send_node = QAction("💣发送到图片节点", self)
        menu.addAction(act_send_node)
        
        # 3. 原有功能 (复刻 PhotoPage._recent_context_menu)
        act_send = QAction(self.photo_page._i18n['send_to_canvas'], self)
        menu.addAction(act_send)
        
        act_ps = QAction(self.photo_page._i18n['send_to_photoshop'], self)
        menu.addAction(act_ps)
        
        act_capcut = QAction(self.photo_page._i18n['send_to_capcut'], self)
        menu.addAction(act_capcut)
        
        act_matting = QAction('抠图', self)
        menu.addAction(act_matting)
        
        act_save = QAction(self.photo_page._i18n.get('save_image', '保存图片'), self)
        menu.addAction(act_save)
        
        # 执行菜单
        action = menu.exec(self.photo_page.recent_list.mapToGlobal(pos))
        
        # 处理动作
        path = item.data(Qt.UserRole)
        if not path:
            return

        if act_return and action == act_return:
            self.on_return_callback(path)
            # QMessageBox.information(self, "提示", "已发送到分镜图")
            
        elif action == act_send_node:
            self.send_to_image_node(path)
            
        elif action == act_send:
            pix = QPixmap(path)
            if not pix.isNull():
                self.photo_page.layers_panel.add_layer_pixmap(pix, self.photo_page._i18n['generated_image'], sync_to_canvas=True)
                try:
                    it = self.photo_page.layers_panel.list.item(self.photo_page.layers_panel.list.count() - 1)
                    if it is not None:
                        self.photo_page.layers_panel.list.setCurrentItem(it)
                except Exception:
                    pass
        elif action == act_ps:
            self.photo_page._send_image_to_app('ps', path)
        elif action == act_capcut:
            self.photo_page._send_to_capcut(path)
        elif action == act_matting:
            self.photo_page._do_matting(path)
        elif action == act_save:
            self.photo_page._save_recent_image(path)

    def inject_quick_links(self):
        """向右侧快捷面板注入快捷链接按钮"""
        # 尝试查找 QuickPanel
        quick_panel = getattr(self.photo_page, 'quick_panel', None)
        if not quick_panel:
            quick_panel = self.photo_page.findChild(QFrame, "QuickPanel")
            
        if not quick_panel:
            return
            
        # --- 修复可见性问题 ---
        # 1. 移除可能导致不可见的阴影
        quick_panel.setGraphicsEffect(None)
        # 2. 强制设置背景 (去除边框线，保留圆角和背景)
        quick_panel.setStyleSheet('#QuickPanel { background: #ffffff; border: none; border-radius: 10px; }')
        # 3. 确保可见
        quick_panel.setVisible(True)
        # ---------------------
        
        # (已移除重复的按钮注入逻辑，因为 PhotoPage 原生 QuickPanel 已包含这些按钮)

    def _replace_prompt_edit(self):
        """替换 PhotoPage 中的 prompt_edit 为 CompatiblePromptEdit"""
        if not hasattr(self.photo_page, 'prompt_edit'):
            return
            
        old_edit = self.photo_page.prompt_edit
        # 获取 prompt_edit 的父控件 (通常是 PromptPanel QFrame)
        parent_widget = old_edit.parentWidget()
        
        if not parent_widget or not parent_widget.layout():
            return
            
        # 递归查找包含 old_edit 的布局
        def find_layout_containing_widget(layout, widget):
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item.widget() == widget:
                    return layout
                elif item.layout():
                    res = find_layout_containing_widget(item.layout(), widget)
                    if res:
                        return res
            return None

        target_layout = find_layout_containing_widget(parent_widget.layout(), old_edit)
        
        if target_layout:
            new_edit = CompatiblePromptEdit()
            # 复制属性
            new_edit.setPlaceholderText(old_edit.placeholderText())
            # 适配样式表：将 QTextEdit 替换为 QLineEdit
            style = old_edit.styleSheet().replace('QTextEdit', 'QLineEdit')
            
            # 确保样式支持输入且可见
            if "color" not in style:
                style += "QLineEdit { color: #333333; }"
            
            # 保持高度一致
            new_edit.setFixedHeight(72) 
            new_edit.setStyleSheet(style)
            
            # 替换控件
            target_layout.replaceWidget(old_edit, new_edit)
            
            # 销毁旧控件
            old_edit.setParent(None)
            old_edit.deleteLater()
            
            # 更新引用
            self.photo_page.prompt_edit = new_edit


    def set_prompt(self, text):
        if hasattr(self.photo_page, 'prompt_edit'):
            self.photo_page.prompt_edit.setText(text)
            
    def load_image(self, path):
        """加载图片到画板"""
        if hasattr(self.photo_page, 'canvas'):
             try:
                 from PySide6.QtGui import QPixmap
                 pix = QPixmap(path)
                 if not pix.isNull():
                     # 使用 HuabanCanvas 的 add_image_layer 方法
                     # 注意：add_image_layer(self, img: QPixmap | str, name: str | None = None)
                     self.photo_page.canvas.add_image_layer(pix, name="导入的图片")
             except Exception as e:
                 print(f"[DirectorArtboard] Failed to load image: {e}")

    def send_to_image_node(self, path):
        """发送图片到图片节点"""
        from PySide6.QtWidgets import QApplication, QMessageBox
        
        # 1. 查找主窗口场景
        scene = None
        main_window = None
        
        # 尝试通过 QApplication 查找 LingDong 主窗口
        for widget in QApplication.topLevelWidgets():
            if widget.__class__.__name__ == "LingDong":
                main_window = widget
                if hasattr(widget, 'scene'):
                    scene = widget.scene
                break
                
        if not scene:
            print("[DirectorArtboard] Cannot find main scene")
            QMessageBox.warning(self, "错误", "无法找到主画布场景")
            return

        # 2. 查找已存在的图片节点
        target_node = None
        CanvasNodeClass = None
        
        # 遍历查找图片节点，同时获取 CanvasNode 类引用
        for item in scene.items():
            # 尝试获取 CanvasNode 基类 (用于创建新节点)
            if CanvasNodeClass is None and hasattr(item, "node_title"):
                # 假设 item 是 CanvasNode 的子类
                # 我们需要找到 CanvasNode 类
                for base in item.__class__.__bases__:
                    if base.__name__ == "CanvasNode":
                        CanvasNodeClass = base
                        break
            
            # 查找目标节点
            if hasattr(item, "node_title") and item.node_title == "图片节点":
                target_node = item
                # 如果找到了，我们可以停止查找，除非我们想找"最新"的或者特定的
                break
        
        # 3. 发送或创建
        if target_node:
            try:
                # 检查是否开启了多图模式
                if hasattr(target_node, 'is_group_mode') and target_node.is_group_mode:
                    if not hasattr(target_node, 'image_paths'):
                        target_node.image_paths = []
                    # 避免重复添加
                    if path not in target_node.image_paths:
                        target_node.image_paths.append(path)
                    
                    # 切换到这张图
                    target_node.current_index = target_node.image_paths.index(path)
                    if hasattr(target_node, 'load_current_image'):
                        target_node.load_current_image()
                    if hasattr(target_node, 'update_group_ui'):
                        target_node.update_group_ui()
                else:
                    # 单图模式，直接替换
                    target_node.load_image(path)
                
                print(f"[DirectorArtboard] Sent image to existing ImageNode: {path}")
                QMessageBox.information(self, "成功", "已发送到图片节点")
            except Exception as e:
                print(f"[DirectorArtboard] Error loading image to node: {e}")
                QMessageBox.warning(self, "错误", f"发送失败: {e}")
                
        else:
            # 创建新节点
            if not CanvasNodeClass:
                # 如果场景中没有任何节点，我们可能无法获取 CanvasNode 类
                # 尝试从 sys.modules 获取
                import sys
                if 'lingdong' in sys.modules:
                    try:
                        CanvasNodeClass = sys.modules['lingdong'].CanvasNode
                    except AttributeError:
                        pass
                
                # 尝试从 __main__ 获取 (如果直接运行 lingdong.py)
                if not CanvasNodeClass and '__main__' in sys.modules:
                    try:
                        if hasattr(sys.modules['__main__'], 'CanvasNode'):
                            CanvasNodeClass = sys.modules['__main__'].CanvasNode
                    except AttributeError:
                        pass
            
            if CanvasNodeClass:
                try:
                    from lingdongpng import ImageNode as ImageNodeFactory
                    ImageNodeClass = ImageNodeFactory.create_image_node(CanvasNodeClass)
                    
                    # 计算位置：在视图中心附近，或者稍微偏移
                    # 获取视图
                    view = None
                    if main_window and hasattr(main_window, 'view'):
                        view = main_window.view
                    elif scene.views():
                        view = scene.views()[0]
                        
                    if view:
                        # 映射视图中心到场景坐标
                        center_pos = view.mapToScene(view.viewport().rect().center())
                        new_x = center_pos.x()
                        new_y = center_pos.y()
                    else:
                        new_x, new_y = 200, 200
                        
                    new_node = ImageNodeClass(new_x, new_y)
                    new_node.load_image(path)
                    scene.addItem(new_node)
                    
                    print(f"[DirectorArtboard] Created new ImageNode with image: {path}")
                    QMessageBox.information(self, "成功", "已创建图片节点并发送图片")
                    
                except Exception as e:
                    print(f"[DirectorArtboard] Error creating new node: {e}")
                    import traceback
                    traceback.print_exc()
                    QMessageBox.warning(self, "错误", f"创建节点失败: {e}")
            else:
                QMessageBox.warning(self, "错误", "无法创建新节点：未找到 CanvasNode 定义")
