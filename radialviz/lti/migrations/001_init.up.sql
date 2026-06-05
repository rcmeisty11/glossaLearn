-- TODO: support multiple sentences per assignments, tables for automatically onboarding integrations
-- TODO: backend should not be setting assignment_id and deployment_id should be inferred via LTI

CREATE TYPE assignment_type AS ENUM ('translation', 'perception', 'production');

CREATE TABLE
    course (
        deployment_id TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW (),
        PRIMARY KEY (deployment_id)
    );

CREATE TABLE
    assignment (
        deployment_id TEXT NOT NULL,
        assignment_id TEXT NOT NULL,
        assignment_type assignment_type NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW (),
        author TEXT NOT NULL,
        work TEXT NOT NULL,
        sentence_id TEXT NOT NULL,
        PRIMARY KEY (
            deployment_id,
            assignment_id,
            assignment_type,
            author,
            work,
            sentence_id
        ),
        FOREIGN KEY (deployment_id) REFERENCES course (deployment_id) ON DELETE CASCADE
    );

CREATE TABLE
    assignment_submission (
        deployment_id TEXT NOT NULL,
        student_id TEXT NOT NULL,
        assignment_id TEXT NOT NULL,
        assignment_artifact TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW (),
        -- just store grade on assignment submission for now
        grade NUMERIC(5, 2),
        PRIMARY KEY (
            deployment_id,
            student_id,
            assignment_id
        ),
        FOREIGN KEY (deployment_id) REFERENCES course (deployment_id) ON DELETE CASCADE
    );

