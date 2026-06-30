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
    // Relative path written by spotify_daily10_decorate.py once it saves
    // a local copy of the generated cover (e.g. "covers/2026-06-24.jpg").
    // Same field/served via the same /music/daily10/cover endpoint as
    // the Music page — only present for runs after the local-save fix
    // shipped (2026-06-24).
    cover_image_path?: string;
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

/** Confirmed real shape from /fitness/run-days, sourced directly from
 *  strava.activities (is_run boolean, no artificial date/row cap --
 *  unlike FitnessSummary.recent_runs, which is capped server-side to
 *  the last 30 days / 10 rows). One row per run; multiple runs on the
 *  same calendar date are NOT pre-aggregated here. */
export interface RunDay {
  strava_id: number;
  start_date: string;
  distance_miles: number;
  moving_time_s: number;
}

export const fitnessApi = {
  summary: () => get<FitnessSummary>("/fitness/summary"),
  crossfit: (limit = 200) => get<CrossfitEntry[]>(`/fitness/crossfit?limit=${limit}`),
  prs: () => get<CrossfitEntry[]>("/fitness/prs"),
  runDays: (year: number) => get<RunDay[]>(`/fitness/run-days?year=${year}`),
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
  // Relative path written by spotify_daily10_decorate.py once it saves
  // a local copy of the generated cover (e.g. "covers/2026-06-24.jpg").
  // Only present for runs after the local-save fix shipped — older
  // daily10_latest.json entries won't have this field at all, which is
  // an expected gap (no image was ever saved for those days), not a bug.
  cover_image_path?: string;
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
  // Confirmed fixed 2026-06-24 — the bug was top_artists()/top_tracks()
  // in api/routers/music.py referencing raw Spotify export field names
  // (master_metadata_album_artist_name, etc) instead of the actual
  // streams_clean.csv columns (artist_name, track_name, played_at).
  // Not a data gap — verified real artists/tracks return correctly now.
  topArtists: (limit = 20) => get<TopArtist[]>(`/music/top-artists?limit=${limit}`),
  topTracks: (limit = 20) => get<TopTrack[]>(`/music/top-tracks?limit=${limit}`),
  // Real shape confirmed from api/routers/music.py — same NewsAPI
  // pattern as sportsApi.news(), just a different query
  // ("music OR album OR concert OR tour"). [] means NEWS_API_KEY isn't
  // set, not a bug.
  news: () => get<NewsArticle[]>("/music/news"),
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

export interface CfbMatchupRequest {
  home_team: string;
  away_team: string;
  spread: number; // negative = home favored
  over_under?: number;
  season?: number;
}

export interface CfbCoachH2H {
  home_record: number;
  away_record: number;
  total: number;
  leader: string;
  trend: string;
}

/** Confirmed real shape from /cfb/matchup-lab, verified against live
 *  output 2026-06-22 (Georgia/Alabama 2024 test case). */
export interface CfbMatchupResult {
  matchup: string;
  bet: string;
  model_score: number;
  edges: string[];
  n_edges: number;
  warnings: string[];
  ppa_gap: number | null;
  sp_gap: number | null;
  ret_gap: number | null;
  recruiting_gap: number | null;
  home_coach: string | null;
  away_coach: string | null;
  coach_h2h: CfbCoachH2H | null;
  spread: number;
  over_under: number | null;
  season: number;
  // True only if model_score >= 70 AND n_edges >= 4 -- the same bar
  // generate_picks.py uses to decide whether a real game is worth
  // publishing as a weekly pick. A matchup can have a real, populated
  // model_score and still have meets_publish_bar: false -- that's the
  // model correctly saying "no strong signal here," not missing data.
  meets_publish_bar: boolean;
}

/** Returned instead of CfbMatchupResult when cfbd.advanced_stats has no
 *  row for one or both teams in the required prior season -- a genuine
 *  data gap, distinct from a low/zero model_score. */
export interface CfbMatchupError {
  error: string;
  message: string;
}

/** Confirmed real shape from /cfb/schedule, built from cfbd_pipeline.py's
 *  own /games field mapping (id, startDate, homeTeam, awayTeam, etc). */
export interface CfbScheduleGame {
  game_id: number;
  season: number;
  week: number;
  start_date: string | null;
  neutral_site: boolean;
  conference_game: boolean;
  home_team: string;
  home_conference: string | null;
  away_team: string;
  away_conference: string | null;
}

/** Confirmed real shape written by scripts/generate_picks.py into
 *  data/bets/todays_picks.json, served by GET /cfb/picks (filtered to
 *  model_score >= min_score, sorted descending) and read by the CFB
 *  page's always-visible PicksList.
 *
 *  bet_type "FADE_TIER_RISK" (renamed from "FADE" 2026-06-29) means the
 *  bet IS on a team whose own historical tier is STRONG_FADE in this
 *  situation -- it is a risk label on the bet, not a different bet. The
 *  prior "FADE" value corresponded to a real bug where bet_team was
 *  silently reassigned to the opposite side from whatever score_game()
 *  actually scored, so the displayed model_score/edges described a team
 *  other than the one being recommended. `bet` always names which side
 *  to actually take, and that side is always the one score_game() scored
 *  -- no exceptions, now. */
export interface CfbPick {
  matchup: string;
  bet: string;
  line: string;
  sport: string;
  edge: string;
  model_score: number;
  stars: string;
  week: number | string;
  // Added alongside the always-visible PicksColumn so the frontend can
  // compare a selected (season, week) against what these picks were
  // actually generated for. Optional because picks files written before
  // this field existed won't have it -- treat a missing season as
  // "can't confirm this matches the selected week," not as season 0.
  season?: number;
  ou: string;
  ppa_gap: number | null;
  sp_gap: number | null;
  bet_type: "EDGE" | "FADE_TIER_RISK";
  generated_at: string;
  ret_gap?: number | null;
  recruiting_gap?: number | null;
  travel_miles?: number | null;
  travel_bucket?: string | null;
  home_coach?: string | null;
  away_coach?: string | null;
  coach_h2h?: CfbCoachH2H | null;
  n_edges: number;
  warnings: string[];
}

/** Confirmed real shape from GET /cfb/picks/summary. Returns {count: 0}
 *  with no other keys when todays_picks.json is empty/missing — the
 *  other fields are only present when count > 0. */
export interface CfbPicksSummary {
  count: number;
  avg_score?: number;
  week?: number | string | null;
  season?: number | string | null;
}

/** Real season-level aggregates from main_marts.mart_live_picks, backing
 *  the site-wide Live Tracker banner. win_rate_pct/total_pnl/roi_pct are
 *  null (not 0) when graded_picks is 0 -- there's a real difference
 *  between "0% win rate" and "no graded picks yet," and the banner
 *  should render an em-dash for the latter, not a misleading 0%. */
export interface CfbLiveTracker {
  season: number;
  graded_picks: number;
  wins: number;
  losses: number;
  pushes: number;
  win_rate_pct: number | null;
  total_pnl: number | null;
  roi_pct: number | null;
  pending_picks: number;
}

export const cfbApi = {
  // min_score defaults to 70 server-side too (api/routers/cfb.py) --
  // passed explicitly here so the client's default is self-documenting
  // and doesn't silently drift from the server's if either changes.
  picks: (minScore = 70) =>
    get<CfbPick[]>(`/cfb/picks?min_score=${minScore}`),
  picksSummary: () => get<CfbPicksSummary>("/cfb/picks/summary"),
  liveTracker: (season?: number) =>
    get<CfbLiveTracker>(`/cfb/live-tracker${season ? `?season=${season}` : ""}`),
  teams: () => get<CfbTeam[]>("/cfb/teams"),
  team: (team: string) =>
    get<CfbTeamDetail>(`/cfb/team/${encodeURIComponent(team)}`),
  gameContext: (gameId: string | number) =>
    get<Record<string, unknown>>(`/cfb/game-context/${gameId}`),
  recruiting: (team: string) =>
    get<CfbRecruitingYear[]>(`/cfb/recruiting/${encodeURIComponent(team)}`),
  modelInfo: () => get<Record<string, unknown>>("/cfb/model-info"),
  lineAccuracy: () => get<Record<string, unknown>[]>("/cfb/line-accuracy"),
  schedule: (season: number, week: number) =>
    get<CfbScheduleGame[]>(`/cfb/schedule?season=${season}&week=${week}`),
  matchupLab: async (
    req: CfbMatchupRequest
  ): Promise<CfbMatchupResult | CfbMatchupError> => {
    const res = await fetch(`${API_BASE}/cfb/matchup-lab`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
      cache: "no-store",
    });
    if (!res.ok) {
      throw new Error(`API /cfb/matchup-lab returned ${res.status}`);
    }
    return res.json();
  },
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

export interface KglwYoutubeMatch {
  video_id: string;
  title: string;
  published_at: string;
  show_id: number;
  show_date: string;
  venue_name: string;
  city: string;
  country: string;
  tour_year: number;
  night_number: number | null;
  match_confidence: "high" | "medium" | "low";
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
    const mapped = shows.map((s) => ({
      ...s,
      id: s.show_id,
      date: s.show_date,
      venue: s.venue_name,
      tour: s.tour_name,
      upcoming: false, // no reliable upcoming flag from API
      videoId: null as string | null,
    }));

    // Populate real videoId from mart_kglw_youtube_matches — built by
    // matching the official YouTube channel's uploads against kglw.shows
    // directly, since kglw.net's own links/show/{id} endpoint is broken
    // server-side (confirmed 2026-06-22 — returns a raw PHP exception as
    // the response body for every show). This mart has no dependency on
    // that endpoint at all.
    //
    // Degrades silently to videoId: null on any failure — a missing
    // endpoint or empty mart isn't an error, it's the same honest "no
    // recording" state the page has always shown.
    try {
      const ids = mapped.map((s) => s.show_id).filter(Boolean);
      if (ids.length > 0) {
        const matches = await get<KglwYoutubeMatch[]>(`/kglw/youtube-matches?show_ids=${ids.join(",")}`);
        const byShowId = new Map(matches.map((m) => [m.show_id, m.video_id]));
        for (const s of mapped) {
          s.videoId = byShowId.get(s.show_id) ?? null;
        }
      }
    } catch {
      // Endpoint not deployed yet, or mart hasn't been built — leave videoId null.
    }

    return mapped;
  },
  show: (showId: number) => get<KglwShow | null>(`/kglw/shows/${showId}`),
  onThisDay: () => get<KglwShow[]>("/kglw/shows/on-this-day"),
  // Per-show YouTube match — used by the show detail panel as a
  // fallback/refresh if the bulk fetch in shows() didn't have this show.
  youtubeMatch: (showId: number) =>
    get<KglwYoutubeMatch[]>(`/kglw/youtube-matches?show_ids=${showId}`).catch(() => []),
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
