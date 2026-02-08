import os
import json
import re
import time
from concurrent.futures import ProcessPoolExecutor
import jieba.posseg as pseg

# ================== 1. 層級校驗邏輯 (防禦性核心 - 保持不變) ==================

class HierarchyValidator:
    """
    負責判斷新發現的 ID 是否符合學術論文的層級邏輯。
    """
    @staticmethod
    def parse_first_number(id_str):
        if not id_str: return None
        arabic = re.match(r'^(\d+)', id_str)
        if arabic: return int(arabic.group(1))
        cn_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
        cn_match = re.match(r'^([一二三四五六七八九十])', id_str)
        if cn_match and cn_match.group(1) in cn_map: return cn_map[cn_match.group(1)]
        return None

    @staticmethod
    def is_valid_continuation(current_parent_id, new_id):
        if not current_parent_id: return True
        parent_num = HierarchyValidator.parse_first_number(current_parent_id)
        new_num = HierarchyValidator.parse_first_number(new_id)
        if parent_num is None or new_num is None: return True
        if new_num > parent_num + 2: return False
        if new_num < parent_num:
            clean_parent = re.sub(r'[^\d\.]', '', current_parent_id).strip('.')
            clean_new = re.sub(r'[^\d\.]', '', new_id)
            if clean_new.startswith(clean_parent + '.') or clean_new.startswith(clean_parent + ' '):
                return True
            return False
        return True

# ================== 2. 提取器與正則配置 (整合修復版) ==================

# 更新後的正則列表：支持5位數，支持緊貼型標題
ID_PATTERNS = [
    re.compile(r'^0(?=[^\d])'),              
    # 支持 1-5 位數的多級序號，如 1.2.3 或 12345.1
    re.compile(r'^\d{1,5}(?:\.\d+){1,5}[\s\.、．]*'), 
    # 支持 1-5 位數的單級序號，如 1. 或 123、 或 12345．
    re.compile(r'^\d{1,5}\s*[\.、．]\s*'),        
    # 中文數字
    re.compile(r'^[一二三四五六七八九十]+\s*[、．]\s*'), 
    re.compile(r'^●\s*'),                    
    # 支持 1-5 位數的括號序號
    re.compile(r'^\d{1,5}\)\s*'),
    # 【新增】支持數字與文字緊貼的情況 (Lookahead)，如 "2統一管理"
    re.compile(r'^\d{1,5}(?=[^\d\s\.、．])') 
]

# 強特徵詞 (保持不變)
STRONG_STARTERS = {
    "所谓", "顾名思义", "意指", "是指", "即", "也就是说", "换言之",
    "众所周知", "显而易见", "不可否认", "诚然", "反之", "事实上",
    "实际上", "毫无疑问", "一般认为", "值得注意", "比如", "例如",
    "因此", "然而", "但是", "长期以来", "自古以来", "早在", "近年来",
    "大量的", "大量", "研究表明", "表明", "综上所述", "根据", "对于",
    "通常", "主要", "它是", "指", "包括", "其特征", "是"
}

