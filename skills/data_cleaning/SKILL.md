# Data Cleaning Skill

## 描述
提供数据清洗功能，包括处理缺失值、去除重复项、数据格式标准化、异常值检测等。

## 适用场景
- 清洗CSV/Excel数据文件
- 处理用户导入的数据
- 数据预处理 pipeline
- 数据质量检查

## 输入参数
- `file_path`: 数据文件路径（CSV格式）
- `operations`: 要执行的操作列表
  - `remove_duplicates`: 去除重复行
  - `fill_missing`: 填充缺失值（需指定method）
  - `normalize_text`: 标准化文本（去除前后空格、统一大小写）
  - `remove_outliers`: 移除异常值（需指定columns和threshold）
  - `convert_types`: 类型转换
- `output_path`: 输出文件路径（可选，默认覆盖原文件）

## 输出
返回清洗后的数据统计和操作结果

## 使用示例
```json
{
  "file_path": "data/raw_data.csv",
  "operations": ["remove_duplicates", "normalize_text"],
  "output_path": "data/cleaned_data.csv"
}
```
