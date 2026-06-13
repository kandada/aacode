# 安全护栏
# utils/safety.py
"""
安全护栏实现
防止危险操作
"""

import re
import shlex
from pathlib import Path
from typing import Dict, List, Tuple, Set, Any, Union
import ast
from aacode.i18n import t


class SafetyGuard:
    """安全护栏"""

    # 风险等级
    RISK_SAFE = "safe"  # 安全命令，直接允许
    RISK_WARNING = "warning"  # 警告命令，需要确认
    RISK_DANGEROUS = "dangerous"  # 危险命令，直接拒绝
    RISK_UNKNOWN = "unknown"  # 未知命令，拒绝

    def __init__(
        self,
        project_path: Path,
        interactive: bool = True,
        dangerous_command_action: str = "log",
        restrict_to_project: bool = True,
    ):
        self.project_path = project_path
        self.project_root = str(project_path)
        self.interactive = interactive  # 是否启用交互式确认
        self.dangerous_command_action = dangerous_command_action  # reject, ask, log
        self.restrict_to_project = restrict_to_project

        # 危险命令模式（注意：rm -rf 已移到特殊检查中，允许在项目目录内使用）
        self.dangerous_patterns = [
            # 文件系统危险操作
            # (r'rm\s+(-rf|-r|-f)\s+', '递归删除文件'),  # 移除，改为特殊检查
            (r"format\s+", "Disk formatting"),
            (r"\bdd\s+", "Disk copy/erase"),
            (r"\bmkfs", "Create filesystem"),
            # 系统危险操作
            (r"shutdown\s+", "Shutdown system"),
            (r"halt\s+", "Halt system"),
            (r"reboot\s+", "Reboot system"),
            (r"poweroff\s+", "Power off"),
            (r"^\s*init\s+", "init process"),  # 只匹配开头的init命令
            # 网络危险操作
            (r"iptables\s+", "Firewall rules"),
            (r"ufw\s+", "Firewall"),
            # Shell危险操作
            (r":\(\)\{.*?;\s*\}.*?;", "Fork bomb"),
            (r"exec\s+/dev/", "Device execution"),
            (
                r"systemctl\s+(stop|restart|start|disable|enable|mask|unmask)",
                "System service management",
            ),
            (
                r"service\s+\S+\s+(stop|restart|start)",
                "Service management",
            ),  # service危险操作需要用户确认
            # 特别危险的权限操作（放宽chmod和chown，但限制特定模式）
            (r"chmod\s+[0-7]{3,4}\s+/\S*", "System directory permission change"),
            (r"chown\s+.*?:\s+/\S*", "System file ownership change"),
        ]

        # 允许的命令白名单（相对安全）
        self.allowed_commands = {
            # ── 基础文件/目录操作（Unix/macOS） ──
            "ls",
            "cd",
            "pwd",
            "cat",
            "echo",
            "grep",
            "glob",
            "find",
            "sed",
            "awk",
            "mkdir",
            "rmdir",
            "touch",
            "cp",
            "mv",
            "rm",  # rm需特别检查
            "ln",
            "readlink",
            "realpath",
            "head",
            "tail",
            "less",
            "more",
            "wc",
            "sort",
            "uniq",
            "tsort",
            "which",
            "whereis",
            "file",
            "stat",
            "basename",
            "dirname",
            "mktemp",
            "split",
            "csplit",
            "test",  # shell test / [ 命令
            ":",  # POSIX null command (no-op)
            # ── 进程管理（需谨慎） ──
            "pkill",
            "kill",
            "shutdown",
            "halt",
            "reboot",
            "poweroff",
            "nohup",
            "disown",
            "jobs",
            "fg",
            "bg",
            "wait",
            "lsof",
            "ulimit",
            "renice",
            "stdbuf",
            "command",
            # ── Windows 基础命令 ──
            "dir",
            "type",
            "copy",
            "xcopy",
            "robocopy",
            "move",
            "del",
            "erase",
            "ren",
            "rename",
            "md",
            "rd",
            "rmdir",
            "where",
            "findstr",
            "more",
            "sort",
            "attrib",
            "icacls",
            "whoami",
            "open",  # macOS 打开文件/目录
            "sw_vers",  # macOS 版本
            "defaults",  # macOS 用户配置
            "launchctl",  # macOS 服务管理
            "osascript",  # macOS AppleScript
            "xcrun",  # Xcode 工具
            "xcodebuild",  # Xcode 构建
            "xcode-select",  # Xcode 命令行工具选择
            "otool",  # macOS 二进制分析
            "lipo",  # macOS 通用二进制工具
            "nm",  # 符号表
            "actool",  # Xcode Asset Catalog 工具
            "ibtool",  # Xcode Interface Builder 工具
            "simctl",  # iOS 模拟器控制
            "codesign",  # 代码签名
            "security",  # macOS 钥匙串/安全
            "pbcopy",  # 剪贴板复制
            "pbpaste",  # 剪贴板粘贴
            "screencapture",  # 屏幕截图
            "say",  # 文字转语音
            "diskutil",  # 磁盘信息
            "mdfind",  # Spotlight 搜索
            "mdls",  # Spotlight 元数据列表
            "mdutil",  # Spotlight 管理
            "fc-list",  # fontconfig 字体列表查询
            "fc-cache",  # fontconfig 字体缓存
            "fc-match",  # fontconfig 字体匹配
            "fc-query",  # fontconfig 字体属性查询
            "fc-scan",  # fontconfig 字体扫描
            "sips",  # 图片处理
            "plutil",  # plist 处理
            "qlmanage",  # Quick Look 管理
            "textutil",  # 文档转换
            "softwareupdate",  # 系统软件更新
            "system_profiler",  # 系统信息
            "networksetup",  # 网络设置
            "scutil",  # 系统配置
            "pkgutil",  # 安装包管理
            "pkgbuild",  # macOS 安装包构建
            "installer",  # macOS 安装器
            "pluginkit",  # 插件管理
            "dd",
            "caffeinate",  # 阻止睡眠
            "pmset",  # 电源管理
            "hdiutil",  # 磁盘映像
            "xattr",  # 扩展属性
            "logger",  # 系统日志
            "hostname",
            "vm_stat",  # macOS 虚拟内存统计
            "ifconfig",  # 网络接口配置信息
            "pgrep",  # 进程名查找
            "pidof",  # 进程ID查找
            "pwdx",  # 进程工作目录
            "systeminfo",
            "tasklist",
            "taskkill",
            "net",
            "netsh",
            "ipconfig",
            "nslookup",
            "pathping",
            "tracert",
            "cls",
            "set",
            "setx",
            "shopt",
            "continue",
            "break",
            "fc",
            "reg",
            "sc",
            "wmic",
            "powershell",
            "pwsh",
            "cmd",
            "start",
            "chcp",
            "mklink",
            "assoc",
            "ftype",
            "cipher",
            "compact",
            "forfiles",
            "tree",
            "fc",
            "comp",
            "certutil",
            "schtasks",
            "wevtutil",
            "clip",
            "doskey",
            "title",
            "color",
            "mode",
            "verify",
            "vol",
            "label",
            "subst",
            "pushd",
            "popd",
            # ── Windows 额外常用命令/工具 ──
            "explorer",  # 资源管理器
            "notepad",  # 记事本
            "mspaint",  # 画图
            "write",  # 写字板
            "calc",  # 计算器
            "winver",  # Windows 版本
            "control",  # 控制面板
            "mmc",  # 管理控制台
            "devmgmt",  # 设备管理器 (mmc)
            "diskmgmt",  # 磁盘管理 (mmc)
            "eventvwr",  # 事件查看器 (mmc)
            "perfmon",  # 性能监视器 (mmc)
            "services",  # 服务 (mmc)
            "taskschd",  # 任务计划程序 (mmc)
            "gpedit",  # 组策略编辑器 (mmc)
            "regedit",  # 注册表编辑器
            "msconfig",  # 系统配置
            "dxdiag",  # DirectX 诊断
            "mstsc",  # 远程桌面
            "appwiz",  # 程序和功能 (cpl)
            "sysdm",  # 系统属性 (cpl)
            "desk",  # 显示设置 (cpl)
            "timedate",  # 日期和时间 (cpl)
            "main",  # 鼠标属性 (cpl)
            "powercfg",  # 电源配置
            "diskpart",  # 磁盘分区 (危险操作已在 dangerous_patterns 中检查)
            "bcdedit",  # 启动配置
            "driverquery",  # 驱动查询
            "getmac",  # MAC 地址
            "route",  # 路由表
            "arp",  # ARP 表
            "nbtstat",  # NetBIOS
            "sfc",  # 系统文件检查器 (只读)
            "dism",  # 部署映像服务
            "chkdsk",  # 磁盘检查 (只读)
            "defrag",  # 磁盘碎片整理
            "recover",  # 文件恢复
            "logoff",  # 注销
            "tscon",  # 终端服务连接
            "tsdiscon",  # 终端服务断开
            "qwinsta",  # 查询会话
            "quser",  # 查询用户
            "msg",  # 发送消息
            "wusa",  # Windows Update 独立安装器
            "gpupdate",  # 组策略更新
            "gpresult",  # 组策略结果
            "takeown",  # 获取所有权
            "runas",  # 以其他用户身份运行
            "icacls",  # 权限控制
            "msiexec",  # Windows Installer
            "winget",  # Windows 包管理器
            "wsl",  # Windows Subsystem for Linux
            "wslpath",  # WSL 路径转换
            "ubuntu",  # WSL Ubuntu
            "bash",  # Git Bash / WSL bash
            # ── Python 生态 ──
            "python",
            "python3",
            "python2",
            "py",  # Windows Python launcher
            "pip",
            "pip3",
            "pipx",
            "virtualenv",
            "venv",
            "poetry",
            "pipenv",
            "conda",
            "mamba",
            "uv",  # 新一代 Python 包管理器
            "uvx",
            "ruff",
            "black",
            "isort",
            "flake8",
            "mypy",
            "pyright",
            "pylint",
            "autopep8",
            "yapf",
            "bandit",
            "pytest",
            "unittest",
            "nose",
            "nose2",
            "tox",
            "nox",
            "coverage",
            "django-admin",
            "django",
            "flask",
            "fastapi",
            "uvicorn",
            "gunicorn",
            "celery",
            "celery-worker",
            "playwright",
            "streamlit",
            "gradio",
            "jupyter",
            "ipython",
            # ── Node.js 生态 ──
            "node",
            "npm",
            "npx",
            "yarn",
            "pnpm",
            "bun",
            "bunx",
            "deno",
            "tsx",
            "ts-node",
            "tsc",
            "eslint",
            "prettier",
            "next",
            "nuxt",
            "express-generator",
            "nest",
            "strapi",
            "vitest",
            "jest",
            "mocha",
            # ── 版本控制 ──
            "git",
            "svn",
            "hg",
            "pre-commit",
            "git-lfs",
            "git-flow",
            "husky",
            "gh",  # GitHub CLI
            "glab",  # GitLab CLI
            "hub",  # GitHub CLI (legacy)
            "act",  # GitHub Actions 本地运行器
            # ── 网络工具 ──
            "curl",
            "wget",
            "http",
            "httpie",
            "scp",
            "rsync",
            "ssh",
            "ssh-keygen",
            "ssh-add",
            "ping",
            "traceroute",
            "netstat",
            "ss",
            "sftp",
            "sshfs",
            "rclone",
            "nc",
            "ncat",
            "socat",
            "dig",
            "host",
            "whois",
            "aria2c",
            # ── 搜索工具 ──
            "rg",
            "ag",
            "ack",
            "fd",
            "locate",
            "mlocate",
            # ── 系统信息 ──
            "ps",
            "top",
            "htop",
            "df",
            "du",
            "free",
            "uptime",
            "uname",
            "arch",
            "id",
            "groups",
            "w",
            "who",
            "last",
            "finger",
            "getconf",
            "sysctl",
            "lscpu",
            "lsblk",
            "lsusb",
            "lspci",
            "dmidecode",
            # ── 权限管理（需谨慎） ──
            "chmod",
            "chown",
            "chgrp",
            "umask",
            # ── 包管理 ──
            "apt",
            "apt-get",
            "dpkg",
            "yum",
            "dnf",
            "brew",
            "pacman",
            "zypper",
            "snap",
            "flatpak",
            "apk",
            "pkg",
            "port",  # MacPorts
            "systemctl",
            "service",
            "sudo",  # 权限提升（需特别检查）
            # ── 编程语言 ──
            "ruby",
            "gem",
            "bundle",
            "rake",
            "rails",
            "go",
            "gofmt",
            "goimports",
            "cargo",
            "rustc",
            "rustup",
            "rustfmt",
            "clippy",
            "java",
            "javac",
            "jar",
            "mvn",
            "gradle",
            "gradlew",
            "ant",
            "php",
            "composer",
            "artisan",
            "perl",
            "cpan",
            "lua",
            "luarocks",
            "swift",
            "swiftc",
            "kotlin",
            "kotlinc",
            "scala",
            "sbt",
            "dotnet",
            "csc",
            "elixir",
            "mix",
            "iex",
            "erl",
            "rebar3",
            "dart",
            "flutter",
            "zig",
            "nim",
            "nimble",
            "crystal",
            "shards",
            "r",
            "rscript",
            "julia",
            # ── 编译/构建工具 ──
            "make",
            "cmake",
            "gcc",
            "g++",
            "clang",
            "clang++",
            "cc",
            "c++",
            "ld",
            "ar",
            "nm",
            "objdump",
            "strip",
            "meson",
            "ninja",
            "bazel",
            "scons",
            "autoconf",
            "automake",
            "configure",
            "pkg-config",
            # ── 编辑器 ──
            "vim",
            "vi",
            "nano",
            "emacs",
            "code",
            "subl",
            "micro",
            "helix",
            "hx",
            # ── Shell ──
            "bash",
            "sh",
            "zsh",
            "fish",
            "dash",
            "ksh",
            "csh",
            "tcsh",
            "source",
            "export",
            "readonly",
            "alias",
            "unalias",
            "eval",
            "exec",
            "trap",
            "read",
            "getopts",
            "shift",
            "return",
            # Shell 控制流关键字和内置命令
            "{",
            "}",
            "for",
            "if",
            "while",
            "until",
            "case",
            "select",
            "function",
            "[",
            "[[",
            "declare",
            "typeset",
            "local",
            "let",
            # Shell 流程控制关键字（续：闭合/中间关键字）
            "done",
            "esac",
            "fi",
            "then",
            "else",
            "elif",
            "do",
            "in",
            # Shell 其他内置命令
            "times",
            "builtin",
            "caller",
            "complete",
            "compgen",
            "compopt",
            "dirs",
            "logout",
            "mapfile",
            "readarray",
            "suspend",
            "hash",
            # ── 压缩工具 ──
            "tar",
            "gzip",
            "gunzip",
            "zip",
            "unzip",
            "bzip2",
            "bunzip2",
            "lzop",
            "xz",
            "unxz",
            "zstd",
            "unzstd",
            "7z",
            "7za",
            "rar",
            "unrar",
            "lz4",
            "pigz",
            # ── 文本处理 ──
            "tr",
            "cut",
            "paste",
            "join",
            "diff",
            "diff3",
            "sdiff",
            "interdiff",
            "cmp",
            "comm",
            "patch",
            "jq",
            "yq",
            "xsv",
            "dasel",
            "xmlstarlet",
            "csvkit",
            "miller",  # CSV/JSON 数据处理
            "mlr",  # miller 的别名
            "pandoc",
            "printf",
            "xargs",
            "tee",
            "rev",
            "fold",
            "pr",
            "column",
            "expand",
            "unexpand",
            "nl",
            "fmt",
            "comm",
            "colrm",
            "strings",
            "od",
            "hexdump",
            "xxd",
            "iconv",
            "dos2unix",
            "unix2dos",
            "base64",
            "base32",
            "md5sum",
            "sha1sum",
            "sha256sum",
            "shasum",
            "cksum",
            "sum",
            # ── 文件操作扩展 ──
            "tree",
            "exa",
            "eza",
            "bat",
            "fzf",
            "ripgrep",
            "silversearcher-ag",
            "entr",
            "inotifywait",
            "watchexec",
            "rsync",
            "install",
            "lsd",
            # ── 虚拟化和容器 ──
            "vagrant",
            "virtualbox",
            "qemu",
            "kvm",
            "lxc",
            "lxd",
            "buildah",
            "skopeo",
            "nerdctl",
            # ── Docker 生态 ──
            "docker",
            "docker-compose",
            "docker-build",
            "docker-run",
            "docker-ps",
            "docker-images",
            "docker-logs",
            "docker-exec",
            "docker-stop",
            "docker-rm",
            "docker-rmi",
            "podman",
            "podman-compose",
            # ── 数据库工具 ──
            "psql",
            "mysql",
            "sqlite3",
            "mongosh",
            "mongo",
            "redis-cli",
            "pg_dump",
            "pg_restore",
            "mysqldump",
            "mongoexport",
            "mongoimport",
            "redis-server",
            "pgcli",
            "mycli",
            "litecli",
            # ── 系统监控 ──
            "iotop",
            "nethogs",
            "glances",
            "ncdu",
            "nmon",
            "vmstat",
            "iostat",
            "mpstat",
            "sar",
            "pidstat",
            "dstat",
            # ── 性能分析 ──
            "perf",
            "strace",
            "ltrace",
            "valgrind",
            "gdb",
            "lldb",
            "dtrace",
            "tcpdump",
            # ── 前端工具 ──
            "webpack",
            "vite",
            "rollup",
            "parcel",
            "esbuild",
            "swc",
            "gulp",
            "grunt",
            "sass",
            "less",
            "postcss",
            "tailwindcss",
            "turbo",
            "lerna",
            "nx",
            "changeset",
            # ── 图像/多媒体工具 ──
            "ffmpeg",
            "ffprobe",
            "ffplay",
            "convert",
            "identify",
            "magick",
            "optipng",
            "pngquant",
            "jpegoptim",
            "gifsicle",
            "svgo",
            "inkscape",
            "dot",  # Graphviz 图形渲染
            "graphviz",  # Graphviz
            "sox",  # 音频处理
            # ── 其他常用工具 ──
            "date",
            "cal",
            "ncal",
            "bc",
            "dc",
            "calc",
            "expr",
            "seq",
            "yes",
            "true",
            "false",
            "sleep",
            "timeout",
            "watch",
            "time",
            "env",
            "printenv",
            "unset",
            "clear",
            "reset",
            "tput",
            "stty",
            "locale",
            "man",
            "info",
            "help",
            "apropos",
            "whatis",
            # ── 终端复用/实用工具 ──
            "tmux",
            "screen",
            "byobu",
            "zellij",
            "parallel",
            "sponge",
            "units",
            "neofetch",
            "screenfetch",
            "fastfetch",
            "hyperfine",
            "asciinema",
            "tldr",
            "cheat",
            "navi",
            "starship",
            # ── 云/DevOps 工具 ──
            "aws",
            "gcloud",
            "az",
            "terraform",
            "ansible",
            "ansible-playbook",
            "kubectl",
            "helm",
            "minikube",
            "kind",
            "k3s",
            "k9s",
            "eksctl",
            "pulumi",
            "vault",
            "consul",
            "packer",
            "serverless",
            "sam",
            "cdk",
            "copilot",
            # ── 日志查看 ──
            "journalctl",
            "dmesg",
            "multitail",
            "lnav",
        }

        # Python危险导入（只包含真正危险的）
        self.dangerous_imports = {
            "os.system",
            "os.popen",
            "subprocess.run",
            "shutil.rmtree",
            "shutil.move",
            # 移除常见模块，只保留真正危险的
            # "socket",  # 常见网络模块
            # "http.server",  # 常见HTTP模块
            # "ctypes",  # 常见C接口模块
            # "cffi",  # 常见C接口模块
        }

    def is_safe_path(self, path: Path) -> bool:
        """检查路径是否安全（放宽限制，允许合理操作）"""
        if not self.restrict_to_project:
            return True
        try:
            # 获取路径字符串
            path_str = str(path)

            # 解析路径
            resolved = path.resolve()
            project_root = Path(self.project_root).resolve()

            # 1. 检查是否在项目目录内（主要安全边界）
            try:
                resolved.relative_to(project_root)
                # 在项目目录内，允许
                return True
            except ValueError:
                # 不在项目目录内，进行更细致的检查
                pass

            # 2. 检查路径遍历深度（允许合理的父目录访问）
            if ".." in path_str:
                parts = Path(path_str).parts
                # 计算路径遍历深度
                dotdot_count = parts.count("..")

                # 允许最多3级父目录访问
                if dotdot_count <= 3:
                    # 计算实际路径
                    try:
                        actual_path = resolved
                        # 检查是否仍然在合理范围内（项目目录的3级父目录内）
                        max_parent = project_root.parent.parent.parent
                        try:
                            actual_path.relative_to(max_parent)
                            # 在允许的父目录范围内
                            return True
                        except ValueError:
                            # 超出允许范围
                            pass
                    except Exception:
                        pass

            # 3. 允许特定的系统目录访问（只读或临时操作）
            allowed_system_paths = [
                "/dev",  # 虚拟设备（/dev/null, /dev/zero, /dev/random 等）
                "/tmp",
                "/var/tmp",
                "/private/tmp",  # 临时目录（包括macOS的/private/tmp）
                "/usr/share",
                "/usr/local/share",  # 共享数据
                "/usr/local",
                "/usr/bin",
                "/bin",
                "/opt",
                "/etc",  # 系统配置（/etc/hosts, /etc/resolv.conf, /etc/os-release 等）
                "/proc",  # 系统信息（/proc/version, /proc/loadavg, /proc/uptime 等）
                "/sys",  # 内核/设备信息
                "/run",  # 运行时数据
                "/var/log",  # 系统日志
                "/Volumes",  # macOS 挂载卷
                "/Applications",  # macOS 应用
                "/Library",  # macOS 库
            ]

            # 检查原始路径和解析后的路径
            for allowed_path in allowed_system_paths:
                if str(resolved).startswith(allowed_path) or path_str.startswith(
                    allowed_path
                ):
                    return True

            # 4. 允许用户主目录访问（只读）
            user_home = str(Path.home())
            if str(resolved).startswith(user_home):
                # 检查是否是危险操作（如删除用户主目录）
                # 这里只做基本检查，具体操作在check_command中检查
                return True

            # 5. 默认拒绝其他项目目录外的访问
            return False

        except Exception:
            # 路径解析失败，保守起见拒绝
            return False

    def _ask_user_confirmation(self, command: str, reason: str) -> bool:
        """询问用户确认危险操作"""
        if not self.interactive:
            return False

        print("\n" + "=" * 60)
        print("⚠️  Detected potentially dangerous operation")
        print("=" * 60)
        print(f"Command: {command}")
        print(f"Reason: {reason}")
        print("=" * 60)

        try:
            response = input("Continue execution? (yes/no, default no): ").strip().lower()
            return response in ["yes", "y"]
        except (KeyboardInterrupt, EOFError):
            print("\n❌ User cancelled operation")
            return False

    def _extract_command_name(self, cmd_path: str) -> str:
        """
        从命令路径中提取命令名称

        处理以下情况：
        - python3 -> python
        - ./script.sh -> script.sh
        - .venv/bin/python -> python
        - /usr/bin/python3 -> python
        - pip3 -> pip

        Args:
            cmd_path: 命令路径

        Returns:
            命令名称
        """
        # 获取路径的最后一部分（文件名）
        cmd_name = Path(cmd_path).name

        # Windows 命令变体：echo. echo: echo; 等（Windows 下 echo. 打印空行）
        # 提取 . : ; 之前的部分作为命令名
        import re as _re
        base_match = _re.match(r'^([a-zA-Z]+)[.:;]', cmd_name)
        if base_match:
            cmd_name = base_match.group(1)

        # 命令映射：将变体映射到基础命令
        command_mapping = {
            "python": ["python", "python2", "python3"],
            "pip": ["pip", "pip2", "pip3"],
        }

        # 检查精确匹配
        for base_cmd, variants in command_mapping.items():
            if cmd_name in variants or any(cmd_name.startswith(v) for v in variants):
                return base_cmd

        # 对于其他命令，检查前缀匹配
        base_commands = {
            "node",
            "npm",
            "npx",
            "yarn",
            "ruby",
            "gem",
            "bundle",
            "java",
            "javac",
            "go",
            "cargo",
            "rustc",
            "php",
            "composer",
            "pytest",
            "unittest",
        }

        for base_cmd in base_commands:
            if cmd_name.startswith(base_cmd):
                return base_cmd

        return cmd_name.lower()

    def _is_project_executable(self, cmd_path: str) -> bool:
        """
        检查是否是项目内的可执行文件

        允许的情况：
        - .venv/bin/python
        - ./node_modules/.bin/webpack
        - bin/custom_script

        Args:
            cmd_path: 命令路径

        Returns:
            是否是项目内的可执行文件
        """
        # 如果是相对路径且在项目目录内
        if not cmd_path.startswith("/"):
            # 检查是否在项目目录内
            try:
                full_path = Path(self.project_root) / cmd_path
                if full_path.exists():
                    # 检查是否在项目目录内
                    resolved = full_path.resolve()
                    project_root = Path(self.project_root).resolve()
                    try:
                        resolved.relative_to(project_root)
                        return True
                    except ValueError:
                        return False
            except Exception:
                pass

        return False

    def _build_result(
        self,
        allowed: bool,
        reason: str,
        risk_level: str = "",
        needs_confirmation: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """构建检查结果字典

        Args:
            allowed: 是否允许
            reason: 原因
            risk_level: 风险等级
            needs_confirmation: 是否需要确认
            **kwargs: 其他字段

        Returns:
            结果字典
        """
        result = {
            "allowed": allowed,
            "reason": reason,
            "risk_level": risk_level
            or (self.RISK_SAFE if allowed else self.RISK_DANGEROUS),
            "needs_confirmation": (
                needs_confirmation if needs_confirmation is not None else False
            ),
        }
        result.update(kwargs)
        return result

    def _protect_quoted_pipes(self, command: str) -> str:
        """将引号内的 | 替换为哨兵字符，避免 _split_pipeline 误判为 shell 管道"""
        result = []
        i = 0
        while i < len(command):
            ch = command[i]
            if ch == "'":
                result.append(ch)
                i += 1
                while i < len(command):
                    c = command[i]
                    if c == "'":
                        result.append(c)
                        break
                    elif c == '|':
                        result.append('\x01')
                    else:
                        result.append(c)
                    i += 1
                i += 1
            elif ch == '"':
                result.append(ch)
                i += 1
                while i < len(command):
                    c = command[i]
                    if c == '\\' and i + 1 < len(command):
                        result.append(c)
                        i += 1
                        result.append(command[i])
                    elif c == '"':
                        result.append(c)
                        break
                    elif c == '|':
                        result.append('\x01')
                    else:
                        result.append(c)
                    i += 1
                i += 1
            else:
                result.append(ch)
                i += 1
        return ''.join(result)

    def _split_pipeline(self, parts: List[str]) -> List[List[str]]:
        """将 token 列表按管道/分隔符拆分为多个命令段

        分隔符: |, &&, ||, ;
        每个段是一个独立的命令，可以单独检查安全性。
        不拆分 heredoc (<<) 内容中的 | 字符。
        不拆分 $(...) 命令替换内的管道符号。
        """
        separators = {"|", "&&", "||", ";"}
        segments = []
        current = []

        heredoc_stack = []  # 栈：跟踪嵌套的 heredoc 结束标记
        subshell_depth = 0  # $(...) 嵌套深度计数器

        i = 0
        while i < len(parts):
            part = parts[i]

            # 检测 $( ... ) 命令替换开始（分离 token：$ 后跟 (）
            if part == '$' and i + 1 < len(parts) and parts[i + 1] == '(':
                subshell_depth += 1
                current.append(part)
                i += 1
                continue

            # 检测 $( 在合并 token 内部（shlex 可能合并成 dollar_open=$(grep 这样的单一 token）
            merged_open = part.count('$(')
            if merged_open > 0:
                subshell_depth += merged_open

            # 检测 $( ... ) 命令替换结束（分离 token：)）
            if subshell_depth > 0 and part == ')':
                subshell_depth = max(0, subshell_depth - 1)

            # 检测 ) 在合并 token 尾部（shlex 可能合并成 true) 这样的单一 token）
            if subshell_depth > 0:
                trailing_close = len(part) - len(part.rstrip(')'))
                if trailing_close > 0:
                    subshell_depth = max(0, subshell_depth - trailing_close)

            # 检测 heredoc 开始: << DELIM
            if part == "<<" and i + 1 < len(parts):
                delim_token = parts[i + 1]
                delim_raw = delim_token
                if (delim_raw.startswith("'") and delim_raw.endswith("'")) or \
                   (delim_raw.startswith('"') and delim_raw.endswith('"')):
                    delim_raw = delim_raw[1:-1]
                heredoc_stack.append(delim_raw)
                current.append(part)
                current.append(delim_token)
                i += 2
                continue

            # 检测 heredoc 结束：匹配最内层结束标记
            if heredoc_stack and part == heredoc_stack[-1]:
                heredoc_stack.pop()
                current.append(part)
                i += 1
                continue

            # 管道拆分（仅在非 heredoc 内且非 $(...) 内时）
            if not heredoc_stack and subshell_depth == 0 and part in separators:
                if current:
                    segments.append(current)
                    current = []
            else:
                current.append(part)

            i += 1

        if current:
            segments.append(current)
        return segments

    @staticmethod
    def _is_pathlike(token: str) -> bool:
        """Check if a token looks like a file path.

        Returns True if the token is an absolute path (starts with '/')
        or contains '..' as a standalone path component (parent traversal).
        Does NOT match '..' as a substring inside other text
        (e.g. '...' ellipsis, 'file..txt').
        """
        if token.startswith("/"):
            return True
        if ".." not in token:
            return False
        return bool(re.search(r'(^|/)\.\.($|/)', token))

    def _split_by_newlines(self, command: str) -> List[str]:
        """Split multi-line command by newlines, respecting heredoc boundaries
        and multi-line quoted strings (e.g. python3 -c \"...\").

        In shell, newlines are equivalent to ';' but only outside heredocs
        and outside multi-line quoted strings.
        """
        lines = command.split('\n')
        result = []
        current = []
        heredoc_delims = []  # queue of heredoc closing delimiters
        in_dq = False  # inside double-quoted string
        in_sq = False  # inside single-quoted string

        def _update_quote_state(line_text: str) -> None:
            """Update in_dq/in_sq based on line content."""
            nonlocal in_dq, in_sq
            i = 0
            while i < len(line_text):
                ch = line_text[i]
                if ch == '\\' and i + 1 < len(line_text):
                    i += 2
                    continue
                if ch == '"' and not in_sq:
                    in_dq = not in_dq
                elif ch == "'" and not in_dq:
                    in_sq = not in_sq
                i += 1

        for line in lines:
            if not line.strip():
                continue

            if heredoc_delims:
                current.append(line)
                if line.strip() == heredoc_delims[0]:
                    heredoc_delims.pop(0)
                continue

            if in_dq or in_sq:
                current.append(line)
                _update_quote_state(line)
                if in_dq or in_sq:
                    continue
                for m in re.finditer(r'<<-?\s*[\'"]?(\w+)[\'"]?', line):
                    heredoc_delims.append(m.group(1))
                if not heredoc_delims:
                    result.append('\n'.join(current))
                    current = []
                continue

            _update_quote_state(line)

            for m in re.finditer(r'<<-?\s*[\'"]?(\w+)[\'"]?', line):
                heredoc_delims.append(m.group(1))

            current.append(line)

            if in_dq or in_sq:
                continue

            if not heredoc_delims:
                result.append('\n'.join(current))
                current = []

        if current:
            result.append('\n'.join(current))

        return result

    def _merge_line_continuations(self, command: str) -> str:
        """合并 shell 行续接符 \\，将多行物理行合并为逻辑行

        shell 中行尾的 \\ 表示下一行是本行的续接。
        此方法在 shlex 解析前将续接行合并，确保参数被正确识别。

        Args:
            command: 原始命令字符串（可能含多行和 \\ 续接符）

        Returns:
            合并续接行后的命令字符串
        """
        lines = command.split('\n')
        result = []
        i = 0
        while i < len(lines):
            line = lines[i].rstrip()
            trailing_bs = len(line) - len(line.rstrip('\\'))
            if trailing_bs % 2 == 1:
                # 奇数个结尾反斜杠 → 最后一个 \\ 是续行符（转义了换行）
                parts = [line[:-1].rstrip()]
                i += 1
                while i < len(lines):
                    next_line = lines[i].rstrip()
                    trailing_bs2 = len(next_line) - len(next_line.rstrip('\\'))
                    if trailing_bs2 % 2 == 1:
                        # 下一行也以续行符结尾，去掉 \\ 后继续
                        parts.append(next_line[:-1].strip())
                        i += 1
                    else:
                        # 续行结束
                        parts.append(next_line.strip())
                        i += 1
                        break
                result.append(' '.join(parts))
            else:
                result.append(line)
                i += 1
        return '\n'.join(result)

    def _assess_risk_level(
        self, cmd_name: str, command: str, parts: List[str]
    ) -> Tuple[str, str]:
        """评估命令风险等级

        Args:
            cmd_name: 命令名称
            command: 完整命令
            parts: 命令参数列表

        Returns:
            (risk_level, reason)
        """
        # 1. 检查是否在白名单中
        if cmd_name not in self.allowed_commands:
            return self.RISK_UNKNOWN, f"Command not in whitelist: {cmd_name}"

        # Shell 控制流关键字：纯语法结构，无直接文件操作，视为安全
        shell_keywords = {
            "for", "if", "while", "until", "case", "select", "function",
            "[", "[[", "{", "}", "declare", "typeset", "local", "let", "readonly",
            "done", "esac", "fi", "then", "else", "elif", "do", "in",
            ":", "true", "false",
        }
        if cmd_name in shell_keywords:
            return self.RISK_SAFE, "Shell keyword/control flow"

        # 2. 检查危险命令模式（已经在check_command中检查过）
        # 3. 根据命令类型评估风险

        # 高风险命令（需要特别检查）
        high_risk_commands = {
            "rm": "File deletion",
            "sudo": "Privilege escalation",
            "chmod": "Permission change",
            "chown": "Ownership change",
            "dd": "Disk operation",
            "format": "Disk format",
            "mkfs": "Create filesystem",
            "shutdown": "System shutdown",
            "halt": "System halt",
            "reboot": "System reboot",
            "pkill": "Process termination",
            "kill": "Process termination",
            "iptables": "Firewall config",
            "ufw": "Firewall management",
        }

        if cmd_name in high_risk_commands:
            return self.RISK_WARNING, high_risk_commands[cmd_name]

        # 中风险命令（可能需要确认）
        medium_risk_commands = {
            "pip": "Python package manager",
            "pip3": "Python package manager",
            "npm": "Node.js package manager",
            "yarn": "Node.js package manager",
            "apt": "System package manager",
            "apt-get": "System package manager",
            "docker": "Container operations",
            "docker-compose": "Container orchestration",
            "systemctl": "System service management",
            "service": "Service management",
        }

        if cmd_name in medium_risk_commands:
            return self.RISK_WARNING, medium_risk_commands[cmd_name]

        # 低风险命令（安全）
        return self.RISK_SAFE, "Safe command"

    def check_command(
        self, command: str, ask_confirmation: bool = True,
        _skip_newline_split: bool = False,
    ) -> Dict[str, Any]:
        """检查命令安全性

        Args:
            command: 要检查的命令
            ask_confirmation: 是否对危险操作询问用户确认

        Returns:
            检查结果字典，包含：
            - allowed: 是否允许执行
            - reason: 原因说明
            - risk_level: 风险等级 (safe/warning/dangerous/unknown)
            - needs_confirmation: 是否需要用户确认
        """
        # 去除多余空格
        command = command.strip()

        # 剥离前导注释行（# 开头的行在 shell 中是注释，不应作为命令检查）
        # 只剥离命令开头的连续注释行，保留命令中间（如 -c "..." 内联脚本中）的注释行
        lines = command.split('\n')
        first_non_comment = 0
        for i, l in enumerate(lines):
            stripped = l.strip()
            if stripped and not stripped.startswith('#'):
                first_non_comment = i
                break
        else:
            if any(l.strip().startswith('#') for l in lines):
                return self._build_result(
                    allowed=True, reason="Command is only comments",
                    risk_level=self.RISK_SAFE,
                )
            # All lines are empty/whitespace – fall through to empty check below
        if first_non_comment > 0:
            command = '\n'.join(lines[first_non_comment:]).strip()

        # 空命令
        if not command:
            return self._build_result(
                allowed=False, reason="Empty command", risk_level=self.RISK_DANGEROUS
            )

        # 合并 \ 行续接符（shell line continuation）
        # 将结尾带 \ 的行与下一行合并，方便后续 shlex 正确解析参数
        command = self._merge_line_continuations(command)

        # 按换行符拆分为逻辑命令（尊重 heredoc 边界）
        # shell 中换行等价于 ; 命令分隔符，但在 heredoc 内除外
        # 只在顶级调用中拆分，递归调用跳过（避免 " ".join 丢失引号导致的误拆）
        if not _skip_newline_split:
            commands = self._split_by_newlines(command)
            if len(commands) > 1:
                final_risk = self.RISK_SAFE
                for cmd in commands:
                    result = self.check_command(cmd, ask_confirmation, _skip_newline_split=True)
                    if not result["allowed"]:
                        return result
                    seg_risk = result.get("risk_level", self.RISK_SAFE)
                    if seg_risk == self.RISK_DANGEROUS:
                        final_risk = self.RISK_DANGEROUS
                    elif seg_risk == self.RISK_WARNING and final_risk != self.RISK_DANGEROUS:
                        final_risk = self.RISK_WARNING
                return self._build_result(
                    allowed=True,
                    reason="All commands passed safety check",
                    risk_level=final_risk,
                )

        # 检查危险模式
        for pattern, description in self.dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                # 根据配置处理危险命令
                if self.dangerous_command_action == "reject":
                    return self._build_result(
                        allowed=False,
                        reason=f"Dangerous operation detected: {description}",
                        risk_level=self.RISK_DANGEROUS,
                        pattern=pattern,
                    )
                elif self.dangerous_command_action == "ask":
                    # 询问用户确认
                    if self.interactive and ask_confirmation:
                        if self._ask_user_confirmation(
                            command, f"Dangerous operation: {description}"
                        ):
                            print(f"✅ User confirmed execution of dangerous command")
                            return self._build_result(
                                allowed=True,
                                reason=f"Dangerous operation confirmed: {description}",
                                risk_level=self.RISK_WARNING,
                            )
                        else:
                            return self._build_result(
                                allowed=False,
                                reason="User cancelled operation",
                                risk_level=self.RISK_DANGEROUS,
                            )
                    else:
                        # 非交互模式，拒绝执行
                        return self._build_result(
                            allowed=False,
                            reason=f"Dangerous operation detected: {description} (confirm in interactive mode)",
                            risk_level=self.RISK_DANGEROUS,
                            pattern=pattern,
                        )
                elif self.dangerous_command_action == "log":
                    # 记录日志但允许执行
                    print(f"⚠️  Warning: dangerous operation detected (logged): {description}")
                    return self._build_result(
                        allowed=True,
                        reason=f"Dangerous operation logged: {description}",
                        risk_level=self.RISK_WARNING,
                    )

        # 解析命令
        command = self._protect_quoted_pipes(command)
        try:
            try:
                parts = shlex.split(command)
            except ValueError:
                # shlex.split 在遇到未闭合引号时会失败（Windows 下常见，如 echo it's done）
                # fallback 到简单空格分割，提取第一个词作为命令名
                parts = command.split()
            if not parts:
                return self._build_result(
                    allowed=False, reason="Unable to parse command", risk_level=self.RISK_DANGEROUS
                )

            # 拆分管道/分隔符，每个段独立检查
            segments = self._split_pipeline(parts)
            if not segments:
                return self._build_result(
                    allowed=False, reason="No valid command segments", risk_level=self.RISK_DANGEROUS
                )

            if len(segments) > 1:
                final_risk = self.RISK_SAFE
                for segment_parts in segments:
                    segment_cmd = " ".join(segment_parts)
                    result = self.check_command(segment_cmd, ask_confirmation, _skip_newline_split=True)
                    if not result["allowed"]:
                        return result
                    seg_risk = result.get("risk_level", self.RISK_SAFE)
                    if seg_risk == self.RISK_DANGEROUS:
                        final_risk = self.RISK_DANGEROUS
                    elif seg_risk == self.RISK_WARNING and final_risk != self.RISK_DANGEROUS:
                        final_risk = self.RISK_WARNING
                return self._build_result(
                    allowed=True, reason="All pipeline segments passed", risk_level=final_risk
                )

            cmd_path = parts[0]

            # 处理环境变量赋值模式: VAR=value command
            # shlex 会将 VAR=value 和 VAR=$(cmd) 解析为独立 token，需要智能跳过
            # VAR=$(cmd args) 中 shlex 会把 $() 内的参数也拆成 token，
            # 需提取 $(cmd) 中的真实命令名并跳过其参数 token
            # 同时处理 VAR=$((expr)) 算术展开模式
            actual_cmd_index = 0
            parts_len = len(parts)
            subshell_command = None  # 从 $(cmd) 或 `cmd` 中提取的命令名
            has_shell_expansion = False  # 赋值 token 包含 $(...) / $((...)) / 反引号展开

            while actual_cmd_index < parts_len and "=" in parts[actual_cmd_index]:
                token = parts[actual_cmd_index]
                if not subshell_command:
                    m = re.search(r'\$\((\w+)', token) or re.search(r'`(\w+)', token)
                    if m:
                        subshell_command = m.group(1)
                if not has_shell_expansion and ('$(' in token or '`' in token):
                    has_shell_expansion = True
                actual_cmd_index += 1

            # shlex 在 POSIX 模式下会把 NAME=$(cmd) 拆成 NAME, =, $, (, cmd, ...
            # 这里的 while 只能匹配 NAME= 一体的情况 (如 FOO=bar)
            # 需要额外处理 NAME 和 = 分离 token 的情况
            if actual_cmd_index == 0 and parts_len > 1 and parts[1] == "=":
                actual_cmd_index = 2
                if parts_len > 2:
                    has_shell_expansion = True
                    for j in range(2, parts_len - 1):
                        if parts[j] == '$' and parts[j+1] == '(':
                            if j + 2 < parts_len and re.match(r'\w+', parts[j+2]):
                                subshell_command = parts[j+2]
                            break
                        if parts[j].startswith('`') and j + 1 < parts_len:
                            m = re.search(r'`(\w+)', parts[j])
                            if m:
                                subshell_command = m.group(1)
                            break

            if actual_cmd_index > 0:
                if subshell_command or has_shell_expansion:
                    # VAR=$(cmd args) / VAR=$((expr)) 模式：跳过展开内的参数 token
                    # 使用括号平衡计数，正确处理嵌套 () 和 $(()) 内的分组括号
                    paren_depth = 1  # 已进入 $(...) / $((...)) 一层
                    while actual_cmd_index < parts_len:
                        t = parts[actual_cmd_index]
                        for ch in t:
                            if ch == '(':
                                paren_depth += 1
                            elif ch == ')':
                                paren_depth -= 1
                                if paren_depth == 0:
                                    break
                            elif ch == '`' and paren_depth == 1:
                                # 反引号闭合最内层
                                paren_depth = 0
                                break
                        actual_cmd_index += 1
                        if paren_depth == 0:
                            break
                    if actual_cmd_index >= parts_len:
                        if subshell_command:
                            # $() 内是唯一命令，使用从替换中提取的命令名
                            cmd_path = subshell_command
                        else:
                            # $((...)) 算术展开或空 $()，纯变量赋值，放行
                            return self._build_result(
                                allowed=True,
                                reason="Variable assignment with shell expansion",
                                risk_level=self.RISK_SAFE,
                            )
                    else:
                        # 展开后还有命令（如 export VAR=$(cmd); actual_cmd）
                        # 跳过残留在当前 token 的 ) 或 ` 关闭符
                        while actual_cmd_index < parts_len and (')' in parts[actual_cmd_index] or '`' in parts[actual_cmd_index]):
                            actual_cmd_index += 1
                        if actual_cmd_index >= parts_len:
                            if subshell_command:
                                cmd_path = subshell_command
                            else:
                                return self._build_result(
                                    allowed=True,
                                    reason="Variable assignment with shell expansion",
                                    risk_level=self.RISK_SAFE,
                                )
                        else:
                            cmd_path = parts[actual_cmd_index]
                            parts = parts[actual_cmd_index:]
                elif actual_cmd_index >= parts_len:
                    # 纯变量赋值（如 VAR=value），无害，放行
                    return self._build_result(
                        allowed=True,
                        reason="Environment variable assignment only",
                        risk_level=self.RISK_SAFE,
                    )
                else:
                    # 跳过赋值 token，使用后续 token 作为实际命令
                    cmd_path = parts[actual_cmd_index]
                    parts = parts[actual_cmd_index:]

            # 处理命令取反模式: ! command
            if cmd_path == "!":
                if len(parts) <= 1:
                    return self._build_result(
                        allowed=True,
                        reason="Bare negation operator",
                        risk_level=self.RISK_SAFE,
                    )
                cmd_path = parts[1]
                parts = parts[1:]

            # 提取命令名称（智能处理路径）
            cmd_name = self._extract_command_name(cmd_path)

            # 评估风险等级
            risk_level, risk_reason = self._assess_risk_level(cmd_name, command, parts)

            # 检查是否是项目内的可执行文件
            if self._is_project_executable(cmd_path):
                # 项目内的可执行文件，检查基础命令名
                if cmd_name in self.allowed_commands:
                    print(f"✅ Allowed project executable: {cmd_path}")
                    return self._build_result(
                        allowed=True,
                        reason=f"Project executable: {cmd_name}",
                        risk_level=self.RISK_SAFE,
                    )
                else:
                    # 对于项目内的脚本，如果是常见扩展名则允许
                    allowed_extensions = {".sh", ".py", ".js", ".rb", ".pl"}
                    if any(cmd_path.endswith(ext) for ext in allowed_extensions):
                        print(f"✅ Allowed project script: {cmd_path}")
                        return self._build_result(
                            allowed=True,
                            reason="Project script file",
                            risk_level=self.RISK_SAFE,
                        )

            # 检查是否在白名单中
            if cmd_name not in self.allowed_commands:
                return self._build_result(
                    allowed=False,
                    reason=f"Command not in whitelist: {cmd_name}",
                    risk_level=self.RISK_UNKNOWN,
                    suggestion=f"Available commands: {', '.join(sorted(list(self.allowed_commands)))}",
                )

            # Shell 控制流关键字：跳过后续特殊检查和路径检查，直接放行
            shell_keywords = {
                "for", "if", "while", "until", "case", "select", "function",
                "[", "[[", "{", "}", "declare", "typeset", "local", "let", "readonly",
                "done", "esac", "fi", "then", "else", "elif", "do", "in",
                ":", "true", "false",
            }
            if cmd_name in shell_keywords:
                return self._build_result(
                    allowed=True,
                    reason=f"Shell keyword/control flow: {cmd_name}",
                    risk_level=self.RISK_SAFE,
                )

            # 特殊检查：rm命令（智能检查）
            if cmd_name == "rm":
                # 检查是否有递归选项（-r/-R/--recursive 才是危险操作）
                has_recursive = False
                has_force = False
                dangerous_targets = []

                for i, part in enumerate(parts):
                    if part.startswith("-"):
                        if any(c in part for c in "rR"):
                            has_recursive = True
                        if "f" in part:
                            has_force = True
                    elif part == "--recursive":
                        has_recursive = True
                    # 检查删除目标
                    elif i > 0 and not part.startswith("-"):
                        # 这是要删除的目标
                        target_path = part

                        # 检查是否是极度危险的删除目标
                        dangerous_patterns = [
                            "/",
                            "/*",
                            "~",
                            "~/*",
                            "/etc",
                            "/var",
                            "/usr",
                            "/bin",
                            "/sbin",
                            "/lib",
                        ]
                        if any(
                            target_path == pattern
                            or target_path.startswith(pattern + "/")
                            for pattern in dangerous_patterns
                        ):
                            return {
                                "allowed": False,
                                "reason": f"rm command target too dangerous: {target_path}",
                                "risk_level": self.RISK_DANGEROUS,
                                "needs_confirmation": False,
                                "suggestion": "Please explicitly specify the file or directory to delete",
                            }

                        # 检查是否尝试删除项目目录外的文件（仅在严格模式下）
                        if self.restrict_to_project:
                            try:
                                # 解析目标路径
                                if target_path.startswith("/"):
                                    # 绝对路径
                                    if not target_path.startswith(self.project_root):
                                        dangerous_targets.append(target_path)
                                else:
                                    # 相对路径，检查是否包含路径遍历
                                    if ".." in target_path:
                                        # 解析相对路径
                                        resolved_path = (Path.cwd() / target_path).resolve()
                                        project_root = Path(self.project_root).resolve()
                                        # 检查是否在项目目录内
                                        try:
                                            resolved_path.relative_to(project_root)
                                        except ValueError:
                                            # 不在项目目录内
                                            dangerous_targets.append(target_path)
                            except Exception:
                                # 路径解析失败，保守起见视为危险
                                dangerous_targets.append(target_path)

                # 只有递归删除才需要特殊检查
                if has_recursive:
                    # 如果尝试删除项目外的文件，拒绝
                    if dangerous_targets:
                        return {
                            "allowed": False,
                            "reason": f"rm -r cannot delete files outside project directory: {', '.join(dangerous_targets)}",
                            "suggestion": "rm -r can only be used within the project directory",
                        }

                    # 在项目目录内使用 rm -r
                    # 如果是交互模式且要求确认，则询问用户
                    flags_desc = "rm -rf" if has_force else "rm -r"
                    if ask_confirmation and self.interactive:
                        # 提取要删除的目标
                        targets = [p for p in parts[1:] if not p.startswith("-")]
                        target_desc = ", ".join(targets) if targets else "files"

                        if not self._ask_user_confirmation(
                            command, f"{flags_desc} recursive deletion, will delete: {target_desc}"
                        ):
                            return {"allowed": False, "reason": "User cancelled operation"}
                        print(f"✅ User confirmed {flags_desc} operation")
                        return {"allowed": True, "reason": f"{flags_desc} operation (user confirmed)"}
                    else:
                        # 非交互模式或不需要确认，直接允许（项目内）
                        return {"allowed": True, "reason": f"rm -r operation (within project directory)"}

                # 普通rm命令（无递归选项），允许
                return {"allowed": True, "reason": "rm command (safe)"}

            # 特殊检查：sudo命令（允许但需要确认）
            if cmd_name == "sudo":
                if not self.restrict_to_project:
                    # 宽松模式：允许任意 sudo 子命令
                    if len(parts) > 1:
                        if ask_confirmation and self.interactive:
                            if not self._ask_user_confirmation(command, "sudo privilege operation"):
                                return {"allowed": False, "reason": "User cancelled operation"}
                            return {"allowed": True, "reason": "sudo operation (user confirmed)"}
                        return {"allowed": True, "reason": "sudo operation (relaxed mode)"}
                    return {"allowed": True, "reason": "sudo command (relaxed mode)"}

                # 只允许特定的sudo命令
                allowed_sudo_commands = {
                    "apt",
                    "apt-get",
                    "dpkg",
                    "systemctl",
                    "service",
                    "pip",
                    "pip3",
                    "npm",
                    "yarn",
                }
                if len(parts) > 1:
                    sub_cmd = parts[1].lower()
                    if sub_cmd not in allowed_sudo_commands:
                        return {
                            "allowed": False,
                            "reason": f"sudo command '{sub_cmd}' not in allowed list",
                            "suggestion": f"Allowed sudo commands: {', '.join(allowed_sudo_commands)}",
                        }

                    # 允许安装操作，但在交互模式下需要用户确认
                    if any(
                        install_keyword in " ".join(parts).lower()
                        for install_keyword in ["install", "add", "update", "upgrade"]
                    ):
                        if ask_confirmation and self.interactive:
                            if not self._ask_user_confirmation(
                                command, "sudo privilege operation, may modify system configuration"
                            ):
                                return {"allowed": False, "reason": "User cancelled operation"}
                            print(f"✅ User confirmed sudo operation")
                            return {
                                "allowed": True,
                                "reason": "Package install operation (user confirmed)",
                            }
                        else:
                            # 非交互模式，直接允许
                            return {"allowed": True, "reason": "Package install operation"}

                # 其他sudo操作，在交互模式下询问
                if ask_confirmation and self.interactive:
                    if not self._ask_user_confirmation(command, "sudo privilege operation"):
                        return {"allowed": False, "reason": "User cancelled operation"}
                    return {"allowed": True, "reason": "sudo operation (user confirmed)"}
                else:
                    return {"allowed": True, "reason": "sudo operation"}

            # 特殊检查：chmod和chown命令（项目内允许，但需要确认）
            if cmd_name in ["chmod", "chown"]:
                if self.restrict_to_project:
                    # 严格模式：检查是否尝试修改系统文件权限
                    if len(parts) > 1:
                        for part in parts[1:]:
                            if part.startswith("/") and not part.startswith(
                                self.project_root
                            ):
                                return {
                                    "allowed": False,
                                        "reason": f"{cmd_name} command cannot modify file permissions outside project directory",
                                }
                            # 检查危险权限设置（如777）
                            if cmd_name == "chmod" and "777" in part:
                                if ask_confirmation and self.interactive:
                                    if not self._ask_user_confirmation(
                                            command, "chmod 777 permissions too permissive, security risk"
                                        ):
                                        return {"allowed": False, "reason": "User cancelled operation"}
                                    return {
                                        "allowed": True,
                                        "reason": "chmod 777 operation (user confirmed)",
                                    }
                                else:
                                    return {
                                        "allowed": True,
                                        "reason": "chmod 777 operation (within project)",
                                    }

                    # 项目内的权限修改，仅对危险操作询问确认
                    if cmd_name == "chmod":
                        # 检查是否是递归操作 (-R)
                        has_recursive = any(
                            p.startswith("-") and "R" in p
                            for p in parts
                        )
                        if has_recursive:
                            if ask_confirmation and self.interactive:
                                if not self._ask_user_confirmation(
                                    command, "chmod -R recursive permission modification"
                                ):
                                    return {"allowed": False, "reason": "User cancelled operation"}
                                return {"allowed": True, "reason": "chmod -R operation (user confirmed)"}
                            return {"allowed": True, "reason": "chmod -R operation (within project)"}
                        # 普通 chmod（如 +x, 644 等），直接允许
                        return {"allowed": True, "reason": "chmod operation (within project)"}
                    else:
                        # chown 需要确认（所有权变更影响较大）
                        if ask_confirmation and self.interactive:
                            if not self._ask_user_confirmation(
                                command, "chown ownership modification"
                            ):
                                return {"allowed": False, "reason": "User cancelled operation"}
                            return {"allowed": True, "reason": "chown operation (user confirmed)"}
                        return {"allowed": True, "reason": "chown operation (within project)"}
                else:
                    # 宽松模式：允许项目外路径，但 chmod 777 仍需确认
                    if len(parts) > 1 and cmd_name == "chmod":
                        for part in parts[1:]:
                            if "777" in part:
                                if ask_confirmation and self.interactive:
                                    if not self._ask_user_confirmation(
                                            command, "chmod 777 permissions too permissive, security risk"
                                        ):
                                        return {"allowed": False, "reason": "User cancelled operation"}
                                    return {"allowed": True, "reason": "chmod 777 operation (user confirmed)"}
                                return {"allowed": True, "reason": "chmod 777 operation (relaxed mode)"}
                    return {"allowed": True, "reason": f"{cmd_name} operation (relaxed mode)"}

            # 特殊检查：pip/pip3命令（允许大部分操作）
            if cmd_name in ["pip", "pip3"]:
                print(f"📦 Detected pip command: {' '.join(parts)}")
                # 允许所有常见pip操作，只禁止明确危险的
                if len(parts) > 1:
                    pip_action = parts[1].lower()
                    # 只禁止明确危险的操作
                    forbidden_pip_actions = {
                        "download",
                        "wheel",
                    }  # 这些可能下载大量文件
                    if pip_action in forbidden_pip_actions:
                        return {
                            "allowed": False,
                            "reason": f"pip operation '{pip_action}' may produce many files",
                            "suggestion": "Please use install instead",
                        }
                # 允许其他所有pip操作
                return {"allowed": True, "reason": "pip operation"}

            # 特殊检查：npm/yarn命令（允许大部分操作）
            if cmd_name in ["npm", "yarn", "npx", "pnpm"]:
                print(f"📦 Detected {cmd_name} command: {' '.join(parts)}")
                # 允许所有常见操作
                return {"allowed": True, "reason": f"{cmd_name} operation"}

            # 纯输出命令：只写 stdout/stderr，不可能写文件，完全跳过路径检查
            output_only_commands = {
                "echo", "printf", "true", "false", "yes", "seq", "expr", "bc", "dc",
                "basename", "dirname", "realpath", "readlink", "pwd",
                "cat", "wc", "sort", "uniq", "cut", "tr", "fold", "rev", "nl", "fmt",
                "grep", "rg", "ag", "find", "sed", "awk",
                "strings", "od", "hexdump", "xxd", "jq", "yq", "diff",
                "cksum", "sum", "md5sum", "sha256sum", "shasum", "base64", "iconv",
                "uname", "arch", "hostname", "uptime", "dmesg",
                "lscpu", "lsblk", "lsusb", "lspci", "getconf", "locale",
                "id", "who", "w", "last", "groups",
                "ls", "file", "stat", "du", "df", "ps", "top", "htop",
                "head", "tail", "less", "more",
                "which", "whereis", "date", "cal", "locate", "mlocate",
                "man", "info", "tldr", "apropos", "whatis",
                "logger", "tput", "stty",
                # 解释器：脚本路径检查无实际安全意义，脚本本身可任意操作
                "python", "python3", "node", "ruby", "java",
                # 目录导航：仅改变 shell 状态，不读写文件
                "cd", "pushd", "popd", "dirs",
            }

            # 子命令委托：元命令的子命令若是纯输出型，整个命令跳过路径检查
            # 例如 git grep → grep 在 output_only，则 git grep 也视为纯输出
            actual_cmd = cmd_name
            if cmd_name not in output_only_commands and len(parts) > 1:
                # 跳过前导全局标志找到子命令（如 git -C /path grep ...）
                sub_idx = 1
                while sub_idx < len(parts) and parts[sub_idx].startswith("-"):
                    sub_idx += 1
                    # 跳过短标志的值 (git -C /path ...)
                    if (
                        sub_idx > 1
                        and sub_idx < len(parts)
                        and len(parts[sub_idx - 1]) == 2
                        and parts[sub_idx - 1][0] == "-"
                    ):
                        sub_idx += 1
                if sub_idx < len(parts):
                    sub_cmd = self._extract_command_name(parts[sub_idx])
                    if sub_cmd in output_only_commands:
                        actual_cmd = sub_cmd

            if actual_cmd not in output_only_commands:
                # 检查路径参数（使用新的is_safe_path方法）
                # 对于awk, sed等命令，参数可能是正则表达式而非路径
                regex_commands = {"awk", "sed", "grep", "rg", "ag", "find"}

                for i, part in enumerate(parts):
                    # 跳过命令本身
                    if i == 0:
                        continue

                    # 检查路径参数（只检测真正的路径组件，避免...省略号等误判）
                    if self._is_pathlike(part):
                        # Windows 命令参数以 / 开头（如 /B、/S、/Q、/i），不是路径
                        # 短标志（/X 或 /XX）在任何平台都不应被当作路径
                        if part.startswith("/") and len(part) <= 3 and part[1:].isalpha():
                            continue

                        # 对于awk/sed/grep等命令，跳过正则表达式参数
                        # 条件1: 包含 { } (awk 的典型语法)
                        if (
                            cmd_name in regex_commands
                            and "/" in part
                            and ("{" in part or "'" in part or '"' in part)
                        ):
                            continue

                        # 条件2: sed/awk 的地址/模式表达式 (/pattern/, //, /re/d 等)
                        # 以 // 开头或包含 , 范围分隔符的斜杠参数是 sed 脚本而非路径
                        if (
                            cmd_name in {"sed", "awk"}
                            and part.startswith("/")
                            and ("," in part or part.count("/") >= 3)
                        ):
                            continue

                        # 跳过解释器的内联代码参数（-c / -e 后的内容不是路径）
                        if (
                            i > 0
                            and parts[i - 1] in {"-c", "-e"}
                            and cmd_name
                            in {
                                "python", "python3", "node", "ruby",
                                "perl", "php", "lua", "bash", "sh", "zsh",
                                "sed",
                            }
                        ):
                            continue

                        try:
                            # 解析路径
                            if not part.startswith("/"):
                                test_path = (Path.cwd() / part).resolve()
                            else:
                                test_path = Path(part).resolve()

                            # 使用新的is_safe_path方法检查
                            if not self.is_safe_path(test_path):
                                # 对于某些只读命令，允许访问系统文件
                                readonly_commands = {
                                    "sysctl", "journalctl",
                                }

                                # 对于只读命令，允许访问（但会记录警告）
                                if cmd_name in readonly_commands:
                                    print(
                                        f"⚠️  Warning: {cmd_name} access outside project directory: {part}"
                                    )
                                    continue

                                # 对于临时目录操作，允许
                                tmp_prefixes = ["/tmp", "/var/tmp", "/private/tmp"]
                                if any(
                                    str(test_path).startswith(prefix)
                                    for prefix in tmp_prefixes
                                ):
                                    if cmd_name in ["mkdir", "touch", "rm", "cp", "mv"]:
                                        print(
                                            f"⚠️  Warning: {cmd_name} operating in temp directory: {part}"
                                        )
                                        continue

                                # 对于包管理器，允许系统路径
                                package_managers = {
                                    "apt", "apt-get", "dpkg",
                                    "yum", "dnf",
                                    "brew",
                                    "pip", "pip3", "pipx",
                                    "npm", "yarn", "pnpm",
                                    "cargo", "go", "gem", "bundle",
                                    "dotnet",
                                    "conda", "mamba",
                                    "pacman", "zypper",
                                    "flatpak", "snap", "apk",
                                    "pkg", "port",
                                    "cpan", "luarocks", "composer",
                                }
                                if cmd_name in package_managers:
                                    continue

                                # 其他情况拒绝
                                return self._build_result(
                                    allowed=False,
                                    reason=f"Path outside safe range: {part}",
                                    risk_level=self.RISK_DANGEROUS,
                                    path=part,
                                )
                        except Exception:
                            # 路径解析失败，可能是无效路径，但允许继续
                            continue

            # 使用评估的风险等级
            return self._build_result(
                allowed=True, reason="Command safety check passed", risk_level=risk_level
            )

        except Exception as e:
            return self._build_result(
                allowed=False,
                reason=f"Command parsing error: {str(e)}",
                risk_level=self.RISK_DANGEROUS,
            )

    def is_safe_content(self, content: str, file_path: str) -> bool:
        """检查内容安全性"""
        # 检查文件大小
        if len(content) > 10 * 1024 * 1024:  # 10MB
            return False

        # 检查是否包含二进制数据
        try:
            content.encode("utf-8")
        except UnicodeEncodeError:
            return False

        # 根据文件类型进行特定检查
        if file_path.endswith(".py"):
            return self._check_python_code(content)
        elif file_path.endswith(".sh"):
            return self._check_shell_script(content)

        return True

    def _check_python_code(self, code: str) -> bool:
        """检查Python代码安全性"""
        try:
            # 解析AST
            tree = ast.parse(code)

            # 检查危险导入
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for name in node.names:
                        full_name = name.name
                        if full_name in self.dangerous_imports:
                            return False

                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for name in node.names:
                        full_name = f"{module}.{name.name}" if module else name.name
                        if full_name in self.dangerous_imports:
                            return False

                # 检查危险函数调用
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        # 检查os.system等
                        func_name = ""
                        if hasattr(node.func, "value") and isinstance(
                            node.func.value, ast.Name
                        ):
                            func_name = f"{node.func.value.id}.{node.func.attr}"
                        if func_name in self.dangerous_imports:
                            return False

            return True

        except SyntaxError:
            # 语法错误，但不是安全问题
            return True
        except:
            return False

    def _check_shell_script(self, script: str) -> bool:
        """检查Shell脚本安全性"""
        # 先合并 \ 续行符，确保续行的命令作为一个整体被检查
        script = self._merge_line_continuations(script)
        lines = script.split("\n")

        for line in lines:
            line = line.strip()

            # 跳过注释和空行
            if not line or line.startswith("#"):
                continue

            # 检查每一行命令
            check_result = self.check_command(line)
            if not check_result["allowed"]:
                return False

        return True

    def is_safe_python_code(self, code: str) -> bool:
        """专门检查要执行的Python代码"""
        # 基本安全检查
        if not self.is_safe_content(code, "execution.py"):
            return False

        # 额外检查：禁止无限循环
        if "while True:" in code and "break" not in code:
            return False

        # 检查资源消耗
        dangerous_patterns = [
            r"import\s+multiprocessing",
            r"import\s+threading",
            r"\.start\(\)",
            r"\.join\(\)",
            r"Pool\(",
            r"Process\(",
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, code):
                return False

        return True
