"""FastAPI application entry point.

Configures the application with:
- Lifespan event management for startup/shutdown
- Structured logging setup
- Request/response middleware
- CORS support
- Health check endpoints
- Global exception handlers
"""

import contextlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, cast

import uvicorn
from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler  # pyright: ignore[reportMissingTypeStubs]
from slowapi.errors import RateLimitExceeded  # pyright: ignore[reportMissingTypeStubs]

# AI agents
from app.ai.agents.content.routes import router as content_router
from app.ai.agents.dark_mode.routes import router as dark_mode_router
from app.ai.agents.scaffolder.routes import router as scaffolder_router
from app.ai.agents.scaffolder.variant_routes import router as variant_router
from app.ai.agents.skills_routes import router as skills_router
from app.ai.blueprints.routes import router as blueprint_router
from app.ai.blueprints.routes import runs_router as blueprint_runs_router
from app.ai.cost_governor_routes import router as cost_governor_router
from app.ai.exceptions import setup_ai_exception_handlers
from app.ai.prompt_store_routes import router as prompt_store_router
from app.ai.routes import router as ai_router
from app.ai.voice.routes import router as voice_router
from app.approval.routes import router as approval_router
from app.auth.routes import router as auth_router
from app.components.routes import router as components_router
from app.connectors.routes import router as connectors_router
from app.connectors.sync_routes import router as connector_sync_router
from app.core.config import get_settings
from app.core.database import engine
from app.core.exceptions import setup_exception_handlers
from app.core.health import router as health_router
from app.core.logging import get_logger, setup_logging
from app.core.middleware import setup_middleware
from app.core.progress_routes import router as progress_router
from app.core.rate_limit import limiter
from app.core.redis import close_redis, redis_available
from app.design_sync.routes import router as design_sync_router
from app.email_engine.routes import router as email_engine_router
from app.knowledge.ontology.routes import router as ontology_router
from app.knowledge.routes import router as knowledge_router
from app.memory.routes import router as memory_router
from app.personas.routes import router as personas_router

