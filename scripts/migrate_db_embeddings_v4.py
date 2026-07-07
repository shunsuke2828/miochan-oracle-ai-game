#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CREDENTIAL_NAME = "MIO_OCI_GENAI_CRED"
EMBEDDING_URL = (
    "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com/"
    "20231130/actions/embedText"
)
EMBEDDING_MODEL = "cohere.embed-v4.0"
EMBEDDING_REGION = "us-chicago-1"
EMBEDDING_DIMENSION = 1536


def main() -> None:
    os.environ["MIO_DATA_MODE"] = "adb"

    from app.config import Settings
    from app.database import AdbRepository

    repository = AdbRepository(Settings())
    parameters = json.dumps(
        {
            "provider": "ocigenai",
            "credential_name": CREDENTIAL_NAME,
            "url": EMBEDDING_URL,
            "model": EMBEDDING_MODEL,
        }
    )
    try:
        with repository.connection() as connection:
            with connection.cursor() as cursor:
                columns = {
                    row[0]
                    for row in cursor.execute(
                        """
                        select column_name
                        from user_tab_columns
                        where table_name = 'MIO_DEMO_SESSIONS'
                        """
                    )
                }
                definitions = {
                    "ANSWER_VECTOR_V4": "vector(1536, float32)",
                    "EMBEDDING_PROVIDER": "varchar2(40)",
                    "EMBEDDING_MODEL": "varchar2(120)",
                    "EMBEDDING_REGION": "varchar2(64)",
                    "EMBEDDED_AT": "timestamp with time zone",
                }
                for name, definition in definitions.items():
                    if name not in columns:
                        cursor.execute(
                            f"alter table mio_demo_sessions add ({name} {definition})"
                        )

                cursor.execute(
                    """
                    select count(*)
                    from mio_demo_sessions
                    where answer_text is not null
                    """
                )
                source_count = int(cursor.fetchone()[0])
                cursor.execute(
                    """
                    update mio_demo_sessions
                    set answer_vector_v4 = dbms_vector_chain.utl_to_embedding(
                          to_clob(answer_text), json(:parameters)
                        ),
                        embedding_provider = 'ocigenai',
                        embedding_model = :model,
                        embedding_region = :region,
                        embedded_at = systimestamp
                    where answer_text is not null
                    """,
                    {
                        "parameters": parameters,
                        "model": EMBEDDING_MODEL,
                        "region": EMBEDDING_REGION,
                    },
                )
                embedded_count = int(cursor.rowcount)
                connection.commit()
                cursor.execute(
                    """
                    select count(*)
                    from mio_demo_sessions
                    where answer_vector_v4 is not null
                      and vector_dimension_count(answer_vector_v4) = :dimension
                      and embedding_model = :model
                    """,
                    dimension=EMBEDDING_DIMENSION,
                    model=EMBEDDING_MODEL,
                )
                verified_count = int(cursor.fetchone()[0])
        if verified_count != source_count:
            raise RuntimeError(
                f"embedding verification mismatch: {verified_count}/{source_count}"
            )
        print(
            "DB embeddings migrated — "
            f"source={source_count} updated={embedded_count} "
            f"verified={verified_count} model={EMBEDDING_MODEL} "
            f"region={EMBEDDING_REGION} dimension={EMBEDDING_DIMENSION}"
        )
    finally:
        repository.close()


if __name__ == "__main__":
    main()
