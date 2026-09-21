import type {
  AlertView,
  CaseBundle,
  CaseListItem,
  ClarifyResult,
  Contact,
  EmailPref,
  CropInfo,
  DiagnoseResult,
  Farm,
  Home,
  Hotspots,
  KccPanel,
  LabelVerdict,
  LiveSummary,
  KrishiAnswer,
  KrishiChip,
  Lang,
  ModelCard,
  NoticeItem,
  OutlookRow,
  PesticideBaseline,
  ProblemView,
  RainfallPanel,
  Summary,
  TargetView,
  TrapReading,
  SatelliteView,
  SprayHour,
  WeatherView,
  Me,
  OtpSent,
  AuthOptions,
  Role,
  StatePlaces,
  PlaceHit,
} from './types'

/** Fired when a signed-in call comes back 401 (session expired or revoked). */
export const UNAUTHORIZED = 'ar:unauthorized'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError(0, 'offline')
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 401 && !path.startsWith('/api/auth/')) window.dispatchEvent(new Event(UNAUTHORIZED))
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  me: () => req<Me>('/api/auth/me'),
  places: () => req<{ states: StatePlaces[] }>('/api/geo/places'),
  whereAmI: (lat: number, lon: number) =>
    req<{ state: string | null; district: string | null; village: string | null }>(
      `/api/geo/reverse?lat=${lat}&lon=${lon}`),
  findPlace: (q: string) => req<{ results: PlaceHit[] }>(`/api/geo/search?q=${encodeURIComponent(q)}`),

  authOptions: (lang: Lang) => req<AuthOptions>(`/api/auth/options?lang=${lang}`),
  requestOtp: (body: { role: Role; purpose: 'signup' | 'login'; email?: string; phone?: string; identifier?: string; lang: Lang }) =>
    req<OtpSent>('/api/auth/otp', json(body)),
  login: (challengeId: string, code: string, role: Role, lang: Lang) =>
    req<Me>('/api/auth/login', json({ challenge_id: challengeId, code, role, lang })),
  signupFarmer: (body: Record<string, unknown>) => req<Me>('/api/auth/signup/farmer', json(body)),
  signupExpert: (body: Record<string, unknown>) => req<Me>('/api/auth/signup/expert', json(body)),
  demoLogin: (role: Role) => req<Me>('/api/auth/demo', json({ role })),
  logout: () => req<{ signed_out: boolean }>('/api/auth/logout', { method: 'POST' }),

  krishiHello: (lang: Lang, screen: string) =>
    req<{ text: string; suggestions: KrishiChip[] }>(`/api/krishi/hello?lang=${lang}&screen=${screen}`),
  krishiAsk: (body: { text?: string; topic?: string; lang: Lang; screen: string; farm_id?: number | null }) =>
    req<KrishiAnswer>('/api/krishi/ask', json(body)),

  health: () => req<{ status: string; model: { is_stub: boolean }; voice: { configured: boolean } }>('/health'),

  crops: (lang: Lang) => req<CropInfo[]>(`/api/kb/crops?lang=${lang}`),
  targets: (lang: Lang, crop?: string) =>
    req<TargetView[]>(`/api/kb/targets?lang=${lang}${crop ? `&crop=${crop}` : ''}`),
  pesticides: () => req<{ id: string; name: string; class: string }[]>('/api/kb/pesticides'),

  samples: (crop: string) => req<{ url: string; true_class: string; expected: 'advise' | 'clarify' | 'escalate' | 'retake' | null }[]>(`/api/samples?crop=${crop}`),
  farms: (lang: Lang) => req<Farm[]>(`/api/farms?lang=${lang}`),
  createFarm: (body: Record<string, unknown>) => req<Farm>('/api/farms', json(body)),
  setFarmLang: (farmId: number, lang: Lang) =>
    req<Farm>(`/api/farms/${farmId}`, { ...json({ lang }), method: 'PATCH' }),
  setFarmLocation: (farmId: number, lat: number, lon: number, confirmFar = false) =>
    req<Farm>(`/api/farms/${farmId}`, { ...json({ lat, lon, confirm_far: confirmFar }), method: 'PATCH' }),
  home: (farmId: number, lang: Lang) => req<Home>(`/api/farms/${farmId}/home?lang=${lang}`),

  diagnose: (farmId: number, image: Blob, lang: Lang, scenario?: string) => {
    const fd = new FormData()
    fd.append('image', image, 'photo.jpg')
    fd.append('lang', lang)
    if (scenario) fd.append('demo_scenario', scenario)
    return req<DiagnoseResult>(`/api/farms/${farmId}/diagnose`, { method: 'POST', body: fd })
  },
  clarify: (problemId: number, cueId: string, answer: 'yes' | 'no' | 'unknown', lang: Lang) =>
    req<ClarifyResult>(`/api/problems/${problemId}/clarify`, json({ cue_id: cueId, answer, lang })),
  escalate: (problemId: number, lang: Lang) =>
    req<{ case: CaseListItem; message: string }>(`/api/problems/${problemId}/escalate?lang=${lang}`, {
      method: 'POST',
    }),
  problem: (problemId: number, lang: Lang) => req<ProblemView>(`/api/problems/${problemId}?lang=${lang}`),
  problemResult: (problemId: number, lang: Lang) =>
    req<DiagnoseResult>(`/api/problems/${problemId}/result?lang=${lang}`),
  liveSummary: (farmId: number, scanId: number, lang: Lang) =>
    req<LiveSummary>(`/api/farms/${farmId}/live/${scanId}?lang=${lang}`),
  followup: (id: number, response: 'improved' | 'no_change' | 'got_worse', lang: Lang) =>
    req<{ case?: CaseListItem; message?: string }>(`/api/followups/${id}`, json({ response, lang })),

  alerts: (farmId: number, lang: Lang) => req<AlertView[]>(`/api/farms/${farmId}/alerts?lang=${lang}`),
  alertOutcome: (id: number, outcome: 'nothing_found' | 'found' | 'snoozed', lang: Lang) =>
    req<{ case?: CaseListItem; message?: string; problem_id?: number }>(
      `/api/alerts/${id}/outcome`,
      json({ outcome, lang }),
    ),
  runRisk: (farmId: number) => req<{ issued: number[] }>(`/api/farms/${farmId}/risk/run`, { method: 'POST' }),

  traps: (farmId: number) => req<TrapReading[]>(`/api/farms/${farmId}/traps`),
  addTrap: (farmId: number, body: Record<string, unknown>) =>
    req<{ issued: number[]; fired: { target: string; trigger: string; level: string }[] }>(
      `/api/farms/${farmId}/traps`,
      json(body),
    ),

  labelCheck: (farmId: number, product: string, lang: Lang, problemId?: number) =>
    req<LabelVerdict>('/api/labelcheck', json({ farm_id: farmId, product, lang, problem_id: problemId })),
  labelNote: (farmId: number, product: string, lang: Lang, problemId?: number) =>
    req<{ suggestion: string | null }>('/api/labelcheck/note', json({ farm_id: farmId, product, lang, problem_id: problemId })),

  cases: (status: 'open' | 'resolved' | 'all' = 'open') => req<CaseListItem[]>(`/api/cases?status=${status}`),
  caseBundle: (id: number) => req<CaseBundle>(`/api/cases/${id}`),
  resolveCase: (id: number, body: Record<string, unknown>) =>
    req<{ verdict: string; final_label: string; model_label: string | null; spread_alerts: number }>(
      `/api/cases/${id}/resolve`,
      json(body),
    ),

  summary: () => req<Summary>('/api/officials/summary'),
  hotspots: () => req<Hotspots>('/api/officials/hotspots'),
  rainfall: () => req<RainfallPanel>('/api/officials/rainfall'),
  modelCard: () => req<ModelCard>('/api/officials/model'),
  pesticideBaseline: () => req<PesticideBaseline>('/api/officials/pesticides'),
  outlook: () => req<OutlookRow[]>('/api/officials/outlook'),
  kcc: () => req<KccPanel>('/api/officials/kcc'),
  addSensor: (farmId: number, readings: Record<string, unknown>[]) =>
    req<{ stored: number }>(`/api/farms/${farmId}/sensor`, json(readings)),
  runAll: () =>
    req<{ farms: number; alerts_issued: number; weather_sources: Record<string, number> }>(
      '/api/officials/risk/run-all',
      { method: 'POST' },
    ),

  weather: (farmId: number, lang: Lang) => req<WeatherView>(`/api/farms/${farmId}/weather?lang=${lang}`),
  satellite: (farmId: number) => req<SatelliteView>(`/api/farms/${farmId}/satellite`),
  notices: (farmId: number, lang: Lang) =>
    req<{ unread: number; items: NoticeItem[] }>(`/api/farms/${farmId}/notices?lang=${lang}`),
  markRead: (farmId: number, ids?: number[]) =>
    req<{ marked: number }>(`/api/farms/${farmId}/notices/read`, json({ ids: ids ?? null })),
  logSpray: (farmId: number, product: string | null, lang: Lang) =>
    req<{ id: number; sprayed_at: string; check: SprayHour | null }>(
      `/api/farms/${farmId}/sprays?lang=${lang}`,
      json({ product }),
    ),
  pushKey: () => req<{ public_key: string }>('/api/push/key'),
  pushSubscribe: (farmId: number, sub: PushSubscriptionJSON) =>
    req<{ subscribed: boolean }>(`/api/farms/${farmId}/push/subscribe`, json(sub)),
  pushUnsubscribe: (endpoint: string) => req<{ subscribed: boolean }>('/api/push/unsubscribe', json({ endpoint })),
  pushTest: (farmId: number, lang: Lang) =>
    req<{ sent: number; removed: number; failed: number }>(`/api/farms/${farmId}/push/test?lang=${lang}`, { method: 'POST' }),
  contact: (farmId: number) => req<Contact>(`/api/farms/${farmId}/contact`),
  saveContact: (farmId: number, email: string | null, email_pref: EmailPref) =>
    req<Contact>(`/api/farms/${farmId}/contact`, { ...json({ email, email_pref }), method: 'PUT' }),
  emailTest: (farmId: number) => req<{ status: string }>(`/api/farms/${farmId}/email/test`, { method: 'POST' }),
  emailSummary: (farmId: number) => req<{ status: string }>(`/api/farms/${farmId}/email/summary`, { method: 'POST' }),
  watchRun: () => req<Record<string, number | string>>('/api/officials/watch/run', { method: 'POST' }),

  tts: async (text: string, lang: Lang): Promise<Blob> => {
    const res = await fetch('/api/voice/tts', json({ text, lang }))
    if (!res.ok) throw new ApiError(res.status, 'tts failed')
    return res.blob()
  },
  stt: (audio: Blob, lang: Lang) => {
    const fd = new FormData()
    fd.append('audio', audio, 'speech.webm')
    fd.append('lang', lang)
    return req<{ transcript: string }>('/api/voice/stt', { method: 'POST', body: fd })
  },
}
