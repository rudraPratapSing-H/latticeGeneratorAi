import { Link, useLocation } from 'react-router-dom'
import { Plus, Sun, Moon, Menu } from 'lucide-react'
import { useTheme } from '@/hooks/useTheme'
import { ENABLE_IMPLANT } from '@/config/env'
import { BackendStatusPill } from '@/components/layout/BackendStatusPill'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/cn'

export function Header() {
  const { theme, toggle } = useTheme()
  const location = useLocation()

  const isImplantActive = location.pathname.startsWith('/implant')
  const isSingleActive = !isImplantActive

  return (
    <header className="border-line bg-bg/80 sticky top-0 z-40 border-b backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
        {/* Logo & Navigation */}
        <div className="flex items-center gap-6">
          <Link
            to="/"
            className="text-text hover:text-accent flex items-center gap-2.5 transition-colors"
          >
            <svg width="24" height="24" viewBox="0 0 32 32" aria-hidden="true">
              <path
                d="M16 2 L28 9 L28 23 L16 30 L4 23 L4 9 Z"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              />
              <path
                d="M16 2 L16 30 M4 9 L28 23 L28 9 L4 23"
                stroke="currentColor"
                strokeWidth="1.5"
                opacity="0.5"
              />
              <circle cx="16" cy="16" r="2.5" fill="currentColor" />
            </svg>
            <span className="text-sm font-semibold tracking-tight">Lattice Designer</span>
          </Link>

          {/* Desktop Nav Links */}
          <nav className="hidden md:flex items-center gap-1 text-xs">
            <Link
              to="/"
              className={cn(
                'rounded-md px-2.5 py-1.5 font-medium transition-colors',
                isSingleActive
                  ? 'bg-surface-2 text-text font-semibold'
                  : 'text-muted hover:text-text hover:bg-surface',
              )}
            >
              Single design
            </Link>
            {ENABLE_IMPLANT && (
              <Link
                to="/implant"
                className={cn(
                  'rounded-md px-2.5 py-1.5 font-medium transition-colors flex items-center gap-1.5',
                  isImplantActive
                    ? 'bg-surface-2 text-text font-semibold'
                    : 'text-muted hover:text-text hover:bg-surface',
                )}
              >
                <span>Implant</span>
                <span className="rounded bg-accent/15 px-1 py-0.2 text-[10px] font-mono text-accent">
                  beta
                </span>
              </Link>
            )}
          </nav>
        </div>

        {/* Desktop actions */}
        <div className="hidden items-center gap-3 sm:flex">
          <BackendStatusPill />
          <Link to="/">
            <Button variant="secondary" size="sm">
              <Plus className="h-3.5 w-3.5" />
              New design
            </Button>
          </Link>
          <button
            onClick={toggle}
            className="text-muted hover:text-text hover:bg-surface-2 cursor-pointer rounded-md p-2 transition-colors"
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          >
            {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
        </div>

        {/* Mobile nav */}
        <div className="flex items-center gap-2 sm:hidden">
          <BackendStatusPill />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                className="text-muted hover:text-text cursor-pointer rounded-md p-2"
                aria-label="Menu"
              >
                <Menu className="h-5 w-5" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem asChild>
                <Link to="/" className="flex items-center gap-2">
                  Single design
                </Link>
              </DropdownMenuItem>
              {ENABLE_IMPLANT && (
                <DropdownMenuItem asChild>
                  <Link to="/implant" className="flex items-center justify-between gap-2">
                    <span>Implant workflow</span>
                    <span className="rounded bg-accent/15 px-1 text-[10px] text-accent">
                      beta
                    </span>
                  </Link>
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link to="/" className="flex items-center gap-2">
                  <Plus className="h-4 w-4" />
                  New design
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem onClick={toggle}>
                {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
                {theme === 'dark' ? 'Light theme' : 'Dark theme'}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  )
}
