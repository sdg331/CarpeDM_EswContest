# Raspberry Pi 배포 및 자동 실행

## 1. 복사 위치

권장 위치는 다음과 같다.

```bash
/home/pi/reliefcheck
```

## 2. 기본 준비

```bash
cd /home/pi/reliefcheck
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

실제 NFC, ESC/POS, QR 카메라 기능까지 설치할 때:

```bash
python -m pip install -e ".[pi]"
```

## 3. 환경 설정

```bash
cp .env.example .env
```

처음에는 안전하게 다음 설정으로 시작한다.

```text
RELIEFCHECK_HOST=127.0.0.1
RELIEFCHECK_PRINTER=screen
RELIEFCHECK_NFC_MODE=manual
RELIEFCHECK_VISION_MODE=simulated
```

Raspberry Pi 터치 화면에서만 사용할 때는 `127.0.0.1`로 충분하다. 같은 Wi-Fi의 휴대폰이나 노트북에서 접속해야 하면 `RELIEFCHECK_HOST=0.0.0.0`으로 바꾸고, `RELIEFCHECK_ADMIN_TOKEN`을 반드시 설정한다.

## 4. 수동 실행 확인

```bash
source .venv/bin/activate
python -m reliefcheck.main --reset-seed
```

확인:

```bash
curl http://127.0.0.1:8008/health
```

## 5. systemd 등록

```bash
mkdir -p /home/pi/reliefcheck/logs
chmod +x /home/pi/reliefcheck/deploy/start-reliefcheck.sh
sudo cp /home/pi/reliefcheck/deploy/reliefcheck.service /etc/systemd/system/reliefcheck.service
sudo systemctl daemon-reload
sudo systemctl enable reliefcheck
sudo systemctl start reliefcheck
```

상태 확인:

```bash
systemctl status reliefcheck
journalctl -u reliefcheck -n 100 --no-pager
curl http://127.0.0.1:8008/health
```

## 6. 키오스크 브라우저 실행

Chromium이 설치되어 있다면 데스크톱 자동 시작에 다음 명령을 연결한다.

```bash
chromium-browser --kiosk --disable-infobars http://127.0.0.1:8008
```

## 7. 실제 장치 전환 순서

1. `RELIEFCHECK_PRINTER=screen` 상태에서 Pi 웹앱 먼저 확인
2. NFC 2대 인식 후 `RELIEFCHECK_NFC_MODE=acr1252u` 전환
3. 프린터 샘플 출력 확인 후 `RELIEFCHECK_PRINTER=cups` 또는 `escpos` 전환
4. QR 카메라 촬영이 안정화된 뒤 `RELIEFCHECK_VISION_MODE=qr-camera` 전환

각 단계마다 `/health`에서 장치 상태가 `ok: true`인지 확인한다.
