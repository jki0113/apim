import asyncio
import time
import uuid
from datetime import datetime
from typing import AsyncGenerator

from app.models.chat import (
    ChatMessage,
    ChatCompletionResponse,
    ChatCompletionResponseChoice,
    ChatCompletionStreamChoice,
    ChatCompletionStreamResponse,
    DeltaMessage,
    Usage,
)
from app.core.logger import get_logger
logger = get_logger(__name__)

async def stream_generator(model: str) -> AsyncGenerator[str, None]:
    """Streaming 응답 생성 로직"""
    chat_id = f"chat_completions-{uuid.uuid4().hex}"
    created_timestamp = int(time.time())

    first_chunk = ChatCompletionStreamResponse(
        id=chat_id, model=model, created=created_timestamp,
        choices=[ChatCompletionStreamChoice(delta=DeltaMessage(role="assistant"))],
    )
    yield_data = f"data: {first_chunk.model_dump_json(exclude_unset=True)}\n\n"
    logger.info(f"{yield_data.strip()}")
    yield yield_data    
    await asyncio.sleep(0.01)

    for word in f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}-{str(uuid.uuid4())}":
        delta = DeltaMessage(content=word + " ")
        chunk = ChatCompletionStreamResponse(
            id=chat_id, model=model, created=created_timestamp,
            choices=[ChatCompletionStreamChoice(delta=delta)],
        )
        yield_data = f"data: {chunk.model_dump_json(exclude_unset=True)}\n\n"
        logger.info(f"{yield_data.strip()}")
        yield yield_data
        await asyncio.sleep(0.01)

    final_chunk = ChatCompletionStreamResponse(
        id=chat_id, model=model, created=created_timestamp,
        choices=[ChatCompletionStreamChoice(delta=DeltaMessage(), finish_reason="stop")],
    )
    yield_data = f"data: {final_chunk.model_dump_json(exclude_unset=True)}\n\n"
    logger.info(f"{yield_data.strip()}")
    yield yield_data
    yield "data: [DONE]\n\n"

async def create_non_streaming_response(model: str) -> ChatCompletionResponse:
    """Non-Streaming 응답 생성 로직"""
    await asyncio.sleep(0.01)
    response = ChatCompletionResponse(
        model=model,
        choices=[
            ChatCompletionResponseChoice(
                message=ChatMessage(role="assistant", content=f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}-{str(uuid.uuid4())}")
            )
        ],
        usage=Usage(),
    )
    logger.info(f"{response.model_dump_json(exclude_unset=True, indent=2)}")
    return response