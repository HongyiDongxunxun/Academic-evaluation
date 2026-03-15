import os
import json
import re
import spacy

# 1. 加载 spaCy 中文模型
try:
    nlp = spacy.load("zh_core_web_sm")
except OSError:
    print("未能找到中文模型，请在命令行执行: python -m spacy download zh_core_web_sm")
    exit()

INPUT_DIR = "test_jsons"
OUTPUT_DIR = "entitites_jsons"

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

def contains_target_entities(text):
    """
    判断单句中是否包含目标实体（书名、人名、机构名）
    """
    if re.search(r'《.*?》', text):
        return True
    
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ in ['PERSON', 'ORG']:
            return True
    return False

def should_filter_block(block):
    """
    判断一个文本块是否应该被过滤掉
    过滤规则：
    1. 1位或2位数字开头，紧接着是人名而不是"年"、"年代"、"月"
    2. 以ABSTRACT或KEY开头
    3. 只有一个人名且文本长度 <= 8
    4. 以"[数字]"格式开头（如[1]、[12]等引用格式）
    """
    block = block.strip()
    if not block:
        return True
    
    if block.upper().startswith('ABSTRACT') or block.upper().startswith('KEY'):
        return True
    
    if re.match(r'^\[\d+\]', block):
        return True
    
    if re.match(r'^\d{1,2}[^\d年月日]', block):
        doc = nlp(block)
        person_count = 0
        for ent in doc.ents:
            if ent.label_ == 'PERSON':
                person_count += 1
                first_person_text = ent.text
                break
        if person_count > 0:
            first_char_after_num = block[1] if len(block) > 1 else ''
            if first_char_after_num not in '年月日':
                return True
    
    doc = nlp(block)
    person_count = 0
    for ent in doc.ents:
        if ent.label_ == 'PERSON':
            person_count += 1
    
    if person_count == 1 and len(block) <= 8:
        return True
    
    return False

def extract_blocks_with_window(text, window_before=1, window_after=0):
    """
    核心逻辑：带有滑动窗口的句子提取
    """
    sents = re.split(r'(?<=[。！？])', text)
    sents = [s.strip() for s in sents if s.strip()]
    
    if not sents:
        return []

    indices_to_keep = set()
    
    for i, sent in enumerate(sents):
        if contains_target_entities(sent):
            start_idx = max(0, i - window_before)
            end_idx = min(len(sents), i + window_after + 1)
            
            for j in range(start_idx, end_idx):
                indices_to_keep.add(j)
                
    if not indices_to_keep:
        return []

    sorted_indices = sorted(list(indices_to_keep))
    extracted_blocks = []
    current_block = [sents[sorted_indices[0]]]
    
    for idx in range(1, len(sorted_indices)):
        curr_i = sorted_indices[idx]
        prev_i = sorted_indices[idx-1]
        
        if curr_i == prev_i + 1:
            current_block.append(sents[curr_i])
        else:
            extracted_blocks.append("".join(current_block))
            current_block = [sents[curr_i]]
            
    if current_block:
        extracted_blocks.append("".join(current_block))
        
    return extracted_blocks

def process_data(data):
    """
    递归遍历 JSON，返回提取的文本块列表和原始文本总字数
    """
    results = []
    total_chars = 0
    
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "original_filename":
                continue
            blocks, chars = process_data(value)
            results.extend(blocks)
            total_chars += chars
            
    elif isinstance(data, list):
        for item in data:
            blocks, chars = process_data(item)
            results.extend(blocks)
            total_chars += chars
            
    elif isinstance(data, str):
        cleaned_text = data.strip()
        if cleaned_text:
            total_chars += len(cleaned_text)
            blocks = extract_blocks_with_window(cleaned_text, window_before=1, window_after=0)
            results.extend(blocks)
            
    filtered_results = [block for block in results if not should_filter_block(block)]
    
    return filtered_results, total_chars

def process_jsons():
    for filename in os.listdir(INPUT_DIR):
        if not filename.endswith(".json"):
            continue
            
        input_path = os.path.join(INPUT_DIR, filename)
        output_path = os.path.join(OUTPUT_DIR, f"entities_{filename}")
        
        with open(input_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                continue
                
        # 获取匹配的文本块和总字数
        matched_blocks, total_original_chars = process_data(data)
        
        # 计算提取出来的总字数
        total_extracted_chars = sum(len(block) for block in matched_blocks)
        
        # 计算比例并格式化为百分比字符串，保留两位小数
        extraction_ratio = "0.00%"
        if total_original_chars > 0:
            ratio = (total_extracted_chars / total_original_chars) * 100
            extraction_ratio = f"{ratio:.2f}%"
        
        # 按顺序构建最终的输出结构
        output_data = {
            "source_file": filename,
            "total_blocks_extracted": len(matched_blocks),
            "extraction_ratio": extraction_ratio,  # 新增的统计数据
            "entity_blocks": matched_blocks
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
            
        print(f"处理完成: {filename} -> 提取比例: {extraction_ratio}。")

if __name__ == "__main__":
    if not os.path.exists(INPUT_DIR):
        print(f"未找到输入目录 {INPUT_DIR}。")
    else:
        process_jsons()