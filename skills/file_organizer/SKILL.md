# File Organizer Skill

## 描述
文件组织和管理工具，提供文件分类、重命名、批量操作、重复文件查找、临时文件清理、文件统计分析等功能。

## 适用场景
- 整理下载文件夹
- 批量处理图片/文档
- 清理项目文件
- 文件系统维护
- 查找和删除重复文件
- 文件分类归档

## 输入参数

### 文件组织 (organize_files)
- `directory` (必需): 要处理的目录路径
- `operations` (必需): 要执行的操作列表
  - `categorize_by_type`: 按文件类型分类
  - `rename_by_pattern`: 按模式重命名文件
  - `find_duplicates`: 查找重复文件
  - `clean_temp_files`: 清理临时文件
  - `analyze_files`: 分析文件统计信息
  - `move_to_target`: 移动到目标目录（需指定target_dir）
  - `copy_to_target`: 复制到目标目录（需指定target_dir）
- `file_pattern` (可选): 文件模式（如 *.txt, *.jpg）
- `target_dir` (可选): 目标目录路径（用于移动/复制操作）

## 输出

### 返回结果
- `success`: 操作是否成功
- `directory`: 处理的目录
- `total_files`: 总文件数
- `operations_performed`: 执行的操作列表
- `files_processed`: 处理的文件信息列表
  - `path`: 文件路径
  - `operation`: 执行的操作
  - `category`: 文件类别（分类时）
  - `original_path`: 原始路径（移动/重命名时）
  - `new_name`: 新文件名（重命名时）
  - `status`: 状态（重复文件查找时）
  - `hash`: 文件哈希（重复文件查找时）
- `total_size_bytes`: 总文件大小（字节）
- `total_size_mb`: 总文件大小（MB）

### 特定操作额外返回
- `categorize_by_type`: `categories`（类别数量）, `category_counts`（各类别文件数）
- `find_duplicates`: `duplicate_count`（重复文件数）, `unique_count`（唯一文件数）, `duplicate_groups`（重复文件组）
- `clean_temp_files`: `cleaned_count`（清理的文件数）
- `analyze_files`: `file_types`（文件类型统计）
- `move_to_target`: `moved_count`（移动的文件数）
- `copy_to_target`: `copied_count`（复制的文件数）

## 使用示例

### 示例1: 按类型分类文件
```json
{
  "directory": "/path/to/downloads",
  "operations": ["categorize_by_type", "analyze_files"]
}
```

### 示例2: 查找重复文件
```json
{
  "directory": "/path/to/photos",
  "operations": ["find_duplicates"],
  "file_pattern": "*.jpg"
}
```

### 示例3: 清理临时文件并重命名
```json
{
  "directory": "/path/to/project",
  "operations": ["clean_temp_files", "rename_by_pattern"],
  "target_dir": "/path/to/backup"
}
```

### 示例4: 移动特定类型文件
```json
{
  "directory": "/path/to/documents",
  "operations": ["move_to_target"],
  "file_pattern": "*.pdf",
  "target_dir": "/path/to/pdf_archive"
}
```