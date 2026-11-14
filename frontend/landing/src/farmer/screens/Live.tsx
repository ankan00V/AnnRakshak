import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertTriangle, CameraOff, CheckCircle2, CloudSun, Droplets, Eye, Leaf, Loader2, MapPin, Monitor, ScanSearch,
  Flashlight, ShieldAlert, SignalLow, SkipForward, Sprout, Stethoscope, Upload, Video, Volume2, VolumeX, X,
} from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import type { LiveContext, LiveFrameReply, LiveGuide, LiveMark, LiveSummary, TargetView } from '../../api/types'
import { useAsync, useCarryable } from '../../lib/hooks'
import { Speaker } from '../../lib/speaker'
import type { Grabber } from '../../lib/videoframes'
import { MAX_VIDEO_BYTES, MAX_VIDEO_SECONDS, VideoError, openVideo } from '../../lib/videoframes'
import { ErrorBox, ListenButton } from '../../ui/kit'
import { useFarmer } from '../FarmerContext'
import DemoNotice, { useReadOnlyFarm } from '../components/DemoNotice'
import { PANEL, PRIMARY, RISK, SECONDARY } from '../tokens'
import { PanelHead, PhotoCurve, hideBroken } from '../ui'
import { lockScroll, onEscape } from '../../lib/sheet'

type Phase = 'intro' | 'starting' | 'live' | 'finishing' | 'summary' | 'error'
type Ask = { cue_id: string; question: string; candidates: TargetView[] }
/** Where the frames come from. A phone points its camera at the crop; a computer
 *  cannot be carried to the field, so it sends a video the farmer already filmed
 *  and we step through it here. The server is handed the same frames either way. */
type Source = 'camera' | 'video'

const FRAME_EVERY_MS = 650   // ~1.5 frames/s, each ~20-40 KB: works on a 3G/4G link
const FRAME_MAX_SIDE = 512
const INFLIGHT_TIMEOUT_MS = 6000
/** How long to wait for the result once it is asked for. Longer than the
 *  server can take to give it: a save that waits on a busy database pool (up
 *  to thirty seconds), or a reconnection waiting for a save already under way
 *  on the line it replaced. Timing out first told the farmer their walk was
 *  lost while it was being written. */
const FINISH_TIMEOUT_MS = 45000
const MIN_FRAME_SIDE = 64        // a stopped or starting track gives 0-2 px frames
const GRAB_EVERY_S = 1           // one frame a second out of an uploaded video
/** What the server says a thin video hit, and the sentence the farmer gets for
 *  it. Each one names the thing to do differently, because "it did not work"
 *  is the same screen for a recording of somebody else's video as for a crop
 *  filmed at dusk, and the two need opposite advice. */
const WHY_VIDEO: Record<string, string> = {
  not_crop: 'videoNotCrop',
  move_a_little: 'videoOneSpot',
  too_dark: 'videoTooDark',
  too_bright: 'videoTooDark',
  hold_steady: 'videoBlurry',
  show_crop: 'videoTooFar',
  come_closer: 'videoTooFar',
}
/** How long to keep trying to get a dropped call back, and the gaps between
 *  tries. A field edge with one bar drops a socket often; walking the whole
 *  field again because of it is not an answer. */
const REDIAL_WAITS_MS = [800, 1500, 3000, 5000, 8000]
/** Drops one call will ride out in all, however quickly each was mended. A
 *  line that falls over every time it is picked up is not a bad patch of
 *  signal, and dialling it for ever only keeps a farmer standing in a field. */
const MAX_DROPS = 12
/** A view that has not advanced in this long is one the farmer may simply not
 *  be able to get: offer them the way past it rather than coach forever. */
const STUCK_MS = 20000
/** Said to the server while the farmer is reading a question or deciding
 *  whether to send a case: without it, thinking looks exactly like a phone that
 *  has gone flat, and the server lets the call go. */
const PING_EVERY_MS = 20000
const MAX_UPLOAD_FRAMES = 260    // three minutes at one a second, and room for second looks
/** A second whose sampled instant was motion-blurred usually has a sharp frame
 *  half a second later: a hand-held phone smears while it moves and settles
 *  when it stops. One second look, only when the server called the first one
 *  blurred — it can add a readable frame and never takes one away. */
const RETRY_BLUR_S = 0.5
/** On a slow link a frame is sent smaller. Measured on 160 leaf photos from
 *  the datasets, each against its own full-size reading by the real model: 384 px at quality 0.6 is 40% fewer bytes,
 *  keeps the same top answer on 158 of them and passes the "is this a crop"
 *  gate on 157 against 159. One step smaller (320 px, 0.5) loses twelve to
 *  that gate, so there is no third tier. */
const SLOW_FRAME_MAX_SIDE = 384
const SLOW_RTT_MS = 2500         // replies slower than this: send smaller frames
const FAST_RTT_MS = 1200         // and faster than this: go back to full size
const SAVE_RETRIES = 2
/** What each frame of a video came to, as a colour on its timeline. */
const MARK_TONE: Record<LiveMark, string> = {
  h: 'bg-leaf', c: 'bg-leaf', p: 'bg-ember', o: 'bg-sky-400', x: 'bg-white/25',
}

/** m:ss into a video. */
function clock(at: number): string {
  const s = Math.max(0, Math.round(at))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** A tap you can feel. A farmer on a guided walk is looking at the leaf, not at
 *  the phone, and in a field at noon cannot read the screen anyway: the buzz is
 *  how they know a view counted without looking down. Not every phone has it. */
function buzz(pattern: number | number[]) {
  try {
    navigator.vibrate?.(pattern)
  } catch {
    /* blocked until the page has been touched, or not there at all */
  }
}

/** What is read aloud at the end. A video that gave nothing says which wall it
 *  hit on the screen; someone who cannot read that screen has to hear it too. */
function spoken(s: LiveSummary, t: (k: string) => string): string {
  const why = s.reading?.why_thin
  return why && WHY_VIDEO[why] && !s.reading.other_crop ? `${s.speech} ${t(WHY_VIDEO[why])}` : s.speech
}

function position(timeoutMs = 6000): Promise<GeolocationPosition | null> {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null)
    const t = setTimeout(() => resolve(null), timeoutMs)
    navigator.geolocation.getCurrentPosition(
      (p) => { clearTimeout(t); resolve(p) },
      () => { clearTimeout(t); resolve(null) },
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 60000 },
    )
  })
}

