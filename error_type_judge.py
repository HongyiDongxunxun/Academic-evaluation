import os
import json
import re
import csv
import shutil

# ================== 正则配置 ==================

# 1. 小标题/序号模式 (Heading Patterns)
# 限制数字序号为 1-3 位以排除年份；排除后面紧跟“世纪/年代/年”的数字；支持次级标题 (1) 和 1)
heading_patterns = [
    r'^0[^\d]',
    r'^\d{1,3}\s+[\d一二三四五六七八九十]+.*',
    r'^\d{1,3}(?!\d)\s*[\.、。]?\s*', 
    r'^[一二三四五六七八九十]{1,3}\s*[、．]?\s*',
    r'^●\s*',
    r'^\d{1,3}[\)）]\s*',
    r'^[\(\（]\d{1,3}[\)\）]\s*'
]

# 2. 参考文献模式
reference_patterns = [
    r'^参考文献[：:]?',
    r'^注[：:]?',
    r'^注释[：:]?',
    r'^注释与参考文献[：:]?',
    r'^\[参考文献\]'
]

# 3. 忽略模式：元数据 (Metadata)
# 包含 [摘要]、[关键词] 等，支持全角半角及随机空格
meta_ignore_pattern = r'^\s*[\[［]\s*(关键词|摘要|Abstract|Keywords|中图分类号|文献标识码|文章编号|DOI|引用格式|分类号)\s*[\]］].*'
# 纯英文元数据模式 (排除掉短序号格式)
english_meta_pattern = r'^[a-zA-Z0-9\s\.\-\/\\,;:()（）"\'一]+$'

# 4. 其他错误模式
publication_mixed_pattern = r'^·.*·$'
# Year_Mixed: 仅在开头检查。排除保护词、排除6位邮编、排除正常年份；识别5位以上粘连年份
year_mixed_pattern = r'^(?:(?!(?:911|985|211|315)(?!\d))\d{3}(?!\d)|\d{5,})'

page_mixed_pattern = r'^（上接.*页）$'

# ================== 辅助函数 ==================

# --- 在 error_type_judge.py 中修改以下部分 ---

def is_heading(text):
    if not text or len(text) > 60: return False
    # 排除年份與世紀干擾
    if re.match(r'^(?:19|20|21)\d{0,2}\s*(?:世紀|世纪|年代|年)', text):
        return False
    return any(re.search(pat, text) for pat in heading_patterns)

def is_reference(text):
    """判断是否为参考文献标题"""
    return any(re.search(pat, text) for pat in reference_patterns)

def is_subtitle(text):
    """判断是否为序号标题或参考文献"""
    return is_heading(text) or is_reference(text)

def is_meta_key(text):
    """识别需要忽略的干扰键 (如摘要、英文标题等)"""
    if not text: return False
    if re.match(meta_ignore_pattern, text): return True
    # 纯英文元数据 (需包含字母且符合字符集，且不是短序号格式)
    if re.search(r'[a-zA-Z]', text) and re.match(english_meta_pattern, text):
        if not is_heading(text): return True
    return False

def check_title_mixed(keys_to_check):
    """Title_Mixed: 在小标题键之间，存在非标题且非忽略元数据的杂质键"""
    sub_indices = [i for i, k in enumerate(keys_to_check) if is_subtitle(k)]
    if len(sub_indices) < 2: return False
    for i in range(len(sub_indices) - 1):
        if sub_indices[i+1] - sub_indices[i] > 1:
            return True
    return False

def extract_number_part(text):
    m = re.match(r'^(\d+(?:\.\d+)*)', text)
    if m: return m.group(1)
    return None

# ================== 辅助函数 (修改版) ==================

# 定义中文数字映射
CN_NUM = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}

def cn_to_int(text):
    """将简单中文序号转换为数字"""
    val = 0
    if text.startswith('十'): 
        val = 10 + (CN_NUM.get(text[1], 0) if len(text) > 1 else 0)
    elif text.endswith('十'):
        val = CN_NUM.get(text[0], 1) * 10
    elif '十' in text:
        parts = text.split('十')
        val = CN_NUM.get(parts[0], 1) * 10 + CN_NUM.get(parts[1], 0)
    else:
        val = CN_NUM.get(text, 0)
    return val