# Email Hub modules
from app.projects.routes import router as projects_router
from app.qa_engine.routes import router as qa_router
from app.rendering.routes import router as rendering_router
from app.streaming.websocket.routes import (
    close_collab_manager,
    collab_router,
    set_collab_manager,
    set_redis_bridge,
    set_sync_handler,
)
from app.templates.routes import router as templates_router

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan event handler."""
    # Startup
    setup_logging(
        log_level=settings.log_level,
        pii_redaction=settings.logging_pii_redaction,
    )
    logger = get_logger(__name__)

    # Initialise Sentry + OTEL (Phase 3 §3.3) — both no-op when unconfigured
    from app.core.observability import init_observability

    init_observability(_app, settings)

    # SECURITY: Fail hard if JWT secret is weak in non-development environments
    _insecure_defaults = {
        "CHANGE-ME-IN-PRODUCTION",
        "CHANGE-ME-IN-PRODUCTION-this-is-not-a-real-secret",
        "",
        "secret",
        "changeme",
    }
    if settings.environment != "development" and (
        settings.auth.jwt_secret_key in _insecure_defaults or len(settings.auth.jwt_secret_key) < 32
    ):
        msg = "AUTH__JWT_SECRET_KEY must be a strong secret (min 32 chars) in non-development environments"
        raise RuntimeError(msg)

    # SECURITY: Block default database credentials in non-development environments
    if settings.environment != "development" and "postgres:postgres@" in settings.database.url:
        msg = "DATABASE__URL must not use default credentials (postgres:postgres) in non-development environments"
        raise RuntimeError(msg)

    logger.info(
        "application.lifecycle_started",
        app_name=settings.app_name,
        version=settings.version,
        environment=settings.environment,
    )
    logger.info("database.connection_initialized")

    # Start collaboration WebSocket manager + Redis bridge (Phase 24.1)
    collab_bridge = None
    if settings.collab_ws.enabled:
        from app.streaming.websocket.manager import CollabConnectionManager
        from app.streaming.websocket.redis_bridge import RedisPubSubBridge

        collab_mgr = CollabConnectionManager(
            max_per_room=settings.collab_ws.max_connections_per_room,
            max_rooms_per_user=settings.collab_ws.max_rooms_per_user,
        )
        set_collab_manager(collab_mgr)

        collab_bridge = RedisPubSubBridge(collab_mgr)
        set_redis_bridge(collab_bridge)
        await collab_bridge.start()

        # CRDT layer (Phase 24.2)
        if settings.collab_ws.crdt_enabled:
            from app.streaming.crdt.document_store import YjsDocumentStore
            from app.streaming.crdt.sync_handler import YjsSyncHandler

            crdt_store = YjsDocumentStore(
                compaction_threshold=settings.collab_ws.crdt_compaction_threshold,
                compaction_interval_s=settings.collab_ws.crdt_compaction_interval_s,
                max_document_size_mb=settings.collab_ws.crdt_max_document_size_mb,
            )
            crdt_sync = YjsSyncHandler(crdt_store)
            set_sync_handler(crdt_sync)
            logger.info("crdt.document_store_started")

        logger.info("collab.ws.manager_started")

    # Load model capability registry from config (Phase 22.1)
    if settings.ai.model_specs:
        from app.ai.capability_registry import load_model_specs_from_config

        load_model_specs_from_config(settings.ai.model_specs)

    # Preload prompt store cache (Phase 22.2)
    if settings.ai.prompt_store_enabled:
        from app.ai.prompt_store import preload_prompt_store_cache
        from app.core.database import get_db_context

        async with get_db_context() as db:
            await preload_prompt_store_cache(db)

    # Start outcome graph poller (feeds blueprint outcomes into Cognee)
    outcome_poller = None
    if getattr(settings, "cognee", None) and settings.cognee.enabled:
        try:
            from app.ai.blueprints.outcome_poller import OutcomeGraphPoller

            outcome_poller = OutcomeGraphPoller()
            await outcome_poller.start()
            logger.info("blueprint.outcome_poller_started")
        except Exception:
            logger.warning("blueprint.outcome_poller_start_failed", exc_info=True)

    # Start Can I Email ontology sync poller
    caniemail_poller = None
    if settings.ontology_sync.enabled:
        try:
            from app.knowledge.ontology.sync.poller import CanIEmailSyncPoller

            caniemail_poller = CanIEmailSyncPoller()
            await caniemail_poller.start()
            logger.info("ontology.sync.poller_started")
        except Exception:
            logger.warning("ontology.sync.poller_start_failed", exc_info=True)

    # Start rendering change detection poller
    change_detector_poller = None
    if settings.change_detection.enabled:
        try:
            from app.knowledge.ontology.change_poller import RenderingChangePoller

            change_detector_poller = RenderingChangePoller()
            await change_detector_poller.start()
            logger.info("change_detection.poller_started")
        except Exception:
            logger.warning("change_detection.poller_start_failed", exc_info=True)

    # Start production judge worker (samples successful runs for offline LLM judging)
    judge_worker = None
    if settings.eval.production_sample_rate > 0.0 and await redis_available():
        try:
            from app.ai.agents.evals.production_sampler import ProductionJudgeWorker

            judge_worker = ProductionJudgeWorker()
            await judge_worker.start()
            logger.info("eval.production_judge_worker_started")
        except Exception:
            logger.warning("eval.production_judge_worker_start_failed", exc_info=True)

    # Start checkpoint cleanup poller (daily, deletes old/completed checkpoints)
    checkpoint_poller = None
    if settings.blueprint.checkpoints_enabled:
        try:
            from app.ai.blueprints.checkpoint_cleanup import CheckpointCleanupPoller

            checkpoint_poller = CheckpointCleanupPoller()
            await checkpoint_poller.start()
            logger.info("blueprint.checkpoint_cleanup_poller_started")
        except Exception:
            logger.warning("blueprint.checkpoint_cleanup_poller_start_failed", exc_info=True)

    # Start cron scheduling engine (Phase 45.1)
    scheduler = None
    if settings.scheduling.enabled:
        try:
            from app.scheduling.engine import CronScheduler

            scheduler = CronScheduler(settings.scheduling)
            await scheduler.start()
            logger.info("scheduling.scheduler_started")
        except Exception:
            logger.warning("scheduling.scheduler_start_failed", exc_info=True)

    # Initialize credential pools eagerly (Phase 46.4)
    if settings.credentials.enabled:
        from app.core.credentials import initialize_pools

        initialize_pools()

    # Load plugins (Phase 25.1) + lifecycle (Phase 25.2)
    _lifecycle_manager = None
    if settings.plugins.enabled:
        try:
            from pathlib import Path

            from app.plugins.lifecycle import PluginLifecycleManager
            from app.plugins.registry import get_plugin_registry

            plugin_registry = get_plugin_registry()
            plugin_dir = Path(settings.plugins.directory)
            loaded = plugin_registry.discover_and_load(plugin_dir)
            logger.info("plugins.startup_complete", loaded_count=len(loaded), plugins=loaded)

            # Start lifecycle health monitor
            _lifecycle_manager = PluginLifecycleManager(
                registry=plugin_registry,
                sandbox=plugin_registry.sandbox,
                health_check_interval_s=settings.plugins.health_check_interval_s,
                max_consecutive_failures=settings.plugins.max_consecutive_failures,
            )
            _lifecycle_manager.start_health_monitor()
        except Exception:
            logger.warning("plugins.startup_failed", exc_info=True)

    # Sync Kestra flow templates (Phase 25.5)
    if settings.kestra.enabled:
        try:
            from app.workflows.service import get_workflow_service

            wf_service = get_workflow_service()
            if await wf_service.health_check():
                synced = await wf_service.sync_flow_templates()
                logger.info("kestra.templates_synced", count=synced)
            else:
                logger.warning("kestra.unavailable_at_startup")
        except Exception:
            logger.warning("kestra.startup_sync_failed", exc_info=True)

    # Mount MCP server session manager (Phase 23.4)
    if settings.mcp.enabled:
        try:
            from app.mcp.server import get_mcp_server

            get_mcp_server()  # Pre-create singleton during startup
            logger.info("mcp.mounted", transport="streamable-http", path="/mcp")
        except Exception:
            logger.warning("mcp.mount_failed", exc_info=True)

    # Start progress cleanup loop (Phase 42.6)
    import asyncio

    from app.core.progress import ProgressTracker

    async def _progress_cleanup_loop() -> None:
        while True:
            await asyncio.sleep(settings.progress.cleanup_interval_seconds)
            ProgressTracker.cleanup_completed(settings.progress.max_retention_seconds)

    progress_cleanup_task = asyncio.create_task(_progress_cleanup_loop())
    logger.info("progress.cleanup_loop_started")

    yield

    # Shutdown

    progress_cleanup_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await progress_cleanup_task
    logger.info("progress.cleanup_loop_stopped")

    if scheduler is not None:
        await scheduler.stop()
        logger.info("scheduling.scheduler_stopped")

    if _lifecycle_manager is not None:
        await _lifecycle_manager.shutdown_all()
        logger.info("plugins.lifecycle_manager_stopped")

    if checkpoint_poller is not None:
        await checkpoint_poller.stop()
        logger.info("blueprint.checkpoint_cleanup_poller_stopped")

    if judge_worker is not None:
        await judge_worker.stop()
        logger.info("eval.production_judge_worker_stopped")

    if change_detector_poller is not None:
        await change_detector_poller.stop()
        logger.info("change_detection.poller_stopped")

    if caniemail_poller is not None:
        await caniemail_poller.stop()
        logger.info("ontology.sync.poller_stopped")

    if outcome_poller is not None:
        await outcome_poller.stop()
        logger.info("blueprint.outcome_poller_stopped")

    if collab_bridge is not None:
        await collab_bridge.stop()
        close_collab_manager()
        logger.info("collab.ws.manager_stopped")

    await close_redis()
    await engine.dispose()
    logger.info("database.connection_closed")
    logger.info("application.lifecycle_stopped", app_name=settings.app_name)


# Create FastAPI application
_is_dev = settings.environment == "development"

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    lifespan=lifespan,
    docs_url="/docs" if _is_dev else None,
    openapi_url="/openapi.json" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
)

# Setup rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, cast(Any, _rate_limit_exceeded_handler))

# Setup middleware
setup_middleware(app)

# Setup exception handlers
setup_exception_handlers(app)

setup_ai_exception_handlers(app)


# Include routers
app.include_router(health_router)
app.include_router(auth_router)

app.include_router(ai_router)
# Dual-mount so the Next.js /api/v1/* proxy can reach chat completions.
# ai_router has prefix="/v1", so mounting under "/api" yields /api/v1/chat/completions.
# Rate limiting is shared (slowapi keys by function, not path).
app.include_router(ai_router, prefix="/api", include_in_schema=False)


app.include_router(knowledge_router)
app.include_router(ontology_router)


app.include_router(collab_router)

# Email Hub routers
app.include_router(projects_router)
app.include_router(email_engine_router)
app.include_router(components_router)
app.include_router(qa_router)
app.include_router(connectors_router)
app.include_router(connector_sync_router)
app.include_router(design_sync_router)
app.include_router(approval_router)
app.include_router(personas_router)
app.include_router(templates_router)
app.include_router(rendering_router)
app.include_router(progress_router)
app.include_router(memory_router)

# Briefs — project management platform connections
if settings.briefs.enabled:
    from app.briefs.routes import router as briefs_router

    app.include_router(briefs_router)

# AI agents
app.include_router(scaffolder_router)
app.include_router(dark_mode_router)
app.include_router(content_router)
app.include_router(blueprint_router)
app.include_router(blueprint_runs_router)

app.include_router(skills_router)
app.include_router(prompt_store_router)
app.include_router(cost_governor_router)

# Voice brief input pipeline (Phase 23.5)
app.include_router(voice_router, prefix="/api")

# Tolgee TMS endpoints (Phase 25.3) — optional feature toggle
if settings.tolgee.enabled:
    from app.connectors.tolgee.routes import router as tolgee_router

    app.include_router(tolgee_router)

# Plugin admin endpoints (Phase 25.1)
if settings.plugins.enabled:
    from app.plugins.routes import router as plugins_router

    app.include_router(plugins_router)

# Workflow orchestration endpoints (Phase 25.5)
if settings.kestra.enabled:
    from app.workflows.routes import router as workflows_router

    app.include_router(workflows_router)

# Typst QA report generation (Phase 25.7)
if settings.reporting.enabled:
    from app.reporting.routes import router as reporting_router

    app.include_router(reporting_router)

# Template upload pipeline (Phase 25.10)
if settings.templates.upload_enabled:
    from app.templates.upload.routes import router as template_upload_router

    app.include_router(template_upload_router)

    # Template eval case management (Phase 25.12)
    from app.ai.agents.evals.template_eval_routes import router as eval_template_router

    app.include_router(eval_template_router)

# Multi-variant campaign assembly (Phase 25.14) — graduated default-on
app.include_router(variant_router)

# Credential pool health (Phase 46.4)
if settings.credentials.enabled:
    from app.core.credentials_routes import router as credentials_health_router

    app.include_router(credentials_health_router)

# Cron scheduling engine (Phase 45.1)
if settings.scheduling.enabled:
    from app.scheduling.routes import router as scheduling_router

    app.include_router(scheduling_router)

# Skill extraction endpoints (Phase 25.11)
if settings.skill_extraction.enabled:
    from app.ai.skills.routes import router as skill_extraction_router

    app.include_router(skill_extraction_router)

# Mount MCP streamable HTTP transport (Phase 23.4)
if settings.mcp.enabled:
    from starlette.routing import Mount as StarletteMount

    from app.mcp.server import get_mcp_asgi_app

    app.routes.append(StarletteMount("/mcp", app=get_mcp_asgi_app()))


@app.get("/")
def read_root() -> dict[str, str]:
    """Root endpoint providing API information."""
    response: dict[str, str] = {"message": settings.app_name}
    if settings.environment == "development":
        response["version"] = settings.version
        response["docs"] = "/docs"
    return response


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # noqa: S104
        port=8891,
        reload=True,
    )
