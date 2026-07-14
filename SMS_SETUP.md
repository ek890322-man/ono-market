# ONO MARKET 문자 알림 설정

Render > ono-market > Environment에 다음 값을 추가합니다.

- SOLAPI_API_KEY
- SOLAPI_API_SECRET
- SOLAPI_SENDER_NUMBER : SOLAPI에 등록/인증된 발신번호, 숫자만
- ADMIN_PHONE : 새 주문 알림을 받을 관리자 휴대폰 번호, 숫자만

동작:
1. 고객 주문 접수 완료 -> 고객 휴대폰 주문 접수 문자
2. 새 주문 접수 -> 관리자 휴대폰 문자
3. 관리자가 주문 상태 변경 -> 고객 휴대폰 상태 변경 문자

SOLAPI 값이 없거나 문자 발송이 실패해도 주문 DB 저장은 정상 유지됩니다.
