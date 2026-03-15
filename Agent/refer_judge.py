import os
import json
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from json_repair import repair_json  # 必须安装: pip install json_repair

# ================= 配置区域 =================
# 填写你的 API Key
API_KEY = "sk-12d3fe740eaa45faa6ee15441da88178" 
BASE_URL = "https://api.deepseek.com"
MODEL_NAME = "deepseek-chat" 

INPUT_FOLDER = "all_json_iter1"
OUTPUT_FOLDER = "refer_judge"       # 修改：输出文件夹改为 refer_judge
FAILED_LOG_FILE = "failed_json.txt"
MAX_WORKERS = 8
# ===========================================

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
print_lock = threading.Lock()

def safe_print(message):
    with print_lock:
        print(message)

def log_failure(filename, reason):
    with print_lock:
        with open(FAILED_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{filename} | 原因: {reason}\n")

def extract_file_number(filename):
    match = re.search(r'full_(\d+)\.json', filename)
    if match:
        return match.group(1)
    return None

def simplify_json_for_prompt(data):
    """
    【修改点】：保留嵌套结构，不合并子键，只对超长文本进行截断，以节省Token。
    """
    simplified = {}
    
    for k, value in data.items():
        if isinstance(value, dict):
            simplified[k] = {}
            for sub_k, sub_v in value.items():
                val_str = str(sub_v)
                # 截断超长文本
                simplified[k][sub_k] = val_str[:800] + ("..." if len(val_str) > 800 else "")
        else:
            val_str = str(value)
            simplified[k] = val_str[:800] + ("..." if len(val_str) > 800 else "")
            
    return simplified

def get_judge_prompt(json_content_str):
    """
    【修改点】：全新设计的 Prompt，专注提取参考文献并保留层级。
    加入 Few-Shot (示例提示)，让模型完全按照你的要求输出。
    """
    return f"""
    Role: 你是一位专业的学术文献数据清洗专家。
    Task: 逐个判断输入的 JSON 键值对，提取出内容为"参考文献"的键，并摒弃所有正文、摘要或噪音。

    **判决逻辑:**
    1. **特征识别**: 检查 Value 的文本。参考文献通常包含：引文序号（如 `[1]`, `[2]`, `(1)`）、作者列表、出版年份、期刊名称、书名等。
    2. **精准过滤**: 忽略普通的正文、引言、结论、作者简介等内容。
    3. **结构保持 (关键)**: 
       - 如果顶层键对应的内容是参考文献，将其值替换为 "References"。
       - 如果内容在嵌套的子键中（如父键下的某个子键），请保留父子键层级关系，并将该子键的值替换为 "References"。
    4. **严格剔除**: **仅输出**被判定为参考文献的键。如果某个键或子键不是参考文献，请完全从输出结果中删掉它。如果整个文档没有参考文献，请输出空字典 {{}}。

    **Input Example:**
    {{
        "key 1": "随着人工智能的发展，深度学习在各个领域...",
        "key 2": "参考文献：",
        "key 3": {{
            "context1": "[1] 张三, 李四. 神经网络研究[J]. 计算机学报, 2020.\\n[2] Wang Y. Deep Learning[M]. Springer, 2019."
        }},
        "key 3": "\\n[3] 王五. 知识图谱构建[J]. 软件学报, 2021."
    }}

    **Output Example:**
    {{
        "key 3": {{
            "context1": "References"
        }},
        "key 3": "References"
    }}

    **Input Data (请处理以下数据):**
    {json_content_str}
    """

def _build_output_path(filename):
    """
    根据输入文件名构建输出文件路径
    
    参数:
        filename: 输入文件名（如 full_123.json）
    
    输出:
        tuple: (file_num, output_path) 或 (None, None) 如果文件名格式不匹配
    """
    file_num = extract_file_number(filename)
    if not file_num:
        return None, None
    output_filename = f"refer_judge_{file_num}.json"
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)
    return file_num, output_path

def _read_and_parse_json_file(file_path):
    """
    读取并解析JSON文件，自动修复损坏的JSON
    
    参数:
        file_path: JSON文件路径
    
    输出:
        tuple: (success: bool, data: dict or None, error_msg: str)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        try:
            data = json.loads(file_content)
        except json.JSONDecodeError:
            data = repair_json(file_content, return_objects=True)
            if not data:
                return False, None, "JSON 损坏且无法修复"
        
        return True, data, ""
    except Exception as e:
        return False, None, str(e)

def _call_llm_judge(json_str):
    """
    调用LLM模型判断JSON内容
    
    参数:
        json_str: JSON格式的字符串
    
    输出:
        tuple: (success: bool, result_json: dict or None, error_msg: str)
    """
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "你是一个只输出JSON格式的助手。不要输出Markdown标记，也不要输出任何解释。"},
                {"role": "user", "content": get_judge_prompt(json_str)}
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            timeout=120
        )
        
        content = response.choices[0].message.content
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        
        try:
            result_json = json.loads(content)
        except:
            result_json = repair_json(content, return_objects=True)
        
        if result_json is None:
            return False, None, "模型返回结果无效"
        
        return True, result_json, ""
    except Exception as e:
        return False, None, str(e)

def _save_result_to_file(result_json, output_path):
    """
    将结果保存到文件
    
    参数:
        result_json: 要保存的JSON数据
        output_path: 输出文件路径
    
    输出:
        tuple: (success: bool, error_msg: str)
    """
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result_json, f, ensure_ascii=False, indent=4)
        return True, ""
    except Exception as e:
        return False, str(e)

def process_single_task(filename):
    input_path = os.path.join(INPUT_FOLDER, filename)
    file_num, output_path = _build_output_path(filename)
    
    if not file_num:
        return False, filename, "文件名格式不匹配"

    try:
        success, data, error_msg = _read_and_parse_json_file(input_path)
        if not success:
            return False, filename, error_msg

        simplified_data = simplify_json_for_prompt(data)
        if not simplified_data:
            return False, filename, "数据为空"

        json_str = json.dumps(simplified_data, ensure_ascii=False, indent=2)

        success, result_json, error_msg = _call_llm_judge(json_str)
        if not success:
            return False, filename, error_msg

        success, error_msg = _save_result_to_file(result_json, output_path)
        if not success:
            return False, filename, error_msg
        
        output_filename = os.path.basename(output_path)
        return True, filename, f"成功 -> {output_filename}"

    except Exception as e:
        return False, filename, str(e)

def main():
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
    
    with open(FAILED_LOG_FILE, 'w', encoding='utf-8') as f:
        f.write(f"=== 失败记录 {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    
    files = [f for f in os.listdir(INPUT_FOLDER) if f.endswith('.json')]
    total = len(files)
    
    print(f"🚀 开始提取参考文献任务，并发数: {MAX_WORKERS}")
    
    success_cnt = 0
    fail_cnt = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_file = {executor.submit(process_single_task, f): f for f in files}
        
        for i, future in enumerate(as_completed(future_to_file), 1):
            fname = future_to_file[future]
            try:
                success, filename, msg = future.result()
                if success:
                    success_cnt += 1
                    safe_print(f"[{i}/{total}] ✅ {msg}")
                else:
                    fail_cnt += 1
                    safe_print(f"[{i}/{total}] ❌ {filename}: {msg}")
                    log_failure(filename, msg)
            except Exception as e:
                fail_cnt += 1
                safe_print(f"[{i}/{total}] ❌ {fname} 线程异常: {e}")
                log_failure(fname, f"线程异常: {e}")

    print(f"\n🎉 任务结束 | 成功: {success_cnt} | 失败: {fail_cnt}")

if __name__ == "__main__":
    main()
