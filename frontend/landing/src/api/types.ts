export type Lang = 'en' | 'hi' | 'mr' | 'bn' | 'ta' | 'te' | 'kn' | 'ml' | 'gu' | 'pa'
export type GateOutcome = 'advise' | 'clarify' | 'escalate' | 'retake'

export interface Farm {
  id: number
  farmer_name: string
  crop: string
  crop_name: string
  photo_diagnosis: boolean
  variety: string | null
  district: string
  village: string | null
  lat: number
  lon: number
  location_source: 'gps' | 'district'
  area_acres: number
  sowing_date: string
  stage: string
  stage_name: string
  das: number
  lang: Lang
  is_demo: boolean
}

export interface TargetView {
  id: string
  crop: string
  kind: string
  tier: string
  name: string
  signature: string
  agent?: string | null
  confidence?: number
  trap_etl?: number | null
}

export interface LadderRung {
  tier: 'cultural' | 'biological' | 'chemical'
  action?: string
  ingredient?: string
  product?: string
  class?: string
  dose?: string
  timing?: string
  verified?: boolean
  label_rule?: string
  for_field?: string
  quantity?: { amount: number; unit: string; water_l: number }
}

export interface Citation {
  title: string
  publisher: string
  url?: string
}

export interface IcarInstitute {
  id: string
  name: string
  city: string
  state: string
  phone?: string
  email?: string
  email_note?: string
}

/** An entry from the ICAR technology repository, linked to our targets. */
export interface IcarTech {
  id: string
  type: 'biocontrol' | 'variety' | 'practice' | 'monitoring' | 'app' | 'reference'
  audience: 'farmer' | 'official'
  short: string
  source_name: string
  summary: string
  claim: string | null
  supply: string | null
  link_reason: string | null
  lead_time_days: number | null
  crops: string[]
  targets: string[]
  institute: IcarInstitute
  for_target?: string | null
}

export interface Advisory {
  target: string
  name: string
  signature: string
  what_to_check: string
  what_to_avoid: string[]
  ladder: LadderRung[]
  expert_trigger: string
  citations: Citation[]
  icar_options: IcarTech[]
}

export interface CaseBrief {
  id: number
  status: string
  reason: string
  queue_position: number
  eta_minutes: number
}

export interface Heatmap {
  grid: number[][]
  rows: number
  cols: number
  method: string
  class: string
}

export interface Gate {
  outcome: GateOutcome
  reason: string
  confidence: number
  threshold: number
  alternatives: TargetView[]
}

export interface DiagnoseResult {
  problem_id: number
  diagnosis_id?: number
  image_url: string | null
  is_stub: boolean
  model_version: string
  heatmap?: Heatmap | null
  prior_bias?: Record<string, number>
  gate: Gate
  message: string
  advisory?: Advisory
  healthy_note?: string
  clarify?: { cue_id: string; question: string; candidates: TargetView[] }
  case?: CaseBrief
  followup?: { id: number; due_on: string }
  /** Set client-side when the Doubt Doctor settled the diagnosis. */
  resolved_by?: { question: string; answer: string }
}

export interface ClarifyResult {
  problem_id: number
  outcome: 'advise' | 'escalate'
  message?: string
  resolved_target?: string
  advisory?: Advisory
  followup?: { id: number; due_on: string }
  case?: CaseBrief
}

export interface AlertView {
  id: number
  farm_id: number
  target: string
  name: string
  crop: string
  tier: string
  trigger: string
  level: 'low' | 'medium' | 'high'
  reason: string
  tasks: string[]
  issued_on: string
  outcome: string | null
  can_photo: boolean
}

export interface WeatherDay {
  on: string
  rh_max: number | null
  t_min: number | null
  t_max: number | null
  rain_mm: number | null
  forecast: boolean
  from_sensor: boolean
}

export interface RainContext {
  subdivision: string
  month: string
  normal_month_mm: number
  expected_to_date_mm?: number
  observed_mm: number | null
  departure_pct?: number
  days?: number
  source?: string
  text?: string
}

export interface ProblemView {
  id: number
  farm_id: number
  status: string
  severity: string
  opened_at: string | null
  target: string | null
  name: string | null
  image_url: string | null
  gate_outcome: GateOutcome | null
  gate_reason: string | null
  confidence: number | null
  is_stub: boolean | null
  advisory_source: string | null
  advisory: Advisory | null
  case: CaseBrief | null
  expert: {
    verdict: string
    final_label: string
    expert_name: string
    notes: string | null
    referred_to_lab: boolean
  } | null
  followup: { id: number; due_on: string; due: boolean } | null
}

