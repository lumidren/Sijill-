#!/usr/bin/env bash
# PDPL-Ready AWS lab: create the test stack, scan it with Prowler, import the result, tear it down.
#
# Run this yourself, against an AWS account you own. It never asks for or stores credentials:
# it uses whatever the AWS CLI and Prowler already pick up (AWS_PROFILE, SSO, environment).
# For the scan, a role with the AWS-managed SecurityAudit and ViewOnlyAccess policies is enough.
#
#   ./lab.sh up        create the deliberately misconfigured stack (needs CloudFormation rights)
#   ./lab.sh scan      run Prowler on the checks PDPL-Ready maps, write JSON-OCSF to ./out
#   ./lab.sh import    load the newest scan into PDPL-Ready (run from the repo, server stopped or not)
#   ./lab.sh down      delete the stack
#
# Environment: AWS_PROFILE / AWS_REGION as usual; LAB_NAME (default pdpl-ready-lab);
# PDPL_ORG (organisation id to import into; default: the collector organisation).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
LAB_NAME="${LAB_NAME:-pdpl-ready-lab}"
STACK="$LAB_NAME"
OUT="$HERE/out"
REGION="${AWS_REGION:-$(aws configure get region 2>/dev/null || echo eu-central-1)}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1 ($2)" >&2; exit 2; }; }

whoami_aws() {
  need aws "install the AWS CLI v2"
  local id
  id="$(aws sts get-caller-identity --query Account --output text)"
  echo "AWS account $id, region $REGION"
  read -r -p "Is this an account you own and may scan? [y/N] " ok
  [[ "$ok" == "y" || "$ok" == "Y" ]] || { echo "stopped"; exit 1; }
}

case "${1:-}" in
  up)
    whoami_aws
    aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \
      --template-file "$HERE/lab-stack.yaml" --parameter-overrides "LabName=$LAB_NAME" \
      --tags purpose=pdpl-ready-test-lab
    aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" --query "Stacks[0].Outputs" --output table
    ;;
  scan)
    whoami_aws
    need prowler "pip install prowler (in its own virtualenv)"
    need python3 "used to read the mapping file"
    checks="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); print(' '.join(sorted({c for r in d['Requirements'] for c in r['Checks']})))" \
      "$REPO/compliance/prowler/pdpl_egypt_aws.json")"
    mkdir -p "$OUT"
    # Prowler exits non-zero when it finds failures; that is the point of the lab.
    # shellcheck disable=SC2086
    prowler aws --region "$REGION" --checks $checks --output-formats json-ocsf \
      --output-directory "$OUT" --output-filename "pdpl-lab-$(date -u +%Y%m%dT%H%M%SZ)" || true
    ls -1t "$OUT"/*.ocsf.json | head -1
    ;;
  import)
    latest="$(ls -1t "$OUT"/*.ocsf.json 2>/dev/null | head -1 || true)"
    [[ -n "$latest" ]] || { echo "no scan in $OUT; run ./lab.sh scan first" >&2; exit 2; }
    py="$REPO/.venv/bin/python"; [[ -x "$py" ]] || py="$REPO/.venv/Scripts/python.exe"
    (cd "$REPO/backend" && "$py" -m app.cli import-findings "$latest" ${PDPL_ORG:+--org "$PDPL_ORG"})
    ;;
  down)
    whoami_aws
    bucket="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
      --query "Stacks[0].Outputs[?OutputKey=='Bucket'].OutputValue" --output text 2>/dev/null || true)"
    [[ -n "$bucket" && "$bucket" != "None" ]] && aws s3 rm "s3://$bucket" --recursive --region "$REGION" || true
    aws cloudformation delete-stack --region "$REGION" --stack-name "$STACK"
    aws cloudformation wait stack-delete-complete --region "$REGION" --stack-name "$STACK"
    echo "lab deleted"
    ;;
  *)
    sed -n '2,15p' "$0"
    exit 1
    ;;
esac
