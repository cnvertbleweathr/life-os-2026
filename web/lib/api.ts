/**
 * lib/api.ts — typed client for the ONS FastAPI backend.
 *
 * Every type here reflects the CONFIRMED response shapes from
 * API_STATE_REFERENCE.md (verified 2026-06-19 against live data).
 * Types added for the Almanac UI revamp (2026-06-21) are marked.
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
  date: string;
  title: string;
}

export const homeApi = {
  summary: () => get<HomeSummary>("/home/summary"),
  calendar: () => get<CalendarEvent[]>("/home/calendar"),
};

// ── Habits ───────────────────────────────────────────────────────────────────

/** Almanac revision: flattened habit item for the new Habits page */
export interface HabitItem {
  key: string;
  label: string;
  done: boolean;
}

export interface HabitToday {
  date: string;
  habits: HabitItem[];
  done_count: number;
  total_count: number;
}

export interface HabitStreak {
  habit: string;
  current_streak: number;
  longest_streak: number;
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
    run_date: string;
    miles: number;
    minutes: number;
    pace: number;
  }[];
  weekly_miles: { week: string; miles: number }[];
}

export interface CrossfitEntry {
  date: string;
  title: string;
  barbell_lift: string | null;
  best_result_raw: number | null;
  best_result_unit: string | null;
  is_pr: boolean;
}

export const fitnessApi = {
  summary: () => get<FitnessSummary>("/fitness/summary"),
  crossfit: (limit = 200) => get<CrossfitEntry[]>(`/fitness/crossfit?limit=${limit}`),
  prs: () => get<CrossfitEntry[]>("/fitness/prs"),
};

// ── Reading ──────────────────────────────────────────────────────────────────

export interface ReadingSummary {
  books_read: number;
  fiction_books: number;
  nonfiction_books: number;
}

export interface BookRead {
  title: string;
  authors: string;
  classification: string; // "fiction" | "nonfiction" | "unknown"
  finished_date: string; // YYYY-MM-DD
  cached_tags: string;
}

export interface ClassificationCount {
  classification: string;
  books: number;
}

export const readingApi = {
  summary: () => get<ReadingSummary>("/reading/summary"),
  // Confirmed permanently empty — hardcover.books_read has no status
  // column, only finished books with marked_read_at. Don't build UI
  // that assumes this populates without a pipeline change.
  inProgress: () => get<unknown[]>("/reading/in-progress"),
  read: (year?: number, limit = 50) =>
    get<BookRead[]>(`/reading/read${year ? `?year=${year}&limit=${limit}` : `?limit=${limit}`}`),
  byClassification: (year?: number) =>
    get<ClassificationCount[]>(`/reading/by-classification${year ? `?year=${year}` : ""}`),
};

// ── Goals ────────────────────────────────────────────────────────────────────

export interface GoalDomainGroup {
  domain: string;
  goals: Goal[];
}

export const goalsApi = {
  progress: () => get<Goal[]>("/goals/progress"),
  byDomain: () => get<GoalDomainGroup[]>("/goals/by-domain"),
};

// ── Music ────────────────────────────────────────────────────────────────────

export interface MusicSummary {
  minutes_ytd: number | null;
  goal_minutes: number | null;
  days_listened: number | null;
  unique_artists: number | null;
  unique_tracks: number | null;
  top_artist: string | null;
  progress_pct: number | null;
}

export interface MusicDaily10 {
  available: boolean;
  date?: string;
  playlist_id?: string;
  updated_at_utc?: string;
  description?: string;
  tewnidge_artists?: string[];
}

export interface TopArtist {
  artist: string;
  minutes: number;
}

export interface TopTrack {
  track: string;
  artist: string;
  minutes: number;
}

export const musicApi = {
  summary: () => get<MusicSummary>("/music/summary"),
  daily10: () => get<MusicDaily10>("/music/daily10"),
  // Confirmed broken upstream as of 2026-06-20 — always returns [] and the
  // root cause hasn't been found yet (possibly streams_clean.csv missing
  // a current-year row). Don't treat [] here as "pipeline hasn't run";
  // it's a known open bug, not an expected empty state. See ROADMAP.md.
  topArtists: (limit = 20) => get<TopArtist[]>(`/music/top-artists?limit=${limit}`),
  topTracks: (limit = 20) => get<TopTrack[]>(`/music/top-tracks?limit=${limit}`),
  news: () => get<unknown[]>("/music/news"),
};

