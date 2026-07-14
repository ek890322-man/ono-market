# PostgreSQL 운영 버전

구조:
- 코드: GitHub
- 이미지: Cloudinary
- 회원/주문/상품/설정: PostgreSQL

Render Blueprint를 다시 Sync/Deploy하면 `ono-market-db` PostgreSQL과
`DATABASE_URL` 연결 설정을 사용하도록 구성되어 있습니다.

주의:
- 기존 SQLite `shop.db` 데이터는 자동 이전되지 않습니다.
- `shop.db`는 GitHub에 올리지 마세요.
- 기존 상품은 PostgreSQL이 비어 있으면 기본 샘플 상품으로 시작합니다.
