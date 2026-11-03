-- Ідемпотентний: безпечно запускати повторно. Якщо auth.users уже є, нічого не змінює,
-- лише гарантує UNIQUE(telegram_id) (потрібен для ON CONFLICT у коді).
CREATE SCHEMA IF NOT EXISTS auth;

CREATE TABLE IF NOT EXISTS auth.users (
    user_id       INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    telegram_id   BIGINT       NOT NULL,
    first_name    VARCHAR(64)  NOT NULL DEFAULT '',
    username      VARCHAR(64),
    language_code VARCHAR(10)  NOT NULL DEFAULT 'uk',
    timezone      VARCHAR(64)  NOT NULL DEFAULT 'Europe/Kyiv',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS users_telegram_id_key ON auth.users (telegram_id);
