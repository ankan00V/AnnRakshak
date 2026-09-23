/** The shape of each farmer screen while its data is on the way.
 *
 *  These mirror the real layouts — same cards, same grid, same order — so the
 *  screen does not jump when the data lands. On a slow rural connection this is
 *  most of what a farmer sees for the first second, so it has to look like the
 *  app, not like a blank page.
 */

import { Bone, BoneLines, Card, Loading } from '../../ui/kit'
import { MAIN, ROW, SIDE, SPLIT } from '../layout'
import { useFarmer } from '../FarmerContext'

/** The farm card: district line, crop name, crop-stage bar. */
function FarmCardBone() {
  return (
    <Card className="p-5 h-full">
      <Bone className="h-3 w-40 rounded-full" />
      <Bone className="h-8 w-52 mt-3" />
      <Bone className="h-2 w-full mt-6 rounded-full" />
      <div className="mt-3 flex justify-between gap-2">
        {Array.from({ length: 5 }, (_, i) => <Bone key={i} className="h-2.5 w-14 rounded-full" />)}
      </div>
    </Card>
  )
}

/** Weather now: the big temperature, the three readings, the note under them. */
function WeatherNowBone() {
  return (
    <Card className="p-5 h-full">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Bone className="h-10 w-24" />
          <Bone className="h-3 w-16 mt-2 rounded-full" />
        </div>
        <div className="flex gap-5">
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className="space-y-2">
              <Bone className="h-5 w-5 rounded-lg" />
              <Bone className="h-2.5 w-8 rounded-full" />
            </div>
          ))}
        </div>
      </div>
      <Bone className="h-11 w-full mt-5 rounded-2xl" />
    </Card>
  )
}

/** The two big buttons: the live walk and the photo scan. */
function CtaBone() {
  return (
    <>
      {Array.from({ length: 2 }, (_, i) => (
        <div key={i} className="rounded-3xl bg-soil-dark/[0.07] p-5 motion-safe:animate-pulse">
          <div className="flex items-center gap-4">
            <Bone className="w-14 h-14 rounded-2xl" />
            <div className="flex-1 space-y-2">
              <Bone className="h-5 w-40" />
              <Bone className="h-3 w-52 rounded-full" />
            </div>
          </div>
        </div>
      ))}
    </>
  )
}

/** One "field check" card: title, the reason, the two things to check. */
export function AlertCardBone() {
  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <Bone className="h-4 w-44" />
        <Bone className="h-5 w-16 rounded-full" />
      </div>
      <BoneLines lines={2} />
      <div className="space-y-2 pt-1">
        <Bone className="h-3 w-5/6 rounded-full" />
        <Bone className="h-3 w-3/5 rounded-full" />
      </div>
      <div className="flex gap-2 pt-1">
        <Bone className="h-9 w-28 rounded-full" />
        <Bone className="h-9 w-24 rounded-full" />
      </div>
    </Card>
  )
}

/** A row in "recent problems" or the history list: thumbnail, name, status. */
export function ProblemRowBone() {
  return (
    <Card className="p-3 flex items-center gap-3">
      <Bone className="w-12 h-12 rounded-xl shrink-0" />
      <div className="flex-1 space-y-2">
        <Bone className="h-3.5 w-2/5" />
        <Bone className="h-2.5 w-1/4 rounded-full" />
      </div>
      <Bone className="h-6 w-16 rounded-full shrink-0" />
    </Card>
  )
}

function SectionBone({ children }: { children: React.ReactNode }) {
  return (
    <section>
      <Bone className="h-6 w-36 mb-3" />
      <div className="space-y-3">{children}</div>
    </section>
  )
}

