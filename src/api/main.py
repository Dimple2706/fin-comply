from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import router
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    from src.governance.audit_logger import (
      log_event, APP_STARTUP, MODEL_LOADED, 
      MODEL_LOAD_FAILED
    )
    
    startup_status = {}
    
    # Verify XGBoost model loaded
    try:
      from src.modeling.ml_layer import _MODEL, _FEATURE_NAMES
      if _MODEL is not None:
        log_event(MODEL_LOADED, 
                  details={'model': 'xgboost', 
                           'features': len(_FEATURE_NAMES)})
        startup_status['xgboost'] = 'loaded'
      else:
        log_event(MODEL_LOAD_FAILED,
                  details={'model': 'xgboost', 
                           'reason': 'model is None'})
        startup_status['xgboost'] = 'failed'
    except Exception as e:
      log_event(MODEL_LOAD_FAILED,
                details={'model': 'xgboost', 'error': str(e)})
      startup_status['xgboost'] = 'failed'
    
    # Verify sentence-transformer loaded
    try:
      from src.intelligence.regulation_mapper import (
        _MODEL as _ST_MODEL
      )
      if _ST_MODEL is not None:
        log_event(MODEL_LOADED,
                  details={'model': 'sentence-transformer',
                           'name': 'all-MiniLM-L6-v2'})
        startup_status['sentence_transformer'] = 'loaded'
      else:
        log_event(MODEL_LOAD_FAILED,
                  details={'model': 'sentence-transformer',
                           'reason': 'model is None'})
        startup_status['sentence_transformer'] = 'failed'
    except Exception as e:
      log_event(MODEL_LOAD_FAILED,
                details={'model': 'sentence-transformer', 
                         'error': str(e)})
      startup_status['sentence_transformer'] = 'failed'
    
    log_event(APP_STARTUP, 
              details={'status': startup_status,
                       'routes': 4})
    
    print(f"Fin-Comply started. Models: {startup_status}")
    
    yield
    # SHUTDOWN (nothing needed)

app = FastAPI(
    title="Fin-Comply",
    description="AI-Powered DPDP Compliance & Regulatory Intelligence Engine",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", 
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

from src.api.auth_routes import auth_router

app.include_router(router)
app.include_router(auth_router)