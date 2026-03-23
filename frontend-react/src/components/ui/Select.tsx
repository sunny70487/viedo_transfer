import { forwardRef, type SelectHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  options: readonly { value: string; label: string; group?: string }[]
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, options, ...props }, ref) => {
    const groups = new Map<string, typeof options[number][]>()
    const ungrouped: typeof options[number][] = []
    options.forEach((opt) => {
      if (opt.group) {
        const arr = groups.get(opt.group) ?? []
        arr.push(opt)
        groups.set(opt.group, arr)
      } else {
        ungrouped.push(opt)
      }
    })

    return (
      <select
        ref={ref}
        className={cn(
          'h-10 w-full rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3 text-sm text-text dark:text-text-dark focus:outline-none focus:ring-2 focus:ring-primary/50 cursor-pointer',
          className
        )}
        {...props}
      >
        {ungrouped.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
        {Array.from(groups.entries()).map(([group, opts]) => (
          <optgroup key={group} label={group}>
            {opts.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </optgroup>
        ))}
      </select>
    )
  }
)
Select.displayName = 'Select'
