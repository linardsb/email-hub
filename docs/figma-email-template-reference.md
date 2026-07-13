# Figma Email Template Reference

## Example Design System

**"The Ultimate Email Design System" (Community)**
https://www.figma.com/design/VUlWjZGAEVZr3mK1EawsYR/The-Ultimate-Email-Design-System--Community-?node-id=0-1&p=f&t=LZrRjzxlmBlbfse4-0

This is the reference example for how a well-structured Figma email design system should be organized for optimal import into the Email Hub via the Design Sync pipeline.

---

## Expected Figma File Structure

### Page Organization

A production-ready email design system in Figma should have these pages:

| Page | Purpose |
|------|---------|
| **Cover / Introduction** | File overview, usage instructions, version log |
| **Design Tokens** | Color palettes, typography scales, spacing system |
| **Components** | Reusable email building blocks (atoms + molecules) |
| **Templates** | Complete email layouts assembled from components |
| **Email Previews** | Full rendered email mockups (desktop + mobile) |

### Design Tokens Page

The tokens page defines the brand's visual language. Our Design Sync pipeline (`app/design_sync/`) extracts these automatically via the Figma API.

**Colors** (extracted as `ExtractedColor`):
- Primary brand color (CTA buttons, links, headers)
- Secondary brand color (accents, borders)
- Background colors (body, section alternates, footer)
- Text colors (heading, body, muted/secondary, link)
- Dark mode variants for each color
- Organized as Figma color styles or variables with semantic names:
  ```
  brand/primary        → #0066cc
  brand/secondary      → #4895ef
  text/heading         → #333333
  text/body            → #555555
  text/muted           → #666666
  background/body      → #ffffff
  background/section   → #f5f5f5
  background/footer    → #f5f5f5
  dark/background      → #1a1a2e
  dark/text            → #e0e0e0
  ```

**Typography** (extracted as `ExtractedTypography`):
- Heading styles (H1-H3) with font family, size, weight, line-height
- Body text styles (regular, small, caption)
- Link/CTA text styles
- Organized as Figma text styles:
  ```
  heading/h1           → Arial, 28px, bold, 1.3
  heading/h2           → Arial, 24px, bold, 1.3
  heading/h3           → Arial, 20px, bold, 1.3
  body/regular         → Arial, 16px, normal, 1.6
  body/small           → Arial, 14px, normal, 1.5
  body/caption         → Arial, 12px, normal, 1.5
  cta/button           → Arial, 16px, bold
  ```

**Spacing** (extracted as `ExtractedSpacing`):
- Section padding (vertical, horizontal)
- Element spacing (between heading and body, between sections)
- Column gaps
- Named as Figma variables:
  ```
  spacing/section-v    → 32px
  spacing/section-h    → 24px
  spacing/element      → 16px
  spacing/column-gap   → 16px
  ```

### Components Page

Components should be organized as Figma components or component sets. Each component maps to a component in our `app/components/data/seeds.py`.

**Required components (match our component library):**

| Figma Component | Hub Equivalent | Notes |
|-----------------|---------------|-------|
| Email Header | `email-header` | Logo + optional nav links |
| Logo Header | `logo-header` | Centered logo only |
| Hero Image | `hero-block` | Full-width image + headline + CTA |
| Text Block | `text-block` | Heading + paragraph |
| CTA Button | `cta-button` | Centered button, filled + ghost variants |
| Image Block | `image-block` | Responsive image with optional caption |
| Full-Width Image | `full-width-image` | Edge-to-edge image |
| 2-Column Layout | `column-layout-2` | Two equal columns |
| 3-Column Layout | `column-layout-3` | Three equal columns |
| 4-Column Layout | `column-layout-4` | Four equal columns |
| Reverse Column | `reverse-column` | Image right, text left (RTL trick) |
| Article Card | `article-card` | Image + heading + body + CTA in 2-col |
| Product Card | `product-card` | Product image + title + price + CTA |
| Divider | `divider` | Horizontal line separator |
| Spacer | `spacer` | Vertical whitespace |
| Social Icons | `social-icons` | Row of social media icon links |
| Email Footer | `email-footer` | Unsubscribe, address, legal text |
| Preheader | `preheader` | Hidden inbox preview text |
| Navigation Bar | `navbar` | Horizontal link navigation |

