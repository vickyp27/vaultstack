from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://vaultstack:vaultstack123@localhost/vaultstack"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # OpenStack
    os_auth_url: str = "http://172.16.109.210/identity"
    os_username: str = "admin"
    os_password: str = "VaultStack123"
    os_project_name: str = "admin"
    os_user_domain_name: str = "Default"
    os_project_domain_name: str = "Default"

    # Storage
    backup_base_path: str = "/var/vaultstack/backups"

    class Config:
        env_file = ".env"

settings = Settings()