def extract_title_body(text, current_parent_id=None):
    """
    提取標題，並進行層級校驗。
    整合修復：
    1. 支持緊貼型序號 (2統一...)
    2. 排除世紀/年代/年份誤判 (1989年...)，防止層級中斷
    """
    id_match = None
    longest_match_len = 0
    
    # 1. 嘗試匹配所有 ID 模式，取最長匹配
    for pattern in ID_PATTERNS:
        match = pattern.match(text)
        if match:
            if match.end() > longest_match_len:
                id_match = match
                longest_match_len = match.end()
    
    if not id_match:
        return False, None, text

    section_id = id_match.group(0).strip()
    clean_text = text[id_match.end():] # 標題候選內容 (去除 ID 後)

    # === 【關鍵修復 A】年份誤判防禦 (防止 1989年... 打斷層級) ===
    # 如果提取出的 ID 恰好是 4 位數字，且後續緊跟 "年" 字
    # 例如：text="1989年9月..." -> id="1989", clean="年9月..."
    # 這通常是年份描述，而非標題
    if re.fullmatch(r'\d{4}', section_id) and clean_text.strip().startswith('年'):
        return False, None, text

    # === 【關鍵修復 B】世紀/年代誤判防禦 ===
    # 排除 "20 世紀"、"80 年代" 等
    if re.match(r'^\s*(世纪|世紀|年代)', clean_text):
        return False, None, text

    # === 校驗 1: 層級邏輯 (防禦性核心) ===
    # 只有通過了上面的年份過濾，才會進入這裡
    # 這樣 "1989" 就不會作為父級 ID 傳入，保證了 "一、" -> "二、" 的連續性
    if not HierarchyValidator.is_valid_continuation(current_parent_id, section_id):
        return False, None, text

    # === 校驗 2: 年份粘連防禦 (舊邏輯保留) ===
    # 防止 "1. 1998年..." 這種情況
    if re.match(r'^\s*[12]\d{3}年', clean_text):
        return False, None, text

    # === 核心：確定搜索邊界 (Hard Limit) ===
    # 規則：標題絕對不會跨越句號、問號或感嘆號
    sentence_end_match = re.search(r'[。？！\?!]', clean_text)
    
    if sentence_end_match:
        limit_index = sentence_end_match.end()
        search_window = clean_text[:limit_index]
        has_punctuation = True
    else:
        limit_index = min(len(clean_text), 50)
        search_window = clean_text[:limit_index]
        has_punctuation = False

    # === 分詞與斷句邏輯 ===
    words = list(pseg.cut(search_window))
    
    split_index = -1
    current_len = 0
    
    for i, w in enumerate(words):
        word = w.word
        flag = w.flag
        
        # 1. 遇到人名 (nr)，立即截斷！
        if flag.startswith('nr'): 
            split_index = current_len
            break
            
        # 2. 遇到強特徵詞 (Strong Starters)
        if word in STRONG_STARTERS:
            split_index = current_len
            break
        
        # 3. 遇到代詞 (r) 且不是第一個詞
        if i > 0 and flag.startswith('r'):
            split_index = current_len
            break

        # 4. 遇到書名號《，視情況截斷
        if word == '《' and current_len > 15: 
            split_index = current_len
            break
            
        current_len += len(word)

    # === 結果判定 ===
    
    # 情況 A: 循環中找到了分割點
    if split_index != -1:
        title_content = clean_text[:split_index].strip()
        body_content = clean_text[split_index:].strip()
    
    # 情況 B: 沒找到分割點，但原本就有句號
    elif has_punctuation:
        title_content = clean_text[:limit_index].strip()
        body_content = clean_text[limit_index:].strip()
        
    # 情況 C: 沒句號，也沒特徵詞
    else:
        # 嘗試找逗號或分號
        punc_match = re.search(r'[，；：,:]', search_window)
        if punc_match:
            split_index = punc_match.start()
        else:
            split_index = min(len(clean_text), 25) # 兜底長度
            
        title_content = clean_text[:split_index].strip()
        body_content = clean_text[split_index:].strip()

    # 最後清洗
    if not title_content and not body_content:
        return True, section_id, ""
        
    full_title = f"{section_id} {title_content}"
    return True, full_title, body_content

# ================== 3. 輔助函數 (保持不變) ==================

