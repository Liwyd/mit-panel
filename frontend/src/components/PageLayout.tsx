import { ReactNode } from 'react'

interface PageLayoutProps {
    /** Static section pinned to the top of the page (title, toolbar, filters). Never scrolls. */
    header?: ReactNode
    /** Scrollable content region (the list/table body). */
    children: ReactNode
    /** Static section pinned to the bottom of the page (pagination, action bar). Never scrolls. */
    footer?: ReactNode
    /** Extra classes for the root container. */
    className?: string
}

/**
 * Fixed-height page shell used by every authed page. The outer shell in App.tsx
 * already pins the sidebar and the mobile header; this component pins a page
 * title/toolbar (header) and a bottom bar (footer) while letting only the
 * middle region scroll. `min-h-0` on the scroll region is what makes flex
 * scroll-containment actually work (flex children default to min-height: auto).
 */
export function PageLayout({ header, children, footer, className }: PageLayoutProps) {
    return (
        <div className={`flex flex-col h-full min-h-0 ${className ?? ''}`}>
            {header ? <div className="shrink-0">{header}</div> : null}
            <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden">{children}</div>
            {footer ? (
                <div className="shrink-0 border-t border-border bg-background pb-[env(safe-area-inset-bottom)]">{footer}</div>
            ) : null}
        </div>
    )
}
