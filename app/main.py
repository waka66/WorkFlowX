from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError

from app.api.v1 import auth, users, teams, projects, tasks, systems
from app.core.exceptions import AppException
from app.core.exception_handlers import (app_exception_handler,unhandled_exception_handler,validation_exception_handler)
from app.core.middlewares import register_middleware
import app.models


app = FastAPI(root_path="/api/v1")

# CORS 中间件,
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(
    AppException,
    app_exception_handler,
)

app.add_exception_handler(
    Exception,
    unhandled_exception_handler,
)

app.add_exception_handler(RequestValidationError, validation_exception_handler)

register_middleware(app)


@app.get("/")
async def root():
    return {"message": "Hello World"}

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(teams.router)
app.include_router(projects.team_projects_router)
app.include_router(projects.projects_router)
app.include_router(tasks.workflows_router)
app.include_router(tasks.tasks_router)
app.include_router(tasks.router)
app.include_router(tasks.projects_router)
app.include_router(tasks.comments_router)
app.include_router(systems.router)
app.include_router(systems.activities_router)
app.include_router(systems.logs_router)
app.include_router(systems.dashboard_router)
app.include_router(systems.search_router)



app.mount("/static", StaticFiles(directory="uploads"), name="static")