def get_level_and_value(text):
    """
    解析标题的层级和数值。
    Level 1: 一./一、 (中文+标点)
    Level 2: （一）   (括号+中文)
    Level 3: 1. / 1 / 1、 (数字+标点 或 数字+空格)
    Level 4: 1.1      (数字.数字)
    Level 5: (1)      (括号+数字)
    """
    text = text.strip()
    
    # 1. Level 4: 1.1 (包含点的阿拉伯数字，需优先匹配)
    # 逻辑：必须包含至少一个点，且点两侧都有数字
    m_l4 = re.match(r'^(\d+(?:\.\d+)+)', text)
    if m_l4:
        nums = list(map(int, m_l4.group(1).split('.')))
        return 4, nums

    # 2. Level 1: 一、 / 一. 
    m_l1 = re.match(r'^([一二三四五六七八九十]+)[、．\.]', text)
    if m_l1:
        return 1, cn_to_int(m_l1.group(1))

    # 3. Level 2: （一） / (一)
    m_l2 = re.match(r'^[（\(]([一二三四五六七八九十]+)[）\)]', text)
    if m_l2:
        return 2, cn_to_int(m_l2.group(1))

    # 4. Level 3: 1. / 1、 / 1 (空格)
    # 这里增加了对空格的兼容 (如 "2 xxx")，以及纯数字加标点
    m_l3 = re.match(r'^(\d+)(?:[、．\.]|\s|$)', text)
    if m_l3:
        return 3, int(m_l3.group(1))

    # 5. Level 5: (1) / （1）
    m_l5 = re.match(r'^[（\(](\d+)[）\)]', text)
    if m_l5:
        return 5, int(m_l5.group(1))

    return 0, None

def check_num_error(headings):
    """Num_Error: 检查序号逻辑，忽略跨级返回的情况"""
    if len(headings) < 2: return False
    
    parsed_headings = [get_level_and_value(h) for h in headings]
    
    for i in range(len(parsed_headings) - 1):
        curr_lv, curr_val = parsed_headings[i]
        next_lv, next_val = parsed_headings[i+1]
        
        # 无法解析则跳过
        if curr_lv == 0 or next_lv == 0: continue

        # --- 情况 A: 同级 (1.1 -> 1.2) ---
        if curr_lv == next_lv:
            if curr_lv == 4: # 列表比较 [1, 1] -> [1, 2]
                if len(curr_val) == len(next_val):
                    # 前缀必须相同，仅末位递增
                    if curr_val[:-1] != next_val[:-1] or next_val[-1] != curr_val[-1] + 1:
                        if next_val[-1] - curr_val[-1] > 5: continue # 忽略大跳跃
                        return True
            else: # 整数比较
                if next_val - curr_val > 5: continue # 忽略大跳跃(如年份)
                if next_val != curr_val + 1:
                    return True

        # --- 情况 B: 进级/子标题 (1. -> 1.1, 一、 -> （一）) ---
        elif next_lv == curr_lv + 1:
            # 下一级必须从 1 开始 (或 1.1)
            is_start = False
            if next_lv == 4: 
                # Level 4 比较特殊，[X, 1] 算开始
                if next_val[-1] == 1: is_start = True
            else:
                if next_val == 1: is_start = True
            
            if not is_start:
                return True

        # --- 情况 C: 退级/返回父级 (1.3 -> 2) 或 混合跳跃 ---
        # 你的需求： "1.3 xxx" -> "2 xxx" 这种不算错。
        # 这里的逻辑是：只要不是同级连续或严格的子级展开，其他层级跳转(如 L4 -> L3)一律视为“开启新章节”或“无关”，不报错。
        else:
            continue

    return False

# ================== 主程序 ==================

