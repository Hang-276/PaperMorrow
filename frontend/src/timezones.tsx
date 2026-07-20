import { useMemo } from 'react'

export type TimezoneOption = { value: string; label: string }

const fallbackZones = [
  'Asia/Shanghai', 'Asia/Hong_Kong', 'Asia/Tokyo', 'Asia/Seoul', 'Asia/Singapore', 'Asia/Kolkata',
  'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Zurich', 'Europe/Moscow',
  'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'America/Toronto',
  'America/Vancouver', 'America/Sao_Paulo', 'Australia/Sydney', 'Pacific/Auckland', 'UTC',
]

export const commonTimezoneValues = ['Asia/Shanghai', 'America/New_York', 'America/Los_Angeles']

export function systemTimezone() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Shanghai' }
  catch { return 'Asia/Shanghai' }
}

function zoneOffset(zone: string, locale: string) {
  try {
    const part = new Intl.DateTimeFormat(locale, { timeZone: zone, timeZoneName: 'longOffset' }).formatToParts(new Date()).find(item => item.type === 'timeZoneName')?.value
    return part?.replace('GMT', 'UTC') || 'UTC'
  } catch { return 'UTC' }
}

export function timezoneLabel(zone: string, locale = navigator.language) {
  const zh = locale.toLowerCase().startsWith('zh')
  const common: Record<string, [string, string]> = {
    'Asia/Shanghai': ['北京时间', 'Beijing Time'],
    'America/New_York': ['华盛顿时间', 'Washington, D.C. Time'],
    'America/Los_Angeles': ['美国西海岸时间', 'U.S. West Coast Time'],
  }
  let name: string | undefined = common[zone]?.[zh ? 0 : 1]
  if (!name) {
    try {
      name = new Intl.DateTimeFormat(locale, { timeZone: zone, timeZoneName: 'long' }).formatToParts(new Date()).find(item => item.type === 'timeZoneName')?.value
    } catch { /* fall through */ }
  }
  name ||= zone.split('_').join(' ').replace('/', ' · ')
  return `${name} (${zoneOffset(zone, locale)}) · ${zone}`
}

export function timezoneOptions(locale = navigator.language): TimezoneOption[] {
  const supported = (Intl as typeof Intl & { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf?.('timeZone') || fallbackZones
  const system = systemTimezone()
  const values = Array.from(new Set([...commonTimezoneValues, system, ...supported]))
  return values.map(value => ({ value, label: timezoneLabel(value, locale) }))
}

export function zonedDateTimeToIso(value: string, timeZone: string) {
  if (!value) return null
  const [datePart,timePart]=value.split('T')
  const [year,month,day]=datePart.split('-').map(Number)
  const [hour,minute]=timePart.split(':').map(Number)
  const wallClock=Date.UTC(year,month-1,day,hour,minute)
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(wallClock))
  const get=(type:string)=>Number(parts.find(part=>part.type===type)?.value||0)
  const represented=Date.UTC(get('year'),get('month')-1,get('day'),get('hour'),get('minute'))
  return new Date(wallClock-(represented-wallClock)).toISOString()
}

export function dateTimeInputInZone(value: string | null | undefined, timeZone: string) {
  if (!value) return ''
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(value))
  const get=(type:string)=>parts.find(part=>part.type===type)?.value||''
  return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`
}

export default function TimezoneSelect({ value, onChange, id }: { value: string; onChange: (value: string) => void; id?: string }) {
  const options = useMemo(() => timezoneOptions(), [])
  const common = options.filter(option => commonTimezoneValues.includes(option.value))
  const others = options.filter(option => !commonTimezoneValues.includes(option.value))
  return <select id={id} value={value} onChange={event => onChange(event.target.value)}>
    <optgroup label={navigator.language.toLowerCase().startsWith('zh') ? '常用时区' : 'Common time zones'}>{common.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</optgroup>
    <optgroup label={navigator.language.toLowerCase().startsWith('zh') ? '全部时区' : 'All time zones'}>{others.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</optgroup>
  </select>
}
