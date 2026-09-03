# ReliefCheck

재난 대피소에서 구호물자가 **누구에게, 어떤 기준으로, 몇 번 지급됐는지** 현장에서 바로 확인하기 위한 오프라인 우선 지급 단말입니다.

ReliefCheck는 Raspberry Pi에서 로컬 웹 콘솔과 SQLite 원장을 실행하고, 가구 카드와 물품 태그를 분리 인식한 뒤 정책 엔진으로 지급 가능 여부를 판정합니다. 네트워크가 불안정한 상황에서도 지급 기록이 남고, 프린터나 카메라 같은 주변 장치는 어댑터 방식으로 단계적으로 연결할 수 있게 구성했습니다.

## 문제 정의

재난 대피소나 임시 구호시설에서는 짧은 시간 안에 많은 사람에게 물품을 지급해야 합니다. 현장에서 수기 명단이나 단순 체크 방식만 사용하면 다음 문제가 생길 수 있습니다.

- 같은 가구가 같은 물품을 다시 받는 중복 지급
- 물품 재고와 실제 지급 기록의 불일치
- 담당자 교대 후 지급 기준을 설명하기 어려운 상황
- 프린터, 네트워크, 카메라 장애가 지급 기록까지 흔드는 문제

ReliefCheck는 물품을 더 많이 나눠주는 시스템이 아니라, 제한된 구호물자가 **공정하게 지급되고 사후에 설명 가능한 기록으로 남도록** 돕는 시스템입니다.

## 시연 흐름

1. 왼쪽 NFC 리더에서 가구 카드를 인식합니다.
2. 오른쪽 NFC 리더에서 물품 태그를 인식합니다.
3. 로컬 정책 엔진이 가구 상태, 물품 상태, 재고, 지급 한도, 카메라 일치 여부를 확인합니다.
4. 승인되면 SQLite 원장에 거래를 먼저 저장하고 지급확인증을 출력합니다.
5. 거절되면 `D001`, `D002`, `R001`, `H001`, `I001`, `V001` 같은 판정 코드와 체크리스트를 남깁니다.
6. 운영 대시보드에서 승인/거절, 재고 압박도, 장치 상태, 감사 해시를 확인합니다.

## 현재 구현 상태

| 구분 | 구현 내용 |
|---|---|
| 실행 환경 | Python 표준 라이브러리 기반 로컬 HTTP 서버 |
| 화면 | 터치 키오스크용 HTML/CSS/JS 콘솔 |
| 저장소 | SQLite, WAL 모드, 가구/물품/정책/거래/장치 로그 |
| 정책 판정 | 지급 한도, 동일 물품 재처리, 재고 부족, 카메라 불일치 차단 |
| 감사 추적 | 정책 버전, 판정 체크리스트, 입력 컨텍스트, 거래 감사 해시 저장 |
| NFC | 수동 입력 모드, ACR1252U/PCSC 리더 어댑터, 웹 등록 모드 |
| 프린터 | 화면 파일 저장, CUPS, ESC/POS USB 백엔드 |
| 카메라 | 시뮬레이션 모드, OpenCV QR 교차검증 어댑터 |
| 검증 | 단위 테스트, SW Evidence Suite, 실험 리포트 생성 |

## 화면 구성

- `현장 지급`: 가구 인증, 물품 인증, 정책 판정, 지급 결과를 한 화면에서 진행합니다.
- `NFC 등록`: 실제 카드/태그 UID를 기존 가구와 물품에 매핑합니다.
- `운영 대시보드`: 거래 수, 승인/거절, 중복 차단, 재고 압박도, 감사 로그를 봅니다.
- `정책 판정`: 마지막 거래의 체크리스트와 입력값을 확인합니다.
- `장치 진단`: NFC, 프린터, 카메라, SQLite 상태를 분리해서 표시합니다.
- `검증 기록`: 실장비 없이도 정책/예외/장애 처리를 재현한 SW 검증 결과를 보여줍니다.
- `실험 결과`: 반복 시험과 결선 시연 흐름을 정리합니다.

## 시스템 구조

