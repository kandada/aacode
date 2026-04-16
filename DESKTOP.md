# 🖥️ AACode Desktop 客户端

AACode Desktop 是 AACode 的桌面图形界面版本，提供更友好的交互体验。

## 📥 下载

| 平台 | 下载链接 | 文件名 |
|------|----------|--------|
| macOS (Apple Silicon) | [下载](https://github.com/kandada/aacode/raw/main/desktop/AACode_1.6.1_aarch64.dmg) | AACode_1.6.1_aarch64.dmg |
| Windows | [下载](https://github.com/kandada/aacode/raw/main/desktop/aacode-desktop-1.6.1.exe) | aacode-desktop-1.6.1.exe |

## 🛠️ 安装步骤

### 1. 安装 Python 环境

AACode Desktop 依赖 Python 运行后端服务，请先安装 Python 3.12+。

#### macOS

```bash
# 方式一：官网下载（推荐）
# 访问 https://www.python.org/downloads/ 下载 macOS 安装包

# 方式二：Homebrew
brew install python@3.12

# 验证安装
python3 --version
```

#### Windows

```
1. 访问 https://www.python.org/downloads/ 下载 Windows 安装包
2. 运行安装程序，务必勾选 "Add Python to PATH"
3. 安装完成后打开命令提示符（CMD）或 PowerShell 验证：
```

```powershell
python --version
# 或
python3 --version
```

> ⚠️ Windows 用户请确保安装时勾选了 "Add Python to PATH"，否则后续命令无法识别 python。

### 2. 安装 AACode 及依赖

#### 方式一：pip 安装（推荐）

```bash
# macOS / Linux
pip3 install aacode

# Windows
pip install aacode
```

#### 方式二：从源码安装

```bash
git clone https://github.com/kandada/aacode.git
cd aacode
```

安装依赖：

```bash
# macOS / Linux
pip3 install -r requirements.txt

# Windows
pip install -r requirements.txt
```

### 3. 初始化配置
进入客户端进入settings页面配置模型秘钥等


### 4. 安装桌面客户端

#### macOS

1. 双击下载的 `AACode_1.6.1_aarch64.dmg`
2. 将 AACode 拖入 Applications 文件夹
3. 首次打开时，如果提示"无法验证开发者"，前往 **系统设置 → 隐私与安全性**，点击"仍要打开"

#### Windows

1. 双击运行 `aacode-desktop-1.6.1.exe`
2. 按安装向导完成安装
3. 安装完成后从开始菜单或桌面快捷方式启动

## 🚀 使用方法

1. 启动 AACode Desktop
2. 在设置中配置 API Key、模型等信息（如果还没通过 `aacode init` 配置）
3. 选择或创建项目目录
4. 在输入框中描述你的任务，回车开始执行

### 使用建议

- 在项目目录中创建 `init.md` 文件，详细描述项目规范和设计思路，Agent 会参考它来生成更符合预期的代码
- 复杂任务建议分步执行，每次聚焦一个子任务
- 任务描述越清晰，结果越好

## ❓ 常见问题

### Python 找不到

Windows 用户如果遇到 `python: command not found`：
1. 确认安装 Python 时勾选了 "Add Python to PATH"
2. 或手动将 Python 安装路径添加到系统环境变量 PATH 中
3. 重启命令提示符或 PowerShell 后重试

### pip 安装依赖失败

```bash
# 升级 pip
python3 -m pip install --upgrade pip

# 使用国内镜像（网络不好时）
pip3 install aacode -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### macOS 提示"无法验证开发者"

前往 **系统设置 → 隐私与安全性**，找到被阻止的应用，点击"仍要打开"。

---

更多信息请访问 [AACode GitHub](https://github.com/kandada/aacode)
