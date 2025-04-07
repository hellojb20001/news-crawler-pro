# 신문 기사 수집기 pro

한국의 주요 신문사들의 기사를 한눈에 모아보는 웹 애플리케이션입니다.

## 주요 기능

- 경제 신문, 종합일간지, 석간 신문 그룹별 기사 수집
- 전체 기사 또는 1면 기사만 선택적 수집
- 실시간 크롤링 상태 확인
- 수집된 기사 복사 및 저장 기능
- 사용자 친화적인 웹 인터페이스

## 설치 방법

1. 저장소 클론
```bash
git clone https://github.com/yourusername/news-crawler-pro.git
cd news-crawler-pro
```

2. 가상환경 생성 및 활성화
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. 필요한 패키지 설치
```bash
pip install -r requirements.txt
```

4. Chrome WebDriver 설치
- Chrome 브라우저가 설치되어 있어야 합니다.
- WebDriver는 자동으로 설치됩니다.

## 실행 방법

```bash
python app.py
```

웹 브라우저에서 `http://localhost:5000`으로 접속하면 애플리케이션을 사용할 수 있습니다.

## 사용 방법

1. 신문사 그룹 선택
   - 경제 신문
   - 종합일간지(조간)
   - 석간 신문

2. 수집 범위 선택
   - 전체 기사
   - 1면 기사만

3. 크롤링 시작 버튼 클릭

4. 결과 확인
   - 수집된 기사 목록 확인
   - 복사 또는 저장 기능 사용

## 기술 스택

- Python 3.8+
- Flask
- Selenium
- Bootstrap 5
- JavaScript

## 라이선스

MIT License

## 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request 