# 硅基流动AI Agent

一个基于硅基流动API的AI Agent，支持prompt接口和读取文件夹中的JSON文件。

## 功能特性

1. **Prompt接口**：直接调用硅基流动API生成文本完成
2. **JSON文件读取**：支持读取指定文件夹中的所有JSON文件
3. **上下文增强**：可结合JSON文件内容生成更智能的回复

## 安装依赖

```bash
# 项目依赖已经包含在requirements.txt中
pip install -r requirements.txt
```

## 快速开始

### 1. 配置API密钥

在使用前，需要获取硅基流动API密钥，并在代码中配置：

```python
from silicon_flow_agent import SiliconFlowAgent

# 替换为您的硅基流动API密钥
api_key = "your_api_key_here"
agent = SiliconFlowAgent(api_key)
```

### 2. 直接使用Prompt接口

```python
# 生成文本完成（直接传入字符串）
result = agent.generate_completion("请解释什么是映射消歧")
print(result)

# 生成文本完成（从txt文件读取prompt）
result = agent.generate_completion("./prompt.txt")
print(result)
```

### 3. 读取JSON文件

```python
# 读取指定文件夹中的所有JSON文件
json_data = agent.read_json_files("./data")
print(f"读取到 {len(json_data)} 个JSON文件")
```

### 4. 结合上下文生成

```python
# 读取JSON文件作为上下文
json_data = agent.read_json_files("./data")

# 结合上下文生成回复
result = agent.generate_completion_with_context(
    "请基于提供的上下文信息，总结映射消歧的主要方法",
    json_data
)
print(result)
```

## 类和方法说明

### SiliconFlowAgent类

#### 初始化
```python
SiliconFlowAgent(api_key, base_url="https://api.siliconflow.cn/v1")
```
- `api_key`：硅基流动API密钥
- `base_url`：API基础URL（默认值已配置）

#### generate_completion方法
```python
generate_completion(prompt, model="Qwen/Qwen2.5-72B-Instruct", temperature=0.7, max_tokens=1024)
```
- `prompt`：提示词字符串或txt文件路径
- `model`：使用的模型（默认：Qwen/Qwen2.5-72B-Instruct）
- `temperature`：生成温度（0-1，默认：0.7）
- `max_tokens`：最大生成token数（默认：1024）

#### read_json_files方法
```python
read_json_files(folder_path)
```
- `folder_path`：文件夹路径
- 返回：字典，键为文件名，值为JSON内容

#### generate_completion_with_context方法
```python
generate_completion_with_context(prompt, context_files, model="Qwen/Qwen2.5-72B-Instruct", temperature=0.7, max_tokens=1024)
```
- `prompt`：提示词
- `context_files`：上下文文件内容（从read_json_files获取）
- `model`：使用的模型
- `temperature`：生成温度
- `max_tokens`：最大生成token数

## 示例用法

运行示例脚本：

```bash
python example_usage.py
```

## 文件结构

```
Agent/
├── silicon_flow_agent.py  # 主Agent类
├── example_usage.py       # 示例用法
├── requirements.txt       # 依赖列表
└── README.md             # 说明文档
```

## 注意事项

1. 请确保您的API密钥安全，不要泄露给他人
2. 大量调用API可能产生费用，请合理使用
3. 建议将API密钥存储在环境变量中，而不是硬编码在代码中
4. 处理大型JSON文件时，请注意内存使用情况

## 下一步工作

您可以：
1. 根据需要修改prompt模板，优化生成效果
2. 扩展Agent功能，支持更多文件类型
3. 结合您的具体业务场景，开发更复杂的应用
4. 添加错误处理和日志记录，提高系统稳定性