export interface Home {
  farm: Farm
  weather: { source: string; fetched_at?: string; days: WeatherDay[] }
  rain_context: RainContext | null
  alerts: AlertView[]
  problems: ProblemView[]
  followups_due: { id: number; problem_id: number; due_on: string; name: string | null }[]
  model: { is_stub: boolean; model_version: string }
}

export interface LabelVerdict {
  code: string
  message: string
  ingredient: string | null
  product: string | null
  is_veto: boolean
  /** 'stop' = known to be wrong here, 'unknown' = no record of it, 'ok' = no objection found. */
  tone: 'stop' | 'unknown' | 'ok'
  /** The heading, from the server: machine-translated only once reviewed. */
  title?: string
  /** No record of this input: the app may fetch an AI note from
   *  /api/labelcheck/note, which never waits the verdict above. */
  note_available?: boolean
  target: string | null
}

export interface TrapReading {
  id: number
  target: string
  trap_type: string
  count: number
  traps: number
  nights: number
  recorded_on: string
  per_trap_night: number
}

export interface CaseListItem extends CaseBrief {
  created_at: string | null
  farm_id: number
  farmer_name: string
  district: string
  crop: string
  severity: string
  photo: string | null
  model_top: TargetView | null
  is_stub: boolean | null
}

export interface CaseBundle {
  case: CaseBrief & { created_at: string | null }
  farm: Farm
  problem: { id: number; severity: string; status: string }
  photos: string[]
  heatmaps: (Heatmap | null)[]
  model: { version: string | null; is_stub: boolean | null; gate_reason: string; hypotheses: TargetView[] }
  doubt_doctor: { question: string; answer: string; cue_id: string }[]
  followups: { due_on: string; response: string | null }[]
  trap_readings: {
    target: string
    recorded_on: string
    count: number
    traps: number
    nights: number
    per_trap_night: number
  }[]
  recent_alerts: AlertView[]
  farm_history: { final_label: string; verdict: string; on: string | null }[]
  candidate_labels: TargetView[]
  icar_referral: IcarTech[]
}

export interface Summary {
  generated_at: string
  includes_demo_data: boolean
  model: { is_stub: boolean; model_version: string }
  totals: {
    farms: number
    diagnoses: number
    open_cases: number
    resolved_cases: number
    confirmed: number
    corrected: number
    field_accuracy: number | null
    alerts_issued: number
    alerts_answered: number
    alerts_found: number
    referred_to_lab: number
  }
  gate_outcomes: Record<string, number>
  escalation_reasons: Record<string, number>
  alerts_by_trigger: Record<string, number>
  by_district: {
    district: string
    farms: number
    confirmed: number
    suspected: number
    open_cases: number
    active_high_alerts: number
  }[]
  top_targets: { target: string; name: string; crop: string; confirmed: number; suspected: number }[]
  accuracy_by_label: { model_label: string; name: string; confirmed: number; corrected: number }[]
}

export interface Hotspots {
  points: {
    problem_id: number
    lat: number
    lon: number
    district: string
    crop: string
    target: string | null
    name: string | null
    status: 'confirmed' | 'suspected' | 'awaiting_expert'
    on: string | null
  }[]
  active_alerts: {
    lat: number
    lon: number
    district: string
    target: string
    name: string
    level: string
    trigger: string
  }[]
  radius_km: number
}

export interface RainfallPanel {
  source: string
  subdivisions: {
    subdivision: string
    reference_place: string
    jjas_normal_mm: number
    current_month: RainContext | null
    jjas_series: [number, number | null, number | null][]
  }[]
}

export interface ModelCard {
  is_stub: boolean
  model_version: string
  backbone?: string
  head?: string
  classes?: string[]
  temperature?: number
  trained_at?: string
  dataset?: string
  split?: { train: number; val: number; test: number }
  test?: { accuracy: number; precision: number; recall: number; f1: number; ece_before: number; ece_after: number }
  gate_on_test?: {
    n: number
    advise_pct: number
    clarify_pct: number
    escalate_pct: number
    accuracy_when_advised: number | null
    clarify_pair_contains_truth: number | null
  }
  benchmark?: { model: string; val_f1: number; accuracy: number; precision: number; recall: number; f1: number }[]
}

export interface CropInfo {
  id: string
  name: string
  photo_diagnosis: boolean
  stages: { key: string; name: string; das: [number, number] }[]
}

export interface PesticideBaseline {
  available: boolean
  state: string
  source: string
  unit_note: string
  chemical: [string, number][]
  bio: [string, number][]
  india_chemical: [string, number][]
  latest_share_pct: number | null
  rank: number | null
  states_ranked: number
}

export interface OutlookRow {
  target: string
  name: string
  crop: string
  farms: number
  districts: string[]
  high: number
  triggers: Record<string, number>
  found: number
  inspected: number
  icar_inputs: IcarTech[]
}

