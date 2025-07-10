import asyncio
import json
import os
import sys
import uvicorn
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from loguru import logger
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware

from bot import run_bot, initiate_outbound_call
import config

load_dotenv(override=True)

# Setup logger
try:
    logger.remove(0)
except ValueError:
    pass
logger.add(sys.stderr, level=config.LOG_LEVEL)

app = FastAPI(title="Exotel Voice AI Bot - Simple Outbound")

# Add CORS middleware - ADD THIS RIGHT AFTER THE APP CREATION
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class OutboundCallRequest(BaseModel):
    customer_number: str
    custom_field: Optional[str] = None

@app.websocket("/")
async def websocket_endpoint(websocket: WebSocket):
    """Your existing WebSocket endpoint - no changes needed"""
    await websocket.accept()
    logger.info("🔌 Exotel WebSocket connection accepted")

    try:
        while True:
            message = await websocket.receive_text()

            try:
                data = json.loads(message)
                event = data.get("event")
                logger.debug(f"📨 Received Exotel event: {event}")

                if event == "start":
                    start_info = data.get("start", {})
                    stream_sid = data.get("stream_sid")
                    call_sid = start_info.get("call_sid")

                    if stream_sid and call_sid:
                        logger.info(f"📞 Exotel call started - Stream: {stream_sid}, Call: {call_sid}")
                        logger.info(f"🚀 Launching Pipecat bot")
                        await run_bot(websocket, stream_sid, call_sid)
                        logger.info(f"🏁 Pipecat bot finished for Exotel call")
                    else:
                        logger.error("❌ Missing stream_sid or call_sid in start event")
                    break

                elif event == "stop":
                    reason = data.get("stop", {}).get("reason", "unknown")
                    logger.info(f"📞 Exotel call ended: {reason}")
                    break

                elif event == "dtmf":
                    digit = data.get("dtmf", {}).get("digit")
                    logger.info(f"📲 DTMF received: {digit}")

            except json.JSONDecodeError as e:
                logger.error(f"❌ Invalid JSON from Exotel: {e}")
            except Exception as e:
                logger.error(f"❌ Error processing message: {e}")

    except Exception as e:
        logger.error(f"❌ WebSocket error: {e}")
    finally:
        logger.info("🧹 WebSocket connection closed")


@app.post("/outbound/call")
async def make_outbound_call(request: OutboundCallRequest):
    """
    Make outbound call using your EXISTING call flow
    No additional coding needed - same experience as inbound calls
    """
    try:
        if config.REQUIRE_E164_FORMAT and not request.customer_number.startswith('+'):
            raise HTTPException(
                status_code=400, 
                detail="Phone number must be in E.164 format (starting with +)"
            )
        
        # Country code validation
        if config.ALLOWED_COUNTRY_CODES:
            valid_country = any(
                request.customer_number.startswith(code) 
                for code in config.ALLOWED_COUNTRY_CODES
            )
            if not valid_country:
                raise HTTPException(
                    status_code=400,
                    detail=f"Phone number must start with one of: {', '.join(config.ALLOWED_COUNTRY_CODES)}"
                )
        
        logger.info(f"🎯 Making outbound call using EXISTING call flow")
        logger.info(f"📞 Customer: {request.customer_number}")
        
        result = initiate_outbound_call(
            customer_number=request.customer_number,
            custom_field=request.custom_field or config.DEFAULT_CUSTOM_FIELD
        )
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Outbound call initiated using existing call flow",
                "customer_number": request.customer_number,
                "custom_field": request.custom_field or config.DEFAULT_CUSTOM_FIELD,
                "flow_type": "existing_voice_app",
                "result": result
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to make outbound call: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    return JSONResponse(
        status_code=200, 
        content={
            "status": "healthy",
            "service": "Exotel Voice AI Bot",
            "outbound_type": "existing_call_flow",
            "manual_coding": "not_required"
        }
    )


@app.get("/")
async def root():
    return JSONResponse(
        content={
            "service": "Exotel Voice AI Bot - Simple Outbound",
            "approach": "Uses your existing call flow - no manual coding needed",
            "how_it_works": [
                "1. You make API call to /outbound/call",
                "2. Exotel calls the customer",
                "3. Customer connects to your EXISTING voice app",
                "4. Same experience as inbound calls"
            ],
            "endpoints": {
                "outbound_call": "POST /outbound/call",
                "health": "GET /health"
            },
            "example": {
                "url": "POST /outbound/call",
                "payload": {
                    "customer_number": "+91XXXXXXXXXX",
                    "custom_field": "customer_support"
                }
            }
        }
    )


async def main():
    required_keys = config.REQUIRED_ENV_VARS
    
    missing = [k for k in required_keys if not os.getenv(k)]
    if missing:
        logger.error(f"❌ Missing env vars: {', '.join(missing)}")
        logger.info("\nTo get EXOTEL_APP_ID:")
        logger.info("1. Go to Exotel Dashboard → Apps/Flows")
        logger.info("2. Find your existing voice app")
        logger.info("3. Copy the App ID (usually a number)")
        return

    host = config.DEFAULT_HOST
    port = int(os.getenv("PORT", config.DEFAULT_PORT))
    
    logger.info(f"📡 Starting server on: {host}:{port}")
    logger.info(f"🎯 Using EXISTING call flow approach")
    logger.info(f"📞 Outbound endpoint: POST http://{host}:{port}/outbound/call")

    config_obj = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config_obj)

    try:
        await server.serve()
    except KeyboardInterrupt:
        logger.info("🛑 Server stopped")


if __name__ == "__main__":
    asyncio.run(main())