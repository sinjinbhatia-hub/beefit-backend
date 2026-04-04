-- BeeFit PostgreSQL Schema for Supabase
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email text UNIQUE NOT NULL,
    display_name text NOT NULL,
    age integer,
    body_weight_kg decimal(6, 2),
    experience_level text CHECK (experience_level IN ('beginner', 'intermediate', 'advanced')) DEFAULT 'intermediate',
    training_focus text DEFAULT 'strength',
    injuries_or_limitations text[] DEFAULT ARRAY[]::text[],
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view their own profile" ON users FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update their own profile" ON users FOR UPDATE USING (auth.uid() = id);

CREATE TABLE IF NOT EXISTS exercises (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    name text UNIQUE NOT NULL,
    canonical_name text,
    category text CHECK (category IN ('compound', 'isolation', 'cardio', 'mobility', 'other')),
    muscles text[] DEFAULT ARRAY[]::text[],
    image_description text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE exercises ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Everyone can view exercises" ON exercises FOR SELECT USING (true);

CREATE TABLE IF NOT EXISTS daily_checkins (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date date NOT NULL,
    sleep_quality integer CHECK (sleep_quality >= 1 AND sleep_quality <= 10),
    fatigue_level integer CHECK (fatigue_level >= 1 AND fatigue_level <= 10),
    mood_readiness integer CHECK (mood_readiness >= 1 AND mood_readiness <= 10),
    muscle_soreness jsonb DEFAULT '{}',
    readiness_score decimal(5, 1) DEFAULT 50.0,
    notes text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, date)
);
ALTER TABLE daily_checkins ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view their own checkins" ON daily_checkins FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert their own checkins" ON daily_checkins FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update their own checkins" ON daily_checkins FOR UPDATE USING (auth.uid() = user_id);

