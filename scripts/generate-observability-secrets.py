"""Print Week 6 secrets for copying into the local .env file."""

import secrets


def token(bytes_count: int = 32) -> str:
    return secrets.token_urlsafe(bytes_count)


print(f"LANGFUSE_NEXTAUTH_SECRET={token()}")
print(f"LANGFUSE_SALT={token()}")
print(f"LANGFUSE_ENCRYPTION_KEY={secrets.token_hex(32)}")
print(f"LANGFUSE_POSTGRES_PASSWORD={token(24)}")
print(f"LANGFUSE_CLICKHOUSE_PASSWORD={token(24)}")
print(f"LANGFUSE_REDIS_PASSWORD={token(24)}")
print("LANGFUSE_MINIO_ACCESS_KEY=paperforge-minio")
print(f"LANGFUSE_MINIO_SECRET_KEY={token(24)}")
print(f"LANGFUSE_INIT_USER_PASSWORD={token(18)}")
print("PAPERFORGE_LANGFUSE__PUBLIC_KEY=pk-lf-paperforge-local")
print(f"PAPERFORGE_LANGFUSE__SECRET_KEY=sk-lf-{token(24)}")
