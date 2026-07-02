from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agent import router as agent_router
from app.api.artifact_boundary import router as artifact_boundary_router
from app.api.interview import router as interview_router
from app.api.preparation import router as preparation_router
from app.api.agent_run import router as agent_run_router
from app.api.workflow import router as workflow_router
from app.api.workflow_run import router as workflow_run_router
from app.config.settings import settings

# 项目入口，创建FastAPI应用，挂载路由

def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

# CORS中间件配置 -- 跨域资源共享
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

#所有的的路由都挂载在/api/interview下
    app.include_router(interview_router, prefix=settings.api_prefix)
    app.include_router(preparation_router, prefix=settings.api_prefix)
    app.include_router(agent_run_router, prefix=settings.api_prefix)
    app.include_router(agent_router, prefix=settings.api_prefix)
    app.include_router(workflow_router, prefix=settings.api_prefix)
    app.include_router(workflow_run_router, prefix=settings.api_prefix)
    app.include_router(artifact_boundary_router, prefix=settings.api_prefix)

    @app.get("/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
