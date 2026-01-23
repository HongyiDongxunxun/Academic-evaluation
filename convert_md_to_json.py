import os
import json

# 定义源目录和目标目录
source_dir = r'D:\code\cleandata'
target_dir = r'D:\code\评价目录\json_data'

# 确保目标目录存在
if not os.path.exists(target_dir):
    os.makedirs(target_dir)

# 遍历源目录下的所有markdown文件
for file_name in os.listdir(source_dir):
    if file_name.endswith('.md'):
        file_path = os.path.join(source_dir, file_name)
        json_file_name = os.path.splitext(file_name)[0] + '.json'
        json_file_path = os.path.join(target_dir, json_file_name)
        
        try:
            # 读取markdown文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析内容，提取标题和对应内容
            lines = content.strip().split('\n')
            json_data = {}
            current_title = "nothing"
            current_content = []
            
            # 遍历所有行，识别标题和内容
            for line in lines:
                stripped_line = line.strip()
                # 检查是否是标题行（以#开头）
                if stripped_line.startswith('#'):
                    # 如果已有内容，保存当前标题和内容
                    if current_content:
                        # 合并当前内容行
                        content_text = '\n'.join(current_content).strip()
                        # 按"\n\n"分割段落
                        paragraphs = content_text.split('\n\n')
                        # 创建段落字典
                        paragraph_dict = {}
                        for i, para in enumerate(paragraphs):
                            if para.strip():  # 跳过空段落
                                paragraph_dict[f"context{i+1}"] = para.strip()
                        # 如果没有段落，直接保存内容
                        if paragraph_dict:
                            json_data[current_title] = paragraph_dict
                        else:
                            json_data[current_title] = content_text
                        current_content = []
                    # 提取新标题（去除所有#和空格）
                    current_title = stripped_line.lstrip('#').strip()
                else:
                    # 非标题行，添加到当前内容
                    current_content.append(line)
            
            # 保存最后一个标题和内容
            if current_content:
                # 合并当前内容行
                content_text = '\n'.join(current_content).strip()
                # 按"\n\n"分割段落
                paragraphs = content_text.split('\n\n')
                # 创建段落字典
                paragraph_dict = {}
                for i, para in enumerate(paragraphs):
                    if para.strip():  # 跳过空段落
                        paragraph_dict[f"context{i+1}"] = para.strip()
                # 如果没有段落，直接保存内容
                if paragraph_dict:
                    json_data[current_title] = paragraph_dict
                else:
                    json_data[current_title] = content_text
            
            # 如果没有任何标题，使用默认标题
            if not json_data:
                json_data["nothing"] = content
            
            # 写入JSON文件
            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            
            print(f"已转换: {file_name} -> {json_file_name}")
        
        except Exception as e:
            print(f"处理文件时出错: {file_name}")
            print(f"错误信息: {str(e)}")

print("所有markdown文件转换完成！")