CREATE TABLE IF NOT EXISTS workout_sessions (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date date NOT NULL,
    status text CHECK (status IN ('scheduled', 'in_progress', 'completed', 'skipped')) DEFAULT 'scheduled',
    training_focus text,
    duration_min integer,
    total_volume_kg decimal(12, 2) DEFAULT 0,
    ai_reasoning text,
    readiness_score decimal(5, 1),
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE workout_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view their own workouts" ON workout_sessions FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert their own workouts" ON workout_sessions FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update their own workouts" ON workout_sessions FOR UPDATE USING (auth.uid() = user_id);

CREATE TABLE IF NOT EXISTS workout_exercises (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id uuid NOT NULL REFERENCES workout_sessions(id) ON DELETE CASCADE,
    exercise_id uuid NOT NULL REFERENCES exercises(id),
    planned_sets integer NOT NULL,
    planned_reps text,
    planned_weight_kg decimal(8, 2),
    rest_sec integer DEFAULT 90,
    rpe_target integer CHECK (rpe_target >= 1 AND rpe_target <= 10),
    actual_sets integer,
    actual_reps integer,
    actual_weight_kg decimal(8, 2),
    actual_rpe integer CHECK (actual_rpe >= 1 AND actual_rpe <= 10),
    notes text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE workout_exercises ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view their own workout exercises" ON workout_exercises FOR SELECT USING (EXISTS (SELECT 1 FROM workout_sessions WHERE workout_sessions.id = workout_exercises.session_id AND workout_sessions.user_id = auth.uid()));
CREATE POLICY "Users can insert their own workout exercises" ON workout_exercises FOR INSERT WITH CHECK (EXISTS (SELECT 1 FROM workout_sessions WHERE workout_sessions.id = session_id AND workout_sessions.user_id = auth.uid()));
CREATE POLICY "Users can update their own workout exercises" ON workout_exercises FOR UPDATE USING (EXISTS (SELECT 1 FROM workout_sessions WHERE workout_sessions.id = workout_exercises.session_id AND workout_sessions.user_id = auth.uid()));

CREATE TABLE IF NOT EXISTS exercise_sets (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    exercise_id uuid NOT NULL REFERENCES exercises(id),
    set_number integer NOT NULL,
    actual_reps integer NOT NULL,
    actual_weight_kg decimal(8, 2) NOT NULL,
    actual_rpe integer CHECK (actual_rpe >= 1 AND actual_rpe <= 10),
    logged_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE exercise_sets ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view exercise sets" ON exercise_sets FOR SELECT USING (true);

CREATE TABLE IF NOT EXISTS user_exercise_profiles (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exercise_id uuid NOT NULL REFERENCES exercises(id),
    estimated_1rm decimal(8, 2),
    recent_avg_rpe decimal(5, 1) DEFAULT 7.0,
    trend text CHECK (trend IN ('increasing', 'stable', 'decreasing')) DEFAULT 'stable',
    plateau_detected boolean DEFAULT false,
    last_updated timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, exercise_id)
);
ALTER TABLE user_exercise_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view their own exercise profiles" ON user_exercise_profiles FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can update their own exercise profiles" ON user_exercise_profiles FOR UPDATE USING (auth.uid() = user_id);

CREATE TABLE IF NOT EXISTS user_goals (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal_description text NOT NULL,
    target text NOT NULL,
    active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE user_goals ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view their own goals" ON user_goals FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert their own goals" ON user_goals FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update their own goals" ON user_goals FOR UPDATE USING (auth.uid() = user_id);

-- Indexes
CREATE INDEX idx_daily_checkins_user_date ON daily_checkins(user_id, date DESC);
CREATE INDEX idx_workout_sessions_user_date ON workout_sessions(user_id, date DESC);
CREATE INDEX idx_workout_exercises_session ON workout_exercises(session_id);
CREATE INDEX idx_user_exercise_profiles_user ON user_exercise_profiles(user_id);
CREATE INDEX idx_user_goals_user ON user_goals(user_id);

-- Seed exercises
INSERT INTO exercises (name, canonical_name, category, muscles, image_description) VALUES
('Barbell Back Squat', 'back_squat', 'compound', ARRAY['quads', 'glutes', 'hamstrings', 'core'], 'Stand with barbell across upper back, lower until thighs parallel, drive through heels.'),
('Barbell Bench Press', 'bench_press', 'compound', ARRAY['chest', 'shoulders', 'triceps'], 'Lie on bench, lower barbell to chest, press back up.'),
('Deadlift', 'deadlift', 'compound', ARRAY['glutes', 'hamstrings', 'back', 'core'], 'Stand with barbell over mid-foot, drive through heels to lift to hip level.'),
('Barbell Romanian Deadlift', 'rdl', 'compound', ARRAY['hamstrings', 'glutes', 'back'], 'Hinge at hips with barbell, lower until hamstring stretch, drive hips forward.'),
('Barbell Overhead Press', 'ohp', 'compound', ARRAY['shoulders', 'triceps', 'chest'], 'Press barbell from shoulders to overhead, full arm extension.'),
('Barbell Rows', 'barbell_row', 'compound', ARRAY['back', 'lats', 'biceps'], 'Bend over, row barbell to chest pulling elbows back.'),
('Pull-ups', 'pullups', 'compound', ARRAY['back', 'lats', 'biceps'], 'Hang from bar, pull up until chin above bar.'),
('Dumbbell Bench Press', 'db_bench_press', 'compound', ARRAY['chest', 'shoulders', 'triceps'], 'Lie on bench with dumbbells, press up and squeeze chest.'),
('Dumbbell Rows', 'db_rows', 'compound', ARRAY['back', 'lats', 'biceps'], 'Single arm row with dumbbell on bench.'),
('Incline Dumbbell Press', 'incline_db_press', 'compound', ARRAY['chest', 'shoulders'], 'Incline bench press with dumbbells focusing on upper chest.'),
('Dumbbell Flyes', 'db_flyes', 'isolation', ARRAY['chest'], 'Lie on bench, arc dumbbells down and out in wide motion.'),
('Barbell Curls', 'barbell_curls', 'isolation', ARRAY['biceps'], 'Standing barbell curl to shoulders.'),
('Tricep Dips', 'tricep_dips', 'compound', ARRAY['triceps', 'chest'], 'Dip station, lower body bending elbows, press back up.'),
('Leg Press', 'leg_press', 'compound', ARRAY['quads', 'glutes', 'hamstrings'], 'Leg press machine, bend knees to 90 degrees then press.'),
('Leg Curl', 'leg_curl', 'isolation', ARRAY['hamstrings'], 'Lying leg curl machine.'),
('Leg Extension', 'leg_extension', 'isolation', ARRAY['quads'], 'Seated leg extension machine.'),
('Lateral Raises', 'lateral_raises', 'isolation', ARRAY['shoulders'], 'Standing dumbbell lateral raises to parallel.'),
('Face Pulls', 'face_pulls', 'isolation', ARRAY['shoulders', 'back'], 'Cable face pulls for rear delts.'),
('Chest Fly Machine', 'chest_fly_machine', 'isolation', ARRAY['chest'], 'Machine chest fly for isolation.'),
('Treadmill Sprint', 'treadmill_sprint', 'cardio', ARRAY['glutes', 'hamstrings', 'quads'], 'High intensity treadmill sprints.'),
('Rowing Machine', 'rowing_machine', 'cardio', ARRAY['back', 'legs', 'core'], 'Full body rowing intervals.'),
('Plank', 'plank', 'isolation', ARRAY['core'], 'Forearm plank hold.'),
('Ab Wheel Rollouts', 'ab_wheel', 'isolation', ARRAY['core'], 'Ab wheel extension and return.'),
('Kettlebell Swings', 'kb_swings', 'compound', ARRAY['glutes', 'hamstrings', 'core', 'shoulders'], 'Hip drive kettlebell swings.')
ON CONFLICT (name) DO NOTHING;

-- Triggers for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = CURRENT_TIMESTAMP; RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER daily_checkins_updated_at BEFORE UPDATE ON daily_checkins FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER workout_sessions_updated_at BEFORE UPDATE ON workout_sessions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER workout_exercises_updated_at BEFORE UPDATE ON workout_exercises FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER user_goals_updated_at BEFORE UPDATE ON user_goals FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
