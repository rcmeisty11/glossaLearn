# lti docs

## justifications

### why are there two dbs?

linguistic data is stored separately from user (LTI/integration) data for security reasons and simplified architecture

## rest

run migrations:

`podman exec -i lti-postgres psql -U postgres -d app_db < lti/migrations/001_init.up.sql`

query that db:

`podman exec -it lti-postgres psql -U postgres -d app_db`