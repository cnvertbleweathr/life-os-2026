/**
 * lib/api.ts — typed client for the ONS FastAPI backend.
 *
 * Every type here reflects the CONFIRMED response shapes from
 * API_STATE_REFERENCE.md (verified 2026-06-19 against live data), not
 * the original artifact design. Nullable fields are marked nullable
 * because they are genuinely null in real responses — don't "fix" that
 * by defaulting away the null in a type definition.
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${path} returned ${res.status}`);
  }
  return res.json();
}

// ── Shared / cross-cutting types ──────────────────────────────────────────────

export interface Goal {
  domain: string;
  goal_key: string;
  goal_value_type: string;
  target_numeric: number | null;
  current_value: number | null;
  progress_percent: number | null;
  pace_status?: string | null;
  label: string;
  description?: string | null;
}

// ── Home ─────────────────────────────────────────────────────────────────────

export interface HomeSummary {
  date: string;
  stat_cards: {
    weekly_miles: number;
    weekly_runs: number;
    ytd_miles: number;
    habits_done: number;
    habits_total: number;
    books_read: number;
  };
  // NOTE: date format here is "Jun 20" style — different from
  // /home/calendar's "YYYY-MM-DD". Do not unify; render as-is.
  calendar: { date: string; title: string }[];
  wod: {
    date: string;
    url: string;
    text: string;
    movements: string[];
    fetched_ok: boolean;
  } | null;
  daily10: {
    date: string;
    playlist_id: string;
    updated_at_utc: string;
    description: string;
    tewnidge_artists: string[];
  } | null;
  picks: unknown[];
  goals: Goal[];
  streams: {
    fetched_at: string;
    my_teams: unknown[];
    top5: unknown[];
    popular: unknown[];
  } | null;
}

export interface CalendarEvent {
  date: string; // YYYY-MM-DD here — differs from /summary's embedded calendar
  title: string;
}

export const homeApi = {
  summary: () => get<HomeSummary>("/home/summary"),
  calendar: () => get<CalendarEvent[]>("/home/calendar"),
};

// ── Habits ───────────────────────────────────────────────────────────────────

export interface HabitToday {
  date: string;
  habits: { key: string; label: string; done: boolean }[];
  done_count: number;
  total_count: number;
}

export interface HabitStreak {
  habit: string;
  current_streak: number;
  longest_streak: number;
  // last_done_date intentionally does not exist — don't add it back
}

export const habitsApi = {
  today: () => get<HabitToday>("/habits/today"),
  streaks: () => get<HabitStreak[]>("/habits/streaks"),
};

// ── Fitness ──────────────────────────────────────────────────────────────────

export interface FitnessSummary {
  running_summary: {
    total_miles: number;
    total_runs: number;
    avg_pace_min_mile: number;
    ytd_miles: number;
  };
  recent_runs: {
    run_date: string; // full ISO timestamp, not just a date
    miles: number;
    minutes: number;
    pace: number;
  }[];
  weekly_miles: { week: string; miles: number }[];
}

export const fitnessApi = {
  summary: () => get<FitnessSummary>("/fitness/summary"),
};

// ── Reading ──────────────────────────────────────────────────────────────────

export interface ReadingSummary {
  books_read: number;
  fiction_books: number;
  nonfiction_books: number;
  // pages_read / avg_days_to_finish do not exist upstream — don't re-add
}

export const readingApi = {
  summary: () => get<ReadingSummary>("/reading/summary"),
  // Always returns [] today — no "currently reading" data source exists.
  // Calling this is fine; just don't build UI that assumes it populates.
  inProgress: () => get<unknown[]>("/reading/in-progress"),
};

// ── Goals ────────────────────────────────────────────────────────────────────

export interface GoalDomainGroup {
  domain: string;
  goals: Goal[];
}

export const goalsApi = {
  progress: () => get<Goal[]>("/goals/progress"),
  // Confirmed shape (2026-06-20): array of { domain, goals } objects,
  // NOT a dictionary keyed by domain name. Don't "fix" this back to
  // Record<string, Goal[]> without re-checking the live endpoint first.
  byDomain: () => get<GoalDomainGroup[]>("/goals/by-domain"),
};

// ── Music ────────────────────────────────────────────────────────────────────

export const musicApi = {
  // Both confirmed empty in testing as of last check — render empty state,
  // not an error state, when these come back [].
  topArtists: () => get<unknown[]>("/music/top-artists"),
  news: () => get<unknown[]>("/music/news"),
};

// ── Shows ────────────────────────────────────────────────────────────────────

export interface ShowsSummary {
  total: number;
  my_artist_count: number; // noisy — substring matching, don't present as precise
  venues: number;
  next_show: { title: string; date: string; venue: string } | null;
}

export interface Show {
  title: string;
  venue_name: string;
  ticket_url: string;
  source: "AEG" | "Ticketmaster";
  is_my_artist: boolean;
  date: string; // YYYY-MM-DD
}

export const showsApi = {
  summary: () => get<ShowsSummary>("/shows/summary"),
  list: (myArtistsOnly = false) =>
    get<Show[]>(`/shows${myArtistsOnly ? "?my_artists_only=true" : ""}`),
  myShows: () => get<unknown[]>("/shows/my-shows"),
};

// ── Sports ───────────────────────────────────────────────────────────────────

export const sportsApi = {
  // Needs NEWS_API_KEY server-side — [] is expected, not a bug, until set.
  news: () => get<unknown[]>("/sports/news"),
};

// ── CFB ──────────────────────────────────────────────────────────────────────

export interface CfbTeam {
  team: string;
  tier: string;
  win_rate: number; // already a percent (e.g. 68.2), NOT a 0-1 fraction
  roi_pct: number;  // already a percent (e.g. 29.91) — confirmed 2026-06-20
  seasons_profitable: number;
  total_bets: number; // really a count of games, not literal bets — label accordingly in UI
}

export interface CfbTeamDetail {
  profile: Record<string, unknown> & { season_rois_json?: string };
  recent_games: unknown[];
  advanced_stats: Record<string, unknown>;
}

export interface CfbRecruitingYear {
  season: number;
  weighted_talent: number;
  weighted_rank: number;
  talent_percentile: number;
  single_year_points: number;
  single_year_rank: number;
}

export const cfbApi = {
  teams: () => get<CfbTeam[]>("/cfb/teams"),
  team: (team: string) => get<CfbTeamDetail>(`/cfb/team/${encodeURIComponent(team)}`),
  gameContext: (gameId: string | number) =>
    get<Record<string, unknown>>(`/cfb/game-context/${gameId}`),
  recruiting: (team: string) =>
    get<CfbRecruitingYear[]>(`/cfb/recruiting/${encodeURIComponent(team)}`),
  modelInfo: () => get<Record<string, unknown>>("/cfb/model-info"),
  // Does NOT include game_id in response today — can't link to game-context
  // detail from this list yet without a backend addition.
  lineAccuracy: () => get<Record<string, unknown>[]>("/cfb/line-accuracy"),
};

/** Parse a team_profiles row's season_rois_json string into an object. */
export function parseSeasonRois(json?: string): Record<string, number> {
  if (!json) return {};
  try {
    return JSON.parse(json);
  } catch {
    return {};
  }
}

