set define off
set serveroutput on
whenever sqlerror exit sql.sqlcode

begin
  execute immediate q'[
    alter table mio_demo_sessions add (
      answer_vector_v4   vector(1536, float32),
      embedding_provider varchar2(40),
      embedding_model    varchar2(120),
      embedding_region   varchar2(64),
      embedded_at        timestamp with time zone
    )
  ]';
exception
  when others then
    if sqlcode != -1430 then raise; end if;
end;
/

commit;

prompt MIO_DEMO Embed v4 columns are ready.
