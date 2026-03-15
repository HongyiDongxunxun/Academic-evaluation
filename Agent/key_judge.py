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
API_KEY = "sk-12d3fe740eaa45faa6ee15441da88178" 
BASE_URL = "https://api.deepseek.com"
MODEL_NAME = "deepseek-chat" 

INPUT_FOLDER = "all_json_iter1"
OUTPUT_FOLDER = "key_judge"
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
    simplified = {}
    keys = list(data.keys())
    keys_to_process = keys[1:] if len(keys) > 0 else []
    
    for k in keys_to_process:
        value = data[k]
        if isinstance(value, dict):
            all_text_content = []
            for sub_k, sub_v in value.items():
                if isinstance(sub_v, str):
                    all_text_content.append(sub_v)
                elif isinstance(sub_v, (int, float)):
                    all_text_content.append(str(sub_v))
            combined_text = " ".join(all_text_content)
            truncated_text = combined_text[:1000] + ("..." if len(combined_text) > 1000 else "")
            simplified[k] = truncated_text
        elif isinstance(value, str):
            simplified[k] = value[:1000]
        else:
            simplified[k] = str(value)[:1000]
    return simplified

def get_judge_prompt(json_content_str):
    """
    【最终逻辑完善版】
    新增核心规则：
    1. 拼接阻断：见到 (上接...)，后面的内容默认为“外来文章”。
    2. 序列连坐：如果 "6" 是 False，那么 "6.1", "6.2" 必须是 False。
    """
    return f"""
    Role: 你是一位专业的学术文献数据清洗专家。
    Task: 判断输入的JSON键(Key)是属于主文章(True)，参考文献(References)，还是噪音(False)。

    **判决逻辑 (请按顺序执行，确保逻辑自洽):**

    **Rule 1: 参考文献强制捕获 (最高优先级)**
    - **特征**：检查 Value (内容)。只要包含引文序号（如 `[1]`, `[7]`, `(1)`）或引文列表格式。
    - **指令**：只要内容像参考文献，无论键名是什么（哪怕是 "·情报理论与实践·"、"Page 1"），**强制判为 "References"**。

    **Rule 2: 拼接阻断与跳跃检测 (Alien Detection - 关键)**
    - **拼接标志**：如果出现 `(上接第XX页)`、`(下转第XX页)` 这样的键或内容。
      -> **指令**：**该标志本身判 "False"，且紧随其后的所有段落（直到遇到参考文献）极大概率是“接”过来的外来文章，统统判 "False"！**
    - **序号跳跃**：如果主文章是 "1", "2"，突然跳到 "6"（中间缺了3,4,5），且主题不连贯。
      -> **指令**：**判 "False"**。

    **Rule 3: 序列连坐原则 (Sequence Consistency)**
    - **原理**：连续的序号通常描述同一个主题。
    - **指令**：
      - 如果父标题（如 "6"）被判定为 **"False"** (因为它是外来拼接文章)，那么它的所有子标题（如 "6.1", "6.2", "6.3"）**必须全部判为 "False"**。
      - 严禁出现 "6" 是 False，但 "6.1" 是 True 的情况。**要杀全杀，要留全留。**

    **Rule 4: 独立新文章检测**
    - 如果出现新的 `[摘要]`, `[关键词]`, `[中图分类号]` 或新作者署名，该键及其后续内容判 "False"。

    **Rule 5: 章节标题保护 (主文章)**
    - 只要键名包含序号（如 "1", "2", "3", "3.1"）且与**主文章**前文逻辑连贯（没有发生 Rule 2 的跳跃），即使内容为空，**绝对判为 "True"**。

    Output JSON Format:
    {{"键名": "判定结果"}}
    
    判定结果选项: "True", "False", "References", "Uncertain"

    Input Data:
    {json_content_str}
    """

def process_single_task(filename):
    input_path = os.path.join(INPUT_FOLDER, filename)
    file_num = extract_file_number(filename)
    
    if not file_num:
        return False, filename, "文件名格式不匹配"

    output_filename = f"key_judge_{file_num}.json"
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)

    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        try:
            data = json.loads(file_content)
        except json.JSONDecodeError:
            data = repair_json(file_content, return_objects=True)
            if not data:
                return False, filename, "JSON 损坏且无法修复"

        simplified_data = simplify_json_for_prompt(data)
        if not simplified_data:
            return False, filename, "数据为空"

        json_str = json.dumps(simplified_data, ensure_ascii=False, indent=2)

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
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        
        try:
            result_json = json.loads(content)
        except:
            result_json = repair_json(content, return_objects=True)

        if not result_json:
            return False, filename, "模型返回结果无效"

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result_json, f, ensure_ascii=False, indent=4)
        
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
    
    print(f"🚀 开始处理 {total} 个文件 (Rule 3: 序列连坐版)，并发数: {MAX_WORKERS}")
    
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