# AGENT_HANDOVER_SPEC

## 1 System overview
```yaml
system_overview:
  repo_root: /home/ray/kg-system
  components:
    frontend:
      path: /home/ray/kg-system/frontend
      stack:
        react: 19.2.0
        vite: 7.3.1
        typescript: 5.9.3
        antv_g6: 5.0.51
      dev_url: http://127.0.0.1:5173
    backend:
      path: /home/ray/kg-system/backend
      stack:
        fastapi: 0.133.1
        uvicorn: 0.41.0
        pydantic: 2.12.5
        nebula3_python: 3.8.3
        python_dotenv: 1.2.1
      dev_url: http://127.0.0.1:8000
      api_health: http://127.0.0.1:8000/api/health
    database:
      compose_root: /home/ray/nebula-docker-compose
      engine: NebulaGraph
      version:
        graphd: 3.8.0
        metad: 3.8.0
        storaged: 3.8.0
        console: 3.6.0
      services:
        - metad
        - storaged
        - graphd
        - console
      optional_services:
        elasticsearch:
          container_name: kg-es
          version: 7.17.27
          url: http://127.0.0.1:9200
  communication:
    - from: frontend
      to: backend
      protocol: http
      request_prefix: /api
      dev_proxy_target: http://localhost:8000
    - from: backend
      to: nebula_graphd
      protocol: tcp
      target: 127.0.0.1:9669
    - from: backend
      to: elasticsearch
      protocol: http
      target: http://127.0.0.1:9200
      enabled_by_default: true
```

## 2 Runtime environment
```yaml
runtime_environment:
  os:
    name: Ubuntu
    version: 24.04.3 LTS
    kernel: Linux 6.6.87.2-microsoft-standard-WSL2
    arch: x86_64
  python:
    required: 3.12.3
    binary: /usr/bin/python3
    backend_venv_python: /home/ray/kg-system/backend/.venv/bin/python
  node:
    required: v20.20.0
    npm: 11.8.0
    binary: /usr/bin/node
  docker:
    engine: 29.1.5
    compose: v5.0.1
```

## 3 Project directory structure
```yaml
project_directory_structure:
  frontend:
    path: /home/ray/kg-system/frontend
    key_files:
      - /home/ray/kg-system/frontend/package.json
      - /home/ray/kg-system/frontend/vite.config.ts
      - /home/ray/kg-system/frontend/src
  backend:
    path: /home/ray/kg-system/backend
    key_files:
      - /home/ray/kg-system/backend/app/main.py
      - /home/ray/kg-system/backend/app/config.py
      - /home/ray/kg-system/backend/scripts/run_backend_single.sh
      - /home/ray/kg-system/backend/scripts/stop_backend_single.sh
  docker:
    path: /home/ray/nebula-docker-compose
    key_files:
      - /home/ray/nebula-docker-compose/docker-compose.yaml
      - /home/ray/nebula-docker-compose/docker-compose.override.yaml
      - /home/ray/nebula-docker-compose/.env
  data:
    import_pipeline_path: /home/ray/kg-system/data-import
    external_source_root: /home/ray/data/kg_demo
    source_files:
      vertices_csv: /home/ray/data/kg_demo/unified_entities_with_synonyms.csv
      edges_root: /home/ray/data/kg_demo/edges
```

