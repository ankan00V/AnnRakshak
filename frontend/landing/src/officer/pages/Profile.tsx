import { useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { api } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import { useAsync } from '../../lib/hooks'
import { Card, Pill } from '../../ui/kit'
import { Field, Fixed, ProfileCard, SaveBar, input, useProfileSave } from '../../ui/ProfileForm'
import { MAIN, SIDE, SPLIT } from '../../ui/layout'
import { PageHead } from '../panels'

/** The officer's own record.
 *
 *  Sign-up asks a page of questions — the post, the office, who they report to,
 *  the districts and crops they cover — and until now none of it could be read
 *  back, let alone corrected when a patch changed. What the district office
 *  checked them against is shown but not editable: an officer who could
 *  rewrite their employee ID, verify themselves or promote themselves to
 *  supervisor would be a way around verification, not a profile.
 */
export default function Profile() {
  const { me } = useAuth()
  const options = useAsync(() => api.authOptions('en'), [])
  const places = useAsync(() => api.places(), [], 'places')
  const { save, busy, done, error } = useProfileSave()
  const p = me?.profile

  const [org, setOrg] = useState(p?.organisation ?? '')
  const [years, setYears] = useState(String(p?.experience_years ?? ''))
  const [address, setAddress] = useState(p?.office_address ?? '')
  const [block, setBlock] = useState(p?.block ?? '')
  const [pincode, setPincode] = useState(p?.pincode ?? '')
  const [phone, setPhone] = useState(p?.office_phone ?? '')
  const [districts, setDistricts] = useState<string[]>(p?.districts ?? [])
  const [crops, setCrops] = useState<string[]>(p?.crops ?? [])
  const [specialities, setSpecialities] = useState<string[]>(p?.specialities ?? [])

  // Which districts this officer may put on their own record. Taking one on
  // is reach — a case from that district gets routed to them, carrying a
  // farmer's name, their village and photographs of their field — so only a
  // supervisor may widen a patch here; anyone else may drop one. The server
  // refuses the rest either way; this is so the screen does not offer what it
  // knows will be refused.
  const mine = p?.districts ?? []
  const inState = places.data?.states.find((s) => s.name === (p?.state ?? ''))?.districts ?? []
  const choices = p?.supervisor && inState.length ? inState.map((d) => d.name) : mine
  const toggle = (list: string[], set: (v: string[]) => void, id: string) =>
    set(list.includes(id) ? list.filter((x) => x !== id) : [...list, id])

  // The record stores the department's id; the office's own name for it comes
  // back with the sign-up options, and a slug is not what anybody calls their
  // service.
  const departmentName = (options.data?.departments ?? []).find((d) => d.id === p?.department)?.name
    ?? p?.department

  const chip = (on: boolean) =>
    `rounded-full px-3 py-1.5 text-xs font-medium border transition-colors ${
      on ? 'bg-leaf-deep text-cream border-leaf-deep' : 'bg-white border-soil-dark/15 text-soil-dark/70'}`

  return (
    <>
      <PageHead title="Your record"
        purpose="What this office knows about you. The lines the district office checked are shown but not yours to change." />

      <div className={`gap-5 ${SPLIT}`}>
        <div className={`${MAIN} space-y-5`}>
          <ProfileCard title="Your post">
            <Field label="Organisation / office">
              <input className={input} value={org} onChange={(e) => setOrg(e.target.value)} />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Years of field experience">
                <input className={input} type="number" min="0" max="60" value={years}
                  onChange={(e) => setYears(e.target.value)} />
              </Field>
              <Field label="Office phone">
                <input className={input} value={phone} onChange={(e) => setPhone(e.target.value)} />
              </Field>
            </div>
            <Field label="Office address">
              <input className={input} value={address} onChange={(e) => setAddress(e.target.value)} />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Block / taluka">
                <input className={input} value={block} onChange={(e) => setBlock(e.target.value)} />
              </Field>
              <Field label="PIN code">
                <input className={input} maxLength={6} value={pincode} onChange={(e) => setPincode(e.target.value)} />
              </Field>
            </div>
          </ProfileCard>

          <ProfileCard title="What you cover"
            sub={p?.supervisor
              ? 'New cases and outbreak alerts from these districts reach you first.'
              : 'New cases and outbreak alerts from these districts reach you first. The district office adds a district to your patch — you can drop one here.'}>
            <div className="flex flex-wrap gap-1.5">
              {choices.map((d) => (
                <button key={d} type="button" onClick={() => toggle(districts, setDistricts, d)}
                  className={chip(districts.includes(d))}>{d}</button>
              ))}
            </div>
            <p className="text-[12px] font-medium text-soil-dark/70 pt-1">Crops you advise on</p>
            <div className="flex flex-wrap gap-1.5">
              {(options.data?.crops ?? []).map((c) => (
                <button key={c.id} type="button" onClick={() => toggle(crops, setCrops, c.id)}
                  className={chip(crops.includes(c.id))}>{c.name}</button>
              ))}
            </div>
            <p className="text-[12px] font-medium text-soil-dark/70 pt-1">Your specialities</p>
            <div className="flex flex-wrap gap-1.5">
              {(options.data?.specialities ?? []).map((x) => (
                <button key={x.id} type="button" onClick={() => toggle(specialities, setSpecialities, x.id)}
                  className={chip(specialities.includes(x.id))}>{x.name}</button>
              ))}
            </div>
          </ProfileCard>

          <SaveBar busy={busy} done={done} error={error} label="Save my record"
            onSave={() => save({
              organisation: org.trim(), office_address: address.trim(), block: block.trim(),
              pincode: pincode.trim(), office_phone: phone.trim(),
              experience_years: years === '' ? undefined : Number(years),
              districts, crops, specialities,
            })} />
        </div>

        <aside className={`${SIDE} space-y-5`}>
          <Card className="p-4 md:p-5 space-y-2">
            <h2 className="font-semibold flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-leaf" /> Checked by the office
            </h2>
            <p className="text-xs text-soil-dark/60">
              These were verified when you were let in, so they are not editable here. The district office
              can change them.
            </p>
            <div className="flex flex-wrap gap-1.5 pt-1">
              <Pill tone={p?.verified ? 'leaf' : 'ochre'}>{p?.verified ? 'Verified' : 'Awaiting verification'}</Pill>
              {p?.supervisor && <Pill tone="dark">Supervisor</Pill>}
            </div>
            <div className="space-y-2 pt-1">
              <Fixed label="Name" value={me?.name} />
              <Fixed label="Post" value={p?.designation_name} />
              <Fixed label="Employee / staff ID" value={p?.employee_id} />
              <Fixed label="Department" value={departmentName} />
              <Fixed label="Reports to" value={[p?.reporting_name, p?.reporting_designation].filter(Boolean).join(' · ')} />
              <Fixed label="Sign-in email" value={me?.email} />
            </div>
          </Card>
        </aside>
      </div>
    </>
  )
}
