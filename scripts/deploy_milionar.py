import paramiko
import os

HOST = '192.168.1.154'
USER = 'samuel'
PASS = 'sonaasam'
REMOTE_DIR = '/home/samuel/milionar'
LOCAL_DIR = r'c:\Users\sam\Desktop\milionar'

files_to_upload = [
    'brain/thinker.py'
]

print("Connecting to SSH...")
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=22, username=USER, password=PASS)

sftp = client.open_sftp()

for file_path in files_to_upload:
    local_path = os.path.join(LOCAL_DIR, file_path.replace('/', '\\'))
    remote_path = f"{REMOTE_DIR}/{file_path}"
    print(f"Uploading {local_path} -> {remote_path}")
    
    # Ensure remote directory exists
    remote_dir = os.path.dirname(remote_path)
    try:
        sftp.stat(remote_dir)
    except IOError:
        sftp.mkdir(remote_dir)
        
    sftp.put(local_path, remote_path)

sftp.close()

print("Restarting bot in tmux...")
# Kill existing session if it exists
stdin, stdout, stderr = client.exec_command('tmux kill-session -t milionar')
stdout.read() # Wait for it to finish

# Start new session
start_cmd = f"cd {REMOTE_DIR} && tmux new-session -d -s milionar bash ./start.sh"
stdin, stdout, stderr = client.exec_command(start_cmd)
err = stderr.read().decode()
if err:
    print(f"Error starting tmux: {err}")
else:
    print("Bot started successfully in tmux session 'milionar'!")

client.close()
