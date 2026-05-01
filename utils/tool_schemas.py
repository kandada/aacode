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

RUN_SHELL_SCHEMA = ToolSchema(
    name="run_shell",
    description="Execute a shell command - the universal Swiss Army knife! The tool always returns success=True; check returncode to determine success/failure. Full stdout and stderr are returned for you to process. Common uses: read files (cat/tail), write files (echo/cat), search (grep/ls/find), development (python/pytest/git). Supports pipes and redirection. Filenames with spaces or special characters must be quoted (e.g. cat \"my file.md\").",
    parameters=[
        ToolParameter(
            name="command",
            type=str,
            required=True,
            description="The shell command to execute (supports pipes, redirection, and other shell features)",
            example='python -c "import sys; print(sys.version)"',
            aliases=["cmd", "shell", "script", "exec"],
        ),
        ToolParameter(
            name="timeout",
            type=int,
            required=False,
            default=30,
            description="Command execution timeout in seconds (default 30). Increase for long-running commands.",
            example=60,
            aliases=["time_limit", "max_time", "wait"],
        ),
        ToolParameter(
            name="stdin_input",
            type=str,
            required=False,
            description="Standard input content to pass to the program. Use when the program calls input() and waits for user input. Separate multiple lines with \\n. If not provided, the program's stdin is empty (input() will raise EOFError immediately).",
            example="5\\n3\\n",
            aliases=["input", "stdin"],
        ),
        ToolParameter(
            name="max_output",
            type=int,
            required=False,
            description="Limit the output character count. Default is None (no limit). Pass a number like 200 to restrict.",
            example=None,
            aliases=["max_chars", "limit", "output_limit"],
        ),
    ],
    examples=[
        {"command": "ls -la", "description": "List all files in current directory (including hidden files)"},
        {"command": "pwd", "description": "Print current working directory"},
        {"command": "python --version", "description": "Check Python version"},
        {"command": "python script.py", "description": "Run a Python script"},
        {
            "command": "python3 calculator.py",
            "stdin_input": "5\n3\n",
            "description": "Run a program that needs user input, simulating entering 5 and 3",
        },
        {"command": "python -c \"print('Hello')\"", "description": "Execute Python code"},
        {"command": "pip list", "description": "List installed packages"},
        {
            "command": "pip install requests",
            "timeout": 60,
            "description": "Install a Python package",
        },
        {"command": "pytest tests/", "description": "Run tests"},
        {"command": "cat \"my notes.txt\"", "description": "View a text file with spaces in filename (filename must be quoted)"},
        {"command": "grep 'pattern' file.txt", "description": "Search file contents"},
        {"command": "find . -name '*.py'", "description": "Find Python files"},
        {"command": "ls -la | grep '.py'", "description": "List Python files"},
        {
            "command": "grep -r 'def main' .",
            "description": "Recursively search for files containing 'main' function",
        },
        {
            "command": "awk '/^def/ {print NR\": \"$0}' file.py",
            "description": "Extract all function definitions from a Python file",
        },
        {
            "command": "sed -i '' 's/old/new/g' file.txt",
            "description": "Replace text in a file (macOS)",
        },
        {
            "command": "sed -i 's/old/new/g' file.txt",
            "description": "Replace text in a file (Linux)",
        },
        {
            "command": "find . -type f -name '*.py' -exec wc -l {} +",
            "description": "Count total lines across all Python files",
        },
        {"command": "ps aux | grep python", "description": "Find running Python processes"},
        {"command": "df -h", "description": "View disk usage (human-readable format)"},
        {"command": "du -sh .", "description": "View total size of current directory"},
        {"command": "free -h", "description": "View memory usage"},
        {
            "command": "curl -s https://api.github.com/users/octocat",
            "description": "Fetch API data",
        },
        {"command": "git status", "description": "Check git status"},
        {"command": "git log --oneline -5", "description": "View last 5 commits"},
        {
            "command": "sort file.txt | uniq -c | sort -nr",
            "description": "Count word frequency in a file",
        },
        {
            "command": "cat access.log | awk '{print $1}' | sort | uniq -c | sort -nr | head -10",
            "description": "Analyze log file, find top 10 visiting IPs",
        },
        {
            "command": "python -m http.server 8000 &",
            "description": "Start a simple HTTP server (background)",
        },
        {
            "command": "kill $(lsof -ti:8000)",
            "description": "Kill the process occupying port 8000 (requires user consent)",
        },
        {"command": "tar -czf backup.tar.gz directory/", "description": "Compress a directory"},
        {"command": "rsync -av source/ destination/", "description": "Sync directories"},
        {"command": "docker ps", "description": "View running containers"},
        {"command": "npm run build", "description": "Run npm build script"},
        {"command": "make clean", "description": "Run make clean"},
        {"command": "ssh user@host 'ls -la'", "description": "Execute command remotely"},
        {
            "command": "echo 'Hello World' > output.txt",
            "description": "Create a file with content",
        },
        {"command": "tail -f logfile.log", "description": "Watch log file in real time"},
        {
            "command": "watch -n 1 'ps aux | grep python'",
            "description": "Monitor Python processes every second",
        },
    ],
    returns="""Returns a dictionary with the following fields:
- success (bool): Whether the tool executed successfully (always True unless the tool itself threw an exception)
- returncode (int): Command exit code (0=success, non-zero=failure)
- stdout (str): Standard output
- stderr (str): Error output
- command (str): The executed command
- working_directory (str): Working directory""",
)


