# TAAS 작업 규칙 (Claude Code용)

딘(커피 로스터, 이지스터 1.8 사용)이 만드는 로스팅 프로그램. 답은 한국어로, 쉬운 말로.

## 구조
- `app/` 로컬 서버(파이썬 기본 라이브러리만) + 브라우저 화면(`app/static/index.html`, 외부 CDN 없음 — 매장 노트북이 오프라인일 수 있음)
- `app/sources.py` 입력 장치. 실제 로스터 연결은 `HardwareRoaster`에 구현하고 `SimulatedRoaster`와 같은 메서드(tick/read/charge/drop/set_controls)를 지킬 것
- `taas_rules/engine.py` 경고 엔진. 숫자는 하드코딩하지 말고 `taas_rules/config.json`에 넣고 근거 노트 번호를 `_note`에 적을 것
- `knowledge/` 로스팅 노트. 새 규칙은 `knowledge/01_TAAS_프로그램규칙_모음.md`를 보고 만들고, 근거는 `knowledge/index.json`으로 노트를 찾아 확인
- `docs/ROADMAP.md` 기능 계획. 기능을 끝내면 ⬜ → ✅로 바꿀 것

## 로스팅 판단 원칙
- 출처가 다르면: 이지스터 1.8 실전 기록(23·47·49·50·52번) > 같은 저자 최신 글 > 일반론(라오 등)
- 이지스터 1.8 단위: 화력 mmAq, 배기 = 댐퍼 10 개방 + 팬 다이얼(50번), 운용 500g~2kg(49번)
- 경고는 '조작 보류'와 '다음 배치 처방'을 구분 (예: 수분 와장창 → 지금은 손대지 말고, 다음 배치 투입온도↑)
- 시간표 기반 제안 금지. 신호(RoR 저점·반등·정체, ET TP, 히트 배리어) 기반으로만 (11·21·39번)

## 작업할 때
- 바꾸면 `python -m pytest tests` 통과 확인
- 화면을 바꾸면 `python -m app.server --speed 10`으로 한 배치 돌려볼 것
- `batches/`의 JSON은 딘의 실제 기록이니 지우거나 고치지 말 것