```text
Browser / Touch UI
        |
        v
ReliefCheck HTTP API
        |
        v
Distribution Service
        |
        +-- Policy Engine
        +-- SQLite Ledger
        +-- NFC Adapter
        +-- Printer Adapter
        +-- Vision Adapter
```

핵심 원칙은 거래 기록을 먼저 확정한 뒤 출력 상태를 별도로 갱신하는 것입니다. 프린터 출력이 실패해도 승인 거래는 원장에 남기 때문에 같은 물품이 중복 지급되는 상황을 줄일 수 있습니다.

## 1차 3D 모델링

실장비 배치 설명을 위해 1차 키오스크 형상 모델을 함께 제공합니다. 현재 모델은 제작 확정 도면이 아니라, 터치 화면, 듀얼 NFC 리더, 영수증 프린터, 카메라, Raspberry Pi 서비스 영역의 위치 관계를 보여주는 개념 모델입니다.

| 파일 | 용도 |
|---|---|
| `models/reliefcheck-kiosk-v1.stl` | GitHub에서 바로 볼 수 있는 3D 미리보기용 모델 |
| `models/reliefcheck-kiosk-v1.scad` | OpenSCAD에서 수정 가능한 원본 모델 |
| `models/reliefcheck-kiosk-v1.json` | 치수와 부품 배치 메타데이터 |
| `docs/10-3d-model-v1.md` | 모델링 의도, 가정 치수, 후속 제작 체크포인트 |

하부 받침 footprint는 약 `460(W) x 340(D)`이고, 출력 용지와 후면 케이블 출구까지 포함한 1차 envelope는 약 `460(W) x 422(D) x 497(H)`입니다. 실제 제작 전에는 장비 실측, 체결부, 방열구, 케이블 반경, 프린터 용지 교체 공간을 다시 반영해야 합니다.

```bash
python scripts/export_kiosk_model.py
```

## 빠른 실행

```bash
git clone https://github.com/sdg331/CarpeDM_EswContest.git
cd CarpeDM_EswContest

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

python -m reliefcheck.main --host 0.0.0.0 --reset-seed
```

브라우저에서 접속합니다.

```text
http://127.0.0.1:8008
```

같은 네트워크의 다른 기기에서 접속할 때는 실행 장치의 IP를 사용합니다.

```text
http://<Raspberry-Pi-IP>:8008
```

## Raspberry Pi 장비 준비

실제 NFC 리더, 프린터, 카메라를 붙일 때는 선택 의존성을 설치합니다.

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git curl usbutils pcscd pcsc-tools swig libpcsclite-dev cups
sudo systemctl enable --now pcscd
sudo systemctl enable --now cups

source .venv/bin/activate
python -m pip install -e ".[pi]"
```

장치 상태를 확인합니다.

```bash
python scripts/hardware_preflight.py
curl http://127.0.0.1:8008/health
```

## NFC 등록 모드

실제 태그 UID가 샘플 UID와 다르면 먼저 웹에서 등록해야 합니다.

1. 웹 UI에서 `NFC 등록` 탭을 엽니다.
2. `가구 카드` 또는 `물품 태그`를 선택합니다.
3. 등록할 가구 또는 물품을 선택합니다.
4. 실제 리더가 연결되어 있으면 `왼쪽 리더 읽기` 또는 `오른쪽 리더 읽기`를 누릅니다.
5. 리더가 아직 불안정하면 UID를 직접 입력합니다.
6. `UID 저장`을 누른 뒤 `현장 지급` 탭에서 같은 태그로 확인합니다.

주의: `--reset-seed` 또는 `샘플 초기화`를 실행하면 등록한 UID가 기본 샘플값으로 돌아갑니다. 시연 직전에는 UID 등록 후 초기화하지 않는 것이 좋습니다.

## 주요 명령

```bash
# 서버 실행
python -m reliefcheck.main --host 0.0.0.0 --reset-seed

# DB만 초기화
python -m reliefcheck.main --init-only --reset-seed

# 기본 흐름 시뮬레이션
python scripts/simulate_flow.py

# 실험 리포트 생성
python scripts/generate_experiment_report.py

