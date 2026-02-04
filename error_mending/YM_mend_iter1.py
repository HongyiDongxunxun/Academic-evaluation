import os
import json
import re
from concurrent.futures import ProcessPoolExecutor

# ================== 核心逻辑 ==================

def fix_key_text(key):
    """
    根据规则修复 Year_Mixed 的键名，增加特有名词保护
    """
    # 排除项：这些数字序列绝对不拆分
    EXCLUDE_NUMS = {"911", "985", "211"}
    
    # 提取开头的连续数字部分进行预检查
    num_prefix_match = re.match(r'^(\d+)', key)
    if num_prefix_match:
        full_num = num_prefix_match.group(1)
        if full_num in EXCLUDE_NUMS:
            return key

    # 规则 1: 3位数黏连 (e.g., "250年代" -> "2 50年代")
    # 修正：确保后两位是 50-90 年代，且不在排除名单中
    match_3 = re.match(r'^(\d)(\d{2})(年代.*)', key)
    if match_3:
        prefix, year_part, suffix = match_3.groups()
        if (prefix + year_part) not in EXCLUDE_NUMS:
            return f"{prefix} {year_part}{suffix}"
    
    # 规则 2: 序号 + 4位年份黏连 (e.g., "2911..." -> "2 911..." 或 "31978..." -> "3 1978...")
    # 针对你的问题 "2911" 变成 "2 911":
    # 我们匹配：(1位序号) + (911 或 19xx 或 20xx)
    match_special = re.match(r'^(\d)(911|985|211)(.*)', key)
    if match_special:
        return f"{match_special.group(1)} {match_special.group(2)}{match_special.group(3)}"

    # 规则 3: 小数序号 + 世纪/年份 (保持原样，但限定范围)
    match_dec_century = re.match(r'^(\d+\.\d+)(\d{2}世纪.*)', key)
    if match_dec_century:
        return f"{match_dec_century.group(1)} {match_dec_century.group(2)}"

    match_dec_year = re.match(r'^(\d+\.\d+)((?:19|20)\d{2}.*)', key)
    if match_dec_year:
        return f"{match_dec_year.group(1)} {match_dec_year.group(2)}"

    return key

def get_reference_index(keys):
    """
    找到参考文献类键的索引，作为处理的结束点
    """
    ref_patterns = [
        r'^参考文献[：:]?',
        r'^注[：:]?',
        r'^注释[：:]?',
        r'^注释与参考文献[：:]?',
        r'^\[参考文献\]'
    ]
    
    for i, key in enumerate(keys):
        for pat in ref_patterns:
            if re.match(pat, key):
                return i
    return len(keys)

def process_single_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        keys = list(data.keys())
        if not keys:
            return

        # --- 确定起始索引 ---
        start_idx = 2
        if len(keys) > 1:
            if re.match(r'^·.*·$', keys[1]):
                start_idx = 3
        
        # --- 确定结束索引 ---
        end_idx = get_reference_index(keys)
        
        # --- 遍历并构建新数据 ---
        new_data = {}
        modified = False
        
        for i, key in enumerate(keys):
            # 范围外：直接复制
            if i < start_idx or i >= end_idx:
                new_data[key] = data[key]
            else:
                # 范围内：尝试修复键名
                new_key = fix_key_text(key)
                if new_key != key:
                    modified = True
                    # print(f"修复: '{key}' -> '{new_key}'") # 调试用
                new_data[new_key] = data[key]
        
        # --- 只有发生修改时才写入文件 ---
        if modified:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, ensure_ascii=False, indent=4)
                
    except Exception as e:
        print(f"处理出错 {os.path.basename(file_path)}: {e}")

# ================== 主程序 ==================

def main():
    target_folder = 'all_json_iter1'
    
    if not os.path.exists(target_folder):
        print(f"文件夹不存在: {target_folder}")
        return

    files = [os.path.join(target_folder, f) for f in os.listdir(target_folder) if f.endswith('.json')]
    total = len(files)
    print(f"开始处理 {total} 个文件...")
    
    # 使用多进程加速
    max_workers = os.cpu_count() or 4
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        executor.map(process_single_file, files)
        
    print("处理完成。")

if __name__ == '__main__':
    main()