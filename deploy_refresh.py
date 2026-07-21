import paramiko, select, sys, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('mqgeek.com', port=22, username='jmq', password='Jmq88326', timeout=30)

sftp = ssh.open_sftp()
files = [
    r"E:\workspace_ominaide\backend\core\config\settings.py",
    r"E:\workspace_ominaide\backend\core\auth\jwt.py",
    r"E:\workspace_ominaide\backend\core\auth\domain\service.py",
    r"E:\workspace_ominaide\backend\core\auth\domain\schemas.py",
    r"E:\workspace_ominaide\backend\core\auth\domain\router.py",
]
for local in files:
    remote = local.replace(r"E:\workspace_ominaide", "/home/jmq/omniaide").replace("\\", "/")
    sftp.put(local, remote)
sftp.close()

transport = ssh.get_transport()
channel = transport.open_session()
channel.exec_command("""
export PATH="$HOME/.local/bin:$PATH"
cd /home/jmq/omniaide
docker-compose build backend 2>&1
echo "===BUILD==="
docker-compose up -d 2>&1
echo "===UP==="
sleep 3
curl -s http://localhost:8000/api/auth/login -X POST -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}'
""")

while True:
    if channel.recv_ready():
        data = channel.recv(8192).decode('utf-8', errors='replace')
        print(data, end='')
        sys.stdout.flush()
    if channel.recv_stderr_ready():
        data = channel.recv_stderr(8192).decode('utf-8', errors='replace')
        print(data, end='', file=sys.stderr)
        sys.stdout.flush()
    if channel.exit_status_ready():
        break
    time.sleep(0.1)

print(f"\nExit: {channel.recv_exit_status()}", flush=True)
ssh.close()
