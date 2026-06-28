import paramiko
import os

HOST = '192.168.1.154'
USER = 'samuel'
PASS = 'sonaasam'
REMOTE_DIR = '/home/samuel/milionar'

files_to_upload = [
    r'c:\Users\sam\Desktop\milionar\main.py',
    r'c:\Users\sam\Desktop\milionar\config.py',
    r'c:\Users\sam\Desktop\milionar\brain\prompts.py',
    r'c:\Users\sam\Desktop\milionar\brain\thinker.py',
    r'c:\Users\sam\Desktop\milionar\brain\tools.py',
    r'c:\Users\sam\Desktop\milionar\market\scanner.py',
    r'c:\Users\sam\Desktop\milionar\trader\risk.py',
    r'c:\Users\sam\Desktop\milionar\trader\executor.py'
]

print("Connecting to SSH...")
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=22, username=USER, password=PASS)
sftp = client.open_sftp()

for f_path in files_to_upload:
    remote_path = f_path.replace('c:\\Users\\sam\\Desktop\\milionar\\', 'milionar/')
    remote_path = remote_path.replace('\\', '/')
    print(f"Uploading {f_path} to {remote_path}")
    sftp.put(f_path, remote_path)
    
sftp.close()

print("Restarting bot...")
stdin, stdout, stderr = client.exec_command('tmux kill-session -t milionar')
stdout.read()
start_cmd = f"cd {REMOTE_DIR} && tmux new-session -d -s milionar bash ./start.sh"
stdin, stdout, stderr = client.exec_command(start_cmd)
err = stderr.read().decode()
if err and "duplicate session" not in err:
    print(f"Error starting tmux: {err}")
else:
    print("Bot restarted!")

client.close()
