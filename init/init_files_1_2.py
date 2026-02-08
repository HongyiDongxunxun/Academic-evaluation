import os
import shutil
from concurrent.futures import ThreadPoolExecutor

def copy_file(args):
    src, dst = args
    shutil.copy2(src, dst)

def reset_and_copy(src_dir, dst_dir):
    # 1. 检查源文件夹
    if not os.path.exists(src_dir):
        print(f"[错误] 源文件夹不存在: {src_dir}")
        return

    src_files = [f for f in os.listdir(src_dir) if f.endswith('.json')]
    total_files = len(src_files)
    print(f"源文件夹 ({src_dir}) 共有文件: {total_files}")

    # 2. 重置目标文件夹 (强制清空再重建，确保没有残留)
    if os.path.exists(dst_dir):
        print(f"正在清空目标文件夹: {dst_dir} ...")
        shutil.rmtree(dst_dir) # 彻底删除文件夹
    
    os.makedirs(dst_dir)
    print(f"已创建空文件夹: {dst_dir}")

    # 3. 多线程复制 (比手动复制更快更稳)
    print(f"开始复制 {total_files} 个文件...")
    
    tasks = []
    for f in src_files:
        src_path = os.path.join(src_dir, f)
        dst_path = os.path.join(dst_dir, f)
        tasks.append((src_path, dst_path))

    # 使用多线程加速IO操作
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(copy_file, tasks))

    # 4. 最终校验
    dst_files = [f for f in os.listdir(dst_dir) if f.endswith('.json')]
    print(f"\n复制完成！")
    print(f"目标文件夹 ({dst_dir}) 现有文件: {len(dst_files)}")
    
    if len(dst_files) == total_files:
        print("✅ 文件数量一致，可以开始运行清洗脚本了。")
    else:
        print("❌ 文件数量不一致，请检查磁盘空间或权限。")

if __name__ == "__main__":
    # 确保这里是您的文件夹名称
    reset_and_copy('all_json_iter1', 'all_json_iter2')