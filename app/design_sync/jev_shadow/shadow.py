"""Post-hoc Jev shadow pass over shipped component matches.

Reads the normalised design tree and the ``ComponentMatch`` list the converter
used, asks Jev the O1/O2/O3 questions per section (one fan-out request each),
compares every answer with the heuristic's, and appends one record per
decision to ``traces/jev_shadow.jsonl``. It never calls back into the
converter and never mutates its inputs.

Records go to their own file, not ``converter_traces.jsonl``:
``traces/regression.py`` reads every line of that file and defaults missing
keys, so shadow rows would skew its aggregates.
"""

from __future__ import annotations

import asyncio
import functools
import html
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.design_sync.component_matcher import ComponentMatch, SlotFill
from app.design_sync.figma.layout_analyzer import EmailSection
from app.design_sync.jev_shadow.client import (
    JEV_MODEL,
    ChoiceAnswer,
    JevClient,
    JevError,
    NoulAnswer,
    SystemOneResponse,
)
from app.design_sync.jev_shadow.questions import (
    NONE_OPTION,
    o1_questions,
    o2_questions,
    o3_questions,
    resolve_slots,
)
from app.design_sync.jev_shadow.state import SectionState, build_section_state
from app.design_sync.protocol import DesignFileStructure, DesignNode, DesignNodeType

logger = get_logger(__name__)

SHADOW_PATH = Path("traces/jev_shadow.jsonl")
_CONCURRENCY = 4

_O2_TYPES = frozenset({DesignNodeType.IMAGE, DesignNodeType.VECTOR, DesignNodeType.INSTANCE})
_O3_SLOT_TYPES = frozenset({"text", "image"})
_O3_ATTR_SUFFIXES = ("_url", "_alt", "_height")
_NODE_ID_RE = re.compile(r'data-node-id="([^"]+)"')
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

BUTTON_ICON = "button_icon"
CONTENT_IMAGE = "content_image"
NOT_EXTRACTED = "not_extracted"
UNMAPPED = "unmapped"
MULTI_NODE = "multi_node"


@dataclass(frozen=True)
class ShadowRecord:
    """One heuristic-vs-Jev comparison for one decision."""

    run_label: str
    section_index: int
    section_node_id: str
    decision_point: str  # o1_type | o1_template | o2_button_icon | o3_slot
    subject: str  # section node id (O1), candidate node id (O2), slot id (O3)
    heuristic_answer: str | None
    jev_answer: str | None
    jev_confidence: float | None
    probabilities: dict[str, float] | None
    agree: bool | None
    model: str
    error: str | None = None
    skipped: bool = False
    # Set on the section's ``o1_type`` record only (one per request), so a sum
    # over records gives the run's token usage without double counting.
    input_tokens: int | None = None


@dataclass(frozen=True)
class O3Slot:
    """An eligible slot fill and the section node(s) the heuristic sourced it from."""

    slot_id: str
    slot_type: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class SectionPlan:
    """Everything needed to ask Jev about one section and score its answers."""

    match: ComponentMatch
    section_state: SectionState
    questions: dict[str, dict[str, object]]
    o2_candidates: tuple[str, ...]  # Figma node ids
    o3_slots: tuple[O3Slot, ...]


def _normalise_text(value: str) -> str:
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", value))).strip()


def o3_eligible(fill: SlotFill) -> bool:
    """Content slots only: text/image with a value, not URL/alt/height attributes."""
    return (
        fill.slot_type in _O3_SLOT_TYPES
        and bool(fill.value.strip())
        and not fill.slot_id.endswith(_O3_ATTR_SUFFIXES)
    )


def fill_sources(fill: SlotFill, section: EmailSection) -> tuple[str, ...]:
    """Section node ids a fill was built from: ``data-node-id`` first, then text match."""
    content_ids = (
        {t.node_id for t in section.texts}
        | {b.node_id for b in section.buttons}
        | {i.node_id for i in section.images}
    )
    found: list[str] = []
    for nid in [fill.attr_overrides.get("data-node-id", ""), *_NODE_ID_RE.findall(fill.value)]:
        if nid in content_ids and nid not in found:
            found.append(nid)
    if found:
        return tuple(found)
    text = _normalise_text(fill.value)
    if not text:
        return ()
    by_text = [t.node_id for t in section.texts if _normalise_text(t.content) == text]
    by_text += [b.node_id for b in section.buttons if _normalise_text(b.text) == text]
    return tuple(dict.fromkeys(by_text))


