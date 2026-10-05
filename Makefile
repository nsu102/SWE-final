PYTHON ?= python3
VENV := backend/work/.venv/bin

.PHONY: setup db backend frontend test rebuild-catalog deploy

# 백엔드 venv(크롤러도 같이 사용), 프런트 의존성, 로컬 .env 준비
setup:
	$(PYTHON) -m venv backend/work/.venv
	$(VENV)/pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
	$(VENV)/pip install -r backend/requirements-backend.txt -r backend/requirements-ml.txt -r backend/requirements-aws.txt
	cp -n backend/.env.example backend/.env || true
	cp -n frontend/.env.example frontend/.env.local || true
	cd frontend && npm install

# pgvector DB (새 볼륨이면 시드 900개 자동 적재)
db:
	$(MAKE) -C backend db-up

backend:
	cd backend && set -a && . ./.env && set +a && work/.venv/bin/uvicorn src.backend.app:app --host 127.0.0.1 --port 8000 --reload

frontend:
	cd frontend && npm run dev

test:
	cd backend && work/.venv/bin/python -m unittest discover -s tests
	cd crawler && ../$(VENV)/python -m unittest discover -s tests
	cd frontend && npm run lint && npm run build

# AWS 배포 (backend/.env.production 기준). 부분 배포: scripts/deploy.sh env|backend|frontend|check
deploy:
	bash scripts/deploy.sh

# 사람 없는 사진으로 무신사 재선별 → 재임베딩 (로컬, 재실행 시 이어서)
rebuild-catalog:
	caffeinate -i bash scripts/rebuild_catalog.sh  # keep the Mac awake for the long run
