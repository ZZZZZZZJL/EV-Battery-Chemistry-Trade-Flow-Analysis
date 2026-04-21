# Render Data Refresh

## Standard Flow

1. In the private workspace, generate or refresh baseline and first-optimization outputs.
2. Build a new runtime bundle release.
3. Validate the release.
4. Upload it to Render disk storage.
5. Switch `current`.
6. Run smoke checks.
7. Record the `data_release_id`.

## Bundle Naming

- Recommended: `data-YYYY-MM-DD-01`
- Same-day retries increment the numeric suffix

## Manifest Requirements

- schema version
- release id
- build timestamp
- public code commit
- private pipeline tag
- algorithms
- metals
- years
- hashes

## Upload Procedure

1. Copy the prepared release folder to `/var/data/runtime/releases/<release-id>`.
2. Keep the previous release untouched.
3. Update `current`.
4. Optionally update `previous`.

## Smoke Test After Switch

- `/healthz`
- `/api/bootstrap`
- `/api/figure?metal=Ni&year=2024&result_mode=baseline`

## Rollback

If smoke tests fail:

1. restore `current` to the previous known-good release
2. rerun smoke checks
3. log the failed release id and stop rollout
