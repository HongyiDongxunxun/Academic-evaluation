import os
import json
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from json_repair import repair_json  # 必须安装: pip install json_repair

# ================= 配置区域 =================
# 填写你的硅基流动 API Key
API_KEY = "sk-crlcljozljzynhgqxpyxzonhhcmfroaczisaaaztkkmdgcwz" 
BASE_URL = "https://api.siliconflow.cn/v1"

# 推荐模型
MODEL_NAME = "deepseek-ai/DeepSeek-V3" 

INPUT_FOLDER = "all_json_iter1"
OUTPUT_FOLDER = "key_judge"
FAILED_LOG_FILE = "failed_json.txt"

# 并发线程数 (根据你的账号等级调整，免费版建议 2-5，付费版 10+)
MAX_WORKERS = 5 
# ===========================================

# 初始化客户端
client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# 打印锁
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
    【核心修改】
    将嵌套的 {Key: {context1: "...", context2: "..."}} 
    拍扁为 {Key: "......"}
    这样LLM只评价第二层的键，依据是合并后的内容。
    """
    simplified = {}
    keys = list(data.keys())
    
    # 1. 移除第一个键 (通常是文件名)
    keys_to_process = keys[1:] if len(keys) > 0 else []
    
    for k in keys_to_process:
        value = data[k]
        
        # 如果值是字典（包含 context1, context2...）
        if isinstance(value, dict):
            # 提取该字典下所有的字符串内容，并拼接
            all_text_content = []
            for sub_k, sub_v in value.items():
                if isinstance(sub_v, str):
                    all_text_content.append(sub_v)
                elif isinstance(sub_v, (int, float)):
                    all_text_content.append(str(sub_v))
            
            # 用空格连接所有段落
            combined_text = " ".join(all_text_content)
            
            # 截取前 800 个字符 (足够判断主题，且节省 Token)
            # 稍微增加长度，因为现在合并了多个context
            truncated_text = combined_text[:800] + ("..." if len(combined_text) > 800 else "")
            
            simplified[k] = truncated_text
            
        # 如果值本身就是字符串（极少数情况）
        elif isinstance(value, str):
            simplified[k] = value[:800]
        else:
            simplified[k] = str(value)[:800]
            
    return simplified

def get_judge_prompt(json_content_str):
    return f"""
    Role: 你是一位专业的学术文献数据清洗专家。
    
    Task: 输入的JSON中，"键(Key)"是文献中的小标题或段落头，"值(Value)"是该标题下提取的正文内容摘要。
    请判断这些**键(Key)**所代表的段落是否属于当前主文章，还是混入的无关文章（噪音）。

    Workflow:
    1. 浏览前几个键及其内容，确定主文章的核心主题、学科领域和作者。
    2. 逐个检查每个键：
       - 阅读该键对应的文本内容(Value)。
       - 判断该内容是否与核心主题一致？
       - 如果内容突然变成完全无关的领域（如从历史变体育），或者作者变了，则判为 False。
    3. 输出结果 JSON:
       - 格式: {{"键名": "判定结果"}}
       - 判定结果选项: "True" (属于主文章), "False" (噪音/无关), "Uncertain".
       - **只评价键名，不要输出内容摘要。**

    Input Data:
    {json_content_str}
    """

def process_single_task(filename):
    input_path = os.path.join(INPUT_FOLDER, filename)
    file_num = extract_file_number(filename)
    
    if not file_num:
        return False, filename, "文件名格式不匹配 (非 full_x.json)"

    output_filename = f"key_judge_{file_num}.json"
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)

    # 断点续传：如果文件已存在且不为空，跳过
    # if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
    #    return True, filename, "已存在，跳过"

    try:
        # 1. 读取文件
        with open(input_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        # 2. 解析与修复
        try:
            data = json.loads(file_content)
        except json.JSONDecodeError:
            data = repair_json(file_content, return_objects=True)
            if not data:
                return False, filename, "JSON 损坏严重无法修复"

        # 3. 数据扁平化处理 (Flatten)
        simplified_data = simplify_json_for_prompt(data)
        
        if not simplified_data:
            return False, filename, "有效数据为空"

        json_str = json.dumps(simplified_data, ensure_ascii=False, indent=2)

        # 4. API 调用
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "你是一个只输出JSON的助手。不要输出Markdown标记。"},
                {"role": "user", "content": get_judge_prompt(json_str)}
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            timeout=120
        )

        content = response.choices[0].message.content
        
        # 5. 清洗结果
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        
        try:
            result_json = json.loads(content)
        except:
            result_json = repair_json(content, return_objects=True)

        if not result_json:
            return False, filename, "模型返回结果无效"

        # 6. 保存
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result_json, f, ensure_ascii=False, indent=4)
        
        return True, filename, f"成功 -> {output_filename}"

    except Exception as e:
        return False, filename, str(e)

def main():
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
    
    # 初始化日志
    with open(FAILED_LOG_FILE, 'w', encoding='utf-8') as f:
        f.write(f"=== 失败记录 {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    
    files = [f for f in os.listdir(INPUT_FOLDER) if f.endswith('.json')]
    total = len(files)
    
    print(f"🚀 开始处理 {total} 个文件，并发数: {MAX_WORKERS}")
    
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