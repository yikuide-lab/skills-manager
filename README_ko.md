# ⚡ Skills Manager

AI Agent 스킬을 검색, 다운로드, 관리하는 GUI 애플리케이션 — Claude Code, Kiro CLI, Gemini CLI에 원클릭 배포.

외부 의존성 없음 — Python 표준 라이브러리만 사용 (tkinter + sqlite3).

[English](README.md) | [中文](README_zh.md) | [日本語](README_ja.md)

## 빠른 시작

```bash
python3 run.py
```

pip으로 설치:

```bash
pip install -e .
skills-manager
```

## 주요 기능

- **자동 검색**: 원격 레지스트리에서 스킬 가져오기, 실패 시 로컬 `registry.json` 사용
- **설치/제거**: 원클릭 설치, 진행률 표시
- **업데이트 감지**: 새 버전이 있는 스킬 강조 표시
- **검색 및 필터**: 퍼지 검색 + 관련성 정렬; 설치됨/사용 가능/카테고리별 필터
- **페이지네이션**: SQLite 기반 페이지 쿼리 — 수천 개의 스킬을 원활하게 처리
- **자동 백업**: 업데이트/제거 전 자동 버전 백업
- **보안 스캔**: 악성 패턴 정적 분석 (프롬프트 인젝션, 데이터 유출, 권한 상승, 공급망 공격)
- **사전 스캔**: 설치 전 스캔 — 임시 디렉토리에 다운로드, 스캔 후 삭제
- **스캔 트래커**: 실시간 스캔 진행 대화상자, 스크롤 가능한 결과 로그
- **프록시 지원**: HTTP/HTTPS 프록시 설정 가능
- **다크 테마**: Catppuccin Mocha 스타일 인터페이스, 툴팁 포함
- **AI 도구 배포**: 설치된 스킬을 Claude Code, Kiro CLI, Gemini CLI에 심볼릭 링크
- **단축키**: Ctrl+F (검색), Ctrl+R (새로고침), Ctrl+I (설치됨), Escape (초기화)

## AI 도구에 스킬 배포

GUI에서 스킬 설치 후, AI 코딩 어시스턴트에 배포:

```bash
python3 deploy_skills.py              # 감지된 모든 도구에 배포
python3 deploy_skills.py --target kiro  # 특정 도구에 배포
python3 deploy_skills.py --dry-run    # 미리보기 (변경 없음)
python3 deploy_skills.py --clean      # 배포된 심볼릭 링크 제거
```

지원 대상:
| 도구 | 스킬 디렉토리 |
|------|---------------|
| Claude Code | `~/.claude/skills/` |
| Kiro CLI | `~/.kiro/skills/` |
| Gemini CLI | `~/.gemini/skills/` |

스킬은 심볼릭 링크로 배포되어 동기화 유지, 추가 디스크 공간 불필요.

## 보안 스캔

GUI 또는 명령줄에서 악성 콘텐츠 스캔:

```bash
python3 skillscan.py ./my-skill/                 # 스킬 디렉토리 스캔
python3 skillscan.py --auto                       # 설치된 모든 스킬 스캔
python3 skillscan.py --auto --min-severity HIGH   # 고위험만 표시
python3 skillscan.py --auto -o report.txt         # 파일로 출력
python3 skillscan.py --auto --json                # JSON 출력
```

4가지 위협 카테고리 탐지: 프롬프트 인젝션, 데이터 유출, 권한 상승, 공급망 공격.

GUI에서 설치된 스킬에 **🛡 Security Scan**, 미설치 스킬에 **🛡 Pre-scan**을 사용하여 설치 전 위험을 평가.

## 프록시 설정

헤더의 **⚙ Proxy**를 클릭하여 HTTP/HTTPS 프록시 설정. `settings.json`에 저장됨.

모든 네트워크 요청 (레지스트리, GitHub API, 스킬 다운로드)이 설정된 프록시를 통해 전송.

## 프로젝트 구조

```
skills_manager/
├── run.py              # 진입점
├── gui.py              # tkinter GUI (페이지네이션, 스캔 트래커, 툴팁)
├── skill_core.py       # 핵심 로직 (가져오기, 설치, 스캔, 프록시)
├── db.py               # SQLite 저장소 (페이지 쿼리)
├── deploy_skills.py    # Claude/Kiro/Gemini에 스킬 배포
├── skillscan.py        # 보안 스캐너 (14개 패턴, 4개 카테고리)
├── logger.py           # 로깅 시스템
├── version_manager.py  # 백업 및 롤백
├── registry.json       # 로컬 폴백 레지스트리
├── settings.json       # 사용자 설정 (프록시 등) — 자동 생성
├── skills.db           # SQLite 데이터베이스 — 자동 생성
├── installed_skills/   # 설치된 스킬 + 매니페스트
├── logs/               # 작업 로그
└── backups/            # 스킬 버전 백업
```

## 커스텀 레지스트리

`registry.json`을 편집하거나 `skill_core.py`의 `REMOTE_REGISTRIES`를 자체 레지스트리 URL로 지정.

## 라이선스

MIT