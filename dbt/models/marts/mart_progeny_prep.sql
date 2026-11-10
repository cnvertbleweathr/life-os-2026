-- Mart: baby prep burndown — open tasks per day from the first task to the due
-- date, against an ideal straight line to zero on the due date.
-- Due date: the earliest due_date of a kid not born yet; else the latest task due date.
-- Future days have open_tasks null (only the ideal line). A view: "today" moves.

{{ config(materialized='view') }}

with tasks as (
    select * from {{ ref('stg_progeny__prep_tasks') }}
),

target as (
    select coalesce(
        (select min(due_date) from {{ ref('stg_progeny__kids') }} where not is_born and due_date is not null),
        (select max(due_date) from tasks)
    ) as baby_due_date
),

bounds as (
    select
        (select min(created_date) from tasks) as start_date,
        greatest(t.baby_due_date, current_date) as end_date,
        t.baby_due_date
    from target t
),

days as (
    select cast(d as date) as day, b.start_date, b.baby_due_date
    from bounds b,
         generate_series(b.start_date, b.end_date, interval 1 day) as g(d)
    where b.start_date is not null
),

total as (
    select count(*) as n from tasks
)

select
    d.day,
    d.baby_due_date,
    d.day > current_date                                              as is_future,
    case when d.day <= current_date then
        (select count(*) from tasks t where t.created_date <= d.day) end    as total_tasks,
    case when d.day <= current_date then
        (select count(*) from tasks t where t.done_date <= d.day) end       as done_tasks,
    case when d.day <= current_date then
        (select count(*) from tasks t
          where t.created_date <= d.day and (t.done_date is null or t.done_date > d.day)) end
                                                                      as open_tasks,
    case when d.baby_due_date is not null and d.baby_due_date > d.start_date then
        round(greatest(
            (select n from total) * (1 - date_diff('day', d.start_date, d.day)
                                        / date_diff('day', d.start_date, d.baby_due_date)), 0), 1)
    end                                                               as ideal_open
from days d
order by d.day
