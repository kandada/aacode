# 工具Schema定义
# utils/tool_schemas.py
"""
为所有工具定义schema
包含参数说明、类型、示例等
"""

from utils.tool_registry import ToolSchema, ToolParameter

# ==================== Atomic Tools Schemas ====================

READ_FILE_SCHEMA = ToolSchema(
    name="read_file",
    description="读取文件内容。用于查看项目中的文件内容。支持读取整个文件或指定行范围。",
    parameters=[
        ToolParameter(
            name="path",
            type=str,
            required=True,
            description="文件的相对路径（相对于项目根目录）",
            example="src/main.py",
            aliases=["file", "filepath", "file_path", "filename"],
        ),
        ToolParameter(
            name="line_start",
            type=int,
            required=False,
            description="起始行号（从1开始，可选）。如果指定，只读取从此行开始的内容",
            example=10,
            aliases=["start", "start_line", "from_line"],
        ),
        ToolParameter(
            name="line_end",
            type=int,
            required=False,
            description="结束行号（包含，可选）。如果指定，只读取到此行的内容",
            example=50,
            aliases=["end", "end_line", "to_line"],
        ),
    ],
    examples=[
        {"path": "init.md"},
        {"path": "src/utils.py"},
        {"path": "README.md"},
        {"path": "api/main.py", "line_start": 55, "line_end": 65},
        {"path": "config.py", "line_start": 1, "line_end": 20},
    ],
    returns="返回字典，包含 success, path, content, size, lines 等字段。如果指定了行范围，还包含 line_range 和 total_lines",
)

WRITE_FILE_SCHEMA = ToolSchema(
    name="write_file",
    description="""写入文件内容。用于创建新文件或覆盖现有文件。
    
**增强功能**：
- 支持从上下文引用内容，节省token
- 两种使用方式：
  1. 直接提供内容：content="文件内容"
  2. 从上下文引用：source="引用标识符"
  
**source参数支持格式**：
- content:<直接内容> - 例如：source="content:Hello World"
- file:<文件路径> - 例如：source="file:existing.txt"
- 上下文文件名 - 例如：source="web_fetch_result"
- last_web_fetch - 最近web_fetch结果
- tool_result:fetch_url - fetch_url工具结果

**源文件过滤参数**（当使用source参数时）：
- source_start_line: 源文件起始行号（1-based）
- source_end_line: 源文件结束行号（1-based）
- source_pattern: 源文件正则表达式模式，只保留匹配的行 
- source_exclude_pattern: 源文件正则表达式模式，排除匹配的行 

**重要规则**：当使用source参数时，所有源文件过滤参数必须使用source_前缀。
             使用不带前缀的参数将触发警告。

**使用建议**：
- 当内容已经在上下文中时，使用source参数节省token
- 当需要生成新内容时，使用content参数
- 需要提取部分内容时，使用source参数配合过滤参数""",
    parameters=[
        ToolParameter(
            name="path",
            type=str,
            required=True,
            description="文件的相对路径（相对于项目根目录）",
            example="src/new_file.py",
            aliases=["file", "filepath", "file_path", "filename", "target"],
        ),
        ToolParameter(
            name="content",
            type=str,
            required=False,
            description="要写入的文件内容（与source二选一）",
            example="print('Hello, World!')",
            aliases=["data", "text", "body", "contents"],
        ),
        ToolParameter(
            name="source",
            type=str,
            required=False,
            description="内容来源标识符（与content二选一）",
            example="content:print('Hello') 或 last_web_fetch",
            aliases=["from", "src", "reference"],
        ),
        ToolParameter(
            name="source_start_line",
            type=int,
            required=False,
            description="源文件起始行号（1-based）。当使用source参数时，指定要提取的起始行。",
            example=1,
            aliases=[],
        ),
        ToolParameter(
            name="source_end_line",
            type=int,
            required=False,
            description="源文件结束行号（1-based，包含）。当使用source参数时，指定要提取的结束行。",
            example=10,
            aliases=[],
        ),
        ToolParameter(
            name="source_pattern",
            type=str,
            required=False,
            description="源文件正则表达式模式。当使用source参数时，只保留匹配此模式的行。",
            example="^def ",
            aliases=[],
        ),
        ToolParameter(
            name="source_exclude_pattern",
            type=str,
            required=False,
            description="源文件正则表达式模式。当使用source参数时，排除匹配此模式的行。",
            example="^#",
            aliases=[],
        ),
    ],
    examples=[
        {"path": "test.py", "content": "# Test file\nprint('test')"},
        {"path": "README.md", "content": "# My Project\n\nDescription here."},
        {"path": "result.html", "source": "content:<html>Hello</html>"},
        {"path": "copy.txt", "source": "file:original.txt"},
        {"path": "web_content.html", "source": "last_web_fetch"},
        {
            "path": "functions.txt",
            "source": "file:source.py",
            "source_start_line": 1,
            "source_end_line": 50,
            "source_pattern": "^def ",
        },
        {
            "path": "clean_code.py",
            "source": "file:original.py",
            "source_exclude_pattern": "^#",
        },
    ],
    returns="返回字典，包含 success, path, size, lines, source_used 等字段",
)

