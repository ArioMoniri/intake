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
    0700 dir): the Postgres and Redis passwords, the object store's root
    pair, the API's OpenBao token and the OTP tier's tokenization key. It
    writes the App Attest and SMS keys empty (see "App Attest and SMS"). A
    re-run keeps every existing value and fills only a missing one.
  - It initialises OpenBao with 3 key shares (threshold 2). The shares and
    the root token go to `/etc/intake-staging/openbao-init.json` (0600).
  - It builds the API image and writes its SBOM (see "Release SBOM" below)
    before it starts anything, because compose needs the SBOM's digest.
  - It unseals OpenBao, enables Transit, and writes the `intake-api` policy,
    the restart-probe KEK and the API's periodic token.
  - It runs the alembic migrations and re-keys every migration role away
    from its committed dev password.
- `./deploy.sh` runs on every deploy **and after every host reboot**. It
  first checks the object-store and SBOM image pins and then the host's swap
  (see above). It builds the API image and writes its SBOM, and stops if
  syft fails. Before anything restarts it runs the release gate and stops if
  deploys are frozen (see "Deploy freeze" below). OpenBao restarts sealed,
  and this script unseals it. It then
  renews the API token, migrates, runs
  `docker compose -p intake-staging up -d --no-build`, so the api runs exactly
  the image the SBOM describes, and probes `/healthz` and `/readyz` over HTTPS.
- `./smoke.sh` runs these checks:
  - `/healthz`, `/readyz`, `/metrics` and `/version` answer 200 over public
    HTTPS.
  - `/version` names the deployed sha, a build time and the sha256 of the
    SBOM on disk. `dev` in any of the three fails. The api container must
    run the image that SBOM describes.
  - The staging header is present, and HTTP redirects to HTTPS.
  - The running API reports `INTAKE_ENV=staging`, no dev gate and a Transit
    KEK.
  - Restart test: a synthetic record encrypted before `docker compose restart
    api` decrypts after it. It decrypts again after OpenBao is restarted and
    unsealed.