## 4 Backend configuration
```yaml
backend_configuration:
  backend_root_path: /home/ray/kg-system/backend
  entrypoint: app.main:app
  startup_command: cd /home/ray/kg-system/backend && source .venv/bin/activate && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
  alternate_startup_command: cd /home/ray/kg-system/backend && HOST=127.0.0.1 PORT=8000 LOG_FILE=/home/ray/kg-system/backend/server.dev.log ./scripts/run_backend_single.sh
  stop_command: cd /home/ray/kg-system/backend && PORT=8000 ./scripts/stop_backend_single.sh
  dependency_source:
    requirements_txt: /home/ray/kg-system/backend/requirements.txt
    requirements_txt_status: absent
    active_venv: /home/ray/kg-system/backend/.venv
    installed_packages:
      - annotated-doc==0.0.4
      - annotated-types==0.7.0
      - anyio==4.12.1
      - click==8.3.1
      - fastapi==0.133.1
      - httpx==0.28.1
      - nebula3-python==3.8.3
      - pydantic==2.12.5
      - python-dotenv==1.2.1
      - PyYAML==6.0.3
      - starlette==0.52.1
      - uvicorn==0.41.0
      - uvloop==0.22.1
      - watchfiles==1.1.1
      - websockets==16.0
  dotenv:
    env_file: /home/ray/kg-system/.env
    env_file_status: absent
  environment_variables:
    NEBULA_HOST: 127.0.0.1
    NEBULA_PORT: 9669
    NEBULA_USER: root
    NEBULA_PASSWORD: nebula
    NEBULA_SPACE: demo_kg
    NEBULA_TIMEOUT_MS: 5000
    NEBULA_POOL_SIZE: 10
    EDGE_TYPE: REL2
    CANDIDATE_LIMIT: 300
    DESC_CANDIDATE_LIMIT: 50
    TOPK: 100
    MAX_EDGES_RETURN: 3000
    SEARCH_MIN_QUERY_LEN: 3
    SEARCH_INCLUDE_EDGES_DEFAULT: 0
    DEBUG_PROBE: 0
    EDGE_SUGGEST_SCAN_LIMIT: 1500
    EDGE_SEARCH_SCAN_LIMIT: 8000
    EDGE_PROP_VALUE_MAX_LEN: 300
    EDGE_PROP_MAX_FIELDS: 24
    EDGE_SNIPPET_MAX_LEN: 90
    EDGE_PROP_FIELD_WHITELIST: evidence,description,sentence,text,pmid,title,label,name,alias,mesh_id,umls_id,drug,disease,symptom,target,pathway
    FALLBACK_ENABLE_SCAN: 0
    ES_ENABLED: 1
    ES_URL: http://127.0.0.1:9200
    ES_INDEX: kg_entity
    ES_TIMEOUT_MS: 1200
    ES_TOPK: 120
    DEV_INSTANCE_TRACE: 1
    AUDIT_LOG_PATH: logs/edit_audit.jsonl
  cors_allow_origins:
    - http://localhost:5173
    - http://127.0.0.1:5173
```

## 5 Frontend configuration
```yaml
frontend_configuration:
  frontend_root_path: /home/ray/kg-system/frontend
  package_json: /home/ray/kg-system/frontend/package.json
  start_command: cd /home/ray/kg-system/frontend && npm run dev -- --host 0.0.0.0 --port 5173
  build_command: cd /home/ray/kg-system/frontend && npm run build
  preview_command: cd /home/ray/kg-system/frontend && npm run preview
  dependency_install_command: cd /home/ray/kg-system/frontend && npm install
  proxy_configuration:
    file: /home/ray/kg-system/frontend/vite.config.ts
    proxy_prefix: /api
    proxy_target: http://localhost:8000
    change_origin: true
  frontend_env:
    root_env_file: /home/ray/kg-system/.env
    root_env_file_status: absent
    declared_variable:
      VITE_API_BASE_URL: http://127.0.0.1:8000
  scripts:
    dev: vite
    build: tsc -b && vite build
    lint: eslint .
    preview: vite preview
```

