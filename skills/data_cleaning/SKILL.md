# Data Cleaning Skill

## 描述
数据清洗工具，处理缺失值、去除重复项、数据格式标准化等。

## 调用示例：
Action: clean_data
Action Input: {"file_path": "data.csv", "operations": ["remove_duplicates", "normalize_text"]}

## 输入参数

- `file_path` (str, 必需): 数据文件路径(CSV)
- `operations` (list, 必需): 操作列表
  - `remove_duplicates`: 去除重复行
  - `fill_missing`: 填充缺失值(需指定method)
  - `normalize_text`: 标准化文本
  - `remove_outliers`: 移除异常值
  - `convert_types`: 类型转换
- `output_path` (str, 可选): 输出路径

## 输出
- `success`: 是否成功
- `file_path`: 处理后的文件
- `operations_performed`: 执行的操作
- `stats`: 统计信息
