# ReliefCheck SW Evidence Suite

- 생성 시각: 2026-09-02T22:36:18+09:00
- 모드: SW Evidence Mode
- 경계: manual/screen/simulated 어댑터 기준이며 물리 장치 신뢰성 수치는 주장하지 않음

## 요약

| 항목 | 값 |
|---|---:|
| 전체 케이스 | 10 |
| 통과 | 10 |
| 실패 | 0 |
| 생성 거래 | 7 |
| 승인 | 4 |
| 거절 | 3 |
| 출력 실패 격리 | 1 |

## 시나리오 결과

| ID | 시나리오 | 기대 | 실제 | 결과 |
|---|---|---|---|---|
| APPROVE | 정상 지급 승인 | APPROVED / OK | APPROVED / OK / PRINTED | PASS |
| DUPLICATE_ITEM | 동일 물품 재태그 차단 | REJECTED / D002 | REJECTED / D002 / NOT_REQUIRED | PASS |
| WATER_LIMIT_APPROVE_1 | 개인 단위 생수 1차 승인 | APPROVED / OK | APPROVED / OK / PRINTED | PASS |
| WATER_LIMIT_APPROVE_2 | 개인 단위 생수 2차 승인 | APPROVED / OK | APPROVED / OK / PRINTED | PASS |
| HOUSEHOLD_LIMIT | 가구별 한도 초과 차단 | REJECTED / D001 | REJECTED / D001 / NOT_REQUIRED | PASS |
| VISION_MISMATCH | 카메라 불일치 차단 | REJECTED / V001 | REJECTED / V001 / NOT_REQUIRED | PASS |
| WRONG_READER | 잘못된 리더 입력 차단 | REJECTED / R001 | REJECTED / R001 / NOT_REQUIRED | PASS |
| UNKNOWN_HOUSEHOLD | 미등록 가구 차단 | REJECTED / H001 | REJECTED / H001 / NOT_REQUIRED | PASS |
| UNKNOWN_ITEM | 미등록 물품 차단 | REJECTED / I001 | REJECTED / I001 / NOT_REQUIRED | PASS |
| PRINT_FAILURE | 프린터 실패 격리 | APPROVED / OK | APPROVED / OK / FAILED | PASS |

## 판정 코드 커버리지

| 코드 | 건수 |
|---|---:|
| D001 | 1 |
| D002 | 1 |
| OK | 4 |
| V001 | 1 |

## 해석

- 이 결과는 물리 장치 성능이 아니라, 실장비 연동 전 소프트웨어 로직과 실패 격리 설계의 재현성 증거다.
- 정상 승인, 중복 물품, 가구 한도, 카메라 불일치, 리더 오인식, 미등록 UID, 출력 실패를 같은 코드 경로로 검증한다.
- 실장비 복귀 후에는 같은 시나리오를 ACR1252U, 실제 프린터, Camera Module 3 입력으로 반복 측정하면 된다.
