#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import termios
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


CREDENTIAL_NAME = "MIO_OCI_GENAI_CRED"
EMBEDDING_URL = (
    "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com/"
    "20231130/actions/embedText"
)
EMBEDDING_HOST = "inference.generativeai.us-chicago-1.oci.oraclecloud.com"
EMBEDDING_MODEL = os.getenv("MIO_DB_EMBED_MODEL", "cohere.embed-v4.0")
EMBEDDING_DIMENSION = (
    1536 if EMBEDDING_MODEL == "cohere.embed-v4.0" else 1024
)


def _read_configuration() -> dict[str, str]:
    terminal_settings = None
    if sys.stdin.isatty():
        terminal_settings = termios.tcgetattr(sys.stdin.fileno())
        hidden_settings = termios.tcgetattr(sys.stdin.fileno())
        hidden_settings[3] &= ~termios.ECHO
        termios.tcsetattr(
            sys.stdin.fileno(), termios.TCSADRAIN, hidden_settings
        )
    try:
        line = sys.stdin.readline()
    finally:
        if terminal_settings is not None:
            termios.tcsetattr(
                sys.stdin.fileno(), termios.TCSADRAIN, terminal_settings
            )
    if not line:
        raise RuntimeError("OCI credential JSON was not provided on stdin")
    payload = json.loads(line)
    if payload.get("reuse_credential") is True:
        return {}
    required = (
        "user_ocid",
        "tenancy_ocid",
        "compartment_ocid",
        "fingerprint",
        "private_key",
    )
    if not all(payload.get(key) for key in required):
        raise RuntimeError("OCI credential JSON is incomplete")
    private_key = str(payload["private_key"]).strip()
    private_key = private_key.replace("-----BEGIN PRIVATE KEY-----", "")
    private_key = private_key.replace("-----END PRIVATE KEY-----", "")
    private_key = private_key.replace("-----BEGIN RSA PRIVATE KEY-----", "")
    private_key = private_key.replace("-----END RSA PRIVATE KEY-----", "")
    payload["private_key"] = "".join(private_key.split())
    return {key: str(payload[key]) for key in required}


def main() -> None:
    os.environ["MIO_DATA_MODE"] = "adb"
    credential = _read_configuration()

    from app.config import Settings
    from app.database import AdbRepository

    repository = AdbRepository(Settings())
    try:
        with repository.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    begin
                      dbms_network_acl_admin.append_host_ace(
                        host => :host,
                        ace => xs$ace_type(
                          privilege_list => xs$name_list('http'),
                          principal_name => :principal_name,
                          principal_type => xs_acl.ptype_db
                        )
                      );
                    exception
                      when others then
                        if sqlcode != -24243 then raise; end if;
                    end;
                    """,
                    host=EMBEDDING_HOST,
                    principal_name=repository.settings.adb_user.upper(),
                )
                connection.commit()
                if credential:
                    cursor.execute(
                        """
                        begin
                          begin
                            dbms_vector_chain.drop_credential(:credential_name);
                          exception when others then null;
                          end;
                        end;
                        """,
                        credential_name=CREDENTIAL_NAME,
                    )
                    cursor.execute(
                        """
                        declare
                          credential_json json_object_t := json_object_t();
                        begin
                          credential_json.put('user_ocid', :user_ocid);
                          credential_json.put('tenancy_ocid', :tenancy_ocid);
                          credential_json.put('compartment_ocid', :compartment_ocid);
                          credential_json.put('private_key', :private_key);
                          credential_json.put('fingerprint', :fingerprint);
                          dbms_vector_chain.create_credential(
                            credential_name => :credential_name,
                            params => json(credential_json.to_string)
                          );
                        end;
                        """,
                        credential_name=CREDENTIAL_NAME,
                        **credential,
                    )
                    connection.commit()

                embedding_parameters = {
                    "provider": "ocigenai",
                    "credential_name": CREDENTIAL_NAME,
                    "url": EMBEDDING_URL,
                    "model": EMBEDDING_MODEL,
                }
                parameters = json.dumps(embedding_parameters)
                cursor.execute(
                    """
                    select vector_dimension_count(
                      dbms_vector_chain.utl_to_embedding(
                        'Oracle AI Database vector embedding smoke test',
                        json(:parameters)
                      )
                    )
                    from dual
                    """,
                    {"parameters": parameters},
                )
                dimension = int(cursor.fetchone()[0])
                if dimension != EMBEDDING_DIMENSION:
                    raise RuntimeError(
                        f"unexpected embedding dimension: {dimension}"
                    )
        print(
            "DB embedding ready — "
            f"provider=ocigenai region=us-chicago-1 "
            f"model={EMBEDDING_MODEL} dimension={dimension} "
            f"credential={CREDENTIAL_NAME}"
        )
    finally:
        repository.close()


if __name__ == "__main__":
    main()
