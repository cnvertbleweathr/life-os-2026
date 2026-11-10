-- Mart: per kid per title — times read, first/last read, rank by re-reads.

{{ config(materialized='view') }}

select
    kid_id,
    title_key,
    arg_max(title, read_date)   as title,
    arg_max(author, read_date)  as author,
    count(*)                    as times_read,
    min(read_date)              as first_read,
    max(read_date)              as last_read,
    row_number() over (partition by kid_id order by count(*) desc, max(read_date) desc) as rank_by_reads
from {{ ref('stg_progeny__books') }}
group by kid_id, title_key
order by kid_id, rank_by_reads
