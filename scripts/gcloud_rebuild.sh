#!/usr/bin/env bash
# 무신사 상품 사진 재선별(대표 썸네일 + 상단 캐러셀 중 사람 없는 상의 사진만)을 GCE GPU VM에서
# 백그라운드로 돌립니다. VM은 끝나면(성공/실패 모두) selections.jsonl 등을
# s3://$AWS_BUCKET_NAME/rebuild/latest/ 에 올리고 스스로 삭제됩니다. 12시간을 넘기면 GCE가 강제 삭제합니다.
set -euo pipefail
export PATH="$HOME/google-cloud-sdk/bin:$PATH"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
name="${VM_NAME:-lookfind-rebuild}"
zone="${ZONE:-asia-northeast3-b}"  # Seoul: close to Musinsa and the S3 bucket (ap-northeast-2)
machine="${MACHINE:-n1-standard-8}"
gpu="${GPU:-nvidia-tesla-t4}"
image_family="${IMAGE_FAMILY:-common-cu129-ubuntu-2204-nvidia-580}"  # Deep Learning VM, driver preinstalled
ssh_vm() { gcloud compute ssh "$name" --zone "$zone" --quiet --command "$1"; }

# The VM clones origin/main, so local code must already be pushed.
if [[ -n "$(git status --porcelain -- backend crawler scripts Makefile)" ]]; then
  echo "commit and push your changes first (the VM clones origin/main)" >&2; exit 1
fi
git fetch -q origin main
if [[ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]]; then
  echo "push first: HEAD is not origin/main" >&2; exit 1
fi

gcloud compute instances create "$name" --zone "$zone" \
  --machine-type "$machine" --accelerator "type=$gpu,count=1" --maintenance-policy TERMINATE \
  --image-family "$image_family" --image-project deeplearning-platform-release \
  --boot-disk-size 100GB --scopes cloud-platform \
  --max-run-duration 12h --instance-termination-action DELETE

echo "waiting for SSH..."
until ssh_vm true 2>/dev/null; do sleep 10; done
ssh_vm "git clone -q $(git remote get-url origin) SWE-final && mkdir -p SWE-final/crawler/data/musinsa/tops/selected"
# Secrets travel over SSH only and disappear with the VM.
gcloud compute scp --zone "$zone" --quiet crawler/.env "$name:SWE-final/crawler/.env"
# Resume from what has already been selected locally or by a previous VM run.
selections=crawler/data/musinsa/tops/selected/selections.jsonl
if [[ -f "$selections" ]]; then
  gcloud compute scp --zone "$zone" --quiet "$selections" "$name:SWE-final/$selections"
fi
ssh_vm "cd SWE-final && nohup bash scripts/vm_rebuild.sh > rebuild.log 2>&1 < /dev/null &"

echo "started on $name ($zone). The VM deletes itself when done."
echo "progress: gcloud compute ssh $name --zone $zone --command 'tail -f SWE-final/rebuild.log'"