def fix_key_text(key):
    PROTECTED = {"911", "985", "211", "315"}
    if re.fullmatch(r'\d{6}', key): return key
    match_century = re.match(r'^(\d+(?:\.\d+)*?)\s*(2[01]世紀|2[01]世纪|1[89]世紀|1[89]世纪.*)', key)
    if match_century:
        p1, p2 = match_century.groups()
        if p1 not in PROTECTED: return f"{p1} {p2}"
    match_year = re.match(r'^(\d+(?:\.\d+)*?)\s*([12]\d{3}年.*)', key)
    if match_year:
        p1, p2 = match_year.groups()
        if p1 not in PROTECTED: return f"{p1} {p2}"
    match_era = re.match(r'^(\d+(?:\.\d+)*?)\s*([12]?\d{1,2}0年代.*)', key)
    if match_era:
        p1, p2 = match_era.groups()
        return f"{p1} {p2}"
    return key

# ================== 4. 單文件處理流程 (修改後：移除截斷) ==================

# ================== 4. 單文件處理流程 (修復父級ID誤判) ==================

def process_single_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        new_data = {}
        
        for main_key, main_value in data.items():
            clean_main_key = fix_key_text(main_key)
            current_section_id = None
            
            # === 【核心修復】父級 ID 提取邏輯優化 ===
            # 尝试从 Key 中提取 ID
            id_match_top = re.match(r'^(\d+(?:\.\d+)*|[一二三四五六七八九十]+)', clean_main_key)
            if id_match_top:
                candidate_id = id_match_top.group(1)
                remaining_text = clean_main_key[id_match_top.end():].strip()
                
                # 防禦規則：如果提取出的 ID 是 4 位數字且後面緊跟“年”，則判定這不是章節號 (如 "1989年...")
                # 此時 current_section_id 保持為 None，這樣內部的 "二、" 就不會因為父級是 1989 而被攔截
                if re.fullmatch(r'\d{4}', candidate_id) and remaining_text.startswith('年'):
                    current_section_id = None
                else:
                    current_section_id = candidate_id

            current_section_key = clean_main_key
            if current_section_key not in new_data:
                new_data[current_section_key] = {}
            
            section_counters = {current_section_key: 1}
            
            if isinstance(main_value, dict):
                # 保持原始順序或按需排序
                sorted_keys = sorted(main_value.keys(), 
                                   key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0)
                
                for ctx_key in sorted_keys:
                    text = main_value[ctx_key]
                    if not isinstance(text, str): continue
                    
                    # 這裡調用的 extract_title_body 必須是之前更新過的版本 (包含年份防禦)
                    is_new, new_title, new_body = extract_title_body(text, current_section_id)
                    
                    if is_new:
                        current_section_key = new_title
                        
                        # 更新當前 ID，以便後續內容能通過校驗 (例如提取出 "二、" 後，下一個 "三、" 的 parent 就是 2)
                        new_id_match = re.match(r'^(\d+(?:\.\d+)*|[一二三四五六七八九十]+)', new_title)
                        if new_id_match:
                            current_section_id = new_id_match.group(1)

                        new_data[current_section_key] = {}
                        section_counters[current_section_key] = 1 
                        if new_body:
                            idx = section_counters[current_section_key]
                            new_data[current_section_key][f"context{idx}"] = new_body
                            section_counters[current_section_key] += 1
                    else:
                        if current_section_key not in section_counters:
                            section_counters[current_section_key] = 1
                        idx = section_counters[current_section_key]
                        new_data[current_section_key][f"context{idx}"] = text
                        section_counters[current_section_key] += 1
            else:
                new_data[clean_main_key] = main_value
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(new_data, f, ensure_ascii=False, indent=4)
            
        return True
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False

# ================== 5. 主程序入口 ==================

def main():
    target_folder = 'all_json_iter1'
    if not os.path.exists(target_folder):
        print(f"文件夾不存在: {target_folder}")
        return

    all_files = [os.path.join(target_folder, f) for f in os.listdir(target_folder) if f.endswith('.json')]
    print(f"[Iter1] 開始深度清洗 {len(all_files)} 個文件 (已禁用參考文獻截斷)...")
    
    max_workers = os.cpu_count() or 4
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        executor.map(process_single_file, all_files)

    print("NE_mend_iter1 處理完成。")

if __name__ == "__main__":
    main()