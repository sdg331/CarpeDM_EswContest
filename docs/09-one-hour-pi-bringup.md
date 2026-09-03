# ReliefCheck 1시간 하드웨어 연결 우선순위

목표는 완성형 통합이 아니라, 1시간 안에 시연 가능한 최소 실장비 증거를 확보하는 것이다.

## 0. 시간 배분

| 시간 | 목표 | 성공 기준 |
|---|---|---|
| 0~10분 | Pi 부팅/네트워크 | 터미널 사용 가능 |
| 10~25분 | 프로젝트 실행 | `http://127.0.0.1:8008` 접속 |
| 25~40분 | NFC 리더 확인/등록 | PC/SC reader name 확인, 등록 탭에서 UID 저장 |
| 40~55분 | 프린터 확인 | CUPS 프린터 이름 확인 또는 screen fallback |
| 55~60분 | 증거 캡처 | `/health`, 대시보드, 장치 사진 |

카메라는 시간이 남을 때만 진행한다.

## 1. Pi에서 기본 패키지 설치

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git curl usbutils pcscd pcsc-tools swig libpcsclite-dev cups
sudo systemctl enable --now pcscd
sudo systemctl enable --now cups
```

## 2. 프로젝트 위치

프로젝트를 Pi에 복사한 뒤 다음 위치에 둔다.

```bash
mkdir -p ~/reliefcheck
cd ~/reliefcheck
```

## 3. 앱 먼저 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m reliefcheck.main --reset-seed
```

확인:

```bash
curl http://127.0.0.1:8008/health
```

## 4. NFC만 먼저 실제 연결

새 터미널에서:

```bash
source ~/reliefcheck/.venv/bin/activate
python -m pip install pyscard
lsusb
pcsc_scan
```

`pcsc_scan`에 리더 이름이 2개 보이면 그 이름을 기록한다.

`.env`:

```text
RELIEFCHECK_NFC_MODE=acr1252u
RELIEFCHECK_NFC_HOUSEHOLD_READER=<왼쪽 리더 이름>
RELIEFCHECK_NFC_ITEM_READER=<오른쪽 리더 이름>
RELIEFCHECK_PRINTER=screen
RELIEFCHECK_VISION_MODE=simulated
```

서버 재실행:

```bash
source ~/reliefcheck/.venv/bin/activate
python -m reliefcheck.main --reset-seed
```

NFC 확인:

```bash
curl -X POST http://127.0.0.1:8008/api/nfc/read-raw \
  -H 'Content-Type: application/json' \
  -d '{"reader":"household"}'
```

웹에서 등록:

1. 브라우저에서 `NFC 등록` 탭을 연다.
2. `가구 카드`와 `HH-001`을 선택한다.
3. `왼쪽 리더 읽기`를 누르거나 방금 읽힌 UID를 직접 입력한다.
4. `UID 저장`을 누른다.
5. 같은 방식으로 `물품 태그`와 `ITEM-RICE-001`을 등록한다.
6. `현장 지급` 탭으로 돌아가 실제 태그 순서대로 시연한다.

## 5. 프린터는 CUPS 우선

```bash
lpstat -p
```

프린터 이름이 보이면 `.env`에 추가한다.

```text
RELIEFCHECK_PRINTER=cups
RELIEFCHECK_CUPS_PRINTER=<프린터 이름>
```

프린터 이름이 안 보이면 오늘은 `RELIEFCHECK_PRINTER=screen`으로 유지하고, 화면 저장 확인증을 시연한다.

## 6. 마지막 진단

```bash
source ~/reliefcheck/.venv/bin/activate
python scripts/hardware_preflight.py
```

## 7. 1시간 안에 꼭 남길 증거

- Pi 화면에서 ReliefCheck 웹앱 실행 사진
- USB에 NFC 리더/프린터가 연결된 사진
- `python scripts/hardware_preflight.py` 출력
- `/health` 화면 또는 터미널 출력
- NFC reader name 2개
- 프린터가 안 되면 `screen` 출력 fallback이 동작하는 장면
