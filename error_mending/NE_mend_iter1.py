import os
import json
import re
import time
from concurrent.futures import ProcessPoolExecutor
import jieba.posseg as pseg

# ================== 1. 层级校验逻辑 (核心新增) ==================

class HierarchyValidator:
    """
    负责判断新发现的ID是否符合当前的层级逻辑
    防止 "如图2.1所示" 在 "3. 结果" 章节中被误判为标题
    """
    @staticmethod
    def parse_first_number(id_str):
        """从 "3.4.1" 提取 3; 从 "一、" 提取 1"""
        if not id_str:
            return None
        
        # 尝试提取阿拉伯数字
        arabic = re.match(r'^(\d+)', id_str)
        if arabic:
            return int(arabic.group(1))
        
        # 尝试提取中文数字
        cn_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
        cn_match = re.match(r'^([一二三四五六七八九十])', id_str)
        if cn_match and cn_match.group(1) in cn_map:
            return cn_map[cn_match.group(1)]
        
        return None

    @staticmethod
    def is_valid_continuation(current_parent_id, new_id):
        """
        判断 new_id 是否是 current_parent_id 的合理后续
        规则：
        1. 如果 new_id 是 parent 的子级 (3 -> 3.1)，通过
        2. 如果 new_id 是 parent 的后续兄弟 (3 -> 4)，通过
        3. 如果 new_id 是 parent 的前序 (3 -> 2.1)，拒绝 (视为正文引用)
        """
        # 如果当前没有父ID (比如在引言或摘要)，则允许任何ID
        if not current_parent_id:
            return True
            
        parent_num = HierarchyValidator.parse_first_number(current_parent_id)
        new_num = HierarchyValidator.parse_first_number(new_id)

        # 如果无法解析数字 (比如 "引言" vs "参考文献"), 默认允许
        if parent_num is None or new_num is None:
            return True

        # 核心逻辑：
        # 情况A: 是子层级 (如 parent="3", new="3.1") -> 必须以 parent_id 开头
        # 注意：这里做字符串前缀匹配比较安全 (避免 3.10 被误判)
        clean_parent = re.sub(r'[^\d\.]', '', current_parent_id).strip('.')
        clean_new = re.sub(r'[^\d\.]', '', new_id)
        
        if clean_new.startswith(clean_parent + '.') or clean_new.startswith(clean_parent + ' '):
            return True

        # 情况B: 是兄弟层级或升级 (如 parent="3", new="4" 或 new="4.1")
        if new_num >= parent_num:
            return True
            
        # 情况C: 是回退层级 (如 parent="3", new="2.1") -> 拒绝
        if new_num < parent_num:
            return False

        return True

# ================== 2. 提取器配置 ==================

# 正则微调：加强了对中文数字的标点限制，防止 "一个" 被匹配
raw_patterns = [
    r'^0(?=[^\d])',              
    r'^\d+(?:\.\d+)+[\s\.、．]*', # 小数型ID (2.1, 1.2.3)
    r'^\d+\s*[\.、．]\s*',        # 整数型+点 (1. , 2、) - 强制要求有点号，避免 "1998年" 匹配 "1"
    r'^[一二三四五六七八九十]+\s*[、．]\s*', # 中文数字+点 (一、) - 强制要求有点号，防止 "一个"
    r'^●\s*',                    
    r'^\d+\)\s*'                 
]
ID_PATTERNS = [re.compile(p) for p in raw_patterns]

STRONG_STARTERS = {
    "所谓", "顾名思义", "意指", "是指", "即", "也就是说", "换言之",
    "众所周知", "显而易见", "不可否认", "诚然", "反之", "事实上",
    "实际上", "毫无疑问", "一般认为", "值得注意", "比如", "例如",
    "因此", "然而", "但是", "长期以来", "自古以来", "早在", "近年来",
    "大量的", "大量", "研究表明", "表明", "综上所述"
}