**Component naming convention:**
- Use `/` hierarchy: `Email / Header`, `Layout / 2-Column`, `Content / Article Card`
- Or flat names matching our slugs: `email-header`, `column-layout-2`
- Include variants as Figma component properties (e.g., CTA button: filled/ghost)

**Component frame sizing:**
- Desktop width: **600px** (email standard max-width)
- Mobile width: **375px** (for responsive preview)
- Each component should have both desktop and mobile variants or use auto-layout for responsive behavior

### Templates Page

Complete email templates assembled from components. Each template corresponds to a `GoldenTemplate` in our system.

**Expected template types:**
- Promotional / Marketing email
- Newsletter / Content digest
- Transactional (order confirmation, shipping, etc.)
- Welcome / Onboarding
- Event invitation

**Template structure in Figma:**
```
Frame: "Promotional Email" (600px wide)
  ├── Email Header (component instance)
  ├── Hero Image (component instance)
  ├── Text Block (component instance)
  ├── 2-Column Layout (component instance)
  │   ├── Product Card (component instance)
  │   └── Product Card (component instance)
  ├── CTA Button (component instance)
  ├── Divider (component instance)
  ├── Social Icons (component instance)
  └── Email Footer (component instance)
```

### Email Previews Page

Side-by-side desktop and mobile mockups showing the final rendered email.

**Expected previews:**
- Desktop (600px within browser/client chrome)
- Mobile (375px within phone frame)
- Dark mode variants for both
- Outlook/Word engine variant (showing MSO rendering differences)

---

## Import Pipeline Compatibility

### What the Design Sync pipeline extracts

When a user connects this Figma file via Design Sync (`/api/v1/design-sync`):

1. **File structure** — Pages, frames, component instances → `DesignFileStructure`
2. **Design tokens** — Color styles, text styles, variables → `ExtractedTokens`
3. **Thumbnails** — Node-level PNG exports → cached for browsing
4. **Component mapping** — Figma component names → Hub component slugs (manual or AI-assisted)

### Figma file requirements for clean import

- Use **Figma color styles** or **variables** (not raw hex on elements) — these are what we extract
- Use **Figma text styles** (not inline font overrides) — these map to typography tokens
- Use **components** (not groups) for reusable email sections — we detect component instances
- Keep templates at **600px width** — this is the email standard and matches our shell
- Name frames descriptively — frame names become section names in the Hub
- Use **auto-layout** where possible — helps us infer spacing tokens
- Avoid raster effects (blur, shadows) — these don't translate to email HTML

### Design system → Hub mapping

```
Figma Design System          →  Email Hub
─────────────────────────────────────────────────
Color styles/variables       →  Project DesignSystem.BrandPalette
Text styles                  →  Project DesignSystem.Typography
Component instances          →  ComponentVersion (matched by slug)
Template frames (600px)      →  GoldenTemplate (via section composition)
Spacing variables            →  DesignSystem.spacing token map
```

---

## Best Practices for Template Authors

1. **One component per frame** — Don't nest email sections inside each other in Figma. Each section should be a flat component instance in the template frame.

2. **Use 600px width** — All email templates must be 600px wide. This matches the outer MSO wrapper and the `max-width` in our email shell.

3. **Define dark mode colors** — Include a dark mode color palette in the tokens page. Name them with a `dark/` prefix so our pipeline maps them correctly.

4. **Include mobile variants** — Show how columns stack on mobile (e.g., 2-column → single column). Our components handle this with `display: inline-block` and media queries, but the Figma preview helps stakeholders understand the behavior.

5. **Mark content slots** — Use Figma text layers with placeholder names that match our `data-slot` IDs: `{{headline}}`, `{{body_text}}`, `{{cta_text}}`, `{{image_url}}`. This helps the import pipeline identify editable content regions.

6. **Keep it flat** — Figma's nested frame hierarchy doesn't map 1:1 to email table structure. Keep the template frame's direct children as the email sections. Deep nesting makes import harder.