RUN_SHELL_SCHEMA = ToolSchema(
    name="run_shell",
    description="""执行shell命令 - 万能的系统命令执行工具

**核心理念**：
- 工具总是成功（success=True），除非工具本身异常
- 命令的成功/失败通过 returncode 判断（0=成功，非0=失败）
- 完整返回 stdout 和 stderr，让你自行判断如何处理

**常用场景**：
1. 文件操作：grep, glob, ls, cat, cp, mv, mkdir, rm, find, nano, vim
2. 包管理：pip install, npm install, apt-get install, brew
3. 代码执行：python script.py, node app.js, bash run.sh
4. 测试运行：pytest, npm test, python -m unittest
5. 版本检查：python --version, node --version, git --version
6. 进程管理：ps aux, kill, pkill
7. 网络操作：curl, wget, ping
8. 系统信息：uname, df, du, free

**重要提示**：
- returncode=0 表示命令成功
- returncode≠0 不一定是错误（如 grep 没找到匹配返回1是正常的）
- 检查 stderr 判断是否有真正的错误
- 支持管道、重定向等 shell 特性：command1 | command2, command > file.txt
- 命令在项目目录下执行，使用相对路径即可

**安全限制**：
- 危险命令要谨慎（如 rm -rf /）
- 绝对路径必须在项目范围内
- 某些系统命令可能被限制""",
    parameters=[
        ToolParameter(
            name="command",
            type=str,
            required=True,
            description="要执行的shell命令（支持管道、重定向等shell特性）",
            example='python -c "import sys; print(sys.version)"',
            aliases=["cmd", "shell", "script", "exec"],
        ),
        ToolParameter(
            name="timeout",
            type=int,
            required=False,
            default=30,
            description="命令执行超时时间（秒），默认30秒。长时间运行的命令建议增加",
            example=60,
            aliases=["time_limit", "max_time", "wait"],
        ),
    ],
    examples=[
        {"command": "ls -la", "description": "列出当前目录所有文件（包括隐藏文件）"},
        {"command": "pwd", "description": "显示当前工作目录"},
        {"command": "python --version", "description": "检查 Python 版本"},
        {"command": "python script.py", "description": "运行 Python 脚本"},
        {"command": "python -c \"print('Hello')\"", "description": "执行 Python 代码"},
        {"command": "pip list", "description": "列出已安装的包"},
        {
            "command": "pip install requests",
            "timeout": 60,
            "description": "安装 Python 包",
        },
        {"command": "pytest tests/", "description": "运行测试"},
        {"command": "cat file.txt", "description": "查看文件内容"},
        {"command": "grep 'pattern' file.txt", "description": "搜索文件内容"},
        {"command": "find . -name '*.py'", "description": "查找 Python 文件"},
        {"command": "ls -la | grep '.py'", "description": "列出 Python 文件"},
        {"command": "ls -la | grep '.py'", "description": "列出 Python 文件"},
    ],
    returns="""返回字典，包含以下字段：
- success (bool): 工具是否成功执行（总是True，除非工具本身异常）
- returncode (int): 命令退出码（0=成功，非0=失败）
- stdout (str): 标准输出
- stderr (str): 错误输出
- command (str): 执行的命令
- working_directory (str): 工作目录""",
)

