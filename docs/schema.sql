-- ===========================================================================
-- KLS Academy — full database schema
--
-- GENERATED FILE. Produced by `alembic upgrade head --sql`.
-- Do not edit by hand: change the SQLAlchemy models and regenerate, or the
-- database and the application will disagree about what the tables look like.
--
-- The supported way to create these tables is:
--     alembic upgrade head
--
-- This file exists as a fallback for running the DDL manually in pgAdmin.
-- It includes the alembic_version row, so Alembic will still consider the
-- database up to date afterwards.
--
BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 87f2faee7f16

CREATE TABLE email_templates (
    template_name VARCHAR(80) NOT NULL, 
    subject VARCHAR(255) NOT NULL, 
    body TEXT NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_email_templates_template_name ON email_templates (template_name);

CREATE TABLE internship_domains (
    slug VARCHAR(80) NOT NULL, 
    title VARCHAR(150) NOT NULL, 
    description TEXT NOT NULL, 
    duration VARCHAR(40) NOT NULL, 
    difficulty VARCHAR(12) NOT NULL, 
    status VARCHAR(8) NOT NULL, 
    icon VARCHAR(40) NOT NULL, 
    outcomes JSON NOT NULL, 
    skills JSON NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_internship_domains_slug ON internship_domains (slug);

CREATE TABLE users (
    full_name VARCHAR(100) NOT NULL, 
    email VARCHAR(255) NOT NULL, 
    phone VARCHAR(20) NOT NULL, 
    password_hash VARCHAR(255) NOT NULL, 
    role VARCHAR(11) NOT NULL, 
    status VARCHAR(9) NOT NULL, 
    email_verified BOOLEAN NOT NULL, 
    last_login_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE TABLE activity_logs (
    user_id UUID, 
    activity VARCHAR(255) NOT NULL, 
    module VARCHAR(50) NOT NULL, 
    entity_id VARCHAR(50), 
    ip_address VARCHAR(45), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_activity_logs_module ON activity_logs (module);

CREATE INDEX ix_activity_logs_user_id ON activity_logs (user_id);

CREATE TABLE admin_profiles (
    user_id UUID NOT NULL, 
    designation VARCHAR(100), 
    permissions VARCHAR(500), 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    UNIQUE (user_id)
);

CREATE TABLE email_logs (
    user_id UUID, 
    template_id UUID, 
    recipient_email VARCHAR(255) NOT NULL, 
    subject VARCHAR(255), 
    status VARCHAR(6) NOT NULL, 
    error TEXT, 
    sent_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(template_id) REFERENCES email_templates (id) ON DELETE SET NULL, 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_email_logs_user_id ON email_logs (user_id);

CREATE TABLE email_tokens (
    user_id UUID NOT NULL, 
    token VARCHAR(255) NOT NULL, 
    purpose VARCHAR(30) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    used_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX ix_email_tokens_token ON email_tokens (token);

CREATE INDEX ix_email_tokens_user_id ON email_tokens (user_id);

CREATE TABLE internship_batches (
    domain_id UUID NOT NULL, 
    batch_name VARCHAR(150) NOT NULL, 
    start_date DATE NOT NULL, 
    end_date DATE NOT NULL, 
    status VARCHAR(8) NOT NULL, 
    seats_total INTEGER NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(domain_id) REFERENCES internship_domains (id) ON DELETE CASCADE
);

CREATE INDEX ix_internship_batches_domain_id ON internship_batches (domain_id);

CREATE TABLE notifications (
    user_id UUID NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    message TEXT NOT NULL, 
    type VARCHAR(12) NOT NULL, 
    is_read BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_notifications_is_read ON notifications (is_read);

CREATE INDEX ix_notifications_user_id ON notifications (user_id);

CREATE TABLE student_profiles (
    user_id UUID NOT NULL, 
    college_name VARCHAR(150), 
    degree VARCHAR(60), 
    branch VARCHAR(80), 
    year VARCHAR(20), 
    linkedin_url VARCHAR(255), 
    github_url VARCHAR(255), 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    UNIQUE (user_id)
);

CREATE TABLE enrollments (
    student_id UUID NOT NULL, 
    batch_id UUID NOT NULL, 
    status VARCHAR(9) NOT NULL, 
    enrolled_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(batch_id) REFERENCES internship_batches (id) ON DELETE CASCADE, 
    FOREIGN KEY(student_id) REFERENCES users (id) ON DELETE CASCADE, 
    CONSTRAINT uq_enrollment_student_batch UNIQUE (student_id, batch_id)
);

CREATE INDEX ix_enrollments_batch_id ON enrollments (batch_id);

CREATE INDEX ix_enrollments_student_id ON enrollments (student_id);

CREATE TABLE offer_letters (
    student_id UUID NOT NULL, 
    batch_id UUID NOT NULL, 
    offer_letter_number VARCHAR(50) NOT NULL, 
    pdf_url VARCHAR(500), 
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    linkedin_verified BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(batch_id) REFERENCES internship_batches (id) ON DELETE CASCADE, 
    FOREIGN KEY(student_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX ix_offer_letters_offer_letter_number ON offer_letters (offer_letter_number);

CREATE INDEX ix_offer_letters_student_id ON offer_letters (student_id);

CREATE TABLE tasks (
    batch_id UUID NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    description TEXT NOT NULL, 
    order_number INTEGER NOT NULL, 
    deadline DATE, 
    estimated_hours INTEGER NOT NULL, 
    requirements JSON NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(batch_id) REFERENCES internship_batches (id) ON DELETE CASCADE, 
    CONSTRAINT uq_task_batch_order UNIQUE (batch_id, order_number)
);

CREATE INDEX ix_tasks_batch_id ON tasks (batch_id);

CREATE TABLE linkedin_submissions (
    student_id UUID NOT NULL, 
    offer_letter_id UUID NOT NULL, 
    linkedin_post_url VARCHAR(500) NOT NULL, 
    status VARCHAR(8) NOT NULL, 
    admin_comment TEXT, 
    reviewed_by UUID, 
    reviewed_at TIMESTAMP WITH TIME ZONE, 
    submitted_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(offer_letter_id) REFERENCES offer_letters (id) ON DELETE CASCADE, 
    FOREIGN KEY(reviewed_by) REFERENCES users (id) ON DELETE SET NULL, 
    FOREIGN KEY(student_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_linkedin_submissions_status ON linkedin_submissions (status);

CREATE INDEX ix_linkedin_submissions_student_id ON linkedin_submissions (student_id);

CREATE TABLE payments (
    student_id UUID NOT NULL, 
    enrollment_id UUID, 
    razorpay_order_id VARCHAR(100), 
    transaction_id VARCHAR(100), 
    signature VARCHAR(255), 
    amount INTEGER NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    payment_status VARCHAR(7) NOT NULL, 
    paid_at TIMESTAMP WITH TIME ZONE, 
    failure_reason VARCHAR(255), 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(enrollment_id) REFERENCES enrollments (id) ON DELETE SET NULL, 
    FOREIGN KEY(student_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_payments_payment_status ON payments (payment_status);

CREATE INDEX ix_payments_razorpay_order_id ON payments (razorpay_order_id);

CREATE INDEX ix_payments_student_id ON payments (student_id);

CREATE INDEX ix_payments_transaction_id ON payments (transaction_id);

CREATE TABLE task_submissions (
    task_id UUID NOT NULL, 
    student_id UUID NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    github_url VARCHAR(500) NOT NULL, 
    live_demo_url VARCHAR(500), 
    description TEXT NOT NULL, 
    status VARCHAR(12) NOT NULL, 
    submitted_at TIMESTAMP WITH TIME ZONE, 
    attempt INTEGER NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(student_id) REFERENCES users (id) ON DELETE CASCADE, 
    FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE
);

CREATE INDEX ix_task_submissions_status ON task_submissions (status);

CREATE INDEX ix_task_submissions_student_id ON task_submissions (student_id);

CREATE INDEX ix_task_submissions_task_id ON task_submissions (task_id);

CREATE TABLE admin_reviews (
    submission_id UUID NOT NULL, 
    reviewed_by UUID, 
    remarks TEXT NOT NULL, 
    status VARCHAR(8) NOT NULL, 
    reviewed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(reviewed_by) REFERENCES users (id) ON DELETE SET NULL, 
    FOREIGN KEY(submission_id) REFERENCES task_submissions (id) ON DELETE CASCADE
);

CREATE INDEX ix_admin_reviews_submission_id ON admin_reviews (submission_id);

CREATE TABLE certificates (
    student_id UUID NOT NULL, 
    enrollment_id UUID, 
    payment_id UUID, 
    certificate_number VARCHAR(50) NOT NULL, 
    certificate_url VARCHAR(500), 
    qr_code_url VARCHAR(500), 
    status VARCHAR(7) NOT NULL, 
    revoked_reason TEXT, 
    issued_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(enrollment_id) REFERENCES enrollments (id) ON DELETE SET NULL, 
    FOREIGN KEY(payment_id) REFERENCES payments (id) ON DELETE SET NULL, 
    FOREIGN KEY(student_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX ix_certificates_certificate_number ON certificates (certificate_number);

CREATE INDEX ix_certificates_student_id ON certificates (student_id);

CREATE TABLE task_screenshots (
    submission_id UUID NOT NULL, 
    image_url VARCHAR(500) NOT NULL, 
    display_order INTEGER NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(submission_id) REFERENCES task_submissions (id) ON DELETE CASCADE
);

CREATE INDEX ix_task_screenshots_submission_id ON task_screenshots (submission_id);

CREATE TABLE certificate_verification_logs (
    certificate_id UUID, 
    queried_number VARCHAR(50) NOT NULL, 
    found BOOLEAN NOT NULL, 
    ip_address VARCHAR(45), 
    user_agent VARCHAR(255), 
    verified_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(certificate_id) REFERENCES certificates (id) ON DELETE CASCADE
);

CREATE INDEX ix_certificate_verification_logs_certificate_id ON certificate_verification_logs (certificate_id);

INSERT INTO alembic_version (version_num) VALUES ('87f2faee7f16') RETURNING alembic_version.version_num;

-- Running upgrade 87f2faee7f16 -> 02584f9e6f21

ALTER TABLE internship_domains ADD COLUMN image_url VARCHAR(500);

ALTER TABLE internship_domains ADD COLUMN display_order INTEGER DEFAULT '0' NOT NULL;

ALTER TABLE tasks ADD COLUMN is_active BOOLEAN DEFAULT true NOT NULL;

ALTER TABLE tasks ADD COLUMN instructions TEXT;

ALTER TABLE tasks ADD COLUMN min_screenshots INTEGER DEFAULT '3' NOT NULL;

ALTER TABLE tasks ADD COLUMN max_screenshots INTEGER DEFAULT '8' NOT NULL;

ALTER TABLE tasks ADD COLUMN require_github BOOLEAN DEFAULT true NOT NULL;

ALTER TABLE tasks ADD COLUMN require_explanation BOOLEAN DEFAULT true NOT NULL;

ALTER TABLE tasks ADD COLUMN min_explanation_chars INTEGER DEFAULT '120' NOT NULL;

ALTER TABLE tasks ADD COLUMN require_live_demo BOOLEAN DEFAULT false NOT NULL;

UPDATE alembic_version SET version_num='02584f9e6f21' WHERE alembic_version.version_num = '87f2faee7f16';

-- Running upgrade 02584f9e6f21 -> 3c91a7de40b2

CREATE TABLE platform_settings (
    id UUID NOT NULL, 
    key VARCHAR(80) NOT NULL, 
    value TEXT NOT NULL, 
    updated_by UUID, 
    updated_at_utc TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX ix_platform_settings_key ON platform_settings (key);

ALTER TABLE users ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE certificates ADD COLUMN student_name VARCHAR(100);

UPDATE certificates
        SET student_name = (
            SELECT full_name FROM users WHERE users.id = certificates.student_id
        )
        WHERE student_name IS NULL;

UPDATE alembic_version SET version_num='3c91a7de40b2' WHERE alembic_version.version_num = '02584f9e6f21';

-- Running upgrade 3c91a7de40b2 -> 5e2c81b0f7aa

CREATE TABLE learning_chapters (
    id UUID NOT NULL, 
    domain_id UUID NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    summary TEXT, 
    order_number INTEGER NOT NULL, 
    difficulty VARCHAR(20) NOT NULL, 
    pdf_url VARCHAR(500), 
    pdf_filename VARCHAR(255), 
    pdf_size_bytes INTEGER, 
    estimated_minutes INTEGER NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(domain_id) REFERENCES internship_domains (id) ON DELETE CASCADE, 
    CONSTRAINT uq_chapter_position UNIQUE (domain_id, order_number)
);

CREATE INDEX ix_learning_chapters_domain_id ON learning_chapters (domain_id);

CREATE TABLE chapter_reads (
    id UUID NOT NULL, 
    student_id UUID NOT NULL, 
    chapter_id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(student_id) REFERENCES users (id) ON DELETE CASCADE, 
    FOREIGN KEY(chapter_id) REFERENCES learning_chapters (id) ON DELETE CASCADE, 
    CONSTRAINT uq_chapter_read UNIQUE (student_id, chapter_id)
);

CREATE INDEX ix_chapter_reads_student_id ON chapter_reads (student_id);

CREATE INDEX ix_chapter_reads_chapter_id ON chapter_reads (chapter_id);

ALTER TABLE certificates DROP COLUMN payment_id;

DROP TABLE payments;

DROP INDEX ix_platform_settings_key;

DROP TABLE platform_settings;

UPDATE alembic_version SET version_num='5e2c81b0f7aa' WHERE alembic_version.version_num = '3c91a7de40b2';

-- Running upgrade 5e2c81b0f7aa -> 9d4f1c7ab653

UPDATE learning_chapters SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL;

ALTER TABLE learning_chapters ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

UPDATE learning_chapters SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL;

ALTER TABLE learning_chapters ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;

UPDATE chapter_reads SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL;

ALTER TABLE chapter_reads ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

UPDATE chapter_reads SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL;

ALTER TABLE chapter_reads ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;

UPDATE alembic_version SET version_num='9d4f1c7ab653' WHERE alembic_version.version_num = '5e2c81b0f7aa';

COMMIT;

