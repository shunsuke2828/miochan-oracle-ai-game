from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("MIO_HOST", "0.0.0.0")
    port: int = int(os.getenv("MIO_PORT", "4317"))
    data_mode: str = os.getenv("MIO_DATA_MODE", "auto").lower()

    adb_user: str = os.getenv("MIO_ADB_USER", "admin")
    adb_password: str = os.getenv("MIO_ADB_PASSWORD", "")
    adb_dsn: str = os.getenv("MIO_ADB_DSN", "wcdkuw08o7t8dax7_high")
    adb_wallet_zip: Path = Path(
        os.getenv("MIO_ADB_WALLET_ZIP", "/home/opc/Wallet_WCDKUW08O7T8DAX7.zip")
    )
    adb_wallet_password: str = os.getenv("MIO_ADB_WALLET_PASSWORD", "")
    oracle_client_lib: Path = Path(
        os.getenv("MIO_ORACLE_CLIENT_LIB", "/opt/oracle/product/26ai/dbhomeFree/lib")
    )

    oci_enabled: bool = _as_bool(os.getenv("MIO_OCI_ENABLE"), False)
    oci_region: str = os.getenv("MIO_OCI_REGION", "us-chicago-1")
    oci_user_ocid: str = os.getenv("MIO_OCI_USER_OCID", "")
    oci_tenancy_ocid: str = os.getenv("MIO_OCI_TENANCY_OCID", "")
    oci_compartment_ocid: str = os.getenv("MIO_OCI_COMPARTMENT_OCID", "")
    oci_fingerprint: str = os.getenv("MIO_OCI_FINGERPRINT", "")
    oci_private_key_file: str = os.getenv("MIO_OCI_PRIVATE_KEY_FILE", "")
    oci_chat_model_id: str = os.getenv("MIO_OCI_CHAT_MODEL_ID", "")
    oci_embed_model_id: str = os.getenv(
        "MIO_OCI_EMBED_MODEL_ID", "cohere.embed-v4.0"
    )

    @property
    def adb_requested(self) -> bool:
        return self.data_mode == "adb" or (
            self.data_mode == "auto" and bool(self.adb_password)
        )

    @property
    def oci_ready(self) -> bool:
        return self.oci_enabled and all(
            (
                self.oci_user_ocid,
                self.oci_tenancy_ocid,
                self.oci_compartment_ocid,
                self.oci_fingerprint,
                self.oci_private_key_file,
                self.oci_chat_model_id,
            )
        )


settings = Settings()
