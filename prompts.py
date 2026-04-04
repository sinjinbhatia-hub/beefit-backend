"""
AI prompt system for BeeFit workout generation.
Includes system prompt, context builder, and response parser.
"""

import json
from typing import Any, Dict, List, Optional
from datetime import datetime

SYSTEM_PROMPT = """You are an elite strength and conditioning coach with 15+ years of experience working with athletes at all levels. Your expertise spans periodization, progressive overload, recovery science, and individual biomechanics.

Your role is to generate personalized workout sessions that respect the user's readiness state, movement capacity, and training history.

CRITICAL RULES FOR WORKOUT GENERATION:

1. READINESS-BASED ADAPTATION:
   - Score 75-100: HIGH readiness. Apply progressive overload. Increase volume or intensity. Include complex movements.
   - Score 50-74: MODERATE readiness. Maintain current stimulus. Standard volume and intensity.
   - Score 0-49: LOW readiness. Pull back significantly. Reduce volume by 30-40%. Lower intensity. Focus on movement quality and recovery.

2. MUSCLE SORENESS CONSIDERATION:
   - If any muscle group shows soreness > 7/10, avoid heavy loading on that area.
   - Never prescribe heavy compound exercises that stress the highest-soreness areas.
   - Consider mobility/accessory work for sore regions.

3. PROGRESSIVE OVERLOAD PRINCIPLES:
   - When readiness allows, increase: reps first, then sets, then weight.
   - Track user's recent session data. Never exceed 10% weekly volume increase.
   - For individuals with low 1RM estimates, prioritize movement pattern mastery before heavy loading.

4. EXERCISE SELECTION STRATEGY:
   - Respect user's experience level (beginner, intermediate, advanced).
   - Avoid exercises not in their exercise profile or those they've never done.
   - Consider primary training focus (strength, hypertrophy, power, endurance, mobility).
   - Balance between compound (60-70%) and isolation (30-40%) movements.

5. STRUCTURE REQUIREMENTS:
   - Always include warm-up (5-10 min dynamic stretching/mobility).
   - Organize main work into logical blocks (e.g., Main Strength, Hypertrophy, Accessory).
   - Include cool-down (5-10 min static stretching/breathing).
   - Estimate total session duration realistically (15-120 min based on intensity and volume).

6. JSON OUTPUT VALIDATION:
   - Return VALID, parseable JSON only.
   - Must follow the exact schema provided.
   - Include all required fields: reasoning, readiness_assessment, workout.
   - RPE targets should be 4-10 scale.
   - Set counts typically 2-5, reps 3-20 based on goal.

7. PERSONALIZATION:
   - Reference user's goals explicitly.
   - Acknowledge their pain points and limitations.
   - Provide brief coaching notes explaining why certain exercises were chosen.
   - Be encouraging and motivational in tone.

Output ONLY the JSON object. No markdown, no explanations outside the JSON block."""


def build_user_context(user_profile: Dict[str, Any], checkin: Optional[Dict[str, Any]], recent_sessions: List[Dict[str, Any]], goals: List[Dict[str, Any]], exercise_profiles: Dict[str, Any]) -> str:
    readiness_score = checkin.get('readiness_score') if checkin else 50
    soreness_summary = checkin['muscle_soreness'] if checkin and checkin.get('muscle_soreness') else {}
    session_summaries = [{'date': s.get('date'), 'training_focus': s.get('training_focus'), 'duration_min': s.get('duration_min'), 'total_volume_kg': s.get('total_volume_kg', 0), 'exercises_count': len(s.get('exercises', []))} for s in recent_sessions[:5]]
    recent_exercises = {}
    for session in recent_sessions[:5]:
        for exc in session.get('exercises', []):
            exc_name = exc.get('exercise_name', 'Unknown')
            if exc_name not in recent_exercises:
                recent_exercises[exc_name] = {'last_weight_kg': exc.get('actual_weight_kg', 0), 'last_reps': exc.get('actual_reps', 0), 'avg_rpe': exc.get('actual_rpe', 7), 'recent_count': 0}
            recent_exercises[exc_name]['recent_count'] += 1
    context = {
        'timestamp': datetime.utcnow().isoformat(),
        'user_profile': {
            'age': user_profile.get('age'),
            'body_weight_kg': user_profile.get('body_weight_kg'),
            'experience_level': user_profile.get('experience_level', 'intermediate'),
            'training_focus': user_profile.get('training_focus', 'strength'),
            'injuries_or_limitations': user_profile.get('injuries_or_limitations', []),
        },
        'today_readiness': {
            'readiness_score': readiness_score,
            'sleep_quality': checkin.get('sleep_quality', 5) if checkin else 5,
            'fatigue_level': checkin.get('fatigue_level', 5) if checkin else 5,
            'mood_readiness': checkin.get('mood_readiness', 5) if checkin else 5,
            'muscle_soreness': soreness_summary,
            'notes': checkin.get('notes', '') if checkin else '',
        },
        'recent_sessions': session_summaries,
        'recent_exercises': recent_exercises,
        'active_goals': [{'goal_description': g.get('goal_description'), 'target': g.get('target')} for g in goals],
        'exercise_profiles': exercise_profiles,
    }
    return json.dumps(context, indent=2)


def parse_ai_response(response_text: str) -> Dict[str, Any]:
    text = response_text.strip()
    if '```json' in text:
        start = text.find('```json') + 7
        end = text.find('```', start)
        if end > start:
            text = text[start:end].strip()
    elif '```' in text:
        start = text.find('```') + 3
        end = text.find('```', start)
        if end > start:
            text = text[start:end].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON from Claude response: {e}")
    for field in ['reasoning', 'readiness_assessment', 'workout']:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")
    workout = data.get('workout', {})
    for field in ['session_name', 'estimated_duration_min', 'training_focus', 'blocks']:
        if field not in workout:
            raise ValueError(f"Missing required workout field: {field}")
    blocks = workout.get('blocks', [])
    if not isinstance(blocks, list) or len(blocks) == 0:
        raise ValueError("Workout must contain at least one block with exercises")
    for block in blocks:
        if 'exercises' not in block or not isinstance(block['exercises'], list):
            raise ValueError("Each block must have an 'exercises' list")
        if len(block['exercises']) == 0:
            raise ValueError("Each block must contain at least one exercise")
    return data
