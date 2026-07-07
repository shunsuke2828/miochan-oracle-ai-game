set define off
set serveroutput on
whenever sqlerror exit sql.sqlcode

begin
  execute immediate q'[
    alter table mio_demo_sessions
    add (ranking_consent number(1) default 0 not null)
  ]';
exception
  when others then
    if sqlcode != -1430 then raise; end if;
end;
/

update mio_demo_sessions
set ranking_consent = 0
where ranking_consent is null;

commit;
