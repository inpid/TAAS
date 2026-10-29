# TAAS 실시간 경고 모듈 (이지스터 1.8)

로스팅 노트(knowledge/)의 규칙 중 **실시간 경고 4종**을 파이썬 코드로 옮긴 것. 외부 라이브러리 없이 돌아감.

| 경고 | 언제 뜨나 | 근거 노트 |
|---|---|---|
| 하강 중 감압 / 큰 폭 감압 | RoR이 아직 꺼지는 중에 화력을 내릴 때, 한 번에 너무 많이 내릴 때 | 11·39 |
| 수분 와장창 | TP 후 ET RoR이 갑자기 바닥 → "손대지 말고 대기", 회복되면 해제 | 51 |
| 1차 후보 / 깊은 히트 배리어 | 190~206℃에서 BT RoR이 꺾이면 1차 후보, 너무 깊으면 크래시 경고 | 43·12 |
| Aero Accel 단계 제안 | 투입 최저 → ET TP 1단계 → BT 140~150℃ 2단계 → 1차 임박 3단계 | 37·50 |

## 폴더
```
taas_rules/engine.py    경고 엔진
taas_rules/config.json  숫자 기준 (여기만 고치면 됨, 각 항목에 근거 노트 적혀 있음)
taas_rules/replay.py    저장된 로그 CSV를 다시 돌려 경고 확인
tests/                  가상 로스팅으로 만든 테스트 8개
knowledge/              로스팅 노트 53개 + 규칙 모음 (근거 자료)
```

## 딘 TAAS 프로젝트에 넣기 (Claude Code)
1. 이 zip을 풀어서 `taas_rules`, `tests`, `knowledge` 폴더를 TAAS 프로젝트 폴더에 복사
2. 프로젝트의 `CLAUDE.md` 끝에 아래 붙여넣기
```
## 로스팅 지식·경고 모듈
- 실시간 경고는 taas_rules/engine.py 의 RoastEngine 을 쓴다. 숫자 기준은 taas_rules/config.json 에서만 바꾼다
- 새 규칙이 필요하면 knowledge/01_TAAS_프로그램규칙_모음.md 를 보고 engine.py 에 감지기를 추가하고 tests/ 에 테스트도 추가한다
- 출처가 다르면: 이지스터 1.8 실전 기록(23·47·49·50·52번) > 같은 저자 최신 글 > 일반론
- 이지스터 1.8: 화력 mmAq, 배기 = 댐퍼 10 개방 + 팬 다이얼
```
3. Claude Code에 이렇게 말하기
```
taas_rules 모듈을 지금 프로그램에 연결해줘.
온도를 읽을 때마다 RoastEngine.update(Sample(...)) 를 부르고,
돌려받은 경고를 화면에 띄워줘. 경고(빨강)·제안(노랑)·정보(회색)로 색 구분.
화력을 바꾸기 전엔 check_gas_cut(새 화력값) 으로 먼저 확인하게 해줘.
```

## 직접 써보기
```python
from taas_rules import RoastEngine, Sample
eng = RoastEngine()
# 투입 순간부터 1~2초마다
for a in eng.update(Sample(t=경과초, bt=원두온도, et=환경온도, gas=화력, exhaust=배기, drum=rpm)):
    print(a)        # 예: [10:06] 정보 · 1차 후보 (히트 배리어) BT 199.8℃ ...
```
지난 로그 확인: `python -m taas_rules.replay 로그.csv` (열 이름 time, bt, et, gas, exhaust, drum)
테스트: `python -m pytest tests`

## 주의
- 숫자 기준은 **주성현 이지스터 1.8 기록 기반 출발값**. 딘 머신(프로브 위치·굵기)으로 첫 배치들을 돌려보고 config.json을 맞출 것
- 테스트는 가상 곡선이라, 실제 로그로 replay 해보고 너무 자주/늦게 뜨는 경고가 있으면 해당 숫자 조정
- 1차 감지는 감압 직후 35초 동안은 꺼둠 (감압 때문에 RoR이 꺼지는 걸 1차로 착각하지 않게)
