#!/usr/bin/env bash
# Runs ON the GCE VM started by scripts/gcloud_rebuild.sh (do not run locally).
# Person-free image selection (thumbnail + top carousel only) for every Musinsa product, then
# uploads the results to s3://$AWS_BUCKET_NAME/rebuild/latest/ and deletes this VM, whether it
# succeeded or not (a partial run resumes on the next launch). Embedding happens afterwards.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
export PATH="$root/backend/work/.venv/bin:$PATH"

upload_results() {
  set +e
  python - <<'EOF'
import os
from pathlib import Path
import boto3
for line in Path("crawler/.env").read_text().splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())
s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION"))
bucket, prefix = os.environ["AWS_BUCKET_NAME"], "rebuild/latest"
for path in ["crawler/data/musinsa/tops/selected/selections.jsonl",
             "crawler/data/musinsa/tops/selected/errors.jsonl",
             "crawler/logs/select.log", "rebuild.log"]:
    if Path(path).exists():
        s3.upload_file(path, bucket, f"{prefix}/{Path(path).name}")
        print("uploaded", path, flush=True)
EOF
}

finish() {
  status=$?
  echo "exit status $status; uploading results to S3 and deleting this VM"
  upload_results
  name="$(curl -s -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/name)"
  zone="$(curl -s -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/zone | awk -F/ '{print $NF}')"
  gcloud compute instances delete "$name" --zone "$zone" --quiet
}
echo "== setup $(date)"
# A fresh VM may still be running apt at boot; wait for its lock instead of failing.
sudo apt-get -o DPkg::Lock::Timeout=600 update -q >/dev/null
sudo apt-get -o DPkg::Lock::Timeout=600 install -y -q python3-venv python3-pip >/dev/null
python3 -m venv backend/work/.venv
pip install -q torch torchvision
pip install -q -r crawler/requirements-ml.txt -r crawler/requirements-aws.txt
python -c "import torch; print('cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
# Only from here on does the VM upload results and delete itself on exit. If setup fails, the VM
# stays up for inspection (gcloud's 12h max-run-duration still deletes it).
trap finish EXIT

echo "== select $(date)"
SELECT_ONLY=1 WORKERS="${WORKERS:-10}" bash scripts/rebuild_catalog.sh
echo "== done $(date)"