// --- Live field walk ----------------------------------------------------------

export interface LiveRisk {
  target: string
  name: string
  level: 'low' | 'medium' | 'high'
  trigger: string
  reason: string
  check: string[]
  prevention: { avoid: string[]; do: string[]; icar: string[] }
}

export interface LiveContext {
  location: { lat: number; lon: number; source: 'gps' | 'farm'; accuracy_m: number | null; km_from_farm: number; far_from_farm: boolean }
  weather_now: {
    temp_c: number | null; rh_pct: number | null; rain_mm_1h: number | null; wind_kmh: number | null
    text: string | null; station: string | null; source: string; observed_at: string | null
  } | null
  forecast: { days: number; rain_mm: number; rh_max: number | null; t_min: number | null; t_max: number | null; source: string } | null
  soil: {
    ph: { value: number; how: 'measured' | 'card' | 'estimated'; source: string; on: string | null; band: string; soc_g_per_kg?: number | null } | null
    moisture: { value_pct: number; how: 'measured' | 'estimated'; source: string; deeper_pct?: number | null; temp_c?: number | null } | null
  }
  crop: { id: string; name: string; stage: string; stage_name: string; das: number; photo_model: boolean }
  risks: LiveRisk[]
}

export interface LiveGuide {
  step: string | null
  kind?: 'scene' | 'plant' | 'close' | 'base'
  index: number
  total: number
  need?: number
  got?: number
  text?: string
}

export interface LiveFrameReply {
  type: 'frame'
  seq: number
  quality: { ok: boolean; hint: string | null; hint_text: string | null; sharp: number; bright: number; veg: number } | null
  counted: boolean
  advanced: boolean
  live: { top: { target: string; name: string; confidence: number }[] } | null
  guide: LiveGuide
}

export interface LiveFinding {
  target: string
  name: string
  views: number
  strong_views: number
  confidence: number
  problem_id: number
  evidence?: string[]
  advisory?: Advisory
  settled_by_answer?: boolean
  reason?: string
  case?: CaseBrief
}

export interface LiveSummary {
  scan_id: number
  verdict: 'all_good' | 'risk' | 'found' | 'check' | 'unclear' | 'no_model'
  context: LiveContext
  seen: LiveFinding[]
  possible: LiveFinding[]
  expert_case: CaseBrief | null
  stats: { frames: number; good_frames: number; classified_views: number; healthy_views: number; other_crop_views: number }
  model_version: string
  photo_model: boolean
  speech: string
}

// --- Weather, notices and notifications -------------------------------------

export type Severity = 'warning' | 'advice' | 'info'
export type SprayStatus = 'good' | 'caution' | 'avoid'

export interface WeatherAdvisory {
  id: string
  rule: string
  severity: Severity
  category: 'safety' | 'rain' | 'wind' | 'cold' | 'heat' | 'spray' | 'disease' | 'irrigation' | 'fog'
  title: string
  text: string
  do: string[]
  source: string
  valid_until: string
}

export interface WeatherNow {
  time: string | null
  temp: number | null
  feels: number | null
  rh: number | null
  dew: number | null
  precip: number | null
  prob_3h: number | null
  wind: number | null
  gust: number | null
  wdir: number | null
  uv: number | null
  uv_band: 'low' | 'moderate' | 'high' | 'very_high' | 'extreme' | null
  cloud: number | null
  vis: number | null
  pressure: number | null
  pressure_trend_24h: number | null
  code: number | null
  is_day: number | null
  station: string | null
}

export interface WeatherHour {
  t: string
  temp: number | null
  rh: number | null
  prob: number | null
  precip: number | null
  wind: number | null
  gust: number | null
  wdir: number | null
  uv: number | null
  cloud: number | null
  vis: number | null
  code: number | null
  is_day: number | null
  spray: SprayStatus
}

export interface WeatherDay {
  on: string
  tmin: number | null
  tmax: number | null
  rain: number | null
  prob: number | null
  rain_hours: number | null
  wind_max: number | null
  gust_max: number | null
  wdir: number | null
  uv_max: number | null
  sunshine_h: number | null
  radiation: number | null
  et0: number | null
  code: number | null
  sunrise: string | null
  sunset: string | null
}

export interface WaterBalance {
  available: boolean
  days?: number
  kc?: number
  et0_week?: number
  etc_week?: number
  rain_week?: number
  eff_rain_week?: number
  deficit?: number
  deficit_threshold?: number
  et0_today?: number | null
  etc_today?: number | null
  next3_rain?: number
  next3_useful_days?: number
  verdict?: 'irrigate' | 'hold_rain' | 'ok' | 'stop_stage'
}

