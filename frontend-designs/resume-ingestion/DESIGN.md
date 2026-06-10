---
name: TalentMatch RAG Design System
colors:
  surface: '#f7f9fb'
  surface-dim: '#d8dadc'
  surface-bright: '#f7f9fb'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f4f6'
  surface-container: '#eceef0'
  surface-container-high: '#e6e8ea'
  surface-container-highest: '#e0e3e5'
  on-surface: '#191c1e'
  on-surface-variant: '#45464d'
  inverse-surface: '#2d3133'
  inverse-on-surface: '#eff1f3'
  outline: '#76777d'
  outline-variant: '#c6c6cd'
  surface-tint: '#565e74'
  primary: '#000000'
  on-primary: '#ffffff'
  primary-container: '#131b2e'
  on-primary-container: '#7c839b'
  inverse-primary: '#bec6e0'
  secondary: '#0058be'
  on-secondary: '#ffffff'
  secondary-container: '#2170e4'
  on-secondary-container: '#fefcff'
  tertiary: '#000000'
  on-tertiary: '#ffffff'
  tertiary-container: '#00201c'
  on-tertiary-container: '#009485'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dae2fd'
  primary-fixed-dim: '#bec6e0'
  on-primary-fixed: '#131b2e'
  on-primary-fixed-variant: '#3f465c'
  secondary-fixed: '#d8e2ff'
  secondary-fixed-dim: '#adc6ff'
  on-secondary-fixed: '#001a42'
  on-secondary-fixed-variant: '#004395'
  tertiary-fixed: '#71f8e4'
  tertiary-fixed-dim: '#4fdbc8'
  on-tertiary-fixed: '#00201c'
  on-tertiary-fixed-variant: '#005048'
  background: '#f7f9fb'
  on-background: '#191c1e'
  surface-variant: '#e0e3e5'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  headline-md:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.01em
  code-mono:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 4px
  container-padding: 24px
  gutter: 16px
  sidebar-width: 260px
  card-gap: 20px
---

## Brand & Style

The design system focuses on precision, intelligence, and high-velocity decision-making for enterprise talent acquisition. It utilizes a **Corporate / Modern** aesthetic that balances the density of AI-driven data with the clarity of a premium SaaS interface. 

The emotional goal is to evoke a sense of "augmented intelligence"—where the user feels empowered by data rather than overwhelmed by it. This is achieved through a systematic application of whitespace, a structured hierarchy of information, and a sophisticated dark-to-light transition between navigation and workspace areas.

## Colors

The palette is anchored by a deep navy and slate foundation, providing a "command center" feel for the navigation. The primary workspace uses a bright, clean neutral scale to ensure maximum legibility for RAG-generated text and candidate profiles.

- **Primary & Secondary:** The Navy (#0F172A) is reserved for structural elements (sidebar, headers), while Electric Blue (#3B82F6) drives primary actions and highlights.
- **Accents:** Teal (#14B8A6) is used for data visualizations and secondary AI-driven insights.
- **Status Tiers:**
  - **High Match (80-100):** Emerald to Teal gradient or solid #10B981.
  - **Medium Match (50-79):** Amber #F59E0B.
  - **Low Match (<50):** Muted Red #EF4444.

## Typography

This design system utilizes **Inter** for its exceptional legibility in data-heavy environments. The typographic scale is optimized for information density without sacrificing clarity. 

- **Weight Usage:** Use Semibold (600) for section headers and Bold (700) sparingly for primary page titles. 
- **Tabular Data:** For numerical data in tables (scores, dates), use the tabular numerals OpenType feature of Inter to ensure vertical alignment.
- **Micro-copy:** Labels and captions use Medium (500) weight at 12px to maintain hierarchy against body text.

## Layout & Spacing

The layout follows a **Fixed-Fluid hybrid** model. The sidebar is fixed at 260px, while the main content area utilizes a fluid 12-column grid that expands to a maximum readable width of 1440px.

- **Grid:** 12 columns on desktop, 8 on tablet, 4 on mobile.
- **Rhythm:** An 8px base grid governs all component dimensions, with a 4px "half-step" used for tight internal component spacing (e.g., icon-to-text).
- **Margins:** Page-level containers use 24px padding on desktop, scaling down to 16px on mobile.

## Elevation & Depth

This design system uses **Tonal Layering** combined with subtle ambient shadows to define hierarchy.

- **Level 0 (Canvas):** #F8FAFC (Background).
- **Level 1 (Cards/Surfaces):** White (#FFFFFF) with a 1px border of #E2E8F0. A very soft shadow (Y: 2px, Blur: 4px, Color: rgba(15, 23, 42, 0.05)) is applied to separate cards from the background.
- **Level 2 (Dropdowns/Modals):** White with a more pronounced shadow (Y: 10px, Blur: 20px, Color: rgba(15, 23, 42, 0.1)) to indicate interactive overlays.
- **The Sidebar:** Uses a flat, dark treatment (#0F172A) to create a strong vertical anchor on the left, using color rather than shadow to denote elevation.

## Shapes

The shape language is "Soft Professional." 

- **Components:** Standard buttons, inputs, and cards use a **10px (0.625rem)** corner radius to feel modern and accessible.
- **Selection States:** Tabs and menu items use a slightly smaller radius (6px) to maintain a crisp look within tight layouts.
- **Tags/Status:** Match scores and category chips are fully rounded (pill-shaped) to distinguish them from actionable buttons.

## Components

- **Buttons:** 
  - *Primary:* Blue background, white text, 10px radius. 
  - *Secondary:* Ghost style with #E2E8F0 border and Navy text.
- **Input Fields:** 1px #E2E8F0 border, white background. Focus state uses a 2px Electric Blue ring with 20% opacity.
- **Cards:** The core of the interface. Must have 24px internal padding, 1px #E2E8F0 border, and 10px radius. Headers within cards should have a subtle bottom border.
- **Chips & Match Scores:** Used for RAG metadata. High-match scores (80+) should use a Teal (#14B8A6) background with white text or a high-contrast treatment.
- **Sidebar Navigation:** Items should have a 4px Electric Blue vertical indicator on the left for the active state, with a subtle #1E293B background highlight.
- **Icons:** Use **Lucide** (2px stroke weight). Icons should always be accompanied by labels in primary navigation to ensure clarity in enterprise workflows.
- **Data Tables:** Row hover states use #F1F5F9. Vertical borders are omitted; only horizontal dividers (#E2E8F0) are used to maintain a clean, airy feel.