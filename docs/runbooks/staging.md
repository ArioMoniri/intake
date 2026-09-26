# Runbook: staging backend on the AWS host (INT-345)

## Synthetic patients only. Read this first

The staging host is **us-east-1** (`i-026e14d0676011da0`). It may hold
**synthetic patients only**. No real patient data, no PHI and no real phone
number may reach it. That holds until an in-country host exists: **HB-I5** is
the in-country GPU/capacity contract and **HB-L11** is counsel on KVKK Art. 9.
Every response from the host carries `X-Intake-Environment:
staging-synthetic-only`.

The artefact lives in `infra/staging/`. It runs API, Postgres, Redis, OpenBao
(server mode, file storage, Transit KEK), an S3-compatible object store and
Caddy (automatic TLS) on this one host. Nothing runs on the developer laptop. Only Caddy publishes ports, and
only 80 and 443. The llama.cpp model server on the same box stays bound to
loopback (`docs/runbooks/model-server-aws.md`). The new security group opens
80/443 to Caddy and to nothing else.

## Object store

The compose service `minio` is the API's document store and WORM audit copy.
Its image is the one the owner chose on 2026-09-26 (**owner decision D1**):
the maintained AGPL-3.0 community fork of the withdrawn upstream image, pinned
by sha256 index digest. **INT-347 (#550)** records the same reference in
`observability/registry.yaml`, with the licence verified from the raw LICENSE
blob.

- `OBJECT_STORE_IMAGE` in `infra/staging/lib.sh` is the only copy in this
  tier. lib.sh exports it and compose interpolates it. deploy.sh's first
  statement refuses an empty or unpinned value before it touches the host.
- The store publishes no port and sits on the internal `backend` network
  only. The API reaches it at `minio:9000`, and its web console is off.
- `./init.sh` generates `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` into the
  root-only env file with every other secret. The store and the api take the
  same pair, with no default. Outside dev the API refuses to boot without it
  (INT-325, PR #521).
- Data lives on the `minio-data` volume. Nothing pre-creates a bucket. The
  API creates both on first use, the audit bucket with object lock, which the
  store can enable only at creation.

## Host memory: swap off or encrypted

OpenBao 2.6 dropped mlock. It refuses to load a config that still sets
`disable_mlock`, so `infra/staging/openbao/openbao.hcl` no longer sets it. An
unsealed server's keys now sit in ordinary memory, which the kernel may page
out. The host must therefore run with swap disabled, or with swap that never
reaches a disk in the clear.

- `./init.sh` and `./deploy.sh` check this before OpenBao starts
  (`require_no_unencrypted_swap` in `lib.sh`). They read `swapon --show` and
  refuse unless every active swap area is either zram (compressed RAM) or
  has dm-crypt at or beneath it, for example LVM on LUKS. A swap file is
  refused, because the script cannot prove that its filesystem is encrypted.
  A host where `swapon` cannot run is refused too.
- The AWS host has no swap today: `swapon --show` prints nothing. Nothing
  needs doing unless that changes.
- `./deploy.sh` repeats the check on every run, because a reboot re-reads
  `/etc/fstab` and can bring swap back.

If the check refuses, turn swap off, as root:

```bash
swapon --show   # what is active
swapoff -a      # turn it all off now
# then delete the swap line(s) from /etc/fstab, so a reboot does not bring it back
```

The alternative is to keep swap but encrypt it: move it onto dm-crypt with a
fresh random key per boot (a `swap` entry in `/etc/crypttab`), or onto zram.
Then re-run the script that refused.

## Prerequisites (owner, one-time)

- On the laptop: `awscli`, `session-manager-plugin`, and `aws sso login`
  (interactive).
- On the host: Docker Engine with the compose v2 plugin, plus `python3`,
  `curl` and `tar`. The host needs no git. Check with
  `docker compose version`. If Docker is missing, install Docker Engine from
  Docker's own apt repository. Whether a runtime may be installed on this box
  is the owner's call (HB-I13 records the same question for the edge tier).
- On the host: swap off or encrypted (see "Host memory" above).
- A private S3 bucket in the account for shipping the tree. `ARTEFACT_BUCKET`
  below is the owner's existing bucket name. It is not invented here.

## 1. Start the host, give it a stable address and a web security group

Run on the laptop:

```bash
export AWS_REGION=us-east-1 IID=i-026e14d0676011da0
aws ec2 start-instances --instance-ids "$IID" && aws ec2 wait instance-running --instance-ids "$IID"

# Elastic IP. Associating it replaces the instance's auto-assigned public IP.
ALLOC=$(aws ec2 allocate-address --domain vpc \
  --tag-specifications 'ResourceType=elastic-ip,Tags=[{Key=Name,Value=intake-staging}]' \
  --query AllocationId --output text)
aws ec2 associate-address --instance-id "$IID" --allocation-id "$ALLOC"
EIP=$(aws ec2 describe-addresses --allocation-ids "$ALLOC" --query 'Addresses[0].PublicIp' --output text)

# Dedicated security group: 80 (ACME HTTP-01 + redirect) and 443, nothing else.
VPC=$(aws ec2 describe-instances --instance-ids "$IID" --query 'Reservations[0].Instances[0].VpcId' --output text)
SG=$(aws ec2 create-security-group --group-name intake-staging-web \
  --description "INT-345 staging: 80/443 to Caddy only" --vpc-id "$VPC" --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id "$SG" --ip-permissions \
  'IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=0.0.0.0/0}]' \
  'IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=0.0.0.0/0}]'

# Attach it IN ADDITION to the existing groups (--groups replaces the whole set).
EXISTING=$(aws ec2 describe-instances --instance-ids "$IID" \
  --query 'Reservations[0].Instances[0].SecurityGroups[].GroupId' --output text)
aws ec2 modify-instance-attribute --instance-id "$IID" --groups $EXISTING "$SG"

echo "STAGING_HOSTNAME=$(echo "$EIP" | tr . -).sslip.io"
```

The hostname is `<EIP-dashed>.sslip.io`. For example, an EIP of 3.91.12.7
gives `3-91-12-7.sslip.io`. sslip.io resolves that name to the EIP, and Caddy
obtains a Let's Encrypt certificate for it on first start. No ACME account
mailbox is configured, because that mailbox is HB-I14.

## 2. Ship the tree

`git archive` stamps `infra/staging/REVISION` with the commit sha through
`export-subst`, so `/version` is truthful on a host that has no `.git`.

Run on the laptop:

```bash
git -C ~/Downloads/previsit fetch origin
git -C ~/Downloads/previsit archive --format=tar.gz --prefix=intake/ -o /tmp/intake-staging.tgz origin/main
aws s3 cp /tmp/intake-staging.tgz "s3://$ARTEFACT_BUCKET/intake-staging.tgz"
aws s3 presign "s3://$ARTEFACT_BUCKET/intake-staging.tgz" --expires-in 900
```

## 3. Initialise, deploy, smoke

```bash
aws ssm start-session --target i-026e14d0676011da0 --region us-east-1
```

Then, on the host:

```bash
sudo -i
curl -fsSL '<the presigned URL from step 2>' -o /tmp/intake-staging.tgz
rm -rf /opt/intake && tar -xzf /tmp/intake-staging.tgz -C /opt && cd /opt/intake/infra/staging
STAGING_HOSTNAME=<EIP-dashed>.sslip.io ./init.sh
./deploy.sh
./smoke.sh
```

- `./init.sh` is run once and is idempotent.
  - It first refuses a host whose active swap is not encrypted (see "Host
    memory" above).
  - It generates every secret into `/etc/intake-staging/.env` (0600, in a
    0700 dir): the Postgres and Redis passwords, the object store's root pair
    and the API's OpenBao token. A re-run keeps every existing value and
    fills only a missing one.
  - It initialises OpenBao with 3 key shares (threshold 2). The shares and
    the root token go to `/etc/intake-staging/openbao-init.json` (0600).
  - It unseals OpenBao, enables Transit, and writes the `intake-api` policy,
    the restart-probe KEK and the API's periodic token.
  - It runs the alembic migrations and re-keys every migration role away
    from its committed dev password.
- `./deploy.sh` runs on every deploy **and after every host reboot**. It
  first checks the object-store image pin and then the host's swap (see
  above). OpenBao restarts
  sealed, and this script unseals it. It then renews the API token,
  builds, migrates, runs `docker compose -p intake-staging up -d --build`,
  and probes `/healthz` and `/readyz` over HTTPS.
- `./smoke.sh` runs these checks:
  - `/healthz`, `/readyz`, `/metrics` and `/version` answer 200 over public
    HTTPS.
  - `/version` names the deployed sha and a build time, never `dev`.
  - The staging header is present, and HTTP redirects to HTTPS.
  - The running API reports `INTAKE_ENV=staging`, no dev gate and a Transit
    KEK.
  - Restart test: a synthetic record encrypted before `docker compose restart
    api` decrypts after it. It decrypts again after OpenBao is restarted and
    unsealed.

Upgrade: repeat steps 2 and 3, skipping `./init.sh`. State lives in
`/etc/intake-staging` and in the project's named volumes, not in `/opt/intake`.

## Known gaps, stated rather than hidden

- **`/readyz` answers 503 on main as of 730e9288.** The response is
  `{"checks": {..., "dev_auth": "error"}}`, because the INT-197 `dev_auth`
  readiness check is mounted outside dev. INT-325 (PR #521, at be74a9d1)
  keeps that check to dev only. The same PR makes every non-dev environment,
  staging included, refuse the DB and object-store credentials' absence; this
  artefact supplies all five. Until #521 merges, smoke check 1 fails on
  `/readyz`, by design and with the reason printed.
- **The restart test runs through the API's cipher, not an HTTP route.** A
  staging API with no dev gate has no authentication tier that can write a
  note. The dev bearers are dev gates, and the OTP tier needs an SMS vendor
  and attestation, both awaiting-human. `infra/staging/staging_probe.py`
  drives the same `wiring_from_env()` cipher inside the api container.
- `/version`'s `sbom_digest` stays `dev`: this artefact produces no SBOM.
- Document upload has no ClamAV here, so it fails closed
  (`scan_not_configured`) although the object store runs.
- The synthetic probe registration and the staging banner/tenant belong to
  the API and app, not to this artefact.
- **Key custody is a staging posture only.** The unseal shares sit on the
  same disk as the data they protect. Production key custody (KMS
  auto-unseal, split custodians) is a key-management design decision for a
  human, and nothing here decides it.

## Teardown

```bash
cd / && docker compose -p intake-staging down   # by project name, no file needed; keeps volumes
```

Destroying the synthetic data means also running `down -v` and
`rm -rf /etc/intake-staging`. Once that is done, the OpenBao data is
unrecoverable by design. Then run, on the laptop:
`aws ec2 modify-instance-attribute --instance-id "$IID" --groups $EXISTING`,
`aws ec2 delete-security-group --group-id "$SG"`,
`aws ec2 disassociate-address --association-id <id>` and
`aws ec2 release-address --allocation-id "$ALLOC"`.
