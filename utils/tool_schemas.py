# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

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
    description=(
        "Execute a shell command (read/write files, grep/find, git, tests, builds; pipes and "
        "redirection supported). Always check returncode for success. Quote paths with spaces. "
        "Long-running processes: action=exec (default), spawn (returns process_id), check, read, "
        "write, kill, or jobs."
    ),
    parameters=[
        ToolParameter(
            name="command",
            type=str,
            required=True,
            default="",
            description="Shell command to execute. Required for exec/spawn; optional for check/read/write/kill.",
            example='python -c "import sys; print(sys.version)"',
            aliases=["cmd", "shell", "script", "exec_cmd"],
        ),
        ToolParameter(
            name="timeout",
            type=int,
            required=False,
            default=30,
            description="Timeout in seconds (default 30).",
            example=60,
            aliases=["time_limit", "max_time", "wait"],
        ),
        ToolParameter(
            name="stdin_input",
            type=str,
            required=False,
            description="stdin content for exec (one-shot) or write (running process). Use \\n for newlines.",
            example="5\\n3\\n",
            aliases=["input", "stdin"],
        ),
        ToolParameter(
            name="max_output",
            type=int,
            required=False,
            default=20000,
            description="Max output characters (default 20000; full_output=true disables). Truncated output is archived.",
            example=20000,
            aliases=["max_chars", "limit", "output_limit"],
        ),
        ToolParameter(
            name="max_output_lines",
            type=int,
            required=False,
            default=500,
            description="Max output lines (default 500).",
            example=500,
            aliases=["output_lines", "max_result_lines"],
        ),
        ToolParameter(
            name="full_output",
            type=bool,
            required=False,
            default=False,
            description="Return full stdout/stderr (may cost many tokens).",
            example=False,
            aliases=["full", "unlimited"],
        ),
        ToolParameter(
            name="stop_on_exit",
            type=bool,
            required=False,
            default=False,
            description="Stop waiting for child processes' pipes once the main process exits. Use for commands that spawn long-running children.",
            example=True,
            aliases=["detach", "no_wait_children"],
        ),
        ToolParameter(
            name="action",
            type=str,
            required=False,
            default="exec",
            description="exec (default), spawn, check, read, write, kill, or jobs.",
            example="spawn",
            aliases=["mode", "op"],
        ),
        ToolParameter(
            name="background",
            type=bool,
            required=False,
            default=False,
            description="Run in the background (equivalent to action=spawn). Use for builds, tests, downloads, or servers.",
            example=True,
            aliases=["run_in_background", "async"],
        ),
        ToolParameter(
            name="process_id",
            type=str,
            required=False,
            description="process_id from spawn; required for check/read/write/kill.",
            example="a1b2c3d4e5f6",
            aliases=["pid", "id"],
        ),
        ToolParameter(
            name="max_lines",
            type=int,
            required=False,
            description="Keep only the last N output lines (exec capture, spawn buffer, or read tail).",
            example=500,
            aliases=["tail_lines", "buffer_size"],
        ),
        ToolParameter(
            name="idle_timeout",
            type=int,
            required=False,
            description="Kill the process if no output is received for this many seconds. Useful for detecting hung processes. Works with both action=\"exec\" and action=\"spawn\".",
            example=60,
            aliases=["idle_limit", "no_output_timeout"],
        ),
        ToolParameter(
            name="use_pty",
            type=bool,
            required=False,
            default=False,
            description="Use a pseudo-terminal (PTY) instead of pipes. Required for interactive tools (simulators, REPLs, SSH) that buffer output differently with pipes. Only works on Linux/macOS.",
            example=True,
            aliases=["pty", "tty"],
        ),
    ],
    examples=[
        {"command": "ls -la", "description": "List all files in current directory (including hidden files)"},
        {"command": "npm run build", "background": True, "description": "Run a long build as a background process"},
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
    returns="""Returns a dictionary. Fields vary by action:

action="exec" (synchronous):
- success (bool): Whether the tool executed (always True unless tool exception)
- returncode (int): Command exit code (0=success, non-zero=failure)
- stdout (str): Standard output
- stderr (str): Error output
- command (str): The executed command
- working_directory (str): Working directory

action="spawn":
- success (bool): True
- process_id (str): Unique ID for check/read/write/kill
- initial_stdout (str): First batch of output
- mode (str): "pty" if use_pty=True, else "pipe"

action="check":
- success (bool): True
- process_id (str): The process ID
- running (bool): Whether the process is still running
- returncode (int or null): Exit code if exited, null if running

action="read":
- success (bool): True
- process_id (str): The process ID
- stdout (str): Recent output lines
- stderr (str): Recent error lines
- running (bool): Whether the process is still running

action="write":
- success (bool): True
- process_id (str): The process ID

action="kill":
- success (bool): True
- process_id (str): The process ID
- returncode (int): Final exit code""",
)


