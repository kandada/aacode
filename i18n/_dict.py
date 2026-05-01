# i18n 翻译字典
# key → {"en": "...", "zh": "..."}

TRANSLATIONS = {
    # ─── Skills ───
    "skills.disabled":           {"en": "ℹ️ Skills feature disabled", "zh": "ℹ️ Skills功能已禁用"},
    "skills.auto_discover_disabled": {"en": "ℹ️ Skills auto-discovery disabled", "zh": "ℹ️ Skills自动发现已禁用"},
    "skills.none_found":         {"en": "ℹ️ No Skills found", "zh": "ℹ️ 未发现任何Skills"},
    "skills.discovered":         {"en": "🔍 Discovered {count} Skills (from SKILL.md)", "zh": "🔍 发现 {count} 个Skills（从 SKILL.md 提取）"},
    "skills.enabled_count":      {"en": "✅ Auto-enabled {count} Skills", "zh": "✅ 已自动启用 {count} 个Skills"},
    "skills.enabled_list":       {"en": "✅ Enabled {count} Skills: {list}", "zh": "✅ 启用 {count} 个Skills: {list}"},
    "skills.registered_tools":   {"en": "✅ Registered {count} skill tool functions", "zh": "✅ 已注册 {count} 个Skill工具函数（支持多功能）"},
    "skills.skill_item":         {"en": "- ✅ {name}: {desc}", "zh": "- ✅ {name}: {desc}"},

    # ─── Tools / Registry ───
    "tools.registered":          {"en": "✅ Registered {count} tools to registry", "zh": "✅ 已注册 {count} 个工具到注册表"},

    # ─── Agent / Task ───
    "agent.start_task":          {"en": "🤖 MainAgent starting task: {task}", "zh": "🤖 主Agent开始执行任务: {task}"},
    "agent.task_done_summary":   {"en": "✅ Task complete: {summary}", "zh": "✅ 任务完成: {summary}"},
    "agent.task_done_elapsed":   {"en": "✅ Done ({elapsed}s)"},
    "agent.max_iterations":      {"en": "⚠️  Max iterations reached, task may be incomplete", "zh": "⚠️  达到最大迭代次数，任务可能未完成"},
    "agent.continue_hint":       {"en": "💡 Tip: continue the session to complete remaining work", "zh": "💡 提示：你可以继续执行追加任务来完成剩余工作"},
    "agent.iteration":           {"en": "🔄 Iteration {n}/{max}", "zh": "🔄 迭代 {n}/{max}"},
    "agent.session_reuse":       {"en": "📋 Reusing session: {id}", "zh": "📋 复用会话ID: {id}"},
    "agent.session_hint":        {"en": "💡 Tip: use --session {id} to continue this session", "zh": "💡 提示: 使用 --session {id} 可以继续此会话"},
    "agent.log_start":           {"en": "📝 Start logging: {file}", "zh": "📝 开始记录任务日志: {file}"},
    "agent.log_saved":           {"en": "📋 Task log saved: {file}", "zh": "📋 任务日志已保存: {file}"},
    "agent.start_loop":          {"en": "🚀 Starting ReAct loop, max {n} iterations", "zh": "🚀 开始ReAct循环，最多{n}次迭代"},
    "agent.history_loaded":      {"en": "📜 Loaded {n} history messages into context", "zh": "📜 已加载 {n} 条历史消息到上下文"},
    "agent.react_loop_failed":   {"en": "❌ ReAct loop failed: {e}", "zh": "❌ ReAct循环执行失败: {e}"},
    "agent.clean_web_tools":     {"en": "⚠️  Error cleaning web_tools: {e}", "zh": "⚠️  清理web_tools时出错: {e}"},

    # ─── Model / API ───
    "model.thinking":            {"en": "🤖 Thinking...", "zh": "🤖 模型思考中"},
    "model.call_failed":         {"en": "\n⚠️  Model call failed! Check:", "zh": "\n⚠️  模型调用遇到问题！请检查："},
    "model.auth_failed":         {"en": "\n🔑 API authentication failed! Check:", "zh": "\n🔑 API认证失败！请检查："},
    "model.network_failed":      {"en": "\n🌐 Network connection failed! Check:", "zh": "\n🌐 网络连接失败！请检查："},
    "model.quota_error":         {"en": "\n📊 API quota/limit error! Check:", "zh": "\n📊 API配额或限制错误！请检查："},
    "model.suggestion":          {"en": "\n💡 Suggestions:", "zh": "\n💡 建议："},
    "model.multimodal_detected": {"en": "🔍 Multimodal model detected: {name}", "zh": "🔍 检测到多模态模型: {name}"},
    "model.multimodal_use_main": {"en": "✅ Multimodal tools will use main model: {name}", "zh": "✅ 多模态工具将使用主模型: {name}"},
    "model.no_api_key":          {"en": "❌ API Key not set! Configure in client Settings or run aacode init.", "zh": "❌ API Key 未设置！请在客户端 Settings 中配置 API Key，或运行 aacode init 设置。"},
    "model.minimax_config":      {"en": "✅ Created MiniMax multimodal config", "zh": "✅ 已创建MiniMax多模态配置"},

    # ─── Context / Compaction ───
    "context.compact_start":     {"en": "📦 Performing smart context compaction...", "zh": "📦 执行智能上下文缩减..."},
    "context.compact_done":      {"en": "✅ Smart context compaction done: {msg_count} messages | Tokens: {old} → {new} ({pct:.1f}% reduced)", "zh": "✅ 智能上下文缩减完成：{msg_count} 条消息 | Token: {old} → {new} (减少 {pct:.1f}%)"},
    "context.no_messages":       {"en": "✅ No intermediate messages to reduce", "zh": "✅ 没有中间消息需要缩减"},
    "context.below_threshold":   {"en": "✅ Message count below threshold, no reduction needed", "zh": "✅ 消息数量未超过阈值，无需缩减"},
    "context.analysis_integrated": {"en": "📊 Project analysis integrated into system prompt", "zh": "📊 项目分析结果已集成到系统提示中"},
    "context.monitor":           {"en": "📊 Context size: ~{tokens} tokens | System: {sys} | User: {user} | Assistant: {asst}", "zh": "📊 上下文大小监控：当前约{tokens} tokens | 系统: {sys} | 用户: {user} | Assistant: {asst}"},
    "context.smart_summary_fail": {"en": "⚠️  Smart summary failed: {e}", "zh": "⚠️  智能摘要生成失败，使用简单摘要: {e}"},
    "context.save_content_fail": {"en": "⚠️  Save {type} content failed: {e}", "zh": "⚠️  保存{type}内容失败: {e}"},

    # ─── Sub Agent ───
    "subagent.task_start":       {"en": "\n🔄 SubAgent {id} starting task", "zh": "\n🔄 子Agent {id} 开始任务"},
    "subagent.result_submitted": {"en": "✅ SubAgent {id} submitted result", "zh": "✅ 子Agent {id} 提交结果"},

    # ─── Multi agent ───
    "multi.task_done":           {"en": "📨 Sub-task complete: {id}", "zh": "📨 子任务完成: {id}"},
    "multi.task_result":         {"en": "Result: {result}", "zh": "结果: {result}"},

    # ─── Session ───
    "session.load_error":        {"en": "⚠️  Failed to load session index: {e}", "zh": "⚠️ 加载会话索引失败: {e}"},
    "session.save_error":        {"en": "⚠️  Failed to save session: {e}", "zh": "⚠️ 保存会话失败: {e}"},
    "session.load_session_error":{"en": "⚠️  Failed to load session: {e}", "zh": "⚠️ 加载会话失败: {e}"},
    "session.save_id_error":     {"en": "⚠️  Failed to save session ID: {e}", "zh": "⚠️ 保存当前会话ID失败: {e}"},

    # ─── Config ───
    "config.load_error":         {"en": "⚠️  Config load failed: {e}", "zh": "⚠️ 配置文件加载失败: {e}"},
    "config.save_error":         {"en": "⚠️  Config save failed: {e}", "zh": "⚠️ 配置文件保存失败: {e}"},

    # ─── CLI ───
    "cli.target_project":        {"en": "🎯 Target project: {path}", "zh": "🎯 目标项目: {path}"},
    "cli.work_dir":              {"en": "📁 Working directory: {path}", "zh": "📁 工作目录: {path}"},
    "cli.aacode_work_dir":       {"en": "📁 aacode work dir: {path}", "zh": "📁 aacode工作目录: {path}"},
    "cli.target_project_dir":    {"en": "🎯 Target project dir: {path}", "zh": "🎯 目标项目目录: {path}"},
    "cli.start_task":            {"en": "🎯 Starting task: {task}", "zh": "🎯 开始任务: {task}"},
    "cli.init_loaded":           {"en": "📝 Init instructions loaded ({n} chars)", "zh": "📝 初始化指令已加载 ({n} 字)"},
    "cli.mapper_init_ok":        {"en": "✅ Enhanced class-method mapper initialized (multi-language)", "zh": "✅ 增强版类方法映射器初始化成功（支持多语言）"},
    "cli.mapper_init_fail":      {"en": "⚠️  Cannot import enhanced mapper: {e}", "zh": "⚠️  无法导入增强版类方法映射器: {e}"},
    "cli.mapper_basic_ok":       {"en": "✅ Basic class-method mapper initialized (Python only)", "zh": "✅ 基础版类方法映射器初始化成功（仅Python）"},
    "cli.mapper_basic_fail":     {"en": "⚠️  Cannot import mapper: {e}", "zh": "⚠️  无法导入类方法映射器: {e}"},
    "cli.analyze_start":         {"en": "🔍 Starting project analysis...", "zh": "🔍 开始分析项目结构..."},
    "cli.analyze_pre_task":      {"en": "🔍 Analyzing project structure before task...", "zh": "🔍 任务开始前分析项目结构..."},
    "cli.analyze_done":          {"en": "✅ Project analysis complete:", "zh": "✅ 项目结构分析完成:"},
    "cli.analyze_struct_file":   {"en": "   - Structure file: {file}", "zh": "   - 结构文件: {file}"},
    "cli.analyze_lines":         {"en": "   - {lang}: {count} files, {lines} lines", "zh": "   - {lang}: {count} 个文件, {lines} 行"},
    "cli.analyze_saved":         {"en": "📝 Structure map saved: {file}", "zh": "📝 项目结构映射已保存到: {file}"},
    "cli.todo_creating":         {"en": "📋 Creating task todo list...", "zh": "📋 创建任务待办清单..."},
    "cli.todo_created":          {"en": "📋 Creating todo: {file}", "zh": "📋 创建待办清单: {file}"},
    "cli.task_done":             {"en": "✅ Task complete!", "zh": "✅ 任务完成!"},
    "cli.session_id_info":       {"en": "📋 Session ID: {id}", "zh": "📋 会话ID: {id}"},
    "cli.iterations_info":       {"en": "Iterations: {n}", "zh": "迭代次数: {n}"},
    "cli.final_status":          {"en": "Final status: {status}", "zh": "最终状态: {status}"},
    "cli.exec_time":             {"en": "Execution time: {time}s", "zh": "执行时间: {time}秒"},
    "cli.save_config":           {"en": "✅ Created default config: {file}"},
    "cli.save_env":              {"en": "✅ Saved to {file}", "zh": "✅ 已保存到 {file}"},
    "cli.continue_prompt":       {"en": "🔄 Continue? (y/n, default y): ", "zh": "🔁 是否继续执行其他任务? (y/n，默认y): "},
    "cli.done_divider":          {"en": "==================================================", "zh": "=================================================="},

    # ─── Init ───
    "init.start":                {"en": "🚀 Initializing AACode...", "zh": "🚀 初始化AACode程序..."},
    "init.python_ver":           {"en": "❌ Python 3.8+ required", "zh": "❌ 需要Python 3.8或更高版本"},
    "init.done":                 {"en": "✅ Initialization complete!", "zh": "✅ 初始化完成！"},
    "init.complete_msg":         {"en": "Use: python aacode/main.py -p <project> 'task'", "zh": "使用: python aacode/main.py -p <项目> '任务'"},

    # ─── Network / URL ───
    "net.adjust_url_dup":        {"en": "🔧 Adjust URL: {old} -> {new}", "zh": "🔧 调整URL: {old} -> {new}"},
    "net.adjust_url_path":       {"en": "🔧 Adjust URL: {old} -> {new}", "zh": "🔧 调整URL: {old} -> {new}"},
    "net.add_anthropic_path":    {"en": "🔧 Add path: {old} -> {new}", "zh": "🔧 添加路径: {old} -> {new}"},

    # ─── Web ───
    "web.save_fetch_fail":       {"en": "⚠️  Save web_fetch result failed: {e}", "zh": "⚠️  保存web_fetch结果失败: {e}"},

    # ─── Error detail lines ───
    "api.check_key":             {"en": "1. Is API key correct", "zh": "1. API密钥是否正确"},
    "api.check_env":             {"en": "2. Is LLM_API_KEY env var set", "zh": "2. 环境变量 LLM_API_KEY 是否设置"},
    "api.check_network":         {"en": "1. Is network connection working", "zh": "1. 网络连接是否正常"},
    "api.check_firewall":        {"en": "3. Firewall or proxy settings", "zh": "3. 防火墙或代理设置"},
    "api.check_endpoint":        {"en": "2. Is the API endpoint reachable", "zh": "2. API服务端点是否可达"},
    "api.check_service_status":  {"en": "1. API service status", "zh": "1. API服务状态"},
    "api.check_model_name":      {"en": "2. Is model name correct", "zh": "2. 模型名称是否正确"},
    "api.check_params":          {"en": "3. Are request parameters valid", "zh": "3. 请求参数是否有效"},
    "api.check_quota":           {"en": "1. Is API quota exhausted", "zh": "1. API配额是否用完"},
    "api.check_rate_limit":      {"en": "2. Is rate limit reached", "zh": "2. 是否达到速率限制"},
    "api.check_balance":         {"en": "3. Is account balance sufficient", "zh": "3. 账户余额是否充足"},
    "api.check_service_avail":   {"en": "4. Is API service available", "zh": "4. API服务是否可用"},
    "api.check_permission":      {"en": "3. Does API key have permissions", "zh": "3. API密钥是否有权限"},
    "api.contact_support":       {"en": "- Contact technical support", "zh": "- 联系技术支持"},

    # ─── Sandbox ───
    "sandbox.created":           {"en": "✅ Sandbox created: {name}", "zh": "✅ 沙箱已创建: {name}"},
    "sandbox.cleaned":           {"en": "✅ Sandbox cleaned: {name}", "zh": "✅ 沙箱已清理: {name}"},

    # ─── main.py analysis / CLI ───
    "cli.perm_error_mkdir":      {"en": "❌ Permission error: cannot create dir '{path}'\n   Error: {e}\n   Check directory permissions", "zh": "❌ 权限错误: 无法创建项目目录 '{path}'\n   错误信息: {e}\n   请检查目录权限或使用有写入权限的目录"},
    "cli.perm_error_write":      {"en": "❌ Permission error: no write permission for '{path}'\n   Error: {e}\n   Use 'chmod' or choose another directory", "zh": "❌ 权限错误: 对目录 '{path}' 没有写入权限\n   错误信息: {e}\n   请使用 'chmod' 命令修改目录权限或选择其他目录"},
    "cli.analyze_found_files":   {"en": "📁 Found {n} files, successfully analyzed {m} code files", "zh": "📁 找到 {n} 个文件，成功分析 {m} 个代码文件"},
    "cli.analyze_found_py":      {"en": "📁 Found {n} Python files", "zh": "📁 找到 {n} 个Python文件"},
    "cli.analyze_ok_count":      {"en": "✅ Successfully analyzed {n} files", "zh": "✅ 成功分析 {n} 个文件"},
    "cli.analyze_mapper_file":   {"en": "   - Mapper file: {file}", "zh": "   - 映射文件: {file}"},
    "cli.analyze_python_done":   {"en": "✅ Python project analysis complete:", "zh": "✅ Python项目结构分析完成:"},
    "cli.analyze_classes":       {"en": "   - Classes: {n}", "zh": "   - 类数量: {n}"},
    "cli.analyze_functions":     {"en": "   - Functions: {n}", "zh": "   - 函数数量: {n}"},
    "cli.analyze_files":         {"en": "   - Files: {n}", "zh": "   - 文件数量: {n}"},
    "cli.todo_created_ok":       {"en": "✅ Todo list created: {path}", "zh": "✅ 待办清单已创建: {path}"},
    "cli.task_exec_failed":      {"en": "❌ Task execution failed: {e}", "zh": "❌ 任务执行失败: {e}"},
    "cli.cleanup_error":         {"en": "⚠️  Error cleaning up: {e}", "zh": "⚠️  清理资源时出错: {e}"},
    "cli.found_todos":           {"en": "📋 Found {n} todo lists:", "zh": "📋 发现 {n} 个待办清单:"},
    "cli.found_logs":            {"en": "📝 Found {n} session logs", "zh": "📝 发现 {n} 个会话日志"},
    "cli.file_item":             {"en": "  {i}. {name}", "zh": "  {i}. {name}"},
    "cli.file_detail":           {"en": "  - {name} ({size} bytes)", "zh": "  - {name} ({size} bytes)"},
    "cli.todo_preview":          {"en": "     Content: {line}...", "zh": "     内容: {line}..."},
    "cli.log_last_lines":        {"en": "📄 {name} (last 20 lines):", "zh": "📄 {name} (最后20行):"},
    "cli.try_resume":            {"en": "🔄 Trying to resume recent task...", "zh": "🔄 尝试恢复最近的任务..."},
    "cli.found_todo_resume":     {"en": "📋 Found todo: {name}", "zh": "📋 找到待办清单: {name}"},
    "cli.original_task":         {"en": "🎯 Original task: {task}", "zh": "🎯 原始任务: {task}"},
    "cli.continue_task":         {"en": "🔄 Continue task: {task}", "zh": "🔄 继续任务: {task}"},
    "cli.start_exec":            {"en": "🎯 Starting execution: {input}", "zh": "🎯 开始执行任务: {input}"},
    "cli.exec_error_result":     {"en": "❌ Task failed: {error}", "zh": "❌ 任务执行失败: {error}"},
    "cli.exec_complete":         {"en": "✅ Task complete!", "zh": "✅ 任务完成!"},
    "cli.exec_iterations":       {"en": "Iterations: {n}", "zh": "迭代次数: {n}"},
    "cli.exec_time_sec":         {"en": "Execution time: {t}s", "zh": "执行时间: {t}秒"},
    "cli.session_id_show":       {"en": "Session ID: {id}", "zh": "会话ID: {id}"},
    "cli.session_reuse_hint":    {"en": "Use --session {id} to continue", "zh": "使用 --session {id} 可以继续此会话"},
    "cli.exec_error":            {"en": "❌ Execution error: {e}", "zh": "❌ 执行出错: {e}"},
    "cli.detect_target":         {"en": "🎯 Detected target project: {path}", "zh": "🎯 检测到目标项目: {path}"},
    "cli.task_complete":         {"en": "✅ Task complete!", "zh": "✅ 任务完成!"},
    "cli.session_id_label":      {"en": "📋 Session ID: {id}", "zh": "📋 会话ID: {id}"},
    "cli.sample_run":            {"en": "🚀 Run {path}:", "zh": "🚀 运行 {path}:"},
    "cli.sample_output":         {"en": "✅ Output: {out}", "zh": "✅ 输出: {out}"},
    "cli.sample_error":          {"en": "❌ Error: {msg}", "zh": "❌ 错误: {msg}"},
    "cli.sample_analyze":        {"en": "💡 Analysis:", "zh": "💡 错误分析:"},
    "cli.sample_import_err":     {"en": "   - Import error: missing dependency module", "zh": "   - 导入错误: 缺少依赖模块"},
    "cli.sample_install_hint":   {"en": "   - Suggestion: check if dependencies need installing", "zh": "   - 建议: 检查是否需要安装依赖包"},
    "cli.sample_dir_hint":       {"en": "   - Or: file may need to run in specific directory", "zh": "   - 或者: 文件可能需要在特定目录运行"},

    # ─── Todo ───
    "todo.added":                {"en": "✅ Added todo [{id}]: {item}", "zh": "✅ 已添加待办事项 [#{id}]: {item}"},
}