## 6 Database configuration
```yaml
database_configuration:
  engine: NebulaGraph
  compose_root: /home/ray/nebula-docker-compose
  compose_files:
    - /home/ray/nebula-docker-compose/docker-compose.yaml
    - /home/ray/nebula-docker-compose/docker-compose.override.yaml
  compose_env_file: /home/ray/nebula-docker-compose/.env
  compose_env:
    TZ: UTC
  docker_project_name: nebula-docker-compose
  docker_network_declared: nebula-net
  docker_network_effective: nebula-docker-compose_nebula-net
  services:
    metad:
      container_name: nebula-docker-compose-metad-1
      image: docker.io/vesoft/nebula-metad:v3.8.0
      host_port_assignment: dynamic
      internal_ports:
        thrift: 9559
        http: 19559
        http2: 19560
      current_host_ports:
        thrift: 46025
        http: 46061
        http2: 44721
      data_path_host: /home/ray/nebula-docker-compose/data/meta0
      log_path_host: /home/ray/nebula-docker-compose/logs/meta0
      config_path_host: /home/ray/nebula-docker-compose/conf/nebula-metad.conf
    storaged:
      container_name: nebula-docker-compose-storaged-1
      image: docker.io/vesoft/nebula-storaged:v3.8.0
      host_port_assignment: dynamic
      internal_ports:
        thrift: 9779
        http: 19779
        admin: 19780
      current_host_ports:
        thrift: 45833
        http: 45061
        admin: 45975
      data_path_host: /home/ray/nebula-docker-compose/data/storage
      log_path_host: /home/ray/nebula-docker-compose/logs/storage
      config_path_host: /home/ray/nebula-docker-compose/conf/nebula-storaged.conf
    graphd:
      container_name: nebula-docker-compose-graphd-1
      image: docker.io/vesoft/nebula-graphd:v3.8.0
      internal_ports:
        graph: 9669
        http: 19669
      current_host_ports:
        graph: 9669
        http: not_published
      log_path_host: /home/ray/nebula-docker-compose/logs/graph
      config_path_host: /home/ray/nebula-docker-compose/conf/nebula-graphd.conf
    console:
      container_name: nebula-docker-compose-console-1
      image: docker.io/vesoft/nebula-console:v3.6.0
    elasticsearch:
      container_name: kg-es
      image: docker.elastic.co/elasticsearch/elasticsearch:7.17.27
      host_port: 9200
  credentials:
    user: root
    password: nebula
    validated_command: docker exec -i nebula-docker-compose-console-1 nebula-console -addr graphd -port 9669 -u root -p nebula -e 'SHOW SPACES;'
  startup_command: cd /home/ray/nebula-docker-compose && docker compose up -d
  shutdown_command: cd /home/ray/nebula-docker-compose && docker compose down
```

## 7 Graph schema
```yaml
graph_schema:
  space:
    name: demo_kg
    vid_type: INT64
    create_statement: CREATE SPACE IF NOT EXISTS demo_kg(partition_num=10, replica_factor=1, vid_type=INT64);
  tags:
    - name: Entity
      fields:
        - { name: entity_type, type: string }
        - { name: entity_name, type: string }
        - { name: entity_raw_id, type: string }
        - { name: description, type: string }
        - { name: source, type: string }
        - { name: version, type: int64 }
        - { name: updated_at, type: int64 }
        - { name: updated_by, type: string }
  edges:
    - name: REL2
      fields:
        - { name: relation, type: string }
        - { name: source, type: string }
        - { name: evidence, type: string }
        - { name: version, type: int64 }
        - { name: updated_at, type: int64 }
        - { name: updated_by, type: string }
  indexes:
    active_tag_indexes: []
    active_edge_indexes: []
    optional_migration_indexes:
      - name: idx_entity_raw_id_norm
        type: tag_index
        target: Entity(raw_id_norm)
        migration_doc: /home/ray/kg-system/backend/docs/raw_id_norm_migration.md
```

