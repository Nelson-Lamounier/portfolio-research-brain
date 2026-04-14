---
title: "Permission Denied on /data/app-deploy/ (SSM Shell)"
type: troubleshooting
tags: [linux, permissions, ssm, ebs, ec2, troubleshooting]
sources: [raw/step-function-runtime-logging.md]
created: 2026-04-13
updated: 2026-04-13
---

# Permission Denied on /data/app-deploy/ (SSM Shell)

## Symptom

```
[Errno 13] Permission denied: '/data/app-deploy/admin-api/deploy.py.202Ae3ac'
```

When running `aws s3 cp` from an interactive `just ssm-shell` session to write to `/data/app-deploy/`.

## Root Cause

The bootstrap step (`ebs_volume.py`) runs as **root** via SSM Run Command. The EBS volume directories are created as `root:root` with mode `755`:

```
drwxr-xr-x  root  root  /data/app-deploy/
```

`just ssm-shell` opens a session as **ssm-user** (restricted account created by the SSM agent). Permission check:

- Is ssm-user the owner? → No (root)
- Is ssm-user in the root group? → No
- Other bits: `r-x` → Read and enter, but **not write**
- Result: `EACCES`

The `.202Ae3ac` suffix is the temp file `aws s3 cp` creates before atomic rename — even a simple `s3 cp` requires write permission on the directory.

### Why sudo didn't work

On this Golden AMI, `ssm-user` had no `NOPASSWD` sudoers entry (not guaranteed across all AMI versions). `sudo aws s3 cp` prompted for an unknown password.

## Fix: Two-Layer Approach

### Layer 1 — `ebs_volume.py`: group-write at directory creation

After creating directories, `ensure_data_directories` now runs:

```python
run_cmd(["chown", "-R", "root:ssm-user", str(app_deploy)], check=False)
run_cmd(["chmod", "-R", "g+w",           str(app_deploy)], check=False)
```

Result: `drwxrwxr-x root ssm-user /data/app-deploy/` (numeric `775`)

`check=False` makes it non-fatal — if `ssm-user` doesn't exist yet at boot (race condition), it logs a warning and continues. The next boot self-heals.

### Layer 2 — `ssm-shell`: root session via AWS-StartInteractiveCommand

Updated `justfile` recipe to use:

```bash
aws ssm start-session \
  --document-name AWS-StartInteractiveCommand \
  --parameters '{"command":["sudo su -"]}'
```

SSM agent handles escalation — bypasses sudoers entirely. You land directly in a root bash session.

### Why Both Layers

| Scenario | Layer 1 alone | Layer 2 alone | Both |
|----------|--------------|--------------|------|
| ssm-shell + s3 cp | ✅ group write | ✅ root | ✅ |
| Old AMI without NOPASSWD | ✅ group write | ✅ SSM escalation | ✅ |
| SSM agent too old for StartInteractiveCommand | ✅ still works | ❌ fails | ✅ |
| First boot before ssm-user created | ⚠️ non-fatal fallback | ✅ root | ✅ |

Layer 1 = permanent structural fix. Layer 2 = developer ergonomics fix.

### EBS Persistence Note

The EBS volume at `/data/` persists across instance replacements. `chown`/`chmod` are called on every boot — permissions self-heal even if a previous pipeline run created files as `root:root 644`.

## Manual One-Time Fix

```bash
chown -R root:ssm-user /data/app-deploy && chmod -R g+w /data/app-deploy
```

## Related Pages

- [[aws-ssm]] — SSM execution model
- [[k8s-bootstrap-pipeline]] — where ebs_volume.py lives
- [[self-hosted-kubernetes]] — EBS volume in the bootstrap sequence
