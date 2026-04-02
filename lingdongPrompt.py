"""
灵动智能体 - 绘画提示词生成模块
支持为分镜脚本的每个镜头生成中英文绘图提示词

功能：
1. 在备注列后方添加"绘画提示词（CN）"和"绘画提示词（EN）"两列
2. 绘画提示词（CN）：综合分镜脚本所有列的信息，生成完整的中文AI绘画提示词（60-100字）
3. 绘画提示词（EN）：将中文提示词翻译成英文，转换为Midjourney/SD格式
4. 英文提示词是中文提示词的翻译版本，内容完全一致
5. 分批处理，避免API超时（每批5行，180秒超时）

绘画提示词生成规则：
- 综合利用：景别、画面内容、人物、人物关系/构图、地点/环境、运镜、音效/台词、备注等所有信息
- 中文提示词：描述完整画面，包括主体、场景、光线、氛围、视角、风格、质量等
- 英文提示词：使用AI绘画专业术语（cinematic, photorealistic, detailed, 8K等）
- 格式规范：英文用逗号分隔关键词，符合Midjourney/Stable Diffusion标准
"""

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication
import requests
import json
import re


class BatchPromptWorker(QThread):
    """分批提示词生成工作线程 - 避免API超时"""
    batch_completed = Signal(int, list)  # 批次号, 提示词数据
    all_completed = Signal(list)  # 所有提示词数据
    error_occurred = Signal(str)
    progress_updated = Signal(int, int)  # 当前进度, 总数
    
    def __init__(self, provider, api_url, api_key, model, system_prompt, 
                 table_data, headers, batch_size):
        super().__init__()
        self.provider = provider
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.table_data = table_data
        self.headers = headers
        self.batch_size = batch_size
        self.all_prompts = []

        # Register to global registry to prevent GC
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_prompt_workers'):
                app._active_prompt_workers = []
            app._active_prompt_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        app = QApplication.instance()
        if app and hasattr(app, '_active_prompt_workers'):
            if self in app._active_prompt_workers:
                app._active_prompt_workers.remove(self)
    
    def run(self):
        try:
            total_rows = len(self.table_data)
            batches = (total_rows + self.batch_size - 1) // self.batch_size
            
            print(f"[提示词生成] 总计 {total_rows} 行，分 {batches} 批处理")
            
            for batch_idx in range(batches):
                start_idx = batch_idx * self.batch_size
                end_idx = min(start_idx + self.batch_size, total_rows)
                
                print(f"[提示词生成] 处理第 {batch_idx + 1}/{batches} 批 (行 {start_idx + 1}-{end_idx})")
                
                # 构建当前批次的数据 - 优化格式，让AI更好理解
                batch_text = "分镜脚本数据：\n\n"
                
                # 显示表头结构
                headers_display = [h for h in self.headers if h != "镜号"]  # 去除镜号列
                batch_text += f"表头结构：{' | '.join(headers_display)}\n\n"
                
                # 为每一行构建详细描述
                for idx in range(start_idx, end_idx):
                    row = self.table_data[idx]
                    batch_text += f"【镜头 {idx + 1}】\n"
                    
                    # 逐列展示数据（跳过镜号，只显示实际数据列）
                    for col_idx, (header, cell_value) in enumerate(zip(headers_display, row)):
                        if str(cell_value).strip():  # 只显示非空数据
                            batch_text += f"  - {header}: {cell_value}\n"
                    
                    batch_text += "\n"
                
                user_message = f"""{batch_text}

请根据以上分镜脚本，为每个镜头生成绘画提示词：
1. 综合所有列的信息（景别、画面内容、人物、地点、运镜等）
2. 生成完整的中文绘画提示词（60-100字）
3. 严格按照JSON格式输出"""
                
                # 发送API请求
                headers_dict = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {self.api_key}'
                }
                
                payload = {
                    'model': self.model,
                    'messages': [
                        {'role': 'system', 'content': self.system_prompt},
                        {'role': 'user', 'content': user_message}
                    ],
                    'stream': False,
                    'temperature': 0.7
                }
                
                response = requests.post(
                    self.api_url,
                    headers=headers_dict,
                    json=payload,
                    timeout=180  # 180秒超时
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result['choices'][0]['message']['content']
                    
                    # 解析JSON
                    json_match = re.search(r'\[[\s\S]*\]', content)
                    if json_match:
                        json_str = json_match.group(0)
                        batch_prompts = json.loads(json_str)
                        self.all_prompts.extend(batch_prompts)
                        
                        print(f"[提示词生成] 第 {batch_idx + 1} 批完成，获得 {len(batch_prompts)} 条提示词")
                        self.batch_completed.emit(batch_idx + 1, batch_prompts)
                        self.progress_updated.emit(end_idx, total_rows)
                    else:
                        raise Exception(f"批次 {batch_idx + 1} 响应格式错误")
                else:
                    raise Exception(f"API错误 {response.status_code}: {response.text}")
            
            # 所有批次完成
            print(f"[提示词生成] 全部完成，共 {len(self.all_prompts)} 条提示词")
            self.all_completed.emit(self.all_prompts)
        
        except Exception as e:
            error_msg = f"生成失败: {str(e)}"
            print(f"[提示词生成] {error_msg}")
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(error_msg)


class DrawingPromptGenerator:
    """绘画提示词生成器"""
    
    # 系统提示词模板
    SYSTEM_PROMPT = """你是专业的AI绘画提示词专家。根据分镜脚本的所有内容，为每个镜头生成绘画提示词。

核心要求：
1. **绘画提示词（CN）**：综合分镜脚本中的所有列（景别、画面内容、人物、人物关系/构图、地点/环境、运镜、音效/台词、备注等），生成一个完整的中文绘画提示词
   - 长度：60-100字
   - 内容：描述完整的画面构成，包括主体、场景、光线、氛围、视角、风格等
   - 风格：适合AI绘画工具（如Midjourney、Stable Diffusion）使用
   - 示例："日出时分的城市街道，阳光洒在地面，一位年轻女性骑着自行车穿过街道，中景构图，暖色调，电影感光线，细节丰富，8K高清"

2. **JSON格式输出**：严格按照以下格式输出，确保可以被解析
3. **每行一个镜头**：row字段对应镜头编号

输出格式（必须严格遵守）：
[
  {
    "row": 1,
    "chinese_prompt": "中文绘画提示词（60-100字，描述完整画面）"
  },
  {
    "row": 2,
    "chinese_prompt": "..."
  }
]

重要提示：
- 要综合利用分镜脚本的所有信息（不只是"画面内容"列）
- 提示词要具体、详细、适合AI绘画工具理解"""
    
    def __init__(self, config_file='api_config.json'):
        """初始化生成器
        
        Args:
            config_file: API配置文件路径
        """
        self.config_file = config_file
        self.worker = None
    
    def load_api_config(self, provider):
        """加载API配置
        
        Args:
            provider: 提供商名称（如 "Hunyuan"）
            
        Returns:
            tuple: (api_url, api_key)
            
        Raises:
            Exception: 配置加载失败
        """
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                api_config = json.load(f)
            
            api_key_name = f'{provider.lower()}_api_key'
            api_key = api_config.get(api_key_name, '')
            
            if not api_key:
                raise Exception(f"{provider} 的API Key未配置")
            
            # 获取API URL
            if provider == "Hunyuan":
                base_url = api_config.get('hunyuan_api_url', 'https://api.vectorengine.ai')
                api_url = f"{base_url.rstrip('/')}/v1/chat/completions"
            else:
                base_url = api_config.get('api_url', 'https://api.vectorengine.ai/v1')
                if base_url.rstrip('/').endswith('/v1'):
                    api_url = f"{base_url.rstrip('/')}/chat/completions"
                else:
                    api_url = f"{base_url.rstrip('/')}/v1/chat/completions"
            
            return api_url, api_key
        
        except Exception as e:
            raise Exception(f"API配置错误: {str(e)}")
    
    def generate_prompts(self, provider, model, table_data, headers, 
                        batch_size=5, callbacks=None):
        """生成绘画提示词
        
        Args:
            provider: AI提供商
            model: 模型名称
            table_data: 表格数据（二维列表）
            headers: 表头列表
            batch_size: 每批处理的行数
            callbacks: 回调函数字典，包含：
                - on_batch_completed: 单批完成回调
                - on_progress: 进度更新回调
                - on_completed: 全部完成回调
                - on_error: 错误回调
        
        Returns:
            BatchPromptWorker: 工作线程对象
        """
        # 加载API配置
        api_url, api_key = self.load_api_config(provider)
        
        print(f"[生成提示词] 使用模型: {provider} / {model}")
        print(f"[生成提示词] API URL: {api_url}")
        
        # 创建工作线程
        self.worker = BatchPromptWorker(
            provider, api_url, api_key, model, 
            self.SYSTEM_PROMPT,
            table_data, headers, batch_size
        )
        
        # 连接回调函数
        if callbacks:
            if 'on_batch_completed' in callbacks:
                self.worker.batch_completed.connect(callbacks['on_batch_completed'])
            if 'on_progress' in callbacks:
                self.worker.progress_updated.connect(callbacks['on_progress'])
            if 'on_completed' in callbacks:
                self.worker.all_completed.connect(callbacks['on_completed'])
            if 'on_error' in callbacks:
                self.worker.error_occurred.connect(callbacks['on_error'])
        
        # 启动线程
        self.worker.start()
        
        return self.worker
    
    @staticmethod
    def update_table_with_prompts(node, all_prompts):
        """将生成的提示词更新到表格节点
        
        Args:
            node: 分镜脚本节点对象
            all_prompts: 所有提示词列表
            
        Returns:
            int: 成功添加的提示词数量
        """
        if not hasattr(node, 'headers') or not hasattr(node, 'table_data'):
            raise Exception("节点结构异常，无法添加提示词列")
        
        # 获取当前状态（必须获取副本，因为属性getter返回的是新列表，但为了安全起见明确操作）
        current_headers = node.headers
        current_widths = node.column_widths
        current_data = node.table_data
        
        print(f"[生成提示词] 更新前 - 表头数: {len(current_headers)}, 列宽数: {len(current_widths)}")
        
        # 确定插入位置：在"备注"之后，或者"开始帧"之前
        # 默认追加到最后
        target_idx = len(current_headers)
        
        # 如果有"开始帧"，插入到它前面（通常是倒数第二列）
        if "开始帧" in current_headers:
            target_idx = current_headers.index("开始帧")
        # 否则如果有"备注"，插入到它后面
        elif "备注" in current_headers:
            target_idx = current_headers.index("备注") + 1
            
        print(f"[生成提示词] 插入位置: 第 {target_idx} 列")
        
        # 1. 更新表头
        new_headers = list(current_headers)
        new_headers.insert(target_idx, "绘画提示词（CN）")
        
        # 2. 更新列宽
        new_widths = list(current_widths)
        # 确保宽度列表长度足够
        if len(new_widths) < len(current_headers):
            new_widths.extend([100] * (len(current_headers) - len(new_widths)))
            
        new_widths.insert(target_idx, 250)  # CN列宽
        
        # 3. 更新数据
        new_data = []
        for row in current_data:
            new_row = list(row)
            # 插入空数据占位
            new_row.insert(target_idx, "")
            new_data.append(new_row)
            
        # 4. 填充生成的提示词
        success_count = 0
        for prompt_item in all_prompts:
            row_idx = prompt_item.get('row', 0) - 1  # 转换为0索引
            if 0 <= row_idx < len(new_data):
                chinese_prompt = prompt_item.get('chinese_prompt', '')
                
                # 填充数据
                new_data[row_idx][target_idx] = chinese_prompt
                
                success_count += 1
                
                if row_idx < 3:  # 只打印前3行的详细信息
                    print(f"[生成提示词] 第{row_idx+1}行: 填充提示词")

        print(f"[生成提示词] 更新后 - 表头数: {len(new_headers)}, 列宽数: {len(new_widths)}")
        
        # 5. 应用更改到节点
        # 注意顺序：先设置表头（更新列数），再设置数据，最后设置列宽
        node.headers = new_headers
        node.table_data = new_data
        node.column_widths = new_widths
        
        # 重新计算表格大小
        total_width = sum(new_widths) + 2
        row_count = len(new_data)
        
        # 使用 getattr 获取属性，提供默认值以兼容旧节点
        title_h = getattr(node, 'title_height', 40)
        header_h = getattr(node, 'header_height', 40)
        cell_h = getattr(node, 'cell_height', 60)
        
        total_height = title_h + header_h + (row_count * cell_h) + 2
        
        print(f"[生成提示词] 设置表格大小: 宽度={total_width}, 高度={total_height}")
        node.setRect(0, 0, total_width, total_height)
        
        # 设置标记，避免 create_table() 重新计算列宽
        node._skip_column_width_recalc = True
        
        # 刷新表格显示（重新创建所有UI元素）
        print(f"[生成提示词] 开始刷新表格...")
        node.create_table()
        
        # 清除标记
        node._skip_column_width_recalc = False
        print(f"[生成提示词] 刷新完成！")
        
        print(f"[生成提示词] 表格最终状态：{len(node.headers)}列 x {len(node.table_data)}行")
        
        return success_count
    
    @staticmethod
    def check_prompts_exist(node):
        """检查表格是否已经包含提示词列
        
        Args:
            node: 分镜脚本节点对象
            
        Returns:
            bool: True表示已存在提示词列
        """
        if not hasattr(node, 'headers'):
            return False
        
        headers = node.headers
        return "绘画提示词（CN）" in headers
