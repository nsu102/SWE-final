# Find the top — 상의 유사 상품 검색

전신 사진을 올리거나 MacBook 카메라로 바로 찍으면 사람 파싱 모델로 상의 영역을 분리하고, Marqo FashionSigLIP 임베딩과 pgvector 유사도 검색으로 비슷한 무신사 상품을 찾아주는 서비스입니다.

```text
crawler/   무신사·에이블리 상품 수집 → 상의 이미지 선별 → S3 업로드 (products.csv, selections.jsonl)
backend/   카탈로그 임베딩 적재(index_catalog) + FastAPI 검색 API + PostgreSQL/pgvector
frontend/  Next.js 웹 — 사진 업로드/카메라 촬영, 상의 크롭 미리보기, 유사 상품 결과
```

```text
[crawler] ──CSV/JSONL──▶ [backend index_catalog] ──768d 벡터──▶ [PostgreSQL + pgvector]
    │                                                                  ▲
    └──이미지──▶ [S3] ◀──presigned URL── [FastAPI /api/search] ─────────┘
                                                ▲
                                   [Next.js frontend] (브라우저에서 직접 호출, CORS)
```

## 빠른 시작

Docker, Python 3.12+, Node 20+가 필요합니다.

```bash
make setup      # 백엔드 venv, 프런트 npm install, .env 템플릿 복사
make db         # pgvector 컨테이너 기동 (빈 볼륨이면 전체 카탈로그 49,705개 자동 적재, 첫 기동 몇 분)
make backend    # http://127.0.0.1:8000  (API 문서: /docs)
make frontend   # http://localhost:3000  (다른 터미널에서)
```

상품 이미지는 비공개 S3 버킷에 있으므로 `backend/.env`에 S3 읽기 권한이 있는 AWS 자격증명을 넣어야 결과 이미지가 보입니다. 첫 검색은 모델(사람 파서 + FashionSigLIP)을 내려받고 로딩하느라 수십 초가 걸리고, 이후 검색은 1초 이내입니다.

## 테스트

```bash
make test       # 백엔드·크롤러 unittest, 프런트 lint + build
```

## 카탈로그 확장

크롤러로 상품을 더 모은 뒤 백엔드에서 임베딩을 적재합니다. 자세한 옵션은 각 README를 참고하세요.

```bash
(cd crawler && ../backend/work/.venv/bin/python -m src.musinsa.crawl_products --max-products 1000)
(cd crawler && ../backend/work/.venv/bin/python -m src.musinsa.select_images)
(cd backend && make seed-musinsa && make seed-dump)   # 신규 상품 임베딩 → 시드 갱신
```

## 배포

- 백엔드: `backend/deploy/backend/` — EC2(Docker + Nginx) + RDS(PostgreSQL 16 + pgvector), S3는 IAM Role로 접근
- 프런트엔드: Vercel 등 — 빌드 전에 `NEXT_PUBLIC_API_URL`을 백엔드 도메인으로, 백엔드 `CORS_ORIGINS`에 프런트 도메인 추가

## 저장소 이력

세 저장소를 커밋 이력을 유지한 채(`git subtree`) 합쳤습니다.

| 디렉터리 | 원본 |
| --- | --- |
| `backend/` | [nsu102/SWE-backend](https://github.com/nsu102/SWE-backend) |
| `crawler/` | [nsu102/SWE-crawl](https://github.com/nsu102/SWE-crawl) |
| `frontend/` | [lahee3423/SWE-frontend](https://github.com/lahee3423/SWE-frontend) |
