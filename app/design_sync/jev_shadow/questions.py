"""Jev question builders for the three shadow decision points.

O1 section type + template (Choice), O2 button icon vs content image (one Noul
per candidate node), O3 which node fills each slot (Choice over short ids).
All questions for a section go in one fan-out request, so they cannot see each
other: slot uniqueness is enforced here in code (:func:`resolve_slots`).
"""

from __future__ import annotations

from app.design_sync.figma.layout_analyzer import EmailSectionType

NONE_OPTION = "none_of_the_above"

SECTION_TYPE_OPTIONS: dict[EmailSectionType, str] = {
    EmailSectionType.HEADER: "Top-of-email header: brand logo, sometimes with a few navigation links.",
    EmailSectionType.PREHEADER: "Tiny line above the header: preview text or a 'view in browser' link.",
    EmailSectionType.HERO: "Main banner near the top: large image and/or headline, often with a call-to-action.",
    EmailSectionType.CONTENT: "Body content: text, images or cards that are not a hero, header, footer or pure button.",
    EmailSectionType.CTA: "A standalone call-to-action: one or two buttons with little or no other content.",
    EmailSectionType.FOOTER: "Bottom-of-email footer: legal text, address, unsubscribe or preference links.",
    EmailSectionType.SOCIAL: "A row of social-network icons or links, optionally with a short label.",
    EmailSectionType.DIVIDER: "A thin horizontal rule separating other sections; no content of its own.",
    EmailSectionType.SPACER: "Empty vertical space between sections; no content.",
    EmailSectionType.NAV: "A horizontal row of navigation or category links, not in the header.",
    EmailSectionType.UNKNOWN: "None of the above, or cannot tell.",
}

# One line per slug the matcher can return: the 60 ``_build_slot_fills`` keys
# plus the 3 ``_match_column_layout`` slugs. Written from each template's
# ``data-slot`` set in ``email-templates/components/<slug>.html``.
SLUG_DESCRIPTIONS: dict[str, str] = {
    "preheader": "Hidden preview text plus a 'view in browser' link.",
    "email-header": "Header with a logo and a row of navigation links.",
    "logo-header": "Header with only a centred logo.",
    "hero-block": "Hero with a headline, supporting text and one button, over a background image.",
    "full-width-image": "One image spanning the full email width, optionally linked; no text.",
    "text-block": "A heading and body text, no image.",
    "article-card": "Two columns: an image beside a heading, body text and a button.",
    "image-block": "One image with a caption underneath.",
    "image-grid": "Two images side by side, each optionally linked.",
    "product-grid": "Two products side by side, each with image, title, description and button.",
    "category-nav": "Three category links in a row.",
    "image-gallery": "Three images in a row.",
    "td": "A card that holds several stacked child blocks of any kind.",
    "cta-button": "One standalone button.",
    "email-footer": "Footer with an editorial block and a legal block.",
    "spacer": "Empty vertical space.",
    "social-icons": "A short label plus a row of social-network icon links.",
    "divider": "A horizontal rule.",
    "navigation-bar": "A row of text navigation links.",
    "hero-text": "Hero image, then heading, subtext, body text and a button, with an optional bottom image.",
    "editorial-2": "Image beside heading, body text and button, on a coloured inner card.",
    "nav-hamburger": "Logo with a collapsible navigation menu.",
    "banner": "One short line of emphasised text on a solid band.",
    "col-gutter": "Two free-form columns separated by a gutter.",
    "article-reverse": "Text (heading, body, button) on the left, image on the right.",
    "editorial-1": "Image beside heading, body text and button, on a coloured band.",
    "editorial-3": "Image beside heading, body text and button, on a strong accent-coloured band.",
    "editorial-4": "Accent band holding a white text card beside an image.",
    "editorial-5": "Wide image above a heading, body text and button.",
    "article-2": "Image beside a heading, subheading, body text and button.",
    "article-3": "Inset image beside heading, body text and button, with outer padding.",
    "article-4": "Inset image beside heading, body text and button, on a white card with padding.",
    "hero-2cta": "Hero image, heading, subtext, body text and two buttons (primary and secondary).",
    "button": "One button.",
    "button-filled": "One button with a solid fill.",
    "button-ghost": "One outlined button with no fill.",
    "button-responsive": "One button that goes full-width on mobile.",
    "cta": "A call-to-action button block.",
    "cta-pair": "Two buttons side by side (primary and secondary).",
    "heading": "A heading line only.",
    "paragraph": "A paragraph of body text only.",
    "icon": "A small icon with a line of text next to it.",
    "list": "A short list of three items.",
    "product-card": "One product: image, title, description, price and button.",
    "product-showcase": "One large product image with a row of up to five detail images.",
    "event-card": "An event: name, date, location, description and a button.",
    "event-card-minimal": "An event: name, date and a button.",
    "event-card-banner": "An event with a banner image, name, date, location and a button.",
    "footer": "Footer with company name, address, unsubscribe and preferences links.",
    "footer-menu": "A row of footer menu links.",
    "footer-social": "A heading plus social-network icon links, inside the footer.",
    "footer-unsub": "A single unsubscribe line.",
    "col-icon": "Two columns, each an icon with a heading.",
    "header": "Header with a logo.",
    "app-store": "App Store and Google Play download badges.",
    "section": "One wide image in an extra-wide wrapper.",
    "image": "A bare image.",
    "image-responsive": "A bare image that scales on mobile.",
    "text-link": "One inline text link.",
    "font-inline": "One short inline line of styled text.",
    "column-layout-2": "Two side-by-side columns, each holding its own content.",
    "column-layout-3": "Three side-by-side columns, each holding its own content.",
    "column-layout-4": "Four side-by-side columns, each holding its own content.",
}

