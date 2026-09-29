---
description: Rules for frontend TypeScript/React files
paths: cms/**/*.{ts,tsx}
---

# Frontend Rules

- Use semantic Tailwind tokens — NEVER primitive colors (text-gray-500, bg-blue-600)
- Use `authFetch` for API calls, SWR hooks for data fetching
- React 19: No setState in useEffect, no component defs inside components
- Dialog for detail views (not Sheet). Widths: detail=28rem, forms=32rem
- Named container sizes collapse in Tailwind v4 — use explicit rem values
