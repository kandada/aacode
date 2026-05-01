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
    ):
        self.project_path = project_path
        self.project_root = str(project_path)
        self.interactive = interactive  # 是否启用交互式确认
        self.dangerous_command_action = dangerous_command_action  # reject, ask, log

        # 危险命令模式（注意：rm -rf 已移到特殊检查中，允许在项目目录内使用）
        self.dangerous_patterns = [
            # 文件系统危险操作
            # (r'rm\s+(-rf|-r|-f)\s+', '递归删除文件'),  # 移除，改为特殊检查
            (r"format\s+", "Disk formatting"),
            (r"\bdd\s+", "Disk copy/erase"),
            (r"mkfs\s+", "Create filesystem"),
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
            (r"pkill\s+", "Process termination"),  # pkill需要用户确认
            (r"kill\s+", "Process termination"),  # kill需要用户确认
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
            "which",
            "whereis",
            "file",
            "stat",
            "basename",
            "dirname",
            "mktemp",
            "test",  # shell test / [ 命令
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
            "hostname",
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
            "alias",
            "unalias",
            "eval",
            "exec",
            "trap",
            "read",
            "getopts",
            "shift",
            "return",
            # ── 压缩工具 ──
            "tar",
            "gzip",
            "gunzip",
            "zip",
            "unzip",
            "bzip2",
            "bunzip2",
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
            "patch",
            "jq",
            "yq",
            "xmlstarlet",
            "csvkit",
            "pandoc",
            "printf",
            "xargs",
            "tee",
            "rev",
            "fold",
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
            "md5sum",
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
            # ── 其他常用工具 ──
            "date",
            "cal",
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
                "/tmp",
                "/var/tmp",
                "/private/tmp",  # 临时目录（包括macOS的/private/tmp）
                "/usr/share",
                "/usr/local/share",  # 共享数据
                "/etc/passwd",
                "/etc/group",  # 只读系统文件
                "/proc/self",
                "/proc/cpuinfo",
                "/proc/meminfo",  # 只读系统信息
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
        self, command: str, ask_confirmation: bool = True
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

        # 空命令
        if not command or len(command) == 0:
            return self._build_result(
                allowed=False, reason="Empty command", risk_level=self.RISK_DANGEROUS
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

            cmd_path = parts[0]

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

            # 特殊检查：rm命令（智能检查）
            if cmd_name == "rm":
                # 检查是否有-rf等危险选项
                has_dangerous_option = False
                dangerous_targets = []

                for i, part in enumerate(parts):
                    if part.startswith("-") and any(c in part for c in "rf"):
                        has_dangerous_option = True
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

                        # 检查是否尝试删除项目目录外的文件
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

                # 如果有危险选项
                if has_dangerous_option:
                    # 如果尝试删除项目外的文件，拒绝
                    if dangerous_targets:
                        return {
                            "allowed": False,
                            "reason": f"rm -rf cannot delete files outside project directory: {', '.join(dangerous_targets)}",
                            "suggestion": "rm -rf can only be used within the project directory",
                        }

                    # 在项目目录内使用 rm -rf
                    # 如果是交互模式且要求确认，则询问用户
                    if ask_confirmation and self.interactive:
                        # 提取要删除的目标
                        targets = [p for p in parts[1:] if not p.startswith("-")]
                        target_desc = ", ".join(targets) if targets else "files"

                        if not self._ask_user_confirmation(
                            command, f"rm -rf recursive deletion, will delete: {target_desc}"
                        ):
                            return {"allowed": False, "reason": "User cancelled operation"}
                        print("✅ User confirmed rm -rf operation")
                        return {"allowed": True, "reason": "rm -rf operation (user confirmed)"}
                    else:
                        # 非交互模式或不需要确认，直接允许（项目内）
                        return {"allowed": True, "reason": "rm -rf operation (within project directory)"}

                # 普通rm命令，允许
                return {"allowed": True, "reason": "rm command (safe)"}

            # 特殊检查：sudo命令（允许但需要确认）
            if cmd_name == "sudo":
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
                # 检查是否尝试修改系统文件权限
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
                                # 非交互模式，允许但警告
                                return {
                                    "allowed": True,
                                    "reason": "chmod 777 operation (within project)",
                                }

                # 项目内的权限修改，在交互模式下询问确认
                if ask_confirmation and self.interactive:
                    if not self._ask_user_confirmation(
                        command, f"{cmd_name} permission modification"
                    ):
                        return {"allowed": False, "reason": "User cancelled operation"}
                    return {"allowed": True, "reason": f"{cmd_name} operation (user confirmed)"}
                else:
                    # 非交互模式，直接允许（项目内）
                    return {"allowed": True, "reason": f"{cmd_name} operation (within project)"}

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

            # 检查路径参数（使用新的is_safe_path方法）
            # 对于awk, sed, grep等命令，它们的参数可能是正则表达式而非路径，需要特殊处理
            regex_commands = {"awk", "sed", "grep", "rg", "ag", "find"}

            for i, part in enumerate(parts):
                # 跳过命令本身
                if i == 0:
                    continue

                # 检查路径参数
                if ".." in part or part.startswith("/"):
                    # Windows 命令参数以 / 开头（如 /B、/S、/Q、/i），不是路径
                    # 短标志（/X 或 /XX）在任何平台都不应被当作路径
                    if part.startswith("/") and len(part) <= 3 and part[1:].isalpha():
                        continue

                    # 对于awk/sed/grep等命令，跳过正则表达式参数（以/开头且包含空格或特殊字符的是正则）
                    if (
                        cmd_name in regex_commands
                        and "/" in part
                        and ("{" in part or "'" in part or '"' in part)
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
                                "ls",
                                "cat",
                                "file",
                                "stat",
                                "head",
                                "tail",
                                "less",
                                "more",
                                "grep",
                                "find",
                                "which",
                                "whereis",
                                "python",
                                "python3",
                                "node",
                                "ruby",
                                "java",
                                "df",
                                "du",
                                "ps",
                                "top",
                                "htop",
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
                                "apt",
                                "apt-get",
                                "dpkg",
                                "yum",
                                "dnf",
                                "brew",
                                "pip",
                                "pip3",
                                "npm",
                                "yarn",
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