_O2_CONDITION = (
    "Node `{short}` is a small decorative icon (arrow, chevron, play mark) that belongs "
    "to the button it sits inside, not a content image."
)


def o1_questions() -> dict[str, dict[str, object]]:
    """Section type and template, over the full option lists."""
    type_criteria: dict[str, object] = {t.value: d for t, d in SECTION_TYPE_OPTIONS.items()}
    template_criteria: dict[str, object] = dict(SLUG_DESCRIPTIONS)
    template_criteria[NONE_OPTION] = "No listed template fits this section."
    return {
        "o1_type": {
            "type": "choice",
            "instructions": "Which kind of email section is described by the state?",
            "criteria": type_criteria,
        },
        "o1_template": {
            "type": "choice",
            "instructions": "Which email component template best reproduces this section's content and layout?",
            "criteria": template_criteria,
        },
    }


def o2_questions(candidate_short_ids: list[str]) -> dict[str, dict[str, object]]:
    """One Noul per image/vector/instance node that sits inside a button."""
    return {
        f"o2_{short}": {
            "type": "noul",
            "instructions": _O2_CONDITION.format(short=short),
            "criteria": {
                "true": "It belongs to the button (a decorative icon).",
                "false": "It is a content image in its own right.",
            },
        }
        for short in candidate_short_ids
    }


def o3_questions(
    slots: list[tuple[str, str]],
    candidate_short_ids: list[str],
    template_slug: str,
) -> dict[str, dict[str, object]]:
    """One Choice per ``(slot_id, slot_type)`` over candidate node ids."""
    if not candidate_short_ids:
        return {}
    criteria: dict[str, object] = {}
    criteria.update(dict.fromkeys(candidate_short_ids))  # ids take null descriptions
    criteria[NONE_OPTION] = "No listed node should fill this slot."
    template_desc = SLUG_DESCRIPTIONS.get(template_slug, template_slug)
    return {
        f"o3_{slot_id}": {
            "type": "choice",
            "instructions": (
                f"The section is rendered with the `{template_slug}` template ({template_desc}). "
                f"Which node (by id in `nodes`) should fill its `{slot_id}` slot, a {slot_type} slot?"
            ),
            "criteria": dict(criteria),
        }
        for slot_id, slot_type in slots
    }


def resolve_slots(answers: dict[str, dict[str, float]]) -> dict[str, str | None]:
    """Greedy one-node-per-slot assignment from per-slot probabilities.

    ``answers`` maps slot id -> {option: probability}. Pairs are taken in
    descending probability; each node fills at most one slot. A slot whose best
    remaining option is ``none_of_the_above`` (or has none left) maps to None.
    """
    pairs = sorted(
        ((p, slot, opt) for slot, probs in answers.items() for opt, p in probs.items()),
        key=lambda t: (-t[0], t[1], t[2]),
    )
    resolved: dict[str, str | None] = {}
    used: set[str] = set()
    for _p, slot, opt in pairs:
        if slot in resolved:
            continue
        if opt == NONE_OPTION:
            resolved[slot] = None
        elif opt not in used:
            resolved[slot] = opt
            used.add(opt)
    for slot in answers:
        resolved.setdefault(slot, None)
    return resolved
