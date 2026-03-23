import { forwardRef, type InputHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        'h-10 w-full rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3 text-sm text-text dark:text-text-dark placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-primary/50',
        className
      )}
      {...props}
    />
  )
)
Input.displayName = 'Input'