LIST_FILES_SCHEMA = ToolSchema(
    name="list_files",
    description="列出项目中的文件。用于查看项目结构和查找文件。默认递归列出所有文件。支持两种模式：1) 仅列出文件（默认） 2) 搜索文件内容（当提供grep参数时）。",
    parameters=[
        ToolParameter(
            name="pattern",
            type=str,
            required=False,
            default="*",
            description="文件名匹配模式（支持通配符）。注意：不是路径(path)，而是文件名模式。默认'*'表示所有文件",
            example="*.py",
            aliases=["path", "file_pattern", "glob", "directory", "dir"],
        ),
        ToolParameter(
            name="max_results",
            type=int,
            required=False,
            default=100,
            description="返回的最大文件数量。注意：不支持max_depth，默认递归列出所有文件",
            example=50,
            aliases=["limit", "max", "count", "max_depth", "depth"],
        ),
        ToolParameter(
            name="grep",
            type=str,
            required=False,
            default=None,
            description="可选：搜索文件内容的关键词。如果提供，将搜索包含该关键词的文件（类似grep功能）",
            example="def test",
            aliases=["search", "query", "text", "keyword"],
        ),
    ],
    examples=[
        {},
        {"pattern": "*.py"},
        {"pattern": "*.md", "max_results": 20},
        {"pattern": "test_*.py"},
        {"path": "."},
        {"grep": "def test"},
        {"pattern": "*.py", "grep": "import requests"},
    ],
    returns="返回字典，包含 success, files (列表), count 等字段。如果提供了grep参数，files中的每个条目会包含匹配的行信息。",
)

SEARCH_FILES_SCHEMA = ToolSchema(
    name="search_files",
    description="在文件中搜索文本内容。用于查找包含特定内容的文件。",
    parameters=[
        ToolParameter(
            name="query",
            type=str,
            required=True,
            description="要搜索的文本内容（必需）",
            example="def main",
            aliases=["search", "text", "keyword", "term", "q"],
        ),
        ToolParameter(
            name="file_pattern",
            type=str,
            required=False,
            default="*.py",
            description="要搜索的文件类型模式",
            example="*.py",
            aliases=["pattern", "glob", "file_type"],
        ),
        ToolParameter(
            name="max_results",
            type=int,
            required=False,
            default=20,
            description="返回的最大结果数量",
            example=10,
            aliases=["limit", "max", "count"],
        ),
    ],
    examples=[
        {"query": "def main"},
        {"query": "import requests", "file_pattern": "*.py"},
        {"query": "TODO", "file_pattern": "*", "max_results": 50},
    ],
    returns="返回字典，包含 success, query, results (列表), count 等字段",
)


# ==================== Web Tools Schemas ====================

SEARCH_WEB_SCHEMA = ToolSchema(
    name="search_web",
    description="在网络上搜索信息。用于查找最新的技术文档、解决方案等。",
    parameters=[
        ToolParameter(
            name="query",
            type=str,
            required=True,
            description="搜索查询关键词",
            example="Python asyncio tutorial",
            aliases=["search", "keyword", "q", "term"],
        ),
        ToolParameter(
            name="max_results",
            type=int,
            required=False,
            default=5,
            description="返回的最大结果数量",
            example=10,
            aliases=["limit", "count", "num", "num_results"],
        ),
    ],
    examples=[
        {"query": "Python asyncio tutorial"},
        {"query": "Flask best practices", "max_results": 10},
    ],
    returns="返回字典，包含 success, query, results (列表) 等字段",
)

FETCH_URL_SCHEMA = ToolSchema(
    name="fetch_url",
    description="获取URL的内容。用于读取网页内容或API响应。",
    parameters=[
        ToolParameter(
            name="url",
            type=str,
            required=True,
            description="要获取的URL地址",
            example="https://example.com/api/data",
            aliases=["link", "uri", "address"],
        ),
        ToolParameter(
            name="timeout",
            type=int,
            required=False,
            default=10,
            description="请求超时时间（秒）",
            example=30,
            aliases=["time_limit", "max_time", "wait"],
        ),
    ],
    examples=[
        {"url": "https://api.github.com/repos/python/cpython"},
        {"url": "https://example.com/data.json", "timeout": 30},
    ],
    returns="返回字典，包含 success, url, content, status_code 等字段",
)


# ==================== Code Tools Schemas ====================

EXECUTE_PYTHON_SCHEMA = ToolSchema(
    name="execute_python",
    description="执行Python代码。用于测试代码片段或运行Python脚本。",
    parameters=[
        ToolParameter(
            name="code",
            type=str,
            required=True,
            description="要执行的Python代码",
            example="print('Hello, World!')",
            aliases=["script", "source", "program"],
        ),
        ToolParameter(
            name="timeout",
            type=int,
            required=False,
            default=30,
            description="执行超时时间（秒）",
            example=60,
            aliases=["time_limit", "max_time", "wait"],
        ),
    ],
    examples=[
        {"code": "print('Hello, World!')"},
        {"code": "import math\nprint(math.pi)", "timeout": 10},
    ],
    returns="返回字典，包含 success, stdout, stderr, returncode 等字段",
)