FINALIZE_TASK_SCHEMA = ToolSchema(
    name="finalize_task",
    description="End the current task and output a final summary. Call this when you are certain the task is fully complete. The task ends immediately after invocation.",
    parameters=[
        ToolParameter(
            name="summary",
            type=str,
            required=True,
            description="A brief summary of what was done and the results",
            example="Successfully created 3 files in src/, all tests passing",
            aliases=["message", "conclusion", "result"],
        ),
    ],
    examples=[
        {"summary": "All file modifications completed, all tests passing"},
        {"summary": "Optimized 3 files, removed redundant code, lint check passed"},
    ],
    returns="Returns status=completed and summary",
)

RUN_SKILLS_SCHEMA = ToolSchema(
    name="run_skills",
    description="""Execute pre-defined skills. Three modes:

1. List available skills: run_skills("__list__")
2. View skill details: run_skills("__info__", {"skill_name": "pandas"})
3. Execute a skill: run_skills("pandas", {"code": "df.describe()"})

For multi-function skills (e.g. playwright), pass "func" in params:
  run_skills("playwright", {"func": "browser_automation", "url": "https://example.com"})

Use __list__ to see available skills first, then __info__ to get parameter details, then execute.
""",
    parameters=[
        ToolParameter(
            name="skill_name",
            type=str,
            required=False,
            description="Skill name, or __list__/__info__ for listing/info modes. If omitted, tries params.skill_name as fallback.",
            example="pandas",
            aliases=["skill", "name"],
        ),
        ToolParameter(
            name="params",
            type=dict,
            required=False,
            description="Parameters for the skill. For multi-function skills, include 'func' key to select sub-function.",
            example={"code": "df.describe()"},
            aliases=["arguments", "args", "kwargs"],
        ),
    ],
    examples=[
        {
            "skill_name": "__list__",
            "description": "List all available skills",
        },
        {
            "skill_name": "__info__",
            "params": {"skill_name": "playwright"},
            "description": "View detailed info for playwright skill",
        },
        {
            "skill_name": "pandas",
            "params": {"code": "pd.read_csv('data.csv').head()"},
            "description": "Execute pandas data analysis code",
        },
        {
            "skill_name": "playwright",
            "params": {"func": "browser_automation", "url": "https://example.com"},
            "description": "Use Playwright to automate browser (multi-function skill)",
        },
        {
            "skill_name": "playwright",
            "params": {"func": "take_screenshot", "url": "https://example.com", "output_path": "screenshot.png"},
            "description": "Take a screenshot using Playwright",
        },
    ],
    returns="Returns a string with the execution result or error message",
)


# ==================== Web Tools Schemas ====================

SEARCH_WEB_SCHEMA = ToolSchema(
    name="search_web",
    description="Search for information on the web. Use to find latest technical documentation, solutions, etc.",
    parameters=[
        ToolParameter(
            name="query",
            type=str,
            required=True,
            description="Search query keywords",
            example="Python asyncio tutorial",
            aliases=["search", "keyword", "q", "term"],
        ),
        ToolParameter(
            name="max_results",
            type=int,
            required=False,
            default=5,
            description="Maximum number of results to return",
            example=10,
            aliases=["limit", "count", "num", "num_results"],
        ),
    ],
    examples=[
        {"query": "Python asyncio tutorial"},
        {"query": "Flask best practices", "max_results": 10},
    ],
    returns="Returns a dictionary with success, query, results (list), and other fields",
)

