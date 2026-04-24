# Emergency Rollback

## Determine The Fault Domain

- If bootstrap fails immediately after code deploy but bundle did not change, suspect code.
- If failures appear immediately after `current` switched, suspect bundle.
- If both changed together, test rollback in this order: data first if schema is suspected, otherwise code first.

## Code Rollback

1. Roll Render back to the previous Git commit/deploy.
2. Keep the existing bundle in place.
3. Re-run smoke checks.

## Data Rollback

1. Repoint `current` to the previous release.
2. Keep code unchanged.
3. Re-run smoke checks.

## Dual Rollback

1. Restore previous code deploy.
2. Restore previous bundle.
3. Re-run smoke checks.

## Minimum Validation Checklist

- `/healthz`
- `/api/bootstrap`
- one baseline figure
- one `first_optimization` figure
- analyst-only compare view if applicable
