# ReliefCheck 하드웨어 연결 세션

이 문서는 장비를 한 번에 모두 연결하지 않고, 원인을 분리하면서 확인하기 위한 진행표다.

## 0. 시작 원칙

- 한 번에 하나의 장치만 실제 모드로 바꾼다.
- 각 단계는 `/health`와 `scripts/hardware_preflight.py` 결과를 남긴 뒤 다음 단계로 넘어간다.
- 실장비 성능 수치는 측정 전까지 발표나 문서에 확정값으로 쓰지 않는다.

## 1. 라즈베리파이 기본 실행

목표: 장치 없이도 Pi에서 웹앱이 안정적으로 뜨는지 확인한다.

```bash
cd /home/pi/reliefcheck
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m reliefcheck.main --reset-seed
```

확인:

```bash
curl http://127.0.0.1:8008/health
python scripts/hardware_preflight.py
```

완료 기준:

- 브라우저에서 `http://127.0.0.1:8008` 접속 가능
- `/health`의 database가 정상
- 프린터, NFC, 카메라는 아직 manual/screen/simulated여도 정상

## 2. NFC 리더 1대 확인

목표: ACR1252U가 OS와 PC/SC에서 보이는지 확인한다.

```bash
python -m pip install -e ".[pi]"
lsusb
python scripts/hardware_preflight.py
```

완료 기준:

- USB 목록에 NFC 리더가 보인다.
- PC/SC 리더 목록에 reader name이 1개 이상 나온다.

## 3. NFC 리더 2대 역할 분리

목표: 왼쪽 리더를 가구 카드, 오른쪽 리더를 물품 태그로 분리한다.

`.env` 예시:

```text
RELIEFCHECK_NFC_MODE=acr1252u
RELIEFCHECK_NFC_HOUSEHOLD_READER=<왼쪽 리더 이름>
RELIEFCHECK_NFC_ITEM_READER=<오른쪽 리더 이름>
RELIEFCHECK_PRINTER=screen
RELIEFCHECK_VISION_MODE=simulated
```

확인:

```bash
python scripts/hardware_preflight.py
python -m reliefcheck.main --reset-seed
curl -X POST http://127.0.0.1:8008/api/nfc/read-once \
  -H 'Content-Type: application/json' \
  -d '{"reader":"household"}'
```

완료 기준:

- 가구 리더에서 가구 카드 UID를 읽는다.
- 물품 리더에서 물품 태그 UID를 읽는다.
- 반대 리더에 태그하면 `R001`이 표시된다.

## 3-1. NFC 등록 모드

목표: 실제 카드와 물품 태그의 UID를 기존 시연 데이터에 매핑한다.

웹 UI:

1. `NFC 등록` 탭을 연다.
2. `가구 카드` 또는 `물품 태그`를 선택한다.
3. 등록 대상을 선택한다.
4. 실제 리더가 연결되어 있으면 `왼쪽 리더 읽기` 또는 `오른쪽 리더 읽기`를 누른다.
5. UID가 들어오면 `UID 저장`을 누른다.
6. `현장 지급` 탭에서 방금 등록한 태그로 지급 흐름을 확인한다.

API 확인:

```bash
curl -X POST http://127.0.0.1:8008/api/nfc/read-raw \
  -H 'Content-Type: application/json' \
  -d '{"reader":"household"}'

curl -X POST http://127.0.0.1:8008/api/register-tag \
  -H 'Content-Type: application/json' \
  -d '{"target_type":"household","target_id":"HH-001","uid":"실제로_읽힌_UID"}'
```

주의:

- 같은 UID를 다른 가구나 물품에 중복 등록하면 거절된다.
- `--reset-seed` 또는 샘플 초기화 버튼을 누르면 등록값이 샘플 UID로 돌아간다.
- 실장비가 아직 불안정하면 UID를 직접 입력해 등록 흐름만 먼저 시연한다.

## 4. 프린터 연결

목표: 승인 거래 후 출력 상태가 `PRINTED` 또는 `FAILED`로 분리되는지 확인한다.

처음에는 CUPS 방식부터 권장한다.

`.env` 예시:

```text
RELIEFCHECK_PRINTER=cups
RELIEFCHECK_CUPS_PRINTER=<프린터 이름>
```

확인:

```bash
lpstat -p
python scripts/hardware_preflight.py
python -m reliefcheck.main --reset-seed
```

완료 기준:

- 승인 거래 후 확인증이 출력된다.
- 프린터를 빼거나 꺼도 거래는 남고 `print_status=FAILED`가 기록된다.
- 같은 거래번호로 재출력이 가능하다.

## 5. 카메라 확인

목표: AI 분류가 아니라 QR/시각 코드 교차검증부터 안정화한다.

`.env` 예시:

```text
RELIEFCHECK_VISION_MODE=qr-camera
RELIEFCHECK_CAMERA_INDEX=0
```

확인:

```bash
python scripts/hardware_preflight.py --camera-probe
```

완료 기준:

- 프레임 1장 캡처가 성공한다.
- 물품 코드가 예상 코드와 다르면 `V001`로 지급 전 차단된다.

## 6. 통합 시연 순서

1. 샘플 데이터 초기화
2. 가구 카드 태그
3. 물품 태그 태그
4. 정책 승인과 확인증 출력
5. 같은 물품 재태그로 중복 차단
6. 반대 리더 태그로 오인식 차단
7. 프린터 실패 후 거래 보존 확인
8. 운영 대시보드에서 감사 해시와 리스크 확인

## 7. 기록해야 할 실측값

| 항목 | 목표 | 기록 위치 |
|---|---:|---|
| NFC 연속 인식 | 100회 | 실험 결과 보고서 |
| 평균 판정 시간 | 1초 이내 | 시연 영상 또는 로그 |
| 프린터 출력 | 30회 | 실험 결과 보고서 |
| 프린터 실패 격리 | 5회 | 거래 감사 로그 |
| 재부팅 후 거래 보존 | 10회 | SQLite 원장 캡처 |
| 카메라 코드 확인 | 30회 | V001/OK 비교 로그 |
