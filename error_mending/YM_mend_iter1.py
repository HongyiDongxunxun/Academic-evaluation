import os
import json
import re
from concurrent.futures import ProcessPoolExecutor

# ================== 核心修复逻辑 ==================

# --- 在 YM_mend_iter1.py 中更新 fix_key_text 函數 ---

def fix_key_text(key):
    """
    修復鍵名中的粘連問題，包含年份、世紀、年代以及特定關鍵詞（985/211等）。
    """
    PROTECTED_KEYWORDS = {"911", "985", "211", "315"}
    
    # 0. 基礎過濾：如果是純6位數字（如股票代碼），直接返回
    if re.fullmatch(r'\d{6}', key): return key
    # 如果完全等於保護詞，直接返回
    if key in PROTECTED_KEYWORDS: return key

    # ================== 新增規則 ==================

    # 規則 A: [新增] 處理 "ID + 985/211..." 的粘連 (例如 "4985高校" -> "4 985高校")
    # 邏輯：單個數字 + 保護詞 + 任意內容
    # 注意：需防止 "1985年" 被誤拆為 "1 985年"，所以排除後面緊跟 "年" 或 "-" 的情況
    match_protected = re.match(r'^(\d)(985|211|315|911)(.*)', key)
    if match_protected:
        id_val, keyword, rest = match_protected.groups()
        # 防禦誤判：如果拆分後看起來像年份（如 1+985+年 = 1985年），則不拆分
        is_year_misjudgment = (id_val == '1' and keyword in ['985', '911'] and re.match(r'^[\s\.]*[年\-\－]', rest))
        if not is_year_misjudgment:
            return f"{id_val} {keyword}{rest}"

    # 規則 B: [新增] 處理 "ID + 年份區間" 的粘連 (例如 "31978－2007年")
    # 邏輯：數字 + (1或2開頭的4位年份) + (區間連接符)
    # 這裡的連接符涵蓋了全形/半形破折號、波浪號等
    match_year_range = re.match(r'^(\d+)([12]\d{3}[－\-—~～].*)', key)
    if match_year_range:
        id_val, rest = match_year_range.groups()
        return f"{id_val} {rest}"

    # ================== 原有規則優化 ==================

    # 規則 C: 處理 "ID + 世紀" (例如 "2.221世紀" -> "2.2 21世紀")
    match_century = re.match(r'^(\d+(?:\.\d+)*?)\s*(2[01]世紀|2[01]世纪.*)', key)
    if match_century:
        p1, p2 = match_century.groups()
        if p1 not in PROTECTED_KEYWORDS:
            return f"{p1} {p2}"

    # 規則 D: 處理 "ID + 年份 + 年" (例如 "1.11998年" -> "1.1 1998年")
    # 使用非貪婪匹配 *? 確保盡可能少地匹配 ID
    match_year = re.match(r'^(\d+(?:\.\d+)*?)\s*([12]\d{3}年.*)', key)
    if match_year:
        p1, p2 = match_year.groups()
        if p1 not in PROTECTED_KEYWORDS:
            return f"{p1} {p2}"

    # 規則 E: 處理 "ID + 年代" (例如 "390年代" -> "3 90年代")
    match_era = re.match(r'^(\d)(\d{2})(年代.*)', key)
    if match_era:
        p1, p2, p3 = match_era.groups()
        # 避免把 911年代 拆成 9 11年代（雖然少見）
        if (p1 + p2) not in PROTECTED_KEYWORDS:
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