RUN_SKILLS_SCHEMA = ToolSchema(
    name="run_skills",
    description=(
        "Execute or inspect a pre-defined skill. Use skill_name='__list__' to list, "
        "skill_name='__info__' with params={'skill_name': ...} for details, or "
        "skill_name='<name>' with params to execute. Multi-function skills take a 'func' key."
    ),
    parameters=[
        ToolParameter(
            name="skill_name",
            type=str,
            required=False,
            description="Skill name, __list__, or __info__. Falls back to params.skill_name.",
            example="pandas",
            aliases=["skill", "name"],
        ),
        ToolParameter(
            name="params",
            type=dict,
            required=False,
            description="Skill parameters; include 'func' for multi-function skills.",
            example={"code": "df.describe()"},
            aliases=["arguments", "args", "kwargs"],
        ),
        ToolParameter(
            name="timeout",
            type=int,
            required=False,
            description="Timeout in seconds (default from config).",
            example=120,
            aliases=["time_limit", "max_time"],
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
            "timeout": 120,
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
    description=(
        "Search the web. Supports multiple search backends auto-detected by URL: "
        "SearXNG (self-hosted, no API key), Brave Search, Google CSE, Bing, SerpAPI. "
        "If all configured backends fail, falls back to scraping Bing/Sogou HTML results. "
        "Use timeout parameter to control how long to wait (default 8s, increase for slow networks)."
    ),
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
        ToolParameter(
            name="timeout",
            type=int,
            required=False,
            default=8,
            description="Timeout in seconds for the search request (default: 8)",
            example=15,
            aliases=["timeout_seconds", "time_limit"],
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


# ==================== Browser Tools Schemas (fastbrowser) ====================

FETCH_RENDERED_SCHEMA = ToolSchema(
    name="fetch_rendered",
    description="Fetch a URL in a real (headless) browser that executes JavaScript, then return the rendered text. Use for SPAs / JS-heavy pages that fetch_url cannot read.",
    parameters=[
        ToolParameter(
            name="url",
            type=str,
            required=True,
            description="URL to render",
            example="https://example.com/spa",
            aliases=["link", "uri", "address"],
        ),
        ToolParameter(
            name="max_chars",
            type=int,
            required=False,
            default=5000,
            description="Max returned characters (default 5000)",
            example=8000,
            aliases=["max_length", "max_content_length"],
        ),
    ],
    examples=[{"url": "https://example.com/spa"}],
    returns="Returns a dictionary with success, url, title, content, content_length",
)

BROWSER_CALL_SCHEMA = ToolSchema(
    name="browser_call",
    description="Call any fastbrowser browser/accessibility tool by name. 'args' is that tool's parameters as an object. Returns the raw result by default; oversized results are auto-compacted and archived.",
    parameters=[
        ToolParameter(
            name="name",
            type=str,
            required=True,
            description="Browser tool name (see browser_tools for the list)",
            example="ax_snapshot",
            aliases=["tool"],
        ),
        ToolParameter(
            name="args",
            type=dict,
            required=False,
            description="Tool parameters (default {})",
            example={},
            aliases=["params", "arguments"],
        ),
        ToolParameter(
            name="compact",
            type=bool,
            required=False,
            default=False,
            description="Return cleaned+truncated output and archive the full result (default false)",
            aliases=["clean"],
        ),
        ToolParameter(
            name="max_chars",
            type=int,
            required=False,
            default=0,
            description="Preview length for compact mode (default 6000)",
            aliases=["max_length"],
        ),
    ],
    examples=[{"name": "extract_text", "args": {}}],
    returns="Returns a dictionary with success, result (or compacted preview + archive path)",
)

BROWSER_TOOLS_SCHEMA = ToolSchema(
    name="browser_tools",
    description="Discover browser/accessibility tools. 'mode': 'names' (default), 'compact' (name+short desc+param names), 'full' (adds param types), or 'help' (full schema for ONE tool, pass 'name').",
    parameters=[
        ToolParameter(
            name="mode",
            type=str,
            required=False,
            default="names",
            description="Detail level: 'names' (default), 'compact', 'full', or 'help'",
            aliases=["detail", "level"],
        ),
        ToolParameter(
            name="name",
            type=str,
            required=False,
            description="With mode='help': the tool to describe",
            aliases=["tool"],
        ),
    ],
    examples=[{"mode": "names"}],
    returns="Returns a dictionary with success, mode, count, tools",
)

AX_ACT_SCHEMA = ToolSchema(
    name="ax_act",
    description="Accessibility (AX) perception + action across web and native desktop surfaces. action='snapshot' returns the accessibility tree (UiNode); other actions (click, double_click, right_click, type, scroll, press_key, focus, set_value, check, select, ...) act on an element by 'ref'.",
    parameters=[
        ToolParameter(
            name="action",
            type=str,
            required=True,
            description="Action name: 'snapshot' | click | double_click | right_click | focus | set_value | type | check | uncheck | select | scroll | press_key | increment | decrement | show_menu | raise | invoke",
            example="snapshot",
        ),
        ToolParameter(
            name="ref",
            type=str,
            required=False,
            description="Element ref: full (web:3:a / desktop:1234:0.2.1) or bare (a / #go / text=Go / role=button)",
            example="web:1:a",
            aliases=["selector", "id", "element"],
        ),
        ToolParameter(
            name="target",
            type=str,
            required=False,
            description="Surface id (e.g. web:3 / desktop:1234); defaults to active/first surface",
            example="desktop:1234",
        ),
        ToolParameter(
            name="text",
            type=str,
            required=False,
            description="Text for type action",
            example="hello",
        ),
        ToolParameter(
            name="value",
            type=str,
            required=False,
            description="Value for set_value / select",
        ),
        ToolParameter(
            name="key",
            type=str,
            required=False,
            description="Key for press_key",
            example="Tab",
        ),
        ToolParameter(
            name="dx",
            type=float,
            required=False,
            description="Horizontal scroll delta",
        ),
        ToolParameter(
            name="dy",
            type=float,
            required=False,
            description="Vertical scroll delta",
            example=300,
        ),
        ToolParameter(
            name="x",
            type=float,
            required=False,
            description="Screen x for a coordinate click (with y)",
        ),
        ToolParameter(
            name="y",
            type=float,
            required=False,
            description="Screen y for a coordinate click (with x)",
        ),
    ],
    examples=[{"action": "snapshot"}, {"action": "click", "ref": "web:1:a"}],
    returns="Returns the accessibility snapshot (tree/text) or the action result",
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
            required=True,
            description="Todo item ID (e.g. 't1', 't2'), returned by add_todo_item. ALWAYS include this parameter. Use the exact todo_id returned by add_todo_item.",
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
    examples=[{"todo_id": "t1"}],
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


# ==================== Multimodal Tools Schemas ====================

UNDERSTAND_IMAGE_SCHEMA = ToolSchema(
    name="understand_image",
    description="Understand image content - supports single or multiple images. Can be used to analyze screenshots, photos, design drafts, etc. This tool is especially suitable for scenarios where you need to view images but don't need to generate code.",
    parameters=[
        ToolParameter(
            name="image_path",
            type=str,
            required=True,
            description="Image path, supports single or multiple (comma separated). Example: 'screenshot.png' or 'img1.jpg,img2.png'",
            example="screenshot.png",
            aliases=["image", "path", "file"],
        ),
        ToolParameter(
            name="prompt",
            type=str,
            required=False,
            description="What do you want to know about the image? Example: 'What is the main content of this image?'",
            example="What is the main content of this image?",
            aliases=["question", "query"],
        ),
    ],
    returns="Returns a dictionary with success, description, images_count, and images fields",
)

UNDERSTAND_VIDEO_SCHEMA = ToolSchema(
    name="understand_video",
    description="Understand video content - analyze scenes, characters, actions, etc. in the video. Requires video file path.",
    parameters=[
        ToolParameter(
            name="video_path",
            type=str,
            required=True,
            description="Video file path",
            example="video.mp4",
            aliases=["video", "path", "file"],
        ),
        ToolParameter(
            name="prompt",
            type=str,
            required=False,
            description="What do you want to know about the video? Example: 'What happened in the video?'",
            example="What happened in the video?",
            aliases=["question", "query"],
        ),
    ],
    returns="Returns a dictionary with success, description, and video fields",
)

UNDERSTAND_UI_DESIGN_SCHEMA = ToolSchema(
    name="understand_ui_design",
    description="Understand UI design drafts/page screenshots and generate frontend code - an important tool for frontend development. Can analyze design drafts or page screenshots, describe UI layout, colors, components, etc., and try to generate corresponding HTML/CSS code. This tool combines multimodal understanding with frontend development knowledge, avoiding disconnection between understanding and code.",
    parameters=[
        ToolParameter(
            name="design_path",
            type=str,
            required=True,
            description="Design draft path, supports single or multiple (comma separated). Example: 'mockup.png' or 'desktop.png,mobile.png'",
            example="mockup.png",
            aliases=["design", "path", "image", "file"],
        ),
        ToolParameter(
            name="prompt",
            type=str,
            required=False,
            description="How do you want to analyze this design? Example: 'Please analyze this login page design'",
            example="Please analyze this login page design",
            aliases=["question", "query"],
        ),
        ToolParameter(
            name="generate_code",
            type=bool,
            required=False,
            default=True,
            description="Whether to generate frontend code, default is true",
            example=True,
            aliases=["code", "gen_code"],
        ),
    ],
    returns="Returns a dictionary with success, analysis, and code fields",
)

ANALYZE_IMAGE_CONSISTENCY_SCHEMA = ToolSchema(
    name="analyze_image_consistency",
    description="Analyze consistency across multiple images (people or objects) - used to check if people in multiple images are the same person, or if object styles are consistent. Suitable for image creation and video production scenarios.",
    parameters=[
        ToolParameter(
            name="image_paths",
            type=str,
            required=True,
            description="Multiple image paths, comma separated. Example: 'person1.jpg,person2.jpg'",
            example="person1.jpg,person2.jpg",
            aliases=["images", "paths", "files", "image_path"],
        ),
        ToolParameter(
            name="prompt",
            type=str,
            required=False,
            description="What aspects of consistency do you want to analyze?",
            example="Are these the same person?",
            aliases=["question", "query"],
        ),
    ],
    returns="Returns a dictionary with success, analysis, images_count, and images fields",
)


SEARCH_HISTORY_SCHEMA = ToolSchema(
    name="search_history",
    description=(
        "Search persisted conversation messages omitted from the model view. Searches content and "
        "tool call arguments; reasoning is excluded. Defaults to the current session."
    ),
    parameters=[
        ToolParameter(
            name="query",
            type=str,
            required=True,
            description="Text to find (case-insensitive).",
            example="E_CACHE_MISS",
            aliases=["q", "text", "keyword"],
        ),
        ToolParameter(
            name="session_id",
            type=str,
            required=False,
            description="Session ID (default: current).",
            example="session_20261021_150000_abcd1234",
            aliases=["session"],
        ),
        ToolParameter(
            name="scope",
            type=str,
            required=False,
            default="current",
            description="current or project.",
            example="project",
            aliases=["range"],
        ),
        ToolParameter(
            name="role",
            type=str,
            required=False,
            description="Role filter: user, assistant, tool, or system.",
            example="user",
            aliases=["role_filter"],
        ),
        ToolParameter(
            name="limit",
            type=int,
            required=False,
            default=20,
            description="Max matches (1-50).",
            example=20,
            aliases=["max_results", "count"],
        ),
        ToolParameter(
            name="offset",
            type=int,
            required=False,
            default=0,
            description="Pagination offset.",
            example=0,
            aliases=["skip"],
        ),
    ],
    returns="Matching messages with session ID, message index, role, timestamp, and a bounded snippet.",
)

READ_HISTORY_SCHEMA = ToolSchema(
    name="read_history",
    description=(
        "Read a bounded range of persisted conversation messages by message index. "
        "Use search_history first to find the relevant index. Never cat the session JSON. "
        "Returns role, timestamp, tool calls, and truncated content."
    ),
    parameters=[
        ToolParameter(
            name="session_id",
            type=str,
            required=False,
            description="Session ID to read. Defaults to the current session.",
            example="session_20261021_150000_abcd1234",
            aliases=["session"],
        ),
        ToolParameter(
            name="start_index",
            type=int,
            required=False,
            default=0,
            description="First message index to read (0-based).",
            example=120,
            aliases=["start", "from"],
        ),
        ToolParameter(
            name="max_messages",
            type=int,
            required=False,
            default=20,
            description="Maximum number of messages to return (1-50).",
            example=20,
            aliases=["limit", "count"],
        ),
        ToolParameter(
            name="max_chars",
            type=int,
            required=False,
            default=12000,
            description="Maximum total characters to return (1000-30000).",
            example=12000,
            aliases=["max_output", "chars"],
        ),
    ],
    returns="A bounded transcript with message indices and a continuation index.",
)


# ==================== Subagent Delegation ====================

DELEGATE_TASK_SCHEMA = ToolSchema(
    name="delegate_task",
    description=(
        "Delegate a self-contained subtask to a focused sub-agent with its own context, "
        "token budget, and tool subset. Returns a compact result, not the full transcript."
    ),
    parameters=[
        ToolParameter(
            name="task_description",
            type=str,
            required=True,
            description="A complete, self-contained description of the subtask.",
            example="Find all call sites of parse_config and summarize the required signature changes.",
            aliases=["task", "description", "prompt"],
        ),
        ToolParameter(
            name="task_type",
            type=str,
            required=False,
            default="general",
            description="One of: general, code, test, research. Selects the child's tool subset.",
            example="code",
        ),
        ToolParameter(
            name="context_strategy",
            type=str,
            required=False,
            default="isolated",
            description="isolated (default), minimal, or shared. Shared/minimal add a short project summary, never the full transcript.",
            example="isolated",
        ),
    ],
    examples=[
        {"task_description": "Run the test suite and summarize failures.", "task_type": "test"},
        {"task_description": "Research the current API rate limits.", "task_type": "research"},
    ],
    returns="Returns task_id, status, and a compact result with final answer, iterations, usage, and optional spill path.",
)


SUBMIT_RESULT_SCHEMA = ToolSchema(
    name="submit_result",
    description=(
        "Submit the final structured result for a sub-agent task. Call exactly once when the "
        "task is complete; do not call other tools afterwards."
    ),
    parameters=[
        ToolParameter(
            name="summary",
            type=str,
            required=True,
            description="Concise final answer / outcome for the parent agent.",
            example="Found 3 call sites; updated signatures in a.py and b.py.",
        ),
        ToolParameter(
            name="files_changed",
            type=list,
            required=False,
            description="Exact file paths changed or inspected.",
            example=["src/a.py", "src/b.py"],
        ),
        ToolParameter(
            name="next_steps",
            type=list,
            required=False,
            description="Remaining work or recommended next actions.",
            example=["Run the full test suite"],
        ),
        ToolParameter(
            name="errors",
            type=list,
            required=False,
            description="Unresolved errors or blockers.",
            example=["None"],
        ),
        ToolParameter(
            name="key_evidence",
            type=list,
            required=False,
            description="Short evidence lines (paths, symbols, outputs).",
            example=["src/a.py:42 calls parse_config"],
        ),
    ],
    returns="Acknowledges the recorded structured result.",
)


# ==================== Tool discovery / proxy schemas ====================
LIST_TOOL_SCHEMAS_SCHEMA = ToolSchema(
    name="list_tool_schemas",
    description=(
        "List tools available to this agent, including tools hidden by the current "
        "tool profile. Use this before asking for a schema you cannot see. Returns "
        "active/inactive status and a one-line description."
    ),
    parameters=[
        ToolParameter(
            name="query",
            type=str,
            required=False,
            default="",
            description="Optional case-insensitive filter on tool name/description.",
        ),
        ToolParameter(
            name="active_only",
            type=bool,
            required=False,
            default=False,
            description="Only list tools in the current profile's active schema set.",
        ),
    ],
    examples=[{"query": "browser", "active_only": False}],
    returns="A compact text list of tool names, status, and descriptions.",
)

GET_TOOL_SCHEMA_SCHEMA = ToolSchema(
    name="get_tool_schema",
    description=(
        "Return the full JSON schema (parameters, required flags, aliases, examples) "
        "for any registered tool, even one not currently advertised in the request. "
        "Pair with call_tool to use a discovered tool without changing profiles."
    ),
    parameters=[
        ToolParameter(
            name="name",
            type=str,
            required=True,
            description="Exact tool name, e.g. browser_call.",
        ),
    ],
    examples=[{"name": "browser_call"}],
    returns="JSON schema for the requested tool.",
)

CALL_TOOL_SCHEMA = ToolSchema(
    name="call_tool",
    description=(
        "Invoke any registered tool by name with a JSON arguments object. This is a "
        "profile-stable proxy for tools that are available but not advertised in the "
        "current tool profile; validate arguments with get_tool_schema first. Do not "
        "use it to call list_tool_schemas/get_tool_schema/call_tool recursively."
    ),
    parameters=[
        ToolParameter(
            name="name",
            type=str,
            required=True,
            description="Exact registered tool name.",
        ),
        ToolParameter(
            name="arguments",
            type=dict,
            required=False,
            default={},
            description="Arguments object passed to the tool after schema normalization.",
        ),
    ],
    examples=[{"name": "browser_call", "arguments": {"tool": "browser_tools", "args": {}}}],
    returns="The tool's raw result serialized as text.",
)


# ==================== 所有工具schema的字典 ====================
ALL_SCHEMAS = {
    # Tool discovery / proxy
    "list_tool_schemas": LIST_TOOL_SCHEMAS_SCHEMA,
    "get_tool_schema": GET_TOOL_SCHEMA_SCHEMA,
    "call_tool": CALL_TOOL_SCHEMA,
    # Atomic Tools
    "run_shell": RUN_SHELL_SCHEMA,
    "run_skills": RUN_SKILLS_SCHEMA,
    # Web Tools
    "search_web": SEARCH_WEB_SCHEMA,
    "fetch_url": FETCH_URL_SCHEMA,
    # Browser Tools (fastbrowser)
    "fetch_rendered": FETCH_RENDERED_SCHEMA,
    "browser_call": BROWSER_CALL_SCHEMA,
    "browser_tools": BROWSER_TOOLS_SCHEMA,
    "ax_act": AX_ACT_SCHEMA,
    # Todo Tools (新名称)
    "add_todo_item": ADD_TODO_ITEM_SCHEMA,
    "mark_todo_completed": MARK_TODO_COMPLETED_SCHEMA,
    "update_todo_item": UPDATE_TODO_ITEM_SCHEMA,
    "get_todo_summary": GET_TODO_SUMMARY_SCHEMA,
    "list_todo_files": LIST_TODO_FILES_SCHEMA,
    "add_execution_record": ADD_EXECUTION_RECORD_SCHEMA,
    # History retrieval tools
    "search_history": SEARCH_HISTORY_SCHEMA,
    "read_history": READ_HISTORY_SCHEMA,
    "delegate_task": DELEGATE_TASK_SCHEMA,
    "submit_result": SUBMIT_RESULT_SCHEMA,
    # MCP Tools
    "list_mcp_tools": LIST_MCP_TOOLS_SCHEMA,
    "call_mcp_tool": CALL_MCP_TOOL_SCHEMA,
    "get_mcp_status": GET_MCP_STATUS_SCHEMA,
    # Multimodal Tools
    "understand_image": UNDERSTAND_IMAGE_SCHEMA,
    "understand_video": UNDERSTAND_VIDEO_SCHEMA,
    "understand_ui_design": UNDERSTAND_UI_DESIGN_SCHEMA,
    "analyze_image_consistency": ANALYZE_IMAGE_CONSISTENCY_SCHEMA,
}


def get_all_schemas():
    """获取所有工具schema"""
    return {**ALL_SCHEMAS}


def get_schema(tool_name: str):
    """获取特定工具的schema"""
    return ALL_SCHEMAS.get(tool_name)