## 8 Data import pipeline
```yaml
data_import_pipeline:
  pipeline_root: /home/ray/kg-system/data-import
  entrypoint: /home/ray/kg-system/data-import/run.sh
  tools:
    nebula_importer:
      binary_resolution_order:
        - env: IMPORTER_BIN
        - path_lookup: nebula-importer
        - fixed_path: /home/ray/nebula-importer/bin/nebula-importer
        - fixed_path: /home/ray/nebula-importer/nebula-importer
    nebula_console_resolution_order:
      - path_lookup: nebula-console
      - docker_exec: docker exec -i nebula-docker-compose-console-1 nebula-console
  source_inputs:
    vertices_csv: /home/ray/data/kg_demo/unified_entities_with_synonyms.csv
    edges_root_glob: /home/ray/data/kg_demo/edges/**/*_edges.csv
  intermediate_outputs:
    vertices_shards_dir: /home/ray/kg-system/data-import/out/vertices_shards
    edges_shards_dir: /home/ray/kg-system/data-import/out/edges_shards
    tmp_dir: /home/ray/kg-system/data-import/out/tmp
    logs_dir: /home/ray/kg-system/data-import/logs
    state_dir: /home/ray/kg-system/data-import/state
  nebula_importer_configs:
    vertices_template: /home/ray/kg-system/data-import/configs/import_vertices.yaml
    edges_template: /home/ray/kg-system/data-import/configs/import_edges.yaml
    vertices_rendered: /home/ray/kg-system/data-import/logs/import_vertices.rendered.yaml
    edges_rendered: /home/ray/kg-system/data-import/logs/import_edges.rendered.yaml
  csv_schema:
    vertices_input_required_columns:
      - ID
      - entity_type
      - entity_name
      - entity_raw_id
      - description
      - source
    vertices_output_columns:
      - ID
      - entity_type
      - entity_name
      - entity_raw_id
      - description
      - source
      - version
      - updated_at
      - updated_by
    edges_input_required_columns:
      - subject_our_defined_id
      - object_our_defined_id
      - relation
      - source
      - pmid
      - relation_detail
      - direction
      - score
    edges_output_columns:
      - srcVID
      - dstVID
      - rank
      - relation
      - source
      - evidence
      - version
      - updated_at
      - updated_by
  import_steps:
    - step: env_check
      command: cd /home/ray/kg-system/data-import && ./scripts/00_env_check.sh
    - step: reset_space_and_apply_schema
      command: cd /home/ray/kg-system/data-import && ./run.sh
      destructive: true
    - step: prepare_vertices
      command: cd /home/ray/kg-system/data-import && python3 scripts/01_prepare_vertices.py --input /home/ray/data/kg_demo/unified_entities_with_synonyms.csv --output-dir /home/ray/kg-system/data-import/out/vertices_shards --shard-size 2000000
    - step: import_vertices
      command: cd /home/ray/kg-system/data-import && nebula-importer --config /home/ray/kg-system/data-import/logs/import_vertices.rendered.yaml
    - step: prepare_edges
      command: cd /home/ray/kg-system/data-import && python3 scripts/02_prepare_edges.py --edges-root /home/ray/data/kg_demo/edges --tmp-dir /home/ray/kg-system/data-import/out/tmp --output-dir /home/ray/kg-system/data-import/out/edges_shards --shard-size 2000000
    - step: import_edges
      command: cd /home/ray/kg-system/data-import && nebula-importer --config /home/ray/kg-system/data-import/logs/import_edges.rendered.yaml
    - step: verify
      command: cd /home/ray/kg-system/data-import && ./scripts/03_verify_after_import.sh
```

