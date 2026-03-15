import os
import json

# 定义文件夹路径
key_judge_dir = 'key_judge'
full_dir = 'all_json_iter2'

# 获取所有key_judge文件
key_judge_files = [f for f in os.listdir(key_judge_dir) if f.startswith('key_judge_') and f.endswith('.json')]

for key_file in key_judge_files:
    # 提取数字部分
    num = key_file.split('_')[-1].split('.')[0]
    full_file = f'full_{num}.json'
    
    # 构建文件路径
    key_path = os.path.join(key_judge_dir, key_file)
    full_path = os.path.join(full_dir, full_file)
    
    # 检查full文件是否存在
    if not os.path.exists(full_path):
        print(f"Warning: {full_file} does not exist")
        continue
    
    # 读取key_judge文件
    with open(key_path, 'r', encoding='utf-8') as f:
        key_data = json.load(f)
    
    # 读取full文件
    with open(full_path, 'r', encoding='utf-8') as f:
        full_data = json.load(f)
    
    # 需要删除的键
    keys_to_delete = []
    
    # 检查每个键
    for key, value in key_data.items():
        if value == 'False' or value == 'References':
            if key in full_data:
                keys_to_delete.append(key)
    
    # 删除键
    for key in keys_to_delete:
        del full_data[key]
    
    # 写回full文件
    with open(full_path, 'w', encoding='utf-8') as f:
        json.dump(full_data, f, ensure_ascii=False, indent=4)
    
    print(f"Processed {full_file}: deleted {len(keys_to_delete)} keys")

print("Processing complete!")