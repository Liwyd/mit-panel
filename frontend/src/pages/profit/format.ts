/**
 * Number and label formatting for the profit page. One digit system on the
 * whole page: Persian digits, via Intl, so a value never mixes 1 and ۱.
 */

const faNumber = new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 0 })
const faDecimal = new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 1, minimumFractionDigits: 0 })

const JALALI_MONTHS = [
    'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
    'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند',
]

export const UNIT_TOMAN = 'تومان'
export const UNIT_GB = 'گیگ'

/** 1234567 -> ۱٬۲۳۴٬۵۶۷ */
export function fa(value: number): string {
    return faNumber.format(Math.round(value))
}

/** One decimal at most: ۱۲٫۵ */
export function faDec(value: number): string {
    return faDecimal.format(value)
}

const faFactorFormat = new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 3, useGrouping: false })

/** A multiplier as typed: 1.4 -> ۱٫۴, 1.25 -> ۱٫۲۵ (no grouping, up to 3 decimals). */
export function faFactor(value: number): string {
    return faFactorFormat.format(value)
}

/** 0.123 -> ۱۲٪ (null shows a dash). */
export function faPercent(value: number | null | undefined, digits = 0): string {
    if (value === null || value === undefined || !Number.isFinite(value)) return '—'
    const text = new Intl.NumberFormat('fa-IR', {
        maximumFractionDigits: digits,
        minimumFractionDigits: digits,
    }).format(value * 100)
    return `${text}٪`
}

export function monthName(key: string): string {
    const month = Number(key.split('-')[1])
    return JALALI_MONTHS[month - 1] ?? key
}

export function monthYear(key: string): string {
    return fa(Number(key.split('-')[0])).replace(/٬/g, '')
}

/**
 * Axis scale: ticks in whole units of a readable size (millions, thousands...)
 * with the unit named once for the whole axis, so tick labels stay short.
 */
export interface AxisScale {
    ticks: number[]
    min: number
    max: number
    divisor: number
    unit: string
}

function niceStep(raw: number): number {
    const power = Math.pow(10, Math.floor(Math.log10(raw)))
    const fraction = raw / power
    const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10
    return nice * power
}

export function axisScale(minValue: number, maxValue: number, target = 4): AxisScale {
    const low = Math.min(0, minValue)
    const high = Math.max(0, maxValue)
    const span = high - low || 1
    const step = niceStep(span / target)
    const min = Math.floor(low / step) * step
    const max = Math.ceil(high / step) * step
    const ticks: number[] = []
    for (let tick = min; tick <= max + step / 2; tick += step) ticks.push(Math.round(tick))
    const big = Math.max(Math.abs(min), Math.abs(max))
    const [divisor, unit] =
        big >= 1e9 ? [1e9, 'میلیارد تومان'] : big >= 1e6 ? [1e6, 'میلیون تومان'] : big >= 1e3 ? [1e3, 'هزار تومان'] : [1, 'تومان']
    return { ticks, min, max, divisor, unit }
}

export function tickLabel(value: number, divisor: number): string {
    return faDecimal.format(value / divisor)
}

/** A user-typed number: Persian/Arabic digits and thousands separators are fine. */
export function parseNumber(text: string): number {
    const latin = text
        .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0))
        .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660))
        .replace(/[٬,،\s]/g, '')
        .replace(/٫/g, '.')
    if (latin === '') return NaN
    return Number(latin)
}

/** "+۱۲٪ نسبت به ماه قبل", or a note when there is nothing to compare with. */
export function versus(current: number, previous: number | null | undefined): string {
    if (previous === null || previous === undefined || previous === 0) return 'ماه قبل داده‌ای ندارد'
    const change = ((current - previous) / Math.abs(previous)) * 100
    const rounded = Math.round(change)
    const sign = rounded > 0 ? '+' : rounded < 0 ? '−' : ''
    // The signed figure is an LTR island so the sign stays on its left.
    return `\u2066${sign}${fa(Math.abs(rounded))}٪\u2069 نسبت به ماه قبل`
}

export function versusPoints(current: number | null, previous: number | null | undefined): string {
    if (current === null || previous === null || previous === undefined) return 'ماه قبل داده‌ای ندارد'
    const points = (current - previous) * 100
    const rounded = Math.round(points * 10) / 10
    const sign = rounded > 0 ? '+' : rounded < 0 ? '−' : ''
    return `\u2066${sign}${faDec(Math.abs(rounded))}\u2069 واحد درصد نسبت به ماه قبل`
}
