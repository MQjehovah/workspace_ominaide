#!/bin/bash
docker exec omniaide_mysql_1 mysql -uomniaide -pomniaide_pass --default-character-set=utf8mb4 omniaide -e "SELECT id, HEX(title) as hex_title FROM plugin_notes ORDER BY id DESC LIMIT 5" 2>/dev/null
