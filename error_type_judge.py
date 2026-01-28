'''
json文件中所有可能出现的小标题种类（序号与文字间可能存在空格）
    0引言
    1 小标题
    1. 小标题
    1、小标题
    1。小标题
    一、小标题
    ●小标题
    一
    1)
    
注意所有的小标题可能出现子标题
    1.1 子标题
    1.1.1 子子标题
    1.1.1.1 子子子标题

'''

'''
    json文件中所有可能出现的参考文献小标题种类（冒号可能没有）
    参考文献：
    注：
    注释：
    注释与参考文献：
    [参考文献]

'''

import os
import json
import re
import shutil

# 定义小标题正则表达式模式
subtitle_patterns = [
    r'^0[^\d]',  # 0引言
    r'^\d+\s*[\.、。]?\s*',  # 数字开头的小标题（如1、1.、1、、1。）
    r'^[一二三四五六七八九十]+\s*[、．]?\s*',  # 中文数字开头的小标题（如一、）
    r'^●\s*',  # ●开头的小标题
    r'^[一二三四五六七八九十]+$',  # 单独的中文数字（如一）
    r'^\d+\)\s*'  # 数字加括号（如1)）
]

# 参考文献小标题模式
reference_patterns = [
    r'^参考文献[：:]?',
    r'^注[：:]?',
    r'^注释[：:]?',
    r'^注释与参考文献[：:]?',
    r'^\[参考文献\]'
]

# 上接xx页模式
page_mixed_pattern = r'^（上接.*页）$'

# Publication_Mixed模式（·xxx·形式）
publication_mixed_pattern = r'^·.*·$'

# Year_Mixed模式（3个及以上数字黏在一起，且前面没有空格）
year_mixed_pattern = r'(?<!\s)\d{3,}'

# 创建结果文件夹
def create_output_dirs(base_dir):
    types = ['Num_Mistake', 'Page_Mixed', 'Initially_Unstructured', 'Title_Mixed', 'Plausibly_Structured']
    for type_name in types:
        type_dir = os.path.join(base_dir, type_name)
        os.makedirs(type_dir, exist_ok=True)

# 检查是否是小标题
def is_subtitle(text):
    for pattern in subtitle_patterns:
        if re.search(pattern, text):
            return True
    # 检查参考文献小标题
    for pattern in reference_patterns:
        if re.search(pattern, text):
            return True
    return False

# 提取小标题的数字部分
def extract_number_part(text):
    # 提取数字序列（如1.1.1）
    num_pattern = r'^(\d+(?:\.\d+)*)'
    match = re.match(num_pattern, text)
    if match:
        return match.group(1)
    # 提取中文数字
    chinese_num_pattern = r'^([一二三四五六七八九十]+)'
    match = re.match(chinese_num_pattern, text)
    if match:
        return match.group(1)
    return None

# 检查是否存在跳过现象
def check_skip_phenomenon(subtitles):
    if len(subtitles) < 2:
        return False
    
    for i in range(len(subtitles) - 1):
        current = subtitles[i]
        next_sub = subtitles[i + 1]
        
        current_num = extract_number_part(current)
        next_num = extract_number_part(next_sub)
        
        if current_num and next_num:
            # 检查是否都是数字序列
            if re.match(r'^\d+(?:\.\d+)*$', current_num) and re.match(r'^\d+(?:\.\d+)*$', next_num):
                # 转换为数字列表
                current_parts = list(map(int, current_num.split('.')))
                next_parts = list(map(int, next_num.split('.')))
                
                # 检查层级
                if len(current_parts) == len(next_parts):
                    # 同级标题，检查是否连续
                    if next_parts[-1] != current_parts[-1] + 1:
                        return True
                elif len(next_parts) == len(current_parts) + 1:
                    # 下一级标题，应该从1开始
                    if next_parts[-1] != 1:
                        return True
                # 不同层级但不是下一级，不视为跳过
    return False

# 检查是否是Title_Mixed
def check_title_mixed(subtitles):
    if len(subtitles) < 2:
        return False
    
    # 检查是否有不同格式的标题混合
    has_chinese_num = False
    has_arabic_num = False
    
    for subtitle in subtitles:
        if re.match(r'^[一二三四五六七八九十]+', subtitle):
            has_chinese_num = True
        if re.match(r'^\d+', subtitle):
            has_arabic_num = True
        
        if has_chinese_num and has_arabic_num:
            return True
    
    return False

