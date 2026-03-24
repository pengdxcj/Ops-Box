import uvicorn
import webbrowser
import threading
import time
from app.main import app

def run_server():
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False
    )

if __name__ == "__main__":
    # 启动服务器线程
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # 等待服务器启动
    print("Starting server...")
    time.sleep(2)
    
    # 打开浏览器
    print("Opening browser...")
    webbrowser.open('http://127.0.0.1:8000/')
    
    # 保持主线程运行
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down server...")