RUN_TESTS_SCHEMA = ToolSchema(
    name="run_tests",
    description="运行测试。用于执行项目的测试套件。",
    parameters=[
        ToolParameter(
            name="test_path",
            type=str,
            required=False,
            default="",
            description="测试文件或目录的路径",
            example="tests/test_main.py",
            aliases=["path", "file", "directory", "target"],
        ),
        ToolParameter(
            name="timeout",
            type=int,
            required=False,
            default=60,
            description="测试执行超时时间（秒）",
            example=120,
            aliases=["time_limit", "max_time", "wait"],
        ),
    ],
    examples=[
        {},
        {"test_path": "tests/test_main.py"},
        {"test_path": "tests/", "timeout": 120},
    ],
    returns="返回字典，包含 success, passed, failed, output 等字段",
)


# ==================== Todo Tools Schemas ====================

ADD_TODO_ITEM_SCHEMA = ToolSchema(
    name="add_todo_item",
    description="添加待办事项。用于记录需要完成的任务。支持多种参数格式。",
    parameters=[
        ToolParameter(
            name="description",
            type=str,
            required=False,
            description="待办事项的描述（推荐使用）",
            example="实现用户认证功能",
            aliases=["item", "task", "todo", "title"],
        ),
        ToolParameter(
            name="priority",
            type=str,
            required=False,
            default="medium",
            description="优先级：low, medium, high",
            example="high",
        ),
        ToolParameter(
            name="category",
            type=str,
            required=False,
            default="任务",
            description="分类标签",
            example="开发",
        ),
        ToolParameter(
            name="task_id",
            type=str,
            required=False,
            description="关联的任务ID（可选）",
            example="task_123",
        ),
    ],
    examples=[
        {"description": "实现用户认证功能"},
        {"item": "修复登录bug", "priority": "high"},
        {"description": "添加数据验证", "category": "开发", "priority": "medium"},
    ],
    returns="返回字典，包含 success, message, item, priority, category 等字段",
)

MARK_TODO_COMPLETED_SCHEMA = ToolSchema(
    name="mark_todo_completed",
    description="标记待办事项为完成。用于更新任务状态。",
    parameters=[
        ToolParameter(
            name="item_pattern",
            type=str,
            required=True,
            description="待办事项的匹配模式（支持模糊匹配）",
            example="用户认证",
        )
    ],
    examples=[{"item_pattern": "用户认证"}, {"item_pattern": "登录bug"}],
    returns="返回字典，包含 success, message, item_pattern 等字段",
)

UPDATE_TODO_ITEM_SCHEMA = ToolSchema(
    name="update_todo_item",
    description="更新待办事项。用于修改任务描述。",
    parameters=[
        ToolParameter(
            name="old_pattern",
            type=str,
            required=True,
            description="原待办事项的匹配模式",
            example="用户认证",
        ),
        ToolParameter(
            name="new_item",
            type=str,
            required=True,
            description="新的待办事项描述",
            example="完善用户认证功能",
        ),
    ],
    examples=[{"old_pattern": "用户认证", "new_item": "完善用户认证功能"}],
    returns="返回字典，包含 success, message 等字段",
)

GET_TODO_SUMMARY_SCHEMA = ToolSchema(
    name="get_todo_summary",
    description="获取待办清单摘要。用于查看任务进度。",
    parameters=[],
    examples=[{}],
    returns="返回字典，包含 success, project_name, todo_file, total_todos, completed_todos, pending_todos, completion_rate 等字段",
)

LIST_TODO_FILES_SCHEMA = ToolSchema(
    name="list_todo_files",
    description="列出所有待办清单文件。用于查看历史待办清单。",
    parameters=[],
    examples=[{}],
    returns="返回字典，包含 success, files (列表), count 等字段",
)

ADD_EXECUTION_RECORD_SCHEMA = ToolSchema(
    name="add_execution_record",
    description="添加执行记录。用于记录任务执行过程。",
    parameters=[
        ToolParameter(
            name="record",
            type=str,
            required=True,
            description="执行记录的描述",
            example="完成了用户认证API的开发",
            aliases=["description", "details", "message", "summary", "content", "text"],
        )
    ],
    examples=[{"record": "完成了用户认证API的开发"}, {"record": "修复了登录bug"}],
    returns="返回字典，包含 success, message, record 等字段",
)

