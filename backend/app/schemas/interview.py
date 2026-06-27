from datetime import datetime

from pydantic import BaseModel, Field

# BaseModel 提供了基础的类型检查（比如你传了数字但它要求字符串，它会报错）
# Field用于定义字段的属性和验证规则，使用Field可以设置更多的约束条件，没有的话只能给这个字段设置str

class StartInterviewRequest(BaseModel):
    role_name: str = Field(alias="roleName", min_length=1, max_length=50)


# 默认情况下，当设置了 alias 后，Pydantic 只认别名
# （即只接受 roleName，拒绝 role_name）。但加上 populate_by_name = True 后，相当于开启了“双重通行证”

class StartInterviewResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    reply: str

    class Config:
        populate_by_name = True



class ChatRequest(BaseModel):
    session_id: str = Field(alias="sessionId", min_length=1)
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    reply: str
    round_no: int = Field(alias="roundNo")

    class Config:
        populate_by_name = True


class EndInterviewRequest(BaseModel):
    session_id: str = Field(alias="sessionId", min_length=1)


class EvaluationResponse(BaseModel):
    strengths: str
    weaknesses: str
    suggestions: str
    technical_ability: str = Field(default="", alias="technicalAbility")
    project_experience: str = Field(default="", alias="projectExperience")
    communication: str = ""
    improvement_suggestions: str = Field(default="", alias="improvementSuggestions")
    summary: str | None = None

    class Config:
        populate_by_name = True


class EndInterviewResponse(BaseModel):
    evaluation: EvaluationResponse


class MessageResponse(BaseModel):
    role_type: str = Field(alias="roleType")
    message_type: str = Field(alias="messageType")
    round_no: int = Field(alias="roundNo")
    content: str
    create_time: datetime = Field(alias="createTime")

    class Config:
        populate_by_name = True


class HistoryResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    role_name: str = Field(alias="roleName")
    status: str
    messages: list[MessageResponse]
    evaluation: EvaluationResponse | None = None

    class Config:
        populate_by_name = True

class DeleteResponse(BaseModel):
    success: bool
