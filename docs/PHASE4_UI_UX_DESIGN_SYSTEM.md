# ShiftFlow Pro – Phase 4 UI/UX Design System Specification

**Document Version:** 2.0  
**Design Philosophy:** Modern Enterprise SaaS, Subtle Glassmorphism, Semantic High-Contrast Tokens, Distraction-Free Information Hierarchy.  
**Inspiration & Repositories Integrated:**
- [pbakaus/impeccable](https://github.com/pbakaus/impeccable): Typography scales, mathematical layout spacing, and clear dashboard hierarchy.
- [ibelick/ui-skills](https://github.com/ibelick/ui-skills): Micro-interactions, animated states, and refined cards.
- [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill): Responsive breakpoints (360px to 1600px) and WCAG 2.1 AA token selection.
- [shadcn/ui & radix-ui](https://github.com/shadcn-ui/ui): Keyboard accessibility, dialog focus management, and accessible form labels.

---

## 1. Design Token Architecture (`/static/css/shiftflow-design-system.css`)

### 1.1 Color Tokens
```css
/* Light Mode Palette */
--sf-bg: #f8fafc;                 /* Slate-50: Crisp, clean background */
--sf-surface: #ffffff;            /* Pure white primary cards */
--sf-surface-elevated: #ffffff;   /* Elevated panels */
--sf-text-primary: #0f172a;       /* Slate-900: Maximum readability */
--sf-text-secondary: #475569;     /* Slate-600: High-contrast subheadings */
--sf-border: #e2e8f0;             /* Slate-200: Subtle separation lines */
--sf-brand: #2563eb;              /* Blue-600: MSEDCL corporate primary */
--sf-brand-hover: #1d4ed8;        /* Blue-700: Button hover states */
--sf-brand-light: #eff6ff;        /* Blue-50: Pill badge highlights */
--sf-success: #10b981;            /* Emerald-500: Approved / Present */
--sf-warning: #f59e0b;            /* Amber-500: Pending / Half-Day */
--sf-danger: #ef4444;             /* Red-500: Rejected / Absent */
--sf-info: #0284c7;               /* Sky-600: Weekly Off / General Shift */

/* Dark Mode Palette */
--sf-bg: #090d16;                 /* Deep Navy/Black: Glare-free operations */
--sf-surface: #0f172a;            /* Slate-900: Elevated card surface */
--sf-surface-elevated: #1e293b;   /* Slate-800: Modals & dropdowns */
--sf-text-primary: #f8fafc;       /* Slate-50: High-contrast white */
--sf-text-secondary: #94a3b8;     /* Slate-400: Clear muted descriptions */
--sf-border: #1e293b;             /* Slate-800: Subtle border */
--sf-brand: #3b82f6;              /* Blue-500: Accessible dark brand */
```

### 1.2 Glassmorphism & Elevation
- Class `.sf-glass-panel`: Background blur of 12px with 85% opacity, creating depth without visual distraction.
- Class `.sf-card-hover`: Smooth translateY(-2px) elevation with soft shadow expansion on hover.

---

## 2. Micro-interactions & Accessible Focus States

- **Keyboard Focus Indicators:** Every interactive button, input, select, and link features `outline: 2px solid var(--sf-brand)` with a 2px offset on keyboard tab navigation (`:focus-visible`).
- **Motion Reduction:** Media query `@media (prefers-reduced-motion: reduce)` sets animation duration to 0.01ms for users with vestibular sensitivities.
- **Button Feedback:** Active scale transform (`scale(0.98)`) provides tactile feedback on touch and mouse press.
- **Loading Skeleton Shimmer:** Dynamic CSS gradient animation (`.sf-skeleton`) for asynchronous table data loading.

---

## 3. Responsive Breakpoints Validation
- **Mobile (360px - 480px):** Sidebar collapses into mobile overlay drawer (`#mobile-menu`); sticky mobile header provides one-tap branding and persona indicators.
- **Tablet (768px - 1024px):** Roster tables and matrices scroll horizontally with custom low-friction scrollbars (`.custom-scrollbar`); KPI cards wrap into 2-column grids.
- **Desktop (1280px - 1600px+):** Full 4-column KPI cards, persistent collapsible sidebar (`w-72` to `w-20`), sticky data table headers, and distraction-free information layout.