def _iter_nodes(root: DesignNode) -> list[DesignNode]:
    out: list[DesignNode] = []
    stack = [root]
    while stack:
        node = stack.pop()
        out.append(node)
        stack.extend(node.children)
    return out


def index_nodes(structure: DesignFileStructure) -> dict[str, DesignNode]:
    return {n.id: n for page in structure.pages for n in _iter_nodes(page)}


def plan_section(match: ComponentMatch, node: DesignNode, index: int, total: int) -> SectionPlan:
    """Build state and every O1/O2/O3 question for one matched section."""
    section = match.section
    sstate = build_section_state(section, node, index, total)
    reverse = {fid: short for short, fid in sstate.ids.items()}

    types = {n.id: n.type for n in _iter_nodes(node)}
    o2_candidates = tuple(
        fid for fid in sstate.ids.values() if fid in sstate.button_nodes and types[fid] in _O2_TYPES
    )

    o3_slots = tuple(
        O3Slot(f.slot_id, f.slot_type, fill_sources(f, section))
        for f in match.slot_fills
        if o3_eligible(f)
    )
    candidate_ids = [t.node_id for t in section.texts]
    candidate_ids += [i.node_id for i in section.images]
    candidate_ids += [b.node_id for b in section.buttons]
    candidate_shorts = list(dict.fromkeys(reverse[c] for c in candidate_ids if c in reverse))
    asked = [(s.slot_id, s.slot_type) for s in o3_slots if len(s.sources) == 1]

    questions = o1_questions()
    questions.update(o2_questions([reverse[fid] for fid in o2_candidates]))
    questions.update(o3_questions(asked, candidate_shorts, match.component_slug))
    return SectionPlan(match, sstate, questions, o2_candidates, o3_slots)


def _o2_heuristic(node_id: str, section: EmailSection) -> str:
    # images first: on slate the icon id is the wrapper frame while its IMAGE
    # child sits in ``section.images`` — that child ships as a content image.
    if node_id in {i.node_id for i in section.images}:
        return CONTENT_IMAGE
    if node_id in {b.icon_node_id for b in section.buttons if b.icon_node_id}:
        return BUTTON_ICON
    return NOT_EXTRACTED


def _records_for(
    plan: SectionPlan,
    run_label: str,
    response: SystemOneResponse | None,
    error: str | None,
) -> list[ShadowRecord]:
    match = plan.match
    section = match.section
    ids = plan.section_state.ids
    reverse = {fid: short for short, fid in ids.items()}
    answers = response.answers if response else {}
    model = response.model if response else JEV_MODEL
    record = functools.partial(
        ShadowRecord,
        run_label=run_label,
        section_index=match.section_idx,
        section_node_id=section.node_id,
        model=model,
        error=error,
    )
    records: list[ShadowRecord] = []

    for qid, point, heuristic in (
        ("o1_type", "o1_type", section.section_type.value),
        ("o1_template", "o1_template", match.component_slug),
    ):
        ans = answers.get(qid)
        choice = ans if isinstance(ans, ChoiceAnswer) else None
        records.append(
            record(
                decision_point=point,
                subject=section.node_id,
                heuristic_answer=heuristic,
                jev_answer=choice.choice if choice else None,
                jev_confidence=choice.confidence if choice else None,
                probabilities=dict(choice.probabilities) if choice else None,
                agree=(choice.choice == heuristic) if choice else None,
                input_tokens=(
                    response.usage.input_tokens if response and point == "o1_type" else None
                ),
            )
        )

    for fid in plan.o2_candidates:
        heuristic = _o2_heuristic(fid, section)
        ans = answers.get(f"o2_{reverse[fid]}")
        noul = ans.noul if isinstance(ans, NoulAnswer) else None
        jev = None if noul is None else (BUTTON_ICON if noul >= 0.5 else CONTENT_IMAGE)
        records.append(
            record(
                decision_point="o2_button_icon",
                subject=fid,
                heuristic_answer=heuristic,
                jev_answer=jev,
                jev_confidence=None if noul is None else max(noul, 1 - noul),
                probabilities=None if noul is None else {"yes": noul, "no": 1 - noul},
                agree=None if jev is None else (jev == BUTTON_ICON) == (heuristic == BUTTON_ICON),
            )
        )

    slot_probs: dict[str, dict[str, float]] = {}
    for slot in plan.o3_slots:
        ans = answers.get(f"o3_{slot.slot_id}")
        if isinstance(ans, ChoiceAnswer):
            slot_probs[slot.slot_id] = dict(ans.probabilities)
    resolved = resolve_slots(slot_probs)
    for slot in plan.o3_slots:
        if len(slot.sources) != 1:
            records.append(
                record(
                    decision_point="o3_slot",
                    subject=slot.slot_id,
                    heuristic_answer=UNMAPPED if not slot.sources else MULTI_NODE,
                    jev_answer=None,
                    jev_confidence=None,
                    probabilities=None,
                    agree=None,
                    skipped=True,
                )
            )
            continue
        heuristic = slot.sources[0]
        probs = slot_probs.get(slot.slot_id)
        jev_answer: str | None = None
        confidence: float | None = None
        if probs is not None:
            # Confidence is the resolved option's probability, not Jev's raw top
            # pick: a slot displaced by the uniqueness rule must not carry the
            # confidence of the node it lost.
            option = resolved.get(slot.slot_id) or NONE_OPTION
            jev_answer = ids.get(option, NONE_OPTION)
            confidence = probs.get(option, 0.0)
        records.append(
            record(
                decision_point="o3_slot",
                subject=slot.slot_id,
                heuristic_answer=heuristic,
                jev_answer=jev_answer,
                jev_confidence=confidence,
                probabilities=(
                    {ids.get(k, k): v for k, v in probs.items()} if probs is not None else None
                ),
                agree=None if jev_answer is None else jev_answer == heuristic,
            )
        )
    return records


