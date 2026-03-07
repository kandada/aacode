# Skills 配置指南

## 概述

Skills（技能）是aacode的可扩展能力模块，允许用户通过配置文件启用和使用预定义的数据处理能力。每个Skill都是独立的，包含详细的文档说明（`SKILL.md`）和可执行的Python实现。

**特点**：
- 只需在 `aacode_config.yaml` 中配置即可使用
- Agent会自动发现并列出可用的Skills
- 支持动态启用/禁用，无需修改代码

```
project/
├── skills/                    # Skills根目录
│   ├── data_cleaning/         # 数据清洗技能
│   │   ├── SKILL.md          # 技能说明文档
│   │   └── clean_csv.py      # 技能实现
│   ├── api_client/           # API客户端技能
│   │   ├── SKILL.md
│   │   └── call_api.py
│   └── data_converter/       # 数据转换技能
│       ├── SKILL.md
│       └── convert_data.py
└── aacode_config.yaml        # 主配置文件
```

## 配置方法

### 1. 在 `aacode_config.yaml` 中配置

```yaml
# Skills配置
skills:
  # 是否启用skills功能
  enabled: true
  
  # Skills目录（相对于项目根目录）
  skills_dir: skills
  
  # 是否自动发现skills目录下的技能
  auto_discover: true
  
  # 启用的skills列表（skills目录下的子目录名）
  enabled_skills:
    - data_cleaning
    - api_client
    - data_converter
```

### 2. 配置项说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enabled` | bool | `true` | 是否启用skills功能 |
| `skills_dir` | str | `skills` | Skills目录路径（相对于项目根目录） |
| `auto_discover` | bool | `true` | 是否自动发现和加载skills |
| `enabled_skills` | list | 见默认配置 | 启用的skills名称列表 |

## 内置Skills

### 1. 数据清洗技能 (data_cleaning)

**功能**：清洗CSV数据文件，支持多种清洗操作

**参数**：
- `file_path` (必需): CSV文件路径
- `operations` (必需): 操作列表
  - `remove_duplicates`: 去除重复行
  - `fill_missing`: 填充缺失值
  - `normalize_text`: 标准化文本
  - `remove_outliers`: 移除异常值
  - `convert_types`: 类型转换
- `output_path` (可选): 输出路径
- `missing_method` (可选): 缺失值填充方法
- `outlier_columns` (可选): 异常值检测列
- `outlier_threshold` (可选): 异常值阈值

**使用示例**：
```json
{
  "file_path": "data/raw_data.csv",
  "operations": ["remove_duplicates", "normalize_text"],
  "output_path": "data/cleaned_data.csv"
}
```

### 2. API客户端技能 (api_client)

**功能**：发送HTTP请求，支持RESTful API调用

**参数**：
- `method` (必需): HTTP方法（GET/POST/PUT/DELETE）
- `url` (必需): 请求URL
- `headers` (可选): 请求头
- `data` (可选): 请求数据
- `params` (可选): URL参数
- `timeout` (可选): 超时时间（秒）
- `retry_count` (可选): 重试次数

**使用示例**：
```json
{
  "method": "GET",
  "url": "https://api.github.com/repos/python/cpython",
  "headers": {"Authorization": "Bearer token123"}
}
```

### 3. 数据转换技能 (data_converter)

**功能**：在JSON/YAML/CSV/XML格式之间转换数据

**参数**：
- `input_path` (必需): 输入文件路径
- `output_path` (必需): 输出文件路径
- `input_format` (可选): 输入格式
- `output_format` (可选): 输出格式
- `encoding` (可选): 文件编码

**使用示例**：
```json
{
  "input_path": "config.yaml",
  "output_path": "config.json",
  "input_format": "yaml",
  "output_format": "json"
}
```

## 自定义Skills

### 1. 创建新的Skill

在 `skills/` 目录下创建新目录：

```
skills/
└── my_custom_skill/
    ├── SKILL.md      # 技能文档
    └── do_something.py  # 技能实现
```

### 2. 编写SKILL.md

```markdown
# My Custom Skill

## 描述
简要描述这个技能的用途

## 适用场景
列出适用场景

## 输入参数
说明输入参数

## 输出
说明返回结果

## 使用示例
提供JSON示例
```

### 3. 编写实现文件

```python
"""
技能实现
"""

async def do_something(param1: str, param2: int = 10) -> dict:
    """
    技能主函数

    Args:
        param1: 参数1说明
        param2: 参数2说明

    Returns:
        返回结果字典
    """
    # 实现逻辑
    return {"success": True, "result": "..."}
```

**注意**：
- 主函数名建议以 `clean_`, `call_`, `convert_`, `process_` 开头
- 函数必须是 `async` 函数
- 返回值必须是 `dict` 类型，包含 `success` 字段

### 4. 启用自定义Skill

在 `aacode_config.yaml` 中添加：

```yaml
skills:
  enabled_skills:
    - my_custom_skill
    - data_cleaning
    - api_client
    - data_converter
```

## 注意事项

1. **Skill名称**：在 `aacode_config.yaml` 中配置的名称必须与 `skills/` 下的目录名完全一致
2. **文件路径**：建议使用相对路径，相对于项目根目录
3. **依赖安装**：某些Skill可能需要额外的Python包，确保已安装
4. **性能考虑**：大数据量处理时请注意超时设置
5. **安全性**：处理外部数据时注意安全，避免注入攻击

## 故障排除

### Skill未加载
- 检查 `enabled` 是否为 `true`
- 检查 `enabled_skills` 列表中是否包含该Skill
- 检查Skill目录是否存在 `SKILL.md` 文件
- 检查实现文件是否有语法错误

### Skill执行失败
- 检查参数是否正确
- 检查输入文件是否存在
- 查看错误信息日志

### 权限问题
- 确保项目目录有读写权限
- 确保配置文件有执行权限
