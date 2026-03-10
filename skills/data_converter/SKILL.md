# Data Converter Skill

## 描述
数据格式转换工具，支持JSON/YAML/CSV/XML等格式互转。

## 调用示例：
Action: convert_format
Action Input: {"input_path": "config.yaml", "output_path": "config.json", "output_format": "json"}

## 输入参数

- `input_path` (str, 必需): 输入文件路径
- `output_path` (str, 必需): 输出文件路径
- `input_format` (str, 可选): 输入格式
- `output_format` (str, 必需): 输出格式 [json, yaml, csv, xml]
- `options` (dict, 可选): 转换选项

## 输出
- `success`: 是否成功
- `output_path`: 输出文件路径
- `file_size`: 文件大小
