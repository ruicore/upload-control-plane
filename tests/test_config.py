from upload_control_plane.config import Settings


def test_settings_defaults_match_t00_runtime_contract() -> None:
    settings = Settings()

    assert settings.app_name == "upload-control-plane"
    assert settings.database_url == "postgresql+psycopg://upload:upload@localhost:25432/upload"
    assert settings.s3_public_endpoint_url == "http://localhost:19000"
    assert settings.s3_bucket == "robot-data"
    assert settings.max_part_count == 10_000


def test_settings_parses_csv_environment_values() -> None:
    settings = Settings.model_validate(
        {
            "api_cors_allowed_headers": "authorization,content-type,idempotency-key",
            "s3_cors_allowed_origins": "http://localhost:5173,http://localhost:3000",
        }
    )

    assert settings.api_cors_allowed_headers == [
        "authorization",
        "content-type",
        "idempotency-key",
    ]
    assert settings.s3_cors_allowed_origins == [
        "http://localhost:5173",
        "http://localhost:3000",
    ]
