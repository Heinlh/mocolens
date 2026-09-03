import type { LucideIcon } from 'lucide-react'
import { BookOpen, Info, LayoutGrid, Plus, Bookmark } from 'lucide-react'

export interface NavItem {
  label: string
  path: string
  icon: LucideIcon
}

export const NEW_QUESTION_PATH = '/ask'

export const SIDEBAR_NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard', path: '/dashboard', icon: LayoutGrid },
  { label: 'Saved insights', path: '/saved-insights', icon: Bookmark },
  { label: 'Sources', path: '/sources', icon: BookOpen },
  { label: 'About', path: '/about', icon: Info },
]

export const NEW_QUESTION_ICON = Plus
