"""
WC (Workflow Controller) Configuration

This module provides configuration management for the WC service using Pydantic Settings.
All configuration values can be set via environment variables or .env file.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class WCConfig(BaseSettings):
    """
    Workflow Controller Configuration

    All settings can be overridden via environment variables.
    Example: WC_HOST=127.0.0.1 WC_PORT=9000 uvicorn src.wc.main:app
    """

    # ========== WC Service Configuration ==========
    wc_host: str = Field(
        default="0.0.0.0",
        description="WC service host address"
    )
    wc_port: int = Field(
        default=8000,
        description="WC service port"
    )

    # ========== TM Configuration ==========
    tm_base_url: str = Field(
        default="http://localhost:8001",
        description="Transaction Manager base URL"
    )

    # ========== RM Configuration ==========
    flights_rm_url: str = Field(
        default="http://localhost:8002",
        description="Flights Resource Manager base URL"
    )
    hotels_rm_url: str = Field(
        default="http://localhost:8003",
        description="Hotels Resource Manager base URL"
    )
    cars_rm_url: str = Field(
        default="http://localhost:8004",
        description="Cars Resource Manager base URL"
    )
    customers_rm_url: str = Field(
        default="http://localhost:8005",
        description="Customers Resource Manager base URL"
    )

    # ========== HTTP Timeout Configuration ==========
    http_connect_timeout: int = Field(
        default=5,
        description="HTTP connection timeout in seconds"
    )
    http_read_timeout: int = Field(
        default=30,
        description="HTTP read timeout in seconds"
    )

    # ========== Logging Configuration ==========
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    log_json: bool = Field(
        default=False,
        description="Whether to output logs in JSON format"
    )

    # ========== Advanced Configuration ==========
    auto_abort_on_error: bool = Field(
        default=True,
        description="Automatically abort transaction on error"
    )
    enable_die: bool = Field(
        default=True,
        description="Enable /admin/die endpoint (disable in production)"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global configuration instance
config = WCConfig()


def get_config() -> WCConfig:
    """
    Get the global configuration instance.

    This function is used for dependency injection in FastAPI.

    Returns:
        WCConfig: The global configuration instance
    """
    return config
