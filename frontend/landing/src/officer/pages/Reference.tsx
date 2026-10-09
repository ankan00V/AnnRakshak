import { api } from '../../api/client'
import { useAsync } from '../../lib/hooks'
import { PanelBone, PesticidePanel, RainfallSection } from '../panels'

/** Background the office reads rather than acts on: what the rain has done
 *  against the IMD normal, and the pesticide figure all of this has to move. */
export default function Reference() {
  const rainfall = useAsync(() => api.rainfall(), [])
  const pesticides = useAsync(() => api.pesticideBaseline(), [])

  return (
    <>
      {rainfall.data ? <RainfallSection r={rainfall.data} /> : <PanelBone rows={6} />}
      {pesticides.data?.available ? <PesticidePanel p={pesticides.data} /> : <PanelBone rows={5} />}
    </>
  )
}