Upgrade: repeat steps 2 and 3, skipping `./init.sh`. State lives in
`/etc/intake-staging` (each release's SBOM included) and in the project's
named volumes, not in `/opt/intake`.

## Release SBOM

`/version` reports `git_sha`, `built_at` and `sbom_digest` (INT-352, audit
F18). The first two are build args baked into the image. The third describes
the image, so the image cannot carry it:

- `./init.sh` and `./deploy.sh` build the api image, then run syft
  (`anchore/syft`, pinned by digest in `lib.sh`, Apache-2.0) on a
  `docker image save` archive of it. The archive is mounted read-only, with
  no network and no capabilities, and syft never gets the docker socket.
- The SPDX JSON SBOM lands in
  `/etc/intake-staging/releases/<commit>/api-<image id>.spdx.json`. That is
  root-only and outside the build context, so it never enters the image.
- Its sha256 reaches the api container as `INTAKE_SBOM_DIGEST`, which compose
  requires. If syft fails or writes anything but an SPDX document, the script
  stops before any container starts.
- An image that already has its SBOM keeps it. A re-deploy of the same commit
  therefore keeps the same digest and does not recreate the api.
- `./smoke.sh` reads the SBOM from disk and never writes one. It compares its
  sha256 with `/version`'s `sbom_digest`.

## App Attest and SMS

Phone sign-in (the API's OTP tier) needs device attestation and an SMS
vendor (INT-352). `./init.sh` generates the tokenization key. The operator
sets the other keys by hand, as root, in `/etc/intake-staging/.env`:

| key | set by | value |
|---|---|---|
| `INTAKE_TOKENIZATION_KEY` | `./init.sh`, once | the HMAC key for phone pseudonyms. Never edit it: a new key forks every existing pseudonym |
| `INTAKE_APP_ATTEST_TEAM_ID` | operator | the signed iOS app's Apple App ID prefix, 10 characters (INT-344, HB-A3) |
| `INTAKE_APP_ATTEST_BUNDLE_ID` | operator, optional | leave empty for the app's committed bundle id |
| `INTAKE_APP_ATTEST_ENVIRONMENT` | operator, optional | leave empty for production. `development` is for dev-signed builds only, never on a public host like this one |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` | operator | the SMS vendor. `TWILIO_FROM` is a Twilio number in E.164 or a Messaging Service SID |

```bash
sudo -i
cd /opt/intake/infra/staging
"${EDITOR:-vi}" /etc/intake-staging/.env   # fill the keys; the file stays 0600 root
./deploy.sh
```

- `./deploy.sh` picks the keys up. Compose passes each one to the api
  container with no default and recreates the container when a value
  changes.
- An empty key reaches the API empty, and the API treats it as unset and
  fails closed. With no team id, every iOS attestation is refused, and
  Android's is refused until HB-A3, so no code is ever sent.
- `./deploy.sh` refuses a team id without all three SMS keys, because a
  verified device would then be told a code was sent that nobody sent.
- A host initialised before INT-352 has no tokenization key, so
  `./deploy.sh` stops with `INTAKE_TOKENIZATION_KEY is empty`. Re-run
  `./init.sh` once: it fills in only what is missing.
- **Setting the SMS keys sends a real phone number through this host to the
  vendor.** The host is synthetic-only (HB-I5, HB-L11), so setting them is the
  owner's decision, and the vendor needs a signed DPA first (invariant 18).

## Deploy freeze

`./deploy.sh` runs `require_release_not_frozen` after it builds the image and
writes its SBOM, and before the first `compose up` (INT-187). It runs the
release gate, `python -m intake_api.admin.release_gate`, in a one-off api
container on the project network, and stops the deploy when:

- deploys are frozen from the console (`/cicd`);
- an SLO's error budget is exhausted (only where a Prometheus is declared —
  staging declares none, and the gate says so on every run);
- the freeze record cannot be read: `INTAKE_RELEASE_FREEZE_REDIS_URL` unset,
  Redis down, or a record that is not the model;
- the gate itself could not run.

A refused deploy has changed nothing on the host: nothing was restarted.
`docs/runbooks/deploy-freeze.md` explains each refusal and how a freeze is
lifted (two people). Do not work around the gate on the host.

## Following main

INT-511. `make staging-follow-main` runs steps 2 and 3 above for one commit
of main, with no hands on the host. It ships a `git archive` of the commit to
the private deploy bucket, presigns it for 30 minutes, and sends an SSM
`AWS-RunShellScript`. That script verifies the archive's sha256 and runs
`scripts/ci/staging_follow_host.sh` from it. The host script points
`/opt/intake` at the new release under `/opt/onvizit-releases/` and runs
`./init.sh`, `./deploy.sh` and `./smoke.sh`. The job posts the smoke verdict
as the commit status `staging-smoke`.

```bash
make staging-follow-main DRY_RUN=1           # the plan for main's head; ships nothing
make staging-follow-main REF=<40-hex sha>    # deploy that commit of main
```

**What it refuses (exit 3).** A refusal posts no status, except on the host.
- An **unmerged** sha: GitHub's compare does not put it on main. The host
  ran unmerged `1785dd58` from 2 Oct; this is the refusal that would have
  stopped it.
- A **red** sha: a check run on it failed. The job's own runs do not count.
  While checks still run, the job waits (exit 0).
- A host whose `/version` lacks `X-Intake-Environment: staging-synthetic-only`.
  The job deploys only to the synthetic host. It never touches real-patient
  configuration, and it never reads `/etc/intake-staging`.
- A **backwards** move: the host already runs a newer commit of main. A host
  already on the sha is left alone (exit 0).
- An archive whose `infra/staging/REVISION` is not the sha, because
  `/version` could not name it then.
- On the host, a **frozen** state (INT-187). The release gate is read in the
  running api container before anything changes, because `./init.sh` starts
  the data tier before `./deploy.sh`'s own gate runs. That gate still runs too.
  Also refused on the host: a second run while one holds the lock, and an
  `/opt/intake` that is not a symlink.

**What red means (exit 1).**
- `./init.sh` or `./deploy.sh` fails: `/opt/intake` points back at the
  previous release, which is what still serves.
- `smoke` is red: the pointer stays on the new release, because `./deploy.sh`
  restarted onto it. The sha is not written to
  `/var/lib/intake-staging-follow/revision`, and the status is `failure`.
  Roll back by hand (docs/release/production-checklist.md §4).
- Smoke is green, but the public `/version` does not report the sha, a build
  time and an SBOM digest: the status is `failure`.

After a green run, releases other than the three newest and the previous one
are removed, together with their `intake-staging/*:<sha>` images.

**The trigger is a config value.** `FOLLOW_TRIGGER` in
`infra/staging/follow-main.conf` is `nightly` (`FOLLOW_NIGHTLY_CRON`, UTC)
until the owner picks. `green_merge` deploys each push to main once all its
checks are green. Moving to `green_merge` needs
`FOLLOW_TRIGGER_DECIDED_BY=owner:<date>` in the same commit, or the job
refuses to start.

**Where it runs.** On the owner's laptop it uses the `aws login` session. On
the `intake-aws-ci` runner it uses the staged workflow
`scripts/ci/staging_follow_main_workflow.yml`. The owner moves that file into
`.github/workflows/`, because no agent edits `.github/**`. The runner has no
instance role, so the workflow assumes a deploy role through GitHub's OIDC
token. The owner sets this up once:
1. Create the IAM role from `infra/staging/follow-main.trust.json` and
   `infra/staging/follow-main.policy.json`. It trusts only this repository's
   `synthetic-staging` environment. It may write one S3 prefix and run one
   SSM document on this instance.
2. Create the GitHub environment `synthetic-staging`, limited to `main`.
3. Set the environment variable `STAGING_FOLLOW_ROLE_ARN` to the role's ARN.

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
  note. The dev bearers are dev gates, and the OTP tier needs the
  operator's App Attest and SMS keys (see "App Attest and SMS").
  `infra/staging/staging_probe.py`
  drives the same `wiring_from_env()` cipher inside the api container.
- The release SBOM is not signed. CI's tag job signs the source-tree SBOM
  with cosign keyless, which needs CI's OIDC identity, and this host has none.
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
