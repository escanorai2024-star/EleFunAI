
class FastGenerationHandler:
    """快速生成处理器"""
    def __init__(self, node):
        self.node = node
        self.is_active = False

    def start(self):
        """开始快速生成流程"""
        if self.is_active:
            print("[快速生成] 流程已在进行中")
            return
            
        print("[快速生成] 开始流程: 第1步 - 生成人物提示词")
        self.is_active = True
        
        # 1. 触发生成提示词
        if hasattr(self.node, 'generate_prompts'):
            # 这里的 generate_prompts 是节点的方法
            self.node.generate_prompts()
            
            # 检查是否立即失败（通过检查按钮状态）
            # 如果按钮可用，说明 generate_prompts 内部检测失败（如无数据）并重置了状态
            if hasattr(self.node, 'btn_gen_prompts') and self.node.btn_gen_prompts.isEnabled():
                print("[快速生成] 检测到提示词生成未启动（可能是数据为空），流程结束")
                self.is_active = False
        else:
            print("[快速生成] 错误: 节点没有 generate_prompts 方法")
            self.is_active = False

    def on_prompts_finished(self):
        """提示词生成完成回调"""
        if not self.is_active:
            return
            
        print("[快速生成] 第1步完成，进入第2步 - 生成图片")
        
        # 2. 触发生成图片
        if hasattr(self.node, 'generate_images'):
            # 使用 QTimer.singleShot 稍微延时，确保UI刷新和数据更新完成
            from PySide6.QtCore import QTimer
            QTimer.singleShot(500, self._trigger_image_generation)
        else:
            print("[快速生成] 错误: 节点没有 generate_images 方法")
            self.is_active = False

    def _trigger_image_generation(self):
        """实际触发图片生成"""
        if self.node:
            print("[快速生成] 执行生成图片...")
            self.node.generate_images()
        self.is_active = False

    def on_prompts_error(self):
        """提示词生成错误回调"""
        if self.is_active:
            print("[快速生成] 流程中断: 提示词生成失败")
            self.is_active = False
