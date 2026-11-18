import type { ReactNode } from 'react'
import { BadgeCheck, MapPin, Sprout } from 'lucide-react'
import { useFarmer } from '../farmer/FarmerContext'
import { fieldPhoto } from '../farmer/fieldPhoto'
import { bcp47, LANGS } from '../lib/i18n'
import BrandMark from '../ui/BrandMark'
import type { Draft, DraftField } from './progress'

/** The phone beside the sign-up form: the farmer's (or expert's) profile as
 *  the app will show it, filling in as they type. It is drawn from the form's
 *  own state, so it is never ahead of or behind what they have entered, and it
 *  uses the app's Profile screen look — the sunset header, the initials, the
 *  tags, the field cards with each crop's own photograph. */

/** An iPhone 15 to the same proportions as the app captures: titanium edge,
 *  black bezel, the camera island, status bar and home indicator. */
export function Handset({ children }: { children: ReactNode }) {
  return (
    <div className="relative w-[290px] rounded-[54px] bg-[linear-gradient(160deg,#d3d6d4,#8e9390_30%,#b5b9b6_60%,#7e8380)] p-[3px] shadow-[0_44px_80px_-36px_rgba(0,0,0,0.75)]">
      <span aria-hidden className="absolute -left-[3px] top-[118px] h-8 w-[3px] rounded-l bg-[#6b706d]" />
      <span aria-hidden className="absolute -left-[3px] top-[166px] h-14 w-[3px] rounded-l bg-[#6b706d]" />
      <span aria-hidden className="absolute -left-[3px] top-[232px] h-14 w-[3px] rounded-l bg-[#6b706d]" />
      <span aria-hidden className="absolute -right-[3px] top-[190px] h-20 w-[3px] rounded-r bg-[#6b706d]" />
      <div className="rounded-[51px] bg-[#0a0a0b] p-[9px]">
        <div className="relative h-[596px] overflow-hidden rounded-[42px] bg-[#f6f1e6] text-soil-dark">
          <div aria-hidden className="absolute inset-x-0 top-0 z-20 flex h-[44px] items-center justify-between px-7 pt-1 text-[13px] font-semibold text-[#111]">
            <span>9:41</span>
            <svg width="58" height="11" viewBox="0 0 78 13" fill="#111">
              <rect x="0" y="9" width="3.2" height="4" rx="1" /><rect x="4.8" y="6.5" width="3.2" height="6.5" rx="1" />
              <rect x="9.6" y="3.8" width="3.2" height="9.2" rx="1" /><rect x="14.4" y="1" width="3.2" height="12" rx="1" />
              <path d="M30.5 3.4a10 10 0 0 1 13 0l-1.3 1.4a8 8 0 0 0-10.4 0zM32.8 5.9a6.6 6.6 0 0 1 8.4 0l-1.3 1.4a4.7 4.7 0 0 0-5.8 0zM35 8.4a3.2 3.2 0 0 1 4 0L37 10.6z" transform="translate(-1 0.5)" />
              <rect x="50.5" y="0.5" width="24" height="12" rx="3.6" fill="none" stroke="#111" strokeOpacity=".4" />
              <rect x="52.5" y="2.5" width="20" height="8" rx="2" />
            </svg>
          </div>
          <span aria-hidden className="absolute left-1/2 top-[10px] z-30 h-[26px] w-[92px] -translate-x-1/2 rounded-full bg-black" />
          <div className="h-full overflow-hidden pt-[44px]">{children}</div>
          <span aria-hidden className="absolute bottom-[7px] left-1/2 z-20 h-[4px] w-[104px] -translate-x-1/2 rounded-full bg-[#111]" />
        </div>
      </div>
    </div>
  )
}

const initials = (name: string) => name.trim().split(/\s+/).slice(0, 2).map((w) => w[0] ?? '').join('').toUpperCase()

/** Something not yet filled in: a soft bar where the words will be. */
function Pending({ w = 'w-24', tone = 'bg-white/35' }: { w?: string; tone?: string }) {
  return <span className={`inline-block h-3 rounded-full align-middle ${w} ${tone}`} />
}

function Tag({ children }: { children: ReactNode }) {
  return <span className="rounded-full bg-[#eef3e6] px-2.5 py-0.5 text-[10px] font-medium text-leaf-deep">{children}</span>
}

