import socket
import threading
import json
import time
from flask import Flask, request, render_template, redirect, url_for
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException

app = Flask(__name__)

class StratumServer:
    def __init__(self, host, port, pool_url, pool_port, username, password, rpc_user, rpc_password, rpc_host='localhost', rpc_port=8332):
        self.host = host
        self.port = port
        self.pool_url = pool_url
        self.pool_port = pool_port
        self.username = username
        self.password = password
        self.rpc_user = rpc_user
        self.rpc_password = rpc_password
        self.rpc_host = rpc_host
        self.rpc_port = rpc_port
        self.difficulty_mode = 'normal'  # Default to normal difficulty
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.bind_socket(self.server_socket, self.host, self.port)
        self.server_socket.listen(10)
        print(f"Stratum server started on {self.host}:{self.port}")
        self.rpc_connection = AuthServiceProxy(f"http://{self.rpc_user}:{self.rpc_password}@{self.rpc_host}:{self.rpc_port}")
        self.miners_connected = 0
        self.best_share = 0
        self.total_shares = 0
        self.rejected_shares = 0
        self.current_difficulty = 16  # Default normal difficulty
        self.auto_increase_thread = threading.Thread(target=self.auto_increase_difficulty)
        self.auto_increase_thread.daemon = True
        self.auto_increase_thread.start()

    def bind_socket(self, sock, host, port):
        while True:
            try:
                sock.bind((host, port))
                return
            except OSError as e:
                if e.errno == 10048:  # Port already in use
                    print(f"Port {port} is in use. Trying next port...")
                    port += 1
                else:
                    raise

    def handle_client(self, client_socket):
        self.miners_connected += 1
        try:
            request = client_socket.recv(1024).decode('utf-8')
            print(f"Received: {request}")

            # Simulate share submission
            share_value = self.simulate_share()
            self.total_shares += 1
            if self.is_stale(share_value):
                self.rejected_shares += 1
                response = {"result": None, "error": "Stale share", "id": None}
            elif self.is_rejected(share_value):
                self.rejected_shares += 1
                response = {"result": None, "error": "Rejected share", "id": None}
            else:
                if share_value > self.best_share:
                    self.best_share = share_value
                response = {
                    "autononce": True,
                    "autoversionmask": True,
                    "autodifficulty": True,
                    "pool": {
                        "url": self.pool_url,
                        "port": self.pool_port,
                        "user": self.username,
                        "password": self.password
                    },
                    "tcp": {
                        "listen": self.host,
                        "port": self.port
                    },
                    "target": {
                        "difficulty": "auto",
                        "versionmask": "auto"
                    }
                }

            # Adjust difficulty based on mode
            if self.difficulty_mode == 'low':
                self.current_difficulty = 1
            elif self.difficulty_mode == 'medium':
                self.current_difficulty = 256
            elif self.difficulty_mode == 'high':
                self.current_difficulty = 4096
            elif self.difficulty_mode == 'agresif':
                self.adjust_aggressive_difficulty()
            elif self.difficulty_mode == 'agresif_pool':
                self.adjust_aggressive_pool_difficulty()
            else:
                self.current_difficulty = 16  # Default normal difficulty

            response["target"]["difficulty"] = self.current_difficulty
            client_socket.send(json.dumps(response).encode('utf-8'))
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            client_socket.close()
            self.miners_connected -= 1

    def adjust_aggressive_difficulty(self):
        # Example logic to adjust difficulty aggressively
        if self.miners_connected > 5:
            self.current_difficulty += 10
        else:
            self.current_difficulty -= 1
        if self.current_difficulty < 1:
            self.current_difficulty = 1

    def adjust_aggressive_pool_difficulty(self):
        # Example logic to adjust difficulty aggressively based on pool conditions
        try:
            pool_stats = self.rpc_connection.getmininginfo()
            network_difficulty = pool_stats['difficulty']
            hashrate = pool_stats['networkhashps']

            # Example condition to adjust difficulty
            if hashrate > 1e12:  # If hashrate is higher than 1 TH/s
                self.current_difficulty = network_difficulty * 2
            else:
                self.current_difficulty = network_difficulty / 2

            if self.current_difficulty < 1:
                self.current_difficulty = 1
        except JSONRPCException as e:
            print(f"Error adjusting pool difficulty: {e}")

    def simulate_share(self):
        import random
        return random.randint(1, 10000)

    def is_stale(self, share_value):
        return share_value % 10 == 0  # Example condition for stale share

    def is_rejected(self, share_value):
        return share_value % 5 == 0  # Example condition for rejected share

    def auto_increase_difficulty(self):
        while True:
            time.sleep(600)  # Adjust every 10 minutes
            self.current_difficulty += 1
            print(f"Auto-increased difficulty to {self.current_difficulty}")
            if self.current_difficulty < 1:
                self.current_difficulty = 1

    def run(self):
        while True:
            client_socket, addr = self.server_socket.accept()
            client_handler = threading.Thread(target=self.handle_client, args=(client_socket,))
            client_handler.start()

@app.route('/')
def index():
    return render_template('index.html', 
                           miners_connected=stratum_server.miners_connected, 
                           best_share=stratum_server.best_share, 
                           total_shares=stratum_server.total_shares, 
                           rejected_shares=stratum_server.rejected_shares, 
                           current_difficulty=stratum_server.current_difficulty)

@app.route('/set_difficulty', methods=['POST'])
def set_difficulty():
    mode = request.form.get('mode')
    if mode in ['low', 'normal', 'medium', 'high', 'agresif', 'agresif_pool']:
        stratum_server.difficulty_mode = mode
    return redirect(url_for('index'))

@app.route('/update_pool_settings', methods=['POST'])
def update_pool_settings():
    pool_url = request.form.get('pool_url')
    pool_port = request.form.get('pool_port')
    listen_port = request.form.get('listen_port')
    
    if pool_url and pool_port and listen_port:
        stratum_server.pool_url = pool_url
        stratum_server.pool_port = int(pool_port)
        stratum_server.port = int(listen_port)
        stratum_server.server_socket.close()
        stratum_server.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        stratum_server.bind_socket(stratum_server.server_socket, stratum_server.host, stratum_server.port)
        stratum_server.server_socket.listen(10)
        
    return redirect(url_for('index'))

if __name__ == "__main__":
    stratum_server = StratumServer(
        host='0.0.0.0',
        port=6661,  # Ganti ini dengan port yang berbeda jika diperlukan
        pool_url='stratum+tcp://examplepool.com',
        pool_port=6661,
        username='user',
        password='password',
        rpc_user='rpcuser',
        rpc_password='rpcpassword'
    )
    server_thread = threading.Thread(target=stratum_server.run)
    server_thread.start()
    app.run(host='0.0.0.0', port=5000)