## 9 API specification
```yaml
api_specification:
  base_url: http://127.0.0.1:8000
  endpoints:
    - endpoint: /api/health
      method: GET
      request_params: []
      response_structure:
        ok: bool
        hosts_rows: int
    - endpoint: /api/search
      method: POST
      request_params:
        q: string
        search_in_name: bool
        search_in_description: bool
        search_in_type: bool
        search_in_raw_id: bool
        include_edges: bool
        entity_type: string|null
        source: string|null
        entity_raw_id: string|null
        entity_raw_id_mode: contains|prefix|exact
      response_structure:
        nodes:
          - id: int
            label: string
            entity_type: string
            raw_id: string
            source: string
            score: number|null
            snippet: string
        edges:
          - source: int
            target: int
            rank: string
            edge_type: string
            relation: string
            source_db: string
        total_candidates: int
        truncated: bool
        meta:
          request_id: string
          strategy: string
          reason: string
          timings_ms: object
    - endpoint: /api/suggest
      method: GET
      request_params:
        q: string
        limit: int=12
        entity_type: string|null
        source: string|null
      response_structure:
        q: string
        items:
          - vid: int
            label: string
            entity_type: string
            source: string
            score: number|null
        truncated: bool
    - endpoint: /api/suggest_raw_id
      method: GET
      request_params:
        q: string
        limit: int=12
        entity_type: string|null
        source: string|null
      response_structure:
        q: string
        items:
          - vid: int
            entity_raw_id: string
            label: string
            entity_type: string
            source: string
        truncated: bool
    - endpoint: /api/entity_types
      method: GET
      request_params: []
      response_structure:
        - entity_type: string
          count: int
    - endpoint: /api/subgraph
      method: POST
      request_params:
        root_vid: int
        hop: int=1
        relations: string[]
        max_nodes: int=300
        max_edges: int=20000
      response_structure:
        root_vid: int
        nodes: GraphNode[]
        edges: GraphEdge[]
        stats:
          node_count: int
          edge_count: int
          truncated: bool
          dropped_nodes: int
    - endpoint: /api/expand
      method: POST
      request_params:
        from_vid: int
        relations: string[]
        existing_node_ids: int[]
        max_nodes: int=300
        max_edges: int=20000
      response_structure:
        added_nodes: GraphNode[]
        added_edges: GraphEdge[]
        stats:
          node_count_after: int
          dropped_nodes: int
          policy: string
    - endpoint: /api/relation_types
      method: GET
      request_params: []
      response_structure:
        - string
    - endpoint: /api/multi_entity_graph
      method: POST
      request_params:
        vids: int[]
        direct_only: bool
        explain_paths: bool
        k: int
        relations: string[]
        max_nodes: int
        max_edges: int
        per_pair_path_limit: int
        ignore_direction: bool
      response_structure:
        nodes: GraphNode[]
        edges: GraphEdge[]
        stats: object
        path_candidates: object[]
    - endpoint: /api/multi_entity_graph_apply_paths
      method: POST
      request_params:
        base_request: object
        choices:
          - u: int
            v: int
            chosen_index: int
      response_structure:
        nodes: GraphNode[]
        edges: GraphEdge[]
        stats: object
        path_candidates: object[]
    - endpoint: /api/node/{vid}
      method: GET
      request_params:
        vid: int
      response_structure:
        vid: int
        entity_name: string
        entity_type: string
        source: string
        description: string
        entity_raw_id: string
        version: int
        updated_at: int
        updated_by: string
        props: object
    - endpoint: /api/node_detail
      method: GET
      request_params:
        vid: int
      response_structure:
        vid: int
        entity_name: string
        entity_type: string
        source: string
        description: string
        entity_raw_id: string
        version: int
        updated_at: int
        updated_by: string
        props: object
    - endpoint: /api/edge_detail
      method: POST
      request_params:
        edge_type: string
        src: int
        dst: int
        rank: string
      response_structure:
        edge_type: string
        src: int
        dst: int
        rank: string
        relation: string
        source_db: string|null
        evidence: string
        version: int
        updated_at: int
        updated_by: string
        updated: bool
        props: object
    - endpoint: /api/schema/editable_fields
      method: GET
      request_params: []
      response_structure:
        entity:
          fields:
            - name: description|entity_name|entity_type|source
              type: string
              maxLen: int
              multiline: bool
              required: bool
        edge:
          fields:
            - name: evidence|relation|source
              type: string
              maxLen: int
              multiline: bool
              required: bool
        forbidden_fields:
          - entity_raw_id
    - endpoint: /api/node/{vid}
      method: PATCH
      request_params:
        vid: int
        set: object<string,string>
        expected_version: int
        updated_by: string
      response_structure:
        vid: int
        updated: object
        version: int
        updated_at: int
        updated_by: string
      error_responses:
        404: node not found
        409:
          error_code: VERSION_CONFLICT
          message: expected_version mismatch
          current_version: int
          current_snapshot: object
        422:
          error_code: VALIDATION_ERROR
          field: string
          message: string
    - endpoint: /api/edge
      method: PATCH
      request_params:
        edge_type: string
        src: int
        dst: int
        rank: string|int
        set: object<string,string>
        expected_version: int
        updated_by: string
      response_structure:
        identity:
          src: int
          dst: int
          rank: string
          edge_type: string
        updated: object
        version: int
        updated_at: int
        updated_by: string
      error_responses:
        404: edge not found
        409:
          error_code: VERSION_CONFLICT
          message: expected_version mismatch
          current_version: int
          current_snapshot: object
        422:
          error_code: VALIDATION_ERROR
          field: string
          message: string
    - endpoint: /api/edge_suggest
      method: GET
      request_params:
        q: string
        limit: int=12
        relation: string|null
        source_db: string|null
      response_structure:
        q: string
        items:
          - edge_type: string
            src: int
            dst: int
            rank: string
            relation: string
            source_db: string
            score: number|null
            src_label: string
            dst_label: string
        truncated: bool
    - endpoint: /api/edge_search
      method: POST
      request_params:
        q: string
        search_in_relation: bool
        search_in_props: bool
        source_db: string|null
        relation: string|null
        limit: int
      response_structure:
        edges:
          - edge_type: string
            src: int
            dst: int
            rank: string
            relation: string
            source_db: string
            score: number|null
            src_label: string
            dst_label: string
            snippet: string
        total_candidates: int
```

