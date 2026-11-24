-- Staging: every Google Calendar event occurrence (scripts/calendar_export.py → calendar.events).
-- 7 days back to 60 days ahead for all calendars, plus the primary calendar's whole year.
-- calendar_kind: primary | birthdays | holidays | other.

with src as (
    {{ select_or_empty('calendar', 'events', [
        ['calendar_id', 'varchar'], ['calendar_name', 'varchar'], ['calendar_kind', 'varchar'],
        ['event_id', 'varchar'], ['title', 'varchar'], ['event_type', 'varchar'],
        ['all_day', 'boolean'], ['start_date', 'date'], ['start_at', 'timestamptz'],
        ['end_at', 'timestamptz'], ['location', 'varchar'], ['status', 'varchar'],
    ]) }}
)

select
    'cal:' || calendar_id || ':' || event_id as event_key,
    calendar_id,
    calendar_name,
    calendar_kind,
    event_id,
    trim(title) as title,
    event_type,
    all_day,
    start_date,
    start_at,
    end_at,
    location
from src
where coalesce(trim(title), '') <> ''
