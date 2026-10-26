"""Verify Supabase user access tokens for private session routes."""

from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient, PyJWKClientConnectionError

from backend.app.config import get_supabase_url


class AuthenticatedUser(str):
    """Verified subject with the original bearer token for request-scoped RLS."""

    def __new__(cls, user_id: str, access_token: str):
        instance = super().__new__(cls, user_id)
        instance.access_token = access_token
        return instance

    def __repr__(self):
        return f"AuthenticatedUser({str(self)!r}, access_token=[redacted])"


bearer_scheme = HTTPBearer(auto_error=False, scheme_name="SupabaseUserBearer")


@lru_cache(maxsize=4)
def _jwk_client(jwks_url: str) -> PyJWKClient:
    # Created on first authenticated request, so importing the application is offline.
    return PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=600)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedUser:
    """Return the verified subject and token; reject invalid tokens safely."""
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(status_code=401, detail="Valid user authentication is required.",
                            headers={"WWW-Authenticate": "Bearer"})
    project_url = get_supabase_url()
    if project_url is None:
        raise HTTPException(status_code=503, detail="User authentication is not configured.")
    issuer = f"{project_url}/auth/v1"
    try:
        signing_key = _jwk_client(f"{issuer}/.well-known/jwks.json").get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(credentials.credentials, signing_key.key,
                            algorithms=["ES256", "RS256"], audience="authenticated",
                            issuer=issuer, options={"require": ["exp", "sub", "iss", "aud", "role"]})
        if claims.get("role") != "authenticated":
            raise jwt.InvalidTokenError("Not a user access token")
        user_id = claims.get("sub")
        if not isinstance(user_id, str) or not user_id.strip():
            raise jwt.InvalidTokenError("Missing subject")
        return AuthenticatedUser(user_id.strip(), credentials.credentials)
    except PyJWKClientConnectionError:
        raise HTTPException(status_code=503, detail="User authentication could not be verified right now.") from None
    except Exception:
        raise HTTPException(status_code=401, detail="Valid user authentication is required.",
                            headers={"WWW-Authenticate": "Bearer"}) from None
