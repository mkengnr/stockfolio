import { cn } from '@/lib/utils'
import { HTMLAttributes } from 'react'

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  color?: string   // hex color from tag
}

export function Badge({ className, color, children, style, ...props }: BadgeProps) {
  const customStyle = color
    ? { backgroundColor: `${color}20`, color, borderColor: `${color}50`, ...style }
    : style
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium',
        !color && 'border-gray-200 bg-gray-100 text-gray-700',
        className,
      )}
      style={customStyle}
      {...props}
    >
      {children}
    </span>
  )
}
