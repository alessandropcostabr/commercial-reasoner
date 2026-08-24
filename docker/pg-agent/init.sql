-- Agente Fase 1 - init do Postgres dedicado (pg-agent).
--
-- INTENCIONALMENTE QUASE VAZIO. O claude-mem server-beta cria todo o schema
-- sozinho no boot (bootstrapServerBetaPostgresSchema, src/storage/postgres/
-- schema.ts:22) - 12 tabelas + indices, todas IF NOT EXISTS, dentro de uma
-- transacao, registrando version=1 em server_beta_schema_migrations.
--
-- NAO usar pgvector: o embedding e coluna JSONB (schema.ts:226); a unica
-- "vector" e TSVECTOR (full-text built-in, nao precisa de extensao).
--
-- O database em si (POSTGRES_DB=agent) ja e criado pela imagem postgres.
-- O project "agent" + team + api-key sao criados POS-BOOT pelo
-- docker/bootstrap/create-agent-key.sh (precisam das tabelas, que so existem
-- depois do server-beta subir).

-- Nada a fazer aqui. Placeholder explicito para o contrato ficar claro.
SELECT 'pg-agent pronto; schema sera bootstrapado pelo server-beta' AS init_note;
