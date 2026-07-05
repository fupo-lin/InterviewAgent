from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.schemas.interview import (
    ChatRequest,
    ChatResponse,
    EndInterviewRequest,
    EndInterviewResponse,
    GrowthReportResponse,
    HistoryResponse,
    InterviewExecutionResponse,
    DeleteResponse,
    StartInterviewRequest,
    StartInterviewResponse,
)
from app.service.interview_service import InterviewService

router = APIRouter(prefix="/interview", tags=["interview"])


# response_model_by_alias确保传递回去的响应中使用别名而不是内部字段名
#async表示这是一个异步函数  
# db: Session = Depends(get_db)表示依赖注入，
# Depends(get_db) 的作用：	每次请求进来时，FastAPI 自动调用 get_db()，给这个接口准备一个数据库 Session。只是这个session取名叫db

@router.post("/start", response_model=StartInterviewResponse, response_model_by_alias=True)
async def start_interview(payload: StartInterviewRequest, db: Session = Depends(get_db)):
    service = InterviewService(db)
    session_id, reply = await service.start(payload.role_name) # 调用start方法，因为是异步方法，所以要await
    return StartInterviewResponse(sessionId=session_id, reply=reply)


@router.post("/chat", response_model=ChatResponse, response_model_by_alias=True)
async def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    service = InterviewService(db)
    reply, round_no = await service.chat(payload.session_id, payload.message)
    return ChatResponse(reply=reply, roundNo=round_no)


@router.post("/end", response_model=EndInterviewResponse)
async def end_interview(payload: EndInterviewRequest, db: Session = Depends(get_db)):
    service = InterviewService(db)
    evaluation = await service.end(payload.session_id)
    return EndInterviewResponse(evaluation=evaluation)


@router.get("/history/{session_id}", response_model=HistoryResponse, response_model_by_alias=True)
def get_history(session_id: str, db: Session = Depends(get_db)):
    service = InterviewService(db)
    return service.history(session_id)


@router.get("/{session_id}/execution", response_model=InterviewExecutionResponse, response_model_by_alias=True)
def get_execution(session_id: str, db: Session = Depends(get_db)):
    service = InterviewService(db)
    return service.execution(session_id)


@router.get("/{session_id}/growth-report", response_model=GrowthReportResponse, response_model_by_alias=True)
def get_growth_report(session_id: str, db: Session = Depends(get_db)):
    service = InterviewService(db)
    return service.growth_report(session_id)


@router.post("/{session_id}/growth-report/generate", response_model=GrowthReportResponse, response_model_by_alias=True)
async def generate_growth_report(session_id: str, db: Session = Depends(get_db)):
    service = InterviewService(db)
    return await service.generate_growth_report(session_id)


@router.delete("/delete/{session_id}", response_model=DeleteResponse, response_model_by_alias=True)
def delete_history(session_id: str, db: Session = Depends(get_db)):
    service = InterviewService(db)
    return service.delete(session_id)
