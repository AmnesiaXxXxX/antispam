import os
import time
import subprocess

def restart_app():
    process = subprocess.Popen(["python3.12", "app.py"])
    return process

def monitor_file(file_path):
    if not os.path.exists(file_path):
        print(f"Файл {file_path} не найден.")
        return
    
    last_modified_time = os.path.getmtime(file_path)
    process = restart_app()
    
    try:
        while True:
            time.sleep(1)
            current_modified_time = os.path.getmtime(file_path)
            if current_modified_time != last_modified_time:
                process.terminate()
                process = restart_app()
                last_modified_time = current_modified_time
    except KeyboardInterrupt:
        process.terminate()

if __name__ == "__main__":
    monitor_file("app.py")
