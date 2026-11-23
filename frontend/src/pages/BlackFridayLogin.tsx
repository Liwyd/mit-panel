import { useEffect, useRef } from 'react'
import type { FieldErrors, UseFormRegister } from 'react-hook-form'
import type { LoginFormData } from '@/types'
import { LoginLogo } from '@/components/LoginLogo'
import { BlackFridayDust } from '@/components/BlackFridayDust'

/*
 * The login page while the Black Friday theme is on: a shop window at night.
 * One paper price tag hangs on a thread and carries the brand logo (its white
 * ground needs paper under it, so the logo itself stays untouched). The form
 * stays quiet beside it, in the panel's own coral.
 */

const styles = `
.bf-login{
  --bf-deep:#0b0a0a;--bf-bg:#100f0f;--bf-card:#171515;--bf-raised:#211e1e;
  --bf-line:rgba(237,233,230,.08);--bf-text:#ede9e6;--bf-text-2:#a8a19d;--bf-muted:#86807c;
  --bf-coral:hsl(0 70% 67%);--bf-coral-hover:hsl(0 70% 71%);--bf-ink-red:#d9241c;
  --bf-paper:#f6f2ea;--bf-ease-out:cubic-bezier(.23,1,.32,1);--bf-ease-in-out:cubic-bezier(.77,0,.175,1);
  position:fixed;inset:0;overflow-y:auto;
  display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);
  background:var(--bf-bg);color:var(--bf-text);-webkit-font-smoothing:antialiased;
}
.bf-login h1{letter-spacing:-.01em;line-height:1.15}
.bf-stage{position:relative;overflow:hidden;background:var(--bf-deep);border-inline-end:1px solid var(--bf-line);min-height:100%}
.bf-stage::before{content:"";position:absolute;inset:0;pointer-events:none;
  background:radial-gradient(60% 55% at 50% 0%, rgba(255,250,244,.07), transparent 70%)}
.bf-hanger{position:absolute;top:0;left:50%;width:300px;margin-left:-150px;transform-origin:50% 0;
  animation:bf-settle 1700ms var(--bf-ease-in-out) both}
.bf-thread{display:block;width:2px;height:calc(50vh - 250px);min-height:120px;margin:0 auto;background:linear-gradient(#5a5450,#8c847d)}
.bf-tag{position:relative;width:300px;margin-top:-6px;padding:56px 28px 0;
  background:var(--bf-paper);color:#1d1a17;border-radius:14px;
  clip-path:polygon(64px 0,calc(100% - 64px) 0,100% 64px,100% 100%,0 100%,0 64px);
  box-shadow:0 30px 60px rgba(0,0,0,.45)}
.bf-hole{position:absolute;top:18px;left:50%;width:18px;height:18px;margin-left:-9px;border-radius:50%;
  background:var(--bf-deep);box-shadow:0 0 0 4px #d8d0c2,inset 0 2px 3px rgba(0,0,0,.6)}
.bf-logo{display:flex;justify-content:center}
.bf-logo img,.bf-logo video{width:168px;height:168px;display:block;object-fit:contain;background:#fff;mix-blend-mode:multiply;pointer-events:none;user-select:none}
.bf-perf{position:relative;height:0;margin:20px -28px 0;border-top:2px dashed rgba(29,26,23,.22)}
.bf-perf::before,.bf-perf::after{content:"";position:absolute;top:-10px;width:18px;height:18px;border-radius:50%;background:var(--bf-deep)}
.bf-perf::before{left:-9px}.bf-perf::after{right:-9px}
.bf-stub{padding:20px 0 24px;display:flex;align-items:flex-end;justify-content:space-between;gap:12px}
.bf-event{font-size:30px;line-height:1.05;letter-spacing:-.02em;color:var(--bf-ink-red)}
.bf-event span{display:block}
.bf-dates{font-size:13px;line-height:20px;color:#6f675e;text-align:end;font-variant-numeric:tabular-nums}

.bf-panel{display:flex;align-items:center;justify-content:center;padding:48px 32px}
.bf-form-wrap{width:100%;max-width:360px}
.bf-kicker{display:flex;align-items:center;gap:8px;font-size:13px;line-height:20px;color:var(--bf-text-2);margin-bottom:16px}
.bf-kicker i{width:6px;height:6px;border-radius:50%;background:var(--bf-coral)}
.bf-title{font-size:32px;font-weight:500;margin-bottom:8px;color:var(--bf-text)}
.bf-sub{font-size:14px;line-height:22px;color:var(--bf-text-2);margin-bottom:32px}
.bf-err{border:1px solid hsl(0 65% 58% / .35);color:hsl(0 80% 74%);background:hsl(0 65% 58% / .1);border-radius:10px;padding:12px 16px;font-size:13px;line-height:20px;margin-bottom:16px}
.bf-form{display:flex;flex-direction:column;gap:16px}
.bf-field label{display:block;font-size:13px;line-height:20px;color:var(--bf-text-2);margin-bottom:8px}
.bf-field input{width:100%;height:48px;padding:0 16px;background:var(--bf-card);color:var(--bf-text);
  border:1px solid var(--bf-line);border-radius:10px;font:inherit;font-size:15px;
  transition:border-color 160ms ease,background-color 160ms ease}
.bf-field input:focus{outline:none;border-color:var(--bf-coral);background:var(--bf-raised)}
.bf-field input:disabled{opacity:.6}
.bf-fielderr{color:hsl(0 80% 74%);font-size:12px;line-height:16px;margin-top:8px}
.bf-btn{margin-top:8px;height:48px;border:0;border-radius:10px;cursor:pointer;
  background:var(--bf-coral);color:#1a0d0d;font:inherit;font-size:15px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.22);
  transition:transform 140ms var(--bf-ease-out),background-color 160ms ease,opacity 160ms ease}
.bf-btn:active{transform:scale(.97)}
.bf-btn:disabled{opacity:.6;cursor:default;transform:none}
.bf-btn:focus-visible{outline:2px solid var(--bf-coral);outline-offset:3px}
@media (hover:hover) and (pointer:fine){.bf-btn:not(:disabled):hover{background:var(--bf-coral-hover)}}
.bf-foot{margin-top:32px;padding-top:16px;border-top:1px solid var(--bf-line);font-size:12px;line-height:16px;color:var(--bf-muted)}

.bf-in{animation:bf-rise 420ms var(--bf-ease-out) both}
.bf-in:nth-child(2){animation-delay:60ms}.bf-in:nth-child(3){animation-delay:110ms}
.bf-in:nth-child(4){animation-delay:150ms}.bf-in:nth-child(5){animation-delay:180ms}.bf-in:nth-child(6){animation-delay:200ms}
@keyframes bf-rise{from{opacity:0;transform:translateY(8px)}}
@keyframes bf-settle{0%{transform:rotate(-7deg);opacity:0}12%{opacity:1}38%{transform:rotate(3.2deg)}
  62%{transform:rotate(-1.3deg)}82%{transform:rotate(.45deg)}100%{transform:rotate(0)}}
@keyframes bf-settle-sm{0%{transform:scale(.78) rotate(-7deg);opacity:0}12%{opacity:1}
  38%{transform:scale(.78) rotate(3.2deg)}62%{transform:scale(.78) rotate(-1.3deg)}
  82%{transform:scale(.78) rotate(.45deg)}100%{transform:scale(.78) rotate(0)}}
@keyframes bf-fade{from{opacity:0}}

@media (max-width:860px){
  .bf-login{grid-template-columns:1fr;grid-template-rows:auto 1fr}
  .bf-stage{height:340px;min-height:0;border-inline-end:0;border-bottom:1px solid var(--bf-line)}
  .bf-hanger{transform:scale(.78);animation-name:bf-settle-sm}
  .bf-thread{height:56px;min-height:0}
  .bf-panel{padding:32px 16px 48px;align-items:flex-start}
  .bf-title{font-size:28px}
}
@media (prefers-reduced-motion:reduce){
  .bf-hanger,.bf-in{animation:bf-fade 300ms ease both}
}
@media (prefers-reduced-motion:reduce) and (max-width:860px){.bf-hanger{transform:scale(.78)}}
`

