import { lazy, type ComponentType } from 'react'

const RELOAD_FLAG = 'mit:chunk-reload'

/**
 * React.lazy for a page module that exports its component by name.
 *
 * After a deploy, a tab opened on the previous release still asks for the old
 * chunk names, which no longer exist. The first failed load reloads the page
 * once to pick up the new release; a second failure in a row is a real error
 * and is thrown to the caller.
 */
export function lazyPage<M extends Record<string, unknown>, K extends keyof M>(
    load: () => Promise<M>,
    name: K,
) {
    return lazy(async () => {
        try {
            const mod = await load()
            sessionStorage.removeItem(RELOAD_FLAG)
            return { default: mod[name] as ComponentType }
        } catch (err) {
            if (!sessionStorage.getItem(RELOAD_FLAG)) {
                sessionStorage.setItem(RELOAD_FLAG, '1')
                window.location.reload()
                // Keep Suspense waiting while the page reloads.
                return new Promise<{ default: ComponentType }>(() => {})
            }
            throw err
        }
    })
}