## 10 Ports
```yaml
ports:
  frontend:
    service: vite_dev_server
    host: 5173
    bind: 0.0.0.0
  backend:
    service: uvicorn
    host: 8000
    bind: 127.0.0.1
  nebula:
    graphd:
      internal: 9669
      host: 9669
    graphd_http:
      internal: 19669
      host: not_published
    metad:
      internal: 9559
      host_mapping_mode: dynamic
      host_current: 46025
    metad_http:
      internal: 19559
      host_mapping_mode: dynamic
      host_current: 46061
    metad_http2:
      internal: 19560
      host_mapping_mode: dynamic
      host_current: 44721
    storaged:
      internal: 9779
      host_mapping_mode: dynamic
      host_current: 45833
    storaged_http:
      internal: 19779
      host_mapping_mode: dynamic
      host_current: 45061
    storaged_admin:
      internal: 19780
      host_mapping_mode: dynamic
      host_current: 45975
    elasticsearch:
      internal: 9200
      host: 9200
    studio:
      host: 7001
```

## 11 Logs
```yaml
logs:
  backend_logs:
    - /home/ray/kg-system/backend/server.dev.log
    - /home/ray/kg-system/backend/server.log
    - /home/ray/kg-system/backend/logs/edit_audit.jsonl
  frontend_logs:
    - /home/ray/kg-system/frontend/vite.dev.log
  data_import_logs:
    - /home/ray/kg-system/data-import/logs/step1_env_check.log
    - /home/ray/kg-system/data-import/logs/step2_drop_space.log
    - /home/ray/kg-system/data-import/logs/step2_create_space.log
    - /home/ray/kg-system/data-import/logs/step2_schema_apply.log
    - /home/ray/kg-system/data-import/logs/step2_schema_verify.log
    - /home/ray/kg-system/data-import/logs/step3_prepare_vertices.log
    - /home/ray/kg-system/data-import/logs/step4_import_vertices.log
    - /home/ray/kg-system/data-import/logs/step5_prepare_edges.log
    - /home/ray/kg-system/data-import/logs/step6_import_edges.log
    - /home/ray/kg-system/data-import/logs/step7_verify.log
    - /home/ray/kg-system/data-import/logs/nebula-importer-vertices.log
    - /home/ray/kg-system/data-import/logs/nebula-importer-edges.log
  docker_logs:
    host_directories:
      - /home/ray/nebula-docker-compose/logs/graph
      - /home/ray/nebula-docker-compose/logs/meta0
      - /home/ray/nebula-docker-compose/logs/storage
    commands:
      - docker logs nebula-docker-compose-graphd-1
      - docker logs nebula-docker-compose-metad-1
      - docker logs nebula-docker-compose-storaged-1
      - docker logs kg-es
```

## 12 Debug commands
```yaml
debug_commands:
  docker_ps: docker ps
  docker_compose_ps: cd /home/ray/nebula-docker-compose && docker compose ps
  backend_health: curl -sS http://127.0.0.1:8000/api/health
  frontend_health: curl -I http://127.0.0.1:5173
  backend_logs_tail: tail -n 200 /home/ray/kg-system/backend/server.dev.log
  backend_logs_follow: tail -f /home/ray/kg-system/backend/server.dev.log
  uvicorn_processes: ps -eo pid=,args= | rg 'python3? -m uvicorn app\\.main:app.*--port 8000' -N
  vite_processes: ps -eo pid=,args= | rg 'vite.*5173' -N
  nebula_console: docker exec -it nebula-docker-compose-console-1 nebula-console -addr graphd -port 9669 -u root -p nebula
  nebula_show_spaces: docker exec -i nebula-docker-compose-console-1 nebula-console -addr graphd -port 9669 -u root -p nebula -e 'SHOW SPACES;'
  nebula_show_stats: docker exec -i nebula-docker-compose-console-1 nebula-console -addr graphd -port 9669 -u root -p nebula -e 'USE demo_kg; SHOW STATS;'
  nebula_describe_tag: docker exec -i nebula-docker-compose-console-1 nebula-console -addr graphd -port 9669 -u root -p nebula -e 'USE demo_kg; DESCRIBE TAG Entity;'
  nebula_describe_edge: docker exec -i nebula-docker-compose-console-1 nebula-console -addr graphd -port 9669 -u root -p nebula -e 'USE demo_kg; DESCRIBE EDGE REL2;'
  import_verify: cd /home/ray/kg-system/data-import && ./scripts/03_verify_after_import.sh
```

