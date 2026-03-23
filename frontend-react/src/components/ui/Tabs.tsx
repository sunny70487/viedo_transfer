import { createContext, useContext, useState, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

const TabsContext = createContext<{ value: string; onChange: (v: string) => void }>({ value: '', onChange: () => {} })

export function Tabs({ defaultValue, children, className }: { defaultValue: string; children: ReactNode; className?: string }) {
  const [value, setValue] = useState(defaultValue)
  return (
    <TabsContext.Provider value={{ value, onChange: setValue }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  )
}

export function TabsList({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('flex border-b border-border dark:border-border-dark', className)}>
      {children}
    </div>
  )
}

export function TabsTrigger({ value, children, className }: { value: string; children: ReactNode; className?: string }) {
  const ctx = useContext(TabsContext)
  const active = ctx.value === value
  return (
    <button
      type="button"
      className={cn(
        'px-4 py-2.5 text-sm font-medium transition-colors cursor-pointer -mb-px',
        active
          ? 'border-b-2 border-primary text-primary'
          : 'text-muted dark:text-muted-dark hover:text-text dark:hover:text-text-dark',
        className
      )}
      onClick={() => ctx.onChange(value)}
    >
      {children}
    </button>
  )
}

export function TabsContent({ value, children, className }: { value: string; children: ReactNode; className?: string }) {
  const ctx = useContext(TabsContext)
  if (ctx.value !== value) return null
  return <div className={cn('py-4', className)}>{children}</div>
}
