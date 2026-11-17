# AWS test lab: prove the Prowler path on a real account

Everything else in this repository is tested with synthetic Prowler output. This lab is how you
show it works against a real AWS account: create a few deliberately weak settings, scan them with
Prowler, import the result, and watch the requirements they map to turn red.

**Run it yourself, on an account you own.** The script asks you to confirm the account before it
does anything, never handles credentials, and uses whatever the AWS CLI already uses.

## What the stack creates

| Resource | Deliberate weakness | Mapped Prowler checks expected to fail |
|---|---|---|
| S3 bucket (public access block **on**) | no versioning, no access logging, no TLS-only policy, no lifecycle | `s3_bucket_object_versioning`, `s3_bucket_server_access_logging_enabled`, `s3_bucket_secure_transport_policy`, `s3_bucket_lifecycle_enabled` |
| Security group, attached to nothing | SSH open to `0.0.0.0/0` | `ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_22` |
| CloudWatch log group (empty) | no retention, no KMS key | `cloudwatch_log_group_retention_policy_specific_days_enabled`, `cloudwatch_log_group_kms_encryption_enabled` |
| 1 GiB gp3 EBS volume | unencrypted (unless EBS default encryption is on) | `ec2_ebs_volume_encryption`, `ec2_ebs_volume_protected_by_backup_plan` |

Nothing is reachable from the internet. The volume costs a few US cents a month; everything else is
free at this size. A fresh account will also fail account-level checks (CloudTrail, GuardDuty,
password policy and so on), which is realistic.

## Steps

```bash
export AWS_PROFILE=my-sandbox AWS_REGION=eu-central-1
./scripts/aws-lab/lab.sh up        # CloudFormation rights needed
./scripts/aws-lab/lab.sh scan      # SecurityAudit + ViewOnlyAccess is enough
./scripts/aws-lab/lab.sh import    # PDPL_ORG=2 to import into another organisation
./scripts/aws-lab/lab.sh down
```

Prowler is not bundled: install it in its own virtualenv (`pip install prowler`). Prowler does not
install on native Windows; use WSL, Linux or macOS.

After `import`, open **Automated checks → Runs** and the requirement pages these checks map to:
A06.01 (encryption at rest), A06.02 (encryption in transit), A06.07 (network exposure),
A05.04 (backups) and A07.02 (logging). Scan again after fixing one setting in the console
to see the change between runs, then run `down`.