# 检查文件类型
def check_file_type(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return 'Initially_Unstructured'
    
    # 获取所有顶层键（包括第一层键）
    all_keys = []
    for key, value in data.items():
        all_keys.append(key)
        if isinstance(value, dict):
            all_keys.extend(value.keys())
    
    # 条件(4)：检查是否有（上接xx页）
    for key in all_keys:
        if re.match(page_mixed_pattern, key):
            return 'Page_Mixed'
    
    # 过滤出小标题（从第一个符合格式的开始）
    valid_subtitles = []
    found_first = False
    for key in all_keys:
        if is_subtitle(key):
            found_first = True
            valid_subtitles.append(key)
        elif found_first:
            # 找到第一个小标题后，忽略不符合格式的键
            continue
    
    # 条件(5)：完全没有小标题
    if not valid_subtitles:
        return 'Initially_Unstructured'
    
    # 条件(6)：检查是否是Title_Mixed
    if check_title_mixed(valid_subtitles):
        return 'Title_Mixed'
    
    # 条件(2)：检查是否有跳过现象
    if check_skip_phenomenon(valid_subtitles):
        return 'Num_Mistake'
    
    # 条件(7)：默认情况
    return 'Plausibly_Structured'

import csv

# 主函数
def main():
    # 输入文件夹
    input_folders = ['json_data', 'error_data']
    # 输出CSV文件
    output_csv = 'strucheck_1.csv'
    
    # 定义CSV表头，将Plausibly_Structured放在最后
    headers = ['filename', 'Num_Mistake', 'Page_Mixed', 'Initially_Unstructured', 'Title_Mixed', 'Publication_Mixed', 'Year_Mixed', 'Mutiple_References', 'Plausibly_Structured']
    
    # 收集所有文件信息
    all_files_info = []
    
    # 处理每个输入文件夹
    for input_folder in input_folders:
        if not os.path.exists(input_folder):
            print(f"文件夹 {input_folder} 不存在，跳过")
            continue
        
        # 处理文件夹中的每个文件
        for filename in os.listdir(input_folder):
            if not filename.endswith('.json'):
                continue
            
            file_path = os.path.join(input_folder, filename)
            
            # 检查所有可能的问题
            file_info = {
                'filename': filename,
                'Num_Mistake': 0,
                'Page_Mixed': 0,
                'Initially_Unstructured': 0,
                'Title_Mixed': 0,
                'Publication_Mixed': 0,
                'Year_Mixed': 0,
                'Mutiple_References': 0,
                'Plausibly_Structured': 0
            }
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                file_info['Initially_Unstructured'] = 1
                all_files_info.append(file_info)
                continue
            
            # 获取所有顶层键和第二层键
            all_keys = []
            for key, value in data.items():
                all_keys.append(key)
                if isinstance(value, dict):
                    all_keys.extend(value.keys())
            
            # 忽略最早读到的键
            if len(all_keys) >= 2:
                # 检查第二个键是否是·xxx·形式
                if re.match(publication_mixed_pattern, all_keys[1]):
                    # 忽略前三个键
                    if len(all_keys) > 3:
                        all_keys = all_keys[3:]
                else:
                    # 忽略前两个键
                    all_keys = all_keys[2:]
            
            # 检查Page_Mixed
            page_mixed_found = False
            for key in all_keys:
                if re.match(page_mixed_pattern, key):
                    file_info['Page_Mixed'] = 1
                    page_mixed_found = True
                    break
            
            # 检查Publication_Mixed
            for key in all_keys:
                if re.match(publication_mixed_pattern, key):
                    file_info['Publication_Mixed'] = 1
                    break
            
            # 检查Year_Mixed
            for key in all_keys:
                if re.search(year_mixed_pattern, key):
                    file_info['Year_Mixed'] = 1
                    break
            
            # 检查Mutiple_References
            reference_count = 0
            for key in all_keys:
                for pattern in reference_patterns:
                    if re.search(pattern, key):
                        reference_count += 1
                        break
            if reference_count >= 2:
                file_info['Mutiple_References'] = 1
            
            # 过滤出小标题
            valid_subtitles = []
            found_first = False
            for key in all_keys:
                if is_subtitle(key):
                    found_first = True
                    valid_subtitles.append(key)
                elif found_first:
                    continue
            
            # 检查Initially_Unstructured
            if not valid_subtitles:
                file_info['Initially_Unstructured'] = 1
                all_files_info.append(file_info)
                continue
            
            # 检查Title_Mixed
            if check_title_mixed(valid_subtitles):
                file_info['Title_Mixed'] = 1
            
            # 检查Num_Mistake
            if check_skip_phenomenon(valid_subtitles):
                file_info['Num_Mistake'] = 1
            
            # 如果没有其他问题，标记为Plausibly_Structured
            if not any([file_info['Num_Mistake'], file_info['Page_Mixed'], file_info['Initially_Unstructured'], file_info['Title_Mixed'], file_info['Publication_Mixed'], file_info['Year_Mixed'], file_info['Mutiple_References']]):
                file_info['Plausibly_Structured'] = 1
            
            all_files_info.append(file_info)
            print(f"处理文件: {filename}")
    
    # 提取文件名中的数字部分用于排序
    def extract_number(filename):
        import re
        match = re.search(r'full_(\d+)\.json', filename)
        if match:
            return int(match.group(1))
        match = re.search(r'full_(\d+)', filename)
        if match:
            return int(match.group(1))
        match = re.search(r'(\d+)', filename)
        if match:
            return int(match.group(1))
        return 0
    
    # 按文件名数字部分升序排序
    all_files_info.sort(key=lambda x: extract_number(x['filename']))
    
    # 统计各类问题的数量
    total_files = len(all_files_info)
    counts = {
        'Num_Mistake': 0,
        'Page_Mixed': 0,
        'Initially_Unstructured': 0,
        'Title_Mixed': 0,
        'Publication_Mixed': 0,
        'Year_Mixed': 0,
        'Mutiple_References': 0,
        'Plausibly_Structured': 0
    }
    
    for file_info in all_files_info:
        for category in counts.keys():
            if file_info[category] == 1:
                counts[category] += 1
    
    # 计算比例并打印
    print("\n===== 各类问题比例 =====")
    for category, count in counts.items():
        if total_files > 0:
            percentage = (count / total_files) * 100
            print(f"{category}: {count} ({percentage:.2f}%)")
        else:
            print(f"{category}: 0 (0.00%)")
    print(f"总计: {total_files} 文件")
    
    # 写入CSV文件
    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=headers)
        writer.writeheader()
        for file_info in all_files_info:
            writer.writerow(file_info)
    
    print(f"\nCSV文件已生成: {output_csv}")
    print("文件按文件名升序排序")

if __name__ == "__main__":
    main()