## 13 Data locations
```yaml
data_locations:
  source_csv:
    vertices: /home/ray/data/kg_demo/unified_entities_with_synonyms.csv
    edges_root: /home/ray/data/kg_demo/edges
  generated_csv:
    vertices_shards: /home/ray/kg-system/data-import/out/vertices_shards
    edges_shards: /home/ray/kg-system/data-import/out/edges_shards
  importer_failure_rows:
    vertices: /home/ray/kg-system/data-import/logs/failed_vertices
    edges: /home/ray/kg-system/data-import/logs/failed_edges
  nebula_storage:
    meta: /home/ray/nebula-docker-compose/data/meta0
    storage: /home/ray/nebula-docker-compose/data/storage
  elasticsearch_storage:
    volume_name: nebula-docker-compose_es-data
```

## 14 Deployment commands
```yaml
deployment_commands:
  full_start_order:
    - step: 1_start_database
      command: cd /home/ray/nebula-docker-compose && docker compose up -d
    - step: 2_wait_for_database
      command: cd /home/ray/nebula-docker-compose && docker compose ps
    - step: 3_validate_database
      command: docker exec -i nebula-docker-compose-console-1 nebula-console -addr graphd -port 9669 -u root -p nebula -e 'SHOW SPACES;'
    - step: 4_start_backend
      command: cd /home/ray/kg-system/backend && source .venv/bin/activate && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
    - step: 5_validate_backend
      command: curl -sS http://127.0.0.1:8000/api/health
    - step: 6_start_frontend
      command: cd /home/ray/kg-system/frontend && npm run dev -- --host 0.0.0.0 --port 5173
    - step: 7_validate_frontend
      command: curl -I http://127.0.0.1:5173
  one_command_dev:
    command: cd /home/ray/kg-system && ./dev.sh
```

## 15 Shutdown commands
```yaml
shutdown_commands:
  frontend:
    - pkill -f 'vite.*5173'
    - lsof -ti:5173 | xargs -r kill
  backend:
    - cd /home/ray/kg-system/backend && PORT=8000 ./scripts/stop_backend_single.sh
    - lsof -ti:8000 | xargs -r kill
  database:
    - cd /home/ray/nebula-docker-compose && docker compose down
  full_shutdown:
    - pkill -f 'vite.*5173'
    - cd /home/ray/kg-system/backend && PORT=8000 ./scripts/stop_backend_single.sh
    - cd /home/ray/nebula-docker-compose && docker compose down
```

## 16 Failure recovery
```yaml
failure_recovery:
  api_500:
    - tail -n 200 /home/ray/kg-system/backend/server.dev.log
    - curl -sS http://127.0.0.1:8000/api/health
    - docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
    - docker logs --tail 200 nebula-docker-compose-graphd-1
    - docker logs --tail 200 kg-es
  database_connection_failure:
    checks:
      - docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
      - docker exec -i nebula-docker-compose-console-1 nebula-console -addr graphd -port 9669 -u root -p nebula -e 'SHOW SPACES;'
      - python3 - <<'PY'\nimport socket\ns=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',9669)); print('ok')\ns.close()\nPY
    recovery_commands:
      - cd /home/ray/nebula-docker-compose && docker compose restart graphd metad storaged
      - sleep 10
      - curl -sS http://127.0.0.1:8000/api/health
  frontend_request_error:
    - sed -n '1,200p' /home/ray/kg-system/frontend/vite.config.ts
    - curl -sS http://127.0.0.1:8000/api/health
    - curl -I http://127.0.0.1:5173
    - ps -eo pid=,args= | rg 'vite.*5173' -N
    - pkill -f 'vite.*5173' && cd /home/ray/kg-system/frontend && npm run dev -- --host 0.0.0.0 --port 5173
  edit_api_conflict_409:
    - GET /api/node/{vid} or POST /api/edge_detail to fetch current_version
    - retry PATCH with expected_version=current_version
```

## 17 Sensitive information
```yaml
sensitive_information:
  database_accounts:
    nebula_root:
      username: root
      password: nebula
      space: demo_kg
  env_parameters_to_override_if_moved:
    - NEBULA_HOST
    - NEBULA_PORT
    - NEBULA_USER
    - NEBULA_PASSWORD
    - NEBULA_SPACE
    - ES_URL
    - ES_INDEX
    - AUDIT_LOG_PATH
    - VITE_API_BASE_URL
  tokens:
    found_in_repo: []
  external_accounts:
    elasticsearch_auth: disabled
```
