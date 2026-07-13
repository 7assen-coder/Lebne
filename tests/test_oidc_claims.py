from api.security.oidc import roles_and_scopes_from_oidc


def test_oidc_claim_mapping_defaults_to_end_user():
    roles, scopes = roles_and_scopes_from_oidc({"sub": "idp-1"})
    assert "end_user" in roles
    assert "chat:write" in scopes


def test_oidc_realm_access_admin():
    roles, scopes = roles_and_scopes_from_oidc(
        {"sub": "a1", "realm_access": {"roles": ["admin"]}}
    )
    assert "admin" in roles
    assert "audit:read" in scopes
