set define off
set serveroutput on
whenever sqlerror exit sql.sqlcode

begin
  execute immediate q'[
    create table mio_demo_sessions (
      session_id       varchar2(64) primary key,
      nickname         varchar2(120) not null,
      public_consent   number(1) default 0 not null,
      ranking_consent  number(1) default 0 not null,
      persona_name     varchar2(120),
      answer_text      varchar2(2000),
      answer_vector    vector(1024, float32),
      answer_vector_v4 vector(1536, float32),
      embedding_provider varchar2(40),
      embedding_model  varchar2(120),
      embedding_region varchar2(64),
      embedded_at      timestamp with time zone,
      is_seed          number(1) default 0 not null,
      created_at       timestamp with time zone default systimestamp not null,
      expires_at       timestamp with time zone
    )
  ]';
exception
  when others then
    if sqlcode != -955 then raise; end if;
end;
/

begin
  execute immediate q'[
    create table mio_demo_messages (
      message_id       number generated always as identity primary key,
      session_id       varchar2(64) not null,
      role_name        varchar2(20) not null,
      content_text     clob not null,
      source_labels    varchar2(2000),
      latency_ms       number,
      created_at       timestamp with time zone default systimestamp not null,
      constraint mio_demo_msg_session_fk foreign key (session_id)
        references mio_demo_sessions(session_id) on delete cascade
    )
  ]';
exception
  when others then
    if sqlcode != -955 then raise; end if;
end;
/

begin
  execute immediate q'[
    create table mio_demo_metrics (
      metric_id        number generated always as identity primary key,
      event_name       varchar2(80) not null,
      session_id       varchar2(64),
      duration_ms      number,
      success_flag     number(1) default 1 not null,
      created_at       timestamp with time zone default systimestamp not null
    )
  ]';
exception
  when others then
    if sqlcode != -955 then raise; end if;
end;
/

begin
  execute immediate q'[
    create table mio_demo_business_metrics (
      metric_key       varchar2(40) primary key,
      metric_label     varchar2(120) not null,
      metric_value     number not null,
      unit_name        varchar2(40) not null,
      period_label     varchar2(80) not null,
      display_order    number default 0 not null,
      updated_at       timestamp with time zone default systimestamp not null
    )
  ]';
exception
  when others then
    if sqlcode != -955 then raise; end if;
end;
/

begin
  execute immediate q'[
    create table mio_demo_customers (
      customer_key     varchar2(40) primary key,
      customer_name    varchar2(120) not null,
      health_score     number not null,
      usage_change_pct number not null,
      open_tickets     number not null,
      renewal_days     number not null,
      updated_at       timestamp with time zone default systimestamp not null
    )
  ]';
exception
  when others then
    if sqlcode != -955 then raise; end if;
end;
/

merge into mio_demo_business_metrics target
using (
  select 'REVENUE' metric_key, '今月の売上' metric_label, 1.28 metric_value,
         '億円' unit_name, '前月比 +8.4%' period_label, 1 display_order from dual
  union all
  select 'CHURN', '解約率', 2.1, '%', '前月比 -0.4pt', 2 from dual
  union all
  select 'MRR', 'MRR', 9640, '万円', '当月', 3 from dual
) source
on (target.metric_key = source.metric_key)
when matched then update set
  target.metric_label = source.metric_label,
  target.metric_value = source.metric_value,
  target.unit_name = source.unit_name,
  target.period_label = source.period_label,
  target.display_order = source.display_order,
  target.updated_at = systimestamp
when not matched then insert (
  metric_key, metric_label, metric_value, unit_name, period_label, display_order
) values (
  source.metric_key, source.metric_label, source.metric_value,
  source.unit_name, source.period_label, source.display_order
);

merge into mio_demo_customers target
using (
  select 'A-CORP' customer_key, 'A社' customer_name, 74 health_score,
         18 usage_change_pct, 2 open_tickets, 46 renewal_days from dual
) source
on (target.customer_key = source.customer_key)
when matched then update set
  target.customer_name = source.customer_name,
  target.health_score = source.health_score,
  target.usage_change_pct = source.usage_change_pct,
  target.open_tickets = source.open_tickets,
  target.renewal_days = source.renewal_days,
  target.updated_at = systimestamp
when not matched then insert (
  customer_key, customer_name, health_score, usage_change_pct,
  open_tickets, renewal_days
) values (
  source.customer_key, source.customer_name, source.health_score,
  source.usage_change_pct, source.open_tickets, source.renewal_days
);

commit;

prompt MIO_DEMO schema is ready.
