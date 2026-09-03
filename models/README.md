# ReliefCheck 3D Model

이 폴더는 ReliefCheck 1차 하드웨어 형상 자료를 모아둔 곳입니다.

## 파일

| 파일 | 용도 |
|---|---|
| `reliefcheck-kiosk-v1.stl` | GitHub에서 바로 볼 수 있는 1차 3D 모델 |
| `reliefcheck-kiosk-v1.scad` | OpenSCAD에서 수정 가능한 파라메트릭 원본 |
| `reliefcheck-kiosk-v1.json` | 치수와 부품 배치 메타데이터 |

## 형상 의도

- 중앙: Raspberry Pi 기반 로컬 키오스크 함체
- 상단: 10.1인치급 터치 화면
- 좌측 패드: 가구 카드 NFC 리더
- 우측 패드: 물품 태그 NFC 리더
- 전면: 80mm 영수증 프린터 배출구
- 상단 후면: Camera Module 3 위치
- 후면: Raspberry Pi 서비스 커버와 케이블 출구

## 치수 기준

단위는 mm입니다. 하부 받침 footprint는 약 `460(W) x 340(D)`이고, 출력 용지와 후면 케이블 출구까지 포함한 1차 envelope는 약 `460(W) x 422(D) x 497(H)`입니다.

이 모델은 실측 전 1차 형상입니다. 실제 제작 전에는 장비 실측, 체결부, 방열구, 케이블 반경, 프린터 용지 교체 공간을 반영해야 합니다.

## STL 재생성

```bash
python scripts/export_kiosk_model.py
```
