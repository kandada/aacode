# Data Converter Skill

## 描述
提供数据格式转换能力，支持JSON/YAML/CSV/XML等常见格式之间的互相转换。

## 适用场景
- 数据格式转换
- 配置文件格式转换
- 数据导入导出
- API数据格式适配

## 输入参数
- `input_path`: 输入文件路径
- `output_path`: 输出文件路径
- `input_format`: 输入格式（自动检测或指定）
- `output_format`: 输出格式
- `options`: 转换选项（如缩进、编码等）

## 输出
返回转换后的文件路径和统计信息

## 使用示例
```json
{
  "input_path": "config.yaml",
  "output_path": "config.json",
  "input_format": "yaml",
  "output_format": "json"
}
```