def extract_title_body(text, current_parent_id=None):
    """
    提取标题，增加了 current_parent_id 参数用于逻辑校验
    """
    # 1. 正则匹配 ID
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
    
    # === 新增：层级校验 ===
    # 如果检测到的 ID (如 2.1) 不符合 当前父节点 (如 3) 的逻辑，则视为正文
    if not HierarchyValidator.is_valid_continuation(current_parent_id, section_id):
        return False, None, text
    # ====================

    clean_text = text[id_match.end():]
    
    # 2. 词性分析 (加速版)
    search_window = clean_text[:60]
    words = list(pseg.cut(search_window))
    
    split_index = -1
    noun_cache = [] 
    current_len = 0
    
    for i, w in enumerate(words):
        word = w.word
        flag = w.flag
        word_end_pos = current_len + len(word)
        
        # 策略 A: 代词
        if i > 0 and flag.startswith('r') and word in ['本文', '我们', '笔者', '这', '此', '其', '它']:
            split_index = current_len
            break
        # 策略 B: 强规则
        if i > 0 and word in STRONG_STARTERS:
            split_index = current_len
            break
        # 策略 C: 重复名词
        if flag.startswith(('n', 'v')): 
            if len(word) > 1 and word in noun_cache:
                split_index = current_len
                break
            if len(word) > 1:
                noun_cache.append(word)
        # 策略 D: 书名号
        if word == '《' and current_len > 1: 
            split_index = current_len
            break
            
        current_len = word_end_pos

    # 3. 兜底
    if split_index == -1:
        punc_match = re.search(r'[，。；：]', clean_text)
        if punc_match:
            split_index = punc_match.start()
        else:
            split_index = min(len(clean_text), 15) if len(clean_text) >= 15 else len(clean_text)

    title_content = clean_text[:split_index].strip()
    body_content = clean_text[split_index:].strip()
    
    full_title = f"{section_id} {title_content}"
    
    return True, full_title, body_content

# ================== 3. 参考文献截断逻辑 (新增) ==================

def truncate_after_references(data):
    """
    找到最后一个 '参考文献' 相关的 Key，删除其后面的所有 Key。
    """
    keys = list(data.keys())
    ref_index = -1
    
    # 倒序查找，找到最后一个出现的参考文献
    for i in range(len(keys) - 1, -1, -1):
        key = keys[i]
        # 匹配 "参考文献" 或 "References"
        if "参考文献" in key or "References" in key or key.strip() == "参考":
            ref_index = i
            break
    
    # 如果没找到，或者参考文献已经是最后一个，不做处理
    if ref_index == -1 or ref_index == len(keys) - 1:
        return data
    
    # 截断：只保留到 ref_index (包含 ref_index)
    new_data = {}
    for i in range(ref_index + 1):
        k = keys[i]
        new_data[k] = data[k]
        
    return new_data

# ================== 4. 单文件处理流程 ==================

def process_single_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        new_data = {}
        
        for main_key, main_value in data.items():
            # Key 清洗
            clean_main_key = main_key
            key_match = re.match(r'^((?:\d+\.)*\d+)([\u4e00-\u9fa5])', main_key)
            if key_match:
                clean_main_key = f"{key_match.group(1)} {main_key[key_match.end(1):]}"
            
            # 获取当前大标题的 ID (用于传入校验器)
            # 例如从 "2 几个突出特点" 中提取 "2"
            current_section_id = None
            id_match_top = re.match(r'^(\d+(?:\.\d+)*|[一二三四五]+)', clean_main_key)
            if id_match_top:
                current_section_id = id_match_top.group(1)

            current_section_key = clean_main_key
            if current_section_key not in new_data:
                new_data[current_section_key] = {}
            
            section_counters = {current_section_key: 1}
            
            if isinstance(main_value, dict):
                sorted_keys = sorted(main_value.keys(), 
                                   key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0)
                
                for ctx_key in sorted_keys:
                    text = main_value[ctx_key]
                    if not isinstance(text, str): continue
                    
                    # === 提取 (传入 current_section_id 进行校验) ===
                    is_new, new_title, new_body = extract_title_body(text, current_section_id)
                    
                    if is_new:
                        current_section_key = new_title
                        
                        # 更新当前 ID，以便后续的 context 校验更准确 (比如从 2 变成了 2.1)
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
        
        # === 最后一步：参考文献截断 ===
        final_data = truncate_after_references(new_data)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, ensure_ascii=False, indent=4)
            
        return (os.path.basename(file_path), True, "")
        
    except Exception as e:
        return (os.path.basename(file_path), False, str(e))

# ================== 5. 主程序入口 ==================

def main():
    target_folder = 'all_json_iter1'
    
    if not os.path.exists(target_folder):
        print(f"文件夹不存在: {target_folder}")
        return

    all_files = [os.path.join(target_folder, f) for f in os.listdir(target_folder) if f.endswith('.json')]
    total_files = len(all_files)
    print(f"检测到 {total_files} 个文件，开始深度清洗...")
    
    max_workers = os.cpu_count() or 4
    start_time = time.time()
    success_count = 0
    fail_count = 0
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        results = executor.map(process_single_file, all_files)
        
        for i, (filename, success, error_msg) in enumerate(results):
            if success:
                success_count += 1
            else:
                fail_count += 1
                print(f"\n[Error] {filename}: {error_msg}")
            
            if (i + 1) % 100 == 0:
                elapsed = time.time() - start_time
                speed = (i + 1) / elapsed
                remaining = (total_files - (i + 1)) / speed
                print(f"进度: {i + 1}/{total_files} | 速度: {speed:.1f} 文件/秒 | 预计剩余: {remaining/60:.1f} 分钟")

    print(f"\n处理完成！成功: {success_count}, 失败: {fail_count}")

if __name__ == "__main__":
    main()