export function HomeSkeleton() {
  const { t } = useFarmer()
  return (
    <Loading label={t('loading')}>
      {/* Below lg only the stacked order shows; from lg the same 8 | 4 split as the real screen. */}
      <div className="space-y-6 lg:space-y-8">
        <div className={ROW}>
          <div className="lg:col-span-8"><FarmCardBone /></div>
          <div className="hidden lg:block lg:col-span-4"><WeatherNowBone /></div>
        </div>
        <div className="lg:hidden"><WeatherNowBone /></div>
        <div className={SPLIT}>
          <div className={`${MAIN} space-y-6 lg:space-y-8`}>
            <div className="space-y-4 lg:grid lg:grid-cols-2 lg:gap-6 lg:space-y-0">
              <CtaBone />
            </div>
            <SectionBone>
              <AlertCardBone />
              <AlertCardBone />
            </SectionBone>
          </div>
          <aside className={`${SIDE} space-y-6 lg:space-y-8 mt-6 lg:mt-0`}>
            <Card className="p-4 space-y-3">
              <Bone className="h-3 w-24 rounded-full" />
              <div className="flex gap-2">
                {Array.from({ length: 4 }, (_, i) => <Bone key={i} className="h-16 flex-1 rounded-xl" />)}
              </div>
            </Card>
            <SectionBone>
              <ProblemRowBone />
              <ProblemRowBone />
            </SectionBone>
          </aside>
        </div>
      </div>
    </Loading>
  )
}

export function AlertsSkeleton() {
  const { t } = useFarmer()
  return (
    <Loading label={t('loading')}>
      <div className="space-y-6">
        <Bone className="h-8 w-48" />
        <div className={`space-y-6 ${SPLIT}`}>
          <div className={`space-y-6 ${MAIN}`}>
            <Card className="p-4 space-y-3">
              <Bone className="h-4 w-32" />
              <BoneLines lines={2} />
            </Card>
            <SectionBone>
              <AlertCardBone />
              <AlertCardBone />
            </SectionBone>
          </div>
          <aside className={`space-y-6 ${SIDE}`}>
            {Array.from({ length: 3 }, (_, i) => (
              <Card key={i} className="p-4 space-y-3">
                <Bone className="h-4 w-36" />
                <Bone className="h-10 w-full rounded-xl" />
              </Card>
            ))}
          </aside>
        </div>
      </div>
    </Loading>
  )
}

export function WeatherSkeleton() {
  const { t } = useFarmer()
  return (
    <Loading label={t('loading')}>
      <div className="space-y-6">
        <div className="space-y-2">
          <Bone className="h-8 w-52" />
          <Bone className="h-3 w-64 rounded-full" />
        </div>
        <WeatherNowBone />
        <SectionBone>
          {Array.from({ length: 2 }, (_, i) => (
            <Card key={i} className="p-4 space-y-2">
              <Bone className="h-4 w-40" />
              <BoneLines lines={2} />
            </Card>
          ))}
        </SectionBone>
        {/* The seven-day strip. */}
        <div className="grid grid-cols-4 gap-2 lg:grid-cols-7">
          {Array.from({ length: 7 }, (_, i) => (
            <Card key={i} className="p-3 space-y-2">
              <Bone className="h-2.5 w-10 rounded-full" />
              <Bone className="h-7 w-7 rounded-lg" />
              <Bone className="h-3 w-12 rounded-full" />
            </Card>
          ))}
        </div>
      </div>
    </Loading>
  )
}

export function HistorySkeleton() {
  const { t } = useFarmer()
  return (
    <Loading label={t('loading')}>
      <div className="space-y-4">
        <Bone className="h-8 w-44" />
        <div className="space-y-2">
          {Array.from({ length: 5 }, (_, i) => <ProblemRowBone key={i} />)}
        </div>
      </div>
    </Loading>
  )
}

export function ProblemDetailSkeleton() {
  const { t } = useFarmer()
  return (
    <Loading label={t('loading')}>
      <div className="space-y-4">
        <Bone className="h-3 w-20 rounded-full" />
        <Bone className="h-56 w-full rounded-2xl" />
        <div className="flex gap-2">
          <Bone className="h-6 w-24 rounded-full" />
          <Bone className="h-6 w-20 rounded-full" />
        </div>
        <Card className="p-4 space-y-3">
          <Bone className="h-5 w-48" />
          <BoneLines lines={3} />
        </Card>
        <Card className="p-4 space-y-3">
          <Bone className="h-4 w-36" />
          <BoneLines lines={4} />
        </Card>
      </div>
    </Loading>
  )
}

/** The farm picker, before we know which fields this farmer has. */
export function FarmPickerSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 2 }, (_, i) => (
        <Card key={i} className="p-4 flex items-center gap-3">
          <Bone className="w-10 h-10 rounded-xl shrink-0" />
          <div className="flex-1 space-y-2">
            <Bone className="h-4 w-32" />
            <Bone className="h-2.5 w-44 rounded-full" />
          </div>
        </Card>
      ))}
    </div>
  )
}