export function ProfilePreview({ draft }: { draft: Draft }) {
  const { t, lang } = useFarmer()
  const language = LANGS.find((l) => l.code === lang)?.label
  const expert = draft.role === 'expert'
  const acres = draft.fields.reduce((n, f) => n + (parseFloat(f.area) || 0), 0)
  return (
    <div className="flex h-full flex-col gap-2.5 px-3 pb-5 text-left">
      {/* The app's own top bar. */}
      <div className="flex items-center justify-between px-1 pt-1">
        <span className="flex items-center gap-1.5 text-[12px] font-semibold text-[#1f3a26]"><BrandMark size={22} /> AnnRakshak</span>
        <span className="grid h-7 w-7 place-items-center rounded-full bg-[#1d4a2c] text-[10px] font-semibold text-cream">
          {initials(draft.name) || <Sprout className="h-3.5 w-3.5" />}
        </span>
      </div>

      {/* The Profile header: a photograph, the initials, the name, the place. */}
      <div className="relative h-[138px] shrink-0 overflow-hidden rounded-[18px] bg-[#1d4a2c]">
        <img src={expert ? '/photos/card-expert.webp' : '/photos/sunset.webp'} alt=""
          className={`absolute inset-0 h-full w-full object-cover ${expert ? 'object-[40%_28%]' : 'object-[center_60%]'}`} />
        <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/25 to-black/5" />
        <div className="relative flex h-full items-end gap-2.5 p-3 text-white">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-white text-[15px] font-semibold text-[#2f6a39] shadow-lg transition-all">
            {initials(draft.name) || <Sprout className="h-5 w-5" />}
          </span>
          <div className="min-w-0 pb-0.5">
            <p className="font-instrument-serif text-[22px] leading-none [overflow-wrap:anywhere]">
              {draft.name || <Pending w="w-28" />}
            </p>
            <p className="mt-1.5 flex items-center gap-1 text-[10px] leading-tight text-white/90">
              <MapPin className="h-3 w-3 shrink-0" aria-hidden />
              {(expert ? draft.post || draft.place : draft.place) || <Pending w="w-20" tone="bg-white/25" />}
            </p>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5 px-0.5">
        <Tag>{expert ? t('authExpert') : t('profileRoleFarmer')}</Tag>
        {language && <Tag>{language}</Tag>}
        {draft.phone && <Tag>+91 {draft.phone.replace(/\D/g, '').slice(-10)}</Tag>}
      </div>

      {expert ? <ExpertBody draft={draft} /> : (
        <>
          <div className="grid grid-cols-2 gap-1.5">
            <Stat label={t('profileStatFields')} value={draft.fields.length} />
            <Stat label={t('profileStatAcres')} value={Math.round(acres * 10) / 10} />
          </div>
          <div className="min-h-0 space-y-1.5 overflow-hidden">
            {draft.fields.length
              ? draft.fields.map((f, i) => <FieldRow key={i} f={f} lang={lang} acresLabel={t('acres')} />)
              : (
                <div className="grid h-[70px] place-items-center rounded-[14px] border-2 border-dashed border-[#1d4a2c]/15 text-[10px] text-soil-dark/50">
                  {t('authFieldsTitle')}
                </div>
              )}
          </div>
        </>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-[12px] bg-white px-2.5 py-2 ring-1 ring-black/[0.04]">
      <p className="font-instrument-serif text-[20px] leading-none text-[#1f3a26] tabular-nums">{value}</p>
      <p className="mt-0.5 text-[9px] text-soil-dark/60">{label}</p>
    </div>
  )
}

function FieldRow({ f, lang, acresLabel }: { f: DraftField; lang: string; acresLabel: string }) {
  const photo = fieldPhoto({ crop: f.crop })
  const sown = f.sowing ? new Date(f.sowing).toLocaleDateString(bcp47(lang as never), { day: 'numeric', month: 'short' }) : ''
  return (
    <div className="flex items-center gap-2.5 rounded-[14px] bg-white p-1.5 ring-1 ring-black/[0.04] animate-fadein">
      <span className="h-11 w-11 shrink-0 overflow-hidden rounded-[10px] bg-[#dfe6d3]">
        {photo && <img src={photo.src} alt="" className="h-full w-full object-cover" />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-instrument-serif text-[15px] leading-tight text-[#1f3a26]">{f.cropName}</span>
        <span className="block truncate text-[9.5px] text-soil-dark/60">
          {[f.area && `${f.area} ${acresLabel}`, sown, f.irrigation].filter(Boolean).join(' · ')}
        </span>
      </span>
    </div>
  )
}

function ExpertBody({ draft }: { draft: Draft }) {
  const { t } = useFarmer()
  const covers = draft.covers ?? []
  const crops = draft.crops ?? []
  return (
    <div className="space-y-2">
      <div className="rounded-[14px] bg-white p-2.5 ring-1 ring-black/[0.04]">
        <p className="flex items-center gap-1 text-[10px] font-semibold text-[#1f3a26]">
          <BadgeCheck className="h-3.5 w-3.5 text-[#4f8a37]" aria-hidden /> {t('authDistricts')}{draft.place ? ` · ${draft.place}` : ''}
        </p>
        <div className="mt-1.5 flex flex-wrap gap-1">
          {covers.length ? covers.slice(0, 8).map((d) => <Tag key={d}>{d}</Tag>) : <Pending w="w-32" tone="bg-[#1d4a2c]/10" />}
          {covers.length > 8 && <Tag>+{covers.length - 8}</Tag>}
        </div>
      </div>
      <div className="rounded-[14px] bg-white p-2.5 ring-1 ring-black/[0.04]">
        <p className="text-[10px] font-semibold text-[#1f3a26]">{t('authCrops')}</p>
        <div className="mt-1.5 flex flex-wrap gap-1">
          {crops.length ? crops.map((c) => <Tag key={c}>{c}</Tag>) : <Pending w="w-24" tone="bg-[#1d4a2c]/10" />}
        </div>
      </div>
    </div>
  )
}
