import os
import json
import re
from concurrent.futures import ProcessPoolExecutor

# ================== 核心修复逻辑 ==================

# --- 在 YM_mend_iter1.py 中更新 fix_key_text 函數 ---

def fix_key_text(key):
    PROTECTED = {"911", "985", "211", "315"}
    if re.fullmatch(r'\d{6}', key): return key

    # 使用 (*?) 非貪婪匹配，確保 2.221世纪 能正確拆分為 2.2 和 21世纪
    # 模式 1: 序號 + 世紀
    match_century = re.match(r'^(\d+(?:\.\d+)*?)\s*(2[01]世纪.*)', key)
    if match_century:
        p1, p2 = match_century.groups()
        if p1 not in PROTECTED:
            return f"{p1} {p2}"

    # 模式 2: 序號 + 年份
    match_year = re.match(r'^(\d+(?:\.\d+)*?)\s*([12]\d{3}年.*)', key)
    if match_year:
        p1, p2 = match_year.groups()
        if p1 not in PROTECTED:
            return f"{p1} {p2}"

    # 維持原有的年代修復邏輯...
    match_3 = re.match(r'^(\d)(\d{2})(年代.*)', key)
    if match_3:
        p1, p2, p3 = match_3.groups()
        if (p1 + p2) not in PROTECTED:
            return f"{p1} {p2}{p3}"

    return key

def process_single_file(file_path):
    """处理单个 JSON 文件的修复逻辑"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        all_keys = list(data.keys())
        if not all_keys: return

        # 确定起始位置
        start_idx = 2
        if len(all_keys) > 2 and re.match(r'^·.*·$', all_keys[2]):
            start_idx = 3
        
        # 确定结束位置 (不修复参考文献后的键)
        end_idx = len(all_keys)
        ref_patterns = [r'^参考文献', r'^注[：:]?', r'^注释', r'^\[参考文献\]']
        for i, k in enumerate(all_keys):
            if any(re.match(p, k) for p in ref_patterns):
                end_idx = i; break
        
        new_data = {}; modified = False
        for i, key in enumerate(all_keys):
            if i < start_idx or i >= end_idx:
                new_data[key] = data[key]
            else:
                new_key = fix_key_text(key)
                if new_key != key:
                    modified = True
                new_data[new_key] = data[key]
        
        if modified:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, ensure_ascii=False, indent=4)
                
    except Exception as e:
        print(f"Error in {os.path.basename(file_path)}: {e}")

# ================== 主程序 ==================

def main():
    target_folder = 'all_json_iter1'
    if not os.path.exists(target_folder):
        print(f"Folder not found: {target_folder}")
        return

    files = [os.path.join(target_folder, f) for f in os.listdir(target_folder) if f.endswith('.json')]
    print(f"正在多进程处理 {len(files)} 个文件...")
    
    with ProcessPoolExecutor() as executor:
        executor.map(process_single_file, files)
        
    print("Year_Mixed 批量修复完成。")

if __name__ == '__main__':
    main()