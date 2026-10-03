# SWE Backend

상의 사진에서 옷 영역을 추출하고 Marqo FashionSigLIP 임베딩으로 유사 상품을 검색하는 백엔드입니다. 상품 원본은 로컬 또는 S3에 둘 수 있고, 상품 정보와 768차원 벡터는 PostgreSQL + pgvector에 저장합니다.

## 구성

```text
src/backend/              FastAPI, ML 추론, PostgreSQL, 이미지 URL
src/jobs/index_catalog.py 크롤링 결과 임베딩 및 DB 적재
src/common/               사람/상의 파싱 공통 코드
deploy/backend/           EC2 + RDS 배포 파일
tests/                    단위 테스트
```

## 로컬 실행

Python 3.12 기준입니다.

```bash
python3 -m venv work/.venv
work/.venv/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
work/.venv/bin/pip install -r requirements-backend.txt -r requirements-ml.txt -r requirements-aws.txt
cp .env.example .env
make db-up
```

로컬 DB는 `pgvector/pgvector:pg16` 컨테이너로 실행되며 `127.0.0.1:5432`에서만 접근할 수 있습니다. 최초 볼륨 생성 시 아래 순서로 자동 초기화됩니다.

1. `src/backend/schema.sql`: `vector` 확장, 상품·검색 이력 테이블, HNSW 인덱스 생성
2. `seed/catalog-*.sql.gz`: S3에 올라간 무신사 상품 전체(49,705개)와 FashionSigLIP 임베딩 적재 (`scripts/load_seed.sh`)

따라서 새로 clone한 환경에서는 `make db-up`만 실행해도 전체 카탈로그가 DB에 들어갑니다. 첫 기동은 HNSW 인덱스 생성 때문에 몇 분 걸리며, 적재가 끝나야 healthy가 됩니다. 압축 시드에는 상품 메타데이터, S3 object key, 768차원 임베딩(소수 4자리 반올림, 검색 순위 영향 없음)만 있으며 이미지와 AWS 인증정보는 포함되지 않습니다.

```bash
make db-status # 상태 확인
make db-shell  # psql 접속
make db-logs   # DB 로그
make db-down   # 컨테이너 중지, 데이터 볼륨 유지
make db-reset  # 데이터 볼륨 삭제 후 완전 초기화
```

Docker 초기화 스크립트는 빈 데이터 볼륨에서만 실행됩니다. 기존 볼륨에 GitHub 시드를 다시 적용하려면 `make db-reset`을 사용해야 하며, 이 명령은 기존 로컬 DB 데이터를 모두 삭제합니다.

기본 로컬 접속 정보는 다음과 같습니다.

```text
host: 127.0.0.1
port: 5432
database: fashion
user: fashion
password: fashion
DATABASE_URL: postgresql://fashion:fashion@localhost:5432/fashion
```

포트나 계정을 바꾸려면 `.env`의 `POSTGRES_*`와 `DATABASE_URL`을 함께 변경해야 합니다. 이 값은 로컬 개발 전용이며 운영 DB 비밀번호로 재사용하면 안 됩니다.

`.env`를 현재 셸에 적용한 뒤 API를 실행합니다.

```bash
set -a
source .env
set +a
work/.venv/bin/uvicorn src.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

- API 문서: `http://127.0.0.1:8000/docs`
- 생존 확인: `GET /health/live`
- DB 포함 상태 확인: `GET /health`
- 이미지 검색: `POST /api/search?limit=20&platform=musinsa`
- 상품 이미지: `GET /media/{platform}/{goods_no}`

### 회원·검색 기록·찜 API

로그인하면 HttpOnly 쿠키 `lookfind_session`(SameSite=Lax, `FRONTEND_URL`이 https면 Secure)이 설정됩니다. 브라우저는 프런트엔드의 Next.js 프록시(`/api/*`, `/media/*`)를 통해 같은 출처로 호출하므로 CORS·토큰 저장이 필요 없습니다. 비밀번호는 표준 라이브러리 scrypt 해시로, 세션은 토큰의 SHA-256만 `sessions` 테이블에 저장합니다(30일 만료). 만료된 쿠키로 검색하면 비로그인 검색으로 처리됩니다. 같은 이메일+IP로 비밀번호를 5번 틀리면 10분간 429로 막히고(IP당 30회), 재설정 요청은 IP당 시간당 5회입니다. 카운터는 프로세스 메모리에 있어 워커 1개 기준이며, 배포 nginx에도 `/api/auth/` 분당 10회 제한이 있습니다. 재설정 메일은 `SMTP_*` 환경변수로 보내고, `SMTP_HOST`가 비어 있으면 링크를 백엔드 로그(WARNING)에 출력합니다.

카카오 로그인은 `KAKAO_REST_API_KEY`(필요하면 `KAKAO_CLIENT_SECRET`)를 설정하고 Kakao Developers에 Redirect URI `KAKAO_REDIRECT_URI`(기본 `{FRONTEND_URL}/api/auth/kakao/callback`)를 등록합니다. 카카오 계정은 `users.kakao_id`로 구분하고 닉네임·프로필 사진을 저장합니다. 카카오가 검증한 이메일이 기존 이메일 계정과 같으면 그 계정에 연결합니다.

