.PHONY: db-up db-down db-logs db-shell db-reset db-status seed-musinsa seed-musinsa-plan

db-up:
	docker compose up -d --wait postgres

db-down:
	docker compose down

db-logs:
	docker compose logs -f postgres

db-shell:
	docker compose exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

db-status:
	docker compose ps postgres

# 로컬 DB 데이터를 모두 지우고 스키마를 처음부터 다시 만듭니다.
db-reset:
	docker compose down -v
	docker compose up -d --wait postgres

# 목표 개수는 기존 DB 행을 포함합니다. 재실행하면 이미 적재한 상품을 건너뜁니다.
seed-musinsa: db-up
	SEED_LIMIT=$${SEED_LIMIT:-900} bash scripts/seed_musinsa.sh

seed-musinsa-plan: db-up
	SEED_LIMIT=$${SEED_LIMIT:-900} SEED_DRY_RUN=1 bash scripts/seed_musinsa.sh
