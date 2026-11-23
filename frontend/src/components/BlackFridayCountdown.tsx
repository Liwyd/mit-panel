import { useEffect, useState } from 'react'
import { useBlackFriday } from '@/lib/black-friday'

/*
 * A red dot-matrix clock counting down to the end of the Black Friday theme.
 * It shows days and hours only, each as two digits of a 5x7 dot grid, with a
 * colon between them that blinks once a second so the clock still feels live.
 * A dot lights in 70ms and fades over 260ms, like LED phosphor. Reduced motion
 * keeps the numbers and drops the fades.
 */

const FONT: Record<number, string[]> = {
    0: ['01110', '10001', '10011', '10101', '11001', '10001', '01110'],
    1: ['00100', '01100', '00100', '00100', '00100', '00100', '01110'],
    2: ['01110', '10001', '00001', '00010', '00100', '01000', '11111'],
    3: ['11111', '00010', '00100', '00010', '00001', '10001', '01110'],
    4: ['00010', '00110', '01010', '10010', '11111', '00010', '00010'],
    5: ['11111', '10000', '11110', '00001', '00001', '10001', '01110'],
    6: ['00110', '01000', '10000', '11110', '10001', '10001', '01110'],
    7: ['11111', '00001', '00010', '00100', '01000', '01000', '01000'],
    8: ['01110', '10001', '10001', '01110', '10001', '10001', '01110'],
    9: ['01110', '10001', '10001', '01111', '00001', '00010', '01100'],
}
const COLON = '0010100'
const UNITS = ['days', 'hours'] as const

const styles = `
.bf-cd{
  position:relative;display:flex;align-items:center;justify-content:space-between;gap:32px;
  background:#070606;border:1px solid rgba(255,59,47,.14);border-radius:20px;
  padding:24px 28px;color:#ede9e6;
  animation:bf-cd-rise 420ms cubic-bezier(.23,1,.32,1) both;
}
.bf-cd-text{min-width:0}
.bf-cd-k{display:flex;align-items:center;gap:8px;font-size:13px;line-height:20px;color:#a8a19d;margin-bottom:8px}
.bf-cd-k i{width:6px;height:6px;border-radius:50%;background:#ff3b2f}
.bf-cd-t{font-size:24px;line-height:1.2;font-weight:500;letter-spacing:0}
.bf-cd-msg{font-size:14px;line-height:22px;color:#a8a19d;margin-top:4px}
.bf-cd-end{font-size:12px;line-height:16px;color:#86807c;margin-top:12px;font-variant-numeric:tabular-nums}
.bf-clock{--d:10px;--g:4px;display:flex;align-items:flex-start;gap:calc(var(--d)*2);flex-shrink:0;direction:ltr}
.bf-unit{display:flex;flex-direction:column;align-items:center;gap:10px}
.bf-pair{display:flex;gap:calc(var(--d) + var(--g))}
.bf-digit{display:grid;grid-template-columns:repeat(5,var(--d));grid-auto-rows:var(--d);gap:var(--g)}
.bf-colon{display:grid;grid-template-columns:var(--d);grid-template-rows:repeat(7,var(--d));gap:var(--g)}
.bf-digit span,.bf-colon span{
  border-radius:50%;background:rgba(255,59,47,.07);
  transition:background-color 260ms ease,box-shadow 260ms ease;
}
.bf-digit span.on,.bf-colon span.on{
  background:#ff3b2f;box-shadow:0 0 calc(var(--d)*.9) rgba(255,59,47,.45);
  transition-duration:70ms;
}
.bf-colon span.on{animation:bf-cd-blink 1s steps(1,end) both}
@keyframes bf-cd-blink{0%{background:#ff3b2f}50%{background:rgba(255,59,47,.3);box-shadow:none}}
.bf-cap{font-size:11px;line-height:16px;color:#86807c}
@keyframes bf-cd-rise{from{opacity:0;transform:translateY(8px)}}
@media (prefers-reduced-motion:reduce){
  .bf-cd{animation:none}
  .bf-digit span,.bf-colon span{transition:none}
  .bf-colon span.on{animation:none}
}
@media (max-width:1100px){.bf-clock{--d:8px;--g:3px}}
@media (max-width:767px){
  .bf-cd{flex-direction:column;align-items:stretch;gap:24px;padding:20px}
  .bf-clock{--d:7px;--g:3px;justify-content:flex-start;align-self:flex-start}
}
`

function Digit({ value }: { value: number }) {
    const rows = FONT[value] ?? FONT[0]
    return (
        <div className="bf-digit">
            {rows.flatMap((row, r) =>
                [...row].map((bit, c) => <span key={r * 5 + c} className={bit === '1' ? 'on' : undefined} />)
            )}
        </div>
    )
}

// Remounted on every tick (keyed by the second), which restarts its blink:
// lit on the tick, dimmed for the second half.
function Colon() {
    return (
        <div className="bf-colon">
            {[...COLON].map((bit, i) => <span key={i} className={bit === '1' ? 'on' : undefined} />)}
        </div>
    )
}

// Ticks on the second boundary, so the clock changes with the system clock
// rather than drifting a few hundred ms behind it. Paused in hidden tabs.
function useNow(enabled: boolean) {
    const [now, setNow] = useState(() => Date.now())
    useEffect(() => {
        if (!enabled) return
        let timer = 0
        const tick = () => {
            setNow(Date.now())
            timer = window.setTimeout(tick, 1000 - (Date.now() % 1000) + 5)
        }
        const onVisibility = () => {
            window.clearTimeout(timer)
            if (!document.hidden) tick()
        }
        tick()
        document.addEventListener('visibilitychange', onVisibility)
        return () => {
            window.clearTimeout(timer)
            document.removeEventListener('visibilitychange', onVisibility)
        }
    }, [enabled])
    return now
}

const endFormat = new Intl.DateTimeFormat('en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Tehran',
})

function formatEnd(date: Date): string {
    const parts = Object.fromEntries(endFormat.formatToParts(date).map((p) => [p.type, p.value]))
    return `Until ${parts.weekday}, ${parts.day} ${parts.month} · ${parts.hour}:${parts.minute}`
}

export function BlackFridayCountdown() {
    const { active, endsAt } = useBlackFriday()
    const now = useNow(active)

    if (!active || !endsAt) return null

    const total = Math.max(0, Math.floor((endsAt.getTime() - now) / 1000))
    const values = [Math.min(99, Math.floor(total / 86400)), Math.floor(total / 3600) % 24]

    return (
        <section className="bf-cd" aria-label="Black Friday countdown">
            <style>{styles}</style>
            <div className="bf-cd-text">
                <div className="bf-cd-k"><i />Black Friday</div>
                <div className="bf-cd-t">Ends in</div>
                <div className="bf-cd-msg" dir="rtl" lang="fa">برای دریافت تخفیف از ربات اقدام کنید</div>
                <div className="bf-cd-end">{formatEnd(endsAt)}</div>
            </div>
            <div
                className="bf-clock"
                role="timer"
                aria-label={`${values[0]} days ${values[1]} hours left`}
            >
                {UNITS.map((unit, i) => (
                    <div key={unit} style={{ display: 'contents' }}>
                        {i > 0 && <Colon key={Math.floor(now / 1000)} />}
                        <div className="bf-unit" aria-hidden="true">
                            <div className="bf-pair">
                                <Digit value={Math.floor(values[i] / 10)} />
                                <Digit value={values[i] % 10} />
                            </div>
                            <div className="bf-cap">{unit}</div>
                        </div>
                    </div>
                ))}
            </div>
        </section>
    )
}
