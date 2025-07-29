import os
os.environ.pop("SSL_CERT_FILE", None)

from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from uuid import uuid4
from app.agent.graph import app as travel_graph
from langchain_core.messages import HumanMessage


# Memory store for jobs (in-memory dict for now)
jobs = {}


app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TravelQuery(BaseModel):
    message: str


# Background processing task
async def process_trip(job_id: str, message: str):
    try:
        stream = travel_graph.astream(
            {"messages": [HumanMessage(content=message)]},
            config={"configurable": {"thread_id": f"user-{job_id}"}},
            stream_mode="values"
        )

        result = []
        async for event in stream:
            content = event["messages"][-1].content
            if content:
                result.append(content)

        jobs[job_id] = {"status": "done", "response": result[-1] if result else "No response."}
        
    except Exception as e:
        jobs[job_id] = {"status": "error", "response": f"Error: {str(e)}"}


# POST to start trip planning
@app.post("/start-plan-trip")
async def start_trip(query: TravelQuery, bg: BackgroundTasks):
    job_id = str(uuid4())
    jobs[job_id] = {"status": "processing", "response": None}
    bg.add_task(process_trip, job_id, query.message)
    return {"job_id": job_id}


# Polling endpoint
@app.get("/get-response/{job_id}")
async def get_result(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return {"status": "not_found", "response": "Invalid job ID."}
    return job


# Serve frontend
@app.get("/")
def serve_ui():
    return FileResponse("frontend/index.html")