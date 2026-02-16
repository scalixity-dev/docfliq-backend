#!/bin/bash
# Create multiple DBs for local Postgres (used by docker-compose)
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE DATABASE identity_db;
  CREATE DATABASE content_db;
  CREATE DATABASE course_db;
  CREATE DATABASE payment_db;
  CREATE DATABASE platform_db;
EOSQL
