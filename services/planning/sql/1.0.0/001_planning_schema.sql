-- Схема planning: навчальні плани, сесії, події, учасники та запрошення.
-- Потребує схему auth (таблиця auth.users).

BEGIN;

CREATE SCHEMA planning;

CREATE TYPE planning.plan_role     AS ENUM ('viewer', 'commenter');
CREATE TYPE planning.activity_type AS ENUM ('lecture', 'practice', 'reading', 'self_study', 'exam_prep');
CREATE TYPE planning.event_type    AS ENUM ('exam', 'test', 'deadline', 'other');

CREATE FUNCTION planning.set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Навчальні плани (власник один, зберігається в самому плані)
CREATE TABLE planning.plans (
    plan_id     INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id    INT NOT NULL REFERENCES auth.users(user_id) ON DELETE CASCADE,
    title       VARCHAR(200) NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_plans_owner_id ON planning.plans(owner_id);

-- Навчальні сесії
CREATE TABLE planning.study_sessions (
    study_session_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id          INT NOT NULL REFERENCES planning.plans(plan_id) ON DELETE CASCADE,
    title            VARCHAR(200) NOT NULL,
    activity_type    planning.activity_type NOT NULL,
    start_time       TIMESTAMPTZ NOT NULL,
    duration_minutes INT NOT NULL CHECK (duration_minutes > 0 AND duration_minutes <= 1440),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_study_sessions_plan_start ON planning.study_sessions(plan_id, start_time);

-- Події (іспити, контрольні, дедлайни)
CREATE TABLE planning.events (
    event_id    INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id     INT NOT NULL REFERENCES planning.plans(plan_id) ON DELETE CASCADE,
    title       VARCHAR(200) NOT NULL,
    event_type  planning.event_type NOT NULL,
    event_date  DATE NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_events_plan_date ON planning.events(plan_id, event_date);

-- Учасники плану (крім власника)
CREATE TABLE planning.plan_members (
    plan_member_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id        INT NOT NULL REFERENCES planning.plans(plan_id) ON DELETE CASCADE,
    user_id        INT NOT NULL REFERENCES auth.users(user_id) ON DELETE CASCADE,
    role           planning.plan_role NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (plan_id, user_id)
);
CREATE INDEX idx_plan_members_user_id ON planning.plan_members(user_id);

-- Запрошення до плану
CREATE TABLE planning.plan_invites (
    plan_invite_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id        INT NOT NULL REFERENCES planning.plans(plan_id) ON DELETE CASCADE,
    role           planning.plan_role NOT NULL,
    token          TEXT NOT NULL UNIQUE,
    created_by     INT NOT NULL REFERENCES auth.users(user_id) ON DELETE CASCADE,
    used_by        INT REFERENCES auth.users(user_id) ON DELETE SET NULL,
    expires_at     TIMESTAMPTZ NOT NULL,
    used_at        TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_plan_invites_plan_id    ON planning.plan_invites(plan_id);
CREATE INDEX idx_plan_invites_created_by ON planning.plan_invites(created_by);
CREATE INDEX idx_plan_invites_used_by    ON planning.plan_invites(used_by);

-- Тригери updated_at
CREATE TRIGGER trg_plans_updated_at BEFORE UPDATE ON planning.plans
    FOR EACH ROW EXECUTE FUNCTION planning.set_updated_at();
CREATE TRIGGER trg_study_sessions_updated_at BEFORE UPDATE ON planning.study_sessions
    FOR EACH ROW EXECUTE FUNCTION planning.set_updated_at();
CREATE TRIGGER trg_events_updated_at BEFORE UPDATE ON planning.events
    FOR EACH ROW EXECUTE FUNCTION planning.set_updated_at();

COMMIT;