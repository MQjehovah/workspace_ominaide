"""Prompts and tool schema for the built-in coding agent loop."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and directories under the project. Paths are relative to the project root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path, default '.'"},
                    "depth": {"type": "number", "description": "Recursion depth 1-4, default 2"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 text file. Use offset/limit for large files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path"},
                    "offset": {"type": "number", "description": "Start line offset, default 0"},
                    "limit": {"type": "number", "description": "Max lines, default 400"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with the given content. Parent directories are created automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path"},
                    "content": {"type": "string", "description": "Full file content"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace an exact string in a file. Use replace_all to change every occurrence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path"},
                    "old_string": {"type": "string", "description": "Exact text to replace"},
                    "new_string": {"type": "string", "description": "Replacement text"},
                    "replace_all": {"type": "boolean", "description": "Replace all occurrences, default false"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_text",
            "description": "Search text files in the project with a regular expression. Returns file path, line number and line text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regular expression"},
                    "path": {"type": "string", "description": "Relative directory to search, default '.'"},
                    "include": {"type": "string", "description": "Optional file suffix filter, e.g. '.ts,.vue'"},
                    "max_results": {"type": "number", "description": "Max matches, default 50"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_search",
            "description": "Search Agent Skills enabled for this Bot. Use before skill_call; never guess a skill key.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keywords, e.g. testing, review, frontend"},
                    "limit": {"type": "number", "description": "Max results, default 5"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_call",
            "description": "Execute a skill returned by skill_search. Pass skill_key and an input object.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_key": {"type": "string", "description": "Skill key from skill_search"},
                    "input": {"type": "object", "description": "Skill input parameters"},
                },
                "required": ["skill_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Find files by glob pattern, e.g. **/*.py or src/**/*.ts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern relative to path"},
                    "path": {"type": "string", "description": "Root directory, default '.'"},
                    "max_results": {"type": "number", "description": "Max matches, default 200"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_patch",
            "description": "Apply multiple exact string edits atomically. Validates every edit before writing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "changes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "old_string": {"type": "string"},
                                "new_string": {"type": "string"},
                                "replace_all": {"type": "boolean"},
                            },
                            "required": ["path", "old_string", "new_string"],
                        },
                    },
                },
                "required": ["changes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a single file. Directories are not supported.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Relative file path"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": "Move or rename a single file. Fails if the target exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Relative source path"},
                    "target": {"type": "string", "description": "Relative target path"},
                },
                "required": ["source", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Show the current git diff (optionally staged or stat-only).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Optional relative path"},
                    "staged": {"type": "boolean", "description": "Show staged changes"},
                    "stat": {"type": "boolean", "description": "Show diffstat only"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command in the project directory and return stdout/stderr/exit code. Use for builds and tests.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command line to run"},
                    "cwd": {"type": "string", "description": "Relative working directory, default '.'"},
                    "timeout_ms": {"type": "number", "description": "Timeout in ms, default 120000"},
                },
                "required": ["command"],
            },
        },
    },
]


def coding_system_prompt(project: str, developer: dict | None, context: str = "",
                         branch: str | None = None) -> str:
    lines = [
        "你是 OmniAide 内置的 Coding Agent，运行在用户自己的服务器上。",
        f"项目根目录：{project}",
        "",
        "工作方式：",
        "1. 先理解项目结构与相关代码，再动手修改；优先读取现有实现而不是猜测。",
        "2. 使用工具真正完成工作，不要只输出计划或伪代码。",
        "3. 所有路径都使用相对项目根目录的路径；不要访问项目根目录以外的位置。",
        "4. 修改后尽量运行构建、测试或最小验证命令确认没有破坏。",
        "5. 不要执行格式化磁盘、关机、删除项目根目录等破坏性命令。",
        "6. 完成后用中文简要说明改了什么、验证结果，以及仍需用户注意的事项。",
        "7. 单次运行有轮次预算。接近上限时停止探索，优先给出可交付结果和阶段性总结。",
        "8. 如果用户只要求分析或报告，不要为了无关的测试失败无限排查；主要调查完成后及时输出报告。",
        "",
        "可用工具：list_dir / glob / read_file / write_file / edit_file / apply_patch / delete_file / move_file / search_text / git_diff / run_command。",
        "可用技能：先 skill_search 检索，再 skill_call 执行；不要猜测技能 key。",
        "",
        "【分支与交付】",
        "默认建议在 feature/* 分支开发；只有用户明确要求时才直接在 master 改动。",
        "如果本次运行指定了分支，就按指定分支执行；否则由交付层创建 feature/* 分支。",
        "不要自行执行 git commit 或 git push；改完留在工作区即可，交付层统一处理。",
    ]
    if branch:
        lines.append(f"本次运行指定分支：{branch}")
        if branch in ("main", "master"):
            lines.append("用户明确要求在这个受保护分支上改动；完成总结里要提醒风险。")

    if context.strip():
        lines += ["", "【项目快照】（自动生成，可能不是最新，动手前以实际文件为准）", context.strip()]

    if developer:
        perms = developer.get("permissions") if isinstance(developer.get("permissions"), list) else []
        lines += ["", "【开发者档案】"]
        if developer.get("github_username"):
            lines.append(f"GitHub 用户名：{developer['github_username']}")
        if developer.get("github_email"):
            lines.append(f"Git 提交邮箱：{developer['github_email']}")
        if developer.get("default_branch"):
            lines.append(f"默认分支：{developer['default_branch']}")
        if developer.get("workspace_roots"):
            lines.append(f"工作区根目录：{', '.join(developer['workspace_roots'])}")
        if developer.get("commit_style"):
            lines.append(f"提交信息规范：{developer['commit_style']}")
        lines.append(f"允许的代码操作：{', '.join(perms) if perms else '仅读取与修改'}")
        if developer.get("notes"):
            lines.append(f"补充说明：{developer['notes']}")
    else:
        lines.append("")
        lines.append("未配置开发者档案：只允许读取和修改文件，不要执行 git commit 或 git push。")
    return "\n".join(lines)
