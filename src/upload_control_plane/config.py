from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "local"
    app_name: str = "upload-control-plane"
    log_level: str = "INFO"

    api_cors_allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    api_cors_allowed_methods: list[str] = Field(
        default_factory=lambda: ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
    )
    api_cors_allowed_headers: list[str] = Field(
        default_factory=lambda: [
            "authorization",
            "content-type",
            "idempotency-key",
            "x-request-id",
        ]
    )
    api_cors_expose_headers: list[str] = Field(default_factory=lambda: ["x-request-id"])

    database_url: str = "postgresql+psycopg://upload:upload@localhost:25432/upload"
    database_echo: bool = False
    database_pool_pre_ping: bool = True

    s3_endpoint_url: str = "http://localhost:19000"
    s3_public_endpoint_url: str = "http://localhost:19000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_region: str = "us-east-1"
    s3_bucket: str = "robot-data"
    s3_addressing_style: str = "path"
    s3_require_tls_in_production: bool = True
    s3_default_encryption_mode: str = "NONE"
    s3_default_kms_key_ref: str = ""
    s3_enable_object_lock: bool = False
    s3_default_object_lock_mode: str = ""
    s3_default_object_lock_retention_days: int | None = None
    s3_enable_conditional_complete: bool = False
    s3_cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )
    s3_cors_allowed_headers: list[str] = Field(
        default_factory=lambda: [
            "content-type",
            "etag",
            "x-amz-checksum-sha256",
            "x-amz-checksum-crc32c",
            "x-amz-server-side-encryption",
        ]
    )
    s3_cors_expose_headers: list[str] = Field(
        default_factory=lambda: [
            "etag",
            "x-amz-checksum-sha256",
            "x-amz-checksum-crc32c",
        ]
    )

    default_part_size_bytes: int = 67_108_864
    min_part_size_bytes: int = 5_242_880
    max_part_size_bytes: int = 5_368_709_120
    max_part_count: int = 10_000
    default_presign_expiry_seconds: int = 900
    max_presign_expiry_seconds: int = 21_600
    max_presign_signature_age_seconds: int = 900
    default_upload_session_expiry_seconds: int = 86_400
    max_upload_session_expiry_seconds: int = 604_800
    max_parts_per_presign_request: int = 100

    max_open_uploads_per_tenant: int = 1_000
    max_open_upload_tasks_per_project: int = 200
    max_open_uploads_per_device: int = 20
    max_bytes_per_tenant: int | None = None
    max_bytes_per_project: int | None = None
    presign_rate_limit_per_tenant_per_minute: int = 600
    presign_rate_limit_per_device_per_minute: int = 120

    default_recycle_retention_days: int = 30
    default_dataset_retention_days: int | None = None
    default_download_url_expiry_seconds: int = 900
    max_download_url_expiry_seconds: int = 21_600

    enable_dataset_validation: bool = False
    enable_metadata_extraction: bool = False
    enable_malware_scan: bool = False
    enable_storage_native_checksum: bool = False
    storage_native_checksum_algorithm: str = ""
    enable_outbox_dispatcher: bool = True
    outbox_max_attempts: int = 12
    outbox_batch_size: int = 100
    worker_poll_interval_seconds: int = 300
    worker_batch_size: int = 100
    expired_session_abort_grace_seconds: int = 0
    validation_queue_max_depth: int = 1_000
    backpressure_storage_error_rate_threshold: float = 0.05
    backpressure_storage_p95_latency_ms: int = 5_000
    enable_checksum_validator: bool = False

    enable_mqtt_control_plane: bool = False
    mqtt_broker_host: str = "emqx"
    mqtt_broker_port: int = 1883
    mqtt_use_tls: bool = False
    mqtt_client_id: str = "upload-control-plane"
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_ca_file: str = ""
    mqtt_cert_file: str = ""
    mqtt_key_file: str = ""
    mqtt_topic_prefix: str = "device"
    mqtt_qos: int = 1
    mqtt_retain_presigned_url_responses: bool = False

    @field_validator(
        "s3_cors_allowed_origins",
        "s3_cors_allowed_headers",
        "s3_cors_expose_headers",
        "api_cors_allowed_origins",
        "api_cors_allowed_methods",
        "api_cors_allowed_headers",
        "api_cors_expose_headers",
        mode="before",
    )
    @classmethod
    def parse_csv_list(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
