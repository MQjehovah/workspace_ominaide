#!/bin/bash
docker exec omniaide_backend_1 python3 -c "from core.config.settings import settings; print(settings.cors_origins_list)" 2>/dev/null
