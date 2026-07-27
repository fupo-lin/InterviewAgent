import json


def sse_event(event: dict) -> str:
    event_name = str(event.get("event") or "message")
    return (
        f"event: {event_name}\n"
        f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
    )

# 将 Python 字典转换成符合 SSE 协议规范的纯文本字符串
# 前端接收 SSE 数据时，要求格式必须是 event: 事件名\n 加上 data: 数据内容\n\n