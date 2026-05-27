"""PostgreSQL SSH 隧道 — 极简版"""
import paramiko, socket, threading, select, os, sys
from dotenv import load_dotenv

load_dotenv("C:/Users/uidq1474/.ssh/server_creds.env")

REMOTE = ("127.0.0.1", 5432)

def forward(src, dst):
    try:
        while True:
            r, _, _ = select.select([src, dst], [], [], 1.0)
            if src in r:
                data = src.recv(8192)
                if not data: break
                dst.send(data)
            if dst in r:
                data = dst.recv(8192)
                if not data: break
                src.send(data)
    except: pass
    finally:
        try: src.close()
        except: pass
        try: dst.close()
        except: pass

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect("10.219.9.92", username="uidq2071", password=os.environ["SERVER_PASS"], timeout=10)
    transport = ssh.get_transport()
    print("SSH已连接")

    listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listen.bind(("127.0.0.1", 5433))
    listen.listen(10)

    print(f"隧道已启动 → localhost:5433")
    print(f"DBeaver: host=localhost port=5433 db=blackscreen user=uidq2071 pass=BlackScreen@2025")
    print(f"按 Ctrl+C 关闭")

    try:
        while True:
            sock, addr = listen.accept()
            chan = transport.open_channel("direct-tcpip", REMOTE, addr)
            if chan:
                threading.Thread(target=forward, args=(sock, chan), daemon=True).start()
            else:
                sock.close()
    except KeyboardInterrupt:
        print("\n隧道已关闭")
    finally:
        listen.close()
        ssh.close()

if __name__ == "__main__":
    main()
