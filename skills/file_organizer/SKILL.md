# File Organizer Skill

## 描述
文件组织和管理工具，提供文件分类、重命名、批量操作等功能。

## 调用示例：
Action: organize_files
Action Input: {"directory": "/path/to/downloads", "operations": ["categorize_by_type"]}

## 输入参数

- `directory` (str, 必需): 要处理的目录
- `operations` (list, 必需): 操作列表
  - `categorize_by_type`: 按类型分类
  - `rename_by_pattern`: 按模式重命名
  - `find_duplicates`: 查找重复文件
  - `clean_temp_files`: 清理临时文件
  - `analyze_files`: 文件统计分析
  - `move_to_target`: 移动文件
  - `copy_to_target`: 复制文件
- `file_pattern` (str, 可选): 文件模式
- `target_dir` (str, 可选): 目标目录

## 输出
- `success`: 是否成功
- `total_files`: 文件总数
- `operations_performed`: 执行的操作
