from __future__ import annotations

from models import DisplayStage, ProductionStage, RouteSpec, TransitionSpec


ROUTES: dict[str, RouteSpec] = {
    "full": RouteSpec(
        key="full",
        production_stages=(
            ProductionStage("mining", "Mining"),
            ProductionStage("processing", "Processing"),
            ProductionStage("refining", "Refining"),
            ProductionStage("cathode", "Cathode"),
        ),
        transitions=(
            TransitionSpec("post_trade_1", "1st Post Trade", "mining", "processing"),
            TransitionSpec("post_trade_2", "2nd Post Trade", "processing", "refining"),
            TransitionSpec("post_trade_3", "3rd Post Trade", "refining", "cathode"),
        ),
    ),
    "intermediate": RouteSpec(
        key="intermediate",
        production_stages=(
            ProductionStage("mining", "Mining"),
            ProductionStage("pro_ref", "Pro Ref"),
            ProductionStage("cathode", "Cathode"),
        ),
        transitions=(
            TransitionSpec("post_trade_1", "1st Post Trade", "mining", "pro_ref"),
            TransitionSpec("post_trade_2", "2nd Post Trade", "pro_ref", "cathode"),
        ),
    ),
    "completed": RouteSpec(
        key="completed",
        production_stages=(
            ProductionStage("mining", "Mining"),
            ProductionStage("processing", "Processing"),
            ProductionStage("refining", "Refining"),
            ProductionStage("pcam", "PCAM"),
            ProductionStage("cathode", "Cathode"),
        ),
        transitions=(
            TransitionSpec("post_trade_1", "1st Post Trade", "mining", "processing"),
            TransitionSpec("post_trade_2", "2nd Post Trade", "processing", "refining"),
            TransitionSpec("post_trade_3", "3rd Post Trade", "refining", "pcam"),
            TransitionSpec("post_trade_4", "4th Post Trade", "pcam", "cathode"),
        ),
    ),
}

ROUTE_ALIASES = {"pro_ref": "intermediate", "pcam": "completed"}


def route_from_options(
    merge_processing_refining: bool,
    show_pcam: bool,
    show_battery: bool,
) -> RouteSpec:
    stages = [ProductionStage("mining", "Mining")]
    if merge_processing_refining:
        stages.append(ProductionStage("pro_ref", "Intermediate"))
    else:
        stages.extend((ProductionStage("processing", "Processing"), ProductionStage("refining", "Refining")))
    if show_pcam:
        stages.append(ProductionStage("pcam", "PCAM"))
    stages.append(ProductionStage("cathode", "Cathode"))
    if show_battery:
        stages.append(ProductionStage("battery", "Battery"))
    transitions = tuple(
        TransitionSpec(
            f"post_trade_{index}",
            f"{index}{'st' if index == 1 else 'nd' if index == 2 else 'rd' if index == 3 else 'th'} Post Trade",
            source.key,
            target.key,
        )
        for index, (source, target) in enumerate(zip(stages, stages[1:]), start=1)
    )
    parts = ["merged" if merge_processing_refining else "full"]
    if not show_pcam:
        parts.append("no_pcam")
    if not show_battery:
        parts.append("no_battery")
    return RouteSpec(key="_".join(parts), production_stages=tuple(stages), transitions=transitions)


def display_stages(route: RouteSpec) -> tuple[DisplayStage, ...]:
    stages: list[DisplayStage] = []
    transition_by_source = {transition.source_stage: transition for transition in route.transitions}
    for production in route.production_stages:
        stages.append(
            DisplayStage(
                key=f"P:{production.key}",
                label=production.label,
                production_key=production.key,
            )
        )
        transition = transition_by_source.get(production.key)
        if transition is not None:
            stages.append(
                DisplayStage(
                    key=f"T:{transition.key}",
                    label=transition.label,
                    transition_key=transition.key,
                )
            )
    return tuple(stages)


def route_for(name: str) -> RouteSpec:
    key = str(name).strip().lower()
    key = ROUTE_ALIASES.get(key, key)
    try:
        return ROUTES[key]
    except KeyError as exc:
        raise ValueError(f"Unsupported route {name!r}. Choose from: {', '.join(ROUTES)}") from exc
