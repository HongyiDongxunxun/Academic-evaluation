import requests
import json
import os
import re

class SiliconFlowAgent:
    def __init__(self, api_key, base_url="https://api.siliconflow.cn/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def generate_completion(self, prompt, model="Qwen/Qwen2.5-72B-Instruct", temperature=0.7, max_tokens=1024):
        """
        调用硅基流动API生成文本完成
        
        Args:
            prompt: 提示词字符串或txt文件路径
            model: 使用的模型，默认Qwen2.5-72B-Instruct
            temperature: 生成温度，范围0-1
            max_tokens: 最大生成 tokens 数
            
        Returns:
            生成的文本
        """
        # 检查是否为文件路径，如果是则读取文件内容
        if isinstance(prompt, str) and os.path.isfile(prompt) and prompt.endswith(".txt"):
            prompt_content = self.read_prompt_from_file(prompt)
            if prompt_content is None:
                raise ValueError(f"无法读取提示词文件: {prompt}")
        else:
            prompt_content = prompt
        
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt_content}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    
    def read_json_files(self, folder_path):
        """
        读取文件夹中的所有JSON文件
        
        Args:
            folder_path: 文件夹路径
            
        Returns:
            字典，键为文件名，值为JSON内容
        """
        json_data = {}
        
        for filename in os.listdir(folder_path):
            if filename.endswith(".json"):
                file_path = os.path.join(folder_path, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        json_data[filename] = data
                except Exception as e:
                    print(f"读取文件 {filename} 时出错: {e}")
        
        return json_data
    
    def read_prompt_from_file(self, file_path):
        """
        从txt文件中读取提示词
        
        Args:
            file_path: txt文件路径
            
        Returns:
            文件中的提示词内容
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            print(f"读取提示词文件 {file_path} 时出错: {e}")
            return None
    
    def generate_completion_with_context(self, prompt, context_files, model="Qwen/Qwen2.5-72B-Instruct", temperature=0.7, max_tokens=1024):
        """
        结合上下文文件生成文本完成
        
        Args:
            prompt: 提示词字符串或txt文件路径
            context_files: 上下文文件内容（从read_json_files获取）
            model: 使用的模型
            temperature: 生成温度
            max_tokens: 最大生成 tokens 数
            
        Returns:
            生成的文本
        """
        # 检查是否为文件路径，如果是则读取文件内容
        if isinstance(prompt, str) and os.path.isfile(prompt) and prompt.endswith(".txt"):
            prompt_content = self.read_prompt_from_file(prompt)
            if prompt_content is None:
                raise ValueError(f"无法读取提示词文件: {prompt}")
        else:
            prompt_content = prompt
        
        # 构建带上下文的提示词
        context_str = "上下文信息：\n"
        for filename, data in context_files.items():
            context_str += f"\n--- 文件: {filename} ---\n"
            context_str += json.dumps(data, ensure_ascii=False, indent=2)
        
        full_prompt = f"{context_str}\n\n{prompt_content}"
        return self.generate_completion(full_prompt, model, temperature, max_tokens)
    
    def check_citation_format(self, content):
        """
        检查内容中是否存在引文格式问题
        
        Args:
            content: 要检查的内容
            
        Returns:
            bool: 如果存在问题返回True，否则返回False
        """
        # 正则表达式匹配引文格式问题，如"[1"、"[]"、"[\s*]"等
        citation_pattern = re.compile(r'\[\s*\d*\s*[^\]]*$|\[\s*\]|\[[^\]]*\s*\d+\s*[^\]]*$')
        content_str = str(content)
        matches = citation_pattern.findall(content_str)
        return len(matches) > 0
    
    def process_citation_check(self, input_folder, output_folder, task_prompt_file=None):
        """
        根据task_prompt_file的提示，检查input_folder中的JSON文件，将存在引文格式问题的文件移动到output_folder
        
        Args:
            input_folder: 输入文件夹路径
            output_folder: 输出文件夹路径
            task_prompt_file: 任务提示词文件路径
            
        Returns:
            int: 发现的问题文件数量
        """
        # 如果提供了任务提示词文件，读取并显示
        if task_prompt_file and os.path.isfile(task_prompt_file):
            task_prompt = self.read_prompt_from_file(task_prompt_file)
            print(f"任务提示：{task_prompt}")
        
        # 获取所有json文件
        json_files = [f for f in os.listdir(input_folder) if f.endswith('.json')]
        total_files = len(json_files)
        error_files = 0
        
        print(f"开始检查 {total_files} 个JSON文件...")
        
        for filename in json_files:
            input_file_path = os.path.join(input_folder, filename)
            output_file_path = os.path.join(output_folder, filename)
            
            try:
                with open(input_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 检查文件内容是否存在引文格式问题
                if self.check_citation_format(data):
                    # 移动文件
                    os.rename(input_file_path, output_file_path)
                    error_files += 1
                    print(f"已移动有问题的文件: {filename}")
            except Exception as e:
                print(f"处理文件 {filename} 时出错: {e}")
                # 如果文件无法正常读取，也视为有问题并移动
                try:
                    os.rename(input_file_path, output_file_path)
                    error_files += 1
                    print(f"已移动无法读取的文件: {filename}")
                except:
                    pass
        
        print(f"检查完成！共检查 {total_files} 个文件，发现 {error_files} 个文件存在引文格式问题，已移动到 {output_folder}")
        return error_files

# 示例用法
if __name__ == "__main__":
    # 硅基流动API密钥
    api_key = "sk-crlcljozljzynhgqxpyxzonhhcmfroaczisaaaztkkmdgcwz"
    
    agent = SiliconFlowAgent(api_key)
    
    # 示例1: 直接使用prompt接口
    print("示例1: 直接使用prompt接口")
    result1 = agent.generate_completion("请解释什么是人工智能")
    print(result1)
    print("\n" + "="*50 + "\n")
    
    # 示例2: 从txt文件读取prompt
    print("示例2: 从txt文件读取prompt")
    # 创建示例prompt文件
    prompt_file = "example_prompt.txt"
    prompt_content = "请解释什么是映射消歧（Mapping Disambiguation）"
    
    try:
        # 写入示例prompt
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(prompt_content)
        
        print(f"已创建示例prompt文件: {prompt_file}")
        print(f"prompt内容: {prompt_content}")
        
        # 从文件读取prompt并生成结果
        result2 = agent.generate_completion(prompt_file)
        print(f"从文件读取prompt生成的结果: {result2}")
        
        # 清理示例文件
        os.remove(prompt_file)
        print(f"已清理示例prompt文件: {prompt_file}")
    except Exception as e:
        print(f"从文件读取prompt失败: {e}")
        # 尝试清理文件
        if os.path.exists(prompt_file):
            os.remove(prompt_file)
    print("\n" + "="*50 + "\n")
    
    # 示例3: 使用task1.txt作为提示词执行引文检查任务
    print("示例3: 使用task1.txt作为提示词执行引文检查任务")
    task_prompt_file = "task1.txt"
    input_folder = "../json_data"
    output_folder = "../error_data"
    
    # 执行引文检查并移动有问题的文件
    error_count = agent.process_citation_check(input_folder, output_folder, task_prompt_file)
    print(f"\n引文检查完成，共发现 {error_count} 个有问题的文件")
    print("\n" + "="*50 + "\n")
