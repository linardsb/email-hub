"""Render context for the design→email HTML converter.

Bundles the 13 inherited parameters previously threaded through
``node_to_email_html`` so renderers can recurse via ``ctx.with_child(...)``
instead of re-passing every argument by keyword.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.design_sync.compatibility import ConverterCompatibility
    from app.design_sync.figma.layout_analyzer import EmailSection, TextBlock
    from app.design_sync.protocol import ExtractedGradient, _NodeProps


@dataclass(frozen=True)
class RenderContext:
    """Inherited render state passed through the node→HTML recursion.

    Frozen by design — child contexts are constructed via :meth:`with_child` or
    :func:`dataclasses.replace`. The one exception is ``slot_counter``: it is a
    *shared mutable dict* (``_next_slot_name`` mutates it in place across the
    whole render). The frozen wrapper protects field reassignment, not the
    referent's contents — that's the intended ownership model.
    """

    section_map: dict[str, EmailSection] = field(default_factory=dict)  # pyright: ignore[reportUnknownVariableType]
    button_ids: frozenset[str] = field(default_factory=frozenset)  # pyright: ignore[reportUnknownVariableType]
    text_meta: dict[str, TextBlock] = field(default_factory=dict)  # pyright: ignore[reportUnknownVariableType]
    gradients_map: dict[str, ExtractedGradient] = field(default_factory=dict)  # pyright: ignore[reportUnknownVariableType]
    props_map: dict[str, _NodeProps] = field(default_factory=dict)  # pyright: ignore[reportUnknownVariableType]
    container_width: int = 600
    parent_bg: str | None = None
    parent_font: str | None = None
    current_section: EmailSection | None = None
    body_font_size: float = 16.0
    compat: ConverterCompatibility | None = None
    indent: int = 0
    depth: int = 0
    slot_counter: dict[str, int] | None = None

    def with_child(
        self,
        *,
        indent: int | None = None,
        depth_delta: int = 1,
        parent_bg: str | None = None,
        parent_font: str | None = None,
        section: EmailSection | None = None,
        container_width: int | None = None,
    ) -> RenderContext:
        """Return a child context with depth bumped and selected fields overridden.

        ``parent_bg``/``parent_font``/``section`` use ``None`` as "inherit" —
        pass an empty string explicitly to clear ``parent_bg``/``parent_font``.
        ``indent`` defaults to ``self.indent + 1`` when omitted.
        """
        return replace(
            self,
            indent=self.indent + 1 if indent is None else indent,
            depth=self.depth + depth_delta,
            parent_bg=self.parent_bg if parent_bg is None else parent_bg,
            parent_font=self.parent_font if parent_font is None else parent_font,
            current_section=self.current_section if section is None else section,
            container_width=self.container_width if container_width is None else container_width,
        )

    @classmethod
    def from_legacy_kwargs(cls, **kw: Any) -> RenderContext:  # noqa: ANN401  # migration helper accepts heterogeneous legacy kwargs
        """Build a context from the pre-refactor ``node_to_email_html`` kwargs.

        Test/migration helper. Maps the old keyword arguments
        (``section_map``, ``button_ids``, ``text_meta``, ``gradients_map``,
        ``props_map``, ``container_width``, ``parent_bg``, ``parent_font``,
        ``current_section``, ``body_font_size``, ``compat``, ``indent``,
        ``slot_counter``, ``_depth``) onto a :class:`RenderContext`.

        ``slot_counter`` keeps its shared-reference semantics — callers
        passing the same dict across multiple calls still see mutations
        propagate.
        """
        button_ids = kw.get("button_ids")
        return cls(
            section_map=kw.get("section_map") or {},
            button_ids=frozenset(button_ids) if button_ids else frozenset(),
            text_meta=kw.get("text_meta") or {},
            gradients_map=kw.get("gradients_map") or {},
            props_map=kw.get("props_map") or {},
            container_width=kw.get("container_width", 600),
            parent_bg=kw.get("parent_bg"),
            parent_font=kw.get("parent_font"),
            current_section=kw.get("current_section"),
            body_font_size=kw.get("body_font_size", 16.0),
            compat=kw.get("compat"),
            indent=kw.get("indent", 0),
            depth=kw.get("_depth", 0),
            slot_counter=kw.get("slot_counter"),
        )
