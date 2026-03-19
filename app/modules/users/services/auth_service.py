from app.modules.users.schemas.response import TokenResponse


class AuthService:
    def create_token(self, user_id: str) -> TokenResponse:
        return TokenResponse(access_token=f"dev-token-{user_id}")