ADD_TODO_SCHEMA = ADD_TODO_ITEM_SCHEMA
COMPLETE_TODO_SCHEMA = MARK_TODO_COMPLETED_SCHEMA
LIST_TODOS_SCHEMA = GET_TODO_SUMMARY_SCHEMA


# ==================== Incremental Tools Schemas ====================

INCREMENTAL_UPDATE_SCHEMA = ToolSchema(
    name="incremental_update",
    description="""增量更新文件内容。支持多种更新模式，优先使用run_shell工具增量更新或此工具而不是write_file修改现有文件。

📋 **使用场景分类**（根据需求选择一种模式）：

1. **智能更新**（推荐）：update_type="smart"
   - 自动分析差异，最小化更改
   - 适合大多数代码修改场景

2. **追加/前置内容**：update_type="append" 或 "prepend"
   - append: 追加到文件末尾
   - prepend: 前置到文件开头
   - 适合添加日志、注释、导入语句等

3. **行级别更新**：update_type="line_update"
   - 精确更新指定行或行范围
   - 需要 line_number（单行）或 line_range（多行，如"10-20"）
   - 适合修复bug、修改特定函数

4. **插入内容**：update_type="insert_before" 或 "insert_after"
   - 在指定位置插入内容
   - 需要 reference_content（匹配内容）或 line_number（行号）
   - 适合添加新函数、配置项

5. **替换内容**：update_type="replace"
   - 替换整个文件或指定行范围
   - ⚠️ 危险：不指定行范围会替换整个文件！
   - 部分替换：使用 start_line + end_line 参数

🔧 **参数使用规则**：

**内容参数（二选一）**：
- new_content: 直接提供新内容（字符串）
- source: 引用现有内容节省token（格式：content:<内容> 或 file:<路径> 或 上下文标识符）

**位置参数**（根据update_type选择）：
- line_update模式 → line_number 或 line_range
- insert模式 → reference_content 或 line_number
- replace模式（部分替换） → start_line + end_line

**源过滤参数**（仅当使用source时，必须带source_前缀）：
- source_start_line: 起始行号
- source_end_line: 结束行号
- source_pattern: 只保留匹配的行
- source_exclude_pattern: 排除匹配的行

🚨 **重要约束**：
1. new_content和source参数二选一，不能同时使用
2. line_update必须指定line_number或line_range
3. insert模式必须指定reference_content或line_number
4. 使用source参数时，过滤参数必须带source_前缀
5. 不指定行范围时，replace会替换整个文件（谨慎！）

📏 **行号计算规则**（重要共识）：
- **行号从1开始**：第1行是文件的第一行
- **包含性范围**：line_range="10-20" 包含第10行和第20行
- **插入位置**：
  - insert_before line_number=10：在第10行之前插入
  - insert_after line_number=10：在第10行之后插入
- **替换范围**：start_line=5, end_line=10 替换第5-10行（包含）
- **空行计数**：空行也计入行号
- **引用匹配**：reference_content匹配时，插入在匹配行的前/后

💡 **最佳实践**：
1. 先查看文件内容
2. 选择最合适的update_type
3. 优先使用source参数引用现有内容节省token
4. 复杂修改可分多次增量更新""",
    parameters=[
        ToolParameter(
            name="path",
            type=str,
            required=True,
            description="文件路径（相对或绝对）",
            example="src/main.py",
            aliases=["file", "filepath", "target"],
        ),
        ToolParameter(
            name="new_content",
            type=str,
            required=False,
            description="新的文件内容（与source二选一）",
            example="def new_function():\n    return 'new'",
            aliases=["content", "code", "text", "data"],
        ),
        ToolParameter(
            name="update_type",
            type=str,
            required=False,
            default="smart",
            description="更新类型：smart(智能分析差异)、replace(替换整个文件或指定行范围)、append(追加到末尾)、prepend(前置到开头)、line_update(行级别更新)、insert_before(在指定行之前插入)、insert_after(在指定行之后插入)",
            example="smart",
            aliases=["type", "mode", "update_mode"],
        ),
        ToolParameter(
            name="source",
            type=str,
            required=False,
            description="内容来源标识符（与new_content二选一）",
            example="content:def new_func():\n    return 'new'",
            aliases=["from", "src", "reference"],
        ),
        ToolParameter(
            name="line_number",
            type=int,
            required=False,
            description="要更新的行号（1-based）。当update_type为line_update时使用",
            example=10,
            aliases=["line", "row", "line_no"],
        ),
        ToolParameter(
            name="line_range",
            type=str,
            required=False,
            description="要更新的行范围，格式如 '10-20'。当update_type为line_update时使用",
            example="10-20",
            aliases=["range", "lines", "line_range_str"],
        ),
        ToolParameter(
            name="reference_content",
            type=str,
            required=False,
            description="参考内容，用于定位插入位置。当update_type为insert_before或insert_after时使用",
            example="if __name__ == \"__main__\":",
            aliases=["reference", "ref_content", "target_content"],
        ),
        ToolParameter(
            name="start_line",
            type=int,
            required=False,
            description="目标文件起始行号（1-based）。当update_type为replace时，指定要替换的起始行。与end_line一起使用进行部分替换。",
            example=5,
            aliases=["from_line", "line_start"],
        ),
        ToolParameter(
            name="end_line",
            type=int,
            required=False,
            description="目标文件结束行号（1-based，包含）。当update_type为replace时，指定要替换的结束行。与start_line一起使用进行部分替换。",
            example=10,
            aliases=["to_line", "line_end"],
        ),
        ToolParameter(
            name="source_start_line",
            type=int,
            required=False,
            description="源文件起始行号（1-based）。当使用source参数时，指定要提取的起始行。",
            example=1,
            aliases=[],
        ),
        ToolParameter(
            name="source_end_line",
            type=int,
            required=False,
            description="源文件结束行号（1-based，包含）。当使用source参数时，指定要提取的结束行。",
            example=10,
            aliases=[],
        ),
        ToolParameter(
            name="source_pattern",
            type=str,
            required=False,
            description="源文件正则表达式模式。当使用source参数时，只保留匹配此模式的行。",
            example="^def ",
            aliases=[],
        ),
        ToolParameter(
            name="source_exclude_pattern",
            type=str,
            required=False,
            description="源文件正则表达式模式。当使用source参数时，排除匹配此模式的行。",
            example="^#",
            aliases=[],
        ),
    ],
    examples=[
        # 场景1：智能更新（推荐）
        {
            "path": "src/main.py",
            "new_content": "def main():\n    print('Hello')",
            "update_type": "smart",
            "description": "智能分析差异，自动更新文件"
        },
        
        # 场景2：追加/前置内容
        {
            "path": "config.py", 
            "new_content": "# 配置更新\nDEBUG = True",
            "update_type": "append",
            "description": "追加内容到文件末尾"
        },
        {
            "path": "main.py",
            "source": "content:import sys\nimport os",
            "update_type": "prepend",
            "description": "前置导入语句到文件开头"
        },
        
        # 场景3：行级别更新
        {
            "path": "src/main.py",
            "new_content": "    print('Updated line')",
            "update_type": "line_update",
            "line_number": 10,
            "description": "更新第10行的内容（行号从1开始）"
        },
        {
            "path": "src/utils.py",
            "new_content": "def updated_function():\n    return 'new'",
            "update_type": "line_update",
            "line_range": "20-25",
            "description": "更新第20-25行的内容（包含第20和25行）"
        },
        
        # 场景4：插入内容
        {
            "path": "src/main.py",
            "new_content": "@app.post(\"/hello\")\ndef hello_post():\n    return {\"message\": \"Hello\"}",
            "update_type": "insert_before",
            "reference_content": "if __name__ == \"__main__\":",
            "description": "在匹配内容前插入新函数（匹配行前插入）"
        },
        {
            "path": "src/main.py",
            "new_content": "    # 新增功能注释",
            "update_type": "insert_after",
            "line_number": 15,
            "description": "在第15行后插入注释（行号从1开始）"
        },
        
        # 场景5：替换内容（部分替换）
        {
            "path": "src/main.py",
            "new_content": "def replaced_function():\n    return 'replaced'",
            "update_type": "replace",
            "start_line": 5,
            "end_line": 10,
            "description": "替换第5-10行的内容（包含第5和10行）"
        },
        
        # 场景6：使用source参数节省token
        {
            "path": "appended.txt",
            "source": "file:source.txt",
            "update_type": "append",
            "description": "引用现有文件内容追加"
        },
        {
            "path": "functions_only.py",
            "source": "file:source.py",
            "source_start_line": 1,
            "source_end_line": 100,
            "source_pattern": "^def ",
            "update_type": "line_update",
            "line_number": 1,
            "description": "从源文件提取函数定义更新"
        },
        
        # 场景7：行号计算示例
        {
            "path": "example.py",
            "new_content": "# 在第3行后插入",
            "update_type": "insert_after",
            "line_number": 3,
            "description": "示例：文件有5行，在第3行后插入，新文件第4行是插入内容"
        },
        
        # 场景8：错误示例（避免这样做）
        {
            "path": "README.md",
            "new_content": "# 新标题",
            "update_type": "replace",
            "description": "⚠️ 危险：不指定行范围会替换整个文件！"
        }
    ],
    returns="返回字典，包含 success, path, action, message, diff_count 等字段。不同模式返回不同信息：\n- smart模式：显示更新的实体数量\n- line_update模式：显示更新的行范围\n- 其他模式：显示执行的具体操作",
)

