#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def migration_blocks() -> list[str]:
    text = (ROOT / "db/migrations/003_mio_rescue.sql").read_text(encoding="utf-8")
    lines = [
        line for line in text.splitlines()
        if not line.lower().startswith(("set ", "whenever ", "prompt "))
    ]
    return [
        block.strip()
        for block in re.split(r"^\s*/\s*$", "\n".join(lines), flags=re.M)
        if block.strip() and block.strip().lower() != "commit;"
    ]


def main() -> None:
    os.environ["MIO_DATA_MODE"] = "adb"
    from app.config import Settings
    from app.database import AdbRepository, db_embedding_parameters
    from app.rescue import (
        CATEGORY_TEMPLATES,
        CHALLENGES,
        EMBEDDING_MODEL,
        GLOBAL_TEMPLATES,
    )

    repository = AdbRepository(Settings())
    try:
        with repository.connection() as connection:
            with connection.cursor() as cursor:
                for block in migration_blocks():
                    cursor.execute(block)

                ideal_count = 0
                for challenge_type, challenge in CHALLENGES.items():
                    for index, ideal_text in enumerate(challenge["ideal"], start=1):
                        key = f"{challenge_type}-ideal-{index}"
                        cursor.execute(
                            """
                            merge into mio_ideal_answers target
                            using (select :ideal_text_key ideal_text_key from dual) source
                            on (target.ideal_text_key = source.ideal_text_key)
                            when matched then update set
                              target.challenge_type = :challenge_type,
                              target.ideal_text = :ideal_text,
                              target.embedding_model = :embedding_model
                            when not matched then insert (
                              challenge_type, ideal_text, ideal_text_key, embedding_model
                            ) values (
                              :challenge_type, :ideal_text, :ideal_text_key, :embedding_model
                            )
                            """,
                            challenge_type=challenge_type,
                            ideal_text=ideal_text,
                            ideal_text_key=key,
                            embedding_model=EMBEDDING_MODEL,
                        )
                        ideal_count += 1

                template_rows: list[tuple[str | None, str, str, int]] = []
                template_rows.extend((None, kind, text, quality) for kind, text, quality in GLOBAL_TEMPLATES)
                for challenge_type, items in CATEGORY_TEMPLATES.items():
                    template_rows.extend((challenge_type, kind, text, quality) for kind, text, quality in items)
                for challenge_type, kind, text, quality in template_rows:
                    digest = hashlib.blake2b(
                        f"{challenge_type}|{kind}|{text}".encode("utf-8"),
                        digest_size=10,
                    ).hexdigest()
                    cursor.execute(
                        """
                        merge into mio_answer_templates target
                        using (select :template_key template_key from dual) source
                        on (target.template_key = source.template_key)
                        when matched then update set
                          target.challenge_type = :challenge_type,
                          target.template_text = :template_text,
                          target.template_kind = :template_kind,
                          target.base_quality = :base_quality,
                          target.is_active = 'Y'
                        when not matched then insert (
                          template_key, challenge_type, template_text,
                          template_kind, base_quality, is_active
                        ) values (
                          :template_key, :challenge_type, :template_text,
                          :template_kind, :base_quality, 'Y'
                        )
                        """,
                        template_key=f"tpl-{digest}",
                        challenge_type=challenge_type,
                        template_text=text,
                        template_kind=kind,
                        base_quality=quality,
                    )

                cursor.execute(
                    """
                    update mio_ideal_answers
                    set ideal_vector = dbms_vector_chain.utl_to_embedding(
                          to_clob(ideal_text), json(:embedding_parameters)
                        ),
                        embedding_model = :embedding_model
                    where ideal_vector is null
                       or embedding_model <> :embedding_model
                    """,
                    embedding_parameters=db_embedding_parameters(),
                    embedding_model=EMBEDDING_MODEL,
                )
                connection.commit()
                challenge_keys = list(CHALLENGES)
                bind_names = ",".join(
                    f":challenge_{index}" for index in range(len(challenge_keys))
                )
                cursor.execute(
                    f"""
                    select count(*),
                           sum(case when ideal_vector is not null then 1 else 0 end),
                           min(vector_dimension_count(ideal_vector))
                    from mio_ideal_answers
                    where challenge_type in ({bind_names})
                    """,
                    {
                        f"challenge_{index}": key
                        for index, key in enumerate(challenge_keys)
                    },
                )
                total, embedded, dimension = cursor.fetchone()
        if int(total) != ideal_count or int(embedded) != ideal_count or int(dimension) != 1536:
            raise RuntimeError(
                f"ideal embedding verification failed: total={total} embedded={embedded} dimension={dimension}"
            )
        print(
            "Mio Rescue migration complete — "
            f"ideal_answers={total} templates={len(template_rows)} dimension={dimension}"
        )
    finally:
        repository.close()


if __name__ == "__main__":
    main()