export interface SprayHour {
  t: string
  status: SprayStatus
  reasons: [string, number | null][]
  wind: number
  gust: number
  prob: number
  temp: number | null
  reasons_text?: string | null
}

export interface WeatherView {
  /** Rain INSAT-3DS measured at this spot in the last 24 h (MOSDAC, ISRO). */
  sat_rain?: { mm: number; hours: number; coverage: number; latest: string; source: string } | null
  fetched_at: string
  stale: boolean
  source: { forecast: string; current: string | null; soil: string | null; et0: string }
  current: WeatherNow
  hourly: WeatherHour[]
  daily: WeatherDay[]
  soil: {
    temp_surface: number | null
    temp_6cm: number | null
    moisture: { depth: string; pct: number | null }[]
    ph: { value: number; how: 'measured' | 'card' | 'estimated'; source: string; on?: string | null; band: string } | null
  } | null
  water: WaterBalance
  spray: { now: SprayHour | null; windows: { start: string; end: string; hours: number; wind: number }[]; reasons_text: string | null }
  advisories: WeatherAdvisory[]
  crop: { id: string; name: string; stage: string; stage_name: string; das: number; kc: number | null }
  watch_for: { target: string; name: string; level: 'high' | 'medium' | 'low' }[]
  location: { lat: number; lon: number; district: string }
  seasonal: { group: string; name: string; targets: string[]; district_calls_this_month: number; state_share_this_month: number; calls: number }[]
}

export interface KccPanel {
  available: boolean
  month: number
  note: string
  source: string
  years: [number, number]
  coverage: Record<string, { calls: number; matched: number; matched_pct: number }>
  groups: {
    id: string; crop: string; label: string; calls: number; month_share: Record<string, number>; peak_months: number[]
    by_year: Record<string, number>; targets: string[]; target_names: string[]
    top_districts: { district: string; calls: number }[]; expected_this_month: number
  }[]
}

export interface NoticeItem extends WeatherAdvisory {
  notice_id: number
  created_at: string
  read: boolean
  active: boolean
}

export interface LiveEvent {
  type: 'notice' | 'alert'
  id: number
  severity: Severity
  title: string
  body: string
  url: string
}

export type EmailPref = 'warnings' | 'all' | 'digest' | 'off'

export interface Contact {
  email: string | null
  email_pref: EmailPref
  phones: number
  email_delivery: 'live' | 'outbox'
}

export interface NdviScene { on: string; mean: number; p25: number; p75: number; source: string; cloud: number }
export interface SatelliteView {
  available: boolean
  reason?: string
  latest?: NdviScene
  previous?: NdviScene | null
  change?: number | null
  days_between?: number | null
  band?: 'sparse' | 'low' | 'moderate' | 'dense'
  drop?: boolean
  age_days?: number
  series?: NdviScene[]
  soil?: { moisture_pct: number; t0_c: number; t10_c: number; observed_at: string } | null
  polygon_ha?: number
  source?: string
}

// --- Sign-in -----------------------------------------------------------------

export type Role = 'farmer' | 'expert'
export type Irrigation = 'rainfed' | 'canal' | 'borewell' | 'open_well' | 'farm_pond' | 'drip' | 'sprinkler'

export interface Me {
  id: number
  role: Role
  name: string
  phone: string | null
  email: string | null
  lang: Lang
  is_demo: boolean
  farm_ids?: number[]
  profile: {
    state?: string | null
    district?: string
    taluka?: string | null
    village?: string | null
    total_land_acres?: number | null
    designation?: string
    designation_name?: string
    organisation?: string
    districts?: string[]
    crops?: string[]
    specialities?: string[]
    languages?: Lang[]
    verified?: boolean
    experience_years?: number
  } | null
}

export interface OtpSent {
  challenge_id: string
  channel: 'email'
  sent_to: string
  expires_in: number
  resend_in: number
  digits: number
}

export interface AuthOptions {
  districts: string[]
  crops: { id: string; name: string }[]
  languages: { code: Lang; name: string }[]
  irrigation: Irrigation[]
  designations: { id: string; name: string }[]
  qualifications: { id: string; name: string }[]
  specialities: { id: string; name: string }[]
  otp: { digits: number; minutes: number; channel: 'email' }
  demo_login: boolean
}

// --- Krishi, the in-app helper -------------------------------------------------

export interface KrishiChip {
  id: string
  text: string
}

export interface KrishiAnswer {
  topic: string | null
  score: number
  text: string
  steps: string[]
  go: { to: string; label: string }[]
  suggestions: KrishiChip[]
}

// --- Where the farm is ---------------------------------------------------------

export interface StatePlaces {
  name: string
  districts: { name: string; local: string | null }[]
}

export interface PlaceHit {
  name: string
  taluka: string | null
  district: string | null
  state: string | null
  lat: number
  lon: number
}