PATCH_FILE_SCHEMA = ToolSchema(
    name="patch_file",
    description="使用补丁（unified diff格式）更新文件。适用于精确的代码修改。",
    parameters=[
        ToolParameter(
            name="path",
            type=str,
            required=True,
            description="文件路径",
            example="src/main.py",
            aliases=["file", "filepath"],
        ),
        ToolParameter(
            name="patch_content",
            type=str,
            required=True,
            description="补丁内容（unified diff格式）",
            example="--- src/main.py\n+++ src/main.py\n@@ -1,3 +1,3 @@\n def main():\n-    print('Old')\n+    print('New')",
            aliases=["patch", "diff", "unified_diff"],
        ),
    ],
    examples=[
        {
            "path": "src/main.py",
            "patch_content": "--- src/main.py\n+++ src/main.py\n@@ -1,3 +1,3 @@\n def main():\n-    print('Old')\n+    print('New')",
        }
    ],
    returns="返回字典，包含 success, path, action, message 等字段",
)

GET_FILE_DIFF_SCHEMA = ToolSchema(
    name="get_file_diff",
    description="获取文件差异。比较当前文件内容与新内容，返回unified diff格式的差异。",
    parameters=[
        ToolParameter(
            name="path",
            type=str,
            required=True,
            description="文件路径",
            example="src/main.py",
            aliases=["file", "filepath"],
        ),
        ToolParameter(
            name="new_content",
            type=str,
            required=True,
            description="新的文件内容",
            example="def main():\n    print('New')",
            aliases=["content", "code", "text"],
        ),
    ],
    examples=[{"path": "src/main.py", "new_content": "def main():\n    print('New')"}],
    returns="返回字典，包含 success, path, diff_count, diff, old_size, new_size 等字段",
)