로그인한 상태의 `POST /api/search`는 `search_events`(썸네일 포함)와 `search_results`에 저장되어 ARCHIVE가 됩니다. 삭제는 숨김 처리라 10분 안에는 되돌릴 수 있고, 그 뒤 다음 삭제 요청 때 계정에서 완전히 분리됩니다.

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| POST | `/api/auth/register`, `/api/auth/login` | `{email, password}` → 세션 쿠키 + `{id, email, display_name, avatar_url}` |
| GET | `/api/auth/kakao`, `/api/auth/kakao/callback` | 카카오 OAuth 시작 / 콜백 (성공 시 쿠키 설정 후 프런트로, 실패 시 `/?login_error=kakao`) |
| POST | `/api/auth/logout` | 세션 삭제, 쿠키 제거 |
| POST | `/api/auth/reset-request` | `{email}` → 재설정 링크 발송 (가입 여부와 무관하게 항상 204) |
| POST | `/api/auth/reset` | `{token, password}` → 비밀번호 변경, 기존 세션 전부 로그아웃, 새 세션 쿠키 발급 |
| GET | `/api/auth/me` | 현재 계정 |
| GET | `/api/history?before={cursor}` | 검색 기록 24개씩 `{items, next_cursor}` |
| GET | `/api/history/{id}` | 해당 검색 기록 + 결과 상품 |
| DELETE | `/api/history/{id}`, `/api/history` | 한 건 / 전체 삭제 → `{deleted_ids}` |
| POST | `/api/history/restore` | `{ids}` → 10분 안에 삭제한 기록 복원 `{restored}` |
| GET | `/api/favorites` | 찜 목록 |
| PUT, DELETE | `/api/favorites/{platform}/{goods_no}` | 찜 추가 / 해제 |

## 크롤링 결과 적재

크롤러 저장소가 만든 `products.csv`와 `selected/selections.jsonl`을 명시적으로 전달합니다. `selections.jsonl`에 `s3_bucket`과 `s3_key`가 있으면 S3에서 직접 이미지를 읽고, 로컬 파일만 있으면 `storage/`에 복사합니다.

```bash
work/.venv/bin/python -m src.jobs.index_catalog \
  --platform musinsa \
  --products ../crawler/data/musinsa/tops/products.csv \
  --selections ../crawler/data/musinsa/tops/selected/selections.jsonl \
  --limit 5
```

`--limit`을 제거하면 선택 완료 상품 전체를 upsert합니다. EC2에서는 access key를 파일에 넣지 말고 S3 읽기 권한이 있는 IAM Role을 인스턴스에 연결하는 방식을 권장합니다.

### 신규 상품 적재와 시드 갱신

크롤러가 새로 선별한 상품 중 DB에 없는 것만 임베딩합니다. 크롤러 결과(`../crawler/data`, 없으면 `data/` 스냅샷)와 S3 이미지를 자동으로 찾아 사용하며, 이미 DB에 있는 상품은 임베딩을 다시 계산하지 않습니다. 중간에 중단되어도 같은 명령을 다시 실행하면 남은 상품부터 이어집니다.

```bash
# 다운로드·임베딩 없이 대상 개수만 확인
make seed-musinsa-plan

# DB 시작 → S3 이미지 로딩 → 임베딩 → pgvector 적재
make seed-musinsa
```

크롤러 저장소를 자동으로 찾지 못하면 경로를 지정합니다. 목표 개수와 배치 크기도 변경할 수 있습니다.

```bash
CRAWLER_ROOT=/absolute/path/to/crawler make seed-musinsa
SEED_LIMIT=60000 SEED_BATCH_SIZE=16 make seed-musinsa   # DB 총개수 상한
```

실행 계획은 `available`, `existing`, `to_index`, `target` 순서로 출력됩니다. 적재 후 `make seed-dump`로 시드 파일을 다시 만들어 커밋하면 팀원도 `make db-reset`으로 같은 카탈로그를 받습니다.

## EC2/RDS 배포

`deploy/backend/env.example`을 `deploy/backend/.env`로 복사하고 RDS 주소, 프런트엔드 도메인, S3 버킷을 입력합니다. RDS는 PostgreSQL 16과 pgvector 확장을 사용할 수 있어야 합니다.

```bash
cd deploy/backend
./deploy.sh
```

Nginx는 외부 요청을 API 컨테이너로 전달하고, API 컨테이너는 `127.0.0.1:8000`에만 노출됩니다. 상세 보안 그룹과 IAM 예시는 `deploy/backend/` 파일을 참고하세요.

## 주요 환경변수

| 이름 | 용도 |
| --- | --- |
| `DATABASE_URL` | PostgreSQL/RDS 접속 문자열 |
| `AUTO_MIGRATE` | 시작 시 스키마 생성 여부 |
| `AWS_BUCKET_NAME` | 상품 이미지 S3 버킷 |
| `AWS_REGION` | S3 리전 |
| `LOCAL_STORAGE_ROOT` | 로컬 상품 이미지 루트 |
| `CORS_ORIGINS` | 브라우저가 백엔드를 직접 호출할 때만 필요한 origin 목록 (Next.js 프록시 사용 시 불필요) |
| `FRONTEND_URL` | 프런트엔드 주소 (재설정 메일 링크, 카카오 Redirect URI, 쿠키 Secure 여부) |
| `KAKAO_REST_API_KEY`, `KAKAO_CLIENT_SECRET`, `KAKAO_REDIRECT_URI` | 카카오 로그인 REST API 키 / Client Secret(선택) / Redirect URI(선택) |
| `MAX_UPLOAD_MB` | 검색 사진 최대 크기 |

`AUTO_MIGRATE=false`인 운영 DB에는 배포 후 `python -m src.backend.migrate`로 새 테이블(`users`, `sessions`, `password_resets`, `search_results`, `favorites`)을 만듭니다.

실제 `.env`, 인증서, 모델 캐시, 로컬 저장 이미지는 Git에 포함되지 않습니다.