def main(input_folder, iter_num=0):
    report_dir = 'error_report'
    os.makedirs(report_dir, exist_ok=True)
    output_csv = os.path.join(report_dir, f'strucheck_iter{iter_num}.csv')
    report_txt = os.path.join(report_dir, f'error_iter{iter_num}.txt')
    
    headers = ['filename', 'Num_Error', 'Page_Mixed', 'Initially_Unstructured', 
               'Title_Mixed', 'Publication_Mixed', 'Year_Mixed', 
               'Mutiple_References', 'Dubiously_Fake_References', 'Plausibly_Structured']
    all_results = []

    if not os.path.exists(input_folder): return

    files = sorted([f for f in os.listdir(input_folder) if f.endswith('.json')],
                   key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0)

    for filename in files:
        file_info = {k: 0 for k in headers}; file_info['filename'] = filename
        try:
            with open(os.path.join(input_folder, filename), 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            file_info['Initially_Unstructured'] = 1; all_results.append(file_info); continue
        
        all_keys = list(data.keys())
        
        # --- 步骤 1: 确定检查起点 ---
        # 跳过前两个键 (文件名和标题)，继续跳过摘要、英文名、及顶层出版信息
        idx = 2
        while idx < len(all_keys):
            key = all_keys[idx]
            if is_meta_key(key) or re.match(publication_mixed_pattern, key):
                idx += 1
            elif not is_heading(key) and len(key) > 20: 
                idx += 1
            else:
                break
        
        # 截取范围并彻底过滤干扰元数据
        keys_to_check = [k for k in all_keys[idx:] if not is_meta_key(k)]
        valid_headings = [k for k in keys_to_check if is_heading(k)]
        valid_subs = [k for k in keys_to_check if is_subtitle(k)]

        if not valid_subs:
            file_info['Initially_Unstructured'] = 1; all_results.append(file_info); continue

        # --- 步骤 2: Publication_Mixed 专项检查 (仅在第一个序号到参考文献之间) ---
        first_h, first_ref = -1, len(keys_to_check)
        for i, k in enumerate(keys_to_check):
            if first_h == -1 and is_heading(k): first_h = i
            if is_reference(k): first_ref = i; break
        if first_h != -1 and first_h < first_ref:
            for k in keys_to_check[first_h : first_ref]:
                if re.match(publication_mixed_pattern, k):
                    file_info['Publication_Mixed'] = 1; break

        # --- 步骤 3: 其他错误判定 ---
        if check_title_mixed(keys_to_check): file_info['Title_Mixed'] = 1
        if check_num_error(valid_headings): file_info['Num_Error'] = 1
        
        for k in keys_to_check:
            if re.match(page_mixed_pattern, k): file_info['Page_Mixed'] = 1
            if re.search(year_mixed_pattern, k): file_info['Year_Mixed'] = 1
        
        ref_count, found_ref, fake_ref = 0, False, False
        for k in keys_to_check:
            if is_reference(k): ref_count += 1; found_ref = True
            elif found_ref and re.match(r'^\d+\s*[\.、。]?\s*', k): fake_ref = True
        
        if ref_count >= 2: file_info['Mutiple_References'] = 1
        if fake_ref: file_info['Dubiously_Fake_References'] = 1
            
        if not any(file_info[f] for f in headers[1:-1]): file_info['Plausibly_Structured'] = 1
        all_results.append(file_info)

    # --- 步骤 4: 输出报告 ---
    total = len(all_results)
    stats_lines = ["===== 各类问题比例 ====="]
    for h in headers[1:]:
        cnt = sum(r[h] for r in all_results)
        pct = (cnt / total * 100) if total > 0 else 0
        stats_lines.append(f"{h}: {cnt} ({pct:.2f}%)")
    stats_lines.append(f"总计: {total} 文件")
    
    with open(report_txt, 'w', encoding='utf-8') as f: f.write("\n".join(stats_lines))
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader(); writer.writerows(all_results)
    
    print(f"\n[Iteration {iter_num}] 已生成报告至 {report_dir}")
    print("\n".join(stats_lines))

if __name__ == "__main__":
    main('all_json_iter0', 0)
    main('all_json_iter1', 1)