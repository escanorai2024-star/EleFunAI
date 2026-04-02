import os
import json
import requests
import traceback
import re
from PySide6.QtCore import QThread, Signal

class OptimizationWorker(QThread):
    # Signals
    optimization_completed = Signal(dict) # {shot_number (str): content (str)}
    task_failed = Signal(str)
    log_signal = Signal(str)

    def __init__(self, script_content, parent=None, grid_count=6, time_optimization_enabled=False):
        super().__init__(parent)
        self.script_content = script_content
        self.grid_count = grid_count
        self.time_optimization_enabled = time_optimization_enabled
        self.running = True

    def run(self):
        print("DEBUG: [OptimizationWorker] run() started") # DEBUG
        try:
            self.log_signal.emit("=== 剧本优化任务开始 ===")
            if self.time_optimization_enabled:
                self.log_signal.emit("已启用剧本时间优化 (生成时间码)")
            
            # Load Config
            print("DEBUG: [OptimizationWorker] Loading API config...") # DEBUG
            api_config = self.load_api_config()
            if not api_config:
                print("DEBUG: [OptimizationWorker] API config load failed") # DEBUG
                self.task_failed.emit("无法加载API配置 (JSON/talk_api_config.json)")
                return
            
            # Determine Provider/Model
            provider, model = self.get_model_selection()
            self.log_signal.emit(f"使用模型: {provider} - {model}")
            print(f"DEBUG: [OptimizationWorker] Model: {provider}, {model}") # DEBUG

            # Construct Prompt
            prompt = self.construct_prompt()
            print(f"DEBUG: [OptimizationWorker] Prompt constructed (Length: {len(prompt)})") # DEBUG
            self.log_signal.emit(f"--- 提示词 Debug Start ---\n{prompt}\n--- 提示词 Debug End ---")
            
            # Call API
            print("DEBUG: [OptimizationWorker] Calling API...") # DEBUG
            response_text = self.call_api(api_config, provider, model, prompt)
            
            if response_text:
                print("DEBUG: [OptimizationWorker] API response received") # DEBUG
                self.log_signal.emit("API响应成功，正在解析...")
                # Parse Response
                parsed_data = self.parse_response(response_text)
                if parsed_data:
                    print(f"DEBUG: [OptimizationWorker] Parsed {len(parsed_data)} shots") # DEBUG
                    self.optimization_completed.emit(parsed_data)
                    self.log_signal.emit(f"✅ 优化完成，共提取 {len(parsed_data)} 个镜头的数据")
                else:
                    print("DEBUG: [OptimizationWorker] Parse failed") # DEBUG
                    self.log_signal.emit(f"API返回内容:\n{response_text}")
                    self.task_failed.emit("无法解析API返回的数据，请检查格式")
            else:
                print("DEBUG: [OptimizationWorker] No response text") # DEBUG
                self.task_failed.emit("API请求失败或无返回")

        except Exception as e:
            print(f"DEBUG: [OptimizationWorker] Exception in run: {e}") # DEBUG
            self.log_signal.emit(f"❌ 运行出错: {e}")
            self.task_failed.emit(str(e))
            traceback.print_exc()

    def load_api_config(self):
        try:
            path = os.path.join(os.getcwd(), 'JSON', 'talk_api_config.json')
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading api config: {e}")
        return None

    def get_model_selection(self):
        # Default
        provider = "Gemini 2.0" 
        model = "gemini-2.0-flash-exp"
        
        try:
            path = os.path.join(os.getcwd(), 'JSON', 'chat_mode_config.json')
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    provider = data.get('last_provider', provider)
                    model = data.get('last_model', model)
        except:
            pass
        return provider, model

    def construct_prompt(self):
        grid_lines = ""
        
        if self.time_optimization_enabled:
            # 时间优化模式
            for i in range(1, self.grid_count + 1):
                if i == 1:
                    grid_lines += f"Grid 1(0:00-0:01): 黑色状态\n"
                elif i == 2:
                    grid_lines += f"Grid 2(0:01-0:02): ...\n"
                elif i == self.grid_count:
                     grid_lines += f"Grid {i}(...-总时长): ...\n"
                else:
                    grid_lines += f"Grid {i}(...-...): ...\n"
        else:
            # 原始模式
            for i in range(1, self.grid_count + 1):
                if i == 1:
                    grid_lines += f"Grid 1: 黑色状态\n"
                else:
                    grid_lines += f"Grid {i}: ...\n"

        prompt = f"""
你是一个专业的动画分镜师。
以下是剧本内容：
{self.script_content}

任务要求：
1. 分析每个镜头的动画内容和图片提示词。
2. 为每个镜头生成{self.grid_count}个关键帧（Grid 1 到 Grid {self.grid_count}）的详细描述。
"""

        if self.time_optimization_enabled:
            prompt += f"""
3. Grid 1 必须始终是“黑色状态”（Black Screen），并且时间码固定为 (0:00-0:01)。
4. 所有的Grid必须包含时间码，格式为 Grid X(分:秒-分:秒): ...。
   每个镜头的标题后面标有了 [TotalSeconds: X]，代表该镜头的总时长(秒)。
   (如果未标注，请默认总时长为 5 秒)

   请严格按照以下规则分配时间：
   - Grid 1: 占用第1秒 (0:00-0:01)。
   - 剩余时间 = TotalSeconds - 1。
   - 将剩余时间合理分配给剩下的 {self.grid_count - 1} 个 Grid (Grid 2 到 Grid {self.grid_count})。
   - 最后一个 Grid 的结束时间必须等于 TotalSeconds。
   
   例如：[TotalSeconds: 5]
   - Grid 1: 0:00-0:01
   - Grid 2: 0:01-0:02
   - Grid 3: 0:02-0:03
   - ...
   - Grid {self.grid_count}: ...-0:05

   注意：禁止生成 'Dialogue:' 这样的前缀，直接描述画面和说话动作即可。
"""
        else:
            prompt += """
3. Grid 1 必须始终是“黑色状态”（Black Screen）。
"""

        prompt += f"""
4. 如果某个镜头包含台词，请在最合适的一个Grid（通常是该镜头的最后一个Grid）中包含台词动作和内容。
   格式必须是：Grid X{'...' if not self.time_optimization_enabled else '(时间码)'}: [画面描述]，[人物]嘴巴张开大喊（或说话）：“[台词内容]”。
   例如：Grid 6{'...' if not self.time_optimization_enabled else '(0:05-0:08)'}: 近景，角色摆出战斗姿态，剑指前方，嘴巴张开大喊：“战斗结束了！”。
   (注意：禁止生成 'Dialogue:' 这样的前缀，直接描述画面和说话动作即可)
5. 严格按照以下格式返回结果，不要包含多余的废话：

[镜头1]
{grid_lines}

[镜头2]
...

请确保每个镜头的描述清晰、具体，有助于后续生成视频。
请为每一个镜头都生成描述。
"""
        return prompt

    def call_api(self, config, provider, model, prompt):
        api_key = ""
        api_url = config.get('api_url', '')
        
        # Map provider to key
        if "Gemini" in provider:
             api_key = config.get('gemini 2.5_api_key')
        elif "ChatGPT" in provider:
             api_key = config.get('chatgpt_api_key')
        elif "DeepSeek" in provider:
             api_key = config.get('deepseek_api_key')
        elif "Claude" in provider:
             api_key = config.get('claude_api_key')
        elif "Hunyuan" in provider:
             api_key = config.get('hunyuan_api_key')
             api_url = config.get('hunyuan_api_url')
        
        if not api_key:
             # Fallback to any available key if specific one missing
             keys = [v for k, v in config.items() if 'api_key' in k and v]
             if keys:
                 api_key = keys[0]
                 self.log_signal.emit(f"未找到 {provider} 的API Key，使用可用 Key")

        if not api_key:
             self.log_signal.emit("❌ 未配置有效的 API Key")
             return None

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        # Adjust URL for OpenAI compatible endpoints
        if not api_url.endswith('/v1/chat/completions'):
            if not api_url.endswith('/v1'):
                 # Ensure no double slash if api_url ends with /
                 api_url = api_url.rstrip('/') + "/v1"
            api_url = f"{api_url}/chat/completions"

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 8000
        }
        
        try:
            self.log_signal.emit(f"正在发送请求到 {api_url}...")
            # Debug info
            debug_info = {
                "url": api_url,
                "model": model,
                "max_tokens": payload.get("max_tokens"),
                "temperature": payload.get("temperature")
            }
            self.log_signal.emit(f"请求参数 Debug: {json.dumps(debug_info, indent=2)}")
            
            response = requests.post(api_url, headers=headers, json=payload, timeout=180)
            if response.status_code == 200:
                result = response.json()
                # Debug response
                self.log_signal.emit(f"API响应 Debug: Status 200")
                
                if 'choices' in result and len(result['choices']) > 0:
                     content = result['choices'][0]['message']['content']
                     self.log_signal.emit(f"--- 响应内容 Debug Start ---\n{content}\n--- 响应内容 Debug End ---")
                     return content
                else:
                     self.log_signal.emit(f"❌ API返回格式异常: {result}")
                     return None
            else:
                self.log_signal.emit(f"❌ API请求失败: {response.status_code} {response.text}")
                return None
        except Exception as e:
            self.log_signal.emit(f"❌ 请求异常: {e}")
            return None

    def parse_response(self, text):
        data = {}
        # Regex to find blocks starting with [镜头X] or [Shot X]
        # Supports [镜头 1], [镜头1], [Shot 1], etc.
        pattern = re.compile(r'\[(?:镜头|Shot)\s*(\d+)\](.*?)(?=\[(?:镜头|Shot)|$)', re.DOTALL | re.IGNORECASE)
        matches = pattern.findall(text)
        
        for shot_num, content in matches:
            # Clean content
            clean_content = content.strip()
            # Store by shot number (normalized to string)
            data[shot_num] = clean_content
            
        return data
