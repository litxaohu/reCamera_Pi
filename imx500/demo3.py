import time
import subprocess
import threading
from datetime import datetime

# 创建一个线程事件，用于接收信号量
detect_event = threading.Event()

last_log_timestamp = None  # 上次日志的时间戳
log_update_interval = 5  # 如果日志没有更新，5秒后重新播放视频
noperson_count = log_update_interval  # 计数器，用于计算没有人出现的时间

def stop_vlc():
    """Stop VLC if it's running."""
    try:
        # 查找并杀死 VLC 进程
        process = subprocess.Popen(["ps", "-A"], stdout=subprocess.PIPE)
        out, _ = process.communicate()
        for line in out.decode().splitlines():
            if "vlc" in line:
                pid = int(line.split(None, 1)[0])  # 获取PID
                subprocess.call(["kill", str(pid)])  # 使用kill命令停止VLC进程
                print(f"VLC stopped. PID: {pid}")
    except Exception as e:
        print(f"Error stopping VLC: {e}")

def start_vlc():
    """Start VLC to play video."""
    global vlc_flag
    vlc_command = "cvlc --fullscreen --loop /home/seeed/reCamera.mp4"
    subprocess.Popen(vlc_command, shell=True)
    vlc_flag = 1  # 设置vlc_flag为1，表示视频正在播放
    print("VLC started.")

def is_vlc_running():
    """Check if vlc is running."""
    process = subprocess.Popen(["ps", "-A"], stdout=subprocess.PIPE)
    out, _ = process.communicate()
    for line in out.decode().splitlines():
        if "vlc" in line:
            return True
    return False

# def monitor_log_and_control_vlc():
    # """Monitor the log file for time updates and control VLC playback."""
    # global last_log_timestamp, vlc_flag

    # while True:
    #     try:
    #         # 读取日志文件，获取 Time: 和 Total persons 的信息
    #         with open("/home/seeed/detect.log", "r") as log_file:
    #             lines = log_file.readlines()

    #         # 获取最后一行日志，并提取时间和Total persons的数量
    #         last_line = lines[-1] if lines else ""
    #         if "Time:" in last_line:
    #             # 从最后一行提取时间（Time: 2025-01-04 16:12:06）
    #             timestamp_str = last_line.split("Time:")[1].strip()
    #             current_timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")

    #             # 如果是第一次初始化或日志时间变化，则停止VLC并重置等待时间
    #             if last_log_timestamp is None:
    #                 last_log_timestamp = current_timestamp  # 初始化第一次时间
    #                 start_vlc()  # 初次启动VLC
    #             elif current_timestamp > last_log_timestamp:
    #                 print(f"Log time updated to {current_timestamp}. Stopping VLC...")
    #                 stop_vlc()
    #                 vlc_flag = 0  # 更新标志，表示视频已停止播放
    #                 last_log_timestamp = current_timestamp  # 更新日志时间戳
    #                 print("Waiting for 5 seconds before restarting VLC...")
    #                 time.sleep(5)  # 等待5秒
    #                 print("Restarting VLC...")
    #                 start_vlc()  # 重新播放视频

    #         else:
    #             print("No valid log data found in the last log entry.")
        
    #     except Exception as e:
    #         print(f"Error while monitoring log: {e}")

    #     # 如果日志文件没有更新且视频没有播放，5秒等待后重新播放视频
    #     if vlc_flag == 0 and last_log_timestamp is not None and time.time() - last_log_timestamp.timestamp() >= log_update_interval:
    #         print("No new log data. Restarting VLC...")
    #         start_vlc()  # 重新启动VLC
    #         last_log_timestamp = datetime.now()  # 更新为当前时间，避免过度启动

    #     time.sleep(1)  # 每1秒检查一次日志

def monitor_log_and_control_vlc():
    global noperson_count, vlc_flag

    """Monitor the log file for time updates and control VLC playback."""
    while True:
        try:
            # 读取日志文件，获取 Time: 和 Total persons 的信息
            with open("/home/seeed/detect.log", "r") as log_file:
                lines = log_file.readlines()

            # 获取最后一行日志，并提取时间和Total persons的数量
            last_line = lines[-1] if lines else ""
            if "Time:" in last_line:
                # 从最后一行提取时间（Time: 2025-01-04 16:12:06）
                timestamp_str = last_line.split("Time:")[1].split(",")[0].strip()
                current_timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                have_person = last_line.split("Detected person:")[1].split(",")[0].strip().lower() == 'true'

                if have_person:
                    noperson_count = 0
                else:
                    noperson_count += 1
                
            else:
                print("No valid log data found in the last log entry.")
        
        except Exception as e:
            print(f"Error while monitoring log: {e}")

        vlc_flag = is_vlc_running  # 更新标志，表示视频已停止播放

        if noperson_count >= log_update_interval and not is_vlc_running():
            print(f"No person detected for {noperson_count} seconds. Restarting VLC...")
            start_vlc()
        elif noperson_count < log_update_interval and is_vlc_running():
            print(f"Person detected. Stopping VLC...")
            stop_vlc()

        time.sleep(1)  # 每1秒检查一次日志
    

# 启动监听线程，监听日志文件
threading.Thread(target=monitor_log_and_control_vlc, daemon=True).start()

# 进入主程序的循环或其他逻辑，模拟实时检测
while True:
    # 模拟检测到人的信号
    user_input = input("Press 'y' to simulate detection signal: ")
    if user_input.lower() == 'y':
        detect_event.set()  # 设置信号量，模拟检测到人
    time.sleep(0.5)
