"""
BeeFit FastAPI Backend - Production Ready
AI-powered personalized fitness app with Supabase integration
"""

import os
import json
from datetime import datetime, timedelta, UTC
from typing import List, Optional, Dict, Any
from functools import lru_cache

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
import anthropic
from passlib.context import CryptContext
from jose import JWTError, jwt
from dotenv import load_dotenv
from supabase import create_client, Client
import pandas as pd

from prompts import SYSTEM_PROMPT, build_user_context, parse_ai_response

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-this")
ALGORITHM = "HS256"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

app = FastAPI(
    title="BeeFit API",
    description="AI-powered personalized fitness backend",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    display_name: str = Field(..., min_length=1)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    display_name: str

class UserProfile(BaseModel):
    display_name: str
    age: Optional[int] = None
    body_weight_kg: Optional[float] = None
    experience_level: str = "intermediate"
    training_focus: str = "strength"

class CheckinRequest(BaseModel):
    sleep_quality: int = Field(..., ge=1, le=10)
    fatigue_level: int = Field(..., ge=1, le=10)
    mood_readiness: int = Field(..., ge=1, le=10)
    muscle_soreness: Optional[Dict[str, int]] = None
    notes: Optional[str] = None

class CheckinResponse(BaseModel):
    id: str
    user_id: str
    date: str
    sleep_quality: int
    fatigue_level: int
    mood_readiness: int
    muscle_soreness: Optional[Dict[str, int]]
    readiness_score: float
    notes: Optional[str]

class WorkoutExerciseSetLog(BaseModel):
    exercise_id: str
    set_number: int
    actual_reps: int
    actual_weight_kg: float
    rpe: int = Field(..., ge=1, le=10)

class WorkoutExerciseRequest(BaseModel):
    exercise_name: str
    planned_sets: int
    planned_reps: str
    planned_weight_kg: float
    rest_sec: int = 90
    rpe_target: int = 7
    notes: Optional[str] = None

class WorkoutSessionRequest(BaseModel):
    date: str
    training_focus: str
    exercises: List[WorkoutExerciseRequest]

class WorkoutSessionResponse(BaseModel):
    id: str
    user_id: str
    date: str
    status: str
    training_focus: str
    duration_min: Optional[int]
    ai_reasoning: Optional[str]
    total_volume_kg: float

class GoalRequest(BaseModel):
    goal_description: str
    target: str
    active: bool = True


def compute_readiness(checkin: Dict[str, Any]) -> float:
    soreness = checkin.get('muscle_soreness', {})
    avg_soreness = sum(soreness.values()) / max(len(soreness), 1) if soreness else 0
    score = (
        checkin['sleep_quality'] * 0.30 +
        (10 - checkin['fatigue_level']) * 0.25 +
        checkin['mood_readiness'] * 0.25 +
        (10 - avg_soreness) * 0.20
    ) * 10
    return round(min(max(score, 0), 100), 1)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(days=30)
    to_encode = {"sub": user_id, "exp": expire}
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.post("/auth/register", response_model=AuthResponse)
async def register(req: RegisterRequest):
    try:
        auth_response = supabase.auth.sign_up({"email": req.email, "password": req.password})
        user_id = auth_response.user.id
        supabase.table("users").insert({
            "id": user_id, "email": req.email, "display_name": req.display_name,
            "experience_level": "intermediate", "training_focus": "strength",
            "created_at": datetime.utcnow().isoformat(),
        }).execute()
        token = create_access_token(user_id)
        return AuthResponse(access_token=token, token_type="bearer", user_id=user_id, display_name=req.display_name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Registration failed: {str(e)}")

@app.post("/auth/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    try:
        auth_response = supabase.auth.sign_in_with_password({"email": req.email, "password": req.password})
        user_id = auth_response.user.id
        user_data = supabase.table("users").select("*").eq("id", user_id).single().execute()
        token = create_access_token(user_id)
        return AuthResponse(access_token=token, token_type="bearer", user_id=user_id, display_name=user_data.data['display_name'])
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/users/me")
async def get_current_user_profile(user_id: str = Depends(get_current_user)):
    try:
        user_data = supabase.table("users").select("*").eq("id", user_id).single().execute()
        return user_data.data
    except Exception as e:
        raise HTTPException(status_code=404, detail="User not found")


@app.post("/checkins", response_model=CheckinResponse)
async def create_checkin(req: CheckinRequest, user_id: str = Depends(get_current_user)):
    try:
        today = datetime.now(UTC).date().isoformat()
        existing = supabase.table("daily_checkins").select("id").eq("user_id", user_id).eq("date", today).execute()
        checkin_data = {
            "user_id": user_id, "date": today, "sleep_quality": req.sleep_quality,
            "fatigue_level": req.fatigue_level, "mood_readiness": req.mood_readiness,
            "muscle_soreness": req.muscle_soreness or {}, "notes": req.notes or "",
        }
        readiness_score = compute_readiness(checkin_data)
        checkin_data["readiness_score"] = readiness_score
        if existing.data and len(existing.data) > 0:
            supabase.table("daily_checkins").update(checkin_data).eq("id", existing.data[0]['id']).execute()
            checkin_id = existing.data[0]['id']
        else:
            result = supabase.table("daily_checkins").insert(checkin_data).execute()
            checkin_id = result.data[0]['id']
        return CheckinResponse(id=checkin_id, user_id=user_id, date=today, sleep_quality=req.sleep_quality,
            fatigue_level=req.fatigue_level, mood_readiness=req.mood_readiness,
            muscle_soreness=req.muscle_soreness or {}, readiness_score=readiness_score, notes=req.notes or "")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Checkin failed: {str(e)}")

@app.get("/checkins/today", response_model=Optional[CheckinResponse])
async def get_today_checkin(user_id: str = Depends(get_current_user)):
    try:
        today = datetime.now(UTC).date().isoformat()
        result = supabase.table("daily_checkins").select("*").eq("user_id", user_id).eq("date", today).execute()
        if result.data and len(result.data) > 0:
            c = result.data[0]
            return CheckinResponse(id=c['id'], user_id=c['user_id'], date=c['date'],
                sleep_quality=c['sleep_quality'], fatigue_level=c['fatigue_level'],
                mood_readiness=c['mood_readiness'], muscle_soreness=c.get('muscle_soreness', {}),
                readiness_score=c['readiness_score'], notes=c.get('notes', ''))
        return None
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch checkin: {str(e)}")

@app.get("/checkins/history")
async def get_checkin_history(limit: int = 30, user_id: str = Depends(get_current_user)):
    try:
        result = supabase.table("daily_checkins").select("*").eq("user_id", user_id).order("date", desc=True).limit(limit).execute()
        return result.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch history: {str(e)}")


@app.post("/workouts/generate")
async def generate_workout(user_id: str = Depends(get_current_user)):
    try:
        user_resp = supabase.table("users").select("*").eq("id", user_id).single().execute()
        user_profile = user_resp.data
        today = datetime.now(UTC).date().isoformat()
        checkin_resp = supabase.table("daily_checkins").select("*").eq("user_id", user_id).eq("date", today).execute()
        checkin = checkin_resp.data[0] if checkin_resp.data else None
        sessions_resp = supabase.table("workout_sessions").select("*, workout_exercises(*, exercises(*))").eq("user_id", user_id).order("date", desc=True).limit(5).execute()
        recent_sessions = []
        for session in sessions_resp.data:
            exercises_list = [{'exercise_name': we.get('exercises', {}).get('name', 'Unknown'), 'actual_weight_kg': we.get('actual_weight_kg', 0), 'actual_reps': we.get('actual_reps', 0), 'actual_rpe': we.get('actual_rpe', 7)} for we in session.get('workout_exercises', [])]
            recent_sessions.append({'date': session['date'], 'training_focus': session.get('training_focus', ''), 'duration_min': session.get('duration_min'), 'total_volume_kg': session.get('total_volume_kg', 0), 'exercises': exercises_list})
        goals_resp = supabase.table("user_goals").select("*").eq("user_id", user_id).eq("active", True).execute()
        goals = goals_resp.data or []
        profiles_resp = supabase.table("user_exercise_profiles").select("*").eq("user_id", user_id).execute()
        exercise_profiles = {p['exercise_id']: {'estimated_1rm': p.get('estimated_1rm'), 'trend': p.get('trend', 'stable'), 'recent_avg_rpe': p.get('recent_avg_rpe', 7)} for p in profiles_resp.data or []}
        context_json = build_user_context(user_profile=user_profile, checkin=checkin, recent_sessions=recent_sessions, goals=goals, exercise_profiles=exercise_profiles)
        response = anthropic_client.messages.create(model="claude-sonnet-4-6", max_tokens=4096, system=SYSTEM_PROMPT, messages=[{"role": "user", "content": context_json}])
        response_text = response.content[0].text
        workout_data = parse_ai_response(response_text)
        session_data = {"user_id": user_id, "date": today, "status": "scheduled", "training_focus": workout_data['workout']['training_focus'], "duration_min": workout_data['workout']['estimated_duration_min'], "ai_reasoning": workout_data.get('reasoning', ''), "readiness_score": checkin['readiness_score'] if checkin else 50}
        session_result = supabase.table("workout_sessions").insert(session_data).execute()
        session_id = session_result.data[0]['id']
        for block in workout_data['workout']['blocks']:
            for exercise in block['exercises']:
                exc_resp = supabase.table("exercises").select("id").eq("name", exercise['exercise_name']).execute()
                if exc_resp.data and len(exc_resp.data) > 0:
                    exercise_id = exc_resp.data[0]['id']
                else:
                    exc_create = supabase.table("exercises").insert({"name": exercise['exercise_name'], "category": "other", "muscles": []}).execute()
                    exercise_id = exc_create.data[0]['id']
                supabase.table("workout_exercises").insert({"session_id": session_id, "exercise_id": exercise_id, "planned_sets": exercise['sets'], "planned_reps": str(exercise['reps']), "planned_weight_kg": exercise['weight_kg'], "rest_sec": exercise.get('rest_sec', 90), "rpe_target": exercise.get('rpe_target', 7), "notes": exercise.get('notes', '')}).execute()
        return {"session_id": session_id, "date": today, "training_focus": workout_data['workout']['training_focus'], "duration_min": workout_data['workout']['estimated_duration_min'], "session_name": workout_data['workout']['session_name'], "readiness_score": checkin['readiness_score'] if checkin else 50, "readiness_assessment": workout_data.get('readiness_assessment', ''), "workout": workout_data['workout']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workout generation failed: {str(e)}")


@app.get("/workouts/today")
async def get_today_workout(user_id: str = Depends(get_current_user)):
    try:
        today = datetime.now(UTC).date().isoformat()
        result = supabase.table("workout_sessions").select("*, workout_exercises(*, exercises(*))").eq("user_id", user_id).eq("date", today).execute()
        if result.data and len(result.data) > 0:
            return result.data[0]
        return None
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch workout: {str(e)}")

@app.get("/workouts/{workout_id}")
async def get_workout(workout_id: str, user_id: str = Depends(get_current_user)):
    try:
        result = supabase.table("workout_sessions").select("*, workout_exercises(*, exercises(*))").eq("id", workout_id).eq("user_id", user_id).single().execute()
        return result.data
    except Exception as e:
        raise HTTPException(status_code=404, detail="Workout not found")

@app.post("/workouts/{workout_id}/log-set")
async def log_set(workout_id: str, set_log: WorkoutExerciseSetLog, user_id: str = Depends(get_current_user)):
    try:
        supabase.table("workout_sessions").select("id").eq("id", workout_id).eq("user_id", user_id).single().execute()
        result = supabase.table("exercise_sets").insert({"exercise_id": set_log.exercise_id, "set_number": set_log.set_number, "actual_reps": set_log.actual_reps, "actual_weight_kg": set_log.actual_weight_kg, "actual_rpe": set_log.rpe, "logged_at": datetime.utcnow().isoformat()}).execute()
        return {"status": "logged", "set_id": result.data[0]['id']}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to log set: {str(e)}")

@app.put("/workouts/{workout_id}/complete")
async def complete_workout(workout_id: str, user_id: str = Depends(get_current_user)):
    try:
        exercises_resp = supabase.table("workout_exercises").select("*, exercise_sets(*)").eq("session_id", workout_id).execute()
        total_volume = sum(s['actual_weight_kg'] * s['actual_reps'] for we in exercises_resp.data for s in we.get('exercise_sets', []))
        supabase.table("workout_sessions").update({"status": "completed", "total_volume_kg": total_volume, "completed_at": datetime.utcnow().isoformat()}).eq("id", workout_id).eq("user_id", user_id).execute()
        return {"status": "completed", "total_volume_kg": total_volume}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to complete workout: {str(e)}")

@app.get("/analytics/exercise/{exercise_id}")
async def get_exercise_analytics(exercise_id: str, user_id: str = Depends(get_current_user)):
    try:
        profile = supabase.table("user_exercise_profiles").select("*").eq("user_id", user_id).eq("exercise_id", exercise_id).single().execute()
        return profile.data
    except Exception as e:
        raise HTTPException(status_code=404, detail="No data for this exercise")

@app.get("/analytics/personal-records")
async def get_personal_records(user_id: str = Depends(get_current_user)):
    try:
        result = supabase.table("user_exercise_profiles").select("*").eq("user_id", user_id).order("estimated_1rm", desc=True).execute()
        return result.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch PRs: {str(e)}")

@app.post("/goals")
async def create_goal(goal: GoalRequest, user_id: str = Depends(get_current_user)):
    try:
        result = supabase.table("user_goals").insert({"user_id": user_id, "goal_description": goal.goal_description, "target": goal.target, "active": goal.active, "created_at": datetime.utcnow().isoformat()}).execute()
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create goal: {str(e)}")

@app.get("/goals")
async def get_goals(user_id: str = Depends(get_current_user)):
    try:
        result = supabase.table("user_goals").select("*").eq("user_id", user_id).execute()
        return result.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch goals: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
