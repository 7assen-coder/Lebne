# Argon2 & IdP

## Argon2 (implemented)
- `wallet/passwords.py` — argon2id hash / verify / rehash
- Used by `change_password`, `/v1/auth/register`, `/v1/auth/login`
- Plaintext passwords are never stored

## Real IdP (implemented)
Configure:
```bash
LEBNE_ENV=production
LEBNE_AUTH_MODE=oidc
LEBNE_OIDC_JWKS_URL=https://<idp>/.../certs
LEBNE_OIDC_ISSUER=https://<idp>/realms/lebne
LEBNE_OIDC_AUDIENCE=lebne-api
```

Behavior:
- User JWTs verified via JWKS (RS256)
- `/v1/auth/dev-token` and local register/login disabled in `oidc` / production as documented
- `hybrid` mode: try IdP then local HS256 (useful for staging)
- Flutter (later): login at IdP → Bearer token → Lebne APIs

Modes: `local` | `hybrid` | `oidc` (`LEBNE_AUTH_MODE`)
