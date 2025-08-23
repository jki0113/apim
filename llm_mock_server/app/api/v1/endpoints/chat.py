from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.chat import ChatCompletionRequest
from app.services import chat_service

router = APIRouter()

@router.post("/completions")
async def chat_completions(request: ChatCompletionRequest):
    """LLM Mock Endpoint"""
    if request.stream:
        return StreamingResponse(
            chat_service.stream_generator(request.model),
            media_type="text/event-stream"
        )
    else:
        return await chat_service.create_non_streaming_response(request.model)