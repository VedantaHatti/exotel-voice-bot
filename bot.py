import os
import sys
import time
import requests
import json
from dotenv import load_dotenv
from loguru import logger
from typing import Optional

from pipecat.frames.frames import TextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.serializers.exotel import ExotelFrameSerializer
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

import config

load_dotenv(override=True)

# Fix duplicate logging
logger.remove()
logger.add(sys.stderr, level=config.LOG_LEVEL)


def make_outbound_call_to_existing_flow(
    customer_number: str,
    custom_field: Optional[str] = None
) -> dict:
    """
    Make outbound call using your EXISTING Exotel call flow
    No manual coding needed - uses the same flow as inbound calls
    """
    
    # Get credentials
    api_key = os.getenv("EXOTEL_API_KEY")
    api_token = os.getenv("EXOTEL_API_TOKEN")
    account_sid = os.getenv("EXOTEL_ACCOUNT_SID")
    subdomain = os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.com")
    caller_id = os.getenv("EXOTEL_CALLER_ID")
    app_id = os.getenv("EXOTEL_APP_ID")  # Your existing voice app ID
    
    if not all([api_key, api_token, account_sid, caller_id, app_id]):
        raise ValueError("Missing required Exotel credentials")
    
    # API URL - request JSON response explicitly
    url = f"https://{api_key}:{api_token}@{subdomain}/v1/Accounts/{account_sid}/Calls/connect.json"
    
    # Voice URL - points to your existing call flow
    voice_url = f"http://my.exotel.com/{account_sid}/exoml/start_voice/{app_id}"
    
    # API payload
    data = {
        'From': customer_number,
        'CallerId': caller_id,
        'Url': voice_url,  # This connects to your existing flow
        'CallType': 'trans',
        'TimeLimit': str(config.CALL_TIMEOUT),
        'TimeOut': str(config.RING_TIMEOUT),
    }
    
    if custom_field:
        data['CustomField'] = custom_field
    
    logger.info(f"📞 Making outbound call to: {customer_number}")
    logger.info(f"🎯 Using existing voice app: {app_id}")
    logger.info(f"🔗 Voice URL: {voice_url}")
    
    try:
        response = requests.post(url, data=data, timeout=30)
        logger.info(f"📡 Response status: {response.status_code}")
        logger.info(f"📋 Response: {response.text}")
        
        response.raise_for_status()
        
        if response.text.strip():
            try:
                result = response.json()
                logger.info(f"✅ Call initiated successfully!")
                logger.info(f"📋 Call SID: {result.get('Call', {}).get('Sid', 'unknown')}")
                return result
            except json.JSONDecodeError:
                logger.warning("⚠️ Non-JSON response but call likely successful")
                return {"success": True, "response": response.text}
        else:
            logger.warning("⚠️ Empty response but call likely successful")
            return {"success": True, "message": "Call initiated"}
            
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to make outbound call: {e}")
        raise


async def run_bot(
    websocket_client,
    stream_sid: str,
    call_sid: str
):
    """Your existing bot code - no changes needed"""
    logger.info(f"\U0001F680 Starting optimized Exotel bot for call {call_sid}, stream {stream_sid}")

    start_time = time.monotonic()

    serializer = ExotelFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        params=ExotelFrameSerializer.InputParams(
            exotel_sample_rate=config.SAMPLE_RATE,
            sample_rate=config.SAMPLE_RATE
        )
    )

    transport = FastAPIWebsocketTransport(
        websocket=websocket_client,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            vad_analyzer=SileroVADAnalyzer() if config.VAD_ENABLED else None,
            serializer=serializer,
        ),
    )

    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        model=config.OPENAI_MODEL
    )

    stt = DeepgramSTTService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        model=config.STT_MODEL,
        language=config.STT_LANGUAGE,
        sample_rate=config.SAMPLE_RATE
    )

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id=config.TTS_VOICE_ID,
        model_id=config.TTS_MODEL,
        sample_rate=config.SAMPLE_RATE,
        encoding="pcm_s16le"
    )

    messages = [
        {
            "role": "system",
            "content": config.SYSTEM_PROMPT,
        },
    ]

    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    pipeline = Pipeline([
        transport.input(),
        stt,
        context_aggregator.user(),
        llm,
        tts,
        transport.output(),
        context_aggregator.assistant(),
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=config.SAMPLE_RATE,
            audio_out_sample_rate=config.SAMPLE_RATE,
            allow_interruptions=config.ENABLE_INTERRUPTIONS,
            enable_metrics=config.ENABLE_METRICS,
            enable_usage_metrics=config.ENABLE_USAGE_METRICS,
        ),
    )

    # Pre-warm TTS (ignore if it fails)
    try:
        # Note: synthesize method might not exist in some versions
        if hasattr(tts, 'synthesize'):
            await tts.synthesize("...")
        logger.info(f"⏱️ TTS warm-up done in {time.monotonic() - start_time:.2f}s")
    except Exception as e:
        logger.warning(f"⚠️ TTS warm-up failed: {e}")

    # Queue greeting before pipeline starts
    await task.queue_frame(TextFrame(config.GREETING_MESSAGE))

    runner = PipelineRunner()

    try:
        await runner.run(task)
    except Exception as e:
        logger.error(f"❌ Error running pipeline for call {call_sid}: {e}")
        raise
    finally:
        logger.info(f"🏁 Exotel bot finished for call {call_sid}")


# Simple function to initiate outbound calls
def initiate_outbound_call(customer_number: str, custom_field: Optional[str] = None) -> dict:
    """
    Simple function to make outbound calls using existing call flow
    """
    return make_outbound_call_to_existing_flow(customer_number, custom_field)