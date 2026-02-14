# ⚡ Skills Manager

AI Agent 技能发现、下载与管理的 GUI 应用 — 一键部署到 Claude Code、Kiro CLI、Gemini CLI、Codex CLI、OpenCode、Roo Code、Droid 和 Grok CLI。

无外部依赖 — 仅使用 Python 标准库（tkinter + sqlite3）。

[English](README.md) | [한국어](README_ko.md) | [日本語](README_ja.md)

## 快速开始

```bash
python3 run.py
```

或通过 pip 安装：

```bash
pip install -e .
skills-manager
```

## 功能特性

- **自动发现**：从远程注册表获取技能，失败时回退到本地 `registry.json`
- **安装/卸载**：一键安装，带进度指示
- **更新检测**：高亮显示有新版本的技能
- **搜索与筛选**：模糊搜索 + 相关性排序；按已安装/可用/分类筛选
- **分页浏览**：SQLite 分页查询 — 流畅处理数千个技能
- **自动备份**：更新/卸载前自动备份旧版本
- **安全扫描**：静态分析恶意模式（提示注入、数据泄露、权限提升、供应链攻击）
- **预扫描**：安装前扫描 — 下载到临时目录，扫描后丢弃
- **扫描追踪器**：实时扫描进度对话框，带可滚动结果日志
- **代理支持**：可配置 HTTP/HTTPS 代理
- **暗色主题**：Catppuccin Mocha 风格界面，带工具提示
- **部署到 AI 工具**：符号链接已安装技能到 Claude Code、Kiro CLI、Gemini CLI、Codex CLI、OpenCode、Roo Code、Droid、Grok CLI
- **快捷键**：Ctrl+F（搜索）、Ctrl+R（刷新）、Ctrl+I（已安装）、Escape（清除）

## 部署技能到 AI 工具

通过 GUI 安装技能后，部署到你的 AI 编程助手：

```bash
python3 deploy_skills.py              # 部署到所有检测到的工具
python3 deploy_skills.py --target kiro  # 部署到指定工具
python3 deploy_skills.py --dry-run    # 预览，不实际操作
python3 deploy_skills.py --clean      # 移除已部署的符号链接
```

支持的目标：
| 工具 | 技能目录 |
|------|----------|
| Claude Code | `~/.claude/skills/` |
| Kiro CLI | `~/.kiro/skills/` |
| Gemini CLI | `~/.gemini/skills/` |
| Codex CLI | `~/.codex/skills/` |
| OpenCode | `~/.config/opencode/skills/` |
| Roo Code | `~/.roo/skills/` |
| Droid (Factory) | `~/.factory/skills/` |
| Grok CLI | `~/.grok/skills/` |

技能通过符号链接部署（非复制），保持同步且不占用额外磁盘空间。

## 安全扫描

通过 GUI 或命令行扫描技能中的恶意内容：

```bash
python3 skillscan.py ./my-skill/                 # 扫描技能目录
python3 skillscan.py --auto                       # 扫描所有已安装技能
python3 skillscan.py --auto --min-severity HIGH   # 仅显示高风险
python3 skillscan.py --auto -o report.txt         # 输出到文件
python3 skillscan.py --auto --json                # JSON 输出
```

检测 4 类威胁：提示注入、数据泄露、权限提升、供应链攻击。

在 GUI 中，对已安装技能使用 **🛡 Security Scan**，对未安装技能使用 **🛡 Pre-scan** 在安装前评估风险。

## 代理配置

点击标题栏的 **⚙ Proxy** 配置 HTTP/HTTPS 代理。设置保存在 `settings.json` 中。

所有网络请求（注册表获取、GitHub API、技能下载）均通过配置的代理。

## 项目结构

```
skills_manager/
├── run.py              # 入口
├── gui.py              # tkinter GUI（分页、扫描追踪、工具提示）
├── skill_core.py       # 核心逻辑（获取、安装、扫描、代理）
├── db.py               # SQLite 存储后端（分页查询）
├── deploy_skills.py    # 部署技能到 Claude/Kiro/Gemini/Codex/OpenCode/Roo/Droid/Grok
├── skillscan.py        # 安全扫描器（14 种模式，4 类威胁）
├── logger.py           # 日志系统
├── version_manager.py  # 备份与回滚
├── registry.json       # 本地回退注册表
├── settings.json       # 用户设置（代理等）— 自动创建
├── skills.db           # SQLite 数据库 — 自动创建
├── installed_skills/   # 已安装技能 + 清单
├── logs/               # 操作日志
└── backups/            # 技能版本备份
```

## 自定义注册表

编辑 `registry.json` 或修改 `skill_core.py` 中的 `REMOTE_REGISTRIES` 指向你自己的注册表 URL。

## 许可证

MIT