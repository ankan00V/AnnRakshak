import { useState, type ReactNode } from 'react'
import {
  Bug, Cloud, CloudDrizzle, CloudFog, CloudLightning, CloudMoon, CloudRain, CloudSun, Moon, Sun,
} from 'lucide-react'
import { wmoKey } from './tokens'

/** The pieces the farmer's tab screens are built from, so Home, Weather and
 *  Scan read as one app rather than three. */

/** A panel's heading: one line a farmer reads first, and the line under it. */
export function PanelHead({ icon: Icon, title, sub, action }: {
  icon?: typeof Sun; title: string; sub?: string; action?: ReactNode
}) {
  return (
    <div className="flex items-start gap-3">
      {Icon && (
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[#e3efd9] text-[#2f6a39]">
          <Icon className="h-6 w-6" aria-hidden />
        </span>
      )}
      <div className="min-w-0 flex-1">
        <h2 className="text-[20px] font-semibold tracking-tight text-balance sm:text-[22px]">{title}</h2>
        {sub && <p className="text-[14px] text-soil-dark/75 sm:text-[15px]">{sub}</p>}
      </div>
      {action}
    </div>
  )
}

/** The white of a card curving up into the photograph above it. */
export function PhotoCurve() {
  return (
    <svg aria-hidden viewBox="0 0 400 24" preserveAspectRatio="none" className="absolute inset-x-0 -bottom-px h-6 w-full">
      <path d="M0 24 V14 Q200 -8 400 14 V24 Z" fill="#fff" />
    </svg>
  )
}

/** The sky as a picture: sun, cloud, rain, storm. */
export function SkyIcon({ code, night, className = '' }: { code: number | null; night: boolean; className?: string }) {
  const k = wmoKey(code)
  const Icon = k === 'wmo_clear' ? (night ? Moon : Sun)
    : k === 'wmo_partly' ? (night ? CloudMoon : CloudSun)
      : k === 'wmo_rain' || k === 'wmo_showers' ? CloudRain
        : k === 'wmo_drizzle' ? CloudDrizzle
          : k === 'wmo_thunder' ? CloudLightning
            : k === 'wmo_fog' ? CloudFog
              : Cloud
  const color = Icon === Sun || Icon === CloudSun ? 'text-[#e6a21a]' : Icon === Moon || Icon === CloudMoon ? 'text-soil-dark/70' : 'text-sky-600'
  return <Icon aria-hidden className={`${color} ${className}`} strokeWidth={1.75} />
}

/** A real photograph of the problem, where the knowledge base has one. */
export function PestPhoto({ target, className = 'h-16 w-16 sm:h-[76px] sm:w-[88px]' }: { target: string; className?: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) {
    return (
      <span className={`flex shrink-0 items-center justify-center rounded-2xl bg-white/70 text-leaf-deep ${className}`} aria-hidden>
        <Bug className="h-8 w-8" />
      </span>
    )
  }
  return (
    <img src={`/api/kb/photo/${target}`} alt="" loading="lazy" onError={() => setFailed(true)}
      className={`shrink-0 rounded-2xl object-cover ${className}`} />
  )
}