export default function Live() {
  const { farmId, lang, t } = useFarmer()
  const readOnly = useReadOnlyFarm() !== null
  const navigate = useNavigate()
  const home = useAsync(() => api.home(farmId!, lang), [farmId, lang], ['home', farmId!, lang].join(':'))
  const [phase, setPhase] = useState<Phase>('intro')
  const [error, setError] = useState<string | null>(null)
  const [ctx, setCtx] = useState<LiveContext | null>(null)
  const [guide, setGuide] = useState<LiveGuide | null>(null)
  const [quality, setQuality] = useState<LiveFrameReply['quality']>(null)
  const [flash, setFlash] = useState(0)
  const [liveTop, setLiveTop] = useState<{ name: string; confidence: number; healthy: boolean } | null>(null)
  const [tally, setTally] = useState<Record<string, { name: string; n: number }>>({})
  const [ask, setAsk] = useState<Ask | null>(null)
  const [expertChoice, setExpertChoice] = useState(false)
  const [summary, setSummary] = useState<LiveSummary | null>(null)
  const [muted, setMuted] = useState(false)
  const carryable = useCarryable()
  const [source, setSource] = useState<Source>('camera')
  const [watched, setWatched] = useState(0)      // how far through the uploaded video
  const [redialling, setRedialling] = useState(false)
  const [stuck, setStuck] = useState(false)
  const [torch, setTorch] = useState<boolean | null>(null)   // null: this camera has no light
  const [videoCut, setVideoCut] = useState(false)      // longer than we watch
  const [videoLen, setVideoLen] = useState(0)          // seconds of the file being read
  const [marks, setMarks] = useState<[number, LiveMark][]>([])   // what each frame read so far came to
  const [slow, setSlow] = useState(false)              // replies are slow: frames go smaller
  const [dragging, setDragging] = useState(false)

  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const speakerRef = useRef<Speaker | null>(null)
  const loopRef = useRef<number | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const grabRef = useRef<Grabber | null>(null)
  const freshWalk = () => ({ at: 0, frames: 0, last: 0, retry: null as number | null, retried: false })
  const walk = useRef(freshWalk())
  /** Which reading of the file is current. Bumped whenever the line drops or
   *  comes back: a frame still being cut from the video for the old line is
   *  then thrown away, not sent alongside the new line's — two pumps used to
   *  run from then on, sending every second twice and stopping half-way. */
  const pumpGen = useRef(0)
  const resumeRef = useRef<string | null>(null)
  const redial = useRef({ tries: 0, timer: 0, drops: 0 })
  const wakeRef = useRef<WakeLockSentinel | null>(null)
  const closedRef = useRef<() => void>(() => undefined)
  const messageRef = useRef<(ev: MessageEvent) => void>(() => undefined)
  const stepSince = useRef(0)
  const fresh = () => ({ seq: 0, inflight: false, sentAt: 0, capturing: false, photoModel: true,
                         finishing: false, done: false, stepsDone: false, source: 'camera' as Source,
                         rtt: 0, slow: false, toExpert: false, saves: 0 })
  const st = useRef(fresh())
  const finishTimer = useRef<number | null>(null)

  /** A guided walk is minutes of looking at the field, not at the phone. Every
   *  phone darkens and then locks a screen nobody has touched — and locking it
   *  stops the camera, which ends the call. The wake lock is the only thing
   *  standing between a farmer halfway down their field and a dead session.
   *  Browsers drop it whenever the page is hidden, so it is taken again every
   *  time the page comes back. */
  const keepAwake = useCallback(async () => {
    if (wakeRef.current || !('wakeLock' in navigator)) return
    try {
      wakeRef.current = await navigator.wakeLock.request('screen')
      wakeRef.current.addEventListener('release', () => { wakeRef.current = null })
    } catch {
      /* denied, or the battery is too low for the browser to allow it */
    }
  }, [])

  const letSleep = useCallback(() => {
    void wakeRef.current?.release().catch(() => undefined)
    wakeRef.current = null
  }, [])

  /** Let go of whatever was feeding frames: the camera's tracks, or the video
   *  file and the object URL holding it in memory. */
  const stopSource = useCallback(() => {
    if (loopRef.current) window.clearInterval(loopRef.current)
    loopRef.current = null
    st.current.capturing = false
    streamRef.current?.getTracks().forEach((tr) => tr.stop())
    streamRef.current = null
    grabRef.current?.close()
    grabRef.current = null
    window.clearTimeout(redial.current.timer)
    letSleep()
  }, [letSleep])

  useEffect(() => () => {
    // Leaving the screen ends the call for good: nothing still on a timer —
    // a redial, a second ask for the result — may pick it back up.
    st.current.done = true
    stopSource()
    if (finishTimer.current) window.clearTimeout(finishTimer.current)
    if (wsRef.current) {
      wsRef.current.onclose = null
      wsRef.current.close()
    }
    speakerRef.current?.dispose()
  }, [stopSource])

  /** The call dropped (network, server restart) before the summary arrived. */
  const lost = useCallback(() => {
    if (st.current.done) return
    st.current.done = true
    if (finishTimer.current) window.clearTimeout(finishTimer.current)
    stopSource()
    // Hang up the line being given up on, rather than leave it open for the
    // server to notice in a minute and a half.
    const ws = wsRef.current
    wsRef.current = null
    if (ws && ws.readyState <= WebSocket.OPEN) ws.close()
    speakerRef.current?.stop()
    setAsk(null)
    setExpertChoice(false)
    setError(t('liveLost'))
    setPhase('error')
  }, [stopSource, t])

  /** Ask for the result. Also how it is asked for again: after a save that
   *  failed, and after the line dropped while the answer was on its way. */
  const askForSummary = useCallback(() => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return false
    ws.send(JSON.stringify({ type: 'finish', send_to_expert: st.current.toExpert }))
    if (finishTimer.current) window.clearTimeout(finishTimer.current)
    finishTimer.current = window.setTimeout(lost, FINISH_TIMEOUT_MS)
    return true
  }, [lost])

  const finish = useCallback((sendToExpert: boolean) => {
    if (st.current.finishing) return
    st.current.finishing = true
    st.current.capturing = false
    st.current.toExpert = sendToExpert
    setPhase('finishing')
    speakerRef.current?.stop()
    if (!askForSummary()) lost()
  }, [askForSummary, lost])

  const sendFrame = useCallback(() => {
    const s = st.current
    const ws = wsRef.current
    const v = videoRef.current
    const c = canvasRef.current
    if (!s.capturing || !ws || ws.readyState !== WebSocket.OPEN || !v || !c || v.readyState < 2) return
    if (Math.min(v.videoWidth, v.videoHeight) < MIN_FRAME_SIDE) return
    const now = Date.now()
    if (s.inflight && now - s.sentAt < INFLIGHT_TIMEOUT_MS) return
    if (now - s.sentAt < FRAME_EVERY_MS) return
    if (s.inflight && !s.slow) {
      // The last frame was never answered in time. Its reply, if it comes, is
      // for an old frame and is not timed — so a link this bad would otherwise
      // never be noticed as slow at all.
      s.rtt = INFLIGHT_TIMEOUT_MS
      s.slow = true
      setSlow(true)
    }
    const scale = Math.min(1, (s.slow ? SLOW_FRAME_MAX_SIDE : FRAME_MAX_SIDE) / Math.max(v.videoWidth, v.videoHeight))
    c.width = Math.round(v.videoWidth * scale)
    c.height = Math.round(v.videoHeight * scale)
    c.getContext('2d')!.drawImage(v, 0, 0, c.width, c.height)
    const data = c.toDataURL('image/jpeg', s.slow ? 0.6 : 0.72).split(',')[1]
    s.seq += 1
    s.inflight = true
    s.sentAt = now
    ws.send(JSON.stringify({ type: 'frame', seq: s.seq, data }))
  }, [])

  /** The file is read to the end. The server settles what the readings are
   *  worth — two frames must agree before anything is called seen, and a thin
   *  reading goes to an expert on its own. */
  const endVideo = useCallback(() => {
    const s = st.current
    if (s.finishing || s.stepsDone) return
    s.capturing = false
    setWatched(1)
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: 'end_of_video' }))
  }, [])

  /** Send the next frame out of the uploaded video. Unlike the camera loop this
   *  is driven by the server's reply to the previous frame: there is no live
   *  scene to keep up with, so frames go one at a time, in order, and the
   *  quality gate and the step machine see exactly what a phone would send. */
  const pumpVideo = useCallback(async () => {
    const g = grabRef.current
    const s = st.current
    const w = walk.current
    if (!g || s.source !== 'video' || !s.capturing || s.finishing) return
    const gen = pumpGen.current
    // Loops rather than recurses: a position the decoder cannot give us is
    // stepped over, not treated as the end of the video.
    for (;;) {
      // A second look at a second the server called blurred comes before the
      // next second, and is the only thing allowed past the end of the count.
      const again = w.retry
      w.retry = null
      if (again == null && (w.frames >= MAX_UPLOAD_FRAMES || w.at > g.duration - 0.01)) return endVideo()
      const at = again ?? w.at
      setWatched(Math.min(1, at / g.duration))
      const data = await g.grab(at)
      const ws = wsRef.current
      if (gen !== pumpGen.current || !s.capturing || s.finishing || !ws || ws.readyState !== WebSocket.OPEN) {
        // The line went while this frame was being cut. Nothing has moved on:
        // the same second is read again once the call is back.
        w.retry = again
        return
      }
      if (again == null) w.at = at + GRAB_EVERY_S
      if (!data) continue
      w.frames += 1
      w.last = at
      w.retried = again != null
      s.seq += 1
      s.inflight = true
      s.sentAt = Date.now()
      // Where in the file this frame is from: it is how the result can say
      // "seen at 0:12" and the farmer can go back and look.
      ws.send(JSON.stringify({ type: 'frame', seq: s.seq, data, at: Math.round(at * 10) / 10 }))
      return
    }
  }, [endVideo])

  const onMessage = useCallback((ev: MessageEvent) => {
    const m = JSON.parse(ev.data)
    const sp = speakerRef.current
    if (m.type === 'ready') {
      setCtx(m.context)
      setGuide(m.guide)
      st.current.photoModel = m.photo_model
      resumeRef.current = m.resume ?? null
      redial.current.tries = 0
      setRedialling(false)
      setStuck(false)
      stepSince.current = Date.now()
      // The line dropped while the answer was on its way back. The walk was
      // held; ask for the answer again rather than walk any of it twice.
      if (st.current.finishing) {
        askForSummary()
        return
      }
      setPhase('live')
      // Back from a drop after every view was in — the farmer is reading the
      // look-alike question, or deciding whether to send photos. Sending
      // frames again would have the server announce the walk done a second
      // time, and that second "done" finished the call underneath the
      // question, throwing their answer away.
      if (st.current.stepsDone) return
      st.current.capturing = true
      // Coming back from a drop, the step is the one they were already on:
      // repeat it, so they know what to point at without reading the screen.
      void sp?.prompt(m.guide.text)
      if (st.current.source === 'video') {
        pumpGen.current += 1
        void pumpVideo()
      }
    } else if (m.type === 'frame') {
      const r = m as LiveFrameReply
      const s = st.current
      // How long the reply took, for the frame just sent and no other: a reply
      // to an older frame says nothing about the link now.
      if (r.seq === s.seq && s.sentAt) {
        const took = Date.now() - s.sentAt
        s.rtt = s.rtt ? s.rtt * 0.7 + took * 0.3 : took
        const nowSlow = s.slow ? s.rtt > FAST_RTT_MS : s.rtt > SLOW_RTT_MS
        if (nowSlow !== s.slow) {
          s.slow = nowSlow
          setSlow(nowSlow)
        }
      }
      // A late reply to an older frame frees nothing: the frame in flight is
      // still in flight. Clearing it here let two frames ride at once and,
      // since no reply then matched the newest frame, the link was never
      // timed again and stayed "slow" for the rest of the walk. What the late
      // reply says is still shown — the server answers frames in order, so it
      // is the latest word on the walk.
      if (r.seq === s.seq) s.inflight = false
      setQuality(r.quality)
      if (r.counted) setFlash((f) => f + 1)
      if (s.source === 'camera' && r.counted) buzz(r.advanced ? [40, 60, 40] : 25)
      if (s.source === 'video') {
        const w = walk.current
        if (r.mark) setMarks((prev) => [...prev, [w.last, r.mark!]])
        const g = grabRef.current
        if (r.quality && !r.quality.ok && r.quality.hint === 'hold_steady' && !w.retried
            && g && w.last + RETRY_BLUR_S < g.duration) {
          w.retry = w.last + RETRY_BLUR_S
        }
      }
      if (r.live?.top?.length) {
        const top = r.live.top[0]
        const healthy = top.target.endsWith('_healthy')
        setLiveTop({ name: top.name, confidence: top.confidence, healthy })
        if (!healthy && top.confidence >= 0.4) {
          setTally((prev) => ({ ...prev, [top.target]: { name: top.name, n: (prev[top.target]?.n ?? 0) + 1 } }))
        }
      }
      setGuide(r.guide)
      if (r.advanced) {
        stepSince.current = Date.now()
        setStuck(false)
      }
      if (r.advanced && r.guide.text) void sp?.prompt(r.guide.text)
      else if (r.quality && !r.quality.ok && r.quality.hint_text) void sp?.hint(r.quality.hint_text)
      if (st.current.source === 'video') void pumpVideo()
    } else if (m.type === 'ask') {
      st.current.capturing = false
      setAsk(m)
      void sp?.prompt(m.question)
    } else if (m.type === 'steps_done') {
      st.current.capturing = false
      st.current.stepsDone = true
      if (m.asked) return
      if (st.current.photoModel) finish(false)
      else setExpertChoice(true)
    } else if (m.type === 'summary') {
      st.current.done = true
      if (finishTimer.current) window.clearTimeout(finishTimer.current)
      stopSource()
      setSummary(m.summary)
      setPhase('summary')
      void sp?.prompt(spoken(m.summary, t))
    } else if (m.type === 'guide') {
      // A view was skipped: the walk has moved on to the next one.
      setGuide(m.guide)
      stepSince.current = Date.now()
      setStuck(false)
      setQuality(null)
      if (m.guide.text) void sp?.prompt(m.guide.text)
    } else if (m.type === 'lang') {
      // Language switched mid-call: the server re-sent the context and the current step.
      setCtx(m.context)
      setGuide(m.guide)
      void sp?.prompt(m.guide.text)
    } else if (m.type === 'error') {
      if (m.seq == null || m.seq === st.current.seq) st.current.inflight = false
      if (m.code === 'SESSION_LIMIT') finish(false)
      else if (m.code === 'SAVE_FAILED') {
        // Nothing was written and the walk is still held: ask again, a little
        // later each time, before telling anybody their walk is gone.
        const run = st.current
        if (finishTimer.current) window.clearTimeout(finishTimer.current)
        if (run.saves >= SAVE_RETRIES) lost()
        else {
          run.saves += 1
          // This call's retry, and only this call's: a farmer who has since
          // given up and started again must not have the new call finished
          // or ended by the old one's timer.
          window.setTimeout(() => {
            if (st.current === run && !run.done && !askForSummary()) lost()
          }, 1500 * run.saves)
        }
      } else if (m.code === 'BAD_MESSAGE') {
        /* ours are well formed; nothing to do about one that was not */
      } else if (m.code === 'RESUME_UNKNOWN') {
        // The walk was waiting too long, or came back to a different server.
        resumeRef.current = null
        lost()
      } else if (m.code === 'TOO_BUSY') {
        st.current.done = true
        stopSource()
        setError(t('liveTooBusy'))
        setPhase('error')
      } else if (st.current.source === 'video') void pumpVideo()  // skip the bad frame, keep going
    }
  }, [askForSummary, finish, lost, pumpVideo, stopSource, t])
  useEffect(() => { messageRef.current = onMessage }, [onMessage])

  // A language change takes effect at once: mid-call the server switches the
  // guidance and context; after the call the summary is re-rendered from what was saved.
  const langSeen = useRef(lang)
  useEffect(() => {
    if (langSeen.current === lang) return
    langSeen.current = lang
    speakerRef.current?.setLang(lang)
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'lang', lang }))
    if (summary && farmId != null) {
      api.liveSummary(farmId, summary.scan_id, lang).then(setSummary).catch(() => undefined)
    }
  }, [lang, summary, farmId])

  const socket = useCallback((open: (ws: WebSocket) => void) => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/api/live/${farmId}`)
    wsRef.current = ws
    // Only the call's current socket speaks for it. A socket left behind — the
    // one a "call dropped" screen never closed, which the server only lets go
    // ninety seconds later — used to land its close on whatever call came
    // next and set that one redialling, or end it. And the handler is read at
    // the moment of each message, not captured when the socket opened, so a
    // language switch mid-call is heard in the words of the summary too.
    ws.onopen = () => { if (wsRef.current === ws) open(ws) }
    ws.onmessage = (e) => { if (wsRef.current === ws) messageRef.current(e) }
    ws.onclose = () => { if (wsRef.current === ws) closedRef.current() }   // also fires after onerror
    return ws
  }, [farmId])

  /** Dial back in and ask for the walk we were on. The camera is left running
   *  throughout: the farmer is still standing in front of the same leaf. */
  const redialNow = useCallback(() => {
    const token = resumeRef.current
    if (!token || st.current.done) return
    socket((ws) => ws.send(JSON.stringify({ type: 'resume', token })))
  }, [socket])

  /** The connection went. On a field edge with one bar that is ordinary, not
   *  fatal — the walk is held on the server for a few minutes, so keep trying
   *  before telling the farmer their walk is gone. */
  const dropped = useCallback(() => {
    const s = st.current
    if (s.done) return
    redial.current.drops += 1
    if (!resumeRef.current || redial.current.tries >= REDIAL_WAITS_MS.length
        || redial.current.drops > MAX_DROPS) return lost()
    // A frame that was on its way when the line went may never have arrived:
    // go back to it, so the second of video it came from is not skipped.
    if (s.source === 'video' && s.inflight) {
      const w = walk.current
      // A second look is asked for again as a second look; a regular second
      // puts the reading back on it. Rewinding the clock to a half-second
      // second look used to shift every later frame half a second off the grid.
      if (w.retried) w.retry = w.last
      else {
        w.retry = null
        w.at = Math.min(w.at, w.last)
      }
      w.frames = Math.max(0, w.frames - 1)
    }
    s.capturing = false
    s.inflight = false
    pumpGen.current += 1
    // While the line is being got back, the wait for the result is paused:
    // the redials are bounded on their own, and a result held on the server
    // is asked for again the moment the line is back.
    if (finishTimer.current) window.clearTimeout(finishTimer.current)
    setRedialling(true)
    const wait = REDIAL_WAITS_MS[redial.current.tries]
    redial.current.tries += 1
    window.clearTimeout(redial.current.timer)
    redial.current.timer = window.setTimeout(redialNow, wait)
  }, [lost, redialNow])

  useEffect(() => { closedRef.current = dropped }, [dropped])

  // A phone that is put to sleep, or an app switched away from to take a call,
  // stops its camera. Coming back, the wake lock has to be taken again and the
  // preview told to play — otherwise the call is alive but blind.
  useEffect(() => {
    const back = () => {
      if (document.visibilityState !== 'visible' || !st.current.capturing) return
      void keepAwake()
      void videoRef.current?.play().catch(() => undefined)
    }
    document.addEventListener('visibilitychange', back)
    return () => document.removeEventListener('visibilitychange', back)
  }, [keepAwake])

  // The call is quiet whenever the farmer is being asked something rather than
  // walking. Say so, so the silence is not read as a phone that has died.
  useEffect(() => {
    if (phase !== 'starting' && phase !== 'live' && phase !== 'finishing') return
    const t = window.setInterval(() => {
      const ws = wsRef.current
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }))
    }, PING_EVERY_MS)
    return () => window.clearInterval(t)
  }, [phase])

  // While the call runs, a downward swipe on the camera must not reach the
  // browser: Chrome on Android reads it as pull-to-refresh, reloads the page
  // and the call is gone. The overlay is touch-none as well; this covers the
  // root scroller, which is the one the browser actually refreshes from.
  useEffect(() => {
    if (phase !== 'starting' && phase !== 'live' && phase !== 'finishing') return
    const root = document.documentElement.style
    const was = root.overscrollBehaviorY
    root.overscrollBehaviorY = 'none'
    return () => { root.overscrollBehaviorY = was }
  }, [phase])

  // Offer the way past a view that is not coming. Some fields have no leaf you
  // can turn over and no plant base above the water.
  useEffect(() => {
    if (phase !== 'live' || source !== 'camera' || !guide?.step) return
    const t = window.setInterval(() => {
      if (Date.now() - stepSince.current > STUCK_MS) setStuck(true)
    }, 1000)
    return () => window.clearInterval(t)
  }, [phase, source, guide?.step])

  const skipView = () => {
    setStuck(false)
    stepSince.current = Date.now()
    wsRef.current?.send(JSON.stringify({ type: 'skip' }))
  }

  /** The camera's own light, where it has one. A field is walked early or late
   *  as often as at noon, and "too dark" is not advice if the phone is holding
   *  the only lamp there is. */
  const flipTorch = async () => {
    const track = streamRef.current?.getVideoTracks()[0]
    if (!track || torch === null) return
    const next = !torch
    try {
      await track.applyConstraints({ advanced: [{ torch: next }] } as unknown as MediaTrackConstraints)
      setTorch(next)
    } catch {
      setTorch(null)   // the camera said it could and then would not
    }
  }

  /** Everything both routes do before a frame exists: forget the last walk and
   *  wake the voice up. */
  const begin = (from: Source) => {
    setPhase('starting')
    setError(null)
    st.current = fresh()
    st.current.source = from
    walk.current = freshWalk()
    setSource(from)
    setWatched(0)
    setMarks([])
    setVideoLen(0)
    setSlow(false)
    setRedialling(false)
    setStuck(false)
    resumeRef.current = null
    redial.current = { tries: 0, timer: 0, drops: 0 }
    setVideoCut(false)
    setTally({})
    setAsk(null)
    setExpertChoice(false)
    setQuality(null)
    setLiveTop(null)
    speakerRef.current?.dispose()
    speakerRef.current = new Speaker(lang)
    speakerRef.current.muted = muted
  }

  /** Open the call. The server is told where the field is and which language to
   *  speak; what is feeding the frames is ours to know. */
  const connect = (pos: GeolocationPosition | null, from: Source) => {
    socket((ws) => ws.send(JSON.stringify({
      type: 'start', lang, mode: from === 'video' ? 'video' : 'walk',
      lat: pos?.coords.latitude ?? null, lon: pos?.coords.longitude ?? null, accuracy: pos?.coords.accuracy ?? null,
    })))
  }

  const start = async () => {
    begin('camera')
    // This attempt, so that anything still on its way when the farmer backs
    // out can tell it has been left behind. Without it the camera opened after
    // they had already hung up — light on, nobody watching — and a call was
    // then dialled for a screen that was no longer there.
    const run = st.current
    const gone = () => run.done || st.current !== run
    const where = position()
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      })
      if (gone()) {
        stream.getTracks().forEach((tr) => tr.stop())
        return
      }
      streamRef.current = stream
    } catch (e) {
      if (gone()) return
      // "Camera not available" is three different problems with three different
      // things to do about them: a permission refused once is refused silently
      // ever after, and nobody finds that setting unprompted.
      const name = e instanceof DOMException ? e.name : ''
      setError(t(name === 'NotAllowedError' || name === 'SecurityError' ? 'liveCamDenied'
        : name === 'NotReadableError' || name === 'AbortError' ? 'liveCamBusy' : 'liveNoCamera'))
      setPhase('error')
      return
    }
    // another app taking the camera, or the OS revoking it, ends the track without an error
    streamRef.current.getVideoTracks()[0]?.addEventListener('ended', () => {
      if (st.current.finishing || st.current !== run) return
      // Ended for good, before the line is let go — otherwise its close was
      // read as a drop, the call redialled, and the farmer was put back into
      // a "live" call with a black screen and a voice telling them where to
      // point a camera that was no longer there.
      run.done = true
      stopSource()
      const ws = wsRef.current
      wsRef.current = null
      ws?.close()
      speakerRef.current?.stop()
      setError(t('liveCamBusy'))
      setPhase('error')
    })
    const track = streamRef.current.getVideoTracks()[0]
    const caps = (track?.getCapabilities?.() ?? {}) as { torch?: boolean }
    setTorch(caps.torch ? false : null)
    const v = videoRef.current!
    v.removeAttribute('src')
    v.srcObject = streamRef.current
    await v.play().catch(() => undefined)
    void keepAwake()
    const pos = await where
    if (gone()) return
    connect(pos, 'camera')
    loopRef.current = window.setInterval(sendFrame, 150)
  }

  /** The computer's route: a video of the field, watched here frame by frame.
   *  Nothing is uploaded — the file is decoded in this browser and only the
   *  frames the walk asks for are sent, exactly as a phone sends them. */
  const startUpload = async (file: File) => {
    begin('video')
    const run = st.current
    try {
      const g = await openVideo(file, videoRef.current!, FRAME_MAX_SIDE, 0.72)
      if (run.done || st.current !== run) return g.close()   // backed out while it was opening
      grabRef.current = g
      setVideoCut(g.full > g.duration + 1)
      setVideoLen(g.duration)
    } catch (e) {
      if (run.done || st.current !== run) return
      const reason = e instanceof VideoError ? e.reason : 'unreadable'
      setError(t(reason === 'too_big' ? 'liveVideoBig' : reason === 'not_video' ? 'liveVideoNot' : 'liveVideoBad')
        .replace('{mb}', String(Math.round(MAX_VIDEO_BYTES / (1024 * 1024)))))
      setPhase('error')
      return
    }
    // No location is asked for: where this computer sits says nothing about
    // a field that was filmed earlier. The field's own position is used.
    connect(null, 'video')
  }

  /** Leave before there is anything to finish: the camera would not open, the
   *  line would not connect. Marked done first, so the socket closing is not
   *  read as a call that dropped. */
  const hangUp = () => {
    st.current.done = true
    stopSource()
    const ws = wsRef.current
    if (ws) {
      ws.onclose = null
      ws.close()
    }
    speakerRef.current?.stop()
    setPhase('intro')
  }

  const answer = (a: 'yes' | 'no' | 'unknown') => {
    if (!ask) return
    wsRef.current?.send(JSON.stringify({ type: 'answer', cue_id: ask.cue_id, answer: a }))
    setAsk(null)
    finish(false)
  }

  const toggleMute = () => {
    const next = !muted
    setMuted(next)
    if (speakerRef.current) {
      speakerRef.current.muted = next
      if (next) speakerRef.current.stop()
    }
  }

  const farm = home.data?.farm
  const live = phase === 'starting' || phase === 'live' || phase === 'finishing'

  if (phase === 'summary' && summary) {
    return <SummaryView s={summary}
      onAgain={() => { setSummary(null); setPhase('intro') }} onDone={() => navigate('/app')} />
  }

  if (readOnly) return <DemoNotice />

  const how = carryable
    ? [[Video, t('liveHow1')], [Eye, t('liveHow2')], [ShieldAlert, t('liveHow3')]] as const
    : [[Monitor, t('liveOnComputer')], [Upload, t('liveUploadSub')], [Eye, t('liveFilmTips')]] as const

  return (
    <div>
      {!live && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px] xl:grid-cols-[minmax(0,1fr)_420px]">
          <div className="min-w-0 space-y-6">
            <section className={`${PANEL} p-2`}>
              <div className="relative h-[230px] overflow-hidden rounded-[22px] bg-[#1d4a2c] sm:h-[260px]">
                <img onError={hideBroken} src="/photos/panicle-closeup.webp" alt="" width={940} height={442}
                  className="absolute inset-0 h-full w-full object-cover" />
                <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/30 to-black/10" />
                <div className="relative flex h-full flex-col justify-between p-5 text-white lg:p-6">
                  <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-ember px-3 py-1 text-[13px] font-bold tracking-wide">
                    <span className="h-2 w-2 rounded-full bg-white motion-safe:animate-pulse" /> LIVE
                  </span>
                  <div className="pb-3">
                    <h1 className="font-instrument-serif text-[36px] leading-none drop-shadow-sm lg:text-[44px]">{t('liveTitle')}</h1>
                    <p className="mt-2 max-w-xl text-[15px] leading-snug drop-shadow">{t('liveCtaSub')}</p>
                  </div>
                </div>
                <PhotoCurve />
              </div>
              <div className="space-y-3 p-3 sm:p-4">
                {farm && !farm.photo_diagnosis && (
                  <p className="rounded-[18px] bg-sky-50 p-3.5 text-[15px] text-sky-950/85">{t('liveNoModel')}</p>
                )}
                {phase === 'error' && error && <ErrorBox offlineLabel={t('offline')} error={new Error(error)} />}
                {/* One route per device, not two. A phone walks the field with its
                    camera. A computer cannot, and its camera faces a desk, so there
                    the walk is a video of the field — offering the webcam as well
                    would only be a button that wastes the farmer's time. */}
                <div
                  onDragOver={(e) => { if (!carryable) { e.preventDefault(); setDragging(true) } }}
                  onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false) }}
                  onDrop={(e) => {
                    if (carryable) return
                    e.preventDefault()
                    setDragging(false)
                    const f = e.dataTransfer.files?.[0]
                    if (f) void startUpload(f)
                  }}
                  className={carryable ? '' : `rounded-[22px] border-2 border-dashed p-4 transition-colors ${
                    dragging ? 'border-[#4b8b3b] bg-[#e3efd9]' : 'border-soil-dark/15 bg-[#f5f7f1]'}`}>
                  <button onClick={carryable ? start : () => fileRef.current?.click()}
                    className={`${PRIMARY} min-h-[56px] text-[17px] shadow-[0_12px_24px_-14px_rgba(29,74,44,0.8)]`}>
                    {carryable ? <Video className="h-5 w-5" /> : <Upload className="h-5 w-5" />}
                    {carryable ? t('liveStart') : t('liveUpload')}
                  </button>
                  {!carryable && <p className="mt-2.5 text-center text-[14px] text-soil-dark/70">{t('liveDropHere')}</p>}
                </div>
              </div>
              <input ref={fileRef} type="file" accept="video/*" className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  e.target.value = ''
                  if (f) void startUpload(f)
                }} />
            </section>
          </div>
          <aside className="min-w-0 space-y-6">
            <section className={`${PANEL} p-5`}>
              <h2 className="text-[20px] font-semibold tracking-tight">{t('liveHowTitle')}</h2>
              <ol className="mt-4 space-y-3">
                {how.map(([Icon, text], i) => (
                  <li key={i} className="flex items-start gap-3 rounded-[20px] bg-[#f5f7f1] p-3.5">
                    <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[#e3efd9] text-[#2f6a39]">
                      <Icon className="h-6 w-6" aria-hidden />
                    </span>
                    <span className="pt-0.5 text-[15px] leading-snug">{text}</span>
                  </li>
                ))}
              </ol>
            </section>
          </aside>
        </div>
      )}

      {/* The call: full screen over the app chrome while it runs. */}
      {/* Above the tour's own z-[60]: while a call is running nothing belongs
          over the camera, whichever mounted first. */}
      <div className={live ? 'fixed inset-0 z-[70] bg-black text-white touch-none overscroll-none' : 'hidden'}>
        <video ref={videoRef} playsInline muted
          className={`absolute inset-0 w-full h-full ${source === 'video' ? 'object-contain' : 'object-cover'}`} />
        <canvas ref={canvasRef} className="hidden" />

        <div className="absolute inset-x-0 top-0 p-4 pt-[max(1rem,env(safe-area-inset-top))] bg-gradient-to-b from-black/80 via-black/50 to-transparent">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-ember px-2 py-0.5 text-[12px] font-bold">
              <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" /> LIVE
            </span>
            {guide && guide.total > 0 && (
              <div className="flex-1 flex gap-1">
                {Array.from({ length: guide.total }).map((_, i) => (
                  <span key={i} className={`h-1 flex-1 rounded-full ${i < guide.index ? 'bg-leaf' : i === guide.index ? 'bg-ochre' : 'bg-white/25'}`} />
                ))}
              </div>
            )}
            {torch !== null && (
              <button onClick={() => { void flipTorch() }} aria-label={t('liveTorch')} aria-pressed={torch}
                className={`w-11 h-11 shrink-0 rounded-full flex items-center justify-center ${torch ? 'bg-ochre text-soil-dark' : 'bg-black/40 ring-1 ring-white/30'} ${
                  // "Too dark" is not advice while the phone is holding the only lamp there is.
                  !torch && quality?.hint === 'too_dark' ? '!ring-2 !ring-ochre animate-pulse' : ''}`}>
                <Flashlight className="w-5 h-5" />
              </button>
            )}
            <button onClick={toggleMute} aria-label={muted ? t('liveUnmute') : t('liveMute')}
              className="w-11 h-11 shrink-0 rounded-full bg-black/40 ring-1 ring-white/30 flex items-center justify-center">
              {muted ? <VolumeX className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}
            </button>
          </div>
          {source === 'video' && (
            <div className="mt-3">
              <p className="text-[12px] uppercase tracking-wide text-white/75">
                {t('liveWatching')}
                {videoCut && <span className="ml-1.5 normal-case tracking-normal text-ochre">
                  {t('liveVideoCut').replace('{min}', String(Math.round(MAX_VIDEO_SECONDS / 60)))}
                </span>}
              </p>
              <span className="mt-1 block h-1 rounded-full bg-white/25">
                <span className="block h-1 rounded-full bg-ochre transition-[width] duration-200" style={{ width: `${Math.round(watched * 100)}%` }} />
              </span>
              <Timeline marks={marks} length={videoLen} className="mt-1.5" />
            </div>
          )}
          {guide?.step && (
            <>
              <p className="mt-3 text-[12px] uppercase tracking-wide text-white/75">
                {t('liveStep').replace('{i}', String(guide.index + 1)).replace('{n}', String(guide.total))}
              </p>
              <p aria-live="polite" className="mt-0.5 text-lg font-semibold leading-snug">{guide.text}</p>
              {guide.need ? (
                <div className="mt-2 flex gap-1.5">
                  {Array.from({ length: guide.need }).map((_, i) => (
                    <span key={i} className={`w-2.5 h-2.5 rounded-full ${i < (guide.got ?? 0) ? 'bg-leaf' : 'bg-white/30'}`} />
                  ))}
                </div>
              ) : null}
            </>
          )}
          <div className="mt-2 flex flex-wrap gap-1.5 text-[12px]">
            {ctx?.weather_now?.temp_c != null && (
              <span className="inline-flex items-center gap-1 rounded-full bg-white/15 px-2 py-0.5">
                <CloudSun className="w-3 h-3" /> {Math.round(ctx.weather_now.temp_c)}° · {ctx.weather_now.rh_pct}%
              </span>
            )}
            {ctx && (
              <span className="inline-flex items-center gap-1 rounded-full bg-white/15 px-2 py-0.5">
                <MapPin className="w-3 h-3" />
                {ctx.location.source === 'gps'
                  ? t('liveGps').replace('{m}', String(Math.round(ctx.location.accuracy_m ?? 0)))
                  : t('liveFarmLoc')}
              </span>
            )}
            {slow && source === 'camera' && (
              <span className="inline-flex items-center gap-1 rounded-full bg-ochre/90 text-soil-dark px-2 py-0.5">
                <SignalLow className="w-3 h-3" /> {t('liveSlowNet')}
              </span>
            )}
          </div>
        </div>

        {/* Where to aim: a leaf-sized box for close-ups, the whole frame otherwise. */}
        {phase === 'live' && guide?.step && source === 'camera' && (
          <div key={flash} className={`absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 border-2 rounded-3xl transition-colors ${
            guide.kind === 'close' ? 'w-[62vw] h-[62vw] max-w-sm max-h-96' : 'w-[88vw] h-[46vh]'
          } ${flash ? 'animate-[pulse_0.6s_ease-out_1] border-leaf' : 'border-white/50'}`} />
        )}

        <div className="absolute inset-x-0 bottom-0 p-4 pb-[max(1rem,env(safe-area-inset-bottom))] bg-gradient-to-t from-black/85 via-black/50 to-transparent space-y-2">
          {phase === 'live' && source === 'video' && guide && (
            <p className="mx-auto w-fit rounded-full bg-white/15 px-3 py-1 text-sm font-medium">
              {t('liveVideoRead').replace('{n}', String(guide.read ?? 0)).replace('{k}', String(guide.kept ?? 0))}
            </p>
          )}
          {/* A video that gave the model almost nothing to read says which wall
              it hit. Without this the farmer watched a good-looking video
              produce "0 clear close-ups" and had no idea what to do about it —
              a screen recording and a crop filmed at dusk fail identically on
              screen and need opposite advice. */}
          {source === 'video' && WHY_VIDEO[guide?.why_thin ?? ''] && (
            <p className="mx-auto max-w-sm rounded-2xl bg-ochre/90 px-3 py-2 text-sm leading-snug text-soil-dark">
              {t(WHY_VIDEO[guide!.why_thin!])}
            </p>
          )}
          {phase === 'live' && source === 'camera' && quality && (
            <p role="status" className={`mx-auto w-fit rounded-full px-3 py-1 text-sm font-medium ${quality.ok ? 'bg-leaf/90' : 'bg-ochre/90 text-soil-dark'}`}>
              {quality.ok ? t('liveKeep') : quality.hint_text}
            </p>
          )}
          {liveTop && phase === 'live' && (
            <p className="mx-auto w-fit flex items-center gap-1.5 rounded-full bg-black/60 px-3 py-1 text-[13px]">
              {liveTop.healthy ? <Leaf className="w-3.5 h-3.5 text-leaf" /> : <Eye className="w-3.5 h-3.5 text-ochre" />}
              {liveTop.name} · {Math.round(liveTop.confidence * 100)}%
            </p>
          )}
          {Object.keys(tally).length > 0 && (
            <p className="text-center text-[12px] text-white/80">
              {t('liveSeenSoFar')}: {Object.values(tally).map((x) => `${x.name} ×${x.n}`).join(' · ')}
            </p>
          )}
          {stuck && phase === 'live' && (
            <div className="flex justify-center">
              <button onClick={skipView}
                className="min-h-[44px] px-4 rounded-full border border-white/40 bg-black/40 text-sm font-medium flex items-center gap-2">
                <SkipForward className="w-4 h-4" /> {t('liveSkip')}
              </button>
            </div>
          )}
          <div className="flex justify-center">
            <button onClick={() => (phase === 'live' ? finish(false) : hangUp())}
              className="min-h-[48px] px-6 rounded-full bg-ember text-white font-medium flex items-center gap-2">
              <X className="w-4 h-4" /> {t('liveEnd')}
            </button>
          </div>
        </div>

        {redialling && (
          <div className="absolute inset-0 bg-black/70 flex flex-col items-center justify-center gap-3 px-8 text-center">
            <Loader2 className="w-8 h-8 animate-spin text-ochre" />
            <p className="text-sm">{t('liveRedial')}</p>
            {source === 'camera' && <p className="text-[13px] text-white/75">{t('liveRedialStay')}</p>}
          </div>
        )}
        {(phase === 'starting' || phase === 'finishing') && (
          <div className="absolute inset-0 bg-black/60 flex flex-col items-center justify-center gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-ochre" />
            <p className="text-sm">{phase === 'starting' ? t('liveStarting') : t('liveAnalysing')}</p>
            {/* A line that will not connect can take a browser a minute to give
                up on. This is over the End button, so it needs its own way out. */}
            {phase === 'starting' && (
              <button onClick={hangUp} className="mt-2 min-h-[44px] px-5 rounded-full border border-white/40 text-sm font-medium flex items-center gap-2">
                <X className="w-4 h-4" /> {t('liveEnd')}
              </button>
            )}
          </div>
        )}

        {ask && (
          <div className="absolute inset-x-3 bottom-[max(0.75rem,env(safe-area-inset-bottom))] rounded-3xl bg-leaf-deep p-4 shadow-2xl">
            <p className="text-[12px] uppercase tracking-wide text-cream/75">{t('liveAnswer')}</p>
            <p className="mt-1 text-lg font-semibold leading-snug">{ask.question}</p>
            <div className="mt-2 grid grid-cols-2 gap-2 text-[13px] leading-snug">
              {ask.candidates.map((c) => (
                <p key={c.id} className="rounded-xl bg-white/10 p-2"><span className="font-semibold">{c.name}</span><br />{c.signature}</p>
              ))}
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2">
              <button onClick={() => answer('yes')} className="min-h-[48px] rounded-2xl bg-cream text-soil-dark font-semibold">{t('yes')}</button>
              <button onClick={() => answer('no')} className="min-h-[48px] rounded-2xl bg-cream text-soil-dark font-semibold">{t('no')}</button>
              <button onClick={() => answer('unknown')} className="min-h-[48px] rounded-2xl border border-cream/40 font-medium text-sm">{t('cantTell')}</button>
            </div>
          </div>
        )}

        {expertChoice && (
          <div className="absolute inset-x-3 bottom-[max(0.75rem,env(safe-area-inset-bottom))] rounded-3xl bg-leaf-deep p-4 shadow-2xl">
            <p className="text-lg font-semibold leading-snug">{t('liveExpertAsk')}</p>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <button onClick={() => { setExpertChoice(false); finish(true) }} className="min-h-[48px] rounded-2xl bg-cream text-soil-dark font-semibold">{t('liveYesSend')}</button>
              <button onClick={() => { setExpertChoice(false); finish(false) }} className="min-h-[48px] rounded-2xl border border-cream/40 font-medium">{t('liveNoThanks')}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

/** A video, as a strip: one tick per frame read, placed where in the file it
 *  came from and coloured by what it came to. It is the difference between
 *  "2 clear close-ups" and seeing that both were in the first ten seconds and
 *  the rest of the walk down the row gave nothing. */
function Timeline({ marks, length, className = '', light = false }: {
  marks: [number, LiveMark][]; length: number; className?: string; light?: boolean
}) {
  const end = Math.max(length, ...marks.map(([at]) => at), 1)
  return (
    <span aria-hidden className={`relative block h-2.5 rounded-full overflow-hidden ${light ? 'bg-soil-dark/10' : 'bg-white/10'} ${className}`}>
      {marks.map(([at, mark], i) => (
        <span key={i} style={{ left: `${(at / end) * 100}%` }}
          className={`absolute top-0 h-full w-[3px] -translate-x-1/2 rounded-full ${
            mark === 'x' && light ? 'bg-soil-dark/20' : MARK_TONE[mark]}`} />
      ))}
    </span>
  )
}

const VERDICT = {
  all_good: { tone: 'bg-[#2f6a39] text-white', icon: CheckCircle2, key: 'verdict_all_good' },
  risk: { tone: 'bg-[#fbf0dc] text-[#5c3a0c] ring-1 ring-ochre/30', icon: AlertTriangle, key: 'verdict_risk' },
  found: { tone: 'bg-[#9a2f17] text-white', icon: ShieldAlert, key: 'verdict_found' },
  check: { tone: 'bg-sky-800 text-white', icon: Stethoscope, key: 'verdict_check' },
  // The walk may only claim what the camera saw: not enough confident views of
  // the plant is its own answer, never "healthy" by default.
  unclear: { tone: 'bg-[#1d4a2c] text-white', icon: ScanSearch, key: 'verdict_unclear' },
  no_model: { tone: 'bg-[#1d4a2c] text-white', icon: CameraOff, key: 'verdict_no_model' },
} as const

function SummaryView({ s, onAgain, onDone }: {
  s: LiveSummary; onAgain: () => void; onDone: () => void
}) {
  const { t, lang } = useFarmer()
  const v = VERDICT[s.verdict]
  const c = s.context
  const w = c.weather_now
  const ph = c.soil.ph
  const moist = c.soil.moisture
  const seenTargets = new Set(s.seen.map((x) => x.target))
  const [allRisks, setAllRisks] = useState(false)
  const [zoom, setZoom] = useState<{ src: string; name: string } | null>(null)
  // Kept with the result, not remembered from the call: it has to survive a
  // language switch, a reload, and being opened again next week.
  const reading = s.reading
  const whyThin = reading?.why_thin ?? null
  const marks = reading?.marks ?? []
  const readable = marks.filter(([, m]) => m !== 'x').length
  const zoomFrom = useRef<HTMLElement | null>(null)
  const zoomClose = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!zoom) return
    // A screen reader is told a dialog opened by landing in it, and the page
    // underneath stops scrolling; closing goes back to the photo it came from.
    zoomClose.current?.focus()
    const release = lockScroll()
    const unEsc = onEscape(() => setZoom(null))
    return () => {
      unEsc()
      release()
      zoomFrom.current?.focus()
    }
  }, [zoom])
  const pending = c.risks.filter((r) => !seenTargets.has(r.target))
  const risks = allRisks ? pending : pending.slice(0, 3)

  const tile = 'rounded-[20px] bg-[#f5f7f1] p-4'
  const tileHead = 'flex items-center gap-1.5 text-[13px] font-medium text-soil-dark/75'
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px] xl:grid-cols-[minmax(0,1fr)_420px]">
      <div className="min-w-0 space-y-6">
        <section className={`rounded-[28px] p-5 lg:p-6 ${v.tone}`}>
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-white/15">
                <v.icon className="h-7 w-7" aria-hidden />
              </span>
              <div>
                <p className="text-[14px] opacity-80">{t('liveTitle')}</p>
                <h1 className="font-instrument-serif text-[32px] leading-tight lg:text-[36px]">{t(v.key)}</h1>
              </div>
            </div>
            <ListenButton text={spoken(s, t)} lang={lang} label={t('listen')} stopLabel={t('stop')} compact tone="light" />
          </div>
          {/* A video that gave almost nothing knows which wall it hit, and the
              general advice is wrong for most of them: telling somebody whose
              screen recording the model cannot read as a crop to "hold the phone
              close to a leaf, in daylight" sends them out to film the same
              unusable thing again. Where the reading says why, it replaces the
              general line rather than sitting under it. */}
          {reading?.other_crop ? (
            // Read well enough — as a crop this field is not growing. Neither
            // "could not see your plants" nor a refilming tip is true of that.
            <p className="mt-4 text-[15px] leading-snug opacity-90">{reading.other_crop.text}</p>
          ) : whyThin && WHY_VIDEO[whyThin] ? (
            <p className="mt-4 text-[15px] leading-snug opacity-90">{t(WHY_VIDEO[whyThin])}</p>
          ) : (s.verdict === 'unclear' || s.verdict === 'no_model') && (
            <p className="mt-4 text-[15px] leading-snug opacity-90">
              {s.verdict === 'unclear' ? t('liveUnclearHint') : t('liveNoModelHint').replace('{crop}', c.crop.name)}
            </p>
          )}
          {s.verdict === 'unclear' && (
            <button onClick={onAgain}
              className="mt-4 min-h-[52px] w-full rounded-full bg-white text-[16px] font-semibold text-soil-dark">
              {t('liveTryAgain')}
            </button>
          )}
          {c.location.far_from_farm && (
            <p className="mt-3 text-[14px] opacity-85">{t('liveFar').replace('{km}', String(c.location.km_from_farm))}</p>
          )}
        </section>

        {s.seen.length > 0 && (
          <section className={`${PANEL} p-5 lg:p-6`}>
            <PanelHead icon={ShieldAlert} title={t('liveSeen')} />
            <div className="mt-4 space-y-3">
              {s.seen.map((x) => (
                <article key={x.target} className="rounded-[20px] bg-[#fdf0ed] p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-[17px] font-semibold">{x.name}</p>
                    <span className="rounded-full bg-[#f9dcd5] px-2.5 py-0.5 text-[13px] font-medium text-[#9a2f17]">
                      {t('liveViews').replace('{n}', String(x.views))} · {Math.round(x.confidence * 100)}%
                    </span>
                  </div>
                  {x.evidence && x.evidence.length > 0 && (
                    <div className="mt-3 flex gap-2">
                      {x.evidence.map((u) => (
                        <button key={u} onClick={(e) => { zoomFrom.current = e.currentTarget; setZoom({ src: u, name: x.name }) }}
                          className="overflow-hidden rounded-2xl focus-visible:ring-2 focus-visible:ring-leaf-deep">
                          <img src={u} alt={x.name} className="h-20 w-20 object-cover" />
                        </button>
                      ))}
                    </div>
                  )}
                  {x.moments && x.moments.length > 0 && (
                    <p className="mt-2 text-[13px] text-soil-dark/75">
                      {t('liveSeenAt')}: {x.moments.map(clock).join(' · ')}
                    </p>
                  )}
                  {x.advisory && (
                    <div className="mt-3 space-y-1.5 rounded-[16px] bg-white/80 p-3.5 text-[15px]">
                      {x.advisory.what_to_avoid[0] && <p className="font-medium text-[#9a2f17]">✕ {x.advisory.what_to_avoid[0]}</p>}
                      {x.advisory.ladder.filter((r) => r.tier !== 'chemical').slice(0, 2).map((r, i) => (
                        <p key={i} className="text-soil-dark/85">• {r.action}</p>
                      ))}
                    </div>
                  )}
                  <Link to={`/app/history/${x.problem_id}`} className="mt-3 inline-flex min-h-[44px] items-center gap-1 text-[15px] font-semibold text-leaf-deep">
                    {t('liveOpenAdvice')} →
                  </Link>
                </article>
              ))}
            </div>
          </section>
        )}

        {s.possible.length > 0 && (
          <section className={`${PANEL} p-5`}>
            <PanelHead icon={Stethoscope} title={t('livePossible')} />
            <ul className="mt-3 space-y-2">
              {s.possible.map((x) => (
                <li key={x.target} className="rounded-[18px] bg-[#f5f7f1] p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[15px] font-semibold">{x.name}</span>
                    {x.case && <span className="rounded-full bg-sky-100 px-2.5 py-0.5 text-[13px] font-medium text-sky-800">~{x.case.eta_minutes} {t('minutes')}</span>}
                  </div>
                  {x.moments && x.moments.length > 0 && (
                    <p className="mt-1 text-[13px] text-soil-dark/75">{t('liveSeenAt')}: {x.moments.map(clock).join(' · ')}</p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        {risks.length > 0 && (
          <section className={`${PANEL} p-5 lg:p-6`}>
            <PanelHead icon={AlertTriangle} title={t('liveRisks')} />
            <div className="mt-4 space-y-3">
              {risks.map((r) => (
                <article key={r.target + r.trigger} className={`rounded-[20px] p-4 ${RISK[r.level].row}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-[16px] font-semibold">{r.name}</p>
                    <span className={`rounded-full px-2.5 py-0.5 text-[13px] font-medium ${RISK[r.level].pill}`}>{t(RISK[r.level].key)}</span>
                  </div>
                  <p className="mt-1 text-[14px] text-soil-dark/80">{r.reason}</p>
                  {r.prevention.do.length > 0 && (
                    <div className="mt-3">
                      <p className="text-[14px] font-semibold text-leaf-deep">{t('livePrevent')}</p>
                      {r.prevention.do.map((d, i) => <p key={i} className="mt-1 text-[15px]">• {d}</p>)}
                      {r.prevention.avoid[0] && <p className="mt-1 text-[15px] text-[#9a2f17]">✕ {r.prevention.avoid[0]}</p>}
                    </div>
                  )}
                  {r.check.length > 0 && (
                    <div className="mt-3">
                      <p className="text-[14px] font-semibold text-soil-dark/80">{t('liveCheck')}</p>
                      {r.check.map((d, i) => <p key={i} className="mt-1 text-[14px] text-soil-dark/85">• {d}</p>)}
                    </div>
                  )}
                  {r.prevention.icar.length > 0 && <p className="mt-2 text-[13px] text-leaf-deep">ICAR: {r.prevention.icar.join(' · ')}</p>}
                </article>
              ))}
              {pending.length > risks.length && (
                <button onClick={() => setAllRisks(true)} className={`${SECONDARY} w-full`}>
                  {t('liveMoreRisks').replace('{n}', String(pending.length - risks.length))}
                </button>
              )}
            </div>
          </section>
        )}
      </div>

      <aside className="min-w-0 space-y-6">
        {/* How much was actually looked at. A verdict on top of forty clear
            close-ups and one on top of two are different claims, and the screen
            used to show them identically. */}
        {reading?.mode === 'video' && marks.length > 0 && (
          <section className={`${PANEL} p-5`}>
            <PanelHead icon={Video} title={t('liveReadTitle')}
              sub={t('liveReadLine').replace('{k}', String(readable)).replace('{n}', String(marks.length))} />
            <Timeline marks={marks} length={0} light className="mt-4" />
            <div className="mt-1 flex justify-between text-[12px] text-soil-dark/70 tabular-nums">
              <span>0:00</span><span>{clock(Math.max(...marks.map(([at]) => at)))}</span>
            </div>
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-soil-dark/80">
              {marks.some(([, m]) => m === 'h' || m === 'c') && (
                <span className="inline-flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-full bg-leaf" /> {t('liveMarkOk')}</span>
              )}
              {marks.some(([, m]) => m === 'p') && (
                <span className="inline-flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-full bg-ember" /> {t('liveMarkProblem')}</span>
              )}
              {marks.some(([, m]) => m === 'x') && (
                <span className="inline-flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-full bg-soil-dark/20" /> {t('liveMarkSkip')}</span>
              )}
              {marks.some(([, m]) => m === 'o') && reading.other_crop && (
                <span className="inline-flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-full bg-sky-400" /> {reading.other_crop.name}</span>
              )}
            </div>
          </section>
        )}
        {reading?.mode === 'walk' && (reading.skipped?.length ?? 0) > 0 && (
          <p className="rounded-[20px] bg-[#fbf0dc] p-4 text-[14px] text-soil-dark/85">
            {t('liveSkippedN').replace('{n}', String(reading.skipped!.length))}
          </p>
        )}

        <section className={`${PANEL} p-5`}>
          <PanelHead icon={CloudSun} title={t('liveFieldNow')} />
          <div className="mt-4 grid grid-cols-2 gap-3">
            <div className={tile}>
              <p className={tileHead}><CloudSun className="h-4 w-4" aria-hidden /> {t('liveNow')}</p>
              {w?.temp_c != null ? (
                <>
                  <p className="mt-1 text-[24px] font-semibold tabular-nums">{Math.round(w.temp_c)}°C</p>
                  <p className="text-[13px] text-soil-dark/75">{w.rh_pct}% · {w.text ?? ''}{w.rain_mm_1h ? ` · ${w.rain_mm_1h} mm` : ''}</p>
                </>
              ) : <p className="mt-1 text-[15px] text-soil-dark/70">—</p>}
            </div>
            <div className={tile}>
              <p className={tileHead}>{t('liveNext')}</p>
              {c.forecast ? (
                <>
                  <p className="mt-1 text-[15px]"><span className="text-[20px] font-semibold tabular-nums">{c.forecast.rain_mm} mm</span> {t('liveRain')}</p>
                  <p className="text-[13px] text-soil-dark/75">{c.forecast.t_min != null ? `${Math.round(c.forecast.t_min)}–${Math.round(c.forecast.t_max ?? 0)}°C` : ''}</p>
                </>
              ) : <p className="mt-1 text-[15px] text-soil-dark/70">—</p>}
            </div>
            <div className={tile}>
              <p className={tileHead}><Sprout className="h-4 w-4" aria-hidden /> {t('liveSoil')}</p>
              {ph ? (
                <>
                  <p className="mt-1 text-[20px] font-semibold">{t('livePh')} {ph.value}</p>
                  <p className="text-[13px] text-soil-dark/75">{ph.band} · {t(`how_${ph.how}`)}</p>
                </>
              ) : <p className="mt-1 text-[15px] text-soil-dark/70">—</p>}
              {moist && (
                <p className="mt-1.5 text-[13px] text-soil-dark/75">
                  <Droplets className="-mt-0.5 mr-1 inline h-3.5 w-3.5" />{t('liveMoisture')} {moist.value_pct}%
                </p>
              )}
            </div>
            <div className={tile}>
              <p className={tileHead}><Leaf className="h-4 w-4" aria-hidden /> {t('liveStage')}</p>
              <p className="mt-1 text-[15px] font-semibold">{c.crop.name}</p>
              <p className="text-[13px] text-soil-dark/75">{c.crop.stage_name} · {c.crop.das} {t('daysOld')}</p>
            </div>
          </div>
        </section>

        <div className="grid grid-cols-2 gap-3">
          <button onClick={onAgain} className={SECONDARY}>{t('liveAgain')}</button>
          <button onClick={onDone} className={PRIMARY}>{t('liveDone')}</button>
        </div>
        <p className="text-center text-[13px] text-soil-dark/70">
          {t('liveStats').replace('{f}', String(s.stats.frames)).replace('{c}', String(s.stats.classified_views))}
          {s.photo_model ? ` · ${s.model_version}` : ''}
        </p>
      </aside>

      {/* The photograph the finding rests on, large enough to check against
          the leaf in your hand. */}
      {zoom && (
        <div role="dialog" aria-modal="true" aria-label={zoom.name} onClick={() => setZoom(null)}
          className="fixed inset-0 z-[80] bg-black/90 flex flex-col items-center justify-center p-4">
          <img src={zoom.src} alt={zoom.name} className="max-w-full max-h-[80vh] rounded-2xl object-contain" />
          <p className="mt-3 text-sm text-white">{zoom.name}</p>
          <button ref={zoomClose} onClick={() => setZoom(null)} aria-label={t('liveClosePhoto')}
            className="absolute top-[max(1rem,env(safe-area-inset-top))] right-4 w-11 h-11 rounded-full bg-black/40 ring-1 ring-white/30 text-white flex items-center justify-center">
            <X className="w-5 h-5" />
          </button>
        </div>
      )}
    </div>
  )
}
