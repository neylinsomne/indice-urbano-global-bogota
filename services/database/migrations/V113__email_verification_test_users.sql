-- =============================================================
-- V113: Email verification + Test users
-- =============================================================

-- 1. Add email_verified column (default FALSE for new registrations)
ALTER TABLE iug.users
    ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE;

-- 2. Mark existing users as verified (admin and any others created before this)
UPDATE iug.users SET email_verified = TRUE;

-- 3. Hardcoded test user - FREE plan
--    Credentials: free_test@inmu.co / test123Free
INSERT INTO iug.users (email, username, password_hash, role, daily_pdf_limit, is_active, email_verified)
VALUES (
    'free_test@inmu.co',
    'free_test',
    '$2b$12$9Ts9mA1sjo61BSzHhaLYNeJGa3p5cFtt/Iy0SARH5QPq3d59Ez3Ni',
    'free',
    2,
    TRUE,
    TRUE
) ON CONFLICT (email) DO NOTHING;

-- 4. Hardcoded test user - PREMIUM plan
--    Credentials: premium_test@inmu.co / test123Premium
INSERT INTO iug.users (email, username, password_hash, role, daily_pdf_limit, is_active, email_verified)
VALUES (
    'premium_test@inmu.co',
    'premium_test',
    '$2b$12$b7NKJq/eazOilI2l04tjuOX4u0KUpUQWUMLj9vFVtX.uKKSvnHVx.',
    'premium',
    20,
    TRUE,
    TRUE
) ON CONFLICT (email) DO NOTHING;
