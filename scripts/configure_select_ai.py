#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROFILE_NAME = "MIO_GEMINI_FLASH"
CREDENTIAL_NAME = "MIO_OCI_GENAI_CRED"
MODEL_NAME = "google.gemini-2.5-flash"
REGION = "us-chicago-1"


def main() -> None:
    os.environ["MIO_DATA_MODE"] = "adb"
    compartment_id = os.getenv("MIO_OCI_COMPARTMENT_OCID", "").strip()
    if not compartment_id:
        raise RuntimeError("MIO_OCI_COMPARTMENT_OCID is required")

    from app.config import Settings
    from app.database import AdbRepository

    repository = AdbRepository(Settings())
    attributes = json.dumps(
        {
            "provider": "oci",
            "credential_name": CREDENTIAL_NAME,
            "oci_compartment_id": compartment_id,
            "region": REGION,
            "model": MODEL_NAME,
            "conversation": True,
            "temperature": 0.2,
            "max_tokens": 700,
        }
    )
    try:
        with repository.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    begin
                      begin
                        dbms_cloud_ai.drop_profile(:profile_name, force => true);
                      exception when others then null;
                      end;
                      dbms_cloud_ai.create_profile(
                        profile_name => :profile_name,
                        attributes => :attributes,
                        status => 'enabled',
                        description => 'Mio Rescue Gemini 2.5 Flash via OCI Generative AI'
                      );
                    end;
                    """,
                    profile_name=PROFILE_NAME,
                    attributes=attributes,
                )
                connection.commit()
                cursor.execute(
                    """
                    select dbms_cloud_ai.generate(
                      prompt => 'JSONだけを返してください: {"status":"ok"}',
                      profile_name => :profile_name,
                      action => 'chat'
                    )
                    from dual
                    """,
                    profile_name=PROFILE_NAME,
                )
                response = cursor.fetchone()[0]
                text = response.read() if hasattr(response, "read") else str(response)
                if "status" not in text.lower() or "ok" not in text.lower():
                    raise RuntimeError(f"unexpected Select AI response: {text[:200]}")
        print(
            "Select AI ready — "
            f"profile={PROFILE_NAME} model={MODEL_NAME} region={REGION}"
        )
    finally:
        repository.close()


if __name__ == "__main__":
    main()