// ── KGLW ─────────────────────────────────────────────────────────────────────

export interface KglwShowTag {
  tag: string;
  tag_slug: string;
}

export interface KglwShow {
  show_id:      number;
  show_date:    string; // YYYY-MM-DD
  show_time:    string | null;
  artist:       string; // Note: kglw.net tracks related-artist shows too,
                          // not just King Gizzard — filter on this field
                          // if only-KGLW shows are wanted.
  show_title:   string;
  venue_id:     number;
  venue_name:   string;
  location:     string;
  city:         string;
  state:        string | null;
  country:      string;
  tour_name:    string;
  show_year:    number;
  show_month:   number;
  show_day:     number;
  show_dayname: string;
  show_tags:    KglwShowTag[];
  permalink:    string;
}

export interface KglwSong {
  song_id:         number;
  name:            string;
  slug:            string;
  is_original:     boolean;
  original_artist: string;
  // No times_played / gap / last_played_date — not exposed by KGLW's API
}

export interface KglwVenue {
  venue_id: number;
  name:     string;
  city:     string;
  state:    string | null;
  country:  string;
  capacity: number | null;
  slug:     string;
  // No latitude/longitude — not available from KGLW's API at all
}

export interface KglwJamchartEntry {
  uniqueid:       string;
  show_id:        number;
  song_id:        number;
  song_name:      string;
  show_date:      string;
  venue_name:     string;
  city:           string;
  state:          string | null;
  country:        string;
  footnote:       string | null;
  jamchart_note:  string | null;
  is_recommended: boolean;
  permalink:      string;
}

export interface KglwSummary {
  total_shows:             number;
  total_songs:             number;
  total_venues:            number;
  total_jamchart_entries:  number;
  next_show: {
    show_date:  string;
    venue_name: string;
    city:       string;
    country:    string;
    show_title: string;
  } | null;
}

export const kglwApi = {
  summary: () => get<KglwSummary>("/kglw/summary"),
  shows: (opts?: { upcoming?: boolean; venueId?: number; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.upcoming) params.set("upcoming", "true");
    if (opts?.venueId != null) params.set("venue_id", String(opts.venueId));
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return get<KglwShow[]>(`/kglw/shows${qs ? `?${qs}` : ""}`);
  },
  show: (showId: number) => get<KglwShow | null>(`/kglw/shows/${showId}`),
  onThisDay: () => get<KglwShow[]>("/kglw/shows/on-this-day"),
  songs: (search?: string) =>
    get<KglwSong[]>(`/kglw/songs${search ? `?search=${encodeURIComponent(search)}` : ""}`),
  songShows: (songId: number) =>
    get<KglwJamchartEntry[]>(`/kglw/songs/${songId}/shows`),
  venues: (search?: string) =>
    get<KglwVenue[]>(`/kglw/venues${search ? `?search=${encodeURIComponent(search)}` : ""}`),
  jamchart: (recommendedOnly = false) =>
    get<KglwJamchartEntry[]>(`/kglw/jamchart${recommendedOnly ? "?recommended=true" : ""}`),
};
