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

# ================== 2. 提取器與正則配置 (重點修改部分) ==================

ID_PATTERNS = [
    re.compile(r'^0(?=[^\d])'),              
    re.compile(r'^\d{1,3}(?:\.\d+){1,3}[\s\.、．]*'), 
    re.compile(r'^\d{1,3}\s*[\.、．]\s*'),        
    re.compile(r'^[一二三四五六七八九十]+\s*[、．]\s*'), 
    re.compile(r'^●\s*'),                    
    re.compile(r'^\d{1,3}\)\s*')                 
]

# 擴充了強特徵詞，包含常見的定義起始詞和轉折詞
STRONG_STARTERS = {
    "所謂", "顧名思義", "意指", "是指", "即", "也就是說", "換言之",
    "眾所周知", "顯而易見", "不可否認", "誠然", "反之", "事實上",
    "實際上", "毫無疑問", "一般認為", "值得注意", "比如", "例如",
    "因此", "然而", "但是", "長期以來", "自古以來", "早在", "近年來",
    "大量的", "大量", "研究表明", "表明", "綜上所述", "根據", "對於",
    "通常", "主要", "它是", "指", "包括", "其特徵", "是"
}

def extract_title_body(text, current_parent_id=None):
    """
    提取標題，並進行層級校驗。
    改進點：遇到句號強制截斷、遇到人名強制截斷、遇到定義詞強制截斷。
    """
    id_match = None
    longest_match_len = 0
    
    for pattern in ID_PATTERNS:
        match = pattern.match(text)
        if match:
            if match.end() > longest_match_len:
                id_match = match
                longest_match_len = match.end()
    
    if not id_match:
        return False, None, text

    section_id = id_match.group(0).strip()
    
    # === 校驗 1: 層級邏輯 ===
    if not HierarchyValidator.is_valid_continuation(current_parent_id, section_id):
        return False, None, text

    clean_text = text[id_match.end():]

    # === 校驗 2: 年份粘連防禦 ===
    if re.match(r'^\s*[12]\d{3}年', clean_text):
        return False, None, text

    # === 核心改進：確定搜索邊界 (Hard Limit) ===
    # 規則：標題絕對不會跨越句號、問號或感嘆號
    # 找到第一個結束性標點
    sentence_end_match = re.search(r'[。？！\?!]', clean_text)
    
    # 如果找到了句號，這就是絕對邊界
    if sentence_end_match:
        # 標題候選區間只到標點符號為止（包含標點）
        limit_index = sentence_end_match.end()
        search_window = clean_text[:limit_index]
        has_punctuation = True
    else:
        # 如果沒句號，限制在 50 字以內，避免標題太長
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
        
        # 1. 遇到人名 (nr)，立即截斷！(防禦 "邱曉威等")
        if flag.startswith('nr'): 
            split_index = current_len
            break
            
        # 2. 遇到強特徵詞/代詞/書名號
        if word in STRONG_STARTERS:
            split_index = current_len
            break
        
        # 3. 遇到代詞 (r) 且不是第一個詞
        if i > 0 and flag.startswith('r'):
            split_index = current_len
            break

        # 4. 遇到書名號《，通常標題不包含書名號後的長描述，視情況截斷
        # 但有些標題就是《xxx》簡介，所以這裡放寬，只有當前面已有內容時才考慮
        if word == '《' and current_len > 15: 
            split_index = current_len
            break
            
        current_len += len(word)

    # === 結果判定 ===
    
    # 情況 A: 循環中找到了分割點 (例如遇到"所謂"或人名)
    if split_index != -1:
        title_content = clean_text[:split_index].strip()
        body_content = clean_text[split_index:].strip()
    
    # 情況 B: 沒找到分割點，但原本就有句號
    elif has_punctuation:
        # 整個候選區間就是標題 (包含句號)
        # 例如: "三、 應用研究成果具有較大的實用價值。"
        title_content = clean_text[:limit_index].strip()
        body_content = clean_text[limit_index:].strip()
        
    # 情況 C: 沒句號，也沒特徵詞，採用長度或逗號兜底
    else:
        # 嘗試找逗號或分號
        punc_match = re.search(r'[，；：,:]', search_window)
        if punc_match:
            split_index = punc_match.start()
        else:
            # 強制截斷長度，避免把一段話當標題
            split_index = min(len(clean_text), 25) # 標題通常不超過25字
            
        title_content = clean_text[:split_index].strip()
        body_content = clean_text[split_index:].strip()

    # 最後清洗：如果標題是空的（只有 ID），視為無效或純 ID
    if not title_content and not body_content:
        # 只有 ID 沒有內容，可能正文在後面
        return True, section_id, ""
        
    full_title = f"{section_id} {title_content}"
    return True, full_title, body_content

# ================== 3. 輔助函數 (保持不變) ==================

def fix_key_text(key):
    PROTECTED = {"911", "985", "211", "315"}
    if re.fullmatch(r'\d{6}', key): return key
    match_century = re.match(r'^(\d+(?:\.\d+)*?)\s*(2[01]世紀|2[01]世纪.*)', key)
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

def process_single_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        new_data = {}
        
        for main_key, main_value in data.items():
            clean_main_key = fix_key_text(main_key)
            current_section_id = None
            id_match_top = re.match(r'^(\d+(?:\.\d+)*|[一二三四五]+)', clean_main_key)
            if id_match_top:
                current_section_id = id_match_top.group(1)

            current_section_key = clean_main_key
            if current_section_key not in new_data:
                new_data[current_section_key] = {}
            
            section_counters = {current_section_key: 1}
            
            if isinstance(main_value, dict):
                # 這裡保持原始順序或按需排序，這裡維持原邏輯
                sorted_keys = sorted(main_value.keys(), 
                                   key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0)
                
                for ctx_key in sorted_keys:
                    text = main_value[ctx_key]
                    if not isinstance(text, str): continue
                    
                    is_new, new_title, new_body = extract_title_body(text, current_section_id)
                    
                    if is_new:
                        current_section_key = new_title
                        new_id_match = re.match(r'^(\d+(?:\.\d+)*|[一二三四五]+)', new_title)
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
        
        # [修改]：移除了 truncate_after_references 調用，防止誤刪
        # final_data = truncate_after_references(new_data) 
        
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