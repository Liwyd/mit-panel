import { useEffect, useState } from 'react'
import { useBlackFriday } from '@/lib/black-friday'

/*
 * Countdown to the end of the Black Friday theme, as a quiet flip clock:
 * two cards, days and hours. When a value changes the upper leaf falls away
 * and the lower one lands, like a split-flap board. That happens on the
 * hour, and once per browser session as an entrance; the small red dot in the
 * label breathes so the card reads as live in between. Reduced motion swaps
 * the numbers without the flip.
 */

const styles = `
.bf-cd{
  position:relative;display:flex;align-items:center;justify-content:space-between;gap:32px;
  background:#0a0909;border:1px solid rgba(237,233,230,.07);border-radius:20px;
  padding:24px 28px;color:#ede9e6;overflow:hidden;isolation:isolate;
  animation:bf-cd-rise 420ms cubic-bezier(.23,1,.32,1) backwards;
}
.bf-cd-text{position:relative;z-index:1;min-width:0}
/* Newsprint: the event name set as dense bold small caps in deep red, at low
   opacity, filling the card behind the content like a printed sheet. It fades
   out under the text column so the copy keeps full contrast. */
.bf-cd-print{position:absolute;inset:-4px;z-index:0;pointer-events:none;user-select:none;
  font-size:11px;line-height:14px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;
  color:#d9241c;opacity:.14;text-align:justify;word-spacing:.2em;overflow:hidden;
  -webkit-mask-image:linear-gradient(90deg,rgba(0,0,0,.25) 0%,rgba(0,0,0,.45) 35%,#000 70%);
  mask-image:linear-gradient(90deg,rgba(0,0,0,.25) 0%,rgba(0,0,0,.45) 35%,#000 70%)}
.bf-cd-k{display:flex;align-items:center;gap:8px;font-size:13px;line-height:20px;color:#a8a19d;margin-bottom:8px}
.bf-cd-k i{width:6px;height:6px;border-radius:50%;background:#ff3b2f;animation:bf-cd-live 2.4s ease-in-out infinite}
.bf-cd-t{font-size:24px;line-height:1.2;font-weight:500;letter-spacing:0}
.bf-cd-msg{width:fit-content;font-size:14px;line-height:22px;color:#a8a19d;margin-top:4px}
.bf-cd-end{font-size:12px;line-height:16px;color:#86807c;margin-top:12px;font-variant-numeric:tabular-nums}

.bf-clock{position:relative;z-index:1;--w:96px;--h:112px;--fs:64px;display:flex;align-items:flex-start;gap:12px;flex-shrink:0;direction:ltr}
.bf-unit{display:flex;flex-direction:column;align-items:center;gap:10px}
.bf-sep{height:var(--h);display:flex;align-items:center;text-shadow:0 0 6px #0a0909;font-size:calc(var(--fs)*.5);color:#4a4542;line-height:1}
.bf-cap{font-size:11px;line-height:16px;color:#a8a19d;background:#0a0909;padding:0 6px;border-radius:4px}

.bf-flip{position:relative;width:var(--w);height:var(--h);perspective:600px;
  font-size:var(--fs);font-weight:500;color:#f1ece8;font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.bf-half,.bf-leaf{position:absolute;left:0;right:0;height:50%;overflow:hidden;backface-visibility:hidden}
.bf-half span,.bf-leaf span{position:absolute;left:0;right:0;top:0;height:var(--h);line-height:var(--h);text-align:center}
.bf-top{top:0;border-radius:12px 12px 0 0;background:linear-gradient(180deg,#1d1a19,#171514);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.05)}
.bf-bottom{bottom:0;border-radius:0 0 12px 12px;background:linear-gradient(180deg,#141211,#100e0e)}
.bf-bottom span{top:auto;bottom:0}
/* the hinge: a dark seam with a faint lit edge under it */
.bf-flip::after{content:"";position:absolute;left:0;right:0;top:50%;height:1px;margin-top:-1px;
  background:#050404;box-shadow:0 1px 0 rgba(255,255,255,.035);z-index:3}
.bf-leaf.bf-top{transform-origin:50% 100%;z-index:2;animation:bf-fall 300ms cubic-bezier(.55,0,.9,.4) forwards}
.bf-leaf.bf-bottom{transform-origin:50% 0;z-index:2;animation:bf-land 340ms cubic-bezier(.23,1,.32,1) 280ms backwards}
.bf-leaf.bf-top::after{content:"";position:absolute;inset:0;background:#000;opacity:0;animation:bf-shade 300ms ease-in forwards}

@keyframes bf-fall{to{transform:rotateX(-90deg)}}
@keyframes bf-land{from{transform:rotateX(90deg)}}
@keyframes bf-shade{to{opacity:.45}}
@keyframes bf-cd-rise{from{opacity:0;transform:translateY(8px)}}
@keyframes bf-cd-live{50%{opacity:.3}}

@media (prefers-reduced-motion:reduce){
  .bf-cd{animation:none}
  .bf-cd-k i{animation:none}
  .bf-leaf{display:none}
}
@media (max-width:1100px){.bf-clock{--w:80px;--h:94px;--fs:52px}}
@media (max-width:767px){
  .bf-cd-print{-webkit-mask-image:linear-gradient(180deg,rgba(0,0,0,.3) 0%,rgba(0,0,0,.45) 45%,#000 80%);mask-image:linear-gradient(180deg,rgba(0,0,0,.3) 0%,rgba(0,0,0,.45) 45%,#000 80%)}
  .bf-cd{flex-direction:column;align-items:stretch;gap:24px;padding:20px}
  .bf-clock{--w:72px;--h:84px;--fs:46px;align-self:flex-start;gap:10px}
}
`

