-- Відображуване ім'я користувача (бачать інші учасники планів).
-- NULL означає "використовувати ім'я з Telegram (first_name)".
-- Безпечно запускати повторно.
ALTER TABLE auth.users
    ADD COLUMN IF NOT EXISTS display_name VARCHAR(64);