// ── Shows ────────────────────────────────────────────────────────────────────

export interface ShowsSummary {
  total: number;
  my_artist_count: number;
  venues: number;
  next_show: { title: string; date: string; venue: string } | null;
}

export interface Show {
  title: string;
  venue_name: string;
  ticket_url: string;
  source: "AEG" | "Ticketmaster";
  is_my_artist: boolean;
  date: string;
  // Almanac aliases for easier use in the new pages
  venue?: string;   // alias for venue_name, populated by the wrapper
}

export const showsApi = {
  summary: async (): Promise<ShowsSummary & {
    total_shows: number;
    venue_count: number;
  }> => {
    const s = await get<ShowsSummary>("/shows/summary");
    return {
      ...s,
      total_shows: s.total,
      venue_count: s.venues,
    };
  },
  list: async (myArtistsOnly = false): Promise<Show[]> => {
    const shows = await get<Show[]>(
      `/shows${myArtistsOnly ? "?my_artists_only=true" : ""}`
    );
    return shows.map((s) => ({ ...s, venue: s.venue_name }));
  },
  myShows: () => get<unknown[]>("/shows/my-shows"),
};

// ── Sports ───────────────────────────────────────────────────────────────────

export interface StreamMatch {
  id: string;
  title: string;
  category: string;
  popular: boolean;
  home_team: string;
  away_team: string;
  kickoff_utc: string | null;
  kickoff_local: string | null;
  watch_url: string;
  sources: unknown[];
  is_live: boolean;
  team_label?: string; // only present on my_teams entries
}

export interface StreamsToday {
  fetched_at: string | null;
  my_teams: StreamMatch[];
  top5: StreamMatch[];
  popular: StreamMatch[];
}

export interface NewsArticle {
  title: string;
  source: string;
  url: string;
  published: string;
}

export const sportsApi = {
  streams: () => get<StreamsToday>("/sports/streams"),
  // Needs NEWS_API_KEY server-side — [] is expected, not a bug, until set.
  news: (q?: string) => get<NewsArticle[]>(`/sports/news${q ? `?q=${encodeURIComponent(q)}` : ""}`),
};

// ── CFB ──────────────────────────────────────────────────────────────────────

export interface CfbTeam {
  team: string;
  tier: string;
  win_rate: number;
  roi_pct: number;
  seasons_profitable: number;
  total_bets: number;
}

// Real columns confirmed from cfbd.advanced_stats (prior season) — joined
// into /cfb/team/{team}'s "advanced_stats" key. These are the actual
// validated metrics, NOT the fabricated power/sr_edge/pace/coach_change
// fields a prior pass invented to match a design mockup.
export interface CfbAdvancedStats {
  off_ppa: number | null;
  def_ppa: number | null;
  off_success_rate: number | null;
  def_success_rate: number | null;
  def_havoc_total: number | null;
  off_rush_ppa: number | null;
}

export interface CfbTeamDetail {
  profile: Record<string, unknown> & { season_rois_json?: string };
  recent_games: Array<{
    season: number;
    week: number;
    home_team: string;
    away_team: string;
    spread: number | null;
    spread_result: string | null;
    off_ppa_gap: number | null;
    home_conference: string | null;
  }>;
  advanced_stats: CfbAdvancedStats | null;
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
  team: (team: string) =>
    get<CfbTeamDetail>(`/cfb/team/${encodeURIComponent(team)}`),
  gameContext: (gameId: string | number) =>
    get<Record<string, unknown>>(`/cfb/game-context/${gameId}`),
  recruiting: (team: string) =>
    get<CfbRecruitingYear[]>(`/cfb/recruiting/${encodeURIComponent(team)}`),
  modelInfo: () => get<Record<string, unknown>>("/cfb/model-info"),
  lineAccuracy: () => get<Record<string, unknown>[]>("/cfb/line-accuracy"),
};