const INTRO_KEY = 'bf-flip-intro'

function introSeen(): boolean {
    try {
        return sessionStorage.getItem(INTRO_KEY) === '1'
    } catch {
        return true
    }
}

function FlipCard({ value, intro }: { value: string; intro: boolean }) {
    // prev is what the card showed before the latest change; n counts changes
    // and keys the leaves, so each change remounts them and replays the flip.
    // The first value flips in from blank once per session.
    const [state, setState] = useState(() => ({ cur: value, prev: intro ? '' : value, n: intro ? 1 : 0 }))
    if (state.cur !== value) setState({ cur: value, prev: state.cur, n: state.n + 1 })

    const flipping = state.n > 0
    return (
        <div className="bf-flip">
            <div className="bf-half bf-top"><span>{state.cur}</span></div>
            <div className="bf-half bf-bottom"><span>{flipping ? state.prev : state.cur}</span></div>
            {flipping && (
                <>
                    <div key={`t${state.n}`} className="bf-leaf bf-top"><span>{state.prev}</span></div>
                    <div key={`b${state.n}`} className="bf-leaf bf-bottom"><span>{state.cur}</span></div>
                </>
            )}
        </div>
    )
}

// Re-renders on each minute boundary; that is enough for days and hours.
// Paused while the tab is hidden, re-synced when it comes back.
function useNow(enabled: boolean) {
    const [now, setNow] = useState(() => Date.now())
    useEffect(() => {
        if (!enabled) return
        let timer = 0
        const tick = () => {
            setNow(Date.now())
            timer = window.setTimeout(tick, 60000 - (Date.now() % 60000) + 50)
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

const pad = (n: number) => String(n).padStart(2, '0')

// Enough copies to fill the widest card; the overflow is clipped.
const PRINT = Array.from({ length: 160 }, () => 'MIT VPN BLACK FRIDAY').join(' · ')

export function BlackFridayCountdown() {
    const { active, endsAt } = useBlackFriday()
    const now = useNow(active)
    const [intro] = useState(() => !introSeen())

    useEffect(() => {
        if (!intro) return
        try {
            sessionStorage.setItem(INTRO_KEY, '1')
        } catch {
            // The entrance just plays again next time.
        }
    }, [intro])

    if (!active || !endsAt) return null

    const total = Math.max(0, Math.floor((endsAt.getTime() - now) / 1000))
    const days = Math.min(99, Math.floor(total / 86400))
    const hours = Math.floor(total / 3600) % 24

    return (
        <section className="bf-cd" aria-label="Black Friday countdown">
            <style>{styles}</style>
            <div className="bf-cd-print" aria-hidden="true">{PRINT}</div>
            <div className="bf-cd-text">
                <div className="bf-cd-k"><i />Black Friday</div>
                <div className="bf-cd-t">Ends in</div>
                <div className="bf-cd-msg" dir="rtl" lang="fa">برای دریافت تخفیف از ربات اقدام کنید</div>
                <div className="bf-cd-end">{formatEnd(endsAt)}</div>
            </div>
            <div className="bf-clock" role="timer" aria-label={`${days} days ${hours} hours left`}>
                <div className="bf-unit" aria-hidden="true">
                    <FlipCard value={pad(days)} intro={intro} />
                    <div className="bf-cap">days</div>
                </div>
                <div className="bf-sep" aria-hidden="true">:</div>
                <div className="bf-unit" aria-hidden="true">
                    <FlipCard value={pad(hours)} intro={intro} />
                    <div className="bf-cap">hours</div>
                </div>
            </div>
        </section>
    )
}