# ==================== MCP Tools Schemas ====================

LIST_MCP_TOOLS_SCHEMA = ToolSchema(
    name="list_mcp_tools",
    description="列出所有可用的MCP（模型上下文协议）工具。MCP工具来自外部服务器，提供文件系统、数据库、网络搜索等功能。",
    parameters=[],
    examples=[{}, {"server_filter": "filesystem"}],
    returns="返回字典，包含 success, tools（工具字典）, count（工具数量）, connected_servers（已连接的服务器列表）等字段",
)

CALL_MCP_TOOL_SCHEMA = ToolSchema(
    name="call_mcp_tool",
    description="调用MCP（模型上下文协议）工具。MCP工具来自外部服务器，可以执行文件操作、数据库查询、网络搜索等任务。",
    parameters=[
        ToolParameter(
            name="tool_name",
            type=str,
            required=True,
            description="MCP工具名称，格式为 'server_name.tool_name' 或直接使用工具名",
            example="filesystem.read_file",
            aliases=["tool", "name", "function"],
        ),
        ToolParameter(
            name="arguments",
            type=dict,
            required=False,
            description="传递给MCP工具的参数",
            example={"path": "/tmp/test.txt"},
            aliases=["args", "params", "input"],
        ),
    ],
    examples=[
        {"tool_name": "filesystem.read_file", "arguments": {"path": "/tmp/test.txt"}},
        {"tool_name": "database.query", "arguments": {"query": "SELECT * FROM users"}},
        {
            "tool_name": "web_search.search",
            "arguments": {"query": "Python programming"},
        },
    ],
    returns="返回字典，包含 success, result（工具执行结果）, error（错误信息，如果有）等字段",
)

GET_MCP_STATUS_SCHEMA = ToolSchema(
    name="get_mcp_status",
    description="获取MCP（模型上下文协议）服务器状态。显示已配置的服务器、连接状态和可用工具。",
    parameters=[],
    examples=[{}, {"detailed": True}],
    returns="返回字典，包含 success, servers（服务器状态列表）, connected_count（已连接服务器数量）, total_count（总服务器数量）等字段",
)


