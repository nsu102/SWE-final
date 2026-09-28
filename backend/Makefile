.PHONY: db-up db-down db-logs db-shell db-reset db-status seed-musinsa seed-musinsa-plan seed-dump

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

# 크롤러 결과 중 DB에 없는 상품만 임베딩합니다. SEED_LIMIT=N이면 DB 총개수 N까지만.
seed-musinsa: db-up
	bash scripts/seed_musinsa.sh

seed-musinsa-plan: db-up
	SEED_DRY_RUN=1 bash scripts/seed_musinsa.sh

# 현재 DB 전체를 seed/catalog-*.sql.gz로 덤프합니다 (새 볼륨의 초기 데이터).
seed-dump: db-up
	bash scripts/dump_seed.sh
