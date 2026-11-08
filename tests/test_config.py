from app.core.config import Settings

SECRET = "test-secret-key-that-is-long-enough-for-hs256-0123456789"


def make_settings(**overrides) -> Settings:
    # _env_file=None: 개발자 PC의 .env가 테스트 결과에 섞이지 않게 한다.
    return Settings(_env_file=None, jwt_secret_key=SECRET, **overrides)


def test_connect_args_without_ssl_only_fix_time_zone():
    assert make_settings().database_connect_args == {"init_command": "SET time_zone = '+00:00'"}


def test_connect_args_with_ssl_ca_verify_certificate_and_host():
    args = make_settings(db_ssl_ca="/etc/secrets/aiven-ca.pem").database_connect_args

    assert args == {
        "init_command": "SET time_zone = '+00:00'",
        "ssl_ca": "/etc/secrets/aiven-ca.pem",
        "ssl_verify_cert": True,
        "ssl_verify_identity": True,
    }


def test_host_name_check_can_be_turned_off_but_certificate_check_stays():
    args = make_settings(
        db_ssl_ca="/etc/secrets/aiven-ca.pem", db_ssl_verify_identity=False
    ).database_connect_args

    assert args["ssl_verify_cert"] is True
    assert args["ssl_verify_identity"] is False