FETCH_URL_SCHEMA = ToolSchema(
    name="fetch_url",
    description="Fetch the content of a URL. Use to read web page content or API responses.",
    parameters=[
        ToolParameter(
            name="url",
            type=str,
            required=True,
            description="The URL address to fetch",
            example="https://example.com/api/data",
            aliases=["link", "uri", "address"],
        ),
        ToolParameter(
            name="timeout",
            type=int,
            required=False,
            default=10,
            description="Request timeout in seconds",
            example=30,
            aliases=["time_limit", "max_time", "wait"],
        ),
    ],
    examples=[
        {"url": "https://api.github.com/repos/python/cpython"},
        {"url": "https://example.com/data.json", "timeout": 30},
    ],
    returns="Returns a dictionary with success, url, content, status_code, and other fields",
)


# ==================== Todo Tools Schemas ====================

ADD_TODO_ITEM_SCHEMA = ToolSchema(
    name="add_todo_item",
    description="Add a todo item. Returns a todo_id (e.g. t1), which can later be used with mark_todo_completed(todo_id='t1') for precise completion.",
    parameters=[
        ToolParameter(
            name="description",
            type=str,
            required=False,
            description="Description of the todo item (recommended)",
            example="Implement user authentication",
            aliases=["item", "task", "todo", "title"],
        ),
        ToolParameter(
            name="priority",
            type=str,
            required=False,
            default="medium",
            description="Priority: low, medium, high",
            example="high",
        ),
        ToolParameter(
            name="category",
            type=str,
            required=False,
            default="Task",
            description="Category label",
            example="Development",
        ),
        ToolParameter(
            name="task_id",
            type=str,
            required=False,
            description="Associated task ID (optional)",
            example="task_123",
        ),
    ],
    examples=[
        {"description": "Implement user authentication"},
        {"item": "Fix login bug", "priority": "high"},
    ],
    returns="Returns a dictionary with success, todo_id (important: for mark_todo_completed), message, item, and other fields",
)

MARK_TODO_COMPLETED_SCHEMA = ToolSchema(
    name="mark_todo_completed",
    description="Mark a todo item as completed. Prefer using todo_id for precise matching (returned by add_todo_item), also supports fuzzy text matching as fallback.",
    parameters=[
        ToolParameter(
            name="todo_id",
            type=str,
            required=False,
            description="Todo item ID (e.g. 't1', 't2'), returned by add_todo_item. Use this parameter first, it is precise and reliable.",
            example="t1",
            aliases=["id"],
        ),
        ToolParameter(
            name="item_pattern",
            type=str,
            required=False,
            description="Matching keyword for the todo item (fallback). Use when todo_id is not available.",
            example="helloworld",
            aliases=["title", "item", "task", "description", "name", "text", "content", "pattern", "todo"],
        ),
    ],
    examples=[{"todo_id": "t1"}, {"item_pattern": "helloworld"}],
    returns="Returns a dictionary with success, message, todo_id, item_pattern, and other fields",
)

UPDATE_TODO_ITEM_SCHEMA = ToolSchema(
    name="update_todo_item",
    description="Update a todo item. Use to modify task descriptions.",
    parameters=[
        ToolParameter(
            name="old_pattern",
            type=str,
            required=True,
            description="The matching pattern of the original todo item",
            example="User Authentication",
        ),
        ToolParameter(
            name="new_item",
            type=str,
            required=True,
            description="The new todo item description",
            example="Complete user authentication feature",
        ),
    ],
    examples=[{"old_pattern": "User Authentication", "new_item": "Complete user authentication feature"}],
    returns="Returns a dictionary with success, message, and other fields",
)

GET_TODO_SUMMARY_SCHEMA = ToolSchema(
    name="get_todo_summary",
    description="Get a summary of the todo list. Use to check task progress.",
    parameters=[],
    examples=[{}],
    returns="Returns a dictionary with success, project_name, todo_file, total_todos, completed_todos, pending_todos, completion_rate, and other fields",
)