# 소프트웨어 검증 증거 생성
python scripts/run_sw_evidence_suite.py

# 테스트
python -m pytest
python -m unittest discover -s tests
```

## 검증 결과

현재 저장소 기준으로 다음 항목을 검증합니다.

- 정상 지급 승인
- 동일 물품 재태그 차단
- 가구별 지급 한도 초과 차단
- 잘못된 리더 입력 차단
- 미등록 가구/물품 UID 차단
- 카메라 불일치 차단
- 프린터 실패 시 거래 보존
- 공개 API에서 내부 파일 경로 제거
- NFC UID 등록과 중복 UID 방지
- SW Evidence Suite 결과 생성

검증 결과는 `reports/sw-evidence-summary.md`, `reports/sw-evidence-latest.json`, `reports/experiment-summary.md`에 남습니다.

## 실장비 확인 범위

현재 코드는 실장비가 없어도 정책 판정과 거래 기록을 검증할 수 있게 만들어져 있습니다. 다만 NFC 반복 인식률, 프린터 연속 출력 성공률, 카메라 인식률 같은 물리 성능 수치는 실제 Raspberry Pi와 장비 연결 후 별도로 측정해야 합니다.

| 장치 | 현재 소프트웨어 상태 | 실장비 연결 시 확인할 것 |
|---|---|---|
| NFC 리더 | ACR1252U/PCSC UID 읽기 어댑터 구현 | 리더 2대 이름 고정, 100회 반복 인식 |
| 감열 프린터 | CUPS/ESC-POS 출력 어댑터 구현 | 승인 거래 출력, 실패 후 재출력 |
| 카메라 | QR 교차검증 어댑터 구현 | 조명 변화, 거리 변화, 오인식 차단 |
| Raspberry Pi | 로컬 실행 구조 준비 | 부팅 후 자동 실행, 전원 재인가 복구 |

## 주요 파일

| 경로 | 역할 |
|---|---|
| `reliefcheck/main.py` | 로컬 HTTP 서버와 API |
| `reliefcheck/ui/` | 키오스크 웹 화면 |
| `reliefcheck/storage/database.py` | SQLite 스키마, 샘플 데이터, 조회 함수 |
| `reliefcheck/policy/rule_engine.py` | 지급 가능 여부를 판단하는 정책 엔진 |
| `reliefcheck/services/distribution.py` | 스캔, 판정, 거래 저장, 출력 연결 |
| `reliefcheck/services/ops.py` | 운영 대시보드와 장치 진단 데이터 |
| `reliefcheck/services/evidence.py` | SW Evidence Suite와 준비도 계산 |
| `reliefcheck/devices/nfc_acr1252u.py` | ACR1252U/PCSC NFC 어댑터 |
| `reliefcheck/devices/printer.py` | 화면 파일, CUPS, ESC/POS 프린터 어댑터 |
| `reliefcheck/vision/item_verification.py` | QR 기반 물품 교차검증 어댑터 |
| `scripts/hardware_preflight.py` | Pi, USB, PC/SC, 프린터, 카메라 사전 점검 |
| `scripts/export_kiosk_model.py` | 1차 STL 모델 재생성 |
| `models/` | STL, OpenSCAD, 모델 메타데이터 |
| `docs/10-3d-model-v1.md` | 1차 3D 모델링 메모 |
| `docs/08-hardware-bringup-session.md` | 실제 장비 연결 단계별 진행표 |
| `docs/09-one-hour-pi-bringup.md` | 제한 시간 내 시연 준비 절차 |
| `deploy/reliefcheck.service` | Raspberry Pi systemd 자동 실행 예시 |

## 다음 단계

1. Raspberry Pi에서 최신 코드를 실행하고 `NFC 등록` 탭까지 확인합니다.
2. ACR1252U 2대의 PC/SC reader name을 고정합니다.
3. 실제 카드와 물품 태그 UID를 등록합니다.
4. 프린터를 CUPS 또는 ESC/POS 방식으로 연결합니다.
5. 실제 장비 치수를 3D 모델에 반영합니다.
6. 장비별 반복 측정 결과를 `reports/`에 추가합니다.
