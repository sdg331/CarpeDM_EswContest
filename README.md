# ReliefCheck

재난대피소 및 임시 구호시설에서 수혜 가구와 구호물자를 분리 인식하고, 로컬 정책 엔진과 SQLite 거래 기록으로 중복 지급을 차단하는 Offline-first 임베디드 시스템 MVP입니다.

## 현재 구현 범위

- 듀얼 NFC 역할 분리 시뮬레이션: 가구 리더 / 물품 리더
- SQLite 로컬 DB: 가구, 물품, 재고, 정책, 거래, 장치 로그
- 정책 엔진: 지급 한도, 동일 물품 재처리, 재고 부족, 카메라 불일치
- 거래 무결성: DB COMMIT 후 출력 상태 갱신
- 거래 감사 추적: 정책 버전, 판정 체크리스트, 입력 컨텍스트, 감사 해시 저장
- 운영 리스크 점수화: 재고 소진, 거절률, 중복 시도, 출력 실패를 운영 대시보드에서 통합 판단
- 프린터 백엔드: 개발용 화면 파일, CUPS, ESC/POS USB 어댑터
- NFC 백엔드: 개발용 수동 입력, ACR1252U/PCSC 어댑터
- 카메라 백엔드: 개발용 시뮬레이션, OpenCV QR 교차검증 어댑터
- 터치 키오스크용 로컬 웹 UI
- 대상 시연용 운영 콘솔: 현장 지급, 운영 대시보드, 정책 판정, 장치 진단, SW 검증, 실험 결과 탭
- NFC 등록 모드: 실제 카드/태그 UID를 기존 가구와 물품에 현장에서 매핑
- 판정 근거 노출: 가구 상태, 물품 상태, 재고, 정책 한도, 중복 이력, 카메라 검증 체크리스트
- SW Evidence Mode: 실장비 미연동 상황에서도 핵심 정책, 예외, 장애 격리를 자동 시나리오로 검증

## 실행 방법

Python 표준 라이브러리만 사용합니다.

```bash
cd /Users/do_not_delay/Desktop/CarpeDM_EswContest
python -m reliefcheck.main --reset-seed
```

브라우저에서 접속:

```text
http://127.0.0.1:8008
```

DB만 초기화:

```bash
python -m reliefcheck.main --init-only --reset-seed
```

흐름 시뮬레이션:

```bash
python scripts/simulate_flow.py
```

테스트:

```bash
python -m unittest discover -s tests
```

실험표 생성:

```bash
python scripts/generate_experiment_report.py
```

소프트웨어 검증 증거 생성:

```bash
python scripts/run_sw_evidence_suite.py
```

하드웨어 사전 점검:

```bash
python scripts/hardware_preflight.py
```

NFC 등록 모드:

1. 웹 UI의 `NFC 등록` 탭을 연다.
2. 등록 종류와 대상을 선택한다.
3. 실제 리더가 연결되어 있으면 `왼쪽 리더 읽기` 또는 `오른쪽 리더 읽기`로 UID를 읽는다.
4. 리더 연결 전이면 UID를 직접 입력하고 `UID 저장`을 누른다.
5. 저장 후 `현장 지급` 탭에서 같은 태그로 지급 흐름을 확인한다.

## 주요 파일

| 경로 | 역할 |
|---|---|
| `reliefcheck/main.py` | 로컬 HTTP 서버와 API |
| `reliefcheck/ui/` | 키오스크 화면 |
| `reliefcheck/storage/database.py` | SQLite 스키마와 샘플 데이터 |
| `reliefcheck/policy/rule_engine.py` | 지급 정책 판정 |
| `reliefcheck/services/distribution.py` | 스캔부터 거래 확정, 출력까지 연결 |
| `reliefcheck/services/ops.py` | 운영 지표, 정책 매트릭스, 장치 진단, 실험 지표 API 데이터 |
| `reliefcheck/services/evidence.py` | SW Evidence Mode, 자동 검증 시나리오, 준비도 계산 |
| `reliefcheck/devices/printer.py` | 프린터 어댑터 |
| `reliefcheck/devices/nfc_acr1252u.py` | ACR1252U/PCSC NFC 어댑터 |
| `reliefcheck/vision/item_verification.py` | QR 카메라 검증 어댑터 |
| `scripts/hardware_preflight.py` | Pi, USB, PC/SC, 프린터, 카메라 사전 진단 |
| `reliefcheck/config/` | 시연용 정책과 샘플 데이터 |
| `docs/` | 아키텍처, 하드웨어 bring-up, 시험 계획 |
| `docs/08-hardware-bringup-session.md` | 실제 장비 연결 단계별 진행표 |
| `docs/04-ui-design-application.md` | Apple 레퍼런스 디자인 적용 기준 |
| `docs/07-competition-readiness.md` | 대상급 시연 완성도 점검표 |
| `reports/sw-evidence-summary.md` | 실장비 미연동 시 소프트웨어 검증 증거 |
| `deploy/reliefcheck.service` | Raspberry Pi systemd 자동 실행 서비스 |

## 다음 개발 단계

1. Raspberry Pi 5에서 현재 MVP 실행
2. ACR1252U 2대 PC/SC reader name 확정
3. ZTP-80USL2 프린터 CUPS 또는 ESC/POS 실제 출력 검증
4. Camera Module 3 QR 검증 촬영 안정화
5. PIR, 음성 안내, LED 상태 표시 추가
6. 실측 기반 2D 배치도와 CAD 제작
