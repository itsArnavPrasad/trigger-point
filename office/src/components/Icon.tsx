/** A small stroke icon set in the spirit of SF Symbols. Decorative: labels always sit beside them. */

const P: Record<string, string> = {
  dashboard: 'M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z',
  office: 'M4 20V8l8-4 8 4v12M9 20v-5h6v5M8 11h.01M12 11h.01M16 11h.01',
  profile: 'M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h5',
  strategy: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM15.5 8.5l-2 5-5 2 2-5z',
  icp: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM12 11a1 1 0 1 0 0 2 1 1 0 0 0 0-2z',
  accounts: 'M3 21h18M5 21V7l7-4v18M12 9h7v12M8 10h.01M8 14h.01M15 13h.01M15 17h.01',
  signals: 'M3 12h3l3-7 4 14 3-7h5',
  people: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 6.5M18.5 14a6.5 6.5 0 0 1 3 6',
  evidence: 'M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6zM9 12l2 2 4-4',
  campaign: 'M21 3L10 14M21 3l-7 18-4-7-7-4z',
  outreach: 'M3 6h18v12H3zM3 7l9 6 9-6',
  meetings: 'M4 6h16v15H4zM4 10h16M8 3v4M16 3v4',
  pipeline: 'M5 20V12M10 20V6M15 20v-9M20 20V4',
  learning: 'M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z',
  finance: 'M12 3v18M16.5 7.5c-.8-1.2-2.5-2-4.5-2-2.5 0-4 1.3-4 3s1.5 2.6 4 3 4 1.4 4 3.2-1.7 3.1-4 3.1c-2.2 0-3.8-.9-4.6-2.3',
  integrations: 'M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0zM12 17v4',
  plus: 'M12 5v14M5 12h14',
  chat: 'M4 5h16v11H9l-5 4z',
  sidebar: 'M3 4h18v16H3zM9 4v16',
  check: 'M5 12.5l4.5 4.5L19 7',
  chevron: 'M9 6l6 6-6 6',
  alert: 'M12 3l10 18H2zM12 10v5M12 18h.01',
  sparkle: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z',
}

export default function Icon({ name, size = 18 }: { name: string; size?: number }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={P[name] ?? P.dashboard} />
    </svg>
  )
}
