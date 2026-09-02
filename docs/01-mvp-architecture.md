# ReliefCheck MVP 아키텍처

## 현재 기준

기획서의 핵심 정의는 NFC 재고관리기가 아니라 재난대피소 현장에서 가구와 물품을 분리 인식하고 지급 가능 여부를 판정하는 임베디드 단말이다. 1차 MVP는 실물 장치가 없어도 로컬에서 검증 가능해야 하며, Raspberry Pi 5로 옮길 때 장치 어댑터만 교체할 수 있어야 한다.

## 레이어

| 레이어 | 구현 위치 | 역할 |
|---|---|---|
| UI/API | `reliefcheck/main.py`, `reliefcheck/ui/` | 터치 화면, 상태 표시, 스캔 입력, 관리자 확인 |
| Session | `reliefcheck/core/session.py` | 현재 가구, 물품, 판정 결과, 화면 상태 |
| Policy | `reliefcheck/policy/rule_engine.py` | 지급 한도, 중복, 재고, 카메라 일치 여부 판정 |
| Service | `reliefcheck/services/distribution.py` | NFC 입력부터 DB COMMIT, 출력까지의 업무 흐름 |
| Storage | `reliefcheck/storage/database.py` | SQLite 스키마, 샘플 데이터, 거래 조회 |
| Device | `reliefcheck/devices/` | 현재는 화면 출력 프린터, 이후 실제 장치 어댑터 추가 |

## MVP 상태 흐름

```text
WAIT_HOUSEHOLD
  -> WAIT_ITEM
  -> POLICY_VALIDATION
  -> RESULT_UI
  -> WAIT_HOUSEHOLD
```

거래 확정 시에는 DB 기록과 재고/물품 상태 갱신을 먼저 완료한 뒤 출력 상태만 별도로 갱신한다. 이 구조는 프린터가 실패해도 같은 지급 거래가 중복 생성되지 않도록 하기 위한 것이다.

## 실제 장치 연결 예정 지점

| 장치 | 현재 상태 | 다음 파일 |
|---|---|---|
| ACR1252U NFC 2대 | UI 버튼으로 UID 입력 시뮬레이션 | `reliefcheck/devices/nfc_acr1252u.py` |
| ZTP-80USL2 감열프린터 | 텍스트 영수증 파일 생성 | `reliefcheck/devices/printer_escpos.py` 또는 CUPS 어댑터 |
| Camera Module 3 | `vision_verified` 플래그로 시뮬레이션 | `reliefcheck/vision/item_verification.py` |
| PIR/음성/LED | 아직 미구현 | GPIO/USB 장치 테스트 후 추가 |

## 제작 우선순위

1. 현재 MVP를 Raspberry Pi에서 그대로 실행한다.
2. NFC 리더 2대를 PC/SC로 구분해서 UID를 읽는다.
3. 실제 프린터에서 샘플 확인증을 출력한다.
4. 카메라 검증은 ArUco/QR로 시작하고, AI 분류는 확장 기능으로 분리한다.
5. 실측 치수표를 만든 뒤 CAD와 함체 출력을 진행한다.
