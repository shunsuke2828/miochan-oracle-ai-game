#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    os.environ["MIO_DATA_MODE"] = "adb"
    from app.config import Settings
    from app.database import (
        DB_EMBED_DIMENSION,
        DB_EMBED_MODEL,
        DB_EMBED_PROVIDER,
        DB_EMBED_REGION,
        AdbRepository,
        db_embedding_parameters,
    )
    from app.personas import SEED_PARTICIPANTS

    repository = AdbRepository(Settings())
    try:
        with repository.connection() as connection:
            with connection.cursor() as cursor:
                for index, (nickname, answer, persona) in enumerate(
                    SEED_PARTICIPANTS, start=1
                ):
                    cursor.execute(
                        """
                        update mio_demo_sessions
                        set nickname = :nickname,
                            persona_name = :persona_name,
                            answer_text = :answer_text,
                            answer_vector_v4 = dbms_vector_chain.utl_to_embedding(
                              to_clob(:answer_text), json(:embedding_parameters)
                            ),
                            embedding_provider = :embedding_provider,
                            embedding_model = :embedding_model,
                            embedding_region = :embedding_region,
                            embedded_at = systimestamp
                        where session_id = :session_id and is_seed = 1
                        """,
                        nickname=nickname,
                        persona_name=persona,
                        answer_text=answer,
                        embedding_parameters=db_embedding_parameters(),
                        embedding_provider=DB_EMBED_PROVIDER,
                        embedding_model=DB_EMBED_MODEL,
                        embedding_region=DB_EMBED_REGION,
                        session_id=f"seed-{index:02d}",
                    )
                connection.commit()
                cursor.execute(
                    """
                    select count(*), min(vector_dimension_count(answer_vector_v4))
                    from mio_demo_sessions
                    where is_seed = 1 and answer_vector_v4 is not null
                    """
                )
                count, dimension = cursor.fetchone()
        if int(count) < len(SEED_PARTICIPANTS) or int(dimension) != DB_EMBED_DIMENSION:
            raise RuntimeError(
                f"seed supervisor migration failed: count={count} dimension={dimension}"
            )
        print(
            "Supervisor survey seeds ready — "
            f"count={count} model={DB_EMBED_MODEL} dimension={dimension}"
        )
    finally:
        repository.close()


if __name__ == "__main__":
    main()
