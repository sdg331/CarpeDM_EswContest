# ReliefCheck 1차 3D 모델링 메모

## 목적

1차 모델은 제작 확정 도면이 아니라, 심사위원과 팀원이 ReliefCheck의 물리 구성을 빠르게 이해하기 위한 형상 자료다. 현재 소프트웨어 흐름인 `가구 카드 인식 -> 물품 태그 인식 -> 정책 판정 -> 지급확인증 출력 -> 운영 기록`이 실제 장치 배치로 어떻게 이어지는지 보여주는 데 집중했다.

## 모델 구성

| 위치 | 구성 요소 | 역할 |
|---|---|---|
| 상단 전면 | 터치 화면 | 현장 지급, NFC 등록, 운영 대시보드 표시 |
| 좌측 상판 | 가구 NFC 리더 | 수혜 가구 카드 UID 인식 |
| 우측 상판 | 물품 NFC 리더 | 개별 구호물자 태그 UID 인식 |
| 전면 중앙 | 80mm 영수증 프린터 | 승인 거래 지급확인증 출력 |
| 상단 후면 | Camera Module 3 | 물품 QR/시각 코드 교차검증 |
| 후면 | Raspberry Pi 서비스 커버 | 전원, USB, LAN, 유지보수 접근 |
| 하부 | 받침대 | 터치 조작 중 흔들림 완화 |

## 가정 치수

| 항목 | 치수 |
|---|---:|
| 하부 받침 폭 | 460 mm |
| 하부 받침 깊이 | 340 mm |
| 전체 envelope 폭 | 460 mm |
| 전체 envelope 깊이 | 422 mm |
| 전체 envelope 높이 | 497 mm |
| NFC 리더 패드 | 126 x 92 mm |
| 화면 프레임 | 290 x 185 mm |
| 프린터 모듈 영역 | 170 x 54 x 76 mm |
| 출력 용지 폭 | 140 mm 표현 |

## 산출물

- `models/reliefcheck-kiosk-v1.stl`: GitHub 3D 미리보기용 STL
- `models/reliefcheck-kiosk-v1.scad`: OpenSCAD 수정용 원본
- `models/reliefcheck-kiosk-v1.json`: 치수/부품 배치 데이터
- `scripts/export_kiosk_model.py`: JSON 기준 STL 재생성 스크립트

## 후속 제작 시 보강할 점

- 실제 터치 디스플레이 베젤 외경과 VESA/브라켓 위치
- ACR1252U 리더 2대의 케이블 방향과 고정 방식
- 80mm 프린터 용지 교체 공간과 전면 배출 각도
- Raspberry Pi 방열구, 전원 스위치, USB/LAN 접근 위치
- 카메라 시야각과 조명 반사 영향
- 하부 무게 중심, 미끄럼 방지 패드, 전도 방지 구조
