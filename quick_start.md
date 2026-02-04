# AACode 快速开始指南

## 🚀 5分钟快速上手

### 步骤1: 环境准备

```bash
# 确保Python 3.8+已安装
python3 --version

# 克隆或下载项目
cd aacode
```

### 步骤2: 初始化配置

```bash
# 运行初始化脚本
python3 init.py

# 按提示输入配置：
# 1. 选择API URL (推荐: DeepSeek)
# 2. 输入API Key
# 3. 选择模型名称
```

**或者手动配置**:

创建 `.env` 文件：
```bash
LLM_API_KEY=your-llm-api-key
LLM_API_URL=https://api.deepseek.com/v1
LLM_MODEL_NAME=deepseek-chat
SEARCHXNG_URL=http://192.168.0.116:8080
```

### 步骤3: 运行第一个任务

```bash
# 使用生成的启动脚本
./run.sh -p examples/my_first_project "创建一个hello world程序"

# 或直接使用Python
python3 main.py -p examples/my_first_project "创建一个hello world程序"
```

### 步骤4: 查看结果

```bash
# 查看生成的文件
ls my_first_project/

# 运行生成的程序
python3 my_first_project/hello.py
```

---

## 📋 常用命令

### 基本使用

```bash
# 创建新项目
python3 main.py -p examples/project_name "任务描述"

# 继续现有项目
python3 main.py -p examples/existing_project "继续开发功能"

# 交互式模式
python3 main.py -p examples/project --interactive
```

---

## 💡 示例任务

### 示例1: 创建Web应用

```bash
python3 main.py -p examples/web_app "创建一个Flask Web应用，包含首页和关于页面"
```

### 示例2: 数据处理

```bash
python3 main.py -p examples/data_processor "创建一个CSV数据处理程序，读取data.csv并生成统计报告"
```

### 示例3: API客户端

```bash
python3 main.py -p examples/api_client "创建一个GitHub API客户端，获取用户信息"
```

### 示例4: 自动化脚本

```bash
python3 main.py -p examples/automation "创建一个文件备份脚本，自动备份指定目录"
```

---

## 🔧 配置说明

### 环境变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| LLM_API_KEY | AI模型API密钥 | sk-xxx |
| LLM_API_URL | API端点URL | https://api.deepseek.com/v1 |
| LLM_MODEL_NAME | 模型名称 | deepseek-chat |
| SEARCHXNG_URL | 搜索引擎URL（可选） | http://localhost:8080/search |

### 项目结构

```
my_project/
├── .aicode/              # AACode工作目录
│   ├── context/          # 上下文文件
│   ├── logs/             # 执行日志
│   ├── tests/            # 测试文件
│   └── todos/            # 待办清单
├── .env                  # 环境配置
├── init.md               # 项目指导原则
└── [你的代码文件]
```

---

## 🎯 最佳实践

### 1. 任务描述要清晰

✅ **好的描述**:
```
"创建一个Python程序，使用requests库获取天气API数据，
并将结果保存到weather.json文件"
```

❌ **不好的描述**:
```
"做个天气程序"
```

### 2. 分步骤执行复杂任务

对于复杂项目，分多次执行：

```bash
# 第一步：创建基础结构
python3 main.py -p examples/app "创建Flask应用基础结构"

# 第二步：添加功能
python3 main.py -p examples/app "添加用户认证功能"

# 第三步：测试
python3 main.py -p examples/app "为所有功能编写测试"
```

### 3. 利用项目指导原则

编辑 `init.md` 文件，添加项目特定的规则：

```markdown
# 项目指导原则

## 代码风格
- 使用PEP 8规范
- 函数名使用snake_case
- 类名使用PascalCase

## 测试要求
- 每个功能必须有单元测试
- 测试覆盖率不低于80%

## 文档要求
- 所有公共函数必须有docstring
- README.md必须包含使用示例
```

### 4. 查看执行日志

```bash
# 查看最新日志
ls -lt .aacode/logs/ | head -5

# 查看详细日志
cat .aacode/logs/agent_thought_and_action_*.log

# 查看待办清单
cat .aacode/todos/*.md
```

---

## 🐛 故障排除

### 问题1: API调用失败

**症状**: "模型调用失败: 401 Unauthorized"

**解决**:
```bash
# 检查API Key是否正确
echo $LLM_API_KEY

# 重新设置
export LLM_API_KEY="your-correct-key"
```

### 问题2: 权限错误

**症状**: "PermissionError: 无法创建项目目录"

**解决**:
```bash
# 使用有写入权限的目录
python3 main.py -p ~/projects/my_project "任务"

# 或修改目录权限
chmod 755 ./projects
```

### 问题3: 依赖缺失

**症状**: "ModuleNotFoundError: No module named 'openai'"

**解决**:
```bash
# 安装依赖
pip3 install -r requirements.txt

# 或使用国内镜像
pip3 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 问题4: 任务执行超时

**症状**: 任务长时间无响应

**解决**:
- 将复杂任务分解为多个小任务
- 增加max_iterations参数：`python3 main.py -p ./project "任务" --max-iterations 50`
- 检查网络连接

---

## 📚 进阶功能

### 1. 使用待办清单

AACode会自动创建待办清单，你可以查看进度：

```bash
# 查看待办清单
cat .aicode/todos/todo_*.md

# 查看完成情况
grep "✅" .aicode/todos/todo_*.md
```

### 2. 会话管理

```bash
# 列出所有会话
python3 -c "from main import AICoder; import asyncio; 
coder = AICoder('./project'); 
asyncio.run(coder.main_agent.list_sessions())"

# 切换会话
# (在交互模式中使用)
```

### 3. 自定义工具

在项目的 `init.md` 中添加自定义工具说明：

```markdown
## 自定义工具

### 数据库工具
- 使用SQLite存储数据
- 连接字符串: sqlite:///data.db

### API工具
- 基础URL: https://api.example.com
- 认证方式: Bearer Token
```

---

## 🎓 学习资源

### 文档
- [README](readme.md) - 项目概述


## 💬 获取帮助

### 常见问题

1. **如何更换AI模型？**
   - 修改 `.env` 文件中的配置

2. **如何查看详细日志？**
   - 查看 `.aicode/logs/` 目录

3. **如何添加新功能？**
   - 编辑 `init.md` 添加指导原则
   - 或直接在任务描述中说明

4. **如何提高成功率？**
   - 使用清晰的任务描述
   - 分步骤执行复杂任务
   - 提供足够的上下文信息

### 调试模式

```bash
# 启用详细输出
export DEBUG=1
python3 main.py -p ./project "任务"

# 查看完整日志
tail -f .aicode/logs/agent_thought_and_action_*.log
```

---

## 🎉 开始你的第一个项目

现在你已经准备好了！试试这个：

```bash
# 创建一个简单的待办事项应用
python3 main.py -p examples/todo_app "创建一个命令行待办事项应用，支持添加、删除、列出任务"

# 等待完成后
cd todo_app
python3 todo.py
```

祝你使用愉快！🚀

---

**文档版本**: v1.0  
**最后更新**: 2026-01-29
