from silicon_flow_agent import SiliconFlowAgent
import os

# 初始化Agent
api_key = "sk-crlcljozljzynhgqxpyxzonhhcmfroaczisaaaztkkmdgcwz"
agent = SiliconFlowAgent(api_key)

# 示例1: 直接使用prompt接口
def example_direct_prompt():
    print("=== 示例1: 直接使用prompt接口 ===")
    prompt = "请解释什么是映射消歧（Mapping Disambiguation）"
    result = agent.generate_completion(prompt)
    print(f"Prompt: {prompt}")
    print(f"结果: {result}")
    print()

# 示例2: 读取文件夹中的JSON文件
def example_read_json_files():
    print("=== 示例2: 读取文件夹中的JSON文件 ===")
    # 请替换为您的JSON文件所在文件夹路径
    json_folder = "../data"  # 假设JSON文件在上级目录的data文件夹中
    try:
        json_data = agent.read_json_files(json_folder)
        print(f"成功读取到 {len(json_data)} 个JSON文件")
        for filename in json_data:
            print(f"- {filename}")
            # 打印每个文件的前100个字符作为预览
            preview = str(json_data[filename])[:100] + "..." if len(str(json_data[filename])) > 100 else str(json_data[filename])
            print(f"  预览: {preview}")
    except Exception as e:
        print(f"读取JSON文件失败: {e}")
    print()

# 示例3: 结合上下文文件生成完成
def example_with_context():
    print("=== 示例3: 结合上下文文件生成完成 ===")
    # 请替换为您的JSON文件所在文件夹路径
    json_folder = "../data"
    try:
        json_data = agent.read_json_files(json_folder)
        if json_data:
            prompt = "请基于提供的上下文信息，总结映射消歧的主要方法和挑战"
            result = agent.generate_completion_with_context(prompt, json_data)
            print(f"Prompt: {prompt}")
            print(f"结果: {result}")
        else:
            print("没有找到JSON文件，无法生成带上下文的结果")
    except Exception as e:
        print(f"生成带上下文的结果失败: {e}")
    print()

# 示例4: 从txt文件读取prompt

def example_prompt_from_file():
    print("=== 示例4: 从txt文件读取prompt ===")
    # 创建示例prompt文件
    prompt_content = "请详细解释映射消歧（Mapping Disambiguation）的概念、应用场景和主要方法"
    prompt_file = "example_prompt.txt"
    
    try:
        # 写入示例prompt到文件
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(prompt_content)
        print(f"已创建示例prompt文件: {prompt_file}")
        print(f"prompt内容: {prompt_content}")
        
        # 从文件读取prompt并生成结果
        result = agent.generate_completion(prompt_file)
        print(f"从文件读取prompt生成的结果: {result}")
        
        # 清理示例文件
        os.remove(prompt_file)
        print(f"已清理示例prompt文件: {prompt_file}")
    except Exception as e:
        print(f"从文件读取prompt失败: {e}")
        # 尝试清理文件
        if os.path.exists(prompt_file):
            os.remove(prompt_file)
    print()

# 运行所有示例
if __name__ == "__main__":
    example_direct_prompt()
    example_read_json_files()
    example_with_context()
    example_prompt_from_file()