# ==================== Skills Schemas ====================

LIST_SKILLS_SCHEMA = ToolSchema(
    name="list_skills",
    description="列出所有可用的Skills。用于发现项目中已安装的技能，了解可用的功能模块。",
    parameters=[],
    examples=[{}],
    returns="返回字典，包含 success, skills (技能列表), count (技能数量) 等字段",
)

GET_SKILL_INFO_SCHEMA = ToolSchema(
    name="get_skill_info",
    description="获取特定Skill的详细信息。用于了解技能的功能、参数和使用方法。",
    parameters=[
        ToolParameter(
            name="skill_name",
            type=str,
            required=True,
            description="要查询的Skill名称",
            example="data_cleaning",
            aliases=["skill", "name"],
        )
    ],
    examples=[{"skill_name": "data_cleaning"}, {"skill_name": "api_client"}],
    returns="返回字典，包含 success, name, description, parameters, examples 等字段",
)


# ==================== 所有工具schema的字典 ====================
ALL_SCHEMAS = {
    # Atomic Tools
    "read_file": READ_FILE_SCHEMA,
    "write_file": WRITE_FILE_SCHEMA,
    "run_shell": RUN_SHELL_SCHEMA,
    "list_files": LIST_FILES_SCHEMA,
    "search_files": SEARCH_FILES_SCHEMA,
    # Web Tools
    "search_web": SEARCH_WEB_SCHEMA,
    "fetch_url": FETCH_URL_SCHEMA,
    # Code Tools
    "execute_python": EXECUTE_PYTHON_SCHEMA,
    "run_tests": RUN_TESTS_SCHEMA,
    # Incremental Tools
    "incremental_update": INCREMENTAL_UPDATE_SCHEMA,
    "patch_file": PATCH_FILE_SCHEMA,
    "get_file_diff": GET_FILE_DIFF_SCHEMA,
    # Todo Tools (新名称)
    "add_todo_item": ADD_TODO_ITEM_SCHEMA,
    "mark_todo_completed": MARK_TODO_COMPLETED_SCHEMA,
    "update_todo_item": UPDATE_TODO_ITEM_SCHEMA,
    "get_todo_summary": GET_TODO_SUMMARY_SCHEMA,
    "list_todo_files": LIST_TODO_FILES_SCHEMA,
    "add_execution_record": ADD_EXECUTION_RECORD_SCHEMA,
    # Todo Tools (兼容旧名称)
    "add_todo": ADD_TODO_SCHEMA,
    "complete_todo": COMPLETE_TODO_SCHEMA,
    "list_todos": LIST_TODOS_SCHEMA,
    # MCP Tools
    "list_mcp_tools": LIST_MCP_TOOLS_SCHEMA,
    "call_mcp_tool": CALL_MCP_TOOL_SCHEMA,
    "get_mcp_status": GET_MCP_STATUS_SCHEMA,
    # Skills查询工具
    "list_skills": LIST_SKILLS_SCHEMA,
    "get_skill_info": GET_SKILL_INFO_SCHEMA,
    # Skills执行工具（动态加载，不在此硬编码）
    # 注意：skills的schema会从skills目录动态加载，通过get_all_schemas()函数合并
}


def get_all_schemas(skills_manager=None):
    """
    获取所有工具schema，包括动态加载的skills

    Args:
        skills_manager: SkillsManager实例，用于获取动态skills的schema

    Returns:
        包含所有schema的字典
    """
    schemas = ALL_SCHEMAS.copy()

    # 如果提供了skills_manager，添加动态skills的schema
    if skills_manager:
        discovered_skills = skills_manager.discover_skills()
        for skill_name in discovered_skills:
            skill_schema = skills_manager.get_skill_schema(skill_name)
            if skill_schema:
                schemas[skill_name] = skill_schema

    return schemas


def get_schema(tool_name: str, skills_manager=None):
    """
    获取特定工具的schema

    Args:
        tool_name: 工具名称
        skills_manager: SkillsManager实例，用于获取动态skills的schema

    Returns:
        工具的schema，如果不存在则返回None
    """
    # 首先检查静态schema
    if tool_name in ALL_SCHEMAS:
        return ALL_SCHEMAS[tool_name]

    # 如果提供了skills_manager，检查动态skills
    if skills_manager:
        skill_schema = skills_manager.get_skill_schema(tool_name)
        if skill_schema:
            return skill_schema

    return None