const tagDate = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: 'Asia/Tehran' })
const tagYear = new Intl.DateTimeFormat('en-GB', { year: 'numeric', timeZone: 'Asia/Tehran' })

interface Props {
    title: string
    endsAt: Date
    serverError: string | null
    register: UseFormRegister<LoginFormData>
    errors: FieldErrors<LoginFormData>
    isSubmitting: boolean
    onSubmit: (e?: React.BaseSyntheticEvent) => Promise<void>
}

/* The tag leans toward the pointer on a damped spring and sways back when the
   pointer leaves, so it reads as paper on a thread. Mouse only, and off for
   reduced motion. Driven by transform on the tag itself, from its live angle,
   so a new target never jumps. */
export function BlackFridayLogin({ title, endsAt, serverError, register, errors, isSubmitting, onSubmit }: Props) {
    const stageRef = useRef<HTMLElement>(null)
    const tagRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        const area = stageRef.current
        const el = tagRef.current
        if (!area || !el) return
        if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

        let angle = 0
        let velocity = 0
        let target = 0
        let frame = 0
        let last = 0
        const STIFFNESS = 90
        const DAMPING = 11 // ratio about 0.6: a loose sway, as a hung tag would

        const step = (t: number) => {
            const dt = last ? Math.min(0.032, (t - last) / 1000) : 0.016
            last = t
            velocity += (-STIFFNESS * (angle - target) - DAMPING * velocity) * dt
            angle += velocity * dt
            el.style.transform = `rotate(${angle.toFixed(3)}deg)`
            if (Math.abs(velocity) < 0.01 && Math.abs(angle - target) < 0.01) {
                frame = 0
                last = 0
                return
            }
            frame = requestAnimationFrame(step)
        }
        const kick = () => {
            if (!frame) frame = requestAnimationFrame(step)
        }
        const onMove = (e: PointerEvent) => {
            const r = area.getBoundingClientRect()
            target = ((e.clientX - r.left) / r.width - 0.5) * -6
            kick()
        }
        const onLeave = () => {
            target = 0
            kick()
        }

        // Pivot at the pin on the top edge of the stage, not the tag's centre.
        el.style.transformOrigin = `50% ${-(el.offsetTop)}px`
        area.addEventListener('pointermove', onMove)
        area.addEventListener('pointerleave', onLeave)
        return () => {
            cancelAnimationFrame(frame)
            area.removeEventListener('pointermove', onMove)
            area.removeEventListener('pointerleave', onLeave)
        }
    }, [])


    return (
        <div className="bf-login">
            <style>{styles}</style>
            <BlackFridayDust variant="login" />

            <section className="bf-stage" ref={stageRef} aria-hidden="true">
                <div className="bf-hanger">
                    <span className="bf-thread" />
                    <div className="bf-tag" ref={tagRef}>
                        <span className="bf-hole" />
                        <LoginLogo label={title} className="bf-logo" size={168} />
                        <div className="bf-perf" />
                        <div className="bf-stub">
                            <div className="bf-event"><span>Black</span><span>Friday</span></div>
                            <div className="bf-dates">Until {tagDate.format(endsAt)}<br />{tagYear.format(endsAt)}</div>
                        </div>
                    </div>
                </div>
            </section>

            <main className="bf-panel">
                <div className="bf-form-wrap">
                    <div className="bf-kicker bf-in"><i />Black Friday week</div>
                    <h1 className="bf-title bf-in">Sign in</h1>
                    <p className="bf-sub bf-in">Enter your credentials to access {title}</p>

                    {serverError && <div className="bf-err bf-in" dir="auto" role="alert">{serverError}</div>}

                    <form className="bf-form bf-in" onSubmit={onSubmit}>
                        <div className="bf-field">
                            <label htmlFor="bf-username">Username</label>
                            <input
                                id="bf-username"
                                type="text"
                                autoComplete="username"
                                autoCapitalize="off"
                                spellCheck={false}
                                disabled={isSubmitting}
                                {...register('username')}
                            />
                            {errors.username && <div className="bf-fielderr">{errors.username.message}</div>}
                        </div>
                        <div className="bf-field">
                            <label htmlFor="bf-password">Password</label>
                            <input
                                id="bf-password"
                                type="password"
                                autoComplete="current-password"
                                disabled={isSubmitting}
                                {...register('password')}
                            />
                            {errors.password && <div className="bf-fielderr">{errors.password.message}</div>}
                        </div>
                        <button className="bf-btn" type="submit" disabled={isSubmitting}>
                            {isSubmitting ? 'Signing in…' : 'Sign in'}
                        </button>
                    </form>

                    <div className="bf-foot bf-in">{title}</div>
                </div>
            </main>
        </div>
    )
}
