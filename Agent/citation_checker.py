import os
import json
import re

class CitationChecker:
    def __init__(self, input_folder, output_folder):
        self.input_folder = input_folder
        self.output_folder = output_folder
        # 正则表达式匹配引文格式问题，如"[1"、"[]"、"[\s*]"等
        self.citation_pattern = re.compile(r'\[\s*\d*\s*[^\]]*$|\[\s*\]|\[[^\]]*\s*\d+\s*[^\]]*$')
    
    def check_citation_format(self, content):
        """
        检查内容中是否存在引文格式问题
        
        Args:
            content: 要检查的内容
            
        Returns:
            bool: 如果存在问题返回True，否则返回False
        """
        # 将内容转换为字符串以便检查
        content_str = str(content)
        # 查找匹配的引文格式问题
        matches = self.citation_pattern.findall(content_str)
        return len(matches) > 0
    
    def check_file(self, file_path):
        """
        检查单个文件是否存在引文格式问题
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: 如果存在问题返回True，否则返回False
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 检查整个文件内容
            return self.check_citation_format(data)
        except Exception as e:
            print(f"处理文件 {file_path} 时出错: {e}")
            # 如果文件无法正常读取，也视为有问题
            return True
    
    def process_files(self):
        """
        处理所有文件，将有问题的文件移动到输出文件夹
        """
        # 获取所有json文件
        json_files = [f for f in os.listdir(self.input_folder) if f.endswith('.json')]
        total_files = len(json_files)
        error_files = 0
        
        print(f"开始检查 {total_files} 个JSON文件...")
        
        for filename in json_files:
            input_file_path = os.path.join(self.input_folder, filename)
            output_file_path = os.path.join(self.output_folder, filename)
            
            # 检查文件是否存在引文格式问题
            if self.check_file(input_file_path):
                # 移动文件
                try:
                    os.rename(input_file_path, output_file_path)
                    error_files += 1
                    print(f"已移动有问题的文件: {filename}")
                except Exception as e:
                    print(f"移动文件 {filename} 时出错: {e}")
        
        print(f"检查完成！共检查 {total_files} 个文件，发现 {error_files} 个文件存在引文格式问题，已移动到 {self.output_folder}")
        return error_files

# 示例用法
if __name__ == "__main__":
    # 配置输入输出文件夹路径
    input_folder = "../json_data"
    output_folder = "../error_data"
    
    # 创建检查器实例
    checker = CitationChecker(input_folder, output_folder)
    
    # 处理文件
    checker.process_files()
