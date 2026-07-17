import uvicorn
import logging
logging.basicConfig(level=logging.INFO)
print("Starting OmniAide backend on http://0.0.0.0:8000")
uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
