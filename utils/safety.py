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


class SafetyGuard:
    """安全护栏"""

    # 风险等级
    RISK_SAFE = "safe"  # 安全命令，直接允许
    RISK_WARNING = "warning"  # 警告命令，需要确认
    RISK_DANGEROUS = "dangerous"  # 危险命令，直接拒绝
    RISK_UNKNOWN = "unknown"  # 未知命令，拒绝

    def __init__(self, project_path: Path, interactive: bool = True):
        self.project_path = project_path
        self.project_root = str(project_path)
        self.interactive = interactive  # 是否启用交互式确认

        # 危险命令模式（注意：rm -rf 已移到特殊检查中，允许在项目目录内使用）
        self.dangerous_patterns = [
            # 文件系统危险操作
            # (r'rm\s+(-rf|-r|-f)\s+', '递归删除文件'),  # 移除，改为特殊检查
            (r"format\s+", "磁盘格式化"),
            (r"\bdd\s+", "磁盘复制/擦除"),  # 使用\b确保是单词边界
            (r"mkfs\s+", "创建文件系统"),
            # 系统危险操作
            (r"shutdown\s+", "关闭系统"),
            (r"halt\s+", "停止系统"),
            (r"reboot\s+", "重启系统"),
            (r"^\s*init\s+", "init进程"),  # 只匹配开头的init命令
            # 网络危险操作
            (r"iptables\s+", "防火墙规则"),
            (r"ufw\s+", "防火墙"),
            # Shell危险操作
            (r":\(\)\{.*?;\s*\}.*?;", "fork炸弹"),
            (r"exec\s+/dev/", "设备执行"),
            # 特别危险的权限操作（放宽chmod和chown，但限制特定模式）
            (r"chmod\s+[0-7]{3,4}\s+/\S*", "系统目录权限设置"),
            (r"chown\s+.*?:\s+/\S*", "系统文件所有权更改"),
        ]

        # 允许的命令白名单（相对安全）
        self.allowed_commands = {
            # 基础命令
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
            # Python生态
            "python",
            "python3",
            "pip",
            "pip3",
            "virtualenv",
            "venv",
            "poetry",
            "pipenv",
            "conda",
            "pytest",
            "unittest",
            "nose",
            "tox",
            "django-admin",
            "django",
            "flask",
            "fastapi",
            "uvicorn",
            "gunicorn",
            "celery",
            "celery-worker",
            # Node.js生态
            "node",
            "npm",
            "npx",
            "yarn",
            "pnpm",
            "express-generator",
            "nest",
            "strapi",
            # 版本控制
            "git",
            "svn",
            "hg",
            "pre-commit",
            "git-lfs",
            "git-flow",
            "husky",
            # 网络工具
            "curl",
            "wget",
            "http",
            "httpie",
            "scp",
            "rsync",
            "ssh",
            "ping",
            "traceroute",
            "netstat",
            "sftp",
            "sshfs",
            "rclone",
            "nc",
            # 搜索工具
            "rg",
            "ag",
            "ack",
            "fd",
            # 系统信息
            "ps",
            "top",
            "htop",
            "df",
            "du",
            "free",
            "uptime",
            "uname",
            # 权限管理（需谨慎）
            "chmod",
            "chown",
            # 包管理
            "apt",
            "apt-get",
            "dpkg",
            "yum",
            "dnf",
            "brew",
            "pacman",
            "systemctl",
            "service",
            "sudo",  # 权限提升（需特别检查）
            # 编程语言
            "ruby",
            "gem",
            "bundle",  # Ruby
            "go",
            "gofmt",  # Go
            "cargo",
            "rustc",  # Rust
            "java",
            "javac",
            "mvn",
            "gradle",  # Java
            "php",
            "composer",  # PHP
            "perl",
            "cpan",  # Perl
            "lua",
            "luarocks",  # Lua
            # 编译工具
            "make",
            "cmake",
            "gcc",
            "g++",
            "clang",
            "cc",
            # 编辑器
            "vim",
            "vi",
            "nano",
            "emacs",
            "code",
            "subl",
            # Shell
            "bash",
            "sh",
            "zsh",
            "fish",
            "source",
            "export",
            "alias",
            # 压缩工具
            "tar",
            "gzip",
            "gunzip",
            "zip",
            "unzip",
            "bzip2",
            "xz",
            # 文本处理
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
            # 文件操作扩展
            "tree",
            "exa",
            "bat",
            "fzf",
            "ripgrep",
            "silversearcher-ag",
            "entr",
            "inotifywait",
            "watchexec",
            # 虚拟化和容器
            "vagrant",
            "virtualbox",
            "qemu",
            "kvm",
            "lxc",
            "lxd",
            "buildah",
            "skopeo",
            "nerdctl",
            # Docker生态
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
            # 数据库工具
            "psql",
            "mysql",
            "sqlite3",
            "mongosh",
            "redis-cli",
            "pg_dump",
            "mysqldump",
            "mongoexport",
            "redis-server",
            # 系统监控
            "htop",
            "iotop",
            "nethogs",
            "glances",
            "ncdu",
            # 性能分析
            "perf",
            "strace",
            "ltrace",
            "valgrind",
            # 前端工具
            "webpack",
            "vite",
            "rollup",
            "parcel",
            "gulp",
            "grunt",
            "npm",
            "yarn",
            "pnpm",
            "bun",
            # 图像工具
            "ffmpeg",
            "convert",
            "identify",
            "ffprobe",
            # 其他常用工具
            "date",
            "cal",
            "bc",
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
            "set",
            "unset",
            "clear",
            "reset",
            "tput",
            # 其他实用工具
            "tmux",
            "screen",
            "byobu",
            "zellij",
            "parallel",
            "xargs",
            "tee",
            "sponge",
            "units",
            "bc",
            "dc",
            "calc",
            "neofetch",
            "screenfetch",
            "asciin",
            "asciinema",
            "nvidia",
            "byobu",
            "zellij",
            "fzf",
            "exa",
            "lsd",
            "tldr",
            "cheat",
            "navi",
            "starship",
            "oh-my-zsh",
            "powerline",
            # 日志查看
            "journalctl",
            "dmesg",
            "tail",
            "less +F",
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
        print("⚠️  检测到潜在危险操作")
        print("=" * 60)
        print(f"命令: {command}")
        print(f"原因: {reason}")
        print("=" * 60)

        try:
            response = input("是否继续执行? (yes/no，默认no): ").strip().lower()
            return response in ["yes", "y"]
        except (KeyboardInterrupt, EOFError):
            print("\n❌ 用户取消操作")
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
            return self.RISK_UNKNOWN, f"命令不在白名单中: {cmd_name}"

        # 2. 检查危险命令模式（已经在check_command中检查过）
        # 3. 根据命令类型评估风险

        # 高风险命令（需要特别检查）
        high_risk_commands = {
            "rm": "文件删除操作",
            "sudo": "权限提升操作",
            "chmod": "权限修改操作",
            "chown": "所有权修改操作",
            "dd": "磁盘操作",
            "format": "磁盘格式化",
            "mkfs": "创建文件系统",
            "shutdown": "系统关机",
            "halt": "系统停止",
            "reboot": "系统重启",
            "iptables": "防火墙配置",
            "ufw": "防火墙管理",
        }

        if cmd_name in high_risk_commands:
            return self.RISK_WARNING, high_risk_commands[cmd_name]

        # 中风险命令（可能需要确认）
        medium_risk_commands = {
            "pip": "Python包管理",
            "pip3": "Python包管理",
            "npm": "Node.js包管理",
            "yarn": "Node.js包管理",
            "apt": "系统包管理",
            "apt-get": "系统包管理",
            "docker": "容器操作",
            "docker-compose": "容器编排",
            "systemctl": "系统服务管理",
            "service": "服务管理",
        }

        if cmd_name in medium_risk_commands:
            return self.RISK_WARNING, medium_risk_commands[cmd_name]

        # 低风险命令（安全）
        return self.RISK_SAFE, "安全命令"

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
                allowed=False, reason="空命令", risk_level=self.RISK_DANGEROUS
            )

        # 检查危险模式
        for pattern, description in self.dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return self._build_result(
                    allowed=False,
                    reason=f"检测到危险操作: {description}",
                    risk_level=self.RISK_DANGEROUS,
                    pattern=pattern,
                )

        # 解析命令
        try:
            parts = shlex.split(command)
            if not parts:
                return self._build_result(
                    allowed=False, reason="无法解析命令", risk_level=self.RISK_DANGEROUS
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
                    print(f"✅ 允许项目内可执行文件: {cmd_path}")
                    return self._build_result(
                        allowed=True,
                        reason=f"项目内可执行文件: {cmd_name}",
                        risk_level=self.RISK_SAFE,
                    )
                else:
                    # 对于项目内的脚本，如果是常见扩展名则允许
                    allowed_extensions = {".sh", ".py", ".js", ".rb", ".pl"}
                    if any(cmd_path.endswith(ext) for ext in allowed_extensions):
                        print(f"✅ 允许项目内脚本: {cmd_path}")
                        return self._build_result(
                            allowed=True,
                            reason="项目内脚本文件",
                            risk_level=self.RISK_SAFE,
                        )

            # 检查是否在白名单中
            if cmd_name not in self.allowed_commands:
                return self._build_result(
                    allowed=False,
                    reason=f"命令不在白名单中: {cmd_name}",
                    risk_level=self.RISK_UNKNOWN,
                    suggestion=f"可用命令: {', '.join(sorted(list(self.allowed_commands)))}",
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
                        dangerous_patterns = ["/", "/*", "~", "~/*", "/etc", "/var", "/usr", "/bin", "/sbin", "/lib"]
                        if any(target_path == pattern or target_path.startswith(pattern + "/") for pattern in dangerous_patterns):
                            return {
                                "allowed": False,
                                "reason": f"rm命令目标过于危险: {target_path}",
                                "risk_level": self.RISK_DANGEROUS,
                                "needs_confirmation": False,
                                "suggestion": "请明确指定要删除的文件或目录",
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
                            "reason": f"rm -rf 不能删除项目目录外的文件: {', '.join(dangerous_targets)}",
                            "suggestion": "只能在项目目录内使用 rm -rf",
                        }

                    # 在项目目录内使用 rm -rf
                    # 如果是交互模式且要求确认，则询问用户
                    if ask_confirmation and self.interactive:
                        # 提取要删除的目标
                        targets = [p for p in parts[1:] if not p.startswith("-")]
                        target_desc = ", ".join(targets) if targets else "文件"

                        if not self._ask_user_confirmation(
                            command, f"rm -rf 递归删除操作，将删除: {target_desc}"
                        ):
                            return {"allowed": False, "reason": "用户取消操作"}
                        print("✅ 用户确认执行 rm -rf 操作")
                        return {"allowed": True, "reason": "rm -rf操作（用户已确认）"}
                    else:
                        # 非交互模式或不需要确认，直接允许（项目内）
                        return {"allowed": True, "reason": "rm -rf操作（项目目录内）"}

                # 普通rm命令，允许
                return {"allowed": True, "reason": "rm命令（安全）"}

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
                            "reason": f"sudo命令 '{sub_cmd}' 不在允许列表中",
                            "suggestion": f"允许的sudo命令: {', '.join(allowed_sudo_commands)}",
                        }

                    # 允许安装操作，但在交互模式下需要用户确认
                    if any(
                        install_keyword in " ".join(parts).lower()
                        for install_keyword in ["install", "add", "update", "upgrade"]
                    ):
                        if ask_confirmation and self.interactive:
                            if not self._ask_user_confirmation(
                                command, "sudo权限操作，可能修改系统配置"
                            ):
                                return {"allowed": False, "reason": "用户取消操作"}
                            print(f"✅ 用户确认sudo操作")
                            return {
                                "allowed": True,
                                "reason": "软件包安装操作（用户已确认）",
                            }
                        else:
                            # 非交互模式，直接允许
                            return {"allowed": True, "reason": "软件包安装操作"}

                # 其他sudo操作，在交互模式下询问
                if ask_confirmation and self.interactive:
                    if not self._ask_user_confirmation(command, "sudo权限操作"):
                        return {"allowed": False, "reason": "用户取消操作"}
                    return {"allowed": True, "reason": "sudo操作（用户已确认）"}
                else:
                    return {"allowed": True, "reason": "sudo操作"}

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
                                "reason": f"{cmd_name}命令不能修改项目目录外的文件权限",
                            }
                        # 检查危险权限设置（如777）
                        if cmd_name == "chmod" and "777" in part:
                            if ask_confirmation and self.interactive:
                                if not self._ask_user_confirmation(
                                    command, "chmod 777权限过于宽松，存在安全风险"
                                ):
                                    return {"allowed": False, "reason": "用户取消操作"}
                                return {
                                    "allowed": True,
                                    "reason": "chmod 777操作（用户已确认）",
                                }
                            else:
                                # 非交互模式，允许但警告
                                return {
                                    "allowed": True,
                                    "reason": "chmod 777操作（项目内）",
                                }

                # 项目内的权限修改，在交互模式下询问确认
                if ask_confirmation and self.interactive:
                    if not self._ask_user_confirmation(
                        command, f"{cmd_name}权限修改操作"
                    ):
                        return {"allowed": False, "reason": "用户取消操作"}
                    return {"allowed": True, "reason": f"{cmd_name}操作（用户已确认）"}
                else:
                    # 非交互模式，直接允许（项目内）
                    return {"allowed": True, "reason": f"{cmd_name}操作（项目内）"}

            # 特殊检查：pip/pip3命令（允许大部分操作）
            if cmd_name in ["pip", "pip3"]:
                print(f"📦 检测到pip命令: {' '.join(parts)}")
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
                            "reason": f"pip操作 '{pip_action}' 可能产生大量文件",
                            "suggestion": "请使用 install 代替",
                        }
                # 允许其他所有pip操作
                return {"allowed": True, "reason": "pip操作"}

            # 特殊检查：npm/yarn命令（允许大部分操作）
            if cmd_name in ["npm", "yarn", "npx", "pnpm"]:
                print(f"📦 检测到{cmd_name}命令: {' '.join(parts)}")
                # 允许所有常见操作
                return {"allowed": True, "reason": f"{cmd_name}操作"}

            # 检查路径参数（使用新的is_safe_path方法）
            for i, part in enumerate(parts):
                # 跳过命令本身
                if i == 0:
                    continue

                # 检查路径参数
                if ".." in part or part.startswith("/"):
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
                                    f"⚠️  警告: {cmd_name}命令访问项目目录外路径: {part}"
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
                                        f"⚠️  警告: {cmd_name}命令在临时目录操作: {part}"
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
                                reason=f"路径超出安全范围: {part}",
                                risk_level=self.RISK_DANGEROUS,
                                path=part,
                            )
                    except Exception:
                        # 路径解析失败，可能是无效路径，但允许继续
                        continue

            # 使用评估的风险等级
            return self._build_result(
                allowed=True, reason="命令安全检查通过", risk_level=risk_level
            )

        except Exception as e:
            return self._build_result(
                allowed=False,
                reason=f"命令解析错误: {str(e)}",
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