LIST_TODO_FILES_SCHEMA = ToolSchema(
    name="list_todo_files",
    description="List all todo list files. Use to view historical todo lists.",
    parameters=[],
    examples=[{}],
    returns="Returns a dictionary with success, files (list), count, and other fields",
)

ADD_EXECUTION_RECORD_SCHEMA = ToolSchema(
    name="add_execution_record",
    description="(Deprecated) Execution records have been merged into the logging system. Calling this tool silently succeeds without writing to the todo list.",
    parameters=[
        ToolParameter(
            name="record",
            type=str,
            required=False,
            description="Execution record description (no longer written, kept for backward compatibility)",
            example="Completed user authentication API development",
            aliases=["description", "details", "message", "summary", "content", "text", "task", "action", "result", "note"],
        )
    ],
    examples=[{"record": "Completed user authentication API development"}],
    returns="Returns a dictionary with success, message fields",
)

ADD_TODO_SCHEMA = ADD_TODO_ITEM_SCHEMA
COMPLETE_TODO_SCHEMA = MARK_TODO_COMPLETED_SCHEMA
LIST_TODOS_SCHEMA = GET_TODO_SUMMARY_SCHEMA


# ==================== MCP Tools Schemas ====================

LIST_MCP_TOOLS_SCHEMA = ToolSchema(
    name="list_mcp_tools",
    description="List all available MCP (Model Context Protocol) tools. MCP tools come from external servers and provide file system, database, web search, and other capabilities.",
    parameters=[],
    examples=[{}, {"server_filter": "filesystem"}],
    returns="Returns a dictionary with success, tools (tool dictionary), count (number of tools), connected_servers (list of connected servers), and other fields",
)

CALL_MCP_TOOL_SCHEMA = ToolSchema(
    name="call_mcp_tool",
    description="Call an MCP (Model Context Protocol) tool. MCP tools come from external servers and can perform file operations, database queries, web searches, and other tasks.",
    parameters=[
        ToolParameter(
            name="tool_name",
            type=str,
            required=True,
            description="MCP tool name, in the format 'server_name.tool_name' or just the tool name directly",
            example="filesystem.read_file",
            aliases=["tool", "name", "function"],
        ),
        ToolParameter(
            name="arguments",
            type=dict,
            required=False,
            description="Arguments to pass to the MCP tool",
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
    returns="Returns a dictionary with success, result (tool execution result), error (error message if any), and other fields",
)

GET_MCP_STATUS_SCHEMA = ToolSchema(
    name="get_mcp_status",
    description="Get MCP (Model Context Protocol) server status. Displays configured servers, connection status, and available tools.",
    parameters=[],
    examples=[{}, {"detailed": True}],
    returns="Returns a dictionary with success, servers (server status list), connected_count (number of connected servers), total_count (total number of servers), and other fields",
)


# ==================== Skills Schemas ====================
# run_skills is the single entry point for all skills (three modes: __list__, __info__, execute)


# ==================== 所有工具schema的字典 ====================
ALL_SCHEMAS = {
    # Atomic Tools
    "run_shell": RUN_SHELL_SCHEMA,
    "finalize_task": FINALIZE_TASK_SCHEMA,
    "run_skills": RUN_SKILLS_SCHEMA,
    # Web Tools
    "search_web": SEARCH_WEB_SCHEMA,
    "fetch_url": FETCH_URL_SCHEMA,
    # Todo Tools (新名称)
    "add_todo_item": ADD_TODO_ITEM_SCHEMA,
    "mark_todo_completed": MARK_TODO_COMPLETED_SCHEMA,
    "update_todo_item": UPDATE_TODO_ITEM_SCHEMA,
    "get_todo_summary": GET_TODO_SUMMARY_SCHEMA,
    "list_todo_files": LIST_TODO_FILES_SCHEMA,
    "add_execution_record": ADD_EXECUTION_RECORD_SCHEMA,
    # MCP Tools
    "list_mcp_tools": LIST_MCP_TOOLS_SCHEMA,
    "call_mcp_tool": CALL_MCP_TOOL_SCHEMA,
    "get_mcp_status": GET_MCP_STATUS_SCHEMA,
}


def get_all_schemas():
    """获取所有工具schema"""
    return {**ALL_SCHEMAS}


def get_schema(tool_name: str):
    """获取特定工具的schema"""
    return ALL_SCHEMAS.get(tool_name)
