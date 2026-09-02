# ReliefCheck 하드웨어 Bring-up 체크리스트

## 1. Raspberry Pi 5 기본 확인

```bash
python3 --version
lsusb
vcgencmd measure_temp
```

완료 기준:

- 10.1인치 터치 디스플레이에서 브라우저가 열린다.
- USB 허브 연결 후 NFC 리더 2대와 프린터가 동시에 인식된다.
- 30분 구동 후 Pi 온도와 팬 동작을 확인한다.

## 2. ACR1252U NFC 리더

확인할 것:

- `lsusb`에서 동일 모델 2대가 모두 보이는지
- PC/SC 서비스에서 reader name이 2개로 분리되는지
- 왼쪽 리더는 가구 카드만, 오른쪽 리더는 물품 태그만 허용되는지

설정 예시:

```text
RELIEFCHECK_NFC_MODE=acr1252u
RELIEFCHECK_NFC_HOUSEHOLD_READER=<왼쪽 리더 이름>
RELIEFCHECK_NFC_ITEM_READER=<오른쪽 리더 이름>
```

실제 읽기 API:

```bash
curl -X POST http://127.0.0.1:8008/api/nfc/read-once \
  -H 'Content-Type: application/json' \
  -d '{"reader":"household"}'
```

MVP 완료 기준:

- 등록 가구 카드 인식
- 등록 물품 태그 인식
- 가구/물품 리더 교차 입력 시 `R001` 표시
- 미등록 UID 입력 시 `H001` 또는 `I001` 표시

## 3. 감열프린터

확인할 것:

- 전원 어댑터 전압/극성
- USB 연결 방식
- CUPS 또는 ESC/POS 직접 출력 중 안정적인 방식
- 용지 없음, 커버 열림, USB 분리 상황에서 앱이 멈추지 않는지

CUPS 설정 예시:

```text
RELIEFCHECK_PRINTER=cups
RELIEFCHECK_CUPS_PRINTER=<CUPS 프린터 이름>
```

ESC/POS USB 설정 예시:

```text
RELIEFCHECK_PRINTER=escpos
RELIEFCHECK_ESCPOS_VENDOR=0x0000
RELIEFCHECK_ESCPOS_PRODUCT=0x0000
```

`0x0000` 값은 실제 `lsusb` 결과의 vendor/product ID로 교체한다.

MVP 완료 기준:

- 거래번호, 가구번호, 물품, 결과, 처리시각이 포함된 확인증 출력
- 프린터 실패 시 DB 거래는 유지되고 `print_status=FAILED`로 남음
- 같은 거래번호로 재출력 가능

## 4. Camera Module 3

초기 구현은 AI 분류가 아니라 ArUco/QR 교차검증으로 시작한다.

설정 예시:

```text
RELIEFCHECK_VISION_MODE=qr-camera
RELIEFCHECK_CAMERA_INDEX=0
```

완료 기준:

- 촬영 영역 조명 반사가 적다.
- 물품 태그의 논리 ID와 카메라가 읽은 시각 ID가 일치한다.
- 불일치 시 `V001`로 승인 전 차단된다.

## 5. 함체 제작 전 실측

CAD 전 반드시 측정:

- 디스플레이 전체 크기, 화면 영역, 고정홀, HDMI/USB 케이블 방향
- 프린터 본체 크기, 배출구, 커버 열림 반경, 전원/USB 방향
- NFC 리더 케이블 포함 점유 공간과 인식 위치
- Pi 5 팬 포함 높이와 모든 케이블 체결 후 외곽
- PowerConf S3 실제 배치 방향과 음향 그릴 위치

폼보드 또는 종이 목업으로 손 접근, 용지 교체, 화면 터치 흔들림을 먼저 확인한 뒤 PLA 출력에 들어간다.

## 6. 상태 확인 기준

장치 전환 후에는 항상 다음 API를 먼저 확인한다.

```bash
curl http://127.0.0.1:8008/health
```

`devices.nfc`, `devices.printer`, `devices.camera`가 각각 `ok: true`인지 확인한 뒤 시연 테스트로 넘어간다.
