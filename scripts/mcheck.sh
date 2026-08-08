#!/bin/bash
docker exec omniaide_backend_1 python3 -c "
import app as a
stack = a.app.user_middleware
for m in stack:
    print(m.cls.__name__)
" 2>/dev/null
