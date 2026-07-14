# Cloudinary 연결 방법

Render > ono-market 서비스 > Environment에서 아래 3개 환경변수를 추가하세요.

- CLOUDINARY_CLOUD_NAME
- CLOUDINARY_API_KEY
- CLOUDINARY_API_SECRET

값은 Cloudinary Console의 API Keys / Product Environment Credentials에서 확인합니다.

환경변수 저장 후 Render를 재배포하세요.

이 버전의 상품 대표/상세 이미지는 Cloudinary에 저장됩니다.
기존 로컬 업로드 이미지는 자동 이전되지 않습니다. 기존 상품 이미지는 관리자에서 다시 업로드하세요.