export interface SeasonRoi {
  season: number;
  roi: number | null;
}

/** Parses team_profiles.season_rois_json — confirmed real shape is a JSON
 *  array of {season, roi} objects (roi nullable when a season had 0 bets),
 *  NOT a {year: roi} map. Always returns an array, never throws. */
export function parseSeasonRois(json?: string | null): SeasonRoi[] {
  if (!json) return [];
  try {
    const parsed = JSON.parse(json);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (r): r is SeasonRoi => r && typeof r.season === "number"
    );
  } catch {
    return [];
  }
}

// ── KGLW ─────────────────────────────────────────────────────────────────────

export interface KglwShowTag {
  tag: string;
  tag_slug: string;
}

export interface KglwShow {
  show_id: number;
  show_date: string;
  show_time: string | null;
  artist: string;
  show_title: string;
  venue_id: number;
  venue_name: string;
  location: string;
  city: string;
  state: string | null;
  country: string;
  tour_name: string;
  show_year: number;
  show_month: number;
  show_day: number;
  show_dayname: string;
  show_tags: KglwShowTag[];
  permalink: string;
  // Almanac aliases mapped for the new explorer
  id?: number;
  date?: string;
  venue?: string;
  tour?: string;
  upcoming?: boolean;
  videoId?: string | null;
}

export interface KglwSong {
  song_id: number;
  name: string;
  slug: string;
  is_original: boolean;
  original_artist: string;
  // Almanac addition
  versions?: number;
}

export interface KglwVenue {
  venue_id: number;
  name: string;
  city: string;
  state: string | null;
  country: string;
  capacity: number | null;
  slug: string;
}

export interface KglwJamchartEntry {
  uniqueid: string;
  show_id: number;
  song_id: number;
  song_name: string;
  show_date: string;
  venue_name: string;
  city: string;
  state: string | null;
  country: string;
  footnote: string | null;
  jamchart_note: string | null;
  is_recommended: boolean;
  permalink: string;
}

export interface KglwSummary {
  total_shows: number;
  total_songs: number;
  total_venues: number;
  total_jamchart_entries: number;
  next_show: {
    show_date: string;
    venue_name: string;
    city: string;
    country: string;
    show_title: string;
  } | null;
}

export const kglwApi = {
  summary: () => get<KglwSummary>("/kglw/summary"),
  shows: async (
    opts?: { upcoming?: boolean; venueId?: number; limit?: number }
  ): Promise<KglwShow[]> => {
    const params = new URLSearchParams();
    if (opts?.upcoming) params.set("upcoming", "true");
    if (opts?.venueId != null) params.set("venue_id", String(opts.venueId));
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const qs = params.toString();
    const shows = await get<KglwShow[]>(`/kglw/shows${qs ? `?${qs}` : ""}`);
    // Map aliases for the Almanac explorer
    return shows.map((s) => ({
      ...s,
      id: s.show_id,
      date: s.show_date,
      venue: s.venue_name,
      tour: s.tour_name,
      upcoming: false, // no reliable upcoming flag from API
      videoId: null,    // no video data from API
    }));
  },
  show: (showId: number) => get<KglwShow | null>(`/kglw/shows/${showId}`),
  onThisDay: () => get<KglwShow[]>("/kglw/shows/on-this-day"),
  songs: async (search?: string): Promise<KglwSong[]> => {
    const songs = await get<KglwSong[]>(
      `/kglw/songs${search ? `?search=${encodeURIComponent(search)}` : ""}`
    );
    // versions isn't exposed — use 0 as placeholder
    return songs.map((s) => ({ ...s, versions: 0 }));
  },
  songShows: (songId: number) =>
    get<KglwJamchartEntry[]>(`/kglw/songs/${songId}/shows`),
  venues: (search?: string) =>
    get<KglwVenue[]>(
      `/kglw/venues${search ? `?search=${encodeURIComponent(search)}` : ""}`
    ),
  jamchart: (recommendedOnly = false) =>
    get<KglwJamchartEntry[]>(
      `/kglw/jamchart${recommendedOnly ? "?recommended=true" : ""}`
    ),
};
