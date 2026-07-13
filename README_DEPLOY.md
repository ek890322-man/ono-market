# ONO MARKET 배포 오류 수정판

수정 내용
- site_settings 테이블 자동 생성 누락 수정
- 기존 shop.db가 있어도 서버 시작 시 site_settings 자동 추가
- DATA_DIR 환경변수 지원

로컬 실행
1. 기존 CMD Ctrl+C
2. 이 ZIP을 새 폴더에 압축 해제
3. start.bat 실행
4. http://127.0.0.1:5000 접속

기존 데이터가 필요 없다면 이전 폴더의 shop.db는 복사하지 마세요.