def _append(records: list[ShadowRecord]) -> None:
    if not records:
        return
    SHADOW_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SHADOW_PATH.open("a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(asdict(record), sort_keys=True) + "\n")


async def run_jev_shadow(
    structure: DesignFileStructure,
    matches: list[ComponentMatch],
    *,
    run_label: str,
    client: JevClient | None = None,
) -> list[ShadowRecord]:
    """Ask Jev about every matched section; log, never raise, never mutate."""
    settings = get_settings().design_sync
    if not settings.jev_shadow_enabled:
        return []
    api_key = settings.jev_api_key.get_secret_value()
    if not api_key:
        logger.warning("design_sync.jev_shadow.no_api_key", run_label=run_label)
        return []

    nodes = index_nodes(structure)
    jev = client or JevClient(api_key)
    semaphore = asyncio.Semaphore(_CONCURRENCY)
    total = len(matches)

    async def one(i: int, match: ComponentMatch) -> list[ShadowRecord]:
        node = nodes.get(match.section.node_id)
        if node is None:
            logger.warning(
                "design_sync.jev_shadow.node_not_found",
                run_label=run_label,
                section_index=match.section_idx,
            )
            return []
        plan = plan_section(match, node, i, total)
        async with semaphore:
            try:
                response = await jev.system_one(plan.section_state.state, plan.questions)
            except (JevError, httpx.HTTPError, TimeoutError) as exc:
                status = exc.status if isinstance(exc, JevError) else None
                logger.warning(
                    "design_sync.jev_shadow.request_failed",
                    run_label=run_label,
                    section_index=match.section_idx,
                    status=status,
                    error_type=type(exc).__name__,
                )
                return _records_for(plan, run_label, None, f"{type(exc).__name__}: {exc}")
        records = _records_for(plan, run_label, response, None)
        logger.info(
            "design_sync.jev_shadow.section_done",
            run_label=run_label,
            section_index=match.section_idx,
            questions=len(plan.questions),
            disagreements=sum(1 for r in records if r.agree is False),
        )
        return records

    try:
        per_section = await asyncio.gather(*(one(i, m) for i, m in enumerate(matches)))
    finally:
        if client is None:
            await jev.aclose()

    records = [r for section_records in per_section for r in section_records]
    _append(records)
    logger.info(
        "design_sync.jev_shadow.run_done",
        run_label=run_label,
        sections=total,
        records=len(records),
        errors=sum(1 for r in records if r.error),
        input_tokens=sum(r.input_tokens for r in records if r.input_tokens is not None),
    )
    return records
