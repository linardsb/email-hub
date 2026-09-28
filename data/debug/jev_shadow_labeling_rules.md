# Content-based labelling rules (design-agnostic)

The label is the answer any design with this content should get. The hand build is evidence of what a
section is and what it is for, not the authority on the template name.

## o1_type
- header: brand logo at the very top, alone or with nav links.
- preheader: tiny top line (view online / my account / preview text).
- hero: the first large banner image near the top, AND the first text band directly under it (headline and/or CTA).
- content: body sections (text, images, cards, columns) that are not hero/header/footer/pure buttons.
- cta: section holding only standalone button(s).
- footer: section containing legal, address or unsubscribe text (even if it also has social icons or a logo).
- social: social icon row with no legal text.
- divider: rule line, or a thin decorative full-width band image with no content of its own.
- spacer: empty space (including an empty gutter column).
- nav: category/navigation link(s) outside the header, including a single nav item cut from a nav row.

## o1_template (by content)
- full-width image, no text -> full-width-image
- image with a text caption underneath -> image-block
- a small image alone (e.g. one column piece) -> image
- heading only -> heading; body only -> paragraph; heading + body -> text-block
- heading and/or body + one CTA (button or text link), no image -> hero-block
- heading + body + two CTAs, no image -> hero-2cta
- wide image above heading/body/button -> editorial-5
- image beside heading/body/button: image left -> article-card, image right -> article-reverse
- small icon with text beside or under it -> icon
- two products side by side (image, title, desc, CTA each) -> product-grid
- N side-by-side columns of other content (incl. rows of 3/4 buttons) -> column-layout-N (2/3/4)
- row of text nav links -> navigation-bar
- one filled standalone button -> button-filled; outlined -> button-ghost
- event details (name, date, time, location) -> event-card
- a card holding several stacked unrelated blocks -> td
- logo only at top -> logo-header
- any section with legal/unsubscribe text -> footer
- A column fragment (a single column cut out of a row) is labelled by its own content.

## o2_button_icon
- small arrow/chevron/play mark inside a button -> button_icon; otherwise content_image.

## o3_slot
- The node id (from the section's candidate texts/images/buttons; button slots use the button FRAME id)
  that should fill the slot, or none_of_the_above when no candidate holds that kind of content
  (e.g. a `date` slot when no node is a date). A generic text slot takes the best text candidate.

## Precedence (ratified 2026-09-29)
- Icon that carries meaning (app/order/rewards glyph) + label -> icon. Decorative arrow/chevron beside a text link -> the link's own template (navigation-bar for nav items).
- Heading vs paragraph: decided by size/weight, not by position above another block.

## Revisions after 4 independent raters (ratified 2026-09-29; supersede earlier lines where they conflict)
- Store/category/place links are type nav even when styled as buttons (template by shape: column-layout-N for button rows).
- Footer with 2+ parts (social, legal, address, link row) -> email-footer; `footer` only for a single legal/address block.
- Decorative band images between sections -> type content, template full-width-image.
- Icon-with-text tiles in a row (icon above/beside short text, 2-4 across) -> col-icon.
- A single standalone button -> cta-button, whatever its style.
- A single nav link cut from a nav row -> text-link (supersedes the navigation-bar precedence line).
- A short standalone label introducing the block below -> heading (supersedes size/weight line).
- Generic slot with a loose but only-plausible candidate (e.g. event `description` <- the time line) takes that candidate.
