# 工具Schema定义
# utils/tool_schemas.py
"""
为所有工具定义schema
包含参数说明、类型、示例等
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from .tool_registry import ToolSchema, ToolParameter
else:
    from .tool_registry import ToolSchema, ToolParameter

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
    description="""执行shell命令 - 万能的系统命令执行工具，你的瑞士军刀！

**核心理念**：
- 工具总是成功（success=True），除非工具本身异常
- 命令的成功/失败通过 returncode 判断（0=成功，非0=失败）
- 完整返回 stdout 和 stderr，让你自行判断如何处理
- **大胆使用**：在安全范围内，不要害怕使用bash命令解决问题

**强大能力展示**：
1. **文本处理专家**：
   - grep/glob/awk/sed/cat：精准搜索、提取、写入、替换
   - sort/uniq：排序、去重、统计
   - cut/tr/wc：字段切割、字符转换、行数统计
   - diff/patch：文件差异比较、补丁应用

2. **文件系统大师**：
   - find/locate：智能文件搜索
   - tar/zip/gzip：压缩解压
   - rsync/scp：同步传输
   - chmod/chown：权限管理

3. **系统监控能手**：
   - ps/top/htop：进程监控
   - df/du：磁盘空间分析
   - free/vmstat：内存监控
   - netstat/ss：网络连接查看

4. **开发工作流**：
   - git：版本控制全套操作
   - docker/docker-compose：容器管理
   - make/cmake：构建系统
   - npm/pip/cargo：包管理

5. **网络工具集**：
   - curl/wget：HTTP请求、下载
   - ping/traceroute：网络诊断
   - ssh/scp：远程连接
   - netcat：网络调试

6. **数据处理管道**：
   - command1 | command2 | command3：组合威力
   - > file.txt：输出重定向
   - < input.txt：输入重定向
   - 2>&1：错误输出合并

**重要提示**：
- returncode=0 表示命令成功
- returncode≠0 不一定是错误（如 grep 没找到匹配返回1是正常的）
- 检查 stderr 判断是否有真正的错误
- 支持管道、重定向等 shell 特性：command1 | command2, command > file.txt
- 命令在项目目录下执行，使用相对路径即可
- **大胆尝试**：命令失败很正常，从错误中学习，调整后重试

**安全限制**：
- 危险命令要谨慎（如 rm -rf /）但可用
- 绝对路径必须在项目范围内
- 某些系统命令可能被限制
- **但请记住**：正常的系统操作、开发命令都可以大胆使用！""",
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
        # 新增更多实用命令示例
        {
            "command": "grep -r 'def main' .",
            "description": "递归搜索包含'main'函数的文件",
        },
        {
            "command": "awk '/^def/ {print NR\": \"$0}' file.py",
            "description": "提取Python文件中的所有函数定义",
        },
        {
            "command": "sed -i '' 's/old/new/g' file.txt",
            "description": "替换文件中的文本（macOS）",
        },
        {
            "command": "sed -i 's/old/new/g' file.txt",
            "description": "替换文件中的文本（Linux）",
        },
        {
            "command": "find . -type f -name '*.py' -exec wc -l {} +",
            "description": "统计所有Python文件的总行数",
        },
        {"command": "ps aux | grep python", "description": "查找正在运行的Python进程"},
        {"command": "df -h", "description": "查看磁盘使用情况（人类可读格式）"},
        {"command": "du -sh .", "description": "查看当前目录总大小"},
        {"command": "free -h", "description": "查看内存使用情况"},
        {
            "command": "curl -s https://api.github.com/users/octocat",
            "description": "获取API数据",
        },
        {"command": "git status", "description": "查看git状态"},
        {"command": "git log --oneline -5", "description": "查看最近5次提交"},
        {
            "command": "sort file.txt | uniq -c | sort -nr",
            "description": "统计文件中单词出现频率",
        },
        {
            "command": "cat access.log | awk '{print $1}' | sort | uniq -c | sort -nr | head -10",
            "description": "分析日志文件，找出前10个访问IP",
        },
        {
            "command": "python -m http.server 8000 &",
            "description": "启动简单的HTTP服务器（后台运行）",
        },
        {
            "command": "kill $(lsof -ti:8000)",
            "description": "关闭占用8000端口的进程（需要用户同意）",
        },
        {"command": "tar -czf backup.tar.gz directory/", "description": "压缩目录"},
        {"command": "rsync -av source/ destination/", "description": "同步目录"},
        {"command": "docker ps", "description": "查看运行中的容器"},
        {"command": "npm run build", "description": "运行npm构建脚本"},
        {"command": "make clean", "description": "运行make清理"},
        {"command": "ssh user@host 'ls -la'", "description": "远程执行命令"},
        {
            "command": "echo 'Hello World' > output.txt",
            "description": "创建文件并写入内容",
        },
        {"command": "tail -f logfile.log", "description": "实时查看日志文件"},
        {
            "command": "watch -n 1 'ps aux | grep python'",
            "description": "每秒监控Python进程",
        },
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
    description="""列出所有可用的Skills。用于发现项目中已安装的技能，了解可用的功能模块。使用具体skill前，请使用get_skill_info工具获取skill的详细信息及其工具调用方法。
一般来说，skill的工具调用方法如下：
调用示例1（scrape_dynamic_page是playwright skill的一个工具）：
Action: scrape_dynamic_page
Action Input: {"url": "http://example.com"}

调用示例2（scrape_web是scrape_web skill的一个工具）
Action: scrape_web
Action Input: {"url": "https://example.com", "operations": ["extract_text", "extract_links"]}


""",
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
    # Todo Tools (新名称)
    "add_todo_item": ADD_TODO_ITEM_SCHEMA,
    "mark_todo_completed": MARK_TODO_COMPLETED_SCHEMA,
    "update_todo_item": UPDATE_TODO_ITEM_SCHEMA,
    "get_todo_summary": GET_TODO_SUMMARY_SCHEMA,
    "list_todo_files": LIST_TODO_FILES_SCHEMA,
    "add_execution_record": ADD_EXECUTION_RECORD_SCHEMA,
    # Todo Tools (兼容旧名称)
    # "add_todo": ADD_TODO_SCHEMA,
    # "complete_todo": COMPLETE_TODO_SCHEMA,
    # "list_todos": LIST_TODOS_SCHEMA,
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
