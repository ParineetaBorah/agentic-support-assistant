CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK (role IN ('admin', 'support_user', 'sales_user')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    tier TEXT NOT NULL CHECK (tier IN ('enterprise', 'smb', 'startup')),
    industry TEXT NOT NULL,
    account_manager UUID NOT NULL REFERENCES users (id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE issues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers (id),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    status TEXT NOT NULL CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE issue_updates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id UUID NOT NULL REFERENCES issues (id),
    update_text TEXT NOT NULL,
    updated_by UUID NOT NULL REFERENCES users (id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE next_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id UUID NOT NULL REFERENCES issues (id),
    recommendation_text TEXT NOT NULL,
    risk_level TEXT NOT NULL CHECK (risk_level IN ('critical', 'high', 'medium', 'low')),
    created_by UUID NOT NULL REFERENCES users (id),
    status TEXT NOT NULL CHECK (status IN ('pending', 'completed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users (id),
    customer_id UUID NOT NULL REFERENCES customers (id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ
);

CREATE TABLE conversation_turns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations (id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE agent_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations (id),
    turn_id UUID REFERENCES conversation_turns (id),
    tool_name TEXT NOT NULL,
    tool_input JSONB,
    tool_output JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE agent_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations (id),
    issue_id UUID NOT NULL REFERENCES issues (id),
    recommended_text TEXT NOT NULL,
    risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    outcome TEXT NOT NULL DEFAULT 'pending' CHECK (outcome IN ('accepted', 'edited', 'dismissed', 'pending')),
    next_action_id UUID REFERENCES next_actions (id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_issues_customer_id ON issues (customer_id);
CREATE INDEX idx_issues_status ON issues (status);
CREATE INDEX idx_issues_severity ON issues (severity);
CREATE INDEX idx_agent_actions_conversation_id ON agent_actions (conversation_id);
CREATE INDEX idx_agent_recommendations_conversation_issue_outcome ON agent_recommendations (conversation_id, issue_id, outcome);
CREATE INDEX idx_conversation_turns_conversation_id ON conversation_turns (conversation_id);

INSERT INTO users (id, username, email, role) VALUES
    ('20000000-0000-0000-0000-000000000001', 'alice', 'alice@acme.com', 'sales_user'),
    ('20000000-0000-0000-0000-000000000002', 'bob', 'bob@acme.com', 'support_user'),
    ('20000000-0000-0000-0000-000000000003', 'carol', 'carol@acme.com', 'admin');

INSERT INTO customers (id, name, tier, industry, account_manager) VALUES
    ('10000000-0000-0000-0000-000000000001', 'Globex Corp', 'enterprise', 'Manufacturing', '20000000-0000-0000-0000-000000000003'),
    ('10000000-0000-0000-0000-000000000002', 'Initech', 'smb', 'Technology', '20000000-0000-0000-0000-000000000002'),
    ('10000000-0000-0000-0000-000000000003', 'Umbrella Ltd', 'startup', 'Biotech', '20000000-0000-0000-0000-000000000001');

INSERT INTO issues (id, customer_id, title, description, severity, status) VALUES
    ('30000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', 'Production database unresponsive',
     'The primary production PostgreSQL instance is not responding to client connections. All customer-facing services are degraded.',
     'critical', 'open'),
    ('30000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', 'API gateway returning timeouts',
     'Requests routed through the API gateway are intermittently timing out under moderate load.',
     'high', 'open'),
    ('30000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000001', 'ETL pipeline failure',
     'The nightly ETL pipeline that syncs data into the analytics warehouse is failing during the transform step.',
     'high', 'open'),
    ('30000000-0000-0000-0000-000000000004', '10000000-0000-0000-0000-000000000002', 'SSO login intermittent failures',
     'Some users report being redirected back to the login page after completing SSO authentication.',
     'medium', 'open');

INSERT INTO issue_updates (id, issue_id, update_text, updated_by) VALUES
    ('40000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001',
     'Confirmed the DB host is at 100% CPU; investigating long-running queries.', '20000000-0000-0000-0000-000000000002'),
    ('40000000-0000-0000-0000-000000000002', '30000000-0000-0000-0000-000000000001',
     'Engaged the on-call DBA team; failover to the standby replica is being prepared.', '20000000-0000-0000-0000-000000000003'),
    ('40000000-0000-0000-0000-000000000003', '30000000-0000-0000-0000-000000000002',
     'Reproduced the timeouts under load testing; gateway logs show upstream connection pool exhaustion.', '20000000-0000-0000-0000-000000000002'),
    ('40000000-0000-0000-0000-000000000004', '30000000-0000-0000-0000-000000000002',
     'Increased the gateway connection pool size as a temporary mitigation.', '20000000-0000-0000-0000-000000000003'),
    ('40000000-0000-0000-0000-000000000005', '30000000-0000-0000-0000-000000000003',
     'ETL job fails at the transform step with a schema mismatch on the orders table.', '20000000-0000-0000-0000-000000000002'),
    ('40000000-0000-0000-0000-000000000006', '30000000-0000-0000-0000-000000000003',
     'Coordinated with Globex''s data team to confirm the upstream schema change.', '20000000-0000-0000-0000-000000000003'),
    ('40000000-0000-0000-0000-000000000007', '30000000-0000-0000-0000-000000000004',
     'Collected affected user reports; issue appears tied to a specific identity provider.', '20000000-0000-0000-0000-000000000002'),
    ('40000000-0000-0000-0000-000000000008', '30000000-0000-0000-0000-000000000004',
     'Reached out to Initech''s IT team to verify the IdP configuration.', '20000000-0000-0000-0000-000000000003');

INSERT INTO next_actions (id, issue_id, recommendation_text, risk_level, created_by, status) VALUES
    ('50000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001',
     'Initiate failover to the standby replica and notify Globex''s incident channel.', 'critical', '20000000-0000-0000-0000-000000000003', 'pending');

INSERT INTO conversations (id, user_id, customer_id) VALUES
    ('60000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000001');

INSERT INTO agent_recommendations (id, conversation_id, issue_id, recommended_text, risk_level, outcome, next_action_id) VALUES
    ('90000000-0000-0000-0000-000000000001', '60000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001',
     'Failover to the standby replica and notify Globex''s incident channel.', 'critical', 'pending', '50000000-0000-0000-0000-000000000001');
