# ⚡ Skills Manager

AI Agent スキルの検索・ダウンロード・管理を行う GUI アプリケーション — Claude Code、Kiro CLI、Gemini CLI、Codex CLI、OpenCode、Roo Code、Droid、Grok CLI へワンクリックデプロイ。

外部依存なし — Python 標準ライブラリのみ使用（tkinter + sqlite3）。

[English](README.md) | [中文](README_zh.md) | [한국어](README_ko.md)

## クイックスタート

```bash
python3 run.py
```

pip でインストール：

```bash
pip install -e .
skills-manager
```

## 主な機能

- **自動検出**: リモートレジストリからスキルを取得、失敗時はローカル `registry.json` にフォールバック
- **インストール/アンインストール**: ワンクリックインストール、進捗表示付き
- **アップデート検出**: 新バージョンがあるスキルをハイライト表示
- **検索とフィルター**: ファジー検索 + 関連性スコアリング、インストール済み/利用可能/カテゴリ別フィルター
- **ページネーション**: SQLite ベースのページクエリ — 数千のスキルをスムーズに処理
- **自動バックアップ**: アップデート/アンインストール前に自動バージョンバックアップ
- **セキュリティスキャン**: 悪意のあるパターンの静的解析（プロンプトインジェクション、データ流出、権限昇格、サプライチェーン攻撃）
- **プリスキャン**: インストール前スキャン — 一時ディレクトリにダウンロード、スキャン後破棄
- **スキャントラッカー**: リアルタイムスキャン進捗ダイアログ、スクロール可能な結果ログ
- **プロキシサポート**: HTTP/HTTPS プロキシ設定可能
- **ダークテーマ**: Catppuccin Mocha スタイルのインターフェース、ツールチップ付き
- **AI ツールへデプロイ**: インストール済みスキルを Claude Code、Kiro CLI、Gemini CLI、Codex CLI、OpenCode、Roo Code、Droid、Grok CLI にシンボリックリンク
- **キーボードショートカット**: Ctrl+F（検索）、Ctrl+R（更新）、Ctrl+I（インストール済み）、Escape（クリア）

## AI ツールへのスキルデプロイ

GUI でスキルをインストール後、AI コーディングアシスタントにデプロイ：

```bash
python3 deploy_skills.py              # 検出された全ツールにデプロイ
python3 deploy_skills.py --target kiro  # 特定ツールにデプロイ
python3 deploy_skills.py --dry-run    # プレビュー（変更なし）
python3 deploy_skills.py --clean      # デプロイ済みシンボリックリンクを削除
```

対応ツール：
| ツール | スキルディレクトリ |
|--------|--------------------|
| Claude Code | `~/.claude/skills/` |
| Kiro CLI | `~/.kiro/skills/` |
| Gemini CLI | `~/.gemini/skills/` |
| Codex CLI | `~/.codex/skills/` |
| OpenCode | `~/.config/opencode/skills/` |
| Roo Code | `~/.roo/skills/` |
| Droid (Factory) | `~/.factory/skills/` |
| Grok CLI | `~/.grok/skills/` |

スキルはシンボリックリンクでデプロイ（コピーではない）、同期を維持し追加ディスク容量不要。

## セキュリティスキャン

GUI またはコマンドラインで悪意のあるコンテンツをスキャン：

```bash
python3 skillscan.py ./my-skill/                 # スキルディレクトリをスキャン
python3 skillscan.py --auto                       # インストール済み全スキルをスキャン
python3 skillscan.py --auto --min-severity HIGH   # 高リスクのみ表示
python3 skillscan.py --auto -o report.txt         # ファイルに出力
python3 skillscan.py --auto --json                # JSON 出力
```

4 カテゴリの脅威を検出：プロンプトインジェクション、データ流出、権限昇格、サプライチェーン攻撃。

GUI では、インストール済みスキルに **🛡 Security Scan**、未インストールスキルに **🛡 Pre-scan** を使用してインストール前にリスクを評価。

## プロキシ設定

ヘッダーの **⚙ Proxy** をクリックして HTTP/HTTPS プロキシを設定。設定は `settings.json` に保存。

全ネットワークリクエスト（レジストリ取得、GitHub API、スキルダウンロード）が設定されたプロキシを経由。

## プロジェクト構成

```
skills_manager/
├── run.py              # エントリーポイント
├── gui.py              # tkinter GUI（ページネーション、スキャントラッカー、ツールチップ）
├── skill_core.py       # コアロジック（取得、インストール、スキャン、プロキシ）
├── db.py               # SQLite ストレージバックエンド（ページクエリ）
├── deploy_skills.py    # Claude/Kiro/Gemini/Codex/OpenCode/Roo/Droid/Grok へスキルデプロイ
├── skillscan.py        # セキュリティスキャナー（14 パターン、4 カテゴリ）
├── logger.py           # ロギングシステム
├── version_manager.py  # バックアップとロールバック
├── registry.json       # ローカルフォールバックレジストリ
├── settings.json       # ユーザー設定（プロキシ等）— 自動作成
├── skills.db           # SQLite データベース — 自動作成
├── installed_skills/   # インストール済みスキル + マニフェスト
├── logs/               # 操作ログ
└── backups/            # スキルバージョンバックアップ
```

## カスタムレジストリ

`registry.json` を編集するか、`skill_core.py` の `REMOTE_REGISTRIES` を独自のレジストリ URL に設定。

## ライセンス

MIT