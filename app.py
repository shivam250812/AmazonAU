import os
import sys
import queue
import threading
import subprocess
from flask import Flask, render_template, request, jsonify, Response

app = Flask(__name__)

# Global state for the running pipeline
current_process = None
log_queue = queue.Queue()

def stream_logs(process):
    """Read from process stdout and stderr and put into queue."""
    for line in iter(process.stdout.readline, ''):
        if line:
            log_queue.put(line)
    process.stdout.close()
    process.wait()
    log_queue.put(f"\n[Process finished with return code {process.returncode}]\n")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/setup', methods=['POST'])
def run_setup():
    global current_process
    if current_process and current_process.poll() is None:
        return jsonify({"error": "A process is already running"}), 400

    # Clear old logs
    while not log_queue.empty():
        try:
            log_queue.get_nowait()
        except queue.Empty:
            break

    log_queue.put("[Starting Setup...]\n")
    
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    data = request.json or {}
    amazon_url = data.get('amazon_url', '').strip()
    delivery_postcode = data.get('delivery_postcode', '').strip()
    seller_login_url = data.get('seller_login_url', '').strip()
    seller_url = data.get('seller_url', '').strip()
    merchant_name = data.get('merchant_name', '').strip()
    merchant_country = data.get('merchant_country', '').strip()

    cmd = [sys.executable, "run_pipeline.py", "--setup"]
    if amazon_url:
        cmd.extend(["--amazon-url", amazon_url])
    if delivery_postcode:
        cmd.extend(["--postcode", delivery_postcode])
    if seller_login_url:
        cmd.extend(["--seller-login-url", seller_login_url])
    if seller_url:
        cmd.extend(["--seller-url", seller_url])
    if merchant_name:
        cmd.extend(["--merchant-name", merchant_name])
    if merchant_country:
        cmd.extend(["--merchant-country", merchant_country])
    current_process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1, # Line buffered
        env=env,
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    
    # Start thread to read logs
    threading.Thread(target=stream_logs, args=(current_process,), daemon=True).start()
    
    return jsonify({"message": "Setup started"})

@app.route('/api/start', methods=['POST'])
def start_pipeline():
    global current_process
    if current_process and current_process.poll() is None:
        return jsonify({"error": "A process is already running"}), 400

    data = request.json or {}
    amazon_url = data.get('amazon_url', '').strip()
    delivery_postcode = data.get('delivery_postcode', '').strip()
    topic = data.get('topic', '').strip()
    keywords = data.get('keywords', '').strip()
    min_price = data.get('min_price', '').strip()
    max_price = data.get('max_price', '').strip()
    pages = data.get('pages', '20').strip()
    seller_login_url = data.get('seller_login_url', '').strip()
    seller_url = data.get('seller_url', '').strip()
    merchant_name = data.get('merchant_name', '').strip()
    merchant_country = data.get('merchant_country', '').strip()

    cmd = [sys.executable, "run_pipeline.py"]
    if amazon_url:
        cmd.extend(["--amazon-url", amazon_url])
    if delivery_postcode:
        cmd.extend(["--postcode", delivery_postcode])
    if topic:
        cmd.extend(["--topic", topic])
    if keywords:
        cmd.extend(["--keywords", keywords])
    if min_price:
        cmd.extend(["--min-price", min_price])
    if max_price:
        cmd.extend(["--max-price", max_price])
    if pages:
        cmd.extend(["--pages", pages])
    if seller_login_url:
        cmd.extend(["--seller-login-url", seller_login_url])
    if seller_url:
        cmd.extend(["--seller-url", seller_url])
    if merchant_name:
        cmd.extend(["--merchant-name", merchant_name])
    if merchant_country:
        cmd.extend(["--merchant-country", merchant_country])

    # Clear old logs
    while not log_queue.empty():
        try:
            log_queue.get_nowait()
        except queue.Empty:
            break

    log_queue.put(f"[Starting Pipeline: {' '.join(cmd)}]\n")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    current_process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1, # Line buffered
        env=env,
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    
    # Start thread to read logs
    threading.Thread(target=stream_logs, args=(current_process,), daemon=True).start()
    
    return jsonify({"message": "Pipeline started"})

@app.route('/api/logs')
def logs():
    def generate():
        while True:
            try:
                line = log_queue.get(timeout=1.0)
                # Format for SSE
                # We need to escape newlines for data payload
                yield f"data: {line}\n\n"
            except queue.Empty:
                # Keep-alive
                yield ": keep-alive\n\n"
                
    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
