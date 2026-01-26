from silicon_flow_agent import SiliconFlowAgent
import os

# 初始化Agent
api_key = "sk-crlcljozljzynhgqxpyxzonhhcmfroaczisaaaztkkmdgcwz"
agent = SiliconFlowAgent(api_key)

# 配置任务参数
task_prompt_file = "task1.txt"  # 提示词文件
input_folder = "../json_data"    # 输入JSON文件文件夹
output_folder = "../error_data"  # 输出错误文件文件夹

# 检查必要文件和文件夹
if not os.path.exists(task_prompt_file):
    print(f"错误：提示词文件 {task_prompt_file} 不存在")
    exit(1)

if not os.path.exists(input_folder):
    print(f"错误：输入文件夹 {input_folder} 不存在")
    exit(1)

if not os.path.exists(output_folder):
    print(f"警告：输出文件夹 {output_folder} 不存在，将创建")
    os.makedirs(output_folder)

# 执行引文检查任务
print("="*60)
print("开始执行引文格式检查任务")
print(f"提示词文件: {task_prompt_file}")
print(f"输入文件夹: {input_folder}")
print(f"输出文件夹: {output_folder}")
print("="*60)

# 读取并显示提示词内容
with open(task_prompt_file, "r", encoding="utf-8") as f:
    prompt_content = f.read()
print("\n提示词内容：")
print(prompt_content)
print("\n" + "="*60)

# 执行检查并移动文件
error_count = agent.process_citation_check(input_folder, output_folder, task_prompt_file)

print("\n" + "="*60)
print(f"任务执行完成！共发现 {error_count} 个文件存在引文格式问题")
print("="*60)
